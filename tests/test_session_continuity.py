"""Pipe tests for hooks/session-continuity.py."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _util import CONTINUITY, HookTestCase

SID = "11111111-2222-3333-4444-555555555555"
SID2 = "99999999-2222-3333-4444-555555555555"
TEAMS_VAR = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
ADVISOR_OFF_VAR = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"
ADVISOR_NOTE = ("(agents you start inherit it; workers work alone: put the work-alone sentence "
                "in each agent prompt, agenting: agents carry it; see the skill)")
OFF_NOTE = ("teammates=off (when a job fits teammates, tell the user once in this chat "
            "how to turn them on; see the skill's teammates section)")
STANDING = ("workflows=on (standing: the user set this for all chats; run Workflows for "
            "substantive tasks without re-asking)")


class ContinuityCase(HookTestCase):
    """HookTestCase with a temp HOME and no teammates or advisor switch, so the settings
    fallbacks never read the real ~/.claude or the shell's environment."""

    def setUp(self):
        super().setUp()
        self._home = tempfile.TemporaryDirectory()
        self._cwd = tempfile.TemporaryDirectory()
        self.home = Path(self._home.name)
        self.cwd = Path(self._cwd.name)
        self.env["HOME"] = str(self.home)
        self.env.pop(TEAMS_VAR, None)
        self.env.pop(ADVISOR_OFF_VAR, None)

    def tearDown(self):
        self._home.cleanup()
        self._cwd.cleanup()
        super().tearDown()

    def write_settings(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")

    def start(self, session=SID, source="startup"):
        out = self.run_hook(CONTINUITY, {"session_id": session, "cwd": str(self.cwd), "source": source})
        return out["hookSpecificOutput"]["additionalContext"]

    def status_here(self):
        """--status run with the temp project directory as cwd (it reads cwd's settings)."""
        r = subprocess.run([sys.executable, str(CONTINUITY), "--status", "--session", SID],
                           capture_output=True, text=True, timeout=20, env=self.env, cwd=str(self.cwd))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def record_default(self, value):
        r = self.run_script(CONTINUITY, "--record-default", "--workflows", value)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout


class Seeding(ContinuityCase):
    def test_new_session_is_seeded_with_defaults(self):
        self.session_start(SID)
        entry = self.read_state()[SID]
        self.assertEqual(entry["mode"], "auto")
        self.assertEqual(entry["disposition"], "balanced")
        self.assertIsNone(entry["workflows"])

    def test_message_is_one_short_line(self):
        msg = self.start()  # temp HOME and cwd: the owner's own advisorModel must not lengthen the line
        self.assertNotIn("\n", msg)
        self.assertTrue(msg.startswith("[agenting] mode=auto · disposition=balanced · "
                                       "workflows=not opted in"), msg)
        self.assertIn(f"(session {SID})", msg)
        self.assertIn(f'python3 "{CONTINUITY}" --record --session {SID}', msg)
        self.assertIn("[--workflows on|off]", msg)
        self.assertIn("Load the agenting skill before moving bulk work off this chat or starting an agent, teammate or Workflow.", msg)
        # Everything except the script path and the session id stays short; the
        # teammates=off note (about 150 characters) is part of the budget. The ceiling went
        # from 450 to 465 for " · advisor=off" (14 characters; the line is 460 long now).
        # The longer advisor=<model> form is not measured here: it only shows with an advisor.
        fixed = len(msg) - len(str(CONTINUITY)) - 2 * len(SID)
        self.assertLess(fixed, 465, msg)

    def test_message_never_asks(self):
        msg = self.session_start(SID)
        self.assertNotIn("AskUserQuestion", msg)
        self.assertNotIn("?", msg)

    def test_clear_starts_a_fresh_continuum(self):
        self.session_start(SID)
        self.record(SID, "--mode", "manual", "--workflows", "on")
        msg = self.session_start(SID, source="clear")
        self.assertIn("mode=auto", msg)
        self.assertIn("workflows=not opted in", msg)


class RecordAndStatus(ContinuityCase):
    def test_record_then_status(self):
        out = self.record(SID, "--mode", "manual", "--disposition", "quality")
        self.assertIn("mode=manual", out)
        self.assertIn("disposition=quality", out)
        st = self.status(SID)
        self.assertIn(f"session {SID}: mode=manual · disposition=quality · "
                      "workflows=not opted in", st)

    def test_status_without_state_reports_defaults(self):
        st = self.status(SID)
        self.assertIn("no state recorded", st)
        self.assertIn("mode=auto · disposition=balanced · workflows=not opted in", st)

    def test_record_survives_compaction(self):
        self.session_start(SID)
        self.record(SID, "--mode", "manual", "--disposition", "fast")
        msg = self.session_start(SID, source="compact")
        self.assertIn("mode=manual · disposition=fast", msg)

    def test_record_needs_a_value(self):
        r = self.run_script(CONTINUITY, "--record", "--session", SID)
        self.assertNotEqual(r.returncode, 0)

    def test_semi_auto_is_no_longer_a_valid_mode(self):
        r = self.run_script(CONTINUITY, "--record", "--session", SID, "--mode", "semi-auto")
        self.assertNotEqual(r.returncode, 0)

    def test_suggestion_flag_is_gone(self):
        r = self.run_script(CONTINUITY, "--record", "--session", SID, "--suggestion", "on")
        self.assertNotEqual(r.returncode, 0)  # nothing recognised to record


class WorkflowsOptIn(ContinuityCase):
    def test_workflows_on_persists_across_compaction(self):
        self.session_start(SID)
        self.record(SID, "--workflows", "on")
        self.assertEqual(self.read_state()[SID]["workflows"], "on")
        msg = self.session_start(SID, source="compact")
        self.assertIn("workflows=on", msg)
        self.assertIn("opted in for this chat", msg)
        self.assertIn("without re-asking", msg)
        self.assertIn("workflows=on", self.status(SID))

    def test_workflows_off(self):
        self.record(SID, "--workflows", "on")
        self.record(SID, "--workflows", "off")
        self.assertIn("workflows=off", self.session_start(SID, source="resume"))

    def test_workflows_flag_leaves_mode_and_disposition_alone(self):
        self.record(SID, "--mode", "manual", "--disposition", "quality")
        self.record(SID, "--workflows", "on")
        entry = self.read_state()[SID]
        self.assertEqual((entry["mode"], entry["disposition"]), ("manual", "quality"))


class LegacyState(ContinuityCase):
    LEGACY = {SID: {"mode": "semi-auto", "disposition": "balanced",
                    "suggestion": "on", "updated": "2026-09-18T00:00:00Z"}}

    def test_legacy_semi_auto_reads_as_manual(self):
        self.write_state(self.LEGACY)
        msg = self.session_start(SID, source="compact")
        self.assertIn("mode=manual", msg)
        self.assertNotIn("semi-auto", msg)
        self.assertIn("mode=manual", self.status(SID))

    def test_legacy_suggestion_is_not_mapped_to_workflows(self):
        self.write_state(self.LEGACY)
        self.assertIn("workflows=not opted in", self.session_start(SID, source="compact"))

    def test_record_rewrites_legacy_entry(self):
        self.write_state(self.LEGACY)
        self.record(SID, "--disposition", "fast")
        entry = self.read_state()[SID]
        self.assertEqual(entry["mode"], "manual")
        self.assertNotIn("suggestion", entry)

    def test_unreadable_mode_reads_as_manual(self):
        self.write_state({SID: {"mode": "???"}})
        self.assertIn("mode=manual", self.session_start(SID, source="compact"))

    def test_corrupt_state_file_does_not_crash(self):
        self.state_file.write_text("{not json", encoding="utf-8")
        self.assertIn("mode=auto", self.session_start(SID))

    def test_non_dict_entry_does_not_crash(self):
        self.write_state({SID: "garbage"})
        self.assertIn("mode=auto", self.session_start(SID))

class Teammates(ContinuityCase):
    def test_teammates_on_from_the_environment(self):
        self.env[TEAMS_VAR] = "TRUE"
        msg = self.start()
        self.assertIn(" · teammates=on · advisor=off (session", msg)
        self.assertNotIn("teammates=off", msg)

    def test_teammates_off_when_absent_everywhere(self):
        msg = self.start()
        self.assertIn(OFF_NOTE, msg)
        self.assertNotIn("teammates=on", msg)

    def test_teammates_off_note_text(self):
        msg = self.start()
        self.assertIn(f"workflows=not opted in · {OFF_NOTE} · advisor=off (session {SID})", msg)
        self.assertNotIn("\n", msg)
        self.assertNotIn("?", msg)

    def test_teammates_on_from_the_user_settings_file(self):
        self.write_settings(self.home / ".claude" / "settings.json", {"env": {TEAMS_VAR: "1"}})
        self.assertIn(" · teammates=on · advisor=off (session", self.start())

    def test_teammates_on_from_the_project_local_settings_file(self):
        self.write_settings(self.cwd / ".claude" / "settings.local.json", {"env": {TEAMS_VAR: "true"}})
        self.assertIn(" · teammates=on · advisor=off (session", self.start())

    def test_environment_variable_beats_the_settings_files(self):
        self.write_settings(self.home / ".claude" / "settings.json", {"env": {TEAMS_VAR: "1"}})
        self.env[TEAMS_VAR] = "0"
        self.assertIn(OFF_NOTE, self.start())

    def test_non_object_settings_file_counts_as_absent(self):
        self.write_settings(self.home / ".claude" / "settings.json", "[1, 2, 3]")
        self.write_settings(self.cwd / ".claude" / "settings.json", "{not json")
        self.write_settings(self.cwd / ".claude" / "settings.local.json", {"env": [TEAMS_VAR]})
        self.assertIn(OFF_NOTE, self.start())

    def test_status_prints_the_teammates_value(self):
        self.assertIn("teammates=off", self.status(SID))
        self.env[TEAMS_VAR] = "1"
        self.assertIn("teammates=on", self.status(SID))


class Advisor(ContinuityCase):
    def settings(self, where, model):
        path = {"home": self.home / ".claude" / "settings.json",
                "project": self.cwd / ".claude" / "settings.json",
                "local": self.cwd / ".claude" / "settings.local.json"}[where]
        self.write_settings(path, {"advisorModel": model} if model is not None else {})

    def test_advisor_is_off_when_nothing_names_one(self):
        msg = self.start()
        self.assertIn(f" · {OFF_NOTE} · advisor=off (session {SID})", msg)
        self.assertNotIn("\n", msg)

    def test_advisor_line_carries_the_model_and_the_work_alone_note(self):
        self.settings("home", "fable-5.2")
        msg = self.start()
        self.assertIn(f" · advisor=fable-5.2 {ADVISOR_NOTE} (session {SID})", msg)
        self.assertNotIn("advisor=off", msg)
        self.assertNotIn("\n", msg)
        self.assertNotIn("?", msg)

    def test_advisor_from_each_settings_file(self):
        for where in ("local", "project", "home"):
            with self.subTest(where=where):
                for f in (self.home / ".claude", self.cwd / ".claude"):
                    for name in ("settings.json", "settings.local.json"):
                        (f / name).unlink(missing_ok=True)
                self.settings(where, f"model-{where}")
                self.assertIn(f" · advisor=model-{where} (agents", self.start())

    def test_advisor_settings_files_are_read_local_then_project_then_user(self):
        self.settings("home", "from-home")
        self.settings("project", "from-project")
        self.assertIn("advisor=from-project (", self.start())
        self.settings("local", "from-local")
        self.assertIn("advisor=from-local (", self.start())
        self.settings("local", None)
        self.assertIn("advisor=from-project (", self.start())

    def test_environment_switch_beats_every_settings_file(self):
        for where in ("local", "project", "home"):
            self.settings(where, "some-model")
        for value in ("1", "true", "YES", " True "):
            with self.subTest(value=value):
                self.env[ADVISOR_OFF_VAR] = value
                self.assertIn(f" · advisor=off (session {SID})", self.start())
        self.env[ADVISOR_OFF_VAR] = "0"  # not truthy: the settings decide again
        self.assertIn("advisor=some-model (", self.start())

    def test_invalid_json_and_non_string_values_are_skipped(self):
        self.write_settings(self.cwd / ".claude" / "settings.local.json", "{not json")
        self.settings("project", 7)
        self.write_settings(self.home / ".claude" / "settings.json",
                            {"advisorModel": "", "env": {"advisorModel": "nested"}})
        self.assertIn(f" · advisor=off (session {SID})", self.start())
        self.write_settings(self.cwd / ".claude" / "settings.local.json", {"advisorModel": ["a"]})
        self.write_settings(self.cwd / ".claude" / "settings.json", [1, 2])
        self.settings("home", "   ")
        self.assertIn(" · advisor=off (", self.start())
        self.settings("home", "last-resort")  # a bad file does not hide a later good one
        self.assertIn("advisor=last-resort (", self.start())

    def test_status_prints_the_advisor_value(self):
        self.assertIn(f" · {OFF_NOTE} · advisor=off · standing default: workflows=unset", self.status_here())
        self.settings("project", "fable-5.2")
        out = self.status_here()
        self.assertIn(f"advisor=fable-5.2 {ADVISOR_NOTE} · standing default", out)
        self.env[ADVISOR_OFF_VAR] = "1"
        self.assertIn("advisor=off", self.status_here())


class StandingDefault(ContinuityCase):
    def test_default_is_recorded_and_shown_by_status(self):
        out = self.record_default("on")
        self.assertIn("standing default: workflows=on", out)
        self.assertEqual(self.read_state()["_defaults"], {"workflows": "on"})
        self.assertIn("standing default: workflows=on", self.status(SID))
        self.assertIn("standing default: workflows=on",
                      self.run_script(CONTINUITY, "--status").stdout)

    def test_new_session_is_seeded_from_the_default_and_labelled_standing(self):
        self.record_default("on")
        msg = self.start()
        self.assertIn(STANDING, msg)
        entry = self.read_state()[SID]
        self.assertEqual((entry["workflows"], entry["workflows_source"]), ("on", "default"))
        self.assertIn(STANDING, self.start(source="compact"))

    def test_existing_session_is_untouched_by_a_later_default(self):
        self.start()
        self.record_default("on")
        self.assertIsNone(self.read_state()[SID]["workflows"])
        self.assertIn("workflows=not opted in", self.start(source="resume"))
        self.assertNotIn("standing", self.start(source="resume"))

    def test_per_chat_record_clears_the_standing_mark(self):
        self.record_default("on")
        self.start()
        self.record(SID, "--workflows", "off")
        entry = self.read_state()[SID]
        self.assertEqual(entry["workflows"], "off")
        self.assertNotIn("workflows_source", entry)
        self.assertNotIn("standing", self.start(source="compact"))

    def test_unset_removes_the_default(self):
        self.record_default("on")
        self.record_default("unset")
        self.assertNotIn("_defaults", self.read_state())
        self.assertIn("standing default: workflows=unset", self.status(SID))
        self.assertIn("workflows=not opted in", self.start(SID2))

    def test_defaults_key_survives_pruning_and_is_not_a_session(self):
        self.record_default("on")
        for i in range(25):
            self.record(f"s{i:02d}", "--mode", "manual")
        state = self.read_state()
        self.assertEqual(state["_defaults"], {"workflows": "on"})
        self.assertEqual(len([k for k in state if k != "_defaults"]), 20)

    def test_record_default_needs_no_session_and_rejects_bad_values(self):
        r = self.run_script(CONTINUITY, "--record-default", "--workflows", "maybe")
        self.assertNotEqual(r.returncode, 0)
        r = self.run_script(CONTINUITY, "--record-default")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.state_file.exists())
        r = self.run_script(CONTINUITY, "--record", "--session", SID, "--workflows", "unset")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
