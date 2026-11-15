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
        out = self.record(SID, "--mode", "manual", "--disposition", "fast")
        self.assertIn("mode=manual", out)
        self.assertIn("disposition=fast", out)
        st = self.status(SID)
        self.assertIn(f"session {SID}: mode=manual · disposition=fast · "
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
        self.record(SID, "--mode", "manual", "--disposition", "fast")
        self.record(SID, "--workflows", "on")
        entry = self.read_state()[SID]
        self.assertEqual((entry["mode"], entry["disposition"]), ("manual", "fast"))


QUALITY_GONE = 'the quality setting is gone: say "critical" for one job that needs the careful models'
MODE_COMMAND = "/agenting-mode [cheapest|fast|balanced]"
PRO_NOTICE = ("[agenting] plan=Pro · mode=fast (set for your plan: cheaper models, fewer agents)."
              "{tip} Change mode: " + MODE_COMMAND)
MAX_NOTICE = "[agenting] plan=Max · mode=balanced (set for your plan). To save usage, change mode: " + MODE_COMMAND


def main_chat_tip():
    """The hook's own tip text, read from its source (the hook is run as a script, never imported)."""
    import re
    m = re.search(r'^MAIN_CHAT_TIP = "(.*)"$', CONTINUITY.read_text(encoding="utf-8"), re.M)
    assert m, "MAIN_CHAT_TIP is not a one-line string constant"
    return m.group(1)


class Cheapest(ContinuityCase):
    """The third disposition, below fast. Only the user's word or a project's default sets it."""

    def setUp(self):
        super().setUp()
        self.env.pop("AGENTING_PLAN_FILE", None)       # read <temp HOME>/.claude.json
        self.env.pop("CLAUDE_CONFIG_DIR", None)

    def test_cheapest_is_recorded_and_carried_across_compaction(self):
        out = self.record(SID, "--disposition", "cheapest")
        self.assertIn("mode=auto · disposition=cheapest · workflows=not opted in", out)
        self.assertEqual(self.read_state()[SID]["disposition"], "cheapest")
        self.assertIn("mode=auto · disposition=cheapest · ", self.session_start(SID, source="compact"))
        self.assertIn("disposition=cheapest", self.status(SID))

    def test_no_plan_starts_a_chat_in_cheapest(self):
        for n, org in enumerate(("claude_pro", "claude_max")):
            with self.subTest(org=org):
                self.write_settings(self.home / ".claude.json", {"oauthAccount": {"organizationType": org}})
                sid = f"{n:08d}-cccc-3333-4444-555555555555"
                msg = self.start(session=sid)
                self.assertNotIn("disposition=cheapest", msg)
                self.assertIn(self.read_state()[sid]["disposition"], ("fast", "balanced"))

    def test_choosing_cheapest_replaces_the_plans_start(self):
        self.write_settings(self.home / ".claude.json", {"oauthAccount": {"organizationType": "claude_pro"}})
        self.assertIn("disposition=fast (set for the Pro plan)", self.start())
        self.record(SID, "--disposition", "cheapest")
        msg = self.start(source="compact")
        self.assertIn("mode=auto · disposition=cheapest · ", msg)
        self.assertNotIn("set for", msg)
        self.assertNotIn("disposition_source", self.read_state()[SID])

    def test_both_first_start_lines_name_the_three_modes(self):
        for n, (org, lead) in enumerate((("claude_pro", "Change mode: "), ("claude_max", "To save usage, change mode: "))):
            with self.subTest(org=org):
                self.write_settings(self.home / ".claude.json", {"oauthAccount": {"organizationType": org}})
                self.write_state({})                   # a fresh install: no plan was told about before
                out = self.run_hook(CONTINUITY, {"session_id": f"{n:08d}-dddd-3333-4444-555555555555",
                                                 "cwd": str(self.cwd), "source": "startup"})
                self.assertTrue(out["systemMessage"].endswith(lead + "/agenting-mode [cheapest|fast|balanced]"),
                                out["systemMessage"])

    def test_the_tip_names_a_model_an_effort_and_the_cost_of_switching(self):
        tip = main_chat_tip()
        self.assertIn("Sonnet at high effort (/model sonnet, then /effort high)", tip)
        self.assertIn("Opus at xhigh effort", tip)
        self.assertIn("do not switch back and forth", tip)
        self.write_settings(self.home / ".claude.json", {"oauthAccount": {"organizationType": "claude_pro"}})
        out = self.run_hook(CONTINUITY, {"session_id": SID, "cwd": str(self.cwd), "source": "startup"})
        self.assertIn(f" Tip: {tip}. Change mode: ", out["systemMessage"])
        self.assertNotIn("\n", out["systemMessage"])

    def test_an_unknown_disposition_is_refused(self):
        r = self.run_script(CONTINUITY, "--record", "--session", SID, "--disposition", "cheap")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.state_file.exists())


