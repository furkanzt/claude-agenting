#!/usr/bin/env python3
"""
session-continuity  --  SessionStart hook that carries three per-session values
across compaction of one chat continuum:

  mode         auto | manual               (default auto)
  disposition  fast | balanced | quality   (default balanced)
  workflows    on | off | unset            (default unset = not opted in)

Claude Code keeps one session_id across compaction of the same conversation,
so state keyed on session_id survives a compaction summary that forgets to
mention it. A genuinely new conversation (startup, /clear) gets a fresh id and
the defaults. /clear is handled explicitly as a new continuum in case the id is
ever reused.

This hook never asks anything. It seeds the defaults the first time it sees a
session_id, then re-injects the recorded values as ONE short additionalContext
line on every later SessionStart. The rules for when those values may change
live in the agenting skill (skills/agenting/reference/modes.md), not here.

STATE
-----
<state dir>/.agenting-session-state.json, where <state dir> is
$AGENTING_STATE_DIR if set (tests use this), else ~/.claude. Deliberately not
next to this script: the installed plugin lives in a versioned cache directory,
so a path relative to __file__ would orphan the state on every update.

    { session_id: {"mode": "auto", "disposition": "balanced",
                    "workflows": "on"|"off"|null, "updated": iso8601} }

workflow-routing-guard.py reads `mode` from the same file: only an explicitly
recorded "auto" drops its Stage-2 approval requirement.

Legacy (2.x) entries: mode "semi-auto" is read as "manual", never as "auto";
an old "suggestion" key is ignored (it recorded a different consent than the
workflows opt-in, so it is not mapped) and dropped on the next --record.

CLI
---
  (no flags)   hook mode: SessionStart JSON on stdin -> additionalContext
  --record --session <id> [--mode auto|manual]
                           [--disposition fast|balanced|quality]
                           [--workflows on|off]
  --status --session <id>
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

STATE_DIR = os.path.expanduser(os.environ.get("AGENTING_STATE_DIR") or "~/.claude")
STATE_PATH = os.path.join(STATE_DIR, ".agenting-session-state.json")
KEEP_SESSIONS = 20
SELF_PATH = os.path.abspath(__file__)

MODES = ("auto", "manual")
DISPOSITIONS = ("fast", "balanced", "quality")
WORKFLOWS = ("on", "off")
DEFAULT_MODE = "auto"
DEFAULT_DISPOSITION = "balanced"


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        d = json.loads(raw) if raw.strip() else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(d: dict) -> None:
    if len(d) > KEEP_SESSIONS:
        d = dict(
            sorted(
                d.items(),
                key=lambda kv: (kv[1].get("updated", "") if isinstance(kv[1], dict) else ""),
            )[-KEEP_SESSIONS:]
        )
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize(entry) -> dict:
    """Recorded values -> current vocabulary."""
    entry = entry if isinstance(entry, dict) else {}
    mode = entry.get("mode")
    if mode not in MODES:
        # No entry at all -> the default. An entry whose mode is legacy
        # "semi-auto" or unreadable -> "manual", matching the routing guard,
        # which drops Stage 2 only for an explicit "auto".
        mode = "manual" if entry else DEFAULT_MODE
    disp = entry.get("disposition")
    if disp not in DISPOSITIONS:
        disp = DEFAULT_DISPOSITION
    wf = entry.get("workflows")
    if wf not in WORKFLOWS:
        wf = None
    return {"mode": mode, "disposition": disp, "workflows": wf}


def fmt_workflows(value) -> str:
    if value == "on":
        return ("workflows=on (the user opted in for this chat: run Workflows for "
                "substantive tasks without re-asking)")
    if value == "off":
        return "workflows=off"
    return "workflows=not opted in"


def summary(v: dict) -> str:
    return (f"mode={v['mode']} · disposition={v['disposition']} · "
            f"{fmt_workflows(v['workflows'])}")


def run_hook() -> int:
    data = read_hook_input()
    session = data.get("session_id") or "unknown"
    source = data.get("source") or ""

    state = load_state()
    if source == "clear":
        state.pop(session, None)  # /clear is a new continuum, never an inherited one
    entry = state.get(session)
    if not isinstance(entry, dict):
        entry = {"mode": DEFAULT_MODE, "disposition": DEFAULT_DISPOSITION,
                 "workflows": None, "updated": utc_now()}
        state[session] = entry
        save_state(state)

    line = (
        f"[agenting] {summary(normalize(entry))} (session {session}). "
        f'Record changes: python3 "{SELF_PATH}" --record --session {session} '
        f"[--mode auto|manual] [--disposition fast|balanced|quality] [--workflows on|off]. "
        f"Load the agenting skill before authoring a Workflow."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": line}}))
    return 0


def record(args) -> int:
    session = args.session or "unknown"
    state = load_state()
    entry = state.get(session)
    if not isinstance(entry, dict):
        entry = {}
    v = normalize(entry)
    if args.mode:
        v["mode"] = args.mode
    if args.disposition:
        v["disposition"] = args.disposition
    if args.workflows:
        v["workflows"] = args.workflows
    v["updated"] = utc_now()
    state[session] = v  # rewrites the entry, dropping legacy keys such as "suggestion"
    save_state(state)
    print(f"recorded: session {session}: {summary(v)}")
    return 0


def status(args) -> int:
    session = args.session or "unknown"
    entry = load_state().get(session)
    if not isinstance(entry, dict):
        print(f"no state recorded for session {session} "
              f"(defaults: {summary(normalize({}))})")
        return 0
    print(f"session {session}: {summary(normalize(entry))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--disposition", choices=DISPOSITIONS)
    ap.add_argument("--workflows", choices=WORKFLOWS)
    args, _ = ap.parse_known_args()

    if args.record:
        if not (args.mode or args.disposition or args.workflows):
            print("nothing to record: pass --mode, --disposition and/or --workflows",
                  file=sys.stderr)
            return 1
        return record(args)

    if args.status:
        return status(args)

    return run_hook()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
