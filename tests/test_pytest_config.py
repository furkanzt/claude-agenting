"""pytest.ini keeps a bare `pytest` inside tests/ and out of the gitignored evals/private."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bare_pytest_collects_tests_and_never_walks_evals():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        shutil.copy(ROOT / "pytest.ini", tmp / "pytest.ini")
        (tmp / "tests").mkdir()
        (tmp / "tests" / "test_ok.py").write_text("def test_ok():\n    pass\n")
        trap = tmp / "evals" / "private" / "tasks" / "t" / "material" / "tests"
        trap.mkdir(parents=True)
        (trap / "test_trap.py").write_text("def test_trap():\n    pass\n")
        r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                           cwd=tmp, capture_output=True, text=True, timeout=60)
        assert "test_ok" in r.stdout, r.stdout + r.stderr
        assert "test_trap" not in r.stdout, r.stdout
        assert not list((tmp / "evals").rglob("__pycache__"))
