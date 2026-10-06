#!/usr/bin/env python3
"""A stub for `claude -p` used by the evalkit tests. No network, no model.

Reads the prompt from stdin (or the positional argument), honours --model and
prints one JSON object shaped like the real `--output-format json` result, with
modelUsage keyed by the model id it was asked for. FAKE_CLAUDE_MODE selects:

  ok           valid run; result is FAKE_CLAUDE_ANSWER (default: an answer block)
  wrong_model  modelUsage names a different model than requested
  alias_drift  modelUsage names a drifted id (<requested>-next), as a moved alias would
  error        is_error true, exit status 1
  timeout      sleeps 60 s (the harness must kill it)
  no_block     answers without the ===ANSWER=== block
  bad_json     prints text that is not JSON

Other env: FAKE_CLAUDE_SEQ (a JSON list of answer texts) with FAKE_CLAUDE_STATE (a counter
file): call n answers with SEQ[min(n, len-1)], so one test can script "garbage, then good".
FAKE_CLAUDE_COST (default 0.01), FAKE_CLAUDE_THINKING (default 100),
FAKE_CLAUDE_LOG (append one JSON line per call: argv, cwd, files, prompt).

`--version` prints FAKE_CLAUDE_VERSION (default "9.9.9 (Fake)") and exits 0 before anything
else happens: no stdin read, no FAKE_CLAUDE_LOG line. FAKE_CLAUDE_VERSION_LOG, if set, gets
one line per such call so a test can count them.
"""

import argparse
import fcntl
import json
import os
import sys
import time

DEFAULT_ANSWER = "Working it out.\n===ANSWER===\n42\n===END==="


def parse_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-p", "--print", action="store_true")
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--tools", nargs="*")
    p.add_argument("--system-prompt")
    p.add_argument("--max-budget-usd")
    p.add_argument("--output-format")
    p.add_argument("prompt", nargs="?")
    args, _ = p.parse_known_args()
    return args


def log_call(args, prompt):
    path = os.environ.get("FAKE_CLAUDE_LOG")
    if not path:
        return
    entry = {"argv": sys.argv[1:], "cwd": os.getcwd(), "files": sorted(os.listdir(".")),
             "prompt": prompt, "model": args.model, "effort": args.effort, "tools": args.tools,
             "system_prompt": args.system_prompt}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def result_json(model, text, cost, thinking, is_error=False):
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 550, "cache_read_input_tokens": 0,
             "output_tokens": thinking + 3, "output_tokens_details": {"thinking_tokens": thinking}}
    return {"type": "result", "subtype": "success", "is_error": is_error, "stop_reason": "end_turn",
            "result": text, "total_cost_usd": cost, "duration_ms": 1234, "num_turns": 1,
            "usage": usage, "modelUsage": {model: {
                "inputTokens": 2, "outputTokens": thinking + 3, "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 550, "costUSD": cost, "thinkingTokens": thinking}}}


def next_in_sequence():
    """The next answer of FAKE_CLAUDE_SEQ, counting calls in FAKE_CLAUDE_STATE (flock-guarded)."""
    seq, state = os.environ.get("FAKE_CLAUDE_SEQ"), os.environ.get("FAKE_CLAUDE_STATE")
    if not seq or not state:
        return None
    answers = json.loads(seq)
    with open(state, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        n = int(f.read().strip() or 0)
        f.seek(0)
        f.truncate()
        f.write(str(n + 1))
    return answers[min(n, len(answers) - 1)]


def answer_version():
    path = os.environ.get("FAKE_CLAUDE_VERSION_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("version\n")
    print(os.environ.get("FAKE_CLAUDE_VERSION", "9.9.9 (Fake)"))
    return 0


def main():
    if "--version" in sys.argv[1:]:
        return answer_version()
    args = parse_args()
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    log_call(args, prompt)
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    cost = float(os.environ.get("FAKE_CLAUDE_COST", "0.01"))
    thinking = int(os.environ.get("FAKE_CLAUDE_THINKING", "100"))
    text = os.environ.get("FAKE_CLAUDE_ANSWER", DEFAULT_ANSWER)
    scripted = next_in_sequence()
    if scripted is not None:
        text = scripted
    model = args.model or "claude-unknown"
    if mode == "timeout":
        time.sleep(60)
    if mode == "bad_json":
        print("this is not json")
        return 0
    if mode == "wrong_model":
        model = "claude-haiku-4-5-20251001" if model != "claude-haiku-4-5-20251001" else "claude-other"
    elif mode == "alias_drift":
        model = model + "-next"
    elif mode == "no_block":
        text = "I think the answer is 42."
    elif mode == "error":
        print(json.dumps(result_json(model, "API Error: overloaded", 0.0, 0, is_error=True)))
        return 1
    print(json.dumps(result_json(model, text, cost, thinking)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
