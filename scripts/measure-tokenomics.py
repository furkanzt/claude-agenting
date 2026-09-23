#!/usr/bin/env python3
"""
measure-tokenomics.py -- reproduce the main/agent spend split, spawn tax, and
effort-distribution numbers documented in the README's "Verified facts"
section, from real ~/.claude/projects transcript data.

WHY THIS EXISTS
---------------
Those numbers were first derived by hand, once, from a live investigation.
This script makes the method repeatable: point it at a projects directory and
a window, and it recomputes them from whatever transcripts exist now.

METHOD
------
- A transcript line is not an API call. Streamed messages write partial lines
  before the final one; only the LAST line per message.id is a real call.
  Every count/cost below is post-dedup.
- "Main session" calls are top-level */*.jsonl files directly under the
  projects dir (one per Claude Code session).
- "Agent" calls are every agent-*.jsonl found anywhere under a session's
  subagents/ or workflows/ subdirectories (both `Agent` tool spawns and
  Workflow-tool agent() calls land there).
- Sidechain messages (isSidechain: true) inside a main-session file are
  excluded from "main" -- they belong to an agent, not the session itself.
- Cost is list price: input * price_in, cache-read * price_in * 0.1,
  cache-write * price_in * 1.25 (5-min default -- this under-counts sessions
  that actually got 1h writes, which cost 2x; a nudge, not a bill), output *
  price_out.
- "Spawn tax" is each agent's FIRST call's cache-write (a cold start is
  always a full rewrite), median across all agents in the window.

Run it: python3 scripts/measure-tokenomics.py [--days N] [--projects-dir DIR]
"""
import argparse
import glob
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRICES_PER_MTOK = {  # (input, output) $/MTok, list price
    "haiku": (1.00, 5.00),
    "sonnet": (3.00, 15.00),
    "opus": (5.00, 25.00),
    "fable": (10.00, 50.00),
}
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25  # 5-min default; 1h writes are 2x (under-counts those)


def price_for(model_id):
    model_id = (model_id or "").lower()
    for key, price in PRICES_PER_MTOK.items():
        if key in model_id:
            return price
    return None


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def dedup_assistant_lines(path, main_only=False):
    """Return (deduped assistant-line dicts in first-seen order, raw count)."""
    raw = 0
    last_by_id = {}
    order = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "assistant":
                    continue
                if main_only and d.get("isSidechain"):
                    continue
                raw += 1
                mid = d.get("message", {}).get("id")
                if mid is None:
                    continue
                if mid not in last_by_id:
                    order.append(mid)
                last_by_id[mid] = d
    except Exception:
        return [], 0
    return [last_by_id[m] for m in order], raw


def call_cost(d):
    u = d.get("message", {}).get("usage", {}) or {}
    price = price_for(d.get("message", {}).get("model"))
    if not price:
        return 0.0
    p_in, p_out = price
    input_tok = u.get("input_tokens", 0) or 0
    cache_read = u.get("cache_read_input_tokens", 0) or 0
    cache_write = u.get("cache_creation_input_tokens", 0) or 0
    output_tok = u.get("output_tokens", 0) or 0
    return (
        input_tok * p_in
        + cache_read * p_in * CACHE_READ_MULT
        + cache_write * p_in * CACHE_WRITE_MULT
        + output_tok * p_out
    ) / 1_000_000


def context_size(d):
    u = d.get("message", {}).get("usage", {}) or {}
    return (
        (u.get("input_tokens", 0) or 0)
        + (u.get("cache_read_input_tokens", 0) or 0)
        + (u.get("cache_creation_input_tokens", 0) or 0)
    )


