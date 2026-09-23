"""Pipe tests for hooks/workflow-routing-guard.py."""

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
    def guard(self, script, session=SID, tool="Workflow"):
        return self.run_hook(GUARD, {"session_id": session, "tool_name": tool,
                                     "tool_input": {"script": script}})

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

    def test_seeded_session_is_auto(self):
        self.run_hook(__import__("_util").CONTINUITY,
                      {"session_id": SID, "cwd": "/tmp", "source": "startup"})
        out = self.guard(ROUTED)
        self.assertNotIn("hookSpecificOutput", out)

    def test_auto_for_another_session_does_not_leak(self):
        self.record("other-session", "--mode", "auto")
        self.assertEqual(self.decision(self.guard(ROUTED)), "deny")


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
