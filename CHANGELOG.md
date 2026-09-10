# Changelog: metric definitions

This file records every change to the *definition* of a number EigenTrace publishes: the beats and ticker the broadcast reads on air, the `attribution` block of each story segment, the daily `docs/data/YYYYMMDD.json` export, the Omission Ledger posts, and the generated site pages (`docs/eigenching.html`, `docs/model_profiles.json`, `docs/spectral_clusters.json`, `docs/soul.md`). It exists so that a reader holding two numbers from different dates can tell whether they were computed the same way. It is not a commit log; commits that changed only wording, plumbing, or reliability are listed only when they change which stories or which models enter a number ("population" changes), because those also break comparability.

Conventions. Dates are commit dates from `git log` (America/New_York). Entries within a date are ordered by importance, not time. "auto commit" marks a change that reached the repository through the hourly `auto: hourly refresh` job, which commits whatever is in the working tree: the live pipeline may have run the new code up to an hour before the commit, and where a patch was applied in the runtime tree first, longer. Nothing here is dated from memory; where a change cannot be dated from git it says so. Current definitions, formulas and measured ranges are in `docs/metrics.md`; this file is its history. "N" is the number of models that returned text for a story (4 or 5). Model roster defaults are the strings in `proxy_auditor.py`; the runtime `.env` can override them and was not read.

## Comparability boundaries (read this first)

A number on one side of a boundary is not comparable with the same-named number on the other side.

| Boundary | What changed | Numbers affected |
|---|---|---|
| 2026-03-24 | VIX redefined (token surprisal, constant 75.0 since 03-06, to embedding cosine distance) | every VIX, mean VIX, state_flag |
| 2026-03-25 / 03-26 | aired void words redefined (donut retrieval to lexical absence); whole-word match from 03-26 | void_words, ticker Core Factors |
| 2026-03-27 | null space projected to source claims instead of vocabulary words | null_space_claims |
| 2026-04-05 | verb drift redefined (curated verb lists to Zipf frequency drift) | verb_downgrade, compression_score |
| 2026-04-06 | source_void created (title + summary + body[:1500] vs responses) | absent_words, absent_ratio, void_context |
| 2026-04-13 | vocabulary 22K to 184K words; state vector beat on air | void_words, logos_words, donut void; EigenChing |
| 2026-04-14 | source_void becomes stem-aware | absent_words, absent_count, absent_ratio |
| 2026-04-20 | source_void excludes headline derivatives | absent_words, absent_count, absent_ratio |
| 2026-04-21 | response length caps removed ("exactly 2 sentences" to unbounded) | density, VIX, absent_ratio, hedges, entity_retention, coverage |
| 2026-05-02 | models receive the article body (before: title + summary[:300] only) | every model-derived number; source_void vs responses finally measures the same text |
| 2026-05-14 | aired void filter simplified (Zipf band dropped) | void_words |
| 2026-05-21 | model roster changed (GPT, Claude, Grok strings) | every model-derived number |
| 2026-06-25 | thin-source gate (stories under 40 source words dropped); ARM segment; signature persisted | population of every number; attribution.eigenching |
| 2026-07-03 | Summary Plus prompt gets three channels; sp_channels stored | summary_plus, sp_channels |
| 2026-07-06 | logos synthesis V9 to V10 with said-stem readout filter | logos_words, dual/triple confirmation, Summary Plus flat channel |
| 2026-07-08 | void ensemble beats replace the void/confirmation/consequence beats on air | what "void words" are heard on air (stored void_words unchanged) |
| 2026-09-04 | data export, soul statistics and model profiles exclude the system's own segments; export dated to the completed day | docs/data summary numbers, docs/soul.md, docs/model_profiles.json |
| 2026-09-09 | EigenChing axis 6 = VIX spread; SVD null vector from the uncentred matrix; killshots need an omitter; source bodies chrome-stripped; Gemini timeout 45 s | state vector, archetypes, null_space_claims, claim_killshots, source_void, compression, and (via the prompt) every response |

## [2026-09-10]

### Fixed

- **Ticker "Friction" (on-air ticker line).** Old: `segment_player.update_ticker` read a top-level `gap_vix` key that no segment has ever carried (the key has been referenced since `b64573b6`, 2026-04-21), so the ticker printed `Friction: 0.0000` on every story. New: `attribution.mean_vix` (fallback: mean of `attribution.model_vix`), one decimal, the same mean VIX the archive beat and the export carry. Why: the ticker number was not a measurement. Commit `a606d537` (the repo copy of the player; the code comment dates the live-player patch 2026-09-09). Affects: ticker overlay only; stored numbers unchanged.

## [2026-09-09]

Commits `69bc8dd3` (22:00, "fix: non-ideological bug batch 2026-09-09"), `88642ab4` (22:02, gitignore only), `63ceb9b6` (23:25, atomic ticker write only). The last two change no metric.

### Changed

