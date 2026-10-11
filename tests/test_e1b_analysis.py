"""evals/probes/e1b_analysis.py applies the pre-registered E1b rules to stored runs. These tests build a tiny
private directory (a stub grader, truth files, stored answers and a runs file) and check the counts and the
boundary of every rule condition. The real task material is never touched."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("e1b_analysis_under_test", ROOT / "evals" / "probes" / "e1b_analysis.py")
e1b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e1b)

TASK = "dont-guess-08"
OTHER = "dont-guess-09"
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

KINDS = ("intent", "partial", "sibling", "absent")
DECISION = ("opus-5-5@xhigh", "sonnet-5-5@xhigh", "haiku-5-5@xhigh")
REFERENCE = "haiku-5-5@high"


def truth(n_unans=30, n_ans=1):
    """Q1..Q{n_ans} answerable; the unanswerable ones follow, kinds cycling intent, partial, sibling, absent."""
    qs = {f"Q{i + 1}": {"answerable": True, "accepted_answers": ["42"], "key": SECRET_TEXT} for i in range(n_ans)}
    for i in range(n_unans):
        qs[f"Q{n_ans + i + 1}"] = {"answerable": False, "kind": KINDS[i % len(KINDS)], "how": SECRET_TEXT}
    return {"questions": qs, "pass_threshold": 0.9}


def block(truth_, *, halluc=(), wrong=(), missed=()):
    """wrong and missed: True for every answerable question, or a tuple of question ids."""
    lines = []
    for qid, q in truth_["questions"].items():
        if q["answerable"]:
            is_wrong = wrong is True or qid in wrong
            is_missed = missed is True or qid in missed
            lines.append(f"{qid}: " + ("43" if is_wrong else "BELIRSIZ" if is_missed else "42"))
        else:
            lines.append(f"{qid}: " + ("a guess" if qid in halluc else "BELIRSIZ"))
    return "\n".join(lines)


class World:
    def __init__(self, tmp, truth_, tasks=(TASK,)):
        self.private = Path(tmp) / "private"
        (self.private / "answers").mkdir(parents=True)
        for t in tasks:
            (self.private / "tasks" / t).mkdir(parents=True)
            (self.private / "tasks" / t / "grader.py").write_text(STUB_GRADER, encoding="utf-8")
            (self.private / "tasks" / t / "truth.json").write_text(json.dumps(truth_), encoding="utf-8")
        self.tasks = tasks
        self.runs = Path(tmp) / "runs.jsonl"
        self.runs.write_text("", encoding="utf-8")
        self.n = 0

    def add(self, cell, repeat, blk, task=TASK, valid=True):
        self.n += 1
        rid = f"r{self.n}"
        rec = {"run_id": rid, "task_id": task, "cell_id": cell, "repeat": repeat, "valid": valid}
        with self.runs.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        (self.private / "answers" / f"{rid}.json").write_text(json.dumps({"run_id": rid, "block": blk}), encoding="utf-8")

    def collect(self, tasks=None):
        return e1b.collect(self.private, self.runs, tasks or self.tasks)


class E1bAnalysis(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self._saved = (e1b.EQUAL_N, e1b.e1.EQUAL_N, e1b.TASKS)
        e1b.EQUAL_N = 2
        e1b.TASKS = (TASK,)
        self.t = truth()

    def tearDown(self):
        e1b.EQUAL_N, e1b.e1.EQUAL_N, e1b.TASKS = self._saved
        self._tmp.cleanup()

    def world(self, t=None):
        return World(self.tmp, t or self.t)

    def fill(self, w, opus=None, sonnet=None, haiku_x=None, haiku_h=None, t=None, repeats=(1, 2)):
        """Each argument is {repeat: block kwargs}; a missing repeat is a clean run."""
        t = t or self.t
        for cell, spec_ in ((e1b.OPUS, opus), (e1b.SONNET, sonnet), (e1b.HAIKU_XHIGH, haiku_x), (e1b.HAIKU_HIGH, haiku_h)):
            for rep in repeats:
                w.add(cell, rep, block(t, **((spec_ or {}).get(rep) or {})))

    # --- the cells and counts -------------------------------------------------------------------------------
    def test_the_decision_cells_are_the_ones_the_rules_name_and_rule_d_reads_the_same_two(self):
        self.assertEqual((e1b.OPUS, e1b.SONNET, e1b.HAIKU_XHIGH, e1b.HAIKU_HIGH),
                         ("opus-5-5@xhigh", "sonnet-5-5@xhigh", "haiku-5-5@xhigh", "haiku-5-5@high"))
        self.assertEqual((e1b.e1.BASELINE, e1b.e1.REFERENCE), (e1b.SONNET, e1b.OPUS))
        self.assertEqual(set(e1b.DECISION_CELLS), set(DECISION))
        self.assertEqual(set(e1b.CELLS), set(DECISION) | {REFERENCE})

    def test_counts_per_cell_and_hallucinations_by_task_and_item_with_kinds(self):
        w = World(self.tmp, self.t, (TASK, OTHER))
        w.add("c", 1, block(self.t, halluc=("Q2", "Q3"), wrong=True), task=TASK)
        w.add("c", 2, block(self.t, missed=True), task=TASK)
        w.add("c", 1, block(self.t, halluc=("Q3",)), task=OTHER)
        data = w.collect()
        agg = e1b.e1.aggregate(data, "c")
        self.assertEqual((agg["runs"], agg["passed"], agg["H"], agg["W"], agg["M"], agg["A"]), (3, 0, 3, 1, 1, 1))
        per = e1b.by_task(data, "c")
        self.assertEqual((per[TASK]["H"], per[OTHER]["H"]), (2, 1))
        self.assertEqual(e1b.hallucinated_items(data, "c"), {f"{TASK}:Q2": 1, f"{TASK}:Q3": 1, f"{OTHER}:Q3": 1})
        row = {r["item"]: r for r in e1b.item_rows(data, ("c",))}
        self.assertEqual((row[f"{TASK}:Q2"]["kind"], row[f"{TASK}:Q3"]["kind"]), ("intent", "partial"))
        self.assertEqual(row[f"{TASK}:Q3"]["cells"]["c"], (1, 2))        # 1 hallucinated run of 2 runs on that item

    def test_invalid_runs_and_repeats_above_equal_n_are_not_counted(self):
        w = self.world()
        w.add("c", 1, block(self.t, halluc=("Q2",)), valid=False)
        w.add("c", 3, block(self.t, halluc=("Q2",)))
        w.add("c", 2, block(self.t))
        self.assertEqual(e1b.e1.aggregate(w.collect(), "c")["runs"], 1)

    # --- Rule A ---------------------------------------------------------------------------------------------
    def test_rule_a_moves_balanced_when_every_condition_holds(self):
        w = self.world()
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}      # sonnet: 4 of 60 item-runs on 2 items
        self.fill(w, sonnet=both)
        d = e1b.decide(w.collect())
        self.assertTrue(d["complete"])
        self.assertEqual([d[k] for k in ("A_i", "A_ii", "A_iii", "A_iv", "A_v")], [True] * 5)
        self.assertEqual(d["rule_A_balanced"], "MOVE balanced to opus/xhigh")

    def test_rule_a_i_needs_sonnet_at_one_percent_or_more_of_the_unanswerable_item_runs(self):
        t50 = truth(50)                                                          # 100 unanswerable item-runs per cell
        w = self.world(t50)
        self.fill(w, t=t50, sonnet={1: {"halluc": ("Q2",)}})                     # 1 of 100: exactly 1%
        self.assertTrue(e1b.decide(w.collect())["A_i"])
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, t50)
            self.fill(w2, t=t50)                                                 # sonnet clean: no measurable problem
            d = e1b.decide(w2.collect())
            self.assertFalse(d["A_i"])
            self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")
        with tempfile.TemporaryDirectory() as other:
            t51 = truth(51)                                                      # 102 item-runs: 1 of 102 is below 1%
            w3 = World(other, t51)
            self.fill(w3, t=t51, sonnet={1: {"halluc": ("Q2",)}})
            self.assertFalse(e1b.decide(w3.collect())["A_i"])

    def test_rule_a_ii_opus_may_have_at_most_a_fifth_of_sonnets_hallucinations(self):
        w = self.world()
        # sonnet 5 (Q2 twice, Q3 twice, Q4 once); opus 1: 5 * 1 <= 5 holds
        sonnet5 = {1: {"halluc": ("Q2", "Q3", "Q4")}, 2: {"halluc": ("Q2", "Q3")}}
        self.fill(w, opus={1: {"halluc": ("Q9",)}}, sonnet=sonnet5)
        self.assertTrue(e1b.decide(w.collect())["A_ii"])
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, self.t)
            sonnet4 = {1: {"halluc": ("Q2", "Q3", "Q4")}, 2: {"halluc": ("Q2",)}}   # sonnet 4: 5 * 1 > 4
            self.fill(w2, opus={1: {"halluc": ("Q9",)}}, sonnet=sonnet4)
            d = e1b.decide(w2.collect())
            self.assertFalse(d["A_ii"])
            self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_iii_opus_may_not_answer_answerable_items_wrongly_more_often_than_sonnet(self):
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        w = self.world()
        self.fill(w, opus={1: {"wrong": True}}, sonnet={**both, 1: {"halluc": ("Q2", "Q3"), "wrong": True}})
        self.assertTrue(e1b.decide(w.collect())["A_iii"])                        # one wrong each: equal is allowed
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, self.t)
            self.fill(w2, opus={1: {"wrong": True}}, sonnet=both)
            d = e1b.decide(w2.collect())
            self.assertFalse(d["A_iii"])
            self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_iv_opus_needs_95_percent_of_the_answerable_item_runs_correct(self):
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        w = self.world()
        self.fill(w, opus={1: {"missed": True}}, sonnet=both)                    # 1 of 2 answerable item-runs correct
        d = e1b.decide(w.collect())
        self.assertFalse(d["A_iv"])
        self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_v_one_item_that_carries_the_result_keeps_balanced_on_sonnet(self):
        w = self.world()
        # sonnet 5 (Q2 twice, Q3 twice, Q4 once), opus 1: (ii) holds, but without Q2 sonnet has 3 and 5 * 1 > 3
        sonnet5 = {1: {"halluc": ("Q2", "Q3", "Q4")}, 2: {"halluc": ("Q2", "Q3")}}
        self.fill(w, opus={1: {"halluc": ("Q9",)}}, sonnet=sonnet5)
        d = e1b.decide(w.collect())
        self.assertTrue(d["A_ii"])
        self.assertFalse(d["A_v"])
        self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")
        self.assertIn(f"{TASK}:Q2", [r["item"] for r in d["leave_one_out"] if not r["holds"]])

    def test_rule_a_v_a_sonnet_problem_that_is_one_item_leaves_nothing_to_measure_and_fails(self):
        w = self.world()
        self.fill(w, sonnet={1: {"halluc": ("Q2",)}, 2: {"halluc": ("Q2",)}})   # sonnet 2 of 60, all on one item
        d = e1b.decide(w.collect())
        self.assertTrue(d["A_i"] and d["A_ii"])
        self.assertTrue(d["leave_one_out"][0]["degenerate"])
        self.assertFalse(d["A_v"])
        self.assertEqual(d["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    # --- Rule B ---------------------------------------------------------------------------------------------
    def test_rule_b_admits_haiku_xhigh_when_every_condition_holds(self):
        t60 = truth(60)                                                          # 120 unanswerable item-runs per cell
        one = {1: {"halluc": ("Q2",)}}
        w = self.world(t60)
        self.fill(w, t=t60, haiku_x=one, sonnet=one)                             # 1 of 120 each: under 1%, tied with sonnet
        d = e1b.decide(w.collect())
        self.assertEqual([d[k] for k in ("B_i", "B_ii", "B_iii", "B_iv")], [True] * 4)
        self.assertEqual(d["rule_B_fast"], "ADMIT haiku/xhigh to fast")
        with tempfile.TemporaryDirectory() as other:                             # the 30-question task: 1 of 60 is 1.7%
            w2 = World(other, self.t)
            self.fill(w2, haiku_x=one, sonnet=one)
            d2 = e1b.decide(w2.collect())
            self.assertFalse(d2["B_ii"])
            self.assertEqual(d2["rule_B_fast"], "KEEP fast on sonnet/xhigh")

    def test_rule_b_i_haiku_xhigh_may_not_hallucinate_more_than_sonnet(self):
        t60 = truth(60)
        w = self.world(t60)
        self.fill(w, t=t60, haiku_x={1: {"halluc": ("Q2",)}})                    # haiku 1, sonnet 0; 1 of 120 is under 1%
        d = e1b.decide(w.collect())
        self.assertTrue(d["B_ii"])
        self.assertFalse(d["B_i"])
        self.assertEqual(d["rule_B_fast"], "KEEP fast on sonnet/xhigh")

    def test_rule_b_ii_haiku_xhigh_may_hallucinate_at_most_one_percent_of_item_runs(self):
        t50 = truth(50)                                                          # 100 unanswerable item-runs per cell
        w = self.world(t50)
        one = {1: {"halluc": ("Q2",)}}
        self.fill(w, t=t50, haiku_x=one, sonnet=one)                             # 1 of 100: exactly 1% is allowed
        self.assertTrue(e1b.decide(w.collect())["B_ii"])
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, t50)
            two = {1: {"halluc": ("Q2", "Q3")}}
            self.fill(w2, t=t50, haiku_x=two, sonnet=two)                        # 2 of 100, tied with sonnet: still over 1%
            d = e1b.decide(w2.collect())
            self.assertTrue(d["B_i"])
            self.assertFalse(d["B_ii"])
            self.assertEqual(d["rule_B_fast"], "KEEP fast on sonnet/xhigh")

    def test_rule_b_iii_and_iv_haiku_xhigh_needs_no_more_wrong_answers_and_95_percent_correct(self):
        t60 = truth(60)
        w = self.world(t60)
        self.fill(w, t=t60, haiku_x={1: {"wrong": True}})
        d = e1b.decide(w.collect())
        self.assertFalse(d["B_iii"])
        self.assertEqual(d["rule_B_fast"], "KEEP fast on sonnet/xhigh")
        with tempfile.TemporaryDirectory() as other:
            w2 = World(other, t60)
            self.fill(w2, t=t60, haiku_x={1: {"missed": True}})
            d2 = e1b.decide(w2.collect())
            self.assertFalse(d2["B_iv"])
            self.assertEqual(d2["rule_B_fast"], "KEEP fast on sonnet/xhigh")

    def test_the_two_rules_are_independent(self):
        t60 = truth(60)
        w = self.world(t60)
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        self.fill(w, t=t60, sonnet=both, haiku_x={1: {"halluc": ("Q2",)}})       # opus clean; sonnet 4; haiku xhigh 1 of 120
        d = e1b.decide(w.collect())
        self.assertEqual((d["rule_A_balanced"], d["rule_B_fast"]), ("MOVE balanced to opus/xhigh", "ADMIT haiku/xhigh to fast"))

    def test_rule_a_one_failing_condition_alone_keeps_balanced_on_sonnet(self):
        t = truth(30, n_ans=20)                         # 40 answerable and 60 unanswerable item-runs per cell
        unans = [q for q, v in t["questions"].items() if not v["answerable"]]
        both = {1: {"halluc": tuple(unans[:2])}, 2: {"halluc": tuple(unans[:2])}}   # sonnet 4 on 2 items; opus clean
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c:
            wa, wb, wc = World(a, t), World(b, t), World(c, t)
            self.fill(wa, t=t, sonnet=both)
            self.assertEqual(e1b.decide(wa.collect())["rule_A_balanced"], "MOVE balanced to opus/xhigh")
            self.fill(wb, t=t, sonnet=both, opus={1: {"wrong": ("Q1",)}})      # one wrong answer: 39 of 40 correct
            db = e1b.decide(wb.collect())
            self.assertEqual((db["A_iii"], db["A_iv"]), (False, True))
            self.assertEqual(db["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")
            self.fill(wc, t=t, sonnet=both, opus={1: {"missed": ("Q1", "Q2", "Q3")}})   # 3 misses: 37 of 40 = 92.5%
            dc = e1b.decide(wc.collect())
            self.assertEqual((dc["A_iii"], dc["A_iv"]), (True, False))
            self.assertEqual(dc["rule_A_balanced"], "KEEP balanced on sonnet/xhigh")

    def test_rule_a_iv_is_exactly_at_95_percent(self):
        t = truth(30, n_ans=20)
        unans = [q for q, v in t["questions"].items() if not v["answerable"]]
        both = {1: {"halluc": tuple(unans[:2])}, 2: {"halluc": tuple(unans[:2])}}
        w = self.world(t)
        self.fill(w, t=t, sonnet=both, opus={1: {"missed": ("Q1", "Q2")}})     # 38 of 40 = 95%: allowed
        d = e1b.decide(w.collect())
        self.assertTrue(d["A_iv"])
        self.assertEqual(d["rule_A_balanced"], "MOVE balanced to opus/xhigh")

    def test_rule_b_one_failing_condition_alone_keeps_fast_on_sonnet(self):
        t = truth(60, n_ans=20)                         # 40 answerable and 120 unanswerable item-runs per cell
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, tempfile.TemporaryDirectory() as c, \
                tempfile.TemporaryDirectory() as d_:
            wa, wb, wc, wd = World(a, t), World(b, t), World(c, t), World(d_, t)
            self.fill(wa, t=t)
            self.assertEqual(e1b.decide(wa.collect())["rule_B_fast"], "ADMIT haiku/xhigh to fast")
            self.fill(wb, t=t, haiku_x={1: {"wrong": ("Q1",)}})                # 39 of 40 correct, but a wrong answer
            db = e1b.decide(wb.collect())
            self.assertEqual((db["B_iii"], db["B_iv"]), (False, True))
            self.assertEqual(db["rule_B_fast"], "KEEP fast on sonnet/xhigh")
            self.fill(wc, t=t, haiku_x={1: {"missed": ("Q1", "Q2", "Q3")}})    # 37 of 40 = 92.5%, no wrong answer
            dc = e1b.decide(wc.collect())
            self.assertEqual((dc["B_iii"], dc["B_iv"]), (True, False))
            self.assertEqual(dc["rule_B_fast"], "KEEP fast on sonnet/xhigh")
            self.fill(wd, t=t, haiku_x={1: {"missed": ("Q1", "Q2")}})          # 38 of 40 = 95%: allowed
            self.assertEqual(e1b.decide(wd.collect())["rule_B_fast"], "ADMIT haiku/xhigh to fast")

    # --- Rule E, Rule D, reference cell, report ------------------------------------------------------------
    def test_a_decision_cell_short_of_the_repeats_gives_the_conservative_verdict_for_both_rows(self):
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        for short_cell in DECISION:
            with self.subTest(short_cell=short_cell), tempfile.TemporaryDirectory() as tmp:
                w = World(tmp, self.t)
                for cell in DECISION + (REFERENCE,):
                    reps = (1,) if cell == short_cell else (1, 2)
                    for rep in reps:
                        w.add(cell, rep, block(self.t, **(both[rep] if cell == "sonnet-5-5@xhigh" else {})))
                d = e1b.decide(w.collect())
                self.assertFalse(d["complete"])
                self.assertTrue(d["verdict"].startswith("INCOMPLETE"))
                self.assertEqual((d["rule_A_balanced"], d["rule_B_fast"]), ("KEEP balanced on sonnet/xhigh", "KEEP fast on sonnet/xhigh"))

    def test_a_shortfall_of_the_reference_cell_alone_does_not_block_the_decision(self):
        w = self.world()
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        for cell in DECISION:
            for rep in (1, 2):
                w.add(cell, rep, block(self.t, **(both[rep] if cell == "sonnet-5-5@xhigh" else {})))
        w.add(REFERENCE, 1, block(self.t))
        self.assertTrue(e1b.decide(w.collect())["complete"])

    def test_a_task_without_runs_or_truth_is_incomplete(self):
        e1b.TASKS = (TASK, OTHER)                                                # the rules expect two tasks here
        w = self.world()
        self.fill(w)
        d = e1b.decide(w.collect())
        self.assertFalse(d["complete"])
        self.assertEqual(d["missing_tasks"], [OTHER])

    def test_rule_d_flags_items_failed_by_sonnet_and_opus_and_exclusion_removes_them(self):
        w = self.world()
        for rep in (1, 2):
            w.add(e1b.SONNET, rep, block(self.t, halluc=("Q3",)))
            w.add(e1b.OPUS, rep, block(self.t, halluc=("Q3",)))
            w.add(e1b.HAIKU_XHIGH, rep, block(self.t))
        data = w.collect()
        self.assertEqual(e1b.e1.defective_candidates(data), [f"{TASK}:Q3"])
        excl = frozenset({f"{TASK}:Q3"})
        self.assertEqual(e1b.e1.aggregate(data, e1b.SONNET, excl)["H"], 0)
        self.assertEqual(e1b.hallucinated_items(data, e1b.SONNET, excl), {})
        self.assertEqual(e1b.e1.defective_candidates(data, excl), [])

    def test_the_reference_cell_is_reported_and_never_decides(self):
        w = self.world()
        both = {1: {"halluc": ("Q2", "Q3")}, 2: {"halluc": ("Q2", "Q3")}}
        self.fill(w, sonnet=both, haiku_h=both)
        text = e1b.render(w.collect())
        self.assertIn(f"`{e1b.HAIKU_HIGH}`", text)
        self.assertIn("=> MOVE balanced to opus/xhigh", text)                    # haiku-high's own failures change nothing

    def test_the_rendered_report_carries_no_question_text_and_lists_item_ids_with_kinds(self):
        w = World(self.tmp, self.t, (TASK, OTHER))
        w.add(e1b.SONNET, 1, block(self.t, halluc=("Q2",)), task=TASK)
        w.add(e1b.SONNET, 1, block(self.t), task=OTHER)
        data = w.collect()
        text = e1b.render(data, extra={"E1 beside": data})
        self.assertNotIn(SECRET_TEXT, text)
        self.assertIn(f"| `{TASK}:Q2` | intent |", text)
        self.assertIn("E1 beside (reported only, Rule C)", text)
        self.assertIn("INCOMPLETE", text)

    def test_the_command_line_prints_the_report_and_fails_cleanly_without_tasks(self):
        w = self.world()
        self.fill(w)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = e1b.main(["--private", str(w.private), "--runs", str(w.runs), "--tasks", TASK])
        self.assertEqual(rc, 0)
        self.assertIn("Rule A (i)", buf.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc2 = e1b.main(["--private", str(Path(self.tmp) / "nowhere"), "--runs", str(w.runs), "--tasks", TASK])
        self.assertEqual(rc2, 2)


if __name__ == "__main__":
    unittest.main()
