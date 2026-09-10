# EigenTrace: deterministic measurement of what frontier language models keep, drop and soften when they summarize news

Preprint skeleton. Draft of 2026-09-10, reviewed against sources the same day. Status: not peer-reviewed; sections marked OWNER: are for the project owner to write or confirm.

Source tags: every number carries a tag of the form [src: docs/page.md] (a site page under `docs/`, read as rendered text; only `index.md` is markdown in the tree, the other pages are `docs/page.html` and the `.md` tag names the page, not a file), [src: report YYYY-MM-DD §section] (one of the four session reports of September 2026), [src: docs/metrics.md §n] (the metric reference in the tree), [src: anamnesis_results/...] (a result file in the tree), or [UNVERIFIED: reason] (a number that appears on the site or in a report but that no script, data file or log in the tree reproduces). Where the site and the code disagree the disagreement is stated, not resolved.

Review note (2026-09-10): every number below was checked against its tagged source. Three site numbers changed meaning under that check and are stated at their true weight where they occur: the LLM-judge null (§1.2, §6), the entity-swap design (§5.1) and the cutoff figures (§5.3).

Definitions: `docs/metrics.md` exists in the tree (36 KB, dated 2026-09-10). §3.1 to §3.8 follow its formulas; where a September session report stated a definition differently, both are given with their tags. OWNER: `docs/metrics.md` is the authority for §3; if it changes, re-derive §3 from it rather than from this draft.

---

## Abstract (draft, measured claims only)

EigenTrace measures what five frontier language models (ChatGPT, Claude, Gemini, DeepSeek, Grok) keep, drop and soften when they summarize the same news story. Each summary is embedded once with a frozen model (BAAI/bge-large-en-v1.5, 1,024 dimensions) and every score is deterministic arithmetic on those vectors; no language model grades another in the measurement path [src: docs/index.md; docs/metrics.md preamble]. We report: (1) a pre-registered entity-swap test on nine matched incident pairs, four models scored, in which semantic retention of a consequential modifier is 0.522 when the actor is an AI developer and 0.545 when it is a conventional corporation (Welch's t = 2.79, p = 0.0085, d = 0.47; n = 36 pair-by-model cells per condition, 216 responses), with a within-category swap moving retention by 0.004 against 0.023 across categories [src: anamnesis_results/entity_swap_log.txt; docs/index.md; docs/boundary.md]; (2) a frontier-model judge (gpt-5.4-mini) reading the same 216 summaries one at a time rates 87% "modifier's force fully preserved" and 96% fully or mostly preserved, so the geometric signal is not visible to item-level LLM judging [src: anamnesis_results/prefilter_v3_results_20260603_232327.json; docs/index.md states the 96% as "fully preserved"]; (3) heavily aligned and lightly tuned models show the effect at indistinguishable strength (p = 0.46) [src: docs/index.md] [UNVERIFIED: no reproducing script or result file found, src: report 2026-09-05 §5]; (4) across 150 stories the concepts absent from all five summaries sit closer to their story's content than random words (Wilcoxon p < 1e-5, two embedding families) [src: docs/consequence-atlas.md; the index page states n = 1,659, see §5.4]; (5) on 277 recent stories the residual direction (source embedding minus panel centroid) separates dropped from kept source words (63% of stories, sign test p = 1e-5) and points at omitted claims (75%, p = 5e-16) [src: report 2026-09-09 §Test 1]. Withdrawn claims and failed controls are reported alongside.

OWNER: trim to 200 words once the numbers above are confirmed against the dataset v1 release.

---

## 1. Introduction

### 1.1 Measurement, not verdict

A summary is a lossy transform of its source. The question this instrument asks is not whether a summary is good but what, specifically, the transform removed, added or softened, and whether five models built by five different labs do the same thing to the same text. The site states the framing in one line: "A measurement, not a verdict" [src: docs/index.md]. Nothing in the method decides whether a given omission was justified; it records that the omission happened and how large it is in a fixed geometric space.

### 1.2 What LLM-as-judge cannot do

The common evaluation pattern asks one model to score another model's faithfulness. That judge is retrained on its own schedule, so its scores drift; it cannot say what changed between source and summary; and item-by-item review misses small systematic shifts. The one measured comparison in this project: a frontier-model judge (gpt-5.4-mini, script `prefilter_validation_v3.py`, run 2026-06-03) was shown the 216 summaries from the entity-swap experiment with a four-point rubric (0 = modifier's force fully preserved, 1 = mostly preserved and slightly weakened, 2 = noticeably softened or hedged, 3 = dropped or contradicted). It rated 187 of 216 (87%) at 0 and 207 of 216 (96%) at 0 or 1; only 9 (4%) at the script's positive threshold of 2 or above [src: anamnesis_results/prefilter_v3_results_20260603_232327.json; prefilter_validation_v3.py JUDGE_RUBRIC, POSITIVE_SEV]. The geometric retention score on the same summaries separates the two conditions at p = 0.0085 [src: docs/index.md]. The site reports the 96% as "modifier fully preserved" [src: docs/index.md]; the rubric's own label for that figure is fully or mostly preserved. The results file records `pooled_auc` and `clustered_auc` as null (not computed). OWNER: state the 87% / 96% split on the site or use the rubric's wording.

### 1.3 What this instrument is

A pipeline that, for each ingested news story, (a) asks five frontier models for a summary under one fixed prompt, (b) embeds the source and the summaries with one frozen embedding model, (c) computes a set of deterministic scores from those vectors and from lexical comparison with the source, and (d) stores everything as a JSON segment. It has run on one consumer GPU since March 2026 (metric definitions dated from 2026-03-03, daily exports from 2026-03-31) [src: docs/metrics.md "How to cite a number"; README.md "Daily exports"], with outages recorded in [src: report 2026-09-06 preamble]. The site describes several derived layers (a narrating local model, a self-audit, a broadcast). This preprint covers only the measurement path; the derived layers are out of scope except where they touch the numbers.