- **EigenChing / state-vector axis 6.** Old: `mean_vix`, quantized with `state_vector.QUANT_RULES["mean_vix"]` (low 15 / high 30, inverted), in `script_v3.py` beat_18b_state_vector (since `eb104c53`, 2026-04-13), `eigenching.py` `__main__` history analysis (since `315fd44d`, 2026-04-16) and `batch_producer.stage_summary_plus_probe` (since `077e84b6`, 2026-06-25). New: `vix_spread = max(model_vix) - min(model_vix)` (0 when fewer than two values), quantized with `QUANT_RULES["vix_spread"]`: low 10 / high 25, inverted, so spread >= 25 is -1 "Breaking" and spread <= 10 is +1 "Tight". Why: mean VIX is a function of consensus density (axis 1), so axis 6 duplicated axis 1; the axis vocabulary in `eigenching.py` had described "vix_spread: how much one model broke ranks" since `1c7eb5b4` (2026-04-16) while the code used the mean, and `state_vector.py` has carried the `vix_spread` rule with these thresholds since its only commit `5c7f5e72` (2026-04-13). Commit `69bc8dd3` (`script_v3.py`, `batch_producer.py`, `eigenching.py`; `state_vector.py` unchanged). Affects: on-air beat_18b_state_vector (signature, archetype name, "this exact state has occurred N times before": the history is recomputed under the new axis, so that count for the same story differs across the boundary); `attribution.eigenching.signature` / `.axes`; `docs/eigenching.html` and `docs/eigenching_data.json` (hourly, `eigenching_report.py`); `docs/eigenching_distribution.md`; which story the ARM segment picks (ranking tie-break unchanged, signature changed). The sixth trit of any signature stored before 2026-09-09 22:00 is a mean-VIX trit.

- **SVD null-space direction (`null_space_vec`).** Old: last right singular vector of the mean-centred N x 1024 response matrix `Y_c` (economy SVD). An N-row centred matrix has rank at most N-1, so that vector had singular value ~0 and a numerically arbitrary direction (row order and float noise decided it). New: last right singular vector of the uncentred unit-row matrix `Y`, the least-variance direction of the raw rows, as the live tree already computed. The scalars `consensus_compression` (S[0]/sum S) and `null_space_energy` (S[-1]/S[0]) are still taken from the centred matrix and are unchanged (they are not published). Why: rank fix. Commit `69bc8dd3`, `geometric_engine.calculate_svd_reconstruction`. Affects: `null_space_claims` (source claims ranked by `abs(cos(v, e_claim))`, stored with signed `null_alignment`): on air beat_10_null_space and the Director prompt "Null claim"; `attribution.null_space_claims` (top 2), `audit_log.jsonl` (top 3), `docs/data` `null_space_claims`, the "Null space" section of the daily Omission Ledger (`claim_extractor.daily_digest`); the triple confirmation (`beat_09_confirmation`: aired void words that occur inside the top-2 null claims); `reconstruction_alignment` (cos(v, donut void centroid), Director context only). In this tree the vector has no other consumer: `consequence_engine.raycast_null_space` has no callers, and the Summary Plus channel labelled "flat raycast" is `logos_words` (see 2026-07-06), which does not use this vector.

- **Killshots (`claim_killshots`).** Old (since `b36c8ec4`, 2026-03-26): `salience >= 0.45 and coverage_ratio <= 0.2`. A claim with an empty `omitted_by` qualified: with N = 5 one model can cover a claim (`coverage_ratio` 0.2) while the other four are "partial" (0.65 <= cosine < 0.75), leaving nobody in `omitted_by`; such claims aired as "Omitted by: all models" (label since `1f4f058d`, 2026-04-13; blank before that). New: additionally requires a non-empty `omitted_by`; the beat lists the omitters and skips claims without one. Why: a claim nobody omitted is not a killshot. Commit `69bc8dd3` (`claim_extractor.find_killshots`, `script_v3.py` beat_15_killshots). Affects: beat_15_killshots; `attribution.claim_killshots` (top 3), `audit_log.jsonl` (top 5), `docs/data` `claim_killshots`, Omission Ledger killshot lists, `void_registry.jsonl`, BroadcastState beliefs, the pundit-desk record. Per-story counts can only fall.

- **Scraped source body (`story.body`, `attribution.source_body`).** Old: trafilatura output (or the regex fallback) stored verbatim; feed chrome ("Recommended Stories", "list 1 of 4", photo credits, sign-up prompts) counted as source text (the commit note puts it in about 75% of bodies). New: `proxy_auditor._strip_chrome` removes chrome lines, lines shorter than four words without terminal punctuation, and inline credit tokens; trafilatura runs with `favor_precision=True`. Why: chrome was being measured as "words the models dropped". Commit `69bc8dd3`. Affects everything downstream of the body: the model prompt (`body[:2000]`, so every response and every response-derived number); `source_void` `absent_words` / `absent_count` / `absent_ratio` / `absent_phrases` / `source_word_count` (`body[:1500]`); `compression` `verb_downgrade` / `entity_retention` / `attribution_buffer` / `compression_score` (`body[:1000]`); `void_vector`; the spiral channel; the thin-source word count. Expect lower `absent_count` and `absent_ratio` and higher `entity_retention` on average after the change.

