#!/usr/bin/env python3
"""A stub for `claude -p` used by tests/test_ux_blind.py. No network, no model.

It reuses tests/fixtures/fake_claude.py for the JSON shape and answers by prompt kind:

  designer prompt   "You are the UI/UX designer ..."   -> a design text naming the model that wrote it
  builder prompt    "Build a prototype ..."            -> an HTML page (UX_FAKE_PAGE: a file to serve instead)
  checklist prompt  "You are checking one prototype page ..." -> {"K1": true, ..., "K8": true}

Env (all optional):
  UX_FAKE_LOG          append one JSON line per call: argv, cwd, files, prompt, model, system_prompt
  UX_FAKE_STATE        a JSON counter file (flock-guarded); needed by the *_FIRST switches
  UX_FAKE_COST         cost per call (default 0.01)
  UX_FAKE_WRONG_MODEL  a model id: its first UX_FAKE_WRONG_FIRST calls answer as another model
  UX_FAKE_REFUSE_MODEL a model id: its first UX_FAKE_REFUSE_FIRST calls end with stop_reason "refusal"
  UX_FAKE_SAFETY_MODEL a model id: its first UX_FAKE_SAFETY_FIRST calls report safety_stops 1 (stop_reason stays "end_turn")
  UX_FAKE_ERROR_MODEL  a model id: its first UX_FAKE_ERROR_FIRST calls come back with is_error true (stop_reason "end_turn",
                       safety_stops 0), as an API error or a rate limit would
  UX_FAKE_API_ERROR_MODEL  a model id: its first UX_FAKE_API_ERROR_FIRST calls fail like a rate limit: is_error true,
                       api_error_status UX_FAKE_API_ERROR_STATUS (default 429), no output tokens, exit status 1
  UX_FAKE_FAIL_MODEL   a model id: its first UX_FAKE_FAIL_FIRST calls fail with is_error true, no output tokens and
                       NO api_error_status, exit status 1
  UX_FAKE_REFUSE_ERROR set to 1: a refusal also comes back with is_error true, no output tokens and exit status 1
  UX_FAKE_NO_BLOCK     "design" / "build" / "checklist": that kind answers without the marker block
  UX_FAKE_BAD_FIRST    the first N checklist calls (all models) answer with text that is not the JSON
  UX_FAKE_CHECK        JSON {model id: {"K1": false, ...}} overrides; every other item stays true
"""
import fcntl
import json
import os
import sys

import fake_claude as base

PAGE = ('<!DOCTYPE html>\n<html lang="tr"><head><meta charset="utf-8">'
        '<title>Fable F design pass</title><meta name="generator" content="Fable 5.2">'
        '<!-- built from the F arm --></head><body><svg xmlns="http://www.w3.org/2000/svg" width="8" '
        'height="8"></svg><p data-run="@@RUN@@">Oyna</p></body></html>')


def bump(name):
    """Count calls under `name` in UX_FAKE_STATE; returns how many came before this one."""
    path = os.environ.get("UX_FAKE_STATE")
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


def kind_of(prompt):
    if prompt.startswith("Build a prototype"):
        return "build"
    if prompt.startswith("You are the UI/UX designer"):
        return "design"
    return "checklist"


def main():
    args = base.parse_args()
    prompt = sys.stdin.read()
    log = os.environ.get("UX_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "files": sorted(os.listdir(".")),
                                "prompt": prompt, "model": args.model,
                                "system_prompt": args.system_prompt}) + "\n")
    model, kind = args.model, kind_of(prompt)
    run = bump("calls")
    cost = float(os.environ.get("UX_FAKE_COST", "0.01"))
    if kind == "design":
        text = f"Screens: DESIGN-BY-{model}. Flow: x."
    elif kind == "build":
        page = PAGE
        if os.environ.get("UX_FAKE_PAGE"):
            page = open(os.environ["UX_FAKE_PAGE"], encoding="utf-8").read()
        text = page.replace("@@RUN@@", str(run))
    else:
        items = {f"K{i}": True for i in range(1, 9)}
        items.update(json.loads(os.environ.get("UX_FAKE_CHECK", "{}")).get(model, {}))
        text = json.dumps(items)
        if bump("checks") < int(os.environ.get("UX_FAKE_BAD_FIRST", "0")):
            text = "I would say most of them hold."
    if os.environ.get("UX_FAKE_NO_BLOCK") != kind:
        text = f"Done.\n===ANSWER===\n{text}\n===END==="
    stop_reason = "end_turn"
    if model == os.environ.get("UX_FAKE_WRONG_MODEL") and \
            bump("wrong") < int(os.environ.get("UX_FAKE_WRONG_FIRST", "0")):
        model = model + "-next"
    if model == os.environ.get("UX_FAKE_REFUSE_MODEL") and \
            bump("refuse") < int(os.environ.get("UX_FAKE_REFUSE_FIRST", "0")):
        stop_reason = "refusal"
    is_error = model == os.environ.get("UX_FAKE_ERROR_MODEL") and \
        bump("error") < int(os.environ.get("UX_FAKE_ERROR_FIRST", "0"))
    safety = 0
    if model == os.environ.get("UX_FAKE_SAFETY_MODEL") and \
            bump("safety") < int(os.environ.get("UX_FAKE_SAFETY_FIRST", "0")):
        safety = 1
    api_status, failed = None, False
    if model == os.environ.get("UX_FAKE_API_ERROR_MODEL") and \
            bump("apierr") < int(os.environ.get("UX_FAKE_API_ERROR_FIRST", "0")):
        api_status, failed = int(os.environ.get("UX_FAKE_API_ERROR_STATUS", "429")), True
    if model == os.environ.get("UX_FAKE_FAIL_MODEL") and \
            bump("fail") < int(os.environ.get("UX_FAKE_FAIL_FIRST", "0")):
        failed = True
    if stop_reason == "refusal" and os.environ.get("UX_FAKE_REFUSE_ERROR") == "1":
        failed = True
    out = base.result_json(model, text, cost, 100, is_error=is_error or failed)
    out["stop_reason"] = stop_reason
    out["safety_stops"] = safety
    out["api_error_status"] = api_status
    if failed:
        out["usage"]["output_tokens"] = 0
        out["usage"]["output_tokens_details"]["thinking_tokens"] = 0
    print(json.dumps(out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
