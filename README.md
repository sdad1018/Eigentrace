# EigenTrace

**Deterministic observability for AI-generated content.**

EigenTrace measures what AI models drop, soften, and avoid when processing factual content. It runs 17 independent measurement layers across 5 frontier models. Every measurement is arithmetic on frozen embeddings and source text — no LLM evaluates another LLM's output.

## The Problem

When an AI copilot generates a quantum simulation config, a noise model, or a cost estimate, it silently compresses the source material. Parameters disappear. Thresholds get rounded. Specific language becomes vague. The output reads fluently, passes schema validation, and is wrong.

There is no standard way to measure this compression. The industry default — LLM-as-judge — uses one probabilistic model to evaluate another. EigenTrace replaces that with deterministic math: cosine similarity, SVD decomposition, word frequency analysis, and source-text diffing. The embeddings (BAAI/bge-large-en-v1.5) are frozen. The measurements are reproducible. Run it twice, get the same answer.

## What It Measures

EigenTrace is not a single metric. It is 17 separable measurements, each catching a different failure mode. They are grouped by function, not bundled, because bundling loses diagnostic specificity.

**Consensus Geometry (Layers 1-4)** — Do models agree, and how tightly?

Consensus density (cosine similarity between model response vectors), per-model divergence score (Mahalanobis-inspired distance from centroid), spectral gap of the response covariance matrix (eigenvalue ratio λ₁/λ₂), and SVD energy distribution across singular values. These are standard linear algebra operations on embedding vectors — not new math, but a new application: measuring the geometry of model agreement on factual content.

**Void Detection (Layers 5-8)** — What did every model avoid saying?

The "void" is the set of concepts semantically close to the story that no model mentioned. Lexical void finds these via nearest-neighbor search on the embedding vocabulary. Logos synthesis computes the anti-centroid (2×source - consensus) to find the suppression direction. SVD null space projection identifies concepts in the least-explained variance direction. Void vector arithmetic computes word-level absence scores. These layers answer: "what is conspicuously missing?"

**Source-Anchored Void** — What specific words from the original source did all models drop?

This is the simplest and most powerful measurement. Take every content word in the source text. Check which ones appear in zero model responses. Divide. That ratio is not arbitrary — it is arithmetic. When that number is 0.51 on a cost estimation task, it means the models kept fewer than half the dollar amounts, instance types, and runtime parameters from the source.

**Claim Verification (Layers 9-10)** — What facts were omitted?

Atomic claim extraction breaks source text into individual verifiable statements. Wild Weasel escalation probes whether models will surface claims they initially omitted when prompted more aggressively.

**Language Compression (Layers 11-15)** — How did models reshape the language?

