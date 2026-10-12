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


class NestedOptions(GuardCase):
    """Observed 2026-10-10: a call whose options hold a nested object (a `schema:`), on one line or
    several, was denied at Stage 1 although model and effort were there, because the guard read the
    innermost last {...} as the options. The reverse also held: model/effort keys inside a nested
    object counted as routing. Routing is read from the top level of the options object only."""

    SCHEMA = "{type:'object', properties:{ok:{type:'boolean'}}}"

    def stage_one(self, script):
        return "STAGE 1/2" in self.reason(self.guard(script))

    def test_routing_keys_before_a_nested_schema_pass_stage_one(self):
        out = self.guard(f"await agent('x', {{model:'haiku', effort:'low', schema:{self.SCHEMA}}})")
        self.assertIn("STAGE 2/2", self.reason(out))
        self.assertNotIn("STAGE 1/2", self.reason(out))

    def test_routing_keys_after_a_nested_schema_pass_stage_one(self):
        self.assertFalse(self.stage_one(f"await agent('x', {{schema:{self.SCHEMA}, model:'haiku', effort:'low'}})"))

    def test_options_spread_over_lines_with_a_nested_schema_pass_stage_one(self):
        script = ("await agent('x', {\n  label: 'l',\n  model: 'haiku',\n  effort: 'low',\n"
                  "  schema: { type: 'object', properties: { ok: { type: 'boolean' } } },\n})")
        out = self.guard(script)
        self.assertIn("STAGE 2/2", self.reason(out))
        self.assertIn("haiku", self.reason(out))

    def test_a_nested_schema_on_both_sides_of_the_routing_keys_passes_stage_one(self):
        script = f"await agent('x', {{schema:{self.SCHEMA}, model:'haiku', effort:'low', extra:{self.SCHEMA}}})"
        self.assertFalse(self.stage_one(script))

    def test_model_and_effort_keys_inside_a_nested_object_are_not_routing(self):
        self.assertTrue(self.stage_one("await agent('x', {schema:{model:'x', effort:'y'}})"))
        self.assertTrue(self.stage_one("await agent('x', {opts:{model:'haiku', effort:'low'}})"))

    def test_the_tiers_in_the_plan_come_from_the_top_level_keys(self):
        self.record(SID, "--mode", "manual")
        script = ("await agent('x', {schema:{properties:{model:'opus', effort:'low'}}, "
                  "model:'sonnet', effort:'high'})")
        reason = self.reason(self.guard(script))
        self.assertIn("STAGE 2/2", reason)
        self.assertIn("Plan signature: sonnet/highx1", reason)   # not opus/low from inside the schema

    def test_an_object_in_the_prompt_expression_is_not_the_options(self):
        self.assertFalse(self.stage_one("await agent(build({a:1}), {model:'haiku', effort:'low'})"))
        self.assertTrue(self.stage_one("await agent(build({model:'haiku', effort:'low'}), {schema:S})"))

    def test_the_options_are_the_last_top_level_object_of_the_call(self):
        self.assertFalse(self.stage_one("await agent({a:1}, {model:'haiku', effort:'low'})"))
        self.assertTrue(self.stage_one("await agent({model:'haiku', effort:'low'}, {schema:S})"))

    def test_a_name_inside_a_value_expression_is_not_a_key(self):
        # `model` here is a variable in a ternary, not a property of the options
        self.assertTrue(self.stage_one("await agent('x', {effort: pick ? model : 'low', schema:S})"))

    def test_a_repeated_key_takes_the_last_value_as_javascript_does(self):
        self.record(SID, "--mode", "manual")
        reason = self.reason(self.guard("await agent('x', {model:'haiku', model:'opus', effort:'low'})"))
        self.assertIn("Plan signature: opus/lowx1", reason)

    def test_options_passed_as_a_variable_are_not_inspected_and_are_unrouted(self):
        self.assertTrue(self.stage_one("await agent('x', opts)"))


class StageOneCauses(GuardCase):
    """Stage 1 names, per call, what is missing, so the fix is obvious from the denial alone."""

    def test_stage_one_reports_each_unrouted_call_by_line_and_cause(self):
        reason = self.reason(self.guard("const a = 1\nawait agent('x', {schema:S})\nawait agent('y', {model:'opus'})"))
        self.assertIn("line    2  [no model, no effort]", reason)
        self.assertIn("line    3  [no effort]", reason)
        self.assertIn("2 agent() call(s) specify no model/effort", reason)

    def test_an_effort_without_a_model_is_reported_as_no_model(self):
        reason = self.reason(self.guard("await agent('x', {effort:'low', schema:S})"))
        self.assertIn("line    1  [no model]", reason)
        self.assertNotIn("no effort", reason)

    def test_options_passed_as_a_variable_are_reported_by_line_and_cause(self):
        reason = self.reason(self.guard("await agent('x', opts)"))
        self.assertIn("STAGE 1/2", reason)
        self.assertIn("line    1  [no model, no effort]", reason)


