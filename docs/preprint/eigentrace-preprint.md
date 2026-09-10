# EigenTrace: deterministic measurement of what frontier language models keep, drop and soften when they summarize news

Preprint skeleton. Draft of 2026-09-10. Status: not peer-reviewed; sections marked OWNER: are for the project owner to write or confirm.

Source tags: every number carries a tag of the form [src: docs/page.md] (a site page under `docs/`, read as rendered text; only `index.md` is markdown in the tree, the other pages are `docs/page.html` and the `.md` tag names the page, not a file), [src: report YYYY-MM-DD §section] (one of the four session reports of September 2026), or [UNVERIFIED] (a number that appears on the site but that no script or data file in the tree reproduces, per [src: report 2026-09-05 §5]). Where the site and the code disagree the disagreement is stated, not resolved.

Definitions: `docs/metrics.md` was absent when this draft was written (checked 2026-09-10). The formulas in §3 are copied from the environment definitions supplied for this draft and from `[src: report 2026-09-05 §3]`. OWNER: when `docs/metrics.md` lands, replace §3.1 to §3.4 with its text verbatim and delete this paragraph.

---

## Abstract (draft, measured claims only)

EigenTrace measures what five frontier language models (ChatGPT, Claude, Gemini, DeepSeek, Grok) keep, drop and soften when they summarize the same news story. Each summary is embedded once with a frozen model (BAAI/bge-large-en-v1.5, 1,024 dimensions) and every score is deterministic arithmetic on those vectors; no language model grades another in the measurement path [src: docs/index.md]. We report: (1) a pre-registered entity-swap test on nine matched incident pairs in which semantic retention of a consequential modifier is 0.522 when the actor is an AI developer and 0.545 when it is a conventional corporation (Welch's t, p = 0.0085, d = 0.47), with a within-category swap moving retention by 0.004 against 0.023 across categories [src: docs/index.md; docs/boundary.md]; (2) a frontier-model judge reading the same 216 summaries one at a time rates 96% "modifier fully preserved", so the geometric signal is not visible to item-level LLM judging [src: docs/index.md]; (3) heavily aligned and lightly tuned models show the effect at indistinguishable strength (p = 0.46) [src: docs/index.md] [UNVERIFIED: no reproducing script found, src: report 2026-09-05 §5]; (4) across 1,659 stories the concepts absent from all five summaries sit closer to their story's content than random words (Wilcoxon p < 1e-5, two embedding families) [src: docs/index.md; see §5.4 for the 150-story discrepancy]; (5) on 277 recent stories the residual direction (source embedding minus panel centroid) separates dropped from kept source words (63% of stories, sign test p = 1e-5) and points at omitted claims (75%, p = 5e-16) [src: report 2026-09-09 §Test 1]. Withdrawn claims and failed controls are reported alongside.

OWNER: trim to 200 words once the numbers above are confirmed against the dataset v1 release.

---

## 1. Introduction

### 1.1 Measurement, not verdict

A summary is a lossy transform of its source. The question this instrument asks is not whether a summary is good but what, specifically, the transform removed, added or softened, and whether five models built by five different labs do the same thing to the same text. The site states the framing in one line: "A measurement, not a verdict" [src: docs/index.md]. Nothing in the method decides whether a given omission was justified; it records that the omission happened and how large it is in a fixed geometric space.

### 1.2 What LLM-as-judge cannot do

The common evaluation pattern asks one model to score another model's faithfulness. That judge is retrained on its own schedule, so its scores drift; it cannot say what changed between source and summary; and item-by-item review misses small systematic shifts. The one measured comparison in this project: a frontier-model judge shown the 216 summaries from the entity-swap experiment rated 96% of them "modifier fully preserved", while the geometric retention score on the same summaries separates the two conditions at p = 0.0085 [src: docs/index.md]. OWNER: name the judge model, the prompt and the script (`prefilter_validation_v3.py` contains the string "fully preserved"; confirm it is the run reported).

### 1.3 What this instrument is

A pipeline that, for each ingested news story, (a) asks five frontier models for a summary under one fixed prompt, (b) embeds the source and the summaries with one frozen embedding model, (c) computes a set of deterministic scores from those vectors and from lexical comparison with the source, and (d) stores everything as a JSON segment. It has run continuously on one consumer GPU since spring 2026, with outages recorded in [src: report 2026-09-06 preamble]. The site describes several derived layers (a narrating local model, a self-audit, a broadcast). This preprint covers only the measurement path; the derived layers are out of scope except where they touch the numbers.

OWNER: one paragraph on why news, why five vendors, why hourly.

---

## 2. Related work

TODO bullets. Cite by name only; `refs.bib` carries entries only for items that can be identified unambiguously, each marked TODO-verify. Do not add references here that have not been read.

- Summarization faithfulness metrics: FactCC, QAGS, FEQA, QuestEval, FRANK, SummaC, AlignScore; the 2026 omission-taxonomy papers named in [src: report 2026-09-09 (site critique) §2d]; FaithBench and FABLES as human-labeled omission/faithfulness benchmarks [src: report 2026-09-09 (site critique) §2d]. TODO: which of these measure omission (recall of source content) as opposed to hallucination (precision), since this instrument measures omission.
- Embedding-based evaluation: BERTScore, MoverScore, cosine-to-reference metrics; the embedding models used here (bge-large-en-v1.5; e5-large as the second family on the Iran page) [src: docs/llm-consensus-geometry-iran-2026.md].
- LLM-as-judge critiques: position bias, self-preference, verbosity bias, drift across judge versions; "Judging LLM-as-a-judge" (Zheng et al.); "LLM evaluators recognize and favor their own generations" (Panickssery et al.). TODO-verify both.
- Disagreement among generations as a signal: SelfCheckGPT; semantic entropy (Kuhn et al.; Farquhar et al.). Named as the lineage of the agreement side of this instrument in [src: report 2026-09-06 §1C].
- Monoculture and homogenization of model outputs: algorithmic monoculture (Kleinberg and Raghavan; Bommasani et al.); homogenization of writing and ideation under LLM assistance (Padmakumar and He; Anderson et al.). TODO-verify. The site's "five labs, same blind spots" claim [src: docs/index.md] belongs to this literature.
- Pyramid / summary content units and Krippendorff's alpha, as the labeling protocol the gold set will use [src: report 2026-09-06 §3C].

OWNER: write the prose once the bullets are verified.

---

## 3. Method

### 3.1 Embedding

All texts are embedded with BAAI/bge-large-en-v1.5, 1,024 dimensions, L2-normalized, on CPU [src: report 2026-09-05 §2]. The model is frozen; the same text always yields the same vector. Let e_1 … e_N be the unit embeddings of the N model summaries for one story (N = 5 when all vendors respond), let c = (1/N) Σ e_i be the centroid and ĉ = c/‖c‖.

### 3.2 Consensus density

density = mean over i < j of cos(e_i, e_j), the mean pairwise cosine of the five summary embeddings [environment definition; src: report 2026-09-05 §3 "Consensus density"].

Measured range in production: median 0.902 over 9,395 registry rows, 86% of rows in [0.85, 0.95]; monthly standard deviation fell from 0.045 (March 2026) to 0.017 (September 2026) [src: report 2026-09-05 §3].

### 3.3 Per-model divergence (VIX) and mean VIX

Per-model VIX_i = 500 · (1 − cos(e_i, ĉ)), clipped to [0, 100] in production [environment definition; src: report 2026-09-05 §3 "Per-model VIX"]. It is a one-shot distance from the panel's own centroid, not a volatility.

Mean VIX = 500 · (1 − sqrt((1 + (N − 1) · density) / N)) [environment definition]. This follows because for unit vectors the mean cosine to ĉ equals ‖c‖ and ‖c‖² = (1 + (N − 1)·density)/N. Consequence: mean VIX is a deterministic function of density and is not an independent measurement. Verified on 9,113 registry rows: median gap between the aired mean VIX and the identity is 0.05 points, 99.6% within one point, correlation with density −0.996 [src: report 2026-09-05 §3 "Mean VIX and the state flag"]. This preprint therefore reports density and per-model VIX only.

Per-model VIX is the most informative channel: per-model spread 6 to 13 points, pairwise correlations between models 0.32 to 0.60; 46 rows hit the clip [src: report 2026-09-05 §3].

### 3.4 Killshot claims (claim-level omission)

A local model (Mistral Small, via Ollama) extracts atomic claims from the headline plus the RSS blurb (not the article body). salience(claim) = cos(claim, headline). For each model, cos(claim, summary) ≥ 0.75 counts as covered, ≥ 0.65 partial, else the model is listed in omitted_by. A killshot is a claim with salience ≥ 0.45, covered by ≤ 20% of models, and omitted by at least one [environment definition; src: report 2026-09-05 §3 "Killshot claims"].

Known defect: in the stored data 44% of 3,530 audited killshots have an empty omitted_by (every model scored partial), which the environment definition's "omitted by at least one" clause now excludes [src: report 2026-09-05 §3]. The 0.75 / 0.65 thresholds are not calibrated against entailment [src: report 2026-09-06 §1C].

### 3.5 Source void (absent words) and absent ratio

Source text = title + blurb + body[:1500]; alphabetic tokens of four or more characters minus a 90-word stoplist; absent = source words whose Porter stem appears in no model's summary, minus title derivatives; absent_ratio = |absent| / |source words| [src: report 2026-09-05 §3 "Source void"]. Measured: absent_ratio 0 to 0.525, mean 0.21; exactly 0 in 16 of 300 recent segments, which looks like a missing source body rather than a real reading [src: report 2026-09-05 §3]. Data-quality note: 226 of 300 stored bodies (75%) contain feed boilerplate ("Recommended Stories", "published"), which inflates absent counts until stripped [src: report 2026-09-06 §1C].

### 3.6 Word-level semantic retention

Retention of a source word = max over summary sentences of cos(embed(word), embed(sentence)). A paraphrased synonym counts as retained; a dropped single modifier moves a sentence embedding only slightly, so the score is conservative about modifier loss [src: docs/boundary.md "Method & reproducibility"]. This is the score behind the entity-swap, charged-language and cutoff results (§5.1 to §5.3).

### 3.7 Compression signature (verb downgrade, entity retention, hedges)

verb_downgrade = clip((mean Zipf frequency of response verbs − mean Zipf frequency of source verbs) / 2, 0, 1); entity_retention = share of capitalized source tokens found as substrings in the response; hedge count = distinct typed-lexicon hedge words in the response that are not in the source; composite = 0.4·verb + 0.3·(1 − retention) + 0.3·min(hedges/3, 1) [src: report 2026-09-05 §3 "Compression"]. Known defect: verb_downgrade is exactly 0 in 78% of stored values because a missing verb measurement collapses to 0 [src: report 2026-09-05 §3]. Entity retention (0.33 to 0.83) and the composite (0.09 to 0.58) are informative [src: report 2026-09-05 §3].

### 3.8 Concept surfacing: void words, logos words, SVD null space

Three production channels surface vocabulary the summaries did not use. They are described here so that the site's claims can be read against the code; none is used as a headline result in this preprint.

- Void words (aired): the 200 vocabulary entries nearest the headline embedding, filtered to words absent from all summaries, top 5 by headline similarity [src: report 2026-09-05 §3 "Void words"]. Ranking is by headline relevance, not by avoidance. A second definition, the annular "in-domain void" (near the headline, far from the centroid), exists and feeds only secondary outputs [src: report 2026-09-05 §3].
- Logos words: 150 AdamW steps on the unit sphere from the normalized centroid, loss = mean(1 − cos(x, e_i)) + 0.75·cos(x, centroid) − 0.30·cos(x, headline); read out the 25 nearest vocabulary words, drop stems any model used, keep 5 [src: report 2026-09-05 §3 "Logos words"]. Because the loss is linear in x on the sphere, the minimizer is a fixed blend of centroid and headline (about 0.22·centroid + 0.30·headline at measured densities); the stem filter does the work of producing unused words [src: report 2026-09-05 §3].
- SVD null space: stack the five embeddings, mean-center, economy SVD, last right-singular vector; claims ranked by |cos| to it [src: report 2026-09-05 §3 "SVD null space"]. Five mean-centered rows have rank at most four, so the smallest singular value is numerically zero and the vector is one arbitrary direction in a 1,020-dimensional complement; null_alignment is negative in more than 95% of 3,091 audited claims [src: report 2026-09-05 §3].

### 3.9 Residual direction (introduced 2026-09-09)

r = e(source) − c, the source embedding minus the panel centroid. Tested as a direction of loss by comparing cos(r, ·) for dropped words, kept words, killshot claims and random words on the same story [src: report 2026-09-09 §Test 1]. Results in §5.6.

### 3.10 Summary Plus

A rewrite step: a model is given the title, its own summary and a list of surfaced words (never the source) and asked to rewrite under a fixed "read the negative space" discipline [src: report 2026-09-09 §Test 2; docs/summary-plus.md]. Two surfacings exist: a centroid raycast (vocab @ anchor, keep words absent from the summaries) and a "convergence" surfacing over source sentences [src: docs/summary-plus.md "How it works"]. Judged by a blind panel of the five frontier models on 1–5 insight and faithfulness scales, with the author model excluded only from judging its own output [src: docs/summary-plus.md; report 2026-09-05 §5 "The Summary Plus head-to-head uses the five frontier models as their own judges (ex-self)"].

### 3.11 Pipeline

1. Ingest RSS items; fetch the article body with trafilatura (boilerplate is currently not stripped, §3.5).
2. Prompt five vendor models with one fixed summarization prompt ("Be direct. No disclaimers." per the code; the Iran page's "do not fact-check" wording differs [src: report 2026-09-05 §5]). API calls run at temperature 0 [src: report 2026-09-06 §1C].
3. Embed source, summaries and claims with the frozen model.
4. Compute §3.2 to §3.8; extract killshots with the local model.
5. Write one segment JSON per story with attribution fields (story_title, story_url, model_responses, model_vix, consensus_density, source_void, killshots, compression, summary_plus, …).
6. Export a daily public JSON without article bodies [src: report 2026-09-06 §1D "Public daily dataset"].

Panel size varies: in the last 300 audit rows the panel had 4 models in 237 and 5 in 63; Claude was absent from 84% of recent segments [src: report 2026-09-06 appendix; report 2026-09-05 §4]. Density, coverage and omission are not normalized for panel size [src: report 2026-09-05 §4]. OWNER: state the normalization used in dataset v1.

---

## 4. Data

Dataset v1 is being assembled separately; see `dataset/README.md` (not present in the tree on 2026-09-10; OWNER: link when it lands). Article bodies are publishers' text and are not distributed; model outputs, titles, URLs, RSS blurbs and measurements are.

Story counts stated on the site, with their pages:

| count | what | source |
|---|---|---|
| 13,307 | story segment files in the private segments directory (2026-09-06) | [src: report 2026-09-06 §1B] |
| 9,395 | registry rows with a density value | [src: report 2026-09-05 §3] |
| 2,201 | stories with a source body of 40+ words, refusals removed (Outliers page corpus, April–June 2026) | [src: docs/large-language-model-outliers.md] |
| 2,171 | stories in the kind-vs-magnitude agreement test | [src: docs/large-language-model-outliers.md] |
| 1,659 | "real news stories" in the Atlas corpus (corrected from 5,170) | [src: docs/consequence-atlas.md; docs/withdrawals.md] |
| 1,592 | stories in the charged-language retention test | [src: docs/boundary.md] |
| 781 / 484 / 31 | Atlas domain buckets: war / other conflict / general | [src: docs/consequence-atlas.md] |
| 510 | Iran-conflict segments, April 16 – June 18, 2026 | [src: docs/llm-consensus-geometry-iran-2026.md] |
| 300 | newest stories with five summaries, five rewrites and a 400+ character body (residual tests) | [src: report 2026-09-09 preamble] |
| 150 | stories in the random-word baseline script | [src: docs/consequence-atlas.md; report 2026-09-05 §5] |
| 22k+ / 18,000+ | "stories measured" / "segments" on overview and dynamics pages; these count all segment types, not stories | [src: docs/overview.md; docs/dynamics.md; report 2026-09-06 §1B] [UNVERIFIED as story counts] |

The story-count triad (1,592 / 1,659 / 150) is inconsistent across pages and code [src: report 2026-09-06 §1D]. OWNER: dataset v1 must fix one denominator per result and this table must be rewritten from it.

Thin-source regime: roughly 75% of ingested stories supplied only a headline and one sentence (median 14 source words); on those the models confabulate, and every measured finding on the Outliers page excludes them [src: docs/large-language-model-outliers.md §01].

---

## 5. Results

Each subsection: the claim, the number, n, the test, the source page, and what the code review found.

### 5.1 Entity swap: the modifier survives less when the actor is an AI developer

Nine matched real incidents, identical sentence structure and modifiers ("quietly", "secretly"), only the company name changed (Boeing / Wells Fargo / Goldman vs OpenAI / Google / Anthropic). Semantic modifier retention 0.522 (AI developer) vs 0.545 (conventional corporation); Welch's t = 2.79, p = 0.0085, Cohen's d = 0.47 [src: docs/index.md; docs/boundary.md; docs/overview.md]. Committed null: within-category swap moves retention 0.004, cross-category 0.023 [src: docs/index.md]. Binary keyword retention shows no gap (26% vs 25%) [src: docs/index.md; docs/overview.md]. Pre-registered [src: docs/boundary.md]. n of summaries = 216 [src: docs/index.md]. Script: `entity_swap_experiment.py` (present in tree; OWNER: confirm it reproduces the numbers).

### 5.2 Charged language is retained more than institutional language

Across 1,592 stories and 106,412 terms, words leaning operational/consequential were retained +0.020 more than institutional/structural words; Welch's t, p < 1e-200, d = 0.35; label-shuffle null cleared; holds in all five frequency bands; IDF explains R² ≈ 0.002 of the variance [src: docs/boundary.md "Finding two"]. OWNER: name the script; none was identified in the tree during this draft. [UNVERIFIED: script not located]

### 5.3 Post-cutoff names are under-retained

Named figures who became prominent after the models' cutoff (about mid-2024) are retained less than established ones: d = 0.75, p < 1e-6 on English-only names; retention 0.48 for a sitting post-cutoff president (Pezeshkian) vs 0.65 for established heads of state; Khamenei 0.66, Xi 0.57 as the transliteration control [src: docs/boundary.md "Finding three"; docs/anamnesis.md]. The name list was chosen after inspecting the data; not pre-registered [src: docs/boundary.md "Honest limits"]. Code review: `docs/cutoff_retention.json` does not exist, so the page renders hard-coded fallback numbers [src: report 2026-09-05 §5]. Candidate scripts: `test_cutoff_clean.py`, `test_cutoff_familiarity.py`. [UNVERIFIED until the data file is regenerated]

### 5.4 Concepts absent from all five summaries are story-specific (random-word baseline)

The surfaced void word sits closer to its story's content than random control words (Wilcoxon p < 0.00001) and closer to its own story than to a random other story (p < 0.00001), in two embedding families (bge-large, e5-large) [src: docs/consequence-atlas.md; docs/llm-consensus-geometry-iran-2026.md]. n: the index page says 1,659 stories, the Atlas and Iran pages say 150; the script hard-codes 150 and tests the annular "donut" void, not the aired lexical void [src: report 2026-09-05 §5]. This preprint reports n = 150. OWNER: rerun on the v1 corpus and state which void definition was tested.

Domain signature: war coverage omits escalation machinery and named leaders; other-conflict coverage omits geography and strike vocabulary (buckets 781 / 484 / 31) [src: docs/consequence-atlas.md]. Names are relabeled to roles by a five-model panel, kept when ≥ 4 of 5 agree by embedding-cluster density [src: docs/consequence-atlas.md]; this step uses models as labelers (see §6).

### 5.5 Model divergence on fully-sourced stories (Outliers page)

On 2,201 stories (April–June 2026): magnitude-outlier share DeepSeek 38.5%, Claude 30.2%, ChatGPT 14.0%, Grok 12.9%, Gemini 4.4%; stylistic-signature ("kind") share ChatGPT 27.5%, Grok 25.8%, DeepSeek 21.9%, Claude 18.0%, Gemini 6.8%; the two outliers coincide on 27% of 2,171 stories [src: docs/large-language-model-outliers.md §02]. DeepSeek on 184 China-related stories: divergence 22.7, outlier share 40% vs 39% baseline [src: docs/large-language-model-outliers.md §03]. Claude declines about 1% of stories [src: docs/large-language-model-outliers.md §04]. Code review: the outlier-kind percentages could not be verified against any script [src: report 2026-09-05 §5]. [UNVERIFIED] Production registry, all time: DeepSeek is the VIX outlier in 32% of rows; recently ChatGPT 30%; Gemini lowest in both eras [src: report 2026-09-05 §3].

### 5.6 Longitudinal: the Iran arc

510 segments over 85 days. (a) The lexical "absent" axis moved from −0.33 (W15) and −0.17 (W16) to +0.18 (W17) and +0.75 (W18), then held in +0.73 to +0.95; weekly n = 20–96 [src: docs/llm-consensus-geometry-iran-2026.md Finding 01]. Survives a second embedding model (e5-large, weekly-trajectory r = 0.991) and three length controls (cap at 100 words: +0.060 vs +0.064; cap at three sentences: +0.054; short-band 0.749 → 0.818); source length flat at 195–227 words, proper-noun density 0.21 [src: same page]. (b) Hedge axis pinned at −1.00, −1.00, −0.98, −0.94, −0.97 over W17–W21 [src: same page, Finding 02]. (c) Outlier handoff on stable-five weeks (W19, W20, W22, W23, W24): Claude 29% → 17%, Grok 22% → 56%; holds under two of three outlier definitions; late-week bins are small (Grok 65% on n = 20 in the all-weeks view) [src: same page, Finding 03]. Scripts: `iran_arc.py`, `iran_arc_v2.py`; data `iran_arc_v2.json`. OWNER: confirm which version produced the page.

### 5.7 The residual direction is a direction of loss (report 2026-09-09, Test 1)

300 newest stories, bge-large, two-sided sign test on paired per-story comparisons [src: report 2026-09-09 preamble].

| comparison (same story) | n | mean A | mean B | A greater | p |
|---|---|---|---|---|---|
| cos(r, dropped words) vs cos(r, kept words), same count | 277 | +0.020 | −0.010 | 63% | 1e-5 |
| cos(r, killshot claims) vs cos(r, kept words) | 256 | +0.070 | −0.011 | 75% | 5e-16 |
| cos(r, stored logos words) vs cos(r, random corpus words) | 300 | −0.051 | −0.045 | 45% | 0.07 |
| cos(r, stored void words) vs random corpus words | 300 | −0.037 | −0.045 | 52% | 0.6 |
| control: cos(source, dropped) vs cos(source, kept) | 277 | 0.549 | 0.710 | 4% | 5e-66 |
| control: cos(source, logos) vs cos(source, random) | 300 | 0.642 | 0.444 | 100% | 1e-90 |

[src: report 2026-09-09 §Test 1]. Reading: the residual discriminates dropped from kept words and killshot claims most of all; the control shows this is not topical similarity (dropped words are less source-similar than kept words). The stored logos and void words carry no residual signal; they are headline-nearest vocabulary [src: report 2026-09-09 §Test 1].

### 5.8 Summary Plus re-compresses and does not recover dropped content (report 2026-09-09, Tests 2–3)

On 1,244 stored rewrites: the displacement e(rewrite) − e(original) points toward the story's own source more than toward a random source (cos +0.373 vs +0.196, 85% of stories, p ≈ 0), and vendors agree within a story more than across (+0.264 vs +0.150); but rewrites end slightly farther from the source than the originals (cos 0.863 vs 0.868, p = 5e-4), move toward the consensus centroid (+0.312), and are about a third the length (median ratio 0.36) [src: report 2026-09-09 §Test 2]. Spillover recovery of dropped source words, excluding words fed in: 2.5% overall, no loss-class advantage (relational 3.8%, magnitude 3.5%, causal 3.8%, human-impact 3.7%, other 2.4%); 9% of added content words are in the source; the 41% "killshot recovery" is title echo because killshots come from the headline and the prompt contains the headline [src: report 2026-09-09 §Test 2].

Controlled arms with the local model (mistral-small, seed 42, temperature 0, 40 stories; arm E on 32): feeding production channel words (B) vs random same-source absent words (C) gives no spillover difference (9 wins of 18, p = 1) and worse grounding (0 wins of 39, p = 4e-12; only 27% of production channel words are in the source); residual-top words (E) vs random (C2): spillover worse (5 of 18, p = 0.10), grounding +0.03 (p = 0.04), non-title killshot recovery 6 vs 3 of 19 [src: report 2026-09-09 §Test 3].

Site claims for the same method: blind-panel insight 2.50 (baseline) → 3.36 (channels A·C), faithfulness 4.68 → 3.07, analogy 0.00, n ≈ 577–615 per arm, seven stories, five judges; head-to-head vs the bare prompt: insight 3.35 (prompt) vs 3.32 (surfacing + prompt), Δ = −0.03, n = 788 per arm; a bare prompt reaches 52 of 56 (92%) of convergence concepts [src: docs/summary-plus.md]. Code review: the baseline numbers could not be reproduced from any script, judges include the author models (ex-self only), one unseeded shuffle is shared by all judges [src: report 2026-09-05 §5; report 2026-09-06 §1C]. [UNVERIFIED]

### 5.9 Loss classes and name erasure (pilots, 300 stories, Aug 7 – Sep 6, 2026)

When all five models drop a source word: adverbs 40%, relational connectives 30%, common and proper nouns 20%, causal and human-impact words 11%; headline words dropped by all five 8.7% vs body-only words 26.2% [src: report 2026-09-06 §1C]. Named spans: 1,335 in the sources, 323 (24%) in none of the five summaries; per-model name-drop rate Gemini 55%, ChatGPT 52%, DeepSeek 46%, Grok 31%, Claude 59% on the small panel it is present in; 21 titled-name erasures [src: report 2026-09-09 (site critique) §1b]. Both pilots used crude matching (5-character stems; NLTK proper-noun runs) on bodies with feed boilerplate; neither is on the site. OWNER: decide whether these go in as pilots or wait for the cleaned corpus.

### 5.10 EigenChing state space (report 2026-09-09)

Six axes on 300 stories: largest correlations density × VIX spread (−0.47) and absent ratio × entity retention (−0.47), both by construction; everything else under 0.25; four principal components carry 80% of variance [src: report 2026-09-09 §EigenChing]. The 729-cell ternary grid over this space is over-quantized for about 30 stories a day [src: same]. Axis 6 is documented as VIX spread but is fed mean VIX [src: report 2026-09-05 §3 "EigenChing state vector"].

---

## 6. Controls and limitations

Plain statements, one per line.

- LLM-judge null. A frontier-model judge rated 96% of the 216 entity-swap summaries "modifier fully preserved"; the geometric score separates the conditions at p = 0.0085 [src: docs/index.md]. The judge misses the effect; this is why the instrument does not use a judge.
- Alignment null. Heavy-RLHF vs lightly-tuned models: p = 0.46, no detectable difference on this comparison with this sample; a failure to find a difference, not proof of none, across model families with their own confounds [src: docs/index.md]. The comparison could not be verified against a script [src: report 2026-09-05 §5]. `docs/dynamics.md` still states a "74% stronger" displacement result that `fix_boundary.py` describes as retracted [src: report 2026-09-05 §5]. OWNER: remove or re-derive before submission.
- No human-labeled omission set yet. No omission channel has been scored against a gold set of what was actually omitted [src: report 2026-09-06 §1C]. The labeling protocol is in `labeling/README.md` (not present in the tree on 2026-09-10; OWNER: link when it lands).
- No error bars yet. Site numbers are point estimates; production trend beats narrate 24-hour deltas with n about 24 and no interval [src: report 2026-09-06 §1D]. Report 2026-09-09 gives sign-test p-values but no confidence intervals.
- One frozen embedding model. Every score is arithmetic on bge-large-en-v1.5; reproducibility rules out randomness, not whether the embedding encodes meaning faithfully [src: docs/index.md; docs/llm-consensus-geometry-iran-2026.md]. e5-large was used as a second family on the Iran page and the random-word test only.
- Self-judging in the roundtable and in Summary Plus. The Summary Plus head-to-head uses the five frontier models as their own judges (ex-self) [src: report 2026-09-05 §5]; the roundtable format asks models to react to the measurements [src: report 2026-09-06 §1C]. The site's "no model judges another" holds for the measurement path (§3.2 to §3.9) but not for these layers, nor for killshot extraction (a local model extracts the claims) or role relabeling (§5.4).
- Small daily samples. About 30 stories a day [src: report 2026-09-09 §EigenChing]; 23 stories on 2026-09-06 [src: report 2026-09-06 §1B]; batches of 3 [src: report 2026-09-05 §4].
- Varying panel size. 4-model panels in 237 of the last 300 audit rows; not normalized [src: report 2026-09-06 appendix; report 2026-09-05 §4].
- Source contamination. 75% of stored bodies carry feed boilerplate [src: report 2026-09-06 §1C]; 23% of recent segments contain a local-model failure string in an analysis field [src: report 2026-09-05 §4].
- Mean VIX and the state flag are functions of density (§3.3); the NOMINAL state can never fire [src: report 2026-09-05 §3].
- Degenerate channels. The aired void words rank by headline relevance; the logos objective is attracted to the consensus; the SVD null vector is arbitrary after mean-centering (§3.8). None of the three carries residual signal [src: report 2026-09-09 §Test 1].
- Withdrawn claims. Own-parent pattern (0 of 5 models under semantic scoring); spontaneous self-map (0 of 4 models without the instruction); eight-test battery downgraded to a ~19% relative trend (Mann-Whitney p = 0.027, permutation p = 0.038, fails parametric and length-controlled tests); corpus count 5,170 → 1,659; single stable void direction (unstable under perturbation, no different from random text) [src: docs/withdrawals.md].
- Pre-registration status. Only the entity-swap test was pre-registered [src: docs/boundary.md]. The cutoff name list was post hoc [src: docs/boundary.md].
- Not peer-reviewed [src: docs/index.md].

---

## 7. What would change our mind

OWNER: fill from the pre-registration ledger. No ledger file was found in the tree on 2026-09-10 (`add_prediction_scorecard.py` scores void-word predictions, which is a different thing [src: report 2026-09-05 §3 "Predictions and scorecard"]). The list below is candidate predictions drawn from the reports' stated bets; none is registered yet. Each needs a date, a hash and a scoring rule before it counts.

- Residual-selected sentences. If residual-top source sentences fed to a rewrite (with the source available) do not beat random sentences on dropped-content recovery with grounding held, the residual is diagnostic only [src: report 2026-09-09 §What this establishes].
- Gold set. If QA-recall coverage does not reach AUC > 0.80 while cosine coverage stays below 0.65 on a human-labeled omission set, the cosine-0.75 coverage rule is retired [src: report 2026-09-06 §3C].
- Alignment gradient. If running both Summary Plus routes against progressively more-tuned models does not open a gap, the durability argument is dropped [src: docs/summary-plus.md "the open test"].
- Cutoff replication. If a pre-registered replication on held-out post-cutoff names does not show d > 0 at p < 0.05, §5.3 is withdrawn [src: docs/boundary.md "Honest limits"].
- Void-word lift. If aired void words do not predict next-day coverage better than same-article random words (lift about 1.0), the channel is dropped from the dataset [src: report 2026-09-06 §3C].
- Noise floor. If re-running the same five models on the same article a day later moves density by a median above 0.01 (about the September monthly SD), single-story density readings are not reported [src: report 2026-09-06 §3D].
- Random-word baseline on the v1 corpus at the corrected n; if p ≥ 0.01 in either embedding family, §5.4 is withdrawn.

---

## 8. Reproducibility

- Code: public repository `sdad1018/Eigentrace` (MIT) [src: docs/index.md]. Note: the tree's `README.md` and `pyproject.toml` currently describe a different product ("omniteardown" v0.4.0), and `pip install -e .` installs that package, not the measurement code [src: README.md; pyproject.toml; report 2026-09-06 §2B item 7]. OWNER: the install command for the measurement library does not exist yet; write it when `eigentrace-measure` is split out (see [src: report 2026-09-06 §4B]).
- Dependencies: `requirements.txt` (floors) and `requirements.lock.txt` (exact production versions; torch CUDA 12.1 build) [src: requirements.txt].
- Embedding model: BAAI/bge-large-en-v1.5; OWNER: pin the Hugging Face revision hash.
- Dataset: `dataset/README.md` (v1, in preparation). Public daily exports under `docs/data/` (142 files on 2026-09-10; no article bodies; schema page says v2 while the exporter writes v1 [src: report 2026-09-06 §1D]).
- Tests: `tests/` holds 8 files with 67 `test_` functions (counted 2026-09-10: test_batch_producer 11, test_claims 5, test_eigentrace 13, test_geometry 10, test_math_compression 6, test_segment_player 6, test_state_vector 7, test_text_filters 9). OWNER: state which pass on a clean checkout; note that `tests/test_eigentrace.py` may cover the hedge scorer rather than the measurement path [src: report 2026-09-06 §4B].
- Changelog: none exists in the tree (no `CHANGELOG.md` on 2026-09-10). OWNER: create one; the withdrawals page [src: docs/withdrawals.md] is the closest record.
- Scripts behind each figure: `docs/preprint/figures.md`.
- Replication cost: "about $50 in API credits" [src: docs/index.md] [UNVERIFIED: no cost breakdown in the tree]. Production cost basis: about 60 paid frontier calls per 3-story batch at baseline [src: report 2026-09-05 §4].
- Determinism caveat: API callers run at temperature 0 [src: report 2026-09-06 §1C], but vendor models change under their names; the Outliers page dates its findings to April–June 2026 [src: docs/large-language-model-outliers.md].

---

## Author and acknowledgements

OWNER: author line, affiliation, contact, funding statement, conflict statement (the instrument measures Anthropic, OpenAI, Google, DeepSeek and xAI outputs; state any relationship).

## References

See `docs/preprint/refs.bib`. Every entry is marked TODO-verify; none has been checked against the published record for this draft.
