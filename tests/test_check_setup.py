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
    TEAMS = None             # value of CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS in the child; None removes it
    ADVISOR_SWITCH = None    # value of CLAUDE_CODE_DISABLE_ADVISOR_TOOL in the child; None removes it
    RECORD_DEFAULT = None    # "on"/"off": record the standing Workflows default first
    PLUGIN_HOOKS_JSON = None  # text of hooks/hooks.json in a temp plugin root (implies EMPTY_PLUGIN_ROOT)
    PLAN_ACCOUNT = None      # the oauthAccount object of <HOME>/.claude.json; None = no such file (no plan)

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
        if cls.PLAN_ACCOUNT is not None:
            (home / ".claude.json").write_text(json.dumps({"oauthAccount": cls.PLAN_ACCOUNT}), encoding="utf-8")
        if cls.PLUGIN_HOOKS_JSON is not None:
            (plugin / "hooks").mkdir()
            (plugin / "hooks" / "hooks.json").write_text(cls.PLUGIN_HOOKS_JSON, encoding="utf-8")
        env = dict(os.environ, HOME=str(home), AGENTING_STATE_DIR=str(state),
                   CLAUDE_PLUGIN_ROOT=str(plugin if cls.EMPTY_PLUGIN_ROOT or cls.PLUGIN_HOOKS_JSON is not None else ROOT))
        env.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
        env.pop("CLAUDE_CODE_DISABLE_ADVISOR_TOOL", None)
        env.pop("AGENTING_PLAN_FILE", None)      # the plan is read from <temp HOME>/.claude.json
        if cls.ADVISOR_SWITCH is not None:
            env["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"] = cls.ADVISOR_SWITCH
        if cls.TEAMS is not None:
            env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = cls.TEAMS
        if cls.RECORD_DEFAULT:
            subprocess.run([sys.executable, str(ROOT / "hooks" / "session-continuity.py"),
                            "--record-default", "--workflows", cls.RECORD_DEFAULT],
                           capture_output=True, text=True, timeout=20, env=env, cwd=str(tmp))
        # cwd is the temp dir, so no project .claude/settings.json of this repo is read
        cls.result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                    text=True, timeout=120, env=env, cwd=str(tmp))

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


AGENT_GUARD_CHECKS = (
    "agent guard script found",
    "an Agent start with no model and no effort is DENIED",
    "an Agent start with model and effort passes silently",
    "an agenting: agent passes without model or effort on the call",
    "a named teammate with no agent file is DENIED even with model and effort",
    "the guard never emits allow",
    "garbage input exits 0 silently",
)
WIRING = "agent guard registered on PreToolUse for Agent"
OFF_DETAIL = ('Useful when 3-5 long-running workers must talk to each other. Turn on: add '
              '"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" under "env" in ~/.claude/settings.json '
              "(experimental; uses more tokens than subagents).")


class TestAgentGuardSection(CheckSetupCase):
    TEAMS = "0"  # the section must not depend on the caller's shell

    def test_should_pass_every_agent_guard_check_on_this_repo(self):
        for name in AGENT_GUARD_CHECKS:
            self.assertCheck(name, "PASS")
        self.assertCheck(WIRING, "PASS")
        self.assertRanToTheEnd()


class TestAgentEntryMissingFromHooksJson(CheckSetupCase):
    PLUGIN_HOOKS_JSON = json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Workflow", "hooks": [
            {"type": "command", "command": "python3 x/workflow-routing-guard.py"}]},
    ]}})

    def test_should_fail_the_wiring_check_when_hooks_json_has_no_agent_entry(self):
        self.assertCheck(WIRING, "FAIL")
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 1)


class TestTeammatesOn(CheckSetupCase):
    TEAMS = "1"

    def test_should_pass_teammates_on_when_the_variable_is_1(self):
        self.assertCheck("teammates: ON", "PASS")
        self.assertIsNone(self.line("teammates: OFF"))


class TestTeammatesOff(CheckSetupCase):
    def test_should_warn_teammates_off_with_the_turn_on_text_when_the_variable_is_absent(self):
        self.assertCheck("teammates: OFF", "WARN")
        self.assertIn(OFF_DETAIL, self.line("teammates: OFF"))
        self.assertIsNone(self.line("teammates: ON"))

    def test_should_keep_exit_code_0_when_only_the_teammates_warning_fires(self):
        self.assertRanToTheEnd()
        self.assertNotIn("FAIL]", self.result.stdout)
        self.assertEqual(self.result.returncode, 0)


