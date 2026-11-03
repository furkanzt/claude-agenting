#!/usr/bin/env python3
"""Run the plugin's hooks-module tests (tests/*.test.ts, tests/*.test.tsx) with `claude plugin test`.

`claude plugin test <dir>` runs every *.test.ts and *.test.tsx under <dir> and takes no filter. At
the repo root that would also pick up files under the gitignored evals/private/ material, which is
not plugin code and must stay out of every test. So this copies only the plugin's own files (the
manifests, hooks/, types/, scripts/ and the test files) into a temporary folder and runs the command
there. Nothing is written inside the repo; no model is called.

usage: python3 scripts/quality/run_plugin_tests.py
Exit status: that of `claude plugin test` (0 when every test passes), 2 when there is nothing to run.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PARTS = (".claude-plugin", "hooks", "types", "scripts")
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def stage(dst: Path) -> list[Path]:
    """Copy the plugin's own files and test files into dst; return the test files copied."""
    for part in PLUGIN_PARTS:
        src = ROOT / part
        if src.is_dir():
            shutil.copytree(src, dst / part, ignore=SKIP)
    tests = sorted(p for p in (ROOT / "tests").iterdir() if p.name.endswith((".test.ts", ".test.tsx")))
    (dst / "tests").mkdir(parents=True, exist_ok=True)
    for t in tests:
        shutil.copy2(t, dst / "tests" / t.name)
    return tests


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / ROOT.name
        tests = stage(dst)
        if not tests:
            print("no tests/*.test.ts or tests/*.test.tsx to run", file=sys.stderr)
            return 2
        return subprocess.run(["claude", "plugin", "test", str(dst)]).returncode


if __name__ == "__main__":
    sys.exit(main())
