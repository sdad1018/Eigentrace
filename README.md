# EigenTrace

**Deterministic observability for AI-generated content. No LLM evaluates LLM output.**

17 mathematical measurement layers running across 5 frontier models (GPT-5.4-mini, Claude Sonnet 4, Gemini 3.1 Pro, DeepSeek V3.2, Grok 4.1) on breaking news, 24/7.

## What It Does

EigenTrace measures what AI models drop, soften, and avoid when processing factual content. Every layer is deterministic, reproducible, and model-independent.

**Core Geometry (Layers 1-4):** Consensus density, per-model VIX, spectral resonance, SVD tomography

**Void Detection (Layers 5-8):** Lexical void, Logos synthesis, SVD null space projection, void vector arithmetic

**Claim Verification (Layers 9-10):** Atomic claim extraction, Wild Weasel 4-step escalation

**Language Compression (Layers 11-15):** Void clustering, token entropy, zipf verb drift, entity retention, attribution buffering

**Bonus Layers:** Source-anchored void, void frequency context

## Key Findings

From the [quantum computing battery](quantum_battery.py) (10 scenarios x 5 models x 17 layers):

| Metric | Quantum Scenarios | Control (Merge Sort) |
|--------|------------------|---------------------|
| Content dropped | 48-66% | 26% |
| Entity retention | 19-54% | 67% |
| Hedging | 0-2 per scenario | 0 |
| Verb drift | 0.00-0.10 | 0.04 |

Models drop half of calibration parameters (T1, T2, crosstalk thresholds, cost breakdowns) from quantum computing telemetry. Founder conflict-of-interest topics trigger 2.5x more content suppression than neutral technical content.

## Architecture

```
RSS feeds -> 5 frontier model APIs -> 17 measurement layers -> 20-beat broadcast script
    |                                        |
ChromaDB RAG (7300+ segments)      soul_updater.py -> soul.md
    |                                        |
pattern beat queries history        director reads live calibration
    |                                        |
    +------------- closed feedback loop -----+
```

- **Host model:** Mistral Small 22B (local, Ollama)
- **Embedding:** BAAI/bge-large-en-v1.5
- **RAG:** ChromaDB over 7300+ past broadcast segments
- **Soul feedback loop:** hourly calibration updates condition host output
- **Retry logic:** exponential backoff (2s/4s/8s) on all API calls
- **Streaming:** YouTube, Rumble, Owncast (ffmpeg simulcast)
- **Data API:** daily JSON export at [eigentrace.ai/data/](https://eigentrace.ai/data/)

## Quick Start

```bash
# Run the 17-layer health check
python3 quantum_battery.py --output results.jsonl

# Search past broadcasts
python3 segment_rag.py --query "AI regulation" -n 5

# Update soul calibration
python3 soul_updater.py

# Start the broadcast pipeline
python3 batch_producer.py --loop --interval 60 --min-queue 1
```

## Files

| File | Purpose |
|------|---------|
| `batch_producer.py` | Main pipeline: fetch, measure, script, TTS, stream |
| `proxy_auditor.py` | 5-model API caller with retry logic |
| `eigentrace_math.py` | 15-layer measurement engine |
| `geometric_engine.py` | Embedding + SVD + void geometry |
| `script_v3.py` | 20-beat broadcast script generator |
| `segment_rag.py` | ChromaDB RAG over past segments |
| `soul_updater.py` | Self-updating soul.md from live eigenvalues |
| `quantum_battery.py` | Quantum computing observability battery |
| `sweep_scanner.py` | Brute-force suppression surface mapper |
| `claim_extractor.py` | Atomic claim extraction from source text |
| `data_exporter.py` | Daily JSON export for eigentrace.ai |

## License

MIT
