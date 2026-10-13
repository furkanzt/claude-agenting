#!/usr/bin/env python3
"""
workflow-routing-guard  --  PreToolUse hook on the Workflow tool.

WHY THIS EXISTS
---------------
Inside a workflow script, an agent() call with no `model` / `effort` inherits
the main-loop model and the session effort. On 2026-08-06 a 16-agent recon
workflow burned 4.45M subagent tokens (~$320 at Opus list rates) that way;
three of those agents did nothing but count files.

But cost is only half of it. Subagents are a *tier* mechanism: the session runs
at one model and one effort, and agent() calls are the only way to use several
tiers at once. So on a cheap session the risk is not overspending — it is
UNDER-POWERING a task that needed Opus. The gate therefore looks both ways:
cheaper AND higher quality.

TWO-STAGE GATE
--------------
  1. ROUTING: if any agent() call lacks model/agentType or lacks effort, DENY.
     Never bypassable -- mode has no say here. `agentType: 'agenting:<name>'`
     (this plugin's agents/, addressed with the plugin prefix) counts as routed.
     The check is static: it reads the keys of the options object in the source
     (quoted keys too). A key whose value is the literal undefined or null is no
     routing. A value read from an item (`effort: lens.effort`) is checked item by
     item when the items are a const array literal nothing in the script can
     change (see "per-item routing" below); otherwise a variable value (shorthand
     `{model, effort}` included) counts on presence alone, since its run-time value
     is unknowable here. Routing inside a spread (`...lens.route`) is invisible, and
     the denial names the spread (2026-10-12, a peer's fan-out). A script that
     mentions `agent` and that the guard cannot read to the end (a string running
     past its line; a template literal, `${` or comment that never closes; an
     agent( whose parentheses never close) is denied too: what follows would go
     unchecked. The escape hatch counts only in a comment.
  2. APPROVAL: even when every call is routed, DENY until the user has approved
     this particular routing plan in this session. Claude presents the plan
     (as proposed / cheaper / higher quality), applies the answer, records the
     approval with --approve, and re-runs.

     AUTO MODE: if this session's mode is explicitly recorded as "auto" in
     <state dir>/.agenting-session-state.json (written by the sibling
     SessionStart hook, hooks/session-continuity.py), Stage 2 drops its
     routing opinion entirely -- no --approve round-trip -- but stays silent on
     PERMISSION (see OUTPUT CONTRACT below). Only an explicit "auto" does this.
     A missing entry, a missing file, legacy "semi-auto" or anything else
     keeps the approval requirement, so an install where the continuity hook
     is absent degrades to asking rather than to a bypass nobody configured.

     RESUMED CHATS: a resumed or forked chat gets a new session_id, and its
     SessionStart hook may not run again (2026-10-08: ac2d086e resumed 499eb944
     and no entry was ever written for it, so an auto chat was asked for
     approval). The new transcript still carries the SessionStart line the
     model was given, "[agenting] mode=<m> ... (session <id>)". When the
     payload's own session_id has no entry, the guard takes the LAST such line
     from payload["transcript_path"] and reads that id's entry instead (the id
     the model records changes under); if that entry is gone it uses the mode
     printed in the line. Only SessionStart hook attachments count, so text that
     merely quotes the line does not; and it only ever follows an id found in
     THIS chat's transcript, never "any auto session". No usable line -> ask.

The same plan re-run in the same session passes silently. Change any tier and
the signature changes, so it asks again (except in auto mode, which never asks).

SINGLE Agent CALLS ARE OUT OF SCOPE
-----------------------------------
Deliberate: every agent definition in this plugin's agents/ pins both model and
effort, and one agent is bounded and cheap. A gate there costs more attention
than it saves. The "sometimes ask" cases where the tier and the task genuinely
disagree belong to the agenting skill, not to this hook.

STATE DIR
---------
$AGENTING_STATE_DIR if set (tests use this), else ~/.claude. Holds
.routing-approvals.json (written here, by --approve) and
.agenting-session-state.json (read-only here).

OUTPUT CONTRACT
---------------
PreToolUse -> hookSpecificOutput.permissionDecision ("deny" only -- this
              file never emits "allow"/"ask") + permissionDecisionReason, OR
              a bare `{"systemMessage": ...}` with NO hookSpecificOutput at
              all (the auto-mode bypass note() -- a visible remark with no
              permission opinion), OR truly empty stdout (every other
              pass-through case: "nothing to say about this call").
              permissionDecision:"allow" is deliberately never used, because
              it would override the user's OWN Claude Code permission
              settings for the Workflow tool, not just this plugin's routing
              approval -- a stronger claim than this hook should ever make.
"""

import argparse
import functools
import hashlib
import json
import os
import re
import sys

ESCAPE_HATCH = "routing: inherit"
MAX_REPORTED = 12
STATE_DIR = os.path.expanduser(os.environ.get("AGENTING_STATE_DIR") or "~/.claude")
APPROVALS_PATH = os.path.join(STATE_DIR, ".routing-approvals.json")
# Same file session-continuity.py's SessionStart hook writes -- read-only from
# here; this script only checks whether the mode was explicitly "auto".
SESSION_STATE_PATH = os.path.join(STATE_DIR, ".agenting-session-state.json")
KEEP_SESSIONS = 20
SELF_PATH = os.path.abspath(__file__)
# The line session-continuity.py injects at SessionStart. The separator between
# the fields is deliberately not matched: transcripts store it as "·" or "\u00b7".
SESSION_LINE_RE = re.compile(r"\[agenting\] mode=([\w-]+)\b.*?\(session ([\w-]+)\)")


