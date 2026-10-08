"""Tests for scripts/measure-tokenomics.py: the price table, the cost model and the two reports.

Every transcript here is built by hand in a temporary projects directory; nothing
reads ~/.claude. Dollar expectations are written out from the price page (the
list in PRICE_PAGE) and not taken from the script's own table, so a wrong table
row fails a test instead of agreeing with itself. The write columns of the
claude-opus-5 row are the exception: the page documents its input, output and
read prices only, and its writes follow the page's 1.25x / 2x rule.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "measure-tokenomics.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tok = load(SCRIPT, "measure_tokenomics_under_test")

# $/MTok from evals/research/2026-10-05-models.md section 1: input, output, cache read, write 5m, write 1h.
PRICE_PAGE = {
    "claude-haiku-4-5-20251001": (1, 5, 0.10, 1.25, 2),
    "claude-sonnet-5-5": (2, 10, 0.20, 2.50, 4),
    "claude-opus-5-5": (4, 20, 0.20, 5, 8),
    "claude-fable-5-1": (10, 50, 0.25, 12.50, 20),
    "claude-opus-5": (5, 25, 0.50, 6.25, 10),
}
M = 1_000_000


def usage(inp=0, out=0, read=0, w5=0, w1=0, split=True, iterations=None, thinking=None):
    u = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
         "cache_creation_input_tokens": w5 + w1}
    if split:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}
    if iterations is not None:
        u["iterations"] = iterations
    if thinking is not None:
        u["output_tokens_details"] = {"thinking_tokens": thinking}
    return u


def stamp(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def assistant(mid, model, minutes_ago, u, effort="high", agent_id=None, sidechain=False):
    rec = {"type": "assistant", "timestamp": stamp(minutes_ago), "effort": effort,
           "message": {"id": mid, "model": model, "usage": u}}
    if agent_id:
        rec["agentId"] = agent_id
    if sidechain:
        rec["isSidechain"] = True
    return rec


def write_lines(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def cost_of(model, inp=0, out=0, read=0, w5=0, w1=0):
    p_in, p_out, p_read, p_w5, p_w1 = PRICE_PAGE[model]
    return (inp * p_in + out * p_out + read * p_read + w5 * p_w5 + w1 * p_w1) / M


class PriceTable(unittest.TestCase):
    def test_every_row_prices_each_category_from_the_price_page(self):
        for model, (p_in, p_out, p_read, p_w5, p_w1) in PRICE_PAGE.items():
            with self.subTest(model=model):
                usd, tokens, priced, legacy = tok.usage_parts(usage(inp=M, out=M, read=M, w5=M, w1=M), model)
                self.assertTrue(priced)
                self.assertFalse(legacy)
                self.assertAlmostEqual(usd["input"], p_in)
                self.assertAlmostEqual(usd["output"], p_out)
                self.assertAlmostEqual(usd["cache_read"], p_read)
                self.assertAlmostEqual(usd["write_5m"], p_w5)
                self.assertAlmostEqual(usd["write_1h"], p_w1)

    def test_previous_generation_is_not_priced_as_5_5(self):
        # Opus 5 is $5/$25 with $0.50 reads; Opus 5.5 is $4/$20 with $0.20 reads.
        self.assertNotEqual(tok.price_for("claude-opus-5"), tok.price_for("claude-opus-5-5"))
        self.assertEqual(tok.price_for("claude-opus-5").read, 0.50)
        self.assertEqual(tok.price_for("claude-opus-5-5").read, 0.20)

    def test_dated_suffix_and_alias_resolve_to_the_same_row(self):
        self.assertEqual(tok.price_for("claude-haiku-4-5"), tok.price_for("claude-haiku-4-5-20251001"))
        self.assertEqual(tok.price_for("claude-opus-5-5-20260922"), tok.price_for("claude-opus-5-5"))
        self.assertEqual(tok.price_for("claude-opus-5-5[1m]"), tok.price_for("claude-opus-5-5"))

    def test_unknown_model_is_unpriced_with_its_tokens_kept(self):
        usd, tokens, priced, _ = tok.usage_parts(usage(inp=10, out=20, read=30, w1=40), "claude-opus-4-8")
        self.assertFalse(priced)
        self.assertEqual(sum(usd.values()), 0.0)
        self.assertEqual(sum(tokens.values()), 100)
        call = tok.CallParts({"message": {"model": "claude-opus-4-8", "usage": usage(inp=10, out=20, read=30, w1=40)}})
        footer = tok.Footer()
        footer.add([call])
        self.assertTrue(any("claude-opus-4-8" in line and "100 tokens" in line for line in footer.lines()))

    def test_prices_are_dated(self):
        self.assertRegex(tok.PRICES_AS_OF, r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn(tok.PRICES_AS_OF, tok.price_header())

    def test_input_prices_agree_with_the_cache_tripwire_hook(self):
        tripwire = load(ROOT / "hooks" / "cache-tripwire.py", "cache_tripwire_under_test")
        ours = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5-5",
                "opus": "claude-opus-5-5", "fable": "claude-fable-5-1"}
        for family, price in tripwire.PRICES_PER_MTOK.items():
            with self.subTest(family=family):
                self.assertEqual(price, tok.price_for(ours[family]).input)


class CostParts(unittest.TestCase):
    def test_writes_are_priced_by_ttl(self):
        usd, _, _, _ = tok.usage_parts(usage(w5=M, w1=M), "claude-opus-5-5")
        self.assertAlmostEqual(usd["write_5m"], 5.0)
        self.assertAlmostEqual(usd["write_1h"], 8.0)

    def test_record_without_a_split_is_a_5m_write_and_flagged(self):
        usd, tokens, _, legacy = tok.usage_parts(usage(w5=M, split=False), "claude-opus-5-5")
        self.assertTrue(legacy)
        self.assertEqual((tokens["write_5m"], tokens["write_1h"]), (M, 0))
        self.assertAlmostEqual(usd["write_5m"], 5.0)
        footer = tok.Footer()
        footer.add([tok.CallParts({"message": {"model": "claude-opus-5-5", "usage": usage(w5=M, split=False)}})])
        self.assertTrue(any("no 5m/1h" in line for line in footer.lines()))

    def test_a_split_that_does_not_add_up_puts_the_rest_in_5m(self):
        u = usage(w5=500_000, w1=500_000)
        u["cache_creation_input_tokens"] = 1_500_000
        w5, w1, legacy = tok.split_writes(u)
        self.assertEqual((w5, w1, legacy), (1_000_000, 500_000, False))

    def test_advisor_iteration_is_priced_at_its_own_model_and_added(self):
        iterations = [
            {"type": "message", "input_tokens": 0, "output_tokens": 0},
            {"type": "advisor_message", "model": "claude-opus-5-5", "input_tokens": M, "output_tokens": 100_000,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        ]
        call = tok.CallParts({"message": {"model": "claude-sonnet-5-5", "usage": usage(inp=M, iterations=iterations)}})
        self.assertEqual(call.advisor_calls, 1)
        self.assertAlmostEqual(call.usd["advisor"], 4.0 + 100_000 * 20 / M)   # Opus 5.5 rates, not Sonnet's
        self.assertAlmostEqual(call.usd["input"], 2.0)
        self.assertAlmostEqual(call.total, 2.0 + 6.0)

    def test_advisor_on_an_unknown_model_is_listed_not_guessed(self):
        iterations = [{"type": "advisor_message", "model": "claude-mystery-9", "input_tokens": 50, "output_tokens": 5}]
        call = tok.CallParts({"message": {"model": "claude-sonnet-5-5", "usage": usage(iterations=iterations)}})
        self.assertEqual(call.usd["advisor"], 0.0)
        self.assertEqual(call.unpriced["claude-mystery-9"], 55)

    def test_dedup_keeps_only_the_last_line_per_message_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-x.jsonl"
            write_lines(path, [
                assistant("m1", "claude-sonnet-5-5", 5, usage(out=1)),
                assistant("m1", "claude-sonnet-5-5", 5, usage(out=2)),
                assistant("m1", "claude-sonnet-5-5", 5, usage(out=99)),
                assistant("m2", "claude-sonnet-5-5", 4, usage(out=7)),
            ])
            calls, raw = tok.dedup_assistant_lines(path)
        self.assertEqual(raw, 4)
        self.assertEqual([c["message"]["usage"]["output_tokens"] for c in calls], [99, 7])


class Cli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def main_session(self, records):
        write_lines(self.root / "projA" / "sessA.jsonl", records)


class Overview(Cli):
    def test_old_invocation_still_works_and_matches_the_explicit_subcommand(self):
        self.main_session([assistant("m1", "claude-opus-5-5", 5, usage(inp=M))])
        plain = self.run_cli("--days", "7", "--projects-dir", str(self.root))
        explicit = self.run_cli("overview", "--days", "7", "--projects-dir", str(self.root))
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(plain.stdout, explicit.stdout)
        self.assertIn("table dated " + tok.PRICES_AS_OF, plain.stdout)

    def test_prices_a_known_main_call(self):
        self.main_session([assistant("m1", "claude-opus-5-5", 5, usage(inp=M, w1=M))])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn(f"cost ${cost_of('claude-opus-5-5', inp=M, w1=M):,.2f}", out)
        self.assertIn("100% of 1,000,000 cache-write tokens were 1-hour writes", out)

    def test_advisor_cost_is_reported_separately(self):
        iterations = [{"type": "advisor_message", "model": "claude-opus-5-5", "input_tokens": M, "output_tokens": 0}]
        self.main_session([assistant("m1", "claude-sonnet-5-5", 5, usage(inp=0, iterations=iterations))])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("advisor iterations: $4.00 over 1 advisor calls", out)

    def test_unpriced_and_synthetic_lines_show_up_in_the_notes(self):
        self.main_session([
            assistant("m1", "claude-opus-4-8", 5, usage(inp=10)),
            assistant("m2", "<synthetic>", 5, usage()),
        ])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("unpriced model claude-opus-4-8", out)
        self.assertIn("1 synthetic zero-token line(s) skipped", out)
        self.assertIn("Main session: 1 calls", out)

    def test_missing_projects_dir_fails_cleanly(self):
        proc = self.run_cli("--projects-dir", str(self.root / "nope"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("No such projects dir", proc.stderr)


class Anatomy(Cli):
    GENERIC, TYPED = "workflow-subagent", "agenting:researcher"

    def agent(self, wf, aid, agent_type, calls, attachments=(), start=30):
        """calls: list of (model, usage, minutes_after_start)."""
        path = self.root / "projSECRET" / "sessSECRET" / "subagents" / "workflows" / wf / f"agent-{aid}.jsonl"
        records = [{"type": "attachment", "attachment": {"type": t, "content": "contentSECRET " * (n // 14)}}
                   for t, n in attachments]
        for i, (model, u, _) in enumerate(calls):
            records.append(assistant(f"{aid}-m{i}", model, start - i, u, agent_id=aid))
        write_lines(path, records)
        path.with_name(f"agent-{aid}.meta.json").write_text(json.dumps({"agentType": agent_type}), encoding="utf-8")

    def journal(self, wf, agents, returned):
        recs = [{"type": "launched"}]
        for aid in agents:
            recs.append({"type": "started", "agentId": aid, "key": f"key-{aid}", "label": f"labelSECRET-{aid}"})
        for aid in returned:
            recs.append({"type": "result", "agentId": aid, "key": f"key-{aid}"})
        write_lines(self.root / "projSECRET" / "sessSECRET" / "subagents" / "workflows" / wf / "journal.jsonl", recs)

    def build(self):
        S = "claude-sonnet-5-5"
        wf = "wf_synth"
        # three generic agents: one cold start, two warm
        self.agent(wf, "g1", self.GENERIC, [(S, usage(inp=2, w1=40_000), 0), (S, usage(inp=2, read=40_000, out=500), 1)],
                   attachments=[("skill_listing", 14_000), ("instructions", 28_000)], start=40)
        for aid, start in (("g2", 38), ("g3", 36)):
            self.agent(wf, aid, self.GENERIC, [(S, usage(inp=2, read=17_000, w1=13_000), 0),
                                              (S, usage(inp=2, read=30_000, out=1_000), 1)],
                       attachments=[("skill_listing", 14_000), ("instructions", 28_000)], start=start)
        # three typed agents without a skill listing
        for aid, start in (("t1", 34), ("t2", 32), ("t3", 30)):
            self.agent(wf, aid, self.TYPED, [(S, usage(inp=2, read=3_000, w1=9_000, out=300), 0)],
                       attachments=[("instructions", 28_000)], start=start)
        # one lone agent on another model: its group must be suppressed
        self.agent(wf, "o1", self.GENERIC, [("claude-opus-5-5", usage(inp=2, w1=20_000), 0)],
                   attachments=[("skill_listing", 14_000)], start=20)
        self.journal(wf, ["g1", "g2", "g3", "t1", "t2", "t3", "o1"], ["g1", "g2", "g3", "t1", "t2", "o1"])

    def report(self, *extra):
        self.build()
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json", *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout), proc.stdout

    def group(self, rep, kind, skill):
        found = [g for g in rep["groups"] if g["kind"] == kind and g["skill_listing_attached"] == skill]
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_first_call_numbers_and_cost_match_a_hand_computation(self):
        rep, _ = self.report()
        S = "claude-sonnet-5-5"
        g = self.group(rep, "generic", "yes")
        self.assertEqual(g["n"], 3)
        self.assertEqual(g["first_context_median"], 30_002)        # g2/g3: 2 + 17,000 + 13,000
        self.assertEqual(g["first_context_p90"], 40_002)           # g1 cold: 2 + 40,000
        self.assertEqual(g["first_fresh_write_median"], 13_000)
        self.assertEqual(g["first_cache_read_median"], 17_000)
        warm = cost_of(S, inp=2, read=17_000, w1=13_000) + cost_of(S, inp=2, read=30_000, out=1_000)
        self.assertAlmostEqual(g["cost_median"], round(warm, 4), places=4)
        self.assertEqual(g["write_1h_share"], 1.0)
        t = self.group(rep, "typed", "no")
        self.assertEqual((t["n"], t["first_context_median"], t["first_fresh_write_median"]), (3, 12_002, 9_000))

    def test_small_groups_are_suppressed_and_counted(self):
        rep, _ = self.report()
        self.assertEqual(rep["suppressed"], {"groups": 1, "agents": 1})
        self.assertFalse(any(g["model"] == "claude-opus-5-5" for g in rep["groups"]))
        rep_all, _ = self.report("--min-agents", "1")
        self.assertEqual(rep_all["suppressed"], {"groups": 0, "agents": 0})

    def test_missing_fields_print_n_a_not_zero(self):
        rep, _ = self.report()
        g = self.group(rep, "generic", "yes")
        self.assertEqual(g["thinking_tokens_median"], "n/a")
        self.assertEqual(rep["coverage"], {"iterations_pct_of_calls": 0, "thinking_pct_of_calls": 0})
        text = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("FLOORS", text)
        self.assertIn("thinking tokens median n/a", text)

    def test_start_rank_and_attachment_sizes(self):
        rep, _ = self.report()
        # start order is by first call: g1, g2, g3, t1, t2, t3, o1 -> ranks 0..6
        ranks = {(r["kind"], r["start_rank"]): r for r in rep["start_rank"]}
        self.assertNotIn(("generic", "0"), ranks)                    # one agent in the bucket: below --min-agents
        self.assertEqual(ranks[("typed", "3+")]["n"], 3)             # t1..t3 started 4th to 6th
        self.assertEqual(ranks[("typed", "3+")]["first_fresh_write_median"], 9_000)
        atts = {(a["kind"], a["attachment_type"]): a for a in rep["attachments_before_first_call"]}
        self.assertEqual(atts[("generic", "skill_listing")]["agents"], 4)
        self.assertNotIn(("typed", "skill_listing"), atts)
        self.assertIn(("typed", "instructions"), atts)

    def test_journal_counts_come_from_the_finish_check_logic(self):
        rep, _ = self.report()
        self.assertEqual(rep["journal"], {"agents_started": 7, "agents_returned": 6})
        self.assertEqual(rep["workflows"], 1)

    def test_journal_logic_agrees_with_the_hook_on_the_trimmed_real_fixtures(self):
        check = tok.load_check_journal()
        self.assertIsNotNone(check)
        self.assertEqual(check(str(FIXTURES / "journal_retried.jsonl"))[:2], (18, 18))
        self.assertEqual(check(str(FIXTURES / "journal_incomplete.jsonl"))[:2], (13, 18))

    def test_json_output_carries_no_ids_paths_labels_or_content(self):
        rep, raw = self.report()
        for secret in ("projSECRET", "sessSECRET", "labelSECRET", "contentSECRET", "key-g1",
                       '"g1"', str(self.root), "/Users/", "agenting:researcher"):
            self.assertNotIn(secret, raw)
        forbidden = {"prompt", "text", "content", "label", "path", "agentId", "session", "cwd", "input", "key"}

        def keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield k
                    yield from keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from keys(v)

        self.assertEqual(forbidden & set(keys(rep)), set())

    def test_by_type_is_opt_in_and_local(self):
        rep, raw = self.report("--by-type")
        self.assertIn("agenting:researcher", raw)
        self.assertTrue(any(g.get("agent_type") == "agenting:researcher" for g in rep["groups"]))

    def test_out_file_is_written_whole_and_stdout_stays_empty(self):
        self.build()
        out = self.root / "report.json"
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json",
                            "--out", str(out))
        self.assertEqual(proc.stdout, "")
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["prices_as_of"], tok.PRICES_AS_OF)
        self.assertEqual([p.name for p in self.root.glob("report.json.*")], [])   # no temp file left behind

    def test_an_old_agent_inside_a_fresh_workflow_is_left_out(self):
        self.build()
        # the workflow folder is fresh (files were just written), but this agent's first call is 30 days old
        self.agent("wf_synth", "old1", self.GENERIC, [("claude-sonnet-5-5", usage(inp=2, w1=1_000), 0)],
                   start=30 * 24 * 60)
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json")
        rep = json.loads(proc.stdout)
        self.assertEqual(rep["agents"]["analysed"], 7)   # the seven built agents, not the old one

    def test_a_workflow_whose_files_are_all_older_than_the_window_is_skipped(self):
        self.build()
        old = datetime.now(timezone.utc).timestamp() - 60 * 24 * 3600
        for path in self.root.rglob("*"):
            if path.is_file():
                os.utime(path, (old, old))
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json")
        rep = json.loads(proc.stdout)
        self.assertEqual(rep["agents"]["analysed"], 0)
        self.assertEqual(rep["groups"], [])


if __name__ == "__main__":
    unittest.main()


class Percentile(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(tok.pctl([7], 0.9), 7)
        self.assertEqual(tok.pctl([1, 2, 3, 4, 5], 0.9), 5)          # ceil(4.5) = 5; round() would pick 4
        self.assertEqual(tok.pctl(list(range(1, 11)), 0.9), 9)
        self.assertEqual(tok.pctl(list(range(1, 26)), 0.9), 23)      # ceil(22.5) = 23; round() would pick 22
        self.assertEqual(tok.pctl([5, 1, 4, 2, 3], 0.9), 5)          # unsorted input


class PinnedPriceRows(unittest.TestCase):
    def test_the_documented_columns_of_the_older_rows(self):
        # documented: Sonnet 5 is $2/$10; Fable 5 reads cost $1.00; Opus 5 is $5/$25 with $0.50 reads
        sonnet5, fable5, opus5 = (tok.price_for(m) for m in ("claude-sonnet-5", "claude-fable-5", "claude-opus-5"))
        self.assertEqual((sonnet5.input, sonnet5.output), (2, 10))
        self.assertEqual((fable5.input, fable5.output, fable5.read), (10, 50, 1.00))
        self.assertEqual((opus5.input, opus5.output, opus5.read), (5, 25, 0.50))
        self.assertTrue(all(r.derived for r in (sonnet5, fable5, opus5)))
        self.assertFalse(tok.price_for("claude-opus-5-5").derived)


class Hardening(Cli):
    """Odd records must cost a line, never a file or a run, and never produce negative dollars."""

    def test_one_odd_line_does_not_discard_the_file(self):
        path = self.root / "agent-x.jsonl"
        write_lines(path, [assistant("m1", "claude-opus-5-5", 5, usage(inp=M))])
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": None}) + "\n")
            f.write(json.dumps([1, 2, 3]) + "\n")
            f.write(json.dumps({"type": "assistant", "message": "text"}) + "\n")
            f.write("{not json\n")
        calls, _ = tok.dedup_assistant_lines(path)
        self.assertEqual(len(calls), 1)

    def test_malformed_usage_fields_are_zero_not_a_crash(self):
        cases = [
            {"input_tokens": "5", "output_tokens": None, "cache_read_input_tokens": [1]},
            "usage as a string",
            {"input_tokens": 1, "iterations": 5},
            {"cache_creation": {"ephemeral_5m_input_tokens": None, "ephemeral_1h_input_tokens": "3"}},
        ]
        for u in cases:
            with self.subTest(usage=u):
                call = tok.CallParts({"message": {"model": "claude-opus-5-5", "usage": u}})
                self.assertGreaterEqual(call.total, 0.0)

    def test_negative_token_counts_are_clamped(self):
        usd, tokens, _, _ = tok.usage_parts({"input_tokens": -M, "output_tokens": -5}, "claude-opus-5-5")
        self.assertEqual((usd["input"], usd["output"], tokens["input"]), (0.0, 0.0, 0))

    def test_naive_timestamps_are_treated_as_utc(self):
        parsed = tok.parse_ts("2026-10-06T10:00:00")
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_the_cli_survives_odd_records_and_still_counts_the_good_ones(self):
        good = assistant("m1", "claude-opus-5-5", 5, usage(inp=M))
        odd = assistant("m2", "claude-opus-5-5", 5, "usage as a string")
        odd["effort"] = ["x"]
        odd["agentId"] = ["unhashable"]
        write_lines(self.root / "projA" / "sessA.jsonl", [good, odd])
        write_lines(self.root / "projA" / "sessA" / "subagents" / "agent-z.jsonl", [odd, good])
        for args in (["--days", "7"], ["anatomy", "--days", "7"]):
            with self.subTest(args=args):
                proc = self.run_cli(*args, "--projects-dir", str(self.root))
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_dangling_symlink_named_like_a_transcript_does_not_crash(self):
        wf = self.root / "projA" / "sessA" / "subagents" / "workflows" / "wf_x"
        wf.mkdir(parents=True)
        write_lines(wf / "agent-ok.jsonl", [assistant("m1", "claude-opus-5-5", 5, usage(inp=M))])
        os.symlink(self.root / "nowhere.jsonl", wf / "agent-dead.jsonl")
        for args in (["--days", "7"], ["anatomy", "--days", "7"]):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args, "--projects-dir", str(self.root)).returncode, 0)

    def test_a_suffixed_derived_model_still_prints_its_note(self):
        footer = tok.Footer()
        footer.add([tok.CallParts({"message": {"model": "claude-sonnet-5[1m]", "usage": usage(inp=1)}})])
        self.assertTrue(any("claude-sonnet-5 is partly derived: input and output documented" in l for l in footer.lines()))

    def test_flag_values_are_validated(self):
        for args in (["--days", "0"], ["--days", "-3"], ["anatomy", "--min-agents", "0"], ["anatomy", "--days", "0"]):
            with self.subTest(args=args):
                proc = self.run_cli(*args, "--projects-dir", str(self.root))
                self.assertEqual(proc.returncode, 2)
                self.assertIn("must be 1 or more", proc.stderr)

    def test_an_unwritable_out_path_is_a_message_not_a_traceback(self):
        (self.root / "afile").write_text("x", encoding="utf-8")
        proc = self.run_cli("anatomy", "--projects-dir", str(self.root), "--out", str(self.root / "afile" / "r.json"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot write", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class OverviewBehaviour(Cli):
    def agent_file(self, name, records):
        write_lines(self.root / "projA" / "sessA" / "subagents" / name, records)

    def test_spawn_tax_uses_the_first_call_and_prices_only_the_write(self):
        self.agent_file("agent-a.jsonl", [
            assistant("m1", "claude-opus-5-5", 60, usage(w1=M, out=100_000), agent_id="a"),
            assistant("m2", "claude-opus-5-5", 50, usage(w1=2 * M), agent_id="a"),
        ])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        # first call: 1,000,000 tokens written at the Opus 5.5 1h rate ($8/MTok); output and later calls excluded
        self.assertIn("Spawn tax: median first-call cache-write 1,000,000 tokens (~$8.000/spawn at the write rates)", out)

    def test_old_and_sidechain_lines_and_stale_files_are_not_counted(self):
        write_lines(self.root / "projA" / "fresh.jsonl", [
            assistant("m1", "claude-opus-5-5", 5, usage(inp=M)),                          # counted
            assistant("m2", "claude-opus-5-5", 60 * 24 * 30, usage(inp=M)),               # 30 days old line
            assistant("m3", "claude-opus-5-5", 5, usage(inp=M), sidechain=True),          # sidechain: belongs to an agent
        ])
        stale = self.root / "projB" / "stale.jsonl"
        write_lines(stale, [assistant("m4", "claude-opus-5-5", 5, usage(inp=M))])
        long_ago = datetime.now(timezone.utc).timestamp() - 40 * 24 * 3600
        os.utime(stale, (long_ago, long_ago))
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("Main session: 1 calls", out)
        self.assertIn("Scanned 1 main session files", out)

    def test_default_window_is_21_days(self):
        write_lines(self.root / "projA" / "s.jsonl", [assistant("m1", "claude-opus-5-5", 60 * 24 * 10, usage(inp=M))])
        self.assertIn("Main session: 1 calls", self.run_cli("--projects-dir", str(self.root)).stdout)
        self.assertIn("Main session: 0 calls", self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout)

    def test_synthetic_lines_in_agent_files_are_skipped_and_do_not_inflate_the_dedup_factor(self):
        self.agent_file("agent-a.jsonl", [
            assistant("m1", "claude-opus-5-5", 5, usage(inp=M), agent_id="a"),
            assistant("m2", "<synthetic>", 5, usage(), agent_id="a"),
        ])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("Agents: 1 calls (raw 1, dedup 1.00x)", out)
        self.assertIn("1 synthetic zero-token line(s) skipped", out)

    def test_synthetic_lines_in_the_main_session_do_not_inflate_its_dedup_factor_either(self):
        write_lines(self.root / "projA" / "s.jsonl", [
            assistant("m1", "claude-opus-5-5", 5, usage(inp=M)),
            assistant("m2", "<synthetic>", 5, usage()),
        ])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("Main session: 1 calls (raw 1, dedup 1.00x)", out)

    def test_effort_distribution_splits_at_the_cutoff(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.agent_file("agent-a.jsonl", [
            assistant("m1", "claude-opus-5-5", 60 * 24 * 2, usage(inp=1), effort="high", agent_id="a"),
            assistant("m2", "claude-opus-5-5", 60, usage(inp=1), effort="xhigh", agent_id="a"),
        ])
        out = self.run_cli("--days", "7", "--effort-cutoff", cutoff, "--projects-dir", str(self.root)).stdout
        self.assertRegex(out, r"before .*: high=100%")
        self.assertRegex(out, r"after: +xhigh=100%")

    def test_dedup_factor_counts_streamed_duplicates(self):
        self.agent_file("agent-a.jsonl", [assistant("m1", "claude-opus-5-5", 5, usage(out=n), agent_id="a") for n in (1, 2, 3)])
        out = self.run_cli("--days", "7", "--projects-dir", str(self.root)).stdout
        self.assertIn("Agents: 1 calls (raw 3, dedup 3.00x)", out)


class AnatomyStatistics(Cli):
    """Five agents in one group, built so that every statistic has a distinguishable expected value."""

    S, OPUS = "claude-sonnet-5-5", "claude-opus-5-5"

    def build(self):
        wf = self.root / "projP" / "sessP" / "subagents" / "workflows" / "wf_stats"
        self.expected = []
        # a5 starts first and a1 last, so start order is the reverse of the file names' alphabetical order
        for i in range(1, 6):
            start = 10 * i                            # a1: 10 minutes ago ... a5: 50 minutes ago
            skill = {"type": "skill_listing", "content": "x" * 7000}
            late_skill = {"type": "skill_listing", "content": "y" * 50_000}
            records = [{"type": "attachment", "attachment": skill}, {"type": "attachment", "attachment": skill}]
            first = usage(inp=2, read=1_000 * i, w1=10_000 * i, thinking=100 * i)
            records.append(assistant(f"a{i}-0", self.S, start, first, agent_id=f"a{i}"))
            records.append({"type": "attachment", "attachment": late_skill})   # after the first call: not part of the start-up
            cost = cost_of(self.S, inp=2, read=1_000 * i, w1=10_000 * i)
            for k in range(1, i):
                iterations = None
                if i >= 3 and k == 1:                  # agents 3, 4, 5 each get one advisor call on their second call
                    advisor_in = 100_000 * (i - 2)
                    iterations = [{"type": "advisor_message", "model": self.OPUS, "input_tokens": advisor_in, "output_tokens": 0}]
                    cost += cost_of(self.OPUS, inp=advisor_in)
                u = usage(inp=2, read=50_000, out=1_000 * i, iterations=iterations)
                records.append(assistant(f"a{i}-{k}", self.S, start - k, u, agent_id=f"a{i}"))
                cost += cost_of(self.S, inp=2, read=50_000, out=1_000 * i)
            write_lines(wf / f"agent-a{i}.jsonl", records)
            (wf / f"agent-a{i}.meta.json").write_text(json.dumps({"agentType": "workflow-subagent"}), encoding="utf-8")
            self.expected.append({
                "i": i, "ctx": 2 + 1_000 * i + 10_000 * i, "fresh": 10_000 * i, "read": 1_000 * i,
                "cost": cost, "calls": i, "advisor": cost_of(self.OPUS, inp=100_000 * (i - 2)) if i >= 3 else 0.0,
                "thinking": 100 * i,
            })
        write_lines(wf / "journal.jsonl", [{"type": "launched"}])

    def report(self, *extra):
        self.build()
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json", *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_every_statistic_matches_a_hand_computation(self):
        rep = self.report("--min-agents", "5")
        self.assertEqual(rep["agents"], {"analysed": 5, "generic": 5, "typed": 0, "calls": 15})
        (g,) = rep["groups"]
        e = self.expected
        ctxs = sorted(x["ctx"] for x in e)
        costs = sorted(x["cost"] for x in e)
        self.assertEqual(g["n"], 5)
        self.assertEqual(g["first_context_median"], ctxs[2])
        self.assertEqual(g["first_context_p90"], ctxs[4])              # nearest rank: the 5th of 5, not the 4th
        self.assertEqual(g["first_fresh_write_median"], 30_000)
        self.assertEqual(g["first_cache_read_median"], 3_000)
        shares = sorted(x["fresh"] / x["ctx"] for x in e)
        self.assertAlmostEqual(g["first_fresh_share_median"], round(shares[2], 3), places=3)
        self.assertEqual(g["calls_median"], 3)
        self.assertAlmostEqual(g["cost_median"], round(costs[2], 4), places=4)
        self.assertAlmostEqual(g["cost_p90"], round(costs[4], 4), places=4)
        self.assertAlmostEqual(g["cost_min"], round(costs[0], 4), places=4)
        self.assertAlmostEqual(g["cost_max"], round(costs[4], 4), places=4)
        self.assertAlmostEqual(g["advisor_cost_median"], round(sorted(x["advisor"] for x in e)[2], 4), places=4)
        self.assertGreater(g["advisor_cost_median"], 0)
        self.assertEqual(g["thinking_tokens_median"], 300)
        self.assertEqual(g["thinking_agents"], 5)
        self.assertEqual(g["write_1h_share"], 1.0)

    def test_coverage_counts_calls_that_carry_the_fields(self):
        rep = self.report("--min-agents", "5")
        # 3 of 15 calls carry usage.iterations; 5 of 15 carry thinking tokens
        self.assertEqual(rep["coverage"], {"iterations_pct_of_calls": 20, "thinking_pct_of_calls": 33})

    def test_start_order_decides_the_rank_not_the_file_name(self):
        rep = self.report("--min-agents", "1")
        ranks = {r["start_rank"]: r for r in rep["start_rank"] if r["kind"] == "generic"}
        self.assertEqual(ranks["0"]["first_fresh_write_median"], 50_000)      # a5 started first
        self.assertEqual(ranks["1-2"]["n"], 2)
        self.assertEqual(ranks["1-2"]["first_fresh_write_median"], 35_000)    # a4 and a3: median of 40,000 and 30,000
        self.assertEqual(ranks["3+"]["first_fresh_write_median"], 15_000)     # a2 and a1: 20,000 and 10,000

    def test_attachments_are_summed_per_type_and_only_those_before_the_first_call_count(self):
        rep = self.report("--min-agents", "5")
        (att,) = [a for a in rep["attachments_before_first_call"] if a["attachment_type"] == "skill_listing"]
        self.assertEqual(att["agents"], 5)
        self.assertTrue(14_000 <= att["chars_median"] <= 14_200, att)         # two of ~7,040 characters, not one, not 50,000 more

    def test_an_agent_whose_first_call_is_old_is_left_out_even_if_its_last_call_is_recent(self):
        self.build()
        wf = self.root / "projP" / "sessP" / "subagents" / "workflows" / "wf_stats"
        write_lines(wf / "agent-late.jsonl", [
            assistant("late-0", self.S, 60 * 24 * 30, usage(inp=2, w1=1_000), agent_id="late"),
            assistant("late-1", self.S, 1, usage(inp=2, read=1_000), agent_id="late"),
        ])
        proc = self.run_cli("anatomy", "--days", "7", "--projects-dir", str(self.root), "--format", "json", "--min-agents", "5")
        self.assertEqual(json.loads(proc.stdout)["agents"]["analysed"], 5)
