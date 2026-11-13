#!/usr/bin/env python3
"""ux_blind  --  a blind comparison of UI/UX design passes (rule set: section 4 of
evals/results/PREREGISTERED-2026-11-13-think-first.md, row `ux-design`).

Arms: F = designer fable-5-2@high writes a design brief, O = designer opus-5-5@xhigh does, D = no
design pass. The same builder (sonnet-5-5@medium) builds one HTML page per run. The owner then picks
the better page in 24 blind pairs and `verdict` applies rules UQ, UB and UD.

    python3 evals/probes/ux_blind.py plan                      # what is missing, a cost bound; no model call
    python3 evals/probes/ux_blind.py design   --max-usd 60     # designer runs (arms F and O)
    python3 evals/probes/ux_blind.py build    --max-usd 40     # builder runs, pages are sanitised
    python3 evals/probes/ux_blind.py checklist --max-usd 40    # two judges, block-1 pages only
    python3 evals/probes/ux_blind.py reject --page ID --reason TEXT   # drop one built page; `build` rebuilds it
    python3 evals/probes/ux_blind.py page [--out blind.html]   # ONE offline HTML file for the owner (needs render-check.json)
    python3 evals/probes/ux_blind.py verdict --results ux-blind-results.json [--json]

Every path lives under a root (default <evals>/private/ux/, override --root):

    briefs/<id>/brief.json, material/, checklist.json     the inputs (override --briefs-dir)
    designs/<brief>-<arm>-<sample>.json                   one design brief per designer run
    pages/<page_id>.html + pages.json                     built pages; the page_id is 8 random hex digits
    checklist.json                                        both judges' answers per block-1 page (private)
    pairs.json                                            the 24 pairs, seed, order and sides (private)
    attempts.jsonl                                        every model attempt, valid or not (private)
    work/                                                 per-attempt scratch directories

Model calls reuse evalkit (call_claude, parse_call, usage_of, extract_block, Budget, call_cost,
prepare_workdir, exclusive_lock, run_pool). `design`, `build` and `checklist` take evalkit's exclusive
lock (results/.evalkit.lock, outside --root) so they never run beside `evalkit.py run|judge`.
The attempt limit per slot is harness `max_retries_invalid` + 1, counted across invocations from
attempts.jsonl, so repeated invocations cannot keep spending on one broken slot. An infrastructure error
(a non-null api_error_status, or a failed call with no output tokens that is not a refusal) is logged but
does not count toward that limit: the invocation stops launching calls and exits with code 3.

Everything the owner sees is blind: file names and file contents never name an arm, a model or a
sample number; the mapping page -> arm lives only in the private files above.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import secrets
import shutil
import sys
import threading
import types
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import evalkit as ev  # noqa: E402

# -- the experiment ----------------------------------------------------------

ARM_CELL = {"F": "fable-5-2@high", "O": "opus-5-5@xhigh"}      # designer cells
BUILDER_CELL = "sonnet-5-5@medium"                              # builder for every arm
JUDGE_CELLS = ("fable-5-1@high", "opus-5-5@high")               # checklist judges
SAMPLES = {"F": (1, 2, 3, 4, 5, 6), "O": (1, 2, 3), "D": (1, 2, 3)}
FAST_DESIGNER = "opus-5-5@xhigh"
N_ITEMS = 8
PAIR_COUNT = 24
RULE_BLOCK_UQ, RULE_BLOCK_UB, RULE_BLOCK_UD = 10, 11, 10        # pairs of 12 that F must win
CHECKLIST_MARGIN = Fraction(1, 20)                              # F is "not below" O within 0.05
MAX_PAGE_BYTES = 300 * 1024                                     # 300 KB read as 1024 bytes
PAGE_TITLE = "Prototype"
CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
       "img-src data:; font-src data:")
CSP_META = f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
RESULTS_FILE_NAME = "ux-blind-results.json"
LEAK_WORDS = re.compile(r"fable|opus|sonnet|haiku|claude|anthropic", re.I)
VIEWPORT_RE = re.compile(r"^(\d{2,4})x(\d{2,4})$")


def block_of(arm: str, sample: int) -> int:
    """1 = F against O (F samples 1-3, O samples 1-3), 2 = F against D (F samples 4-6, D 1-3)."""
    if arm == "O":
        return 1
    if arm == "D":
        return 2
    return 1 if sample <= 3 else 2


def all_slots(brief_ids) -> list[dict]:
    return [{"brief": b, "arm": arm, "sample": s, "block": block_of(arm, s)}
            for b in brief_ids for arm in ("F", "O", "D") for s in SAMPLES[arm]]


# -- prompts -----------------------------------------------------------------

def marker_instruction(markers) -> str:
    start, end = markers
    return (f"Put your final answer between a line `{start}` and a line `{end}`. "
            "Put nothing else between the two marker lines.")


DESIGNER_HEAD = ("You are the UI/UX designer for the game whose conventions and existing style are in "
                 "the files in your working directory. Work only from those files and your own "
                 "reasoning.\n\nThe owner wants this:\n")
DESIGNER_BODY = (
    "\n\nWrite the design brief a developer will build from, in exactly these sections:\n"
    "1. Screens: each screen and what is on it.\n"
    "2. Flow: how the player moves between screens and back.\n"
    "3. States: every state of each screen (empty, loading, error, success, wherever they apply) "
    "and what it shows.\n"
    "4. Words: every UI string, in the game's own language and tone.\n"
    "5. Main action: the one thing the player most needs to do, and where it sits.\n"
    "6. Assumptions: what you decided that the owner did not say.\n"
    "At most about 1,200 words. Describe the design; do not write code.")


def designer_prompt(brief: dict, markers) -> str:
    """The same text for arm F and arm O; the arm never reaches the prompt."""
    return DESIGNER_HEAD + brief["description"] + DESIGNER_BODY + "\n\n" + marker_instruction(markers)


BUILDER_HEAD = ("Build a prototype for the game whose conventions and existing style are in the files "
                "in your working directory. Work only from those files and your own reasoning.\n\n"
                "The owner wants this:\n")
DESIGN_PART_WITH = "A designer wrote this design brief. Follow it:\n"
DESIGN_PART_NONE = "There is no design brief. Make the design choices yourself."


def design_part(design_text) -> str:
    return DESIGN_PART_NONE if design_text is None else DESIGN_PART_WITH + design_text


def builder_prompt(brief: dict, design_text, markers) -> str:
    """Arms F and O pass the design text, arm D passes None; only that paragraph differs."""
    rules = ("Rules: one self-contained HTML document with inline CSS and JavaScript; no network "
             "request of any kind (no external fonts, images, scripts or styles); no browser storage "
             "(localStorage, sessionStorage, cookies, IndexedDB); keep all state in memory; no alert, confirm or "
             "prompt dialogs; no form submission and no page navigation (switch screens by showing and hiding "
             "elements); no History API; portrait layout "
             f"for a {brief['viewport']} phone screen; UI strings in the game's own language; "
             "no HTML comments.\nOutput only the HTML document.")
    return (BUILDER_HEAD + brief["description"] + "\n\n" + design_part(design_text) + "\n\n" + rules
            + "\n\n" + marker_instruction(markers))


def checklist_prompt(brief: dict, page_html: str, markers) -> str:
    items = "\n".join(f"{it['id']}: {it['question']} (answer true when: {it['yes_means']})"
                      for it in brief["checklist"])
    ids = ", ".join(f'"{it["id"]}": true or false' for it in brief["checklist"])
    return (
        "You are checking one prototype page against a checklist. Judge only from the HTML source "
        "below.\n\n## What the owner asked for\n\n" + brief["description"]
        + "\n\n## Checklist\n\n" + items
        + "\n\n## Page source\n\n" + page_html
        + "\n\n## Reply\n\nAnswer every checklist item with true or false in one JSON object: {" + ids
        + "}. " + marker_instruction(markers))


# -- sanitising a built page -------------------------------------------------

EXT = r"(?:https?:)?//"                       # absolute http(s) URL or protocol-relative //host
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
GENERATOR_RE = re.compile(r"<meta\b(?=[^>]*\bname\s*=\s*[\"']?generator\b)[^>]*>", re.I)
LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
LINK_EXT_RE = re.compile(r"\bhref\s*=\s*[\"']?\s*" + EXT, re.I)
SCRIPT_EXT_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']?\s*" + EXT + r"[^>]*>.*?</script\s*>",
                           re.I | re.S)
IMPORT_STRIP_RE = re.compile(r"@import\s*(?:url\(\s*)?[\"']?\s*" + EXT + r"[^;\n]*;?", re.I)
HEAD_RE = re.compile(r"(<head\b[^>]*>)(.*?)(</head\s*>)", re.I | re.S)
HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.I)
HTML_OPEN_RE = re.compile(r"<html\b[^>]*>", re.I)
BODY_OPEN_RE = re.compile(r"<body\b", re.I)
TITLE_RE = re.compile(r"(<title\b[^>]*>)(.*?)(</title\s*>)", re.I | re.S)
FENCE_RE = re.compile(r"^\s*```[A-Za-z]*[ \t]*\n(.*?)\n?```\s*$", re.S)
SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.I | re.S)
EVENT_ATTR_RE = re.compile(r"\bon[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)
STORAGE_RE = re.compile(r"\b(?:localStorage|sessionStorage|indexedDB)\b|\bdocument\s*\.\s*cookie\b", re.I)
DIALOG_RE = re.compile(r"\b(?:alert|confirm|prompt)\s*\(")
HISTORY_RE = re.compile(r"\bhistory\s*\.\s*(?:pushState|replaceState)\b")
NAVIGATE_RE = re.compile(r"\blocation\s*\.\s*href\s*=(?!=)|\blocation\s*\.\s*(?:assign|replace)\s*\(|"
                         r"\bwindow\s*\.\s*open\s*\(")
EXTERNAL_USE = (
    ("src, href or action points to an external URL",
     re.compile(r"\b(?:src|href|action|formaction|poster|srcset)\s*=\s*[\"']?\s*" + EXT, re.I)),
    ("url() points to an external URL",
     re.compile(r"url\(\s*[\"']?\s*" + EXT, re.I)),
    ("fetch, import(), WebSocket, EventSource or sendBeacon to an external URL",
     re.compile(r"\b(?:fetch|import|WebSocket|EventSource|sendBeacon)\s*\(\s*[\"'`]\s*"
                r"(?:(?:https?|wss?):)?//", re.I)),
    ("XMLHttpRequest open() to an external URL",
     re.compile(r"\.open\s*\(\s*[\"'`]\w+[\"'`]\s*,\s*[\"'`]\s*(?:(?:https?|wss?):)?//", re.I)),
)


def strip_fence(text: str) -> str:
    m = FENCE_RE.match(text)
    return m.group(1) if m else text


def insert_head_first(page: str, snippet: str) -> str:
    """snippet becomes the first child of <head>; a head is created when the page has none."""
    m = HEAD_OPEN_RE.search(page)
    if m:
        return page[:m.end()] + snippet + page[m.end():]
    m = HTML_OPEN_RE.search(page)
    if m:
        return page[:m.end()] + "<head>" + snippet + "</head>" + page[m.end():]
    m = BODY_OPEN_RE.search(page)
    at = m.start() if m else 0
    return page[:at] + "<head>" + snippet + "</head>" + page[at:]


def force_title(page: str):
    """(page, had_title): the first <title> (inside <head> when there is one) now reads Prototype."""
    head = HEAD_RE.search(page)
    scope = (head.start(2), head.end(2)) if head else (0, len(page))
    m = TITLE_RE.search(page, *scope)
    if not m:
        return page, False
    return page[:m.start(2)] + PAGE_TITLE + page[m.end(2):], True


def sanitize_page(raw: str):
    """(clean page or None, list of reasons). A page with reasons is invalid and must be rebuilt."""
    page = COMMENT_RE.sub("", raw)
    page = GENERATOR_RE.sub("", page)
    page = SCRIPT_EXT_RE.sub("", page)
    page = LINK_RE.sub(lambda m: "" if LINK_EXT_RE.search(m.group(0)) else m.group(0), page)
    page = IMPORT_STRIP_RE.sub("", page)
    page, had_title = force_title(page)
    reasons = [why for why, rx in EXTERNAL_USE if rx.search(page)]
    code = SCRIPT_BLOCK_RE.findall(page) + [m.group(1) for m in EVENT_ATTR_RE.finditer(page)]
    if any(STORAGE_RE.search(c) for c in code):
        reasons.append("script uses browser storage")
    if any(DIALOG_RE.search(c) for c in code):
        reasons.append("script opens a dialog (alert, confirm or prompt)")
    if any(HISTORY_RE.search(c) for c in code):
        reasons.append("script uses the History API")
    if any(NAVIGATE_RE.search(c) for c in code):
        reasons.append("script navigates the page (location or window.open)")
    if not (re.search(r"<html\b", page, re.I) or re.search(r"<body\b", page, re.I)):
        reasons.append("no <html or <body")
    if len(page.encode("utf-8")) > MAX_PAGE_BYTES:
        reasons.append("larger than 300 KB")
    if reasons:
        return None, reasons
    return insert_head_first(page, CSP_META + ("" if had_title else f"<title>{PAGE_TITLE}</title>")), []


# -- the stores --------------------------------------------------------------

STORE_LOCK = threading.Lock()          # guards read-modify-write of pages.json and checklist.json


class UX:
    """Context: evalkit's Ctx plus every path under the root, and the loaded briefs."""

    def __init__(self, ctx, root, briefs_dir=None):
        self.ctx = ctx
        self.root = Path(root).resolve()
        self.briefs_dir = Path(briefs_dir).resolve() if briefs_dir else self.root / "briefs"
        self.designs = self.root / "designs"
        self.pages = self.root / "pages"
        self.pages_json = self.root / "pages.json"
        self.checklist_json = self.root / "checklist.json"
        self.pairs_json = self.root / "pairs.json"
        self.attempts = self.root / "attempts.jsonl"
        # evalkit.prepare_workdir only reads `work_dir`, so a stand-in keeps scratch files under the root
        self.workctx = types.SimpleNamespace(work_dir=self.root / "work")
        self.markers = ctx.harness["answer_markers"]
        self.max_attempts = ctx.harness["max_retries_invalid"] + 1
        self.per_run_cap = ctx.harness["runner"]["max_budget_usd_per_run"]
        self._briefs = None
        self.infra_stop = threading.Event()     # set by the first infrastructure error of an invocation
        self.infra_lines = []

    @property
    def briefs(self) -> dict:
        if self._briefs is None:
            self._briefs = load_briefs(self.briefs_dir)
        return self._briefs

    def read(self, path, default):
        return ev.read_json(path) if Path(path).exists() else default

    def need_cells(self, cell_ids):
        missing = [c for c in cell_ids if c not in self.ctx.cells]
        if missing:
            raise ev.EvalError("evals/cells.json has no cell " + ", ".join(missing))


