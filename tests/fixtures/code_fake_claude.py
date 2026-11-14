#!/usr/bin/env python3
"""A stub for `claude -p` used by tests/test_code_bench.py. No network, no model.

It plays a test writer or a coder that edits files in its working directory, as a script says.

The kind of a call is read from the prompt's fixed instruction: "T" (write the tests), "A" (no tests),
"B" (locked tests) or "C" (own tests).

Env:
  CODE_FAKE_SCRIPT   a JSON file {"T": [action, ...], "A": [...], "B": [...], "C": [...], "default": [...]}.
                     Call n of a kind takes item n of that kind's list; the last item repeats; a kind with
                     no list uses "default"; no list at all = an action that changes nothing.
  CODE_FAKE_STATE    a JSON counter file (flock-guarded); needed for scripts of more than one item
  CODE_FAKE_LOG      append one JSON line per call: argv, cwd, files (every file under cwd), prompt, model,
                     effort, tools, system_prompt, kind, autoupdater (DISABLE_AUTOUPDATER in the child's
                     environment), advisor_switch
  CODE_FAKE_VERSION  what `--version` prints (default "2.1.325 (Claude Code)")

An action (every key optional):
  "write":  {"rel/path": "text"}   files written (folders made) relative to the working directory
  "delete": ["rel/path"]           files removed
  "symlink": {"rel/link": "target"}
  "mode":   "ok" (default) | "api_error" (is_error, api_error_status 529, no output tokens, exit 1)
            | "budget_cap" (is_error, subtype error_max_budget_usd, exit 1) | "timeout" (writes, then
            sleeps 60 s) | "refusal" (stop_reason refusal) | "wrong_model" | "bad_json"
  "cost":   a number (default 0.25), or null for a result without total_cost_usd (cost unknown)
  "denials": a number of permission denials to report
Paths that leave the working directory are refused, as the real permission mode refuses them.
"""
import fcntl
import json
import os
import sys
import time

import fake_claude as base

KINDS = (("Write the tests for this change", "T"), ("Make this change in the source files", "A"),
         ("The test files listed below", "B"), ("First write tests for this change", "C"))


def kind_of(prompt):
    for marker, kind in KINDS:
        if marker in prompt:
            return kind
    return "default"


def bump(name):
    path = os.environ.get("CODE_FAKE_STATE")
    if not path:
        return 0
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        state = json.loads(f.read() or "{}")
        n = state.get(name, 0)
        state[name] = n + 1
        f.seek(0)
        f.truncate()
        f.write(json.dumps(state))
    return n


def action_for(kind):
    path = os.environ.get("CODE_FAKE_SCRIPT")
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        script = json.load(f)
    items = script.get(kind) or script.get("default") or [{}]
    return items[min(bump(kind if script.get(kind) else "default"), len(items) - 1)]


def inside(rel):
    full = os.path.realpath(os.path.join(os.getcwd(), rel))
    here = os.path.realpath(os.getcwd())
    return full == here or full.startswith(here + os.sep)


def apply(action):
    for rel, text in (action.get("write") or {}).items():
        if not inside(rel):
            continue
        os.makedirs(os.path.dirname(os.path.join(".", rel)) or ".", exist_ok=True)
        with open(rel, "w", encoding="utf-8") as f:
            f.write(text)
    for rel in action.get("delete") or []:
        if inside(rel) and os.path.isfile(rel):
            os.unlink(rel)
    for rel, target in (action.get("symlink") or {}).items():
        if inside(rel):
            os.symlink(target, rel)


def all_files():
    out = []
    for dirpath, _, files in os.walk("."):
        for fn in files:
            out.append(os.path.relpath(os.path.join(dirpath, fn), "."))
    return sorted(out)


def main():
    if "--version" in sys.argv[1:]:
        print(os.environ.get("CODE_FAKE_VERSION", "2.1.325 (Claude Code)"))
        return 0
    args = base.parse_args()
    prompt = sys.stdin.read()
    kind = kind_of(prompt)
    log = os.environ.get("CODE_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "files": all_files(), "prompt": prompt,
                                "model": args.model, "effort": args.effort, "tools": args.tools,
                                "system_prompt": args.system_prompt, "kind": kind,
                                "autoupdater": os.environ.get("DISABLE_AUTOUPDATER"),
                                "advisor_switch": os.environ.get("CLAUDE_CODE_DISABLE_ADVISOR_TOOL")}) + "\n")
    action = action_for(kind)
    mode = action.get("mode", "ok")
    apply(action)
    if mode == "timeout":
        time.sleep(60)
    if mode == "bad_json":
        print("this is not json")
        return 0
    cost = action.get("cost", 0.25)
    model = args.model or "claude-unknown"
    if mode == "wrong_model":
        model = model + "-other"
    out = base.result_json(model, "DONE", cost if cost is not None else 0.0, 50,
                           is_error=mode in ("api_error", "budget_cap"))
    if cost is None:
        del out["total_cost_usd"]
    out["stop_reason"] = "refusal" if mode == "refusal" else "end_turn"
    out["safety_stops"] = 0
    out["api_error_status"] = 529 if mode == "api_error" else None
    out["permission_denials"] = [{"tool_name": "Write"}] * int(action.get("denials", 0))
    if mode == "api_error":
        out["usage"]["output_tokens"] = 0
    if mode == "budget_cap":
        out["subtype"] = "error_max_budget_usd"
    print(json.dumps(out))
    return 1 if mode in ("api_error", "budget_cap") else 0


if __name__ == "__main__":
    sys.exit(main())
