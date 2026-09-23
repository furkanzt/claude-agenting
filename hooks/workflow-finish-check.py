#!/usr/bin/env python3
"""
workflow-finish-check  --  UserPromptSubmit hook: did every workflow agent return?

WHY THIS EXISTS
---------------
A workflow script's own summary is computed from whatever agents returned;
agents that died are silently absent from it. In August 2026 one run's headline
numbers came from 38 of 122 agents and looked like a finished audit. The
post-completion check lived only in the agenting skill, so it ran only when
someone remembered it. This hook makes the check mechanical.

HOW
---
When a Workflow finishes, Claude Code delivers a user-turn prompt containing a
<task-notification> block with

    <summary>Dynamic workflow "<name>" completed</summary>
    <diagnostics>Per-agent results: /abs/path/.../journal.jsonl — ...

The journal is JSONL: one {"type":"launched"}, then per agent
{"type":"started","agentId","key","label","phase"} and later
{"type":"result","agentId","key",...}.

An agent counts as MISSING when neither its agentId nor its `key` has a result.
The key is the (prompt, opts) cache key: when the runtime restarts an
interrupted agent it logs a second `started` line with the same key and a new
agentId, and that retry's result covers the first attempt. Counting agentIds
alone would report those superseded attempts as lost work. A started line
without a key falls back to agentId alone.

OUTPUT
------
Silent (no stdout) when every started agent is covered, when the prompt holds no
workflow notification, and on any error. Otherwise one additionalContext line
per incomplete workflow. Never blocks the prompt.
"""

import json
import re
import sys

MAX_LABELS = 8

NOTIFICATION_RE = re.compile(r"<task-notification>(.*?)(?:</task-notification>|\Z)", re.S)
NAME_RE = re.compile(r'<summary>\s*Dynamic workflow "([^\n]*)"\s+\w+\s*</summary>')
DIAGNOSTICS_RE = re.compile(r"<diagnostics>(.*?)</diagnostics>", re.S)
JOURNAL_RE = re.compile(r"Per-agent results:\s*([^\n]+?\.jsonl)")


def read_journal(path):
    """Return (started: list of dicts in order, result_ids: set, result_keys: set)."""
    started, result_ids, result_keys = [], set(), set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            kind = rec.get("type")
            if kind == "started":
                started.append(rec)
            elif kind == "result":
                if rec.get("agentId"):
                    result_ids.add(rec["agentId"])
                if rec.get("key"):
                    result_keys.add(rec["key"])
    return started, result_ids, result_keys


def check_journal(path):
    """Return (returned, total, missing_labels) over logical agents, or None if
    the journal has no started agents."""
    started, result_ids, result_keys = read_journal(path)
    if not started:
        return None
    units = {}  # logical agent (key, else agentId) -> (first started record, agentIds)
    for rec in started:
        unit = rec.get("key") or rec.get("agentId")
        if not unit:
            continue
        first, ids = units.setdefault(unit, (rec, set()))
        if rec.get("agentId"):
            ids.add(rec["agentId"])
    missing = []
    for unit, (first, ids) in units.items():
        if unit in result_keys or ids & result_ids:
            continue
        missing.append(first.get("label") or first.get("agentId") or "?")
    total = len(units)
    return total - len(missing), total, missing


def warning_for(block):
    diag = DIAGNOSTICS_RE.search(block)
    m = JOURNAL_RE.search(diag.group(1) if diag else block)
    if not m:
        return None
    path = m.group(1).strip()
    name_m = NAME_RE.search(block)
    name = name_m.group(1) if name_m else "(unnamed)"
    try:
        res = check_journal(path)
    except Exception:
        return None
    if not res:
        return None
    returned, total, missing = res
    if not missing:
        return None
    shown = ", ".join(missing[:MAX_LABELS])
    if len(missing) > MAX_LABELS:
        shown += f", … and {len(missing) - MAX_LABELS} more"
    return (
        f'[agenting] Workflow "{name}": {returned} of {total} agents returned; '
        f"missing: {shown}. The workflow's own summary was built without them. "
        f"Read {path} and report the real count before presenting or acting on this "
        f"result (agenting skill: \"When the finish check fires\")."
    )


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return
    prompt = data.get("prompt") if isinstance(data, dict) else None
    if not isinstance(prompt, str) or "<task-notification>" not in prompt:
        return
    if "Per-agent results:" not in prompt:
        return
    lines = []
    for block in NOTIFICATION_RE.findall(prompt):
        w = warning_for(block)
        if w:
            lines.append(w)
    if lines:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
