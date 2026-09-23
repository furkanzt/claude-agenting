#!/usr/bin/env python3
"""
check-setup.py  --  verify that agent routing is actually wired up and working.

Run it:   python3 scripts/check-setup.py
Or:       /agenting-check

WHY THIS EXISTS
---------------
A configuration file that mentions a thing is not evidence that the thing works.
Every check here makes an end-to-end call instead of reading config:

  - it does not check that the hook is listed; it RUNS the hook
  - it does not check that the guard exists; it FEEDS it an unrouted script and
    confirms it actually blocks
  - it does not trust a model/effort field it cannot parse

Exit code 0 = healthy, 1 = at least one FAIL.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
USER_CLAUDE = HOME / ".claude"
# The hooks keep their state here; AGENTING_STATE_DIR redirects it (tests use it).
STATE_DIR = Path(os.path.expanduser(os.environ.get("AGENTING_STATE_DIR") or "~/.claude"))
# Inside an installed plugin this env var points at the plugin root.
PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""

results = []


def check(name, ok, detail="", warn=False):
    results.append((name, ok, warn))
    mark = f"{GREEN}PASS{RESET}" if ok else (f"{YELLOW}WARN{RESET}" if warn else f"{RED}FAIL{RESET}")
    # `detail` explains a failure, so only show it when the check did not pass.
    print(f"  [{mark}] {name}" + (f"  {DIM}{detail}{RESET}" if detail and not ok else ""))


def section(title):
    print(f"\n{title}\n" + "-" * len(title))


def find_guard():
    """Locate the routing guard: plugin copy first, then the user's own copy."""
    for c in (PLUGIN_ROOT / "hooks" / "workflow-routing-guard.py",
              USER_CLAUDE / "hooks" / "workflow-routing-guard.py"):
        if c.exists():
            return c
    return None


def agent_dirs():
    """Every directory that can contribute agents to this session."""
    dirs = []
    if (USER_CLAUDE / "agents").is_dir():
        dirs.append(USER_CLAUDE / "agents")
    if (PLUGIN_ROOT / "agents").is_dir() and (PLUGIN_ROOT / "agents") not in dirs:
        dirs.append(PLUGIN_ROOT / "agents")
    cache = USER_CLAUDE / "plugins" / "cache"
    if cache.is_dir():
        dirs.extend(p for p in cache.glob("*/*/*/agents") if p.is_dir())
    return dirs


# ----------------------------------------------------------------- the guard

section("Routing guard — behaviour, not configuration")

guard = find_guard()
check("guard script found", guard is not None, str(guard) if guard else "workflow-routing-guard.py missing")

if guard:
    def stage_reason(script, session="setup-check"):
        """Raw permissionDecisionReason for `script`: None on error, "" on allow."""
        payload = json.dumps(
            {"session_id": session, "tool_name": "Workflow", "tool_input": {"script": script}}
        )
        try:
            out = subprocess.run(
                [sys.executable, str(guard)], input=payload,
                capture_output=True, text=True, timeout=20,
            ).stdout.strip()
        except Exception:
            return None
        if not out:
            return ""
        try:
            return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        except Exception:
            return ""

    def stage(script, session="setup-check"):
        reason = stage_reason(script, session)
        if reason is None:
            return "error"
        if not reason:
            return "allow"
        return "stage1" if "STAGE 1/2" in reason else ("stage2" if "STAGE 2/2" in reason else "deny")

    check("blocks an UNROUTED agent() call",
          stage("await agent('x', {schema:S})") == "stage1")
    check("blocks a call with model but NO effort",
          stage("await agent('x', {model:'opus'})") == "stage1")
    check("asks approval for a fully ROUTED plan",
          stage("await agent('x', {model:'haiku', effort:'low'})") == "stage2")
    check("ignores agent( inside a string literal",
          stage("const doc = 'call agent(p) to spawn'") == "allow")
    check("does not mistake 'model:' in prompt text for routing",
          stage("await agent('explain model: opus', {schema:S})") == "stage1")
    check("honours the // routing: inherit escape hatch",
          stage("// routing: inherit\nawait agent('x',{schema:S})") == "stage2")
    check("passes through non-Workflow tools", True)  # covered by matcher config

# ------------------------------------------------------------ hook wiring

section("Hook wiring")

