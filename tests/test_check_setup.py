"""Run scripts/check-setup.py against odd ~/.claude/settings.json files.

Each class runs the health check once per distinct setup (a run takes a few seconds), in a
fresh temporary HOME and AGENTING_STATE_DIR, so the real ~/.claude is never read or written.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _util import ROOT

SCRIPT = ROOT / "scripts" / "check-setup.py"
SUMMARY = re.compile(r"^  \d+ passed, \d+ failed, \d+ warnings$", re.M)
SETTINGS_MISSING = object()


class CheckSetupCase(unittest.TestCase):
    """Subclasses set SETTINGS (raw text, or SETTINGS_MISSING) and optionally EMPTY_PLUGIN_ROOT."""

    SETTINGS = SETTINGS_MISSING
    EMPTY_PLUGIN_ROOT = False

    @classmethod
    def setUpClass(cls):
        if cls is CheckSetupCase:
            raise unittest.SkipTest("base class")
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        home, state, plugin = tmp / "home", tmp / "state", tmp / "plugin"
        for d in (home / ".claude", state, plugin):
            d.mkdir(parents=True)
        if cls.SETTINGS is not SETTINGS_MISSING:
            (home / ".claude" / "settings.json").write_text(cls.SETTINGS, encoding="utf-8")
        env = dict(os.environ, HOME=str(home), AGENTING_STATE_DIR=str(state),
                   CLAUDE_PLUGIN_ROOT=str(plugin if cls.EMPTY_PLUGIN_ROOT else ROOT))
        cls.result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                    text=True, timeout=120, env=env)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def line(self, name):
        """The stdout line of the check called `name`, or None."""
        for ln in self.result.stdout.splitlines():
            if re.match(rf"^  \[(PASS|FAIL|WARN)\] {re.escape(name)}(  |$)", ln):
                return ln
        return None

    def assertCheck(self, name, status):
        ln = self.line(name)
        self.assertIsNotNone(ln, f"no line for {name!r}\n{self.result.stdout}")
        self.assertTrue(ln.startswith(f"  [{status}] "), ln)

    def assertRanToTheEnd(self):
        self.assertNotIn("Traceback", self.result.stderr)
        self.assertRegex(self.result.stdout, SUMMARY)


class NonObjectChecks:
    """Mixin: what every valid-JSON-but-not-an-object settings.json must produce."""

    def test_should_fail_the_parse_check_and_still_print_a_summary_when_settings_is_not_an_object(self):
        self.assertCheck("settings.json parses", "FAIL")
        self.assertIn("not a JSON object (" + self.KIND + ")", self.line("settings.json parses"))
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 1)

    def test_should_keep_running_the_later_sections_when_settings_is_not_an_object(self):
        self.assertCheck("agent definitions found", "PASS")
        self.assertCheck("guard registered on PreToolUse", "PASS")  # via the plugin's hooks.json


class TestSettingsIsAList(NonObjectChecks, CheckSetupCase):
    SETTINGS, KIND = "[]", "list"


class TestSettingsIsNull(NonObjectChecks, CheckSetupCase):
    SETTINGS, KIND = "null", "NoneType"


class TestSettingsIsANumber(NonObjectChecks, CheckSetupCase):
    SETTINGS, KIND = "1", "int"


class TestSettingsIsNotJson(CheckSetupCase):
    SETTINGS = "{not json"

    def test_should_fail_the_parse_check_and_exit_1_when_settings_is_not_json(self):
        self.assertCheck("settings.json parses", "FAIL")
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 1)


class TestSettingsIsMissing(CheckSetupCase):
    def test_should_pass_the_parse_check_when_there_is_no_settings_file(self):
        self.assertCheck("settings.json parses", "PASS")
        self.assertRanToTheEnd()


class TestHooksKeyIsAList(CheckSetupCase):
    """No hooks.json in the plugin root, so only settings.json could register the guard."""

    EMPTY_PLUGIN_ROOT = True
    SETTINGS = json.dumps({"hooks": ["workflow-routing-guard"]})

    def test_should_count_a_hooks_list_as_not_registered_without_crashing(self):
        self.assertCheck("settings.json parses", "PASS")
        self.assertIn("not registered anywhere", self.line("guard registered on PreToolUse"))
        self.assertCheck("guard registered on PreToolUse", "FAIL")
        self.assertRanToTheEnd()


class TestPreToolUseGroupIsAString(CheckSetupCase):
    """With the plugin's own hooks.json present, a bad settings.json entry does not hide it."""

    SETTINGS = json.dumps({"hooks": {"PreToolUse": ["workflow-routing-guard"]}})

    def test_should_not_crash_and_fall_back_to_the_plugin_hooks_json_when_a_group_is_a_string(self):
        self.assertCheck("guard registered on PreToolUse", "PASS")
        self.assertRanToTheEnd()


class TestEveryWrongShapedEntryIsIgnored(CheckSetupCase):
    """No hooks.json in the plugin root, so only settings.json could register the guard."""

    EMPTY_PLUGIN_ROOT = True
    SETTINGS = json.dumps({"hooks": {"PreToolUse": [
        "workflow-routing-guard",
        {"hooks": "workflow-routing-guard"},
        {"hooks": ["workflow-routing-guard", 7, None]},
        {"hooks": [{"command": ["workflow-routing-guard"]}, {"command": None}, {"command": 5}]},
    ]}})

    def test_should_count_none_as_registered_when_every_entry_has_the_wrong_shape(self):
        self.assertIn("not registered anywhere", self.line("guard registered on PreToolUse"))
        self.assertCheck("guard registered on PreToolUse", "FAIL")
        self.assertRanToTheEnd()


class TestWellFormedEntryRegistersTheGuard(CheckSetupCase):
    EMPTY_PLUGIN_ROOT = True
    SETTINGS = json.dumps({"hooks": {"PreToolUse": [
        "junk", {"hooks": [7, {"command": 5}, {"command": "python3 /x/workflow-routing-guard.py"}]},
    ]}})

    def test_should_register_the_guard_when_a_valid_entry_sits_beside_bad_ones(self):
        self.assertCheck("guard registered on PreToolUse", "PASS")
        self.assertRanToTheEnd()


if __name__ == "__main__":
    unittest.main()
