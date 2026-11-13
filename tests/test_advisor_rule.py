"""The advisor rule for agent files: workers work alone, the design agent is the one exception.

The sentence below is a literal on purpose. It is not read from any file under test, so a
change to an agent file cannot move the pin with it.
"""

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"

SENTENCE = (
    "Work alone. The `advisor` tool belongs to the lead that started you, so do not call it: "
    "decide from the brief and the files, and when something blocks you, say so in your result."
)
# The one agent that may use the advisor: the design agent.
EXCEPTIONS = frozenset({"system-architect"})


def front_matter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


def check_agents(agents_dir, exceptions=EXCEPTIONS):
    """Return a list of problems found in a folder of agent files (empty means clean)."""
    problems = []
    files = {p.stem: p for p in sorted(Path(agents_dir).glob("*.md"))}
    for name in sorted(exceptions):
        if name not in files:
            problems.append(f"exception {name} has no file")
    for name, path in files.items():
        text = path.read_text(encoding="utf-8")
        want = 0 if name in exceptions else 1
        got = text.count(SENTENCE)
        if got != want:
            problems.append(f"{name}: sentence appears {got} times, expected {want}")
        keys = {line.split(":", 1)[0].strip() for line in front_matter(text).splitlines() if ":" in line}
        for key in ("model", "effort"):
            if key not in keys:
                problems.append(f"{name}: front matter has no {key}")
    return problems


def write_agent(folder, name, body, extra_front=""):
    text = f"---\nname: {name}\ndescription: test\nmodel: sonnet\neffort: low\n{extra_front}---\n\n{body}\n"
    (Path(folder) / f"{name}.md").write_text(text, encoding="utf-8")


class RealAgentFiles(unittest.TestCase):
    def setUp(self):
        self.files = sorted(AGENTS.glob("*.md"))

    def test_there_are_agent_files(self):
        self.assertGreater(len(self.files), 5)

    def test_every_worker_agent_carries_the_work_alone_sentence_once(self):
        for path in self.files:
            if path.stem in EXCEPTIONS:
                continue
            with self.subTest(agent=path.stem):
                self.assertEqual(path.read_text(encoding="utf-8").count(SENTENCE), 1)

    def test_the_design_agent_does_not_carry_the_sentence(self):
        for name in EXCEPTIONS:
            with self.subTest(agent=name):
                path = AGENTS / f"{name}.md"
                self.assertTrue(path.exists(), f"exception {name} has no file")
                self.assertEqual(path.read_text(encoding="utf-8").count(SENTENCE), 0)

    def test_every_agent_front_matter_still_has_model_and_effort(self):
        for path in self.files:
            with self.subTest(agent=path.stem):
                keys = {
                    line.split(":", 1)[0].strip()
                    for line in front_matter(path.read_text(encoding="utf-8")).splitlines()
                    if ":" in line
                }
                self.assertIn("model", keys)
                self.assertIn("effort", keys)

    def test_the_whole_folder_passes_the_checker(self):
        self.assertEqual(check_agents(AGENTS), [])


class Checker(unittest.TestCase):
    """The checker itself must bite on synthetic folders."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_a_worker_without_the_sentence_is_reported(self):
        write_agent(self.dir, "worker", "Body.")
        write_agent(self.dir, "system-architect", "Design.")
        self.assertEqual(check_agents(self.dir), ["worker: sentence appears 0 times, expected 1"])

    def test_a_worker_with_the_sentence_twice_is_reported(self):
        write_agent(self.dir, "worker", f"{SENTENCE}\n\n{SENTENCE}")
        write_agent(self.dir, "system-architect", "Design.")
        self.assertEqual(check_agents(self.dir), ["worker: sentence appears 2 times, expected 1"])

    def test_the_exception_carrying_the_sentence_is_reported(self):
        write_agent(self.dir, "worker", SENTENCE)
        write_agent(self.dir, "system-architect", SENTENCE)
        self.assertEqual(check_agents(self.dir), ["system-architect: sentence appears 1 times, expected 0"])

    def test_an_exception_name_with_no_file_is_reported(self):
        write_agent(self.dir, "worker", SENTENCE)
        self.assertEqual(check_agents(self.dir), ["exception system-architect has no file"])

    def test_a_front_matter_without_effort_is_reported(self):
        path = self.dir / "worker.md"
        path.write_text(f"---\nname: worker\nmodel: sonnet\n---\n\n{SENTENCE}\n", encoding="utf-8")
        write_agent(self.dir, "system-architect", "Design.")
        self.assertEqual(check_agents(self.dir), ["worker: front matter has no effort"])


if __name__ == "__main__":
    unittest.main()
