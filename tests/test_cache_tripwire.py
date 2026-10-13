"""Tests for hooks/cache-tripwire.py: lines that are not a real tier never cause a nudge.

The hook keeps its state next to the script, so every test copies the script into a
fresh temporary directory and runs the copy; the repo's hooks/ directory is never
written to, and nothing reads ~/.claude.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "cache-tripwire.py"

SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
SYNTHETIC = "<synthetic>"


def line(model, effort="high", write=32000, sidechain=False):
    message = {"usage": {"cache_creation_input_tokens": write}}
    if model is not None:
        message["model"] = model
    return {"type": "assistant", "isSidechain": sidechain, "effort": effort, "message": message}


class TripwireCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.script = self.dir / "cache-tripwire.py"
        shutil.copy(HOOK, self.script)
        self.state_path = self.dir / ".cache-tripwire-state.json"
        self.transcript = self.dir / "t.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def write_transcript(self, records):
        self.transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    def write_state(self, data):
        self.state_path.write_text(json.dumps(data), encoding="utf-8")

    def state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def prompt(self, session="s1"):
        """Run the hook copy once; return the additionalContext or None when silent."""
        payload = {"session_id": session, "transcript_path": str(self.transcript)}
        r = subprocess.run([sys.executable, str(self.script)], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.strip()
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None


class SyntheticAndModelLessLinesTest(TripwireCase):
    def test_a_synthetic_latest_line_between_same_tier_lines_stays_silent_on_two_prompts(self):
        self.write_transcript([line(SONNET, "xhigh"), line(SYNTHETIC, None, 0)])
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|xhigh"})
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|xhigh"})

    def test_a_synthetic_first_line_seeds_the_baseline_at_the_first_real_tier(self):
        self.write_transcript([line(SYNTHETIC, None, 0), line(SONNET, "xhigh"), line(SONNET, "xhigh")])
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|xhigh"})

    def test_lines_with_no_model_are_skipped_like_synthetic_ones(self):
        self.write_transcript([line(None, None, 0), line(SONNET, "high"), line(None, None, 0)])
        self.assertIsNone(self.prompt())
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|high"})

    def test_a_message_that_is_not_an_object_is_skipped(self):
        self.write_transcript([{"type": "assistant", "message": "oops"}, line(SONNET, "high")])
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|high"})

    def test_a_transcript_of_only_synthetic_lines_exits_silently_without_state(self):
        self.write_transcript([line(SYNTHETIC, None, 0), line(None, None, 0)])
        self.assertIsNone(self.prompt())
        self.assertFalse(self.state_path.exists())

    def test_a_real_switch_after_a_synthetic_line_still_fires_with_the_real_tags(self):
        self.write_state({"s1": f"{SONNET}|high"})
        self.write_transcript([line(SONNET, "high"), line(SYNTHETIC, None, 0),
                               line(OPUS, "max", 66975), line(SYNTHETIC, None, 0)])
        msg = self.prompt()
        self.assertEqual(msg, "[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max: "
                              "re-wrote 67k tokens, ~$0.33 of window.")
        self.assertEqual(self.state(), {"s1": f"{OPUS}|max"})
        self.assertIsNone(self.prompt())


class LegacyBaselineTest(TripwireCase):
    def test_a_legacy_none_baseline_is_reseeded_silently_when_the_real_tier_never_changed(self):
        self.write_state({"s1": "None|None"})
        self.write_transcript([line(SONNET, "high"), line(SONNET, "high")])
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|high"})

    def test_a_legacy_synthetic_baseline_is_reseeded_silently_when_the_real_tier_never_changed(self):
        self.write_state({"s1": f"{SYNTHETIC}|None"})
        self.write_transcript([line(SONNET, "high"), line(SONNET, "high")])
        self.assertIsNone(self.prompt())
        self.assertEqual(self.state(), {"s1": f"{SONNET}|high"})

    def test_a_legacy_baseline_with_a_real_drift_fires_once_then_stays_silent(self):
        self.write_state({"s1": "None|None"})
        self.write_transcript([line(SONNET, "high"), line(OPUS, "max", 66975)])
        msg = self.prompt()
        self.assertTrue(msg.startswith("[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max"), msg)
        self.assertEqual(self.state(), {"s1": f"{OPUS}|max"})
        self.assertIsNone(self.prompt())

    def test_a_legacy_synthetic_baseline_with_a_real_drift_fires_once_then_stays_silent(self):
        self.write_state({"s1": f"{SYNTHETIC}|xhigh"})
        self.write_transcript([line(SONNET, "high"), line(OPUS, "max")])
        self.assertTrue(self.prompt().startswith("[cache tripwire] model changed sonnet-5-5/high -> opus-5-5/max"))
        self.assertIsNone(self.prompt())


if __name__ == "__main__":
    unittest.main()