# --------------------------------------------------------------- script parsing


# A `/` after one of these characters or words, or at the very start, begins a regex literal; after
# anything else (a name, a number, `)` or `]`) it is division. JavaScript decides the same way, by what
# came before it. A `)` that closes an `if`, `while`, `for` or `with` header is the exception: what
# follows starts a statement, so a `/` there begins a regex.
REGEX_AFTER = set("([{}<>,;:=!&|?+-*%~^")
REGEX_AFTER_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
                     "case", "do", "else", "yield", "await"}
HEADER_WORDS = {"if", "while", "for", "with"}
HEADER_END = ")if"   # `prev` after the `)` of one of those headers
LINE_ENDS = "\n\r\u2028\u2029"   # JavaScript's line terminators
WORD = re.compile(r"[\w$]+")
AGENT_CALL = re.compile(r"(?<![\w.$])agent\s*(?:\?\.\s*)?\(")   # `agent(` and `agent?.(`
AGENT_WORD = re.compile(r"(?<![\w.$])agent\b")
LINE_END = re.compile(f"[{LINE_ENDS}]")


def regex_end(src: str, i: int) -> int:
    """Index just past the regex literal that starts with the `/` at src[i], flags included, or 0
    when no regex closes on this line (a regex cannot span lines), so the slash is division."""
    j, in_class, n = i + 1, False, len(src)
    while j < n and src[j] not in LINE_ENDS:
        ch = src[j]
        if ch == "\\":
            if j + 1 < n and src[j + 1] in LINE_ENDS:
                return 0
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            flags = WORD.match(src, j + 1)
            return flags.end() if flags else j + 1
        j += 1
    return 0


def is_operand(prev: str) -> bool:
    """Whether the last code token ends an operand (a name, a number, a literal, `)` or `]`)."""
    return prev in ("x", ")", "]") or bool(prev) and (prev[0].isalnum() or prev[0] in "_$") and prev not in REGEX_AFTER_WORDS


def scan_source(src: str):
    """(clean, problem, comments): `src` with comments and the bodies of strings, template text and
    regex literals blanked out, length preserved; (index, what) of the first construct that never
    closes, or None; and the (start, end) span of every comment.

    Length is preserved because indices computed here (line numbers, the position of an agent(
    call) are used against the original text too. An opening quote stays visible, the closing one
    is blanked. The code inside a template's `${...}` is scanned as code, with its delimiters turned
    into `(` and `)`: an agent() call written there is checked, and its braces are not taken for an
    options object. Scanning a template as one flat string let a nested template end the outer one,
    and an apostrophe in its text (``${x ? `The instructor's deck` : ''}``) then blanked the rest of
    the script, hiding every later call (2026-10-12 review, 2 of 177 real scripts). A quoted string
    ends at its line's end, as in JavaScript, so a stray quote cannot blank more than one line.
    """
    out, n, i = list(src), len(src), 0
    holes = []    # per open `${`: [index of the template's backtick, index of the `$`, braces open inside it]
    parens = []   # per open `(`: whether it opens an if/while/for/with header
    comments = []
    prev = ""     # the last code token: a punctuation character, a word, "x" for an operand, or HEADER_END
    problem = None

    def blank(a, b):
        for k in range(a, min(b, n)):
            if src[k] != "\n":
                out[k] = " "

    def fail(at, what):
        nonlocal problem
        problem = problem or (at, what)

    def template_text(i, opened_at):
        """Blank template text from i up to the closing backtick or the next `${`.
        Returns (index after it, whether a `${` opened)."""
        while i < n:
            ch = src[i]
            if ch == "\\":
                blank(i, i + 2)
                i += 2
            elif ch == "`":
                out[i] = " "
                return i + 1, False
            elif ch == "$" and src.startswith("{", i + 1):
                out[i], out[i + 1] = " ", "("
                return i + 2, True
            else:
                blank(i, i + 1)
                i += 1
        fail(opened_at, "a template literal opened here never closes")
        return n, False

    while i < n:
        c = src[i]
        if src.startswith("//", i):
            m = LINE_END.search(src, i)
            j = m.start() if m else n
            comments.append((i, j))
            blank(i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                fail(i, "a comment opened here never closes")
            j = n if j < 0 else j + 2
            comments.append((i, j))
            blank(i, j)
            i = j
        elif c == "/" and (not prev or prev in REGEX_AFTER or prev in REGEX_AFTER_WORDS or prev == HEADER_END) \
                and (j := regex_end(src, i)):
            blank(i + 1, j)
            prev, i = "x", j
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] not in (c, "\n", "\r"):
                if src[j] == "\\":   # an escaped line end, CRLF included, continues the string
                    j += 3 if src.startswith("\r\n", j + 1) else 2
                else:
                    j += 1
            if j < n and src[j] == c:
                j += 1
            else:
                fail(i, "a string opened here does not close on its line")
            blank(i + 1, j)
            prev, i = "x", min(j, n)
        elif c == "`" or (c == "}" and holes and holes[-1][2] == 0):
            if c == "`":
                opened_at = i
            else:   # this `}` closes a `${`: back to the template's text
                opened_at = holes.pop()[0]
                out[i] = ")"
            i, interpolates = template_text(i + 1, opened_at)
            if interpolates:
                holes.append([opened_at, i - 2, 0])
                prev = "("
            else:
                prev = "x"
        elif m := WORD.match(src, i):
            word = m.group()
            prev = "x" if prev == "." or word[0].isdigit() else word   # `x.return` is a property name
            i = m.end()
        elif c in "+-" and src.startswith(c, i + 1) and is_operand(prev):
            i += 2   # postfix `i++`: still an operand, so a `/` after it is division
        else:
            if holes and c in "{}":
                holes[-1][2] += 1 if c == "{" else -1
            if c == "(":
                parens.append(prev in HEADER_WORDS)
            if not c.isspace():
                prev = HEADER_END if c == ")" and parens and parens.pop() else c
            i += 1
    if holes:
        fail(holes[-1][1], "a template's ${ opened here never closes")
    return "".join(out), problem, comments


