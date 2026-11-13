#!/usr/bin/env python3
"""
agent-routing-guard  --  PreToolUse hook on the Agent tool.

WHY THIS EXISTS
---------------
workflow-routing-guard.py keeps unrouted agent() calls out of Workflow scripts. A plain
Agent tool call has the same hole: with no `model` and no `effort` the subagent starts
on the main chat's tier. On a Fable or Opus chat that is the expensive tier by accident;
on a cheap chat it can under-power a task that needed more. This hook makes sure no agent
starts on the main chat's tier unless the caller said so on purpose.

It only ever DENIES or stays SILENT (plus one non-blocking note). It never emits
permissionDecision "allow" or "ask": whether the Agent tool may run at all is the
user's own permission setting, and an "allow" here would override it.

FACTS MEASURED ON 2026-11-13 WITH CLAUDE CODE 2.1.323
-----------------------------------------------------
  * An ordinary subagent (an Agent call with no `name`) applies the call's `model`
    and the call's `effort`.
  * With agent teams on (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1), an Agent call with a
    `name` starts a TEAMMATE (unless it is a fork or passes `isolation`). A teammate
    applies the call's `model`, but IGNORES the call's `effort`: asked `xhigh` and
    `low`, both ran at the settings default `medium`. A teammate started from an agent
    file runs at that file's `effort`; an `effort` on the call did not override it
    (file `low`, call `xhigh`, ran `low`).
  Consequence: for a teammate the only way to choose an effort is an agent file.

DECISION ORDER
--------------
  1. Not an Agent call, tool_input not an object, unreadable stdin, or ANY exception:
     exit 0, no output. The hook never blocks because of its own fault.
  2. subagent_type "fork": silent (a fork copies the main chat on purpose).
  3. The prompt holds a line that is exactly `routing: inherit` (case-insensitive,
     optional leading `//` or `#`): silent. The same words inside a sentence do not count.
  4. Resolve the agent file, if any, to learn what it pins: `agenting:<name>` ->
     <plugin root>/agents/<name>.md; another plugin's `<plugin>:<name>` -> the newest
     ~/.claude/plugins/cache/*/<plugin>/*/agents/<name>.md; a bare name ->
     <cwd>/.claude/agents/<name>.md, then ~/.claude/agents/<name>.md. Only the
     frontmatter's `model` and `effort` are read; `model: inherit` counts as not set.
     A built-in type has no file. Two of them bring their own model whatever the chat
     runs on (BUILT_IN_MODEL below), so the guard asks them for an effort only: asking
     for a model there would push a cheap helper onto a costlier tier.
  5. Teammate = `name` is a non-empty string AND agent teams are on AND `isolation` unset.
  6. model_ok  = the call has a model OR the file sets one.
     effort_ok = ordinary subagent: the call has an effort OR the file sets one;
                 teammate: ONLY the file sets one.
  7. Both ok: silent, except a teammate whose call effort differs from the file's gets a
     note (additionalContext, no permissionDecision): the call's effort is ignored.
  8. Otherwise DENY, with a reason that names what is missing and the chat's own tier
     (read from the last main-thread assistant record of the transcript).

The `agenting:` agents are exempt only because every agents/*.md of this plugin pins both
model and effort; tests/test_agent_guard.py checks that.
"""
import glob
import json
import os
import re
import sys

MAX_TAIL_BYTES = 2_000_000
SYNTHETIC_MODEL = "<synthetic>"
TEAMS_ENV = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INHERIT_LINE = re.compile(r"^[ \t]*(?://|#)?[ \t]*routing:[ \t]*inherit[ \t]*$", re.IGNORECASE | re.MULTILINE)
AGENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Built-in agent types that run on their own model, measured 2026-11-13 on Claude Code 2.1.323 from a
# claude-fable-5-2/xhigh chat with no model on the call: claude-code-guide ran on Haiku 5.5 and
# statusline-setup on Sonnet 5.5. Explore ran on Opus 5.5 at xhigh and Plan on Fable 5.2 at xhigh
# in the same check, so they are deliberately absent: they need a model like any other start.
BUILT_IN_MODEL = {"claude-code-guide": "haiku", "statusline-setup": "sonnet"}


# ------------------------------------------------------------------ small readers


def text_of(value):
    """The stripped string, or "" when the value is not a non-empty string."""
    return value.strip() if isinstance(value, str) else ""


def teams_on() -> bool:
    return os.environ.get(TEAMS_ENV, "").strip().lower() in ("1", "true")


