#!/usr/bin/env python3
"""Apply scenario→test mappings to the Gherkin catalogue.

Input: a JSON file (argv[1]) with a list of objects:
    {"scenario": "<exact title>", "feature_file": "chat.feature",
     "backed_by": "tests/test_chat.py::test_x"}

For each mapping, finds `Scenario:`/`Scenario Outline: <title>` in
<FEATURES_DIR>/<feature_file>, rewrites the `# Backed by:` comment in the
tag/comment block above it, and removes the `@gap` tag. Prints a summary; exits
non-zero if any mapping could not be applied (a typo'd title is loud, not
silent). Idempotent. Run build_coverage_matrix.py afterwards.

Used by the gap-fill loop: implementation agents return mappings AS DATA and
this script applies them deterministically — never let parallel agents
hand-edit shared feature files.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── EDIT ME per project ──────────────────────────────────────────────────────
# Repo root, assuming this file sits at <root>/scripts/quality/.
ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "features"
# ─────────────────────────────────────────────────────────────────────────────

SCEN_RE = re.compile(r"^(\s*)Scenario(?: Outline)?:\s*(.+?)\s*$")
STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But|Examples|Feature|Background)\b")
TAG_RE = re.compile(r"^\s*@")
BACKED_RE = re.compile(r"^(\s*)#\s*Backed by:.*$")


def apply_one(lines: list[str], title: str, backed_by: str) -> bool:
    for i, ln in enumerate(lines):
        m = SCEN_RE.match(ln)
        if not m or m.group(2) != title:
            continue
        indent = m.group(1)
        block_start = i
        j = i - 1
        while j >= 0 and (i - j) <= 8:
            prev = lines[j]
            if STEP_RE.match(prev) or SCEN_RE.match(prev) or prev.strip() == "":
                break
            block_start = j
            j -= 1
        replaced = False
        for k in range(block_start, i):
            if BACKED_RE.match(lines[k]):
                lines[k] = f"{indent}# Backed by: {backed_by}"
                replaced = True
            if TAG_RE.match(lines[k]):
                cleaned = re.sub(r"\s*@gap\b", "", lines[k]).rstrip()
                lines[k] = cleaned if cleaned.strip() else lines[k]
        if not replaced:
            lines.insert(i, f"{indent}# Backed by: {backed_by}")
        return True
    return False


def main() -> int:
    mappings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    by_file: dict[str, list[dict]] = {}
    for m in mappings:
        by_file.setdefault(m["feature_file"], []).append(m)

    misses: list[tuple[str, str]] = []
    applied = 0
    for fname, items in sorted(by_file.items()):
        path = FEATURES / fname
        if not path.is_file():
            misses.extend((fname, m["scenario"]) for m in items)
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        changed = False
        for m in items:
            if apply_one(lines, m["scenario"], m["backed_by"]):
                applied += 1
                changed = True
            else:
                misses.append((fname, m["scenario"]))
        if changed:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"applied {applied}/{len(mappings)} mappings across {len(by_file)} files")
    if misses:
        print("MISSES (title not found — fix and re-run):")
        for fname, title in misses:
            print(f"  [{fname}] {title}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
