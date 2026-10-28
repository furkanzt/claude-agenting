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
    "switches agenting mode (auto/manual) or disposition (fast/balanced/quality)",
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


if __name__ == "__main__":
    unittest.main()
