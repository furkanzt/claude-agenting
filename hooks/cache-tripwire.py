#!/usr/bin/env python3
"""UserPromptSubmit hook — mid-session model/effort switch cost tripwire.

A model or effort change mid-session invalidates the prompt cache prefix:
the next assistant turn re-writes the whole carried context instead of
reading it from cache. Measured case (this project, 2026-08-10): sonnet/high
-> opus/max mid-session rewrote 66,975 tokens on the very next turn.

This hook compares the session's FIRST main-thread assistant model+effort to
its LATEST, and if they differ, reports the token cost paid at the transition
point. It fires once per distinct switch (tracked in a small per-session
state file next to this script) rather than on every subsequent prompt.

Cost estimates are approximate list-price input-token cost of the NEW model,
at a flat 1.25x cache-write multiplier (5-min default TTL) -- a nudge, not a
bill. Subagent ("sidechain") messages are intentionally excluded: agents are
expected to use a different tier than the main session by design.

Never blocks: any parse failure or missing data exits silently (exit 0).
"""
import json
import os
import sys

MAX_TAIL_BYTES = 2_000_000
MAX_SCAN_LINES = 200_000
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache-tripwire-state.json")

# Approximate list-price input $/MTok, matched by substring against message.model.
PRICES_PER_MTOK = {
    "haiku": 1.00,
    "sonnet": 3.00,
    "opus": 5.00,
    "fable": 10.00,
}
CACHE_WRITE_MULTIPLIER = 1.25  # 5-min ephemeral write; 1h write is 2x but this is a nudge, not a bill.


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def find_first_main_assistant(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            return d
    return None


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
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            return d
        if seek_to == 0 or tail_bytes >= cap:
            return None
        tail_bytes *= 4


def find_entry_to_tier(path, target_model, target_effort):
    """First main-assistant line matching (target_model, target_effort) -- the
    point the session most recently entered its current tier. Bounded scan:
    a very long transcript falls back to no-cost-figure rather than reading
    the whole file every prompt."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= MAX_SCAN_LINES:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            model = d.get("message", {}).get("model")
            effort = d.get("effort")
            if model == target_model and effort == target_effort:
                return d
    return None


def price_for_model(model_id: str):
    model_id = (model_id or "").lower()
    for key, price in PRICES_PER_MTOK.items():
        if key in model_id:
            return price
    return None


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def short_model(model_id: str) -> str:
    return (model_id or "?").replace("claude-", "")


def build_tripwire_message(prev_model, prev_effort, last_model, last_effort, transition):
    prev_tag = f"{short_model(prev_model)}/{prev_effort or '?'}"
    last_tag = f"{short_model(last_model)}/{last_effort or '?'}"
    if not transition:
        return f"[cache tripwire] model changed {prev_tag} -> {last_tag} mid-session."
    u = transition.get("message", {}).get("usage", {})
    write_tokens = u.get("cache_creation_input_tokens")
    if not write_tokens:
        return f"[cache tripwire] model changed {prev_tag} -> {last_tag} mid-session."
    price = price_for_model(last_model)
    cost_str = ""
    if price:
        cost = write_tokens / 1_000_000 * price * CACHE_WRITE_MULTIPLIER
        cost_str = f", ~${cost:.2f} of window"
    write_k = write_tokens / 1000
    return f"[cache tripwire] model changed {prev_tag} -> {last_tag}: re-wrote {write_k:.0f}k tokens{cost_str}."


def main():
    data = read_hook_input()
    transcript_path = data.get("transcript_path")
    session_id = data.get("session_id") or "unknown"

    if not transcript_path or not os.path.isfile(transcript_path):
        sys.exit(0)

    first = find_first_main_assistant(transcript_path)
    last = find_last_main_assistant(transcript_path)
    if not first or not last:
        sys.exit(0)

    first_model = first.get("message", {}).get("model")
    first_effort = first.get("effort")
    last_model = last.get("message", {}).get("model")
    last_effort = last.get("effort")

    state = load_state()
    baseline_key = state.get(session_id)
    if baseline_key is None:
        # First time this session is seen: seed the baseline at the session's
        # starting tier, nothing to report yet even if it already drifted
        # before this hook existed for this session.
        state[session_id] = f"{first_model}|{first_effort}"
        save_state(state)
        prev_model, prev_effort = first_model, first_effort
    else:
        prev_model, prev_effort = baseline_key.split("|", 1)
        prev_effort = None if prev_effort == "None" else prev_effort

    if prev_model == last_model and prev_effort == last_effort:
        sys.exit(0)  # no new switch since we last reported

    transition = find_entry_to_tier(transcript_path, last_model, last_effort)
    message = build_tripwire_message(prev_model, prev_effort, last_model, last_effort, transition)

    state[session_id] = f"{last_model}|{last_effort}"
    save_state(state)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": message,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
