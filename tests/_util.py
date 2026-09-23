"""Shared helpers for the hook pipe tests.

Every hook runs as a subprocess with JSON on stdin, the way Claude Code runs it,
and with AGENTING_STATE_DIR pointed at a fresh temporary directory, so no test
reads or writes the real ~/.claude state files.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

CONTINUITY = HOOKS / "session-continuity.py"
GUARD = HOOKS / "workflow-routing-guard.py"
FINISH = HOOKS / "workflow-finish-check.py"


class HookTestCase(unittest.TestCase):
    """Gives each test its own AGENTING_STATE_DIR."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)
        self.env = dict(os.environ, AGENTING_STATE_DIR=str(self.state_dir))

    def tearDown(self):
        self._tmp.cleanup()

    # -- running things ------------------------------------------------------

    def run_script(self, script, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(script), *args],
            input=stdin, capture_output=True, text=True, timeout=20, env=self.env,
        )

    def run_hook(self, script, payload):
        """Pipe a hook payload in; return parsed JSON output, or None if silent."""
        r = self.run_script(script, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.strip()
        return json.loads(out) if out else None

    # -- state ---------------------------------------------------------------

    @property
    def state_file(self):
        return self.state_dir / ".agenting-session-state.json"

    def read_state(self):
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def write_state(self, data):
        self.state_file.write_text(json.dumps(data), encoding="utf-8")

    def record(self, session, *flags):
        r = self.run_script(CONTINUITY, "--record", "--session", session, *flags)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def status(self, session):
        return self.run_script(CONTINUITY, "--status", "--session", session).stdout

    def session_start(self, session, source="startup"):
        out = self.run_hook(CONTINUITY, {"session_id": session, "cwd": "/tmp", "source": source})
        self.assertIsNotNone(out)
        return out["hookSpecificOutput"]["additionalContext"]