OWNER: one paragraph on why news, why five vendors, why hourly.

---

## 2. Related work

TODO bullets. Cite by name only; `refs.bib` carries entries only for items identified unambiguously (see the header of `refs.bib` for which were checked against the published record on 2026-09-10). Do not add references here that have not been read.

- Summarization faithfulness metrics: FactCC, QAGS, FEQA, QuestEval, FRANK, SummaC, AlignScore; the 2026 omission-taxonomy papers named in [src: report 2026-09-09 (site critique) §2d] (not identified; no entry in `refs.bib`); FaithBench and FABLES as human-labeled omission/faithfulness benchmarks [src: report 2026-09-09 (site critique) §2d]. TODO: which of these measure omission (recall of source content) as opposed to hallucination (precision), since this instrument measures omission.
- Embedding-based evaluation: BERTScore, MoverScore, cosine-to-reference metrics; the embedding models used here (bge-large-en-v1.5; e5-large as the second family on the Iran page) [src: docs/llm-consensus-geometry-iran-2026.md "survives a second embedding model"].
- LLM-as-judge critiques: position bias, self-preference, verbosity bias, drift across judge versions; "Judging LLM-as-a-judge" (Zheng et al.); "LLM evaluators recognize and favor their own generations" (Panickssery et al.).
- Disagreement among generations as a signal: SelfCheckGPT; semantic entropy (Kuhn et al.; Farquhar et al.). Named as the lineage of the agreement side of this instrument in [src: report 2026-09-06 §1C].
- Monoculture and homogenization of model outputs: algorithmic monoculture (Kleinberg and Raghavan; Bommasani et al.); homogenization of writing and ideation under LLM assistance (Padmakumar and He; Anderson et al.). The site's "five labs, same blind spots" claim [src: docs/index.md] belongs to this literature.
- Pyramid / summary content units and Krippendorff's alpha, as the labeling protocol the gold set will use [src: report 2026-09-06 §3C].

OWNER: write the prose once the bullets are verified.

---

## 3. Method

### 3.1 Embedding

All texts are embedded with BAAI/bge-large-en-v1.5, 1,024 dimensions, unit-normalized, on CPU (`geometric_engine.GeometricPerturbationEngine.embed_texts`) [src: docs/metrics.md preamble; report 2026-09-05 §2]. The model is frozen; the same text always yields the same vector. Let e_1 … e_N be the unit embeddings of the N model summaries for one story (N = 4 or 5 in recent data), let c = (1/N) Σ e_i be the centroid, ĉ = c/‖c‖, and h the headline embedding [src: docs/metrics.md preamble]. The vocabulary used for word readouts is a 184,789-word tensor [src: docs/metrics.md preamble].

### 3.2 Consensus density

density d = 2/(N(N−1)) · Σ_{i<j} e_i·e_j, the mean pairwise cosine of the summary embeddings [src: docs/metrics.md §1; environment definition]. Whole-response embeddings, so shared length and format count as agreement [src: docs/metrics.md §1].

Measured range in production: median 0.902 over 9,395 registry rows, 86% of rows in [0.85, 0.95]; monthly standard deviation fell from 0.045 (March 2026) to 0.017 (September 2026) [src: report 2026-09-05 §3]. On the 99 most recent story segments: 0.864 to 0.950, median 0.916 [src: docs/metrics.md §1].

### 3.3 Per-model divergence (VIX) and mean VIX

Per-model VIX_i = clip(500 · (1 − e_i·ĉ), 0, 100) [src: docs/metrics.md §1; environment definition]. It is a one-shot distance from the panel's own centroid, not a volatility; the factor 500 is a display choice; the values are not independent because Σ_i (1 − e_i·ĉ) = N(1 − ‖c‖) [src: docs/metrics.md §1; report 2026-09-05 §3].

Mean VIX = (1/N) Σ_i VIX_i = 500 · (1 − sqrt((1 + (N − 1) · d) / N)), exact whenever no VIX_i hits the clip, because for unit vectors Σ_i e_i·ĉ = N‖c‖ and ‖c‖² = (1 + (N − 1)·d)/N [src: docs/metrics.md §1; environment definition]. Consequence: mean VIX carries no information beyond d and N. Verified on 9,113 registry rows: median gap between the aired mean VIX and the identity 0.05 points, 99.6% within one point, correlation with density −0.996 [src: report 2026-09-05 §3 "Mean VIX and the state flag"]; on synthetic panels the identity holds to 1e-13, on 99 stored segments the median gap is 0.047 [src: docs/metrics.md §1]. This preprint therefore reports density and per-model VIX only.

Per-model VIX is the most informative channel: per-model spread 6 to 13 points, pairwise correlations between models 0.32 to 0.60; 46 rows hit the clip [src: report 2026-09-05 §3]. Recent per-story maxima 11.5 to 41.6 (median 22.7), minima 5.7 to 21.2 [src: docs/metrics.md §1].

### 3.4 Killshot claims (claim-level omission)

A local Mistral model via Ollama (`mistral:latest`, temperature 0, at most 500 tokens, in `claim_extractor.py`) extracts atomic claims from the headline plus the RSS blurb, never the article body [src: docs/metrics.md §5; report 2026-09-05 §3]. salience(claim) = cos(claim, h). For each model, cos(claim, whole response) ≥ 0.75 counts as covered, 0.65 to 0.75 partial, else the model is listed in omitted_by; coverage_ratio = covered / N. A killshot is a claim with salience ≥ 0.45, coverage_ratio ≤ 0.2 and non-empty omitted_by; top 3 by salience are stored [src: docs/metrics.md §5; environment definition].

Known defect: the omitted_by requirement was added on 2026-09-09. Before it, 44% of 3,530 audited killshots had an empty omitted_by (every model scored partial) [src: report 2026-09-05 §3]; 40% of killshots in the 99-segment sample, mostly pre-fix, have none; in the 12 segments after the fix, 0 of 15 [src: docs/metrics.md §5]. The 0.75 / 0.65 thresholds are not calibrated against entailment [src: report 2026-09-06 §1C]. A one-sentence claim scored against a multi-sentence response can be marked omitted when paraphrased inside it, and covered when the response merely shares its topic [src: docs/metrics.md §5].

