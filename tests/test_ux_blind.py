"""Tests for evals/probes/ux_blind.py, the blind UI/UX design-pass comparison.

Every test works in a temporary evals directory and a temporary root, with `claude` replaced by
tests/fixtures/ux_fake_claude.py. No test reads evals/private, calls a real model or touches the network.
Tests that only need built pages seed them straight into the store, without a model call.
"""

import contextlib
import hashlib
import html
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE = FIXTURES / "ux_fake_claude.py"
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(FIXTURES))

import evalkit as ev  # noqa: E402

# The red-proof runs point these at mutated copies, so the real files are never edited.
UX_SRC = Path(os.environ.get("UX_BLIND_UNDER_TEST") or EVALS / "probes" / "ux_blind.py")
CHECK_SRC = Path(os.environ.get("CHECK_UX_UNDER_TEST") or ROOT / "scripts" / "quality" / "check_ux_pages.py")
_spec = importlib.util.spec_from_file_location("ux_blind_under_test", UX_SRC)
ux = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ux)
_cspec = importlib.util.spec_from_file_location("check_ux_pages_under_test", CHECK_SRC)
chk = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(chk)

MODELS = {"fable-5-2@high": "claude-test-fable-5-2", "opus-5-5@xhigh": "claude-test-opus-5-5",
          "opus-5-5@high": "claude-test-opus-5-5", "fable-5-1@high": "claude-test-fable-5-1",
          "sonnet-5-5@medium": "claude-test-sonnet-5-5"}
CELLS = {"cells": {cid: {"model_id": mid, "effort": cid.split("@")[1],
                         "price": {"input": 1.0, "output": 5.0}} for cid, mid in MODELS.items()}}
RUNNER_PROMPT, JUDGE_PROMPT = "Runner prompt.", "Judge prompt."
BRIEF_IDS = ["ux-01", "ux-02", "ux-03", "ux-04"]
MARKERS = ["===ANSWER===", "===END==="]
CSP_TEXT = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "img-src data:; font-src data:")


def harness():
    return {"harness_version": 1, "repeats_default": 3, "max_retries_invalid": 2,
            "runner": {"claude_bin": f"{shlex.quote(sys.executable)} {shlex.quote(str(FAKE))}",
                       "flags": ["--restricted", "--output-format", "json"],
                       "tools_files": "Read,Grep,Glob", "tools_inline": "", "timeout_s": 30,
                       "max_budget_usd_per_run": 1, "jobs": 2, "system_prompt": RUNNER_PROMPT},
            "answer_markers": MARKERS,
            "judge": {"cell": "fable-5-1@high", "repeats": 2, "system_prompt": JUDGE_PROMPT},
            "decision": {"noticed_extra_misses": 1, "confirmation_tasks_min": 2}}


def write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def page_html(extra="", title="Prototype"):
    return (f'<!doctype html><html><head><title>{title}</title></head><body>{extra}<p>R&amp;D "q" \'z\' &lt;b&gt;</p>'
            '<svg xmlns="http://www.w3.org/2000/svg"></svg></body></html>')


