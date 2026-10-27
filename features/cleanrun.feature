Feature: Clean runs fan a set of self-contained tasks out as separate claude -p processes with explicit routing, a money cap, safe resume and recorded results

  # ---------------------------------------------------------------- run, plan, status

  # Backed by: tests/test_cleanrun.py::test_every_task_runs_once_in_its_own_kit_with_the_pinned_flags
  Scenario: Each task runs once in its own kit with the pinned flags
    Given a tasks file with three tasks "t0", "t1" and "t2", where "t1" lists the file "page.txt"
    And a system prompt file whose bytes are "RULES: answer ok.\r\nSecond line.\r\n"
    When I run cleanrun.py run with model "claude-opus-5-5", effort "xhigh" and tools "Read"
    Then the exit code is 0
    And summary.json says state "finished", ran 3, resumed 0 and no failed task
    And claude was launched exactly three times, each with the prompt on stdin and the flags "--restricted", "--strict-mcp-config", "--no-session-persistence" and "--disable-slash-commands"
    And each launch carries "--model claude-opus-5-5", "--effort xhigh", "--tools Read", "--output-format json" and the schema under "--json-schema"
    And each launch reads the system prompt byte for byte, CRLF included, through "--system-prompt-file" and never gets "--system-prompt"
    And the working directory of "t1" holds only "page.txt" and those of "t0" and "t2" are empty
    And outputs/t1.json holds the structured output and ledger.jsonl holds three attempt records

  @gap @wip
  # Backed by: @gap
  Scenario: Without --tools the run is given an empty tool list
    Given a tasks file with one task
    When I run cleanrun.py run without a --tools option
    Then the claude command line carries "--tools" followed by an empty string

  # Backed by: tests/test_cleanrun.py::test_plan_launches_nothing_and_bounds_overshoot_by_the_tasks_that_run
  Scenario: Plan launches nothing and bounds the overshoot by the tasks that will run
    Given a tasks file with one task
    When I run cleanrun.py plan with "--max-usd 5", "--jobs 4" and the default "--per-run-usd 2.5"
    Then the exit code is 0
    And claude is never launched
    And stdout contains "1 to run"
    And stdout contains "worst-case overshoot about 1 x $2.5", which is min(jobs, tasks) and not jobs
    And stdout contains "soft cap"

  @gap @wip
  # Backed by: @gap
  Scenario: Plan counts finished tasks as resumes
    Given a finished run of two tasks in an output directory
    When I run cleanrun.py plan with the same arguments
    Then stdout contains "2 resume, 0 to run"
    And the exit code is 0

  # Backed by: tests/test_cleanrun.py::test_the_banner_counts_only_the_tasks_that_will_run
  Scenario: The run banner counts only the tasks that will launch
    Given a finished run of two tasks in an output directory
    When I run cleanrun.py run again with the same arguments
    Then stdout contains "2 resume, 0 to run"
    And stdout contains "0 task(s) x" in the cost bound

  # Backed by: tests/test_cleanrun.py::test_status_reports_the_last_run_and_all_ledger_attempts
  Scenario: Status reports the last run and the ledger totals
    Given a finished run of one task
    When I run cleanrun.py status with that output directory
    Then the exit code is 0
    And stdout contains "state finished"
    And stdout contains "all runs: 1 attempt(s), 1 valid"

  # Backed by: tests/test_cleanrun.py::test_status_survives_a_torn_ledger_and_a_missing_directory
  Scenario: Status tolerates a torn ledger line and reports a missing directory
    Given a finished run whose ledger.jsonl ends with the torn line '{"id": "t0", "event": "att'
    When I run cleanrun.py status with that output directory
    Then stdout contains "1 unreadable line(s)" and stderr has no traceback
    And running cleanrun.py status on a directory that does not exist exits with code 2

  @gap @wip
  # Backed by: @gap
  Scenario: Status exits 1 when the last run did not finish cleanly
    Given an output directory whose summary.json says state "stopped" with a stopped reason
    When I run cleanrun.py status with that output directory
    Then the exit code is 1
    And the first stdout line ends with ", stopped: " followed by that reason
    And the exit code is also 1 when summary.json says "finished" but lists a failed or crashed task

  @gap @wip
  # Backed by: @gap
  Scenario: Status on an output directory without summary.json says so
    Given an existing output directory with no summary.json
    When I run cleanrun.py status with that output directory
    Then stdout contains "no readable summary.json"
    And the exit code is 1

  # Backed by: tests/test_cleanrun.py::test_unicode_line_separators_inside_a_prompt_are_one_line
  Scenario: A Unicode line separator inside a prompt does not split the tasks line
    Given a tasks file with one task whose prompt contains U+0085
    When I run cleanrun.py run
    Then the exit code is 0
    And claude received the prompt unchanged, U+0085 included

  # ---------------------------------------------------------------- explicit routing

  # Backed by: tests/test_cleanrun.py::test_aliases_and_bad_efforts_are_refused_before_any_launch
  Scenario Outline: A model alias, a non-claude model or an unknown effort is refused before any launch
    Given a tasks file with one task
    When I run cleanrun.py run with model "<model>" and effort "<effort>"
    Then the exit code is 2
    And claude is never launched

    Examples:
      | model           | effort  |
      | opus            | xhigh   |
      | sonnet          | high    |
      | gpt-5           | high    |
      | claude-opus-5-5 | extreme |

  # Backed by: tests/test_cleanrun.py::test_a_different_answering_model_invalidates_the_run
  Scenario: A run answered by another model than the routed one is invalid
    Given a task whose claude answer names "claude-haiku-4-5-20251001" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5" and no retries
    Then the exit code is 1
    And the first problem of the failed task contains "model mismatch"
    And summary.json models_observed is {"claude-haiku-4-5-20251001": 1}
    And stdout names "claude-haiku-4-5-20251001"
    And outputs/t0.json does not exist

  @gap @wip
  # Backed by: @gap
  Scenario: An answer naming the routed model plus a second model is also invalid
    Given a task whose claude answer names "claude-opus-5-5" and "claude-haiku-4-5-20251001" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5" and no retries
    Then the exit code is 1
    And the first problem of the failed task contains "model mismatch"
    And outputs/t0.json does not exist

  # Backed by: tests/test_cleanrun.py::test_a_missing_claude_is_a_usage_error_and_nothing_is_charged
  Scenario: A claude executable that cannot be found is a usage error and nothing is charged
    Given a tasks file with two tasks
    When I run cleanrun.py run with "--claude-bin" pointing at a path that does not exist
    Then the exit code is 2
    And stderr contains "cannot find the claude executable"
    And ledger.jsonl does not exist

  # Backed by: tests/test_cleanrun.py::test_the_flag_wins_over_the_environment_variable
  Scenario: The --claude-bin flag wins over CLEANRUN_CLAUDE_BIN
    Given CLEANRUN_CLAUDE_BIN points at a working stub
    When I run cleanrun.py run with "--claude-bin /bin/definitely-not-claude"
    Then the exit code is 2

  @gap @wip
  # Backed by: @gap
  Scenario: A claude that exists but cannot be started stops the run without charging it
    Given a claude command that is found on the path but fails to start when spawned
    When I run cleanrun.py run
    Then the exit code is 2
    And the ledger holds a "not_started" event and no "attempt" event
    And summary.json stopped is "claude could not start"
    And summary.json charged_usd is 0.0

  @gap @wip
  # Backed by: @gap
  Scenario: Changing the model, the effort, the tools or the schema reruns a finished task
    Given a finished run of one task with effort "xhigh"
    When I run cleanrun.py run again with effort "high"
    Then claude is launched a second time for that task
    And the same holds when only the model, only the tools or only the schema differ

  @gap @wip
  # Backed by: @gap
  Scenario: Plan refuses the same bad inputs as run and writes nothing
    Given a tasks file with one task and an output directory that does not exist
    When I run cleanrun.py plan with model "opus"
    Then the exit code is 2
    And the output directory is not created, and no ledger.jsonl or summary.json is written
    And the same holds for a bad schema, a validator that does not import and a malformed tasks file

  # ---------------------------------------------------------------- validating an answer

  # Backed by: tests/test_cleanrun.py::test_each_failure_kind_is_a_failed_task_never_a_saved_output
  Scenario: Each kind of bad answer is a failed task and never a saved output
    Given five tasks whose claude answers are an invalid output, no structured output, an error with exit 1, text that is not JSON, and an error with exit 0
    When I run cleanrun.py run with no retries
    Then the exit code is 1
    And summary.json lists 5 failed tasks
    And the outputs directory holds no .json file

  # Backed by: tests/test_cleanrun.py::test_an_error_names_its_subtype_and_message
  Scenario: A claude error names its subtype and message in the problem
    Given a task whose claude answer is an error with subtype "error_during_execution" and the message "API Error: overloaded"
    When I run cleanrun.py run
    Then the first problem of the failed task contains "error_during_execution"
    And the first problem of the failed task contains "overloaded"

  # Backed by: tests/test_cleanrun.py::test_stderr_reaches_the_problem_text
  Scenario: Text on claude's stderr reaches the problem text
    Given a task whose claude prints "auth failed: token expired" to stderr and exits with 1
    When I run cleanrun.py run
    Then the first problem of the failed task contains "auth failed: token expired"

  # Backed by: tests/test_cleanrun.py::test_retry_turns_a_bad_first_answer_into_a_saved_one
  Scenario: A retry turns a bad first answer into a saved one
    Given a task whose first claude answer is an invalid output and whose second is valid
    When I run cleanrun.py run with "--retries 1"
    Then the exit code is 0
    And the "valid" flags of the ledger attempts are [false, true]

  # Backed by: tests/test_cleanrun.py::test_a_crashing_validator_is_a_problem_not_a_crash
  Scenario: A validator that raises is a failed task, not a crash
    Given a validator whose validate function raises KeyError
    When I run cleanrun.py run
    Then the exit code is 1
    And the first problem of the failed task contains "validator raised KeyError"

  # Backed by: tests/test_cleanrun.py::test_the_validator_sees_the_task_and_its_file_names
  Scenario: The validator is handed the task id and the names of its files
    Given a validator that accepts only the task id "t0" with the file list ["page.txt"]
    And a task "t0" that lists the file "page.txt"
    When I run cleanrun.py run
    Then the exit code is 0

  @gap @wip
  # Backed by: @gap
  Scenario Outline: A timeout, a non-JSON answer or an error answer is retried up to --retries times
    Given a task whose claude <failure> on every attempt
    When I run cleanrun.py run with "--retries 2"
    Then the exit code is 1
    And the ledger holds exactly three attempt records, all with valid false

    Examples:
      | failure                                    |
      | hangs past the timeout                     |
      | prints text that is not JSON               |
      | answers with is_error true and no budget subtype |

  @gap @wip
  # Backed by: @gap
  Scenario: A validator that does not import is a usage error
    Given a validator file that raises at import time
    When I run cleanrun.py run with "--validator" pointing at it
    Then the exit code is 2
    And stderr contains "does not import"
    And no claude process is launched

  # ---------------------------------------------------------------- money

  # Backed by: tests/test_cleanrun.py::test_unknown_cost_is_charged_at_the_per_run_cap
  Scenario: A run with no reported cost is charged at the per-run cap
    Given a task whose claude answer has no total_cost_usd
    When I run cleanrun.py run with "--per-run-usd 1.5"
    Then summary.json unknown_cost_runs is 1
    And summary.json charged_usd is 1.5
    And summary.json observed_cost_usd is 0.0

  # Backed by: tests/test_cleanrun.py::test_a_budget_stop_is_reported_plainly_and_not_retried
  Scenario: A run that hits its per-run budget is reported plainly and not retried
    Given a task whose claude answer is an error with subtype "error_max_budget_usd"
    When I run cleanrun.py run with "--retries 2"
    Then the ledger holds exactly one attempt
    And the first problem of the failed task contains "per-run budget reached"

  # Backed by: tests/test_cleanrun.py::test_a_budget_stop_is_reported_plainly_and_not_retried
  Scenario: Token counts fall back to modelUsage when the top-level usage is zero
    Given a task whose claude answer is an error with subtype "error_max_budget_usd" and a top-level usage of zero
    When I run cleanrun.py run
    Then the attempt's output_tokens is 52 and its cache_write is 1131, summed from modelUsage

  # Backed by: tests/test_cleanrun.py::test_max_usd_stops_new_launches_and_reports_what_did_not_run
  Scenario: --max-usd stops new launches and reports what did not run
    Given six tasks that each cost $0.6
    When I run cleanrun.py run with "--max-usd 1.0" and "--jobs 1"
    Then the exit code is 2
    And summary.json state is "stopped" and its stopped reason contains "--max-usd"
    And summary.json launches is 2
    And summary.json not_run lists 4 tasks

  # Backed by: tests/test_cleanrun.py::test_max_usd_lets_runs_already_in_flight_finish
  Scenario: --max-usd lets attempts already in flight finish
    Given three tasks, the second slow, each costing $0.6
    When I run cleanrun.py run with "--max-usd 0.5" and "--jobs 2"
    Then the exit code is 2
    And outputs/t1.json exists
    And both ledger attempts are valid
    And summary.json not_run lists only "t2"

  @gap @wip
  # Backed by: @gap
  Scenario: Resumed tasks skip both the --max-usd gate and the usage check
    Given a finished run of two tasks
    When I run cleanrun.py run again with a usage-check command that exits 2 and "--max-usd 0.01"
    Then the exit code is 0
    And summary.json resumed is 2 and stopped is null
    And the usage-check command was never executed

  @gap @wip
  # Backed by: @gap
  Scenario: A resumed invocation starts its --max-usd count at zero
    Given a finished run of two tasks that cost $0.6 each
    When I run cleanrun.py run again with "--max-usd 0.5" and a third new task
    Then the third task is launched
    And summary.json charged_usd covers only the third task

  @gap @wip
  # Backed by: @gap
  Scenario: Every attempt is appended to ledger.jsonl with its routing and cost
    Given one task with model "claude-opus-5-5", effort "xhigh" and a reported cost of $0.05
    When I run cleanrun.py run
    Then ledger.jsonl holds one record with event "attempt" and attempt 1
    And that record carries model "claude-opus-5-5", model_observed ["claude-opus-5-5"] and effort "xhigh"
    And that record carries cost_usd 0.05, cost_unknown false and charged_usd 0.05

  @gap @wip
  # Backed by: @gap
  Scenario: A saved output records the task id, run key, model, time and output
    Given one task that ran successfully
    When I read outputs/t0.json
    Then it holds the fields "id", "key", "model", "ts" and "output"
    And "model" equals the routed model id

  # ---------------------------------------------------------------- resume

  # Backed by: tests/test_cleanrun.py::test_finished_tasks_are_skipped_and_changed_ones_rerun
  Scenario: A finished task is skipped, and a changed prompt or system prompt reruns it
    Given a finished run of tasks "a" and "b"
    When I run cleanrun.py run again unchanged
    Then no new claude call is made and summary.json resumed is 2
    When I change the prompt of "b" and run again
    Then exactly one new claude call is made
    When I change the system prompt file and run again
    Then both tasks are launched again

  # Backed by: tests/test_cleanrun.py::test_a_changed_file_reruns_its_task
  Scenario: A changed input file reruns its task
    Given a finished run of one task that lists "page.txt" containing "v1"
    When "page.txt" is changed to contain "v2" and I run again
    Then claude is launched a second time

  # Backed by: tests/test_cleanrun.py::test_a_flat_read_only_tasks_run_key_is_pinned
  Scenario: A flat Read-only task keeps the run key release 3.3.4 gave it
    Given one task with the prompt "first" and the file "page.txt" containing "data", run with --tools Read, model claude-opus-5-5, effort xhigh and the test's fixed system prompt, schema and validator
    When the run finishes and I read outputs/t0.json
    Then "key" equals 276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71, the key release 3.3.4 produced for these inputs, so finished out-dirs keep resuming

  # Backed by: tests/test_cleanrun.py::test_a_tightened_validator_reruns_its_tasks
  Scenario: A changed validator source reruns the finished tasks
    Given a finished run of one task
    When the validator file gets one extra comment line and I run again
    Then claude is launched a second time

  # Backed by: tests/test_cleanrun.py::test_a_saved_output_that_no_longer_validates_is_rerun
  Scenario: A saved output that no longer passes the validator is rerun and the rejection is logged
    Given a finished run of one task whose outputs/t0.json now holds the answer "tampered"
    When I run cleanrun.py run again
    Then claude is launched a second time
    And ledger.jsonl holds an event "resume_rejected"

  # Backed by: tests/test_cleanrun.py::test_a_corrupt_saved_output_is_rerun_not_a_crash
  Scenario: A corrupt saved output is rerun and does not crash plan or run
    Given a finished run of two tasks whose outputs/t0.json holds "[]" and outputs/t1.json holds "null"
    When I run cleanrun.py plan
    Then the exit code is 0
    When I run cleanrun.py run
    Then the exit code is 0
    And claude has been launched four times in total

  # ---------------------------------------------------------------- inputs

  # Backed by: tests/test_cleanrun.py::test_bad_task_files_are_usage_errors
  Scenario Outline: A malformed tasks file is a usage error with no traceback
    Given a tasks file with the defect "<defect>"
    When I run cleanrun.py run
    Then the exit code is 2
    And stderr has no traceback
    And claude is never launched

    Examples:
      | defect                                   |
      | two tasks with the same id               |
      | ids that differ only in case             |
      | an id containing a slash                 |
      | an empty prompt                          |
      | a listed file that does not exist        |
      | a line that is not JSON                  |
      | a file with no tasks                     |

  # Backed by: tests/test_cleanrun.py::test_unreadable_inputs_are_usage_errors_not_tracebacks
  Scenario Outline: An unreadable or out-of-range option is a usage error and starts no run
    Given a tasks file with one task
    When I run cleanrun.py run with the defect "<defect>"
    Then the exit code is 2
    And stderr has no traceback
    And summary.json does not exist in the default output directory (this clause is not checked for the --out-dir row, whose own directory is the file)

    Examples:
      | defect                                      |
      | a system prompt file that is not UTF-8      |
      | a schema path that is a directory           |
      | an --out-dir that is a file                 |
      | --max-usd nan                               |
      | --per-run-usd inf                           |

  @gap @wip
  # Backed by: @gap
  Scenario: A schema that is not a JSON Schema object is refused
    Given a schema file containing {"type": "array"}
    When I run cleanrun.py run
    Then the exit code is 2
    And stderr contains "schema must be a JSON Schema object"

  @gap @wip
  # Backed by: @gap
  Scenario: A schema over 100000 bytes is refused because it travels on the command line
    Given a schema file whose re-serialised JSON (json.dumps with its default separators, UTF-8) is larger than 100000 bytes
    When I run cleanrun.py run
    Then the exit code is 2
    And stderr contains "schema is over 100000 bytes"

  @gap @wip
  # Backed by: @gap
  Scenario Outline: A jobs, retries or timeout value out of range is a usage error
    Given a tasks file with one task
    When I run cleanrun.py run with "<option>"
    Then the exit code is 2
    And stderr contains "--jobs and --timeout must be >= 1 and --retries >= 0"

    Examples:
      | option      |
      | --jobs 0    |
      | --timeout 0 |
      | --retries -1 |

  # Backed by: tests/test_cleanrun.py::test_a_tasks_file_with_a_bom_and_crlf_is_read
  Scenario: A tasks file with a byte order mark and CRLF line ends is read
    Given a tasks file that starts with a UTF-8 BOM and ends its line with CRLF
    When I run cleanrun.py run
    Then the exit code is 0

  # Backed by: tests/test_cleanrun.py::test_two_files_with_the_same_name_are_refused
  Scenario: Two files of one task with the same base name are refused
    Given a task that lists "page.txt" and "x/page.txt"
    When I run cleanrun.py run
    Then the exit code is 2

  # Backed by: tests/test_cleanrun.py::test_a_second_run_on_the_same_out_dir_is_refused_while_the_first_holds_the_lock
  Scenario: A second run on the same output directory is refused while the first holds the lock
    Given a first cleanrun.py run is still working in an output directory
    When I start a second cleanrun.py run on the same directory
    Then the second exits with code 2
    And its stderr contains "another cleanrun"

  # ---------------------------------------------------------------- process groups, signals, crashes

  # Backed by: tests/test_cleanrun.py::test_a_timeout_kills_the_whole_process_group
  Scenario: A timeout kills the whole process group, grandchild included
    Given a task whose claude starts a grandchild process and then hangs
    When I run cleanrun.py run with "--timeout 2" and no retries
    Then the exit code is 1
    And the first problem of the failed task contains "timeout"
    And the grandchild process is no longer alive within 10 seconds

  # Backed by: tests/test_cleanrun.py::test_an_orphan_holding_the_output_open_cannot_stall_the_run
  Scenario: An orphan that holds the output file open cannot stall the run
    Given a task whose claude answers ok but leaves a process in a new session holding its stdout file open
    When I run cleanrun.py run with "--timeout 30"
    Then the exit code is 0
    And the run ends in under 20 seconds
    And outputs/t0.json exists

  # Backed by: tests/test_cleanrun.py::test_ctrl_c
  # Backed by: tests/test_cleanrun.py::test_sigterm
  # Backed by: tests/test_cleanrun.py::test_sighup_from_a_closed_terminal
  Scenario Outline: A stop signal kills every running group, launches nothing new and writes the summary
    Given five hanging tasks and "--jobs 2" with two claude processes running
    When the cleanrun process receives <signal>
    Then the exit code is 130
    And only the two claude calls already running ever existed
    And no grandchild process survives
    And summary.json state is "interrupted", its stopped reason is "interrupted" and not_run lists 5 tasks

    Examples:
      | signal  |
      | SIGINT  |
      | SIGTERM |
      | SIGHUP  |

  @gap @wip
  # Backed by: @gap
  Scenario: SIGQUIT is handled like the other stop signals
    Given five hanging tasks and "--jobs 2" with two claude processes running
    When the cleanrun process receives SIGQUIT
    Then the exit code is 130
    And summary.json state is "interrupted"

  # Backed by: tests/test_cleanrun.py::test_repeated_ctrl_c_while_the_summary_is_written_cannot_deadlock
  Scenario: Repeated Ctrl-C while the summary is being written cannot deadlock
    Given three hanging tasks with "--jobs 2" and the summary writer held for one second
    When SIGINT is sent repeatedly for four seconds
    Then the exit code is 130
    And summary.json state is "interrupted"

  # Backed by: tests/test_cleanrun.py::test_a_hanging_validator_cannot_block_an_interrupt
  Scenario: A hanging validator cannot block an interrupt past the grace period
    Given a validator that sleeps 300 seconds and a grace period of 4 seconds
    When SIGINT arrives once while the validator is running
    Then the exit code is 130 within 30 seconds
    And summary.json state is "interrupted"

  # Backed by: tests/test_cleanrun.py::test_a_second_ctrl_c_leaves_at_once_even_with_a_long_grace
  Scenario: A second Ctrl-C leaves at once even with a long grace period
    Given a validator that sleeps 300 seconds and a grace period of 120 seconds
    When SIGINT arrives twice, one second apart
    Then the exit code is 130 within 15 seconds
    And summary.json state is "interrupted"

  # Backed by: tests/test_cleanrun.py::test_a_crash_inside_a_task_stops_new_launches_and_still_writes_the_summary
  Scenario: A crash inside a task stops new launches and still writes the summary
    Given a validator that calls sys.exit(3) and four tasks with "--jobs 1"
    When I run cleanrun.py run
    Then the exit code is 3
    And summary.json crashed lists 1 task and its stopped reason contains "internal error"
    And summary.json launches is 1
    And summary.json not_run lists 3 tasks

  # ---------------------------------------------------------------- usage check

  @gap @wip
  # Backed by: @gap
  Scenario: Without --usage-check no check command runs
    Given a tasks file with one task
    When I run cleanrun.py run without --usage-check
    Then the exit code is 0
    And no usage-check command was executed, so no shared usage cache or its lock file is created

  # Backed by: tests/test_cleanrun.py::test_room_in_the_window_is_probed_once_for_many_jobs
  Scenario: Room in the window is probed once for many parallel jobs
    Given four tasks and a usage-check command that exits 0 and counts its calls
    When I run cleanrun.py run with that command and "--jobs 4"
    Then the exit code is 0
    And the usage-check command was executed exactly once

  # Backed by: tests/test_cleanrun.py::test_one_reading_is_shared_by_runs_in_other_processes
  Scenario: A reading is shared with another cleanrun process using the same command
    Given a usage-check command that exits 0 and counts its calls
    When a first cleanrun.py run and then a second one on another output directory both use that command
    Then both exit with code 0
    And the usage-check command was executed exactly once in total

  # Backed by: tests/test_cleanrun.py::test_a_shared_reading_expires
  Scenario: A shared reading older than 60 seconds is not reused
    Given a usage-check command that exits 2 and a first run that stops with exit code 2
    And the shared cache entry is aged by 120 seconds
    And the command now exits 0
    When a second cleanrun.py run on another output directory uses the same command
    Then the exit code is 0
    And the usage-check command was executed twice in total

  # Backed by: tests/test_cleanrun.py::test_an_unreadable_window_is_never_shared
  Scenario: An unreadable window is never shared between processes
    Given a usage-check command that exits 1 and counts its calls
    When two cleanrun.py runs on different output directories each use that command
    Then the usage-check command was executed 6 times, 3 per run

  # Backed by: tests/test_cleanrun.py::test_a_full_window_stops_before_any_launch
  Scenario: A full usage window stops the run before any launch
    Given a usage-check command that exits 2 and two tasks
    When I run cleanrun.py run with that command
    Then the exit code is 2
    And summary.json stopped is "usage check: window full"
    And claude is never launched

  # Backed by: tests/test_cleanrun.py::test_an_unreadable_window_is_retried_then_stops_as_unreadable
  Scenario: An unreadable usage window is retried twice and then stops the run as unreadable
    Given a usage-check command that exits 1 and counts its calls
    When I run cleanrun.py run with that command
    Then the exit code is 2
    And summary.json stopped is "usage check: unreadable"
    And the usage-check command was executed 3 times
    And claude is never launched

  # ---------------------------------------------------------------- final report

  @gap @wip
  # Backed by: @gap
  Scenario: Failed tasks are listed after the final summary line and a stop reason is appended to it
    Given a run stopped by "--max-usd" in which one task also failed with four problems
    When I read stdout
    Then the last summary line ends with "; STOPPED: --max-usd" followed by the limit
    And one line "  <id>: <problems joined by '; '>" follows per failed or crashed task, with at most 3 problems each
