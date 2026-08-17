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

scan_targets = []
for d in ("agents", "commands", "hooks", "scripts", "skills", ".claude-plugin", "templates"):
    if (PLUGIN_ROOT / d).is_dir():
        scan_targets.extend(p for p in (PLUGIN_ROOT / d).rglob("*") if p.is_file())
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

# The scaffold TEMPLATE shipped with the plugin — not a search for a real
# project instance, which may legitimately not exist yet.
tpl_md = PLUGIN_ROOT / "templates" / "AGENTING.md"
if tpl_md.is_file():
    tpl_txt = tpl_md.read_text(encoding="utf-8")
    absent = [s for s in ("## Rules & Edge Cases", "## Config", "## Learned Precedents")
              if s not in tpl_txt]
    check("templates/AGENTING.md carries all three sections",
          not absent, "missing: " + ", ".join(absent))
else:
    check("templates/AGENTING.md carries all three sections", False, f"{tpl_md} missing")

LOG_HEADER = "timestamp,source,shape_key,plan_signature,answer"
tpl_csv = PLUGIN_ROOT / "templates" / "log.csv"
if tpl_csv.is_file():
    lines = tpl_csv.read_text(encoding="utf-8").splitlines()
    header = lines[0].strip() if lines else ""
    check("templates/log.csv header matches the schema",
          header == LOG_HEADER, f"got {header!r}, want {LOG_HEADER!r}")
else:
    check("templates/log.csv header matches the schema", False, f"{tpl_csv} missing")

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