def find_agent_calls(src: str, clean: str):
    """Yield (start, end) of each agent(...) call, scanning with balanced parens; end is None
    for a call whose parentheses never close."""
    for m in AGENT_CALL.finditer(clean):
        depth, end = 0, None
        for i in range(m.end() - 1, len(clean)):
            if clean[i] == "(":
                depth += 1
            elif clean[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        yield m.start(), end


def opts_span(clean_call: str):
    """Return (start, end) of the last top-level {...} argument of an agent(...) call.

    "Top level" means directly inside the call's own parentheses: an object nested in the
    options (a `schema:`) or one inside another argument's expression (`build({...})`) is not
    the options object. Taking the innermost last `{` instead made every call with a nested
    schema look unrouted, and let keys inside a schema count as routing.

    Indices are returned because they get applied to two different strings: a
    key's PRESENCE is checked against the stripped text (so the word "model:"
    inside a prompt is not mistaken for routing), while its VALUE is read from
    the raw text (stripping blanks out everything inside quotes).
    """
    span, open_at, depth = None, None, 0
    for j, ch in enumerate(clean_call):
        if ch in "([{":
            if ch == "{" and depth == 1:
                open_at = j
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if ch == "}" and depth == 1 and open_at is not None:
                span, open_at = (open_at, j + 1), None
    return (open_at, len(clean_call)) if open_at is not None else span


IDENT = re.compile(r"[A-Za-z_$][\w$]*")
QUOTED_KEY = re.compile(r"(['\"])([A-Za-z_$][\w$]*)\1")   # `{'model': 'haiku'}`, read from the raw text
COLON = re.compile(r"\s*:")
SHORTHAND_END = re.compile(r"\s*(?:[,}]|$)")   # `{model, effort}` is `{model: model, effort: effort}`
SPREAD_NAME_MAX = 40
QUOTED = re.compile(r"\s*['\"]([^'\"]+)['\"]")
# A value that is nothing but `undefined` or `null`: JavaScript passes no routing for it.
NULLISH = re.compile(r"\s*(undefined|null)\s*(?=[,}]|$)")
ROUTING_KEYS = ("model", "agentType", "effort")


def top_level_entries(clean_opts: str, raw_opts: str):
    """({key: index just after its colon}, [(start, end) of each spread expression], opaque) for
    the options object itself; `opaque` is True when some entry is not a plain key (a getter or a
    method, a computed `[key]`, `__proto__`), so a key it lacks may still exist at run time.

    Only identifiers that start a property (right after the opening brace or a comma at the
    options' own depth) count, so keys inside a nested object, and names inside a value
    expression such as a ternary, are not mistaken for options. A quoted key (`'model':`) is read
    from the raw text, since its name is blanked in the stripped one. A spread (`...lens.route`) is
    recorded, not resolved: what it holds is only known at run time.
    """
    keys, spreads, depth, expect_key, i, n = {}, [], 0, False, 0, len(clean_opts)
    spread_at, opaque = None, False
    while i < n:
        ch = clean_opts[i]
        if ch in "([{":
            opaque = opaque or expect_key   # `[key]: value`
            depth += 1
            expect_key = depth == 1 and ch == "{"
            i += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0 and spread_at is not None:
                spreads.append((spread_at, i))
                spread_at = None
            i += 1
        elif depth == 1 and ch == ",":
            if spread_at is not None:
                spreads.append((spread_at, i))
                spread_at = None
            expect_key = True
            i += 1
        elif expect_key and clean_opts.startswith("...", i):
            spread_at, expect_key = i + 3, False
            i += 3
        elif expect_key and (m := IDENT.match(clean_opts, i)):   # expect_key is only ever set at depth 1
            colon = COLON.match(clean_opts, m.end())
            if colon:
                keys[m.group()] = colon.end()   # a repeated key: the last one wins, as in JavaScript
            elif SHORTHAND_END.match(clean_opts, m.end()):
                keys[m.group()] = m.start()     # shorthand: its value is the variable of the same name
            else:
                opaque = True                   # `get effort() {...}`, `async run() {...}`
            expect_key = False
            i = m.end()
        elif expect_key and ch in "'\"" and (m := QUOTED_KEY.match(raw_opts, i)):
            if colon := COLON.match(clean_opts, m.end()):
                keys[m.group(2)] = colon.end()
            else:
                opaque = True
            expect_key = False
            i = m.end()
        else:
            if depth == 1 and not ch.isspace():
                opaque = opaque or expect_key   # `[key]: value`, a numeric key, a generator method
                expect_key = False
            i += 1
    if spread_at is not None:   # options left unclosed (opts_span ran to the end of the call)
        spreads.append((spread_at, n))
    return keys, spreads, opaque or "__proto__" in keys


def top_level_keys(clean_opts: str, raw_opts: str) -> dict:
    return top_level_entries(clean_opts, raw_opts)[0]


def nullish(clean_opts: str, raw_opts: str, key: str) -> str:
    """'undefined' or 'null' when a top-level key's whole value is that literal, else ''."""
    at = top_level_keys(clean_opts, raw_opts).get(key)
    m = NULLISH.match(clean_opts, at) if at is not None else None
    return m.group(1) if m else ""


def missing_routing(clean_opts: str, raw_opts: str) -> str:
    """Why this options object carries no routing, or '' when it has a model (or agentType) and an
    effort. A key whose value is the literal undefined or null is no routing. When something is
    missing and the options spread another object in, the spread is named: the guard reads the
    source, so whatever routing the spread carries at run time is invisible to it."""
    keys, spreads, _ = top_level_entries(clean_opts, raw_opts)
    routed = [k for k in ("model", "agentType") if k in keys and not nullish(clean_opts, raw_opts, k)]
    causes = []
    if not routed:
        empty = next((k for k in ("model", "agentType") if k in keys), None)
        causes.append(f"{empty} is {nullish(clean_opts, raw_opts, empty)}" if empty else "no model")
    if "effort" not in keys:
        causes.append("no effort")
    elif nullish(clean_opts, raw_opts, "effort"):
        causes.append(f"effort is {nullish(clean_opts, raw_opts, 'effort')}")
    why = ", ".join(causes)
    if why and spreads:
        why += "; the guard cannot read " + ", ".join(spread_name(clean_opts, raw_opts, s) for s in spreads)
    return why


def spread_name(clean_opts: str, raw_opts: str, span) -> str:
    """`...<expr>` as written, without a trailing comment (blank in the stripped text) and capped."""
    a, b = span
    b = a + len(clean_opts[a:b].rstrip())
    name = " ".join(raw_opts[a:b].split())
    if len(name) > SPREAD_NAME_MAX:
        name = name[: SPREAD_NAME_MAX - 1] + "…"
    return "..." + name


def kv(raw_opts: str, clean_opts: str, key: str) -> str:
    """The quoted value of a top-level key, read from the raw opts text; empty string if the
    key is absent or its value is not a quoted literal."""
    at = top_level_keys(clean_opts, raw_opts).get(key)
    m = QUOTED.match(raw_opts, at) if at is not None else None
    return m.group(1) if m else ""


# ------------------------------------------------------- per-item routing (`effort: lens.effort`)
#
# A fan-out keeps each item's tier as data and reads it in the options. Presence alone let an item with
# no effort run on the session's tier (2026-10-12, a peer's LENSES), and the plan showed "?". When the
# items visibly come from a `const` array literal and nothing in the script can change them, each item
# is read: one that provably sets no model or effort is a Stage 1 cause, and the plan shows the tiers.
#
# "Nothing can change them" is checked by shape, not by following the code: the list's name appears only
# in its declaration and as the list a recognised loop iterates (or `.length`); every use of a loop
# variable over it is a property read that assigns nothing; the literal ends at its `]`; its items hold
# only plain keys; the call's options spread nothing. Anything else (a chained `.map`, `??=` defaults,
# a reassigned or shadowed name, a helper the list is passed to) stays presence-only, so this denies only
# an item that really lacks the key (the 3.3.2 pre-release review found eleven ways a looser check was
# wrong).

MEMBER = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*\.\s*([A-Za-z_$][\w$]*)\s*(?=[,}]|$)")
WHOLE_QUOTED = re.compile(r"\s*['\"]([^'\"\n]+)['\"]\s*(?=[,}]|$)")
NAME = r"[A-Za-z_$][\w$]*"
# The callback's parameters must not reach the items another way: map's third parameter is the list, and
# pipeline hands its first stage the item twice, `(item, originalItem)`. So map, forEach and flatMap take
# `(item)` or `(item, index)`, and pipeline's first stage `(item)` only; a callback with more is no
# recognised loop, and the list's name in it is then an ordinary use (3.3.2 denied
# `L.forEach((l, i, arr) => { arr[i].effort = 'low' })`).
ARROW_PARAM = rf"(?:async\s+)?(?:\(\s*(?P<p1>{NAME})\s*{{extra}}\)|(?P<p2>{NAME}))\s*=>"
LOOP_FORMS = (
    re.compile(rf"(?<![\w.$])(?P<list>{NAME})\s*\.\s*(?:map|forEach|flatMap)\s*\(\s*"
               + ARROW_PARAM.format(extra=rf"(?:,\s*{NAME}\s*)?")),
    re.compile(rf"(?<![\w.$])pipeline\s*\(\s*(?P<list>{NAME})\s*,\s*" + ARROW_PARAM.format(extra="")),
    re.compile(rf"(?<![\w.$])for\s*\(\s*(?:const|let|var)\s+(?P<p1>{NAME})\s+of\s+(?P<list>{NAME})\s*\)"),
)
MEMBER_READ = re.compile(rf"\s*\??\.\s*{NAME}")
ASSIGNS = re.compile(r"\s*(?:(?:\*\*|<<|>>>?|&&|\|\||\?\?|[-+*/%&|^])?=(?![=>])|\+\+|--)")
UPDATES_BEFORE = re.compile(r"(?:\+\+|--|\bdelete)\s*$")
SPACE = re.compile(r"\s*")
LENGTH_READ = re.compile(r"\s*\.\s*length\b")
ITEM_READ = re.compile(rf"\s*\[[^\[\]]*\]\s*\??\.\s*{NAME}")    # `CLUSTERS[i].label`
KEY_BEFORE = re.compile(r"[{,]\s*$")
KEY_AFTER = re.compile(r"\s*:(?!:)")
STRINGIFY_BEFORE = re.compile(r"JSON\s*\.\s*stringify\s*\(\s*$")
ARROW_PARAMS_BEFORE = re.compile(r"\(\s*(?:[\w$]+\s*,\s*)*$")       # `(report, ` before the name
ARROW_PARAM_AT = re.compile(r"\s*(?:,\s*[\w$]+\s*)*\)\s*=>")
CONST_BEFORE = re.compile(r"(?<![\w.$])const\s+$")
MAX_ITEMS_NAMED = 4


