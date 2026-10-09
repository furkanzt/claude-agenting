"""Pipe tests for hooks/workflow-routing-guard.py."""

import json
import re
import shlex
import subprocess
import sys
import unittest

from _util import GUARD, HookTestCase

SID = "guard-test-session"
ROUTED = "await agent('x', {model:'haiku', effort:'low'})"
UNROUTED = "await agent('x', {schema:S})"
PLUGIN_AGENT = "await agent('trace it', {agentType:'agenting:researcher', effort:'medium'})"


class GuardCase(HookTestCase):
    def guard(self, script, session=SID, tool="Workflow", transcript=None):
        payload = {"session_id": session, "tool_name": tool, "tool_input": {"script": script}}
        if transcript is not None:
            payload["transcript_path"] = str(transcript)
        return self.run_hook(GUARD, payload)

    def transcript(self, *starts, name="chat.jsonl", extra=()):
        """Write a transcript shaped like Claude Code's: one SessionStart record per
        (mode, session) pair, in the two forms it stores them (the hook_additional_context
        attachment and the hook_success one with the hook's JSON stdout), plus `extra`."""
        records = []
        for mode, sid in starts:
            line = (f"[agenting] mode={mode} \u00b7 disposition=balanced \u00b7 workflows=not opted in "
                    f"(session {sid}). Record changes: python3 \"/x/session-continuity.py\" "
                    f"--record --session {sid} [--mode auto|manual]. Load the agenting skill.")
            records.append({"type": "attachment", "attachment": {
                "type": "hook_additional_context", "hookEvent": "SessionStart",
                "hookName": "SessionStart", "content": ["[other] hello", line]}})
            records.append({"type": "attachment", "attachment": {
                "type": "hook_success", "hookEvent": "SessionStart", "hookName": "SessionStart:resume",
                "stdout": json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                             "additionalContext": line}})}})
        records.extend(extra)
        path = self.state_dir / name
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def decision(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision")

    @staticmethod
    def reason(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


class StageOne(GuardCase):
    def test_unrouted_call_is_denied(self):
        out = self.guard(UNROUTED)
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("STAGE 1/2", self.reason(out))
        self.assertIn("agenting skill", self.reason(out))

    def test_model_without_effort_is_denied(self):
        self.assertIn("STAGE 1/2", self.reason(self.guard("await agent('x', {model:'opus'})")))

    def test_plugin_agent_type_without_effort_is_denied(self):
        out = self.guard("await agent('x', {agentType:'agenting:scanner'})")
        self.assertIn("STAGE 1/2", self.reason(out))

    def test_unrouted_is_denied_even_in_auto_mode(self):
        self.record(SID, "--mode", "auto")
        out = self.guard(UNROUTED)
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("STAGE 1/2", self.reason(out))

    def test_model_word_inside_prompt_is_not_routing(self):
        self.assertIn("STAGE 1/2", self.reason(self.guard("await agent('model: opus', {schema:S})")))

    def test_escape_hatch_counts_as_routed(self):
        out = self.guard("// routing: inherit\nawait agent('x', {schema:S})")
        self.assertIn("STAGE 2/2", self.reason(out))


class PluginAgentType(GuardCase):
    def test_prefixed_agent_type_passes_stage_one(self):
        out = self.guard(PLUGIN_AGENT)  # no recorded mode -> Stage 2, not Stage 1
        self.assertIn("STAGE 2/2", self.reason(out))
        self.assertIn("agent:agenting:researcher", self.reason(out))

    def test_prefixed_agent_type_runs_in_auto_mode(self):
        self.record(SID, "--mode", "auto")
        out = self.guard(PLUGIN_AGENT)
        self.assertIsNone(self.decision(out))
        self.assertIn("systemMessage", out)


class StageTwoManual(GuardCase):
    def test_missing_state_requires_approval(self):
        out = self.guard(ROUTED)
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("STAGE 2/2", self.reason(out))

    def test_manual_requires_approve_then_passes(self):
        self.record(SID, "--mode", "manual")
        out = self.guard(ROUTED)
        self.assertEqual(self.decision(out), "deny")
        reason = self.reason(out)
        self.assertIn("STAGE 2/2", reason)
        m = re.search(r'python3 "([^"]+)" --approve (\w+) --session (\S+)', reason)
        self.assertIsNotNone(m, reason)
        self.assertEqual(m.group(1), str(GUARD))
        r = subprocess.run([sys.executable, m.group(1), "--approve", m.group(2),
                            "--session", m.group(3)],
                           capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.state_dir / ".routing-approvals.json").exists())
        self.assertIsNone(self.guard(ROUTED))  # approved plan: silent pass-through

    def test_changed_plan_asks_again(self):
        self.record(SID, "--mode", "manual")
        reason = self.reason(self.guard(ROUTED))
        h = re.search(r"--approve (\w+)", reason).group(1)
        self.run_script(GUARD, "--approve", h, "--session", SID)
        out = self.guard("await agent('x', {model:'opus', effort:'xhigh'})")
        self.assertIn("STAGE 2/2", self.reason(out))

    def test_plan_counts_call_sites_and_says_runs_can_be_more(self):
        # observed 2026-10-08: "2 agents total" was shown for a script that ran 8 agents
        self.record(SID, "--mode", "manual")
        reason = self.reason(self.guard(
            "await pipeline(groups, g => agent('a', {model:'sonnet', effort:'high'}),"
            " r => agent('b', {model:'sonnet', effort:'medium'}))"))
        self.assertIn("2 agent() call sites", reason)
        self.assertIn("not runs", reason)
        self.assertNotIn("agents total", reason)

    def test_deny_names_why_it_is_asking(self):
        self.record(SID, "--mode", "manual")
        self.assertIn("mode is manual", self.reason(self.guard(ROUTED)))
        self.assertIn("no agenting mode is recorded", self.reason(self.guard(ROUTED, session="never-seen")))

    def test_legacy_semi_auto_is_treated_as_manual(self):
        self.write_state({SID: {"mode": "semi-auto", "disposition": "balanced",
                                "suggestion": "on"}})
        out = self.guard(ROUTED)
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("STAGE 2/2", self.reason(out))


class StageTwoAuto(GuardCase):
    def test_auto_drops_stage_two_with_system_message_only(self):
        self.record(SID, "--mode", "auto")
        out = self.guard(ROUTED)
        self.assertIsNotNone(out)
        self.assertIn("systemMessage", out)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertNotIn("permissionDecision", str(out))

    def test_auto_note_counts_call_sites_not_agents(self):
        # a call inside a loop is one call site however many agents it spawns at run time
        self.record(SID, "--mode", "auto")
        out = self.guard("for (const x of xs) {\n  await agent(x, {model:'haiku', effort:'low'})\n}\n"
                         "await agent('y', {model:'haiku', effort:'low'})")
        self.assertIn("2 agent() call sites", out["systemMessage"])
        self.assertNotIn("2 agents", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out)   # still no allow, still no ask

    def test_seeded_session_is_auto(self):
        self.run_hook(__import__("_util").CONTINUITY,
                      {"session_id": SID, "cwd": "/tmp", "source": "startup"})
        out = self.guard(ROUTED)
        self.assertNotIn("hookSpecificOutput", out)

    def test_auto_for_another_session_does_not_leak(self):
        self.record("other-session", "--mode", "auto")
        self.assertEqual(self.decision(self.guard(ROUTED)), "deny")


class StageTwoResumedChat(GuardCase):
    """A resumed or forked chat gets a new session_id and its SessionStart hook may not run
    again (observed 2026-10-08: ac2d086e resumed 499eb944, no state entry was ever written).
    The chat's own transcript still carries the SessionStart line naming the id it started
    under, so the guard follows that instead of falling back to manual."""

    NEW, OLD = "resumed-id", "original-id"

    def test_new_id_follows_the_original_id_recorded_as_auto(self):
        self.record(self.OLD, "--mode", "auto")
        out = self.guard(ROUTED, session=self.NEW, transcript=self.transcript(("auto", self.OLD)))
        self.assertIn("systemMessage", out)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn(self.OLD, out["systemMessage"])

    def test_new_id_follows_the_original_id_recorded_as_manual(self):
        self.record(self.OLD, "--mode", "manual")
        out = self.guard(ROUTED, session=self.NEW, transcript=self.transcript(("auto", self.OLD)))
        self.assertEqual(self.decision(out), "deny")   # the live entry beats the line's old text
        self.assertIn("STAGE 2/2", self.reason(out))

    def test_evicted_original_id_uses_the_mode_in_the_line(self):
        self.record("someone-else", "--mode", "auto")   # the state file exists, just not for OLD
        for mode, denied in (("auto", False), ("manual", True)):
            with self.subTest(mode=mode):
                out = self.guard(ROUTED, session=self.NEW,
                                 transcript=self.transcript((mode, self.OLD)))
                self.assertEqual(self.decision(out) == "deny", denied)

    def test_the_last_line_in_the_transcript_names_the_id_to_follow(self):
        # a resumed chat that was resumed again: the middle id carried the live mode
        self.record("first-id", "--mode", "auto")
        self.record("middle-id", "--mode", "manual")
        out = self.guard(ROUTED, session=self.NEW,
                         transcript=self.transcript(("auto", "first-id"), ("manual", "middle-id")))
        self.assertEqual(self.decision(out), "deny")

    def test_own_entry_wins_over_the_transcript(self):
        self.record(self.OLD, "--mode", "auto")
        self.record(self.NEW, "--mode", "manual")
        out = self.guard(ROUTED, session=self.NEW, transcript=self.transcript(("auto", self.OLD)))
        self.assertEqual(self.decision(out), "deny")

    def test_no_line_in_the_transcript_still_asks(self):
        self.record(self.OLD, "--mode", "auto")
        out = self.guard(ROUTED, session=self.NEW, transcript=self.transcript())
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("could not be found", self.reason(out))

    def test_missing_or_unreadable_transcript_still_asks(self):
        self.record(self.OLD, "--mode", "auto")
        for transcript in (self.state_dir / "does-not-exist.jsonl", self.state_dir):
            with self.subTest(transcript=transcript.name):
                self.assertEqual(self.decision(self.guard(ROUTED, session=self.NEW,
                                                          transcript=transcript)), "deny")
        self.assertEqual(self.decision(self.guard(ROUTED, session=self.NEW)), "deny")  # no path

    def test_text_that_only_quotes_the_line_is_not_a_session_start(self):
        self.record(self.OLD, "--mode", "auto")
        quoted = {"type": "assistant", "message": {"content": [{"type": "text", "text":
                  f"[agenting] mode=auto \u00b7 disposition=balanced (session {self.OLD})."}]}}
        out = self.guard(ROUTED, session=self.NEW, transcript=self.transcript(extra=[quoted]))
        self.assertEqual(self.decision(out), "deny")

    def test_a_line_naming_an_unrelated_id_does_not_borrow_another_sessions_auto(self):
        self.record("unrelated", "--mode", "auto")
        out = self.guard(ROUTED, session=self.NEW,
                         transcript=self.transcript(("manual", self.OLD)))
        self.assertEqual(self.decision(out), "deny")


class PassThrough(GuardCase):
    def test_non_workflow_tool_is_silent(self):
        self.assertIsNone(self.guard(UNROUTED, tool="Bash"))

    def test_agent_inside_string_is_ignored(self):
        self.assertIsNone(self.guard("const doc = 'call agent(p) to spawn'"))

    def test_malformed_input_is_silent(self):
        r = self.run_script(GUARD, stdin="{not json")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))


if __name__ == "__main__":
    unittest.main()