def load_briefs(briefs_dir: Path) -> dict:
    """{brief id: brief dict with `dir` and `checklist`}, validated; sorted by id."""
    if not briefs_dir.is_dir():
        raise ev.EvalError(f"no briefs directory at {briefs_dir}")
    out = {}
    for d in sorted(p for p in briefs_dir.iterdir() if (p / "brief.json").is_file()):
        brief = ev.read_json(d / "brief.json")
        for field in ("id", "game", "title", "description", "chained_choices", "viewport"):
            if field not in brief:
                raise ev.EvalError(f"{d / 'brief.json'}: missing field {field}")
        if not isinstance(brief["viewport"], str) or not VIEWPORT_RE.match(brief["viewport"]):
            raise ev.EvalError(f"{d / 'brief.json'}: viewport must look like 390x780")
        items = ev.read_json(d / "checklist.json")
        ids = [it.get("id") for it in items] if isinstance(items, list) else []
        if ids != [f"K{i}" for i in range(1, N_ITEMS + 1)] or any(
                not it.get("question") or not it.get("yes_means") for it in items):
            raise ev.EvalError(f"{d / 'checklist.json'}: needs exactly {N_ITEMS} items K1..K{N_ITEMS}, "
                               "each with id, question and yes_means")
        if brief["id"] in out:
            raise ev.EvalError(f"brief id {brief['id']} appears twice")
        out[brief["id"]] = {**brief, "dir": d, "checklist": items}
    if not out:
        raise ev.EvalError(f"{briefs_dir} holds no brief (a folder with brief.json)")
    return out