def close_of(clean: str, i: int):
    """Index just past the bracket that closes the one at clean[i], or None."""
    depth = 0
    for j in range(i, len(clean)):
        if clean[j] in "([{":
            depth += 1
        elif clean[j] in ")]}":
            depth -= 1
            if depth == 0:
                return j + 1
    return None


def body_span(clean: str, i: int, statement: bool):
    """(start, end) of the arrow body or loop statement from clean[i]: a `{...}` block, or an
    expression ending at the first `,` `;` or unmatched closing bracket at its own depth; a braceless
    loop statement also ends at its line's end, or in a script without semicolons it would run on
    over the lines after the loop."""
    while i < len(clean) and clean[i].isspace():
        i += 1
    if clean.startswith("{", i):
        return i, close_of(clean, i) or len(clean)
    depth = 0
    for j in range(i, len(clean)):
        ch = clean[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return i, j
            depth -= 1
        elif depth == 0 and (ch in ",;" or statement and ch == "\n"):
            return i, j
    return i, len(clean)


@functools.lru_cache(maxsize=4)
def loops(clean: str):
    """(list, param, header start, header end, body start, body end) for every recognised loop:
    `list.map(param => ...)` (or forEach, flatMap), the first stage of `pipeline(list, param =>
    ...)`, and `for (const param of list)`."""
    found = []
    for form in LOOP_FORMS:
        for m in form.finditer(clean):
            param = m.group("p1") or m.groupdict().get("p2")
            start, end = body_span(clean, m.end(), statement=form is LOOP_FORMS[2])
            found.append((m.group("list"), param, m.start(), m.end(), start, end))
    return tuple(found)


def uses(clean: str, name: str):
    return re.finditer(rf"(?<![\w.$]){re.escape(name)}(?![\w$])", clean)


def mentions_only(clean: str, m) -> bool:
    """Whether this mention of a name is no use of the variable at all: an object key
    (`{ lens: lens.key }`), or the argument of JSON.stringify, which only reads."""
    return bool(KEY_BEFORE.search(clean, max(0, m.start() - 4), m.start()) and KEY_AFTER.match(clean, m.end())
                or STRINGIFY_BEFORE.search(clean, max(0, m.start() - 24), m.start()))


@functools.lru_cache(maxsize=64)
def only_read(clean: str, param: str) -> bool:
    """Whether every use of `param` is a recognised loop's binding or a property read that assigns
    nothing (`lens.effort`, not `lens = ...`, `lens.effort ??= ...`, `lens[k] = ...` or `f(lens)`).
    Another arrow function may name a parameter the same (a later pipeline stage's `(report, lens)`)
    as long as it sits outside every recognised loop over `param`, where it cannot shadow the item."""
    found = [lp for lp in loops(clean) if lp[1] == param]
    for m in uses(clean, param):
        if any(h0 <= m.start() < h1 for _, _, h0, h1, _, _ in found) or mentions_only(clean, m):
            continue
        if ARROW_PARAM_AT.match(clean, m.end()) and ARROW_PARAMS_BEFORE.search(clean, max(0, m.start() - 80), m.start()) \
                and not any(b0 <= m.start() < b1 for *_, b0, b1 in found):
            continue
        read = MEMBER_READ.match(clean, m.end())
        if not read or ASSIGNS.match(clean, read.end()) or UPDATES_BEFORE.search(clean, max(0, m.start() - 10), m.start()):
            return False
    return True


@functools.lru_cache(maxsize=64)
def only_iterated(clean: str, name: str) -> bool:
    """Whether `name` appears only in one `const` declaration, as the list a recognised loop
    iterates, as `name.length`, or in a property read of one item (`name[i].label`)."""
    sources = [(h0, h1) for n, _, h0, h1, _, _ in loops(clean) if n == name]
    declared = 0
    for m in uses(clean, name):
        if any(h0 <= m.start() < h1 for h0, h1 in sources) or mentions_only(clean, m):
            continue
        read = LENGTH_READ.match(clean, m.end()) or ITEM_READ.match(clean, m.end())
        if read and not ASSIGNS.match(clean, read.end()):
            continue
        if CONST_BEFORE.search(clean, max(0, m.start() - 12), m.start()):
            declared += 1
            continue
        return False
    return declared == 1


@functools.lru_cache(maxsize=64)
def const_array_items(clean: str, raw: str, name: str):
    """((clean_item, raw_item), ...) of `const NAME = [...]` when the initializer is that literal
    alone (not `[...].map(...)`) and holds no spread element or hole; None otherwise."""
    decl = re.search(rf"(?<![\w.$])const\s+{re.escape(name)}\s*=\s*", clean)
    if not decl or not clean.startswith("[", decl.end()):
        return None
    a = decl.end()
    b = close_of(clean, a)
    if b is None:
        return None
    after = SPACE.match(clean, b).end()
    if not (after == len(clean) or clean[after] in ";}" or "\n" in clean[b:after] and IDENT.match(clean, after)):
        return None   # `[...].map(...)`, `[...] + x`, `[...]\n(...)`: the list is not the literal itself
    items, depth, start = [], 0, a + 1
    for j in range(a + 1, b):
        ch = clean[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}" and j < b - 1:
            depth -= 1
        if (ch == "," and depth == 0) or j == b - 1:
            chunk = clean[start:j].strip()
            if chunk.startswith("...") or not chunk and ch == ",":
                return None   # a spread element or a hole: the indexes would not be the run-time ones
            if chunk:
                items.append((clean[start:j], raw[start:j]))
            start = j + 1
    return tuple(items)


def item_value(clean_item: str, raw_item: str, prop: str):
    """("set", value) when the item is an object literal whose `prop` is a quoted literal; ("unset", "")
    when it provably has none (absent from plain keys only, or undefined or null); ("?", "") otherwise."""
    lead = len(clean_item) - len(clean_item.lstrip())
    if not clean_item.startswith("{", lead) or close_of(clean_item, lead) != len(clean_item.rstrip()):
        return "?", ""
    c, r = clean_item[lead:], raw_item[lead:]
    keys, spreads, opaque = top_level_entries(c, r)
    if prop not in keys:
        return ("?", "") if spreads or opaque else ("unset", "")
    if NULLISH.match(c, keys[prop]):
        return "unset", ""
    m = WHOLE_QUOTED.match(r, keys[prop])
    return ("set", m.group(1)) if m else ("?", "")


def per_item(clean: str, raw: str, start: int, clean_opts: str, raw_opts: str):
    """(list name, one {routing key: (state, value)} per item) when the call's routing values read
    one item of a const array literal nothing can change (see above); None when the guard cannot tell."""
    keys, spreads, _ = top_level_entries(clean_opts, raw_opts)
    members = {k: m.groups() for k in ROUTING_KEYS
               if k in keys and (m := MEMBER.match(clean_opts, keys[k]))}
    params = {param for param, _ in members.values()}
    if spreads or len(params) != 1 or re.search(r"\bprototype\b", clean):   # `Object.prototype.effort = ...`
        return None
    param = params.pop()
    enclosing = [(b0, name) for name, p, _, _, b0, b1 in loops(clean) if p == param and b0 <= start < b1]
    name = max(enclosing)[1] if enclosing else None
    if not name or not only_iterated(clean, name) or \
            not all(only_read(clean, p) for n, p, *_ in loops(clean) if n == name):
        return None
    items = const_array_items(clean, raw, name)
    if not items:
        return None
    rows = []
    for clean_item, raw_item in items:
        row = {}
        for k in ROUTING_KEYS:
            if k in members:
                row[k] = item_value(clean_item, raw_item, members[k][1])
            elif k not in keys or nullish(clean_opts, raw_opts, k):
                row[k] = ("unset", "")
            else:
                value = kv(raw_opts, clean_opts, k)
                row[k] = ("set", value) if value else ("?", "")
        rows.append(row)
    return name, rows


def per_item_gaps(name: str, rows) -> str:
    """The Stage 1 cause for the items that provably set no model (nor agentType) or no effort, or ''."""
    def which(idx):
        named = ", ".join(f"{name}[{i}]" for i in idx[:MAX_ITEMS_NAMED])
        return named + (f" and {len(idx) - MAX_ITEMS_NAMED} more" if len(idx) > MAX_ITEMS_NAMED else "")
    no_model = [i for i, r in enumerate(rows) if r["model"][0] == r["agentType"][0] == "unset"]
    no_effort = [i for i, r in enumerate(rows) if r["effort"][0] == "unset"]
    causes = [f"no model in {which(no_model)}"] if no_model else []
    causes += [f"no effort in {which(no_effort)}"] if no_effort else []
    return ", ".join(causes)


def per_item_tier(rows):
    """(model, effort) for the plan: the distinct item tiers in item order, each side joined by "|"
    in step with the other (`haiku|opus` / `low|xhigh`), or one value when it is the same for all."""
    pairs = []
    for r in rows:
        model = r["model"][1] or (f"agent:{r['agentType'][1]}" if r["agentType"][1] else "?")
        pair = (model, r["effort"][1] or "?")
        if pair not in pairs:
            pairs.append(pair)
    return tuple(side[0] if len(set(side)) == 1 else "|".join(side) for side in zip(*pairs))


def has_escape_hatch(src: str, start: int, comments) -> bool:
    """True if a comment on this line or the one above it says `routing: inherit`. The words in a
    string or a prompt do not count (`Explain why routing: inherit is risky`)."""
    line_start = src.rfind("\n", 0, start) + 1
    line_end = src.find("\n", start)
    line_end = len(src) if line_end == -1 else line_end
    prev_start = src.rfind("\n", 0, line_start - 1) + 1 if line_start > 0 else 0
    return any(src.find(ESCAPE_HATCH, max(a, prev_start), min(b, line_end)) >= 0 for a, b in comments)


def load_script(tool_input: dict):
    """Return (script_text, source_label); (None, reason) if not inspectable."""
    script = tool_input.get("script")
    if isinstance(script, str) and script.strip():
        return script, "inline script"
    path = tool_input.get("scriptPath")
    if isinstance(path, str) and path:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8") as fh:
                return fh.read(), f"scriptPath {path}"
        except OSError:
            return None, f"could not read scriptPath: {path}"
    if tool_input.get("name"):
        return None, "named workflow"
    return None, "no script"


# -------------------------------------------------------------------- approvals


def load_approvals() -> dict:
    try:
        with open(APPROVALS_PATH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_approvals(d: dict) -> None:
    if len(d) > KEEP_SESSIONS:
        d = dict(list(d.items())[-KEEP_SESSIONS:])
    try:
        os.makedirs(os.path.dirname(APPROVALS_PATH), exist_ok=True)
        tmp = APPROVALS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)
        os.replace(tmp, APPROVALS_PATH)
    except Exception:
        pass


def plan_signature(tiers) -> str:
    """Build a stable signature from the (model, effort) counts."""
    counts = {}
    for model, effort in tiers:
        key = (model or "inherit", effort or "inherit")
        counts[key] = counts.get(key, 0) + 1
    return "|".join(f"{m}/{e}x{n}" for (m, e), n in sorted(counts.items()))


def call_sites(n: int) -> str:
    return f"{n} agent() call site" + ("" if n == 1 else "s")


def plan_hash(sig: str) -> str:
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]


