"""Self-enforcement of the BDD catalogue — the meta-guard.

The TDD/BDD discipline (TDD.md, BDD.md) only survives if it is machine-checked:
this test fails CI whenever the catalogue and reality drift apart. For every
features/*.feature file it enforces:

1. VALID GHERKIN — parseable by the official parser (skipped gracefully if the
   `gherkin-official` package isn't installed).
2. FULL TRACEABILITY — every scenario carries a "# Backed by:" comment naming
   its executable proof, or is explicitly tagged @gap AND @wip (the
   work-in-progress escape hatch). A bare @gap cannot be committed.
3. REAL REFERENCES — every unit/loop ref points at an existing file, and a
   ::name ref at a real function in it; every file>title ref at an existing
   file. A renamed/deleted test breaks the build, not the promise ledger.
4. FRESH MATRIX — the committed coverage-matrix totals match a live recount
   (regenerate with the matrix builder).

The checker functions are pure so the guard itself is testable: the synthetic
red-path tests below prove each rule actually bites.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── EDIT ME per project ──────────────────────────────────────────────────────
# Repo root, assuming this file sits at <root>/tests/.
ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "features"
# Refs resolved as <file>::<function> (file must exist; "def <function>" must
# appear in it). Include your unit-test dirs AND your quality-loop check dirs.
UNIT_REF_PREFIXES: tuple[str, ...] = ("tests/", "scripts/quality/")
# Refs resolved as "<file> > <test title>" (only the file part is checked) —
# the Vitest/Jest style. Empty tuple if the project has no JS tests.
FILE_TITLE_REF_PREFIXES: tuple[str, ...] = ()
# Where the generated matrix lives + the builder that regenerates it.
MATRIX_PATH = ROOT / "docs" / "scenarios" / "coverage-matrix.md"
MATRIX_BUILDER = ROOT / "scripts" / "quality" / "build_coverage_matrix.py"
REGEN_CMD = "python3 scripts/quality/build_coverage_matrix.py"
# Feature files excluded from the matrix count (must mirror the builder).
EXCLUDE_FILES: set[str] = set()
# ─────────────────────────────────────────────────────────────────────────────

_ALL_PREFIXES = UNIT_REF_PREFIXES + FILE_TITLE_REF_PREFIXES

SCEN_RE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+?)\s*$")
STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But|Examples|Feature|Background)\b")
TAG_RE = re.compile(r"^\s*@")
BACKED_RE = re.compile(r"#\s*Backed by:\s*(.+?)\s*$")


# ── pure checkers ────────────────────────────────────────────────────────────

def scenarios_with_metadata(text: str) -> list[dict]:
    """Parse a feature text into [{title, tags, backed}] using the same
    walk-up-the-comment-block convention as the matrix builder."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        m = SCEN_RE.match(ln)
        if not m:
            continue
        tags: list[str] = []
        backed_parts: list[str] = []
        j = i - 1
        while j >= 0 and (i - j) <= 8:
            prev = lines[j]
            if STEP_RE.match(prev) or SCEN_RE.match(prev):
                break
            if TAG_RE.match(prev):
                tags = re.findall(r"@[\w:-]+", prev) + tags
            b = BACKED_RE.search(prev)
            if b:
                backed_parts.insert(0, b.group(1))
            j -= 1
        # Aggregate ALL stacked Backed-by lines (dropping any would hide a
        # citation from validation); dedupe identical repeats.
        seen: list[str] = []
        for part in backed_parts:
            if part not in seen:
                seen.append(part)
        out.append({"title": m.group(1), "tags": tags, "backed": ", ".join(seen) or None})
    return out


def traceability_violations(text: str) -> list[str]:
    """Rule 2: every scenario is backed, or explicitly @gap AND @wip."""
    problems = []
    for s in scenarios_with_metadata(text):
        backed = (s["backed"] or "").strip()
        is_gap = "@gap" in s["tags"] or not backed or backed.lower().startswith("@gap")
        if not is_gap:
            continue
        if "@wip" in s["tags"]:
            continue  # sanctioned work-in-progress
        problems.append(s["title"])
    return problems


def _split_refs(backed: str) -> list[str]:
    """Split a Backed-by value into refs. Commas separate refs ONLY when the
    next segment starts a new known path prefix — file>title test titles may
    legitimately contain commas."""
    refs: list[str] = []
    for seg in backed.split(","):
        seg = seg.strip()
        if not seg:
            continue
        if seg.startswith(_ALL_PREFIXES) or not refs:
            refs.append(seg)
        else:
            refs[-1] += ", " + seg
    return refs


def reference_violations(text: str, root: Path) -> list[str]:
    """Rule 3: refs resolve to real files (and real functions for :: refs)."""
    problems = []
    for s in scenarios_with_metadata(text):
        backed = (s["backed"] or "").strip()
        if not backed or backed.lower().startswith("@gap"):
            continue
        for ref in _split_refs(backed):
            if FILE_TITLE_REF_PREFIXES and ref.startswith(FILE_TITLE_REF_PREFIXES):
                if not (root / ref.split(" > ")[0]).is_file():
                    problems.append(f"{s['title']} -> {ref}")
            elif ref.startswith(UNIT_REF_PREFIXES):
                base = ref.split(" ")[0]
                fpath = root / base.split("::")[0]
                if not fpath.is_file():
                    problems.append(f"{s['title']} -> {ref}")
                    continue
                if "::" in base:
                    func = base.split("::", 1)[1].split("[")[0]
                    if f"def {func}" not in fpath.read_text(encoding="utf-8"):
                        problems.append(f"{s['title']} -> {ref} (no such test function)")
            else:
                problems.append(f"{s['title']} -> unrecognized ref '{ref}'")
    return problems


