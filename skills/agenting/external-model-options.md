# External Model Options — skeleton for later

**Status: NOT WIRED UP.** Nothing in `~/.claude/` calls a non-Claude model.
The `gemini-*` agents were removed on 2026-08-06 because the CLI had no working
auth and silently fell back to Sonnet. This file exists so the decision can be
revisited with numbers instead of assumptions.

---

## 1. Current tiers (what you actually run)

Prices verified 2026-10-05 against Anthropic's pricing page (Haiku 5.5 added and
re-checked there on 2026-10-09); source and the effort/capability evidence in
[`evals/research/2026-10-05-models.md`](../../evals/research/2026-10-05-models.md).

| Tier | Model | In $/MTok | Out $/MTok | Context | Agents |
|---|---|---:|---:|---|---|
| cheap | Haiku 5.5 | 0.10 (0.50 over 100K) | 0.50 (2.50 over 100K) | 1M | `scanner` |
| mid | Sonnet 5.5 | 2.00 | 10.00 | 1M | see the roster in the README |
| top | Opus 5.5 | 4.00 | 20.00 | 1M | see the roster in the README |
| max | Fable 5.1 | 10.00 | 50.00 | 1M | none |

Sonnet's $2/$10 was introductory pricing on Sonnet 5; it is now the permanent
price and Sonnet 5.5 launched at it. Cache reads are $0.01 (Haiku 5.5), $0.20
(Sonnet 5.5, Opus 5.5) and $0.25 (Fable 5.1) per MTok; cache writes are 1.25×
(5 min) or 2× (1 h) the input price. No long-context premium except Haiku 5.5,
which is priced per request: a prompt over 100K tokens pays 5× per token. Batch API
−50%, up to 24 h latency. Haiku 5.5 (released 2026-10-07, retirement not before
2027-10-07) honours `effort`; Haiku 4.5 (`claude-haiku-4-5-20251001`, $1/$5, no
effort parameter) is still active with retirement not before 2026-10-15. The `haiku`
alias resolves to Haiku 5.5 on CLI 2.1.295. The harness in
[`evals/`](../../evals/README.md) is how a replacement gets tested.

*Sonnet 5.5's cache read is shown at $0.20 as in the 10-05 note; the pricing page on
2026-10-09 gives $0.10 (0.05× input). Re-verify before relying on it.*

## 2. External candidates

| Vendor / tier | In $/MTok | Out $/MTok | vs Haiku 5.5 | Notes |
|---|---:|---:|---|---|
| Gemini 2.5 Flash-Lite | 0.10 | 0.40 | same input price, 20% cheaper output; **5× cheaper input** only for prompts over 100K | Was ~10× cheaper than Haiku 4.5; Haiku 5.5 closed most of that gap |
| Gemini 3.1 Pro (<200K) | 2.00 | 12.00 | — | ≈ Sonnet 5.5 |
| Gemini 3.1 Pro (>200K) | **4.00** | 12.00 | — | **Twice Sonnet 5.5's input price ($2.00)** — long-context edge is a myth here |
| *(add candidate)* | | | | |
| *(add candidate)* | | | | |

> ⚠️ Gemini **explicit context caching bills storage per hour**, independent of
> queries — measured at ~$5,183/month to hold a 1.6M-token corpus idle on Pro.
> Never cache a slow-changing corpus there; shard, warm briefly, let it expire.

## 3. When does it become worth it?

The only defensible use is **bulk mechanical reading at Flash-Lite tier**, and since
Haiku 5.5 it only exists for prompts Haiku 5.5 charges at its long-prompt rate.
Haiku 5.5 bills each request at $0.10/MTok when the prompt is up to 100K tokens and
$0.50/MTok above, so a corpus read in chunks under 100K costs the same input price
as Flash-Lite and saves nothing. For one unchunked prompt over 100K the saving over
Haiku 5.5 is `N × $0.40/MTok` (Flash-Lite figures unverified since 2026-08-06):

| Job size (prompts over 100K) | Haiku 5.5 | Flash-Lite | You save |
|---:|---:|---:|---:|
| 250K (kazanım index) | $0.125 | $0.025 | **$0.10** |
| 2M (whole docs corpus) | $1.00 | $0.20 | $0.80 |
| 20M (10 full passes) | $10.00 | $2.00 | $8.00 |
| 200M | $100.00 | $20.00 | $80.00 |
| any size, chunked under 100K | $0.10/MTok | $0.10/MTok | **$0** |

**Break-even against maintenance.** A second vendor costs: an API key to rotate,
an auth path that can die silently, a second failure mode, and a second set of
model IDs to keep current. Call that ~2 h/year of your time.

> **Rule of thumb: do not wire up an external tier for cost while Haiku 5.5 can read
> the job in chunks under 100K.** The saving is zero there. Revisit only for a job that
> cannot be chunked, above ~20M input tokens or more than ~10× a month. Below that you
> are optimizing a line item smaller than one coffee.

## 4. What does NOT justify it

- **"Saves Claude tokens."** A Claude *subagent* already isolates context —
  `scanner` returns ~400 tokens whether it read 10 files or 10,000. An external
  model adds no context isolation on top of that, only a price delta.
- **"Gemini is better at long context."** Not at Pro tier above 200K, where it
  costs more than Sonnet 5.5.
- **"It's free."** It is not free; it is cheap. The maintenance is the cost.

## 5. What WOULD justify it

- Sustained bulk OCR/extraction at the volumes in §3
- A genuinely independent second opinion for cross-checking (different vendor,
  different training) — quality, not cost
- Rate-limit headroom if Claude limits become the bottleneck

## 6. If you wire one up — the checklist

1. **Prove the auth end-to-end before anything else.** The last setup failed
   because `GEMINI_API_KEY` was unset while `settings.json` said
   `auth.selectedType = gemini-api-key`. A config file is not proof.
   `gemini -p "Reply PONG"` is.
2. **Make failure loud.** The old agents fell back to Sonnet silently, so
   "I delegated to Gemini" was false and invisible. Any external agent must
   report `EXTERNAL CALL FAILED` and stop, not quietly substitute.
3. **Pin it to one job shape**, not a whole layer. "Flash-Lite does the
   de-hyphenation pass" is maintainable; "Gemini is the junior dev tier" is not.
4. **Re-verify the price table before trusting it.** The Gemini numbers were correct
   on 2026-08-06 and not re-verified since; the Claude numbers were re-verified
   on 2026-10-05. Both vendors reprice.
