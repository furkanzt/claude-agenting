#!/usr/bin/env python3
"""Render check for built UX pages: do they load and show something before the owner sees them?

    python3 scripts/quality/check_ux_pages.py [--root DIR] [--json] [--out FILE]

For every <root>/pages/<page_id>.html it loads the page in headless Chromium inside the same kind of frame
the blind file uses (a wrapper document with one <iframe sandbox="allow-scripts" srcdoc=...> at 390x780),
waits for load plus 1.5 seconds, and records, per page id:

  - uncaught script errors on load (count and the first message, cut to 120 characters);
  - whether the frame rendered anything: visible text length of its body, and counts of canvas, svg, img;
  - one click on the first visible button or link, and the uncaught errors that click raised.

A page FAILS when it has an uncaught error on load or on that first click, or when it rendered nothing
(visible text under 20 characters and no canvas, svg or img).

It works by page id only: it reads the page files and nothing else under the root, so whoever runs it
stays blind to which arm built which page. Headless, muted, offline; the browser is always closed.
--out FILE writes the result as JSON (scalar values only per page); `ux_blind.py page` needs that file
(<root>/render-check.json), newer than every page, with every page passed.

Playwright for Python (pip package `playwright`, driving its own Chromium) is imported only when a check
runs, so the pure helpers can be tested without a browser.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / "evals" / "private" / "ux"
VIEWPORT = (390, 780)
SETTLE_MS = 1500            # after load, before looking at the frame
AFTER_CLICK_MS = 400
MIN_TEXT = 20               # visible characters below which (with no canvas, svg or img) a page is blank
MAX_MESSAGE = 120
MUTE_JS = Path.home() / ".claude" / "browser-check" / "mute.js"

MEASURE_JS = """() => {
  const b = document.body;
  return {text: b ? (b.innerText || '').trim().length : 0,
          canvas: document.querySelectorAll('canvas').length,
          svg: document.querySelectorAll('svg').length,
          img: document.querySelectorAll('img').length};
}"""


def wrapper_html(page_source: str) -> str:
    """The frame the owner will see: one sandboxed srcdoc iframe at the phone viewport."""
    import html
    w, h = VIEWPORT
    return ("<!doctype html><html><head><meta charset=\"utf-8\"></head><body style=\"margin:0\">"
            f'<iframe sandbox="allow-scripts" width="{w}" height="{h}" style="width:{w}px;height:{h}px;border:0" '
            f'srcdoc="{html.escape(page_source, quote=True)}"></iframe></body></html>')


def judge_page(stats: dict):
    """(passed, reasons) from the scalar stats of one page."""
    reasons = []
    if stats["load_errors"] > 0:
        reasons.append("uncaught error on load")
    if stats["click_errors"] > 0:
        reasons.append("uncaught error on first click")
    if stats["text_length"] < MIN_TEXT and stats["canvas"] + stats["svg"] + stats["img"] == 0:
        reasons.append("rendered nothing")
    return not reasons, reasons


def build_report(pages: dict) -> dict:
    failed = sorted(pid for pid, st in pages.items() if not st["passed"])
    return {"version": 1, "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "viewport": f"{VIEWPORT[0]}x{VIEWPORT[1]}", "pages": pages,
            "checked": len(pages), "failed": len(failed), "all_passed": not failed and bool(pages)}


def short(message: str) -> str:
    return " ".join(str(message).split())[:MAX_MESSAGE]


def check_one(context, source: str) -> dict:
    """Load one page in the wrapper frame and measure it. Scalars only."""
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(short(getattr(e, "message", None) or e)))
    page.on("dialog", lambda d: d.dismiss())
    stats = {"load_errors": 0, "first_load_error": "", "click_errors": 0, "first_click_error": "",
             "clicked": False, "text_length": 0, "canvas": 0, "svg": 0, "img": 0}
    try:
        page.set_content(wrapper_html(source), wait_until="load")
        page.wait_for_timeout(SETTLE_MS)
        stats["load_errors"], stats["first_load_error"] = len(errors), errors[0] if errors else ""
        element = page.query_selector("iframe")
        frame = element.content_frame() if element else None
        if frame is not None:
            m = frame.evaluate(MEASURE_JS)
            stats.update(text_length=m["text"], canvas=m["canvas"], svg=m["svg"], img=m["img"])
            target = frame.locator("button:visible, a:visible").first
            if target.count() > 0:
                before = len(errors)
                try:
                    target.click(timeout=2000)
                    stats["clicked"] = True
                except Exception:       # a click that cannot be made is not an uncaught page error
                    pass
                page.wait_for_timeout(AFTER_CLICK_MS)
                new = errors[before:]
                stats["click_errors"], stats["first_click_error"] = len(new), new[0] if new else ""
    finally:
        page.close()
    stats["passed"], reasons = judge_page(stats)
    stats["reasons"] = "; ".join(reasons)
    return stats


def check_ux_pages_render(root, out_path=None) -> dict:
    """Check every <root>/pages/<page_id>.html; returns the report (see build_report) and, with out_path,
    writes it there. Only page files are read."""
    from playwright.sync_api import sync_playwright
    pages_dir = Path(root) / "pages"
    sources = {f.stem: f.read_text(encoding="utf-8") for f in sorted(pages_dir.glob("*.html"))}
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--mute-audio"])
        try:
            context = browser.new_context(viewport={"width": 900, "height": 900}, service_workers="block")
            if MUTE_JS.is_file():
                context.add_init_script(path=str(MUTE_JS))
            context.set_offline(True)
            for page_id, source in sources.items():
                results[page_id] = check_one(context, source)
        finally:
            browser.close()
    report = build_report(results)
    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(f"{out}.tmp{os.getpid()}")
        tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, out)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render check for built UX pages (by page id only).")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help=f"default {DEFAULT_ROOT}")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--out", help="also write the JSON report here (ux_blind.py page wants <root>/render-check.json)")
    args = ap.parse_args(argv)
    if not any((Path(args.root) / "pages").glob("*.html")):
        print(f"check_ux_pages: no pages under {Path(args.root) / 'pages'}", file=sys.stderr)
        return 2
    report = check_ux_pages_render(args.root, args.out)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for pid, st in report["pages"].items():
            print(f"{pid} {'PASS' if st['passed'] else 'FAIL'} text={st['text_length']} canvas={st['canvas']} "
                  f"svg={st['svg']} img={st['img']} load_errors={st['load_errors']} "
                  f"click_errors={st['click_errors']} clicked={st['clicked']}"
                  + (f"  [{st['reasons']}]" if st["reasons"] else "")
                  + (f"  first error: {st['first_load_error'] or st['first_click_error']}"
                     if st["first_load_error"] or st["first_click_error"] else ""))
        print(f"{report['checked']} page(s) checked, {report['failed']} failed")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
