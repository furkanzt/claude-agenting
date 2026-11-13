#!/usr/bin/env python3
"""
session-continuity  --  SessionStart hook that carries three per-session values
across compaction of one chat continuum:

  mode         auto | manual               (default auto)
  disposition  fast | balanced | quality   (default balanced)
  workflows    on | off | unset            (default unset = not opted in)

plus three read-only facts the line also carries: whether Agent Teams (teammates)
are on, the advisor state of the session, and a standing Workflows default the owner
sets once for all chats.

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

A reserved top-level key "_defaults" ({"workflows": "on"|"off"}) holds the standing
Workflows default. It is not a session: it is never pruned and never counted. A
session seen for the first time is seeded with it and marked
"workflows_source": "default" (cleared by a per-chat --record --workflows).

workflow-routing-guard.py reads `mode` from the same file by session id: only an
explicitly recorded "auto" drops its Stage-2 approval requirement. It never
looks at "_defaults".

Teammates: on when CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is 1/true in the hook's
environment; when the variable is absent, the first of ~/.claude/settings.json,
<cwd>/.claude/settings.json and <cwd>/.claude/settings.local.json whose "env"
object has it decides.

Advisor: the line says "advisor=off", or "advisor=<model>" when the session has an
advisor. Agents the session starts inherit its advisor, so the line reminds the lead to
put the work-alone sentence in each agent prompt. "off" when
CLAUDE_CODE_DISABLE_ADVISOR_TOOL is 1/true/yes in the hook's environment; otherwise
the first non-empty string under the top-level key "advisorModel" in <cwd>/.claude/
settings.local.json, <cwd>/.claude/settings.json, ~/.claude/settings.json (in that
order); otherwise "off". A file that is missing, not JSON or has no such string is
skipped. An --advisor flag given at launch cannot be seen from here.

Legacy (2.x) entries: mode "semi-auto" is read as "manual", never as "auto";
an old "suggestion" key is ignored (it recorded a different consent than the
workflows opt-in, so it is not mapped) and dropped on the next --record.

CLI
---
  (no flags)   hook mode: SessionStart JSON on stdin -> additionalContext
  --record --session <id> [--mode auto|manual]
                           [--disposition fast|balanced|quality]
                           [--workflows on|off]
  --record-default --workflows on|off|unset      (standing default, no --session)
  --status [--session <id>]
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
DEFAULTS_KEY = "_defaults"
TEAMS_VAR = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
ADVISOR_OFF_VAR = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"


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
    defaults = d.get(DEFAULTS_KEY)
    d = {k: v for k, v in d.items() if k != DEFAULTS_KEY}  # not a session: never counted or pruned
    if len(d) > KEEP_SESSIONS:
        d = dict(
            sorted(
                d.items(),
                key=lambda kv: (kv[1].get("updated", "") if isinstance(kv[1], dict) else ""),
            )[-KEEP_SESSIONS:]
        )
    if isinstance(defaults, dict) and defaults:
        d[DEFAULTS_KEY] = defaults
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
    out = {"mode": mode, "disposition": disp, "workflows": wf}
    if wf and entry.get("workflows_source") == "default":
        out["workflows_source"] = "default"
    return out


def default_workflows(state: dict):
    d = state.get(DEFAULTS_KEY)
    wf = d.get("workflows") if isinstance(d, dict) else None
    return wf if wf in WORKFLOWS else None


def seed_entry(state: dict) -> dict:
    """A fresh session record: the built-in defaults plus the standing Workflows default."""
    entry = {"mode": DEFAULT_MODE, "disposition": DEFAULT_DISPOSITION,
             "workflows": None, "updated": utc_now()}
    wf = default_workflows(state)
    if wf:
        entry["workflows"] = wf
        entry["workflows_source"] = "default"
    return entry


def fmt_workflows(value, standing=False) -> str:
    if value == "on" and standing:
        return ("workflows=on (standing: the user set this for all chats; run Workflows "
                "for substantive tasks without re-asking)")
    if value == "on":
        return ("workflows=on (the user opted in for this chat: run Workflows for "
                "substantive tasks without re-asking)")
    if value == "off":
        return "workflows=off"
    return "workflows=not opted in"


def summary(v: dict) -> str:
    return (f"mode={v['mode']} · disposition={v['disposition']} · "
            f"{fmt_workflows(v['workflows'], v.get('workflows_source') == 'default')}")


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true")


def teammates_on(cwd) -> bool:
    """Agent Teams switch: the hook's environment first, then the `env` object of the
    user, project and local settings files (the first that names the variable decides)."""
    if TEAMS_VAR in os.environ:
        return _truthy(os.environ[TEAMS_VAR])
    paths = [os.path.expanduser("~/.claude/settings.json")]
    if cwd and isinstance(cwd, str):
        paths += [os.path.join(cwd, ".claude", "settings.json"),
                  os.path.join(cwd, ".claude", "settings.local.json")]
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            env = data.get("env") if isinstance(data, dict) else None
            if isinstance(env, dict) and TEAMS_VAR in env:
                return _truthy(env[TEAMS_VAR])
        except Exception:
            continue  # unreadable or not an object: counts as absent
    return False


def fmt_teammates(on: bool) -> str:
    if on:
        return "teammates=on"
    return ("teammates=off (when a job fits teammates, tell the user once in this chat "
            "how to turn them on; see the skill's teammates section)")


def advisor_state(cwd):
    """The session's advisor model, or "off". The environment switch wins; then the
    first non-empty string under "advisorModel" in the local, project and user settings."""
    if str(os.environ.get(ADVISOR_OFF_VAR, "")).strip().lower() in ("1", "true", "yes"):
        return "off"
    paths = []
    if cwd and isinstance(cwd, str):
        paths += [os.path.join(cwd, ".claude", "settings.local.json"),
                  os.path.join(cwd, ".claude", "settings.json")]
    paths.append(os.path.expanduser("~/.claude/settings.json"))
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            model = data.get("advisorModel") if isinstance(data, dict) else None
            if isinstance(model, str) and model.strip():
                return model.strip()
        except Exception:
            continue  # missing, unreadable or not JSON: skipped
    return "off"


def fmt_advisor(model: str) -> str:
    if model == "off":
        return "advisor=off"
    return (f"advisor={model} (agents you start inherit it; workers work alone: put the "
            "work-alone sentence in each agent prompt, agenting: agents carry it; see the skill)")


def fmt_default(state: dict) -> str:
    return f"standing default: workflows={default_workflows(state) or 'unset'}"


def run_hook() -> int:
    data = read_hook_input()
    session = data.get("session_id") or "unknown"
    if session == DEFAULTS_KEY:
        session = "unknown"
    source = data.get("source") or ""

    state = load_state()
    if source == "clear":
        state.pop(session, None)  # /clear is a new continuum, never an inherited one
    entry = state.get(session)
    if not isinstance(entry, dict):
        entry = seed_entry(state)
        state[session] = entry
        save_state(state)

    line = (
        f"[agenting] {summary(normalize(entry))} · "
        f"{fmt_teammates(teammates_on(data.get('cwd')))} · "
        f"{fmt_advisor(advisor_state(data.get('cwd')))} (session {session}). "
        f'Record changes: python3 "{SELF_PATH}" --record --session {session} '
        f"[--mode auto|manual] [--disposition fast|balanced|quality] [--workflows on|off]. "
        f"Load the agenting skill before moving bulk work off this chat or starting an agent, teammate or Workflow."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": line}}))
    return 0


def record(args) -> int:
    session = args.session or "unknown"
    if session == DEFAULTS_KEY:
        session = "unknown"
    state = load_state()
    entry = state.get(session)
    if not isinstance(entry, dict):
        entry = seed_entry(state)
    v = normalize(entry)
    if args.mode:
        v["mode"] = args.mode
    if args.disposition:
        v["disposition"] = args.disposition
    if args.workflows:
        v["workflows"] = args.workflows
        v.pop("workflows_source", None)  # a per-chat value replaces the standing default
    v["updated"] = utc_now()
    state[session] = v  # rewrites the entry, dropping legacy keys such as "suggestion"
    save_state(state)
    print(f"recorded: session {session}: {summary(v)}")
    return 0


def record_default(args) -> int:
    if args.workflows not in WORKFLOWS + ("unset",):
        print("nothing to record: pass --workflows on|off|unset", file=sys.stderr)
        return 1
    state = load_state()
    if args.workflows == "unset":
        state.pop(DEFAULTS_KEY, None)
    else:
        state[DEFAULTS_KEY] = {"workflows": args.workflows}
    save_state(state)
    print(f"recorded: {fmt_default(state)}")
    return 0


def status(args) -> int:
    session = args.session or "unknown"
    state = load_state()
    entry = state.get(session) if session != DEFAULTS_KEY else None
    tail = (f" · {fmt_teammates(teammates_on(os.getcwd()))} · "
            f"{fmt_advisor(advisor_state(os.getcwd()))} · {fmt_default(state)}")
    if not isinstance(entry, dict):
        print(f"no state recorded for session {session} "
              f"(defaults: {summary(normalize(seed_entry(state)))}){tail}")
        return 0
    print(f"session {session}: {summary(normalize(entry))}{tail}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--record-default", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--disposition", choices=DISPOSITIONS)
    ap.add_argument("--workflows", choices=WORKFLOWS + ("unset",))
    args, _ = ap.parse_known_args()

    if args.record_default:
        return record_default(args)

    if args.record:
        if args.workflows == "unset":
            print("--workflows unset is only valid with --record-default", file=sys.stderr)
            return 1
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
