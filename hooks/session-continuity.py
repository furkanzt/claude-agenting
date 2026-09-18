#!/usr/bin/env python3
"""
session-continuity  --  SessionStart hook carrying three per-session axes --
mode (manual/semi-auto/auto), auto-disposition (fast/balanced/quality), and
the suggestion axis (on/off) -- across compaction within one chat continuum.

WHY THIS EXISTS
----------------
All three axes used to live in conversational memory only (skills/agenting/
SKILL.md, pre-2.1.0): nothing was written to disk, so a compaction that
summarized the conversation could silently drop "the user set semi-auto" or
"they picked quality," falling back to the written default with no signal
that anything changed.

Claude Code keeps ONE session_id across a compaction of the same
conversation -- verified empirically against this user's own ultralearning
session-log (~/Desktop/impark/furkansal/ultralearning/session-log/
compact-*.md): three separate compaction events spanning ~9 hours shared one
session_id prefix. Resume (--resume/--continue) is NOT independently
verified here; it's assumed to keep the same id by Claude Code's own design,
same as compaction -- if that assumption is ever wrong, resume degrades to
re-asking once (suggestion) or a fresh default (disposition), not to silent
data loss. A "startup" of a genuinely new conversation gets a fresh id, so it
starts back at the defaults correctly. `/clear` is a deliberate new
continuum, not a continuation, and its source is handled explicitly below
rather than trusted to also get a fresh id.

Default mode is now `auto` (2.1.0; was `manual`).

DISPOSITION HAS NO ASK -- IT JUST DEFAULTS (final 2.1.0 design)
-----------------------------------------------------------------
This went through two wrong drafts before landing here, both corrected by
the user directly, not guessed at:
  1. First draft asked the disposition question immediately in the
     SessionStart additionalContext -- every session, every project, even
     ones that never touch routing. Rejected: far too eager.
  2. Second draft moved the ask into the agenting skill's own procedure, to
     fire lazily right before auto's first self-decided plan. Better, but
     still an ask -- and the user's actual answer, once given directly, was
     simpler than either: disposition should just default to `balanced` and
     stay there, silently, forever, for this axis. `balanced` already picks
     cheap vs. expensive per task automatically (see the routing table), so
     there's nothing to ask about most of the time. `fast`/`quality` are
     available, but ONLY by explicit user request -- natural language or
     `/agenting-mode <disposition>` -- never suggested, never inferred from
     a pattern of frequent quality-tier picks ("if it works, it works" was
     the user's own words for why no drift-tracking exists either).
So THIS HOOK NEVER ASKS ANYTHING, and disposition specifically is never
`null` -- it is seeded `"balanced"` on first sight of a session_id and stays
whatever it was last explicitly set to, full stop.

The suggestion axis (separate: "want workflow suggestions proactively
flagged?") is NOT the same as disposition and keeps its own lazy,
once-per-continuum ask, driven by the agenting skill at the first
workflow-shaped task -- the user confirmed that one stays as designed. It
alone can be `null` ("not yet asked").

STATE
-----
~/.claude/.agenting-session-state.json -- deliberately the SAME directory as
the routing guard's own ~/.claude/.routing-approvals.json
(workflow-routing-guard.py), and deliberately NOT a path next to this script:
the installed plugin lives in a VERSIONED cache directory
(~/.claude/plugins/cache/agenting/agenting/<version>/), so a path relative to
__file__ would orphan its state on every plugin update. A fixed user-level
path survives that.

    { session_id: {"mode": "auto", "disposition": "balanced",
                    "suggestion": "on"|"off"|null, "updated": iso8601} }

`disposition` always holds a concrete value -- `null` never appears there.
`suggestion` being `null` means "not yet asked"; that IS still a valid state
for that one field. workflow-routing-guard.py's Stage 2 reads `mode` from
this same file to decide whether it can drop its approval requirement: only
an explicitly recorded "auto" does that (via a bare systemMessage, never
permissionDecision:"allow" -- that field would override the user's own
Claude Code permission settings for the Workflow tool, not just this
plugin's routing opinion); a missing entry does NOT trigger it, precisely so
that hook keeps today's safe behavior if this hook is ever absent or not yet
wired up.

CLI
---
Hook mode (default): reads the SessionStart JSON payload from stdin, prints
hookSpecificOutput.additionalContext.

  --record --session <id> [--mode manual|semi-auto|auto]
                           [--disposition fast|balanced|quality]
                           [--suggestion on|off]
      Persist the given axis value(s) for that session_id. Mirrors the
      routing guard's `--approve` idiom. For disposition, this only ever
      runs off an explicit user request -- there is no "after asking" case
      to mirror for that one field anymore.

  --status --session <id>
      Print the recorded state for that session_id (or "no state recorded"),
      for /agenting-mode to report ground truth instead of relying on
      conversational recall that may have been summarized away, and for the
      skill's lazy suggestion-ask to check "has this already been asked?"
      before asking.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

STATE_PATH = os.path.expanduser("~/.claude/.agenting-session-state.json")
KEEP_SESSIONS = 20
SELF_PATH = os.path.abspath(__file__)

MODES = ("manual", "semi-auto", "auto")
DISPOSITIONS = ("fast", "balanced", "quality")
SUGGESTIONS = ("on", "off")
DEFAULT_MODE = "auto"
DEFAULT_DISPOSITION = "balanced"


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
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
        d = dict(sorted(d.items(), key=lambda kv: kv[1].get("updated", ""))[-KEEP_SESSIONS:])
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


def emit(context: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


def fmt_suggestion(value):
    return value if value else "not yet set (ask lazily when first relevant, then record it)"


def run_hook() -> int:
    data = read_hook_input()
    session = data.get("session_id") or "unknown"
    cwd = data.get("cwd") or ""
    source = data.get("source") or ""

    state = load_state()
    if source == "clear":
        # /clear is a deliberate new continuum. If Claude Code ever reuses the
        # same session_id across a /clear (unverified either way -- see the
        # module docstring), don't inherit stale state onto it regardless.
        state.pop(session, None)
    entry = state.get(session)

    if entry is not None:
        mode = entry.get("mode", DEFAULT_MODE)
        disp = entry.get("disposition") or DEFAULT_DISPOSITION
        sugg = fmt_suggestion(entry.get("suggestion"))
        return emit(
            f"[agenting] Session state carried over from earlier in this chat continuum "
            f"(session {session}): mode={mode}, disposition={disp}, suggestion={sugg}. "
            f"Anything already set here must not be re-asked -- apply it silently for the "
            f"rest of this session, including across further compaction. Disposition is "
            f"never asked about at all, only changed on explicit user request. "
            f"session_id and recorder path for /agenting-mode: {session} / \"{SELF_PATH}\"."
        )

    # First SessionStart this session_id has ever produced: silently seed the
    # defaults. Mode defaults to `auto`; disposition defaults to `balanced`
    # and is NEVER asked about (see module docstring) -- only the suggestion
    # axis is lazily asked later, by the agenting skill's own procedure, the
    # first time a task looks workflow-shaped.
    state[session] = {
        "mode": DEFAULT_MODE,
        "disposition": DEFAULT_DISPOSITION,
        "suggestion": None,
        "updated": utc_now(),
    }
    save_state(state)

    return emit(
        f"[agenting] New chat continuum (session_id: {session}, cwd: {cwd or 'unknown'}). "
        f"Mode defaults to `auto` (Stage-2 workflow-routing questions self-decided, not "
        f"asked, unless changed). Disposition defaults to `balanced` and is NEVER asked "
        f"about -- it only changes on explicit user request (natural language or "
        f"/agenting-mode fast|balanced|quality), or a project's agenting/AGENTING.md Config "
        f"knob auto-disposition-default, if the first read of that file this continuum "
        f"finds one pinned AND --status still shows the seeded balanced (an earlier explicit "
        f"user choice this continuum must not be overwritten by a later-read pin); do not "
        f"suggest changing it yourself, even if quality- or fast-tier picks turn out to be "
        f"frequent this continuum. The "
        f"workflow-suggestion preference is separate and unset for now -- ask about THAT "
        f"one lazily, once, the first time a task actually looks workflow-shaped this "
        f"continuum, per skills/agenting/SKILL.md. Recorder path for persisting any change "
        f"(mode, disposition, or the suggestion answer once asked): "
        f'"{SELF_PATH}" (--record --session {session} ..., or --status --session {session} '
        f"to check current state)."
    )


def record(args) -> int:
    session = args.session or "unknown"
    state = load_state()
    entry = state.setdefault(
        session, {"mode": DEFAULT_MODE, "disposition": DEFAULT_DISPOSITION, "suggestion": None}
    )
    if args.mode:
        entry["mode"] = args.mode
    if args.disposition:
        entry["disposition"] = args.disposition
    if args.suggestion:
        entry["suggestion"] = args.suggestion
    entry["updated"] = utc_now()
    save_state(state)
    print(
        f"recorded: session {session} mode={entry['mode']} "
        f"disposition={entry['disposition']} suggestion={entry['suggestion']}"
    )
    return 0


def status(args) -> int:
    session = args.session or "unknown"
    entry = load_state().get(session)
    if not entry:
        print(f"no state recorded for session {session} (default: mode={DEFAULT_MODE}, disposition={DEFAULT_DISPOSITION}, suggestion unset)")
        return 0
    mode = entry.get("mode", DEFAULT_MODE)
    disp = entry.get("disposition") or DEFAULT_DISPOSITION
    sugg = fmt_suggestion(entry.get("suggestion"))
    print(f"session {session}: mode={mode} disposition={disp} suggestion={sugg}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--session")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--disposition", choices=DISPOSITIONS)
    ap.add_argument("--suggestion", choices=SUGGESTIONS)
    args, _ = ap.parse_known_args()

    if args.record:
        if not (args.mode or args.disposition or args.suggestion):
            print("nothing to record: pass --mode and/or --disposition and/or --suggestion", file=sys.stderr)
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