class QualityIsGone(ContinuityCase):
    def test_the_line_offers_three_dispositions(self):
        msg = self.start()
        self.assertIn("[--disposition cheapest|fast|balanced] ", msg)
        self.assertNotIn("quality", msg)

    def test_recording_quality_records_balanced_and_says_what_to_say_instead(self):
        out = self.record(SID, "--disposition", "quality")
        self.assertIn(f"disposition=balanced · workflows=not opted in ({QUALITY_GONE})", out)
        self.assertEqual(self.read_state()[SID]["disposition"], "balanced")
        self.assertNotIn("quality", self.session_start(SID, source="compact"))

    def test_a_chat_recorded_as_quality_reads_as_balanced_and_the_line_says_so(self):
        self.write_state({SID: {"mode": "auto", "disposition": "quality", "workflows": None,
                                "updated": "2026-11-01T00:00:00Z"}})
        msg = self.session_start(SID, source="compact")
        self.assertIn(f"mode=auto · disposition=balanced ({QUALITY_GONE}) · workflows=not opted in", msg)
        self.assertIn(f"disposition=balanced ({QUALITY_GONE})", self.status(SID))
        self.record(SID, "--mode", "manual")          # any record rewrites the entry
        self.assertEqual(self.read_state()[SID]["disposition"], "balanced")
        self.assertNotIn("quality", self.session_start(SID, source="compact"))


