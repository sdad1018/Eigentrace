---
layout: default
title: "EigenTrace Data API"
---

# EigenTrace Structured Data

Machine-readable JSON files for research. Updated daily at midnight UTC.

## Endpoint

<pre>https://eigentrace.ai/data/YYYYMMDD.json</pre>

## Example

<pre>https://eigentrace.ai/data/20260331.json</pre>

## Schema (v2)

Each JSON file contains:

**summary** — daily aggregates (mean density, mean VIX, top void/logos words)

Since 2026-09-10 (`schema_revision: "1.1"`; the `version` string is unchanged) every summary aggregate carries its sample size and a 95% interval. Files before 2026-09-10 lack these fields; treat them as optional. On a day with no stories `mean_density` and `mean_vix` are `null` and `n` is 0 (older files wrote 0.0).
- n — stories the day means are computed over; n_unique_guid — distinct story guids among them
- mean_density_ci95, mean_vix_ci95 — [lo, hi] percentile-bootstrap 95% interval on the day mean (null when n < 2)
- per_model_vix — {model: {mean, ci95, n, seed}} per-model mean VIX with its interval
- outlier — {model, runner_up, bootstrap_share, n_paired}: the day's highest-VIX model and the share of resamples in which it keeps that title (below 0.8 it is not separable from the runner-up)
- state_rates — {LOCKSTEP, CONTESTED, HIGH_FRICTION: {k, n, point, lo, hi}} Wilson intervals on the state shares
- killshots_per_story — {n, point, ci95}
- ci_method, ci_seed — percentile bootstrap, B=2000, unit = story, seed = int(YYYYMMDD) so every interval is reproducible from the file; the percentile bootstrap under-covers slightly below n=10

**stories[]** — per-story data:
- consensus_density, mean_vix, state_flag
- model_vix — per-model friction scores
- void_words — filtered lexical void list (Channel 1)
- logos_words — Logos synthesis list (Channel 2)
- null_space_claims — SVD blind spot claims with alignment scores (Channel 3)
- claim_killshots — high-salience omitted facts
- dual_confirmed, triple_confirmed — multi-channel convergence
- compression — language compression scoring:
  - compression_score — overall 0-1 (1 = maximum reshaping)
  - verb_downgrade — zipf frequency drift (positive = softening)
  - entity_retention — named entity survival rate
  - attribution_buffer — typed hedge insertions
- beats[] — full broadcast transcript

**weasel_probes[]** — Wild Weasel escalation data with cliff tables

## Fifteen Measurement Layers

Layers 1-4: Core geometry (density, VIX, spectral resonance, SVD tomography)

Layers 5-8: Four word-finding channels (lexical void, Logos synthesis, SVD null space, void vector)

Layers 9-10: Verification (atomic claim extraction, Wild Weasel escalation)

Layers 11-12: Clustering and patterns (void clustering, token entropy)

Layers 13-15: Language compression (verb downgrade, entity abstraction, attribution buffering)

## License

MIT. Cite as: EigenTrace (2026). *Measuring Language Compression in Aligned Language Models*. eigentrace.ai

## Contact

GitHub: [sdad1018/Eigentrace](https://github.com/sdad1018/Eigentrace)
