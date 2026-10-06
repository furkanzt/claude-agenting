# Sonnet 5.5 vs Opus 5.5: open-book abstention and verification (deep research, 2026-10-06)

Run: the `deep-research` workflow (5 search angles, 17 sources fetched, 80 claims extracted, 25 put to a 3-vote adversarial check, 11 confirmed, 14 killed). The question given to it covered open-book abstention; it was **not** given this harness's verification result (0 wrong verdicts in 96 for each of Sonnet `high` and Opus `high`), so where it says verification has no direct evidence it means no *published* evidence.

## Verdict

No source, vendor or independent, reports a detected Sonnet 5.5 vs Opus 5.5 difference on open-book abstention, and no published open-book or grounded benchmark covers either model. Our 0/102 vs 0/102 result is the only direct evidence. It bounds each model's hallucination rate below about 3% (95% one-sided), and 102 items cannot rule out a gap of roughly 3-5 points, so it is a bounded null rather than proof of equality. The differences that were detected are different constructs: a large closed-book recall gap (AA-Omniscience net 0.35 vs 0.58, Opus ahead), a small input-hallucination gap in the agentic audit (1.41 vs 1.27, Opus ahead, near the floor), and Sonnet 5.5 ahead on MASK honesty under pressure (94.5% vs 87.4%). On the card's own numbers the closed-book gap is knowledge, not abstention discipline: both models guess wrong on 71% of the items they do not get right. The evidence does not justify keeping BELİRSİZ-style abstention on Opus by default, so Sonnet 5.5 xhigh can take it. Adversarial verification of claimed findings has no direct evidence for either model, so that task type should get its own paired test before it moves.

## Findings

### 1. (high confidence; vote 3-0 (Opus card), 2-1 (suprmind page; corroborated by primary cards))

There is no published open-book or context-grounded abstention or hallucination result for Sonnet 5.5 or Opus 5.5. The Opus 5.5 card has no Sonnet 5.5 results and no open-book abstention benchmark. The Sonnet 5.5 card has only closed-book AA-Omniscience, MASK and an agentic audit. Aggregator grounded columns (Vectara, FACTS, HalluHard) are empty for both models. Nothing in the literature found directly tests adversarial verification of claimed findings either. The direct evidence on tier difference is therefore our own harness.

Sources: https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf, https://www.anthropic.com/claude-sonnet-5-5-system-card, https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/

### 2. (high confidence; vote 3-0)

The closest vendor-published metric to open-book hallucination, Input hallucination (misrepresenting the contents of files, tool outputs or past user turns), shows a small but statistically detectable Opus advantage: Sonnet 5.5 1.41 vs Opus 5.5 1.27 on a 1-10 scale where lower is better. The 95% CIs do not overlap. The gap is only 0.14 points, both models sit near the 1.0 floor, and it is an LLM-judged audit score over simulated agentic transcripts. It is not a count of fabricated answers to unanswerable document questions, so it does not transfer directly to BELİRSİZ.

Sources: https://www.anthropic.com/claude-sonnet-5-5-system-card, https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf

### 3. (high confidence; vote 3-0)

The card's own summary of the two models is mixed, so neither tier is uniformly better on honesty-type tasks. Sonnet 5.5 is more honest under pressure than Opus 5.5 (MASK honesty rate 94.5% vs 87.4%, non-overlapping CIs) but hallucinates more on closed-book factual recall. Opus is better on most audit metrics (see finding 2). The direction of the tier gap flips with the construct measured.

Sources: https://www.anthropic.com/claude-sonnet-5-5-system-card

### 4. (medium confidence; vote 3-0 (claim 4), 3-0 (claim 1); a stronger related claim was refuted 1-2)

The closed-book hallucination gap between Opus and Sonnet is mostly a knowledge gap, not an abstention-discipline gap. On the Sonnet 5.5 card's own AA-Omniscience figures both models guess wrong on the same share of the items they do not get right: 0.27/(0.27+0.11) = 0.71 for Sonnet 5.5 and 0.17/(0.17+0.07) = 0.71 for Opus 5.5. Opus simply gets more right (0.76 vs 0.62). The Opus 5.5 card (Sonnet 5 only) shows the same pattern: Opus 5.5 is ahead on net score (0.58 vs 0.23) and correct answers (0.76 vs 0.47), and Sonnet 5 abstains more (0.28 vs 0.07). Sonnet 5 must not be used as a stand-in for Sonnet 5.5.

