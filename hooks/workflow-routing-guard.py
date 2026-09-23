#!/usr/bin/env python3
"""
workflow-routing-guard  --  PreToolUse hook on the Workflow tool.

WHY THIS EXISTS
---------------
Inside a workflow script, an agent() call with no `model` / `effort` inherits
the main-loop model and the session effort. On 2026-08-06 a 16-agent recon
workflow burned 4.45M subagent tokens (~$320 at Opus list rates) that way;
three of those agents did nothing but count files.

But cost is only half of it. Subagents are a *tier* mechanism: the session runs
at one model and one effort, and agent() calls are the only way to use several
tiers at once. So on a cheap session the risk is not overspending — it is
UNDER-POWERING a task that needed Opus. The gate therefore looks both ways:
cheaper AND higher quality.

TWO-STAGE GATE
--------------
  1. ROUTING: if any agent() call lacks model/agentType or lacks effort, DENY.
     Never bypassable -- mode has no say here. `agentType: 'agenting:<name>'`
     (this plugin's agents/, addressed with the plugin prefix) counts as routed.
  2. APPROVAL: even when every call is routed, DENY until the user has approved
     this particular routing plan in this session. Claude presents the plan
     (as proposed / cheaper / higher quality), applies the answer, records the
     approval with --approve, and re-runs.

     AUTO MODE: if this session's mode is explicitly recorded as "auto" in
     <state dir>/.agenting-session-state.json (written by the sibling
     SessionStart hook, hooks/session-continuity.py), Stage 2 drops its
     routing opinion entirely -- no --approve round-trip -- but stays silent on
     PERMISSION (see OUTPUT CONTRACT below). Only an explicit "auto" does this.
     A missing entry, a missing file, legacy "semi-auto" or anything else
     keeps the approval requirement, so an install where the continuity hook
     is absent degrades to asking rather than to a bypass nobody configured.

The same plan re-run in the same session passes silently. Change any tier and
the signature changes, so it asks again (except in auto mode, which never asks).

SINGLE Agent CALLS ARE OUT OF SCOPE
-----------------------------------
Deliberate: every agent definition in this plugin's agents/ pins both model and
effort, and one agent is bounded and cheap. A gate there costs more attention
than it saves. The "sometimes ask" cases where the tier and the task genuinely
disagree belong to the agenting skill, not to this hook.

STATE DIR
---------
$AGENTING_STATE_DIR if set (tests use this), else ~/.claude. Holds
.routing-approvals.json (written here, by --approve) and
.agenting-session-state.json (read-only here).

OUTPUT CONTRACT
---------------
PreToolUse -> hookSpecificOutput.permissionDecision ("deny" only -- this
              file never emits "allow"/"ask") + permissionDecisionReason, OR
              a bare `{"systemMessage": ...}` with NO hookSpecificOutput at
              all (the auto-mode bypass note() -- a visible remark with no
              permission opinion), OR truly empty stdout (every other
              pass-through case: "nothing to say about this call").
              permissionDecision:"allow" is deliberately never used, because
              it would override the user's OWN Claude Code permission
              settings for the Workflow tool, not just this plugin's routing
              approval -- a stronger claim than this hook should ever make.
"""

import argparse
import hashlib
import json
import os
import re
import sys

ESCAPE_HATCH = "routing: inherit"
MAX_REPORTED = 12
STATE_DIR = os.path.expanduser(os.environ.get("AGENTING_STATE_DIR") or "~/.claude")
APPROVALS_PATH = os.path.join(STATE_DIR, ".routing-approvals.json")
# Same file session-continuity.py's SessionStart hook writes -- read-only from
# here; this script only checks whether the mode was explicitly "auto".
SESSION_STATE_PATH = os.path.join(STATE_DIR, ".agenting-session-state.json")
KEEP_SESSIONS = 20
SELF_PATH = os.path.abspath(__file__)


# --------------------------------------------------------------- script parsing