# ── the guard bites: synthetic red-path proofs ───────────────────────────────

_BAD_UNBACKED = """Feature: X
  Scenario: has no backing at all
    Given a
    When b
    Then c
"""

_BAD_BARE_GAP = """Feature: X
  @gap
  # Backed by: @gap
  Scenario: committed gap without wip
    Given a
    When b
    Then c
"""

_OK_WIP_GAP = _BAD_BARE_GAP.replace("@gap", "@gap @wip", 1)

_BAD_REF = """Feature: X
  # Backed by: tests/test_does_not_exist.py::test_nope
  Scenario: cites a ghost test
    Given a
    When b
    Then c
"""

_STACKED = """Feature: X
  # Backed by: tests/test_does_not_exist.py::test_nope
  # Backed by: tests/test_also_missing.py::test_gone
  Scenario: stacked citations
    Given a
    When b
    Then c
"""


def test_guard_flags_unbacked_scenario():
    assert traceability_violations(_BAD_UNBACKED) == ["has no backing at all"]


def test_guard_flags_bare_gap_but_allows_wip():
    assert traceability_violations(_BAD_BARE_GAP) == ["committed gap without wip"]
    assert traceability_violations(_OK_WIP_GAP) == []


def test_guard_flags_ghost_reference(tmp_path):
    assert reference_violations(_BAD_REF, tmp_path) == [
        "cites a ghost test -> tests/test_does_not_exist.py::test_nope"
    ]


def test_stacked_backed_by_lines_are_all_validated(tmp_path):
    # Both stacked citations must surface — recording only the nearest would
    # let a ghost ref hide behind a valid one.
    assert len(reference_violations(_STACKED, tmp_path)) == 2


def test_split_refs_keeps_commas_inside_test_titles():
    if not FILE_TITLE_REF_PREFIXES:
        pytest.skip("project has no file>title refs")
    p = FILE_TITLE_REF_PREFIXES[0]
    assert _split_refs(
        f"{p}a.test.ts > offers a Lightbox, never inline, "
        f"tests/test_b.py::test_x, {p}c.test.ts > grows (1499/1, 2999/1)"
    ) == [
        f"{p}a.test.ts > offers a Lightbox, never inline",
        "tests/test_b.py::test_x",
        f"{p}c.test.ts > grows (1499/1, 2999/1)",
    ]


# ── the real catalogue passes ────────────────────────────────────────────────

def _feature_files() -> list[Path]:
    files = sorted(FEATURES.glob("*.feature"))
    assert files, "features/ directory is empty — the catalogue is gone?"
    return files


@pytest.mark.parametrize("path", _feature_files(), ids=lambda p: p.name)
def test_feature_parses_as_valid_gherkin(path: Path):
    gherkin = pytest.importorskip("gherkin", reason="gherkin-official not installed")
    from gherkin.parser import Parser  # noqa: F401
    from gherkin.token_scanner import TokenScanner

    Parser().parse(TokenScanner(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", _feature_files(), ids=lambda p: p.name)
def test_every_scenario_is_backed_or_sanctioned_wip(path: Path):
    problems = traceability_violations(path.read_text(encoding="utf-8"))
    assert not problems, (
        f"{path.name}: scenarios without an executable proof (add the test and "
        f"a '# Backed by:' line, or tag @gap @wip while developing): {problems}"
    )


@pytest.mark.parametrize("path", _feature_files(), ids=lambda p: p.name)
def test_every_backed_by_reference_is_real(path: Path):
    problems = reference_violations(path.read_text(encoding="utf-8"), ROOT)
    assert not problems, (
        f"{path.name}: stale/ghost 'Backed by' refs (did a test get renamed? "
        f"fix the ref or re-run apply_backed_by.py): {problems}"
    )


def test_coverage_matrix_is_fresh():
    """The committed matrix totals must match a live recount of features/."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_coverage_matrix", MATRIX_BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    total = armed = 0
    for path in _feature_files():
        if path.name in EXCLUDE_FILES:
            continue
        _, scenarios = mod.parse_feature(str(path))
        total += len(scenarios)
        armed += sum(1 for s in scenarios if s["status"] == "ARMED")

    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    m = re.search(r"\*\*(\d+) scenarios\*\* — \*\*(\d+) ARMED\*\*", matrix)
    assert m, "coverage-matrix.md summary line not found — regenerate it"
    assert (int(m.group(1)), int(m.group(2))) == (total, armed), (
        f"coverage-matrix.md is stale (says {m.group(1)}/{m.group(2)} ARMED, "
        f"recount is {total}/{armed}) — run: {REGEN_CMD}"
    )