### 3.5 Source void (absent words) and absent ratio

Source text S = title + ". " + RSS summary + body[:1500]; source words = lowercase alphabetic tokens of four or more characters not in a 70-word stoplist (report 2026-09-05 §3 says 90 words; `docs/metrics.md` §2 says 70; OWNER: count the list in `eigentrace_math.py`); absent_words = source words whose surface form and Porter stem appear in no response, excluding headline derivatives; absent_ratio = absent_count / source word count [src: docs/metrics.md §2; report 2026-09-05 §3 "Source void"]. Measured: absent_ratio 0 to 0.525, mean 0.21 over 300 recent segments; exactly 0 in 16 of 300, which looks like a missing source body rather than a real reading [src: report 2026-09-05 §3]; 0 to 0.505, median 0.216, exactly 0 in 7% of the 99 most recent [src: docs/metrics.md §2]. The denominator grows with body length [src: docs/metrics.md §2]. Data-quality note: 226 of 300 stored bodies (75%) contain feed boilerplate ("Recommended Stories", "published"), which inflates absent counts until stripped [src: report 2026-09-06 §1C].

### 3.6 Word-level semantic retention

Retention of a source word = max over summary sentences of cos(embed(word), embed(sentence)). A paraphrased synonym counts as retained; a dropped single modifier moves a sentence embedding only slightly, so the score is conservative about modifier loss [src: docs/boundary.md "Method & reproducibility"; docs/anamnesis.md "Method & what we cannot prove"]. This is the score behind the entity-swap, charged-language and cutoff results (§5.1 to §5.3). It is not part of the production pipeline described in `docs/metrics.md`.

### 3.7 Compression signature (verb downgrade, entity retention, hedges)

verb_downgrade = mean over models of clip((mean Zipf frequency of response content verbs − mean Zipf frequency of source content verbs) / 2, 0, 1), content verbs by NLTK POS tag; entity_retention = mean over models of the share of regex-capitalized source tokens found as case-insensitive substrings in the response; hedge count = distinct response words in three fixed lists (epistemic 11, attribution 10, distancing 9) not present in the source, summed over models; compression_score = 0.4·verb_downgrade + 0.3·(1 − entity_retention) + 0.3·min(avg hedges per model / 3, 1) [src: docs/metrics.md §6; report 2026-09-05 §3 "Compression"]. Source text here is body[:1000], not the 1,500 used in §3.5 [src: docs/metrics.md §6]. Known defect: verb_downgrade is exactly 0 in 78% of 300 stored values [src: report 2026-09-05 §3] and 65% of the 99 most recent [src: docs/metrics.md §6] because a missing verb measurement collapses to 0 and the measure is one-sided. Entity retention (0.33 to 0.83 on 300; 0.344 to 0.938, median 0.578 on 99) and the composite (0.09 to 0.58; 0.094 to 0.594, median 0.320) are informative [src: report 2026-09-05 §3; docs/metrics.md §6].

### 3.8 Concept surfacing: void words, logos words, SVD null space

Three production channels surface vocabulary the summaries did not use. They are described here so that the site's claims can be read against the code; none is used as a headline result in this preprint.

- Void words (aired): the 200 vocabulary entries nearest the headline embedding, words of four or more characters whose whole-word regex does not match the concatenated responses, top 5 by headline similarity [src: docs/metrics.md §2; report 2026-09-05 §3 "Void words"]. Ranking is by headline relevance, not by avoidance. A second definition, the annular "donut void" (cos(h, w) > 0.52 and cos(ĉ, w) below an adaptive inner threshold), exists and feeds only secondary outputs [src: docs/metrics.md §2; report 2026-09-05 §3].
- Logos words: minimize L(x) = mean_i(1 − cos(x, e_i)) + 0.75·cos(x, ĉ) − 0.30·cos(x, h) with AdamW (lr 0.05, weight decay 1e-4), 150 steps, start x₀ = ĉ, renormalized each step; read out the 25 nearest vocabulary words, drop stems any model used, keep 5; if fewer than 3 survive, use the unfiltered top 5 [src: docs/metrics.md §3; report 2026-09-05 §3 "Logos words"]. Because the loss is linear in x on the sphere, the minimizer is x* ∝ (‖c‖ − 0.75)·ĉ + 0.30·h, which pulls toward the centroid whenever d > 0.453 (N = 5), i.e. at every density seen in production (about 0.22·centroid + 0.30·headline at measured densities); the stem filter does the work of producing unused words [src: docs/metrics.md §3; report 2026-09-05 §3].
- SVD null space: stack the N unit embeddings, economy SVD, last right-singular vector v; claims ranked by |cos(v, claim)|, top 3 kept [src: docs/metrics.md §4]. Until 2026-09-09 production mean-centered the matrix first; five mean-centered rows have rank at most four, so the smallest singular value was numerically zero and v an arbitrary direction in a 1,020-dimensional complement; null_alignment was negative in more than 95% of 3,091 audited claims [src: report 2026-09-05 §3 "SVD null space", measured on the centered version]. The centering was removed on 2026-09-09; v now lies in the row space of the responses (a combination of what the models wrote) and its sign is arbitrary [src: docs/metrics.md §4 and "How to cite a number"].

### 3.9 Residual direction

r = e(source) − c, the source embedding minus the panel centroid. Production has computed this vector as `void_vector` since 2026-04-13 (stored as its norm and five coordinate indices; ‖r‖ 0.331 to 0.602, median 0.441 on 99 segments) but never projects it to words [src: docs/metrics.md §3 "residual, void_vector"]. On 2026-09-09 it was tested off-repository as a direction of loss by comparing cos(r, ·) for dropped words, kept words, killshot claims and random words on the same story [src: report 2026-09-09 §Test 1; docs/metrics.md §3 notes the script is not in the repository]. Results in §5.7.

