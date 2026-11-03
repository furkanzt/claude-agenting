Feature: Fan-out view
  The hooks module hooks/fanouts/register.tsx shows clean runs (scripts/cleanrun.py, and
  clean_runtime.mjs, which runs each agent() call of a Workflow script as its own cleanrun) the
  way Claude Code shows a Workflow: a row above the prompt laid out like the bottom panel's
  Workflow row, and a /fanouts pane laid out like /workflows. scripts/fanout_scan.py finds the
  runs with ps and reads their folders; it never writes.

  # Scanner: what a run folder and the process table say

  # Backed by: tests/test_fanout_scan.py::test_a_live_runtime_shows_running_done_and_queued_calls
  Scenario: A live clean_runtime run lists its calls as running, done and queued
    Given a node clean_runtime.mjs process with --out run1 and one cleanrun child for calls/gkc_B/out
    And journal.jsonl has started lines for gkc:A, gkc:B and denetle:A
    And log.txt has the line "done gkc:A (277 s)"
    When the scanner runs
    Then gkc:A is done with cost 1.26 and gkc:B is running with the child's model and effort
    And denetle:A is queued and the counts are 3 total, 1 done, 1 running, 1 queued

  # Backed by: tests/test_fanout_scan.py::test_tokens_count_output_and_cache_like_the_workflow_view
  Scenario: Tokens count output, cache writes and cache reads, as the Workflow view's tok does
    Given a call whose ledger attempt has 1000 output tokens, 20000 cache writes and 10600 cache reads
    When the scanner runs
    Then the call's tokens are 31600 and its out_tokens are 1000

  # Backed by: tests/test_fanout_scan.py::test_a_fail_line_wins_over_an_old_output_and_names_the_ledger_problem
  Scenario: A FAIL line names the ledger's problem
    Given log.txt has "FAIL denetle:T5:1: cleanrun exit 3" and the call's last attempt has the problem "missing key 'items'"
    When the scanner runs
    Then the call is failed with the error "missing key 'items'"

  # Backed by: tests/test_fanout_scan.py::test_a_failed_call_shows_cleanruns_own_stderr
  Scenario: A failed call shows cleanrun's own stderr
    Given log.txt has "FAIL x:1: cleanrun exit 2" and calls/x_1/stderr.txt ends with a usage-window line
    When the scanner runs
    Then the call's error is that last stderr line

  # Backed by: tests/test_fanout_scan.py::test_a_later_done_line_replaces_an_earlier_fail
  Scenario: A later done line replaces an earlier FAIL line
    Given log.txt has "FAIL x:1" and then "done x:1 (40 s)"
    When the scanner runs
    Then the call is done

  # Backed by: tests/test_fanout_scan.py::test_a_live_process_beats_an_output_left_by_an_earlier_run
  Scenario: A live cleanrun process beats an output an earlier run left
    Given a call with an outputs file and a live cleanrun child for its out-dir
    When the scanner runs
    Then the call is running

  # Backed by: tests/test_fanout_scan.py::test_a_rerun_that_dies_is_not_done_although_the_first_run_left_result_json
  Scenario: A re-run in the same folder that dies is not reported done
    Given log.txt holds a finished first run and a second "start" line with no "finished" line after it
    And result.json from the first run is still there
    When the scanner reads the folder with no process holding it
    Then the run is died, the first run's calls are left out and the cost is the second run's 0.5

  # Backed by: tests/test_fanout_scan.py::test_a_finished_rerun_is_timed_from_its_own_start_line_across_midnight
  Scenario: A finished re-run is timed from its own start line, across midnight
    Given the last "start" line is at 23:58:00 and the run finished at 00:03:00
    When the scanner reads the folder
    Then the run is done with an elapsed time of 300 seconds

  # Backed by: tests/test_fanout_scan.py::test_a_live_rerun_counts_only_its_own_cost
  Scenario: A live re-run counts only its own attempts' cost
    Given a ledger with a 20.0 attempt from an earlier run and a 1.5 attempt from this run
    When the scanner runs while the runtime is live
    Then the run's cost is 1.5

  # Backed by: tests/test_fanout_scan.py::test_an_orphaned_cleanrun_is_shown_under_its_runtime
  Scenario: A cleanrun whose runtime died is shown under that runtime
    Given a cleanrun child for run1/calls/x_1/out whose parent is pid 1
    When the scanner runs
    Then the fan-out is the runtime run1, state died, with x:1 running and a problem saying no runtime records them

  # Backed by: tests/test_fanout_scan.py::test_two_labels_on_one_call_folder_are_flagged_and_do_not_share_numbers
  Scenario: Two labels that share one calls folder are flagged, and the refused one says why
    Given the labels kavram:şekil and kavram:çekil, which both map to calls/kavram__ekil
    And log.txt has "FAIL kavram:çekil: cleanrun exit 2" while kavram:şekil runs
    When the scanner runs
    Then kavram:çekil is failed, says it shares that folder and carries no cost, and the run has a problem naming both labels

  # Backed by: tests/test_fanout_scan.py::test_two_labels_on_one_call_folder_without_a_fail_count_its_numbers_once
  Scenario: Two labels that share one calls folder count its numbers once
    Given kavram:şekil and kavram:çekil both done in calls/kavram__ekil, whose one attempt cost 0.3 and used 1000 tokens
    When the scanner runs
    Then only the first label carries the cost and tokens, the run's totals are 0.3 and 1000, and the share problem is raised

  # Backed by: tests/test_fanout_scan.py::test_a_path_with_spaces_is_joined_back
  Scenario: An out folder with spaces in its path is found
    Given a runtime with --out "My Runs", which ps prints split at the space
    When the scanner runs
    Then the fan-out's folder is "My Runs"

  # Backed by: tests/test_fanout_scan.py::test_a_relative_out_is_resolved_through_the_process_cwd_once
  Scenario: A relative --out is resolved through the process's working directory, once
    Given a runtime started with --out run1
    When the scanner runs twice with the same resolver
    Then the working directory was looked up once

  # Backed by: tests/test_fanout_scan.py::test_a_known_folder_a_process_may_hold_is_unknown_not_dead
  Scenario: A known folder a live process may hold is unknown, not dead
    Given a runtime with --out run1 whose working directory cannot be read
    When the scanner reads the known folder run1
    Then that fan-out's state is unknown

  # Backed by: tests/test_fanout_scan.py::test_a_live_standalone_run_counts_its_claude_children_as_running
  Scenario: A standalone cleanrun counts its claude -p children as running
    Given a cleanrun run with three tasks, one output and two live claude -p children
    When the scanner runs
    Then the tasks are done, pending, pending and the counts say 2 running

  # Backed by: tests/test_fanout_scan.py::test_a_task_out_of_attempts_fails_while_the_run_goes_on
  Scenario: A standalone task out of attempts fails while the run goes on
    Given a live cleanrun with --retries 1 and two invalid attempts for t2 in this run
    When the scanner runs
    Then t2 is failed with its last problem

  # Backed by: tests/test_fanout_scan.py::test_a_task_that_will_not_be_retried_fails_at_once
  Scenario: A standalone task cleanrun will not retry fails at once
    Given a live cleanrun whose last attempt for t1 says "per-run budget reached ... not retried"
    When the scanner runs
    Then t1 is failed

  # Backed by: tests/test_fanout_scan.py::test_a_finished_standalone_run_reads_failed_and_not_run_tasks
  Scenario: A finished standalone run reads its failed and not-run tasks from summary.json
    Given summary.json is finished with t2 failed ("not JSON") and t3 not run ("interrupted")
    When the scanner reads the folder
    Then t2 is failed with "not JSON" and t3 is skipped with "interrupted"

  # Backed by: tests/test_fanout_scan.py::test_a_reused_out_dir_counts_only_what_this_run_requested
  Scenario: A reused out-dir counts only what this run requested
    Given four outputs, three of them older than this run, and a summary with requested 2
    When the scanner reads the folder
    Then the fan-out has 2 agents

  # Backed by: tests/test_fanout_scan.py::test_a_ps_that_exits_non_zero_or_prints_nothing_is_degraded
  Scenario: A ps that fails makes the snapshot degraded
    Given ps exits 1, or prints nothing
    When the scanner runs
    Then the snapshot says degraded true and a "ps failed" problem

  # Backed by: tests/test_fanout_scan.py::test_etime_forms
  # Backed by: tests/test_fanout_scan.py::test_ps_rows_keep_the_whole_command
  # Backed by: tests/test_fanout_scan.py::test_flag_forms
  Scenario: ps elapsed times, command lines and flags are read as ps prints them
    Given the etimes "04:48", "1:02:03" and "2-01:00:00" and the flag forms "--out a" and "--out=b"
    When the scanner parses them
    Then they read 288, 3723 and 176400 seconds, and the values a and b

  # Backed by: tests/test_fanout_scan.py::test_a_node_without_out_is_not_a_runtime
  # Backed by: tests/test_fanout_scan.py::test_only_cleanrun_run_counts
  Scenario: Only a node clean_runtime.mjs with --out and a cleanrun.py run are fan-outs
    Given clean_runtime.mjs without --out, and cleanrun.py plan and status
    When the scanner classifies them
    Then none of them is a fan-out; clean_runtime.mjs with --out and cleanrun.py run are

  # Backed by: tests/test_fanout_scan.py::test_interpreter_options_before_the_script_are_skipped
  Scenario: Interpreter options before the script are skipped
    Given node --enable-source-maps --no-warnings --max-old-space-size=8192 clean_runtime.mjs, and python3 -X utf8 -u cleanrun.py run
    When the scanner classifies them
    Then both are found

  # Backed by: tests/test_fanout_scan.py::test_call_id_matches_clean_runtime
  # Backed by: tests/test_fanout_scan.py::test_an_emoji_label_finds_the_folder_clean_runtime_made
  Scenario: A label with characters outside the BMP finds the folder clean_runtime.mjs made
    Given the labels "duzelt:T5.6" and "kavram:🙂A"
    When their calls folders are named
    Then they are "duzelt_T5.6" and "kavram___A" (an emoji is two UTF-16 units), cut at 120 units

  # Backed by: tests/test_fanout_scan.py::test_the_log_keeps_only_the_last_run
  Scenario: Only the last run in log.txt counts
    Given a log.txt with a finished first run, a FAIL and a dropped-item warning, then a second "start" line
    When the scanner reads it
    Then only the second run's events count, its script is b.js and its start time is the second start line's

  # Backed by: tests/test_fanout_scan.py::test_an_old_output_does_not_make_a_rerun_call_done
  # Backed by: tests/test_fanout_scan.py::test_an_old_summary_does_not_make_a_rerun_call_failed
  # Backed by: tests/test_fanout_scan.py::test_an_old_stderr_is_not_this_failures_reason
  Scenario: Files an earlier run left do not decide a re-run call's state
    Given a call whose tasks.jsonl is fresh but whose output, summary or stderr.txt is older
    When the scanner runs while the runtime is live
    Then the call is queued, and a FAIL reason is "cleanrun exit 2", not the old stderr

  # Backed by: tests/test_fanout_scan.py::test_a_relabelled_call_follows_its_last_started_line
  Scenario: A relabelled call follows its last started line
    Given x:1 started under key c1:old, which has a result, then started again under c1:new
    When the scanner runs
    Then x:1 is one queued row

  # Backed by: tests/test_fanout_scan.py::test_a_finished_summary_without_output_is_a_failure
  Scenario: A finished summary with no output is a failure with its reason
    Given a call whose summary is "stopped" and whose ledger says not_started "usage over 90%"
    When the scanner runs
    Then the call is failed with "usage over 90%"

  # Backed by: tests/test_fanout_scan.py::test_a_summary_stop_reason_explains_a_failed_call
  Scenario: A failed call shows its summary's stop reason
    Given log.txt has "FAIL x:1: cleanrun exit 3" and the call's summary says stopped "max-usd 6 reached"
    When the scanner runs
    Then the call's error is "max-usd 6 reached"

  # Backed by: tests/test_fanout_scan.py::test_ended_runs_without_a_start_line_read_their_state_from_files
  Scenario: A run with no start line reads done, failed or died from result.json and cost.json
    Given ended run folders with result.json and cost.json, cost.json alone, or neither
    When the scanner reads them
    Then they are done, failed and died, and the cost is the ledgers' 2.0, never cost.json's

  # Backed by: tests/test_fanout_scan.py::test_a_run_whose_script_threw_is_failed_by_its_log
  Scenario: A run whose script threw is failed
    Given a log.txt with a "start" line and a cost line but no "finished" line
    When the scanner reads the folder
    Then the run is failed

  # Backed by: tests/test_fanout_scan.py::test_a_running_placeholder_under_a_dead_runtime_is_a_dead_call
  Scenario: A running placeholder under a dead runtime is a stopped call
    Given x:1 with a "running" summary and x:2 never started, and no runtime process
    When the scanner reads the folder
    Then x:1 is died with "its process is gone", x:2 is skipped, and the run is died

  # Backed by: tests/test_fanout_scan.py::test_a_finished_run_ends_at_its_result_json
  # Backed by: tests/test_fanout_scan.py::test_a_finished_run_ignores_a_result_json_left_by_an_earlier_run
  # Backed by: tests/test_fanout_scan.py::test_a_dead_runtime_ends_at_its_newest_file
  # Backed by: tests/test_fanout_scan.py::test_a_dead_run_ends_at_its_journal_when_that_is_newest
  Scenario: A run's end is its result.json when it finished, else its newest file
    Given a finished run with this run's result.json, one with an older result.json, and dead runs whose newest file is a summary or the journal
    When the scanner reads them
    Then the ends are that result.json, the log, the summary and the journal

  # Backed by: tests/test_fanout_scan.py::test_a_dead_run_from_days_ago_is_dated_by_its_log_not_today
  Scenario: A dead run from days ago is dated by its log, not today
    Given a run whose start line and log.txt are three days old
    When the scanner reads it
    Then it started 600 seconds before its log was last written

  # Backed by: tests/test_fanout_scan.py::test_the_shared_ledger_counts_only_this_runs_attempts
  Scenario: The shared OUT/ledger.jsonl counts only this run's attempts
    Given a folder with no per-call ledgers and an OUT/ledger.jsonl with a 9.0 attempt from an earlier run and a 0.5 one from this run
    When the scanner reads it
    Then x:1 and the run cost 0.5

  # Backed by: tests/test_fanout_scan.py::test_a_three_part_spaced_path_takes_the_longest_join
  # Backed by: tests/test_fanout_scan.py::test_a_trailing_word_after_a_spaced_path_is_not_part_of_it
  Scenario: A path with spaces is joined to the longest part that exists, and stops at the next word
    Given the out folders "a b c" (with "a b" also existing) and "My Runs" followed by the word extra
    When the scanner runs
    Then the folders are "a b c" and "My Runs"

  # Backed by: tests/test_fanout_scan.py::test_a_cwd_handed_back_skips_the_lookup
  Scenario: A working directory handed back skips the lookup
    Given a runtime with --out run1 and its cwd passed with --cwd
    When the scanner runs
    Then lsof is never asked

  # Backed by: tests/test_fanout_scan.py::test_an_unresolved_process_holds_only_the_folder_its_path_names
  # Backed by: tests/test_fanout_scan.py::test_an_unresolved_dot_path_may_hold_any_known_folder
  Scenario: An unresolved process makes unknown only the folders it may hold
    Given an unresolved runtime with --out run1, then one with --out "."
    When the scanner reads the known folders run1 and run2, then run1
    Then run1 is unknown and run2 died; with "." every known folder is unknown

  # Backed by: tests/test_fanout_scan.py::test_a_live_fanouts_own_folder_given_back_is_not_listed_twice
  Scenario: A live fan-out's own folder given back is listed once
    Given a running runtime whose folder is also passed with --dir, with and without a trailing slash
    When the scanner runs
    Then the snapshot holds one fan-out

  # Backed by: tests/test_fanout_scan.py::test_a_known_folder_that_was_deleted_is_skipped
  Scenario: A known folder that was deleted is skipped
    Given a --dir that no longer exists
    When the scanner runs
    Then the snapshot holds no fan-out

  # Backed by: tests/test_fanout_scan.py::test_running_fanouts_come_first
  # Backed by: tests/test_fanout_scan.py::test_running_first_then_newest_first
  Scenario: Running fan-outs come first, then the newest
    Given a live runtime and two ended folders started at different times
    When the scanner runs
    Then the order is live, newer, old

  # Backed by: tests/test_fanout_scan.py::test_a_killed_standalone_run_ends_at_its_newest_file
  # Backed by: tests/test_fanout_scan.py::test_a_finished_standalone_run_ends_at_its_summary
  Scenario: A standalone run's end is its newest file
    Given a killed run whose newest file is an output, and a finished one whose newest is its summary
    When the scanner reads them
    Then they end at that output and that summary, timed from .lock

  # Backed by: tests/test_fanout_scan.py::test_a_stopped_standalone_run_says_why
  Scenario: A stopped standalone run says why
    Given a summary stopped with "max-usd reached"
    When the scanner reads it
    Then the run is stopped with the problem "max-usd reached"

  # Backed by: tests/test_fanout_scan.py::test_without_a_retries_flag_one_retry_is_allowed
  # Backed by: tests/test_fanout_scan.py::test_the_retries_flag_is_read
  Scenario: A standalone task gets one retry unless --retries says otherwise
    Given tasks with one and two invalid attempts, with no --retries, then two invalid attempts with --retries 3
    When the scanner runs
    Then one invalid attempt is pending, two are failed, and with --retries 3 two are still pending

  # Backed by: tests/test_fanout_scan.py::test_an_old_output_with_attempts_now_is_being_redone_not_done
  Scenario: A standalone task with an old output and attempts now is being redone
    Given t1 and t2 with outputs from an earlier invocation, t1 with an attempt in this one
    When the scanner runs
    Then t1 is pending and t2 is done and resumed

  # Backed by: tests/test_fanout_scan.py::test_main_prints_a_degraded_v1_snapshot_when_ps_fails
  # Backed by: tests/test_fanout_scan.py::test_main_hands_back_only_cwds_of_live_processes
  Scenario: The scanner prints a v1 snapshot even when ps fails, and hands back only live processes' cwds
    Given ps raising, and --cwd for a live pid 100 and a gone pid 999
    When the scanner runs
    Then the first prints v 1, degraded true and "ps failed"; the second hands back only pid 100

  # The band: a row like the bottom panel's Workflow row

  # Backed by: tests/fanouts.test.tsx > the band draws the bottom-panel Workflow row, and says it is a clean fan-out
  Scenario: A running fan-out gets one bottom-panel row above the prompt
    Given a running fan-out merge5 with 1 of 3 agents done, 7m09s and 132.2k tokens
    When the band is drawn
    Then it reads "◯ merge5  ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱  1/3 · 7m09s · ↓ 132.2k tokens · clean fan-out"
    And it is a plain Button with the digit 1, which the engine draws before it as "1: "

  # Backed by: tests/fanouts.test.tsx > in Ghostty (TERM_PROGRAM ghostty) the bar is █░, as the engine draws it there
  # Backed by: tests/fanouts.test.tsx > in Ghostty (TERM xterm-ghostty) the bar is █░, as the engine draws it there
  Scenario: In Ghostty the row's bar is █░, as the engine draws it there
    Given TERM_PROGRAM ghostty, or TERM xterm-ghostty
    When the band is drawn for a fan-out with 1 of 3 agents done
    Then its bar reads "██████░░░░░░░░░░░░░░"

  # Backed by: tests/fanouts.test.tsx > with only GHOSTTY_RESOURCES_DIR set the bar stays ▰▱, as the engine draws it then
  Scenario: Outside that rule the bar is ▰▱, as the engine draws it, even with GHOSTTY_RESOURCES_DIR set
    Given TERM xterm-256color and GHOSTTY_RESOURCES_DIR set, with no TERM_PROGRAM
    When the band is drawn for a fan-out with 1 of 3 agents done
    Then its bar reads "▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱"

  # Backed by: tests/fanouts.test.tsx > model names, counts and durations read as the Workflow view writes them
  Scenario: Times, token counts and model names read as the engine writes them
    Given 1725 seconds, 2500000 tokens and the model claude-opus-5-5
    When they are formatted
    Then they read "28m45s", "2.5m" and "Opus 5.5"

  # Backed by: tests/fanouts.test.tsx > pressing a band row (ctrl+x tab, enter) opens the pane on that fan-out, with the keyboard
  Scenario: Pressing a band row opens the pane on that fan-out
    Given two running fan-outs in the band, the first row holding the focus ring when the band takes the keyboard
    When the second row is pressed
    Then the pane opens with the keyboard and Escape closing it, showing the second fan-out

  # Backed by: tests/fanouts.test.tsx > each band row carries its digit, so typing 2 into an empty prompt opens the pane on the second, mid-turn too
  Scenario: Typing a band row's digit into an empty prompt opens the pane on that fan-out, mid-turn too
    Given two running fan-outs in the band while Claude is working
    When the band is drawn
    Then its rows carry the digits 1 and 2
    And the row with the digit 2, pressed as the engine presses it for a 2 typed into an empty prompt, opens the pane on the second fan-out

  # Backed by: tests/fanouts.test.tsx > beside a docked pane the band row is clipped to the band's width after its digit, never wrapped
  Scenario: Beside a docked pane the band row is clipped, never wrapped
    Given a running fan-out merge5 and a band 70 cells wide
    When the band is drawn
    Then the row takes the 67 cells after the engine's "1: ", ending "· cl…", its name and bar whole

  # Backed by: tests/fanouts.test.tsx > a finished run is ◯ in success, a failed one ✘, a stopped one ⚠
  Scenario: The row's icon says how a run ended
    Given a done, a failed and a died fan-out that ended 5 seconds ago
    When the band is drawn
    Then their icons are ◯ in success, ✘ in error and ⚠ in warning

  # Backed by: tests/fanouts.test.tsx > the band leaves the drawing to the engine when no fan-out runs
  Scenario: With no fan-out to show, the band is the engine's
    Given no fan-out
    When the band is drawn
    Then the engine draws it

  # Backed by: tests/fanouts.test.tsx > with a survey up the band is the engine's, even while a fan-out runs
  Scenario: A survey keeps the band, even while a fan-out runs
    Given a running fan-out and a survey holding the band
    When the band is drawn
    Then the engine draws it, and without the survey the fan-out's row is drawn

  # Backed by: tests/fanouts.test.tsx > the band shows three rows at most, and fits maxRows
  Scenario: The band shows three rows at most and fits the room it has
    Given four running fan-outs
    When the band is drawn with maxRows 10, then with maxRows 2
    Then it shows 3 rows and "+1 more clean fan-outs · /fanouts", then 1 row and "+3 more"

  # Backed by: tests/fanouts.test.tsx > an ended run keeps its band row five minutes from when it was seen ending
  Scenario: An ended run keeps its row for five minutes from when it was seen ending
    Given a run whose files say it ended long ago, seen running and then seen ending
    When the band is drawn as it ends, 290 seconds later and 310 seconds later
    Then the first two show its ⚠ row and the third leaves the band to the engine

  # Backed by: tests/fanouts.test.tsx > the stale marker shows only while the scanner fails, and clears on the next good scan
  Scenario: The row says so while the scanner fails
    Given a good scan, a failed scan, then a good scan
    When the band is drawn after each
    Then only the second drawing carries "· ⚠ scanner failing"

  # Backed by: tests/fanouts.test.tsx > a run first seen long after it ended does not get band time
  Scenario: A run first seen long after it ended gets no band time
    Given a fan-out that ended an hour before the mod first saw it
    When the band is drawn
    Then the engine draws it

  # Backed by: tests/fanouts.test.tsx > the view never puts an unreadable fan-out in the band, nor announces one
  Scenario: An unreadable fan-out is never put in the band nor announced
    Given a fan-out in state unknown, known to have ended 5 seconds ago
    When the band and the end toasts are worked out
    Then it is in neither

  # The pane: the /workflows view

  # Backed by: tests/fanouts.test.tsx > the pane is the /workflows view: header, Phases column, the open phase's agents, on every surface
  Scenario: The pane is laid out like /workflows
    Given a running fan-out with the phases GKC (done) and Denetle (one running, one queued)
    When the pane is drawn on terminal, desktop, vscode and mobile
    Then it shows the name, "clean fan-out · merge_phases.js", "1/3 agents · 7m09s · $6.36"
    And a frame titled "Phases" and "Denetle · 2 agents" with the rows "  ✔ GKC      1/1" and "❯ 2 Denetle  0/2"

  # Backed by: tests/fanouts.test.tsx > picking a phase, by press or by moving the focus ring, shows its agents
  Scenario: Up and down pick the phase whose agents are shown
    Given the pane open on Denetle
    When the person presses the GKC row, then moves the focus ring onto Denetle
    Then the agents shown are GKC's, then Denetle's

  # Backed by: tests/fanouts.test.tsx > the selected phase takes the focus ring when the pane takes the keyboard
  Scenario: The selected phase holds the focus ring when the pane opens
    Given a fan-out whose open phase is Denetle
    When the pane is drawn
    Then the Denetle row is the one with autoFocus

  # Backed by: tests/fanouts.test.tsx > a phase not started yet says so
  Scenario: A phase not started yet says so
    Given a fan-out whose phases include Düzelt with no agents
    When the person picks Düzelt
    Then the agent column reads "Not started yet"

  # Backed by: tests/fanouts.test.tsx > several fan-outs get a row of tabs; picking one shows it
  # Backed by: tests/fanouts.test.tsx > one fan-out has no tabs
  Scenario: Several fan-outs get tabs
    Given a running fan-out and one that is done
    When the pane is drawn and the second tab is pressed
    Then the tabs read "◯ merge5" and "◯ other" and the header is other's, ending in "· done"

  # Backed by: tests/fanouts.test.tsx > the agent column shows ten rows at a time, with the pager in the bottom border
  Scenario: The agent column shows ten rows at a time, with the pager in the bottom border
    Given a phase of 450 agents
    When the pane is drawn
    Then the agent rows are agent:0 to agent:9 and the bottom border ends " 1-10 of 450 ↓ ╯"

  # Backed by: tests/fanouts.test.tsx > ↓ past the phases moves ❯ onto the agents, and the page scrolls to keep the next row in view
  Scenario: Down past the phases moves the pointer onto the agents and scrolls the page
    Given a phase of 14 agents
    When the focus ring moves onto agent:3, agent:9, agent:13, then back to the phase
    Then ❯ marks agent:3 and agent:9, the pager reads "1-10 of 14 ↓", "2-11 of 14 ↑↓", "5-14 of 14 ↑", and back on the phase no row is marked and the pager is "1-10 of 14 ↓"

  # Backed by: tests/fanouts.test.tsx > a call still queued, its effort unknown, does not hide the effort the others share
  Scenario: A queued call with no effort known yet does not hide the phase's shared effort
    Given a phase with one running xhigh call and one queued call whose effort is not known yet
    When the pane is drawn
    Then the column title ends "· xhigh", the running row reads "Opus 5.5" and the queued row reads "queued"

  # Backed by: tests/fanouts.test.tsx > the focus ring meets every phase row before any agent row
  Scenario: The focus ring meets every phase row before any agent row
    Given a fan-out with two phases, the open one holding two agents
    When the pane is drawn
    Then its Buttons, in order, are phase:1, phase:2, agent:0, agent:1

  # Backed by: tests/fanouts.test.tsx > a phase whose agents share one effort names it once, in the column title
  Scenario: A phase whose agents share one effort names it once, in the column title
    Given the phases Denetle (high and xhigh) and GKC (one xhigh agent)
    When the pane shows each
    Then Denetle's rows name their efforts and its title none, and GKC's title ends "· xhigh" while its row reads "Opus 5.5 · 35.9k tok"

  # Backed by: tests/fanouts.test.tsx > a failed agent's row ends with its error
  Scenario: A failed agent's row carries its error, cut to fit before the frame is
    Given a fan-out with one failed agent "output did not validate"
    When the pane is drawn 130 and then 80 columns wide
    Then the row reads "· failed — output did not validate" before its time, and at 80 columns the reason is cut while the row keeps its 55 cells

  # Backed by: tests/fanouts.test.tsx > a run's first problem shows under the header, the others do not
  Scenario: A run's first problem shows under its header
    Given a stopped fan-out with two problems
    When the pane is drawn
    Then the line under the header stats ("... · stopped") reads "⚠ " and the first problem, and the second is not shown

  # Backed by: tests/fanouts.test.tsx > a scanner that fails is reported in the pane, not thrown
  Scenario: A scanner failure is shown in the pane
    Given the scanner exits 1 with "Traceback: boom"
    When the pane is drawn
    Then it reads "⚠ scanner: fanout_scan.py exited 1: Traceback: boom"

  # Backed by: tests/fanouts.test.tsx > the pane notes when Claude Code is another version than the look was copied from
  # Backed by: tests/fanouts.test.tsx > no version note under the version the look was copied from
  # Backed by: tests/fanouts.test.tsx > no version note when the engine gives no version
  Scenario: The pane notes when Claude Code is not the version the look was copied from
    Given the look was copied from Claude Code 2.1.317
    When the pane is drawn under 2.1.400, under 2.1.317, and with no version
    Then only the first carries the dim line "layout copied from Claude Code 2.1.317; running 2.1.400"

  # Backed by: tests/fanouts.test.tsx > the selected phase is in permission, a done one ✔ success, an open one's number subtle
  Scenario: Phase rows use the Workflow view's colours
    Given a fan-out whose GKC phase is done and Denetle is selected
    When the pane is drawn
    Then Denetle's row is permission, GKC's ✔ success with its counts subtle, the running ⏺ subtle and the frame text

  # Backed by: tests/fanouts.test.tsx > agent stats carry the state where an agent did not simply run
  Scenario: An agent's stats name its state where it did not simply run
    Given died, skipped, pending, resumed and twice-attempted agents
    When their stats are written
    Then they end "· stopped", "· skipped", "· queued", "· resumed" and "· 2 attempts"

  # Backed by: tests/fanouts.test.tsx > the header ends with the state of a run that is over
  Scenario: The header ends with the state of a run that is over
    Given a running, a done, a failed and a died fan-out
    When their header stats are written
    Then the running one has no state word and the others end "· done", "· failed" and "· stopped"

  # Backed by: tests/fanouts.test.tsx > the phase column widens for a long title instead of cutting a short word
  Scenario: The phase column widens for a long title instead of cutting a short word
    Given the phases GKC and Denetle, then one titled "A very long phase title indeed"
    When the phase column is sized
    Then it is 18 cells and "Denetle" fits, then 28 cells at most

  # Opening, closing and the scan loop

  # Backed by: tests/fanouts.test.tsx > /fanouts opens the pane with the keyboard, Escape closing it; /fanouts again closes it
  Scenario: /fanouts opens the pane, and closes it when it is open
    Given the pane is closed
    When the person runs /fanouts twice
    Then the first opens it with focus and closeOnEscape, the second closes it

  # Backed by: tests/fanouts.test.tsx > /fanouts runs at once while a turn is in flight, as /rename does
  Scenario: /fanouts runs at once while Claude is working
    Given a session starts with the plugin loaded
    When the plugin registers /fanouts
    Then it registers it with immediate true, so typing /fanouts mid-turn opens the pane without waiting for the turn to end

  # Backed by: tests/fanouts.test.tsx > a toast says when a running fan-out finishes; a stopped one says stopped
  # Backed by: tests/fanouts.test.tsx > a stopped run is announced as stopped
  Scenario: A toast says when a running fan-out ends
    Given a fan-out seen running
    When the next scan finds it done, or died
    Then a toast reads "clean fan-out merge5 finished: 3/3 agents · 7m12s · $6.36", or "... stopped: ..."

  # Backed by: tests/fanouts.test.tsx > a scan that cannot read the process table keeps the last snapshot: no false end toast
  Scenario: A degraded scan keeps the last snapshot and toasts nothing
    Given a running fan-out, then a snapshot with degraded true
    When the second scan lands
    Then no toast fires, the row still shows the run and the pane shows the scanner error

  # Backed by: tests/fanouts.test.tsx > a run unreadable for one scan keeps its row and its end is still announced
  Scenario: A run unreadable for one scan keeps its row and its end toast
    Given a running fan-out, then the same folder unknown, then done
    When the three scans land
    Then the row stays after the unknown scan and one "finished" toast fires after the last

  # Backed by: tests/fanouts.test.tsx > it scans every 3 s while a fan-out runs and every 15 s while none does
  Scenario: The scan runs every 3 seconds while a fan-out runs, every 15 seconds otherwise
    Given a running fan-out, then none
    When the clock moves 3, 14 and then 1 more second
    Then the scanner has run 2 times and then 3 times

  # Backed by: tests/fanouts.test.tsx > /fanouts while a scan is scheduled does not start a second loop
  Scenario: /fanouts does not start a second scan loop
    Given the scan loop is running at 3 seconds
    When /fanouts runs and the clock moves 30 seconds
    Then the scanner has run 10 more times

  # Backed by: tests/fanouts.test.tsx > the scanner is given back the folders it reported and the cwds it resolved
  Scenario: The scanner is given back the folders and working directories it reported
    Given a scan that reported /w/clean/merge5 and pid 27785 in /w
    When the next scan starts
    Then its arguments end "--dir /w/clean/merge5 --cwd 27785=/w"

  # Backed by: tests/fanouts.test.tsx > an ended folder is passed back for two hours, then dropped
  Scenario: An ended folder is passed back to the scanner for two hours
    Given a fan-out seen ending
    When scans run 7100 and 7300 seconds later
    Then the scan after the first still passes its folder with --dir, and the scan after the second does not

  # Backed by: tests/fanouts.test.tsx > at most twenty folders are passed back, newest first
  Scenario: At most twenty folders are passed back, newest first
    Given 25 ended fan-outs
    When the next scan starts
    Then it passes 20 folders with --dir, the newest first