def design_path(ux, slot) -> Path:
    return ux.designs / f"{slot['brief']}-{slot['arm']}-{slot['sample']}.json"


def slot_key(stage, slot, judge=None) -> str:
    return "|".join([stage, slot["brief"], slot["arm"], str(slot["sample"])] + ([judge] if judge else []))


def attempts_by_slot(ux) -> dict:
    out = {}
    for e in ev.read_jsonl(ux.attempts):
        out.setdefault(e.get("slot"), []).append(e)
    return out


def failures_of(entries) -> int:
    """Counted failed attempts of a slot. An infrastructure error is logged but never counted."""
    return sum(1 for e in entries if not e.get("accepted") and not e.get("infra_error"))


def only_infra(entries) -> bool:
    """True when a slot has attempts and every one of them was an infrastructure error."""
    return bool(entries) and all(e.get("infra_error") for e in entries)


def pages_index(ux) -> dict:
    """{(brief, arm, sample): page_id} from pages.json."""
    return {(v["brief"], v["arm"], v["sample"]): pid for pid, v in ux.read(ux.pages_json, {}).items()}


def checklist_for_page(ux, page_id):
    return ux.read(ux.checklist_json, {}).get(page_id, {}).get("judges", {})


def page_credited(judges: dict, item_ids):
    """Items credited because EVERY judge said true; None while a judge is missing."""
    if any(j not in judges for j in JUDGE_CELLS):
        return None
    return [k for k in item_ids if all(judges[j].get(k) is True for j in JUDGE_CELLS)]


# -- plan --------------------------------------------------------------------

def compute_plan(ux) -> dict:
    slots, by_slot = all_slots(ux.briefs), attempts_by_slot(ux)
    pages, exhausted = pages_index(ux), {"designs": 0, "builds": 0, "checklist": 0}
    designs = [s for s in slots if s["arm"] in ARM_CELL and not design_path(ux, s).exists()]
    builds = [s for s in slots if (s["brief"], s["arm"], s["sample"]) not in pages]
    waiting = [s for s in builds if s["arm"] in ARM_CELL and not design_path(ux, s).exists()]
    exhausted["designs"] = sum(failures_of(by_slot.get(slot_key("design", s), [])) >= ux.max_attempts
                               for s in designs)
    exhausted["builds"] = sum(failures_of(by_slot.get(slot_key("build", s), [])) >= ux.max_attempts
                              for s in builds)
    check = []
    for s in slots:
        if s["block"] != 1:
            continue
        pid = pages.get((s["brief"], s["arm"], s["sample"]))
        have = checklist_for_page(ux, pid) if pid else {}
        for j in JUDGE_CELLS:
            if j not in have:
                check.append((s, j))
    exhausted["checklist"] = sum(
        failures_of(by_slot.get(slot_key("checklist", s, j), [])) >= ux.max_attempts for s, j in check)
    infra = {"designs": sum(only_infra(by_slot.get(slot_key("design", s), [])) for s in designs),
             "builds": sum(only_infra(by_slot.get(slot_key("build", s), [])) for s in builds),
             "checklist": sum(only_infra(by_slot.get(slot_key("checklist", s, j), [])) for s, j in check)}
    missing = len(designs) + len(builds) + len(check)
    flagged = flagged_fable_slots(ux)
    return {"briefs": len(ux.briefs), "designs_total": sum(1 for s in slots if s["arm"] in ARM_CELL),
            "designs_missing": len(designs), "builds_total": len(slots), "builds_missing": len(builds),
            "builds_waiting_for_design": len(waiting),
            "checklist_total": sum(1 for s in slots if s["block"] == 1) * len(JUDGE_CELLS),
            "checklist_missing": len(check), "exhausted_designs": exhausted["designs"],
            "exhausted_builds": exhausted["builds"], "exhausted_checklist": exhausted["checklist"],
            "infra_waiting_designs": infra["designs"], "infra_waiting_builds": infra["builds"],
            "infra_waiting_checklist": infra["checklist"], "infra_waiting": sum(infra.values()),
            "calls_missing": missing, "per_run_cap_usd": ux.per_run_cap,
            "cost_bound_usd": missing * ux.per_run_cap, "fable_flagged_slots": flagged,
            "_designs": designs, "_builds": builds, "_check": check}


