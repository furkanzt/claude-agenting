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

A retry whose prompt changed (an agent that embeds an earlier agent's output,
re-run after a resume) gets a NEW key, so the dead first attempt stays missing
by key. The hook cannot know whether that later attempt is the same work: a
script may give one label to several different items, and then the dead
attempt is a real failure. So it does not hide it. It still counts by key and
names each missing agent whose label (and phase) has a LATER attempt that
returned, so the reader can check the journal per label instead of guessing.

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


def journal_detail(path):
    """Counts over logical agents (by key, else agentId), or None if nothing started.

    Returns {"returned", "total", "missing": [labels], "retried": [labels]}, where
    `retried` lists the missing agents whose label and phase have a LATER started
    record that returned (probably a retry under a changed prompt)."""
    started, result_ids, result_keys = read_journal(path)
    if not started:
        return None
    units = {}  # logical agent (key, else agentId) -> [index of first started record, record, agentIds]
    for i, rec in enumerate(started):
        unit = rec.get("key") or rec.get("agentId")
        if not unit:
            continue
        entry = units.setdefault(unit, [i, rec, set()])
        if rec.get("agentId"):
            entry[2].add(rec["agentId"])

    def returned(rec):
        return (rec.get("key") in result_keys) or (rec.get("agentId") in result_ids)

    missing, retried = [], []
    for unit, (i, first, ids) in units.items():
        if unit in result_keys or ids & result_ids:
            continue
        label = first.get("label") or first.get("agentId") or "?"
        missing.append(label)
        same = (first.get("label"), first.get("phase"))
        if first.get("label") and any((r.get("label"), r.get("phase")) == same and returned(r) for r in started[i + 1:]):
            retried.append(label)
    total = len(units)
    return {"returned": total - len(missing), "total": total, "missing": missing, "retried": retried}


def check_journal(path):
    """Return (returned, total, missing_labels) over logical agents, or None if
    the journal has no started agents."""
    d = journal_detail(path)
    return None if d is None else (d["returned"], d["total"], d["missing"])


def capped(labels):
    shown = ", ".join(labels[:MAX_LABELS])
    if len(labels) > MAX_LABELS:
        shown += f", … and {len(labels) - MAX_LABELS} more"
    return shown


def warning_for(block):
    diag = DIAGNOSTICS_RE.search(block)
    m = JOURNAL_RE.search(diag.group(1) if diag else block)
    if not m:
        return None
    path = m.group(1).strip()
    name_m = NAME_RE.search(block)
    name = name_m.group(1) if name_m else "(unnamed)"
    try:
        d = journal_detail(path)
    except Exception:
        return None
    if not d or not d["missing"]:
        return None
    missing, retried = d["missing"], d["retried"]
    head = f'[agenting] Workflow "{name}": {d["returned"]} of {d["total"]} agents returned; missing: {capped(missing)}.'
    tail = (f" Read {path} and report the real count before presenting or acting on this "
            f"result (agenting skill: \"When the finish check fires\").")
    if not retried:
        return head + " The workflow's own summary was built without them." + tail
    if len(retried) == len(missing):
        note = (" Every one of them has a later attempt with the same label that returned, which is what a "
                "retry under a changed prompt looks like (for example after a resume): if each label names one "
                "item, no work is missing. If the script gives one label to several different items, these "
                "are real failures.")
    else:
        note = (f" {len(retried)} of them have a later attempt with the same label that returned (probably "
                f"retries under a changed prompt): {capped(retried)}. The others have no result under any "
                "attempt, and the workflow's own summary was built without them.")
    return head + note + tail


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