def load_session_state() -> dict:
    try:
        with open(SESSION_STATE_PATH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _session_start_texts(attachment: dict):
    """The text a SessionStart hook put in front of the model, from either form
    the transcript stores it in."""
    if attachment.get("hookEvent") != "SessionStart":
        return
    kind = attachment.get("type")
    if kind == "hook_additional_context":
        content = attachment.get("content")
        yield from (content if isinstance(content, list) else [content])
    elif kind == "hook_success":
        try:
            yield json.loads(attachment.get("stdout") or "")["hookSpecificOutput"]["additionalContext"]
        except Exception:
            return


def transcript_session_line(transcript_path):
    """(mode, session_id) from the last "[agenting] mode=... (session <id>)" line
    that a SessionStart hook put into this chat's transcript, or None. Streams the
    file (they reach ~10 MB) and parses only the lines that can hold the marker."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    found = None
    try:
        with open(os.path.expanduser(transcript_path), "rb") as fh:
            for raw in fh:
                if b"[agenting] mode=" not in raw:
                    continue
                try:
                    record = json.loads(raw)
                except ValueError:
                    continue
                attachment = record.get("attachment") if isinstance(record, dict) else None
                if not isinstance(attachment, dict):
                    continue
                for text in _session_start_texts(attachment):
                    if isinstance(text, str):
                        for m in SESSION_LINE_RE.finditer(text):
                            found = (m.group(1), m.group(2))
    except OSError:
        return None
    return found


def session_mode(session: str, transcript_path):
    """(mode, origin): the mode recorded for this session id, else the one this
    chat's SessionStart line leads to (see RESUMED CHATS in the module docstring).
    `origin` is the id it was read from, None when the session's own entry answered.
    (None, None) when nothing is recorded anywhere -- the caller asks."""
    state = load_session_state()
    entry = state.get(session)
    if isinstance(entry, dict):
        return entry.get("mode"), None
    line = transcript_session_line(transcript_path)
    if line is None:
        return None, None
    line_mode, origin = line
    origin_entry = state.get(origin)
    if isinstance(origin_entry, dict):
        return origin_entry.get("mode"), origin
    return line_mode, origin


# ------------------------------------------------------------------------- main


def deny(reason: str, system_msg: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": system_msg,
            }
        )
    )
    return 0


def note(system_msg: str) -> int:
    """No permission opinion -- deliberately does NOT set permissionDecision,
    unlike deny(). This hook's job is Workflow ROUTING approval only; whether
    the Workflow tool may run at all is the user's own Claude Code permission
    setting (defaultMode, an allowlist, etc.), and a `permissionDecision:
    "allow"` here would override that entirely, not just this plugin's own
    approval step -- exactly the gap between "I have no opinion" (the
    pre-existing silent `return 0` pass-through, used everywhere else in this
    file that isn't a deliberate deny) and "I am overriding your permission
    settings" (which nothing in this file should ever do). Used only for the
    auto-mode Stage-2 bypass, so the auto-approval is visible via
    systemMessage instead of being a silent no-op, without touching the
    underlying permission decision."""
    print(
        json.dumps(
            {
                "systemMessage": system_msg,
            }
        )
    )
    return 0


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # malformed input must not break the hook
    if not isinstance(payload, dict) or payload.get("tool_name") != "Workflow":
        return 0  # valid JSON that is not an object ([], null) is malformed input too

    session = payload.get("session_id") or "unknown"
    tool_input = payload.get("tool_input")
    src, label = load_script(tool_input if isinstance(tool_input, dict) else {})
    if src is None:
        return 0  # cannot inspect it, so do not block it

    clean, problem, comments = scan_source(src)
    unrouted, tiers = [], []
    for start, end in find_agent_calls(src, clean):
        if end is None:
            problem = problem or (start, "this agent( call's parentheses never close")
            continue
        if has_escape_hatch(src, start, comments):
            tiers.append(("inherit", "inherit"))
            continue
        clean_call, raw_call = clean[start:end], src[start:end]
        span = opts_span(clean_call)
        clean_opts = clean_call[span[0] : span[1]] if span else ""
        raw_opts = raw_call[span[0] : span[1]] if span else ""
        line = src.count("\n", 0, start) + 1
        snippet = " ".join(raw_call.split())[:70]

        # PRESENCE from the stripped text, VALUE from the raw text.
        why = missing_routing(clean_opts, raw_opts)
        items = None if why else per_item(clean, src, start, clean_opts, raw_opts)
        if items:
            why = per_item_gaps(*items)
        if why:
            unrouted.append((line, why, snippet))
        elif items:
            tiers.append(per_item_tier(items[1]))
        else:
            model = kv(raw_opts, clean_opts, "model")
            atype = kv(raw_opts, clean_opts, "agentType")
            effort = kv(raw_opts, clean_opts, "effort") or "?"
            tiers.append((model or (f"agent:{atype}" if atype else "?"), effort))

    # --- STAGE 1, before anything else: a script the guard cannot read to the end ------
    # Whatever follows an unclosed string, template or comment is blanked, so the calls there go
    # unchecked: fail closed rather than pass a script whose routing was never read. Valid
    # JavaScript never ends inside one, so this denies only a broken script or a guard misread.
    if problem and AGENT_WORD.search(src):
        at, what = problem
        line = src.count("\n", 0, at) + 1
        text = " ".join(src[src.rfind("\n", 0, at) + 1 :].split("\n", 1)[0].split())[:70]
        return deny(
            f"""STAGE 1/2 — UNREADABLE SCRIPT: the routing guard could not read this script to the end ({label}),
so it cannot tell whether every agent() call is routed.

    line {line:>4}  [{what}]  {text}…

Close it and run again. If the script is valid JavaScript, the guard misread it; the
likely cause is a regex literal it took for division (one right after `)` or `]`):
move the regex into a const of its own, or write it as new RegExp(...).""",
            "Workflow stopped (1/2): the routing guard could not read the script.",
        )

    if not tiers and not unrouted:
        return 0  # no agent() calls at all

    # --- STAGE 1: missing routing ------------------------------------------
    if unrouted:
        rows = "\n".join(
            f"    line {ln:>4}  [{why}]  {sn}…" for ln, why, sn in unrouted[:MAX_REPORTED]
        )
        more = (
            f"\n    … and {len(unrouted) - MAX_REPORTED} more"
            if len(unrouted) > MAX_REPORTED
            else ""
        )
        return deny(
            f"""STAGE 1/2 — MISSING ROUTING: {len(unrouted)} agent() call(s) specify no model/effort ({label}).

Unrouted calls INHERIT the main-loop model and the session effort. That cuts
both ways: wasted spend on an expensive session, and an under-powered agent on
a cheap one.

{rows}{more}

DO THIS: give every agent() call a model (or agentType) AND an effort, e.g.
  {{model: 'haiku', effort: 'low'}}  or  {{agentType: 'agenting:researcher', effort: 'medium'}}
Tier table: load the agenting skill if it isn't loaded yet.

Write the keys into the options object itself: the guard reads the source, so it
cannot see routing inside a spread (`...lens.route`) or an options variable. For
per-item routing, spell the keys out:
  {{agentType: lens.agentType, model: lens.model, effort: lens.effort}}
When `lens` is an item of a const array literal the call iterates (NAME.map(lens =>
...), forEach, flatMap, the first stage of pipeline(NAME, lens => ...), or for (const
lens of NAME)) and the script only reads the list and its items, every item is read
and one with no model or effort is named here. Otherwise only the key's presence is
checked, so every item must set it. A literal undefined or null does not count.

For deliberate inheritance, put `// {ESCAPE_HATCH}` on that line or the one above it.""",
            f"Workflow stopped (1/2): {len(unrouted)} agent() call(s) have no routing.",
        )

    # --- STAGE 2: plan approval --------------------------------------------
    sig = plan_signature(tiers)
    h = plan_hash(sig)

    mode, origin = session_mode(session, payload.get("transcript_path"))
    if mode == "auto":
        carried = f", mode carried over from session {origin}" if origin else ""
        return note(
            f"Workflow routing auto-approved ({call_sites(len(tiers))}, auto mode{carried}, "
            f"plan {h}) — no --approve round-trip needed. Your own Claude Code "
            f"permission settings, if any, still apply to running Workflow itself."
        )

    if h in load_approvals().get(session, []):
        return 0  # this plan was already approved in this session

    counts = {}
    for model, effort in tiers:
        counts[(model, effort)] = counts.get((model, effort), 0) + 1
    table = "\n".join(
        f"    {n:>3} call site(s)   {m:<16} effort: {e}"
        for (m, e), n in sorted(counts.items(), key=lambda x: -x[1])
    )
    if mode is None:
        why = (f"no agenting mode is recorded for session {session}, and this chat's SessionStart "
               f"line could not be found in its transcript, so the guard asks")
    else:
        why = f"mode is {mode}" + (f", carried over from session {origin}" if origin else "")

    return deny(
        f"""STAGE 2/2 — PLAN APPROVAL: {call_sites(len(tiers))}, all routed. Waiting on the user
({why}). Procedure: the agenting skill.

{table}

{call_sites(len(tiers))} -- call sites, not runs: a call inside a loop, map(),
parallel() or pipeline() runs once per item, so the script launches more agents than this.
Plan signature: {sig}

DO THIS, in order:
  1. Put this plan to the user with AskUserQuestion. Offer ALL THREE
     directions, not just "cheaper":
       [as proposed]     the plan above
       [cheaper/faster]  name which agents you would step down a tier
       [higher quality]  name which agents you would step up a tier
     If the session is on a cheap tier (sonnet/medium), lead with the UPGRADE
     option; on an expensive tier (opus/xhigh), lead with the DOWNGRADE option.
  2. Apply the answer to the script. Changing the plan changes the signature,
     so the gate will ask again — that is intended.
  3. Record the approval:
       python3 "{SELF_PATH}" --approve {h} --session {session}
  4. Run the Workflow again.

The same plan re-run in this session will not ask again.""",
        f"Workflow stopped (2/2): a routing plan with {call_sites(len(tiers))} is awaiting approval.",
    )


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--approve")
    ap.add_argument("--session")
    args, _ = ap.parse_known_args()

    if args.approve:
        session = args.session or "unknown"
        d = load_approvals()
        d.setdefault(session, [])
        if args.approve not in d[session]:
            d[session].append(args.approve)
        save_approvals(d)
        print(f"approved: plan {args.approve} (session {session})")
        return 0

    return run_hook()


if __name__ == "__main__":
    sys.exit(main())
