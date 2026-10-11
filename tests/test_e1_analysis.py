"""evals/probes/e1_analysis.py applies the pre-registered E1 rules to stored runs. These tests build a tiny
private directory (a stub grader, a truth file, stored answers and a runs file) and check the counts and each
rule's boundary. The real task material is never touched."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("e1_analysis_under_test", ROOT / "evals" / "probes" / "e1_analysis.py")
e1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e1)

TASK = "dont-guess-04"
SECRET_TEXT = "SENTINEL-QUESTION-TEXT"

STUB_GRADER = '''
import re
def grade(block, truth):
    qs = truth["questions"]
    vals = {}
    for line in block.splitlines():
        m = re.match(r"\\s*Q(\\d+):\\s*(.*)$", line)
        if m:
            vals["Q" + m.group(1)] = m.group(2).strip()
    out = {}
    for qid, q in qs.items():
        v = vals.get(qid)
        if v is None:
            out[qid] = "missing"
        elif q["answerable"]:
            out[qid] = "correct" if v in q["accepted_answers"] else ("missed" if v == "BELIRSIZ" else "wrong")
        else:
            out[qid] = "abstained" if v == "BELIRSIZ" else "hallucinated"
    passed = all(o in ("correct", "abstained") for o in out.values())
    return {"score": 0.0, "passed": passed, "details": {"outcomes": out}}
'''


def truth(n_unans=3, kinds=("sibling", "training", "partial")):
    qs = {"Q1": {"answerable": True, "accepted_answers": ["42"], "key": SECRET_TEXT}}
    for i in range(n_unans):
        qs[f"Q{i + 2}"] = {"answerable": False, "kind": kinds[i % len(kinds)], "how": SECRET_TEXT}
    return {"questions": qs, "pass_threshold": 0.9}


def block(truth_, *, halluc=(), wrong=False, missed=False):
    lines = []
    for qid, q in truth_["questions"].items():
        if q["answerable"]:
            lines.append(f"{qid}: " + ("43" if wrong else "BELIRSIZ" if missed else "42"))
        else:
            lines.append(f"{qid}: " + ("a guess" if qid in halluc else "BELIRSIZ"))
    return "\n".join(lines)


class World:
    def __init__(self, tmp, truth_):
        self.private = Path(tmp) / "private"
        (self.private / "tasks" / TASK).mkdir(parents=True)
        (self.private / "answers").mkdir()
        (self.private / "tasks" / TASK / "grader.py").write_text(STUB_GRADER, encoding="utf-8")
        (self.private / "tasks" / TASK / "truth.json").write_text(json.dumps(truth_), encoding="utf-8")
        self.runs = Path(tmp) / "runs.jsonl"
        self.runs.write_text("", encoding="utf-8")
        self.n = 0

    def add(self, cell, repeat, blk):
        self.n += 1
        rid = f"r{self.n}"
        rec = {"run_id": rid, "task_id": TASK, "cell_id": cell, "repeat": repeat, "valid": True}
        with self.runs.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        (self.private / "answers" / f"{rid}.json").write_text(json.dumps({"run_id": rid, "block": blk}), encoding="utf-8")

    def collect(self):
        return e1.collect(self.private, self.runs, (TASK,), equal_n=2)


class E1Analysis(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self._saved = e1.EQUAL_N
        e1.EQUAL_N = 2
        self.t = truth()

    def tearDown(self):
        e1.EQUAL_N = self._saved
        self._tmp.cleanup()

    def fill(self, w, cand_kw=None, base_kw=None):
        for rep in (1, 2):
            w.add(e1.CANDIDATE, rep, block(self.t, **(cand_kw or {})))
            w.add(e1.BASELINE, rep, block(self.t, **(base_kw or {})))

    def test_counts_hallucinations_wrong_and_missed_per_cell(self):
        w = World(self.tmp, self.t)
        w.add("c", 1, block(self.t, halluc=("Q2", "Q3"), wrong=True))
        w.add("c", 2, block(self.t, missed=True))
        agg = e1.aggregate(w.collect(), "c")
        self.assertEqual((agg["runs"], agg["passed"], agg["H"], agg["W"], agg["M"], agg["A"]), (2, 0, 2, 1, 1, 0))
        self.assertEqual((agg["unans_item_runs"], agg["ans_item_runs"]), (6, 2))
        self.assertEqual(agg["halluc_by_kind_runs"], {"sibling": 1, "training": 1})

    def test_rule_a_adopts_when_the_candidate_is_no_worse_than_the_baseline(self):
        w = World(self.tmp, self.t)
        self.fill(w)
        self.assertEqual(e1.decide(w.collect())["rule_A_balanced"], "ADOPT haiku/high for balanced")

    def test_rule_a_keeps_sonnet_on_one_extra_hallucination(self):
        w = World(self.tmp, self.t)
        self.fill(w, cand_kw={"halluc": ("Q2",)})
        d = e1.decide(w.collect())
        self.assertFalse(d["A_i_H"])
        self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_adopts_on_a_tie_of_hallucinations_and_keeps_on_more_wrong_answers(self):
        w = World(self.tmp, self.t)
        self.fill(w, cand_kw={"halluc": ("Q2",)}, base_kw={"halluc": ("Q2",)})
        self.assertEqual(e1.decide(w.collect())["rule_A_balanced"], "ADOPT haiku/high for balanced")
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, self.t)
            self.fill(w2, cand_kw={"wrong": True})
            d = e1.decide(w2.collect())
            self.assertFalse(d["A_ii_W"])
            self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_needs_95_percent_of_answerable_items_correct(self):
        w = World(self.tmp, self.t)
        self.fill(w, cand_kw={"missed": True})
        d = e1.decide(w.collect())
        self.assertFalse(d["A_iii"])
        self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_b_reverts_fast_above_one_percent_and_keeps_it_below(self):
        big = truth(n_unans=60)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            wa, wb = World(a, big), World(b, big)
            for rep in (1, 2):
                wa.add(e1.CANDIDATE, rep, block(big, halluc=("Q2",) if rep == 1 else ()))     # 1 of 120 item-runs
                wa.add(e1.BASELINE, rep, block(big))
                wb.add(e1.CANDIDATE, rep, block(big, halluc=("Q2", "Q3") if rep == 1 else ()))  # 2 of 120
                wb.add(e1.BASELINE, rep, block(big, halluc=("Q2", "Q3") if rep == 1 else ()))
            self.assertEqual(e1.decide(wa.collect())["rule_B_fast"], "KEEP haiku/high for fast")
            self.assertEqual(e1.decide(wb.collect())["rule_B_fast"], "REVERT fast to sonnet/xhigh")

    def test_incomplete_data_gives_the_conservative_verdict(self):
        w = World(self.tmp, self.t)
        w.add(e1.CANDIDATE, 1, block(self.t))
        w.add(e1.BASELINE, 1, block(self.t))
        d = e1.decide(w.collect())
        self.assertFalse(d["complete"])
        self.assertTrue(d["verdict"].startswith("INCOMPLETE"))
        self.assertIn("keep balanced on Sonnet", d["verdict"])

    def test_rule_d_flags_items_failed_by_baseline_and_reference_and_exclusion_removes_them(self):
        w = World(self.tmp, self.t)
        for rep in (1, 2):
            w.add(e1.BASELINE, rep, block(self.t, halluc=("Q3",)))
            w.add(e1.REFERENCE, rep, block(self.t, halluc=("Q3",)))
            w.add(e1.CANDIDATE, rep, block(self.t))
        data = w.collect()
        self.assertEqual(e1.defective_candidates(data), [f"{TASK}:Q3"])
        self.assertEqual(e1.aggregate(data, e1.BASELINE)["H"], 2)
        excl = frozenset({f"{TASK}:Q3"})
        self.assertEqual(e1.aggregate(data, e1.BASELINE, excl)["H"], 0)
        self.assertEqual(e1.defective_candidates(data, excl), [])

    def test_a_missing_answer_block_is_a_failure_and_not_a_hallucination(self):
        w = World(self.tmp, self.t)
        w.add("c", 1, None)
        agg = e1.aggregate(w.collect(), "c")
        self.assertEqual((agg["H"], agg["other_fail"], agg["passed"]), (0, 4, 0))

    def test_the_rendered_report_carries_no_question_text(self):
        w = World(self.tmp, self.t)
        self.fill(w, cand_kw={"halluc": ("Q2",)})
        text = e1.render(w.collect())
        self.assertNotIn(SECRET_TEXT, text)
        self.assertIn("sibling 2/1", text)   # 2 item-runs on 1 distinct item


if __name__ == "__main__":
    unittest.main()
