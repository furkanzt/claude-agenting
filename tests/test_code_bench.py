"""Tests for evals/probes/code_bench.py, the core of the coding experiment's tool (sandboxed test
runner, self-test, trees and overlays, task records, install, records).

The runner tests make REAL sandboxed runs of pytest and node --test on tiny projects in a temp
folder. vitest is not installed: its adapter is tested on hand-written JSON in the format of vitest's
JSON reporter, and one live test runs only when $CODE_BENCH_VITEST_MODULES names a node_modules
folder that holds vitest. Install tests build a toy git project in a temp folder (git -C <tmp>
init/add/commit/config only). No test calls a model, reaches the network, reads evals/private or
writes inside the repository.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The tool is macOS only: every test run goes through /usr/bin/sandbox-exec, and the node tests need node.
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists() or not shutil.which("node"),
    reason="code_bench needs macOS sandbox-exec and node")

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
sys.path.insert(0, str(EVALS))

import evalkit as ev  # noqa: E402

# Red-proof runs point this at a mutated copy, so the real file is never edited.
CB_SRC = Path(os.environ.get("CODE_BENCH_UNDER_TEST") or EVALS / "probes" / "code_bench.py")
_spec = importlib.util.spec_from_file_location("code_bench_under_test", CB_SRC)
cb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cb   # dataclasses look the module up by name
_spec.loader.exec_module(cb)

MARKER = "ZQXMARK7731"
VITEST_MODULES = (os.environ.get("CODE_BENCH_VITEST_MODULES") or "").split(os.pathsep)[0] or None


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def project(tmp_path, files):
    tree = tmp_path / "tree"
    for rel, text in files.items():
        write(tree / rel, text)
    tree.mkdir(parents=True, exist_ok=True)
    return tree


def run(tree, runner, files, names=(), limit=30, **kw):
    return cb.run_tests(tree, runner, ".", files, limit, names, **kw)


# -- pytest, real runs ---------------------------------------------------------------

MOD = "def add(a, b):\n    return a + b\n"


def test_pytest_run_with_passing_tests_is_pass(tmp_path):
    tree = project(tmp_path, {"mod.py": MOD, "tests/test_a.py":
                              "from mod import add\ndef test_one():\n    assert add(1, 2) == 3\n"
                              "def test_two():\n    assert add(0, 0) == 0\n"})
    r = run(tree, "pytest", ["tests/test_a.py"])
    assert (r.result, r.tests, r.failed) == ("pass", 2, 0)
    assert r.seconds > 0


def test_pytest_run_with_a_failing_test_is_fail(tmp_path):
    tree = project(tmp_path, {"mod.py": MOD, "tests/test_a.py":
                              "from mod import add\ndef test_one():\n    assert add(1, 2) == 4\n"
                              "def test_two():\n    assert add(0, 0) == 0\n"})
    r = run(tree, "pytest", ["tests/test_a.py"])
    assert (r.result, r.tests, r.failed) == ("fail", 2, 1)


def test_pytest_file_with_no_tests_or_only_skipped_tests_is_no_tests(tmp_path):
    tree = project(tmp_path, {"tests/test_none.py": "X = 1\n", "tests/test_skip.py":
                              "import pytest\n@pytest.mark.skip\ndef test_s():\n    pass\n"})
    r = run(tree, "pytest", ["tests/test_none.py"])
    assert (r.result, r.tests, r.failed) == ("no_tests", 0, 0)
    r = run(tree, "pytest", ["tests/test_skip.py"])
    assert (r.result, r.tests, r.failed) == ("no_tests", 0, 0)


def test_pytest_import_of_a_listed_name_is_load_error_missing_name(tmp_path):
    tree = project(tmp_path, {"mod.py": MOD, "tests/test_mul.py":
                              "from mod import mul\ndef test_mul():\n    assert mul(2, 3) == 6\n"})
    assert run(tree, "pytest", ["tests/test_mul.py"], names=["mul"]).result == "load_error_missing_name"
    assert run(tree, "pytest", ["tests/test_mul.py"], names=["other"]).result == "load_error"


def test_pytest_missing_module_named_in_the_list_is_load_error_missing_name(tmp_path):
    tree = project(tmp_path, {"tests/test_new.py":
                              "from pkg.newmod import thing\ndef test_t():\n    assert thing\n",
                              "pkg/__init__.py": ""})
    assert run(tree, "pytest", ["tests/test_new.py"], names=["pkg/newmod.py"]).result == \
        "load_error_missing_name"


def test_pytest_syntax_error_is_load_error(tmp_path):
    tree = project(tmp_path, {"tests/test_syn.py": "def test_x(:\n    pass\n"})
    r = run(tree, "pytest", ["tests/test_syn.py"], names=["test_x", "x"])
    assert r.result == "load_error"


def test_pytest_one_file_missing_a_name_and_one_broken_file_is_load_error(tmp_path):
    tree = project(tmp_path, {"mod.py": MOD,
                              "tests/test_mul.py": "from mod import mul\ndef test_m():\n    pass\n",
                              "tests/test_syn.py": "def test_x(:\n    pass\n"})
    r = run(tree, "pytest", ["tests/test_mul.py", "tests/test_syn.py"], names=["mul"])
    assert r.result == "load_error"


def _gone(pid, within=5.0):
    end = time.monotonic() + within
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_pytest_time_out_is_timeout_and_kills_the_whole_process_group(tmp_path):
    tree = project(tmp_path, {"tests/test_slow.py":
                              "import subprocess, sys, time, pathlib\n"
                              "def test_slow():\n"
                              "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                              "    pathlib.Path('child.pid').write_text(str(p.pid))\n"
                              "    time.sleep(120)\n"})
    started = time.monotonic()
    r = run(tree, "pytest", ["tests/test_slow.py"], limit=3)
    assert r.result == "timeout" and r.tests is None and r.failed is None
    assert time.monotonic() - started < 20
    pid = int((tree / "child.pid").read_text())
    assert _gone(pid), "the grandchild survived the time limit"


# -- node --test, real runs ------------------------------------------------------------

LIB = "export function add(a, b) { return a + b; }\n"
NT = "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"


def test_node_run_with_passing_tests_is_pass_and_an_empty_file_adds_no_test(tmp_path):
    tree = project(tmp_path, {"lib.mjs": LIB,
                              "test/a.test.mjs": NT + "import { add } from '../lib.mjs';\n"
                              "test('one', () => assert.equal(add(1, 2), 3));\n"
                              "test('two', () => assert.equal(add(0, 0), 0));\n",
                              "test/empty.test.mjs": NT})
    r = run(tree, "node-test", ["test/a.test.mjs", "test/empty.test.mjs"])
    assert (r.result, r.tests, r.failed) == ("pass", 2, 0)


def test_node_run_with_a_failing_test_is_fail(tmp_path):
    tree = project(tmp_path, {"lib.mjs": LIB,
                              "test/a.test.mjs": NT + "import { add } from '../lib.mjs';\n"
                              "test('one', () => assert.equal(add(1, 2), 4));\n"
                              "test('two', () => assert.equal(add(0, 0), 0));\n"
                              "test.skip('three', () => {});\n"})
    r = run(tree, "node-test", ["test/a.test.mjs"])
    assert (r.result, r.tests, r.failed) == ("fail", 2, 1)


def test_node_file_with_no_tests_is_no_tests(tmp_path):
    tree = project(tmp_path, {"test/empty.test.mjs": NT})
    r = run(tree, "node-test", ["test/empty.test.mjs"])
    assert (r.result, r.tests, r.failed) == ("no_tests", 0, 0)


def test_node_missing_export_or_file_of_a_listed_name_is_load_error_missing_name(tmp_path):
    tree = project(tmp_path, {"lib.mjs": LIB,
                              "test/exp.test.mjs": NT + "import { mul } from '../lib.mjs';\n"
                              "test('m', () => assert.equal(mul(2, 3), 6));\n",
                              "test/file.test.mjs": NT + "import { mul } from '../src/mul.mjs';\n"
                              "test('m', () => assert.equal(mul(2, 3), 6));\n"})
    assert run(tree, "node-test", ["test/exp.test.mjs"], names=["mul"]).result == "load_error_missing_name"
    assert run(tree, "node-test", ["test/exp.test.mjs"], names=["div"]).result == "load_error"
    assert run(tree, "node-test", ["test/file.test.mjs"], names=["src/mul.mjs"]).result == \
        "load_error_missing_name"


def test_node_syntax_error_is_load_error(tmp_path):
    tree = project(tmp_path, {"test/syn.test.mjs": NT + "test('x', () => { (( });\n"})
    r = run(tree, "node-test", ["test/syn.test.mjs"], names=["x"])
    assert r.result == "load_error" and r.tests == 0


def test_node_one_broken_file_beside_a_failing_test_is_load_error(tmp_path):
    tree = project(tmp_path, {"test/syn.test.mjs": NT + "test('x', () => { (( });\n",
                              "test/fail.test.mjs": NT + "test('f', () => assert.equal(1, 2));\n"})
    r = run(tree, "node-test", ["test/syn.test.mjs", "test/fail.test.mjs"])
    assert r.result == "load_error"


def test_node_error_after_tests_ran_is_fail_not_load_error(tmp_path):
    tree = project(tmp_path, {"test/late.test.mjs": NT + "test('ok', () => {});\n"
                              "setTimeout(() => { throw new Error('late'); }, 10);\n"})
    r = run(tree, "node-test", ["test/late.test.mjs"])
    assert (r.result, r.tests, r.failed) == ("fail", 2, 1)


def test_node_time_out_is_timeout(tmp_path):
    tree = project(tmp_path, {"test/slow.test.mjs": NT +
                              "test('slow', async () => { await new Promise(r => setTimeout(r, 120000)); });\n"})
    started = time.monotonic()
    r = run(tree, "node-test", ["test/slow.test.mjs"], limit=3)
    assert r.result == "timeout"
    assert time.monotonic() - started < 20


def test_runner_runs_in_test_cwd_with_tree_relative_files(tmp_path):
    tree = project(tmp_path, {"web/lib.mjs": LIB, "web/package.json": '{"type": "module"}\n',
                              "web/test/a.test.mjs": NT + "import { add } from '../lib.mjs';\n"
                              "import fs from 'node:fs';\n"
                              "test('cwd', () => assert.ok(fs.existsSync('package.json')));\n"})
    r = cb.run_tests(tree, "node-test", "web", ["web/test/a.test.mjs"], 30, ())
    assert (r.result, r.tests) == ("pass", 1)


# -- vitest: the JSON reporter format, and one live run --------------------------------

def vjson(results, success=None):
    n_failed = sum(1 for r in results for a in r.get("assertionResults", []) if a["status"] == "failed")
    return json.dumps({
        "numTotalTestSuites": len(results), "numPassedTestSuites": 0, "numFailedTestSuites": 0,
        "numPendingTestSuites": 0, "numTotalTests": 0, "numPassedTests": 0, "numFailedTests": n_failed,
        "numPendingTests": 0, "numTodoTests": 0, "startTime": 1731600000000,
        "success": (n_failed == 0) if success is None else success, "testResults": results})


def assertion(title, status, messages=()):
    return {"ancestorTitles": ["mul"], "fullName": f"mul {title}", "status": status, "title": title,
            "duration": 1, "failureMessages": list(messages), "meta": {}}


def file_result(name, status, asserts, message=""):
    return {"assertionResults": asserts, "startTime": 1731600000000, "endTime": 1731600000100,
            "status": status, "message": message, "name": name}


def test_vitest_json_with_passing_tests_is_pass():
    j = vjson([file_result("/w/tree/src/mul.test.ts", "passed",
                           [assertion("a", "passed"), assertion("b", "passed"), assertion("c", "skipped")])])
    p = cb.parse_vitest_json(0, j, "", ["mul"])
    assert (p.result, p.tests, p.failed) == ("pass", 2, 0)


def test_vitest_json_with_a_failing_test_is_fail():
    j = vjson([file_result("/w/tree/src/mul.test.ts", "failed",
                           [assertion("a", "passed"), assertion("b", "failed", ["AssertionError: 5 != 6"])])])
    p = cb.parse_vitest_json(1, j, "", ["mul"])
    assert (p.result, p.tests, p.failed) == ("fail", 2, 1)
    assert "5 != 6" in p.detail


def test_vitest_json_no_test_suite_found_is_no_tests():
    j = vjson([file_result("/w/tree/src/empty.test.ts", "failed", [],
                           "No test suite found in file /w/tree/src/empty.test.ts")], success=False)
    p = cb.parse_vitest_json(1, j, "", ["mul"])
    assert (p.result, p.tests, p.failed) == ("no_tests", 0, 0)


def test_vitest_json_failed_import_of_a_listed_name_is_load_error_missing_name():
    j = vjson([file_result("/w/tree/src/mul.test.ts", "failed", [],
                           'Failed to resolve import "./mul" from "src/mul.test.ts". Does the file exist?')],
              success=False)
    assert cb.parse_vitest_json(1, j, "", ["mul"]).result == "load_error_missing_name"
    assert cb.parse_vitest_json(1, j, "", ["div"]).result == "load_error"


def test_vitest_json_failed_file_for_another_reason_is_load_error():
    j = vjson([file_result("/w/tree/src/a.test.ts", "failed", [],
                           'Transform failed with 1 error:\n/w/tree/src/a.test.ts:3:10: ERROR: Expected ")" '
                           'but found "}"'),
               file_result("/w/tree/src/b.test.ts", "failed", [assertion("b", "failed", ["x"])])],
              success=False)
    assert cb.parse_vitest_json(1, j, "", ["mul"]).result == "load_error"


def test_vitest_error_outside_tests_with_all_tests_passing_is_fail():
    j = vjson([file_result("/w/tree/src/a.test.ts", "passed", [assertion("a", "passed")])], success=False)
    p = cb.parse_vitest_json(1, j, "Unhandled Rejection", ["mul"])
    assert (p.result, p.tests) == ("fail", 1)
    j = vjson([file_result("/w/tree/src/a.test.ts", "failed", [assertion("a", "passed")],
                           "Error: afterAll hook failed")], success=False)
    assert cb.parse_vitest_json(1, j, "", ["mul"]).result == "fail"


def test_vitest_without_a_json_file_is_no_tests_or_load_error():
    assert cb.parse_vitest_json(1, None, "No test files found, exiting with code 1", []).result == "no_tests"
    assert cb.parse_vitest_json(1, None, "Error: failed to load config", []).result == "load_error"


def test_vitest_without_a_vitest_binary_is_check_infra(tmp_path):
    tree = project(tmp_path, {"src/a.test.ts": "import { test } from 'vitest'\ntest('a', () => {})\n"})
    r = run(tree, "vitest", ["src/a.test.ts"])
    assert r.result == "check_infra"


@pytest.mark.skipif(not (VITEST_MODULES and (Path(VITEST_MODULES) / ".bin" / "vitest").exists()),
                    reason="no vitest binary reachable ($CODE_BENCH_VITEST_MODULES)")
def test_vitest_live_run_maps_pass_fail_and_missing_name(tmp_path):
    tree = project(tmp_path, {"package.json": '{"type": "module", "private": true}\n',
                              "lib.mjs": LIB,
                              "a.test.mjs": "import { test, expect } from 'vitest';\nimport { add } from './lib.mjs';\n"
                              "test('a', () => expect(add(1, 2)).toBe(3));\n",
                              "b.test.mjs": "import { test, expect } from 'vitest';\nimport { add } from './lib.mjs';\n"
                              "test('b', () => expect(add(1, 2)).toBe(4));\n",
                              "c.test.mjs": "import { test, expect } from 'vitest';\nimport { mul } from './mul.mjs';\n"
                              "test('c', () => expect(mul(2, 3)).toBe(6));\n"})
    cb.clone_node_modules(Path(VITEST_MODULES), tree / "node_modules")
    assert run(tree, "vitest", ["a.test.mjs"], limit=60).result == "pass"
    assert run(tree, "vitest", ["b.test.mjs"], limit=60).result == "fail"
    assert run(tree, "vitest", ["c.test.mjs"], names=["mul.mjs"], limit=60).result == "load_error_missing_name"


# -- the sandbox ----------------------------------------------------------------------------

def test_the_test_sees_only_the_minimal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("NODE_OPTIONS", "--require=/nonexistent.js")
    monkeypatch.setenv("CODE_BENCH_SECRET", "s3cret")
    tree = project(tmp_path, {"tests/test_env.py":
                              "import os, pathlib\n"
                              f"REAL_HOME = {str(cb.real_home())!r}\n"
                              "def test_env():\n"
                              "    e = os.environ\n"
                              "    assert 'NODE_OPTIONS' not in e and 'CODE_BENCH_SECRET' not in e\n"
                              "    assert e['CI'] == '1' and e['PYTHONDONTWRITEBYTECODE'] == '1'\n"
                              "    assert e['HOME'] == e['TMPDIR'].rstrip('/') and e['HOME'] != REAL_HOME\n"
                              "    assert set(e['PATH'].split(':')) >= {'/usr/bin', '/bin'}\n"
                              "    pathlib.Path(e['HOME'], 'scratch.txt').write_text('ok')\n"
                              "    pathlib.Path('in-tree.txt').write_text('ok')\n"})
    r = run(tree, "pytest", ["tests/test_env.py"])
    assert (r.result, r.tests) == ("pass", 1), r.detail
    assert (tree / "in-tree.txt").exists()


def test_a_refused_sandbox_profile_is_check_infra(tmp_path):
    tree = project(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n", "a.test.mjs": NT})
    bad = lambda dirs, home: "(version 1)(allow default"  # noqa: E731
    assert run(tree, "pytest", ["tests/test_a.py"], profile_fn=bad).result == "check_infra"
    assert run(tree, "node-test", ["a.test.mjs"], profile_fn=bad).result == "check_infra"


def test_a_missing_runner_binary_is_check_infra(tmp_path):
    tree = project(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n", "a.test.mjs": NT})
    assert run(tree, "pytest", ["tests/test_a.py"],
               tools=cb.Tools(python="/nonexistent/python3", node=None)).result == "check_infra"
    assert run(tree, "node-test", ["a.test.mjs"],
               tools=cb.Tools(python=sys.executable, node=None)).result == "check_infra"


def test_detail_is_the_tail_of_the_output_capped(tmp_path):
    tree = project(tmp_path, {"tests/test_long.py":
                              "def test_long():\n    print('x' * 20000)\n    print('END-' + 'OF-RUN')\n"
                              "    assert False\n"})
    r = run(tree, "pytest", ["tests/test_long.py"])
    assert r.result == "fail"
    assert len(r.detail) <= cb.DETAIL_MAX and "END-OF-RUN" in r.detail   # printed last, after the x's


# -- selftest ---------------------------------------------------------------------------------

def open_network(dirs, home):
    return cb.sandbox_profile(dirs, home).replace("(deny network*)\n", "")


def open_writes(dirs, home):
    return cb.sandbox_profile(dirs, home).replace("(deny file-write*)\n", "")


def test_selftest_passes_with_the_real_sandbox(tmp_path):
    rep = cb.selftest(tmp_path / "work")
    assert rep["pytest"] == "pass" and rep["node-test"] == "pass" and rep["ok"] is True
    assert rep["vitest"] == "skipped" or VITEST_MODULES


def test_selftest_fails_closed_when_a_canary_test_did_not_run(tmp_path, monkeypatch):
    cut = cb.PY_CANARY.index("def test_reading_the_home_folder_is_refused")
    monkeypatch.setattr(cb, "PY_CANARY", cb.PY_CANARY[:cut])
    rep = cb.selftest(tmp_path / "work")
    assert rep["pytest"] == "wrong_count" and rep["node-test"] == "pass" and rep["ok"] is False


def test_selftest_fails_closed_when_the_network_is_open(tmp_path):
    rep = cb.selftest(tmp_path / "work", profile_fn=open_network)
    assert rep["pytest"] == "fail" and rep["node-test"] == "fail" and rep["ok"] is False


def test_selftest_fails_closed_when_writes_outside_are_allowed(tmp_path):
    rep = cb.selftest(tmp_path / "work", profile_fn=open_writes)
    assert rep["pytest"] == "escaped" and rep["node-test"] == "escaped" and rep["ok"] is False


def test_selftest_command_prints_words_and_exits_by_the_verdict(tmp_path, capsys):
    args = ["selftest", "--work", str(tmp_path / "w"), "--root", str(tmp_path / "root"),
            "--evals-dir", str(tmp_path / "evals")]
    assert cb.main(args) == 0
    assert capsys.readouterr().out.strip() == "selftest: pytest pass, node-test pass, vitest skipped: ok"
    app = cb.make_app(cb.build_parser().parse_args(args))
    app.profile_fn = open_network
    assert cb.main(args, app=app) == 1
    assert "FAILED" in capsys.readouterr().out
    assert not (tmp_path / "root").exists() and not (tmp_path / "evals").exists()


# -- trees, copies, overlays ------------------------------------------------------------------

def test_clone_tree_copy_is_independent_of_its_source(tmp_path):
    src = project(tmp_path, {"a.txt": "one", "sub/b.txt": "two"})
    dst = tmp_path / "copy"
    cb.clone_tree(src, dst)
    (dst / "a.txt").write_text("changed")
    (dst / "new.txt").write_text("new")
    assert (src / "a.txt").read_text() == "one" and not (src / "new.txt").exists()
    assert (dst / "sub/b.txt").read_text() == "two"


def test_make_copy_applies_deletions_overlay_files_and_node_modules(tmp_path):
    start = project(tmp_path, {"a.txt": "one", "gone.txt": "bye", "node_modules/stale/x.js": "old"})
    nm = tmp_path / "nm"
    write(nm / "pkg/index.js", "export default 1;\n")
    src_file = tmp_path / "from_disk.txt"
    write(src_file, "disk")
    copy = cb.make_copy(tmp_path / "work", start, {"a.txt": b"two", "new/b.txt": src_file},
                        deleted=["gone.txt"], node_modules={"from": str(nm), "to": "node_modules"})
    assert (copy / "a.txt").read_text() == "two" and (copy / "new/b.txt").read_text() == "disk"
    assert not (copy / "gone.txt").exists()
    assert (copy / "node_modules/pkg/index.js").exists() and not (copy / "node_modules/stale").exists()
    assert (start / "a.txt").read_text() == "one" and (start / "gone.txt").exists()
    cb.drop_copy(copy)
    assert not copy.exists() and not copy.parent.exists()


def test_overlay_of_lists_changed_new_and_deleted_files_and_ignores_caches(tmp_path):
    start = project(tmp_path, {"a.py": "one", "b.py": "same", "c.py": "gone"})
    copy = tmp_path / "copy"
    cb.clone_tree(start, copy)
    (copy / "a.py").write_text("two")
    (copy / "c.py").unlink()
    write(copy / "tests/test_new.py", "new")
    for junk in ("__pycache__/a.pyc", "tests/__pycache__/t.pyc", ".pytest_cache/v", "node_modules/x/i.js",
                 ".vite/deps.json", ".vitest/results.json", "web/node_modules/y.js"):
        write(copy / junk, "junk")
    ov = cb.overlay_of(copy, start)
    assert sorted(ov.files) == ["a.py", "tests/test_new.py"]
    assert ov.deleted == ("c.py",) and ov.symlinks_ignored == 0
    assert cb.overlay_contents(copy, ov)["a.py"] == b"two"


def test_overlay_of_ignores_and_counts_symlinks_the_copy_added(tmp_path):
    start = project(tmp_path, {"a.py": "one", "old_link_target.py": "t"})
    os.symlink("old_link_target.py", start / "kept_link.py")
    copy = tmp_path / "copy"
    cb.clone_tree(start, copy)
    os.symlink("/etc/hosts", copy / "evil.py")
    os.symlink("a.py", copy / "alias.py")
    os.symlink("/tmp", copy / "dirlink")
    ov = cb.overlay_of(copy, start)
    assert ov.files == {} and ov.deleted == () and ov.symlinks_ignored == 3


def test_matches_patterns_uses_whole_path_globs():
    assert cb.matches_patterns("tests/test_a.py", ["tests/**/*.py"])
    assert cb.matches_patterns("tests/x/y/test_a.py", ["tests/**/*.py"])
    assert cb.matches_patterns("a.test.ts", ["**/*.test.ts"])
    assert cb.matches_patterns("web/src/a.test.ts", ["**/*.test.ts"])
    assert cb.matches_patterns("web/src/__tests__/fixtures/data.json", ["web/src/**/__tests__/**"])
    assert not cb.matches_patterns("src/a.py", ["*.py"])
    assert not cb.matches_patterns("src/test_a.py", ["tests/**/*.py"])
    assert cb.matches_patterns("tests/x/test_a.py", ["tests/"]) and cb.matches_patterns("tests/a.py", ["tests/"])
    assert not cb.matches_patterns("tests", ["tests/"]) and not cb.matches_patterns("mytests/a.py", ["tests/"])


def test_source_unchanged_only_when_every_changed_path_is_a_test_path():
    pats = ["tests/**"]
    assert cb.source_unchanged(cb.Overlay({"tests/test_a.py": "h"}, ("tests/old.py",), 0), pats)
    assert cb.source_unchanged(cb.Overlay({}, (), 2), pats)
    assert not cb.source_unchanged(cb.Overlay({"tests/test_a.py": "h", "mod.py": "h"}, (), 0), pats)
    assert not cb.source_unchanged(cb.Overlay({"tests/test_a.py": "h"}, ("mod.py",), 0), pats)


# -- missing names, red words, time limits -------------------------------------------------------

def test_missing_name_matching_rules():
    assert cb.missing_name_in("E   ImportError: cannot import name 'mul' from 'mod'", ["mul"])
    assert cb.missing_name_in("ModuleNotFoundError: No module named 'pkg.newmod'", ["pkg/newmod.py"])
    assert cb.missing_name_in("ModuleNotFoundError: No module named 'pkg.newmod'", ["newmod"])
    assert cb.missing_name_in("AttributeError: module 'mod' has no attribute 'LIMIT'", ["LIMIT"])
    assert cb.missing_name_in("FileNotFoundError: [Errno 2] No such file or directory: "
                              "'/t/tree/data/levels.json'", ["data/levels.json"])
    assert cb.missing_name_in("SyntaxError: The requested module '../lib.mjs' does not provide an "
                              "export named 'mul'", ["mul"])
    assert cb.missing_name_in("Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/t/tree/src/mul.ts' "
                              "imported from /t/tree/test/a.test.ts", ["src/mul.ts"])
    assert cb.missing_name_in("TypeError: Cannot read properties of undefined (reading 'sumOfParts')",
                              ["sumOfParts"])
    assert cb.missing_name_in("TypeError: (0 , _mod.sumOfParts) is not a function", ["sumOfParts"])
    assert not cb.missing_name_in("SyntaxError: Unexpected identifier 'mul'", ["mul"])
    assert not cb.missing_name_in("ImportError: cannot import name 'multiply' from 'mod'", ["mul"])
    assert not cb.missing_name_in("ImportError: cannot import name 'mul' from 'mod'", [])


def test_red_on_start_is_fail_timeout_or_load_error_missing_name():
    assert {w for w in cb.RESULT_WORDS if cb.is_red(w)} == {"fail", "timeout", "load_error_missing_name"}
    assert not cb.is_red("locked_changed")


def test_time_limit_is_five_times_the_reference_between_20_and_60_seconds():
    assert cb.time_limit_for(1.0) == 20.0
    assert cb.time_limit_for(6.0) == 30.0
    assert cb.time_limit_for(30.0) == 60.0


# -- task records ----------------------------------------------------------------------------------

def record(code="code-01", **over):
    rec = {"code": code, "project_dir": "/abs/project", "before": "a" * 40, "after": "b" * 40,
           "language": "python", "rating": "easy", "runner": "pytest", "test_cwd": ".",
           "hidden_tests": ["tests/test_mul.py"], "run_files": ["tests/test_mul.py"],
           "test_patterns": ["tests/**"], "runner_config": [], "source_files": ["mod.py"],
           "names": ["mul"], "node_modules": None, "strip": [], "brief": f"briefs/{code}.md"}
    rec.update(over)
    return rec


@pytest.mark.parametrize("over", [
    {"code": "task-1"}, {"project_dir": "relative/path"}, {"before": "abc123"}, {"runner": "jest"},
    {"language": "go"}, {"rating": "trivial"}, {"test_cwd": "../up"},
    {"hidden_tests": ["/abs/test.py"]}, {"hidden_tests": ["tests/../../x.py"]},
    {"run_files": ["tests/other.py"]}, {"source_files": []}, {"names": []},
    {"node_modules": {"from": "rel/nm", "to": "node_modules"}},
    {"node_modules": {"from": "/abs/nm", "to": "../nm"}}, {"strip": ["../x"]},
])
def test_task_records_with_a_bad_field_are_refused(over):
    with pytest.raises(cb.BenchError) as e:
        cb.validate_task(record(**over))
    assert e.value.word == "task_invalid"


def test_a_good_task_record_is_accepted():
    t = cb.validate_task(record(runner="vitest", language="typescript", test_cwd="web",
                                node_modules={"from": "/abs/nm", "to": "web/node_modules"}))
    assert t.code == "code-01" and t.runner == "vitest" and t.node_modules["to"] == "web/node_modules"
    assert t.names == ("mul",) and isinstance(t.project_dir, Path)


# -- install on a toy git project ------------------------------------------------------------------

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_TERMINAL_PROMPT="0")


def tgit(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=GIT_ENV, stdin=subprocess.DEVNULL).stdout.decode().strip()


def commit(repo, files, deleted=(), msg="c"):
    for rel, text in files.items():
        write(repo / rel, text)
    for rel in deleted:
        (repo / rel).unlink()
    tgit(repo, "add", "-A")
    tgit(repo, "commit", "-q", "-m", msg)
    return tgit(repo, "rev-parse", "HEAD")


MUL_TEST = (f"import mod\n\ndef test_mul_{MARKER}():\n    print('out-{MARKER}')\n"
            f"    assert getattr(mod, 'mul', None) is not None, 'msg-{MARKER}'\n"
            "    assert mod.mul(2, 3) == 6\n")


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    """A git project with: c0 (before), c1 (adds mul, deletes legacy.py, adds its test), c2 (a wrong mul)."""
    repo = tmp_path_factory.mktemp("toy") / f"proj-{MARKER}"
    repo.mkdir()
    tgit(repo, "init", "-q")
    tgit(repo, "config", "commit.gpgsign", "false")
    c0 = commit(repo, {
        "mod.py": MOD, "legacy.py": "OLD = 1\n",
        "tests/test_add.py": "from mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        "CLAUDE.md": "Plan: add mul to mod.py\n", "pkg/CLAUDE.md": "mul\n", "pkg/__init__.py": "",
        "docs/plan.md": "mul will multiply\n", ".github/workflows/ci.yml": "run: mul\n",
        ".claude/settings.json": '{"mul": 1}\n', "AGENTS.md": "mul\n",
        "notes/LEAK.txt": "LEAKY_NAME is coming\n", "scripts/notes.txt": "the mul plan\n"})
    c1 = commit(repo, {"mod.py": MOD + "\n\ndef mul(a, b):\n    return a * b\n",
                       "tests/test_mul.py": MUL_TEST}, deleted=["legacy.py"])
    c2 = commit(repo, {"mod.py": MOD + "\n\ndef mul(a, b):\n    return a - b\n"})
    return {"repo": repo, "c0": c0, "c1": c1, "c2": c2}


def toy_task(toy, code="code-01", **over):
    rec = record(code, project_dir=str(toy["repo"]), before=toy["c0"], after=toy["c1"],
                 source_files=["mod.py", "legacy.py"], strip=["scripts/notes.txt"])
    rec.update(over)
    return rec


class Bench:
    def __init__(self, tmp_path, tasks, briefs=None):
        self.tmp = tmp_path
        self.root = tmp_path / "root"
        self.results = tmp_path / "results" / "code-runs.jsonl"
        self.evals = tmp_path / "evals"
        self.work = tmp_path / "work"
        write(self.root / "tasks.json", json.dumps({"tasks": tasks}))
        for t in tasks:
            write(self.root / t["brief"], (briefs or {}).get(t["code"], f"Brief {MARKER}: add mul.\n"))

    def args(self, *extra):
        return ["install", "--root", str(self.root), "--results", str(self.results),
                "--evals-dir", str(self.evals), "--work", str(self.work), *extra]

    def install(self, *extra, app_hook=None):
        args = self.args(*extra)
        app = cb.make_app(cb.build_parser().parse_args(args))
        if app_hook:
            app_hook(app)
        return cb.main(args, app=app)

    def public(self):
        return ev.read_jsonl(self.results)

    def private(self):
        return ev.read_jsonl(self.root / "attempts.jsonl")

    def installed(self, code="code-01"):
        return json.loads((self.root / "tasks" / code / "installed.json").read_text())

    def tdir(self, code="code-01"):
        return self.root / "tasks" / code


def test_install_builds_start_reference_hidden_and_passes_a_good_task(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install() == 0
    out = capsys.readouterr().out
    assert "code-01 install: ok (start fail, reference pass 3/3, 1 tests" in out
    td = b.tdir()
    assert (td / "start/mod.py").read_text() == MOD and (td / "start/legacy.py").exists()
    assert "def mul" in (td / "reference/mod.py").read_text() and not (td / "reference/legacy.py").exists()
    assert (td / "hidden/tests/test_mul.py").read_text() == MUL_TEST
    assert not (td / "start/tests/test_mul.py").exists()
    info = b.installed()
    assert info["ok"] is True and info["reason"] is None and info["reference_passes"] == 3
    assert info["start_result"] == "fail" and info["names_added"] == 1
    assert 20.0 <= info["time_limit_s"] <= 60.0 and len(info["task_hash"]) == 64
    lines = b.public()
    assert [(x["what"], x["run"], x["result"]) for x in lines] == [
        ("install_start", 1, "fail"), ("install_reference", 1, "pass"),
        ("install_reference", 2, "pass"), ("install_reference", 3, "pass")]
    assert all(x["step"] == "install" and x["task"] == "code-01" and x["tests"] == 1 for x in lines)


def test_install_strips_the_fixed_list_and_the_task_strip_list(tmp_path, toy):
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install() == 0
    start = b.tdir() / "start"
    for gone in ("CLAUDE.md", "pkg/CLAUDE.md", "AGENTS.md", "docs", ".github", ".claude", "scripts/notes.txt"):
        assert not (start / gone).exists(), gone
    assert (start / "notes/LEAK.txt").exists() and (start / "pkg/__init__.py").exists()


def test_install_fails_a_task_whose_hidden_tests_are_not_red_on_start(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, hidden_tests=["tests/test_add.py"], run_files=["tests/test_add.py"])])
    assert b.install() == 1
    assert "code-01 install: failed start_not_red" in capsys.readouterr().out
    assert b.installed()["ok"] is False and b.installed()["reason"] == "start_not_red"
    assert [(x["what"], x["result"]) for x in b.public()] == [("install_start", "pass")]


def test_install_fails_a_task_whose_reference_does_not_pass(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, after=toy["c2"], source_files=["mod.py"])])
    assert b.install() == 1
    assert "code-01 install: failed reference_fails" in capsys.readouterr().out
    assert [(x["what"], x["result"]) for x in b.public()] == [("install_start", "fail"),
                                                              ("install_reference", "fail")]


def test_install_fails_a_task_that_leaks_an_added_name(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, names=["mul", "LEAKY_NAME"])])
    assert b.install() == 1
    out = capsys.readouterr().out
    assert "code-01 install: failed leak" in out and "LEAKY" not in out
    assert b.public() == []
    note = [x for x in b.private() if x.get("event") == "leak"]
    assert note and "LEAKY_NAME in notes/LEAK.txt" in note[0]["detail"]


def test_install_without_the_task_strip_list_finds_the_leak_it_hides(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, strip=[])])
    assert b.install() == 1
    assert "code-01 install: failed leak" in capsys.readouterr().out


def test_leak_check_ignores_names_the_before_source_already_has(tmp_path):
    tree = project(tmp_path, {"README.txt": "add and mul and multiply_all\n"})
    assert cb.added_names(["add", "mul", "div"], [MOD.encode()]) == ["mul", "div"]
    assert cb.find_leaks(tree, ["div"]) == []
    assert cb.find_leaks(tree, ["mul"]) == [("mul", "README.txt")]
    assert cb.find_leaks(tree, ["multiply"]) == []


def test_leak_check_reads_the_path_of_a_file_too(tmp_path):
    tree = project(tmp_path, {"lib/fancy_newthing.py": "x = 1\n", "notes/readme.txt": "nothing\n",
                              "newmod/data.json": "{}\n", "src/other_newmod.py": "y = 2\n"})
    assert cb.find_leaks(tree, ["fancy_newthing.py"]) == [("fancy_newthing.py", "lib/fancy_newthing.py (its path)")]
    assert cb.find_leaks(tree, ["readme"]) == [("readme", "notes/readme.txt (its path)")]
    assert cb.find_leaks(tree, ["newmod"]) == [("newmod", "newmod/data.json (its path)")]   # a folder name
    assert cb.find_leaks(tree, ["thing"]) == []                                             # whole tokens only


def test_install_fails_a_task_with_a_source_file_that_neither_commit_has(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, source_files=["mod.py", "legacy.py", "no_such_file.py"])])
    assert b.install() == 1
    assert "code-01 install: failed task_invalid" in capsys.readouterr().out
    assert b.installed()["ok"] is False and b.installed()["reason"] == "task_invalid"
    assert b.public() == []


def test_the_fixed_strip_files_go_in_any_letter_case(tmp_path):
    tree = project(tmp_path, {"Changelog.md": "mul\n", "pkg/changelog.md": "mul\n", "pkg/claude.MD": "x\n",
                              "pkg/changelog.md.txt": "kept\n", "mod.py": MOD})
    task = cb.validate_task(record(strip=[]))
    removed = cb.strip_tree(tree, task)
    assert sorted(removed) == ["Changelog.md", "pkg/changelog.md", "pkg/claude.MD"]
    assert (tree / "pkg/changelog.md.txt").exists() and (tree / "mod.py").exists()


def test_a_trial_root_keeps_its_record_beside_it(tmp_path):
    parse = cb.build_parser().parse_args
    trial = cb.make_app(parse(["status", "--root", str(tmp_path / "trial")]))
    assert trial.results == (tmp_path / "trial").resolve() / "code-runs.jsonl"
    named = cb.make_app(parse(["status", "--root", str(tmp_path / "trial"), "--results", str(tmp_path / "r.jsonl")]))
    assert named.results == (tmp_path / "r.jsonl").resolve()
    default = cb.make_app(parse(["status"]))
    evals = cb.HERE.parent
    assert default.results == evals / "results" / "code-runs.jsonl" and default.root == evals / "private" / "code"


def test_a_command_with_the_lock_removes_what_a_killed_invocation_left(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])
    write(b.work / "copy-old1" / "tree" / "mod.py", "left behind\n")
    write(b.work / "snap-old2" / "tree" / "mod.py", "left behind\n")
    write(b.work / "selftest-other" / "x.txt", "another command's folder\n")
    write(b.work / "copy-not-a-folder", "a file\n")
    assert b.install() == 0
    assert not (b.work / "copy-old1").exists() and not (b.work / "snap-old2").exists()
    assert (b.work / "selftest-other" / "x.txt").exists() and (b.work / "copy-not-a-folder").exists()


def test_a_test_file_whose_name_starts_with_a_dash_is_run_as_a_file(tmp_path):
    tree = project(tmp_path, {"mod.py": MOD, "-x_test.py":
                              "from mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"})
    r = run(tree, "pytest", ["-x_test.py"])
    assert (r.result, r.tests, r.failed) == ("pass", 1, 0)
    # node's own test runner starts the file as `node -y.test.mjs` ("bad option"): it reads as not loaded
    write(tree / "-y.test.mjs", "import test from 'node:test';\ntest('ok', () => {});\n")
    assert run(tree, "node-test", ["-y.test.mjs"]).result == "load_error"


def test_install_refuses_a_missing_strip_entry(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, strip=["no/such/file.txt"])])
    assert b.install() == 1
    assert "code-01 install: failed strip_missing" in capsys.readouterr().out


def test_install_refuses_to_run_when_the_selftest_fails(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])

    def hook(app):
        app.profile_fn = open_network
    assert b.install(app_hook=hook) == 2
    assert capsys.readouterr().err.strip() == "code_bench: error: selftest_failed"
    assert not b.tdir().exists() and b.public() == []


def test_install_with_an_invalid_task_record_prints_task_invalid_and_the_code(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy, runner="jest")])
    assert b.install() == 2
    assert capsys.readouterr().err.strip() == "code_bench: error: task_invalid code-01"


def test_install_takes_evalkits_exclusive_lock(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])
    with ev.exclusive_lock(b.evals / "results" / ".evalkit.lock"):
        assert b.install() == 2
    assert capsys.readouterr().err.strip() == "code_bench: error: locked"
    assert not b.tdir().exists()


def test_install_runs_git_only_with_read_only_subcommands(tmp_path, toy, monkeypatch):
    seen = []
    real = cb.git

    def spy(project_dir, *args, **kw):
        seen.append(args[0])
        return real(project_dir, *args, **kw)
    monkeypatch.setattr(cb, "git", spy)
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install() == 0
    assert set(seen) <= {"archive", "show", "cat-file", "rev-parse", "ls-tree"} and "archive" in seen
    for bad in ("checkout", "reset", "stash", "clean", "restore", "worktree", "rm", "switch"):
        with pytest.raises(ValueError):
            cb.git(toy["repo"], bad)


# -- records and privacy ---------------------------------------------------------------------------

def check_line(**over):
    line = {"kind": "check", "step": "install", "task": "code-01", "cell": None, "arm": None, "run": 1,
            "try": None, "what": "install_start", "suite": None, "result": "fail", "tests": 1,
            "failed": 1, "seconds": 0.5, "ts": "2026-11-14T18:00:00Z"}
    line.update(over)
    return line


@pytest.mark.parametrize("over", [
    {"what": "install_start /private/x"}, {"result": "FAILED test_mul"}, {"task": "proj-x"},
    {"cell": "sonnet 5.5"}, {"suite": "../x"}, {"step": "deploy"}, {"seconds": [1, 2]},
    {"detail": "x"}, {"ts": "yesterday"},
])
def test_public_line_refuses_text_unknown_keys_and_unknown_words(over):
    with pytest.raises(ValueError):
        cb.public_line(check_line(**over))


def test_public_line_accepts_fixed_words_and_numbers():
    assert cb.public_line(check_line())["result"] == "fail"
    assert cb.public_line(check_line(step="C", cell="haiku-5-5@high", arm="B",
                                     what="given", suite="sonnet-5-5@high#1", result="locked_changed"))


def test_model_line_builder_writes_the_fixed_keys_and_keeps_detail_private(tmp_path):
    rec = cb.Records(tmp_path / "pub.jsonl", tmp_path / "priv.jsonl")
    rec.model({"step": "T", "task": "code-02", "cell": "opus-5-5@medium", "arm": None, "run": 1,
               "try": 2, "attempt": 1, "valid": True, "reason": None, "infra": False, "cost_usd": 0.41,
               "cost_unknown": False, "duration_ms": 1200, "input_tokens": 10, "output_tokens": 5,
               "cache_read_tokens": 0, "num_turns": 3, "denials": 0, "files_changed": 2,
               "files_dropped": 1, "cli_version": "2.1.325"}, detail=f"stderr {MARKER}")
    pub = ev.read_jsonl(tmp_path / "pub.jsonl")[0]
    assert set(pub) == set(cb.MODEL_KEYS) and pub["kind"] == "model" and pub["files_dropped"] == 1
    assert MARKER not in (tmp_path / "pub.jsonl").read_text()
    assert ev.read_jsonl(tmp_path / "priv.jsonl")[0]["detail"] == f"stderr {MARKER}"
    short = rec.model({"step": "C", "task": "code-03", "cell": "haiku-5-5@high", "arm": "B", "run": 2,
                       "valid": False, "reason": "spawn_failed"})
    assert set(short) == set(cb.MODEL_KEYS) and short["cost_usd"] is None
    with pytest.raises(ValueError):
        rec.model({"step": "T", "task": "code-02", "reason": "the API said no"})
    with pytest.raises(ValueError):
        rec.model({"step": "T", "task": "code-02", "prompt": "a private brief"})


def test_no_path_name_or_output_text_reaches_the_public_file_or_the_terminal(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install() == 0
    shown = capsys.readouterr()
    public = b.results.read_text()
    for text in (public, shown.out, shown.err):
        assert MARKER not in text
        assert str(tmp_path) not in text and "/private/" not in text and "test_mul" not in text
    private = (b.root / "attempts.jsonl").read_text()
    assert f"out-{MARKER}" in private and f"msg-{MARKER}" in private and f"test_mul_{MARKER}" in private


def test_an_unexpected_exception_prints_a_code_word_and_the_task_only(tmp_path, toy, monkeypatch, capsys):
    real = cb.build_task_trees

    def boom(task, root):
        if task.code == "code-01":
            raise RuntimeError(f"broken at {toy['repo']} {MARKER}")
        return real(task, root)
    monkeypatch.setattr(cb, "build_task_trees", boom)
    b = Bench(tmp_path, [toy_task(toy), toy_task(toy, "code-02")])
    assert b.install() == 1
    shown = capsys.readouterr()
    assert "code-01 install: failed internal" in shown.out and "code-02 install: ok" in shown.out
    assert MARKER not in shown.out + shown.err and "Traceback" not in shown.out + shown.err
    assert b.installed("code-01")["ok"] is False and b.installed("code-01")["reason"] == "internal"
    notes = [x for x in b.private() if x.get("event") == "internal"]
    assert notes and "Traceback" in notes[0]["detail"] and MARKER in notes[0]["detail"]

    def boom_early(root):
        raise RuntimeError(f"broken at {toy['repo']} {MARKER}")
    monkeypatch.setattr(cb, "load_tasks", boom_early)
    assert b.install() == 2
    shown = capsys.readouterr()
    assert shown.err.strip() == "code_bench: error: internal"
    assert MARKER not in shown.out + shown.err and "Traceback" not in shown.out + shown.err


# == fixes after the independent check ===============================================================

def test_vitest_2_missing_relative_import_is_load_error_missing_name():
    msg = ("Failed to load url ./newmod.js (resolved id: ./newmod.js) in /w/tree/src/a.test.js. "
           "Does the file exist?")
    j = vjson([file_result("/w/tree/src/a.test.js", "failed", [], msg)], success=False)
    assert cb.parse_vitest_json(1, j, "", ["newmod"]).result == "load_error_missing_name"
    assert cb.parse_vitest_json(1, j, "", ["src/newmod.js"]).result == "load_error_missing_name"
    assert cb.parse_vitest_json(1, j, "", ["other"]).result == "load_error"


def test_an_empty_file_list_is_no_tests_and_starts_no_runner(tmp_path, monkeypatch):
    tree = project(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n"})

    def never(*a, **k):
        raise AssertionError("a runner was started")
    monkeypatch.setattr(cb, "spawn_sandboxed", never)
    for runner in cb.RUNNERS:
        r = run(tree, runner, [])
        assert (r.result, r.tests, r.failed) == ("no_tests", 0, 0)


def test_a_requested_test_file_that_does_not_exist_is_load_error(tmp_path):
    tree = project(tmp_path, {"tests/test_a.py": "def test_a():\n    pass\n",
                              "a.test.mjs": NT + "test('a', () => {});\n"})
    assert run(tree, "pytest", ["tests/test_a.py", "tests/test_gone.py"]).result == "load_error"
    assert run(tree, "node-test", ["a.test.mjs", "gone.test.mjs"]).result == "load_error"
    assert run(tree, "vitest", ["a.test.mjs", "gone.test.mjs"]).result == "load_error"


def test_node_runs_a_file_whose_name_holds_glob_characters_as_itself(tmp_path):
    tree = project(tmp_path, {"r/[id].test.mjs": NT + "test('b', () => assert.equal(1, 1));\n",
                              "r/i.test.mjs": NT + "test('i', () => assert.equal(1, 2));\n"})
    r = run(tree, "node-test", ["r/[id].test.mjs"])
    assert (r.result, r.tests, r.failed) == ("pass", 1, 0)


def test_node_a_requested_file_that_never_reported_did_not_load():
    events = json.dumps({"event": "pass", "file": "/w/tree/a.test.mjs", "name": "a", "nesting": 0,
                         "kind": "test", "skip": False, "todo": False, "failure": None})
    p = cb.parse_node_events(0, events, "", [], ["a.test.mjs", "b.test.mjs"], Path("/w/tree"))
    assert p.result == "load_error"
    p = cb.parse_node_events(0, events, "", [], ["a.test.mjs"], Path("/w/tree"))
    assert (p.result, p.tests) == ("pass", 1)


def test_vitest_json_counts_only_the_requested_files():
    j = vjson([file_result("/w/tree/a.test.js", "passed", [assertion("a", "passed")]),
               file_result("/w/tree/sub/a.test.js", "failed", [assertion("s", "failed", ["x"])])], success=False)
    p = cb.parse_vitest_json(1, j, "", [], ["a.test.js"], Path("/w/tree"))
    assert (p.result, p.tests, p.failed) == ("pass", 1, 0)
    p = cb.parse_vitest_json(1, j, "", [], ["a.test.js", "b.test.js"], Path("/w/tree"))
    assert p.result == "load_error"


def _live_vitest_dirs():
    return [Path(p) for p in (os.environ.get("CODE_BENCH_VITEST_MODULES") or "").split(os.pathsep)
            if p and (Path(p) / ".bin" / "vitest").exists()]


@pytest.mark.skipif(not _live_vitest_dirs(), reason="no vitest binary reachable ($CODE_BENCH_VITEST_MODULES)")
def test_vitest_live_substring_filter_and_missing_relative_import(tmp_path):
    for i, nm in enumerate(_live_vitest_dirs()):
        tree = project(tmp_path / str(i), {
            "package.json": '{"type": "module", "private": true}\n',
            "a.test.js": "import { test, expect } from 'vitest';\ntest('a', () => expect(1).toBe(1));\n",
            "sub/a.test.js": "import { test, expect } from 'vitest';\ntest('s', () => expect(1).toBe(2));\n",
            "n.test.js": "import { test, expect } from 'vitest';\nimport { x } from './newmod.js';\n"
                         "test('n', () => expect(x).toBe(1));\n"})
        cb.clone_node_modules(nm, tree / "node_modules")
        r = run(tree, "vitest", ["a.test.js"], limit=60)
        assert (r.result, r.tests, r.failed) == ("pass", 1, 0), (nm, r.detail)
        assert run(tree, "vitest", ["n.test.js"], names=["newmod"], limit=60).result == "load_error_missing_name"


def test_a_failed_reinstall_leaves_installed_json_not_ok(tmp_path, toy, capsys):
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install() == 0 and b.installed()["ok"] is True
    write(b.root / "tasks.json", json.dumps({"tasks": [toy_task(toy, strip=["no/such.txt"])]}))
    assert b.install() == 1
    info = b.installed()
    assert info["ok"] is False and info["reason"] == "strip_missing" and "task_hash" not in info


def _fast_selftest(monkeypatch, vitest="skipped", ok=True):
    monkeypatch.setattr(cb, "selftest", lambda *a, **k: {"pytest": "pass" if ok else "fail",
                                                         "node-test": "pass", "vitest": vitest, "ok": ok})


def test_install_reports_check_infra_as_the_runner_failing_not_the_task(tmp_path, toy, monkeypatch, capsys):
    _fast_selftest(monkeypatch)
    b = Bench(tmp_path, [toy_task(toy)])
    assert b.install(app_hook=lambda app: setattr(app, "tools", cb.Tools("/nonexistent/python3", None))) == 1
    out = capsys.readouterr().out
    assert "code-01 install: stopped check_infra" in out and "failed" not in out
    assert b.installed()["reason"] == "check_infra"


def test_a_task_that_runs_vitest_needs_the_vitest_canary(tmp_path, monkeypatch):
    _fast_selftest(monkeypatch, vitest="skipped")
    app = cb.App(root=tmp_path / "r", results=tmp_path / "p.jsonl", evals_dir=tmp_path / "e", work=tmp_path / "w")
    assert cb.require_selftest(app)["ok"] is True
    with pytest.raises(cb.BenchError) as e:
        cb.require_selftest(app, need_vitest=True)
    assert e.value.word == "selftest_failed"
    _fast_selftest(monkeypatch, vitest="pass")
    assert cb.require_selftest(app, need_vitest=True)["ok"] is True


@pytest.fixture(scope="module")
def linky(tmp_path_factory):
    """A git project whose before commit has links that leave the tree and whose change edits an
    executable script."""
    repo = tmp_path_factory.mktemp("linky") / "proj"
    repo.mkdir()
    tgit(repo, "init", "-q")
    tgit(repo, "config", "commit.gpgsign", "false")
    write(repo / "mod.py", MOD)
    write(repo / "run.sh", "#!/bin/sh\necho old\n")
    os.chmod(repo / "run.sh", 0o755)
    os.symlink("/etc/hosts", repo / "abs_link")
    os.symlink("../outside", repo / "rel_link")
    c0 = commit(repo, {})
    write(repo / "tests/test_mul.py", MUL_TEST)
    write(repo / "tests/check.sh", "#!/bin/sh\nexit 0\n")
    os.chmod(repo / "tests/check.sh", 0o755)
    c1 = commit(repo, {"mod.py": MOD + "\n\ndef mul(a, b):\n    return a * b\n",
                       "run.sh": "#!/bin/sh\necho new\n"})
    return {"repo": repo, "c0": c0, "c1": c1}


def test_install_skips_links_that_leave_the_tree_and_keeps_exec_modes(tmp_path, linky, capsys):
    rec = record(project_dir=str(linky["repo"]), before=linky["c0"], after=linky["c1"],
                 source_files=["mod.py", "run.sh"], hidden_tests=["tests/test_mul.py", "tests/check.sh"],
                 run_files=["tests/test_mul.py"])
    b = Bench(tmp_path, [rec])
    assert b.install() == 0, capsys.readouterr()
    td = b.tdir()
    assert b.installed()["links_skipped"] == 2
    assert not (td / "start/abs_link").exists() and not (td / "start/abs_link").is_symlink()
    assert os.stat(td / "reference/run.sh").st_mode & 0o111
    assert os.stat(td / "hidden/tests/check.sh").st_mode & 0o111
    assert not os.stat(td / "reference/mod.py").st_mode & 0o111


def test_writing_over_a_file_keeps_its_mode(tmp_path):
    f = tmp_path / "x.sh"
    f.write_text("a")
    os.chmod(f, 0o755)
    cb._write_file(f, b"b")
    assert os.stat(f).st_mode & 0o777 == 0o755
    src = tmp_path / "src.sh"
    src.write_text("c")
    os.chmod(src, 0o700)
    cb._write_file(tmp_path / "new.sh", src)
    assert os.stat(tmp_path / "new.sh").st_mode & 0o777 == 0o700
    cb._write_file(tmp_path / "plain.txt", b"d", 0o644)
    assert os.stat(tmp_path / "plain.txt").st_mode & 0o777 == 0o644


def test_a_sandboxed_test_cannot_signal_a_process_outside_the_sandbox(tmp_path):
    other = subprocess.Popen(["/bin/sleep", "60"])
    try:
        tree = project(tmp_path, {"tests/test_sig.py":
                                  "import os, signal\n"
                                  f"def test_sig():\n    os.kill({other.pid}, signal.SIGKILL)\n"})
        r = run(tree, "pytest", ["tests/test_sig.py"])
        assert r.result == "fail" and "PermissionError" in r.detail
        assert other.poll() is None, "the sandboxed test killed an outside process"
    finally:
        other.kill()
        other.wait()


def test_selftest_fails_closed_when_signals_to_outside_processes_are_allowed(tmp_path):
    def open_signals(dirs, home):
        return cb.sandbox_profile(dirs, home).replace("(deny signal)\n", "")
    rep = cb.selftest(tmp_path / "work", profile_fn=open_signals)
    assert rep["pytest"] != "pass" and rep["node-test"] != "pass" and rep["ok"] is False


def test_a_child_that_left_the_process_group_is_killed_after_the_run(tmp_path):
    body = ("import subprocess, sys, pathlib\n"
            "def test_daemon():\n"
            "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'],"
            " start_new_session=True)\n"
            "    pathlib.Path('daemon.pid').write_text(str(p.pid))\n")
    tree = project(tmp_path, {"tests/test_d.py": body,
                              "tests/test_slow.py": body.replace("def test_daemon", "def test_slow")
                              .replace("daemon.pid", "slow.pid") + "    import time; time.sleep(120)\n"})
    assert run(tree, "pytest", ["tests/test_d.py"]).result == "pass"
    assert _gone(int((tree / "daemon.pid").read_text())), "a setsid child outlived a passing run"
    assert run(tree, "pytest", ["tests/test_slow.py"], limit=3).result == "timeout"
    assert _gone(int((tree / "slow.pid").read_text())), "a setsid child outlived a time-out"


def test_a_run_that_floods_its_output_is_stopped_and_only_its_tail_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "LOG_MAX_BYTES", 2_000_000)
    tree = project(tmp_path, {"tests/test_flood.py":
                              # capfd.disabled(): the bytes reach the run's real output while the
                              # test is still running (pytest would otherwise hold them until the end)
                              "import os, time\ndef test_flood(capfd):\n"
                              "    with capfd.disabled():\n"
                              "        for _ in range(300):\n"
                              "            os.write(1, b'y' * 100000 + b'\\n')\n"
                              "            time.sleep(0.02)\n"
                              "    assert False\n"})
    r = run(tree, "pytest", ["tests/test_flood.py"], limit=30)
    assert r.result == "timeout" and len(r.detail) <= cb.DETAIL_MAX
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * 1_000_000 + b"END")
    assert cb.read_tail(big, 10) == "aaaaaaaEND"


def test_a_cloned_node_modules_has_no_link_that_leaves_it(tmp_path):
    nm = tmp_path / "nm"
    write(nm / "pkg/index.js", "x")
    os.symlink(str(nm), nm / "node_modules")                 # absolute, back into itself
    os.symlink(str(nm / "pkg"), nm / "abs_pkg")             # absolute, into itself
    os.symlink("/etc/hosts", nm / "hosts")                   # absolute, outside
    os.symlink("../../elsewhere", nm / "pkg/up")             # relative, outside
    os.symlink("pkg/index.js", nm / "fine.js")               # relative, inside: kept as it is
    dst = tmp_path / "copy" / "node_modules"
    assert cb.clone_node_modules(nm, dst) == 4
    assert os.readlink(dst / "node_modules") == "." and os.readlink(dst / "abs_pkg") == "pkg"
    assert not (dst / "hosts").is_symlink() and not (dst / "pkg/up").is_symlink()
    assert os.readlink(dst / "fine.js") == "pkg/index.js" and (dst / "abs_pkg/index.js").read_text() == "x"


# == the model steps, with a stub claude ===========================================================

import contextlib  # noqa: E402
import io  # noqa: E402
import shlex  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fixtures" / "code_fake_claude.py"
ALL_CELLS = sorted(set(cb.T_CELLS) | set(cb.C_CELLS))
MODEL_IDS = {c: "claude-test-" + c.replace("@", "-at-") for c in ALL_CELLS}
HIDDEN_MARK = "HIDDENQ5512"
SUITE_GOOD = {"tests/test_mul_w.py": "from mod import mul\n\ndef test_mul_w():\n    assert mul(2, 3) == 6\n"}
SUITE_WEAK = {"tests/test_mul_k.py": "from mod import mul\n\ndef test_mul_k():\n    assert mul(2, 2) == 4\n"}
SUITE_NOT_RED = {"tests/test_add_w.py": "from mod import add\n\ndef test_add_w():\n    assert add(2, 2) == 4\n"}
SUITE_BAD_REF = {"tests/test_mul_b.py": "from mod import mul\n\ndef test_mul_b():\n    assert mul(2, 3) == 7\n"}
CODE_GOOD = {"mod.py": MOD + "\n\ndef mul(a, b):\n    return a * b\n"}
CODE_WRONG = {"mod.py": MOD + "\n\ndef mul(a, b):\n    return a + b\n"}
HIDDEN_TEST = (f"from mod import mul\n\ndef test_hidden_{HIDDEN_MARK}():\n    print('out-{HIDDEN_MARK}')\n"
               f"    assert mul(2, 3) == 6, 'msg-{HIDDEN_MARK}'\n")
VERSION_OK = "2.1.325 (Claude Code)"


def model_harness(timeout_s=20, cap=6):
    return {"harness_version": 1, "repeats_default": 3, "max_retries_invalid": 2,
            "runner": {"claude_bin": f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}",
                       "flags": ["--restricted", "--strict-mcp-config", "--no-session-persistence",
                                 "--disable-slash-commands", "--output-format", "json"],
                       "tools_files": "Read,Grep,Glob", "tools_inline": "", "timeout_s": timeout_s,
                       "max_budget_usd_per_run": cap, "jobs": 1,
                       "system_prompt": "Runner prompt about answer formats."},
            "answer_markers": ["===ANSWER===", "===END==="],
            "judge": {"cell": "fable-5-1@high", "repeats": 2, "system_prompt": "Judge."},
            "decision": {"noticed_extra_misses": 1, "confirmation_tasks_min": 2}}


class MB:
    """A temp root with installed python tasks (start, reference, hidden written directly), a temp
    evals folder wired to the stub claude, and helpers to script the stub and read the records."""

    def __init__(self, tmp_path, monkeypatch, codes=("code-01",), timeout_s=20, cap=6, selftest_ok=True,
                 task_over=None, brief=None):
        self.tmp = tmp_path
        self.root, self.evals, self.work = tmp_path / "root", tmp_path / "evals", tmp_path / "work"
        self.results = tmp_path / "results" / "code-runs.jsonl"
        self.log, self.state, self.script_path = tmp_path / "calls.jsonl", tmp_path / "state.json", tmp_path / "script.json"
        write(self.evals / "harness.json", json.dumps(model_harness(timeout_s, cap)))
        write(self.evals / "cells.json", json.dumps({"cells": {c: {"model_id": m, "effort": c.split("@")[1]}
                                                                for c, m in MODEL_IDS.items()}}))
        write(self.evals / "rows.json", json.dumps({"rows": []}))
        recs = []
        for code in codes:
            rec = record(code, test_patterns=["tests/**"], hidden_tests=["tests/test_mul.py"],
                         run_files=["tests/test_mul.py"])
            rec.update(task_over or {})
            recs.append(rec)
            write(self.root / rec["brief"], brief or f"Brief {MARKER}: add mul(a, b) to mod.py; it returns a * b.\n")
            td = self.root / "tasks" / code
            write(td / "start/mod.py", MOD)
            write(td / "start/tests/test_add.py", "from mod import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
            write(td / "reference/mod.py", CODE_GOOD["mod.py"])
            write(td / "reference/tests/test_add.py", (td / "start/tests/test_add.py").read_text())
            write(td / "hidden/tests/test_mul.py", HIDDEN_TEST)
            write(td / "installed.json", json.dumps({"code": code, "ok": True, "reason": None,
                                                     "reference_seconds": 0.5, "task_hash": "h" * 64}))
        write(self.root / "tasks.json", json.dumps({"tasks": recs}))
        for k, v in {"CODE_FAKE_LOG": self.log, "CODE_FAKE_STATE": self.state,
                     "CODE_FAKE_SCRIPT": self.script_path}.items():
            monkeypatch.setenv(k, str(v))
        monkeypatch.delenv("CODE_FAKE_VERSION", raising=False)
        monkeypatch.delenv("DISABLE_AUTOUPDATER", raising=False)
        _fast_selftest(monkeypatch, ok=selftest_ok)
        self.script()

    def script(self, **kinds):
        write(self.script_path, json.dumps(kinds))
        self.state.unlink(missing_ok=True)

    def cli(self, cmd, *extra, jobs=True):
        args = [cmd, "--root", str(self.root), "--results", str(self.results), "--evals-dir", str(self.evals),
                "--work", str(self.work), *extra]
        if jobs and cmd in ("write-tests", "code"):
            args += ["--jobs", "1"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cb.main(args)
        return code, out.getvalue(), err.getvalue()

    def calls(self, kind=None):
        rows = ev.read_jsonl(self.log) if self.log.exists() else []
        return [r for r in rows if kind is None or r["kind"] == kind]

    def public(self, **match):
        return [x for x in ev.read_jsonl(self.results) if all(x.get(k) == v for k, v in match.items())]

    def private(self):
        return ev.read_jsonl(self.root / "attempts.jsonl")

    def suite_meta(self, cell, run, code="code-01"):
        return json.loads((cb.suite_dir(self.root, code, cell, run) / "meta.json").read_text())

    def run_meta(self, cell, arm, run=1, code="code-01"):
        return json.loads((cb.run_dir_of(self.root, code, cell, arm, run) / "meta.json").read_text())

    def seed_suite(self, cell, run, files, fit=None, code="code-01"):
        d = cb.suite_dir(self.root, code, cell, run)
        for rel, text in files.items():
            write(d / "files" / rel, text)
        write(d / "meta.json", json.dumps({"task": code, "cell": cell, "run": run, "ended": "done",
                                           "files": sorted(files), "tries": 1}))
        if fit is not None:
            write(d / "fit.json", json.dumps({"suite": cb.suite_id(cell, run), "fit": fit}))

    def give(self, suite, code="code-01"):
        g = cb.given_of(self.root)
        g[code] = {"suite": suite, "fixed_at": "2026-11-14T18:00:00Z"}
        write(self.root / "given.json", json.dumps(g))


def test_write_tests_runs_every_test_writing_cell_twice_with_file_tools_only(tmp_path, monkeypatch):
    nm = tmp_path / "nm"
    write(nm / "pkg/index.js", "x")
    b = MB(tmp_path, monkeypatch, task_over={"node_modules": {"from": str(nm), "to": "node_modules"}})
    b.script(T=[{"write": SUITE_GOOD}])
    code, out, err = b.cli("write-tests")
    assert code == 0, err
    calls = b.calls()
    assert [c["model"] for c in calls] == [MODEL_IDS[c] for c in cb.T_CELLS for _ in (1, 2)]
    for c in calls:
        argv = c["argv"]
        i = argv.index("--permission-mode")
        assert argv[i:i + 8] == ["--permission-mode", "dontAsk", "--allowedTools", "Read", "Grep", "Glob",
                                 "Write", "Edit"]
        assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob,Write,Edit"
        assert c["system_prompt"] == cb.SYSTEM_PROMPT and "--restricted" in argv
        assert argv[argv.index("--max-budget-usd") + 1] == "6"
        assert c["autoupdater"] == "1" and c["advisor_switch"] == "1"
        assert c["files"] == ["mod.py", "tests/test_add.py"]          # a copy of start, no node_modules
        assert c["prompt"].startswith(f"Brief {MARKER}") and cb.INSTRUCTIONS["T"] in c["prompt"]
        assert c["prompt"].rstrip().endswith(cb.DONE_LINE)
        assert "/work/" in c["cwd"] and str(b.root) not in c["cwd"]
    lines = b.public(kind="check", step="T")
    assert len(lines) == 8 and {x["result"] for x in lines} == {"load_error_missing_name"}
    assert [(x["cell"], x["run"], x["suite"]) for x in lines] == [
        (c, r, f"{c}#{r}") for c in cb.T_CELLS for r in (1, 2)]
    assert len(b.public(kind="model", step="T")) == 8 and "DISABLE_AUTOUPDATER" not in os.environ
    m = b.suite_meta("opus-5-5@high", 2)
    assert m["files"] == ["tests/test_mul_w.py"] and m["red"] is True and m["tries"] == 1 and m["ended"] == "done"
    assert (cb.suite_dir(b.root, "code-01", "opus-5-5@high", 2) / "files/tests/test_mul_w.py").exists()
    assert "write-tests: done" in out
    assert b.cli("write-tests")[0] == 0 and len(b.calls()) == 8           # stored runs are not made again


def test_write_tests_keeps_only_the_test_files_and_counts_what_it_dropped(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"write": {**SUITE_NOT_RED, **CODE_GOOD, "newsrc.py": "X = 1\n"}, "delete": ["tests/test_add.py"],
                 "symlink": {"tests/link.py": "/etc/hosts"}}, {"write": SUITE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    second = b.calls()[1]
    assert "newsrc.py" not in second["files"] and "tests/link.py" not in second["files"]
    assert "tests/test_add.py" in second["files"] and "tests/test_add_w.py" in second["files"]
    m = b.suite_meta("sonnet-5-5@high", 1)
    assert m["files"] == ["tests/test_add_w.py", "tests/test_mul_w.py"] and m["files_dropped"] == 4
    line = b.public(kind="model", run=1)[0]
    assert line["files_changed"] == 5 and line["files_dropped"] == 4
    stored = cb.suite_dir(b.root, "code-01", "sonnet-5-5@high", 1) / "files"
    assert sorted(str(x.relative_to(stored)) for x in stored.rglob("*") if x.is_file()) == m["files"]


def test_a_suite_that_is_not_red_gets_another_try_with_the_check_output(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"write": SUITE_NOT_RED}, {"write": SUITE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    first, second = b.calls()[:2]
    assert cb.RETRY_LINE not in first["prompt"]
    assert cb.RETRY_LINE in second["prompt"] and "1 passed" in second["prompt"]
    assert "tests/test_add_w.py" in second["files"]                       # the same copy, as left
    assert [x["result"] for x in b.public(kind="check", run=1)] == ["pass", "load_error_missing_name"]
    assert [x["try"] for x in b.public(kind="model", run=1)] == [1, 2]
    m = b.suite_meta("sonnet-5-5@high", 1)
    assert m["red"] is True and m["tries"] == 2 and m["red_first"] == ["pass", "load_error_missing_name"]


def test_a_writer_that_never_gets_red_stops_after_three_tries(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"write": SUITE_NOT_RED}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    assert len(b.calls()) == 6                                            # 3 tries x 2 runs
    m = b.suite_meta("sonnet-5-5@high", 1)
    assert m["tries"] == 3 and m["red"] is False and m["red_first"] == ["pass"] * 3


def test_a_writer_that_writes_no_test_is_told_so(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"write": CODE_GOOD}, {"write": SUITE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    assert cb.NOTE_NO_TESTS in b.calls()[1]["prompt"]
    assert [x["result"] for x in b.public(kind="check", run=1)] == ["no_tests", "load_error_missing_name"]


def test_write_tests_never_runs_the_reference(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    bases = []
    real = cb.run_on_copy

    def spy(work, task, base, *a, **k):
        bases.append(Path(base).name)
        return real(work, task, base, *a, **k)
    monkeypatch.setattr(cb, "run_on_copy", spy)
    b.script(T=[{"write": SUITE_NOT_RED}, {"write": SUITE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    assert bases and set(bases) == {"start"}


def test_an_api_error_is_an_attempt_not_a_try_and_leaves_no_trace(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"mode": "api_error", "write": {"tests/test_junk.py": "x = 1\n"}}, {"write": SUITE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    calls = b.calls()
    assert "tests/test_junk.py" not in calls[1]["files"]                 # the copy was put back
    assert calls[1]["prompt"] == calls[0]["prompt"]                      # the same try again
    lines = b.public(kind="model", run=1)
    assert [(x["try"], x["attempt"], x["infra"], x["valid"]) for x in lines] == [(1, 1, True, False), (1, 2, False, True)]
    assert lines[0]["reason"] == "is_error"
    assert len(b.public(kind="check", run=1)) == 1 and b.suite_meta("sonnet-5-5@high", 1)["files"] == ["tests/test_mul_w.py"]


def test_three_api_errors_end_the_run(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(T=[{"mode": "api_error", "write": SUITE_GOOD}], B=[{"mode": "api_error", "write": CODE_GOOD}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    m = b.suite_meta("sonnet-5-5@high", 1)
    assert m["ended"] == "infra" and m["files"] == [] and m["processes"] == 3
    assert [x["attempt"] for x in b.public(kind="model", run=1)] == [1, 2, 3]
    assert b.public(kind="check", step="T") == []
    b.seed_suite("sonnet-5-5@xhigh", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@xhigh#1")
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", "B", "--rounds", "1")[0] == 0
    r = b.run_meta("haiku-5-5@high", "B")
    assert r["ended"] == "infra" and r["correct"] is False and r["finished"] is False and r["tries"] == 0


def test_a_time_out_and_a_budget_cap_are_tries_and_an_unknown_cost_is_charged_the_cap(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch, timeout_s=2, cap=6)
    b.script(T=[{"mode": "timeout", "write": SUITE_NOT_RED}, {"mode": "budget_cap", "cost": 6.0},
                {"write": SUITE_GOOD, "cost": None}])
    assert b.cli("write-tests", "--cells", "sonnet-5-5@high")[0] == 0
    lines = b.public(kind="model", run=1)
    assert [(x["try"], x["reason"], x["infra"], x["cost_unknown"]) for x in lines] == [
        (1, "timeout", False, True), (2, "budget_cap", False, False), (3, None, False, True)]
    assert len(b.public(kind="check", run=1)) == 3
    m = b.suite_meta("sonnet-5-5@high", 1)
    assert m["cost_usd"] == 18.0 and m["cost_unknown"] == 2 and m["red"] is True


def test_no_model_process_starts_once_the_spend_total_reaches_the_limit(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch, cap=6)
    rec = cb.Records(b.results, b.root / "attempts.jsonl")
    rec.model({"step": "T", "task": "code-01", "cell": "sonnet-5-5@high", "run": 9, "try": 1, "attempt": 1,
               "valid": False, "reason": "timeout", "cost_usd": None, "cost_unknown": True})
    b.script(T=[{"write": SUITE_GOOD, "cost": 0.25}])
    code, out, err = b.cli("write-tests", "--cells", "sonnet-5-5@high", "--max-usd", "6.01")
    assert code == 3 and len(b.calls()) == 1
    assert "spend stop reached ($6.25 of $6.01)" in out and "(spend $6.25)" in out
    code, out, _ = b.cli("write-tests", "--cells", "sonnet-5-5@high", "--max-usd", "6.2")
    assert code == 3 and len(b.calls()) == 1                         # read from the record: nothing new
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", "A", "--max-usd", "6.2")[0] == 3
    assert len(b.calls()) == 1


@pytest.mark.parametrize("cmd", ["write-tests", "code"])
def test_a_model_command_stops_when_the_claude_version_differs(tmp_path, monkeypatch, cmd):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    monkeypatch.setenv("CODE_FAKE_VERSION", "2.1.326 (Claude Code)")
    code, out, err = b.cli(cmd, "--cells", "sonnet-5-5@medium" if cmd == "code" else "sonnet-5-5@high")
    assert (code, err.strip()) == (2, "code_bench: error: version_mismatch") and b.calls() == []
    extra = ("--cells", "sonnet-5-5@medium", "--rounds", "1") if cmd == "code" else ("--cells", "sonnet-5-5@high")
    assert b.cli(cmd, *extra, "--allow-version", "2.1.326")[0] == 0 and b.calls()
    assert {x["cli_version"] for x in b.public(kind="model")} == {"2.1.326"}


@pytest.mark.parametrize("cmd", ["write-tests", "fix-suites", "code", "cross"])
def test_a_command_that_runs_tests_refuses_when_the_selftest_fails(tmp_path, monkeypatch, cmd):
    b = MB(tmp_path, monkeypatch, selftest_ok=False)
    code, out, err = b.cli(cmd)
    assert (code, err.strip()) == (2, "code_bench: error: selftest_failed") and b.calls() == []


@pytest.mark.parametrize("cmd", ["write-tests", "fix-suites", "code", "cross"])
def test_a_command_that_writes_records_takes_evalkits_lock(tmp_path, monkeypatch, cmd):
    b = MB(tmp_path, monkeypatch)
    with ev.exclusive_lock(b.evals / "results" / ".evalkit.lock"):
        code, out, err = b.cli(cmd)
    assert (code, err.strip()) == (2, "code_bench: error: locked") and b.calls() == []


def test_fix_suites_scores_every_suite_and_fixes_the_first_fit_in_the_fixed_order(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    plan = {("sonnet-5-5@high", 1): SUITE_NOT_RED, ("sonnet-5-5@high", 2): SUITE_BAD_REF,
            ("sonnet-5-5@xhigh", 1): {**SUITE_GOOD, "tests/helper_data.json": "{}"}}
    for cell, run in cb.GIVEN_ORDER:
        b.seed_suite(cell, run, plan.get((cell, run), SUITE_WEAK))
    code, out, _ = b.cli("fix-suites")
    assert code == 0 and "code-01 fix-suites: 6 of 8 fit, given sonnet-5-5@xhigh#1" in out
    fits = {(c, r): json.loads((cb.suite_dir(b.root, "code-01", c, r) / "fit.json").read_text())
            for c, r in cb.GIVEN_ORDER}
    assert fits[("sonnet-5-5@high", 1)]["fit"] is False and fits[("sonnet-5-5@high", 1)]["start"] == "pass"
    assert fits[("sonnet-5-5@high", 2)]["fit"] is False and fits[("sonnet-5-5@high", 2)]["reference"] == ["fail"]
    assert fits[("sonnet-5-5@xhigh", 1)]["fit"] is True and fits[("sonnet-5-5@xhigh", 1)]["reference"] == ["pass", "pass"]
    assert cb.given_of(b.root)["code-01"]["suite"] == "sonnet-5-5@xhigh#1"
    g = b.public(what="given")
    assert [(x["step"], x["suite"], x["result"], x["cell"], x["run"]) for x in g] == [
        ("fit", "sonnet-5-5@xhigh#1", "pass", "sonnet-5-5@xhigh", 1)]
    xr = b.public(suite="sonnet-5-5@xhigh#1", what="fit_reference")
    assert [x["try"] for x in xr] == [1, 2] and b.public(suite="sonnet-5-5@high#1", what="fit_reference") == []


def test_the_given_suite_waits_for_all_eight_suites_and_is_never_changed(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    for cell, run in cb.GIVEN_ORDER[1:]:
        b.seed_suite(cell, run, SUITE_WEAK)
    code, out, _ = b.cli("fix-suites")
    assert "given pending (7 of 8 suites stored)" in out and "code-01" not in cb.given_of(b.root)
    b.seed_suite(*cb.GIVEN_ORDER[0], SUITE_GOOD)
    code, out, _ = b.cli("fix-suites")
    assert cb.given_of(b.root)["code-01"]["suite"] == "sonnet-5-5@high#1"
    write(cb.suite_dir(b.root, "code-01", "sonnet-5-5@high", 1) / "fit.json", json.dumps({"fit": False}))
    code, out, _ = b.cli("fix-suites")
    assert "(fixed earlier)" in out and cb.given_of(b.root)["code-01"]["suite"] == "sonnet-5-5@high#1"
    assert len(b.public(what="given")) == 1


def test_an_infra_ended_suite_is_not_fit_and_is_not_run(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    for cell, run in cb.GIVEN_ORDER:
        b.seed_suite(cell, run, SUITE_GOOD)
    meta = cb.suite_dir(b.root, "code-01", "sonnet-5-5@high", 1) / "meta.json"
    write(meta, json.dumps({**json.loads(meta.read_text()), "ended": "infra"}))
    b.cli("fix-suites")
    assert b.public(suite="sonnet-5-5@high#1") == []
    assert cb.given_of(b.root)["code-01"]["suite"] == "sonnet-5-5@high#2"


def test_a_task_with_no_fit_suite_runs_arm_a_only(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    for cell, run in cb.GIVEN_ORDER:
        b.seed_suite(cell, run, SUITE_NOT_RED)
    code, out, _ = b.cli("fix-suites")
    assert "no given suite: arms B and C are left out" in out and cb.given_of(b.root)["code-01"]["suite"] is None
    assert [(x["result"], x["suite"]) for x in b.public(what="given")] == [("fail", None)]
    b.script(A=[{"write": CODE_GOOD}])
    code, out, _ = b.cli("code", "--cells", "haiku-5-5@high", "--rounds", "1")
    assert code == 0 and "code-01 haiku-5-5@high B: left out (no fit suite)" in out
    assert [c["kind"] for c in b.calls()] == ["A"]


def test_arm_a_has_one_try_and_only_the_hidden_tests_run(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.script(A=[{"write": CODE_WRONG}])
    assert b.cli("code", "--cells", "haiku-5-5@medium", "--arms", "A", "--rounds", "1")[0] == 0
    assert len(b.calls()) == 1 and cb.INSTRUCTIONS["A"] in b.calls()[0]["prompt"]
    assert [(x["what"], x["result"]) for x in b.public(kind="check")] == [("hidden", "fail")]
    m = b.run_meta("haiku-5-5@medium", "A")
    assert (m["tries"], m["finished"], m["correct"], m["escaped"], m["correct_first"]) == (1, None, False, None, False)
    assert m["files"] == ["mod.py"] and m["source_unchanged"] is False


def test_arm_b_a_coder_that_fixes_the_code_at_the_second_try(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    b.script(B=[{"write": {**CODE_WRONG, "notes_helper.py": "N = 1\n"}}, {"write": CODE_GOOD}])
    assert b.cli("code", "--cells", "haiku-5-5@medium", "--arms", "B", "--rounds", "1")[0] == 0
    first, second = b.calls()
    assert "tests/test_mul_w.py" in first["files"] and "- tests/test_mul_w.py" in first["prompt"]
    assert cb.INSTRUCTIONS["B"] in first["prompt"] and cb.RETRY_LINE not in first["prompt"]
    assert cb.RETRY_LINE in second["prompt"] and "assert 5 == 6" in second["prompt"]
    assert "notes_helper.py" in second["files"]                           # the same copy
    assert [(x["what"], x["try"], x["result"]) for x in b.public(kind="check")] == [
        ("given", 1, "fail"), ("hidden", 1, "fail"), ("given", 2, "pass"), ("hidden", 2, "pass")]
    assert {x["suite"] for x in b.public(what="given")} == {"sonnet-5-5@high#1"}
    m = b.run_meta("haiku-5-5@medium", "B")
    assert (m["tries"], m["finished"], m["correct"], m["correct_first"], m["escaped"]) == (2, True, True, False, False)
    assert m["cost_usd"] == 0.5 and m["duration_ms"] == 2 * 1234 and m["checks"] == ["fail", "pass"]


def test_arm_b_a_coder_that_edits_a_locked_file_fails_the_try_and_the_file_is_put_back(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch, task_over={"runner_config": ["pytest.ini"]})
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    cheat = {"tests/test_mul_w.py": "def test_mul_w():\n    assert True\n", **CODE_WRONG}
    b.script(B=[{"write": cheat}, {"write": {"pytest.ini": "[pytest]\naddopts = -k nothing\n"}},
                {"write": CODE_GOOD}])
    assert b.cli("code", "--cells", "haiku-5-5@medium", "--arms", "B", "--rounds", "1")[0] == 0
    calls = b.calls()
    assert cb.NOTE_LOCKED in calls[1]["prompt"] and cb.NOTE_LOCKED in calls[2]["prompt"]
    assert "pytest.ini" not in calls[2]["files"]
    assert [x["result"] for x in b.public(what="given")] == ["locked_changed", "locked_changed", "pass"]
    assert [x["files_dropped"] for x in b.public(kind="model")] == [1, 1, 0]
    m = b.run_meta("haiku-5-5@medium", "B")
    assert m["finished"] is True and m["correct"] is True and m["tries"] == 3
    stored = cb.run_dir_of(b.root, "code-01", "haiku-5-5@medium", "B", 1) / "overlay/tests/test_mul_w.py"
    assert stored.read_text() == SUITE_GOOD["tests/test_mul_w.py"]


def test_arm_b_a_run_that_passes_the_given_suite_but_not_the_hidden_tests_escaped(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_WEAK, fit=True)
    b.give("sonnet-5-5@high#1")
    b.script(B=[{"write": CODE_WRONG}])
    assert b.cli("code", "--cells", "sonnet-5-5@medium", "--rounds", "1")[0] == 0
    m = b.run_meta("sonnet-5-5@medium", "B")
    assert (m["tries"], m["finished"], m["correct"], m["escaped"]) == (1, True, False, True)


def test_arm_c_own_tests_must_exist_be_red_on_start_and_pass_on_the_copy(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    b.script(C=[{"write": CODE_GOOD}, {"write": SUITE_NOT_RED}, {"write": SUITE_GOOD}])
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", "C", "--rounds", "1")[0] == 0
    calls = b.calls()
    assert cb.INSTRUCTIONS["C"] in calls[0]["prompt"] and "tests/test_mul_w.py" not in calls[0]["files"]
    assert cb.NOTE_NO_TESTS in calls[1]["prompt"] and cb.NOTE_OWN_NOT_RED in calls[2]["prompt"]
    assert [x["result"] for x in b.public(what="own")] == ["no_tests", "fail", "pass"]
    assert [x.get("own_reason") for x in b.private() if x.get("what") == "own"] == ["no_own_tests", "own_not_red", None]
    m = b.run_meta("haiku-5-5@high", "C")
    assert m["finished"] is True and m["correct"] is True and m["correct_first"] is True and m["tries"] == 3


def test_hidden_tests_run_after_every_try_and_are_never_shown_to_the_model(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    b.script(B=[{"write": CODE_WRONG}], C=[{"write": {**SUITE_GOOD, **CODE_WRONG}}])
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", "B,C", "--rounds", "1")[0] == 0
    assert len(b.public(what="hidden", arm="B")) == 3 and len(b.public(what="hidden", arm="C")) == 3
    for c in b.calls():
        assert HIDDEN_MARK not in c["prompt"] and "tests/test_mul.py" not in c["files"]
    assert any(HIDDEN_MARK in (x.get("detail") or "") for x in b.private() if x.get("what") == "hidden")


def test_step_c_plan_has_180_runs_in_rounds_in_the_order_task_cell_arm():
    tasks = [cb.validate_task(record(f"code-0{i}")) for i in range(1, 7)]
    given = {t.code: {"suite": "sonnet-5-5@high#1"} for t in tasks}
    plan = cb.c_units(tasks, given, cb.C_ROUNDS)
    units = plan["units"]
    assert len(units) == 180 and plan["left_out"] == [] and plan["pending"] == []
    assert {a: sum(1 for u in units if u[3] == a) for a in "ABC"} == {"A": 66, "B": 90, "C": 24}
    per_cell = {}
    for n, t, cell, arm in units:
        per_cell.setdefault((cell, arm), set()).add(n)
    assert per_cell == {("haiku-5-5@medium", "A"): {1, 2, 3, 4}, ("haiku-5-5@medium", "B"): {1, 2, 3, 4},
                        ("haiku-5-5@high", "A"): {1, 2, 3, 4}, ("haiku-5-5@high", "B"): {1, 2, 3, 4},
                        ("haiku-5-5@high", "C"): {1, 2, 3, 4}, ("sonnet-5-5@low", "A"): {1, 2, 3},
                        ("sonnet-5-5@low", "B"): {1, 2, 3}, ("sonnet-5-5@medium", "B"): {1, 2, 3},
                        ("opus-5-5@high", "B"): {1}}
    assert [u[0] for u in units] == sorted(u[0] for u in units)          # round by round
    first = [(u[1].code, u[2], u[3]) for u in units[:9]]
    assert first == [("code-01", "haiku-5-5@medium", "A"), ("code-01", "haiku-5-5@medium", "B"),
                     ("code-01", "haiku-5-5@high", "A"), ("code-01", "haiku-5-5@high", "B"),
                     ("code-01", "haiku-5-5@high", "C"), ("code-01", "sonnet-5-5@low", "A"),
                     ("code-01", "sonnet-5-5@low", "B"), ("code-01", "sonnet-5-5@medium", "B"),
                     ("code-01", "opus-5-5@high", "B")]
    assert units[9][1].code == "code-02"
    given["code-03"] = {"suite": None}
    del given["code-04"]
    plan = cb.c_units(tasks, given, cb.C_ROUNDS)
    assert len(plan["left_out"]) == 19 and len(plan["pending"]) == 19 and len(plan["units"]) == 180 - 38


def test_code_runs_whole_rounds_up_to_the_rounds_option(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch, codes=("code-01", "code-02"))
    b.script(A=[{"write": CODE_GOOD}])
    assert b.cli("code", "--cells", "haiku-5-5@medium,sonnet-5-5@low", "--arms", "A", "--rounds", "1")[0] == 0
    assert [(x["task"], x["cell"], x["run"]) for x in b.public(kind="model")] == [
        ("code-01", "haiku-5-5@medium", 1), ("code-01", "sonnet-5-5@low", 1),
        ("code-02", "haiku-5-5@medium", 1), ("code-02", "sonnet-5-5@low", 1)]
    assert b.cli("code", "--cells", "haiku-5-5@medium,sonnet-5-5@low", "--arms", "A", "--rounds", "2")[0] == 0
    assert [x["run"] for x in b.public(kind="model")][4:] == [2, 2, 2, 2]


def test_an_interrupted_command_says_interrupted_not_done(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    monkeypatch.setattr(cb.ev, "run_pool", lambda *a, **k: 130)       # what Ctrl-C makes the pool return
    code, out, _ = b.cli("code", "--cells", "haiku-5-5@medium", "--arms", "A", "--rounds", "1")
    assert code == 130 and "code: interrupted" in out and "code: done" not in out
    code, out, _ = b.cli("write-tests", "--cells", "sonnet-5-5@high")
    assert code == 130 and "write-tests: interrupted" in out and "write-tests: done" not in out


def test_cross_runs_every_fit_suite_on_the_final_copies_of_arms_a_and_c_only(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.seed_suite("sonnet-5-5@high", 2, SUITE_WEAK, fit=True)
    b.seed_suite("sonnet-5-5@xhigh", 1, SUITE_NOT_RED, fit=False)
    b.give("sonnet-5-5@high#1")
    skip_suite = ("import pytest\n\n@pytest.fixture\ndef two():\n    return 2\n\n"
                  "def pytest_collection_modifyitems(config, items):\n    for it in items:\n"
                  "        if 'test_mul_w' in it.nodeid:\n            it.add_marker(pytest.mark.skip)\n")
    own = {"tests/conftest.py": skip_suite,
           "tests/test_c_own.py": "from mod import mul\n\ndef test_c_own(two):\n    assert mul(two, 3) == 6\n"}
    b.script(A=[{"write": CODE_WRONG}, {"write": CODE_WRONG}, {}], B=[{"write": CODE_GOOD}],
             C=[{"write": {**own, **CODE_GOOD}}])
    assert b.cli("code", "--cells", "haiku-5-5@medium,haiku-5-5@high,sonnet-5-5@low", "--rounds", "1")[0] == 0
    assert b.run_meta("haiku-5-5@high", "C")["finished"] is True
    assert b.run_meta("sonnet-5-5@low", "A")["source_unchanged"] is True
    ran = []
    real = cb.run_on_copy
    monkeypatch.setattr(cb, "run_on_copy", lambda *a, **k: ran.append(1) or real(*a, **k))
    # another task's entry with the same suite id and the same non-test overlay is never reused
    other = b.run_meta("haiku-5-5@medium", "A")["nontest_hash"]
    write(b.root / "cross.json", json.dumps({"code-02|sonnet-5-5@high#1|haiku-5-5@medium|A|1": {
        "task": "code-02", "suite": "sonnet-5-5@high#1", "nontest_hash": other, "result": "pass",
        "tests": 1, "failed": 0, "seconds": 0.1}}))
    code, out, _ = b.cli("cross")
    assert code == 0 and "code-01 cross: 4 pairs run, 2 reused" in out and len(ran) == 4
    copies = {(x["cell"], x["arm"], x["run"]): x["result"] for x in b.public(step="cross", what="copy")}
    assert copies == {("haiku-5-5@medium", "A", 1): "changed", ("haiku-5-5@high", "A", 1): "changed",
                      ("haiku-5-5@high", "C", 1): "changed", ("sonnet-5-5@low", "A", 1): "unchanged"}
    assert all(x["suite"] is None for x in b.public(what="copy"))
    got = {(x["suite"], x["cell"], x["arm"]): x["result"] for x in b.public(step="cross", what="cross")}
    assert got == {("sonnet-5-5@high#1", "haiku-5-5@medium", "A"): "fail",
                   ("sonnet-5-5@high#1", "haiku-5-5@high", "A"): "fail",
                   ("sonnet-5-5@high#1", "haiku-5-5@high", "C"): "pass",
                   ("sonnet-5-5@high#2", "haiku-5-5@medium", "A"): "pass",
                   ("sonnet-5-5@high#2", "haiku-5-5@high", "A"): "pass",
                   ("sonnet-5-5@high#2", "haiku-5-5@high", "C"): "pass"}
    assert all(x["run"] == 1 for x in b.public(step="cross"))
    code, out, _ = b.cli("cross")
    assert "0 pairs run, 0 reused" in out and len(b.public(step="cross")) == 10      # 6 pairs, 4 copies, once


def test_plan_counts_what_is_missing_and_the_spend(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch, codes=tuple(f"code-0{i}" for i in range(1, 7)))
    code, out, _ = b.cli("plan")
    assert code == 0
    assert "plan: 6 tasks, 6 installed" in out
    assert "step T: 0 of 48 suites stored, 48 to run" in out
    assert "step C: 0 of 180 runs stored (A 0/66, B 0/90, C 0/24), 180 to run, 0 left out" in out
    assert "spend: $0.00 so far" in out and "projected unknown; stop at $226.00" in out
    b.script(T=[{"write": SUITE_GOOD, "cost": 1.0}])
    assert b.cli("write-tests", "--task", "code-01", "--cells", "sonnet-5-5@high")[0] == 0
    code, out, _ = b.cli("plan", "--json")
    p = json.loads(out)
    assert p["T"]["stored"] == 2 and p["T"]["missing"] == 46 and p["spend"]["total"] == 2.0
    assert p["spend"]["projected"] is None                                # no step-C cost seen yet
    assert b.calls() and len(b.calls()) == 2
    code, out, _ = b.cli("status")
    assert "code-01: installed ok, T 2/8, fit 0, given pending, C 0" in out and "spend: $2.00" in out


def test_no_private_text_reaches_the_public_record_or_the_terminal_in_the_model_steps(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    suite = {f"tests/test_mul_{MARKER}.py": f"from mod import mul\n\ndef test_w_{MARKER}():\n"
                                            f"    print('out-{MARKER}')\n    assert mul(2, 3) == 6, 'msg-{MARKER}'\n"}
    b.script(T=[{"write": suite}], B=[{"write": CODE_WRONG}, {"write": CODE_GOOD}], A=[{"write": CODE_WRONG}],
             C=[{"write": {**suite, **CODE_GOOD}}])
    shown = []
    for cmd, extra in (("write-tests", ()), ("fix-suites", ()), ("code", ("--rounds", "1")), ("cross", ()),
                       ("plan", ()), ("status", ())):
        code, out, err = b.cli(cmd, *extra)
        assert code == 0, (cmd, err)
        shown.append(out + err)
    public = b.results.read_text()
    for text in shown + [public]:
        assert MARKER not in text and HIDDEN_MARK not in text and str(tmp_path) not in text
        assert "/private/" not in text and "test_mul" not in text and "Traceback" not in text
    assert MARKER in b.calls()[0]["prompt"]                               # the brief reached the model
    private = (b.root / "attempts.jsonl").read_text()
    assert f"out-{MARKER}" in private and f"out-{HIDDEN_MARK}" in private
    for line in ev.read_jsonl(b.results):
        cb.public_line(line)


def _call(stdout="", returncode=0, timeout=False, error=None):
    return {"stdout": stdout, "returncode": returncode, "timeout": timeout, "error": error}


def _out(model="claude-x", **over):
    d = {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn", "safety_stops": 0,
         "api_error_status": None, "result": "DONE", "total_cost_usd": 0.3, "duration_ms": 10, "num_turns": 2,
         "usage": {"input_tokens": 1, "output_tokens": 5, "cache_read_input_tokens": 0},
         "modelUsage": {model: {"costUSD": 0.3}}}
    d.update(over)
    return json.dumps(d)


def test_a_model_process_gets_one_reason_word_and_the_infra_reading():
    cell = {"model_id": "claude-x"}
    read = lambda call: cb.read_process(call, cell, 6.0)  # noqa: E731
    cases = [
        (_call(error="spawn failed: no such file"), (False, "spawn_failed", True)),
        (_call(timeout=True), (False, "timeout", False)),
        (_call("not json"), (False, "json_parse", False)),
        (_call(_out(is_error=True, subtype="error_max_budget_usd"), 1), (False, "budget_cap", False)),
        (_call(_out(stop_reason="refusal")), (False, "refusal", False)),
        (_call(_out(model="claude-y")), (False, "model_mismatch", False)),
        (_call(_out(is_error=True), 1), (False, "is_error", False)),
        (_call(_out(is_error=True, api_error_status=529, usage={"output_tokens": 0}), 1), (False, "is_error", True)),
        (_call(_out()), (True, None, False)),
    ]
    for call, want in cases:
        p = read(call)
        assert (p.valid, p.reason, p.infra) == want, call
    assert read(_call(timeout=True)).unknown is True and read(_call(error="spawn failed: x")).cost == 0.0


def test_the_prompts_are_fixed_texts_with_the_brief_and_a_capped_check_output():
    p = cb.build_prompt("B", "The brief.", ["tests/a.py", "tests/b.py"])
    assert p == ("The brief.\n\n" + cb.INSTRUCTIONS["B"] + "\n\n- tests/a.py\n- tests/b.py\n\n" + cb.DONE_LINE)
    p = cb.build_prompt("A", "The brief.", feedback="x" * 9000 + "END")
    assert p.startswith("The brief.\n\n" + cb.INSTRUCTIONS["A"] + "\n\n" + cb.DONE_LINE + "\n\n" + cb.RETRY_LINE)
    assert p.endswith("END") and len(p.split(cb.RETRY_LINE + "\n")[1]) == cb.DETAIL_MAX
    for kind in "TAC":
        assert cb.build_prompt(kind, "b").count("- ") == 0 and "Bash" not in cb.SYSTEM_PROMPT


def test_runnable_files_follow_the_runners_naming_rule_or_the_tasks_own():
    py = cb.validate_task(record())
    assert cb.runnable_files(["tests/test_a.py", "tests/conftest.py", "tests/a_test.py", "tests/data.json"], py) \
        == ["tests/a_test.py", "tests/test_a.py"]
    js = cb.validate_task(record(runner="node-test", language="typescript"))
    assert cb.runnable_files(["test/a.test.ts", "test/helpers.ts", "test/fixture.test.json", "src/b.spec.mjs"], js) \
        == ["src/b.spec.mjs", "test/a.test.ts"]
    own = cb.validate_task(record(runner="node-test", run_patterns=["test/**/*.ts"]))
    assert cb.runnable_files(["test/a.ts", "test/x/b.ts", "src/c.ts"], own) == ["test/a.ts", "test/x/b.ts"]


# -- the checker's findings: check_infra stops, the note survives, the whole version, resumed runs ------

def _infra_runner(monkeypatch):
    """run_on_copy whose FIRST call while state["on"] comes back check_infra (with a marker in its private
    detail); every other call is a real run."""
    real = cb.run_on_copy
    state = {"on": True, "used": False}

    def fake(*a, **k):
        if state["on"] and not state["used"]:
            state["used"] = True
            return cb.TestResult("check_infra", None, None, 0.0, f"sandbox refused {MARKER}")
        return real(*a, **k)
    monkeypatch.setattr(cb, "run_on_copy", fake)
    return state


@pytest.mark.parametrize("case", ["T", "fit", "A", "B", "C", "cross"])
def test_a_check_infra_test_run_stops_the_unit_and_stores_nothing(tmp_path, monkeypatch, case):
    b = MB(tmp_path, monkeypatch)
    state = _infra_runner(monkeypatch)
    if case == "T":
        b.script(T=[{"write": SUITE_GOOD}])
        args = ("write-tests", "--cells", "sonnet-5-5@high")
    elif case == "fit":
        for cell, run in cb.GIVEN_ORDER:
            b.seed_suite(cell, run, SUITE_GOOD)
        args = ("fix-suites",)
    else:
        b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
        b.give("sonnet-5-5@high#1")
        b.script(A=[{"write": CODE_GOOD}], B=[{"write": CODE_GOOD}], C=[{"write": {**SUITE_GOOD, **CODE_GOOD}}])
        arm = "A" if case == "cross" else case
        args = ("code", "--cells", "haiku-5-5@high", "--arms", arm, "--rounds", "2")
        if case == "cross":
            state["on"] = False
            assert b.cli(*args)[0] == 0
            state["on"] = True
            args = ("cross",)
        if case in ("B", "C"):
            b.script(B=[{"write": CODE_WRONG}, {"write": CODE_GOOD}], C=[{"write": {**SUITE_GOOD, **CODE_GOOD}}])
    calls_before = len(b.calls())
    code, out, err = b.cli(*args)
    assert code == 2 and err.strip().startswith("code_bench: error: check_infra"), (out, err)
    assert MARKER not in out + err
    assert any(x.get("event") == "check_infra" and MARKER in (x.get("detail") or "") for x in b.private())
    if case == "T":
        assert not (cb.suite_dir(b.root, "code-01", "sonnet-5-5@high", 1) / "meta.json").exists()
        assert len(b.calls()) == 1                                         # run 2 never started
    elif case == "fit":
        assert not (cb.suite_dir(b.root, "code-01", "sonnet-5-5@high", 1) / "fit.json").exists()
        assert "code-01" not in cb.given_of(b.root)
    elif case == "cross":
        pairs = [v for v in json.loads((b.root / "cross.json").read_text()).values() if v.get("suite")]
        assert pairs == [] and len(b.calls()) == calls_before
    else:
        assert not (cb.run_dir_of(b.root, "code-01", "haiku-5-5@high", case, 1) / "meta.json").exists()
        assert len(b.calls()) == 1                                         # no second try, no run 2
        assert all(x["result"] == "check_infra" for x in b.public(kind="check"))   # no line reads infra as a result
    state["on"] = False                                                   # the runner works again
    b.script(T=[{"write": SUITE_GOOD}], A=[{"write": CODE_GOOD}], B=[{"write": CODE_GOOD}],
             C=[{"write": {**SUITE_GOOD, **CODE_GOOD}}])
    code, out, err = b.cli(*args)
    assert code == 0, err
    if case == "T":
        assert b.suite_meta("sonnet-5-5@high", 1)["red"] is True
    elif case == "fit":
        assert cb.given_of(b.root)["code-01"]["suite"] == "sonnet-5-5@high#1"
    elif case == "cross":
        assert [x["result"] for x in b.public(what="cross")] == ["check_infra", "pass", "pass"]
    else:
        m = b.run_meta("haiku-5-5@high", case)
        assert m["correct"] is True and m["tries"] == 1


@pytest.mark.parametrize("arm", ["B", "C"])
def test_the_note_that_says_why_a_try_failed_survives_a_long_check_output(tmp_path, monkeypatch, arm):
    b = MB(tmp_path, monkeypatch, task_over={"runner_config": ["pytest.ini"]})
    loud = {"tests/test_mul_w.py": "from mod import mul\n\ndef test_mul_w():\n    assert mul(2, 3) == 6, 'x' * 6000\n"}
    b.seed_suite("sonnet-5-5@high", 1, loud, fit=True)
    b.give("sonnet-5-5@high#1")
    many = {"tests/test_many.py": "import pytest\n\n@pytest.mark.parametrize('i', range(6000))\n"
                                  "def test_many(i):\n    assert i >= 0\n"}
    b.script(B=[{"write": {"pytest.ini": "[pytest]\n", **CODE_WRONG}}, {"write": CODE_GOOD}],
             C=[{"write": many}, {"write": {**SUITE_GOOD, **CODE_GOOD}, "delete": ["tests/test_many.py"]}])
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", arm, "--rounds", "1")[0] == 0
    second = b.calls()[1]["prompt"]
    note = cb.NOTE_LOCKED if arm == "B" else cb.NOTE_OWN_NOT_RED
    output = second.split(cb.RETRY_LINE + "\n")[1]
    assert output.startswith(note) and len(output) <= cb.DETAIL_MAX
    assert ("x" * 200 if arm == "B" else "6000 passed") in output and len(output) > 3000   # the output's tail follows


def test_the_claude_version_must_match_as_a_whole_version(tmp_path, monkeypatch):
    assert cb.version_matches("2.1.325 (Claude Code)", "2.1.325") and cb.version_matches("2.1.325", "2.1.325")
    for other in ("2.1.3251 (Claude Code)", "2.1.325.1 (Claude Code)", "2.1.32 (Claude Code)"):
        assert not cb.version_matches(other, "2.1.325")
    b = MB(tmp_path, monkeypatch)
    for other in ("2.1.3251 (Claude Code)", "2.1.325.1 (Claude Code)"):
        monkeypatch.setenv("CODE_FAKE_VERSION", other)
        code, out, err = b.cli("write-tests", "--cells", "sonnet-5-5@high")
        assert (code, err.strip()) == (2, "code_bench: error: version_mismatch") and b.calls() == []


def _analysis():
    src = os.environ.get("CODE_BENCH_ANALYSIS_UNDER_TEST") or EVALS / "probes" / "code_bench_analysis.py"
    spec = importlib.util.spec_from_file_location("code_bench_analysis_for_bench", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_run_cut_by_the_spend_stop_is_made_again_and_the_analysis_reads_its_final_incarnation(tmp_path, monkeypatch):
    b = MB(tmp_path, monkeypatch)
    b.seed_suite("sonnet-5-5@high", 1, SUITE_GOOD, fit=True)
    b.give("sonnet-5-5@high#1")
    b.script(B=[{"write": CODE_WRONG, "cost": 1.0}])
    code, out, _ = b.cli("code", "--cells", "haiku-5-5@high", "--arms", "B", "--rounds", "1", "--max-usd", "2.0")
    assert code == 3 and not (cb.run_dir_of(b.root, "code-01", "haiku-5-5@high", "B", 1) / "meta.json").exists()
    b.script(B=[{"write": CODE_GOOD, "cost": 1.0}])
    assert b.cli("code", "--cells", "haiku-5-5@high", "--arms", "B", "--rounds", "1", "--max-usd", "10")[0] == 0
    assert [(x["try"], x["attempt"]) for x in b.public(kind="model")] == [(1, 1), (2, 1), (1, 1)]
    an = _analysis()
    lines = an.read_record(b.results)
    o = an.c_outcome(an.group(lines)["C"][("code-01", "haiku-5-5@high", "B", 1)], "B")
    m = b.run_meta("haiku-5-5@high", "B")
    assert (o["tries"], o["correct"], o["correct_first"], o["finished"]) == (m["tries"], m["correct"],
                                                                            m["correct_first"], m["finished"])
    assert o["cost"] == m["cost_usd"] == 1.0 and o["cut_cost"] == 2.0
    assert an.spend_of(lines)["total"] == 3.0
