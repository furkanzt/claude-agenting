Feature: The tripwire nudges once per mid-session model or effort switch with the cache re-write cost, and never blocks

  The tripwire (hooks/cache-tripwire.py) runs on UserPromptSubmit. It compares the session's
  main-thread tier (model plus effort) with the last tier it reported, and prints a one-line
  additionalContext nudge when they differ. Prices are list input $/MTok times a flat 1.25
  cache-write multiplier. Every path exits 0.

  # NOTE on testing: the state file is hooks/.cache-tripwire-state.json (STATE_PATH, next to the
  # script) and there is no environment override. A test must therefore run a copy of the hook in a
  # temp directory, or import it with STATE_PATH patched, or it writes into the repo and the plugin dir.

  # ---- When it stays silent ---------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A hook payload with no transcript path exits 0 and prints nothing
    Given a UserPromptSubmit payload "{}" with no transcript_path
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty
    And no state file is written

  @gap @wip
  # Backed by: @gap
  Scenario: A transcript path that does not exist exits 0 and prints nothing
    Given a payload whose transcript_path is "/nonexistent/x.jsonl"
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: Non-JSON stdin exits 0 and prints nothing
    Given stdin is the text "not json"
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: Empty stdin exits 0 and prints nothing
    Given stdin is empty
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: Valid JSON that is not an object exits 0 and prints nothing
    Given stdin is the text "[]"
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty

  @gap @wip
  # Backed by: @gap
  Scenario: A transcript holding only sidechain assistant messages exits 0 and prints nothing
    Given a transcript whose only assistant line is marked isSidechain true
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty
    And no state file is written

  @gap @wip
  # Backed by: @gap
  Scenario: First sight of a session on a single tier seeds the baseline and stays silent
    Given a session "s1" never seen before whose main-thread assistant lines are all claude-sonnet-5-5 at effort high
    When the tripwire runs
    Then stdout is empty
    And the state file maps "s1" to "claude-sonnet-5-5|high"

  @gap @wip
  # Backed by: @gap
  Scenario: A session whose transcript carries no effort field stays silent on the same model
    Given a session "s1" whose main-thread assistant lines are claude-sonnet-5-5 with no effort field
    When the tripwire runs twice
    Then stdout is empty both times
    And the state file maps "s1" to "claude-sonnet-5-5|None"

  @gap @wip
  # Backed by: @gap
  Scenario: Sidechain assistant messages on another tier never trigger a nudge
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the latest sidechain assistant line is claude-opus-5-5 at effort max
    And the latest main-thread assistant line is claude-sonnet-5-5 at effort high
    When the tripwire runs
    Then stdout is empty

  # ---- When it fires and what it prints --------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A model and effort switch prints the re-write size and cost as additionalContext
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first claude-opus-5-5 at effort max main-thread line has cache_creation_input_tokens 66975
    And the latest main-thread assistant line is claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And the output JSON hookEventName is "UserPromptSubmit"
    And the output JSON additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max: re-wrote 67k tokens, ~$0.33 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: An effort-only switch on the same model still fires
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first claude-sonnet-5-5 at effort low main-thread line has cache_creation_input_tokens 80000
    And the latest main-thread assistant line is claude-sonnet-5-5 at effort low
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> sonnet-5-5/low: re-wrote 80k tokens, ~$0.20 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A switch is priced at the new model, not the old one
    Given session "s1" has baseline "claude-opus-5-5|max"
    And the first claude-sonnet-5-5 at effort high main-thread line has cache_creation_input_tokens 80000
    And the latest main-thread assistant line is claude-sonnet-5-5 at effort high
    When the tripwire runs
    Then the additionalContext ends with "re-wrote 80k tokens, ~$0.20 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A missing effort is shown as a question mark
    Given session "s1" has baseline "claude-sonnet-5-5|None"
    And the first claude-opus-5-5 main-thread line has no effort field and cache_creation_input_tokens 40000
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/? -> opus-5-5/?: re-wrote 40k tokens, ~$0.20 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A switch whose transition line wrote no cache tokens, absent or 0, prints the short message
    # Absent and 0 take the same "if not write_tokens" branch; a missing transition line lands here too.
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the claude-opus-5-5 at effort max transition line has no cache_creation_input_tokens, or has cache_creation_input_tokens 0
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max mid-session."

  @gap @wip
  # Backed by: @gap
  Scenario: A switch to a model with no price prints the token count without a cost
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the latest main-thread assistant line is claude-mystery-1 at effort max with cache_creation_input_tokens 67000
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> mystery-1/max: re-wrote 67k tokens."

  @gap @wip
  # Backed by: @gap
  Scenario: The cost applies the 1.25 cache-write multiplier to the input price
    Given session "s1" has baseline "claude-opus-5-5|max"
    And the claude-haiku-5-5 at effort low transition line has cache_creation_input_tokens 400000
    When the tripwire runs
    Then the additionalContext ends with "re-wrote 400k tokens, ~$0.05 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A malformed transcript line is skipped and the switch is still reported
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And a transcript line "garbage{" sits before the claude-opus-5-5 at effort max line
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max: re-wrote 80k tokens, ~$0.40 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: The latest main-thread line is found behind a long run of trailing sidechain lines
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the claude-opus-5-5 at effort max main-thread line, with no cache_creation_input_tokens, is followed by sidechain lines totalling more than 65536 bytes
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max mid-session."

  @gap @wip
  # Backed by: @gap
  Scenario: A transition line at the 200001st transcript line falls back to the short message
    # Blank lines count. The scan reads 0-based indexes 0 to 199999, so a transition at index 199999
    # (the 200000th line) still gets the cost figure and one at index 200000 does not.
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first claude-opus-5-5 at effort max main-thread line, with cache_creation_input_tokens 80000, is at 0-based line index 200000
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max mid-session."

  @gap @wip
  # Backed by: @gap
  Scenario: A transition line at the 200000th transcript line still gets the cost figure
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first claude-opus-5-5 at effort max main-thread line, with cache_creation_input_tokens 80000, is at 0-based line index 199999
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max: re-wrote 80k tokens, ~$0.40 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A sub-1k re-write rounds to 0k tokens and $0.00
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first claude-sonnet-5-5 at effort low main-thread line has cache_creation_input_tokens 500
    And the latest main-thread assistant line is claude-sonnet-5-5 at effort low
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> sonnet-5-5/low: re-wrote 0k tokens, ~$0.00 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: A model id with capital letters is priced but printed with its capitals
    # price_for_model lowercases the id; short_model strips only a lowercase "claude-" prefix.
    Given session "s1" has baseline "claude-sonnet-5-5|high"
    And the first "Claude-Opus-5-5" at effort max main-thread line has cache_creation_input_tokens 80000
    And the latest main-thread assistant line is "Claude-Opus-5-5" at effort max
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed sonnet-5-5/high -> Claude-Opus-5-5/max: re-wrote 80k tokens, ~$0.40 of window."

  # ---- Once per switch, per session ------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A first-seen session that already drifted fires on its first prompt
    Given session "s1" is not in the state file
    And its first main-thread assistant line is claude-sonnet-5-5 at effort high
    And its latest main-thread assistant line is claude-opus-5-5 at effort max
    When the tripwire runs
    Then the additionalContext starts with "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max"
    And the state file maps "s1" to "claude-opus-5-5|max"

  @gap @wip
  # Backed by: @gap
  Scenario: A later prompt on the tier already reported prints nothing and leaves the state alone
    # The hook sees only the stored "model|effort" string, so it cannot tell a nudged baseline
    # from one seeded on first sight; both reach this same branch.
    Given session "s1" has baseline "claude-opus-5-5|max" in the state file
    And the latest main-thread assistant line is claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty
    And the state file maps "s1" to "claude-opus-5-5|max"

  @gap @wip
  # Backed by: @gap
  Scenario: A second distinct switch is reported from the previously reported tier
    Given the tripwire already reported the switch to claude-opus-5-5 at effort max for session "s1"
    And the latest main-thread assistant line is now claude-sonnet-5-5 at effort high
    When the tripwire runs
    Then the additionalContext starts with "[cache tripwire] model changed opus-5-5/max -> sonnet-5-5/high"
    And the state file maps "s1" to "claude-sonnet-5-5|high"

  @gap @wip
  # Backed by: @gap
  Scenario: Re-entering an earlier tier reports the earliest line seen on that tier, not the real re-write
    # NOTE: probable bug. find_entry_to_tier returns the FIRST line on the tier, so any later re-entry
    # to a tier seen earlier (a switch away and back, or the same tier again) picks the session's
    # earliest such line instead of the line that actually re-wrote the cache. Pinned as today's behaviour.
    Given the tripwire already reported the switch to claude-opus-5-5 at effort max for session "s1"
    And the session's very first line was claude-sonnet-5-5 at effort high with cache_creation_input_tokens 1000
    And the latest line is claude-sonnet-5-5 at effort high with cache_creation_input_tokens 5
    When the tripwire runs
    Then the additionalContext is "[cache tripwire] model changed opus-5-5/max -> sonnet-5-5/high: re-wrote 1k tokens, ~$0.00 of window."

  @gap @wip
  # Backed by: @gap
  Scenario: Baselines are kept per session id
    Given session "s1" has baseline "claude-sonnet-5-5|high" in the state file
    And session "s2" is not in the state file and has drifted to claude-opus-5-5 at effort max
    When the tripwire runs for session "s2"
    Then the state file still maps "s1" to "claude-sonnet-5-5|high"
    And the state file maps "s2" to "claude-opus-5-5|max"

  @gap @wip
  # Backed by: @gap
  Scenario: A payload with no session id is tracked under the key "unknown"
    Given a payload with a valid transcript_path and no session_id
    When the tripwire runs
    Then the state file contains the key "unknown"

  @gap @wip
  # Backed by: @gap
  Scenario: A corrupt state file is treated as empty, so the session is seeded at its first line and a drift fires
    Given the state file contains "{corrupt"
    And session "s1" drifted from claude-sonnet-5-5 at effort high to claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And the additionalContext starts with "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max"
    And the state file maps "s1" to "claude-opus-5-5|max"

  @gap @wip
  # Backed by: @gap
  Scenario: A state file that is valid JSON but not an object leaves the hook silent and the state unchanged
    Given the state file contains "[]"
    And session "s1" drifted from claude-sonnet-5-5 at effort high to claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty
    And the state file still contains "[]"

  @gap @wip
  # Backed by: @gap
  Scenario: A baseline value with no pipe leaves the hook silent and the state unchanged
    Given the state file maps "s1" to "nopipe"
    And session "s1" drifted from claude-sonnet-5-5 at effort high to claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And stdout is empty
    And the state file still maps "s1" to "nopipe"

  @gap @wip
  # Backed by: @gap
  Scenario: A failing state write is swallowed, so the nudge is printed again on the next prompt
    Given the state file cannot be written
    And session "s1" has baseline "claude-sonnet-5-5|high" in memory only
    And the latest main-thread assistant line is claude-opus-5-5 at effort max
    When the tripwire runs on two successive prompts
    Then both runs exit 0
    And both runs print the same additionalContext nudge

  @gap @wip
  # Backed by: @gap
  Scenario: Main-thread lines with no model make the tripwire nudge on every prompt
    # NOTE: probable bug. The stored baseline is the string "None", which never equals the real None
    # of an absent message.model (effort "None" is mapped back to None; the model is not).
    Given session "s1" has baseline "None|None" in the state file
    And every main-thread assistant line has no message.model and no effort field
    When the tripwire runs on two successive prompts
    Then both runs print the additionalContext "[cache tripwire] model changed None/? -> ?/? mid-session."
    And the state file maps "s1" to "None|None" after each run

  # ---- Prices ----------------------------------------------------------------

  # Backed by: tests/test_tokenomics.py::test_tripwire_prices_haiku_5_5_below_the_haiku_4_5_family_rate
  Scenario: Haiku 5.5 is priced at $0.10 per MTok, not the $1.00 Haiku 4.5 family rate
    Given the tripwire price table
    When the price of "claude-haiku-5-5" and of "claude-haiku-4-5-20251001" is looked up
    Then the first is 0.10 and the second is 1.00

  # Backed by: tests/test_tokenomics.py::test_input_prices_agree_with_the_cache_tripwire_hook
  Scenario: Every tripwire input price equals the meter's input price for the same family
    Given the tripwire price table with keys "haiku-5", "haiku", "sonnet", "opus" and "fable"
    When each price is compared with the meter's input price for claude-haiku-5-5, claude-haiku-4-5, claude-sonnet-5-5, claude-opus-5-5 and claude-fable-5-1
    Then all five are equal

  @gap @wip
  # Backed by: @gap
  Scenario: A model id matching no price key has no price
    Given the tripwire price table
    When the price of "claude-mystery-1" and of an empty model id is looked up
    Then both lookups return None

  # ---- Never blocks ----------------------------------------------------------

  @gap @wip
  # Backed by: @gap
  Scenario: A nudge never carries a decision field
    Given a switch from claude-sonnet-5-5 at effort high to claude-opus-5-5 at effort max
    When the tripwire runs
    Then the exit code is 0
    And the output JSON has only the key "hookSpecificOutput"