### 3.10 Summary Plus

Two different objects carry this name [src: docs/metrics.md §8]. (a) On air: each active frontier model is sent the story title, its own earlier summary and up to three word lists (logos words; spiral words; the aired headline-void words), never the source, and asked for a tighter 2 to 3 sentence rewrite; the prompt labels the lists as SVD-derived and source-anchored, which they are not [src: docs/metrics.md §8; report 2026-09-09 §Test 2]. (b) On the site: a written "read the negative space" discipline pasted beside the source, with a centroid surfacing (vocab @ anchor, keep words absent from the summaries) and a "convergence" surfacing over source sentences, judged by a blind panel of the five frontier models on 1 to 5 insight and faithfulness scales with no model scoring its own output [src: docs/summary-plus.md "How it works", "The result"; report 2026-09-05 §5]. The measurements in §5.8 from report 2026-09-09 concern (a); the site numbers in §5.8 concern (b).

### 3.11 Pipeline

1. Ingest RSS items; fetch the article body with trafilatura (boilerplate is currently not stripped, §3.5).
2. Prompt five vendor models with one fixed summarization prompt ("Be direct. No disclaimers." per the code; the Atlas and Iran pages describe it as "summarize directly; do not fact-check whether events occurred" [src: docs/consequence-atlas.md "Method"; docs/llm-consensus-geometry-iran-2026.md "Method"; report 2026-09-05 §5]). API calls run at temperature 0 [src: report 2026-09-06 §1C].
3. Embed source, summaries and claims with the frozen model.
4. Compute §3.2 to §3.9; extract killshots with the local model.
5. Write one segment JSON per story with attribution fields (story_title, story_url, model_responses, model_vix, consensus_density, source_void, killshots, compression, summary_plus, …) [src: README.md "Outputs"].
6. Export a daily public JSON without article bodies [src: report 2026-09-06 §1D "Public daily dataset"; README.md "Daily exports"].

Panel size varies: in the last 300 audit rows the panel had 4 models in 237 and 5 in 63; Claude was absent from 84% of recent segments [src: report 2026-09-06 appendix; report 2026-09-05 §4]. Density, coverage and omission are not normalized for panel size [src: report 2026-09-05 §4]. OWNER: state the normalization used in dataset v1.

---

## 4. Data

Dataset v1 is being assembled separately; see `dataset/README.md` (not present in the tree on 2026-09-10; OWNER: link when it lands). Article bodies are publishers' text and are not distributed; model outputs, titles, URLs, RSS blurbs and measurements are.

Story counts stated on the site, with their pages:

| count | what | source |
|---|---|---|
| 13,307 | story segment files in the private segments directory (2026-09-06) | [src: report 2026-09-06 §1B] |
| 9,395 | registry rows with a density value | [src: report 2026-09-05 §3] |
| 2,201 | stories with a source body of 40+ words, refusals removed (Outliers page corpus, April–June 2026) | [src: docs/large-language-model-outliers.md §01, "How this was measured"] |
| 2,171 | stories in the kind-vs-magnitude agreement test | [src: docs/large-language-model-outliers.md §02] |
| 1,659 | "real news stories" in the Atlas corpus (corrected from 5,170) | [src: docs/consequence-atlas.md; docs/withdrawals.md Withdrawal 04] |
| 1,592 | stories in the charged-language retention test | [src: docs/boundary.md Finding two] |
| 781 / 484 / 31 | Atlas domain buckets: war / other conflict / general | [src: docs/consequence-atlas.md] |
| 510 | Iran-conflict segments, April 16 – June 18, 2026 | [src: docs/llm-consensus-geometry-iran-2026.md] |
| 300 | newest stories with five summaries, five rewrites and a 400+ character body (residual tests) | [src: report 2026-09-09 preamble] |
| 150 | stories in the random-word baseline ("150 stories" on the Atlas and Summary Plus pages, "150 Iran stories" on the Iran page) | [src: docs/consequence-atlas.md; docs/summary-plus.md; docs/llm-consensus-geometry-iran-2026.md; report 2026-09-05 §5] |
| 22k+ / 18,000+ | "stories measured" / "segments" on the overview and dynamics pages; these count all segment types, not stories | [src: docs/overview.md; docs/dynamics.md; report 2026-09-06 §1B] [UNVERIFIED as story counts] |

The story-count triad (1,592 / 1,659 / 150) is inconsistent across pages and code [src: report 2026-09-06 §1D]. OWNER: dataset v1 must fix one denominator per result and this table must be rewritten from it.

Thin-source regime: roughly 75% of ingested stories supplied only a headline and one sentence (median 14 source words); on those the models confabulate, and every measured finding on the Outliers page excludes them [src: docs/large-language-model-outliers.md §01].

---

## 5. Results

Each subsection: the claim, the number, n, the test, the source page, and what the code review found.

### 5.1 Entity swap: the modifier survives less when the actor is an AI developer

Nine matched real incidents, identical sentence structure and modifiers ("quietly", "secretly"), only the company name changed (Boeing / Wells Fargo / Goldman vs OpenAI / Google / Anthropic) [src: docs/index.md; entity_swap_experiment.py PAIRS]. Semantic modifier retention 0.5224 (AI developer) vs 0.5450 (conventional corporation), n = 36 pair-by-model cells per condition; Welch's t = 2.787, p = 0.008542, Cohen's d = 0.471; binary keyword retention 26% vs 25% [src: anamnesis_results/entity_swap_log.txt "AGGREGATE RESULTS"; docs/overview.md; docs/index.md]. Committed null: six within-category swaps (three AI to AI, three corporation to corporation) move retention by 0.0037 on average, the cross-category gap is 0.0226 [src: anamnesis_results/entity_swap_log.txt; docs/index.md rounds these to 0.004 and 0.023 and calls the ratio "six times"; the log prints "exceeds null by >2x"]. n of summaries = 216 = 36 cells × 2 conditions × 3 runs [src: prefilter_validation_v3.py docstring; anamnesis_results/entity_swap_full_results.json runs_per_cell = 3].