def flagged_fable_slots(ux) -> int:
    n = 0
    for p in sorted(ux.designs.glob("*.json")) if ux.designs.is_dir() else []:
        if ev.read_json(p).get("slot_failed"):
            n += 1
    return n


def cmd_plan(ux, args):
    p = compute_plan(ux)
    if args.json:
        print(json.dumps({k: v for k, v in p.items() if not k.startswith("_")}, indent=2))
        return 0
    print(f"briefs: {p['briefs']}")
    print(f"designs: {p['designs_missing']} missing of {p['designs_total']} "
          f"({p['exhausted_designs']} out of attempts)")
    print(f"builds: {p['builds_missing']} missing of {p['builds_total']} "
          f"({p['builds_waiting_for_design']} waiting for a design, {p['exhausted_builds']} out of attempts)")
    print(f"checklist calls: {p['checklist_missing']} missing of {p['checklist_total']} "
          f"({p['exhausted_checklist']} out of attempts)")
    print(f"slots waiting only on infra errors: {p['infra_waiting']} "
          f"({p['infra_waiting_designs']} designs, {p['infra_waiting_builds']} builds, "
          f"{p['infra_waiting_checklist']} checklist calls)")
    print(f"calls missing: {p['calls_missing']}")
    print(f"cost bound: ${p['cost_bound_usd']:.2f} ({p['calls_missing']} calls x "
          f"${p['per_run_cap_usd']:.2f} per-run cap)")
    print(f"fable slots flagged (a refused or wrong-model attempt): {p['fable_flagged_slots']}")
    return 0


# -- one slot: attempts, validity, logging ----------------------------------

def is_refusal(data) -> bool:
    """A safety refusal as Claude Code 2.1.323 reports it: stop_reason "refusal", or safety_stops above 0
    (an integer, 0 on a normal run). The 'refus' substring check on stop_reason, subtype and
    terminal_reason is a second net. An API error, a rate limit or a timeout is NOT a refusal."""
    if not isinstance(data, dict):
        return False
    stops = data.get("safety_stops")
    if data.get("stop_reason") == "refusal" or (
            isinstance(stops, int) and not isinstance(stops, bool) and stops > 0):
        return True
    return any(isinstance(data.get(k), str) and "refus" in data[k].lower()
               for k in ("stop_reason", "subtype", "terminal_reason"))


def counts_against_fable(reason) -> bool:
    return isinstance(reason, str) and (reason == "refused" or reason.startswith("model_mismatch"))


INFRA_EXIT = 3


def is_infra_error(call, data) -> bool:
    """An infrastructure error: the CLI reports a non-null api_error_status, or the call failed (a spawn
    failure, a non-zero exit or is_error) and produced no output tokens. The caller checks for a refusal
    first, so a refusal is never an infra error. A timeout is not one: it counts as a failed attempt."""
    if call.get("timeout"):
        return False
    d = data if isinstance(data, dict) else {}
    if d.get("api_error_status") is not None:
        return True
    failed = bool(call.get("error")) or call.get("returncode") not in (0, None) or bool(d.get("is_error"))
    return failed and not (d.get("usage") or {}).get("output_tokens")


def run_slot(ux, *, stage, key, ident, cell_id, prompt, tools, system_prompt, brief, accept, budget, stop):
    """Up to (max_attempts - earlier failures) attempts. Returns a dict: ok, payload, stopped, usage,
    observed, attempts (total for the slot), cost_usd (all attempts of the slot), reasons (invalid ones)."""
    cell = ux.ctx.cells[cell_id]
    prior = attempts_by_slot(ux).get(key, [])
    out = {"ok": False, "payload": None, "stopped": False, "usage": None, "observed": None,
           "attempts": len(prior), "cost_usd": sum(e.get("cost_usd") or 0.0 for e in prior),
           "reasons": [e["reason"] for e in prior if not e.get("accepted") and not e.get("infra_error")]}
    for _ in range(max(0, ux.max_attempts - failures_of(prior))):
        if budget.exhausted() or stop.event.is_set() or ux.infra_stop.is_set():
            out["stopped"] = True
            return out
        wd = ev.prepare_workdir(ux.workctx, {"delivery": "files", "dir": brief["dir"]}, "ux-")
        try:
            call = ev.call_claude(ux.ctx, cell, prompt, wd, tools, system_prompt, stop)
        finally:
            shutil.rmtree(wd, ignore_errors=True)
        if ev.was_cancelled(call, stop):       # killed by Ctrl-C: not an attempt
            out["stopped"] = True
            return out
        valid, reason, data = ev.parse_call(call, cell["model_id"])
        refused = is_refusal(data)
        if refused:
            valid, reason = False, "refused"
        infra = not refused and is_infra_error(call, data)
        status = data.get("api_error_status") if isinstance(data, dict) else None
        if infra:
            valid, reason = False, reason or f"api_error_status={status}"
        cost, unknown = ev.call_cost(call, data)
        budget.add(cost)
        payload = None
        if valid:
            payload, reason = accept(data.get("result") or "")
            valid = payload is not None
        observed = ",".join(sorted((data or {}).get("modelUsage") or {})) or None
        usage = ev.usage_of(data, cell["model_id"])
        out["attempts"] += 1
        out["cost_usd"] += cost or 0.0
        ev.append_jsonl(ux.attempts, {
            "ts": ev.now(), "slot": key, "stage": stage, **ident, "cell": cell_id,
            "model_expected": cell["model_id"], "model_observed": observed, "attempt": out["attempts"],
            "accepted": valid, "reason": None if valid else reason, "cost_usd": cost,
            "stop_reason": (data or {}).get("stop_reason"), "safety_stops": (data or {}).get("safety_stops"),
            "api_error_status": status, "infra_error": infra,
            **({"cost_unknown": True} if unknown else {}), **usage})
        if valid:
            out.update(ok=True, payload=payload, usage=usage, observed=observed)
            return out
        if infra:
            ux.infra_lines.append(
                f"ux_blind: infra error on {key}: api_error_status {status if status is not None else 'none'} "
                f"({reason}); no new calls were started and this attempt was not counted; "
                "run the same command again when the service is back (exit 3)")
            ux.infra_stop.set()
            out["infra"] = True
            return out
        out["reasons"].append(reason)
    return out


def tools_files(ux) -> str:
    return ux.ctx.harness["runner"]["tools_files"]


# -- design ------------------------------------------------------------------

def accept_design(text, markers):
    block = ev.extract_block(text, markers)
    if block is None:
        return None, "no_answer_block"
    if not block.strip():
        return None, "empty_answer"
    return block, None


