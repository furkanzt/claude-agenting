"""Pipe tests for hooks/workflow-finish-check.py.

Fixtures (tests/fixtures/):
  journal_retried.jsonl     trimmed copy of a real run: 23 started / 18 result
                            lines, where the 5 unanswered agentIds were
                            interrupted and restarted under the same key, and
                            every restart returned. The run is complete.
  journal_incomplete.jsonl  the same run with the 5 restarts removed:
                            18 logical agents, 13 returned.
  journal_complete.jsonl    small synthetic run, every agent returned.
"""

import json
import unittest

from _util import FINISH, FIXTURES, HookTestCase

INCOMPLETE_MISSING = ["classify:MAT.7.1-1", "classify:MAT.7.2", "verify:MAT.7.4-1",
                      "verify:MAT.7.6", "verify:MAT.7.7"]


def notification(journal, name="Phase 4 classify", status="completed"):
    return (
        "<task-notification>\n<task-id>w123</task-id>\n"
        f"<status>{status}</status>\n"
        f'<summary>Dynamic workflow "{name}" {status}</summary>\n'
        '<result>{"themes": []}</result>\n'
        f"<diagnostics>Per-agent results: {journal} — one "
        '{"type":"result",...} line per completed agent with its full return value.\n'
        "If the result above is empty or unexpected, Read this file BEFORE diagnosing."
        "</diagnostics>\n"
        "<usage><agent_count>18</agent_count><agents_done>18</agents_done></usage>\n"
        "</task-notification>"
    )


class FinishCheck(HookTestCase):
    def check(self, prompt):
        return self.run_hook(FINISH, {"session_id": "s", "hook_event_name": "UserPromptSubmit",
                                      "prompt": prompt})

    def context(self, prompt):
        out = self.check(prompt)
        self.assertIsNotNone(out, "expected a warning, got silence")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        return out["hookSpecificOutput"]["additionalContext"]

    # -- warns -----------------------------------------------------------------

    def test_incomplete_run_warns_with_counts_and_labels(self):
        journal = FIXTURES / "journal_incomplete.jsonl"
        ctx = self.context(notification(journal))
        self.assertTrue(ctx.startswith('[agenting] Workflow "Phase 4 classify": '
                                       "13 of 18 agents returned; missing: "), ctx)
        for label in INCOMPLETE_MISSING:
            self.assertIn(label, ctx)
        self.assertIn(f"Read {journal} and report the real count", ctx)
        self.assertIn("agenting skill", ctx)

    def test_label_list_is_capped_at_eight(self):
        journal = self.state_dir / "big" / "journal.jsonl"
        journal.parent.mkdir()
        rows = [{"type": "launched"}]
        rows += [{"type": "started", "key": f"k{i}", "agentId": f"a{i}", "label": f"part:{i}"}
                 for i in range(12)]
        rows.append({"type": "result", "key": "k0", "agentId": "a0", "result": "ok"})
        journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        ctx = self.context(notification(journal))
        self.assertIn("1 of 12 agents returned", ctx)
        self.assertIn("part:8", ctx)
        self.assertNotIn("part:9", ctx)
        self.assertIn("… and 3 more", ctx)

    def test_path_with_spaces(self):
        journal = self.state_dir / "dir with spaces" / "journal.jsonl"
        journal.parent.mkdir()
        journal.write_text((FIXTURES / "journal_incomplete.jsonl").read_text(encoding="utf-8"),
                           encoding="utf-8")
        self.assertIn("13 of 18", self.context(notification(journal)))

    def test_every_notification_in_one_prompt_is_checked(self):
        prompt = (notification(FIXTURES / "journal_complete.jsonl", name="A") + "\n"
                  + notification(FIXTURES / "journal_incomplete.jsonl", name="B"))
        ctx = self.context(prompt)
        self.assertIn('Workflow "B"', ctx)
        self.assertNotIn('Workflow "A"', ctx)

    def test_agent_without_key_falls_back_to_agent_id(self):
        journal = self.state_dir / "journal.jsonl"
        rows = [{"type": "started", "agentId": "a1", "label": "one"},
                {"type": "started", "agentId": "a2", "label": "two"},
                {"type": "result", "agentId": "a1", "result": "ok"}]
        journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        ctx = self.context(notification(journal))
        self.assertIn("1 of 2 agents returned; missing: two.", ctx)

    # -- silent ----------------------------------------------------------------

    def test_complete_run_is_silent(self):
        self.assertIsNone(self.check(notification(FIXTURES / "journal_complete.jsonl")))

    def test_restarted_agents_that_returned_are_not_missing(self):
        # 23 started vs 18 results by agentId, but every key has a result.
        self.assertIsNone(self.check(notification(FIXTURES / "journal_retried.jsonl")))

    def test_non_workflow_prompt_is_silent(self):
        self.assertIsNone(self.check("please fix the failing test in foo.py"))

    def test_other_task_notification_is_silent(self):
        prompt = ("<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n"
                  '<summary>Background command "npm test" completed</summary>\n'
                  "</task-notification>")
        self.assertIsNone(self.check(prompt))

    def test_unreadable_journal_is_silent(self):
        self.assertIsNone(self.check(notification(self.state_dir / "nope" / "journal.jsonl")))

    def test_journal_without_started_lines_is_silent(self):
        journal = self.state_dir / "journal.jsonl"
        journal.write_text('{"type":"launched"}\nnot json\n', encoding="utf-8")
        self.assertIsNone(self.check(notification(journal)))

    def test_malformed_stdin_is_silent(self):
        r = self.run_script(FINISH, stdin="{not json")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))


if __name__ == "__main__":
    unittest.main()
