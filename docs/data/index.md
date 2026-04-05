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
