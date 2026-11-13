"""Pipe tests for hooks/agent-routing-guard.py."""

import json

from _util import AGENT_GUARD, ROOT, HookTestCase

TEAMS = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
ROUTED = {"description": "trace it", "prompt": "find the caller", "model": "sonnet", "effort": "low"}


class AgentGuardCase(HookTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.state_dir / "home"
        self.project = self.state_dir / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.env.pop(TEAMS, None)
        self.env["HOME"] = str(self.home)

    def start(self, tool_input, teams=None, cwd=None, transcript=None, tool="Agent"):
        """Pipe one PreToolUse payload in; return the parsed output, None when silent."""
        if teams is not None:
            self.env[TEAMS] = teams
        payload = {"session_id": "agent-guard-test", "cwd": str(cwd or self.project),
                   "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
        if transcript is not None:
            payload["transcript_path"] = str(transcript)
        return self.run_hook(AGENT_GUARD, payload)

    def agent_file(self, base, name, **pins):
        folder = base / ".claude" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        lines = ["---", f"name: {name}", "description: test agent"]
        lines += [f"{k}: {v}" for k, v in pins.items()]
        lines += ["---", "", "You are a test agent.", ""]
        (folder / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")

    def transcript(self, *records):
        path = self.state_dir / "chat.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def assistant(model, effort, sidechain=False):
        rec = {"type": "assistant", "message": {"model": model, "role": "assistant"}, "effort": effort}
        if sidechain:
            rec["isSidechain"] = True
        return rec

    @staticmethod
    def decision(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision")

    @staticmethod
    def reason(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


class Ordinary(AgentGuardCase):
    def test_routed_subagent_passes_silently(self):
        self.assertIsNone(self.start(dict(ROUTED)))

    def test_no_model_and_no_effort_is_denied(self):
        out = self.start({"description": "trace it", "prompt": "find the caller"})
        self.assertEqual(self.decision(out), "deny")
        reason = self.reason(out)
        self.assertIn('Agent start "trace it" has no model and no effort', reason)
        self.assertIn('model: "sonnet", effort: "low"', reason)
        self.assertIn('"routing: inherit"', reason)
        self.assertEqual(out["systemMessage"],
                         "agenting: an agent start had no model or effort; Claude is retrying with both set")

    def test_effort_only_missing_is_denied(self):
        out = self.start({"description": "trace it", "prompt": "p", "model": "sonnet"})
        self.assertEqual(self.decision(out), "deny")
        reason = self.reason(out)
        self.assertIn("has no effort. Its effort would come from the settings default for that model", reason)
        self.assertNotIn("has no model", reason)

    def test_model_only_missing_is_denied(self):
        out = self.start({"description": "trace it", "prompt": "p", "effort": "low"})
        self.assertEqual(self.decision(out), "deny")
        reason = self.reason(out)
        self.assertIn("has no model.", reason)
        self.assertIn("Add one from the routing table", reason)
        self.assertNotIn("no effort", reason)

    def test_agenting_agent_with_no_call_fields_passes(self):
        self.assertIsNone(self.start({"description": "scan", "prompt": "p", "subagent_type": "agenting:coder"}))

    def test_fork_passes(self):
        self.assertIsNone(self.start({"description": "fork it", "prompt": "p", "subagent_type": "fork"}))

    def test_inherit_mark_passes(self):
        for prompt in ("Do the work.\nrouting: inherit\nThanks.", "// Routing: Inherit", "  # routing:inherit  "):
            with self.subTest(prompt=prompt):
                self.assertIsNone(self.start({"description": "d", "prompt": prompt}))

    def test_inherit_words_inside_a_sentence_still_denied(self):
        prompt = "Explain why routing: inherit is risky and when it is fine."
        out = self.start({"description": "d", "prompt": prompt})
        self.assertEqual(self.decision(out), "deny")

    def test_model_inherit_in_agent_file_counts_as_not_set(self):
        self.agent_file(self.home, "pinless", model="inherit", effort="low")
        out = self.start({"description": "d", "prompt": "p", "subagent_type": "pinless"})
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("has no model.", self.reason(out))

    def test_long_description_is_cut_to_60_characters(self):
        out = self.start({"description": "x" * 100, "prompt": "p"})
        self.assertIn('Agent start "' + "x" * 60 + '" has no model', self.reason(out))

    def test_a_named_start_with_teams_off_is_an_ordinary_subagent(self):
        self.assertIsNone(self.start(dict(ROUTED, name="worker")))
        out = self.start({"description": "d", "prompt": "p", "name": "worker", "model": "sonnet"})
        self.assertIn('Agent start "d" has no effort', self.reason(out))

    def test_a_named_start_with_isolation_is_an_ordinary_subagent(self):
        self.assertIsNone(self.start(dict(ROUTED, name="worker", isolation="worktree"), teams="1"))


class Teammates(AgentGuardCase):
    def test_teammate_without_a_file_is_denied_even_with_model_and_effort(self):
        out = self.start(dict(ROUTED, name="worker"), teams="1")
        self.assertEqual(self.decision(out), "deny")
        reason = self.reason(out)
        self.assertIn('Teammate "worker" cannot be given an effort on the call', reason)
        self.assertIn("measured 2026-11-13, CLI 2.1.323", reason)
        self.assertIn("agenting:reviewer opus/xhigh", reason)
        self.assertNotIn("has no model", reason)

    def test_teams_env_true_is_read_case_insensitively(self):
        out = self.start(dict(ROUTED, name="worker"), teams="True")
        self.assertIn("Teammate", self.reason(out))

    def test_teammate_without_a_file_and_without_a_model_says_so(self):
        out = self.start({"description": "d", "prompt": "p", "name": "worker"}, teams="1")
        self.assertIn('Teammate "worker" has no model, and cannot be given an effort on the call', self.reason(out))

    def test_teammate_with_a_file_effort_but_no_model_gets_the_model_text(self):
        self.agent_file(self.home, "modelless", effort="low")
        out = self.start({"description": "d", "prompt": "p", "name": "worker", "subagent_type": "modelless"}, teams="1")
        reason = self.reason(out)
        self.assertIn('Teammate "worker" has no model.', reason)
        self.assertNotIn("cannot be given an effort", reason)

    def test_teammate_from_an_agenting_agent_passes(self):
        self.assertIsNone(self.start(
            {"description": "d", "prompt": "p", "name": "worker", "subagent_type": "agenting:coder"}, teams="1"))

    def test_teammate_with_a_differing_call_effort_passes_with_a_note(self):
        out = self.start({"description": "d", "prompt": "p", "name": "worker",
                          "subagent_type": "agenting:coder", "effort": "xhigh"}, teams="1")
        self.assertIsNone(self.decision(out))
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertIn('effort "xhigh" written on the call is ignored', hso["additionalContext"])
        self.assertIn('"low"', hso["additionalContext"])

    def test_teammate_with_the_same_call_effort_as_its_file_is_silent(self):
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "name": "worker",
                                      "subagent_type": "agenting:coder", "effort": "low"}, teams="1"))


class AgentFiles(AgentGuardCase):
    def test_user_agent_file_that_pins_both_passes(self):
        self.agent_file(self.home, "mine", model="haiku", effort="medium")
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "subagent_type": "mine"}))

    def test_user_agent_file_that_pins_only_the_model_is_denied_for_effort(self):
        self.agent_file(self.home, "half", model="haiku")
        out = self.start({"description": "d", "prompt": "p", "subagent_type": "half"})
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("has no effort", self.reason(out))

    def test_project_agent_file_under_cwd_is_found(self):
        self.agent_file(self.project, "local", model="sonnet", effort="high")
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "subagent_type": "local"}))

    def test_a_built_in_type_has_no_file_and_still_needs_routing(self):
        out = self.start({"description": "d", "prompt": "p", "subagent_type": "general-purpose"})
        self.assertEqual(self.decision(out), "deny")

    def test_a_built_in_type_with_its_own_model_is_asked_for_an_effort_only(self):
        out = self.start({"description": "d", "prompt": "p", "subagent_type": "claude-code-guide"})
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("has no effort", self.reason(out))
        self.assertNotIn("has no model", self.reason(out))
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "subagent_type": "claude-code-guide",
                                      "effort": "medium"}))
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "subagent_type": "statusline-setup",
                                      "effort": "low"}))

    def test_explore_and_plan_bring_no_model_of_their_own(self):
        for kind in ("Explore", "Plan"):
            with self.subTest(kind=kind):
                out = self.start({"description": "d", "prompt": "p", "subagent_type": kind, "effort": "medium"})
                self.assertEqual(self.decision(out), "deny")
                self.assertIn("has no model", self.reason(out))

    def test_another_plugins_agent_file_is_found_in_the_plugin_cache(self):
        folder = self.home / ".claude" / "plugins" / "cache" / "market" / "otherplug" / "1.2.0" / "agents"
        folder.mkdir(parents=True)
        (folder / "helper.md").write_text("---\nname: helper\nmodel: sonnet\neffort: medium\n---\nbody\n",
                                          encoding="utf-8")
        self.assertIsNone(self.start({"description": "d", "prompt": "p", "subagent_type": "otherplug:helper"}))
        out = self.start({"description": "d", "prompt": "p", "subagent_type": "otherplug:absent"})
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("has no model and no effort", self.reason(out))

    def test_every_plugin_agent_file_pins_model_and_effort(self):
        files = sorted((ROOT / "agents").glob("*.md"))
        self.assertGreater(len(files), 0)
        for path in files:
            with self.subTest(agent=path.name):
                head = path.read_text(encoding="utf-8").split("---")[1]
                self.assertRegex(head, r"(?m)^model:\s*(opus|sonnet|haiku|fable)\s*$")
                self.assertRegex(head, r"(?m)^effort:\s*(low|medium|high|xhigh|max)\s*$")


