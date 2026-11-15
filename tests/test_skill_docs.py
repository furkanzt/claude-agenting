"""Guards on the agenting skill's text: triggers must not shrink, and the fan-out
guidance must keep its evidence caveats."""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "agenting" / "SKILL.md"
FAN_OUTS = ROOT / "skills" / "agenting" / "reference" / "fan-outs.md"
CLEANRUN = ROOT / "scripts" / "cleanrun.py"
FAKE_CLAUDE = ROOT / "tests" / "fixtures" / "fake_claude_cleanrun.py"

OLD_TRIGGERS = [
    "writing or editing a Workflow script",
    "choosing a model or effort for an agent() or Agent call",
    "switches agenting mode (auto/manual) or disposition (cheapest/fast/balanced)",
    "calls a job critical or throwaway",
    "opts in to workflows for this chat",
    "agenting/AGENTING.md",
]


def description():
    m = re.search(r"^description:\s*(.+)$", SKILL.read_text(encoding="utf-8"), re.M)
    assert m, "SKILL.md has no description line"
    return m.group(1)


class SkillTriggers(unittest.TestCase):
    def test_every_old_trigger_phrase_is_still_there(self):
        for phrase in OLD_TRIGGERS:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, description())

    def test_planning_a_fan_out_triggers_the_skill(self):
        self.assertIn("planning a fan-out of many agents", description())

    def test_the_description_stays_short(self):
        # it sits in the skill listing that every generic agent carries
        self.assertLess(len(description()), 420)


class ProcedureCleanRunStep(unittest.TestCase):
    def setUp(self):
        text = SKILL.read_text(encoding="utf-8")
        self.procedure = text.split("## Procedure: before calling Workflow", 1)[1].split("\n## ", 1)[0]
        self.steps = re.findall(r"^(\d+)\.\s+\*\*(.+?)\*\*", self.procedure, re.M)

    def test_a_clean_run_step_comes_before_drafting(self):
        # 2026-10-27: a 19-agent fan-out ran as generic Workflow agents because nothing the
        # numbered checklist asked led to the clean-run test, which sat in a later section
        titles = [title for _, title in self.steps]
        clean = next(i for i, t in enumerate(titles) if "clean run" in t.lower())
        draft = next(i for i, t in enumerate(titles) if t.startswith("Draft"))
        self.assertLess(clean, draft)
        self.assertEqual([int(n) for n, _ in self.steps], list(range(1, len(self.steps) + 1)))

    def test_the_clean_run_step_carries_the_four_conditions_and_the_default(self):
        step = self.procedure.split("**Clean run or Workflow?**", 1)[1].split("\n3. ", 1)[0]
        for phrase in ("self-contained", "no tool beyond Read", "do not coordinate",
                       "checked in code", "cleanrun.py plan"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step)


    def test_the_clean_run_step_shows_the_files_and_the_commands(self):
        # 2026-10-28: the step said to use cleanrun.py plan but not what to put in front of it, and in
        # auto mode the guard's warning arrives after the launch, so the skill is where the model learns it
        step = self.procedure.split("**Clean run or Workflow?**", 1)[1].split("\n3. ", 1)[0]
        step = " ".join(step.split())
        for phrase in ("tasks.jsonl", "rules.md", "schema.json", "check.py",
                       '{"path": "reports/q3.txt", "as": "q3/report.txt"}',
                       'python3 "<plugin>/scripts/cleanrun.py" plan --tasks tasks.jsonl --system-prompt rules.md '
                       '--schema schema.json --model <full id> --effort <effort> --validator check.py --out-dir out',
                       "--out-dir out --tools Read",        # 2026-11-06: tasks with files need a reading tool
                       "run --max-usd N", "status --out-dir out",
                       "two levels above this skill's base directory", "reference/fan-outs.md"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step)


