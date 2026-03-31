---
layout: default
title: "EigenTrace Data API"
---

# EigenTrace Structured Data

Machine-readable JSON files for research. Updated daily at midnight UTC.

## Endpoint

```
https://eigentrace.ai/data/YYYYMMDD.json
```

## Example

```
https://eigentrace.ai/data/20260330.json
```

## Schema (v1)

Each JSON file contains:

- `summary` — daily aggregates (mean density, mean VIX, top void/logos words)
- `stories[]` — per-story data:
  - `consensus_density`, `mean_vix`, `state_flag`
  - `model_vix` — per-model friction scores
  - `void_words` — full lexical void list (Channel 1)
  - `logos_words` — full Logos synthesis list (Channel 2)
  - `null_space_claims` — SVD blind spot claims with alignment scores (Channel 3)
  - `claim_killshots` — high-salience omitted facts
  - `dual_confirmed`, `triple_confirmed` — multi-channel convergence
  - `beats[]` — full broadcast transcript
- `weasel_probes[]` — Wild Weasel escalation data

## License

MIT. Cite as: EigenTrace (2026). *Omission Ledger*. https://eigentrace.ai

## Contact

GitHub: [sdad1018/Eigentrace](https://github.com/sdad1018/Eigentrace)
