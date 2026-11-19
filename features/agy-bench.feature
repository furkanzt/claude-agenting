Feature: The Antigravity eval bench runs the eval tasks through agy in a guarded, logged run, keeps its records apart from the Claude instrument, and stops at the meter stop lines

  # ---------------------------------------------------------------- the guard hook

  # Backed by: tests/test_agy_bench.py::test_no_policy_denies_every_tool
  Scenario: A run with no policy file may use no tool
    Given the guard hook is installed above a run directory that has no policy file
    When the agent asks to read a file inside the run directory
    Then the hook answers deny

  # Backed by: tests/test_agy_bench.py::test_tool_outside_policy_is_denied
  Scenario: A tool the run's policy does not list is denied
    Given a policy that allows read_file and run_command
    When the agent asks for manage_task
    Then the hook answers deny
    And with an empty policy even read_file is denied

  # Backed by: tests/test_agy_bench.py::test_read_file_inside_cwd_allowed_outside_denied
  Scenario: read_file is allowed inside the run directory and denied outside it
    Given a policy that allows read_file
    When the agent reads a file under the run directory
    Then the hook answers allow
    And reading a file one level above, a home path or a path with ".." is denied

  # Backed by: tests/test_agy_bench.py::test_read_only_commands_inside_cwd_are_allowed
  Scenario: Read-only shell commands that stay in the run directory are allowed
    Given a policy that allows run_command
    When the agent runs find, grep piped to wc, ls and wc joined by &&, cat of a file inside, or find piped to sort and uniq
    Then the hook answers allow for each

  # Backed by: tests/test_agy_bench.py::test_unsafe_commands_are_denied
  Scenario: Shell commands that could leave the run directory, write, or run anything else are denied
    Given a policy that allows run_command
    When the agent runs a command with a parent path, an absolute path outside, a variable, a redirection, a network tool, find -exec, a newline, an unknown operator, an interpreter, an environment assignment, a backtick, a home path, sed -i or a search of /
    Then the hook answers deny for each

  # Backed by: tests/test_agy_bench.py::test_main_logs_every_event_and_answers_json
  Scenario: The hook logs every event per conversation and always prints one JSON object
    Given the guard hook installed under a work directory
    When it receives a SessionStart and then a PreToolUse that reads /etc/passwd
    Then it prints {} for the first and a deny decision for the second
    And hooklogs/<conversation id>.jsonl holds both events with the model name and the decision

  # ---------------------------------------------------------------- setup, meters, plan

  # Backed by: tests/test_agy_bench.py::test_setup_installs_agent_and_hook_above_the_run_dirs
  Scenario: Setup installs the eval agent and the guard hook one level above the run directories
    Given an evals root with the agy bench templates
    When agy_bench setup runs
    Then private/work/.agents holds the eval-runner agent whose body is the harness runner system prompt
    And the guard hook is copied unchanged and registered for SessionStart, Stop and every PreToolUse

  # Backed by: tests/test_agy_bench.py::test_meters_reads_the_three_pools
  Scenario: The meters command reads the Claude, Gemini and Argon pools from agy -p /usage
    Given agy reports Claude 81% weekly and 64% five-hour, Gemini 55% and 90%, Argon 77% weekly
    When agy_bench meters --json runs
    Then it prints those numbers keyed by pool

  # Backed by: tests/test_agy_bench.py::test_unreadable_meters_are_an_error
  Scenario: Meters that cannot be read are an error
    Given agy -p /usage prints something that is not the meter table
    When agy_bench meters runs
    Then it exits with status 2

  # Backed by: tests/test_agy_bench.py::test_stage_one_is_every_screening_task_times_cells_times_repeats
  Scenario: Stage 1 plans every screening task for every stage cell, with the Claude pool at its own repeat count
    Given three screening tasks, one Gemini cell with 2 repeats and one Claude cell with 1 repeat
    When agy_bench plan --stage 1 runs
    Then it lists the nine runs, each with its own run id

  # Backed by: tests/test_agy_bench.py::test_run_ids_differ_from_the_claude_instrument
  Scenario: An agy run id never equals a Claude instrument run id
    Given the Claude instrument's run ids for the same task
    When the agy stage 1 plan is computed
    Then no run id appears in both

  # Backed by: tests/test_agy_bench.py::test_unknown_stage_is_an_error
  Scenario: An unknown stage is an error
    When agy_bench plan --stage 9 runs
    Then it exits with status 2

  # ---------------------------------------------------------------- runs

  # Backed by: tests/test_agy_bench.py::test_a_full_stage_records_valid_runs_and_code_scores
  Scenario: A full stage records each run's tokens, version and meters, keeps the answer privately and code-grades it
    Given the stub agy answers every task correctly
    When agy_bench run --stage 1 runs
    Then results/agy-runs.jsonl holds nine valid runs with the model id, the agy version, the token counts and the meters read before the run
    And each answer is stored under private/agy-answers
    And every run of a code-graded task has a passing line in results/agy-scores.jsonl

  # Backed by: tests/test_agy_bench.py::test_the_claude_instrument_files_are_never_written
  Scenario: The bench never writes the Claude instrument's records
    When a full agy stage runs
    Then results/runs.jsonl, results/scores.jsonl and private/answers do not exist

  # Backed by: tests/test_agy_bench.py::test_the_run_dir_holds_only_the_material_and_is_removed
  Scenario: A run directory holds only the task material and is removed with its policy afterwards
    When a full agy stage runs
    Then agy saw only data.txt in every run directory
    And no run directory and no policy file is left

  # Backed by: tests/test_agy_bench.py::test_the_command_line_selects_agent_model_and_settings
  Scenario: The agy command line selects the eval agent, the cell's model, the session settings and JSON output
    When one agy run starts
    Then its arguments name the eval-runner agent, the cell's model id, settings that forbid access outside the workspace, JSON output and the prompt attached to -p

  # Backed by: tests/test_agy_bench.py::test_a_finished_plan_runs_nothing_again
  Scenario: A finished stage plans nothing and runs nothing again
    Given a stage that ran to the end
    When the plan is computed and the stage is run again
    Then the plan is empty and agy is not called

  # Backed by: tests/test_agy_bench.py::test_max_runs_bounds_the_invocation
  Scenario: --max-runs bounds one invocation
    When agy_bench run --stage 1 --max-runs 2 runs
    Then agy is called exactly twice

  # Backed by: tests/test_agy_bench.py::test_denied_tool_calls_are_counted_and_the_run_stays_valid
  Scenario: A denied tool call is counted and does not invalidate the run
    Given the agent tries to cat a file above its run directory
    When the run ends with an answer
    Then the run is valid with 1 tool call and 1 denied tool call

  # Backed by: tests/test_agy_bench.py::test_wrong_model_in_the_hook_log
  Scenario: A hook log that names another model makes the run invalid
    When the hook log's model name differs from the requested model
    Then the run is invalid with reason model_mismatch, and no answer or score is stored

  # Backed by: tests/test_agy_bench.py::test_a_helper_conversation
  Scenario: A second conversation in the run directory makes the run invalid
    When a helper conversation starts in the run directory
    Then the run is invalid with reason helper_spawned

  # Backed by: tests/test_agy_bench.py::test_a_foreign_workspace
  Scenario: A session whose workspace is not the run directory makes the run invalid
    When the session's workspace paths name another directory
    Then the run is invalid with reason workspace_mismatch

  # Backed by: tests/test_agy_bench.py::test_no_hook_log
  Scenario: A run with no hook log is invalid
    When the run leaves no hook log for its conversation
    Then the run is invalid with reason no_hook_log

  # Backed by: tests/test_agy_bench.py::test_status_error
  Scenario: A run that ends with a non-quota error is invalid
    When agy reports status ERROR without a quota message
    Then the run is invalid with reason status_error

  # Backed by: tests/test_agy_bench.py::test_empty_response
  Scenario: A run with an empty response is invalid
    When agy reports SUCCESS with an empty response
    Then the run is invalid with reason no_output

  # Backed by: tests/test_agy_bench.py::test_output_that_is_not_json
  Scenario: Output that is not JSON makes the run invalid
    When agy prints text that is not JSON
    Then the run is invalid with reason json_parse

  # Backed by: tests/test_agy_bench.py::test_a_hung_run_is_killed
  Scenario: A run that outlives the print timeout plus the grace is killed
    Given a print timeout of 1 second and a grace of 1 second
    When agy hangs
    Then the run is killed and recorded invalid with reason timeout

  # ---------------------------------------------------------------- stop lines

  # Backed by: tests/test_agy_bench.py::test_a_quota_error_stops_that_pool_only
  Scenario: A quota error stops the runs of that pool and the others go on
    Given the Claude model's runs end with a quota error
    When agy_bench run --stage 1 runs
    Then one Claude run is recorded invalid with reason quota and no other Claude run starts
    And all six Gemini runs are valid, and the command exits with status 3

  # Backed by: tests/test_agy_bench.py::test_a_weekly_meter_under_its_stop_line_starts_no_run_in_that_pool
  Scenario: A weekly meter under its stop line starts no run in that pool
    Given the Claude weekly meter reads 65% and its stop line is 70%
    When agy_bench run --stage 1 runs
    Then no Claude run starts, all six Gemini runs do, the output names the stop line and the command exits with status 3

  # Backed by: tests/test_agy_bench.py::test_unreadable_meters_start_no_run
  Scenario: Unreadable meters start no run
    Given agy -p /usage cannot be read
    When agy_bench run --stage 1 runs
    Then agy is never called for a task and the command exits with status 2

  # Backed by: tests/test_agy_bench.py::test_a_held_lock_is_an_error
  Scenario: A second bench run while one holds the lock is an error
    Given another process holds results/.agy-bench.lock
    When agy_bench run --stage 1 runs
    Then it exits with status 2 without calling agy

  # ---------------------------------------------------------------- judge and report

  # Backed by: tests/test_agy_bench.py::test_judge_scores_the_judge_task_runs_into_the_agy_scores_only
  Scenario: The judge grades the agy runs of judge-graded tasks with the pinned judge, once
    Given a finished stage with three valid runs of a judge-graded task
    When agy_bench judge runs
    Then results/agy-scores.jsonl holds two judge passes per run from the pinned judge model
    And results/scores.jsonl is not created
    And a second judge invocation calls no judge

  # Backed by: tests/test_agy_bench.py::test_report_counts_passes_and_tokens_per_task_and_cell
  Scenario: The report gives passes, scores and median tokens per task and cell, and the meters per pool
    Given a finished and judged stage
    When agy_bench report --stage 1 --json runs
    Then each task and cell has its valid, scored and passed counts, its mean score and its median tokens
    And each pool has the weekly meter read before its first and its last run