class WorkedExample(unittest.TestCase):
    """The example at the end of fan-outs.md is run for real, against the stub, so it cannot drift from the script."""

    def setUp(self):
        text = FAN_OUTS.read_text(encoding="utf-8")
        self.example = text.split("### A worked example", 1)[1]
        self.files = {name: body for name, body in
                      re.findall(r"\*\*`([\w.]+)`\*\*[^\n]*\n```[a-z]*\n(.*?)\n```", self.example, re.S)}
        m = re.search(r"```\n(python3 \"<plugin>/scripts/cleanrun\.py\" plan.*?)\n```", self.example, re.S)
        self.commands = m.group(1).splitlines() if m else []

    def test_it_names_all_four_files_and_three_commands(self):
        self.assertEqual(sorted(self.files), ["check.py", "rules.md", "schema.json", "tasks.jsonl"])
        self.assertEqual([c.split()[2] for c in self.commands], ["plan", "run", "status"])

    def test_every_task_line_and_the_schema_are_json_and_one_task_uses_an_as_entry(self):
        lines = self.files["tasks.jsonl"].splitlines()
        tasks = [json.loads(line) for line in lines]
        self.assertEqual([t["id"] for t in tasks], ["t1", "t2"])
        self.assertTrue(any(isinstance(f, dict) and set(f) == {"path", "as"} for t in tasks for f in t["files"]))
        self.assertEqual(json.loads(self.files["schema.json"])["type"], "object")

    def test_the_commands_run_as_written_against_the_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name, body in self.files.items():
                (d / name).write_text(body + "\n", encoding="utf-8")
            (d / "reports").mkdir()
            (d / "page.txt").write_text("any text\n", encoding="utf-8")
            (d / "reports" / "q3.txt").write_text("any other text\n", encoding="utf-8")
            env = dict(os.environ, CLEANRUN_CLAUDE_BIN=f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE_CLAUDE))}",
                       FAKE_STATE_DIR=str(d))
            done = {}
            for line in self.commands:
                argv = shlex.split(line.replace('"<plugin>/scripts/cleanrun.py"', shlex.quote(str(CLEANRUN))))
                argv[0] = sys.executable
                done[argv[2]] = subprocess.run(argv, cwd=d, env=env, capture_output=True, text=True, timeout=120)
            plan, run, status = done["plan"], done["run"], done["status"]
            self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
            self.assertIn("plan: 2 task(s), 0 resume, 2 to run", plan.stdout)
            self.assertIn("tools 'Read'", plan.stdout)          # both tasks list files: the example must give Read
            self.assertIn("cost bound:", plan.stdout)
            # the stub answers {"answer": ...}, which the example's validator rightly rejects: what matters
            # here is that the written run line is accepted and runs (a usage error would be exit 2)
            self.assertIn(run.returncode, (0, 1), run.stdout + run.stderr)
            self.assertNotIn("Traceback", run.stdout + run.stderr)
            self.assertTrue((d / "out" / "summary.json").exists())
            self.assertEqual(status.returncode, run.returncode, status.stdout + status.stderr)   # status echoes the last run
            self.assertIn("last run", status.stdout)


