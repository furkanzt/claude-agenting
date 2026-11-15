#!/usr/bin/env python3
"""
session-continuity  --  SessionStart hook that carries three per-session values
across compaction of one chat continuum:

  mode         auto | manual               (default auto)
  disposition  cheapest | fast | balanced  (default balanced; fast on a Pro plan)
  workflows    on | off | unset            (default unset = not opted in)

plus four read-only facts the line also carries: whether Agent Teams (teammates)
are on, the advisor state of the session, a standing Workflows default the owner
sets once for all chats, and the account's plan when it can be read.

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

Plan: Claude Code keeps the account's plan in ~/.claude.json under "oauthAccount"
(.claude.json in $CLAUDE_CONFIG_DIR when that is set; $AGENTING_PLAN_FILE names
another file, tests use this). The fields are not documented, so the reading is
narrow: organizationType decides when it holds a word ("max" or "pro" as a whole
word; any other value, such as a team or enterprise account, is no plan); without it
the first of organizationRateLimitTier, userRateLimitTier and planDisplayName that
holds one of the two words decides. Anything else, a missing file or a file that is
not JSON is "no plan" and changes nothing.

A session id with no record starts in `fast` on Pro and in `balanced` on Max and is
marked "disposition_source": "plan" (cleared by a per-chat --record --disposition).
The user is told once, in a systemMessage, at the SessionStart that opens a NEW chat
(source startup or clear); a chat that already existed and lost its record (source
resume, compact or fork) is seeded the same way without a word. A project whose
agenting/AGENTING.md (in the working folder or above it, up to the folder with .git)
names an auto-disposition-default has made its own choice: no plan start and no
notice there. The plan the user was last told about is kept under the reserved
top-level key "_plan"; the first new chat that is told after it changed gets a
one-line "plan changed" notice instead.

`cheapest` (3.7.0) sits below `fast`: the cheapest cell that passes the owner's bar on
every row. A plan never starts a chat there; only the user's word or a project's
default does.

`quality` was a third disposition until 3.6.0. A recorded "quality" reads as
"balanced" and the line says so; --record --disposition quality records "balanced"
and says that the word "critical" sends one job to the careful models.

Legacy (2.x) entries: mode "semi-auto" is read as "manual", never as "auto";
an old "suggestion" key is ignored (it recorded a different consent than the
workflows opt-in, so it is not mapped) and dropped on the next --record.

CLI
---
  (no flags)   hook mode: SessionStart JSON on stdin -> additionalContext
  --record --session <id> [--mode auto|manual]
                           [--disposition cheapest|fast|balanced]
                           [--workflows on|off]
  --record-default --workflows on|off|unset      (standing default, no --session)
  --status [--session <id>]
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

STATE_DIR = os.path.expanduser(os.environ.get("AGENTING_STATE_DIR") or "~/.claude")
STATE_PATH = os.path.join(STATE_DIR, ".agenting-session-state.json")
KEEP_SESSIONS = 20
SELF_PATH = os.path.abspath(__file__)

def _plan_path() -> str:
    """Where Claude Code keeps the account: $AGENTING_PLAN_FILE (tests), else .claude.json in
    $CLAUDE_CONFIG_DIR when that is set, else in the home folder."""
    if os.environ.get("AGENTING_PLAN_FILE"):
        return os.path.expanduser(os.environ["AGENTING_PLAN_FILE"])
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.path.join(os.path.expanduser(os.environ["CLAUDE_CONFIG_DIR"]), ".claude.json")
    return os.path.expanduser("~/.claude.json")


PLAN_PATH = _plan_path()

MODES = ("auto", "manual")
DISPOSITIONS = ("cheapest", "fast", "balanced")
REMOVED_DISPOSITION = "quality"          # a third disposition until 3.6.0; read as balanced
WORKFLOWS = ("on", "off")
DEFAULT_MODE = "auto"
DEFAULT_DISPOSITION = "balanced"
DEFAULTS_KEY = "_defaults"
PLAN_KEY = "_plan"
RESERVED_KEYS = (DEFAULTS_KEY, PLAN_KEY)
PLAN_DISPOSITION = {"Pro": "fast", "Max": "balanced"}
PLAN_NAMES = tuple(PLAN_DISPOSITION)      # membership by ==, so an odd stored value never raises
CONTINUING_SOURCES = ("resume", "compact", "fork")   # SessionStart of a chat that already existed
PLAN_FIELDS = ("organizationType", "organizationRateLimitTier", "userRateLimitTier", "planDisplayName")
PROJECT_DEFAULT_RE = re.compile(r"auto-disposition-default[`* \t]*:[`* \t]*(cheapest|fast|balanced|quality)\b", re.I)
# The tip for the main chat of a Pro plan. One line, read by the tests with a regular expression.
# Sonnet at high is `fast`'s cell for planning and writing tests (the coding experiment's question
# 4, with the owner's choice of 2026-11-15: evals/results/REPORT-2026-11-15-coding.md). The second
# sentence names `fast`'s cell for an architecture decision, Sonnet at xhigh since the round of
# 2026-11-15 (evals/results/REPORT-2026-11-15-architecture.md); until then it named Opus at xhigh.
# It says "architecture decision", not "design decision": the UI/UX design row is still Opus xhigh.
# The warning against switching back and forth is the owner's. Claude Code's docs (prompt-caching,
# read 2026-11-15) say an effort change keeps the cache on Sonnet 5.5 with a subscription or an API
# key, and a model switch never. Not on Amazon Bedrock, Google Cloud, a Claude apps gateway, with
# CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS set or under a HIPAA configuration: the hook does not check
# those, and a Pro plan is a subscription.
MAIN_CHAT_TIP = "run this chat on Sonnet at high effort (/model sonnet, then /effort high). For an architecture decision (a choice later work is built on) raise the effort (/effort xhigh) and stay on Sonnet, then go back to high: an effort change keeps the chat's cache, a model switch throws it away, so do not switch back and forth between Sonnet and Opus"
MODE_COMMAND = "/agenting-mode [" + "|".join(DISPOSITIONS) + "]"
QUALITY_GONE = ('the quality setting is gone: say "critical" for one job that needs the careful models')
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
    plan = d.get(PLAN_KEY)
    d = {k: v for k, v in d.items() if k not in RESERVED_KEYS}  # not sessions: never counted or pruned
    if len(d) > KEEP_SESSIONS:
        d = dict(
            sorted(
                d.items(),
                key=lambda kv: (kv[1].get("updated", "") if isinstance(kv[1], dict) else ""),
            )[-KEEP_SESSIONS:]
        )
    if isinstance(defaults, dict) and defaults:
        d[DEFAULTS_KEY] = defaults
    if isinstance(plan, dict) and plan:
        d[PLAN_KEY] = plan
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
    was_quality = disp == REMOVED_DISPOSITION
    if disp not in DISPOSITIONS:
        disp = DEFAULT_DISPOSITION
    wf = entry.get("workflows")
    if wf not in WORKFLOWS:
        wf = None
    out = {"mode": mode, "disposition": disp, "workflows": wf}
    if wf and entry.get("workflows_source") == "default":
        out["workflows_source"] = "default"
    plan = entry.get("plan")
    if (entry.get("disposition_source") == "plan" and plan in PLAN_NAMES
            and disp == PLAN_DISPOSITION[plan] and not was_quality):
        out["disposition_source"] = "plan"
        out["plan"] = plan
    if was_quality:
        out["was_quality"] = True
    return out


def _load_plan_file():
    """The plan file as JSON. Claude Code rewrites the file while it runs, so a file caught half
    written is read once more after a moment."""
    for attempt in (1, 2):
        try:
            with open(PLAN_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            if attempt == 1:
                time.sleep(0.05)
    return None


def read_plan():
    """"Pro", "Max" or None: the account's plan as Claude Code keeps it. The fields are not
    documented, so anything unreadable or unknown is None (no plan: nothing changes)."""
    try:
        data = _load_plan_file()
        account = data.get("oauthAccount") if isinstance(data, dict) else None
        if not isinstance(account, dict):
            return None
        for key in PLAN_FIELDS:
            value = account.get(key)
            if not isinstance(value, str):
                continue
            words = re.findall(r"[a-z]+", value.lower())
            if "max" in words:
                return "Max"
            if "pro" in words:
                return "Pro"
            if key == PLAN_FIELDS[0] and words:
                return None            # the account names another kind of plan (team, enterprise)
    except Exception:
        return None
    return None


def project_rules_file(cwd):
    """agenting/AGENTING.md of the project that holds cwd: in cwd, or in the nearest folder above it,
    up to and including the folder that has .git. None when there is none."""
    if not (cwd and isinstance(cwd, str)):
        return None
    folder = os.path.abspath(cwd)
    for _ in range(25):
        path = os.path.join(folder, "agenting", "AGENTING.md")
        if os.path.isfile(path):
            return path
        parent = os.path.dirname(folder)
        if os.path.exists(os.path.join(folder, ".git")) or parent == folder:
            return None
        folder = parent
    return None


def project_has_default(cwd) -> bool:
    """True when the project's agenting/AGENTING.md names an auto-disposition-default outside a
    comment: the project chose its own start, so the plan does not."""
    path = project_rules_file(cwd)
    if not path:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = re.sub(r"<!--.*?-->", "", f.read(), flags=re.S)
    except Exception:
        return False
    return bool(PROJECT_DEFAULT_RE.search(text))


def plan_start(cwd):
    """(plan, starts): the plan that can be read, and the plan that starts a new chat here (None in a
    project that names its own default)."""
    plan = read_plan()
    return plan, (plan if plan and not project_has_default(cwd) else None)


def default_workflows(state: dict):
    d = state.get(DEFAULTS_KEY)
    wf = d.get("workflows") if isinstance(d, dict) else None
    return wf if wf in WORKFLOWS else None


def seed_entry(state: dict, plan=None) -> dict:
    """A fresh session record: the built-in defaults, the plan's starting disposition when a plan
    is given, and the standing Workflows default."""
    entry = {"mode": DEFAULT_MODE, "disposition": DEFAULT_DISPOSITION,
             "workflows": None, "updated": utc_now()}
    if plan in PLAN_NAMES:
        entry["disposition"] = PLAN_DISPOSITION[plan]
        entry["disposition_source"] = "plan"
        entry["plan"] = plan
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


def fmt_disposition(v: dict) -> str:
    text = f"disposition={v['disposition']}"
    if v.get("disposition_source") == "plan":
        return f"{text} (set for the {v['plan']} plan)"
    if v.get("was_quality"):
        return f"{text} ({QUALITY_GONE})"
    return text


def summary(v: dict) -> str:
    return (f"mode={v['mode']} · {fmt_disposition(v)} · "
            f"{fmt_workflows(v['workflows'], v.get('workflows_source') == 'default')}")


def plan_notice(plan: str, changed_from=None) -> str:
    """What the user is told at the first SessionStart of a chat that the plan started."""
    if changed_from:
        return (f"[agenting] plan changed from {changed_from} to {plan} · "
                f"new chats now start in {PLAN_DISPOSITION[plan]}.")
    if plan == "Pro":
        tip = f" Tip: {MAIN_CHAT_TIP}." if MAIN_CHAT_TIP else ""
        return ("[agenting] plan=Pro · mode=fast (set for your plan: cheaper models, fewer agents)."
                f"{tip} Change mode: {MODE_COMMAND}")
    return f"[agenting] plan=Max · mode=balanced (set for your plan). To save usage, change mode: {MODE_COMMAND}"


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
    if session in RESERVED_KEYS:
        session = "unknown"
    source = data.get("source") or ""

    # The plan file and the project file are read BEFORE the state is loaded, so the gap between
    # loading and saving the state stays as short as it was (another chat may write in between).
    plan, starts = plan_start(data.get("cwd"))
    state = load_state()
    if source == "clear":
        state.pop(session, None)  # /clear is a new continuum, never an inherited one
    entry = state.get(session)
    notice = None
    if not isinstance(entry, dict):
        entry = seed_entry(state, starts)
        state[session] = entry
        # The user is told at the start of a NEW chat only. A chat that already existed and lost its
        # record (pruned after 20 newer ones) is seeded again without a word.
        if starts and source not in CONTINUING_SOURCES:
            seen = state.get(PLAN_KEY)
            before = seen.get("plan") if isinstance(seen, dict) else None
            notice = plan_notice(plan, before if before in PLAN_NAMES and before != plan else None)
            state[PLAN_KEY] = {"plan": plan, "updated": utc_now()}
        save_state(state)

    line = (
        f"[agenting] {summary(normalize(entry))} · "
        f"{fmt_teammates(teammates_on(data.get('cwd')))} · "
        f"{fmt_advisor(advisor_state(data.get('cwd')))}"
        f"{f' · plan={plan}' if plan else ''} (session {session}). "
        f'Record changes: python3 "{SELF_PATH}" --record --session {session} '
        f"[--mode auto|manual] [--disposition cheapest|fast|balanced] [--workflows on|off]. "
        f"Load the agenting skill before moving bulk work off this chat or starting an agent, teammate or Workflow."
    )
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": line}}
    if notice:
        out["systemMessage"] = notice      # shown to the user, once, at the chat the plan started
    print(json.dumps(out))
    return 0


def record(args) -> int:
    session = args.session or "unknown"
    if session in RESERVED_KEYS:
        session = "unknown"
    _, starts = plan_start(os.getcwd())
    state = load_state()
    entry = state.get(session)
    if not isinstance(entry, dict):
        entry = seed_entry(state, starts)  # the same start SessionStart and --status would give
    v = normalize(entry)
    v.pop("was_quality", None)
    note = ""
    if args.mode:
        v["mode"] = args.mode
    if args.disposition:
        if args.disposition == REMOVED_DISPOSITION:
            args.disposition = DEFAULT_DISPOSITION
            note = f" ({QUALITY_GONE})"
        v["disposition"] = args.disposition
        v.pop("disposition_source", None)  # the user's own choice replaces the plan's start
        v.pop("plan", None)
    if args.workflows:
        v["workflows"] = args.workflows
        v.pop("workflows_source", None)  # a per-chat value replaces the standing default
    v["updated"] = utc_now()
    state[session] = v  # rewrites the entry, dropping legacy keys such as "suggestion"
    save_state(state)
    print(f"recorded: session {session}: {summary(v)}{note}")
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
    entry = state.get(session) if session not in RESERVED_KEYS else None
    plan, starts = plan_start(os.getcwd())
    tail = (f" · {fmt_teammates(teammates_on(os.getcwd()))} · "
            f"{fmt_advisor(advisor_state(os.getcwd()))} · {fmt_default(state)}"
            f"{f' · plan={plan}' if plan else ''}")
    if not isinstance(entry, dict):
        print(f"no state recorded for session {session} "
              f"(defaults: {summary(normalize(seed_entry(state, starts)))}){tail}")
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
    ap.add_argument("--disposition", choices=DISPOSITIONS + (REMOVED_DISPOSITION,))
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