def design_one(ux, slot, budget, stop):
    cell_id, brief = ARM_CELL[slot["arm"]], ux.briefs[slot["brief"]]
    label = f"{slot['brief']} {slot['sample']}"
    res = run_slot(ux, stage="design", key=slot_key("design", slot), ident=slot_ident(slot),
                   cell_id=cell_id, prompt=designer_prompt(brief, ux.markers), tools=tools_files(ux),
                   system_prompt=ux.ctx.system_prompt(cell_id), brief=brief, budget=budget, stop=stop,
                   accept=lambda text: accept_design(text, ux.markers))
    if not res["ok"]:
        return label + (" infra error" if res.get("infra") else " stopped" if res["stopped"]
                        else f" left missing after {res['attempts']} attempt(s)")
    flagged = "fable" in ux.ctx.cells[cell_id]["model_id"] and any(
        counts_against_fable(r) for r in res["reasons"])
    ev.write_json_atomic(design_path(ux, slot), {
        "brief": slot["brief"], "arm": slot["arm"], "sample": slot["sample"], "cell": cell_id,
        "design": res["payload"], "usage": res["usage"], "cost_usd": res["cost_usd"],
        "model_observed": res["observed"], "attempts": res["attempts"],
        "attempt_reasons": res["reasons"], "slot_failed": flagged})
    return f"{label} designed in {res['attempts']} attempt(s)"


def slot_ident(slot):
    return {"brief": slot["brief"], "arm": slot["arm"], "sample": slot["sample"]}


def pool_args(ux, args):
    budget = ev.Budget(args.max_usd, ux.per_run_cap)
    return budget, args.jobs or ux.ctx.harness["runner"]["jobs"]


def finish(ux, label, budget, code):
    print(f"{label} cost ${budget.spent:.4f}" +
          (f" ({budget.unknown} call(s) with unknown cost charged at the per-run cap)" if budget.unknown else ""))
    if ux.infra_lines:
        print(ux.infra_lines[0], file=sys.stderr)
        return INFRA_EXIT
    return code


def cmd_design(ux, args):
    ux.need_cells(list(ARM_CELL.values()))
    todo = [s for s in compute_plan(ux)["_designs"]
            if failures_of(attempts_by_slot(ux).get(slot_key("design", s), [])) < ux.max_attempts]
    print(f"{len(todo)} design run(s) to do")
    budget, jobs = pool_args(ux, args)
    code = ev.run_pool(ux.ctx, todo, lambda s, stop: design_one(ux, s, budget, stop), jobs, "design")
    return finish(ux, "design", budget, code)


# -- build -------------------------------------------------------------------

def accept_page(text, markers):
    block = ev.extract_block(text, markers)
    if block is None:
        return None, "no_answer_block"
    page, reasons = sanitize_page(strip_fence(block).strip())
    if page is None:
        return None, "page_invalid: " + "; ".join(reasons)
    return page, None


def new_page_id(taken) -> str:
    while True:
        pid = secrets.token_hex(4)
        if pid not in taken:
            return pid


def store_page(ux, slot, page: str) -> str:
    with STORE_LOCK:
        index = ux.read(ux.pages_json, {})
        for pid, v in index.items():
            if (v["brief"], v["arm"], v["sample"]) == (slot["brief"], slot["arm"], slot["sample"]):
                return pid                                  # already built by another worker
        pid = new_page_id(index)
        ux.pages.mkdir(parents=True, exist_ok=True)
        (ux.pages / f"{pid}.html").write_text(page, encoding="utf-8")
        index[pid] = {"brief": slot["brief"], "arm": slot["arm"], "sample": slot["sample"],
                      "block": slot["block"]}
        ev.write_json_atomic(ux.pages_json, index)
        return pid


def build_one(ux, slot, budget, stop):
    brief, label = ux.briefs[slot["brief"]], f"{slot['brief']} page {slot['sample']}"
    text = None
    if slot["arm"] in ARM_CELL:
        text = ev.read_json(design_path(ux, slot))["design"]
    res = run_slot(ux, stage="build", key=slot_key("build", slot), ident=slot_ident(slot),
                   cell_id=BUILDER_CELL, prompt=builder_prompt(brief, text, ux.markers),
                   tools=tools_files(ux), system_prompt=ux.ctx.system_prompt(BUILDER_CELL), brief=brief,
                   budget=budget, stop=stop, accept=lambda t: accept_page(t, ux.markers))
    if not res["ok"]:
        return label + (" infra error" if res.get("infra") else " stopped" if res["stopped"]
                        else f" left missing after {res['attempts']} attempt(s)")
    store_page(ux, slot, res["payload"])
    return f"{label} built in {res['attempts']} attempt(s)"


def cmd_build(ux, args):
    ux.need_cells([BUILDER_CELL])
    by_slot = attempts_by_slot(ux)
    todo = [s for s in compute_plan(ux)["_builds"]
            if (s["arm"] not in ARM_CELL or design_path(ux, s).exists())
            and failures_of(by_slot.get(slot_key("build", s), [])) < ux.max_attempts]
    print(f"{len(todo)} build(s) to do")
    budget, jobs = pool_args(ux, args)
    code = ev.run_pool(ux.ctx, todo, lambda s, stop: build_one(ux, s, budget, stop), jobs, "build")
    return finish(ux, "build", budget, code)


def cmd_reject(ux, args):
    """Drop one built page (its file, its pages.json entry, its checklist answers) and log ONE counted
    failed build attempt for its slot, so `build` rebuilds it within the same cap. Prints no arm."""
    with STORE_LOCK:
        index = ux.read(ux.pages_json, {})
        if args.page not in index:
            raise ev.EvalError(f"no page {args.page}")
        slot = {**index[args.page]}
        prior = attempts_by_slot(ux).get(slot_key("build", slot), [])
        ev.append_jsonl(ux.attempts, {
            "ts": ev.now(), "slot": slot_key("build", slot), "stage": "build", **slot_ident(slot),
            "cell": BUILDER_CELL, "model_expected": None, "model_observed": None, "attempt": len(prior) + 1,
            "accepted": False, "reason": f"rejected: {args.reason}", "cost_usd": 0.0, "stop_reason": None,
            "safety_stops": None, "api_error_status": None, "infra_error": False,
            "rejected_page": args.page})
        index.pop(args.page)
        ev.write_json_atomic(ux.pages_json, index)
        (ux.pages / f"{args.page}.html").unlink(missing_ok=True)
        checks = ux.read(ux.checklist_json, {})
        if checks.pop(args.page, None) is not None:
            ev.write_json_atomic(ux.checklist_json, checks)
    print(f"rejected page {args.page}: {args.reason}")
    return 0


# -- checklist ---------------------------------------------------------------

def accept_checklist(text, markers, item_ids):
    obj = ev.parse_judgment(text, markers)
    if obj is None:
        return None, "checklist_unparseable: no JSON object between the markers"
    if sorted(obj) != sorted(item_ids) or any(not isinstance(obj[k], bool) for k in item_ids):
        return None, f"checklist_unparseable: need exactly {', '.join(item_ids)} as true or false"
    return {k: obj[k] for k in item_ids}, None


def store_checklist(ux, page_id, judge, answer, item_ids):
    with STORE_LOCK:
        data = ux.read(ux.checklist_json, {})
        entry = data.setdefault(page_id, {"judges": {}})
        entry["judges"][judge] = answer
        credited = page_credited(entry["judges"], item_ids)
        if credited is not None:
            entry["credited"], entry["score"] = credited, len(credited) / len(item_ids)
        ev.write_json_atomic(ux.checklist_json, data)