class FanOutGuidance(unittest.TestCase):
    def setUp(self):
        self.text = FAN_OUTS.read_text(encoding="utf-8")
        self.skill = SKILL.read_text(encoding="utf-8")

    def test_every_saving_is_a_list_price_and_the_window_caveat_travels_with_it(self):
        for name, text in (("fan-outs.md", self.text), ("SKILL.md fan-out section",
                           self.skill.split("## Fan-outs", 1)[1].split("\n## ", 1)[0])):
            with self.subTest(doc=name):
                self.assertIn("list price", text)
                self.assertIn("usage-window effect was not measured", text)

    def test_no_withdrawn_or_single_observation_figures(self):
        for banned in ("PDF page", "$0.54", "$0.16", "$1.86", "$0.56"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.text)
                self.assertNotIn(banned, self.skill)

    def test_levers_carry_an_evidence_tag(self):
        lever_block = self.text.split("## Levers", 1)[1]
        for number in re.findall(r"^\d\.\s+\*\*.*?\*\*", lever_block, re.M):
            self.assertRegex(number, r"external|observed|untested|measured")

    def test_clean_run_guidance_says_the_saving_is_list_price_only(self):
        # clean runs entered the guidance once the owner accepted list price as the basis
        # (2026-10-08): the window effect stays unmeasured, so the caveat must travel with them
        section = self.text.split("## Clean runs", 1)[1]
        self.assertIn("list-price only", section)
        self.assertIn("window effect is not measured", section)
        self.assertIn("refuses aliases", section)

    def test_the_read_heavy_clean_run_saving_is_reported_with_its_confound_and_its_source(self):
        # 2026-10-28: the 63% was measured on short tasks. One read-heavy unit was then run both ways at a
        # cost of a few dollars: about half, but confounded (the Workflow readers self-checked with Bash,
        # the clean runs took far fewer turns) and a single Workflow sample, so it must not read as 63%
        # or as proof of a start-up saving
        section = " ".join(self.text.split("## Clean runs", 1)[1].split())
        for phrase in ("Read-heavy tasks: observed on one unit",
                       "about half on that unit, not 63%",
                       "observed, not measured",
                       "most of the saving is fewer turns and not a smaller start-up",
                       "The Workflow side is a single run",
                       "evals/research/2026-10-28-clean-run-read-heavy-unit.md"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
        self.assertTrue((ROOT / "evals" / "research" / "2026-10-28-clean-run-read-heavy-unit.md").is_file())

    def test_advisor_is_stated_as_a_fact_not_a_proposal(self):
        self.assertIn("do not raise it", self.text)

    def test_text_is_english_and_has_no_local_paths(self):
        for text in (self.text, self.skill):
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/private/", text)


DELEGATION = ROOT / "skills" / "agenting" / "reference" / "delegation.md"
MODES = ROOT / "skills" / "agenting" / "reference" / "modes.md"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
TEAMS_VAR = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"


class DelegationRules(unittest.TestCase):
    """The skill's rules for where work runs must agree with the hooks that enforce them."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.delegation = DELEGATION.read_text(encoding="utf-8")
        self.modes = MODES.read_text(encoding="utf-8")

    def test_the_skill_says_agent_starts_are_checked_and_the_hook_is_wired(self):
        self.assertIn("agent-routing-guard.py", self.skill)
        self.assertNotIn("is not gated", self.skill)
        entries = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        wired = [e for e in entries if e.get("matcher") == "Agent"
                 and any("agent-routing-guard.py" in h.get("command", "") for h in e.get("hooks", []))]
        self.assertEqual(len(wired), 1)

    def test_the_bulk_thresholds_are_the_same_in_the_skill_and_the_reference(self):
        # the owner fixed these on 2026-11-13; a pin keeps one file from drifting away from the other
        section = " ".join(self.skill.split("## Where the work runs", 1)[1].split("\n## ", 1)[0].split())
        reference = " ".join(self.delegation.split())
        for phrase in ("about 5 or more similar items",
                       "about 10 or more files or 20k or more tokens",
                       "2 or more independent parts",
                       "Time alone never decides"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
                self.assertIn(phrase, reference)

    def test_the_fast_thresholds_are_twice_the_usual_ones_in_the_skill_and_the_reference(self):
        # the owner fixed these on 2026-11-14 ("jobs about twice as big"); pinned in both files
        section = " ".join(self.skill.split("## Where the work runs", 1)[1].split("\n## ", 1)[0].split())
        reference = " ".join(self.delegation.split("## In `fast`", 1)[1].split("\n## ", 1)[0].split())
        for phrase in ("about 10 or more similar items",
                       "about 20 or more files or 40k or more tokens of reading",
                       "4 or more independent parts",
                       "only when the user asks for one"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)
                self.assertIn(phrase, reference)
        self.assertIn("Bulk coding still leaves the chat", section)
        self.assertIn("Bulk coding is not cut", reference)
        self.assertIn("fewer than 5 agents", reference)
        self.assertIn("/advisor off", reference)

    def test_the_prototype_rule_names_both_paths_and_what_each_mode_does(self):
        section = self.skill.split("## Where the work runs", 1)[1].split("\n## ", 1)[0]
        self.assertLess(section.index("**3. Think first?**"), section.index("**4. A prototype: throwaway or keep?**"))
        step = " ".join(section.split("**4. A prototype: throwaway or keep?**", 1)[1].split())
        for needle in ("the `cheapest` cells", "no tests, no review, no design pass", "in any disposition",
                       "keeping it means building it again on the keep path",
                       "The user's word decides", "in `manual` mode ask once before building",
                       "in `auto` mode decide, and say in one line which path you took",
                       "one new file outside the real code",
                       "changes real files or will be implemented if approved", "Unclear: keep."):
            with self.subTest(needle=needle):
                self.assertIn(needle, step)
        reference = self.delegation.split("## A prototype: throwaway or keep", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in reference.splitlines() if ln.startswith("| \"")]
        self.assertEqual([ln.split("|")[2].strip() for ln in rows],
                         ["Throwaway", "Throwaway", "Keep", "Keep", "Keep"])
        self.assertIn("Unclear, so keep", rows[-1])
        self.assertIn("it is built again on the keep path", " ".join(reference.split()))

    def test_the_four_vehicles_are_named_in_the_same_order_in_both_files(self):
        order = ["One agent", "Clean run", "Workflow", "Teammates"]
        for name, text in (("SKILL.md", self.skill.split("## Where the work runs", 1)[1].split("\n## ", 1)[0]),
                           ("delegation.md", self.delegation.split("## The four vehicles", 1)[1].split("\n## ", 1)[0])):
            with self.subTest(doc=name):
                rows = [line.split("|")[1].strip().strip("*") for line in text.splitlines()
                        if line.startswith("|") and not line.startswith("|---") and "Vehicle" not in line]
                self.assertEqual([next(o for o in order if r.startswith(o)) for r in rows], order)

    def test_the_teammates_switch_has_one_name_in_the_docs_and_the_hooks(self):
        for path in (DELEGATION, ROOT / "hooks" / "session-continuity.py", ROOT / "hooks" / "agent-routing-guard.py"):
            with self.subTest(file=path.name):
                self.assertIn(TEAMS_VAR, path.read_text(encoding="utf-8"))

    def test_the_teammate_effort_rule_is_stated_where_a_teammate_is_started(self):
        section = " ".join(self.skill.split("## Agent starts", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn("its effort **only from an agent file**", section)
        self.assertIn("TaskStop", section)
        self.assertIn("effort only from an agent file", " ".join(self.delegation.replace("*", "").split()))

    def test_the_standing_default_is_documented_with_the_flag_the_recorder_accepts(self):
        self.assertIn("--record-default --workflows on", self.modes)
        recorder = (ROOT / "hooks" / "session-continuity.py").read_text(encoding="utf-8")
        self.assertIn('"--record-default"', recorder)

    def test_the_delegation_reference_has_no_local_paths(self):
        self.assertNotIn("/Users/", self.delegation)
        self.assertNotIn("/private/", self.delegation)


README = ROOT / "README.md"
ALONE = ("Work alone. The `advisor` tool belongs to the lead that started you, so do not call it: "
         "decide from the brief and the files, and when something blocks you, say so in your result.")
CARRIES_ALONE = re.compile(r"work alone\..{0,40}advisor", re.I)


class AdvisorDocs(unittest.TestCase):
    """The docs for "workers work alone" must carry the exact sentence the hooks look for."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.delegation = DELEGATION.read_text(encoding="utf-8")
        self.readme = README.read_text(encoding="utf-8")

    def test_the_skill_carries_the_work_alone_sentence_once_in_its_own_section(self):
        self.assertEqual(self.skill.count(ALONE), 1)
        section = self.skill.split("## The advisor is for the decider", 1)[1].split("\n## ", 1)[0]
        self.assertIn(ALONE, section)
        self.assertTrue(any(CARRIES_ALONE.search(line) for line in section.splitlines()))
        self.assertIn("// advisor: allowed", section)
        self.assertIn("const ALONE", section)
        self.assertLessEqual(len([line for line in section.splitlines() if line.strip()]), 16)
        # the section follows "Where the work runs" and the routing table follows it
        order = [self.skill.index(h) for h in ("## Where the work runs", "## The advisor is for the decider",
                                               "## Routing table")]
        self.assertEqual(order, sorted(order))

    def test_the_delegation_reference_carries_the_sentence_or_names_the_skill_as_its_source(self):
        section = self.delegation.split("## The advisor\n", 1)[1].split("\n## ", 1)[0]
        flat = " ".join(section.split())
        self.assertTrue(ALONE in flat or ("SKILL.md" in flat and "The advisor is for the decider" in flat))
        for phrase in ("Subagents inherit the configured advisor", "CLAUDE_CODE_DISABLE_ADVISOR_TOOL",
                       "advisor: allowed", "--disallowedTools"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)
        # the limits belong to the "not measured" section, which stays the last one
        self.assertLess(self.delegation.index("## The advisor\n"), self.delegation.index("## What was not measured"))
        self.assertIn("--advisor", self.delegation.split("## What was not measured", 1)[1])

    def test_the_readme_names_the_allow_mark_and_the_environment_variable(self):
        self.assertIn("advisor: allowed", self.readme)
        self.assertIn("CLAUDE_CODE_DISABLE_ADVISOR_TOOL", self.readme)

    def test_the_advisor_docs_carry_no_local_paths(self):
        for name, text in (("SKILL.md", self.skill), ("delegation.md", self.delegation), ("README.md", self.readme)):
            with self.subTest(doc=name):
                self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()


class ThinkFirstDocs(unittest.TestCase):
    """The think-first step, its two routing rows and the agent roster: the 2026-11-13 round, and the
    architecture round of 2026-11-15 that gave the architecture row to Sonnet xhigh below "critical".
    The expected cells are written here from the reports, not read from the files under test."""

    NEW_ROWS = ("Decide an architecture or approach that later work is built on",
                "Design a UI/UX solution before a prototype, screen or flow is built")
    MODES_ROWS = ("Architecture or approach decision", "UI/UX design before a build")

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.modes = (ROOT / "skills" / "agenting" / "reference" / "modes.md").read_text(encoding="utf-8")
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def section(self, text, start, end):
        a = text.index(start)
        return text[a:text.index(end, a)]

    def test_the_think_first_step_states_its_three_conditions_and_its_two_design_agents(self):
        step = self.section(self.skill, "**3. Think first?**", "## The advisor is for the decider")
        for needle in ("later work is built on the choice", "at least two options would work",
                       "expensive to undo", "Otherwise just build",
                       "`agenting:system-architect`", "`agenting:ux-designer`",
                       "it is not the default", "only when the user asks for it",
                       "the model of its disposition's cell, or of the one \"critical\" picks",
                       "The architecture row was"):
            with self.subTest(needle=needle):
                self.assertIn(needle, step)
        self.assertLess(self.skill.index("**2. Which vehicle?**"), self.skill.index("**3. Think first?**"))

    def test_the_architecture_row_is_sonnet_xhigh_below_critical_and_the_ux_row_is_opus_xhigh(self):
        table = self.section(self.skill, "## Routing table", "**How the cells were measured.**")
        # the routing table is `balanced`: Sonnet xhigh for the architecture row since the round of
        # 2026-11-15 (7 fails of 30 against Opus xhigh's 10, under both judge models), Opus xhigh for UI/UX.
        routed = dict(zip(self.NEW_ROWS, (["`sonnet`", "`xhigh`"], ["`opus`", "`xhigh`"])))
        for row in self.NEW_ROWS:
            with self.subTest(row=row):
                line = next(ln for ln in table.splitlines() if ln.startswith(f"| {row} |"))
                self.assertEqual([c.strip() for c in line.split("|")[2:4]], routed[row])
        # columns of the disposition table: cheapest, fast, balanced, "critical". The owner gave the
        # architecture row to Sonnet xhigh in cheapest; the round's rules gave it to fast and balanced.
        expected = {"Architecture or approach decision": ["`sonnet`/`xhigh`"] * 3 + ["`opus`/`xhigh`"],
                    "UI/UX design before a build": ["`opus`/`xhigh`"] * 4}
        for row in self.MODES_ROWS:
            with self.subTest(row=row):
                line = next(ln for ln in self.modes.splitlines() if ln.startswith(f"| {row} |"))
                self.assertEqual([c.strip() for c in line.split("|")[2:6]], expected[row])

    def test_the_design_agents_file_pins_the_critical_cell_and_the_step_says_to_name_the_model(self):
        # agents/system-architect.md stays on Opus xhigh, the cell "critical" picks for the architecture
        # row. The row's own cell is Sonnet xhigh, so the step must say to write that model on the call.
        fm = re.match(r"^---\n(.*?)\n---\n", (ROOT / "agents" / "system-architect.md").read_text(encoding="utf-8"),
                      re.S).group(1)
        pinned = "`{}`/`{}`".format(re.search(r"^model:\s*(\S+)", fm, re.M).group(1),
                                    re.search(r"^effort:\s*(\S+)", fm, re.M).group(1))
        line = next(ln for ln in self.modes.splitlines() if ln.startswith("| Architecture or approach decision |"))
        cells = [c.strip() for c in line.split("|")[2:6]]
        self.assertEqual(pinned, cells[3])
        self.assertEqual(pinned, "`opus`/`xhigh`")
        step = " ".join(self.section(self.skill, "**3. Think first?**", "## The advisor is for the decider").split())
        self.assertIn("`system-architect`'s file pins the \"critical\" cell, `opus`/`xhigh`", step)
        self.assertIn("write the row's model on the call: `model: 'sonnet'`", step)
        self.assertIn("The architecture row was measured at `xhigh` only: at `high`, Sonnet was never run on it and "
                      "Opus passed 0 of 3 runs of the hard task.", step)
        self.assertEqual(cells[2], "`sonnet`/`xhigh`")          # the cell that sentence names is balanced's

    def test_no_cell_of_the_routing_table_or_the_disposition_table_names_fable(self):
        table = self.section(self.skill, "## Routing table", "**How the cells were measured.**")
        rows = [ln for ln in table.splitlines() if ln.startswith("| ")]
        rows += [ln for ln in self.modes.splitlines() if ln.startswith("| ") and "`/`" in ln]
        self.assertGreater(len(rows), 15)
        for ln in rows:
            with self.subTest(row=ln[:40]):
                self.assertNotIn("fable", ln.lower())

    def tier_table(self, text, sep):
        """{agent name: "model/effort"} from a tier table whose rows look like | `opus`<sep>`xhigh` | `a`, `b` |."""
        out = {}
        for m in re.finditer(rf"^\| `(\w+)`{re.escape(sep)}`(\w+)` \| (.+?) \|$", text, re.M):
            for name in re.findall(r"`([a-z-]+)`", m.group(3)):
                self.assertNotIn(name, out, f"{name} is listed twice")
                out[name] = f"{m.group(1)}/{m.group(2)}"
        return out

    def test_the_agent_tables_list_every_agent_file_once_at_the_tier_its_front_matter_pins(self):
        files = {}
        for f in sorted((ROOT / "agents").glob("*.md")):
            fm = re.match(r"^---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S).group(1)
            files[f.stem] = "{}/{}".format(re.search(r"^model:\s*(\S+)", fm, re.M).group(1),
                                           re.search(r"^effort:\s*(\S+)", fm, re.M).group(1))
        self.assertIn("ux-designer", files)
        agents_part = self.section(self.skill, "| Tier | Agents (`agenting:<name>`) |", "Every tier here is a Claude model")
        self.assertEqual(self.tier_table(agents_part, "/"), files)
        self.assertEqual(self.tier_table(self.readme, " / "), files)
        self.assertIn(f"**{len(files)} tiered agent definitions**", self.readme)

    def test_the_ux_designer_is_read_only_on_opus_xhigh_and_returns_the_six_part_brief(self):
        text = (ROOT / "agents" / "ux-designer.md").read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertRegex(fm, r"(?m)^model: opus$")
        self.assertRegex(fm, r"(?m)^effort: xhigh$")
        self.assertRegex(fm, r"(?m)^tools: Read, Grep, Glob$")
        for part in ("**Screens:**", "**Flow:**", "**States:**", "**Words:**", "**Main action:**", "**Assumptions:**"):
            with self.subTest(part=part):
                self.assertIn(part, text)
        self.assertIn("write no code", text)


class ModeTableDocs(unittest.TestCase):
    """The disposition table after 3.7.0: a cheapest column, three build rows, don't-guess on Haiku xhigh,
    the architecture row on Sonnet xhigh below "critical". The expected cells are the owner's decisions of
    2026-11-15 and the verdict of that day's architecture round, written here, not read from the files."""

    COLUMNS = ["`cheapest`", "`fast`", "`balanced`", '"critical"']
    CELLS = {
        "List / count": ["haiku/medium"] * 4,
        "Mechanical cleanup": ["sonnet/low"] * 4,
        "Read code/prose, report": ["haiku/medium"] * 3 + ["sonnet/high"],
        "Prose→rules, classify, judge": ["haiku/xhigh", "sonnet/low", "sonnet/medium", "sonnet/high"],
        "Synthesize across many files": ["opus/high", "opus/high", "opus/xhigh", "opus/xhigh"],
        "Decide under BELİRSİZ": ["haiku/xhigh"] * 3 + ["opus/xhigh"],
        "Adversarial verify/refute": ["haiku/xhigh", "sonnet/high", "sonnet/high", "opus/high"],
        "Architecture or approach decision": ["sonnet/xhigh"] * 3 + ["opus/xhigh"],
        "UI/UX design before a build": ["opus/xhigh"] * 4,
        "Plan a build and write its tests": ["sonnet/high", "sonnet/high", "opus/high", "opus/high"],
        "Bulk coding against tests that exist": ["haiku/medium"] * 3 + ["sonnet/low"],
        "Review a build": ["haiku/xhigh", "sonnet/high", "sonnet/high", "opus/high"],
    }

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.modes = (ROOT / "skills" / "agenting" / "reference" / "modes.md").read_text(encoding="utf-8")

    def table(self):
        """{row name: [four cells as model/effort]} of the disposition table, and its header cells."""
        lines = self.modes.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith("| Routing-table row |"))
        header = [c.strip() for c in lines[start].split("|")[2:-1]]
        rows = {}
        for ln in lines[start + 2:]:
            if not ln.startswith("| "):
                break
            cells = [c.strip() for c in ln.split("|")[1:-1]]
            rows[cells[0]] = [c.replace("`", "") for c in cells[1:]]
        return header, rows

    def test_the_disposition_table_has_the_four_columns_and_every_cell_the_owner_decided(self):
        header, rows = self.table()
        self.assertEqual(header, self.COLUMNS)
        self.assertEqual(rows, self.CELLS)

    def test_the_review_row_follows_the_verify_row_in_every_column(self):
        _, rows = self.table()
        self.assertEqual(rows["Review a build"], rows["Adversarial verify/refute"])

    def test_the_routing_table_is_the_balanced_column_for_the_changed_rows(self):
        table = self.skill[self.skill.index("## Routing table"):self.skill.index("**How the cells were measured.**")]
        expected = {"Decide under a \"don't guess\" constraint (BELİRSİZ)": ["`haiku`", "`xhigh`"],
                    "Plan a build and write its tests, before cheaper workers code": ["`opus`", "`high`"],
                    "Bulk coding against tests that exist": ["`haiku`", "`medium`"],
                    "Review a build before it is called done": ["`sonnet`", "`high`"]}
        for row, cells in expected.items():
            with self.subTest(row=row):
                line = next(ln for ln in table.splitlines() if ln.startswith(f"| {row} |"))
                self.assertEqual([c.strip() for c in line.split("|")[2:4]], cells)

    def test_what_cheapest_gives_up_is_written_down_row_by_row(self):
        part = self.modes[self.modes.index("**What `cheapest` gives up,**"):self.modes.index("## The plan sets where a new chat starts")]
        flat = " ".join(part.split())
        for needle in ("Classify on Haiku `xhigh`: 4.1% wrong labels", "Verify on Haiku `xhigh`: 1 false \"confirmed\" in 384",
                       "Review follows verify and was not measured itself", "cheaper at list price, not quicker"):
            with self.subTest(needle=needle):
                self.assertIn(needle, flat)
        self.assertNotIn("architecture", flat)          # since 2026-11-15 cheapest gives nothing up there
        self.assertIn("`fast` keeps a safer cell on two rows, by the owner's choice: classify and verify (with review)",
                      " ".join(self.modes.split()))

    def test_no_plan_starts_in_cheapest_and_the_docs_say_so(self):
        flat = " ".join(self.modes.split())
        self.assertIn("No plan starts a chat in `cheapest`.", flat)
        self.assertIn("Change mode: /agenting-mode [cheapest|fast|balanced]", flat)
        self.assertIn("starts in the plan's when the plan can be read, never in `cheapest`", " ".join(self.skill.split()))

    def test_the_docs_say_when_an_effort_change_keeps_the_cache_and_when_it_does_not(self):
        part = self.modes[self.modes.index("## The plan sets where a new chat starts"):self.modes.index("## Where the cells come from")]
        flat = " ".join(part.split())
        for needle in ("For an architecture decision (a choice later work is built on) raise the effort (/effort xhigh) "
                       "and stay on Sonnet, then go back to high",
                       "An effort change keeps the cache on Sonnet 5.5 with a subscription or an API key.",
                       "It does not on Amazon Bedrock, Google Cloud or a Claude apps gateway, with "
                       "`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` set, or under a HIPAA configuration",
                       "It does not cover a UI/UX design, whose row is Opus `xhigh`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, flat)
        # the line the docs quote is the hook's own tip
        hook = (ROOT / "hooks" / "session-continuity.py").read_text(encoding="utf-8")
        tip = re.search(r'^MAIN_CHAT_TIP = "(.*)"$', hook, re.M).group(1)
        self.assertIn(f"Tip: {tip}. Change mode: /agenting-mode [cheapest|fast|balanced]", flat)

    def test_the_bulk_coder_is_haiku_medium_never_changes_tests_and_stops_after_three_failed_checks(self):
        text = (ROOT / "agents" / "bulk-coder.md").read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertRegex(fm, r"(?m)^model: haiku$")
        self.assertRegex(fm, r"(?m)^effort: medium$")
        flat = " ".join(text.split())
        for needle in ("Never change, delete, skip or weaken a given test file or the test runner's configuration",
                       "Check with the command you were given, and only with it",
                       "At most three failed checks", "Never write \"pass\" unless you ran the check and saw it pass",
                       "Work alone. The `advisor` tool belongs to the lead that started you"):
            with self.subTest(needle=needle):
                self.assertIn(needle, flat)
        self.assertIn("`agenting:bulk-coder`", self.skill)

