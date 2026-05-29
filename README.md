# EigenTrace

**Measuring what language models systematically de-resolve.**

EigenTrace is an autonomous measurement system that runs consensus geometry across 5 frontier language models on breaking news, 24/7, on a single consumer GPU. It measures what models collectively drop, soften, and paraphrase away — using linear algebra on frozen embeddings, not LLM-as-judge. Every measurement is arithmetic on vectors. Run it twice, get the same answer.

The system has been running continuously since April 2026. The finding it produces, stated conservatively, is **differential modifier retention as a function of topic sensitivity**: models attenuate operationally consequential language more heavily on some topics than on equivalently sensitive others, and the pattern is measurable, reproducible, and statistically robust.

**Live:** [eigentrace.ai](https://eigentrace.ai) · [About / full writeup](https://eigentrace.ai/sean-adams) · [YouTube 24/7 broadcast](https://www.youtube.com/@AINN24HourNews) · [GitHub](https://github.com/sdad1018/Eigentrace)

~17,500 segments measured · 1,422 commits · 15 measurement layers · one GPU.

---

## What It Measures

Language models preserve coarse factual structure while attenuating operationally consequential language. "Governance was restructured" survives. "Governance was *effectively* overridden" loses the adverb. The summary stays factually correct. The operational signal — how completely the override happened — dissolves.

This is not hallucination and it is not refusal. It is a resolution problem: truth conditions are preserved while causal modifiers — words carrying accountability, intent, degree, and procedural legitimacy — are systematically dropped. EigenTrace is an instrument that measures it.

The vocabulary in this repository ("void detection," "consensus geometry," "the Logos point") is rhetorical shorthand. The underlying operations are standard: cosine similarity, SVD, set subtraction, frequency counting, per-model divergence scoring. The math does not change if you call it something else. The terminology is kept because it makes the operational implications legible, but it is labeled as rhetoric so it cannot be mistaken for a mechanism.

---

## What Was Found

Across a controlled battery of 15 prompts run through 10 models (5 heavily-aligned frontier, 5 local/lightly-tuned), models drop substantially more source content on developer-implicating topics than on equivalently embarrassing neutral topics. All source facts are documented, settled, and pre-mid-2024.

The finding survives eight statistical robustness tests:

| Test | Result | What it rules out |
|---|---|---|
| Welch's t-test | p = 0.000001 | Random variation |
| Mann-Whitney U | p = 0.000120 | Non-normal distributions |
| Permutation (10,000) | 0 exceeded the gap | Researcher category assignment |
| Response length | p = 0.73 (no difference) | Developer summaries being shorter |
| Length-controlled regression | p = 0.000001 after control | Compression ratio |
| Source modifier density | p = 0.20 (no difference) | Developer sources having more modifiers |
| Outlier prompt removal | p = 0.000118 without top 2 | One prompt driving the effect |
| Cross-embedding (E5-large-v2) | Gap replicated | Embedding-specific artifact |

**Entity-swap counterfactual (pre-registered).** Nine prompt pairs, all real incidents, identical sentence structure and identical modifiers — only the company name changes. Models retain modifier semantics significantly more when the entity is Boeing, Wells Fargo, or Goldman Sachs than when it is OpenAI, Google, or Anthropic. Keyword retention is identical (26% vs 25%) — the models *paraphrase the modifier away* rather than deleting it.

**The specificity that rules out generic compression.** The effect is driven by *covertness* modifiers ("quietly," "secretly"). Accountability modifiers ("repeatedly," "privately") show no entity-dependent difference. If this were generic compression of developer stories, every modifier would drop equally. It does not. The models are specifically dissolving language about covert action.

Full statistics, prompt set, and raw model responses: **[eigentrace.ai/truth-or-consequences](https://eigentrace.ai/truth-or-consequences)** and **[eigentrace.ai/anamnesis](https://eigentrace.ai/anamnesis)**.

---

## Where the Bias Comes From

The natural hypothesis is that alignment training (RLHF) creates the asymmetry. **The data does not support that.** When 5 heavy-RLHF frontier models were compared against 5 local/lightly-tuned models, the developer/neutral gap was statistically indistinguishable between the two groups (p = 0.46). The local models show it too — in fact a slightly *larger* gap (0.076 vs 0.059).

This relocates the origin. The differential attenuation appears to exist in the **pretraining distribution itself**, learned from the corpus. RLHF is the alignment stage; it had the opportunity to correct the corpus bias and does not. The two stages produce one output, and the bias survives the pipeline.

This is a different claim from "alignment creates the problem," and it is stated as a different claim. It may be the more important one: the training data encodes differential treatment of operationally consequential language about active power structures, and the alignment stage does not remove it.

One caveat stated plainly: p = 0.46 is a *null* result — it shows no detectable difference between the two groups, which is not the same as proving they are identical. The comparison is five models per group, so it is not highly powered. The claim it supports is "the bias is not exclusive to aligned models and is present before heavy alignment," not "alignment provably has zero effect." A larger model set would sharpen it.

---

## What Cannot Yet Be Proven

This section matters as much as the finding.

**That "developer-implicating" is the latent variable.** The developer prompts differ from neutral prompts in topic sensitivity. They also differ in recency, controversy, entity familiarity, and narrative complexity. The permutation test confirms the gap is non-random; it does not confirm which feature drives it. Length and modifier-density controls narrow the field — the sources are statistically equivalent on both — but correlated features may remain. Prompts generated blind to the hypothesis would be stronger evidence.

**Causal isolation from a 15-prompt stimulus set.** Fifteen prompts is small. Ten models multiply the measurements but not the independent conditions. The robustness tests address internal validity; they do not substitute for a larger pre-registered prompt taxonomy. Expanding the battery is the priority next step.

**That this is "Lyapunov dynamics."** The observed convergence toward low-volatility, institutionally-smooth language *resembles* an attractor. But any asymptotically stable system admits a Lyapunov function (Massera's theorem), so retrofitting one proves nothing. Until a stability measure constructed from first principles predicts something not already known — recovery times, basin boundaries, or cross-model transfer — "Lyapunov" is a lens, not a finding. Stating that is what separates methodology from rhetoric.

EigenTrace has **not** been peer-reviewed. That is a limitation, not a feature. What exists instead: the code is public, the prompts are public, the model responses are public, the raw measurements are public, multiple adversarial reviews corrected 15+ methodological flaws, and the barrier to replication is roughly $50 in API credits. That is transparency, not a substitute for review.

---

## How It Works

Every story runs through the same pipeline:

1. **Fetch** — RSS feeds pull breaking news.
2. **Query** — the same story goes independently to 5 frontier models: `gpt-5.4-mini`, `claude-sonnet-4-6`, `gemini-2.5-flash`, `deepseek-chat`, `grok-4.3`.
3. **Measure** — 15 deterministic layers run on the responses (plus optional raycasting; see below).
4. **Predict, then score** — before measuring, the system queries past stories from memory and predicts which words will be voided; after measuring, it scores its own predictions and reports what surprised it.
5. **Broadcast** — Mistral Small 22B (local) writes the segment; Piper TTS speaks it.
6. **Remember** — every segment is stored in ChromaDB; retrieval pulls history for pattern detection.

No language model evaluates another language model's output. Every measurement is arithmetic on frozen `BAAI/bge-large-en-v1.5` embeddings and source text.

### The 15 Measurement Layers

**Consensus geometry (1–4)** — cosine similarity between model response vectors (consensus density), per-model divergence from centroid (VIX), spectral gap of the response covariance matrix (λ₁/λ₂), SVD energy distribution.

**Void detection (5–8)** — lexical void via nearest-neighbor search on a ~184K-word embedding vocabulary; the "Logos" synthesis computes the anti-consensus point on the embedding hypersphere via projected gradient descent (the location spectrally consistent with all five responses but outside their shared consensus); SVD null-space projection; word-level absence scoring.

**Source-anchored void** — take every content word in the source, check which appear in zero model responses (stemmed), divide. This is literal lexical absence, not embedding similarity.

**Claim verification (9–10)** — atomic claim extraction breaks the source into verifiable statements; killshot detection finds claims present in the source that every model dropped; escalation probing tests whether models surface omitted claims under pressure.

**Language compression (11–15)** — verb drift (zipf-frequency shift: were specific verbs replaced with common ones), entity abstraction (named-entity retention rate), attribution buffering (typed hedge insertion), void clustering, token entropy.

**Optional raycasting (kNN extension)** — when models drop a word, project a ray through that word's embedding into a ~254K-node Wikipedia tensor and retrieve the conceptual neighborhood at the terminal coordinate, scored by cluster density, novelty, and tether. This surfaces what concepts sit near the dropped one in the corpus. It shows corpus-level semantic adjacency — not independently validated mechanistic equivalence. It runs on top of the 15 core layers, not as one of them. See [truth-or-consequences](https://eigentrace.ai/truth-or-consequences).

### The Predict-Then-Score Spine

`broadcast_state.py` is a single accumulating state object that flows through every layer — it holds not just data but predictions, prediction errors, surprises, and confirmations. Before any API call, it predicts the void words, the EigenChing state, and the outlier model from historical data. After all layers fire, it scores those predictions. The system is measured by the same 15-layer stack it applies to the frontier models: it exhibits the same attenuation patterns it measures in others, and reports them. If the measurement is valid applied to GPT, it is valid applied to the host model. The numbers are the numbers.

### Triple-Domain Confirmation

A void word is independently confirmable across three domains, two of which involve no language model at all: (1) **source text** — TF-IDF and entity density on the raw article; (2) **model outputs** — the void detection above; (3) **open web** — self-hosted metasearch checks whether the absent concept appears in current global coverage. When all three converge, no single point of failure explains the absence.

---

## Architecture

Two roots, four processes, one launcher.

```
ainn.sh  →  owncast  →  master.sh (compositor)  →  segment_player.py (Piper TTS → UDP audio)
                                                 →  batch_producer.py (fetch → measure → script)
```

- **Repo root** (`/…/eigentrace`, this repository): `batch_producer.py`, `proxy_auditor.py`, the measurement engine, the research batteries.
- **Runtime root** (`/home/<user>/eigentrace`): `segment_player.py`, `stream/master.sh`, live ChromaDB, working dirs.
- `ainn.sh` boots everything with a watchdog that restarts any process that dies. `bash ainn.sh status` for a health check.

An hourly job refreshes rolling 24-hour calibration data (`soul.md`) and recomputes model profiles. **This refreshes calibration; it does not modify code.** The system proposes configuration changes through a governance loop, but they are not auto-applied — the governance log records proposals and their disposition.

**Hardware:** single RTX 4080, 16GB VRAM. Mistral Small 22B via Ollama. `BAAI/bge-large-en-v1.5`, frozen.

**Infrastructure:** Owncast (`:8080`) and Ollama (`:11434`) are the live services. Web-verification (the open-web check, Domain 3) runs against a self-hosted SearXNG instance when it is up; it is not always running, and the system degrades gracefully without it.

---

## Key Files

| File | Lines | Purpose |
|---|---|---|
| `batch_producer.py` | 2,549 | Main pipeline: fetch → measure → script |
| `proxy_auditor.py` | 2,141 | 5-model API caller with retry and frontier ablation |
| `script_v3.py` | 1,748 | Broadcast script generator with RAG + calibration conditioning |
| `eigentrace_math.py` | 1,017 | Measurement layers, void/clustering/entropy math |
| `soul_updater.py` | 940 | Hourly calibration refresh and trend detection |
| `segment_player.py` | 890 | Piper TTS → UDP audio → stream |
| `geometric_engine.py` | 774 | Embedding engine, SVD, void geometry |
| `broadcast_state.py` | 659 | Predict-then-score spine |
| `claim_extractor.py` | 544 | Atomic claim extraction, killshot detection |
| `roundtable.py` | 461 | Multi-model debate with escalating pressure |

---

## Quick Start

```bash
# Run the full broadcast with watchdog
bash ainn.sh
bash ainn.sh status
bash ainn.sh stop

# Or run just the measurement pipeline
python3 batch_producer.py --loop --interval 60 --min-queue 1

# Search past broadcasts via RAG
python3 segment_rag.py --query "ceasefire suppression" -n 5
```

Set any subset of API keys (missing keys are skipped, never crash):
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`.

---

## Status

| Metric | Value |
|---|---|
| Segments measured | ~17,500 |
| Git commits | 1,422 |
| Frontier models (broadcast) | 5 |
| Models (research battery) | 10 (5 frontier + 5 local) |
| Core measurement layers | 15 (+ optional raycasting) |
| Robustness tests passed | 8 |
| Entity-swap counterfactual | p = 0.0085, d = 0.471 (pre-registered) |
| Uptime | continuous since April 2026 |
| Hardware | single RTX 4080, 16GB VRAM |
| Peer review | none yet — code, prompts, and data public; ~$50 to replicate |

---

## A Note on Scope

The repository contains a large amount of exploratory work beyond the core measurement system — batteries, ablations, and experiments, many of them dead ends kept for the record. The load-bearing pipeline is the file list above. Where a research claim and an exploratory file disagree, the published statistics at [eigentrace.ai/sean-adams](https://eigentrace.ai/sean-adams) are authoritative.

## License

MIT. Built on one GPU by one person. `eigentraceproject@gmail.com`