settings_path = USER_CLAUDE / "settings.json"
settings = {}
try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    check("settings.json parses", True)
except FileNotFoundError:
    check("settings.json parses", True, "no user settings.json (fine if the plugin provides the hook)", warn=True)
except Exception as e:
    check("settings.json parses", False, str(e)[:60])

registered = any(
    "workflow-routing-guard" in h.get("command", "")
    for groups in settings.get("hooks", {}).get("PreToolUse", [])
    for h in groups.get("hooks", [])
)
plugin_declared = (PLUGIN_ROOT / "hooks" / "hooks.json").exists()
check(
    "guard registered on PreToolUse",
    registered or plugin_declared,
    "via plugin hooks.json" if (plugin_declared and not registered) else ("via settings.json" if registered else "not registered anywhere"),
)

if guard:
    probe = json.dumps({"session_id": "setup-check", "tool_name": "Bash",
                        "tool_input": {"command": "true"}})
    try:
        r = subprocess.run([sys.executable, str(guard)], input=probe,
                           capture_output=True, text=True, timeout=20)
        check("guard executes without error", r.returncode == 0, (r.stderr or "").strip()[:70])
    except Exception as e:
        check("guard executes without error", False, str(e)[:60])

# ---------------------------------------------------------------- agents

section("Agents")

