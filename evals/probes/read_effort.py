#!/usr/bin/env python3
"""Read the effort each subagent actually ran with, from its transcript.

Every assistant record in a subagent transcript (agent-<id>.jsonl) carries `effort`,
`perTurnEffort` and `requestedModel`, so whether a pinned effort was applied can be read
directly instead of inferred from thinking tokens. Workflow runs live in
<session>/subagents/workflows/<run>/, Agent-tool runs in <session>/subagents/. A label comes
from agent-<id>.meta.json ("description"); the group of "low-2" is "low".

    python3 evals/probes/read_effort.py <dir>
    python3 evals/probes/read_effort.py <dir> --expect low=low,medium=medium,unpinned=medium

With --expect (group=effort pairs) the exit status is 1 when a group is missing or recorded
any other effort. The probe that produces such a directory is effort_application.workflow.js
in this directory; run it with the Workflow tool, then point this script at the run's directory.
Thinking time is thinkingDurationMs summed per agent; per-record output_tokens in these
transcripts are partial stream counts and are not used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


def read_agent(path: Path) -> dict:
    efforts, per_turn, models = Counter(), Counter(), Counter()
    thinking_ms = turns = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        turns += 1
        efforts[str(rec.get("effort"))] += 1
        per_turn[str(rec.get("perTurnEffort"))] += 1
        models[str(rec.get("requestedModel"))] += 1
        thinking_ms += rec.get("thinkingDurationMs") or 0
    label = path.stem
    meta = path.with_name(path.stem + ".meta.json")
    if meta.is_file():
        try:
            label = json.loads(meta.read_text(encoding="utf-8")).get("description") or label
        except ValueError:
            pass
    return {"label": label, "turns": turns, "efforts": sorted(efforts), "per_turn": sorted(per_turn),
            "models": sorted(models), "thinking_ms": thinking_ms}


def read_agents(directory: Path) -> list[dict]:
    return [read_agent(p) for p in sorted(Path(directory).glob("agent-*.jsonl"))]


def group_of(label: str) -> str:
    return re.sub(r"-\d+$", "", label)


def summarize(agents: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in agents:
        groups[group_of(a["label"])].append(a)
    return {g: {"n": len(v),
                "efforts": sorted({e for a in v for e in a["efforts"]}),
                "models": sorted({m for a in v for m in a["models"]}),
                "mean_thinking_ms": mean(a["thinking_ms"] for a in v)} for g, v in groups.items()}


def check_expectations(summary: dict[str, dict], expect: dict[str, str]) -> list[str]:
    problems = []
    for group, want in expect.items():
        if group not in summary:
            problems.append(f"{group}: no agents found")
        elif summary[group]["efforts"] != [want]:
            problems.append(f"{group}: expected effort {want}, recorded {summary[group]['efforts']}")
    return problems


def parse_expect(text: str) -> dict[str, str]:
    out = {}
    for pair in filter(None, (p.strip() for p in text.split(","))):
        group, _, effort = pair.rpartition("=")
        if not group or not effort:
            raise ValueError(f"bad expectation {pair!r}; use group=effort")
        out[group] = effort
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("directory")
    ap.add_argument("--expect", default="", help="comma-separated group=effort pairs to assert")
    args = ap.parse_args(argv)
    agents = read_agents(Path(args.directory))
    if not agents:
        print(f"no agent-*.jsonl in {args.directory}", file=sys.stderr)
        return 2
    summary = summarize(agents)
    print(f"{'group':<34}{'n':>3}  {'recorded effort':<18}{'model':<22}{'mean thinking ms':>17}")
    for g, s in sorted(summary.items()):
        print(f"{g[:33]:<34}{s['n']:>3}  {','.join(s['efforts']):<18}{','.join(s['models']):<22}{s['mean_thinking_ms']:>17.0f}")
    problems = check_expectations(summary, parse_expect(args.expect)) if args.expect else []
    for p in problems:
        print("MISMATCH", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