class UXTestCase(unittest.TestCase):
    """A fresh evals directory and root per test, wired to the fake claude."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.evals = self.base / "evals"
        self.root = self.base / "ux"
        self.briefs = self.root / "briefs"
        self.log = self.base / "calls.jsonl"
        write(self.evals / "harness.json", json.dumps(harness()))
        write(self.evals / "cells.json", json.dumps(CELLS))
        write(self.evals / "rows.json", json.dumps({"rows": []}))
        self.enterContext(mock.patch.dict(os.environ, {
            "UX_FAKE_LOG": str(self.log), "UX_FAKE_STATE": str(self.base / "state.json")}))
        self.ctx = ev.Ctx(self.evals)
        self.make_briefs(4)

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixtures -----------------------------------------------------------

    def make_briefs(self, count):
        shutil.rmtree(self.briefs, ignore_errors=True)
        for i in range(1, count + 1):
            d = self.briefs / f"ux-{i:02d}"
            write(d / "brief.json", json.dumps({
                "id": f"ux-{i:02d}", "game": "Game", "title": f"Screen number {i}",
                "description": f"Add screen number {i} with {{braces}} and a reward.",
                "chained_choices": ["a", "b", "c"], "viewport": "390x780"}))
            write(d / "material" / "conventions.md", "Use short Turkish words.\n")
            write(d / "checklist.json", json.dumps([
                {"id": f"K{k}", "question": f"Question {k}?", "yes_means": f"Yes {k}"} for k in range(1, 9)]))

    def env(self, **kw):
        return mock.patch.dict(os.environ, {k: str(v) for k, v in kw.items()})

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        full = list(argv) + ["--root", str(self.root), "--briefs-dir", str(self.briefs)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ux.main(full, ctx=self.ctx)
        return code, out.getvalue(), err.getvalue()

    def calls(self, model=None, kind=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        if model:
            rows = [r for r in rows if r["model"] == MODELS.get(model, model)]
        starts = {"design": "You are the UI/UX designer", "build": "Build a prototype",
                  "checklist": "You are checking one prototype page"}
        if kind:
            rows = [r for r in rows if r["prompt"].startswith(starts[kind])]
        return rows

    def attempts(self):
        return ev.read_jsonl(self.root / "attempts.jsonl")

    def plan(self):
        code, out, err = self.cli("plan", "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def pipeline(self, *steps):
        for step in steps or ("design", "build", "checklist"):
            code, out, err = self.cli(step, "--jobs", "1")
            self.assertEqual(code, 0, out + err)

    def pages_json(self):
        return json.loads((self.root / "pages.json").read_text())

    def seed_pages(self, ids=BRIEF_IDS):
        """Write built pages straight into the store: 12 per brief, no model call."""
        index, n = {}, 0
        for b in ids:
            for arm in ("F", "O", "D"):
                for s in ux.SAMPLES[arm]:
                    pid = hashlib.sha1(f"page{n}".encode()).hexdigest()[:8]
                    n += 1
                    write(self.root / "pages" / f"{pid}.html", page_html(f"<p>content {n}</p>"))
                    index[pid] = {"brief": b, "arm": arm, "sample": s, "block": ux.block_of(arm, s)}
        write(self.root / "pages.json", json.dumps(index))
        return index

    def seed_checklist(self, f_total=96, o_total=96):
        """Both judges credit the same items: F pages share f_total items, O pages share o_total."""
        index, data = self.pages_json(), {}
        for arm, total in (("F", f_total), ("O", o_total)):
            left = total
            for pid in sorted(p for p, v in index.items() if v["arm"] == arm and v["block"] == 1):
                k = min(8, left)
                left -= k
                items = {f"K{i}": i <= k for i in range(1, 9)}
                data[pid] = {"judges": {j: dict(items) for j in ux.JUDGE_CELLS}}
        write(self.root / "checklist.json", json.dumps(data))

    def seed_render_check(self, failed=(), skip=(), newer=True):
        """Write <root>/render-check.json in the shape check_ux_pages.py writes, newer (or older) than every page."""
        entries = {pid: {"load_errors": 0, "first_load_error": "", "click_errors": 0, "first_click_error": "",
                         "clicked": True, "text_length": 40, "canvas": 0, "svg": 0, "img": 0,
                         "passed": pid not in failed, "reasons": ""} for pid in self.pages_json() if pid not in skip}
        path = self.root / "render-check.json"
        write(path, json.dumps(chk.build_report(entries)))
        newest = max(f.stat().st_mtime_ns for f in (self.root / "pages").glob("*.html"))
        t = newest + (10 ** 9 if newer else -10 ** 9)
        os.utime(path, ns=(t, t))

    def make_page_file(self):
        self.seed_render_check()
        code, out, err = self.cli("page")
        self.assertEqual(code, 0, out + err)
        return json.loads((self.root / "pairs.json").read_text())

    def results_file(self, f1, f2, table=None, name="results.json"):
        """Answers where F is preferred in f1 block-1 pairs and f2 block-2 pairs."""
        table = table or json.loads((self.root / "pairs.json").read_text())
        wins, seen, answers = {1: f1, 2: f2}, {1: 0, 2: 0}, []
        for p in table["pairs"]:
            want_f = seen[p["block"]] < wins[p["block"]]
            seen[p["block"]] += 1
            f_left = p["left"]["arm"] == "F"
            answers.append({"pair": p["pair"], "choice": "A" if f_left == want_f else "B"})
        path = self.base / name
        write(path, json.dumps({"version": 1, "answers": answers, "finished": True}))
        return path

    def verdict(self, results, *extra):
        return self.cli("verdict", "--results", str(results), *extra)

    def ready_for_verdict(self, f_total=96, o_total=96):
        self.seed_pages()
        self.seed_checklist(f_total, o_total)
        self.make_page_file()


# -- plan --------------------------------------------------------------------

class PlanTests(UXTestCase):
    def test_plan_counts_36_designs_48_builds_and_48_checklist_calls_for_four_briefs(self):
        p = self.plan()
        self.assertEqual((p["designs_missing"], p["builds_missing"], p["checklist_missing"]), (36, 48, 48))
        self.assertEqual(p["calls_missing"], 132)
        self.assertEqual(p["cost_bound_usd"], 132 * 1.0)
        self.assertEqual(self.calls(), [], "plan must not call a model")

    def test_plan_text_names_the_counts_and_the_cost_bound(self):
        code, out, _ = self.cli("plan")
        self.assertEqual(code, 0)
        self.assertIn("designs: 36 missing of 36", out)
        self.assertIn("builds: 48 missing of 48", out)
        self.assertIn("checklist calls: 48 missing of 48", out)
        self.assertIn("cost bound: $132.00", out)

    def test_plan_counts_only_what_is_still_missing(self):
        index = self.seed_pages()
        pid = next(p for p, v in index.items() if v["arm"] == "F" and v["sample"] == 1)
        write(self.root / "designs" / "ux-01-F-1.json", json.dumps({"design": "x"}))
        write(self.root / "checklist.json", json.dumps({pid: {"judges": {"fable-5-1@high": {}}}}))
        index.pop(next(p for p, v in index.items() if v["arm"] == "D" and v["sample"] == 1))
        write(self.root / "pages.json", json.dumps(index))
        p = self.plan()
        self.assertEqual((p["designs_missing"], p["builds_missing"]), (35, 1))
        self.assertEqual(p["checklist_missing"], 48 - 1)

    def test_plan_works_while_another_writer_holds_the_lock(self):
        with ev.exclusive_lock(self.ctx.lock_path):
            self.assertEqual(self.cli("plan")[0], 0)

    def test_briefs_need_exactly_eight_checklist_items(self):
        items = json.loads((self.briefs / "ux-01" / "checklist.json").read_text())
        write(self.briefs / "ux-01" / "checklist.json", json.dumps(items[:7]))
        code, _, err = self.cli("plan")
        self.assertEqual(code, 2)
        self.assertIn("exactly 8 items", err)

    def test_brief_viewport_must_look_like_390x780(self):
        brief = json.loads((self.briefs / "ux-01" / "brief.json").read_text())
        brief["viewport"] = "phone"
        write(self.briefs / "ux-01" / "brief.json", json.dumps(brief))
        code, _, err = self.cli("plan")
        self.assertEqual(code, 2)
        self.assertIn("viewport", err)


# -- prompts -----------------------------------------------------------------

class PromptTests(UXTestCase):
    def test_designer_prompt_is_byte_identical_for_fable_and_opus(self):
        self.make_briefs(1)
        self.pipeline("design")
        fable = [c["prompt"] for c in self.calls("fable-5-2@high", "design")]
        opus = [c["prompt"] for c in self.calls("opus-5-5@xhigh", "design")]
        self.assertEqual((len(fable), len(opus)), (6, 3))
        self.assertEqual(set(fable) | set(opus), {fable[0]})
        brief = json.loads((self.briefs / "ux-01" / "brief.json").read_text())
        self.assertIn(brief["description"], fable[0])
        for section in ("1. Screens", "2. Flow", "3. States", "4. Words", "5. Main action", "6. Assumptions",
                        "do not write code"):
            self.assertIn(section, fable[0])
        self.assertTrue(fable[0].endswith(ux.marker_instruction(MARKERS)))
        self.assertIn("`===ANSWER===`", fable[0])
        self.assertIn("`===END===`", fable[0])

    def test_builder_prompt_differs_between_arms_only_in_the_design_paragraph(self):
        brief = {"description": "Add a shop.", "viewport": "390x780"}
        f = ux.builder_prompt(brief, "DESIGN {with braces} A", MARKERS)
        o = ux.builder_prompt(brief, "DESIGN B", MARKERS)
        d = ux.builder_prompt(brief, None, MARKERS)
        self.assertNotEqual(f, o)
        self.assertEqual(f.replace(ux.design_part("DESIGN {with braces} A"), "@@"),
                         o.replace(ux.design_part("DESIGN B"), "@@"))
        self.assertEqual(f.replace(ux.design_part("DESIGN {with braces} A"), "@@"),
                         d.replace(ux.design_part(None), "@@"))
        self.assertIn("A designer wrote this design brief. Follow it:\nDESIGN {with braces} A", f)
        self.assertIn("There is no design brief. Make the design choices yourself.", d)
        self.assertNotIn("A designer wrote", d)
        self.assertIn("portrait layout for a 390x780 phone screen", f)
        self.assertIn("Output only the HTML document", f)

    def test_the_builder_prompt_forbids_browser_storage_identically_for_every_arm(self):
        brief = {"description": "Add a shop.", "viewport": "390x780"}
        rule = ("no browser storage (localStorage, sessionStorage, cookies, IndexedDB); "
                "keep all state in memory")
        for design in ("DESIGN A", "DESIGN B", None):
            self.assertIn(rule, ux.builder_prompt(brief, design, MARKERS))

    def test_the_builder_prompt_forbids_dialogs_form_submission_navigation_and_the_history_api_for_every_arm(self):
        brief = {"description": "Add a shop.", "viewport": "390x780"}
        rule = ("no alert, confirm or prompt dialogs; no form submission and no page navigation "
                "(switch screens by showing and hiding elements); no History API")
        prompts = [ux.builder_prompt(brief, d, MARKERS) for d in ("DESIGN A", "DESIGN B", None)]
        for p in prompts:
            self.assertIn(rule, p)
        self.assertEqual({p.split(rule)[1].split("Output only")[0] for p in prompts}, {"; portrait layout for a 390x780 phone screen; UI strings in the game's own language; no HTML comments.\n"})

    def test_each_builder_gets_the_design_of_its_own_arm_and_none_for_d(self):
        self.make_briefs(1)
        self.pipeline("design", "build")
        builds = self.calls("sonnet-5-5@medium", "build")
        self.assertEqual(len(builds), 12)
        with_fable = [c for c in builds if "DESIGN-BY-claude-test-fable-5-2" in c["prompt"]]
        with_opus = [c for c in builds if "DESIGN-BY-claude-test-opus-5-5" in c["prompt"]]
        without = [c for c in builds if "There is no design brief." in c["prompt"]]
        self.assertEqual((len(with_fable), len(with_opus), len(without)), (6, 3, 3))

    def test_every_model_call_is_restricted_with_the_harness_tools_and_system_prompts(self):
        self.make_briefs(1)
        self.pipeline()
        for kind, tools, system in (("design", "Read,Grep,Glob", RUNNER_PROMPT),
                                    ("build", "Read,Grep,Glob", RUNNER_PROMPT),
                                    ("checklist", "", JUDGE_PROMPT)):
            rows = self.calls(kind=kind)
            self.assertTrue(rows, kind)
            for c in rows:
                self.assertIn("--restricted", c["argv"], kind)
                self.assertEqual(c["argv"][c["argv"].index("--tools") + 1], tools, kind)
                self.assertEqual(c["system_prompt"], system, kind)

    def test_every_call_runs_in_a_fresh_directory_holding_a_copy_of_the_material(self):
        self.make_briefs(1)
        self.pipeline("design")
        rows = self.calls(kind="design")
        self.assertEqual(len({c["cwd"] for c in rows}), len(rows))
        for c in rows:
            self.assertEqual(c["files"], ["conventions.md"])
            self.assertTrue(c["cwd"].startswith(str((self.root / "work").resolve())), c["cwd"])
        self.assertEqual(list((self.root / "work").iterdir()), [], "scratch directories are removed")
        self.assertFalse((self.evals / "private").exists(), "nothing is written beside the root")

    def test_checklist_prompt_holds_the_description_the_eight_items_and_the_page_source(self):
        brief = {"description": "Add a shop.", "checklist": [
            {"id": f"K{i}", "question": f"Is {i} true?", "yes_means": f"{i} holds"} for i in range(1, 9)]}
        p = ux.checklist_prompt(brief, "<html>PAGE-SOURCE</html>", MARKERS)
        self.assertIn("Add a shop.", p)
        self.assertIn("<html>PAGE-SOURCE</html>", p)
        for i in range(1, 9):
            self.assertIn(f"K{i}: Is {i} true? (answer true when: {i} holds)", p)
        self.assertTrue(p.endswith(ux.marker_instruction(MARKERS)))


# -- sanitising --------------------------------------------------------------

class SanitiseTests(unittest.TestCase):
    def clean(self, raw):
        out, reasons = ux.sanitize_page(raw)
        self.assertEqual(reasons, [], reasons)
        return out

    def test_comments_are_removed(self):
        out = self.clean("<!doctype html><html><head><!-- F arm --></head><body><!--\nmulti\nline-->x</body></html>")
        self.assertNotIn("<!--", out)
        self.assertNotIn("F arm", out)
        self.assertIn("<!doctype html>", out)

    def test_title_is_forced_to_prototype(self):
        out = self.clean('<html><head><TITLE lang="tr">Fable design pass</TITLE></head><body>x</body></html>')
        self.assertIn(">Prototype</TITLE>", out)
        self.assertNotIn("Fable", out)

    def test_a_missing_title_is_added(self):
        out = self.clean("<html><head><meta charset=utf-8></head><body>x</body></html>")
        self.assertEqual(out.lower().count("<title>prototype</title>"), 1)

    def test_an_svg_title_in_the_body_is_left_alone(self):
        out = self.clean("<html><head><title>Head</title></head><body><svg><title>Star</title></svg></body></html>")
        self.assertIn("<title>Prototype</title>", out)
        self.assertIn("<title>Star</title>", out)

    def test_generator_meta_is_removed_in_either_attribute_order(self):
        out = self.clean('<html><head><meta name="generator" content="Fable 5.2">'
                         '<meta content="x" NAME=\'Generator\'><meta name="viewport" content="w"></head>'
                         '<body>x</body></html>')
        self.assertNotIn("generator", out.lower())
        self.assertIn('name="viewport"', out)

    def test_the_csp_is_the_first_child_of_head(self):
        out = self.clean('<html><head lang="tr"><meta charset="utf-8"><title>T</title></head><body>x</body></html>')
        self.assertIn(f'<head lang="tr"><meta http-equiv="Content-Security-Policy" content="{CSP_TEXT}">'
                      '<meta charset="utf-8">', out)
        self.assertEqual(out.count("Content-Security-Policy"), 1)

    def test_a_head_is_created_when_the_page_has_none(self):
        out = self.clean("<html><body>x</body></html>")
        self.assertIn(f'<html><head><meta http-equiv="Content-Security-Policy" content="{CSP_TEXT}">'
                      "<title>Prototype</title></head><body>", out)

    def test_external_links_scripts_and_imports_are_removed(self):
        out = self.clean(
            '<html><head><link rel="stylesheet" href="https://fonts.example/css">'
            '<link rel="icon" href="data:,"><link rel=preload href=//cdn.example/x.css>'
            '<script src="http://cdn.example/a.js"></script><script src="//cdn.example/b.js" defer></script>'
            '<style>@import url("https://fonts.example/x.css"); @import "//x.example/y.css" screen;'
            "body{color:red}</style></head><body><script>var a = 1;</script></body></html>")
        for gone in ("fonts.example", "cdn.example", "x.example", "@import"):
            self.assertNotIn(gone, out)
        self.assertIn('<link rel="icon" href="data:,">', out)
        self.assertIn("var a = 1;", out)
        self.assertIn("body{color:red}", out)

    def invalid(self, raw, fragment):
        out, reasons = ux.sanitize_page(raw)
        self.assertIsNone(out, raw)
        self.assertTrue(any(fragment in r for r in reasons), (reasons, raw))

    def test_a_remaining_external_url_in_src_href_or_action_is_invalid(self):
        for tag in ('<img src="https://x.example/a.png">', "<a href='http://x.example'>go</a>",
                    '<form action="//x.example/post"></form>', "<iframe src = https://x.example></iframe>",
                    '<p id="a"></p><script>img.src = "https://x.example/a.png"</script>'):
            self.invalid(f"<html><body>{tag}</body></html>", "src, href or action")

    def test_a_remaining_external_url_in_css_url_is_invalid(self):
        self.invalid("<html><head><style>body{background:url(https://x.example/a.png)}</style></head>"
                     "<body></body></html>", "url()")
        self.invalid("<html><head><style>a{background:URL( '//x.example/a.png' )}</style></head>"
                     "<body></body></html>", "url()")

    def test_a_script_that_reaches_an_external_url_is_invalid(self):
        for code in ('fetch("https://x.example/api")', "fetch('//x.example/api')",
                     'var x = new XMLHttpRequest(); x.open("GET", "http://x.example/a")',
                     'import("https://x.example/m.js")', 'new WebSocket("wss://x.example/s")'):
            self.invalid(f"<html><body><script>{code}</script></body></html>", "external URL")

    def test_xmlns_and_plain_text_mentions_are_fine(self):
        out = self.clean('<html xmlns="http://www.w3.org/1999/xhtml"><body><svg xmlns="http://www.w3.org/2000/svg">'
                         '</svg><p>Read https://example.com/rules and // comments.</p>'
                         "<script>// see http://example.com\nvar fetchLater = 1; /* XMLHttpRequest */</script>"
                         "</body></html>")
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', out)

    def test_a_script_that_uses_browser_storage_is_invalid(self):
        for code in ('localStorage.setItem("a", "b")', "var s = sessionStorage.getItem('a')", "indexedDB.open('db')",
                     'document.cookie = "a=b"', "document . cookie", "window.LOCALSTORAGE"):
            self.invalid(f"<html><body><script>{code}</script></body></html>", "browser storage")
        self.invalid('<html><body><button onclick="localStorage.clear()">x</button></body></html>', "browser storage")

    def test_a_plain_text_mention_of_browser_storage_outside_a_script_is_fine(self):
        self.clean("<html><body><p>Progress is not saved: no localStorage, no cookie, no indexedDB.</p>"
                   '<script>var state = {cookies: 3, store: "memory"};</script></body></html>')

    def test_a_script_that_opens_a_dialog_is_invalid(self):
        for code in ('alert("hi")', "window.alert(1)", "if (confirm('Sure?')) go()", 'var n = prompt ("Name")'):
            self.invalid(f"<html><body><script>{code}</script></body></html>", "dialog")
        self.invalid('<html><body><button onclick="alert(1)">x</button></body></html>', "dialog")

    def test_a_script_that_uses_the_history_api_is_invalid(self):
        for code in ('history.pushState({}, "", "/a")', "window.history.replaceState(null, '', '#b')",
                     "history . pushState(1, '')"):
            self.invalid(f"<html><body><script>{code}</script></body></html>", "History API")

    def test_a_script_that_navigates_the_page_is_invalid(self):
        for code in ('location.href = "next.html"', "window.location.href='#a'", "document.location.assign('x')",
                     "location.replace('x')", "window.open('x')"):
            self.invalid(f"<html><body><script>{code}</script></body></html>", "navigates")
        self.invalid('<html><body><a href="#" onclick="location.href=\'x\'">x</a></body></html>', "navigates")

    def test_look_alike_calls_and_comparisons_are_fine(self):
        self.clean("<html><body><script>myalert(1); xalert(1); preconfirm(3); reprompt(2); confirmed(2); var prompts = []; x.alerts(); dialog.open(1);"
                   " mylocation.replace('x'); relocation.assign(1); 'abc'.replace('a', 'b'); myhistory.pushState(1);"
                   " if (location.href == 'a' || location.href === 'b') {} location.hash = '#a';"
                   " var n = history.length; function showPrompt() {}</script></body></html>")

    def test_a_plain_text_mention_of_dialogs_and_navigation_outside_a_script_is_fine(self):
        self.clean("<html><body><p>No alert( or confirm( dialogs, no window.open( and no history.pushState, "
                   "no location.href = x.</p></body></html>")

    def test_a_document_with_neither_html_nor_body_is_invalid(self):
        self.invalid("Sorry, I cannot build that.", "no <html or <body")

    def test_a_body_without_an_html_tag_is_accepted(self):
        self.assertIn("<head>", self.clean("<body>x</body>"))

    def test_the_size_limit_is_300_kb_of_utf8_bytes(self):
        shell = "<html><body><p>%s</p></body></html>"
        fill = 300 * 1024 - len(shell % "")
        out, reasons = ux.sanitize_page(shell % ("x" * fill))
        self.assertEqual(reasons, [])
        self.assertIsNotNone(out)
        self.invalid(shell % ("x" * (fill + 1)), "300 KB")
        self.invalid(shell % ("é" * (fill // 2 + 1)), "300 KB")

    def test_a_wrapping_code_fence_is_stripped(self):
        self.assertEqual(ux.strip_fence("```html\n<html>x</html>\n```"), "<html>x</html>")
        self.assertEqual(ux.strip_fence("<html>x</html>"), "<html>x</html>")


# -- design ------------------------------------------------------------------

class DesignTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.make_briefs(1)

    def design_file(self, arm, sample, brief="ux-01"):
        return json.loads((self.root / "designs" / f"{brief}-{arm}-{sample}.json").read_text())

    def test_design_stores_text_usage_cost_observed_model_and_attempts(self):
        self.pipeline("design")
        self.assertEqual(len(list((self.root / "designs").glob("*.json"))), 9)
        d = self.design_file("F", 2)
        self.assertEqual(d["design"], "Screens: DESIGN-BY-claude-test-fable-5-2. Flow: x.")
        self.assertEqual((d["brief"], d["arm"], d["sample"], d["cell"]), ("ux-01", "F", 2, "fable-5-2@high"))
        self.assertEqual(d["model_observed"], "claude-test-fable-5-2")
        self.assertEqual((d["attempts"], d["cost_usd"], d["slot_failed"]), (1, 0.01, False))
        self.assertEqual(d["usage"]["thinking_tokens"], 100)
        self.assertEqual(self.design_file("O", 1)["model_observed"], "claude-test-opus-5-5")
        self.assertEqual(self.plan()["designs_missing"], 0)

    def test_a_missing_answer_block_is_a_failed_design_retried_twice(self):
        with self.env(UX_FAKE_NO_BLOCK="design"):
            self.pipeline("design")
        self.assertEqual(len(self.calls(kind="design")), 27, "3 attempts for each of 9 slots")
        self.assertFalse((self.root / "designs").exists())
        log = self.attempts()
        self.assertEqual(len(log), 27)
        self.assertEqual({e["reason"] for e in log}, {"no_answer_block"})
        self.assertFalse(any(e["accepted"] for e in log))
        self.assertEqual(self.plan()["designs_missing"], 9)

    def test_the_attempt_limit_holds_across_invocations(self):
        with self.env(UX_FAKE_NO_BLOCK="design"):
            self.pipeline("design")
        self.assertEqual(self.plan()["exhausted_designs"], 9)
        self.pipeline("design")
        self.assertEqual(len(self.calls(kind="design")), 27, "a second run makes no further call")

    def test_a_wrong_model_attempt_is_invalid_and_retried(self):
        with self.env(UX_FAKE_WRONG_MODEL="claude-test-fable-5-2", UX_FAKE_WRONG_FIRST=1):
            self.pipeline("design")
        d = self.design_file("F", 1)
        self.assertEqual((d["attempts"], d["model_observed"]), (2, "claude-test-fable-5-2"))
        self.assertEqual(self.design_file("F", 2)["attempts"], 1)
        first, second = [e for e in self.attempts() if e["slot"] == "design|ux-01|F|1"]
        self.assertFalse(first["accepted"])
        self.assertEqual(first["model_observed"], "claude-test-fable-5-2-next")
        self.assertTrue(first["reason"].startswith("model_mismatch"))
        self.assertTrue(second["accepted"])
        self.assertEqual(d["attempt_reasons"], [first["reason"]])

    def test_a_refused_attempt_is_invalid_and_retried(self):
        with self.env(UX_FAKE_REFUSE_MODEL="claude-test-opus-5-5", UX_FAKE_REFUSE_FIRST=1):
            self.pipeline("design")
        first = next(e for e in self.attempts() if e["slot"] == "design|ux-01|O|1")
        self.assertEqual((first["accepted"], first["reason"]), (False, "refused"))
        self.assertEqual(self.design_file("O", 1)["attempts"], 2)

    def test_a_fable_slot_with_a_wrong_model_or_refused_attempt_is_flagged_failed(self):
        with self.env(UX_FAKE_WRONG_MODEL="claude-test-fable-5-2", UX_FAKE_WRONG_FIRST=1):
            self.pipeline("design")
        self.assertTrue(self.design_file("F", 1)["slot_failed"])
        self.assertFalse(self.design_file("F", 2)["slot_failed"])
        self.assertEqual(self.plan()["fable_flagged_slots"], 1)
        shutil.rmtree(self.root)
        self.make_briefs(1)
        with self.env(UX_FAKE_REFUSE_MODEL="claude-test-fable-5-2", UX_FAKE_REFUSE_FIRST=1):
            self.pipeline("design")
        self.assertTrue(self.design_file("F", 1)["slot_failed"])

    def test_safety_stops_above_zero_is_a_refusal_even_with_stop_reason_end_turn(self):
        with self.env(UX_FAKE_SAFETY_MODEL="claude-test-fable-5-2", UX_FAKE_SAFETY_FIRST=1):
            self.pipeline("design")
        first = next(e for e in self.attempts() if e["slot"] == "design|ux-01|F|1")
        self.assertEqual((first["accepted"], first["reason"]), (False, "refused"))
        self.assertEqual((first["stop_reason"], first["safety_stops"]), ("end_turn", 1))
        d = self.design_file("F", 1)
        self.assertEqual((d["attempts"], d["slot_failed"]), (2, True))

    def test_an_error_attempt_is_retried_but_does_not_flag_the_slot(self):
        with self.env(UX_FAKE_ERROR_MODEL="claude-test-fable-5-2", UX_FAKE_ERROR_FIRST=1):
            self.pipeline("design")
        first = next(e for e in self.attempts() if e["slot"] == "design|ux-01|F|1")
        self.assertEqual((first["accepted"], first["reason"]), (False, "is_error"))
        self.assertEqual((first["stop_reason"], first["safety_stops"]), ("end_turn", 0))
        d = self.design_file("F", 1)
        self.assertEqual((d["attempts"], d["slot_failed"]), (2, False))
        self.assertEqual(self.plan()["fable_flagged_slots"], 0)

    def test_every_attempt_logs_stop_reason_and_safety_stops(self):
        self.pipeline("design")
        log = self.attempts()
        self.assertEqual(len(log), 9)
        for e in log:
            self.assertEqual((e["stop_reason"], e["safety_stops"]), ("end_turn", 0))

    def test_is_refusal_reads_stop_reason_safety_stops_and_the_substring_net(self):
        normal = {"stop_reason": "end_turn", "safety_stops": 0, "terminal_reason": "completed", "subtype": "success"}
        self.assertFalse(ux.is_refusal(normal))
        self.assertTrue(ux.is_refusal({**normal, "stop_reason": "refusal"}))
        self.assertTrue(ux.is_refusal({**normal, "safety_stops": 1}))
        self.assertTrue(ux.is_refusal({**normal, "safety_stops": 3}))
        self.assertTrue(ux.is_refusal({**normal, "terminal_reason": "model_refusal"}))
        self.assertTrue(ux.is_refusal({**normal, "terminal_reason": "Model_REFUSAL"}))
        self.assertTrue(ux.is_refusal({**normal, "subtype": "error_refusal"}))
        for not_refusal in ({**normal, "is_error": True, "api_error_status": 429}, {**normal, "subtype": "error_during_execution"},
                            {**normal, "safety_stops": None}, {**normal, "safety_stops": True}, None, "text"):
            self.assertFalse(ux.is_refusal(not_refusal), not_refusal)

    def test_an_opus_slot_with_a_wrong_model_attempt_is_not_flagged(self):
        with self.env(UX_FAKE_WRONG_MODEL="claude-test-opus-5-5", UX_FAKE_WRONG_FIRST=1):
            self.pipeline("design")
        d = self.design_file("O", 1)
        self.assertEqual(d["attempts"], 2)
        self.assertFalse(d["slot_failed"])

    def test_the_budget_stops_the_run(self):
        self.make_briefs(4)
        code, out, _ = self.cli("design", "--jobs", "1", "--max-usd", "0.025")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls()), 3, "stops launching once $0.025 is passed")
        self.assertEqual(len(list((self.root / "designs").glob("*.json"))), 3)
        self.assertIn("design cost $0.0300", out)

    def test_run_commands_hold_the_evalkit_lock_and_refuse_when_it_is_taken(self):
        with ev.exclusive_lock(self.ctx.lock_path):
            for step in ("design", "build", "checklist"):
                code, _, err = self.cli(step)
                self.assertEqual(code, 2, step)
                self.assertIn("already writing", err)
        self.assertEqual(self.calls(), [])

    def test_a_missing_cell_stops_before_any_call(self):
        cells = json.loads((self.evals / "cells.json").read_text())
        del cells["cells"]["fable-5-2@high"]
        write(self.evals / "cells.json", json.dumps(cells))
        self.ctx = ev.Ctx(self.evals)
        code, _, err = self.cli("design")
        self.assertEqual(code, 2)
        self.assertIn("fable-5-2@high", err)
        self.assertEqual(self.calls(), [])


# -- build -------------------------------------------------------------------

class BuildTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.make_briefs(1)

    def test_build_stores_pages_under_random_hex_ids_with_a_private_mapping(self):
        self.pipeline("design", "build")
        index = self.pages_json()
        self.assertEqual(len(index), 12)
        for pid, v in index.items():
            self.assertRegex(pid, r"^[0-9a-f]{8}$")
            self.assertTrue((self.root / "pages" / f"{pid}.html").is_file())
        keys = {(v["arm"], v["sample"], v["block"]) for v in index.values()}
        self.assertEqual(keys, {("F", s, 1 if s <= 3 else 2) for s in range(1, 7)}
                         | {("O", s, 1) for s in (1, 2, 3)} | {("D", s, 2) for s in (1, 2, 3)})
        self.assertEqual({v["brief"] for v in index.values()}, {"ux-01"})

    def test_page_ids_file_names_and_contents_do_not_reveal_the_arm(self):
        self.pipeline("design", "build")
        files = sorted((self.root / "pages").iterdir())
        self.assertEqual(len(files), 12)
        for f in files:
            self.assertRegex(f.name, r"^[0-9a-f]{8}\.html$")
            text = f.read_text()
            self.assertNotRegex(text, r"(?i)fable|opus|sonnet|generator|<!--|F arm")
            self.assertIn("<title>Prototype</title>", text)
            self.assertIn(f'content="{CSP_TEXT}"', text)
        self.assertEqual(len({f.name for f in files}), 12)

    def test_a_design_is_needed_before_its_page_can_be_built(self):
        self.pipeline("build")
        index = self.pages_json()
        self.assertEqual({v["arm"] for v in index.values()}, {"D"})
        self.assertEqual(len(index), 3)
        self.assertEqual(self.plan()["builds_waiting_for_design"], 9)

    def test_an_invalid_page_is_rebuilt_twice_then_left_missing(self):
        write(self.base / "bad.html", '<html><body><img src="https://x.example/a.png"></body></html>')
        with self.env(UX_FAKE_PAGE=self.base / "bad.html"):
            self.pipeline("design", "build")
        self.assertEqual(len(self.calls(kind="build")), 36, "3 attempts for each of 12 slots")
        self.assertFalse((self.root / "pages.json").exists())
        reasons = {e["reason"] for e in self.attempts() if e["stage"] == "build"}
        self.assertEqual(len(reasons), 1)
        self.assertTrue(next(iter(reasons)).startswith("page_invalid: src, href or action"))

    def test_a_page_with_no_answer_block_is_retried_and_stored_on_a_later_run(self):
        self.pipeline("design")
        with self.env(UX_FAKE_NO_BLOCK="build"):
            self.pipeline("build")
        self.assertFalse((self.root / "pages.json").exists())
        (self.root / "attempts.jsonl").unlink()      # the owner resets the attempt budget
        self.pipeline("build")
        self.assertEqual(len(self.pages_json()), 12)

    def test_a_fenced_answer_is_unwrapped_before_it_is_stored(self):
        write(self.base / "fenced.html", "```html\n" + page_html("<p>fenced</p>") + "\n```")
        with self.env(UX_FAKE_PAGE=self.base / "fenced.html"):
            self.pipeline("design", "build")
        for f in (self.root / "pages").iterdir():
            self.assertNotIn("```", f.read_text())
            self.assertIn("<p>fenced</p>", f.read_text())

    def test_the_build_attempt_log_names_the_slot_and_the_cell(self):
        self.pipeline("design", "build")
        e = next(e for e in self.attempts() if e["slot"] == "build|ux-01|F|1")
        self.assertEqual((e["cell"], e["model_observed"], e["accepted"]),
                         ("sonnet-5-5@medium", "claude-test-sonnet-5-5", True))


# -- checklist ---------------------------------------------------------------

class ChecklistTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.make_briefs(1)

    def test_each_judge_reads_each_block_one_page_once(self):
        self.pipeline("design", "build", "checklist")
        calls = self.calls(kind="checklist")
        self.assertEqual(len(calls), 12, "6 block-1 pages x 2 judges")
        self.assertEqual(sorted(c["model"] for c in calls), sorted(["claude-test-fable-5-1"] * 6 + ["claude-test-opus-5-5"] * 6))
        data = json.loads((self.root / "checklist.json").read_text())
        block_one = {pid for pid, v in self.pages_json().items() if v["block"] == 1}
        self.assertEqual(set(data), block_one)
        for entry in data.values():
            self.assertEqual(set(entry["judges"]), set(ux.JUDGE_CELLS))
            self.assertEqual(entry["judges"]["fable-5-1@high"], {f"K{i}": True for i in range(1, 9)})
            self.assertEqual(entry["score"], 1.0)
        self.assertEqual(self.plan()["checklist_missing"], 0)

    def test_the_judge_prompt_holds_the_page_source_of_the_page_it_judges(self):
        self.pipeline("design", "build", "checklist")
        first = self.calls(kind="checklist")[0]["prompt"]
        sources = [f.read_text() for f in (self.root / "pages").iterdir()]
        self.assertEqual(sum(s in first for s in sources), 1)

    def test_an_item_is_credited_only_when_both_judges_say_true(self):
        ids = [f"K{i}" for i in range(1, 9)]
        both = {j: {k: True for k in ids} for j in ux.JUDGE_CELLS}
        self.assertEqual(ux.page_credited(both, ids), ids)
        split = {"fable-5-1@high": {**{k: True for k in ids}, "K3": False},
                 "opus-5-5@high": {**{k: True for k in ids}, "K5": False}}
        self.assertEqual(ux.page_credited(split, ids), ["K1", "K2", "K4", "K6", "K7", "K8"])
        self.assertIsNone(ux.page_credited({"fable-5-1@high": both["fable-5-1@high"]}, ids))

    def test_stored_page_results_credit_what_both_judges_said_true(self):
        self.pipeline("design", "build")
        check = {"claude-test-fable-5-1": {"K2": False}, "claude-test-opus-5-5": {"K4": False}}
        with self.env(UX_FAKE_CHECK=json.dumps(check)):
            self.pipeline("checklist")
        entry = next(iter(json.loads((self.root / "checklist.json").read_text()).values()))
        self.assertEqual(entry["credited"], ["K1", "K3", "K5", "K6", "K7", "K8"])
        self.assertEqual(entry["score"], 6 / 8)

    def test_an_unparseable_judge_reply_is_retried_up_to_twice_then_left_missing(self):
        self.pipeline("design", "build")
        with self.env(UX_FAKE_BAD_FIRST=100):
            self.pipeline("checklist")
        self.assertEqual(len(self.calls(kind="checklist")), 36, "3 attempts for each of 12 calls")
        self.assertFalse((self.root / "checklist.json").exists())
        self.assertEqual({e["reason"][:21] for e in self.attempts() if e["stage"] == "checklist"},
                         {"checklist_unparseable"})
        self.assertEqual(self.plan()["checklist_missing"], 12)

    def test_a_judge_reply_that_is_fixed_on_the_retry_is_stored(self):
        self.pipeline("design", "build")
        with self.env(UX_FAKE_BAD_FIRST=2):
            self.pipeline("checklist")
        self.assertEqual(len(self.calls(kind="checklist")), 14)
        self.assertEqual(self.plan()["checklist_missing"], 0)

    def test_a_reply_without_all_eight_real_booleans_is_not_accepted(self):
        ids = [f"K{i}" for i in range(1, 9)]
        good = json.dumps({k: True for k in ids})
        wrap = lambda body: f"===ANSWER===\n{body}\n===END==="
        self.assertEqual(ux.accept_checklist(wrap(good), MARKERS, ids)[1], None)
        for body in (json.dumps({k: True for k in ids[:7]}), json.dumps({**{k: True for k in ids}, "K9": True}),
                     json.dumps({**{k: True for k in ids}, "K8": "yes"}), json.dumps({**{k: True for k in ids}, "K8": 1}),
                     "[true]"):
            self.assertIsNone(ux.accept_checklist(wrap(body), MARKERS, ids)[0], body)

    def test_a_wrong_model_judge_is_invalid_and_retried(self):
        self.pipeline("design", "build")
        with self.env(UX_FAKE_WRONG_MODEL="claude-test-fable-5-1", UX_FAKE_WRONG_FIRST=1):
            self.pipeline("checklist")
        bad = [e for e in self.attempts() if e["stage"] == "checklist" and not e["accepted"]]
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]["reason"].startswith("model_mismatch"))
        self.assertEqual(self.plan()["checklist_missing"], 0)


# -- pairs and the blind page ------------------------------------------------

class BlindPageTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.index = self.seed_pages()

    def test_the_pair_table_has_24_pairs_12_per_block_and_no_page_twice(self):
        table = self.make_page_file()
        pairs = table["pairs"]
        self.assertEqual(len(pairs), 24)
        self.assertEqual([sum(p["block"] == b for p in pairs) for b in (1, 2)], [12, 12])
        used = [p[side]["page"] for p in pairs for side in ("left", "right")]
        self.assertEqual(len(used), 48)
        self.assertEqual(set(used), set(self.index))
        self.assertEqual([p["position"] for p in pairs], list(range(1, 25)))
        self.assertEqual(len({p["pair"] for p in pairs}), 24)
        for p in pairs:
            self.assertRegex(p["pair"], r"^[0-9a-f]{10}$")

    def test_block_one_pairs_f_against_o_and_block_two_uses_f_samples_4_to_6_against_d(self):
        pairs = self.make_page_file()["pairs"]
        for p in pairs:
            arms = {p["left"]["arm"]: p["left"], p["right"]["arm"]: p["right"]}
            if p["block"] == 1:
                self.assertEqual(set(arms), {"F", "O"})
                self.assertIn(arms["F"]["sample"], (1, 2, 3))
                self.assertEqual(arms["F"]["sample"], arms["O"]["sample"])
            else:
                self.assertEqual(set(arms), {"F", "D"})
                self.assertIn(arms["F"]["sample"], (4, 5, 6))
                self.assertIn(arms["D"]["sample"], (1, 2, 3))
                self.assertEqual(arms["F"]["sample"] - 3, arms["D"]["sample"])
            for ref in arms.values():
                self.assertEqual(self.index[ref["page"]]["arm"], ref["arm"])
                self.assertEqual(self.index[ref["page"]]["brief"], p["brief"])
        for b in BRIEF_IDS:
            self.assertEqual([sum(p["brief"] == b and p["block"] == k for p in pairs) for k in (1, 2)], [3, 3])

    def test_one_shuffled_order_with_a_random_side_per_pair(self):
        with mock.patch.object(ux.secrets, "randbits", return_value=12345):
            pairs = self.make_page_file()["pairs"]
        canonical = [(b, k) for b in BRIEF_IDS for _ in range(3) for k in (1, 2)]
        self.assertNotEqual([(p["brief"], p["block"]) for p in pairs], canonical)
        self.assertNotEqual([p["block"] for p in pairs], sorted(p["block"] for p in pairs))
        self.assertNotEqual([p["brief"] for p in pairs], sorted(p["brief"] for p in pairs))
        f_left = sum(p["left"]["arm"] == "F" for p in pairs)
        self.assertTrue(4 <= f_left <= 20, f_left)

    def test_the_pair_table_is_a_function_of_the_stored_seed(self):
        class FakeUX:
            briefs = {b: None for b in BRIEF_IDS}
        idx = {(v["brief"], v["arm"], v["sample"]): pid for pid, v in self.index.items()}
        with mock.patch.object(ux.secrets, "randbits", return_value=777):
            a, b = ux.make_pairs(FakeUX, idx), ux.make_pairs(FakeUX, idx)
        self.assertEqual(a, b)
        self.assertEqual(a["seed"], 777)
        with mock.patch.object(ux.secrets, "randbits", return_value=778):
            self.assertNotEqual(ux.make_pairs(FakeUX, idx)["pairs"], a["pairs"])

    def test_pairs_are_not_reshuffled_when_pairs_json_exists(self):
        with mock.patch.object(ux.secrets, "randbits", return_value=1):
            self.make_page_file()
        before = ((self.root / "pairs.json").read_bytes(), (self.root / "blind.html").read_bytes())
        with mock.patch.object(ux.secrets, "randbits", return_value=2):
            self.make_page_file()
        after = ((self.root / "pairs.json").read_bytes(), (self.root / "blind.html").read_bytes())
        self.assertEqual(before, after)

    def test_page_refuses_while_pages_are_not_built(self):
        index = self.pages_json()
        index.pop(next(iter(index)))
        write(self.root / "pages.json", json.dumps(index))
        code, _, err = self.cli("page")
        self.assertEqual(code, 2)
        self.assertIn("not built yet", err)
        self.assertFalse((self.root / "pairs.json").exists())

    def test_page_refuses_a_page_that_names_a_model(self):
        pid = next(iter(self.index))
        write(self.root / "pages" / f"{pid}.html", page_html("<p>Made by Claude</p>"))
        self.seed_render_check()
        code, _, err = self.cli("page")
        self.assertEqual(code, 2)
        self.assertIn(f"{pid}.html names a model", err)
        self.assertFalse((self.root / "blind.html").exists())

    def test_page_writes_to_out_when_given(self):
        out = self.base / "elsewhere" / "owner.html"
        self.seed_render_check()
        code, text, _ = self.cli("page", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        self.assertFalse((self.root / "blind.html").exists())
        self.assertIn("24 pairs", text)

    def blind(self):
        self.make_page_file()
        return (self.root / "blind.html").read_text(encoding="utf-8")

    def test_blind_html_is_one_offline_document(self):
        text = self.blind()
        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', text)
        self.assertRegex(text, r'<meta name="viewport" content="[^"]*width=device-width')
        stripped = text.replace("xmlns=&quot;http://www.w3.org/2000/svg&quot;", "")
        self.assertNotIn("http://", stripped)
        self.assertNotIn("https://", stripped)
        self.assertNotRegex(stripped, r"(?i)\b(?:src|href)=[\"']?(?:https?:)?//")
        self.assertNotRegex(stripped, r"(?i)\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon)\b")
        self.assertNotRegex(stripped, r"<link\b|<script[^>]*\bsrc=")

    def test_blind_html_names_no_arm_model_block_sample_or_page(self):
        text = self.blind()
        self.assertNotRegex(text, r"(?i)fable|opus|sonnet|haiku|claude|anthropic|model")
        self.assertNotRegex(text, r"(?i)\bsample\b|\barm\b|\bdesign\b")
        self.assertNotIn('"block"', text)
        self.assertNotIn('"arm"', text)
        for b in BRIEF_IDS:
            self.assertNotIn(b, text)
        for pid in self.index:
            self.assertNotIn(pid, text)
        self.assertNotIn('"F"', text)

    def test_blind_html_embeds_48_pages_as_sandboxed_srcdoc_iframes_labelled_a_and_b(self):
        text = self.blind()
        found = []

        class Grab(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == "iframe":
                    found.append(dict(attrs))

        Grab().feed(text)
        self.assertEqual(text.count("srcdoc="), 48)
        self.assertEqual(len(found), 48)
        stored = sorted((self.root / "pages" / f"{pid}.html").read_text() for pid in self.index)
        self.assertEqual(sorted(f["srcdoc"] for f in found), stored)
        for f in found:
            self.assertEqual(f["sandbox"], "allow-scripts")
            self.assertEqual((f["width"], f["height"]), ("390", "780"))
        self.assertEqual(text.count("<figcaption>A</figcaption>"), 24)
        self.assertEqual(text.count("<figcaption>B</figcaption>"), 24)
        self.assertEqual(text.count("<template "), 24)

    def test_blind_html_shows_each_pair_in_its_stored_order_with_the_a_page_on_the_left(self):
        table = self.make_page_file()
        text = (self.root / "blind.html").read_text()
        deck = json.loads(re.search(r'id="deck">(.*?)</script>', text, re.S).group(1))
        self.assertEqual([p["id"] for p in deck["pairs"]], [p["pair"] for p in table["pairs"]])
        self.assertEqual({p["title"] for p in deck["pairs"]}, {f"Screen number {i}" for i in range(1, 5)})
        self.assertIn("Add screen number 1 with {braces} and a reward.", [p["description"] for p in deck["pairs"]])
        p = table["pairs"][0]
        tpl = re.search(r'<template id="t-%s">(.*?)</template>' % p["pair"], text, re.S).group(1)
        left = (self.root / "pages" / f"{p['left']['page']}.html").read_text()
        right = (self.root / "pages" / f"{p['right']['page']}.html").read_text()
        self.assertLess(tpl.index(html.escape(left, quote=True)), tpl.index(html.escape(right, quote=True)))

    def test_blind_html_has_the_buttons_back_save_and_the_fallback_textarea(self):
        text = self.blind()
        for needle in ("A is better", "B is better", "'Back'", "Save results", "ux-blind-results.json",
                       "new Blob(", "type: 'application/json'", "createObjectURL", "localStorage.setItem(key,",
                       "localStorage.getItem(key)", "button('Back', '', back, pos === 0)",
                       "'Pair ' + (pos + 1) + ' of ' + total", "el('textarea'", "finished: list.length === total",
                       "version: 1", 'sandbox="allow-scripts"'):
            self.assertIn(needle, text)
        self.assertNotIn("Tie", text)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_blind_html_scripts_parse(self):
        text = self.blind()
        scripts = [s for s in re.findall(r"<script>(.*?)</script>", text, re.S)]
        self.assertEqual(len(scripts), 1)
        f = self.base / "blind.js"
        write(f, scripts[0])
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


# -- verdict -----------------------------------------------------------------

class VerdictTests(UXTestCase):
    def run_verdict(self, f1, f2, f_total=96, o_total=96):
        self.ready_for_verdict(f_total, o_total)
        code, out, err = self.verdict(self.results_file(f1, f2), "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_verdict_refuses_with_23_answers(self):
        self.ready_for_verdict()
        path = self.results_file(12, 12)
        data = json.loads(path.read_text())
        data["answers"].pop()
        write(path, json.dumps(data))
        code, out, err = self.verdict(path)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("only 23 of 24 pairs are answered", err)

    def test_verdict_refuses_a_pair_answered_twice_or_an_unknown_pair(self):
        self.ready_for_verdict()
        path = self.results_file(12, 12)
        data = json.loads(path.read_text())
        dup = {**data, "answers": data["answers"] + [data["answers"][0]]}
        write(path, json.dumps(dup))
        self.assertIn("answered twice", self.verdict(path)[2])
        unknown = {**data, "answers": data["answers"][:23] + [{"pair": "ffffffffff", "choice": "A"}]}
        write(path, json.dumps(unknown))
        code, out, err = self.verdict(path)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("unknown pair", err)
        bad = {**data, "answers": [{**data["answers"][0], "choice": "tie"}] + data["answers"][1:]}
        write(path, json.dumps(bad))
        self.assertIn("neither A nor B", self.verdict(path)[2])

    def test_verdict_refuses_while_the_checklist_is_incomplete(self):
        self.ready_for_verdict()
        data = json.loads((self.root / "checklist.json").read_text())
        data.pop(next(iter(data)))
        write(self.root / "checklist.json", json.dumps(data))
        code, out, err = self.verdict(self.results_file(12, 12))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("checklist is incomplete for 1 block-1 page", err)

    def test_verdict_refuses_without_a_pair_table(self):
        self.seed_pages()
        path = self.base / "r.json"
        write(path, json.dumps({"answers": []}))
        code, _, err = self.verdict(path)
        self.assertEqual(code, 2)
        self.assertIn("run `page` first", err)

    def test_uq_fires_at_10_of_12_when_the_checklist_condition_holds(self):
        v = self.run_verdict(10, 0)
        self.assertEqual((v["block1_f_preferred_raw"], v["block1_f_preferred_counted"]), (10, 10))
        self.assertEqual(v["quality_designer"], "fable-5-2@high")
        self.assertEqual(v["balanced_designer"], "opus-5-5@xhigh")

    def test_uq_does_not_fire_at_9_of_12(self):
        v = self.run_verdict(9, 0)
        self.assertEqual((v["quality_designer"], v["balanced_designer"]), ("opus-5-5@xhigh", "opus-5-5@xhigh"))

    def test_uq_does_not_fire_at_10_of_12_when_f_is_more_than_0_05_below_o_on_the_checklist(self):
        v = self.run_verdict(10, 0, f_total=91, o_total=96)
        self.assertAlmostEqual(v["mean_O"] - v["mean_F"], 5 / 96)
        self.assertFalse(v["checklist_not_below"])
        self.assertEqual(v["quality_designer"], "opus-5-5@xhigh")
        self.assertEqual(v["balanced_designer"], "opus-5-5@xhigh")

    def test_uq_still_fires_when_f_is_below_o_by_less_than_0_05(self):
        v = self.run_verdict(10, 0, f_total=92, o_total=96)
        self.assertTrue(v["checklist_not_below"])
        self.assertEqual(v["quality_designer"], "fable-5-2@high")

    def test_ub_needs_11_of_12_and_the_same_checklist_condition(self):
        v = self.run_verdict(10, 0)
        self.assertEqual((v["quality_designer"], v["balanced_designer"]), ("fable-5-2@high", "opus-5-5@xhigh"))
        v = self.run_verdict(11, 0)
        self.assertEqual((v["quality_designer"], v["balanced_designer"]), ("fable-5-2@high", "fable-5-2@high"))
        v = self.run_verdict(11, 0, f_total=80, o_total=96)
        self.assertEqual((v["quality_designer"], v["balanced_designer"]), ("opus-5-5@xhigh", "opus-5-5@xhigh"))

    def test_fast_always_uses_the_opus_designer(self):
        self.assertEqual(self.run_verdict(12, 12)["fast_designer"], "opus-5-5@xhigh")

    def test_ud_fires_at_10_of_12_in_block_two_and_not_at_9(self):
        self.assertTrue(self.run_verdict(0, 10)["design_pass_default"])
        self.assertFalse(self.run_verdict(0, 9)["design_pass_default"])
        self.assertTrue(self.run_verdict(0, 12)["design_pass_default"])

    def test_block_counts_are_kept_apart(self):
        v = self.run_verdict(7, 3)
        self.assertEqual((v["block1_f_preferred_raw"], v["block2_f_preferred_raw"]), (7, 3))
        self.assertEqual((v["block1_f_preferred_counted"], v["block2_f_preferred_counted"]), (7, 3))

    def test_mean_scores_are_credited_items_over_eight_per_page_over_twelve_pages(self):
        v = self.run_verdict(10, 0, f_total=60, o_total=72)
        self.assertAlmostEqual(v["mean_F"], 60 / 96)
        self.assertAlmostEqual(v["mean_O"], 72 / 96)

    def test_verdict_counts_how_often_the_left_page_was_chosen(self):
        self.ready_for_verdict()
        table = json.loads((self.root / "pairs.json").read_text())
        path = self.base / "left.json"
        write(path, json.dumps({"answers": [{"pair": p["pair"], "choice": "A"} for p in table["pairs"]]}))
        v = json.loads(self.verdict(path, "--json")[1])
        self.assertEqual((v["left_chosen"], v["pairs"]), (24, 24))
        write(path, json.dumps({"answers": [{"pair": p["pair"], "choice": "B"} for p in table["pairs"]]}))
        self.assertEqual(json.loads(self.verdict(path, "--json")[1])["left_chosen"], 0)

    def test_the_text_verdict_prints_counts_means_the_left_bias_and_the_rule_outcomes(self):
        self.ready_for_verdict()
        code, out, _ = self.verdict(self.results_file(11, 10))
        self.assertEqual(code, 0)
        self.assertIn("block 1 (F against O): F preferred in 11 of 12 counted (11 raw;", out)
        self.assertIn("block 2 (F against D): F preferred in 10 of 12 counted (10 raw;", out)
        self.assertIn("mean_F 1.0000  mean_O 1.0000", out)
        self.assertRegex(out, r"left page chosen \d+ of 24")
        self.assertIn("UQ (quality): designer fable-5-2@high", out)
        self.assertIn("UB (balanced): designer fable-5-2@high", out)
        self.assertIn("fast: designer opus-5-5@xhigh", out)
        self.assertIn("a design pass is the default", out)
        code, out, _ = self.verdict(self.results_file(5, 5, name="low.json"))
        self.assertIn("UQ (quality): designer opus-5-5@xhigh", out)
        self.assertIn("not a default; available on request, no benefit measured", out)

    def test_json_verdict_holds_scalars_only(self):
        v = self.run_verdict(10, 10)
        for key, value in v.items():
            self.assertIsInstance(value, (int, float, bool, str), key)
        text = json.dumps(v)
        for pid in self.pages_json():
            self.assertNotIn(pid, text)
        self.assertNotIn("ux-0", text)

    def flag_f_slots(self, block, n, preferred, results):
        """Mark the F design slot of n pairs in `block` as failed; the owner preferred F in those pairs
        (preferred=True) or the other page (preferred=False)."""
        table = json.loads((self.root / "pairs.json").read_text())
        choice = {a["pair"]: a["choice"] for a in json.loads(Path(results).read_text())["answers"]}
        done = 0
        for p in table["pairs"]:
            f_left = p["left"]["arm"] == "F"
            f_won = (choice[p["pair"]] == "A") == f_left
            if p["block"] == block and f_won == preferred and done < n:
                f = p["left"] if f_left else p["right"]
                write(self.root / "designs" / f"{p['brief']}-F-{f['sample']}.json", json.dumps({"slot_failed": True}))
                done += 1
        self.assertEqual(done, n)

    def test_a_pair_whose_f_page_comes_from_a_flagged_slot_counts_as_f_not_preferred(self):
        self.ready_for_verdict()
        path = self.results_file(11, 0)
        self.flag_f_slots(1, 2, True, path)
        v = json.loads(self.verdict(path, "--json")[1])
        self.assertEqual((v["block1_f_preferred_raw"], v["block1_f_preferred_counted"]), (11, 9))
        self.assertEqual((v["block1_pairs_flagged"], v["block1_pairs_changed"]), (2, 2))
        self.assertEqual((v["quality_designer"], v["balanced_designer"]), ("opus-5-5@xhigh", "opus-5-5@xhigh"))
        self.assertEqual((v["block2_f_preferred_raw"], v["block2_f_preferred_counted"]), (0, 0))

    def test_without_flagged_slots_raw_and_counted_are_equal(self):
        v = self.run_verdict(11, 10)
        self.assertEqual((v["block1_f_preferred_raw"], v["block1_f_preferred_counted"]), (11, 11))
        self.assertEqual((v["block2_f_preferred_raw"], v["block2_f_preferred_counted"]), (10, 10))
        self.assertEqual((v["block1_pairs_flagged"], v["block1_pairs_changed"], v["block2_pairs_changed"]), (0, 0, 0))
        self.assertEqual(v["balanced_designer"], "fable-5-2@high")

    def test_a_flagged_slot_whose_pair_the_owner_did_not_prefer_changes_nothing(self):
        self.ready_for_verdict()
        path = self.results_file(10, 0)
        self.flag_f_slots(1, 2, False, path)
        v = json.loads(self.verdict(path, "--json")[1])
        self.assertEqual((v["block1_f_preferred_raw"], v["block1_f_preferred_counted"]), (10, 10))
        self.assertEqual((v["block1_pairs_flagged"], v["block1_pairs_changed"]), (2, 0))
        self.assertEqual(v["quality_designer"], "fable-5-2@high")

    def test_rule_ud_uses_the_counted_number_of_block_two(self):
        self.ready_for_verdict()
        path = self.results_file(0, 10)
        self.flag_f_slots(2, 2, True, path)
        v = json.loads(self.verdict(path, "--json")[1])
        self.assertEqual((v["block2_f_preferred_raw"], v["block2_f_preferred_counted"]), (10, 8))
        self.assertFalse(v["design_pass_default"])

    def test_the_left_bias_count_stays_on_the_raw_choices(self):
        self.ready_for_verdict()
        table = json.loads((self.root / "pairs.json").read_text())
        path = self.base / "left.json"
        write(path, json.dumps({"answers": [{"pair": p["pair"], "choice": "A"} for p in table["pairs"]]}))
        for p in table["pairs"]:
            if p["left"]["arm"] == "F":
                write(self.root / "designs" / f"{p['brief']}-F-{p['left']['sample']}.json", json.dumps({"slot_failed": True}))
        v = json.loads(self.verdict(path, "--json")[1])
        self.assertEqual(v["left_chosen"], 24)

    def test_the_text_verdict_reports_raw_counted_and_changed_pairs_with_a_note(self):
        self.ready_for_verdict()
        path = self.results_file(10, 10)
        self.flag_f_slots(1, 1, True, path)
        self.flag_f_slots(2, 1, True, path)
        table = json.loads((self.root / "pairs.json").read_text())
        lost = next(p for p in table["pairs"] if p["block"] == 1 and not (self.root / "designs" / f"{p['brief']}-F-{(p['left'] if p['left']['arm'] == 'F' else p['right'])['sample']}.json").exists()
                    and json.loads(path.read_text())["answers"][p["position"] - 1]["choice"] == ("B" if p["left"]["arm"] == "F" else "A"))
        f = lost["left"] if lost["left"]["arm"] == "F" else lost["right"]
        write(self.root / "designs" / f"{lost['brief']}-F-{f['sample']}.json", json.dumps({"slot_failed": True}))
        out = self.verdict(path)[1]
        self.assertIn("block 1 (F against O): F preferred in 9 of 12 counted (10 raw; 2 pair(s) with a flagged Fable slot, 1 changed by it)", out)
        self.assertIn("block 2 (F against D): F preferred in 9 of 12 counted (10 raw; 1 pair(s) with a flagged Fable slot, 1 changed by it)", out)
        self.assertIn("NOTE: section 2 counts a Fable slot with a refused or wrong-model attempt as failed: "
                      "1 block-1 and 1 block-2 pair(s) the owner chose F in are counted as not preferred. "
                      "The rules above use the counted numbers.", out)
        self.assertIn("UQ (quality): designer opus-5-5@xhigh", out)


# -- infrastructure errors ---------------------------------------------------

def call_dict(returncode=0, timeout=False, error=None):
    return {"stdout": "", "returncode": returncode, "timeout": timeout, "error": error}


class InfraTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.make_briefs(1)

    def test_a_non_null_api_error_status_is_an_infra_error(self):
        self.assertTrue(ux.is_infra_error(call_dict(0), {"api_error_status": 529, "usage": {"output_tokens": 20}}))
        self.assertTrue(ux.is_infra_error(call_dict(1), {"api_error_status": 429, "is_error": True}))
        self.assertTrue(ux.is_infra_error(call_dict(0), {"api_error_status": 429, "usage": {"output_tokens": 20}}))
        self.assertTrue(ux.is_infra_error(call_dict(0), {"api_error_status": 0, "usage": {"output_tokens": 20}}))
        self.assertFalse(ux.is_infra_error(call_dict(0), {"api_error_status": None, "usage": {"output_tokens": 20}}))

    def test_a_failed_call_with_no_output_tokens_is_an_infra_error_without_a_status(self):
        self.assertTrue(ux.is_infra_error(call_dict(error="spawn failed: no such file"), None))
        self.assertTrue(ux.is_infra_error(call_dict(1), None))
        self.assertTrue(ux.is_infra_error(call_dict(1), {"is_error": True, "usage": {"output_tokens": 0}}))
        self.assertTrue(ux.is_infra_error(call_dict(0), {"is_error": True, "usage": {}}))

    def test_a_timeout_a_failure_with_output_and_a_normal_call_are_not_infra_errors(self):
        self.assertFalse(ux.is_infra_error(call_dict(None, timeout=True), None))
        self.assertFalse(ux.is_infra_error(call_dict(None, timeout=True), {"api_error_status": 500}))
        self.assertFalse(ux.is_infra_error(call_dict(None, timeout=True, error="x"), None))
        self.assertFalse(ux.is_infra_error(call_dict(1), {"is_error": True, "usage": {"output_tokens": 50}}))
        self.assertFalse(ux.is_infra_error(call_dict(0), {"is_error": False, "usage": {"output_tokens": 50}}))
        self.assertFalse(ux.is_infra_error(call_dict(0), None), "unparseable output from a clean exit is a counted failure")

    def test_three_rate_limit_errors_leave_the_slot_runnable(self):
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-fable-5-2", UX_FAKE_API_ERROR_FIRST=3):
            for _ in range(3):
                self.assertEqual(self.cli("design", "--jobs", "1")[0], 3)
        log = [e for e in self.attempts() if e["slot"] == "design|ux-01|F|1"]
        self.assertEqual(len(log), 3)
        for e in log:
            self.assertEqual((e["accepted"], e["infra_error"], e["api_error_status"]), (False, True, 429))
        p = self.plan()
        self.assertEqual((p["exhausted_designs"], p["designs_missing"], p["infra_waiting_designs"]), (0, 9, 1))
        self.assertEqual(self.cli("design", "--jobs", "1")[0], 0)
        d = json.loads((self.root / "designs" / "ux-01-F-1.json").read_text())
        self.assertEqual((d["attempts"], d["slot_failed"], d["attempt_reasons"]), (4, False, []))
        self.assertEqual(self.plan()["infra_waiting"], 0)

    def test_three_attempts_that_are_not_infra_errors_still_exhaust_the_slot(self):
        with self.env(UX_FAKE_NO_BLOCK="design"):
            self.pipeline("design")
        p = self.plan()
        self.assertEqual((p["exhausted_designs"], p["infra_waiting_designs"]), (9, 0))
        self.assertFalse(any(e["infra_error"] for e in self.attempts()))

    def test_the_first_infra_error_stops_the_invocation_with_exit_3_and_starts_nothing_more(self):
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-fable-5-2", UX_FAKE_API_ERROR_FIRST=1000):
            code, out, err = self.cli("design", "--jobs", "1")
        self.assertEqual(code, 3)
        self.assertEqual(len(self.calls()), 1, "nothing is started after the first infra error")
        lines = [ln for ln in err.splitlines() if "infra error" in ln]
        self.assertEqual(len(lines), 1)
        self.assertIn("design|ux-01|F|1", lines[0])
        self.assertIn("api_error_status 429", lines[0])
        self.assertIn("design cost", out)

    def test_build_and_checklist_stop_on_an_infra_error_too(self):
        self.pipeline("design")
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-sonnet-5-5", UX_FAKE_API_ERROR_FIRST=1000):
            code, _, err = self.cli("build", "--jobs", "1")
        self.assertEqual((code, len(self.calls(kind="build"))), (3, 1))
        self.assertIn("infra error on build|", err)
        self.pipeline("build")
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-fable-5-1", UX_FAKE_API_ERROR_FIRST=1000):
            code, _, err = self.cli("checklist", "--jobs", "1")
        self.assertEqual((code, len(self.calls(kind="checklist"))), (3, 1))
        self.assertIn("infra error on checklist|", err)

    def test_a_failed_call_with_no_output_and_no_status_stops_the_invocation_too(self):
        with self.env(UX_FAKE_FAIL_MODEL="claude-test-fable-5-2", UX_FAKE_FAIL_FIRST=1000):
            code, _, err = self.cli("design", "--jobs", "1")
        self.assertEqual((code, len(self.calls())), (3, 1))
        self.assertIn("api_error_status none", err)
        e = self.attempts()[0]
        self.assertEqual((e["infra_error"], e["api_error_status"], e["accepted"]), (True, None, False))

    def test_a_refusal_that_comes_back_with_is_error_is_not_an_infra_error(self):
        with self.env(UX_FAKE_REFUSE_MODEL="claude-test-fable-5-2", UX_FAKE_REFUSE_FIRST=1, UX_FAKE_REFUSE_ERROR=1):
            code, _, err = self.cli("design", "--jobs", "1")
        self.assertEqual(code, 0, err)
        first = next(e for e in self.attempts() if e["slot"] == "design|ux-01|F|1")
        self.assertEqual((first["reason"], first["infra_error"], first["output_tokens"]), ("refused", False, 0))
        d = json.loads((self.root / "designs" / "ux-01-F-1.json").read_text())
        self.assertEqual((d["attempts"], d["slot_failed"]), (2, True))

    def test_a_slot_with_an_infra_error_and_a_counted_failure_is_not_waiting_only_on_infra(self):
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-fable-5-2", UX_FAKE_API_ERROR_FIRST=1):
            self.cli("design", "--jobs", "1")
        with self.env(UX_FAKE_NO_BLOCK="design"):
            self.cli("design", "--jobs", "1")
        p = self.plan()
        self.assertEqual((p["infra_waiting_designs"], p["exhausted_designs"], p["designs_missing"]), (0, 9, 9))

    def test_plan_text_shows_the_slots_waiting_only_on_infra_errors(self):
        with self.env(UX_FAKE_API_ERROR_MODEL="claude-test-fable-5-2", UX_FAKE_API_ERROR_FIRST=1):
            self.cli("design", "--jobs", "1")
        out = self.cli("plan")[1]
        self.assertIn("slots waiting only on infra errors: 1 (1 designs, 0 builds, 0 checklist calls)", out)


# -- reject and the render-check gate ----------------------------------------

class RejectTests(UXTestCase):
    def setUp(self):
        super().setUp()
        self.index = self.seed_pages()
        self.seed_checklist()
        self.d_page = next(p for p, v in self.index.items() if v["arm"] == "D" and v["brief"] == "ux-01" and v["sample"] == 1)

    def test_reject_removes_the_page_and_build_lists_it_as_missing_again_without_printing_the_arm(self):
        self.assertEqual(self.plan()["builds_missing"], 0)
        code, out, err = self.cli("reject", "--page", self.d_page, "--reason", "blank screen")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"rejected page {self.d_page}: blank screen\n")
        self.assertEqual(err, "")
        self.assertFalse((self.root / "pages" / f"{self.d_page}.html").exists())
        self.assertNotIn(self.d_page, self.pages_json())
        self.assertEqual(self.plan()["builds_missing"], 1)
        code, out, _ = self.cli("build", "--jobs", "1")
        self.assertEqual(code, 0)
        self.assertIn("1 build(s) to do", out)
        self.assertEqual(len(self.calls(kind="build")), 1)
        new = next(p for p, v in self.pages_json().items()
                   if (v["brief"], v["arm"], v["sample"]) == ("ux-01", "D", 1))
        self.assertNotEqual(new, self.d_page)

    def test_reject_logs_one_counted_failed_build_attempt_for_the_slot(self):
        self.cli("reject", "--page", self.d_page, "--reason", "blank screen")
        log = [e for e in self.attempts() if e["slot"] == "build|ux-01|D|1"]
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["accepted"], log[0]["infra_error"], log[0]["reason"], log[0]["stage"]),
                         (False, False, "rejected: blank screen", "build"))
        self.assertEqual(ux.failures_of(log), 1)

    def test_rejections_count_toward_the_same_cap_as_other_failed_builds(self):
        for _ in range(3):
            page = next(p for p, v in self.pages_json().items() if (v["brief"], v["arm"], v["sample"]) == ("ux-01", "D", 1))
            self.assertEqual(self.cli("reject", "--page", page, "--reason", "bad")[0], 0)
            self.cli("build", "--jobs", "1")
        self.assertEqual(len(self.calls(kind="build")), 2, "the third rebuild is refused by the cap")
        p = self.plan()
        self.assertEqual((p["builds_missing"], p["exhausted_builds"]), (1, 1))

    def test_reject_also_drops_the_checklist_answers_of_that_page(self):
        f_page = next(p for p, v in self.index.items() if v["arm"] == "F" and v["sample"] == 1 and v["brief"] == "ux-01")
        self.assertIn(f_page, json.loads((self.root / "checklist.json").read_text()))
        self.cli("reject", "--page", f_page, "--reason", "x")
        self.assertNotIn(f_page, json.loads((self.root / "checklist.json").read_text()))

    def test_reject_of_an_unknown_page_is_refused(self):
        code, out, err = self.cli("reject", "--page", "deadbeef", "--reason", "x")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no page deadbeef", err)

    def test_reject_takes_the_evalkit_lock(self):
        with ev.exclusive_lock(self.ctx.lock_path):
            code, _, err = self.cli("reject", "--page", self.d_page, "--reason", "x")
        self.assertEqual(code, 2)
        self.assertIn("already writing", err)
        self.assertIn(self.d_page, self.pages_json())

    def refuses(self, fragment):
        code, out, err = self.cli("page")
        self.assertEqual((code, out), (2, ""))
        self.assertIn(fragment, err)
        self.assertFalse((self.root / "pairs.json").exists())
        self.assertFalse((self.root / "blind.html").exists())
        return err

    def test_page_refuses_without_a_render_check_file(self):
        self.refuses("render-check.json is missing")

    def test_page_refuses_with_a_render_check_older_than_a_page(self):
        self.seed_render_check(newer=False)
        self.refuses("render-check.json is older than a page file")

    def test_page_refuses_when_a_page_changed_after_the_check(self):
        self.seed_render_check()
        f = next((self.root / "pages").glob("*.html"))
        future = (self.root / "render-check.json").stat().st_mtime_ns + 5 * 10 ** 9
        os.utime(f, ns=(future, future))
        self.refuses("older than a page file")

    def test_page_refuses_when_the_render_check_lists_a_failed_page(self):
        self.seed_render_check(failed={self.d_page})
        err = self.refuses("did not pass 1 page(s)")
        self.assertIn(self.d_page, err)

    def test_page_refuses_when_a_page_is_missing_from_the_render_check(self):
        self.seed_render_check(skip={self.d_page})
        err = self.refuses("did not pass 1 page(s)")
        self.assertIn(self.d_page, err)

    def test_page_accepts_a_fresh_render_check_that_passes_every_page(self):
        self.seed_render_check()
        code, out, err = self.cli("page")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "blind.html").is_file())

    def test_the_render_check_must_name_a_page_rebuilt_after_a_reject(self):
        self.seed_render_check()
        self.cli("reject", "--page", self.d_page, "--reason", "x")
        self.cli("build", "--jobs", "1")
        code, out, err = self.cli("page")
        self.assertEqual((code, out), (2, ""))
        self.assertRegex(err, r"older than a page file|did not pass 1 page")     # which one depends on the clock
        self.assertFalse((self.root / "blind.html").exists())


# -- the render check's pure parts (the browser run is a live check) ----------

class RenderCheckTests(unittest.TestCase):
    def stats(self, **kw):
        base = {"load_errors": 0, "click_errors": 0, "text_length": 40, "canvas": 0, "svg": 0, "img": 0}
        return {**base, **kw}

    def test_a_page_with_enough_text_and_no_errors_passes(self):
        self.assertEqual(chk.judge_page(self.stats()), (True, []))
        self.assertEqual(chk.judge_page(self.stats(text_length=20)), (True, []))

    def test_an_uncaught_error_on_load_fails_the_page(self):
        self.assertEqual(chk.judge_page(self.stats(load_errors=1)), (False, ["uncaught error on load"]))

    def test_an_uncaught_error_on_the_first_click_fails_the_page(self):
        self.assertEqual(chk.judge_page(self.stats(click_errors=2)), (False, ["uncaught error on first click"]))

    def test_a_page_with_under_20_characters_and_nothing_drawn_rendered_nothing(self):
        self.assertEqual(chk.judge_page(self.stats(text_length=19)), (False, ["rendered nothing"]))
        self.assertEqual(chk.judge_page(self.stats(text_length=0)), (False, ["rendered nothing"]))

    def test_a_canvas_an_svg_or_an_img_counts_as_rendered(self):
        for kind in ("canvas", "svg", "img"):
            self.assertEqual(chk.judge_page(self.stats(text_length=3, **{kind: 1})), (True, []), kind)

    def test_every_failing_reason_is_reported(self):
        ok, reasons = chk.judge_page(self.stats(load_errors=1, click_errors=1, text_length=0))
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 3)

    def test_the_report_fails_unless_every_page_passed_and_there_is_at_least_one(self):
        good, bad = {"passed": True}, {"passed": False}
        self.assertTrue(chk.build_report({"a1": good, "b2": good})["all_passed"])
        r = chk.build_report({"a1": good, "b2": bad})
        self.assertEqual((r["all_passed"], r["checked"], r["failed"]), (False, 2, 1))
        self.assertFalse(chk.build_report({})["all_passed"])
        self.assertEqual((r["version"], r["viewport"]), (1, "390x780"))

    def test_messages_are_cut_to_120_characters_on_one_line(self):
        out = chk.short("a  b\n" + "x" * 300)
        self.assertEqual(len(out), 120)
        self.assertNotIn("\n", out)

    def test_the_frame_is_sandboxed_without_same_origin_at_the_phone_viewport(self):
        w = chk.wrapper_html('<p class="a">x & y</p>')
        self.assertIn('sandbox="allow-scripts"', w)
        self.assertNotIn("allow-same-origin", w)
        self.assertIn('width="390" height="780"', w)
        self.assertIn("&lt;p class=&quot;a&quot;&gt;x &amp; y&lt;/p&gt;", w)

    def test_the_check_reads_only_page_files_and_never_names_the_arm_mapping(self):
        src = CHECK_SRC.read_text(encoding="utf-8")
        for private in ("pages.json", "designs", "attempts", "pairs.json", "checklist.json"):
            self.assertNotIn(private, src)
        self.assertEqual(src.count('glob("*.html")'), 2)

    def test_the_report_can_be_read_by_the_page_gate_in_the_shape_ux_blind_expects(self):
        r = chk.build_report({"a1": {"passed": True, "text_length": 3}})
        self.assertEqual(set(r["pages"]), {"a1"})
        for st in r["pages"].values():
            for v in st.values():
                self.assertIsInstance(v, (int, str, bool))


# -- the command line --------------------------------------------------------

class CommandLineTests(UXTestCase):
    def test_the_script_runs_as_a_command_and_defaults_the_root_to_private_ux(self):
        env = dict(os.environ, AGENTING_EVALS_DIR=str(self.evals))
        briefs = self.evals / "private" / "ux" / "briefs"
        shutil.copytree(self.briefs, briefs)
        r = subprocess.run([sys.executable, str(UX_SRC), "plan", "--json"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["designs_missing"], 36)

    def test_an_unknown_briefs_directory_is_a_clear_error(self):
        shutil.rmtree(self.briefs)
        code, _, err = self.cli("plan")
        self.assertEqual(code, 2)
        self.assertIn("no briefs directory", err)


if __name__ == "__main__":
    unittest.main()