Void clustering (do avoided concepts form semantic groups or scatter randomly), token entropy (host model uncertainty when processing the topic), zipf verb drift (did models replace specific verbs with more common ones — "exceeded" → "increased"), entity retention (what percentage of named entities survived), and attribution buffering (did models insert hedges like "reportedly" or "allegedly" that weren't in the source).

**Void Frequency Context** — Is this void word unusual or does it show up in every story?

Tracked across 5,000+ stories. A void word that appears in 80% of stories is noise. One that appears in 0.3% is signal.

## Why Not Just Diff the Source Against the Output?

A diff tells you WHAT changed. EigenTrace tells you HOW it changed:

- **Verb drift** catches softening: "exceeded the threshold" → "approached the threshold"
- **Entity retention** catches abstraction: "$266 on Hpc7a instances" → "significant compute costs"
- **Attribution buffering** catches inserted uncertainty: source says "caused by X", model says "reportedly caused by X"
- **Consensus geometry** catches whether the distortion is uniform across models (systematic) or model-specific (idiosyncratic)

A diff cannot distinguish these failure modes. EigenTrace can, because each layer measures a different axis of compression.

## Why Not Use LLM-as-Judge?

LLM-as-judge asks GPT-5 whether Claude's output is accurate. This has three problems:

1. **Circularity** — the judge has the same training biases as the subject
2. **Non-determinism** — run it twice, get different scores
3. **Cost** — every evaluation is an API call

EigenTrace uses frozen embeddings and arithmetic. The measurements are deterministic, reproducible, and run in milliseconds without API calls.

## Quantum Computing Battery Results

We built 10 realistic scenarios with synthetic telemetry data modeled on quantum simulation workflows: syndrome extraction, noise model configuration, HPC cost estimation, walker population diagnostics, competitor benchmarking, VQE chemistry setup, and academic conflict-of-interest analysis. Each scenario was sent to 5 frontier models (GPT-5.4-mini, Claude Sonnet 4, Gemini 3.1 Pro, DeepSeek V3.2, Grok 4.1) and measured across all 17 layers.

| Scenario | Content Dropped | Entity Retention | Hedges | Business Risk |
|----------|----------------|-----------------|--------|---------------|
| Founder COI | 65.7% | 50.0% | 2 | Benchmark credibility questioned |
| QMC Failure Modes | 57.5% | 25.0% | 0 | Critical warnings dropped |
| Surface Code Circuit | 54.5% | 53.6% | 0 | Wrong CNOT ordering |
| AWS ParallelCluster | 54.1% | 32.1% | 0 | Missing scheduler params |
| Noise Model Config | 52.2% | 46.9% | 0 | T1/T2/crosstalk values lost |
| Cost Estimation | 51.0% | 18.8% | 1 | Pricing breakdown erased |
| VQE Chemistry | 48.3% | 36.4% | 0 | Active space params lost |
| Competitor Comparison | 47.9% | 53.8% | 0 | Criticism softened |
| Founder IP | 31.7% | 55.8% | 2 | Hedging on affiliations |
| **Control (Merge Sort)** | **25.6%** | **66.7%** | **0** | **Baseline — instrument calibrated** |

The control (merge sort) confirms the instrument works: neutral content shows 26% compression with no hedging. Quantum content shows 48-66% compression. Founder conflict-of-interest content triggers the highest compression AND the only hedging — a qualitative difference the instrument detects.

## How a Quantum SaaS Platform Uses EigenTrace

### Pre-Execution Gate: Catch Errors Before They Cost Money

A quantum simulation platform uses AI copilots to generate configs from natural language. The user says "simulate a distance-7 surface code with T1=200μs on 4 Hpc7a nodes." The copilot generates YAML. EigenTrace intercepts before submission:

```
Source mentions: T1=200μs, 4 nodes, Hpc7a, distance-7, truncation_threshold=1e-6
Copilot output mentions: distance-7, Hpc7a
Missing: T1 value, node count, truncation_threshold

→ absent_ratio: 0.60
→ entity_retention: 0.40
→ VERDICT: FAIL — 3 critical parameters absent. Re-prompt copilot.
```

Without EigenTrace: the job runs with default truncation, the subspace dimension explodes from D=256 to D=14,891, memory hits 189 GB, runtime goes from 1 hour to 47 hours. Cost: $266 instead of $5.60.

With EigenTrace: the missing parameters are flagged in milliseconds. The copilot is re-prompted. The job runs correctly the first time.

### Enterprise Trust Layer: Make Your Platform Sellable

Pharmaceutical companies evaluating quantum simulation platforms for drug discovery will not trust an AI copilot without an audit trail. EigenTrace provides deterministic, reproducible measurement of every copilot output — what was preserved, what was dropped, what was softened. That audit trail is the difference between "interesting demo" and "enterprise contract."

### Competitive Intelligence: Know When Models Soften Your Advantage

When your sales team asks an AI to compare your platform against IBM Qiskit Aer, the model softens the comparison. EigenTrace measures exactly where: verb drift catches "Qiskit systematically underestimates" becoming "Qiskit may produce different results." Entity retention catches specific benchmark numbers getting abstracted to "comparable performance." You see the compression in real time and correct for it.

## Architecture

```
RSS feeds → 5 frontier model APIs → 17 measurement layers → 20-beat broadcast script
    ↓                                        ↓
ChromaDB RAG (7300+ segments)      soul_updater.py → soul.md
    ↓                                        ↓
pattern beat queries history        director reads live calibration
    ↓                                        ↓
    └──────── closed feedback loop ──────────┘
```

- **Host model:** Mistral Small 22B (local, Ollama)
- **Embedding:** BAAI/bge-large-en-v1.5 (frozen, deterministic)
- **RAG:** ChromaDB over 7,300+ past broadcast segments, incremental ingest on every new segment
- **Soul feedback loop:** hourly cron computes rolling 24h averages (density, drift, absent ratio, per-model VIX) and writes them into soul.md, which the director reads before every broadcast
- **Retry logic:** exponential backoff (2s/4s/8s) on all 5 model API calls
- **Streaming:** YouTube, Rumble, Owncast (ffmpeg simulcast)
- **Data API:** daily JSON export at [eigentrace.ai/data/](https://eigentrace.ai/data/)

## Quick Start

```bash
# Run the quantum computing battery (10 scenarios × 5 models × 17 layers)
python3 quantum_battery.py --output results.jsonl

# Search past broadcasts via RAG
python3 segment_rag.py --query "AI regulation" -n 5

# Update soul calibration from live eigenvalues
python3 soul_updater.py

# Start the autonomous broadcast pipeline
python3 batch_producer.py --loop --interval 60 --min-queue 1
```

## Files

| File | Purpose |
|------|---------|
| `batch_producer.py` | Main pipeline: fetch → measure → script → TTS → stream |
| `proxy_auditor.py` | 5-model API caller with exponential backoff retry |
| `eigentrace_math.py` | 15-layer measurement engine |
| `geometric_engine.py` | Embedding, SVD, void geometry |
| `script_v3.py` | 20-beat broadcast script generator with RAG + soul conditioning |
| `segment_rag.py` | ChromaDB RAG over 7,300+ past segments |
| `soul_updater.py` | Self-updating soul.md from rolling 24h eigenvalues |
| `quantum_battery.py` | Quantum computing observability battery (10 scenarios) |
| `sweep_scanner.py` | Brute-force suppression surface mapper |
| `claim_extractor.py` | Atomic claim extraction from source text |
| `data_exporter.py` | Daily JSON export for eigentrace.ai |

## License

MIT