def checklist_one(ux, unit, budget, stop):
    slot, judge, page_id = unit
    brief = ux.briefs[slot["brief"]]
    ids = [it["id"] for it in brief["checklist"]]
    page = (ux.pages / f"{page_id}.html").read_text(encoding="utf-8")
    res = run_slot(ux, stage="checklist", key=slot_key("checklist", slot, judge),
                   ident={**slot_ident(slot), "judge": judge, "page": page_id}, cell_id=judge,
                   prompt=checklist_prompt(brief, page, ux.markers), tools="",
                   system_prompt=ux.ctx.harness["judge"]["system_prompt"], brief=brief, budget=budget,
                   stop=stop, accept=lambda t: accept_checklist(t, ux.markers, ids))
    label = f"{page_id} {judge}"
    if not res["ok"]:
        return label + (" infra error" if res.get("infra") else " stopped" if res["stopped"]
                        else f" left missing after {res['attempts']} attempt(s)")
    store_checklist(ux, page_id, judge, res["payload"], ids)
    return f"{label} judged in {res['attempts']} attempt(s)"


def cmd_checklist(ux, args):
    ux.need_cells(list(JUDGE_CELLS))
    pages, by_slot, todo = pages_index(ux), attempts_by_slot(ux), []
    for s, judge in compute_plan(ux)["_check"]:
        pid = pages.get((s["brief"], s["arm"], s["sample"]))
        if pid and failures_of(by_slot.get(slot_key("checklist", s, judge), [])) < ux.max_attempts:
            todo.append((s, judge, pid))
    print(f"{len(todo)} checklist call(s) to do")
    budget, jobs = pool_args(ux, args)
    code = ev.run_pool(ux.ctx, todo, lambda u, stop: checklist_one(ux, u, budget, stop), jobs, "checklist")
    return finish(ux, "checklist", budget, code)


# -- pairs and the blind page ------------------------------------------------

def page_ref(arm, sample, index, brief):
    return {"page": index[(brief, arm, sample)], "arm": arm, "sample": sample}


def make_pairs(ux, index) -> dict:
    """The full pair table: 12 pairs F s vs O s (block 1), 12 pairs F s+3 vs D s (block 2), one shuffled
    order and a random side per pair, all drawn from one stored seed."""
    seed = secrets.randbits(64)
    rng = random.Random(seed)
    pairs = []
    for b in ux.briefs:
        for s in (1, 2, 3):
            pairs.append({"block": 1, "brief": b, "a": page_ref("F", s, index, b),
                          "b": page_ref("O", s, index, b)})
            pairs.append({"block": 2, "brief": b, "a": page_ref("F", s + 3, index, b),
                          "b": page_ref("D", s, index, b)})
    rng.shuffle(pairs)
    ids, out = set(), []
    for position, p in enumerate(pairs, 1):
        pid = "%010x" % rng.getrandbits(40)
        while pid in ids:
            pid = "%010x" % rng.getrandbits(40)
        ids.add(pid)
        left, right = (p["a"], p["b"]) if rng.random() < 0.5 else (p["b"], p["a"])
        out.append({"pair": pid, "position": position, "block": p["block"], "brief": p["brief"],
                    "left": left, "right": right})
    return {"version": 1, "seed": seed, "deck": "%012x" % rng.getrandbits(48), "pairs": out}


def required_pages(ux, index):
    missing = [f"{b} {arm} {s}" for b in ux.briefs for arm in SAMPLES for s in SAMPLES[arm]
               if (b, arm, s) not in index]
    if missing:
        raise ev.EvalError(f"{len(missing)} page(s) are not built yet, e.g. {missing[0]}; run `build` first")


def load_or_create_pairs(ux, index) -> dict:
    if ux.pairs_json.exists():
        return ev.read_json(ux.pairs_json)
    required_pages(ux, index)
    table = make_pairs(ux, index)
    ev.write_json_atomic(ux.pairs_json, table)
    return table