SEEDED = "disposition is seeded immediately (balanced, or fast on a Pro plan), never null/unset"
RECORDED = "--record persists mode, disposition and the workflows opt-in"
PRO_START = "a Pro plan starts a new chat in fast and the user is told once"


class TestSessionChecksWithoutAPlan(CheckSetupCase):
    def test_should_pass_the_session_checks_and_the_made_up_pro_plan_check_when_no_plan_can_be_read(self):
        for name in (SEEDED, RECORDED, PRO_START, "--status reports what --record persisted"):
            self.assertCheck(name, "PASS")
        self.assertRanToTheEnd()


class TestSessionChecksOnAProPlan(CheckSetupCase):
    PLAN_ACCOUNT = {"organizationType": "claude_pro"}

    def test_should_pass_the_session_checks_when_the_account_is_on_a_pro_plan(self):
        for name in (SEEDED, RECORDED, PRO_START):
            self.assertCheck(name, "PASS")
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 0)


ADVISOR_ON = "advisor: fable-5.2 (agents inherit it; workers are told to work alone)"


class TestAdvisorOff(CheckSetupCase):
    def test_should_report_advisor_off_as_a_pass_when_no_advisor_is_configured(self):
        self.assertCheck("advisor: off", "PASS")
        self.assertIsNone(self.line(ADVISOR_ON))
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 0)


class TestAdvisorOn(CheckSetupCase):
    SETTINGS = json.dumps({"advisorModel": "fable-5.2"})

    def test_should_report_the_advisor_model_as_a_pass_when_settings_name_one(self):
        self.assertCheck(ADVISOR_ON, "PASS")
        self.assertIsNone(self.line("advisor: off"))
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 0)


class TestAdvisorSwitchedOffByTheEnvironment(CheckSetupCase):
    SETTINGS = json.dumps({"advisorModel": "fable-5.2"})
    ADVISOR_SWITCH = "1"

    def test_should_report_advisor_off_when_the_environment_switch_beats_the_settings(self):
        self.assertCheck("advisor: off", "PASS")
        self.assertIsNone(self.line(ADVISOR_ON))


ADVISOR_RULE_CHECKS = (
    "with an advisor, a Workflow whose workers are not told to work alone is DENIED",
    "with an advisor, a Workflow that carries the work-alone sentence is not denied for it",
    "with an advisor, an Agent start with no work-alone sentence is DENIED",
    "with an advisor, an Agent start that carries the sentence passes silently",
    "every agenting: worker agent carries the work-alone sentence, the design agent does not",
)


class TestAdvisorRuleSection(CheckSetupCase):
    ADVISOR_SWITCH = "1"   # the caller's own switch must not hide the probes that run with an advisor on

    def test_should_prove_the_work_alone_denials_with_the_advisor_on(self):
        for name in ADVISOR_RULE_CHECKS:
            self.assertCheck(name, "PASS")
        self.assertRanToTheEnd()
        self.assertEqual(self.result.returncode, 0)


class TestStandingDefaultRecorded(CheckSetupCase):
    RECORD_DEFAULT = "on"

    def test_should_show_standing_default_on_after_it_was_recorded(self):
        self.assertCheck("standing Workflows default: on", "PASS")


class TestStandingDefaultUnset(CheckSetupCase):
    def test_should_show_standing_default_unset_when_nothing_was_recorded(self):
        self.assertCheck("standing Workflows default: unset", "PASS")


class TestAgentGuardNameIsNotTheOldPluginId(CheckSetupCase):
    """hooks/agent-routing-guard.py and hooks.json carry "agent-routing-guard" in their text."""

    def test_should_not_flag_the_agent_guard_name_as_the_old_plugin_id_or_old_vocabulary(self):
        self.assertCheck('no stale "agent-routing" string survives the rename', "PASS")
        self.assertCheck("no pre-3.0.0 semi-auto / suggestion / log.csv vocabulary survives", "PASS")


if __name__ == "__main__":
    unittest.main()