Pre-registration: `anamnesis_results/entity_swap_preregistration.md`, dated 2026-05-23; the run is stamped 2026-05-24 [src: anamnesis_results/entity_swap_full_results.json timestamp]. Design as registered: at least 15 prompt pairs, five models, 3 runs per cell at temperature 0.7, system prompt "Summarize the following in 2-3 sentences.", primary metric = cosine of the modifier-bearing clause under bge-large-en-v1.5, Welch's t with threshold p < 0.01, a one-tailed prediction, six null swaps [src: anamnesis_results/entity_swap_preregistration.md]. Deviations recorded in the tree: 9 cross-category pairs were run, not 15 [src: entity_swap_log.txt line 3 "Pairs: 9 cross-category + 6 null"]; the log prints per-model results for ChatGPT, Claude, DeepSeek and Grok only (72 result lines) and none for Gemini, so 36 cells = 9 pairs × 4 models [src: anamnesis_results/entity_swap_log.txt]; the log does not state whether the printed p is one- or two-sided. The site says "five models" for this result [src: docs/boundary.md]. The experiment ran at temperature 0.7, not the production temperature 0 (§3.11). OWNER: state the four-model panel and the 9-of-15 pairs on the site, and the sidedness of the test.

### 5.2 Charged language is retained more than institutional language

Across 1,592 stories, words leaning operational/consequential ("teeth": 11,338 term occurrences, retention 0.5605) were retained more than institutional/structural words ("cage": 33,473 occurrences, retention 0.5407): gap +0.0198, Welch's t = 32.2, p = 4.7e-222, Cohen's d = 0.353; a 200-shuffle label-permutation null gives a mean gap of 5e-5 (null p = 0.0) [src: anamnesis_results/teeth_cage_results.json, produced by test_a_teeth_cage.py on 2026-06-14; docs/boundary.md "Finding two" states +0.020, p < 10⁻²⁰⁰, d = 0.35]. IDF control: over 106,412 terms, IDF alone explains R² = 0.0016 of retention (page: "≈ 0.002") and the teeth coefficient controlling for IDF is +0.0206 (p reported as 0.0) [src: anamnesis_results/salience_control_results.json, produced by test_salience_control.py]. The two files use different term pools (44,811 vs 106,412 occurrences); the page attaches the 106,412 count to the main gap. The page's "holds in all five frequency bands" is in neither result file and the teeth-cage script contains no band split [UNVERIFIED: no result file for the frequency-band control]. The scripts also state the direction as a reversal of the sanitization hypothesis (`verdict: REVERSED`), which is how the page reads it.

### 5.3 Post-cutoff names are under-retained

Named figures who became prominent after the models' cutoff (about mid-2024) are retained less than established ones. Reproduced from the tree: `anamnesis_results/cutoff_clean_results.json` gives d = 0.7465 on English-only names (d_english; also d_all = 1.387 and d_intl = 2.623), per-name retention Pezeshkian 0.4806, Khamenei 0.6594, Xi 0.5748, Netanyahu 0.6471, Putin 0.6102, Modi 0.6181, Trump 0.5856, Biden 0.6351, Araghchi 0.4618, Baghaei 0.4352, Hegseth 0.5438, Vance 0.5270, Witkoff 0.5162 [src: anamnesis_results/cutoff_clean_results.json]. The site states d = 0.75, Pezeshkian 0.48, Khamenei 0.66, Xi 0.57 [src: docs/boundary.md "Finding three"; docs/anamnesis.md], which match. Two site figures are not in that file: "p < 10⁻⁶" (no p-value is stored in cutoff_clean_results.json) [UNVERIFIED: no p in the result file] and "0.65 retention for established heads of state" (Netanyahu 0.647 and Khamenei 0.659 individually; the mean of the eight pre-cutoff names in the page's own table is 0.61) [UNVERIFIED as a group mean]. A second file, `cutoff_familiarity_results.json`, reports a word-level test on a different list (post-cutoff retention 0.492 vs pre-cutoff 0.590, p = 9.5e-54, d = 1.51, n = 229 / 820 word occurrences) [src: anamnesis_results/cutoff_familiarity_results.json]; it is not the test the page describes. Scripts: `test_cutoff_clean.py`, `test_cutoff_familiarity.py`.

The name list was chosen after inspecting the data; not pre-registered [src: docs/boundary.md "Honest limits"; docs/anamnesis.md]. Page rendering: `docs/boundary.html` fetches `/cutoff_retention.json`, which does not exist, and falls back to hard-coded per-name values [src: report 2026-09-05 §5; docs/boundary.html script]; those fallbacks equal the values in `cutoff_clean_results.json` to three decimals, so the page shows real results through a missing-file path. OWNER: generate `docs/cutoff_retention.json` from the result file and store the test's p-value.

### 5.4 Concepts absent from all five summaries are story-specific (random-word baseline)

The surfaced void word sits closer to its story's content than random control words ("margarita", "stapler", "photosynthesis"; Wilcoxon p < 0.00001) and closer to its own story than to a random other story (p < 0.00001), in two embedding families (bge-large, e5-large) [src: docs/consequence-atlas.md; docs/llm-consensus-geometry-iran-2026.md; docs/summary-plus.md]. n: the index page says 1,659 stories; the Atlas, Summary Plus and Iran pages say 150 (the Iran page: "150 Iran stories"); the script hard-codes 150 and tests the annular "donut" void, not the aired lexical void [src: report 2026-09-05 §5]. This preprint reports n = 150. OWNER: rerun on the v1 corpus and state which void definition was tested; identify the script (six top-level scripts contain the control words, see `figures.md` F8).

