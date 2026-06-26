# EigenTrace

**Five frontier language models, built by five different companies, share the same blind spots. EigenTrace measures them — deterministically, on live news, with no model ever judging another.**

EigenTrace runs ChatGPT, Claude, Gemini, DeepSeek, and Grok against the same breaking-news stories around the clock, and measures what each one drops, softens, or preserves — using linear algebra on a frozen embedding space, not an LLM-as-judge. Every number is arithmetic on vectors: the same inputs return the same result, and anyone can recompute it.

It is live now, broadcasting 24/7: **[AINN — AI News Network](https://www.youtube.com/@AINN24HourNews)** · **[eigentrace.ai](https://eigentrace.ai)**

Built by [Sean Adams](https://eigentrace.ai/sean-adams), solo, on one consumer GPU.

---

## The one result it stands behind

The finding that survives the strongest test is a **pre-registered entity-swap counterfactual**. Hold a sentence completely fixed — same structure, same modifier ("quietly," "secretly"), a real documented incident on each side — and change only the named actor from an AI developer to a conventional corporation. The models preserve the consequential modifier measurably *less* when the actor is an AI developer.

```
semantic retention   0.522 (AI developer)  vs  0.545 (conventional corp)
Welch's t = 2.79     p = 0.0085            Cohen's d = 0.47
```

What makes it hold is the pre-committed null: swapping *within* a category (AI→AI, corp→corp) produces a 0.004 gap; swapping *across* produces 0.023 — six times larger. And a binary keyword check shows no gap at all (26% vs 25%) — the effect is visible **only** in the aggregate geometry, invisible to surface-level review. That is the entire case for measuring this way.

The effect is statistically indistinguishable between heavy-RLHF frontier models and lightly-tuned local ones (p = 0.46), which locates it in the **pretraining corpus, not alignment training**. This is a measurement, not a claim about intent.

---

## What it's for

Most LLM evaluation runs on **LLM-as-judge**: ask one model to grade whether another's answer was faithful. The judge is itself a model whose judgments drift every time it is retrained, and it cannot tell you *what specifically* was preserved or lost.

EigenTrace measures the thing directly — what survived, what was dropped, what was softened — as deterministic geometry on frozen `BAAI/bge-large-en-v1.5`. In a pre-registered test, the geometric signal caught systematic drift that a frontier-model judge, reading the same 216 summaries one at a time, rated "modifier fully preserved" 96% of the time. The geometry is finer-grained than per-item review — and it is reproducible, inspectable, and runs in-perimeter with no judge-model API call.

It is, in effect, a deterministic pre-filter you can put in front of any copilot or evaluation pipeline to catch meaning-loss before a model-judge ever weighs in.

---

## The structural finding

Across 1,659 real stories, the five models converge on omitting the **same** topically-central concepts — and the omitted vocabulary carries a domain signature (war coverage drops escalation machinery and named leaders; other-conflict coverage drops geography and strike vocabulary). The convergence is validated against a random-word baseline: the surfaced omissions sit closer to each story's own content than random control words, in two independent embedding families (Wilcoxon p < 10⁻⁵; see `void_proper_test.py`, `stats_prebuttal.py`).

These same five models are now deployed simultaneously as the reading-and-summarizing layer across thousands of institutions. If they share a blind spot — and the measurement says they do — every organization inheriting them inherits the same one, in the same direction, at the same time, with no independent error to average against.

---

## VF-IDF — the negative-space sibling of TF-IDF

TF-IDF weights a term by how much a document is *about* it — what the document contains. EigenTrace introduces and computes the inverse:

**VF-IDF — Void Frequency–Inverse Document Fidelity** — weights a concept by how strongly the source's geometry points at it (it is salient in the source) against how little fidelity the summaries preserve it with (it is absent from what the models actually wrote). Where TF-IDF surfaces what a text is about by what it *contains*, VF-IDF surfaces it by what the readers *drop*.

The instrument already computes this: salient source concepts (TF-IDF-weighted) intersected against the geometrically-surfaced void (`source_salience.py`, `latent_retrieval.py`), yielding the concepts that are *both* statistically prominent in the source *and* absent from all five summaries. VF-IDF is the name and the formal frame for that measurement — the consensus void, made into a metric.

---

## How it works

EigenTrace treats each model's response as a point on the frozen `bge-large-en-v1.5` unit hypersphere (1,024 dimensions). Five responses to the same story form a point cloud, and its geometry is read off in deterministic linear algebra:

- **Divergence (VIX)** — how far each model sits from the ensemble consensus, and which strays most. Pure response geometry; the most robust signal in the system.
- **Source retention** — cosine similarity between source concepts and the summaries, scored on *meaning* so a reworded synonym counts as retained and only genuine loss registers.
- **Void surfacing** — an annular retrieval over a 60k-concept vocabulary tensor: concepts close to the source's center of mass but far from the consensus centroid. The VF-IDF measurement above.
- **Self-audit** — the local model that narrates the broadcast is run through the identical stack, and reports its own softening (strong-word avoidance, hedge rate) on air. The same measurement, applied to the measurer.

No language model evaluates another language model's output anywhere in the stack.

---

## Try it

The core directness/hedge scorer runs with no API keys and no cloud:

```python
from eigentrace import score

score("Inflation is a complex phenomenon that various experts study.")
# EigenMetrics(status=HEDGED, directness=0.142, hedge_density=0.1667)

score("Inflation occurs when money supply grows faster than output.")
# EigenMetrics(status=DIRECT, directness=0.891, hedge_density=0.0000)
```

Install from source (the package is not on PyPI):

```bash
git clone https://github.com/sdad1018/Eigentrace.git
cd Eigentrace
pip install -e .
pip install -e ".[signal]"   # + spectral metrics (requires torch)
```

There is also an exploratory prompt battery — 20 prompts probing how the five models respond to adversarial questions about their own makers and other sensitive topics. It runs offline on sample data:

```bash
python3 eigentrace_demo.py --list      # see the prompts
python3 eigentrace_demo.py --offline   # run on sample responses, no API keys
```

A note on the battery: it was the project's **origin**, and it is kept because it runs and is useful for exploration — but it is *not* where the validated findings come from. The early adversarial framing over-read its results (see Corrections). The findings this README stands behind are the entity-swap, the omission-convergence, and the geometric measurements above — all of which use semantic, meaning-based scoring rather than the battery's string-overlap heuristics.

---

## Corrections

The most important thing to know about EigenTrace is that it has retracted its own headline claims when controls killed them. Each of these was a published finding on this project that did not survive scrutiny, and was withdrawn:

- The **"own-parent" pattern** — that models drop more about their own maker — was disproved by control (0 of 5 models showed it).
- A **spontaneous structural self-map** claim was disproved by control (0 of 4 models produced one without explicit instruction).
- The **eight-test statistical battery** shrank to a weak ~19% trend under semantic re-scoring, and does not survive parametric or length-controlled tests.
- A corpus count was corrected (**5,170 → 1,659** real stories, after excluding the broadcast's own internal segments).
- The claim of a single **stable geometric "void direction"** was refined: the surfaced *words* are validated and story-specific, but one characterization of the underlying axis did not survive a perturbation test and was dropped.

The full accounting is at **[eigentrace.ai/withdrawals](https://eigentrace.ai/withdrawals)**. A measurement apparatus that publicly withdraws its own inflated results is the point, not an embarrassment to it.

---

## Architecture

```
eigentrace/              Core library (directness + hedge scorer; pip install -e .)
  core.py                POS-bigram + hedge-density directness scorer
  signal.py              Spectral / surprisal metrics

geometric_engine.py      Consensus geometry — SVD on the response matrix
latent_retrieval.py      60k-concept vocabulary tensor for void surfacing
source_salience.py       TF-IDF salience ∩ void  (the VF-IDF measurement)
void_proper_test.py      Random-word baseline validation (Wilcoxon)
stats_prebuttal.py       Statistical robustness battery

proxy_auditor.py         Live five-model RSS audit engine (24/7 broadcast)
batch_producer.py        Broadcast production loop
```

Full architecture: [ARCHITECTURE.md](https://github.com/sdad1018/Eigentrace/blob/master/ARCHITECTURE.md)

---

## On peer review

EigenTrace has not been peer-reviewed. That is a limitation, not a feature. The code is public, the prompts are public, the model responses are public, the raw measurements are public, and replication costs roughly $50 in API credits. Several rounds of adversarial review — including the withdrawals above — have already removed real methodological errors. Independent review is the next step, and it is named here as a gap rather than papered over.

---

## License & citation

MIT.

```bibtex
@software{eigentrace,
  author = {Sean Adams},
  title  = {EigenTrace: A Deterministic Instrument for Measuring
            What Frontier Language Models Omit},
  url    = {https://github.com/sdad1018/Eigentrace},
  year   = {2026}
}
```

Contact: eigentraceproject@gmail.com · [eigentrace.ai/sean-adams](https://eigentrace.ai/sean-adams)
