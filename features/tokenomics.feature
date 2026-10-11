Feature: The meter prices Claude Code transcripts at list price per category and reports what a Workflow agent costs to start

  # ---------------------------------------------------------------- price rows

  # Backed by: tests/test_tokenomics.py::test_every_row_prices_each_category_from_the_price_page
  Scenario: Every price row prices input, output, cache read and both cache writes from the price page
    Given a call on model "claude-sonnet-5-5" with 1,000,000 tokens in each of input, output, cache read, 5-minute write and 1-hour write
    When the meter prices the call
    Then the dollars are $2.00 input, $10.00 output, $0.20 cache read, $2.50 5-minute write and $4.00 1-hour write
    And the same check holds for every row on the price page, which are the six rows of PRICE_PAGE
    And "claude-haiku-5-5" is checked with 20,000 tokens in each category (a prompt of 80,000) at $0.10, $0.50, $0.01, $0.125 and $0.20 per MTok, because a prompt over 100,000 tokens pays the long-prompt row

  # Backed by: tests/test_tokenomics.py::test_previous_generation_is_not_priced_as_5_5
  Scenario: The previous generation of a model keeps its own price row
    Given the price table
    When the meter looks up "claude-opus-5" and "claude-opus-5-5"
    Then the two rows differ
    And the cache read price is $0.50 per MTok for "claude-opus-5" and $0.20 per MTok for "claude-opus-5-5"

  # Backed by: tests/test_tokenomics.py::test_dated_suffix_and_alias_resolve_to_the_same_row
  Scenario: A trailing date or bracket suffix on a model id resolves to the bare model's row
    Given the price table
    When the meter looks up "claude-opus-5-5-20260922" and "claude-opus-5-5[1m]"
    Then both return the same row as "claude-opus-5-5"
    And "claude-haiku-4-5" returns the same row as "claude-haiku-4-5-20251001"

  # Backed by: tests/test_tokenomics.py::test_the_documented_columns_of_the_older_rows
  Scenario: The older Sonnet 5, Fable 5 and Opus 5 rows are marked as partly derived
    Given the price table
    When the meter looks up "claude-sonnet-5", "claude-fable-5" and "claude-opus-5"
    Then Sonnet 5 is $2 input and $10 output, Fable 5 is $10 input, $50 output and $1.00 cache read, and Opus 5 is $5 input, $25 output and $0.50 cache read
    And all three rows have derived true
    And the row for "claude-opus-5-5" has derived false

  # Backed by: tests/test_tokenomics.py::test_prices_are_dated
  Scenario: The price table carries a date that the report header repeats
    Given the price table
    When the meter reads PRICES_AS_OF and builds the price header
    Then PRICES_AS_OF matches the form YYYY-MM-DD
    And the price header contains that date

  # Backed by: tests/test_tokenomics.py::test_input_prices_agree_with_the_cache_tripwire_hook
  Scenario: The meter's input prices agree with the cache tripwire's prices
    Given the cache tripwire hook with its PRICES_PER_MTOK families haiku-5, haiku, sonnet, opus and fable
    When each family price is compared with the meter's input price for the matching model id
    Then every family price equals the meter's input price

  # --------------------------------------------------------- Haiku 5.5 long prompt

  # Backed by: tests/test_tokenomics.py::test_prompt_at_the_threshold_pays_the_short_rate
  Scenario: A Haiku 5.5 prompt of exactly 100,000 tokens pays the short rate
    Given a call on model "claude-haiku-5-5" with 100,000 input tokens and 1,000,000 output tokens
    When the meter prices the call
    Then the input dollars are $0.01 at $0.10 per MTok
    And the output dollars are $0.50 at $0.50 per MTok

  # Backed by: tests/test_tokenomics.py::test_prompt_over_the_threshold_pays_the_long_rate_on_every_category
  Scenario: A Haiku 5.5 prompt over 100,000 tokens pays the long rate on every category
    Given a call on model "claude-haiku-5-5" with a prompt of 100,001 tokens (1 input token, 50,000 cache read tokens and 50,000 1-hour write tokens) and 1,000,000 output tokens
    When the meter prices the call
    Then the dollars are $0.0000005 input, $0.0025 cache read, $0.05 1-hour write and $2.50 output

  # Backed by: tests/test_tokenomics.py::test_a_model_without_a_long_row_ignores_the_threshold
  Scenario: A model with no long-prompt row ignores the 100,000 token threshold
    Given a call on model "claude-sonnet-5-5" with 200,000 input tokens
    When the meter prices the call
    Then the input dollars are $0.40 at $2 per MTok

  @gap @wip
  # Backed by: @gap
  Scenario: A bracket suffix on the Haiku 5.5 id still earns the long-prompt row
    Given a call on model "claude-haiku-5-5[1m]" with 100,001 input tokens
    When the meter prices the call
    Then the input dollars are $0.0500005 at $0.50 per MTok

  # ------------------------------------------------------------ cost by category

  # Backed by: tests/test_tokenomics.py::test_writes_are_priced_by_ttl
  Scenario: Five-minute and one-hour cache writes are priced at different rates
    Given a call on model "claude-opus-5-5" with 1,000,000 5-minute write tokens and 1,000,000 1-hour write tokens
    When the meter prices the call
    Then the 5-minute write dollars are $5.00
    And the 1-hour write dollars are $8.00

  # Backed by: tests/test_tokenomics.py::test_record_without_a_split_is_a_5m_write_and_flagged
  Scenario: A cache write with no 5m/1h split is priced as a 5-minute write and counted in the footer
    Given a call on model "claude-opus-5-5" with 1,000,000 cache-creation tokens and no cache_creation breakdown
    When the meter prices the call
    Then the write is 1,000,000 5-minute tokens and 0 1-hour tokens, priced at $5.00
    And the call is marked as a legacy write
    And a footer line says the call had no 5m/1h cache-write split

  # Backed by: tests/test_tokenomics.py::test_a_split_that_does_not_add_up_puts_the_rest_in_5m
  Scenario: A cache-write split that falls short of the total puts the remainder in the 5-minute bucket
    Given a usage block with 500,000 5-minute tokens, 500,000 1-hour tokens and a cache_creation_input_tokens total of 1,500,000
    When the meter splits the writes
    Then the result is 1,000,000 5-minute tokens, 500,000 1-hour tokens and legacy false

  # Backed by: tests/test_tokenomics.py::test_advisor_iteration_is_priced_at_its_own_model_and_added
  Scenario: An advisor iteration is priced at the advisor model's rates and added to the call
    Given a "claude-sonnet-5-5" call with 1,000,000 input tokens and an advisor_message iteration on "claude-opus-5-5" with 1,000,000 input and 100,000 output tokens
    When the meter prices the call
    Then the advisor dollars are $6.00 at Opus 5.5 rates
    And the input dollars are $2.00 and the call total is $8.00
    And the call counts 1 advisor call

  # Backed by: tests/test_tokenomics.py::test_advisor_on_an_unknown_model_is_listed_not_guessed
  Scenario: An advisor iteration on an unpriced model costs $0 and is kept as unpriced tokens under its model name
    Given a "claude-sonnet-5-5" call with an advisor_message iteration on "claude-mystery-9" with 50 input and 5 output tokens
    When the meter prices the call
    Then the advisor dollars are $0.00
    And the unpriced tokens for "claude-mystery-9" are 55

  @gap @wip
  # Backed by: @gap
  Scenario: A cache write inside an advisor iteration with no split marks the call as a legacy write
    Given a "claude-sonnet-5-5" call whose advisor_message iteration has 1,000 cache-creation tokens and no cache_creation breakdown
    When the meter prices the call
    Then the call is marked as a legacy write
    And the footer counts one call priced as a 5-minute write

  # Backed by: tests/test_tokenomics.py::test_unknown_model_is_unpriced_with_its_tokens_kept
  Scenario: A model that is not in the table is unpriced, with its tokens kept and listed
    Given a call on model "claude-opus-4-8" with 10 input, 20 output, 30 cache read and 40 1-hour write tokens
    When the meter prices the call and builds the footer
    Then priced is false and the dollars sum to $0.00
    And the tokens sum to 100
    And a footer line names "claude-opus-4-8" with "100 tokens"

  @gap @wip
  # Backed by: @gap
  Scenario: A call with no model name is listed as unpriced under "(none)"
    Given a call with no model field and 7 input tokens
    When the meter prices the call and builds the footer
    Then the footer line is "unpriced model (none): 1 calls, 7 tokens counted, $0 in the totals"

  # Backed by: tests/test_tokenomics.py::test_a_suffixed_derived_model_still_prints_its_note
  Scenario: A derived price row prints its note in the footer, also when the model id has a bracket suffix
    Given a call on model "claude-sonnet-5[1m]" with 1 input token
    When the footer is built from the call
    Then a footer line contains "claude-sonnet-5 is partly derived: input and output documented"

  # Backed by: tests/test_tokenomics.py::test_negative_token_counts_are_clamped
  Scenario: Negative token counts are treated as zero
    Given a call on model "claude-opus-5-5" with input_tokens -1,000,000 and output_tokens -5
    When the meter prices the call
    Then the input and output dollars are $0.00
    And the input tokens are 0

  # Backed by: tests/test_tokenomics.py::test_malformed_usage_fields_are_zero_not_a_crash
  Scenario: Malformed usage fields never raise and never produce negative dollars
    Given calls on model "claude-opus-5-5" whose usage has string, null or list token counts, is itself a string, has iterations 5, or has a non-numeric cache_creation split
    When the meter builds each call's parts
    Then no call raises
    And every call total is at least $0.00

  # Backed by: tests/test_tokenomics.py::test_prices_a_known_main_call
  Scenario: The overview prices a known main-session call and reports the 1-hour write share
    Given a main session with one "claude-opus-5-5" call of 1,000,000 input tokens and 1,000,000 1-hour write tokens
    When the overview runs with --days 7
    Then the output contains "cost $12.00"
    And the output contains "100% of 1,000,000 cache-write tokens were 1-hour writes"

  @gap @wip
  # Backed by: @gap
  Scenario: The overview prints a total shadow cost split into main and agents
    Given a main session call costing $12.00 and an agent call costing $2.00
    When the overview runs with --days 7
    Then the output contains "Total shadow cost: $14.00 (main $12.00 / agents $2.00)"

  # Backed by: tests/test_tokenomics.py::test_advisor_cost_is_reported_separately
  Scenario: The overview reports advisor dollars on their own line
    Given a main session with one "claude-sonnet-5-5" call and an advisor_message iteration on "claude-opus-5-5" with 1,000,000 input tokens
    When the overview runs with --days 7
    Then the output contains "advisor iterations: $4.00 over 1 advisor calls"

  # ------------------------------------------------- deduplication and synthetic

  # Backed by: tests/test_tokenomics.py::test_dedup_keeps_only_the_last_line_per_message_id
  Scenario: Only the last transcript line per message id counts as a call
    Given a transcript with three lines for message "m1" (output 1, 2 and 99 tokens) and one line for "m2" (output 7)
    When the meter deduplicates the file
    Then the raw count is 4
    And the kept calls have output tokens 99 and 7

  # Backed by: tests/test_tokenomics.py::test_dedup_factor_counts_streamed_duplicates
  Scenario: The overview's dedup factor is raw lines divided by real calls
    Given an agent file with three streamed lines for one message id
    When the overview runs with --days 7
    Then the output contains "Agents: 1 calls (raw 3, dedup 3.00x)"

  # Backed by: tests/test_tokenomics.py::test_synthetic_lines_in_agent_files_are_skipped_and_do_not_inflate_the_dedup_factor
  Scenario: A synthetic line in an agent file is skipped and does not raise the dedup factor
    Given an agent file with one "claude-opus-5-5" call and one "<synthetic>" line
    When the overview runs with --days 7
    Then the output contains "Agents: 1 calls (raw 1, dedup 1.00x)"
    And the output contains "1 synthetic zero-token line(s) skipped"

  # Backed by: tests/test_tokenomics.py::test_synthetic_lines_in_the_main_session_do_not_inflate_its_dedup_factor_either
  Scenario: A synthetic line in the main session does not raise its dedup factor
    Given a main session with one "claude-opus-5-5" call and one "<synthetic>" line
    When the overview runs with --days 7
    Then the output contains "Main session: 1 calls (raw 1, dedup 1.00x)"

  # Backed by: tests/test_tokenomics.py::test_unpriced_and_synthetic_lines_show_up_in_the_notes
  Scenario: The overview's Notes list an unpriced model and count the synthetic line
    Given a main session with one "claude-opus-4-8" call of 10 input tokens and one "<synthetic>" line
    When the overview runs with --days 7
    Then the output contains "unpriced model claude-opus-4-8"
    And the output contains "1 synthetic zero-token line(s) skipped"
    And the output contains "Main session: 1 calls"

  # Backed by: tests/test_tokenomics.py::test_one_odd_line_does_not_discard_the_file
  Scenario: One malformed transcript line costs that line, not the file
    Given an agent file with one good call followed by an assistant record with a null message, a JSON list, an assistant record with a string message and a line that is not JSON
    When the meter deduplicates the file
    Then exactly 1 call is returned

  # Backed by: tests/test_tokenomics.py::test_the_cli_survives_odd_records_and_still_counts_the_good_ones
  Scenario: The overview exits 0 on a transcript with odd effort, agent id and usage values
    Given a main session and an agent file holding a good call and a call whose usage is a string, effort is a list and agentId is a list
    When the overview runs with --days 7
    Then it exits with code 0

  # Backed by: tests/test_tokenomics.py::test_a_dangling_symlink_named_like_a_transcript_does_not_crash
  Scenario: A dangling symlink named like an agent transcript does not stop either report
    Given a workflow folder holding a valid "agent-ok.jsonl" and a symlink "agent-dead.jsonl" pointing at a file that does not exist
    When the overview and then anatomy run with --days 7
    Then both exit with code 0

  @gap @wip
  # Backed by: @gap
  Scenario: Distinct agents are counted by agent id, falling back to the file path when the id is missing
    Given two agent files, one whose calls carry agentId "a1" on two lines and one whose calls carry no agentId
    When the overview runs with --days 7
    Then the output contains "Distinct agents: 2"

  # Backed by: tests/test_tokenomics.py::test_naive_timestamps_are_treated_as_utc
  Scenario: A timestamp with no zone is read as UTC
    Given the timestamp "2026-10-06T10:00:00"
    When the meter parses it
    Then the UTC offset is 0

  # ------------------------------------------------------------------ overview

  # Backed by: tests/test_tokenomics.py::test_old_invocation_still_works_and_matches_the_explicit_subcommand
  Scenario: The overview is the default report and matches the explicit overview subcommand
    Given a main session with one "claude-opus-5-5" call of 1,000,000 input tokens
    When the meter runs with "--days 7" and again with "overview --days 7"
    Then both exit with code 0 and print identical output
    And the output contains "table dated" followed by the PRICES_AS_OF date

  # Backed by: tests/test_tokenomics.py::test_missing_projects_dir_fails_cleanly
  Scenario: The overview fails with exit code 1 when the projects directory does not exist
    Given a projects directory path that does not exist
    When the overview runs with --projects-dir at that path
    Then the exit code is 1
    And stderr contains "No such projects dir"

  @gap @wip
  # Backed by: @gap
  Scenario: Anatomy fails with exit code 1 when the projects directory does not exist
    Given a projects directory path that does not exist
    When anatomy runs with --projects-dir at that path
    Then the exit code is 1
    And stderr contains "No such projects dir: /nonexistent" for the path "/nonexistent"

  # Backed by: tests/test_tokenomics.py::test_old_and_sidechain_lines_and_stale_files_are_not_counted
  Scenario: Old lines, sidechain lines and files older than the window are not counted
    Given a fresh main session file with one current call, one 30-day-old call and one sidechain call, and a second session file last modified 40 days ago
    When the overview runs with --days 7
    Then the output contains "Main session: 1 calls"
    And the output contains "Scanned 1 main session files"

  # Backed by: tests/test_tokenomics.py::test_default_window_is_21_days
  Scenario: The default window is 21 days
    Given a main session with one call made 10 days ago
    When the overview runs with no --days and again with --days 7
    Then the first output contains "Main session: 1 calls"
    And the second output contains "Main session: 0 calls"

  # Backed by: tests/test_tokenomics.py::test_flag_values_are_validated
  Scenario: A --days or --min-agents value below 1 exits with code 2
    Given the flags "--days 0", "--days -3", "anatomy --min-agents 0" and "anatomy --days 0"
    When the meter runs with each
    Then every run exits with code 2
    And stderr contains "must be 1 or more"

  # Backed by: tests/test_tokenomics.py::test_spawn_tax_uses_the_first_call_and_prices_only_the_write
  Scenario: The spawn tax prices only the first call's cache write
    Given an agent whose first "claude-opus-5-5" call wrote 1,000,000 1-hour tokens and produced 100,000 output tokens, and whose second call wrote 2,000,000 1-hour tokens
    When the overview runs with --days 7
    Then the output contains "Spawn tax: median first-call cache-write 1,000,000 tokens (~$8.000/spawn at the write rates)"

  @gap @wip
  # Backed by: @gap
  Scenario: No spawn tax line is printed when no agent's first call wrote to cache
    Given an agent whose first call has 1,000 input tokens and no cache writes
    When the overview runs with --days 7
    Then the output contains no line starting with "Spawn tax"

  # Backed by: tests/test_tokenomics.py::test_effort_distribution_splits_at_the_cutoff
  Scenario: The effort distribution is split at --effort-cutoff
    Given an agent with a call 2 days ago at effort "high" and a call 1 hour ago at effort "xhigh", and an --effort-cutoff 1 day ago
    When the overview runs with --days 7
    Then the line "Agent effort distribution before" shows "high=100%"
    And the line "Agent effort distribution after" shows "xhigh=100%"

  @gap @wip
  # Backed by: @gap
  Scenario: An effort-distribution range with no calls prints a placeholder
    Given an empty projects directory
    When the overview runs with --days 7 and --effort-cutoff 2026-01-01T00:00:00+00:00
    Then both effort distribution lines end with "(no calls in this range)"

  # ------------------------------------------------------------------- anatomy

  # Backed by: tests/test_tokenomics.py::test_first_call_numbers_and_cost_match_a_hand_computation
  Scenario: Anatomy reports first-call context, fresh write and whole-agent cost per group
    Given a workflow of three generic "claude-sonnet-5-5" agents with a skill listing, two of which start with 17,000 cache read and 13,000 1-hour write tokens and one with a 40,000 token 1-hour write
    When anatomy runs with --days 7 and --format json
    Then the generic skill-listing group has n 3, first_context_median 30,002, first_context_p90 40,002, first_fresh_write_median 13,000 and first_cache_read_median 17,000
    And write_1h_share is 1.0
    And cost_median equals the hand-priced cost of the median agent's two calls at Sonnet 5.5 rates

  # Backed by: tests/test_tokenomics.py::test_every_statistic_matches_a_hand_computation
  Scenario: Every anatomy statistic uses nearest-rank p90 and the median of the group
    Given five generic agents in one group with first-call writes of 10,000 to 50,000 tokens, one to five calls each, advisor calls on the last three and thinking tokens of 100 to 500
    When anatomy runs with --min-agents 5
    Then agents.analysed is 5 and agents.calls is 15
    And first_context_p90 is the largest of the five first contexts, not the fourth
    And first_fresh_write_median is 30,000, first_cache_read_median is 3,000, calls_median is 3 and thinking_tokens_median is 300
    And cost_median, cost_p90, cost_min, cost_max and advisor_cost_median equal the hand-priced values

  # Backed by: tests/test_tokenomics.py::test_nearest_rank
  Scenario: The p90 is a nearest-rank percentile and equals the maximum below ten values
    Given the value lists [7], [1,2,3,4,5], 1 to 10 and 1 to 25
    When the meter takes the 0.9 percentile of each
    Then the results are 7, 5, 9 and 23

  # Backed by: tests/test_tokenomics.py::test_small_groups_are_suppressed_and_counted
  Scenario: A group smaller than --min-agents is suppressed and counted
    Given a workflow with 7 agents in which one "claude-opus-5-5" agent is alone in its group
    When anatomy runs with --days 7 and again with --min-agents 1
    Then the first report has suppressed groups 1 and agents 1, and no group for "claude-opus-5-5"
    And the second report has suppressed groups 0 and agents 0

  # Backed by: tests/test_tokenomics.py::test_missing_fields_print_n_a_not_zero
  Scenario: A thinking-token median with no data prints n/a, and coverage reads 0 percent
    Given a workflow whose calls carry no thinking token counts and no usage.iterations
    When anatomy runs with --days 7
    Then thinking_tokens_median is "n/a" and coverage is 0 percent for both iterations and thinking
    And the text report contains "thinking tokens median n/a"

  # Backed by: tests/test_tokenomics.py::test_missing_fields_print_n_a_not_zero
  Scenario: Low coverage of advisor and thinking fields adds a FLOORS note
    Given a workflow whose calls carry usage.iterations and thinking token counts on 0 percent of calls
    When anatomy runs with --days 7 in text format
    Then the Notes contain "FLOORS"

  # Backed by: tests/test_tokenomics.py::test_coverage_counts_calls_that_carry_the_fields
  Scenario: Coverage is the share of calls that carry usage.iterations and thinking tokens
    Given five agents with 15 calls in total, 3 calls carrying usage.iterations and 5 carrying thinking tokens
    When anatomy runs with --min-agents 5
    Then coverage.iterations_pct_of_calls is 20
    And coverage.thinking_pct_of_calls is 33

  @gap @wip
  # Backed by: @gap
  Scenario: The typed-versus-generic caveat is always the last note
    Given any workflow with at least one analysed agent
    When anatomy runs with --days 7 and --format json
    Then the last entry of notes is "typed-versus-generic differences are observational (different tasks, sessions and tool sets), not a controlled comparison"

  @gap @wip
  # Backed by: @gap
  Scenario: Anatomy JSON states that dollars are list price only
    Given a workflow with at least one analysed agent
    When anatomy runs with --days 7 and --format json
    Then list_price_only is true
    And prices_as_of equals PRICES_AS_OF

  # Backed by: tests/test_tokenomics.py::test_start_order_decides_the_rank_not_the_file_name
  Scenario: Start rank follows the first call's time, not the file name
    Given five generic agents a1 to a5 where a5 made its first call first and a1 last
    When anatomy runs with --min-agents 1
    Then rank bucket "0" has first_fresh_write_median 50,000
    And rank bucket "1-2" has n 2 and first_fresh_write_median 35,000
    And rank bucket "3+" has first_fresh_write_median 15,000

  # Backed by: tests/test_tokenomics.py::test_start_rank_and_attachment_sizes
  Scenario: A start-rank bucket below --min-agents is omitted; rank counts all agents in the workflow and buckets are reported per kind
    Given a workflow of 4 generic and 3 typed agents in which the generic agents started before the typed ones
    When anatomy runs with --days 7
    Then the generic rank bucket "0" is absent because it holds one agent
    And the typed rank bucket "3+" has n 3 and first_fresh_write_median 9,000

  # Backed by: tests/test_tokenomics.py::test_attachments_are_summed_per_type_and_only_those_before_the_first_call_count
  Scenario: Attachment sizes are summed per type and only those before the first call count
    Given five agents each with two skill_listing attachments of about 7,040 characters before the first call and one 50,000-character skill_listing attachment after it
    When anatomy runs with --min-agents 5
    Then the skill_listing row has agents 5
    And chars_median is between 14,000 and 14,200

  # Backed by: tests/test_tokenomics.py::test_journal_counts_come_from_the_finish_check_logic
  Scenario: Anatomy takes started and returned agent counts from the finish check's journal logic
    Given a workflow whose journal.jsonl starts 7 agents and returns 6
    When anatomy runs with --days 7 and --format json
    Then journal is {"agents_started": 7, "agents_returned": 6}
    And workflows is 1

  @gap @wip
  # Backed by: @gap
  Scenario: Anatomy reports the journal as n/a when an analysed workflow has no journal
    Given an analysed workflow folder with no journal.jsonl
    When anatomy runs with --days 7 and --format json
    Then journal is "n/a"
    And the text report has no "Journals:" line

  @gap @wip
  # Backed by: @gap
  Scenario: Anatomy counts agent files it could not analyse and says so in the notes
    Given a workflow in which analysing one agent file raises
    When anatomy runs with --days 7 and --format json
    Then the notes contain "1 agent file(s) could not be analysed and are not counted"

  # Backed by: tests/test_tokenomics.py::test_journal_logic_agrees_with_the_hook_on_the_trimmed_real_fixtures
  Scenario: The meter's journal reader agrees with the finish-check hook on recorded journals
    Given the fixtures "journal_retried.jsonl" and "journal_incomplete.jsonl"
    When the meter's loaded check_journal reads each
    Then "journal_retried.jsonl" gives returned 18 and started 18
    And "journal_incomplete.jsonl" gives returned 13 and started 18

  # Backed by: tests/test_tokenomics.py::test_json_output_carries_no_ids_paths_labels_or_content
  Scenario: The anatomy JSON carries no id, path, label, content or agent type name
    Given a workflow whose project, session, label, attachment content and agent type are marked with secret strings
    When anatomy runs with --days 7 and --format json
    Then none of the secret strings, the projects directory path or "/Users/" appear in the output
    And no key named prompt, text, content, label, path, agentId, session, cwd, input or key appears

  # Backed by: tests/test_tokenomics.py::test_by_type_is_opt_in_and_local
  Scenario: --by-type adds the exact agent type name to each group
    Given a workflow with agents of type "agenting:researcher"
    When anatomy runs with --by-type and --format json
    Then the output contains "agenting:researcher"
    And a group has agent_type "agenting:researcher"

  # Backed by: tests/test_tokenomics.py::test_out_file_is_written_whole_and_stdout_stays_empty
  Scenario: --out writes the whole report to the file, leaves stdout empty and leaves no temp file
    Given a workflow with analysed agents
    When anatomy runs with --format json and --out at a path in the projects directory
    Then stdout is empty
    And the file parses as JSON with prices_as_of equal to PRICES_AS_OF
    And no temporary file "report.json.*" is left behind

  # Backed by: tests/test_tokenomics.py::test_an_unwritable_out_path_is_a_message_not_a_traceback
  Scenario: An unwritable --out path exits 1 with a message
    Given an --out path whose parent is a regular file
    When anatomy runs with that --out
    Then the exit code is 1
    And stderr contains "cannot write"
    And stderr does not contain "Traceback"

  # Backed by: tests/test_tokenomics.py::test_an_old_agent_inside_a_fresh_workflow_is_left_out
  # Backed by: tests/test_tokenomics.py::test_an_agent_whose_first_call_is_old_is_left_out_even_if_its_last_call_is_recent
  Scenario: An agent whose first call is older than the window is left out of a fresh workflow
    Given a fresh workflow folder with 7 recent agents and one agent whose first call is 30 days old
    When anatomy runs with --days 7
    Then agents.analysed is 7
    And an old first call is excluded even when the agent's last call is 1 minute old

  # Backed by: tests/test_tokenomics.py::test_a_workflow_whose_files_are_all_older_than_the_window_is_skipped
  Scenario: A workflow whose agent files are all older than the window is skipped
    Given a workflow whose agent files were last modified 60 days ago
    When anatomy runs with --days 7 and --format json
    Then agents.analysed is 0
    And groups is an empty list
