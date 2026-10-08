#!/usr/bin/env python3
"""
measure-tokenomics.py -- the plugin's cost meter, run on real ~/.claude/projects
transcripts.

Two reports:

  measure-tokenomics.py [overview] [--days N] [--projects-dir DIR]
      The main/agent spend split, spawn tax and effort distribution documented in
      the README's "Verified facts" section.

  measure-tokenomics.py anatomy [--days N] [--projects-dir DIR]
                                [--min-agents N] [--format text|json] [--out FILE]
                                [--by-type]
      What a Workflow agent costs to START, from the local Workflow transcripts:
      first-call context, how much of it was written to cache fresh, the 5m/1h
      split, whole-agent cost per category, advisor cost, and the size (never the
      content) of what Claude Code attached before the first call. Aggregates
      only: no prompt, response, path, label or id is printed or written.

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
  Synthetic zero-token lines (model "<synthetic>") are not API calls and are
  skipped.
- Dedup is per file: the same message.id in two files would count twice. (In
  real transcripts it does not occur.) A malformed line is skipped, not the file.
- Cost is LIST PRICE, per category, from PRICES below (a table dated
  PRICES_AS_OF, keyed by model id; a trailing -YYYYMMDD date or [..] suffix on the
  id is ignored, anything else is a different, unpriced model): uncached input, cache reads, 5-minute
  cache writes, 1-hour cache writes (both read from usage.cache_creation) and
  output. A record with no 5m/1h split is priced as a 5-minute write and counted
  in the footer. A model id that is not in the table is "unpriced": its tokens
  are counted and listed in the footer, its dollars are not guessed.
- Advisor iterations (usage.iterations entries of type "advisor_message") are
  billed at the advisor model's own rates and are NOT part of the top-level
  usage numbers, so they are priced separately and added to the call's cost.
- "Spawn tax" is each agent's FIRST call's cache-write (a cold start is a full
  rewrite of whatever was not already cached), median across all agents in the
  window, priced at the write rates only. (The 2026-08-10 README figure priced the
  whole first call.)
- p90 is nearest-rank, so it equals the maximum for groups below ten agents.
- Under a subscription, dollars here are a consumption indicator, not a bill,
  and the effect on a usage window was not measured.

Fields in the transcripts are undocumented and may change; the figures are only
as good as the coverage printed beside them (usage.iterations and thinking token
counts appear on only part of the messages, so advisor and thinking figures are
floors).
"""
import argparse
import glob
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import tempfile
from collections import Counter, defaultdict, namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRICES_AS_OF = "2026-10-05"
PRICE_SOURCE = "evals/research/2026-10-05-models.md, section 1"

Price = namedtuple("Price", "input output read write_5m write_1h derived")


def _price(inp, out, read, derived=False):
    # Every row on the price page has 5-minute writes at 1.25x and 1-hour writes
    # at 2x the input price, so the write columns follow from the input price.
    return Price(inp, out, read, inp * 1.25, inp * 2.0, derived)


# $/MTok, list price, keyed by EXACT model id. derived=True marks a row with at
# least one column not read directly from the price page (see PRICE_NOTES).
PRICES = {
    "claude-haiku-4-5-20251001": _price(1, 5, 0.10),
    "claude-haiku-4-5": _price(1, 5, 0.10),
    "claude-sonnet-5-5": _price(2, 10, 0.20),
    "claude-opus-5-5": _price(4, 20, 0.20),
    "claude-fable-5-1": _price(10, 50, 0.25),
    # previous generation: still common in older transcripts
    "claude-opus-5": _price(5, 25, 0.50, derived=True),
    "claude-fable-5": _price(10, 50, 1.00, derived=True),
    "claude-sonnet-5": _price(2, 10, 0.20, derived=True),
}
PRICE_NOTES = {
    "claude-opus-5": "input, output and cache read documented; write columns follow the 1.25x/2x rule",
    "claude-fable-5": "input, output and cache read documented; write columns follow the 1.25x/2x rule",
    "claude-sonnet-5": "input and output documented; cache read assumed 0.1x input",
}

CATS = ("input", "cache_read", "write_5m", "write_1h", "output", "advisor")
GENERIC_AGENT_TYPES = {"", "workflow-subagent"}
VALID_FORMATS = ("text", "json")