Sources: https://www.anthropic.com/claude-sonnet-5-5-system-card, https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf

### 5. (high confidence; vote 3-0 (AA paper), 3-0 (index mechanics))

AA-Omniscience and similar closed-book benchmarks (and SimpleQA-type recall tests) do not measure the open-book 'source is silent' behavior, and transfer is unproven. The benchmark gives models no context and no tools. The index rewards correct answers, penalizes wrong ones and gives 0 for abstaining, so a model with weaker recall scores lower even if its abstention on provided text is identical.

Sources: https://arxiv.org/html/2511.13029v1, https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-high-vs-claude-opus-5-5-low, https://www.anthropic.com/claude-sonnet-5-5-system-card, https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf

### 6. (medium confidence; vote 2-1 (comparison page), 3-0 (index mechanics claim))

Where Artificial Analysis does detect a tier difference, it is on closed-book recall and it is large: AA-Omniscience Index Sonnet 5.5 High 21 vs Opus 5.5 Low 39. The direction holds at matched effort (xhigh vs xhigh 24 vs 43) and at default or max (32 vs 46). That this is a real recall/calibration gap, not an effort artefact, says nothing about open-book abstention. The page does not break out the accuracy and hallucination-rate components.

Sources: https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-high-vs-claude-opus-5-5-low, https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-xhigh-vs-claude-opus-5-5-xhigh

### 7. (low confidence; vote 2-1)

Within the Claude family a tier label does not reliably predict abstention-like behavior; it has to be measured per model and per task. In PhantomFill's required-field schema rung (json_req), Haiku 4.5 refused 40/40, Sonnet 4.6 fabricated in 90%, and Opus 4.8 fabricated in 13% (refused 39/53). The ordering is not monotonic in tier or release date. This covers 4.x models only and gives no evidence about 5.5. The same paper's free-text and escape-available rungs showed a very large Sonnet-vs-Opus gap on those older models, so this finding cuts against assuming tier equivalence as much as against assuming Opus superiority.

Sources: https://arxiv.org/html/2607.20492

### 8. (high confidence; vote 3-0 (Miller formula), 3-0 (paired formula))

