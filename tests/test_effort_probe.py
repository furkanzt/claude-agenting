"""The subagent-effort reader (evals/probes/read_effort.py): it reports the effort a subagent
transcript records, groups repeats by label, and flags a pin that was not applied."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "evals" / "probes" / "read_effort.py"
spec = importlib.util.spec_from_file_location("read_effort_under_test", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def write_agent(directory, agent_id, label, effort, thinking_ms=1000, model="claude-haiku-5-5", extra=()):
    lines = [json.dumps({"type": "user", "message": {}})]
    for ms in (thinking_ms,) * 2:
        lines.append(json.dumps({"type": "assistant", "effort": effort, "perTurnEffort": effort,
                                 "requestedModel": model, "thinkingDurationMs": ms, "message": {"usage": {}}}))
    lines.extend(extra)
    (Path(directory) / f"agent-{agent_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (Path(directory) / f"agent-{agent_id}.meta.json").write_text(json.dumps({"description": label}), encoding="utf-8")


class ReadEffort(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_the_recorded_effort_model_and_thinking_time(self):
        write_agent(self.dir, "a1", "low-1", "low", thinking_ms=2500)
        [agent] = probe.read_agents(self.dir)
        self.assertEqual((agent["label"], agent["efforts"], agent["models"]), ("low-1", ["low"], ["claude-haiku-5-5"]))
        self.assertEqual((agent["turns"], agent["thinking_ms"]), (2, 5000))

    def test_groups_repeats_by_label_and_averages_thinking_time(self):
        write_agent(self.dir, "a1", "high-1", "high", thinking_ms=1000)
        write_agent(self.dir, "a2", "high-2", "high", thinking_ms=3000)
        write_agent(self.dir, "a3", "low-1", "low", thinking_ms=500)
        summary = probe.summarize(probe.read_agents(self.dir))
        self.assertEqual(summary["high"]["n"], 2)
        self.assertEqual(summary["high"]["mean_thinking_ms"], 4000)
        self.assertEqual(summary["low"]["efforts"], ["low"])

    def test_ignores_non_assistant_and_unparseable_lines(self):
        write_agent(self.dir, "a1", "low-1", "low", extra=("{not json", json.dumps([1, 2])))
        [agent] = probe.read_agents(self.dir)
        self.assertEqual(agent["turns"], 2)

    def test_a_pin_that_was_not_applied_is_reported(self):
        write_agent(self.dir, "a1", "xhigh-1", "medium")
        summary = probe.summarize(probe.read_agents(self.dir))
        self.assertEqual(probe.check_expectations(summary, {"xhigh": "xhigh"}),
                         ["xhigh: expected effort xhigh, recorded ['medium']"])
        self.assertEqual(probe.check_expectations(summary, {"xhigh": "medium"}), [])
        self.assertEqual(probe.check_expectations(summary, {"high": "high"}), ["high: no agents found"])

    def test_the_cli_exits_nonzero_on_a_mismatch_and_zero_otherwise(self):
        write_agent(self.dir, "a1", "low-1", "low")
        run = lambda expect: subprocess.run([sys.executable, str(SCRIPT), str(self.dir), "--expect", expect],
                                            capture_output=True, text=True)
        self.assertEqual(run("low=low").returncode, 0)
        bad = run("low=high")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("MISMATCH low: expected effort high", bad.stdout)

    def test_an_empty_directory_is_an_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.dir)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
