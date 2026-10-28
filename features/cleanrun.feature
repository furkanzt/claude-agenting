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

  # Backed by: tests/test_cleanrun.py::test_without_also_models_a_helper_beside_the_routed_model_is_still_a_mismatch
  Scenario: An answer naming the routed model plus a second model is also invalid
    Given a task whose claude answer names "claude-opus-5-5" and "claude-haiku-4-5-20251001" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5", no retries and no --also-models option
    Then the exit code is 1
    And the only problem of the failed task is "model mismatch: answered by ['claude-haiku-4-5-20251001', 'claude-opus-5-5'], routed to claude-opus-5-5"
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

  # ---------------------------------------------------------------- tool permissions

  # Backed by: tests/test_cleanrun.py::test_the_list_is_passed_to_claude_as_its_allowed_tools_flag
  Scenario Outline: --allowed-tools is passed to claude as its allowed-tools flag
    Given a tasks file with one task
    When I run cleanrun.py run with "--tools <tools>" and "--allowed-tools <given>"
    Then the exit code is 0
    And the claude command line carries "--allowed-tools" followed by "<sent>"
    And it still carries "--tools" followed by "<tools>"

    Examples:
      | tools             | given                      | sent                     |
      | WebSearch,WebFetch | WebSearch,WebFetch        | WebSearch,WebFetch       |
      | Bash,Read         | Bash(git status:*), Read   | Bash(git status:*),Read  |
      | Bash              | Bash(git log --format=%h,%s:*) | Bash(git log --format=%h,%s:*) |
      | Read Glob         | Glob                       | Glob                     |

  # Backed by: tests/test_cleanrun.py::test_without_the_option_claude_gets_no_allowed_tools_flag
  Scenario: Without --allowed-tools claude gets no allowed-tools flag
    Given a tasks file with two tasks
    When I run cleanrun.py run with "--tools Read" and no --allowed-tools option
    Then the exit code is 0
    And no claude command line carries "--allowed-tools" or "--allowedTools"
    And each claude command line carries "--tools" followed by "Read"

  # Backed by: tests/test_cleanrun.py::test_a_name_that_tools_does_not_list_is_refused_by_run_and_by_plan
  Scenario Outline: An --allowed-tools entry that --tools does not list is a usage error for run and plan
    Given a tasks file with one task and an output directory that does not exist
    When I run cleanrun.py <command> with "--tools <tools>" and "--allowed-tools <allowed>"
    Then the exit code is 2
    And stderr mentions "--allowed-tools" and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | command | tools     | allowed              |
      | run     | Read      | WebFetch             |
      | plan    | Read      | WebFetch             |
      | run     |           | Read                 |
      | plan    | Read      | Bash(git status:*)   |
      | run     | WebSearch | WebSearch,WebFetch   |
      | plan    | Bash      | Bash(git status      |
      | run     | (git status) | (git status)      |
      | run     | Bash      | Bash(git (x),Bash,(y)) |
      | plan    | Bash      | Bash((a),WebFetch,(b)) |
      | run     | Bash      | Bash(echo $(date) *) |
      | plan    | Bash,Read | Bash(a)Read          |
      | plan    | Bash      | Bash(a (b)           |
      | run     | Read,Glob | Read<TAB>Glob        |
      | plan    | Read<TAB>Glob | Read<TAB>Glob    |
      | run     | Read)     | Read)                |
      | plan    | Read,WebFetch,!WebFetch | WebFetch |
      | run     | Read,! WebFetch | Read,WebFetch  |
      | plan    | default   | WebFetch             |

    # Claude cuts a list with one inside/outside flag, so a nested "(" or text after an entry's ")"
    # would be several grants there, among them a whole-tool Bash or a name --tools never listed.
    # Refusing them keeps the checked list identical to the granted one. <TAB> stands for a tab character.

  # Backed by: tests/test_cleanrun.py::test_the_list_enters_the_run_key_only_when_it_is_given
  Scenario: A task run with --allowed-tools gets a different run key than the same task without it
    Given the pinned scenario's task (prompt "first", file "page.txt" containing "data") run twice in separate output directories with "--tools Read", once without and once with "--allowed-tools Read"
    When I read outputs/t0.json of both
    Then the "key" of the run without the option is 276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71, the one pinned by the scenario "A flat Read-only task keeps the run key release 3.3.4 gave it"
    And the "key" of the run with the option differs from it

  # Backed by: tests/test_cleanrun.py::test_changing_the_list_reruns_a_finished_task
  Scenario: Changing --allowed-tools reruns a finished task
    Given a finished run of one task with "--tools Read,Glob" and "--allowed-tools Read"
    When I run cleanrun.py run again with the same arguments
    Then no new claude call is made
    When I run again with "--allowed-tools Read,Glob"
    Then claude is launched a second time for that task
    When I run again with "--allowed-tools Glob,Read,Read", the same grant reordered and repeated
    Then no new claude call is made
    When I run again without --allowed-tools
    Then claude is launched a third time for that task

  # ---------------------------------------------------------------- helper models (--also-models)

  # Backed by: tests/test_cleanrun.py::test_a_helper_on_the_list_is_accepted_and_the_summary_lists_both_models
  Scenario: A helper model on the --also-models list is accepted and the summary lists both models
    Given a task whose claude answer names "claude-opus-5-5" and "claude-haiku-4-5-20251001" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5" and "--also-models claude-haiku-4-5-20251001"
    Then the exit code is 0
    And summary.json models_observed is {"claude-opus-5-5": 1, "claude-haiku-4-5-20251001": 1}
    And stdout names "claude-haiku-4-5-20251001"
    And the attempt in ledger.jsonl has model_observed ["claude-haiku-4-5-20251001", "claude-opus-5-5"]
    And outputs/t0.json exists
    And the claude command line carries no "--also-models"

  # Backed by: tests/test_cleanrun.py::test_a_model_not_on_the_list_is_rejected_and_named
  Scenario: A second model that --also-models does not list is a mismatch that names it
    Given a task whose claude answer names "claude-opus-5-5" and "claude-sonnet-4-5-20250929" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5", no retries and "--also-models claude-haiku-4-5-20251001"
    Then the exit code is 1
    And the only problem of the failed task starts with "model mismatch: answered by ['claude-opus-5-5', 'claude-sonnet-4-5-20250929'], routed to claude-opus-5-5"
    And it contains "not on --also-models: claude-sonnet-4-5-20250929"
    And outputs/t0.json does not exist

  # Backed by: tests/test_cleanrun.py::test_the_routed_model_missing_is_rejected_even_when_a_listed_helper_answered
  Scenario: An answer without the routed model is a mismatch even when only a listed helper answered
    Given a task whose claude answer names only "claude-haiku-4-5-20251001" in modelUsage
    When I run cleanrun.py run with model "claude-opus-5-5", no retries and "--also-models claude-haiku-4-5-20251001"
    Then the exit code is 1
    And the only problem of the failed task starts with "model mismatch: answered by ['claude-haiku-4-5-20251001'], routed to claude-opus-5-5"
    And it contains "claude-opus-5-5 is not among them"
    And outputs/t0.json does not exist

  # Backed by: tests/test_cleanrun.py::test_an_alias_in_also_models_is_refused_by_run_and_by_plan
  Scenario Outline: An alias or a non-claude id in --also-models is a usage error for run and plan
    Given a tasks file with one task and an output directory that does not exist
    When I run cleanrun.py <command> with "--also-models <given>"
    Then the exit code is 2
    And stderr contains "--also-models must be a full model id" and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | command | given                              |
      | run     | haiku                              |
      | plan    | haiku                              |
      | run     | Sonnet                             |
      | plan    | claude-haiku-4-5-20251001,opus     |
      | run     | gpt-5                              |
      | plan    | claude-haiku-4-5-20251001, default |

  # Backed by: tests/test_cleanrun.py::test_a_space_separated_list_or_the_routed_model_in_another_case_is_refused_by_run_and_by_plan
  Scenario Outline: A space inside an --also-models id or the routed model in another case is a usage error for run and plan
    Given a tasks file with one task and an output directory that does not exist
    When I run cleanrun.py <command> with model "claude-opus-5-5" and "--also-models <given>"
    Then the exit code is 2
    And stderr contains "<message>" and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | command | given                                                                            | message                                         |
      | run     | claude-haiku-4-5-20251001 claude-sonnet-4-5-20250929                             | a model id has no space                         |
      | plan    | claude-haiku-4-5-20251001 claude-sonnet-4-5-20250929                             | a model id has no space                         |
      | run     | claude-sonnet-4-5-20250929, claude-haiku-4-5-20251001 claude-sonnet-4-5-20250929 | a model id has no space                         |
      | plan    | claude-sonnet-4-5-20250929, claude-haiku-4-5-20251001 claude-sonnet-4-5-20250929 | a model id has no space                         |
      | run     | claude-OPUS-5-5                                                                  | names --model 'claude-opus-5-5' in another case |
      | plan    | claude-OPUS-5-5                                                                  | names --model 'claude-opus-5-5' in another case |
      | run     | claude-haiku-4-5-20251001,claude-Opus-5-5                                        | names --model 'claude-opus-5-5' in another case |
      | plan    | claude-haiku-4-5-20251001,claude-Opus-5-5                                        | names --model 'claude-opus-5-5' in another case |

  # Backed by: tests/test_cleanrun.py::test_an_id_a_run_could_never_report_is_refused_by_run_and_by_plan
  Scenario Outline: An --also-models id that claude could never report is a usage error for run and plan
    Given a tasks file with one task and an output directory that does not exist
    When I run cleanrun.py <command> with "--also-models <given>"
    Then the exit code is 2
    And stderr contains "written as claude reports them" and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | given                                   | what it is               |
      | claude-haiku-4-5-20251001;claude-sonnet-4-5-20250929 | a ';' list   |
      | claude-haiku                            | a partial id             |
      | claude-                                 | a bare prefix            |
      | claude-Haiku-4-5-20251001               | another case             |
      | claude-<FULLWIDTH h>aiku-4-5-20251001   | a fullwidth look-alike   |
      | claude-haiku-4-5-20251001<ZERO WIDTH>   | a zero-width character   |
      | claude-haiku-4-5<SOFT HYPHEN>-20251001  | a soft hyphen            |

    # <FULLWIDTH h>, <ZERO WIDTH> and <SOFT HYPHEN> stand for U+FF48, U+200B and U+00AD, each in both run and plan.

  # Backed by: tests/test_cleanrun.py::test_the_weaker_check_is_recorded_where_the_result_is_read
  Scenario: The weaker model check is recorded where the result is read
    Given a task answered by "claude-opus-5-5" and "claude-haiku-4-5-20251001"
    When I run cleanrun.py plan and then run with "--also-models claude-haiku-4-5-20251001"
    Then the plan line says "also models claude-haiku-4-5-20251001 (weaker model check)"
    And the run's first line says "(weaker model check)"
    And summary.json holds "also_models" as the list with that id
    And outputs/t0.json holds "also_models" as the same list

  # Backed by: tests/test_cleanrun.py::test_a_default_run_mentions_neither_the_weaker_check_nor_a_grant
  Scenario: A default run mentions neither the weaker check nor a grant, and a grant shows in the plan
    Given a tasks file with one task
    When I run cleanrun.py plan and then run with no --also-models and no --allowed-tools
    Then neither the plan output nor summary.json nor outputs/t0.json mentions "also" or "allowed"
    When I run cleanrun.py plan with "--tools Read" and "--allowed-tools Read"
    Then the plan line says "allowed 'Read'"

  # Backed by: tests/test_cleanrun.py::test_also_models_enter_the_run_key_only_when_they_add_a_model
  Scenario: --also-models changes the run key only when it adds a model beside the routed one
    Given the pinned scenario's task (prompt "first", file "page.txt" containing "data") run three times in separate output directories with "--tools Read": without --also-models, with "--also-models claude-haiku-4-5-20251001" and with "--also-models claude-opus-5-5"
    When I read outputs/t0.json of each
    Then the "key" of the run without the option is 276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71, the one pinned by the scenario "A flat Read-only task keeps the run key release 3.3.4 gave it"
    And the "key" of the run that lists only the routed model equals it too
    And the "key" of the run that lists the helper differs from it

  # Backed by: tests/test_cleanrun.py::test_a_changed_also_models_set_reruns_a_finished_task_and_a_reordered_one_resumes
  Scenario: A changed --also-models set reruns a finished task and the same set reordered resumes it
    Given a finished run of one task, answered by "claude-opus-5-5" and "claude-haiku-4-5-20251001", with "--also-models claude-haiku-4-5-20251001"
    When I run cleanrun.py run again with the same arguments
    Then no new claude call is made
    When I run again with "--also-models claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929"
    Then claude is launched a second time for that task
    When I run again with "--also-models claude-sonnet-4-5-20250929,claude-haiku-4-5-20251001,claude-haiku-4-5-20251001", the same set reordered and repeated
    Then no new claude call is made
    When I run again with "--also-models claude-sonnet-4-5-20250929,claude-haiku-4-5-20251001,claude-opus-5-5", which adds only the routed model
    Then no new claude call is made

  # ---------------------------------------------------------------- hashing the input files

  # Backed by: tests/test_cleanrun.py::test_the_digest_equals_an_independent_sha256
  Scenario: A file's digest in the run key is its sha256
    Given files of 0 bytes, 1 byte, one byte under a megabyte, exactly a megabyte, one over and a little over two
    When cleanrun hashes each for the run key
    Then each digest equals the sha256 that Python's hashlib computes for the same bytes

  # Backed by: tests/test_cleanrun.py::test_a_large_file_is_hashed_in_chunks_not_read_whole
  Scenario: A large file is hashed in chunks and not read whole
    Given a file of 16 megabytes
    When cleanrun hashes it for the run key
    Then the digest is that file's sha256
    And the memory allocated while hashing stays under 4 megabytes

  # Backed by: tests/test_cleanrun.py::test_a_file_shared_by_several_tasks_resumes_and_reruns_them_all_when_it_changes
  Scenario: A shared input file resumes its tasks and a change to it reruns all of them
    Given three tasks that list one file, finished
    When I run again with the file unchanged
    Then no new claude call is made
    When I run again after the file's content changed
    Then claude is launched again for all three tasks

  # Backed by: tests/test_cleanrun.py::test_a_rewrite_with_the_mtime_put_back_during_a_run_is_seen_when_the_task_is_picked_up
  Scenario: A rewrite with the mtime put back during a run is seen when the task is picked up
    Given a finished task whose input file is rewritten in place at the same size, with its mtime put back, while another task holds the only worker
    When the held-up task is picked up
    Then claude is launched for it again, with the new bytes in its kit
    And it is not resumed from the output made from the old bytes

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

  # ---------------------------------------------------------------- kit paths (object entries in files)

  # Backed by: tests/test_cleanrun.py::test_an_object_entry_lands_at_its_kit_path_and_claude_sees_it_there
  Scenario: An object entry is copied to its kit path and claude sees it there
    Given a task whose files are {"path": "src/report.bin", "as": "sub/dir/name.pdf"} and the string entry "page.txt"
    When I run cleanrun.py run
    Then the exit code is 0
    And the working tree claude ran in holds exactly "sub/dir/name.pdf" with the bytes of src/report.bin and "page.txt" with the bytes of page.txt
    And its top level lists only "page.txt" and "sub"

  # Backed by: tests/test_cleanrun.py::test_the_validator_sees_the_kit_path_of_an_object_entry
  Scenario: The validator is handed the kit path of an object entry and the base name of a string entry
    Given a validator that accepts only the file list ["sub/name.md", "page.txt"]
    And a task whose files are {"path": "other.txt", "as": "sub/name.md"} and "page.txt"
    When I run cleanrun.py run
    Then the exit code is 0

  # Backed by: tests/test_cleanrun.py::test_two_files_with_the_same_base_name_are_accepted_at_different_kit_paths
  Scenario: Two files with the same base name are accepted when their kit paths differ
    Given a task whose files are {"path": "page.txt", "as": "a/page.txt"} and {"path": "x/page.txt", "as": "b/page.txt"}
    And a task whose files are the string entry "page.txt" and {"path": "x/page.txt", "as": "x/page.txt"}
    When I run cleanrun.py run
    Then the exit code is 0
    And the first task's working tree holds "a/page.txt" and "b/page.txt", each with the bytes of its own source
    And the second task's working tree holds "page.txt" and "x/page.txt", each with the bytes of its own source
    # Two string entries with one base name are still refused: see "Two files of one task with the same base name are refused".

  # Backed by: tests/test_cleanrun.py::test_an_invalid_kit_path_is_refused_by_run_and_by_plan
  Scenario Outline: An invalid "as" is a usage error for run and plan and writes nothing
    Given a task "t0" whose files are {"path": "page.txt", "as": <as>}
    When I run cleanrun.py run, and separately cleanrun.py plan
    Then the exit code is 2
    And stderr names "t0", the entry as JSON and "<defect>", and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | as                                   | defect             |
      | ""                                   | non-empty string   |
      | 5                                    | non-empty string   |
      | null                                 | non-empty string   |
      | "/etc/page.txt"                      | absolute           |
      | "../page.txt"                        | '..' segment       |
      | "sub/../page.txt"                    | '..' segment       |
      | "./page.txt"                         | '.'                |
      | "a/./page.txt"                       | '.'                |
      | "."                                  | '.'                |
      | "a//page.txt"                        | empty              |
      | "a/"                                 | empty              |
      | "a<BACKSLASH>page.txt"               | backslash          |
      | "a<NUL>page.txt"                     | NUL                |
      | "d/" repeated 256 times, then "x"    | longer than 512 bytes |
      | three segments of 127 s-cedillas     | longer than 512 bytes |
      | "d/" then 256 x characters           | 255 bytes          |
      | 128 s-cedillas (256 bytes in UTF-8)  | 255 bytes          |
      | "x" then U+FFFF                      | unassigned         |
      | "d/" then U+10FFFF                   | unassigned         |
      | "x/..namedfork/rsrc"                 | ..namedfork        |
      | "..NamedFork"                        | ..namedfork        |

    # <BACKSLASH> and <NUL> stand for a backslash and a NUL character.

  # Backed by: tests/test_cleanrun.py::test_a_lone_surrogate_in_as_is_a_usage_error_not_a_traceback
  Scenario: A lone surrogate in "as" is a usage error for run and plan, not a traceback
    Given a task "t0" whose tasks line holds the JSON escape \ud800 as its "as", which is legal JSON but no file name
    When I run cleanrun.py run, and separately cleanrun.py plan
    Then the exit code is 2
    And stderr mentions "lone surrogate" and has no traceback
    And the output directory is not created
    And claude is never launched

  # Backed by: tests/test_cleanrun.py::test_a_kit_that_cannot_be_built_fails_its_task_and_not_the_fan_out
  Scenario: A kit that cannot be built fails its task and the other tasks still run
    Given two tasks, the first with an object entry whose copy fails at run time
    When I run cleanrun.py run
    Then the exit code is 1, not an internal-error stop
    And the summary lists only the first task as failed, with "could not build the task's kit"
    And claude is launched once, for the second task

  # Backed by: tests/test_cleanrun.py::test_a_malformed_object_entry_is_refused_by_run_and_by_plan
  Scenario Outline: A malformed object entry is a usage error for run and plan and writes nothing
    Given a task "t0" whose files hold the entry <entry>
    When I run cleanrun.py run, and separately cleanrun.py plan
    Then the exit code is 2
    And stderr names "t0" and "<defect>", and has no traceback
    And the output directory is not created
    And claude is never launched

    Examples:
      | entry                                              | defect                      |
      | {"path": "page.txt"}                               | exactly a non-empty "path"  |
      | {"as": "x.txt"}                                    | exactly a non-empty "path"  |
      | {"path": "", "as": "x.txt"}                        | exactly a non-empty "path"  |
      | {"path": 5, "as": "x.txt"}                         | exactly a non-empty "path"  |
      | {"path": "page.txt", "as": "x.txt", "mode": "ro"}  | exactly a non-empty "path"  |
      | {"path": "missing.txt", "as": "x.txt"}             | no such file missing.txt    |

  # Backed by: tests/test_cleanrun.py::test_a_traversal_in_as_creates_nothing_outside_the_kit
  Scenario: A traversal in "as" is refused and creates nothing outside the kit
    Given TMPDIR points into the test's own directory, so the kit would be made there
    And a task whose files are {"path": "page.txt", "as": ...} with "as" in turn each of "../escape-1.txt", "../../escape-2.txt", "../../../escape-3.txt", "sub/../../escape-4.txt" and an absolute path into the test's directory
    When I run cleanrun.py run, and separately cleanrun.py plan, for each attempt
    Then each exit code is 2 and claude is never launched
    And every path in the test's directory and its bytes are what they were before, TMPDIR is still empty
    And no escape file exists in the test directory's parent or grandparent

  # Backed by: tests/test_cleanrun.py::test_kit_paths_that_are_equal_ignoring_case_are_refused
  Scenario Outline: Two entries on one kit path, ignoring case, are refused when either is an object entry
    Given a task "t0" whose files are <first> and <second>
    When I run cleanrun.py run, and separately cleanrun.py plan
    Then the exit code is 2
    And stderr names "t0", the second entry as JSON and "same kit path"
    And the output directory is not created

    Examples:
      | first                                       | second                                       |
      | {"path": "page.txt", "as": "d/page.txt"}    | {"path": "other.txt", "as": "d/page.txt"}    |
      | {"path": "page.txt", "as": "Docs/Page.txt"} | {"path": "other.txt", "as": "docs/page.txt"} |
      | "page.txt"                                  | {"path": "other.txt", "as": "page.txt"}      |
      | {"path": "other.txt", "as": "PAGE.txt"}     | "page.txt"                                   |
      | {"path": "page.txt", "as": "<NFC s-cedilla>.md"} | {"path": "other.txt", "as": "<NFD s-cedilla>.md"} |
      | {"path": "page.txt", "as": "<U+0390>"}      | {"path": "other.txt", "as": "<U+03AA U+0301>"} |

    # A macOS disk treats a composed and a decomposed s-cedilla (U+015F, s U+0327) as one name, so they collide.
    # It also treats U+0390 and U+03AA U+0301 as one name, which only the canonical caseless match
    # (NFD, casefold, NFD) sees: casefolding after NFC alone leaves them apart.

  # Backed by: tests/test_cleanrun.py::test_a_file_where_another_entry_needs_a_directory_is_refused
  Scenario Outline: A file where another entry needs a directory is refused
    Given a task "t0" whose files are <first> and <second>
    When I run cleanrun.py run, and separately cleanrun.py plan
    Then the exit code is 2
    And stderr names "t0", the second entry as JSON and "directory"
    And the output directory is not created

    Examples:
      | first                                        | second                                          |
      | {"path": "page.txt", "as": "a"}              | {"path": "other.txt", "as": "a/b.txt"}          |
      | {"path": "other.txt", "as": "a/b.txt"}       | {"path": "page.txt", "as": "a"}                 |
      | {"path": "other.txt", "as": "a/b/c.txt"}     | {"path": "page.txt", "as": "a/b"}               |
      | "page.txt"                                   | {"path": "other.txt", "as": "page.txt/in.txt"}  |
      | {"path": "other.txt", "as": "page.txt/in.txt"} | "page.txt"                                    |
      | {"path": "page.txt", "as": "A"}              | {"path": "other.txt", "as": "a/b.txt"}          |
      | {"path": "page.txt", "as": "<U+0390>"}       | {"path": "other.txt", "as": "<U+03AA U+0301>/b.txt"} |
      | {"path": "other.txt", "as": "<U+03AA U+0301>/b.txt"} | {"path": "page.txt", "as": "<U+0390>"}  |

  # Backed by: tests/test_cleanrun.py::test_an_object_entry_with_no_directory_keys_like_the_string_entry
  Scenario: An object entry with no directory part keys exactly like the string entry of the same name and bytes
    Given the pinned scenario's task (prompt "first", page.txt containing "data", --tools Read)
    And the same task with the entry {"path": "src/page-v1.txt", "as": "page.txt"}, whose source also contains "data"
    When each runs in its own output directory and I read outputs/t0.json
    Then both "key"s equal 276e916802a89618a91fb043338e79ee870da432a7fb3c737b963cb2b8ef8e71, the one pinned by the scenario "A flat Read-only task keeps the run key release 3.3.4 gave it"

  # Backed by: tests/test_cleanrun.py::test_the_kit_path_of_an_object_entry_is_part_of_the_run_key
  Scenario: Moving an object entry to another kit path changes its run key and reruns it
    Given the pinned scenario's task with the entry {"path": "page.txt", "as": "docs/page.txt"}, and again with "as" "other/page.txt"
    When each runs in its own output directory
    Then the two keys differ, and neither equals the pinned key
    When a finished run with "docs/page.txt" is run again unchanged
    Then no new claude call is made
    When it is run again with "other/page.txt"
    Then claude is launched again for that task

  # Backed by: tests/test_cleanrun.py::test_a_changed_file_under_an_object_entry_reruns_its_task
  Scenario: A changed file under an object entry reruns its task
    Given a finished run of one task with the entry {"path": "page.txt", "as": "in/page.txt"}
    When I run cleanrun.py run again unchanged
    Then no new claude call is made
    When page.txt is changed and I run again
    Then claude is launched a second time

  # Backed by: tests/test_cleanrun.py::test_the_copy_refuses_a_destination_outside_the_kit
  Scenario: The copy refuses a destination outside the kit even if a kit path got past the load checks
    Given a kit directory
    When cleanrun's place() is asked for "../escape.txt", "a/../../escape.txt", an absolute path, "" or "."
    Then each raises RuntimeError and no file or directory is created anywhere in the test's directory
    And place() for "a/b/c.txt" returns that path under the resolved kit and creates "a/b" inside it
    And place() for "a/b", now a directory in the kit, raises RuntimeError

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