class Robustness(AgentGuardCase):
    def test_garbage_stdin_exits_zero_silently(self):
        for raw in ("", "not json", "[]", "null", "42", '"Agent"', "{", '{"tool_name": "Agent"}',
                    '{"tool_name": "Agent", "tool_input": "x"}', '{"tool_name": "Agent", "tool_input": []}'):
            with self.subTest(stdin=raw):
                r = self.run_script(AGENT_GUARD, stdin=raw)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, "")

    def test_odd_field_types_exit_zero_without_a_decision(self):
        r = self.run_script(AGENT_GUARD, stdin=json.dumps({
            "tool_name": "Agent", "cwd": 5, "transcript_path": 7,
            "tool_input": {"model": 3, "effort": ["x"], "name": 9, "prompt": 1, "subagent_type": {"a": 1},
                           "description": None}}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_another_tool_is_silent(self):
        self.assertIsNone(self.start({"description": "d", "prompt": "p"}, tool="Bash"))
        self.assertIsNone(self.start({"description": "d", "prompt": "p"}, tool="Workflow"))

    def test_deny_json_never_contains_allow_or_ask(self):
        cases = [({"description": "d", "prompt": "p"}, None),
                 ({"description": "d", "prompt": "p", "model": "sonnet"}, None),
                 (dict(ROUTED, name="worker"), "1")]
        for tool_input, teams in cases:
            if teams:
                self.env[TEAMS] = teams
            r = self.run_script(AGENT_GUARD, stdin=json.dumps({"tool_name": "Agent", "tool_input": tool_input}))
            with self.subTest(tool_input=tool_input):
                out = json.loads(r.stdout)
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
                self.assertNotRegex(r.stdout, r'"(allow|ask)"')

    def test_reason_names_the_chat_tier_when_the_transcript_has_one(self):
        transcript = self.transcript(
            self.assistant("claude-opus-5-5", "xhigh"),
            self.assistant("claude-fable-5-2", "max"),
            self.assistant("claude-haiku-5-5", "low", sidechain=True),
            self.assistant("<synthetic>", "low"),
        )
        out = self.start({"description": "d", "prompt": "p"}, transcript=transcript)
        self.assertIn("It would run on this chat's tier (claude-fable-5-2/max).", self.reason(out))

    def test_reason_falls_back_when_there_is_no_transcript(self):
        reason = self.reason(self.start({"description": "d", "prompt": "p"}))
        self.assertIn("It would run on this chat's tier.", reason)
        empty = self.transcript()
        reason = self.reason(self.start({"description": "d", "prompt": "p"}, transcript=empty))
        self.assertIn("It would run on this chat's tier.", reason)
        reason = self.reason(self.start({"description": "d", "prompt": "p"}, transcript=self.state_dir / "missing.jsonl"))
        self.assertIn("It would run on this chat's tier.", reason)

    def test_the_hook_is_wired_in_hooks_json_for_the_agent_tool(self):
        entries = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        agent = [e for e in entries if e.get("matcher") == "Agent"]
        self.assertEqual(len(agent), 1)
        command = agent[0]["hooks"][0]["command"]
        self.assertEqual(command, 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/agent-routing-guard.py"')
        self.assertEqual(agent[0]["hooks"][0]["timeout"], 10)
        self.assertEqual(len([e for e in entries if e.get("matcher") == "Workflow"]), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
