"""Pipe tests for hooks/session-continuity.py."""

import unittest

from _util import CONTINUITY, HookTestCase

SID = "11111111-2222-3333-4444-555555555555"


class Seeding(HookTestCase):
    def test_new_session_is_seeded_with_defaults(self):
        self.session_start(SID)
        entry = self.read_state()[SID]
        self.assertEqual(entry["mode"], "auto")
        self.assertEqual(entry["disposition"], "balanced")
        self.assertIsNone(entry["workflows"])

    def test_message_is_one_short_line(self):
        msg = self.session_start(SID)
        self.assertNotIn("\n", msg)
        self.assertTrue(msg.startswith("[agenting] mode=auto · disposition=balanced · "
                                       "workflows=not opted in"), msg)
        self.assertIn(f"(session {SID})", msg)
        self.assertIn(f'python3 "{CONTINUITY}" --record --session {SID}', msg)
        self.assertIn("[--workflows on|off]", msg)
        self.assertIn("Load the agenting skill before authoring a Workflow.", msg)
        # Everything except the script path and the session id stays short.
        fixed = len(msg) - len(str(CONTINUITY)) - 2 * len(SID)
        self.assertLess(fixed, 300, msg)

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


class RecordAndStatus(HookTestCase):
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


class WorkflowsOptIn(HookTestCase):
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


class LegacyState(HookTestCase):
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


if __name__ == "__main__":
    unittest.main()