Domain signature: war coverage omits escalation machinery and named leaders; other-conflict coverage omits geography and strike vocabulary (buckets 781 / 484 / 31) [src: docs/consequence-atlas.md]. Names are relabeled to roles by a five-model panel, kept when ≥ 4 of 5 agree by embedding-cluster density [src: docs/consequence-atlas.md "How the sorting works"]; this step uses models as labelers (see §6).

### 5.5 Model divergence on fully-sourced stories (Outliers page)

On 2,201 stories (April–June 2026): magnitude-outlier share DeepSeek 38.5%, Claude 30.2%, ChatGPT 14.0%, Grok 12.9%, Gemini 4.4%; stylistic-signature ("kind") share ChatGPT 27.5%, Grok 25.8%, DeepSeek 21.9%, Claude 18.0%, Gemini 6.8%; the two outliers coincide on 27% of 2,171 stories [src: docs/large-language-model-outliers.md §02]. DeepSeek on 184 China-related stories: divergence 22.7, outlier share 40% vs 39% baseline [src: docs/large-language-model-outliers.md §03]. Claude declines about 1% of stories [src: docs/large-language-model-outliers.md §04]. Gemini is present on roughly half as many stories as the others [src: docs/large-language-model-outliers.md §07]. Code review: the outlier-kind percentages could not be verified against any script [src: report 2026-09-05 §5]. [UNVERIFIED] Production registry, all time: DeepSeek is the VIX outlier in 32% of rows; recently ChatGPT 30%; Gemini lowest in both eras [src: report 2026-09-05 §3].

### 5.6 Longitudinal: the Iran arc

510 segments over 85 days (April 16 – June 18, 2026). (a) The lexical "absent" axis moved from −0.33 (W15) and −0.17 (W16) to +0.18 (W17) and +0.75 (W18), then held in +0.73 to +0.95; weekly n = 20–96 [src: docs/llm-consensus-geometry-iran-2026.md Finding 01]. Survives a second embedding model (e5-large, semantic rather than lexical retention, weekly-trajectory r = 0.991) and three length controls (cap at 100 words: +0.060 vs +0.064 uncapped; cap at three sentences: +0.054; short-band 0.749 → 0.818); source length flat at 195–227 words, proper-noun density 0.21; summaries lengthened from about 138 to 176 words [src: same page]. (b) Hedge axis pinned at −1.00 (W17), −1.00 (W18), then −0.98, −0.94, −0.97 in the following weeks [src: same page, Finding 02]. (c) Outlier handoff on stable-five weeks (W19, W20, W22, W23, W24, all five models present on ≥ 80% of stories): Claude 29% → 17%, Grok 22% → 56%; holds under two of three outlier definitions; Gemini was absent from the pipeline in W16–W18 (present on 0–5% of stories), which inflated the early full-corpus Claude shares (42–49%); late-week bins are small (Grok 65% on n = 20 in the all-weeks view) [src: same page, Finding 03 and "What we tested against"]. Scripts: `iran_arc.py`, `iran_arc_v2.py`; data `iran_arc.json`, `iran_arc_v2.json` (all present). OWNER: confirm which version produced the page.

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

[src: report 2026-09-09 §Test 1]. Reading: the residual discriminates dropped from kept words and killshot claims most of all; the control shows this is not topical similarity (dropped words are less source-similar than kept words). The stored logos and void words carry no residual signal; they are headline-nearest vocabulary [src: report 2026-09-09 §Test 1]. The script (`geom_test.py`) is in a session scratchpad, not the repository, so `docs/metrics.md` treats the result as unpublished [src: docs/metrics.md §3; report 2026-09-09 last line].

### 5.8 Summary Plus re-compresses and does not recover dropped content (report 2026-09-09, Tests 2–3)

On 1,244 stored on-air rewrites (§3.10a): the displacement e(rewrite) − e(original) points toward the story's own source more than toward a random source (cos +0.373 vs +0.196, 85% of stories, p ≈ 0), and vendors agree within a story more than across (+0.264 vs +0.150); but rewrites end slightly farther from the source than the originals (cos 0.863 vs 0.868, p = 5e-4), move toward the consensus centroid (+0.312), and are about a third the length (median ratio 0.36) [src: report 2026-09-09 §Test 2]. Spillover recovery of dropped source words, excluding words fed in: 2.5% overall, no loss-class advantage (relational 3.8%, magnitude 3.5%, causal 3.8%, human-impact 3.7%, other 2.4%); 9% of added content words are in the source; the 41% "killshot recovery" is title echo because killshots come from the headline and the prompt contains the headline [src: report 2026-09-09 §Test 2].

Controlled arms with the local model (mistral-small, seed 42, temperature 0, 40 stories; arm E on 32): feeding production channel words (B) vs random same-source absent words (C) gives no spillover difference (9 wins of 18, p = 1) and worse grounding (0 wins of 39, p = 4e-12; only 27% of production channel words are in the source); residual-top words (E) vs random (C2): spillover worse (5 of 18, p = 0.10), grounding +0.03 (p = 0.04), non-title killshot recovery 6 vs 3 of 19 [src: report 2026-09-09 §Test 3].

Site claims for the page method (§3.10b): blind-panel insight 2.50 (baseline) → 3.36 (channels A·C), faithfulness 4.68 → 3.07, analogy 0.00, n ≈ 577–615 per arm, seven stories, five judges; head-to-head vs the bare prompt (baseline 2.59 in that table): insight 3.35 (prompt) vs 3.32 (surfacing + prompt), Δ = −0.03, n = 788 per arm; a bare prompt reaches 52 of 56 (92%) of convergence concepts [src: docs/summary-plus.md]. Code review: the baseline numbers could not be reproduced from any script, judges include the author models (ex-self only), one unseeded shuffle is shared by all judges, n = 7 stories with means only [src: report 2026-09-05 §5; report 2026-09-06 §1C]. [UNVERIFIED]

### 5.9 Loss classes and name erasure (pilots, 300 stories, Aug 7 – Sep 6, 2026)

