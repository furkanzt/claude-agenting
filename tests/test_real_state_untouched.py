"""Runs a hook round-trip under AGENTING_STATE_DIR and asserts the real
~/.claude state files did not change -- proof the override is honoured."""

import hashlib
import unittest
from pathlib import Path

from _util import CONTINUITY, GUARD, HookTestCase

REAL = [Path.home() / ".claude" / ".agenting-session-state.json",
        Path.home() / ".claude" / ".routing-approvals.json"]


def fingerprint(p):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


class RealStateUntouched(HookTestCase):
    def test_override_keeps_real_files_unchanged(self):
        before = [fingerprint(p) for p in REAL]
        sid = "real-state-probe"
        self.run_hook(CONTINUITY, {"session_id": sid, "source": "startup"})
        self.record(sid, "--mode", "manual", "--workflows", "on")
        self.run_script(GUARD, "--approve", "abc123", "--session", sid)
        self.run_hook(GUARD, {"session_id": sid, "tool_name": "Workflow",
                              "tool_input": {"script": "await agent('x', {model:'haiku', effort:'low'})"}})
        self.assertEqual([fingerprint(p) for p in REAL], before)
        self.assertTrue((self.state_dir / ".agenting-session-state.json").exists())
        self.assertTrue((self.state_dir / ".routing-approvals.json").exists())


if __name__ == "__main__":
    unittest.main()