def norm_model(model_id):
    """Lower-case model id without a trailing [..] or -YYYYMMDD suffix ('' when it is not a string)."""
    mid = re.sub(r"\[[^\]]*\]$", "", model_id.strip().lower()) if isinstance(model_id, str) else ""
    return mid if mid in PRICES else re.sub(r"-\d{8}$", "", mid)


def price_for(model_id):
    """Price row for a model id (a trailing -YYYYMMDD or [..] suffix is ignored), else None."""
    return PRICES.get(norm_model(model_id))


def num(x):
    """A token count from a transcript field: a non-negative number, else 0."""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else 0


def parse_ts(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue  # one odd record must not discard the file
                if main_only and d.get("isSidechain"):
                    continue
                raw += 1
                mid = msg.get("id")
                if not isinstance(mid, str):
                    continue
                if mid not in last_by_id:
                    order.append(mid)
                last_by_id[mid] = d
    except Exception:
        return [], 0
    return [last_by_id[m] for m in order], raw


def is_synthetic(d):
    return (d.get("message") or {}).get("model") == "<synthetic>"


def mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


# ---------------------------------------------------------------- cost model


def split_writes(u):
    """(write_5m tokens, write_1h tokens, legacy) from one usage block.

    legacy is True when the block has cache writes but no 5m/1h split; those
    tokens are priced as 5-minute writes.
    """
    total = num(u.get("cache_creation_input_tokens"))
    cc = u.get("cache_creation")
    if isinstance(cc, dict):
        w5 = num(cc.get("ephemeral_5m_input_tokens"))
        w1 = num(cc.get("ephemeral_1h_input_tokens"))
        if w5 + w1 < total:  # a split that does not add up: the remainder is a 5-minute write
            w5 += total - w5 - w1
        return w5, w1, False
    return total, 0, total > 0


def usage_parts(u, model):
    """(dollars by category, tokens by category, priced, legacy_write) for one usage block."""
    if not isinstance(u, dict):
        u = {}
    w5, w1, legacy = split_writes(u)
    tok = {
        "input": num(u.get("input_tokens")),
        "cache_read": num(u.get("cache_read_input_tokens")),
        "write_5m": w5,
        "write_1h": w1,
        "output": num(u.get("output_tokens")),
    }
    usd = dict.fromkeys(CATS, 0.0)
    price = price_for(model)
    if price:
        usd["input"] = tok["input"] * price.input / 1e6
        usd["cache_read"] = tok["cache_read"] * price.read / 1e6
        usd["write_5m"] = w5 * price.write_5m / 1e6
        usd["write_1h"] = w1 * price.write_1h / 1e6
        usd["output"] = tok["output"] * price.output / 1e6
    return usd, tok, price is not None, legacy


class CallParts:
    """Cost and token breakdown of one deduplicated API call, advisor iterations included."""

    def __init__(self, d):
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        u = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
        self.model = msg.get("model") if isinstance(msg.get("model"), str) else None
        self.usd, self.tok, priced, self.legacy_write = usage_parts(u, self.model)
        self.unpriced = Counter()  # model id -> tokens
        if not priced:
            self.unpriced[self.model or "(none)"] += sum(self.tok.values())
        self.advisor_calls = 0
        self.has_iterations = "iterations" in u
        iterations = u.get("iterations") if isinstance(u.get("iterations"), list) else []
        for it in iterations:
            if not isinstance(it, dict) or it.get("type") != "advisor_message":
                continue
            a_usd, a_tok, a_priced, a_legacy = usage_parts(it, it.get("model"))
            self.usd["advisor"] += sum(a_usd.values())
            self.advisor_calls += 1
            self.legacy_write = self.legacy_write or a_legacy
            if not a_priced:
                a_model = it.get("model")
                self.unpriced[a_model if isinstance(a_model, str) and a_model else "(none)"] += sum(a_tok.values())
        self.context = self.tok["input"] + self.tok["cache_read"] + self.tok["write_5m"] + self.tok["write_1h"]
        self.fresh_write = self.tok["write_5m"] + self.tok["write_1h"]
        self.total = sum(self.usd.values())
        details = u.get("output_tokens_details")
        thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
        self.thinking = thinking if isinstance(thinking, int) else None

    @property
    def write_cost(self):
        return self.usd["write_5m"] + self.usd["write_1h"]


class Footer:
    """Things a reader must know before trusting a figure."""

    def __init__(self):
        self.unpriced_calls = Counter()
        self.unpriced_tokens = Counter()
        self.legacy_calls = 0
        self.synthetic_skipped = 0
        self.derived_models = set()

    def add(self, parts_list):
        for p in parts_list:
            if p.unpriced:
                for model, tokens in p.unpriced.items():
                    self.unpriced_calls[model] += 1
                    self.unpriced_tokens[model] += tokens
            if p.legacy_write:
                self.legacy_calls += 1
            price = price_for(p.model)
            if price and price.derived:
                self.derived_models.add(norm_model(p.model))

    def lines(self):
        out = []
        for model in sorted(self.unpriced_calls):
            out.append(
                f"unpriced model {model}: {self.unpriced_calls[model]:,} calls, "
                f"{self.unpriced_tokens[model]:,} tokens counted, $0 in the totals"
            )
        if self.legacy_calls:
            out.append(f"{self.legacy_calls:,} call(s) had no 5m/1h cache-write split and were priced as 5-minute writes")
        if self.synthetic_skipped:
            out.append(f"{self.synthetic_skipped:,} synthetic zero-token line(s) skipped")
        for model in sorted(self.derived_models):
            out.append(f"price row {model} is partly derived: {PRICE_NOTES.get(model, 'see PRICES')}")
        return out


def price_header():
    return (
        f"Prices: list price, table dated {PRICES_AS_OF} ({PRICE_SOURCE}); advisor iterations are priced at "
        "their own model. Dollars are a consumption indicator, not a bill; the usage-window effect is not measured."
    )


# ------------------------------------------------------------------ overview


def summarize(parts, raw_count, label):
    n = len(parts)
    if n == 0:
        print(f"{label}: 0 calls in window")
        return 0, 0.0, 0.0
    cost = sum(p.total for p in parts)
    advisor = sum(p.usd["advisor"] for p in parts)
    avg_ctx = statistics.mean(p.context for p in parts)
    dedup_factor = raw_count / n if n else 0
    print(
        f"{label}: {n:,} calls (raw {raw_count:,}, dedup {dedup_factor:.2f}x), "
        f"avg context {avg_ctx:,.0f}, cost ${cost:,.2f}, ${cost / n:.3f}/call"
        + (f" (advisor ${advisor:,.2f} of it)" if advisor else "")
    )
    return n, cost, advisor


def write_share_line(parts, label):
    w1 = sum(p.tok["write_1h"] for p in parts)
    w5 = sum(p.tok["write_5m"] for p in parts)
    if not w1 + w5:
        return None
    return f"{label}: {w1 / (w1 + w5) * 100:.0f}% of {w1 + w5:,} cache-write tokens were 1-hour writes"


def cmd_overview(args):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    effort_cutoff = parse_ts(args.effort_cutoff)
    root = Path(args.projects_dir)

    if not root.is_dir():
        print(f"No such projects dir: {root}", file=sys.stderr)
        return 1

    footer = Footer()

    # mtime pre-filter: skip files that could not contain in-window lines.
    # (A file can be older than its last line only if still being appended to
    # right at the cutoff boundary, which self-corrects on the next run.)
    main_files = [p for p in root.glob("*/*.jsonl") if mtime(p) >= cutoff.timestamp()]
    agent_files = [
        Path(p)
        for p in glob.glob(str(root / "**" / "agent-*.jsonl"), recursive=True)
        if mtime(p) >= cutoff.timestamp()
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
            aid = str(d.get("agentId") or fp)
            prev = agent_first_call.get(aid)
            if prev is None or ts < parse_ts(prev.get("timestamp")):
                agent_first_call[aid] = d

    synthetic_main = sum(1 for d in main_calls if is_synthetic(d))
    synthetic_agent = sum(1 for d in agent_calls if is_synthetic(d))
    footer.synthetic_skipped = synthetic_main + synthetic_agent
    main_raw -= synthetic_main      # a synthetic line is not a call, so it must not inflate the dedup factor
    agent_raw -= synthetic_agent
    main_calls = [d for d in main_calls if not is_synthetic(d)]
    agent_calls = [d for d in agent_calls if not is_synthetic(d)]
    agent_first_call = {k: d for k, d in agent_first_call.items() if not is_synthetic(d)}

    main_parts = [CallParts(d) for d in main_calls]
    agent_parts = [CallParts(d) for d in agent_calls]
    footer.add(main_parts)
    footer.add(agent_parts)

    print(price_header())
    print(f"Window: last {args.days} days (since {cutoff.date().isoformat()})")
    print(f"Scanned {len(main_files)} main session files, {len(agent_files)} agent files\n")

    n_main, cost_main, adv_main = summarize(main_parts, main_raw, "Main session")
    n_agent, cost_agent, adv_agent = summarize(agent_parts, agent_raw, "Agents")
    print(f"\nTotal shadow cost: ${cost_main + cost_agent:,.2f} (main ${cost_main:,.2f} / agents ${cost_agent:,.2f})")
    advisor_calls = sum(p.advisor_calls for p in main_parts + agent_parts)
    if advisor_calls:
        print(
            f"  of which advisor iterations: ${adv_main + adv_agent:,.2f} over {advisor_calls:,} advisor calls "
            "(billed on top of the top-level usage numbers)"
        )
    for line in (write_share_line(main_parts, "Main session"), write_share_line(agent_parts, "Agents")):
        if line:
            print(f"  {line}")
    print(f"Distinct agents: {len(agent_first_call):,}")

    spawn_writes, spawn_costs = [], []
    for d in agent_first_call.values():
        p = CallParts(d)
        if p.fresh_write:
            spawn_writes.append(p.fresh_write)
            spawn_costs.append(p.write_cost)
    if spawn_writes:
        print(
            f"\nSpawn tax: median first-call cache-write {statistics.median(spawn_writes):,.0f} tokens "
            f"(~${statistics.median(spawn_costs):.3f}/spawn at the write rates), total across window ~${sum(spawn_costs):,.2f}"
        )

    if effort_cutoff:
        before = [str(d.get("effort")) for d in agent_calls if (ts := parse_ts(d.get("timestamp"))) and ts < effort_cutoff]
        after = [str(d.get("effort")) for d in agent_calls if (ts := parse_ts(d.get("timestamp"))) and ts >= effort_cutoff]

        def dist(lst):
            if not lst:
                return "(no calls in this range)"
            c = Counter(lst)
            return ", ".join(f"{k}={v / len(lst) * 100:.0f}%" for k, v in c.most_common())

        print(f"\nAgent effort distribution before {args.effort_cutoff}: {dist(before)}")
        print(f"Agent effort distribution after:  {dist(after)}")

    notes = footer.lines()
    if notes:
        print("\nNotes:")
        for line in notes:
            print(f"  - {line}")
    return 0


# ------------------------------------------------------------------- anatomy


def load_check_journal():
    """The finish-check hook's journal logic, imported so both always count agents the same way."""
    path = Path(__file__).resolve().parent.parent / "hooks" / "workflow-finish-check.py"
    try:
        spec = importlib.util.spec_from_file_location("agenting_workflow_finish_check", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.check_journal
    except Exception:
        return None


def pctl(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def med(values):
    return statistics.median(values) if values else None


def read_pre_attachments(path):
    """[(attachment type, character count)] for attachment records before the first assistant record."""
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("type") == "assistant":
                    break
                if rec.get("type") == "attachment":
                    att = rec.get("attachment") or {}
                    out.append((str(att.get("type") or "?"), len(json.dumps(att, ensure_ascii=False))))
    except Exception:
        pass
    return out


def read_meta(agent_path):
    meta_path = str(agent_path)[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def analyze_agent(path, cutoff):
    """One agent's launch anatomy, or None when it has no priced-or-unpriced call in the window."""
    calls, _ = dedup_assistant_lines(path)
    calls = [d for d in calls if not is_synthetic(d)]
    if not calls:
        return None
    first_ts = parse_ts(calls[0].get("timestamp"))
    if not first_ts or first_ts < cutoff:
        return None
    parts = [CallParts(d) for d in calls]
    first = parts[0]
    meta = read_meta(path)
    agent_type = str(meta.get("agentType") or "")
    attachments = read_pre_attachments(path)
    w5 = sum(p.tok["write_5m"] for p in parts)
    w1 = sum(p.tok["write_1h"] for p in parts)
    thinking = [p.thinking for p in parts if p.thinking is not None]
    return {
        "first_ts": first_ts,
        "model": first.model or "n/a",
        "effort": str(calls[0].get("effort") or "n/a"),
        "agent_type": agent_type,
        "kind": "generic" if agent_type in GENERIC_AGENT_TYPES else "typed",
        "skill_listing": any(t == "skill_listing" for t, _ in attachments),
        "attachments": attachments,
        "first_context": first.context,
        "first_fresh": first.fresh_write,
        "first_read": first.tok["cache_read"],
        "first_input": first.tok["input"],
        "calls": len(parts),
        "cost": sum(p.total for p in parts),
        "advisor_cost": sum(p.usd["advisor"] for p in parts),
        "advisor_calls": sum(p.advisor_calls for p in parts),
        "write_5m": w5,
        "write_1h": w1,
        "iterations_calls": sum(1 for p in parts if p.has_iterations),
        "thinking_calls": len(thinking),
        "thinking_total": sum(thinking) if thinking else None,
        "parts": parts,
    }


def rank_bucket(rank):
    return "0" if rank == 0 else "1-2" if rank <= 2 else "3+"


def group_stats(agents):
    n = len(agents)
    ctx = [a["first_context"] for a in agents]
    fresh = [a["first_fresh"] for a in agents]
    read = [a["first_read"] for a in agents]
    cost = [a["cost"] for a in agents]
    w1 = sum(a["write_1h"] for a in agents)
    w5 = sum(a["write_5m"] for a in agents)
    think = [a["thinking_total"] for a in agents if a["thinking_total"] is not None]
    return {
        "n": n,
        "first_context_median": round(med(ctx)),
        "first_context_p90": round(pctl(ctx, 0.9)),
        "first_fresh_write_median": round(med(fresh)),
        "first_cache_read_median": round(med(read)),
        "first_fresh_share_median": round(med([a["first_fresh"] / a["first_context"] for a in agents if a["first_context"]]) or 0, 3),
        "write_1h_share": round(w1 / (w1 + w5), 3) if (w1 + w5) else "n/a",
        "calls_median": round(med([a["calls"] for a in agents]), 1),
        "cost_median": round(med(cost), 4),
        "cost_p90": round(pctl(cost, 0.9), 4),
        "cost_min": round(min(cost), 4),
        "cost_max": round(max(cost), 4),
        "advisor_cost_median": round(med([a["advisor_cost"] for a in agents]), 4),
        "thinking_tokens_median": round(med(think)) if think else "n/a",
        "thinking_agents": len(think),
    }


def build_anatomy(root, days, min_agents, by_type):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    check_journal = load_check_journal()
    footer = Footer()
    wf_dirs = [
        Path(p)
        for p in glob.glob(str(root / "*" / "*" / "subagents" / "workflows" / "wf_*"))
        if Path(p).is_dir()
    ]
    all_agents, wf_count = [], 0
    started = returned = unreadable = 0
    journal_known = True
    for wf in sorted(wf_dirs):
        agent_files = sorted(wf.glob("agent-*.jsonl"))
        if not agent_files or max(mtime(p) for p in agent_files) < cutoff.timestamp():
            continue
        agents = []
        for agent_path in agent_files:
            try:
                analysed = analyze_agent(agent_path, cutoff)
            except Exception:
                unreadable += 1
                continue
            if analysed:
                agents.append(analysed)
        if not agents:
            continue
        wf_count += 1
        agents.sort(key=lambda a: a["first_ts"])
        for rank, a in enumerate(agents):
            a["rank"] = rank
        all_agents.extend(agents)
        journal = wf / "journal.jsonl"
        res = None
        if check_journal and journal.is_file():
            try:
                res = check_journal(str(journal))
            except Exception:
                res = None
        if res:
            returned += res[0]
            started += res[1]
        else:
            journal_known = False

    for a in all_agents:
        footer.add(a["parts"])

    def key(a):
        k = (a["model"], a["effort"], a["kind"], "yes" if a["skill_listing"] else "no")
        return k + ((a["agent_type"] or "generic",) if by_type else ())

    grouped = defaultdict(list)
    for a in all_agents:
        grouped[key(a)].append(a)
    groups, suppressed_groups, suppressed_agents = [], 0, 0
    for k, members in sorted(grouped.items()):
        if not members or len(members) < min_agents:
            suppressed_groups += 1
            suppressed_agents += len(members)
            continue
        g = {"model": k[0], "effort": k[1], "kind": k[2], "skill_listing_attached": k[3]}
        if by_type:
            g["agent_type"] = k[4]
        g.update(group_stats(members))
        groups.append(g)

    ranks = []
    for kind in ("generic", "typed"):
        for bucket in ("0", "1-2", "3+"):
            members = [a for a in all_agents if a["kind"] == kind and rank_bucket(a["rank"]) == bucket]
            if not members or len(members) < min_agents:
                continue
            ranks.append({
                "kind": kind,
                "start_rank": bucket,
                "n": len(members),
                "first_context_median": round(med([a["first_context"] for a in members])),
                "first_fresh_write_median": round(med([a["first_fresh"] for a in members])),
                "first_cache_read_median": round(med([a["first_read"] for a in members])),
            })

    att_chars = defaultdict(list)
    for a in all_agents:
        seen = defaultdict(int)
        for t, c in a["attachments"]:
            seen[t] += c
        for t, c in seen.items():
            att_chars[(a["kind"], t)].append(c)
    attachments = [
        {"kind": kind, "attachment_type": t, "agents": len(v), "chars_median": round(med(v))}
        for (kind, t), v in sorted(att_chars.items())
        if len(v) >= min_agents
    ]

    total_calls = sum(a["calls"] for a in all_agents)
    it_calls = sum(a["iterations_calls"] for a in all_agents)
    th_calls = sum(a["thinking_calls"] for a in all_agents)
    pct = lambda x: round(x / total_calls * 100) if total_calls else "n/a"
    coverage = {"iterations_pct_of_calls": pct(it_calls), "thinking_pct_of_calls": pct(th_calls)}
    notes = footer.lines()
    if total_calls and (it_calls / total_calls < 0.5 or th_calls / total_calls < 0.5):
        notes.insert(
            0,
            "advisor and thinking figures are FLOORS: usage.iterations / thinking token counts are present on only "
            f"{coverage['iterations_pct_of_calls']}% / {coverage['thinking_pct_of_calls']}% of calls",
        )
    if unreadable:
        notes.append(f"{unreadable} agent file(s) could not be analysed and are not counted")
    notes.append("typed-versus-generic differences are observational (different tasks, sessions and tool sets), not a controlled comparison")

    return {
        "prices_as_of": PRICES_AS_OF,
        "list_price_only": True,
        "window_days": days,
        "min_agents_per_group": min_agents,
        "workflows": wf_count,
        "journal": {"agents_started": started, "agents_returned": returned} if journal_known else "n/a",
        "agents": {
            "analysed": len(all_agents),
            "generic": sum(1 for a in all_agents if a["kind"] == "generic"),
            "typed": sum(1 for a in all_agents if a["kind"] == "typed"),
            "calls": total_calls,
        },
        "coverage": coverage,
        "groups": groups,
        "suppressed": {"groups": suppressed_groups, "agents": suppressed_agents},
        "start_rank": ranks,
        "attachments_before_first_call": attachments,
        "notes": notes,
    }


def fmt(v, spec="{:,}"):
    return v if isinstance(v, str) else spec.format(v)


def render_anatomy_text(r):
    out = [price_header(), ""]
    out.append(
        f"Workflow anatomy, last {r['window_days']} days: {r['workflows']} workflows, {r['agents']['analysed']} agents "
        f"({r['agents']['generic']} generic, {r['agents']['typed']} typed), {r['agents']['calls']:,} calls."
    )
    if isinstance(r["journal"], dict):
        out.append(f"Journals: {r['journal']['agents_started']} logical agents started, {r['journal']['agents_returned']} returned.")
    pct = lambda v: v if isinstance(v, str) else f"{v}%"
    out.append(
        f"Coverage: usage.iterations on {pct(r['coverage']['iterations_pct_of_calls'])} of calls, "
        f"thinking tokens on {pct(r['coverage']['thinking_pct_of_calls'])} of calls."
    )
    out.append(f"Groups with at least {r['min_agents_per_group']} agents (smaller groups are suppressed: "
               f"{r['suppressed']['groups']} groups, {r['suppressed']['agents']} agents):\n")
    for g in r["groups"]:
        label = f"{g['model']} @ {g['effort']}, {g['kind']}" + (f" ({g['agent_type']})" if "agent_type" in g else "") + \
            f", skill listing {g['skill_listing_attached']}"
        out.append(f"  {label}  (n={g['n']})")
        out.append(
            f"    first call: context median {g['first_context_median']:,} (p90 {g['first_context_p90']:,}), "
            f"fresh write median {g['first_fresh_write_median']:,} ({g['first_fresh_share_median'] * 100:.0f}%), "
            f"cache read median {g['first_cache_read_median']:,}"
        )
        out.append(
            f"    whole agent: ${g['cost_median']:.3f} median (p90 ${g['cost_p90']:.3f}, range ${g['cost_min']:.3f}-${g['cost_max']:.3f}), "
            f"{g['calls_median']:g} calls median, 1h share of writes {fmt(g['write_1h_share'], '{:.0%}')}, "
            f"advisor ${g['advisor_cost_median']:.3f} median, thinking tokens median {fmt(g['thinking_tokens_median'])} "
            f"(from {g['thinking_agents']} agents)"
        )
    if r["start_rank"]:
        out.append("\nBy start order within a workflow (0 = first agent started):")
        for s in r["start_rank"]:
            out.append(
                f"  {s['kind']:8} rank {s['start_rank']:>3}  n={s['n']:<4} context median {s['first_context_median']:,}, "
                f"fresh write median {s['first_fresh_write_median']:,}, cache read median {s['first_cache_read_median']:,}"
            )
    if r["attachments_before_first_call"]:
        out.append("\nAttachments before the first call (characters, never content):")
        for a in r["attachments_before_first_call"]:
            out.append(f"  {a['kind']:8} {a['attachment_type']:28} agents={a['agents']:<4} chars median {a['chars_median']:,}")
    out.append("\nNotes:")
    out.extend(f"  - {n}" for n in r["notes"])
    return "\n".join(out)


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def cmd_anatomy(args):
    root = Path(args.projects_dir)
    if not root.is_dir():
        print(f"No such projects dir: {root}", file=sys.stderr)
        return 1
    report = build_anatomy(root, args.days, args.min_agents, args.by_type)
    text = json.dumps(report, indent=2) if args.format == "json" else render_anatomy_text(report)
    if args.out:
        try:
            write_atomic(args.out, text + "\n")
        except OSError as e:
            print(f"cannot write {args.out}: {e}", file=sys.stderr)
            return 1
    else:
        print(text)
    return 0


# ---------------------------------------------------------------------- main


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def common_parser(description):
    ap = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Reports: overview (default) and anatomy. Put the report name first: measure-tokenomics.py anatomy --days 7",
    )
    ap.add_argument("--days", type=positive_int, default=21, help="window size in days (default 21 -- \"three weeks\")")
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = "overview"
    if argv and argv[0] in ("overview", "anatomy"):
        cmd = argv.pop(0)
    if cmd == "anatomy":
        ap = common_parser("Workflow launch anatomy from local transcripts (aggregates only).")
        ap.add_argument("--min-agents", type=positive_int, default=3, help="suppress groups with fewer agents (default 3)")
        ap.add_argument("--format", choices=VALID_FORMATS, default="text")
        ap.add_argument("--out", help="write the report to this file (atomic) instead of stdout")
        ap.add_argument("--by-type", action="store_true",
                        help="also group by the exact agent type name (local use: names of your own agent definitions appear)")
        return cmd_anatomy(ap.parse_args(argv))
    ap = common_parser(__doc__)
    ap.add_argument(
        "--effort-cutoff",
        default="2026-08-06T22:31:00+00:00",
        help="ISO timestamp splitting the agent effort-distribution before/after (default: this skill's birth)",
    )
    return cmd_overview(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