def strip_comments_and_strings(src: str) -> str:
    """Blank out comments and string bodies, preserving length.

    Length is preserved because indices computed here (line numbers, the
    position of an agent( call) are used against the original text too.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            if i + 1 < n:
                out[i] = out[i + 1] = " "
                i += 2
        elif c in "'\"`":
            quote = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    out[i] = " "
                    if i + 1 < n and src[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if src[i] == quote:
                    out[i] = " "
                    i += 1
                    break
                if src[i] != "\n":
                    out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def find_agent_calls(src: str):
    """Yield (start, clean_call, raw_call), scanning with balanced parens."""
    clean = strip_comments_and_strings(src)
    for m in re.finditer(r"(?<![\w.$])agent\s*\(", clean):
        start = m.start()
        i = m.end() - 1
        depth = 0
        while i < len(clean):
            if clean[i] == "(":
                depth += 1
            elif clean[i] == ")":
                depth -= 1
                if depth == 0:
                    yield start, clean[start : i + 1], src[start : i + 1]
                    break
            i += 1


def opts_span(clean_call: str):
    """Return (start, end) of the last {...} block inside an agent(...) call.

    Indices are returned because they get applied to two different strings: a
    key's PRESENCE is checked against the stripped text (so the word "model:"
    inside a prompt is not mistaken for routing), while its VALUE is read from
    the raw text (stripping blanks out everything inside quotes).
    """
    last_open = clean_call.rfind("{")
    if last_open == -1:
        return None
    depth = 0
    for j in range(last_open, len(clean_call)):
        if clean_call[j] == "{":
            depth += 1
        elif clean_call[j] == "}":
            depth -= 1
            if depth == 0:
                return last_open, j + 1
    return last_open, len(clean_call)


def has_key(clean_opts: str, key: str) -> bool:
    return re.search(rf"\b{key}\s*:", clean_opts) is not None


def kv(raw_opts: str, key: str) -> str:
    """Extract key: 'value' from the raw opts text; empty string if absent."""
    m = re.search(rf"\b{key}\s*:\s*['\"]([^'\"]+)['\"]", raw_opts)
    return m.group(1) if m else ""


def has_escape_hatch(src: str, start: int) -> bool:
    """True if `routing: inherit` appears on this line or the one above it."""
    line_start = src.rfind("\n", 0, start) + 1
    line_end = src.find("\n", start)
    line_end = len(src) if line_end == -1 else line_end
    this_line = src[line_start:line_end]
    prev_start = src.rfind("\n", 0, line_start - 1) + 1 if line_start > 0 else 0
    prev_line = src[prev_start : max(line_start - 1, 0)]
    return ESCAPE_HATCH in this_line or ESCAPE_HATCH in prev_line


def load_script(tool_input: dict):
    """Return (script_text, source_label); (None, reason) if not inspectable."""
    script = tool_input.get("script")
    if isinstance(script, str) and script.strip():
        return script, "inline script"
    path = tool_input.get("scriptPath")
    if isinstance(path, str) and path:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8") as fh:
                return fh.read(), f"scriptPath {path}"
        except OSError:
            return None, f"could not read scriptPath: {path}"
    if tool_input.get("name"):
        return None, "named workflow"
    return None, "no script"


# -------------------------------------------------------------------- approvals


def load_approvals() -> dict:
    try:
        with open(APPROVALS_PATH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_approvals(d: dict) -> None:
    if len(d) > KEEP_SESSIONS:
        d = dict(list(d.items())[-KEEP_SESSIONS:])
    try:
        os.makedirs(os.path.dirname(APPROVALS_PATH), exist_ok=True)
        tmp = APPROVALS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)
        os.replace(tmp, APPROVALS_PATH)
    except Exception:
        pass


def plan_signature(tiers) -> str:
    """Build a stable signature from the (model, effort) counts."""
    counts = {}
    for model, effort in tiers:
        key = (model or "inherit", effort or "inherit")
        counts[key] = counts.get(key, 0) + 1
    return "|".join(f"{m}/{e}x{n}" for (m, e), n in sorted(counts.items()))


def plan_hash(sig: str) -> str:
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]


def explicit_auto_mode(session: str) -> bool:
    """True only if session-continuity.py explicitly recorded "auto" for this
    session_id. A missing/unreadable file, a missing entry, or legacy
    "semi-auto" returns False -- the safe default (see the module docstring)."""
    try:
        with open(SESSION_STATE_PATH, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        return (state.get(session) or {}).get("mode") == "auto"
    except Exception:
        return False


# ------------------------------------------------------------------------- main


def deny(reason: str, system_msg: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": system_msg,
            }
        )
    )
    return 0


def note(system_msg: str) -> int:
    """No permission opinion -- deliberately does NOT set permissionDecision,
    unlike deny(). This hook's job is Workflow ROUTING approval only; whether
    the Workflow tool may run at all is the user's own Claude Code permission
    setting (defaultMode, an allowlist, etc.), and a `permissionDecision:
    "allow"` here would override that entirely, not just this plugin's own
    approval step -- exactly the gap between "I have no opinion" (the
    pre-existing silent `return 0` pass-through, used everywhere else in this
    file that isn't a deliberate deny) and "I am overriding your permission
    settings" (which nothing in this file should ever do). Used only for the
    auto-mode Stage-2 bypass, so the auto-approval is visible via
    systemMessage instead of being a silent no-op, without touching the
    underlying permission decision."""
    print(
        json.dumps(
            {
                "systemMessage": system_msg,
            }
        )
    )
    return 0


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # malformed input must not break the hook

    if payload.get("tool_name") != "Workflow":
        return 0

    session = payload.get("session_id") or "unknown"
    src, label = load_script(payload.get("tool_input") or {})
    if src is None:
        return 0  # cannot inspect it, so do not block it

    unrouted, tiers = [], []
    for start, clean_call, raw_call in find_agent_calls(src):
        if has_escape_hatch(src, start):
            tiers.append(("inherit", "inherit"))
            continue
        span = opts_span(clean_call)
        clean_opts = clean_call[span[0] : span[1]] if span else ""
        raw_opts = raw_call[span[0] : span[1]] if span else ""
        line = src.count("\n", 0, start) + 1
        snippet = " ".join(raw_call.split())[:70]

        # PRESENCE from the stripped text, VALUE from the raw text.
        if not (has_key(clean_opts, "model") or has_key(clean_opts, "agentType")):
            unrouted.append((line, "no model, no effort", snippet))
        elif not has_key(clean_opts, "effort"):
            unrouted.append((line, "no effort", snippet))
        else:
            model = kv(raw_opts, "model")
            atype = kv(raw_opts, "agentType")
            effort = kv(raw_opts, "effort") or "?"
            tiers.append((model or (f"agent:{atype}" if atype else "?"), effort))

    if not tiers and not unrouted:
        return 0  # no agent() calls at all

    # --- STAGE 1: missing routing ------------------------------------------
    if unrouted:
        rows = "\n".join(
            f"    line {ln:>4}  [{why}]  {sn}…" for ln, why, sn in unrouted[:MAX_REPORTED]
        )
        more = (
            f"\n    … and {len(unrouted) - MAX_REPORTED} more"
            if len(unrouted) > MAX_REPORTED
            else ""
        )
        return deny(
            f"""STAGE 1/2 — MISSING ROUTING: {len(unrouted)} agent() call(s) specify no model/effort ({label}).

Unrouted calls INHERIT the main-loop model and the session effort. That cuts
both ways: wasted spend on an expensive session, and an under-powered agent on
a cheap one.

{rows}{more}

DO THIS: give every agent() call a model (or agentType) AND an effort, e.g.
  {{model: 'haiku', effort: 'low'}}  or  {{agentType: 'agenting:researcher', effort: 'medium'}}
Tier table: load the agenting skill if it isn't loaded yet.

For deliberate inheritance, put `// {ESCAPE_HATCH}` on that line or the one above it.""",
            f"Workflow stopped (1/2): {len(unrouted)} agent() call(s) have no routing.",
        )

    # --- STAGE 2: plan approval --------------------------------------------
    sig = plan_signature(tiers)
    h = plan_hash(sig)

    if explicit_auto_mode(session):
        return note(
            f"Workflow routing auto-approved ({len(tiers)} agents, auto mode, "
            f"plan {h}) — no --approve round-trip needed. Your own Claude Code "
            f"permission settings, if any, still apply to running Workflow itself."
        )

    if h in load_approvals().get(session, []):
        return 0  # this plan was already approved in this session

    counts = {}
    for model, effort in tiers:
        counts[(model, effort)] = counts.get((model, effort), 0) + 1
    table = "\n".join(
        f"    {n:>3} agent(s)   {m:<16} effort: {e}"
        for (m, e), n in sorted(counts.items(), key=lambda x: -x[1])
    )

    return deny(
        f"""STAGE 2/2 — PLAN APPROVAL: {len(tiers)} agents, all routed. Waiting on the user
(this session is in manual mode, or has no recorded mode). Procedure: the agenting skill.

{table}

{len(tiers)} agents total.  Plan signature: {sig}

DO THIS, in order:
  1. Put this plan to the user with AskUserQuestion. Offer ALL THREE
     directions, not just "cheaper":
       [as proposed]     the plan above
       [cheaper/faster]  name which agents you would step down a tier
       [higher quality]  name which agents you would step up a tier
     If the session is on a cheap tier (sonnet/medium), lead with the UPGRADE
     option; on an expensive tier (opus/xhigh), lead with the DOWNGRADE option.
  2. Apply the answer to the script. Changing the plan changes the signature,
     so the gate will ask again — that is intended.
  3. Record the approval:
       python3 "{SELF_PATH}" --approve {h} --session {session}
  4. Run the Workflow again.

The same plan re-run in this session will not ask again.""",
        f"Workflow stopped (2/2): a {len(tiers)}-agent routing plan is awaiting approval.",
    )


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--approve")
    ap.add_argument("--session")
    args, _ = ap.parse_known_args()

    if args.approve:
        session = args.session or "unknown"
        d = load_approvals()
        d.setdefault(session, [])
        if args.approve not in d[session]:
            d[session].append(args.approve)
        save_approvals(d)
        print(f"approved: plan {args.approve} (session {session})")
        return 0

    return run_hook()


if __name__ == "__main__":
    sys.exit(main())
