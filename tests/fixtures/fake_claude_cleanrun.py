#!/usr/bin/env python3
"""A stub for `claude -p` used by the cleanrun tests. No network, no model.

Reads the prompt from stdin and the system prompt from --system-prompt-file, honours
--model, and prints one JSON object shaped like the real `--output-format json` result
(field names and error shapes checked against claude 2.1.294). The mode comes from a
`@@mode:NAME@@` directive in the prompt, else FAKE_MODE, else ok; `@@seq:A,B,...@@`
plays the listed modes on successive calls for the same prompt.

  ok              success; structured_output {"answer": "ok", "files": [names in the working dir]}
  invalid_output  success; structured_output {"answer": "bad"}
  no_structured   success without structured_output
  wrong_model     modelUsage names another model
  error           is_error true, subtype error_during_execution, errors list, exit 1
  error_exit0     is_error true but exit 0 with a structured_output (defensive case)
  budget          the real --max-budget-usd stop: exit 1, is_error, subtype
                  error_max_budget_usd, errors list, no result, no structured_output,
                  top-level usage all zero, real counts only in modelUsage
  bad_json        prints text that is not JSON
  no_cost         total_cost_usd missing
  stderr_fail     prints only to stderr ("auth failed: token expired"), exit 1
  hang            starts a grandchild (sleep 300) in its own process group, writes its
                  pid to FAKE_PIDS_DIR, then sleeps 300 s itself
  orphan          answers ok, but first starts `sleep 300` in a NEW session that keeps
                  the stdout file open; writes its pid to FAKE_PIDS_DIR
  slow            sleeps FAKE_SLOW_S (default 2) then answers ok

Env: FAKE_COST (default 0.05), FAKE_LOG (one JSON line per call), FAKE_STATE_DIR (seq counters).
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time


def arg(name):
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else None


def log(entry):
    path = os.environ.get("FAKE_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(entry) + "\n")


def seq_mode(prompt, modes):
    state = os.environ.get("FAKE_STATE_DIR", ".")
    path = os.path.join(state, "seq_" + hashlib.sha1(prompt.encode()).hexdigest()[:12])
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        n = int(f.read().strip() or 0)
        f.seek(0)
        f.truncate()
        f.write(str(n + 1))
    return modes[min(n, len(modes) - 1)]


def record_pid(pid):
    d = os.environ.get("FAKE_PIDS_DIR")
    if d:
        with open(os.path.join(d, f"{pid}.pid"), "w") as f:
            f.write(str(pid))


def main():
    prompt = sys.stdin.read()
    model = arg("--model") or "claude-unknown"
    spf = arg("--system-prompt-file")
    system = open(spf, "rb").read().decode("utf-8") if spf else arg("--system-prompt")
    m = re.search(r"@@mode:(\w+)@@", prompt)
    s = re.search(r"@@seq:([\w,]+)@@", prompt)
    mode = seq_mode(prompt, s.group(1).split(",")) if s else (m.group(1) if m else os.environ.get("FAKE_MODE", "ok"))
    log({"argv": sys.argv[1:], "files": sorted(os.listdir(".")), "prompt": prompt, "system": system,
         "mode": mode, "pid": os.getpid()})
    cost = float(os.environ.get("FAKE_COST", "0.05"))
    usage_mu = {"inputTokens": 3, "outputTokens": 40, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 500,
                "costUSD": cost, "contextWindow": 200000}
    if mode == "hang":
        child = subprocess.Popen(["sleep", "300"])
        record_pid(child.pid)
        time.sleep(300)
        return 0
    if mode == "orphan":
        child = subprocess.Popen(["sleep", "300"], start_new_session=True)   # inherits stdout, leaves the group
        record_pid(child.pid)
        mode = "ok"
    if mode == "slow":
        time.sleep(float(os.environ.get("FAKE_SLOW_S", "2")))
        mode = "ok"
    if mode == "bad_json":
        print("this is not json")
        return 0
    if mode == "stderr_fail":
        sys.stderr.write("auth failed: token expired\n")
        return 1
    out = {"type": "result", "subtype": "success", "terminal_reason": "completed", "is_error": False,
           "num_turns": 2, "total_cost_usd": cost,
           "usage": {"input_tokens": 3, "output_tokens": 40, "cache_creation_input_tokens": 500, "cache_read_input_tokens": 0},
           "modelUsage": {model: dict(usage_mu)}}
    if mode == "ok":
        out["structured_output"] = {"answer": "ok", "files": sorted(os.listdir("."))}
    elif mode == "invalid_output":
        out["structured_output"] = {"answer": "bad"}
    elif mode == "wrong_model":
        out["modelUsage"] = {"claude-haiku-4-5-20251001": dict(usage_mu)}
        out["structured_output"] = {"answer": "ok"}
    elif mode == "error":
        out.update(is_error=True, subtype="error_during_execution", errors=["API Error: overloaded"])
        print(json.dumps(out))
        return 1
    elif mode == "error_exit0":
        out.update(is_error=True, subtype="error_during_execution", result="something went wrong")
        out["structured_output"] = {"answer": "ok"}
    elif mode == "budget":
        out.update(is_error=True, subtype="error_max_budget_usd", terminal_reason="budget_exhausted",
                   errors=["Reached maximum budget ($0.0005)"], num_turns=1)
        out["usage"] = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        out["modelUsage"] = {model: {**usage_mu, "outputTokens": 52, "cacheCreationInputTokens": 1131}}
        print(json.dumps(out))
        return 1
    elif mode == "no_cost":
        del out["total_cost_usd"]
        out["structured_output"] = {"answer": "ok"}
    if "structured_output" in out:
        out["result"] = json.dumps(out["structured_output"])
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