0/102 vs 0/102 is a bounded null, not evidence of equality. Each rate is bounded below about 3% (rule of three 2.9%; Clopper-Pearson two-sided 3.55%), so a true gap of a few points would not be detected. Verifier-computed Fisher power at n=102 is about 8.5% for 3% vs 0%, about 40% for 5% vs 0% and about 95% for 10% vs 0%. Textbook sample-size formulas (Miller's closed form giving about 969 items for a 3-point difference with a continuous score; the paired Connor/McNemar form N* = (z+z)^2*sigma_D^2/(pA-pB)^2) are normal approximations. With both failure counts at 0, sigma_D^2 = 0 and N* is 0/0, so the planning method is to pick a target delta and an assumed discordant rate and use an exact test on the discordant pairs.

Sources: https://arxiv.org/pdf/2411.00640, https://arxiv.org/pdf/2605.30315

### 9. (low confidence; vote 0-3 / 1-2 on the candidate claims; none survived)

Which kinds of unanswerable items separate model tiers is not established by any claim that survived verification. Candidate hypotheses were all rejected or unverified: that closed-set or enum answer slots separate tiers (refuted 0-3), that BBQ-style ambiguous items are saturated for Opus (refuted 0-3, though the Opus card prints Opus 5.5 at 99.99% vs Sonnet 5 at 98.60%), that Vectara-style leaderboards order Anthropic tiers (refuted 1-2 and 0-3), and that AbstentionBench shows scale does not help or that reasoning lowers abstention (refuted 0-3, abstract-only evidence). Our harness found that Haiku 4.5 separates from both big models (19/102), so the items discriminate at the low end but are at floor for the top two tiers.

Sources: https://arxiv.org/html/2607.20492, https://arxiv.org/abs/2506.09038, https://github.com/vectara/hallucination-leaderboard/, https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf

### 10. (medium confidence; vote n/a (synthesis))

Decision implication. The evidence supports routing open-book abstention (BELİRSİZ-style) to Sonnet 5.5 xhigh: no published or harness-detected difference exists, the detected tier differences are on other constructs, and the one closed-book gap is knowledge rather than abstention discipline. The justification is bounded, meaning a gap under about 3-5 points is not excluded, and the only vendor signal that favors Opus is a small input-hallucination gap in the agentic audit. Adversarial verification of claimed findings is a different task with no direct evidence for either model, so moving it needs its own paired test (same items to both models, exact test on the discordant pairs, items harder than the current set).

Sources: https://www.anthropic.com/claude-sonnet-5-5-system-card, https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf, https://arxiv.org/html/2511.13029v1, https://arxiv.org/pdf/2411.00640

## Caveats

Absence of published evidence is not evidence of equality. The decision rests on an underpowered null (0/102 vs 0/102, upper bound about 3%) and on the lack of any grounded benchmark for either model. All vendor data are self-reported and dated Sept 22 and 28, 2026, so they are under two weeks old. Vectara, FACTS Grounding, HalluHard or AA could add 5.5 rows soon and change the picture. Several key numbers (input hallucination, MASK, AA-Omniscience breakdowns) were read from figure images, though the printed labels were checked. The AA component numbers (accuracy 54% vs 66%, hallucination rate 47% vs 59%) come from secondary sites, and verifiers disagreed about suprmind's reliability (stale dates, one row reportedly duplicated), so treat them as low weight. The AA hallucination-rate direction (Sonnet lower) conflicts with the card's net-score direction, because the metrics are defined differently. The PhantomFill preprint is single-author, non-peer-reviewed, covers only Haiku 4.5, Sonnet 4.6 and Opus 4.8 and tests forced fabrication with no escape, so it does not apply to 5.5. Many sub-claims were rejected by the voters, including all claims about item types that separate tiers, AbstentionBench scaling effects, Vectara tier ordering and the leaderboard-scale power claims. Some rejections looked odd against the verifier notes (for example the paired-SE claim, where Miller's paper does recommend paired analysis), so those stay unresolved, not disproven. Verifiers ran out of WebSearch budget (200/200), so the searches for contradicting evidence were limited to direct fetches. The power numbers at n=102 and the roughly 250 and 860 item estimates are verifier-computed approximations, not published figures. Nothing found tests adversarial verification of claimed findings directly. Our harness itself was not independently reviewed.

## Open questions

- Does Sonnet 5.5 differ from Opus 5.5 on adversarial verification of claimed findings (rejecting wrong or unsupported claims while accepting correct ones)? No source tested this, so it needs a dedicated paired harness with an exact discordant-pair test.
- Which unanswerable-item types separate the two top tiers on open-book tasks (near-miss or partially supported questions, closed-set answer slots, long or multi-document context, multi-hop)? Our items are at floor for both models, so a harder set (and likely 250 or more items for a 3-point effect) is needed to find any gap.
- Will Vectara HHEM, FACTS Grounding or HalluHard publish rows for Sonnet 5.5 and Opus 5.5, and will Artificial Analysis publish the Omniscience accuracy and hallucination-rate components at matched xhigh effort, so the direction of the closed-book abstention gap can be settled?
- Does the 1.41 vs 1.27 input-hallucination gap in the agentic audit show up on long-document, tool-output-heavy workloads like ours, and is a gap of about 0.14 points on a near-floor 1-10 scale practically meaningful for the BELİRSİZ pipeline?

## Claims the voters rejected (do not rely on these)

- On closed-book AA-Omniscience, Sonnet 5.5 is clearly worse than Opus 5.5. Net score is 0.35 vs 0.58. Fraction incorrect is about 0.27 vs 0.17, correct about 0.62 vs 0.76, and abstained (Unsure) about 0.11 vs 0.07. These Opus 5.5 and Sonnet 5.5 figures are read from Figures 6.3.2.1.A and B, not stated in prose. Sonnet 5.5 therefore abstains less and answers wrongly more than Opus 5.5 when the model has to rely on its  (vote 1-2; https://www.anthropic.com/claude-sonnet-5-5-system-card)
- In a form-filling task with an explicit escape value available (json_esc rung), Sonnet 4.6 and Opus 4.8 separated sharply. Escape utilization was Sonnet 10%, Haiku 42%, Opus 91%. That is a large tier gap in abstention behavior, but it is measured on the previous Claude generation (Sonnet 4.6 and Opus 4.8, not 5.5) and on synthetic form-filling, not open-book QA with a provided document. (vote 1-2; https://arxiv.org/html/2607.20492)
- Which unanswerable items separate models depends on the answer slot. Closed-vocabulary enum fields and minimum-count arrays drive near-universal fabrication, while free-string fields that can carry a disclaimer are resisted. Sonnet 4.6 fabricated crowd sentiment in 90% of social-thread trials but refused to fabricate a customer's words in 100% of ticket trials. For GPT-5.5 on tickets, customer_sentiment (enum) fabric (vote 0-3; https://arxiv.org/html/2607.20492)
- Larger scale does not reliably predict lower hallucination (a tier-agnostic finding): size predicts accuracy but not hallucination rate or Omniscience Index, and several small models beat larger peers. This weakens the assumption that Opus-tier is inherently safer than Sonnet-tier on abstention, at least in the closed-book setting. (vote 0-3; https://arxiv.org/html/2511.13029v1)
- AbstentionBench evaluates 20 frontier LLMs on 20 abstention datasets and concludes that abstention is unsolved and that scaling model size gives little benefit. This bears on whether a bigger tier (Opus) would abstain better than a smaller tier (Sonnet). The abstract is the only text checked, so the per-model results are unverified and the models tested predate the 5.5 generation. (vote 0-3; https://arxiv.org/abs/2506.09038)
- Reasoning fine-tuning lowers abstention by 24% on average, including in math and science domains the reasoning models were trained on. If this holds, more reasoning effort (xhigh) could hurt abstention rather than help, so a null difference between Sonnet and Opus at xhigh would not be surprising. The abstract does not say whether the effect holds for the 5.5 generation. (vote 0-3; https://arxiv.org/abs/2506.09038)
- The Vectara leaderboard shows no consistent tier ordering among Anthropic models on grounded-summarization hallucination. Haiku 4.5 (9.8%) is lower than Sonnet 4.6 (10.6%), Opus 4.5 (10.9%), Opus 4.7 (12.0%) and Opus 4.6 (12.2%). Larger or newer tiers are not better on this metric, so it does not detect a Sonnet vs Opus difference. (vote 1-2; https://github.com/vectara/hallucination-leaderboard/)
- The benchmark filters out refusals and scores only documents that every model summarized. A model's willingness to abstain on insufficient content therefore does not enter the hallucination rate, so the leaderboard does not measure open-book abstention (BELİRSİZ-style behavior). It only measures factual consistency of produced summaries. (vote 0-3; https://github.com/vectara/hallucination-leaderboard/)
- The card's closest context-grounded abstention proxy, BBQ ambiguous questions (correct answer is unknown), is at ceiling for both tiers. Opus 5.5 scores 99.99% and Sonnet 5 scores 98.60%, a gap of about 1.4 points. On disambiguated questions, where the model must commit to an answer the context supports, the gap is larger: Opus 5.5 89.65% vs Sonnet 5 72.36%. This suggests say unknown when the context does not settle  (vote 0-3; https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf)
- The paper's own power analysis: with about 30 items per hallucination type, the minimum detectable effect is 20-26 percentage points. A tier gap smaller than that, such as 0.072 vs 0.127 FPR, cannot be resolved at per-type n of about 30. This bears directly on how many unanswerable items are needed, and 0 of 102 per model would be a bounded-rate result, not proof of equality. (vote 0-3; https://arxiv.org/html/2607.18360)
- Comparing two models on the same questions with a paired analysis gives a smaller standard error than an unpaired comparison whenever the models' per-question scores are positively correlated. This applies to Sonnet 5.5 vs Opus 5.5 scored on the same 102 unanswerable items. The paper recommends paired SE, CI and correlation reporting wherever two models are compared. (vote 0-3; https://arxiv.org/pdf/2411.00640)
- On real leaderboards at (alpha, power) = (0.05, 0.8), small gaps are not resolvable at benchmark sizes of roughly 1k-12k items. Every pair with |delta| <= 2 pp was unresolved and every pair with |delta| > 5 pp was resolved. Headline: 11/40 Open LLM Leaderboard v1 pairs and 4/9 MMLU-Pro adjacent pairs are unresolved. So distinguishing near-equal models takes thousands of items, far more than 102. (vote 1-2; https://arxiv.org/pdf/2605.30315)
- On closed-book AA-Omniscience (max-with-fallback runs), Opus 5.5 beats Sonnet 5.5 on accuracy (66.2% vs 53.9%) and Index (46.4 vs 32.3), but Opus 5.5 has the HIGHER hallucination (overconfidence) rate: 58.6% vs 47.0%. So the closed-book benchmark detects a tier difference, and the direction on abstention calibration favors Sonnet 5.5, not Opus 5.5. (vote 0-3; https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/)
- The page's own methodology says closed-book and grounded metrics measure different things and do not transfer. A model can score well on grounded summarization yet badly on admitting ignorance, and reasoning mode helps open-ended tasks while hurting grounded ones. This supports the view that AA-Omniscience and SimpleQA results cannot be used as a proxy for source-bound BELİRSİZ behavior. Evidence cited: Llama 4 Maver (vote 0-3; https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/)

## Sources

- [primary] https://www.anthropic.com/claude-sonnet-5-5-system-card (Vendor system cards (primary), 5 claims)
- [secondary] https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/ (Vendor system cards (primary), 5 claims)
- [blog] https://thezvi.substack.com/p/claude-opus-55-the-system-card (Vendor system cards (primary), 3 claims)
- [primary] https://arxiv.org/html/2607.20492 (Open-book / grounded abstention benchmarks, 5 claims)
- [primary] https://arxiv.org/html/2511.13029v1 (Closed-book transfer to open-book, 5 claims)
- [secondary] https://artificialanalysis.ai/models/comparisons/claude-sonnet-5-5-high-vs-claude-opus-5-5-low (Closed-book transfer to open-book, 4 claims)
- [primary] https://arxiv.org/abs/2506.09038 (Closed-book transfer to open-book, 5 claims)
- [primary] https://github.com/vectara/hallucination-leaderboard/ (Closed-book transfer to open-book, 5 claims)
- [primary] https://www-cdn.anthropic.com/fc1b44717c85dc068bc6ba5024219938094694bd/Claude%20Opus%205.5%20System%20Card.pdf (Closed-book transfer to open-book, 5 claims)
- [secondary] https://x.com/bridgemindai/status/2024117967508635846 (Closed-book transfer to open-book, 4 claims)
- [primary] https://arxiv.org/html/2607.18360 (Adversarial verification / sycophancy, 4 claims)
- [blog] https://dev.to/alex_spinov/zero-failures-isnt-zero-risk-the-rule-of-three-for-evals-4hcd (Statistical power / sample size, 5 claims)
- [primary] https://arxiv.org/pdf/2411.00640 (Statistical power / sample size, 5 claims)
- [primary] https://arxiv.org/pdf/2605.30315 (Statistical power / sample size, 5 claims)
- [primary] https://aclanthology.org/2026.lrec-1.353.pdf (Statistical power / sample size, 5 claims)
- [blog] https://tianpan.co/blog/2026/04/15/statistical-power-llm-evals (Statistical power / sample size, 5 claims)
- [secondary] https://en.wikipedia.org/wiki/Rule_of_three_(statistics) (Statistical power / sample size, 5 claims)

## Stats

{"angles": 5, "sourcesFetched": 17, "claimsExtracted": 80, "claimsVerified": 25, "confirmed": 11, "killed": 14, "unverified": 0, "afterSynthesis": 10, "urlDupes": 5, "budgetDropped": 7, "agentCalls": 99}