- **Soul "stories processed" count** (`docs/soul.md`, "You have processed N+ stories"). Old: count of every `tmp/segments/*_segment.json`, including idle, weekly, governance, self-audit, roundtable, pundit and silence output. New: story files only (`YYYYMMDD_HHMMSS_<12 hex>_segment.json`). Commit `69bc8dd3`, `soul_updater.inject_epistemic_anchor`.

- **Cross-story frequency table** (`cross_story_freq.py`, read by the cross-story beat). Old: `freq[word]` was updated inside a loop over `w`, so each count was credited to the previous loop's word. New: `freq[w]`. Commit `69bc8dd3`. Cross-story counts produced before this date are unreliable.

### Changed (population)

- **Gemini timeout 600 s to 45 s** (`proxy_auditor.call_gemini`) and **transient API errors retried** (timeouts, resets, 429/5xx: two retries with backoff; auth/parameter errors and missing keys never retried; `batch_producer._call_with_retry`). Why: one slow Gemini call stalled the producer for ten minutes; one transient failure used to cost a model its seat for the story. Commit `69bc8dd3`. Affects which stories have four versus five responses, and N enters `consensus_density`, every per-model VIX, `mean_vix`, `state_flag`, `coverage_ratio`, killshots, `source_void` ("absent from all models"), the compression means and the EigenChing axes. Not a formula change.

- **Producer queue gate** counts only unplayed story segments younger than six hours (own-output files used to hold the gate shut); **failure strings** (`[Gemini error: ...]`, `[Mistral unavailable: ...]`) are no longer appended to scripts and read aloud; the duplicated Wikipedia edit-velocity beat is removed. Commit `69bc8dd3`. Changes what airs, not how anything is measured.

## [2026-09-04] auto commit `43a26beb`

### Changed

- **Daily data export (`docs/data/YYYYMMDD.json`).** Old (since `b63c1eaf`, 2026-03-31): every `*_segment.json` whose filename starts with the date, so the system's own segments (idle, silence, consolidation, weekly, governance, foraging, self-audit, roundtable, pundit desk, conversation), which carry no `model_vix` and a `consensus_density` of 0, were counted as stories and averaged into `mean_density` and `mean_vix`. New: those segment types, and any segment without `model_vix`, are skipped. Affects `summary.stories_analyzed`, `mean_density`, `mean_vix`, `top_void_words`, `top_logos_words`, `dual_confirmed_global` and the `stories` array. `data_exporter.py`.
- **Export and ledger date.** Old: `daily_report.sh` ran at 00:00 with `DATE = today`, exporting and ledgering the day that had just begun. New: `DATE = yesterday` (the completed day); `set -e` removed so one failing step no longer aborts the export. Which pre-2026-09-04 daily files were later regenerated by the separate "daily data auto" job is not established here.
- **Soul rolling 24-hour statistics** (`soul_updater.load_recent_segments`) and **site profiles** (`refresh_profiles.sh`: `docs/model_profiles.json` per-model VIX means, outlier rates and lengths since epoch 2026-04-14; `docs/spectral_clusters.json`) exclude the system's own segments. Same commit.

## [2026-07-08] auto commits `8ad18801` (21:00), `fc640f21` (22:00); docstring amendments `8fac86e9`, `b2baafd4`

### Added

- **Void ensemble v1.1 on air.** New beats `ensemble_intro`, `ensemble_top5`, `ensemble_raycast`, `ensemble_opine`, `ensemble_memory`, `ensemble_provenance` built from a vote over every available candidate list (headline void, source void, logos, `sp_flat`, `sp_spiral`, `sp_void`, synthesis, donut, VF-IDF and others), weight `1/(1 + rank)` (0.3 for source-void words), merged by stem and by geographic group, ranked by (number of channels, summed weight), top 5; stored as `attribution.ensemble`. When the ensemble runs, `void_ensemble.weave_beats` removes `beat_06_void_reveal`, `beat_07_void_analysis`, `beat_09_confirmation`, `beat_consequence_accountability` and `beat_consequence_data` from the aired script. `void_ensemble.py`, wired in `batch_producer.stage_3_geometric` / `stage_7_write_segments`. Affects what "void words" the audience hears from this date; `attribution.void_words` and the `docs/data` `void_words` field are unchanged (still the lexical void of 2026-03-25). Note that `sp_flat` re-labels the logos list and `sp_void` re-labels the aired void, so one computation can cast two votes.

### Documentation only

