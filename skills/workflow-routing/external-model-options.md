# External Model Options — skeleton for later

**Status: NOT WIRED UP.** Nothing in `~/.claude/` calls a non-Claude model.
The `gemini-*` agents were removed on 2026-08-06 because the CLI had no working
auth and silently fell back to Sonnet. This file exists so the decision can be
revisited with numbers instead of assumptions.

---

## 1. Current tiers (what you actually run)

| Tier | Model | In $/MTok | Out $/MTok | Context | Agents |
|---|---|---:|---:|---|---|
| cheap | Haiku 4.5 | 1.00 | 5.00 | 200K | `scanner`, `text-mechanic` |
| mid | Sonnet 5 | 3.00 (2.00 intro→2026-08-31) | 15.00 (10.00) | 1M | 12 agents |
| top | Opus 5 | 5.00 | 25.00 | 1M | 6 agents |
| max | Fable 5 | 10.00 | 50.00 | 1M | — |

Cache read ≈ 0.1×. Cache write 1.25× (5 min) / 2× (1 h). No long-context
premium. Batch API −50%, up to 24 h latency.

## 2. External candidates

| Vendor / tier | In $/MTok | Out $/MTok | vs Haiku 4.5 | Notes |
|---|---:|---:|---|---|
| Gemini 2.5 Flash-Lite | 0.10 | 0.40 | **~10× cheaper** | The only tier with a real cost edge |
| Gemini 3.1 Pro (<200K) | 2.00 | 12.00 | — | ≈ Sonnet 5 |
| Gemini 3.1 Pro (>200K) | **4.00** | 12.00 | — | **More than Sonnet 5 ($3.00)** — long-context edge is a myth here |
| *(add candidate)* | | | | |
| *(add candidate)* | | | | |

> ⚠️ Gemini **explicit context caching bills storage per hour**, independent of
> queries — measured at ~$5,183/month to hold a 1.6M-token corpus idle on Pro.
> Never cache a slow-changing corpus there; shard, warm briefly, let it expire.

## 3. When does it become worth it?

The only defensible use is **bulk mechanical reading at Flash-Lite tier**.
Per job of size *N* input tokens, the saving over Haiku 4.5 is `N × $0.90/MTok`:

| Job size | Haiku 4.5 | Flash-Lite | You save |
|---:|---:|---:|---:|
| 250K (kazanım index) | $0.25 | $0.025 | **$0.22** |
| 2M (whole docs corpus) | $2.00 | $0.20 | $1.80 |
| 20M (10 full passes) | $20.00 | $2.00 | $18.00 |
| 200M | $200.00 | $20.00 | $180.00 |

**Break-even against maintenance.** A second vendor costs: an API key to rotate,
an auth path that can die silently, a second failure mode, and a second set of
model IDs to keep current. Call that ~2 h/year of your time.

> **Rule of thumb: wire up an external tier only when a single job exceeds
> ~20M input tokens, or you run the corpus more than ~10× a month.**
> Below that you are optimizing a line item smaller than one coffee.

## 4. What does NOT justify it

- **"Saves Claude tokens."** A Claude *subagent* already isolates context —
  `scanner` returns ~400 tokens whether it read 10 files or 10,000. An external
  model adds no context isolation on top of that, only a price delta.
- **"Gemini is better at long context."** Not at Pro tier above 200K, where it
  costs more than Sonnet 5.
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
4. **Re-verify the price table before trusting it.** These numbers were correct
   on 2026-08-06 and both vendors reprice.