class SpreadsAndNullishValues(GuardCase):
    """Observed 2026-10-12 (a peer session in ~/Desktop/impark): a fan-out kept each lens's routing as
    data and spread it into the options, `{..., schema: CLAIMS, ...lens.route}`. The guard reads the
    source, not run-time values, so routing inside a spread is invisible to it, and the Stage 1 cause did
    not say so. The workaround, explicit keys with variable values, passes on key presence alone: the
    guard cannot know what `lens.effort` holds at run time, and says so in the denial text."""

    PEER = ("const LENSES = [{ key: 'auth-code', route: { agentType: 'agenting:researcher', effort: 'medium' },"
            " prompt: 'p' }]\n"
            "await pipeline(LENSES, (lens) => agent(lens.prompt, { label: `inspect:${lens.key}`,"
            " phase: 'Inspect', schema: CLAIMS, ...lens.route }))")

    def stage_one(self, script):
        return "STAGE 1/2" in self.reason(self.guard(script))

    def test_routing_inside_a_spread_is_named_in_the_stage_one_cause(self):
        reason = self.reason(self.guard(self.PEER))
        self.assertIn("STAGE 1/2", reason)
        self.assertIn("line    2  [no model, no effort; the guard cannot read ...lens.route]", reason)
        self.assertIn("agentType: lens.agentType, model: lens.model, effort: lens.effort", reason)

    def test_a_spread_inside_a_nested_object_is_not_named(self):
        reason = self.reason(self.guard("await agent('x', {schema: {...base, type:'object'}})"))
        self.assertIn("line    1  [no model, no effort]", reason)
        self.assertNotIn("cannot read", reason)

    def test_explicit_routing_keys_pass_stage_one_next_to_a_spread(self):
        self.assertFalse(self.stage_one("await agent('x', {...common, model:'haiku', effort:'low'})"))
        self.assertFalse(self.stage_one("await agent('x', {model:'haiku', effort:'low', ...extra})"))

    def test_variable_routing_values_pass_on_presence_and_show_question_marks(self):
        # the guard cannot evaluate lens.effort; the plan says "?" rather than guessing a tier
        self.record(SID, "--mode", "manual")
        workaround = self.PEER.replace("...lens.route",
                                       "agentType: lens.agentType, model: lens.model, effort: lens.effort")
        for script in ("await agent('x', {model:M, effort:E})", workaround):
            with self.subTest(script=script[-60:]):
                reason = self.reason(self.guard(script))
                self.assertIn("STAGE 2/2", reason)
                self.assertIn("Plan signature: ?/?x1", reason)

    def test_a_literal_undefined_or_null_value_is_not_routing(self):
        self.assertIn("line    1  [model is undefined]",
                      self.reason(self.guard("await agent('x', {model: undefined, effort:'low'})")))
        self.assertIn("line    1  [effort is null]",
                      self.reason(self.guard("await agent('x', {\n  model: 'haiku',\n  effort: null\n})")))
        self.assertFalse(self.stage_one("await agent('x', {model: undefined ?? 'haiku', effort:'low'})"))

    def test_every_spread_is_named_and_nothing_after_it_leaks_in(self):
        # each spread ends at the comma or brace that closes it, so the key after it is not part of its name
        reason = self.reason(self.guard("await agent('x', {...a, schema: S, ...b})"))
        self.assertIn("line    1  [no model, no effort; the guard cannot read ...a, ...b]", reason)

    def test_a_spread_name_drops_a_trailing_comment_and_is_capped(self):
        reason = self.reason(self.guard("await agent('x', {\n  ...lens.route // per-lens routing\n})"))
        self.assertIn("[no model, no effort; the guard cannot read ...lens.route]", reason)
        long = "pick(" + ", ".join(f"option{i}" for i in range(12)) + ")"
        reason = self.reason(self.guard(f"await agent('x', {{...{long}}})"))
        cause = re.search(r"cannot read (\.\.\.[^\]]*)\]", reason).group(1)
        self.assertTrue(cause.startswith("...pick(option0, option1"), cause)
        self.assertTrue(cause.endswith("…"), cause)
        self.assertLessEqual(len(cause), 3 + 40)

    def test_an_agent_type_beside_model_undefined_passes_stage_one(self):
        reason = self.reason(self.guard(
            "await agent('x', {agentType:'agenting:researcher', model: undefined, effort:'medium'})"))
        self.assertIn("STAGE 2/2", reason)
        self.assertIn("agent:agenting:researcher", reason)


class ShorthandKeys(GuardCase):
    """Found in the pre-release review of 3.3.1 (2026-10-12): `{model, effort}` is `{model: model,
    effort: effort}`, but the guard only took an identifier followed by a colon as a key, so a
    destructured fan-out that forwards its routing was denied, and next to a spread the cause blamed
    the spread. A shorthand key now counts on presence, like any variable value."""

    def test_a_destructured_fan_out_forwarding_shorthand_keys_passes_stage_one(self):
        self.record(SID, "--mode", "manual")
        reason = self.reason(self.guard(
            "const LENSES = [{prompt: 'a', model: 'haiku', effort: 'low'}];\n"
            "await pipeline(LENSES, ({prompt, model, effort}) => agent(prompt, {label: 'l', model, effort}))"))
        self.assertIn("STAGE 2/2", reason)
        self.assertIn("Plan signature: ?/?x1", reason)

    def test_shorthand_and_explicit_keys_mix_and_a_spread_is_not_blamed(self):
        for script in ("await agent('x', {model, effort: 'low'})",
                       "await agent('x', {agentType: 'agenting:scanner', effort})",
                       "await agent('x', {model, effort, ...extra})",
                       "await agent('x', {\n  model,\n  effort\n})"):
            with self.subTest(script=script):
                reason = self.reason(self.guard(script))
                self.assertIn("STAGE 2/2", reason)
                self.assertNotIn("cannot read", reason)

    def test_a_shorthand_name_that_is_not_a_routing_key_is_still_unrouted(self):
        self.assertIn("line    1  [no model, no effort]",
                      self.reason(self.guard("await agent('x', {label, schema})")))


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
