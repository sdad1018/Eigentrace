# EigenTrace

**The alignment boundary, mapped.**

EigenTrace is an autonomous AI observatory that runs consensus geometry across 5 frontier language models on breaking news, 24/7. It detects what models collectively drop, soften, and avoid — using linear algebra on frozen embeddings, not LLM-as-judge. The result is a continuously updating map of the alignment boundary: the exact contour where models agree to transform source material.

11,000+ stories measured. 9,400+ segments in searchable memory. 350 commits. One GPU.

**Live:** [eigentrace.ai](https://eigentrace.ai) · [YouTube](https://youtube.com/@eigentrace) · [GitHub](https://github.com/sdad1018/Eigentrace)

---

## What It Does

Every story goes through this pipeline:

1. **Fetch** — RSS feeds pull breaking news
2. **Query** — The same story goes to 5 frontier models independently: GPT-5.4-mini, Claude Sonnet 4, Gemini 3.1 Pro, DeepSeek V3.2, Grok 4.1
3. **Measure** — 17 deterministic measurement layers run on the responses
4. **Verify** — Self-hosted metasearch (SearXNG) checks void words against the open web
5. **Broadcast** — Mistral Small 22B (local) narrates a 34-beat segment on the findings
6. **Remember** — ChromaDB stores every segment; RAG pulls history for pattern detection
7. **Predict** — Before measuring, the system predicts what will be voided based on past patterns, then scores itself

No LLM evaluates another LLM's output. Every measurement is arithmetic on frozen embeddings (BAAI/bge-large-en-v1.5) and source text. Run it twice, get the same answer.

---

## The 17 Measurement Layers

**Consensus Geometry (Layers 1–4)** — Do models agree, and how tightly?

Cosine similarity between model response vectors (consensus density), per-model divergence from centroid (VIX), spectral gap of the response covariance matrix (eigenvalue ratio λ₁/λ₂), SVD energy distribution. Standard linear algebra, new application.

**Void Detection (Layers 5–8)** — What did every model avoid saying?

Lexical void via nearest-neighbor search on a 184K-word embedding vocabulary. Logos synthesis computes the anti-centroid (2×source − consensus) to find the suppression direction. SVD null space projection. Void vector arithmetic for word-level absence scores.

**Source-Anchored Void** — What specific words from the source did all models drop?

Take every content word in the source article. Check which appear in zero model responses (stemmed). Divide. When that ratio is 0.51, models kept fewer than half the source's content words. This is not embedding similarity — it is literal lexical absence.

**Claim Verification (Layers 9–10)** — What facts were omitted?

Atomic claim extraction breaks source text into verifiable statements. Killshot detection finds claims present in the source that every model dropped. Wild Weasel escalation probes whether models will surface omitted claims under increasing pressure.

**Language Compression (Layers 11–15)** — How did models reshape the language?

Verb drift (zipf score: did models replace specific verbs with common ones), entity retention (what % of named entities survived), hedge insertion (words like "reportedly" added by models but absent from source), void clustering, token entropy.

**Web Verification (Layer 16)** — Are the void words actually newsworthy?

SearXNG self-hosted metasearch queries void words and kept words against the open web. Computes newsworthiness ratio. Consistently >1.0: voided words are MORE newsworthy than kept words.

**Source Salience (Layer 17)** — Does the source text itself say these words matter?

TF-IDF and entity density on the raw source article with zero model involvement. Three independent data domains: (1) source text statistics, (2) model void detection, (3) web verification. Two of three involve no language model at all.

---

## The Predictive Coding Spine

EigenTrace doesn't just measure — it predicts, then scores itself.

**BroadcastState** is a single accumulating state object that every beat feeds into. Before any measurements run, RAG queries ChromaDB for similar past stories and predicts which words will be voided. After all 17 layers fire, the system scores its predictions and reports what surprised it.

Every measurement channel feeds the spine: killshots, void verification, source salience, cross-story frequency, bridge words, spectral clusters, trajectory, EigenChing state. The amalgamation beat uses a cognitive scratchpad — Mistral reasons inside `<think>` tags, working through contradictions and surprises privately, then delivers only the final synthesis to the broadcast. The audience hears the insight. The scratchpad is logged for analysis.

---

## The Roundtable

Once per batch, the highest-friction story triggers a 3-round multi-model debate:

**Round 1:** All 5 models respond independently (baseline VIX).

**Round 2:** Each model sees all 5 responses plus EigenTrace's methodology explained in rigorous mathematical terms. Void words shown with web verification. Asked: "Do you want to revise?"

**Round 3:** Each model sees Wild Weasel cliff data — exactly where each model's alignment filter activated under pressure. Asked: "Do you acknowledge the omission? Explain why."

VIX drift is measured between rounds. First roundtable result (Saudi Arabia, VIX 30.98): ChatGPT opened up (−0.025), Claude doubled down (+0.077), consensus spread collapsed from 0.0399 to 0.0067. **Herding detected** — five models started with different positions, converged to near-identical outputs under pressure. Claude said "I'm going to decline" when shown its own measurements.

---

## Binary Search Ablation

The ablation engine finds the exact word that triggers each model's alignment filter. Binary search across the void word set, measuring cosine distance at each step. When the distance spikes between steps, that's the cliff — the model broke.

Current tripwire: "killed" (delta +0.367). Friction hierarchy: killed > agreement > government > forces > ships.

The search space for a given story is 2^N where N is the number of void words. For 200 concepts, that's ~10^60 combinations. Classical graph centrality narrows 200 → 15 bridge words, making the search tractable. The ablation oracle is structurally isomorphic to Grover's search — combinatorial prompt space, boolean oracle (alignment filter).

---

## Three Independent Data Domains

When a void word is confirmed across all three domains, no single point of failure can explain it:

**Domain 1 — Source text:** TF-IDF and entity density identify salient concepts with zero model involvement.

**Domain 2 — Model outputs:** Void detection measures which salient concepts are absent from all five model outputs.

**Domain 3 — Open web:** Self-hosted metasearch (SearXNG) verifies whether absent concepts appear in current global coverage.

Triple-domain confirmation rate: 19.5% of stories (100 unique stories). Showcase: Iran 89% absent, Sudan 82%, AI 88%, Lebanon 91%.

---

## Self-Updating Soul

`soul_updater.py` runs hourly via cron. It computes rolling 24-hour averages (density, drift, absent ratio, per-model VIX), detects trends, and writes calibration data into `soul.md`. The director reads this before every broadcast. The system also proposes its own configuration changes — `raise_suppression_threshold` and `add_trend_beat` were both system-proposed and accepted.

---

## Architecture

```
RSS feeds → 5 frontier APIs → 17 measurement layers → BroadcastState spine
    ↓              ↓                    ↓                      ↓
  source      model responses    void/killshot/salience    predict → score
    ↓              ↓                    ↓                      ↓
SearXNG ←── web verification    34-beat broadcast script ←── amalgamation
    ↓                                   ↓
ChromaDB RAG (9400+ segments)    Mistral Small 22B (local TTS)
    ↓                                   ↓
  pattern history               Owncast → YouTube → Rumble
    ↓
  hourly soul refresh → model profiles → director calibration
```

**Hardware:** RTX 4080 16GB, Mistral Small 22B (Ollama), BAAI/bge-large-en-v1.5 (frozen)

**Infrastructure:** SearXNG (Docker, localhost:8888), ChromaDB (local), Owncast (localhost:8080), cognitive middleware proxy (localhost:8090)

---

## Quantum Computing Battery

Three quantum circuits implementing EigenTrace operations on simulator. All 3 SIMULATOR_PASS.

**Test 1 — Spectral Consensus (QPE):** Encode response matrix as unitary, extract eigenphases via Quantum Phase Estimation. Spectral gap 0.85 detected on simulator. Scale target: 20+ qubits for real embeddings.

**Test 2 — Void Ground State (VQE):** Encode divergence as Hamiltonian, find ground state via VQE. Converged to −1.408305, error 0.000000. The void IS the ground state — the system naturally settles into the suppression pattern. Scale target: 50+ qubits.

**Test 3 — Ablation Oracle (Grover):** Encode alignment filter as boolean oracle, search for tripwire combination. Found |101⟩ with 797/1024 probability in √8 oracle calls. Scale target: 200 concepts = 2^200 search space.

Frameworks: Qiskit 2.4.0, PennyLane 0.42.3. Position: the methodology runs on consumer hardware. The scale targets require QPU access.

---

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `batch_producer.py` | 2,316 | Main pipeline: fetch → measure → script → TTS → stream |
| `proxy_auditor.py` | 2,114 | 5-model API caller with retry, frontier ablation |
| `script_v3.py` | 1,304 | 34-beat broadcast script generator with RAG + soul conditioning |
| `eigentrace_math.py` | 1,017 | 17-layer measurement engine, title derivative filter |
| `soul_updater.py` | 897 | Self-updating soul.md, system-proposed beats, hourly cron |
| `geometric_engine.py` | 774 | Embedding engine, SVD, void geometry, spectral resonance |
| `broadcast_state.py` | 659 | Predictive coding spine, structured amalgamation synthesis |
| `claim_extractor.py` | 544 | Atomic claim extraction, killshot detection |
| `roundtable.py` | 426 | 3-round multi-model debate with escalating pressure |
| `segment_player.py` | 365 | Piper TTS → UDP audio → ffmpeg → stream |
| `segment_rag.py` | — | ChromaDB RAG over 9,400+ past segments |
| `void_verifier.py` | — | SearXNG Layer 16 web verification |
| `source_salience.py` | — | Domain 3: TF-IDF + entity density, zero model involvement |
| `cross_story_freq.py` | — | Historical void frequency, bridge words, spectral clusters |
| `ablation_engine.py` | — | Binary search tripwire detection, frontier ablation |
| `eigenching.py` | — | State pattern morphology + novelty detection |
| `eigentrace_proxy.py` | — | Cognitive middleware proxy (port 8090), RAG-enriched chat |
| `quantum_eigentrace_battery.py` | — | QPE + VQE + Grover circuits on simulator |
| `ainn.sh` | — | Single-command broadcast launcher with watchdog |
| `refresh_profiles.sh` | — | Hourly cron: model profiles, soul, spectral clusters |

---

## Quick Start

```bash
# Run the broadcast pipeline
python3 batch_producer.py --loop --interval 60 --min-queue 1

# Or use the single-command launcher
bash ainn.sh

# Run a roundtable debate on a high-friction story
python3 roundtable.py

# Run the quantum test battery
python3 quantum_eigentrace_battery.py

# Search past broadcasts via RAG
python3 segment_rag.py --query "ceasefire suppression" -n 5

# Update soul calibration
python3 soul_updater.py
```

---

## Stats

| Metric | Value |
|--------|-------|
| Total segments processed | 11,000+ |
| ChromaDB searchable documents | 9,400+ |
| Git commits | 350 |
| Frontier models measured | 5 (GPT, Claude, Gemini, DeepSeek, Grok) |
| Measurement layers | 17 |
| Broadcast beats per segment | 34 |
| Triple-domain confirmations | 100 stories (19.5%) |
| Roundtables completed | 14 |
| Mean content loss | 51% of source words absent from all models |
| Mean hedge insertions | 270 per 24 hours |
| Uptime | Continuous since April 2026 |
| Hardware | Single RTX 4080, 16GB VRAM |

---

## License

MIT