class Plan(ContinuityCase):
    """The account's plan, read from <HOME>/.claude.json (a temp HOME here)."""

    def setUp(self):
        super().setUp()
        self.env.pop("AGENTING_PLAN_FILE", None)       # read <temp HOME>/.claude.json
        self.env.pop("CLAUDE_CONFIG_DIR", None)

    def write_plan(self, **account):
        self.write_settings(self.home / ".claude.json", {"oauthAccount": account, "other": 1})

    def begin(self, session=SID, source="startup"):
        """(additionalContext, systemMessage or None) of one SessionStart."""
        out = self.run_hook(CONTINUITY, {"session_id": session, "cwd": str(self.cwd), "source": source})
        return out["hookSpecificOutput"]["additionalContext"], out.get("systemMessage")

    def test_no_plan_file_changes_nothing(self):
        msg, notice = self.begin()
        self.assertIsNone(notice)
        self.assertTrue(msg.startswith("[agenting] mode=auto · disposition=balanced · workflows=not opted in"), msg)
        self.assertNotIn("plan", msg)
        self.assertNotIn("_plan", self.read_state())

    def test_a_pro_plan_starts_a_new_chat_in_fast_and_tells_the_user(self):
        self.write_plan(organizationType="claude_pro", organizationRateLimitTier="default_claude_pro")
        msg, notice = self.begin()
        tip = main_chat_tip()
        self.assertEqual(notice, PRO_NOTICE.format(tip=f" Tip: {tip}." if tip else ""))
        self.assertTrue(msg.startswith("[agenting] mode=auto · disposition=fast (set for the Pro plan) · "
                                       "workflows=not opted in"), msg)
        self.assertIn(f" · advisor=off · plan=Pro (session {SID}). ", msg)
        entry = self.read_state()[SID]
        self.assertEqual((entry["disposition"], entry["disposition_source"], entry["plan"]), ("fast", "plan", "Pro"))
        self.assertEqual(self.read_state()["_plan"]["plan"], "Pro")
        self.assertIn("disposition=fast (set for the Pro plan)", self.status_here())

    def test_a_max_plan_starts_in_balanced_and_tells_the_user(self):
        self.write_plan(organizationType="claude_max", organizationRateLimitTier="default_claude_max_20x")
        msg, notice = self.begin()
        self.assertEqual(notice, MAX_NOTICE)
        self.assertIn("mode=auto · disposition=balanced (set for the Max plan) · ", msg)
        self.assertIn(" · plan=Max (session ", msg)

    def test_the_user_is_told_at_the_first_start_of_a_chat_only(self):
        self.write_plan(organizationType="claude_pro")
        self.assertIsNotNone(self.begin()[1])
        for source in ("compact", "resume"):
            msg, notice = self.begin(source=source)
            self.assertIsNone(notice, source)
            self.assertIn("disposition=fast (set for the Pro plan)", msg)
        self.assertIsNotNone(self.begin(source="clear")[1])        # /clear is a new chat
        self.assertIsNotNone(self.begin(session=SID2)[1])

    def test_the_users_own_choice_replaces_the_plans_start(self):
        self.write_plan(organizationType="claude_pro")
        self.begin()
        self.record(SID, "--workflows", "on")                       # not a choice of disposition
        self.record(SID, "--mode", "manual")                        # nor is the mode
        self.record(SID, "--mode", "auto")
        self.assertIn("disposition=fast (set for the Pro plan)", self.begin(source="compact")[0])
        out = self.record(SID, "--disposition", "balanced")
        self.assertIn("disposition=balanced · ", out)
        msg, notice = self.begin(source="compact")
        self.assertIn("mode=auto · disposition=balanced · workflows=on", msg)
        self.assertNotIn("set for", msg)
        self.assertIsNone(notice)
        entry = self.read_state()[SID]
        self.assertNotIn("disposition_source", entry)
        self.assertNotIn("plan", entry)
        self.record(SID, "--disposition", "fast")                   # choosing fast is a choice too
        self.assertNotIn("set for", self.begin(source="compact")[0])

    def test_a_plan_change_is_told_once_at_the_next_new_chat(self):
        self.write_plan(organizationType="claude_pro")
        self.begin()
        self.write_plan(organizationType="claude_max")
        self.assertIsNone(self.begin(source="compact")[1])          # an old chat keeps its own start
        self.assertIn("disposition=fast (set for the Pro plan)", self.begin(source="compact")[0])
        msg, notice = self.begin(session=SID2)
        self.assertEqual(notice, "[agenting] plan changed from Pro to Max · new chats now start in balanced.")
        self.assertIn("disposition=balanced (set for the Max plan)", msg)
        self.assertEqual(self.begin(session="33333333-2222-3333-4444-555555555555")[1], MAX_NOTICE)
        self.write_plan(organizationType="claude_pro")
        self.assertEqual(self.begin(session="44444444-2222-3333-4444-555555555555")[1],
                         "[agenting] plan changed from Max to Pro · new chats now start in fast.")

    def test_which_fields_name_the_plan(self):
        cases = [
            ({"organizationType": "claude_max"}, "Max"),
            ({"organizationRateLimitTier": "default_claude_max_5x"}, "Max"),
            ({"organizationType": "claude_pro"}, "Pro"),
            ({"organizationType": None, "userRateLimitTier": "default_claude_pro"}, "Pro"),
            ({"planDisplayName": "Pro"}, "Pro"),
            ({"organizationType": "claude_team", "organizationRateLimitTier": "default_claude_max_5x"}, None),
            ({"organizationType": "claude_enterprise"}, None),
            ({"organizationType": "professional_services", "planDisplayName": "Product"}, None),
            ({"organizationRateLimitTier": "maximal_tier", "planDisplayName": "Maxwell"}, None),
            ({"organizationType": "", "organizationRateLimitTier": "default_claude_pro"}, "Pro"),
            ({"organizationType": 7, "planDisplayName": ["Pro"]}, None),
            ({"billingType": "pro", "seatTier": "max"}, None),          # not plan fields
        ]
        for n, (account, plan) in enumerate(cases):
            with self.subTest(account=account):
                self.write_plan(**account)
                msg, notice = self.begin(session=f"{n:08d}-2222-3333-4444-555555555555")
                if plan:
                    self.assertIn(f" · plan={plan} (session ", msg)
                else:
                    self.assertNotIn("plan", msg)
                    self.assertIsNone(notice)

    def test_an_unreadable_plan_file_changes_nothing(self):
        for content in ("{not json", "[1, 2]", '{"oauthAccount": "x"}', "{}"):
            with self.subTest(content=content):
                self.write_settings(self.home / ".claude.json", content)
                msg, notice = self.begin(source="clear")
                self.assertIsNone(notice)
                self.assertIn("mode=auto · disposition=balanced · workflows=not opted in", msg)

    def test_a_project_that_names_its_own_default_is_not_started_by_the_plan(self):
        self.write_plan(organizationType="claude_pro")
        self.write_settings(self.cwd / "agenting" / "AGENTING.md",
                            "# Agenting\n\n## Config\n\n- `auto-disposition-default: balanced`\n")
        msg, notice = self.begin()
        self.assertIsNone(notice)
        self.assertIn("mode=auto · disposition=balanced · workflows=not opted in", msg)
        self.assertIn(" · plan=Pro (session ", msg)                 # the fact is still on the line
        # the template's commented example is not a choice
        self.write_settings(self.cwd / "agenting" / "AGENTING.md",
                            "## Config\n<!-- e.g. auto-disposition-default: balanced -->\n")
        msg, notice = self.begin(session=SID2)
        self.assertIsNotNone(notice)
        self.assertIn("disposition=fast (set for the Pro plan)", msg)

    def test_a_chat_that_lost_its_record_is_seeded_by_the_plan_without_a_notice(self):
        self.write_plan(organizationType="claude_pro")
        for source in ("compact", "resume", "fork"):                # no record: pruned, or a fork's new id
            with self.subTest(source=source):
                msg, notice = self.begin(session=f"{source}00-2222-3333-4444-555555555555", source=source)
                self.assertIsNone(notice)
                self.assertIn("disposition=fast (set for the Pro plan)", msg)
        self.assertNotIn("_plan", self.read_state())                 # nobody was told yet
        self.assertEqual(self.begin(session=SID2)[1], PRO_NOTICE.format(
            tip=f" Tip: {main_chat_tip()}." if main_chat_tip() else ""))

    def test_a_record_for_a_chat_with_no_record_starts_where_the_plan_starts(self):
        self.write_plan(organizationType="claude_pro")
        self.assertIn("disposition=fast (set for the Pro plan)", self.status_here())
        r = subprocess.run([sys.executable, str(CONTINUITY), "--record", "--session", SID, "--mode", "manual"],
                           capture_output=True, text=True, timeout=20, env=self.env, cwd=str(self.cwd))
        self.assertIn("mode=manual · disposition=fast (set for the Pro plan)", r.stdout)
        self.assertEqual(self.read_state()[SID]["disposition"], "fast")

    def test_a_chat_in_a_project_with_its_own_default_does_not_swallow_the_plan_change(self):
        self.write_plan(organizationType="claude_pro")
        self.begin()
        self.write_plan(organizationType="claude_max")
        self.write_settings(self.cwd / "agenting" / "AGENTING.md", "- `auto-disposition-default: fast`\n")
        self.assertIsNone(self.begin(session=SID2)[1])
        (self.cwd / "agenting" / "AGENTING.md").unlink()
        self.assertEqual(self.begin(session="33333333-2222-3333-4444-555555555555")[1],
                         "[agenting] plan changed from Pro to Max · new chats now start in balanced.")

    def test_the_plan_change_is_still_told_after_the_plan_could_not_be_read_for_a_while(self):
        self.write_plan(organizationType="claude_pro")
        self.begin()
        self.write_settings(self.home / ".claude.json", "{not json")
        self.assertIsNone(self.begin(session=SID2)[1])
        self.write_plan(organizationType="claude_pro")
        self.assertTrue(self.begin(session="33333333-2222-3333-4444-555555555555")[1].startswith("[agenting] plan=Pro"))
        self.write_settings(self.home / ".claude.json", "{not json")
        self.begin(session="44444444-2222-3333-4444-555555555555")
        self.write_plan(organizationType="claude_max")
        self.assertEqual(self.begin(session="55555555-2222-3333-4444-555555555555")[1],
                         "[agenting] plan changed from Pro to Max · new chats now start in balanced.")

    def test_the_project_file_is_found_from_a_folder_inside_the_project(self):
        self.write_plan(organizationType="claude_pro")
        self.write_settings(self.cwd / "agenting" / "AGENTING.md", "## Config\n- **auto-disposition-default:** `Balanced`\n")
        (self.cwd / ".git").mkdir()
        inner = self.cwd / "src" / "deep"
        inner.mkdir(parents=True)
        out = self.run_hook(CONTINUITY, {"session_id": SID, "cwd": str(inner), "source": "startup"})
        self.assertNotIn("systemMessage", out)
        self.assertIn("disposition=balanced · ", out["hookSpecificOutput"]["additionalContext"])
        # a file above the folder that has .git belongs to another project
        other = self.cwd / "vendor" / "lib"
        (other / ".git").mkdir(parents=True)
        out = self.run_hook(CONTINUITY, {"session_id": SID2, "cwd": str(other), "source": "startup"})
        self.assertIn("systemMessage", out)

    def test_what_counts_as_a_project_default(self):
        self.write_plan(organizationType="claude_pro")
        cases = [("- `auto-disposition-default: balanced`", True), ("auto-disposition-default : fast", True),
                 ("- **auto-disposition-default:** quality", True), ("`auto-disposition-default`: `fast`", True),
                 ("auto-disposition-default: cheapest", True),
                 ("auto-disposition-default:\nNotes follow", False), ("auto-disposition-default: TBD", False),
                 ("<!-- auto-disposition-default: balanced -->", False), ("nothing here", False)]
        for n, (text, own) in enumerate(cases):
            with self.subTest(text=text):
                self.write_settings(self.cwd / "agenting" / "AGENTING.md", f"## Config\n{text}\n")
                notice = self.begin(session=f"{n:08d}-bbbb-3333-4444-555555555555")[1]
                self.assertEqual(notice is None, own)

    def test_an_odd_stored_plan_value_never_stops_the_hook(self):
        self.write_plan(organizationType="claude_pro")
        self.write_state({"_plan": {"plan": ["Pro"]},
                          SID: {"mode": "auto", "disposition": "fast", "disposition_source": "plan", "plan": {}},
                          SID2: {"mode": "auto", "disposition": "turbo", "disposition_source": "plan", "plan": "Pro"}})
        msg, _ = self.begin(source="compact")
        self.assertIn("mode=auto · disposition=fast · workflows=not opted in", msg)    # the odd mark is dropped
        self.assertIn("disposition=balanced · ", self.begin(session=SID2, source="compact")[0])  # no "set for"
        notice = self.begin(session="33333333-2222-3333-4444-555555555555")[1]
        self.assertTrue(notice.startswith("[agenting] plan=Pro · mode=fast"), notice)
        self.assertEqual(self.read_state()["_plan"]["plan"], "Pro")
        self.assertIn("recorded: session", self.record(SID, "--mode", "manual"))

    def test_a_reserved_key_is_never_a_session_id(self):
        self.write_plan(organizationType="claude_pro")
        self.begin()
        for key in ("_plan", "_defaults"):
            with self.subTest(key=key):
                msg, _ = self.begin(session=key)
                self.assertIn("(session unknown)", msg)
        self.assertEqual(self.read_state()["_plan"]["plan"], "Pro")
        self.assertNotIn("mode", self.read_state()["_plan"])

    def test_the_plan_file_is_read_from_the_config_folder_when_one_is_set(self):
        self.write_plan(organizationType="claude_max")                      # the home folder's file
        config = self.home / "other-config"
        self.write_settings(config / ".claude.json", {"oauthAccount": {"organizationType": "claude_pro"}})
        self.env["CLAUDE_CONFIG_DIR"] = str(config)
        self.assertIn(" · plan=Pro (session ", self.begin()[0])
        self.env["CLAUDE_CONFIG_DIR"] = str(self.home / "empty-config")     # no file there: no plan
        self.assertNotIn("plan", self.begin(session=SID2)[0])

    def test_the_line_with_a_plan_or_the_quality_note_stays_short_asks_nothing_and_is_read_by_the_guard(self):
        import re
        guard = (CONTINUITY.parent / "workflow-routing-guard.py").read_text(encoding="utf-8")
        pattern = re.search(r'^SESSION_LINE_RE = re\.compile\(r"(.+)"\)$', guard, re.M)
        self.assertIsNotNone(pattern, "the guard's SESSION_LINE_RE is not a one-line raw string any more")
        line_re = re.compile(pattern.group(1))
        self.write_plan(organizationType="claude_pro")
        self.write_state({SID2: {"mode": "manual", "disposition": "quality", "workflows": None}})
        for session, source, mode in ((SID, "startup", "auto"), (SID2, "compact", "manual")):
            with self.subTest(session=session):
                msg, notice = self.begin(session=session, source=source)
                self.assertNotIn("\n", msg)
                self.assertNotIn("?", msg + (notice or ""))
                self.assertNotIn("AskUserQuestion", msg + (notice or ""))
                self.assertLess(len(msg) - len(str(CONTINUITY)) - 2 * len(session), 570, msg)
                m = line_re.search(msg)
                self.assertEqual((m.group(1), m.group(2)), (mode, session))

    def test_the_plan_record_is_not_a_session(self):
        self.write_plan(organizationType="claude_pro")
        for n in range(25):                                         # more than the 20 sessions kept
            self.begin(session=f"{n:08d}-aaaa-3333-4444-555555555555")
        state = self.read_state()
        self.assertEqual(state["_plan"]["plan"], "Pro")
        self.assertEqual(len([k for k in state if not k.startswith("_")]), 20)
        r = self.run_script(CONTINUITY, "--record", "--session", "_plan", "--mode", "manual")
        self.assertEqual(self.read_state()["_plan"]["plan"], "Pro")  # never overwritten by a record
        self.assertIn("session unknown", r.stdout)


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