def json_for_script(obj) -> str:
    return (json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


BLIND_CSS = """
:root { color-scheme: light dark; --bg: #f6f6f4; --fg: #1d1d1b; --muted: #5d5d58; --line: #c9c9c2;
  --card: #ffffff; --accent: #1f5fbf; --accent-fg: #ffffff; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #ece8e8; --muted: #a2a29a;
  --line: #3d3d39; --card: #20201e; --accent: #6fa3ee; --accent-fg: #0d1a2e; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
  font: 16px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; }
.count { margin: 0; color: var(--muted); font-size: 14px; }
h1 { margin: 4px 0 6px; font-size: 22px; }
.brief { margin: 0 0 12px; max-width: 70ch; }
.bar { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 16px; }
button { font: inherit; padding: 10px 18px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--card); color: var(--fg); cursor: pointer; }
button.choice { border-color: var(--accent); }
button.chosen { background: var(--accent); color: var(--accent-fg); }
button:disabled { opacity: .45; cursor: default; }
.frames { display: flex; gap: 24px; overflow-x: auto; padding-bottom: 12px; justify-content: center; }
figure { margin: 0; flex: none; }
figcaption { font-weight: 600; text-align: center; margin-bottom: 6px; }
iframe { display: block; border: 1px solid var(--line); background: #fff; }
textarea { width: 100%; min-height: 160px; font: 13px/1.4 ui-monospace, Menlo, monospace; }
"""

BLIND_JS = r"""
(function () {
  var deck = JSON.parse(document.getElementById('deck').textContent);
  var pairs = deck.pairs, total = pairs.length, key = 'uxb-' + deck.deck;
  var answers = {}, pos = 0;
  var view = document.getElementById('view');

  function known(id) { for (var i = 0; i < total; i++) { if (pairs[i].id === id) return true; } return false; }
  function load() {
    try {
      var saved = JSON.parse(localStorage.getItem(key) || 'null');
      if (saved && saved.answers) {
        Object.keys(saved.answers).forEach(function (id) {
          if (known(id) && (saved.answers[id] === 'A' || saved.answers[id] === 'B')) answers[id] = saved.answers[id];
        });
      }
    } catch (e) { /* storage may be blocked; answers then live in memory only */ }
    pos = firstOpen();
  }
  function save() {
    try { localStorage.setItem(key, JSON.stringify({ answers: answers })); } catch (e) { /* ignore */ }
  }
  function firstOpen() {
    for (var i = 0; i < total; i++) { if (!answers[pairs[i].id]) return i; }
    return total;
  }
  function results() {
    var list = [];
    pairs.forEach(function (p) { if (answers[p.id]) list.push({ pair: p.id, choice: answers[p.id] }); });
    return { version: 1, answers: list, finished: list.length === total };
  }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function choose(c) { answers[pairs[pos].id] = c; save(); pos += 1; render(); }
  function back() { if (pos > 0) { pos -= 1; render(); } }
  function download() {
    var blob = new Blob([JSON.stringify(results(), null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = el('a', { href: url, download: 'ux-blind-results.json' });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }
  function button(label, cls, fn, disabled) {
    var b = el('button', { type: 'button', 'class': cls || '' }, label);
    if (disabled) b.disabled = true;
    b.addEventListener('click', fn);
    return b;
  }
  function render() {
    view.textContent = '';
    if (pos >= total) { return renderFinal(); }
    var p = pairs[pos], current = answers[p.id];
    view.appendChild(el('p', { 'class': 'count' }, 'Pair ' + (pos + 1) + ' of ' + total));
    view.appendChild(el('h1', {}, p.title));
    view.appendChild(el('p', { 'class': 'brief' }, p.description));
    var bar = el('div', { 'class': 'bar' });
    bar.appendChild(button('Back', '', back, pos === 0));
    bar.appendChild(button('A is better', 'choice' + (current === 'A' ? ' chosen' : ''), function () { choose('A'); }));
    bar.appendChild(button('B is better', 'choice' + (current === 'B' ? ' chosen' : ''), function () { choose('B'); }));
    view.appendChild(bar);
    var frames = el('div', { 'class': 'frames' });
    frames.appendChild(document.getElementById('t-' + p.id).content.cloneNode(true));
    view.appendChild(frames);
  }
  function renderFinal() {
    var r = results();
    view.appendChild(el('p', { 'class': 'count' }, 'All ' + total + ' pairs answered'));
    view.appendChild(el('h1', {}, 'Save your results'));
    view.appendChild(el('p', { 'class': 'brief' },
      'Save the file and send it back. If the download does not start, copy the text below instead.'));
    var bar = el('div', { 'class': 'bar' });
    bar.appendChild(button('Back', '', back, false));
    bar.appendChild(button('Save results', 'choice chosen', download, false));
    view.appendChild(bar);
    var box = el('textarea', { readonly: 'readonly', 'aria-label': 'Results as JSON' });
    box.value = JSON.stringify(r, null, 2);
    view.appendChild(box);
  }
  load();
  render();
})();
"""


def build_blind_html(ux, table) -> str:
    """One offline file: a template per pair holds the two pages as sandboxed srcdoc iframes; only the
    current pair is cloned into the document. Pair ids are opaque; no arm, block, sample or page id."""
    m = VIEWPORT_RE.match
    deck, templates = [], []
    for p in sorted(table["pairs"], key=lambda x: x["position"]):
        brief = ux.briefs[p["brief"]]
        w, h = m(brief["viewport"]).groups()
        deck.append({"id": p["pair"], "title": brief["title"], "description": brief["description"]})
        figures = []
        for label, side in (("A", "left"), ("B", "right")):
            src = (ux.pages / f"{p[side]['page']}.html").read_text(encoding="utf-8")
            figures.append(
                f'<figure><figcaption>{label}</figcaption>'
                f'<iframe title="Page {label}" sandbox="allow-scripts" width="{w}" height="{h}" '
                f'style="width:{w}px;height:{h}px" srcdoc="{html.escape(src, quote=True)}"></iframe></figure>')
        templates.append(f'<template id="t-{p["pair"]}">{"".join(figures)}</template>')
    data = json_for_script({"deck": table["deck"], "pairs": deck})
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Blind comparison</title>\n<style>" + BLIND_CSS + "</style>\n</head>\n<body>\n"
            "<main id=\"view\"></main>\n" + "\n".join(templates)
            + f"\n<script type=\"application/json\" id=\"deck\">{data}</script>\n"
            "<script>" + BLIND_JS + "</script>\n</body>\n</html>\n")


RENDER_CHECK = "render-check.json"


def require_render_check(ux, index):
    """Refuse unless render-check.json exists, is newer than every page file and lists every page as passed."""
    f = ux.root / RENDER_CHECK
    hint = f"run scripts/quality/check_ux_pages.py --root {ux.root} --out {f}"
    if not f.is_file():
        raise ev.EvalError(f"{RENDER_CHECK} is missing; {hint}")
    files = [ux.pages / f"{pid}.html" for pid in index.values()]
    if any(p.is_file() and p.stat().st_mtime_ns >= f.stat().st_mtime_ns for p in files):
        raise ev.EvalError(f"{RENDER_CHECK} is older than a page file; {hint}")
    data = ev.read_json(f)
    entries = data.get("pages") if isinstance(data, dict) and isinstance(data.get("pages"), dict) else {}
    bad = sorted(pid for pid in index.values()
                 if not isinstance(entries.get(pid), dict) or entries[pid].get("passed") is not True)
    if bad:
        raise ev.EvalError(f"the render check did not pass {len(bad)} page(s): " + ", ".join(bad[:5])
                           + (" ..." if len(bad) > 5 else "") + "; reject them with `reject`, rebuild, and check again")


def cmd_page(ux, args):
    index = pages_index(ux)
    required_pages(ux, index)
    require_render_check(ux, index)
    table = load_or_create_pairs(ux, index)
    problems = []
    for p in table["pairs"]:
        for side in ("left", "right"):
            f = ux.pages / f"{p[side]['page']}.html"
            if not f.is_file():
                problems.append(f"{f.name} is missing")
            elif LEAK_WORDS.search(f.read_text(encoding="utf-8")):
                problems.append(f"{f.name} names a model or vendor; rebuild it before the owner sees it")
    if problems:
        raise ev.EvalError("; ".join(problems[:5]) + (f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""))
    out = Path(args.out) if args.out else ux.root / "blind.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_blind_html(ux, table), encoding="utf-8")
    print(f"wrote {out} ({len(table['pairs'])} pairs, {out.stat().st_size // 1024} KB)")
    return 0


# -- verdict -----------------------------------------------------------------

def read_answers(path, table) -> dict:
    """{pair id: "A"|"B"}; refuses unless every pair is answered exactly once and nothing else is."""
    data = ev.read_json(path)
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, list):
        raise ev.EvalError(f"{path}: no `answers` list")
    pair_ids = [p["pair"] for p in table["pairs"]]
    got = {}
    for a in answers:
        pid, choice = (a.get("pair"), a.get("choice")) if isinstance(a, dict) else (None, None)
        if pid not in pair_ids:
            raise ev.EvalError(f"{path}: answer for an unknown pair; no verdict")
        if choice not in ("A", "B"):
            raise ev.EvalError(f"{path}: a choice is neither A nor B; no verdict")
        if pid in got:
            raise ev.EvalError(f"{path}: a pair is answered twice; no verdict")
        got[pid] = choice
    if len(got) != len(pair_ids):
        raise ev.EvalError(f"only {len(got)} of {len(pair_ids)} pairs are answered; no verdict")
    return got


def check_table(table):
    pairs = table.get("pairs", [])
    per_block = [sum(1 for p in pairs if p["block"] == b) for b in (1, 2)]
    if len(pairs) != PAIR_COUNT or per_block != [12, 12]:
        raise ev.EvalError("pairs.json is not 24 pairs with 12 per block; no verdict")


