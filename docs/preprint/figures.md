# Figures for docs/preprint/eigentrace-preprint.md

One row per figure. "Producer" is the script or data file in the tree (`/mnt/c/Users/M4ISI/eigentrace`) that makes it, or "TODO: script needed". Status is what was checked on 2026-09-10: the file exists and is named for the result (present), or the result has no reproducing script (missing). No figure was regenerated for this draft.

| # | figure | section | producer | status |
|---|---|---|---|---|
| F1 | Pipeline diagram: RSS → body fetch → five vendor summaries → frozen embedding → scores → segment JSON → daily export | §3.11 | TODO: script needed (draw from `batch_producer.py` stages; no diagram source exists) | missing |
| F2 | Density distribution over the registry (histogram, median 0.902, 86% in [0.85, 0.95]) with monthly SD line (0.045 → 0.017) | §3.2 | TODO: script needed; numbers were computed from the registry in [src: report 2026-09-05 §3] with no script committed | missing |
| F3 | Mean VIX vs density scatter with the identity curve 500·(1 − sqrt((1+(N−1)d)/N)) (9,113 rows, r = −0.996) | §3.3 | TODO: script needed; same origin as F2 | missing |
| F4 | Entity-swap retention: 0.522 vs 0.545 with the within/cross-category null (0.004 / 0.023) and the keyword control (26% / 25%) | §5.1 | `entity_swap_experiment.py` (present; OWNER: confirm it emits these numbers) | present, unconfirmed |
| F5 | LLM-judge null: 96% "modifier fully preserved" on 216 summaries vs the geometric separation | §1.2, §6 | `prefilter_validation_v3.py` (present; contains the string "fully preserved"; OWNER: confirm) | present, unconfirmed |
| F6 | Charged vs institutional retention (+0.020, d = 0.35, five frequency bands, IDF R² ≈ 0.002) | §5.2 | TODO: script needed; not located in the tree | missing |
| F7 | Cutoff edge scatter: per-name retention, established vs post-cutoff, dot size = story count (the Boundary page plot) | §5.3 | page fetches `docs/cutoff_retention.json`, which does not exist; renders hard-coded fallbacks [src: report 2026-09-05 §5]. Candidates: `test_cutoff_clean.py`, `test_cutoff_familiarity.py` | missing data file |
| F8 | Random-word baseline: cos(void word, own story) vs random control words and vs random other story, two embedding families, n = 150 | §5.4 | one of `void_proper_test.py`, `corpus_void_target.py`, `planet_rigor.py`, `strain_gauge.py`, `synth_void.py`, `confront.py`, `summary_plus.py` (all contain the control words "margarita"/"stapler"); hard-codes 150 stories and tests the donut void [src: report 2026-09-05 §5]. OWNER: identify the one that produced the page | present, ambiguous |
| F9 | Atlas domain chart: stakes / actors / specifics / fence by domain (war 781, other conflict 484, general 31) | §5.4 | `build_atlas_data.py`, `consequence_atlas.py` → `docs/atlas_data.json`, `atlas_chart_data.json` | present |
| F10 | Outliers: magnitude-outlier share and kind-outlier share per model, 2,201 stories | §5.5 | TODO: script needed; percentages could not be verified against any script [src: report 2026-09-05 §5]. `docs/model_profiles.json` and `refresh_profiles.sh` publish a related "suppression rank" (ascending mean centroid distance) but not these shares | missing |
| F11 | Iran arc Fig 1: six-axis weekly mean signature, W15–W24 | §5.6 | `iran_arc.py` / `iran_arc_v2.py` → `iran_arc.json` / `iran_arc_v2.json` (OWNER: confirm which version the page embeds) | present |
| F12 | Iran arc Fig 2: VIX-outlier share by week per model, stable-five weeks shaded | §5.6 | same as F11 | present |
| F13 | Iran arc controls: absent axis under bge-large vs e5-large (r = 0.991); length-capped variants | §5.6 | TODO: locate; not separated from F11 scripts in this draft | unknown |
| F14 | Residual-direction paired comparisons (Test 1 table as a paired dot plot, n = 277 / 256 / 300) | §5.7 | `geom_test.py` in the 2026-09-09 session scratchpad, not in the repo [src: report 2026-09-09 last line]. TODO: move into the tree under a `experiments/` path with its cached outputs | missing from tree |
| F15 | Summary Plus displacement geometry (toward source vs random source, +0.373 vs +0.196; length ratio 0.36) | §5.8 | same scratchpad script as F14 | missing from tree |
| F16 | Controlled arms A–F, C2: spillover recovery, grounding, killshot recovery, length, echo | §5.8 | `arms_test.py`, `arms_e.py`, `arms_results.json`, `arms_e_results.json` in the session scratchpad [src: report 2026-09-09 last line] | missing from tree |
| F17 | Summary Plus blind-panel arms (insight / faithfulness / analogy; baseline, A, A·C, C, human) and the head-to-head vs bare prompt (n = 788) | §5.8 | `confront10_final_BOTH.py`, `confront10_final.py` → `confront10_final_results.json`, `confront10_final_panel.json`; baseline numbers not reproducible from any script [src: report 2026-09-05 §5] | present, not reproducing |
| F18 | Loss-class drop rates (adverbs 40%, relational 30%, nouns 20%, causal 11%; headline 8.7% vs body 26.2%) | §5.9 | TODO: script needed; pilot run in the 2026-09-06 session, not committed | missing |
| F19 | Name-erasure leaderboard (per-model name-drop rate; 323 of 1,335 spans in no summary) | §5.9 | TODO: script needed; pilot run in the 2026-09-09 session with NLTK, not committed; production needs spaCy NER and boilerplate stripping | missing |
| F20 | EigenChing axis correlation matrix and PCA variance (4 PCs = 80%) | §5.10 | session scratchpad (2026-09-09), script not named in the report | missing from tree |
| F21 | Panel-size over time (4-model vs 5-model rows; Claude absence 84%) | §3.11, §6 | TODO: script needed; from the audit log | missing |
| F22 | Withdrawals timeline (five entries with the control that killed each) | §6 | `docs/withdrawals.html` text only; no data figure needed | n/a |

Notes

- Figures whose producer is in a session scratchpad (F14–F16, F20) must be re-run from the tree before submission; the scratchpad is not versioned.
- Figures F2, F3, F18, F19, F21 are registry or segment scans. They should be one cached pass over `tmp/segments` (private) writing a derived table into the dataset v1 build, not per-figure scans.
- Article bodies must not appear in any figure or its committed data file (publisher copyright).
- Every figure caption in the preprint must carry the same [src: …] tag as the number it plots.
