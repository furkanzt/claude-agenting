#!/usr/bin/env python3
"""The guard and the log of an Antigravity eval run (probes/agy_bench.py).

agy has no --tools or --system-prompt flag, so an eval run is shaped by a custom agent
(eval-runner.md) and by this hook, both installed one level ABOVE the per-run working
directories (private/work/.agents/), where agy finds them by walking up from the run's cwd.
Nothing is ever written inside a working directory: a scan task counts every file there.

Per event, stdin is agy's camelCase JSON payload. The hook:
- appends one line to <work>/hooklogs/<conversationId>.jsonl (model, cwd, workspace, tool,
  decision), which agy_bench reads to check the run's validity;
- on PreToolUse, decides. The policy of a run is <work>/policy/<cwd basename>.json, written by
  agy_bench before the run: {"tools": [...]}. No policy file means every tool is denied (fail
  closed). An allowed tool is still denied when any path argument resolves outside the run's cwd,
  and run_command is allowed only for a read-only command allowlist (no redirection, no
  substitution, no parent paths, no absolute path outside the cwd).

Stdout is always one JSON object: {"decision": ...} on PreToolUse, {} otherwise.
"""
import json
import os
import shlex
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))          # <work>/.agents/evalhook -> <work>

READ_ONLY_COMMANDS = {
    "find", "ls", "grep", "egrep", "fgrep", "wc", "cat", "head", "tail", "sort", "uniq", "cut",
    "tr", "file", "stat", "du", "basename", "dirname", "nl", "comm", "diff", "printf", "echo",
    "true", "pwd", "tree", "md5", "shasum",
}
FIND_ACTIONS_DENIED = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0",
                       "-fprintf", "-fls"}
SEPARATORS = {"|", "||", "&&", ";"}
# "$" covers variables ($HOME) and substitution; a newline is a command separator to sh.
FORBIDDEN_CHARS = (">", "<", "`", "$", "\n", "\r")


def inside(path, cwd):
    p = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
    return p == cwd or p.startswith(cwd + os.sep)


def check_path_arg(value, cwd):
    """None when the string is not a path outside the cwd, else a reason."""
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("~") or ".." in value.split("/"):
        return "parent or home path"
    if value.startswith("/") and not inside(value, cwd):
        return "path outside the working directory"
    return None


def check_command(line, cwd):
    """None when the command line is read-only and stays inside the cwd, else a reason."""
    if any(c in line for c in FORBIDDEN_CHARS):
        return "redirection or substitution"
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars="|&;")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return "unparseable command"
    if not tokens:
        return "empty command"
    expect_command = True
    current = None
    for tok in tokens:
        if tok in SEPARATORS:
            expect_command = True
            continue
        if all(c in "|&;" for c in tok):
            return f"operator not allowed: {tok}"
        if expect_command:
            if "=" in tok and not tok.startswith("-"):
                return "environment assignment"
            current = os.path.basename(tok)
            if current not in READ_ONLY_COMMANDS:
                return f"command not allowed: {current}"
            expect_command = False
            continue
        if current == "find" and tok in FIND_ACTIONS_DENIED:
            return f"find action not allowed: {tok}"
        reason = check_path_arg(tok, cwd)
        if reason:
            return reason
    return None


def decide(payload):
    """The PreToolUse answer for one payload: {"decision": "allow"|"deny", "reason"?}."""
    cwd = os.path.realpath(payload.get("cwd") or "/nonexistent")
    tool = (payload.get("toolCall") or {}).get("name")
    args = (payload.get("toolCall") or {}).get("args") or {}
    policy_path = os.path.join(WORK, "policy", os.path.basename(cwd) + ".json")
    try:
        with open(policy_path) as f:
            allowed = set(json.load(f).get("tools") or [])
    except (OSError, ValueError):
        allowed = set()
    if tool not in allowed:
        return {"decision": "deny", "reason": f"tool {tool} is not available in this task"}
    for key, value in args.items():
        if key == "CommandLine":
            continue
        reason = check_path_arg(value, cwd)
        if reason:
            return {"decision": "deny", "reason": f"{key}: {reason}"}
    if tool == "run_command":
        reason = check_command(str(args.get("CommandLine") or ""), cwd)
        if reason:
            return {"decision": "deny", "reason": f"run_command: {reason}"}
    return {"decision": "allow"}


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    event = payload.get("hookEventName")
    out = decide(payload) if event == "PreToolUse" else {}
    tc = payload.get("toolCall") or {}
    rec = {"t": time.time(), "event": event, "modelName": payload.get("modelName"),
           "conversationId": payload.get("conversationId"), "cwd": payload.get("cwd"),
           "workspacePaths": payload.get("workspacePaths"), "tool": tc.get("name"),
           "decision": out.get("decision")}
    logdir = os.path.join(WORK, "hooklogs")
    try:
        os.makedirs(logdir, exist_ok=True)
        name = os.path.basename(str(payload.get("conversationId") or "unknown")) + ".jsonl"
        with open(os.path.join(logdir, name), "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    print(json.dumps(out))


if __name__ == "__main__":
    main()