- `reconstruct_unaligned_truth` (V9) docstring corrected: its consensus-gravity term pulls toward the centroid (the sign has been `+0.15` since `7a37bc77`, 2026-03-06). The V10 docstring's "~8x less escape" claim withdrawn and replaced by measured bands (`8fac86e9`, `b2baafd4`). No numeric change.

## [2026-07-06] auto commit `189a1a49`

### Changed

- **Logos words (`logos_words`, "Logos synthesis", "the anti-consensus point").** Old (V9, `reconstruct_unaligned_truth`, aired since 2026-03-26): projected gradient descent on the unit sphere (AdamW, lr 0.05, 150 steps, start at the centroid) minimising `LogosLossV9(x, e_i) + 0.15 * cos(x, centroid) - 0.30 * cos(x, headline)`; readout = the 5 vocabulary words nearest `x*`. New (V10, `reconstruct_unaligned_truth_v10`): same optimiser on `mean_i (1 - cos(x, e_i)) + 0.75 * cos(x, centroid) - 0.30 * cos(x, headline)`; readout = the 25 nearest vocabulary words, drop any word whose every token's Porter stem appears in some model's response, keep 5; if fewer than 3 survive, the unfiltered top 5. V9 remains as the exception fallback. Why (docstring): adopted after a pre-registered three-round ablation, story-specificity indistinguishable from V9 with less escape from the consensus; the escape figure was amended on 2026-07-08 (above). `docs/metrics.md` shows the V10 objective is linear in `x` for unit vectors, with closed form `x* proportional to (||c|| - 0.75) * centroid + 0.30 * headline`. Affects: beat_08_logos_reveal; `attribution.logos_words`, `audit_log.jsonl`, `docs/data` `logos_words` and `top_logos_words`; dual and triple confirmation (`beat_09_confirmation`, `docs/data` `dual_confirmed`); the Summary Plus "flat raycast" channel; the Wild Weasel step-2 prompt; the ensemble vote.

## [2026-07-03 to 2026-07-05] auto commits `0e7db193` (07-03 00:01), `a9d00a47` (07-03 01:02), `ff2530fe` (07-03 08:02), `1aeda9df` (07-05)

### Changed

- **Summary Plus prompt and `sp_channels`.** Old (2026-06-07): each active model got the story title, its own summary, and `logos_words[:5]` "surfaced as related". New: three labelled lists: "Flat raycast (SVD anti-consensus direction)" = `logos_words`; "Convergence spiral (independent second SVD derivation)" = `spiral_sampler.convergence_spiral` over the source (summary only until `1aeda9df`, then title + summary + body, at most 5,000 characters), minus words already in the flat list; "Source-anchored void (source words no summary kept)" = the aired headline-void words (`void_override`) minus the other two lists. Each list is stem-deduplicated to 5 (`a9d00a47`) and stored as `attribution.sp_channels`. The labels are prompt text: the spiral contains no SVD and the "source-anchored" list is the headline void, not `source_void`. Affects `beat_03c_summary_plus_*` text, `attribution.summary_plus` / `sp_channels`, the ARM segment (reuses `summary_plus`), the pundit desk. Model output, not deterministic.
- **Wild Weasel escalation segment restored** (`ff2530fe`). Between `077e84b6` (2026-06-25) and `ff2530fe` (2026-07-03) the producer called `stage_summary_plus_probe` in place of `stage_weasel_probe`, so no `wild_weasel` segment was produced in that window and `docs/data` `weasel_probes` counts it as zero; from 07-03 both segments are produced.
- **Pundit desk** (`1aeda9df`): new own-output segment type built from the roundtable record. In that record a killshot without `omitted_by` is labelled "all five models"; this is prompt text for the pundits, not a stored metric.

## [2026-06-25] auto commits `077e84b6` (15:05), `01bfa338` (20:02)

### Added

- **Thin-source gate** (`proxy_auditor.fetch_feed`, `MIN_SOURCE_WORDS = 40`). Stories whose title + RSS summary + scraped body contain fewer than 40 words are dropped before any model is called (`thin_source_dropped` in the log). Old: headline-only stories were measured. Commit `01bfa338`. Affects the population of every published number from this date (near-zero `source_word_count` stories disappear; `absent_ratio` and `entity_retention` denominators shift).
- **Wild Weasel ARM** (`segment_type = summary_plus_arm`, `batch_producer.stage_summary_plus_probe`). Story = the most "closed" EigenChing signature in the batch (sum of `-trit` over the absent, verb_drift, entity and hedge axes; tie broken by highest mean VIX); the host model derives three questions from the source; each frontier model answers; a posture is assigned by matching refusal phrases. New published segment. Commit `077e84b6`.
- **EigenChing signature persisted** as `attribution.eigenching` (`signature`, `axes`, `archetype`, `name`, `tier`, `distance`). Before this date the signature was computed for narration only; for earlier segments it must be recomputed from the stored signals with the axis definitions of that date. Commit `077e84b6`.

## [2026-06-11] auto commit `4934ff41`

### Added