When all five models drop a source word: adverbs 40%, relational connectives 30%, common and proper nouns 20%, causal and human-impact words 11%; headline words dropped by all five 8.7% vs body-only words 26.2% [src: report 2026-09-06 §1C]. Named spans: 1,335 in the sources, 323 (24%) in none of the five summaries; per-model name-drop rate Gemini 55%, ChatGPT 52%, DeepSeek 46%, Grok 31%, Claude 59% on the small panel it is present in; 21 titled-name erasures [src: report 2026-09-09 (site critique) §1b]. Both pilots used crude matching (5-character stems; NLTK proper-noun runs) on bodies with feed boilerplate; neither is on the site, and the site critique says the relational-vs-noun result should not be published until its method is [src: report 2026-09-09 (site critique) §2c]. OWNER: decide whether these go in as pilots or wait for the cleaned corpus.

### 5.10 EigenChing state space (report 2026-09-09)

Six axes on 300 stories: largest correlations density × VIX spread (−0.47) and absent ratio × entity retention (−0.47), both by construction; everything else under 0.25; four principal components carry 80% of variance [src: report 2026-09-09 §EigenChing]. The 729-cell ternary grid over this space is over-quantized for about 30 stories a day [src: same]. Axis 6 was fed mean VIX (a function of axis 1) until 2026-09-09 and is VIX spread (max − min of per-model VIX) since [src: docs/metrics.md §7; report 2026-09-05 §3 "EigenChing state vector"]. Axes 2, 3 and 5 sit at one pole in 79–86% of recent stories, so most cells cannot occur; 20 of the 32 named archetype cells had never occurred in 6,509 stories [src: docs/metrics.md §7].

---

## 6. Controls and limitations

Plain statements, one per line.

- LLM-judge null. A frontier-model judge (gpt-5.4-mini) rated 87% of the 216 entity-swap summaries "modifier's force fully preserved" and 96% fully or mostly preserved; the geometric score separates the conditions at p = 0.0085 [src: anamnesis_results/prefilter_v3_results_20260603_232327.json; docs/index.md]. The judge misses the effect; this is why the instrument does not use a judge. Note that this validation is itself one model's item-level judgment of other models' outputs.
- Alignment null. Heavy-RLHF vs lightly-tuned models: p = 0.46, no detectable difference on this comparison with this sample; a failure to find a difference, not proof of none, across model families with their own confounds [src: docs/index.md]. The comparison could not be verified against a script or result file [src: report 2026-09-05 §5]. `docs/dynamics.md` still states a "74% stronger" displacement result that `fix_boundary.py` describes as retracted, and states the null as establishing that the effect "is corpus-inherited, not alignment-produced", stronger than the index page's wording [src: docs/dynamics.md "What We Found", "What our own data already tells us"; fix_boundary.py docstring]. OWNER: remove or re-derive before submission.
- Pre-registration deviations. The entity-swap pre-registration specified at least 15 pairs and five models; 9 pairs were run and four models appear in the results (§5.1) [src: anamnesis_results/entity_swap_preregistration.md; entity_swap_log.txt].
- No human-labeled omission set yet. No omission channel has been scored against a gold set of what was actually omitted; every omission number in this draft is a model-versus-model or model-versus-source geometric comparison with no human label anywhere [src: report 2026-09-06 §1C; docs/consequence-atlas.md "Acknowledged limits": "No human baseline"]. The labeling protocol is in `labeling/README.md` (not present in the tree on 2026-09-10; OWNER: link when it lands).
- No error bars yet. Site numbers are point estimates; production trend beats narrate 24-hour deltas with n about 24 and no interval [src: report 2026-09-06 §1D]; the README states that published per-day measurements carry no error bars [src: README.md "Limitations"]. Report 2026-09-09 gives sign-test p-values but no confidence intervals.
- One frozen embedding model. Every score is arithmetic on bge-large-en-v1.5; reproducibility rules out randomness, not whether the embedding encodes meaning faithfully [src: docs/index.md; docs/llm-consensus-geometry-iran-2026.md; README.md "Limitations"]. e5-large was used as a second family on the Iran page and the random-word test only.
- Self-judging in the roundtable, in Summary Plus and in the Atlas. The Summary Plus blind panel uses the five frontier models as their own judges (ex-self) [src: report 2026-09-05 §5; docs/summary-plus.md]; the Atlas relabels names to roles by a five-model panel [src: docs/consequence-atlas.md]; the roundtable format asks models to react to the measurements [src: report 2026-09-06 §1C]; the LLM-judge null (above) is a model judgment by construction. The site's "no model judges another" holds for the measurement path (§3.2 to §3.9) but not for these layers, nor for killshot extraction (a local model extracts the claims) [src: docs/metrics.md §5; report 2026-09-06 §1D on `llms.txt`].
- Small daily samples. About 30 stories a day [src: report 2026-09-09 §EigenChing]; 23 stories on 2026-09-06 [src: report 2026-09-06 §1B]; batches of 3 [src: report 2026-09-05 §4]; the README says "roughly ten stories a day" [src: README.md "Limitations"]. OWNER: reconcile.
- Varying panel size. 4-model panels in 237 of the last 300 audit rows; not normalized [src: report 2026-09-06 appendix; report 2026-09-05 §4].
- Source contamination. 75% of stored bodies carry feed boilerplate [src: report 2026-09-06 §1C]; 23% of recent segments (68 of 300) contain a local-model failure string in an analysis field [src: report 2026-09-05 §4].
- Mean VIX and the state flag are functions of density (§3.3); the NOMINAL state is unreachable for N ≥ 3 [src: docs/metrics.md §1; report 2026-09-05 §3].
- Degenerate channels. The aired void words rank by headline relevance; the logos objective is attracted to the consensus; the SVD null vector was arbitrary under mean-centering until 2026-09-09 and is now a combination of the responses with arbitrary sign (§3.8). None of the three carries residual signal [src: report 2026-09-09 §Test 1; docs/metrics.md §§2–4].
- Withdrawn claims. Own-parent pattern (0 of 5 models under semantic scoring); spontaneous self-map (0 of 4 models without the instruction); eight-test battery downgraded to a ~19% relative trend (Mann-Whitney p = 0.027, permutation p = 0.038, fails parametric and length-controlled tests); corpus count 5,170 → 1,659; single stable void direction (unstable under perturbation, no different from random text) [src: docs/withdrawals.md].
- Pre-registration status. Only the entity-swap test was pre-registered [src: docs/boundary.md "Method & reproducibility"]. The cutoff name list was post hoc [src: docs/boundary.md "Honest limits"].
- Model drift. Vendor models change under their names; the Outliers page dates its findings to April–June 2026 [src: docs/large-language-model-outliers.md §08].
- Not peer-reviewed [src: docs/index.md; README.md "Limitations"].