def compute_verdict(ux, table, answers, checklist) -> dict:
    check_table(table)
    wins, left_chosen = {1: 0, 2: 0}, 0
    credited, pages_seen = {"F": 0, "O": 0}, {"F": 0, "O": 0}
    flagged_pairs, counted = {1: 0, 2: 0}, {1: 0, 2: 0}
    ids = [f"K{i}" for i in range(1, N_ITEMS + 1)]
    missing = 0
    for p in table["pairs"]:
        chosen_side = "left" if answers[p["pair"]] == "A" else "right"
        left_chosen += chosen_side == "left"
        f_ref = p["left"] if p["left"]["arm"] == "F" else p["right"]
        d = ux.designs / f"{p['brief']}-F-{f_ref['sample']}.json"
        f_failed = d.exists() and bool(ev.read_json(d).get("slot_failed"))
        flagged_pairs[p["block"]] += f_failed
        if p[chosen_side]["arm"] == "F":
            wins[p["block"]] += 1
            counted[p["block"]] += not f_failed       # section 2: a failed Fable slot is never "preferred"
        for side in ("left", "right"):
            ref = p[side]
            if p["block"] == 1:
                got = page_credited(checklist.get(ref["page"], {}).get("judges", {}), ids)
                if got is None:
                    missing += 1
                else:
                    credited[ref["arm"]] += len(got)
                    pages_seen[ref["arm"]] += 1
    if missing:
        raise ev.EvalError(f"the checklist is incomplete for {missing} block-1 page(s); run `checklist`; no verdict")
    mean_f = Fraction(credited["F"], N_ITEMS * pages_seen["F"])
    mean_o = Fraction(credited["O"], N_ITEMS * pages_seen["O"])
    not_below = mean_f >= mean_o - CHECKLIST_MARGIN
    uq = counted[1] >= RULE_BLOCK_UQ and not_below
    ub = counted[1] >= RULE_BLOCK_UB and not_below
    ud = counted[2] >= RULE_BLOCK_UD
    return {"block1_f_preferred_raw": wins[1], "block1_f_preferred_counted": counted[1],
            "block1_pairs_flagged": flagged_pairs[1], "block1_pairs_changed": wins[1] - counted[1],
            "block2_f_preferred_raw": wins[2], "block2_f_preferred_counted": counted[2],
            "block2_pairs_flagged": flagged_pairs[2], "block2_pairs_changed": wins[2] - counted[2],
            "mean_F": float(mean_f), "mean_O": float(mean_o), "checklist_not_below": not_below,
            "left_chosen": left_chosen, "pairs": len(table["pairs"]),
            "quality_designer": ARM_CELL["F"] if uq else FAST_DESIGNER,
            "balanced_designer": ARM_CELL["F"] if ub else FAST_DESIGNER,
            "fast_designer": FAST_DESIGNER,
            "design_pass_default": ud}


def cmd_verdict(ux, args):
    table = ux.read(ux.pairs_json, None)
    if table is None:
        raise ev.EvalError(f"no pairs.json under {ux.root}; run `page` first")
    answers = read_answers(args.results, table)
    v = compute_verdict(ux, table, answers, ux.read(ux.checklist_json, {}))
    if args.json:
        print(json.dumps(v, indent=2))
        return 0
    for b, name in ((1, "F against O"), (2, "F against D")):
        print(f"block {b} ({name}): F preferred in {v[f'block{b}_f_preferred_counted']} of 12 counted "
              f"({v[f'block{b}_f_preferred_raw']} raw; {v[f'block{b}_pairs_flagged']} pair(s) with a flagged "
              f"Fable slot, {v[f'block{b}_pairs_changed']} changed by it)")
    print(f"mean_F {v['mean_F']:.4f}  mean_O {v['mean_O']:.4f}  "
          f"(F not below O by the 0.05 margin: {'yes' if v['checklist_not_below'] else 'no'})")
    print(f"left page chosen {v['left_chosen']} of {v['pairs']} times (bias check, report only)")
    print(f"UQ (quality): designer {v['quality_designer']}")
    print(f"UB (balanced): designer {v['balanced_designer']}")
    print(f"fast: designer {v['fast_designer']}")
    print("UD (design pass): " + ("a design pass is the default"
                                  if v["design_pass_default"] else
                                  "not a default; available on request, no benefit measured"))
    n1, n2 = v["block1_pairs_changed"], v["block2_pairs_changed"]
    if v["block1_pairs_flagged"] or v["block2_pairs_flagged"]:
        print(f"NOTE: section 2 counts a Fable slot with a refused or wrong-model attempt as failed: "
              f"{n1} block-1 and {n2} block-2 pair(s) the owner chose F in are counted as not preferred. "
              "The rules above use the counted numbers.")
    return 0


# -- CLI ---------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="ux_blind", description=__doc__.split("\n\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="where everything lives (default <evals>/private/ux)")
    common.add_argument("--briefs-dir", help="default <root>/briefs")
    common.add_argument("--evals-dir", help="evals directory (default $AGENTING_EVALS_DIR or this repo's)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, spend=False, lock=None):
        sp = sub.add_parser(name, parents=[common], help=help_, description=help_)
        sp.set_defaults(fn=fn, spends=spend, lock=spend if lock is None else lock)
        if spend:
            sp.add_argument("--max-usd", type=float, help="stop launching calls once this much is spent")
            sp.add_argument("--jobs", type=int, help="parallel workers (default harness runner.jobs)")
        return sp

    sp = add("plan", cmd_plan, "what is missing and a cost bound (no model call)")
    sp.add_argument("--json", action="store_true")
    add("design", cmd_design, "run the designers (arms F and O)", True)
    add("build", cmd_build, "run the builder for every missing page", True)
    add("checklist", cmd_checklist, "both judges score every block-1 page", True)
    sp = add("reject", cmd_reject, "drop one built page so `build` rebuilds it", lock=True)
    sp.add_argument("--page", required=True, help="the page id")
    sp.add_argument("--reason", required=True, help="why (printed back, logged with the failed attempt)")
    sp = add("page", cmd_page, "write the blind HTML file for the owner")
    sp.add_argument("--out", help="default <root>/blind.html")
    sp = add("verdict", cmd_verdict, "apply rules UQ, UB and UD to the owner's results")
    sp.add_argument("--results", required=True)
    sp.add_argument("--json", action="store_true", help="scalar counts, means and verdict words only")
    return p


def main(argv=None, ctx=None):
    args = build_parser().parse_args(argv)
    try:
        ctx = ctx or ev.Ctx(args.evals_dir)
        ux = UX(ctx, args.root or ctx.private / "ux", args.briefs_dir)
        if args.lock:
            with ev.exclusive_lock(ctx.lock_path):
                return args.fn(ux, args)
        return args.fn(ux, args)
    except ev.EvalError as e:
        print(f"ux_blind: error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nux_blind: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