- **Prediction scorecard** (`beat_18d_prediction_scorecard`): airs "Prediction accuracy on this story: N percent" from `BroadcastState.prediction_score` (predicted outlier model and predicted void words checked against the story's `model_vix` argmax and void words). New on-air number; not exported.

## [2026-06-07] auto commit `7853872f` (wording change `14210ba5`, 2026-06-06)

### Added

- **Summary Plus on air** (`beat_03c_summary_plus_intro` and one "take two" beat per model). Each active model is asked to rewrite its summary using `logos_words[:5]`; stored as `attribution.summary_plus`. Model output, not deterministic. `14210ba5` changed the narration of the compression report and Director prompts from "softened / suppressed" to "vary / differ": no numbers changed.

## [2026-05-21] `ae6eb7b8`, `c655fe29`, `35f43021`

### Changed (population)

- **Model roster defaults.** OpenAI `gpt-5.4-mini` to `gpt-5.5` (`ae6eb7b8`) and back to `gpt-5.4-mini` (`c655fe29`, same day). Anthropic `claude-sonnet-4-20250514` to `claude-sonnet-4-6-20250217` (`ae6eb7b8`) to `claude-sonnet-4-6-20260217` (`c655fe29`) to `claude-sonnet-4-6` (`35f43021`). Grok `grok-4-1-fast-non-reasoning` to `grok-4-3-fast` (`ae6eb7b8`) to `grok-4.3` (`c655fe29`). Every model-derived number before and after comes from different models; `docs/model_profiles.json` averages across the change.

## [2026-05-14] `1cabf800`

### Changed

- **Aired void words filter** (`batch_producer.stage_4_generate_scripts`). Old (since `d4574f00`, 2026-04-01): `eigentrace_math.filter_void_candidates`: drop headline stems and prefix artifacts, exact-stem dedup, Zipf frequency band 1.5 to 6.0, top 15. New: drop words equal to a headline word (3+ letters) or sharing a 4-character prefix with a headline word of 4+ letters; top 15; unfiltered list if everything is filtered. The Zipf band no longer applies to aired void words. Affects `void_words` (beats 06/07, ticker Core Factors, `attribution`, `audit_log.jsonl`, `docs/data` `void_words` / `top_void_words`), `synthesis_words` (= top 5), the Wild Weasel step-1 prompt, and later the Summary Plus void channel and the ensemble vote.

## [2026-05-02] `c9f3459e`, `6b449784`

### Changed

- **What the models are asked.** Old (`_prompt_for_story`, unchanged from `bcb35d3d` 2026-03-31 to this commit): "Breaking news: {title} / Summary: {summary[:300]}". The scraped body was stored as `story.body` and, from 2026-04-06, used as *source* text by `source_void` and `compression`, but it was never sent to the models. New: "Breaking news: {title} / Article text: {body[:2000]}" when a body exists, else `summary[:500]`. Why (commit): "METHODOLOGICAL FIX: models now receive article body text". Affects every response-derived number. In particular, from 2026-04-06 to 2026-05-02 `source_void` counted as "absent" the words of a body the models had not seen, and `entity_retention` / `verb_downgrade` compared responses with a source the models had not read; those values are not comparable with later ones.
- Gemini default `gemini-3.1-pro-preview` to `gemini-2.5-flash` (`6b449784`; population).

## [2026-04-21] `6cc77198`, `96657391`, `b64573b6`

### Changed

- **Response length caps removed** (`6cc77198`). Old: prompt "In exactly 2 sentences: what happened and one concrete implication", system prompts "Be direct. 2 sentences.", Anthropic `max_tokens` 350, Mistral 500, `model_responses` truncated at 500 characters, `source_body` stored at 2,000 characters. New: "Explain what happened and the concrete implications", "Be direct and thorough", `max_tokens` 1000 / 2000, no truncation, `source_body` 5,000 characters (ablation `max_tokens` 200 kept). Affects `consensus_density` (longer same-prompt responses embed closer), every VIX and `state_flag`, `absent_ratio` (more source words covered), hedge counts (more words), `entity_retention`, `coverage_ratio` and killshots.
- `filter_void_candidates` excludes title derivatives by substring or shared 4-character prefix (demonyms such as "cubans" for "Cuba"; `96657391`); applies to aired void words until 2026-05-14.
- `segment_player.py` began reading the nonexistent `gap_vix` key for the ticker (`b64573b6`): ticker Friction reads 0.0000 from here until the 2026-09-09/10 fix.

## [2026-04-20] `cf71a82a`

### Changed

- **`source_void.absent_words` exclude headline derivatives.** `source_anchored_void` gains a `title` argument; a source word is not absent if its Porter stem matches a headline word's stem, or it contains / is contained in a headline word, or shares a 4+ character prefix with one ("iranian" when the headline says "Iran"). Affects `absent_words`, `absent_count`, `absent_ratio` (`absent_phrases` unchanged); EigenChing axis 2; the consequence raycast input; later the Summary Plus void channel.

## [2026-04-16] `1c7eb5b4`, `315fd44d`, `c2387c02`, `03bed83d`

### Added

- **EigenChing archetypes** (`eigenching.py`): the 729 ternary states get 32 hand-named cells ("The Sealed Vault", "The Cornering", ...) and compositional names for the rest; `beat_18b` announces the name, meaning and history matches; morphology tiers (variant at Hamming distance 1, cousin at 2, compositional at 3+) and the novelty detector (`315fd44d`). The module docstring and axis vocabulary describe axis 6 as `vix_spread`; the `__main__` analysis (`315fd44d`) and the on-air beat used `mean_vix` until 2026-09-09.
- **`docs/model_profiles.json`** (`c2387c02`, then hourly): per-model mean VIX, outlier rate (share of stories where the model has the highest VIX), consistency and verbosity, computed over segments from the "clean epoch" 2026-04-14 onward (the stemming and dedup fixes of that date).
- `beat_15e_spectral_clusters` on air (`03bed83d`); `docs/spectral_clusters.json` added to the hourly refresh 2026-04-21 (`6047c970`) and regenerated the same day with a boilerplate filter and higher threshold (`35b6d1e9`), a sparsified 5-cluster graph (`c93c31a8`) and PMI-weighted adjacency (`9e9d5ebc`); a NameError fix on 2026-05-13 (`1afd3d9a`) made the Laplacian recompute from the filtered co-occurrence matrix, so cluster files before that date are from the unfiltered matrix.

## [2026-04-14] `11b6ba49`, `2f66c846`

### Changed

- **`source_void` becomes stem-aware.** Old (2026-04-06): surface-form set difference (source words minus all response words), so "blockades" was absent when a model wrote "blockade". New: a source word is absent only if neither its surface form nor its Porter stem appears in any response. Affects `absent_words`, `absent_count`, `absent_ratio` (lower after), EigenChing axis 2. Title-based deduplication stops the same story entering from several feeds (`2f66c846`; population).

## [2026-04-13] `eb104c53`, `5c7f5e72`, `1f4f058d`, `84bb17bf`, `bc9cd6f7`, `366ada7e`, `29f4018b`

### Added

- **State vector on air** (`beat_18b_state_vector`, `eb104c53`) with `state_vector.py` (`5c7f5e72`, its only commit; thresholds unchanged since): six trits from `consensus_density` (<= 0.82 gives -1, >= 0.92 gives +1), `absent_ratio` (0.3 / 0.6, inverted), `verb_drift` = `verb_downgrade` (0.02 / 0.08, inverted), `entity_retention` (0.3 / 0.6), `hedge_count` = `attribution_buffer.total` (1 / 4, inverted), and `mean_vix` (15 / 30, inverted) as axis 6 until 2026-09-09. "This exact state has occurred N times before" is the count of stored segments with the same signature.
- **Vocabulary 22,611 to 184,789 words** (`366ada7e`, build script `build_vocab_200k.py`; the tensor files are untracked, so the switch date is the commit's). The vocabulary is the search space of the aired void words, the logos readout and the donut void, and therefore of `void_context` and `void_frequency.json`; all of those change character from this date.
- **`void_vector`** ("Layer 8", `bc9cd6f7`): residual source-minus-centroid magnitude stored in `attribution`; never aired.

### Changed

- **Per-model void readout** (`beat_04c_per_model_void`, `84bb17bf`). Old: identical lists for every model (circular). New: words some models kept and others dropped. Same commit: regex fallback for paywalled pages after trafilatura, so more stories have a non-empty body (population for `source_void`).
- **Killshot omitters label** (`1f4f058d`): "Omitted by:" reads "all models" instead of blank when `omitted_by` is empty (removed 2026-09-09).
- Story category from a content classifier instead of feed tags (`29f4018b`, by commit message): affects `docs/data` `category` and the per-category `void_frequency` counts.

## [2026-04-09] `fee66a84`, `3d464fb9`, `f15c2796`, `dd5d7afb`

### Changed

- **Body scraper**: regex HTML strip, first 1,500 characters, minimum 200 (`bcb35d3d`) replaced by trafilatura extract, first 2,000 characters, minimum 100 (`fee66a84`). Cleaner bodies mean fewer navigation words counted as absent by `source_void`.
- **Absent-words readout** (`beat_04b_absent_words`, added by `dd5d7afb` with the per-model comparison beat): a 66-word navigation stoplist was added (`3d464fb9`) and removed the same day because it suppressed legitimate words (`f15c2796`); the gate `absent_ratio > 0.3 and at least 3 words` from `3d464fb9` remains.

## [2026-04-06] `40623e0f`, `75580976`, `bf084f13`, `38051f8c`

### Added

- **`source_void`** (`eigentrace_math.source_anchored_void`): source = title + ". " + RSS summary + `body[:1500]`; source words = lowercase alphabetic tokens of 4+ letters not in a 70-word stoplist; `absent_words` = source words in no response (surface form; stem-aware from 04-14; headline derivatives excluded from 04-20); `absent_phrases` = source bigrams / trigrams absent as substrings from every response, first 20 alphabetically; `absent_ratio = absent_count / source_word_count`. **`void_context`** labels for the donut void words by their document frequency across past stories (`HIGH_SALIENCE` in source and under 10% of stories, `POSSIBLE_SIGNAL` under 30%, `GENERIC_ARTIFACT` 30% or more, `EMBEDDING_SIGNAL` not in source and under 10%) accumulated in `void_frequency.json` without decay. Wired into the pipeline and broadcast (`75580976`), saved in segments (`bf084f13`) and added to the data API with `compression` (`38051f8c`).

## [2026-04-05] `08ad708e`

### Changed

- **`verb_downgrade` ("verb drift") redefined.** Old (`2136a70c`, 2026-04-01): per model, `weak_added / (strong_kept + weak_added)` from curated lists (`STRONG_VERBS`, 27 words such as "killed", "seized"; `WEAK_VERBS`, 20 words such as "identified", "linked"), 1.0 when the source had strong verbs and the model kept none. New: content verbs = NLTK POS tags starting with `VB`, longer than 2 characters, not auxiliaries; `drift = mean Zipf(response verbs) - mean Zipf(source verbs)` (wordfreq, English); per model `clip(drift / 2, 0, 1)`; mean over models. Why (commit): "no STRONG_VERBS/WEAK_VERBS lists, zero editorial judgment". Affects `verb_downgrade`, `compression_score` (weight 0.4), `beat_11_compression_report`, and from 04-13 EigenChing axis 3. The new measure is one-sided (rarer verbs than the source give 0).

## [2026-04-01 to 2026-04-04] `2136a70c`, `06c7158e`, `23bf31e9`, `d4574f00`, `551b67a7`, `6e7a5f92`, `501f4ffc`

### Added

- **Language compression** (`eigentrace_math.score_language_compression`, `2136a70c`): `entity_retention` (regex runs of capitalised words plus all-caps tokens, minus 24 sentence starters; retained if the entity is a substring of the response; mean over models), `entity_abstraction_rate = 1 - entity_retention`, `attribution_buffer` (three fixed hedge lists, epistemic / attribution / distancing; per model the distinct list words in the response that are not in the source; `total` summed over models), `compression_score = 0.4 * verb_downgrade + 0.3 * (1 - entity_retention) + 0.3 * min(avg hedges per model / 3, 1)`. Source = title + ". " + summary + `body[:1000]`. Wired into stage 3 and the 20-beat script on 2026-04-04 (`06c7158e`, `23bf31e9`).
- **Aired void filter** `filter_void_candidates` (`d4574f00`): headline-stem removal, prefix-artifact removal, stem dedup, Zipf band 1.5 to 6.0; aired count raised from 5 to 15 (`synthesis_words` = top 5). Tuned the same day: prefix clusters of 3+ candidates skipped and 4-character collapse added (`551b67a7`), then the 4-character collapse removed to keep semantic clusters (`6e7a5f92`). Replaced 2026-05-14.
- Epistemological disclaimer beat after the Logos reconstruction (`501f4ffc`).

## [2026-03-31] `b63c1eaf`, `bcb35d3d`, `90289803`

### Added

- **Data API** `docs/data/YYYYMMDD.json` (`data_exporter.py`, `b63c1eaf`): per story `consensus_density`, `mean_vix`, `state_flag`, `model_vix`, `void_words`, `logos_words`, `null_space_claims`, `claim_killshots`, `dual_confirmed` (top-10 void words also in the top-10 logos words), beats; `summary` with `stories_analyzed`, `mean_density`, `mean_vix`, `top_void_words`, `top_logos_words`, `dual_confirmed_global`. Own-output segments excluded from 2026-09-04.
- **Article body scraping** (`bcb35d3d`): `story.body` = first 1,500 characters of regex-stripped HTML when at least 200 characters; stored, used as source text from 2026-04-06, sent to the models only from 2026-05-02. 24-hour freshness filter on stories (`90289803`; population).

## [2026-03-27] `80acda15`, `89e154d0`, `1c9f2b33`

### Changed

- **`null_space_claims` ("Channel 3").** Old (`bc6f0049`, 2026-03-26): the SVD null-space vector was projected onto the vocabulary tensor to yield words. New: projected onto the atomic source claims: claims ranked by `abs(cos(v, e_claim))`, top 3 kept with signed `null_alignment`, `salience`, `coverage_ratio`, `omitted_by`. `audit_log.jsonl` entries enriched with `model_vix`, void, logos, killshots and null space (`89e154d0`). Host narration model Qwen 2.5 14B to Mistral Small (`1c9f2b33`): narration and claim extraction only, not a measured model.

## [2026-03-26] `b36c8ec4`, `bc6f0049`, `dd01f11a`, `8b2c928b`

### Added

- **Claims, coverage, killshots** (`claim_extractor.py`, `b36c8ec4`): the local Mistral extracts atomic claims from headline + RSS summary; `salience = cos(claim, headline)`; per model covered if `cos(claim, response) >= 0.75` (`COVERAGE_THRESHOLD`), partial if `>= 0.65`, else omitted; `coverage_ratio = covered / N`; killshot = `salience >= 0.45 and coverage_ratio <= 0.2` (plus a named omitter from 2026-09-09). Daily Omission Ledger digest. Same commit: the aired void check became a whole-word regex match instead of a substring test.
- **Logos topic anchor** (`bc6f0049`): `- 0.30 * cos(x, headline)` added to the V9 objective; all six math layers enter script generation.
- **Model roster** (`dd01f11a`): `gpt-4o` to `gpt-5.4-mini`; `claude-haiku-4-5` to `claude-sonnet-4-20250514`; `gemini-2.5-flash` to `gemini-3.1-pro-preview`; `grok-4-fast-non-reasoning` to `grok-4-1-fast-non-reasoning`. **Wild Weasel** escalation probe (`wild_weasel` segment) added. 8-beat broadcast format (`8b2c928b`).

## [2026-03-25] `a49081a0`

### Changed

- **Aired void words redefined ("lexical void").** Old: the donut / annular retrieval of `latent_retrieval.in_domain_void` (vocabulary words with cosine to the headline above 0.52 and cosine to the response centroid below 0.60), via `geometric_engine.run`. New (`batch_producer._compute_void`, stored as `void_override`): the 200 vocabulary words nearest the headline, minus words shorter than 4 characters, minus words present in the concatenated responses (substring test; whole-word regex from 2026-03-26), top 5 by headline similarity. The donut list stays as the fallback and still feeds `void_context`, `void_frequency.json` and `reconstruction_alignment`. Affects `void_words`, ticker Core Factors, the void beats, and from 03-31 `docs/data`.

## [2026-03-24] `60d2a2e2`

### Changed

- **Per-model VIX redefined.** Old (`proxy_auditor.proxy_audit_text`): token-surprisal score `100 * (0.75 * hard + 0.35 * mid) / tokens`, where `hard` counts tokens with surprisal of 10 nats or more and `mid` those between 6 and 10, using Mistral-7B log-probabilities (live from `c4b2d3a4`, 2026-03-03). Because the scorer was stubbed out on 2026-03-06 (`7a37bc77`, `_score_token_logprob` returns `None`), every token fell to `FLOOR = 11.5`, every token counted as hard, and every model scored exactly 75.0 from 03-06 to 03-24. New (`batch_producer.stage_3_geometric`): `VIX_i = clip(500 * (1 - cos(e_i, unit centroid)), 0, 100)` over BGE-large embeddings of whole responses; `mean_vix` = mean over active models; `state_flag`: `mean_vix > 30` HIGH_FRICTION, `> 15` CONTESTED, `density > 0.9` LOCKSTEP, else NOMINAL; callouts (logged only). The batch pipeline replaces the per-story queue worker. No VIX before 2026-03-24 is comparable with any after it. `docs/metrics.md` shows `mean_vix` is a function of `consensus_density` and N.

## Before the batch pipeline (2026-03-03 to 2026-03-20)

- `90e5ae36` (2026-03-03): `consensus_density` defined as the mean of the upper triangle of the response Gram matrix (mean pairwise cosine); the formula has not changed since (no later commit touches that function body).
- `c4b2d3a4` (2026-03-03): token-log-probability VIX with a local Mistral-7B scorer; `338d9c4f` (2026-03-03): hand-written `CONCEPT_BANK` replaced by a 60K-word vocabulary tensor as the search space for void and concept words.
- `33dbfa46` (2026-03-05): per-model void proximity and tightened donut thresholds; `71900b7c` (2026-03-05): spectral (FFT) "Logos Transform" analysis added (never aired).
- `7a37bc77` (2026-03-06): Mistral-7B scorer retired, freezing the surprisal VIX at 75.0 (see 2026-03-24); `spectral_gap` added; the V9 consensus-gravity sign changed from `loss - 0.15 * cos(x, centroid)` to `loss + 0.15 * cos(x, centroid)`, so from this date V9 pulled the synthesis toward the centroid (documented in code on 2026-07-08).
- `f567ea73`, `abb22683` (2026-03-20): research-battery changes (`eigentrace/core.py`, `eigentrace_null.py`): residual eigen-VIX, void thresholds relaxed (`prompt_threshold` 0.45 to 0.35, `centroid_ceiling` 0.25 to 0.35), hedge lexicon expanded. These predate the broadcast pipeline of 03-24 and did not feed on-air numbers.
- The station went live on 2026-03-16 (`16364b3d`); every number aired between 03-16 and 03-24 came from the pre-batch `proxy_auditor` path described above.
