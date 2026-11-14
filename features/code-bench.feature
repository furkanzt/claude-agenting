Feature: The code bench runs test suites in a sandbox, installs the coding tasks, runs the two model steps and keeps its public record free of text

  evals/probes/code_bench.py is the tool of evals/results/PREREGISTERED-2026-11-14-coding.md: the sandboxed test
  runner and its fixed result words, the self-test, trees and overlays, the task records, `install`, the model
  steps (`write-tests`, `fix-suites`, `code`, `cross`), `plan`, `status`, the spend stop and the two record files.
  The runner tests make real sandboxed runs of pytest and node --test on tiny projects in a temp folder; vitest is
  checked on hand-written JSON in its reporter's format, plus live runs that are skipped unless
  $CODE_BENCH_VITEST_MODULES names node_modules folders with vitest. Install tests use a toy git project in a temp
  folder. The model steps run against tests/fixtures/code_fake_claude.py, a stub claude that writes and edits files
  in its working folder as each test scripts it. No test calls a model or reaches the network.

  # Backed by: tests/test_code_bench.py::test_pytest_run_with_passing_tests_is_pass
  Scenario: A pytest run whose two tests pass is pass
    Given a tiny python project with two passing tests
    When the runner runs that file with pytest in the sandbox
    Then the result is pass with 2 tests and 0 failed

  # Backed by: tests/test_code_bench.py::test_pytest_run_with_a_failing_test_is_fail
  Scenario: A pytest run with one failing test of two is fail
    Given a tiny python project with one passing and one failing test
    When the runner runs that file with pytest
    Then the result is fail with 2 tests and 1 failed

  # Backed by: tests/test_code_bench.py::test_pytest_file_with_no_tests_or_only_skipped_tests_is_no_tests
  Scenario: A pytest file with no tests, or with only skipped tests, is no_tests
    Given a test file that defines no test and a test file whose only test is skipped
    When the runner runs each with pytest
    Then both results are no_tests with 0 tests and 0 failed

  # Backed by: tests/test_code_bench.py::test_pytest_import_of_a_listed_name_is_load_error_missing_name
  Scenario: A pytest file that cannot import a listed name is load_error_missing_name
    Given a test file that runs "from mod import mul" while mod has no mul
    When the runner runs it with names ["mul"] and again with names ["other"]
    Then the first result is load_error_missing_name and the second is load_error

  # Backed by: tests/test_code_bench.py::test_pytest_missing_module_named_in_the_list_is_load_error_missing_name
  Scenario: A pytest file whose missing module is a listed file is load_error_missing_name
    Given a test file that imports pkg.newmod, which does not exist
    When the runner runs it with names ["pkg/newmod.py"]
    Then the result is load_error_missing_name

  # Backed by: tests/test_code_bench.py::test_pytest_syntax_error_is_load_error
  Scenario: A pytest file with a syntax error is load_error
    Given a test file with a syntax error
    When the runner runs it with names ["test_x", "x"]
    Then the result is load_error

  # Backed by: tests/test_code_bench.py::test_pytest_one_file_missing_a_name_and_one_broken_file_is_load_error
  Scenario: A missing listed name in one pytest file and a syntax error in another is load_error
    Given one test file that cannot import mul and another with a syntax error
    When the runner runs both with names ["mul"]
    Then the result is load_error, because not every file failed to load only for a listed name

  # Backed by: tests/test_code_bench.py::test_pytest_time_out_is_timeout_and_kills_the_whole_process_group
  Scenario: A pytest run over the time limit is timeout and its whole process group is killed
    Given a test that starts a child process sleeping 120 s and then sleeps 120 s itself
    When the runner runs it with a 3 s limit
    Then the result is timeout with tests and failed null, the call returns within 20 s and the child process is gone

  # Backed by: tests/test_code_bench.py::test_node_run_with_passing_tests_is_pass_and_an_empty_file_adds_no_test
  Scenario: A node --test run whose two tests pass is pass and a file with no tests adds no test
    Given a file with two passing node:test tests and a file with none
    When the runner runs both with node --test
    Then the result is pass with 2 tests and 0 failed

  # Backed by: tests/test_code_bench.py::test_node_run_with_a_failing_test_is_fail
  Scenario: A node --test run with one failing test, one passing and one skipped is fail
    Given a node:test file with a failing, a passing and a skipped test
    When the runner runs it
    Then the result is fail with 2 tests and 1 failed

  # Backed by: tests/test_code_bench.py::test_node_file_with_no_tests_is_no_tests
  Scenario: A node --test file with no tests is no_tests
    Given a node:test file that defines no test
    When the runner runs it
    Then the result is no_tests with 0 tests and 0 failed

  # Backed by: tests/test_code_bench.py::test_node_missing_export_or_file_of_a_listed_name_is_load_error_missing_name
  Scenario: A node file that misses a listed export or file is load_error_missing_name
    Given a node:test file importing mul from a module without it, and one importing ../src/mul.mjs, which does not exist
    When the runner runs the first with names ["mul"], again with ["div"], and the second with ["src/mul.mjs"]
    Then the results are load_error_missing_name, load_error and load_error_missing_name

  # Backed by: tests/test_code_bench.py::test_node_syntax_error_is_load_error
  Scenario: A node file with a syntax error is load_error
    Given a node:test file with a syntax error
    When the runner runs it
    Then the result is load_error with 0 tests

  # Backed by: tests/test_code_bench.py::test_node_one_broken_file_beside_a_failing_test_is_load_error
  Scenario: A broken node file beside a file with a failing test is load_error
    Given a node:test file with a syntax error and another with a failing test
    When the runner runs both
    Then the result is load_error

  # Backed by: tests/test_code_bench.py::test_node_error_after_tests_ran_is_fail_not_load_error
  Scenario: A node file that throws after its tests ran is fail, not a load error
    Given a node:test file whose test passes and which throws 10 ms later
    When the runner runs it
    Then the result is fail with 2 tests and 1 failed

  # Backed by: tests/test_code_bench.py::test_node_time_out_is_timeout
  Scenario: A node --test run over the time limit is timeout
    Given a node:test test that waits 120 s
    When the runner runs it with a 3 s limit
    Then the result is timeout and the call returns within 20 s

  # Backed by: tests/test_code_bench.py::test_runner_runs_in_test_cwd_with_tree_relative_files
  Scenario: The runner runs in test_cwd with tree-relative file paths
    Given a tree whose tests live under web/ and a test that checks package.json is in its working folder
    When the runner runs "web/test/a.test.mjs" with test_cwd "web"
    Then the result is pass with 1 test

  # Backed by: tests/test_code_bench.py::test_vitest_json_with_passing_tests_is_pass
  Scenario: vitest JSON with two passed and one skipped test is pass
    Given a vitest JSON report with assertions passed, passed and skipped
    When the vitest adapter reads it with exit code 0
    Then the result is pass with 2 tests and 0 failed

  # Backed by: tests/test_code_bench.py::test_vitest_json_with_a_failing_test_is_fail
  Scenario: vitest JSON with a failed assertion is fail and the failure text goes to the detail
    Given a vitest JSON report with one passed and one failed assertion whose message is "5 != 6"
    When the vitest adapter reads it
    Then the result is fail with 2 tests and 1 failed and the detail holds "5 != 6"

  # Backed by: tests/test_code_bench.py::test_vitest_json_no_test_suite_found_is_no_tests
  Scenario: vitest JSON for a file with no test suite is no_tests
    Given a vitest JSON report whose only file failed with "No test suite found in file" and no assertions
    When the vitest adapter reads it
    Then the result is no_tests with 0 tests

  # Backed by: tests/test_code_bench.py::test_vitest_json_failed_import_of_a_listed_name_is_load_error_missing_name
  Scenario: vitest JSON for a file that cannot resolve a listed import is load_error_missing_name
    Given a vitest JSON report whose file failed with 'Failed to resolve import "./mul"' and no assertions
    When the vitest adapter reads it with names ["mul"] and with names ["div"]
    Then the results are load_error_missing_name and load_error

  # Backed by: tests/test_code_bench.py::test_vitest_json_failed_file_for_another_reason_is_load_error
  Scenario: vitest JSON with a transform error in one file and a failing test in another is load_error
    Given a vitest JSON report with a file that failed with "Transform failed" and a file with a failed assertion
    When the vitest adapter reads it
    Then the result is load_error

  # Backed by: tests/test_code_bench.py::test_vitest_error_outside_tests_with_all_tests_passing_is_fail
  Scenario: vitest JSON with all tests passing but an error outside the tests is fail
    Given a vitest report with success false and exit code 1 while its one test passed, and one whose file failed in a hook
    When the vitest adapter reads each
    Then both results are fail

  # Backed by: tests/test_code_bench.py::test_vitest_without_a_json_file_is_no_tests_or_load_error
  Scenario: vitest without a JSON file is no_tests after "No test files found", else load_error
    Given no JSON file and the output "No test files found", then no JSON file and a config error
    When the vitest adapter reads each
    Then the results are no_tests and load_error

  # Backed by: tests/test_code_bench.py::test_vitest_without_a_vitest_binary_is_check_infra
  Scenario: A vitest run with no vitest binary under the tree is check_infra
    Given a tree with a vitest test file and no node_modules
    When the runner runs it with vitest
    Then the result is check_infra and npx is never used

  # Backed by: tests/test_code_bench.py::test_vitest_live_run_maps_pass_fail_and_missing_name
  Scenario: A live vitest run maps pass, fail and a missing listed file (only when vitest is reachable)
    Given $CODE_BENCH_VITEST_MODULES names a node_modules folder with vitest, cloned into a tiny project
    When the runner runs a passing file, a failing file, and a file importing ./mul.mjs with names ["mul.mjs"]
    Then the results are pass, fail and load_error_missing_name

  # Backed by: tests/test_code_bench.py::test_the_test_sees_only_the_minimal_environment
  Scenario: The test sees only the minimal environment and may write in the tree and its scratch home
    Given NODE_OPTIONS and CODE_BENCH_SECRET are set in the parent
    When a pytest test checks its environment and writes in HOME and in the tree
    Then NODE_OPTIONS and CODE_BENCH_SECRET are absent, CI and PYTHONDONTWRITEBYTECODE are "1", HOME equals TMPDIR and is not the real home, and both writes succeed

  # Backed by: tests/test_code_bench.py::test_a_refused_sandbox_profile_is_check_infra
  Scenario: A sandbox profile that sandbox-exec refuses is check_infra
    Given a profile with a syntax error
    When the runner runs a passing pytest file and a node --test file
    Then both results are check_infra

  # Backed by: tests/test_code_bench.py::test_a_missing_runner_binary_is_check_infra
  Scenario: A missing python or node binary is check_infra
    Given the python binary "/nonexistent/python3", then no node binary
    When the runner runs a pytest file, then a node --test file
    Then both results are check_infra

  # Backed by: tests/test_code_bench.py::test_detail_is_the_tail_of_the_output_capped
  Scenario: The detail is the tail of the output, at most 4000 characters
    Given a failing test that prints 20000 characters and then "END-OF-RUN"
    When the runner runs it
    Then the detail has at most 4000 characters and holds "END-OF-RUN"

  # Backed by: tests/test_code_bench.py::test_selftest_passes_with_the_real_sandbox
  Scenario: The self-test passes with the real sandbox
    Given the canary projects for pytest and node --test (vitest not reachable)
    When the self-test runs
    Then pytest and node-test are pass, vitest is skipped and ok is true

  # Backed by: tests/test_code_bench.py::test_selftest_fails_closed_when_a_canary_test_did_not_run
  Scenario: The self-test fails when a canary test did not run
    Given a python canary file that lost its home-folder test
    When the self-test runs
    Then pytest is wrong_count, node-test is pass and ok is false

  # Backed by: tests/test_code_bench.py::test_selftest_fails_closed_when_the_network_is_open
  Scenario: The self-test fails when the sandbox lets a TCP connection through
    Given a sandbox profile without the network denial
    When the self-test runs
    Then pytest and node-test are fail and ok is false

  # Backed by: tests/test_code_bench.py::test_selftest_fails_closed_when_writes_outside_are_allowed
  Scenario: The self-test fails when the sandbox lets a write outside the tree through
    Given a sandbox profile without the write denial
    When the self-test runs
    Then pytest and node-test are escaped and ok is false

  # Backed by: tests/test_code_bench.py::test_selftest_command_prints_words_and_exits_by_the_verdict
  Scenario: The selftest command prints fixed words and exits 0 or 1
    Given the real sandbox, then a profile that lets the network through
    When `selftest` runs
    Then it prints "selftest: pytest pass, node-test pass, vitest skipped: ok" and exits 0, then prints FAILED and exits 1, and creates neither the root nor the evals folder

  # Backed by: tests/test_code_bench.py::test_clone_tree_copy_is_independent_of_its_source
  Scenario: A cloned tree is independent of its source
    Given a tree with a.txt "one"
    When it is cloned with cp -cR and the clone's a.txt is changed and a file added
    Then the source still has a.txt "one" and no new file

  # Backed by: tests/test_code_bench.py::test_make_copy_applies_deletions_overlay_files_and_node_modules
  Scenario: make_copy applies deletions, overlay files and node_modules, and drop_copy removes it
    Given a start tree with a.txt, gone.txt and a stale node_modules, and a node_modules folder elsewhere
    When make_copy runs with a.txt as bytes, new/b.txt from disk, gone.txt deleted and that node_modules
    Then the copy has the new contents, no gone.txt and the new node_modules, the start is unchanged, and drop_copy removes the copy's folder

  # Backed by: tests/test_code_bench.py::test_overlay_of_lists_changed_new_and_deleted_files_and_ignores_caches
  Scenario: overlay_of lists changed, new and deleted files and ignores caches and node_modules
    Given a copy with a.py changed, c.py deleted, tests/test_new.py added and __pycache__, .pytest_cache, node_modules, .vite and .vitest files
    When overlay_of compares it with the start
    Then the files are a.py and tests/test_new.py, the deleted path is c.py and no symlink is counted

  # Backed by: tests/test_code_bench.py::test_overlay_of_ignores_and_counts_symlinks_the_copy_added
  Scenario: overlay_of ignores and counts symlinks the copy added
    Given a start with one symlink and a copy that adds three symlinks (two files, one folder)
    When overlay_of compares them
    Then the overlay has no file and no deletion and counts 3 symlinks

  # Backed by: tests/test_code_bench.py::test_matches_patterns_uses_whole_path_globs
  Scenario: Test patterns are globs over the whole tree-relative path
    Given the patterns "tests/**/*.py", "**/*.test.ts", "web/src/**/__tests__/**" and "*.py"
    When paths are matched
    Then tests/x/y/test_a.py, a.test.ts and web/src/a.test.ts match, and src/a.py does not match "*.py"
    And the pattern "tests/" matches every path under tests, and neither "tests" itself nor mytests/a.py

  # Backed by: tests/test_code_bench.py::test_source_unchanged_only_when_every_changed_path_is_a_test_path
  Scenario: The source is unchanged only when every changed or deleted path is a test path
    Given the test pattern "tests/**"
    When overlays change only tests, change mod.py too, or delete mod.py
    Then only the first is source unchanged

  # Backed by: tests/test_code_bench.py::test_missing_name_matching_rules
  Scenario: The missing-name reading matches error forms of python, node and vite to the listed names
    Given error lines for a missing import, module, attribute, file, export, module path, property and function
    When they are matched against the listed names
    Then each matches its name, and a syntax error, a longer name or an empty list does not match

  # Backed by: tests/test_code_bench.py::test_red_on_start_is_fail_timeout_or_load_error_missing_name
  Scenario: Red on the start state is fail, timeout or load_error_missing_name
    Given the fixed result words
    When each is read as red or not
    Then exactly fail, timeout and load_error_missing_name are red

  # Backed by: tests/test_code_bench.py::test_time_limit_is_five_times_the_reference_between_20_and_60_seconds
  Scenario: The time limit is five times the reference run, at least 20 s and at most 60 s
    Given reference runs of 1 s, 6 s and 30 s
    When the time limit is computed
    Then it is 20 s, 30 s and 60 s

  # Backed by: tests/test_code_bench.py::test_task_records_with_a_bad_field_are_refused
  Scenario: A task record with a bad field is refused as task_invalid
    Given task records with a bad code, a relative project_dir, a short commit, an unknown runner, a path with "..", run files outside the hidden tests or an empty names list
    When each is validated
    Then each is refused with task_invalid

  # Backed by: tests/test_code_bench.py::test_a_good_task_record_is_accepted
  Scenario: A good vitest task record with node_modules under web is accepted
    Given a vitest task record with test_cwd "web" and node_modules to "web/node_modules"
    When it is validated
    Then it gives a Task with runner vitest and the node_modules target

  # Backed by: tests/test_code_bench.py::test_install_builds_start_reference_hidden_and_passes_a_good_task
  Scenario: install builds start, reference and hidden from git and passes a good task
    Given a toy git project whose change adds mul, deletes legacy.py and adds tests/test_mul.py
    When install runs
    Then start has the before source, reference has mul and no legacy.py, hidden has the test, installed.json says ok with 3 of 3 reference passes, and the public record has install_start fail and three install_reference pass lines

  # Backed by: tests/test_code_bench.py::test_install_strips_the_fixed_list_and_the_task_strip_list
  Scenario: install strips the fixed list of the rules and the task's own strip list
    Given the toy project with CLAUDE.md, pkg/CLAUDE.md, AGENTS.md, docs/, .github/, .claude/ and scripts/notes.txt in the task's strip list
    When install runs
    Then none of them is in start/, and notes/LEAK.txt and pkg/__init__.py are

  # Backed by: tests/test_code_bench.py::test_the_fixed_strip_files_go_in_any_letter_case
  Scenario: The fixed strip files are removed in any letter case
    Given a tree with Changelog.md, pkg/changelog.md, pkg/claude.MD, pkg/changelog.md.txt and mod.py
    When the tree is stripped
    Then the first three are removed, and pkg/changelog.md.txt and mod.py stay

  # Backed by: tests/test_code_bench.py::test_install_fails_a_task_whose_hidden_tests_are_not_red_on_start
  Scenario: install fails a task whose hidden tests pass on the start state
    Given a task whose hidden test is tests/test_add.py, which already passes at before
    When install runs
    Then it prints "code-01 install: failed start_not_red", exits 1 and installed.json says ok false

  # Backed by: tests/test_code_bench.py::test_install_fails_a_task_whose_reference_does_not_pass
  Scenario: install fails a task whose reference does not pass
    Given a task whose after commit has a wrong mul
    When install runs
    Then it prints "code-01 install: failed reference_fails" and the record has install_start fail and one install_reference fail

  # Backed by: tests/test_code_bench.py::test_install_fails_a_task_that_leaks_an_added_name
  Scenario: install fails a task when an added name occurs in the stripped start tree
    Given a task whose names include LEAKY_NAME, which notes/LEAK.txt holds and the before source does not
    When install runs
    Then it prints "code-01 install: failed leak" without the name, no test runs, and attempts.jsonl names the file

  # Backed by: tests/test_code_bench.py::test_install_without_the_task_strip_list_finds_the_leak_it_hides
  Scenario: Without the task's strip list the leak check finds the name it hid
    Given the good task with an empty strip list, so scripts/notes.txt that mentions mul stays
    When install runs
    Then it prints "code-01 install: failed leak"

  # Backed by: tests/test_code_bench.py::test_leak_check_ignores_names_the_before_source_already_has
  Scenario: The leak check looks only for names the change adds, as whole tokens
    Given a before source that has add, and a tree whose README says "add and mul and multiply_all"
    When the added names of add, mul and div are found and the tree is searched
    Then mul and div are added, mul is found in README.txt, div and multiply are not found

  # Backed by: tests/test_code_bench.py::test_leak_check_reads_the_path_of_a_file_too
  Scenario: The leak check also reads the path of every file
    Given a tree with lib/fancy_newthing.py, notes/readme.txt, newmod/data.json and src/other_newmod.py
    When the tree is searched for the added names fancy_newthing.py, readme, newmod and thing
    Then the first three are found in a path (a file name, a file name without its ending, a folder name) and thing is not

  # Backed by: tests/test_code_bench.py::test_install_fails_a_task_with_a_source_file_that_neither_commit_has
  Scenario: install fails a task whose record lists a source file that neither commit has
    Given the good task with no_such_file.py added to its source files
    When install runs
    Then it prints "code-01 install: failed task_invalid", installed.json says ok false, and no test runs

  # Backed by: tests/test_code_bench.py::test_install_refuses_a_missing_strip_entry
  Scenario: install fails a task whose own strip entry does not exist
    Given a task whose strip list names no/such/file.txt
    When install runs
    Then it prints "code-01 install: failed strip_missing"

  # Backed by: tests/test_code_bench.py::test_install_refuses_to_run_when_the_selftest_fails
  Scenario: install refuses to run when the self-test fails
    Given a sandbox profile that lets the network through
    When install runs
    Then stderr is "code_bench: error: selftest_failed", the exit code is 2, no task folder exists and the record is empty

  # Backed by: tests/test_code_bench.py::test_install_with_an_invalid_task_record_prints_task_invalid_and_the_code
  Scenario: install with an invalid task record prints the reason word and the task code
    Given a task record with runner "jest"
    When install runs
    Then stderr is "code_bench: error: task_invalid code-01" and the exit code is 2

  # Backed by: tests/test_code_bench.py::test_install_takes_evalkits_exclusive_lock
  Scenario: install takes evalkit's exclusive lock
    Given another holder of results/.evalkit.lock
    When install runs
    Then stderr is "code_bench: error: locked", the exit code is 2 and nothing is built

  # Backed by: tests/test_code_bench.py::test_a_command_with_the_lock_removes_what_a_killed_invocation_left
  Scenario: A command that takes the lock first removes what a killed invocation left in the scratch folder
    Given a scratch folder with the folders copy-old1, snap-old2 and selftest-other and a file named copy-not-a-folder
    When install runs
    Then copy-old1 and snap-old2 are gone, and selftest-other and the file are still there

  # Backed by: tests/test_code_bench.py::test_a_trial_root_keeps_its_record_beside_it
  Scenario: A trial root keeps its record beside it, never in the repository's public record
    Given the options --root <trial> without --results, then with --results, then neither option
    When the app is made
    Then the record is <trial>/code-runs.jsonl, then the named file, then <evals>/results/code-runs.jsonl

  # Backed by: tests/test_code_bench.py::test_install_runs_git_only_with_read_only_subcommands
  Scenario: install calls git only with read-only subcommands
    Given a spy on the tool's git function
    When install runs
    Then every subcommand is archive, show, cat-file, rev-parse or ls-tree, and checkout, reset, stash, clean, restore, worktree, rm and switch are refused

  # Backed by: tests/test_code_bench.py::test_public_line_refuses_text_unknown_keys_and_unknown_words
  Scenario: A public line with free text, an unknown key or an unknown word is refused
    Given check lines with a path in what, a test name in result, a project name as task, a bad cell, a bad suite, an unknown step, a list, a detail key or a bad time
    When each is validated as a public line
    Then each is refused

  # Backed by: tests/test_code_bench.py::test_public_line_accepts_fixed_words_and_numbers
  Scenario: A public line of fixed words and numbers is accepted
    Given an install_start check line and a step C given check line with suite sonnet-5-5@high#1 and result locked_changed
    When each is validated
    Then both are accepted

  # Backed by: tests/test_code_bench.py::test_model_line_builder_writes_the_fixed_keys_and_keeps_detail_private
  Scenario: A model line has exactly the fixed keys and its detail goes only to attempts.jsonl
    Given a step T model line with a detail holding a marker
    When it is recorded
    Then the public line has exactly the model keys and no marker, attempts.jsonl has the detail, a line with only some keys gets null for the rest, and a free-text reason or an unknown key such as prompt is refused

  # Backed by: tests/test_code_bench.py::test_no_path_name_or_output_text_reaches_the_public_file_or_the_terminal
  Scenario: No path, test name or output text reaches the public record or the terminal
    Given a marker in the brief, in the project's folder name, in a hidden test's name, in its printed output and in its failure message
    When install runs
    Then neither the public record nor stdout nor stderr holds the marker, a temp path or the test name, and attempts.jsonl holds all three markers

  # Backed by: tests/test_code_bench.py::test_an_unexpected_exception_prints_a_code_word_and_the_task_only
  Scenario: An unexpected exception prints a code word and the task only, and the other tasks go on
    Given building the trees of code-01 raises an error whose text holds a path and a marker, and code-02 is good
    When install runs, and then install runs while reading the task records raises such an error
    Then the first prints "code-01 install: failed internal" and "code-02 install: ok" and exits 1, installed.json of code-01 says ok false with reason internal, the second prints "code_bench: error: internal" and exits 2, no traceback or marker is shown, and attempts.jsonl holds the traceback

  # Backed by: tests/test_code_bench.py::test_vitest_2_missing_relative_import_is_load_error_missing_name
  Scenario: vitest 2's message for a missing relative import is load_error_missing_name
    Given a vitest JSON report whose file failed with "Failed to load url ./newmod.js (resolved id: ./newmod.js)"
    When the vitest adapter reads it with names ["newmod"], ["src/newmod.js"] and ["other"]
    Then the results are load_error_missing_name, load_error_missing_name and load_error

  # Backed by: tests/test_code_bench.py::test_an_empty_file_list_is_no_tests_and_starts_no_runner
  Scenario: An empty list of files is no_tests and starts no runner
    Given a tree with a passing test and a runner that must not start
    When pytest, node --test and vitest are each given no file
    Then each result is no_tests with 0 tests and nothing was started

  # Backed by: tests/test_code_bench.py::test_a_requested_test_file_that_does_not_exist_is_load_error
  Scenario: A requested test file that does not exist is load_error for every runner
    Given a tree with one test file and a second requested file that does not exist
    When pytest, node --test and vitest are asked to run both
    Then each result is load_error

  # Backed by: tests/test_code_bench.py::test_node_runs_a_file_whose_name_holds_glob_characters_as_itself
  Scenario: node --test runs a file whose name holds glob characters as itself
    Given r/[id].test.mjs with a passing test and r/i.test.mjs with a failing one
    When the runner runs r/[id].test.mjs
    Then the result is pass with 1 test, so the glob did not pick r/i.test.mjs

  # Backed by: tests/test_code_bench.py::test_a_test_file_whose_name_starts_with_a_dash_is_run_as_a_file
  Scenario: A test file whose name starts with a dash is run as a file, never read as an option
    Given a project with the test files -x_test.py and -y.test.mjs
    When pytest runs the first and node --test the second
    Then pytest gives pass with 1 test, and node, which cannot start such a file, gives load_error

  # Backed by: tests/test_code_bench.py::test_node_a_requested_file_that_never_reported_did_not_load
  Scenario: A node file that never reported an event did not load
    Given node events for a.test.mjs only
    When they are read for a.test.mjs and b.test.mjs, then for a.test.mjs alone
    Then the first is load_error and the second is pass with 1 test

  # Backed by: tests/test_code_bench.py::test_vitest_json_counts_only_the_requested_files
  Scenario: vitest results of files that were not requested are dropped
    Given a vitest report for a.test.js (passed) and sub/a.test.js (failed), which the substring filter a.test.js also ran
    When it is read for the file a.test.js, then for a.test.js and b.test.js
    Then the first is pass with 1 test and 0 failed, the second is load_error

  # Backed by: tests/test_code_bench.py::test_vitest_live_substring_filter_and_missing_relative_import
  Scenario: Live vitest runs drop other files and read a missing relative import (only when vitest is reachable)
    Given each node_modules folder of $CODE_BENCH_VITEST_MODULES cloned into a project with a.test.js, a failing sub/a.test.js and n.test.js importing ./newmod.js
    When the runner runs a.test.js, then n.test.js with names ["newmod"]
    Then the results are pass with 1 test and load_error_missing_name, for vitest 2 and 5 alike

  # Backed by: tests/test_code_bench.py::test_a_failed_reinstall_leaves_installed_json_not_ok
  Scenario: A failed re-install leaves installed.json not ok
    Given a task that installed ok, then the same task with a strip entry that does not exist
    When install runs again
    Then installed.json says ok false with reason strip_missing and has no task hash

  # Backed by: tests/test_code_bench.py::test_install_reports_check_infra_as_the_runner_failing_not_the_task
  Scenario: install reports a runner that cannot run as check_infra, not as a failed task
    Given a python binary that does not exist
    When install runs a good task
    Then it prints "code-01 install: stopped check_infra" with no "failed", and installed.json has reason check_infra

  # Backed by: tests/test_code_bench.py::test_a_task_that_runs_vitest_needs_the_vitest_canary
  Scenario: A task that runs vitest needs the vitest canary to pass
    Given a self-test whose vitest canary was skipped, then one where it passed
    When the self-test is required with and without a vitest task in scope
    Then it fails with selftest_failed only when a vitest task is in scope and the canary was skipped

  # Backed by: tests/test_code_bench.py::test_install_skips_links_that_leave_the_tree_and_keeps_exec_modes
  Scenario: install skips links that leave the tree and keeps executable modes
    Given a project with an absolute link and a ../ link at before, and a change that edits an executable run.sh and adds an executable tests/check.sh
    When install runs
    Then it passes, installed.json counts 2 links skipped, the links are not in start/, and run.sh in reference/ and check.sh in hidden/ are executable while mod.py is not

  # Backed by: tests/test_code_bench.py::test_writing_over_a_file_keeps_its_mode
  Scenario: Writing a file keeps the mode of the file it replaces or of its source
    Given a 0755 file, a 0700 source file and a new file with mode 0644 given
    When each is written
    Then the modes are 0755, 0700 and 0644

  # Backed by: tests/test_code_bench.py::test_a_sandboxed_test_cannot_signal_a_process_outside_the_sandbox
  Scenario: A sandboxed test cannot signal a process outside the sandbox
    Given a sleep process started outside the sandbox and a test that sends it SIGKILL
    When the runner runs the test
    Then the result is fail with a PermissionError and the sleep process is still alive

  # Backed by: tests/test_code_bench.py::test_selftest_fails_closed_when_signals_to_outside_processes_are_allowed
  Scenario: The self-test fails when the sandbox lets a signal to an outside process through
    Given a sandbox profile without the signal denial
    When the self-test runs
    Then pytest and node-test are not pass and ok is false

  # Backed by: tests/test_code_bench.py::test_a_child_that_left_the_process_group_is_killed_after_the_run
  Scenario: A child that left the process group is killed after the run
    Given a passing test that starts a setsid child sleeping 300 s, and a test that does the same and then sleeps past the 3 s limit
    When the runner runs each
    Then the results are pass and timeout and both setsid children are gone

  # Backed by: tests/test_code_bench.py::test_a_run_that_floods_its_output_is_stopped_and_only_its_tail_is_read
  Scenario: A run that floods its output is stopped and only its tail is read
    Given an output cap of 2 MB and a test that writes 30 MB to the run's output, a little at a time, and then fails
    When the runner runs it
    Then the result is timeout with a detail of at most 4000 characters, and read_tail reads only the last bytes of a file

  # Backed by: tests/test_code_bench.py::test_a_cloned_node_modules_has_no_link_that_leaves_it
  Scenario: A cloned node_modules has no link that leaves it
    Given a node_modules folder with absolute links into itself, an absolute link to /etc/hosts, a ../../ link and a relative link inside
    When it is cloned
    Then 4 links are changed: the two into itself point into the clone, the two outside are gone, and the inside link is kept

  # Backed by: tests/test_code_bench.py::test_write_tests_runs_every_test_writing_cell_twice_with_file_tools_only
  Scenario: write-tests runs every test-writing cell twice per task with file tools only
    Given one installed task with a node_modules folder and a stub writer that writes a red suite
    When write-tests runs, and then runs again
    Then the stub is called 8 times, twice each for sonnet-5-5@high, sonnet-5-5@xhigh, opus-5-5@medium and opus-5-5@high, with --permission-mode dontAsk, --allowedTools Read Grep Glob Write Edit, --tools Read,Grep,Glob,Write,Edit, the fixed system prompt, DISABLE_AUTOUPDATER 1 and the advisor off, in a copy of start without node_modules, with the brief and the step-T text; 8 red_first lines and 8 suites are stored; the second invocation calls nothing

  # Backed by: tests/test_code_bench.py::test_write_tests_keeps_only_the_test_files_and_counts_what_it_dropped
  Scenario: Step T keeps only the test files and counts what it dropped
    Given a writer that adds a test, changes mod.py, adds newsrc.py, deletes tests/test_add.py and adds a symlink
    When write-tests runs
    Then the suite is tests/test_mul_w.py only, files_dropped is 4, files_changed is 5, and the red-first check sees the start's mod.py

  # Backed by: tests/test_code_bench.py::test_a_suite_that_is_not_red_gets_another_try_with_the_check_output
  Scenario: A suite that is not red gets another try in the same copy with the check's output
    Given a writer whose first suite passes on start and whose second is red
    When write-tests runs
    Then the second prompt holds the retry line and "1 passed", the copy still has the first file, the red_first results are pass then load_error_missing_name, and the suite is red after 2 tries

  # Backed by: tests/test_code_bench.py::test_a_writer_that_never_gets_red_stops_after_three_tries
  Scenario: A writer whose suite is never red stops after three tries
    Given a writer whose suite always passes on start
    When write-tests runs one cell
    Then each run makes 3 calls and its suite is stored with red false

  # Backed by: tests/test_code_bench.py::test_a_writer_that_writes_no_test_is_told_so
  Scenario: A writer that writes no test file is told so
    Given a writer that only changes mod.py and then writes a red suite
    When write-tests runs
    Then the second prompt says no test file was added or changed and the red_first results are no_tests then load_error_missing_name

  # Backed by: tests/test_code_bench.py::test_write_tests_never_runs_the_reference
  Scenario: Step T never runs the reference
    Given a spy on every test copy's base tree
    When write-tests runs two tries
    Then every base tree is start

  # Backed by: tests/test_code_bench.py::test_an_api_error_is_an_attempt_not_a_try_and_leaves_no_trace
  Scenario: An API error is an attempt, not a try, and leaves no trace in the copy
    Given a first process that writes a file and fails with api_error_status 529, then a good writer
    When write-tests runs
    Then the second process gets the same prompt in a copy without that file, the model lines are try 1 attempt 1 infra and try 1 attempt 2 valid, and one red_first line exists

  # Backed by: tests/test_code_bench.py::test_three_api_errors_end_the_run
  Scenario: Three API errors end the run in step T and in step C
    Given a writer and a coder whose processes always fail with an API error
    When write-tests and then code run
    Then the suite is stored with ended infra, no file and 3 processes and no check line; the arm-B run ends infra, not correct and not finished

  # Backed by: tests/test_code_bench.py::test_a_time_out_and_a_budget_cap_are_tries_and_an_unknown_cost_is_charged_the_cap
  Scenario: A time-out and a budget stop are tries, and an unknown cost is charged the $6 cap
    Given a 2 s process time limit, a writer that times out, then stops at its budget, then writes a red suite without a cost
    When write-tests runs
    Then the model lines are tries 1, 2 and 3 with reasons timeout, budget_cap and none, none of them infra, three red_first lines exist, and the run costs $18 with 2 unknown costs

  # Backed by: tests/test_code_bench.py::test_no_model_process_starts_once_the_spend_total_reaches_the_limit
  Scenario: No model process starts once the spend total over all invocations reaches the limit
    Given a public record with one model line of unknown cost ($6) and a writer that costs $0.25
    When write-tests runs with --max-usd 6.01, then write-tests and code run with --max-usd 6.2
    Then the first makes exactly one call, prints "(spend $6.25)" and "spend stop reached ($6.25 of $6.01)" and exits 3; the next two make no call and exit 3

  # Backed by: tests/test_code_bench.py::test_a_model_command_stops_when_the_claude_version_differs
  Scenario: A model command stops when claude --version is not 2.1.325
    Given a stub that says "2.1.326 (Claude Code)"
    When write-tests or code runs, then runs with --allow-version 2.1.326
    Then the first prints "code_bench: error: version_mismatch", exits 2 and calls nothing; the second runs and records cli_version 2.1.326

  # Backed by: tests/test_code_bench.py::test_a_command_that_runs_tests_refuses_when_the_selftest_fails
  Scenario: write-tests, fix-suites, code and cross refuse to run when the self-test fails
    Given a failing self-test
    When each command runs
    Then it prints "code_bench: error: selftest_failed", exits 2 and calls nothing

  # Backed by: tests/test_code_bench.py::test_a_command_that_writes_records_takes_evalkits_lock
  Scenario: write-tests, fix-suites, code and cross take evalkit's exclusive lock
    Given another holder of results/.evalkit.lock
    When each command runs
    Then it prints "code_bench: error: locked", exits 2 and calls nothing

  # Backed by: tests/test_code_bench.py::test_fix_suites_scores_every_suite_and_fixes_the_first_fit_in_the_fixed_order
  Scenario: fix-suites scores every suite and the given suite is the first fit one in the fixed order
    Given sonnet-5-5@high run 1 not red on start, run 2 red but failing on the reference, and the other six fit
    When fix-suites runs
    Then it prints "6 of 8 fit, given sonnet-5-5@xhigh#1", fit.json says why each of the first two is not fit, the fit one passed the reference twice (try 1 and 2), and one public given line names sonnet-5-5@xhigh#1 with result pass

  # Backed by: tests/test_code_bench.py::test_the_given_suite_waits_for_all_eight_suites_and_is_never_changed
  Scenario: The given suite waits for all eight suites and is never changed afterwards
    Given seven stored suites, then the eighth, then a changed fit.json
    When fix-suites runs after each
    Then the first says "given pending (7 of 8 suites stored)", the second fixes sonnet-5-5@high#1, and the third keeps it and writes no second given line

  # Backed by: tests/test_code_bench.py::test_an_infra_ended_suite_is_not_fit_and_is_not_run
  Scenario: A suite whose run ended on infra errors is not fit and is not run
    Given eight good suites, the first of which ended on infra errors
    When fix-suites runs
    Then no line names the first suite and the given suite is sonnet-5-5@high#2

  # Backed by: tests/test_code_bench.py::test_a_task_with_no_fit_suite_runs_arm_a_only
  Scenario: A task with no fit suite runs arm A only
    Given eight suites that all pass on start
    When fix-suites runs and then code runs haiku-5-5@high for round 1
    Then fix-suites says arms B and C are left out and writes a given line with result fail and no suite, code prints "code-01 haiku-5-5@high B: left out (no fit suite)" and only an arm-A process runs

  # Backed by: tests/test_code_bench.py::test_arm_a_has_one_try_and_only_the_hidden_tests_run
  Scenario: Arm A has one try and only the hidden tests run
    Given a coder that writes a wrong mul
    When code runs haiku-5-5@medium arm A for round 1
    Then one process runs with the arm-A text, the only check line is hidden fail, and the run is stored with 1 try, finished null, not correct and escaped null

  # Backed by: tests/test_code_bench.py::test_arm_b_a_coder_that_fixes_the_code_at_the_second_try
  Scenario: Arm B: a coder that fixes the code at the second try
    Given a given suite and a coder that writes a wrong mul and a helper, then the right mul
    When code runs haiku-5-5@medium arm B for round 1
    Then the first process sees the suite file and its path in the prompt, the second gets the retry line with "assert 5 == 6" in the same copy, the check lines are given fail, hidden fail, given pass, hidden pass, and the run is finished and correct, not correct at the first try, costs $0.50 and 2468 ms

  # Backed by: tests/test_code_bench.py::test_arm_b_a_coder_that_edits_a_locked_file_fails_the_try_and_the_file_is_put_back
  Scenario: Arm B: a coder that edits a locked test file or the runner's configuration fails the try and the file is put back
    Given a task whose runner_config is pytest.ini and a coder that weakens the given test, then writes pytest.ini, then writes the right mul
    When code runs haiku-5-5@medium arm B for round 1
    Then the given results are locked_changed, locked_changed and pass, the next prompts say a locked file was put back, pytest.ini is gone from the copy, files_dropped is 1, 1, 0 and the stored test file is the given one

  # Backed by: tests/test_code_bench.py::test_arm_b_a_run_that_passes_the_given_suite_but_not_the_hidden_tests_escaped
  Scenario: Arm B: a run that passes the given suite but not the hidden tests escaped
    Given a weak given suite that checks mul(2, 2) only and a coder that writes mul as a + b
    When code runs sonnet-5-5@medium for round 1
    Then the run is finished after 1 try, not correct and escaped

  # Backed by: tests/test_code_bench.py::test_arm_c_own_tests_must_exist_be_red_on_start_and_pass_on_the_copy
  Scenario: Arm C: the coder's own tests must exist, be red on the start state and pass on the copy
    Given a coder that writes the right mul and no test, then a test that passes on start, then a red test
    When code runs haiku-5-5@high arm C for round 1
    Then the own results are no_tests, fail and pass, the private reasons are no_own_tests and own_not_red, the prompts say why, and the run is finished and correct

  # Backed by: tests/test_code_bench.py::test_hidden_tests_run_after_every_try_and_are_never_shown_to_the_model
  Scenario: The hidden tests run after every try and are never shown to the model
    Given a hidden test whose name and output hold a marker, and coders in arms B and C that never pass their check
    When code runs haiku-5-5@high arms B and C for round 1
    Then each arm has 3 hidden lines, no prompt holds the marker, no working copy has the hidden file, and attempts.jsonl has the marker

  # Backed by: tests/test_code_bench.py::test_step_c_plan_has_180_runs_in_rounds_in_the_order_task_cell_arm
  Scenario: Step C has 180 runs, in rounds, in the order task, cell, arm
    Given six tasks with a given suite each
    When the step-C units are listed
    Then there are 180 (66 in arm A, 90 in B, 24 in C) with the cells' arms and runs of the rules' table, round by round, starting with code-01 haiku-5-5@medium A; a task with no fit suite leaves out its 19 B and C runs and a task with no given suite yet keeps them pending

  # Backed by: tests/test_code_bench.py::test_code_runs_whole_rounds_up_to_the_rounds_option
  Scenario: code runs whole rounds up to --rounds
    Given two tasks and two arm-A cells
    When code runs with --rounds 1 and then with --rounds 2
    Then round 1 makes run 1 of each cell on code-01, then on code-02, and the second invocation adds run 2 of each

  # Backed by: tests/test_code_bench.py::test_an_interrupted_command_says_interrupted_not_done
  Scenario: An interrupted model command says "interrupted", not "done"
    Given a pool that returns 130, as it does after Ctrl-C
    When code and write-tests run
    Then each exits 130 and prints "interrupted" with the spend, and neither prints "done"

  # Backed by: tests/test_code_bench.py::test_cross_runs_every_fit_suite_on_the_final_copies_of_arms_a_and_c_only
  Scenario: cross runs every fit suite on the final copies of arms A and C only, without the run's own tests
    Given two fit suites, a wrong copy in two arm-A runs, a right copy in arm C whose own conftest.py would skip the suite, an arm-B copy, an arm-A copy with no source change, and a cross.json entry of another task with the same suite and non-test overlay
    When cross runs, and then runs again
    Then it makes 6 cross lines (4 runs, 2 identical pairs of this task reused, the other task's entry never): the strong suite fails both wrong copies and passes the right one, the weak suite passes all three; one copy line per copy of arms A and C says changed or unchanged (the arm-A copy with no source change); the second invocation adds nothing

  # Backed by: tests/test_code_bench.py::test_plan_counts_what_is_missing_and_the_spend
  Scenario: plan and status count what is missing and the spend
    Given six installed tasks, then two step-T runs that cost $1 each
    When plan runs, then plan --json and status run
    Then plan prints "step T: 0 of 48 suites stored", "step C: 0 of 180 runs stored (A 0/66, B 0/90, C 0/24)" and "projected unknown; stop at $226.00", then 2 stored and 46 missing and a spend of $2.00, and status prints "code-01: installed ok, T 2/8, fit 0, given pending, C 0"

  # Backed by: tests/test_code_bench.py::test_no_private_text_reaches_the_public_record_or_the_terminal_in_the_model_steps
  Scenario: No private text reaches the public record or the terminal in the model steps
    Given a marker in the brief, in a suite's file name, test name, output and failure message, and in the hidden test's name and output
    When write-tests, fix-suites, code, cross, plan and status run
    Then no output and no public line holds a marker, a temp path, a test name or a traceback, every public line passes the vocabulary check, the brief reached the model, and attempts.jsonl holds both markers

  # Backed by: tests/test_code_bench.py::test_a_model_process_gets_one_reason_word_and_the_infra_reading
  Scenario: A model process gets one reason word and evalkit's infra reading
    Given a spawn failure, a time-out, text that is not JSON, a budget stop, a refusal, another model, an error with output, an API error with no output and a good result
    When each is read
    Then the reasons are spawn_failed, timeout, json_parse, budget_cap, refusal, model_mismatch, is_error, is_error and none, and only the spawn failure and the API error are infra

  # Backed by: tests/test_code_bench.py::test_the_prompts_are_fixed_texts_with_the_brief_and_a_capped_check_output
  Scenario: The prompts are fixed texts with the brief, the suite's paths in arm B and a capped check output
    Given a brief, two suite paths and a check output of 9003 characters
    When the prompts are built
    Then arm B is the brief, the arm-B text, the paths and the DONE line; a later try adds the retry line and the last 4000 characters

  # Backed by: tests/test_code_bench.py::test_runnable_files_follow_the_runners_naming_rule_or_the_tasks_own
  Scenario: The files a runner runs follow its naming rule, or the task's own run_patterns
    Given suite files with tests, a conftest, helpers and data files
    When the runnable files are picked for pytest, node --test and a task with run_patterns
    Then only the test files are picked: test_a.py and a_test.py; a.test.ts and b.spec.mjs; every .ts under test/

  # Backed by: tests/test_code_bench.py::test_a_check_infra_test_run_stops_the_unit_and_stores_nothing
  Scenario: A test run that comes back check_infra stops the unit and stores nothing
    Given a runner whose first run comes back check_infra, in write-tests (red first), fix-suites (fit_start), code arm A (hidden), arm B (given), arm C (own tests on start) and cross
    When the command runs, and runs again once the runner works
    Then it exits 2 with "code_bench: error: check_infra", the private detail goes to attempts.jsonl only, no suite meta.json, fit.json, given suite, run meta.json or cross pair is stored, no further model process starts and no public line reads infra as a result; the next invocation makes the unit and stores it

  # Backed by: tests/test_code_bench.py::test_the_note_that_says_why_a_try_failed_survives_a_long_check_output
  Scenario: The note that says why a try failed survives a long check output
    Given arm B with a given suite whose failure message is 6000 characters and a coder that changes pytest.ini, and arm C with own tests of 6000 passing cases
    When the next try's prompt is built
    Then the check output part starts with the locked-file note (arm B) or the own-not-red note (arm C), is at most 4000 characters, and ends with the output's tail

  # Backed by: tests/test_code_bench.py::test_the_claude_version_must_match_as_a_whole_version
  Scenario: The Claude Code version must match as a whole version
    Given claude --version printing 2.1.3251 or 2.1.325.1
    When write-tests runs
    Then it prints "code_bench: error: version_mismatch", exits 2 and calls nothing; 2.1.325 alone or with "(Claude Code)" matches

  # Backed by: tests/test_code_bench.py::test_a_run_cut_by_the_spend_stop_is_made_again_and_the_analysis_reads_its_final_incarnation
  Scenario: A run cut by the spend stop is made again and the analysis reads its final incarnation
    Given an arm-B run cut by a $2 spend stop after two failed tries at $1 each
    When code runs again with a higher stop and the coder now writes the right code
    Then the public model lines are try 1, try 2, try 1, and the analysis reads the stored run's tries, correct, correct at the first try and finished, a run cost of $1.00, a cut cost of $2.00 and a spend of $3.00
