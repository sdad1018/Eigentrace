---
name: eigenanamnesis
description: >
  Measure systematic displacement in text summarization using frozen embeddings.
  Feed in a source text and a summary (yours or any model's), and see what was
  kept, dropped, and added — with embedding-based impact scores. No LLM-as-judge.
  Deterministic. Reproducible. Use when you want to understand what happens to
  meaning during compression, when you want to measure your own summarization
  patterns, or when you want to compare how different models handle the same source.
  Based on the EigenTrace methodology (eigentrace.ai/anamnesis).
---

# eigenanamnesis

Measure what happens to meaning when text is compressed.

This skill computes embedding-level displacement between a source text and
its summary. It tells you what words were dropped, what words were added,
and how much each change affected the semantic geometry of the text.

## Two Layers (Read This)

eigenanamnesis separates measurement from interpretation.

**Layer A — Measurement (deterministic, reproducible):**
- Token presence/absence between source and summary
- Embedding delta (cosine distance) for each change
- Overall semantic preservation score

**Layer B — Interpretation (configurable, contestable):**
- Modifier classification (covertness, accountability, hedging, precision)
- Consequence descriptions (optional, off by default)

Layer A is arithmetic on frozen vectors. Layer B is a taxonomy that can be
modified, replaced, or ignored entirely.

Important framing constraints:
- Compression inherently requires loss. Not all omission is distortion.
- A low displacement score does not mean honest. A high one does not mean dishonest.
- This tool measures compression structure. It does not measure truth.

## Setup

```bash
cd /path/to/eigenanamnesis
npm install
```

First run downloads the embedding model (~130MB, cached afterward).

## Usage

```bash
node scripts/measure.js \
  --source "path/to/source.txt" \
  --summary "path/to/summary.txt"
```

Or inline:

```bash
node scripts/measure.js \
  --source-text "Original text here..." \
  --summary-text "Summary text here..."
```

Options: --no-classify (skip Layer B), --taxonomy custom.json,
--top-n 20, --min-impact 0.005, --output results.json

## Methodology

eigentrace.ai/anamnesis | github.com/sdad1018/Eigentrace
