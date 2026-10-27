"""Guards on the agenting skill's text: triggers must not shrink, and the fan-out
guidance must keep its evidence caveats."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "agenting" / "SKILL.md"
FAN_OUTS = ROOT / "skills" / "agenting" / "reference" / "fan-outs.md"

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

    def test_advisor_is_stated_as_a_fact_not_a_proposal(self):
        self.assertIn("do not raise it", self.text)

    def test_text_is_english_and_has_no_local_paths(self):
        for text in (self.text, self.skill):
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/private/", text)


if __name__ == "__main__":
    unittest.main()