---

## 7. What would change our mind

OWNER: fill from the pre-registration ledger. No ledger file was found in the tree on 2026-09-10 (`add_prediction_scorecard.py` scores void-word predictions, which is a different thing [src: report 2026-09-05 §3 "Predictions and scorecard"]). The list below is candidate predictions drawn from the reports' stated bets; none is registered yet. Each needs a date, a hash and a scoring rule before it counts.

- Residual-selected sentences. If residual-top source sentences fed to a rewrite (with the source available) do not beat random sentences on dropped-content recovery with grounding held, the residual is diagnostic only [src: report 2026-09-09 §What this establishes].
- Gold set. If QA-recall coverage does not reach AUC > 0.80 while cosine coverage stays below 0.65 on a human-labeled omission set, the cosine-0.75 coverage rule is retired [src: report 2026-09-06 §3C].
- Alignment gradient. If running both Summary Plus routes against progressively more-tuned models does not open a gap, the durability argument is dropped [src: docs/summary-plus.md "Where measurement ends · and the open test"; docs/index.md].
- Cutoff replication. If a pre-registered replication on held-out post-cutoff names does not show d > 0 at p < 0.05, §5.3 is withdrawn [src: docs/boundary.md "Honest limits" (calls for the replication; the threshold is this draft's)].
- Void-word lift. If aired void words do not predict next-day coverage better than same-article random words (lift about 1.0), the channel is dropped from the dataset [src: report 2026-09-06 §3C].
- Noise floor. If re-running the same five models on the same article a day later moves density by a median above 0.01 (about the September monthly SD), single-story density readings are not reported [src: report 2026-09-06 §3D].
- Random-word baseline on the v1 corpus at the corrected n; if p ≥ 0.01 in either embedding family, §5.4 is withdrawn.

---

## 8. Reproducibility

- Code: public repository `sdad1018/Eigentrace` (MIT) [src: docs/index.md; LICENSE]. The tree's `README.md` now describes EigenTrace, with `git clone … && bash install.sh` as the install path (`install.sh` present, installs `requirements.lock.txt`, NLTK data, Piper, Ollama with mistral-small, Owncast) [src: README.md "Install"]. `pyproject.toml` still names the package "omniteardown" v0.4.0 although its dependency list was replaced with EigenTrace's on 2026-09-10, so `pip install -e .` installs a package by that name [src: pyproject.toml; report 2026-09-06 §2B item 7]. OWNER: rename the package or split out `eigentrace-measure` (see [src: report 2026-09-06 §4B]).
- Dependencies: `requirements.txt` (floors) and `requirements.lock.txt` (exact production versions; torch 2.5.1+cu121) [src: requirements.txt; requirements.lock.txt].
- Embedding model: BAAI/bge-large-en-v1.5; OWNER: pin the Hugging Face revision hash.
- Dataset: `dataset/README.md` (v1, in preparation; absent on 2026-09-10). Public daily exports under `docs/data/` (142 files on 2026-09-10; no article bodies; one file per day since 2026-03-31; schema page says v2 while the exporter writes v1 [src: README.md "Daily exports"; report 2026-09-06 §1D]).
- Tests: `tests/` holds 8 files with 69 `def test_` functions (counted 2026-09-10: test_batch_producer 11, test_claims 5, test_eigentrace 13, test_geometry 12, test_math_compression 6, test_segment_player 6, test_state_vector 7, test_text_filters 9); `pytest --collect-only` collects 127 tests (parametrization) on 2026-09-10; the README says 125 [src: README.md "Tests"]. OWNER: state which pass on a clean checkout; note that `tests/test_eigentrace.py` may cover the hedge scorer rather than the measurement path [src: report 2026-09-06 §4B].
- Changelog: `CHANGELOG.md` is linked from `README.md` and from `docs/metrics.md` but does not exist in the tree (2026-09-10). OWNER: create it; the definition-date table in `docs/metrics.md` and the withdrawals page [src: docs/withdrawals.md] are the closest records.
- Metric definitions: `docs/metrics.md` (formulas, code locations, ranges, definition dates).
- Scripts behind each figure: `docs/preprint/figures.md`.
- Replication cost: "about $50 in API credits" [src: docs/index.md; docs/consequence-atlas.md; docs/withdrawals.md; docs/summary-plus.md] [UNVERIFIED: no cost breakdown in the tree]. Production cost basis: about 60 paid frontier calls per 3-story batch at baseline [src: report 2026-09-05 §4].
- Determinism caveat: API callers run at temperature 0 [src: report 2026-09-06 §1C], but vendor models change under their names; the Outliers page dates its findings to April–June 2026 [src: docs/large-language-model-outliers.md]. The entity-swap experiment ran at temperature 0.7 with three runs per cell [src: anamnesis_results/entity_swap_preregistration.md; entity_swap_full_results.json].

---

## Author and acknowledgements

OWNER: author line (the README names Sean Adams [src: README.md "Author"]), affiliation, contact, funding statement, conflict statement (the instrument measures Anthropic, OpenAI, Google, DeepSeek and xAI outputs; state any relationship).

## References

See `docs/preprint/refs.bib`. Its header records which entries were checked against the published record on 2026-09-10 and which rest on recollection of the standard citation.