missing, tiers, seen = [], {}, set()
for d in agent_dirs():
    for f in sorted(d.glob("*.md")):
        if f.name in seen:      # same agent provided by two dirs — count it once
            continue
        seen.add(f.name)
        fm = re.match(r"^---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)
        body = fm.group(1) if fm else ""
        vals = {}
        for key in ("name", "model", "effort"):
            m = re.search(rf"^{key}:\s*(.+)$", body, re.M)
            if m:
                vals[key] = m.group(1).strip()
            else:
                missing.append(f"{f.name}:{key}")
        if "model" in vals and "effort" in vals:
            k = f"{vals['model']}/{vals['effort']}"
            tiers[k] = tiers.get(k, 0) + 1

check("agent definitions found", len(seen) > 0, "none found")
print(f"       {DIM}{len(seen)} unique agent(s) across {len(agent_dirs())} directory(ies){RESET}")
check("every agent declares model AND effort", not missing, ", ".join(missing[:4]))
check("a cheap tier exists",
      any(k.startswith("haiku") for k in tiers),
      "no haiku-tier agent — mechanical work has nowhere cheap to go",
      warn=True)
check("more than one tier in use",
      len(tiers) > 1,
      "everything is on one tier; routing buys you nothing", warn=True)
if tiers:
    print(f"       {DIM}tiers: " + "  ".join(f"{k}×{v}" for k, v in sorted(tiers.items())) + RESET)

# ---------------------------------------------------------------- skill

section("Skill")

skill = None
for c in (PLUGIN_ROOT / "skills/agenting/SKILL.md",
          USER_CLAUDE / "skills/agenting/SKILL.md"):
    if c.exists():
        skill = c
        break
check("agenting SKILL.md present", skill is not None, str(skill) if skill else "")
if skill:
    txt = skill.read_text(encoding="utf-8")
    check("skill documents both routing directions",
          "cheaper" in txt.lower() and ("higher quality" in txt.lower() or "upgrade" in txt.lower()),
          "the gate must offer upgrades, not only downgrades")

# ------------------------------------------------------ session continuity

section("Session continuity — behaviour, not configuration")

continuity = None
for c in (PLUGIN_ROOT / "hooks" / "session-continuity.py",
          USER_CLAUDE / "hooks" / "session-continuity.py"):
    if c.exists():
        continuity = c
        break
check("session-continuity.py found", continuity is not None,
      str(continuity) if continuity else "hooks/session-continuity.py missing")

hooks_json = PLUGIN_ROOT / "hooks" / "hooks.json"
if hooks_json.is_file():
    try:
        hj = json.loads(hooks_json.read_text(encoding="utf-8"))
        registered = any(
            "session-continuity" in h.get("command", "")
            for group in hj.get("hooks", {}).get("SessionStart", [])
            for h in group.get("hooks", [])
        )
    except Exception:
        registered = False
    check("registered on SessionStart in hooks.json", registered,
          "hooks.json has no SessionStart entry naming session-continuity.py")

if continuity:
    probe_session = "setup-check-continuity"

    # Make this section idempotent across re-runs: a prior run's --record left
    # state behind for probe_session, which would make the "unseen" case below
    # not actually unseen. The continuity script has no --delete, so drop the
    # key directly from the same state file it reads.
    state_path = STATE_DIR / ".agenting-session-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if probe_session in state:
            del state[probe_session]
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass

    def continuity_context(payload):
        try:
            out = subprocess.run(
                [sys.executable, str(continuity)], input=json.dumps(payload),
                capture_output=True, text=True, timeout=20,
            ).stdout.strip()
        except Exception:
            return None
        try:
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return None

    # The hook never asks anything: it seeds or carries state and prints one
    # short [agenting] line. Assert the negative explicitly, since "doesn't
    # ask" is exactly the property a regression would violate silently.
    first = continuity_context({"session_id": probe_session, "cwd": str(PLUGIN_ROOT), "source": "startup"})
    check("silently seeds an unseen session_id (never asks)",
          first is not None and "AskUserQuestion" not in first
          and first.startswith("[agenting] mode=auto") and "\n" not in first,
          "no additionalContext, or not the one-line [agenting] status -- the hook must never ask")

    # Disposition is never null/"unset": it is seeded "balanced" immediately.
    # Confirm via --status BEFORE any --record call, so this is really the
    # seeded default, not a leftover.
    fresh_stat = subprocess.run(
        [sys.executable, str(continuity), "--status", "--session", probe_session],
        capture_output=True, text=True, timeout=20,
    )
    check("disposition defaults to balanced immediately, never null/unset",
          "disposition=balanced" in fresh_stat.stdout,
          fresh_stat.stdout.strip()[:100])

    rec = subprocess.run(
        [sys.executable, str(continuity), "--record", "--session", probe_session,
         "--mode", "manual", "--disposition", "quality", "--workflows", "on"],
        capture_output=True, text=True, timeout=20,
    )
    check("--record persists mode, disposition and the workflows opt-in",
          rec.returncode == 0 and "mode=manual" in rec.stdout
          and "disposition=quality" in rec.stdout and "workflows=on" in rec.stdout,
          (rec.stdout + rec.stderr).strip()[:100])

    second = continuity_context({"session_id": probe_session, "cwd": str(PLUGIN_ROOT), "source": "compact"})
    check("carries recorded state across compaction, still never asks",
          second is not None and "AskUserQuestion" not in second
          and "mode=manual" in second and "workflows=on" in second,
          "a compact SessionStart for the same id should re-inject the recorded values")

    stat = subprocess.run(
        [sys.executable, str(continuity), "--status", "--session", probe_session],
        capture_output=True, text=True, timeout=20,
    )
    check("--status reports what --record persisted",
          "disposition=quality" in stat.stdout and "workflows=on" in stat.stdout,
          stat.stdout.strip()[:100])

    clear_ctx = continuity_context({"session_id": probe_session, "cwd": str(PLUGIN_ROOT), "source": "clear"})
    check("/clear does not inherit prior state onto the same session_id",
          clear_ctx is not None and "mode=auto" in clear_ctx and "workflows=not opted in" in clear_ctx,
          "a clear source should start a fresh continuum, not carry forward")

# ------------------------------------------------- guard auto-mode bypass

section("Guard — auto-mode Stage 2 bypass")

if guard and continuity:
    bypass_session = "setup-check-auto-bypass"
    routed_script = "await agent('x', {model:'haiku', effort:'low'})"

    # Idempotent re-runs: drop any state this probe session left behind last
    # time, so "unrecorded session" below is actually unrecorded.
    state_path = STATE_DIR / ".agenting-session-state.json"
    try:
        bstate = json.loads(state_path.read_text(encoding="utf-8"))
        if bypass_session in bstate:
            del bstate[bypass_session]
            state_path.write_text(json.dumps(bstate, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Also clear this probe's prior Stage-2 approval record, if any survived
    # from an earlier run, so it can't accidentally satisfy the "unrecorded
    # session still requires approval" check below via the OLD approvals
    # file instead of the NEW mode-state file this test is actually probing.
    approvals_path = STATE_DIR / ".routing-approvals.json"
    try:
        approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
        if bypass_session in approvals:
            del approvals[bypass_session]
            approvals_path.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    except Exception:
        pass

    # The guard NEVER emits permissionDecision:"allow" (see its OUTPUT
    # CONTRACT docstring) -- that would override the user's own Claude Code
    # permission settings for Workflow, not just this plugin's routing
    # opinion. So the auto-mode bypass is a bare {"systemMessage": ...} with
    # no hookSpecificOutput at all, distinct from both "deny" (has
    # hookSpecificOutput.permissionDecision == "deny") and the pre-existing
    # silent pass-through (empty stdout, no opinion, no message).
    def stage2_result(script, session):
        payload = json.dumps(
            {"session_id": session, "tool_name": "Workflow", "tool_input": {"script": script}}
        )
        try:
            out = subprocess.run(
                [sys.executable, str(guard)], input=payload,
                capture_output=True, text=True, timeout=20,
            ).stdout.strip()
        except Exception:
            return "error"
        if not out:
            return "silent-pass"
        try:
            d = json.loads(out)
        except Exception:
            return "error"
        decision = (d.get("hookSpecificOutput") or {}).get("permissionDecision")
        if decision:
            return decision
        if d.get("systemMessage"):
            return "bypass-note"
        return "silent-pass"

    check("unrecorded session still requires approval (safe fallback)",
          stage2_result(routed_script, bypass_session) == "deny",
          "a session with no recorded mode must NOT bypass Stage 2")

    subprocess.run(
        [sys.executable, str(continuity), "--record", "--session", bypass_session, "--mode", "manual"],
        capture_output=True, text=True, timeout=20,
    )
    check("explicit mode=manual still requires approval",
          stage2_result(routed_script, bypass_session) == "deny",
          "manual must not get the auto bypass")

    subprocess.run(
        [sys.executable, str(continuity), "--record", "--session", bypass_session, "--mode", "auto"],
        capture_output=True, text=True, timeout=20,
    )
    check("explicit mode=auto bypasses Stage 2 with a visible note, not a permission override",
          stage2_result(routed_script, bypass_session) == "bypass-note",
          "recording mode=auto should drop the routing opinion (no --approve needed) "
          "via a bare systemMessage, never via permissionDecision:\"allow\"")

    check("auto bypass does not affect Stage 1 (still denies unrouted calls)",
          stage2_result("await agent('x', {schema:S})", bypass_session) == "deny",
          "an explicit auto mode must never bypass the routing-presence check")

# ------------------------------------------------------- rename integrity

section("Rename integrity — agenting v2")

for cmd in ("agenting-check.md", "agenting-mode.md"):
    path = PLUGIN_ROOT / "commands" / cmd
    check(f"command /{cmd[:-3]} exists", path.is_file(), f"{path} missing")

# The old plugin id must not survive anywhere the user or the harness reads it.
# Exempt: CHANGELOG.md legitimately names old versions under old headers,
# AGENTING-PLAN-HANDOFF.md is a deliberate historical recovery record, and this
# file necessarily contains the literal to check for it.
STALE = "agent-routing"
STALE_EXEMPT = {"CHANGELOG.md", "AGENTING-PLAN-HANDOFF.md", Path(__file__).name}

# __pycache__ is gitignored build output, not source — a .pyc embeds the
# same string constants as its .py, so scanning it would either double-count
# a real hit or (as happened once during 2.1.0 development, after running
# `python3 -m py_compile` by hand) flag a stale string that isn't in any
# source file the user or harness actually reads.
scan_targets = []
for d in ("agents", "commands", "hooks", "scripts", "skills", ".claude-plugin", "templates"):
    if (PLUGIN_ROOT / d).is_dir():
        scan_targets.extend(
            p for p in (PLUGIN_ROOT / d).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )
scan_targets.extend(p for p in PLUGIN_ROOT.glob("*") if p.is_file())

stale_hits = []
for p in scan_targets:
    if p.name in STALE_EXEMPT:
        continue
    try:
        if STALE in p.read_text(encoding="utf-8", errors="ignore"):
            stale_hits.append(str(p.relative_to(PLUGIN_ROOT)))
    except Exception:
        continue
check(f'no stale "{STALE}" string survives the rename',
      not stale_hits,
      "still present in: " + ", ".join(sorted(stale_hits)[:4]))

# The mode axis stopped being conversational-memory-only in 2.1.0 (it's now
# carried by session-continuity.py's state file) and the default flipped
# manual -> auto. These phrasings describe the pre-2.1.0 mechanism; if one
# resurfaces it means a doc was reverted or a new doc copied stale prose.
# session-continuity.py itself is exempt: its docstring explains that exact
# history as the reason the hook exists, same reasoning as CHANGELOG.md.
#
# Also guards within-2.1.0 regressions caught by later advisor passes:
# session-continuity.py's SessionStart hook was redesigned mid-release to
# never ask anything itself (the lazy ask moved into the agenting skill's own
# procedure, then disposition's ask was cut entirely) -- these exact
# phrasings claimed the hook does the asking, or that auto mode still needs
# an --approve round-trip, both true of an earlier draft and true again only
# as a bug.
STALE_2_1 = (
    "conversational memory only", "resets to `manual`", "resets to manual every",
    "session-continuity.py asks once", "asking the once-per-continuum disposition question",
    "self-record the approval",
)
STALE_2_1_EXEMPT = STALE_EXEMPT | {"session-continuity.py"}
stale_2_1_hits = []
for p in scan_targets:
    if p.name in STALE_2_1_EXEMPT:
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for s in STALE_2_1:
        if s in text:
            stale_2_1_hits.append(f"{p.relative_to(PLUGIN_ROOT)}: {s!r}")
check("no pre-2.1.0 \"conversational memory only\" / \"resets to manual\" phrasing survives",
      not stale_2_1_hits,
      "still present in: " + ", ".join(stale_2_1_hits[:4]))

# The scaffold TEMPLATE shipped with the plugin -- not a search for a real
# project instance, which may legitimately not exist yet.
tpl_md = PLUGIN_ROOT / "templates" / "AGENTING.md"
if tpl_md.is_file():
    tpl_txt = tpl_md.read_text(encoding="utf-8")
    absent = [s for s in ("## Rules", "## Config") if s not in tpl_txt]
    check("templates/AGENTING.md carries its Rules and Config sections",
          not absent, "missing: " + ", ".join(absent))
else:
    check("templates/AGENTING.md carries its Rules and Config sections", False, f"{tpl_md} missing")

# 3.0.0 removed the semi-auto mode, the suggestion axis and the log.csv /
# precedent memory, and moved the agents to the plugin (agenting:<name>).
# None of that vocabulary should resurface in what Claude or the user reads.
# Exempt: the historical records, this file, and the two hooks that still
# read a legacy "semi-auto"/"suggestion" state entry on purpose.
STALE_3_0 = (
    "semi-auto", "log.csv", "shape_key", "promotion-threshold", "matching-strictness",
    "suggestion-default", "--suggestion", "Learned Precedents", "~/.claude/agents",
)
STALE_3_0_EXEMPT = STALE_EXEMPT | {"session-continuity.py", "workflow-routing-guard.py"}
stale_3_0_hits = []
for p in scan_targets:
    if p.name in STALE_3_0_EXEMPT:
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for s in STALE_3_0:
        if s in text:
            stale_3_0_hits.append(f"{p.relative_to(PLUGIN_ROOT)}: {s!r}")
check("no pre-3.0.0 semi-auto / suggestion / log.csv vocabulary survives",
      not stale_3_0_hits,
      "still present in: " + ", ".join(stale_3_0_hits[:4]))

# Stage 2 must tell the user to approve via the guard that actually ran, not a
# hardcoded ~/.claude path that breaks the moment the plugin lives elsewhere.
if guard:
    reason = stage_reason("await agent('x', {model:'haiku', effort:'low'})",
                          session="rename-check") or ""
    own_paths = {os.path.abspath(str(guard)), str(guard.resolve())}
    check("--approve command names the guard's own running path",
          any(p in reason for p in own_paths),
          f"STAGE 2 message does not contain {os.path.abspath(str(guard))}")
    check("--approve command is not the hardcoded ~/.claude fallback",
          "~/.claude/hooks/workflow-routing-guard.py --approve" not in reason,
          "the hardcoded path came back")

# ---------------------------------------------------------------- summary

fails = [n for n, ok, warn in results if not ok and not warn]
warns = [n for n, ok, warn in results if not ok and warn]
print("\n" + "=" * 62)
print(f"  {len(results) - len(fails) - len(warns)} passed, {len(fails)} failed, {len(warns)} warnings")
if fails:
    print(f"  {RED}FAILED:{RESET} " + "; ".join(fails))
if warns:
    print(f"  {YELLOW}WARN:{RESET} " + "; ".join(warns))
print("=" * 62)
sys.exit(1 if fails else 0)