def frontmatter_pins(path):
    """(model, effort) an agent file pins, each "" when not set. `model: inherit` is not set."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return "", ""
    if not lines or lines[0].strip() != "---":
        return "", ""
    pins = {"model": "", "effort": ""}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^(model|effort)[ \t]*:[ \t]*(.*)$", line)
        if not m:
            continue
        value = re.sub(r"[ \t]+#.*$", "", m.group(2)).strip().strip("\"'").strip()
        pins[m.group(1)] = value
    if pins["model"].lower() == "inherit":
        pins["model"] = ""
    return pins["model"], pins["effort"]


def agent_file_pins(subagent_type, cwd):
    """(model, effort) pinned by the agent file `subagent_type` points at; ("", "") when none."""
    kind = text_of(subagent_type)
    if not kind:
        return "", ""
    if kind.startswith("agenting:"):
        name = kind[len("agenting:"):]
        if not AGENT_NAME.match(name):
            return "", ""
        return frontmatter_pins(os.path.join(PLUGIN_ROOT, "agents", name + ".md"))
    if ":" in kind:
        plugin, _, name = kind.partition(":")
        if not AGENT_NAME.match(plugin) or not AGENT_NAME.match(name):
            return "", ""
        found = glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache", "*", plugin, "*",
                                       "agents", name + ".md"))
        if not found:
            return "", ""
        return frontmatter_pins(max(found, key=os.path.getmtime))
    if not AGENT_NAME.match(kind):
        return "", ""
    candidates = []
    if text_of(cwd):
        candidates.append(os.path.join(cwd, ".claude", "agents", kind + ".md"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".claude", "agents", kind + ".md"))
    for path in candidates:
        if os.path.isfile(path):
            return frontmatter_pins(path)
    return BUILT_IN_MODEL.get(kind, ""), ""


def is_real_main_assistant(d):
    """A main-thread assistant line that names a real model (as in cache-tripwire.py)."""
    if not isinstance(d, dict) or d.get("type") != "assistant" or d.get("isSidechain"):
        return False
    message = d.get("message")
    if not isinstance(message, dict):
        return False
    model = message.get("model")
    return isinstance(model, str) and model != "" and model != SYNTHETIC_MODEL


def find_last_main_assistant(path):
    size = os.path.getsize(path)
    tail_bytes = 65536
    cap = max(size, MAX_TAIL_BYTES)
    while True:
        with open(path, "rb") as f:
            seek_to = max(0, size - tail_bytes)
            f.seek(seek_to)
            chunk = f.read()
        for line in reversed(chunk.decode("utf-8", errors="replace").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not is_real_main_assistant(d):
                continue
            return d
        if seek_to == 0 or tail_bytes >= cap:
            return None
        tail_bytes *= 4


def chat_tier(transcript_path):
    """(model, effort) of the main chat's latest assistant record; ("", "") when unreadable."""
    try:
        path = text_of(transcript_path)
        if not path:
            return "", ""
        last = find_last_main_assistant(path)
        if not last:
            return "", ""
        return text_of(last["message"].get("model")), text_of(last.get("effort"))
    except Exception:
        return "", ""


# ----------------------------------------------------------------------- output


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


def note(context: str) -> int:
    """No permission opinion: additionalContext only, never a permissionDecision."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": context}}))
    return 0


INHERIT_HINT = 'To inherit on purpose, put a line "routing: inherit" in the prompt.'
AGENT_HINT = "or use an agenting: agent, which sets them itself."


def teammate_reason(subject, model_missing):
    lead = f'{subject} has no model, and cannot' if model_missing else f"{subject} cannot"
    return (
        f"[agenting] {lead} be given an effort on the call: on this Claude Code version a teammate takes its "
        "effort only from an agent file, and an effort written on the call is ignored (measured 2026-11-13, "
        "CLI 2.1.323). Start it from an agenting: agent whose tier fits (agenting:coder sonnet/low, "
        "agenting:researcher sonnet/medium, agenting:coder-ts sonnet/high, agenting:reviewer opus/xhigh), "
        "or drop the name to start a one-off agent, where model and effort on the call both apply. "
        + INHERIT_HINT
    )


def ordinary_reason(subject, model_missing, effort_missing, model, effort):
    tier = f" ({model}/{effort or '?'})" if model else ""
    if model_missing and effort_missing:
        return (
            f"[agenting] {subject} has no model and no effort. It would run on this chat's tier{tier}. "
            f'Add both from the routing table, for example model: "sonnet", effort: "low", {AGENT_HINT} '
            + INHERIT_HINT
        )
    if model_missing:
        return (
            f"[agenting] {subject} has no model. It would run on this chat's model"
            f"{f' ({model})' if model else ''}. "
            f'Add one from the routing table, for example model: "sonnet", {AGENT_HINT} ' + INHERIT_HINT
        )
    return (
        f"[agenting] {subject} has no effort. Its effort would come from the settings default for that model, "
        f'not from the routing table. Add one, for example effort: "low", {AGENT_HINT} ' + INHERIT_HINT
    )


# ------------------------------------------------------------------------- main


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    if tool_input.get("subagent_type") == "fork":
        return 0
    prompt = tool_input.get("prompt")
    if isinstance(prompt, str) and INHERIT_LINE.search(prompt):
        return 0

    file_model, file_effort = agent_file_pins(tool_input.get("subagent_type"), payload.get("cwd"))
    call_model = text_of(tool_input.get("model"))
    call_effort = text_of(tool_input.get("effort"))
    name = text_of(tool_input.get("name"))
    teammate = bool(name) and teams_on() and not tool_input.get("isolation")

    model_ok = bool(call_model or file_model)
    effort_ok = bool(file_effort) if teammate else bool(call_effort or file_effort)

    if model_ok and effort_ok:
        if teammate and call_effort and call_effort != file_effort:
            return note(
                f'[agenting] Teammate "{name}": the effort "{call_effort}" written on the call is ignored for a '
                f'teammate; it runs at the agent file\'s effort "{file_effort}".'
            )
        return 0

    if teammate:
        subject = f'Teammate "{name}"'
    else:
        description = " ".join(text_of(tool_input.get("description")).split())[:60]
        subject = f'Agent start "{description}"'
    model, effort = chat_tier(payload.get("transcript_path"))

    if teammate and not effort_ok:
        reason = teammate_reason(subject, not model_ok)
        system_msg = "agenting: a teammate start could not carry an effort; Claude is retrying from an agenting: agent"
    else:
        reason = ordinary_reason(subject, not model_ok, not effort_ok, model, effort)
        system_msg = "agenting: an agent start had no model or effort; Claude is retrying with both set"
    return deny(reason, system_msg)


def main() -> int:
    try:
        return run_hook()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
