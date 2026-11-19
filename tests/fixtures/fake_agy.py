#!/usr/bin/env python3
"""A stub for the Antigravity CLI (`agy`) used by tests/test_agy_bench.py. No network, no model.

It behaves like the real CLI where evals/probes/agy_bench.py depends on it:

  agy --version                     prints FAKE_AGY_VERSION (default "1.5.12")
  agy -p /usage                     prints the meter table (tab separated, like agy 1.5.12)
  agy --agent A --model M --settings S --output-format json --print-timeout Ns -p=<prompt>
                                    runs one "turn" in the cwd and prints the JSON result

Like the real CLI, a run walks up from its cwd to find `.agents/hooks.json` and runs the hook
commands it registers (cwd = the .agents directory, payload as camelCase JSON on stdin):
SessionStart and Stop always, and one PreToolUse when FAKE_AGY_TOOL is set. So the real guard
hook (evals/agy/eval_hook.py, installed by `agy_bench setup`) writes the hook log for real.

FAKE_AGY_MODE selects the run's behaviour:
  ok            valid run; response FAKE_AGY_ANSWER (default: an answer block with 42)
  wrong_model   the hook payload's modelName differs from --model
  helper        a second conversation (a helper) starts in the same cwd
  workspace     the SessionStart payload's workspacePaths is another directory
  status_error  status ERROR with a non-quota error
  empty         status SUCCESS with an empty response
  bad_json      prints text that is not JSON
  no_hook       runs no hook at all
  timeout       sleeps 60 s (the bench must kill it)
  meters_fail   `-p /usage` prints garbage and exits 1
FAKE_AGY_QUOTA_MODELS: comma-separated model ids whose runs end with a quota error.
FAKE_AGY_METERS: JSON {"claude": [weekly, five_hour], "gemini": [weekly, five_hour], "argon": weekly}
(default all 100).
FAKE_AGY_TOOL: JSON {"name": ..., "args": {...}} for one PreToolUse call during the run.
FAKE_AGY_LOG: append one JSON line per run: argv, cwd, the files under cwd, the hook decision.
"""

import json
import os
import subprocess
import sys
import time
import uuid

DEFAULT_ANSWER = "Working it out.\n===ANSWER===\n42\n===END==="


def meters():
    m = json.loads(os.environ.get("FAKE_AGY_METERS") or "{}")
    c = m.get("claude", [100, 100])
    g = m.get("gemini", [100, 100])
    a = m.get("argon", 100)
    reset = "2026-11-26T12:00:00Z"
    return "\n".join([
        f"Gemini Models\tWeekly Limit Remaining\t{g[0]}%\t{reset}",
        f"Gemini Models\tFive Hour Limit Remaining\t{g[1]}%\t{reset}",
        f"Claude and GPT models\tWeekly Limit Remaining\t{c[0]}%\t{reset}",
        f"Claude and GPT models\tFive Hour Limit Remaining\t{c[1]}%\t{reset}",
        f"Gemini 4 Argon\tGemini 4 Argon Weekly Limit\t{a}%\t{reset}",
    ])


def parse(argv):
    opts, prompt = {}, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("-p="):
            prompt = a[3:]
        elif a in ("-p", "--print"):
            i += 1
            prompt = argv[i] if i < len(argv) else ""
        elif a.startswith("--") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            i += 1
        i += 1
    return opts, prompt


def find_hooks(cwd):
    d = os.path.realpath(cwd)
    while True:
        p = os.path.join(d, ".agents", "hooks.json")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def run_hooks(hooks_path, event, payload, matcher_tool=None):
    """Run every handler for `event`; return the last stdout parsed as JSON (or {})."""
    with open(hooks_path) as f:
        spec = json.load(f)
    hook_cwd = os.path.dirname(hooks_path)
    out = {}
    for named in spec.values():
        if named.get("enabled") is False:
            continue
        for entry in named.get(event, []):
            handlers = entry.get("hooks", [entry]) if "matcher" in entry else [entry]
            for h in handlers:
                r = subprocess.run(h["command"], shell=True, cwd=hook_cwd, capture_output=True,
                                   text=True, input=json.dumps({**payload, "hookEventName": event}),
                                   timeout=30)
                try:
                    out = json.loads(r.stdout or "{}")
                except ValueError:
                    out = {}
    return out


def main():
    argv = sys.argv[1:]
    mode = os.environ.get("FAKE_AGY_MODE", "ok")
    if argv[:1] == ["--version"]:
        print(os.environ.get("FAKE_AGY_VERSION", "1.5.12"))
        return 0
    opts, prompt = parse(argv)
    if prompt == "/usage":
        if mode == "meters_fail":
            print("something went wrong")
            return 1
        print(meters())
        return 0
    cwd = os.getcwd()
    model = opts.get("model", "")
    files = sorted(os.path.relpath(os.path.join(dp, f), cwd)
                   for dp, _, fs in os.walk(cwd) for f in fs)
    log = {"argv": argv, "cwd": cwd, "files": files, "decision": None}
    if mode == "timeout":
        time.sleep(60)
        return 0
    conv = str(uuid.uuid4())
    hooks = find_hooks(cwd)
    if hooks and mode != "no_hook":
        base = {"conversationId": conv, "cwd": cwd, "workspacePaths": [cwd],
                "modelName": model if mode != "wrong_model" else model + "-other",
                "transcriptPath": "/dev/null", "artifactDirectoryPath": "/dev/null",
                "lastUserInput": (prompt or "")[:200]}
        start = dict(base)
        if mode == "workspace":
            start["workspacePaths"] = ["/somewhere/else"]
        run_hooks(hooks, "SessionStart", start)
        tool = os.environ.get("FAKE_AGY_TOOL")
        if tool:
            res = run_hooks(hooks, "PreToolUse", {**base, "toolCall": json.loads(tool), "stepIdx": 1})
            log["decision"] = res.get("decision")
        if mode == "helper":
            helper = {**base, "conversationId": str(uuid.uuid4())}
            run_hooks(hooks, "SessionStart", helper)
            run_hooks(hooks, "Stop", helper)
        run_hooks(hooks, "Stop", base)
    if os.environ.get("FAKE_AGY_LOG"):
        with open(os.environ["FAKE_AGY_LOG"], "a") as f:
            f.write(json.dumps(log) + "\n")
    quota = [m for m in (os.environ.get("FAKE_AGY_QUOTA_MODELS") or "").split(",") if m]
    usage = {"input_tokens": 1000, "output_tokens": 50, "thinking_tokens": 10,
             "cache_read_tokens": 400, "total_tokens": 1060}
    if mode == "bad_json":
        print("not json at all")
        return 0
    if model in quota:
        res = {"conversation_id": conv, "status": "ERROR", "response": "",
               "error": "RESOURCE_EXHAUSTED: you have reached the quota for Claude and GPT models"}
    elif mode == "status_error":
        res = {"conversation_id": conv, "status": "ERROR", "response": "", "error": "internal error"}
    else:
        answer = "" if mode == "empty" else os.environ.get("FAKE_AGY_ANSWER", DEFAULT_ANSWER)
        res = {"conversation_id": conv, "status": "SUCCESS", "response": answer,
               "duration_seconds": 0.1, "num_turns": 1, "usage": usage}
    print(json.dumps(res))
    return 1 if res["status"] == "ERROR" else 0


if __name__ == "__main__":
    sys.exit(main())