def summarize(calls, raw_count, label):
    n = len(calls)
    if n == 0:
        print(f"{label}: 0 calls in window")
        return 0, 0.0
    cost = sum(call_cost(d) for d in calls)
    avg_ctx = statistics.mean(context_size(d) for d in calls)
    dedup_factor = raw_count / n if n else 0
    print(
        f"{label}: {n:,} calls (raw {raw_count:,}, dedup {dedup_factor:.2f}x), "
        f"avg context {avg_ctx:,.0f}, cost ${cost:,.2f}, ${cost / n:.3f}/call"
    )
    return n, cost


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=21, help="window size in days (default 21 -- \"three weeks\")")
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument(
        "--effort-cutoff",
        default="2026-08-06T22:31:00+00:00",
        help="ISO timestamp splitting the agent effort-distribution before/after (default: this skill's birth)",
    )
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    effort_cutoff = parse_ts(args.effort_cutoff)
    root = Path(args.projects_dir)

    if not root.is_dir():
        print(f"No such projects dir: {root}", file=sys.stderr)
        sys.exit(1)

    # mtime pre-filter: skip files that could not contain in-window lines.
    # (A file can be older than its last line only if still being appended to
    # right at the cutoff boundary, which self-corrects on the next run.)
    main_files = [p for p in root.glob("*/*.jsonl") if p.stat().st_mtime >= cutoff.timestamp()]
    agent_files = [
        Path(p)
        for p in glob.glob(str(root / "**" / "agent-*.jsonl"), recursive=True)
        if Path(p).stat().st_mtime >= cutoff.timestamp()
    ]

    main_calls, main_raw = [], 0
    for fp in main_files:
        deduped, raw = dedup_assistant_lines(fp, main_only=True)
        main_raw += raw
        main_calls.extend(d for d in deduped if (ts := parse_ts(d.get("timestamp"))) and ts >= cutoff)

    agent_calls, agent_raw = [], 0
    agent_first_call = {}  # agentId (or file path if missing) -> earliest in-window call
    for fp in agent_files:
        deduped, raw = dedup_assistant_lines(fp, main_only=False)
        agent_raw += raw
        for d in deduped:
            ts = parse_ts(d.get("timestamp"))
            if not ts or ts < cutoff:
                continue
            agent_calls.append(d)
            aid = d.get("agentId") or str(fp)
            prev = agent_first_call.get(aid)
            if prev is None or ts < parse_ts(prev.get("timestamp")):
                agent_first_call[aid] = d

    print(f"Window: last {args.days} days (since {cutoff.date().isoformat()})")
    print(f"Scanned {len(main_files)} main session files, {len(agent_files)} agent files\n")

    n_main, cost_main = summarize(main_calls, main_raw, "Main session")
    n_agent, cost_agent = summarize(agent_calls, agent_raw, "Agents")
    print(f"\nTotal shadow cost: ${cost_main + cost_agent:,.2f} (main ${cost_main:,.2f} / agents ${cost_agent:,.2f})")
    print(f"Distinct agents: {len(agent_first_call):,}")

    spawn_writes, spawn_costs = [], []
    for d in agent_first_call.values():
        w = (d.get("message", {}).get("usage", {}) or {}).get("cache_creation_input_tokens", 0) or 0
        if w:
            spawn_writes.append(w)
            spawn_costs.append(call_cost(d))
    if spawn_writes:
        print(
            f"\nSpawn tax: median first-call cache-write {statistics.median(spawn_writes):,.0f} tokens "
            f"(~${statistics.median(spawn_costs):.3f}/spawn), total across window ~${sum(spawn_costs):,.2f}"
        )

    if effort_cutoff:
        before = [d.get("effort") for d in agent_calls if (ts := parse_ts(d.get("timestamp"))) and ts < effort_cutoff]
        after = [d.get("effort") for d in agent_calls if (ts := parse_ts(d.get("timestamp"))) and ts >= effort_cutoff]

        def dist(lst):
            if not lst:
                return "(no calls in this range)"
            c = Counter(lst)
            return ", ".join(f"{k}={v / len(lst) * 100:.0f}%" for k, v in c.most_common())

        print(f"\nAgent effort distribution before {args.effort_cutoff}: {dist(before)}")
        print(f"Agent effort distribution after:  {dist(after)}")


if __name__ == "__main__":
    main()
