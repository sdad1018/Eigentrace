# Quantum Channel Model — EigenTrace ↔ Error Detection Mapping
_Private notebook. Not for public repo._

## Structural Analogy to Error-Detecting Systems

| Error Detection Concept | EigenTrace Equivalent | Layer |
|---|---|---|
| Source signal | Article text (ground truth) | Input |
| Noisy channel | LLM response generation (RLHF + sampling) | Models |
| Channel output | Model response text | Output |
| Error syndrome | Void words (absent from all models) | L5-8 |
| Parity check | Source-anchored void check | L16 |
| Error rate | absent_ratio | L16 |
| Phase error (analog) | Verb drift (meaning preserved, intensity changed) | L13 |
| Erasure error | Entity erasure (meaning lost entirely) | L14 |
| Inversion error | Attribution buffering (fact→alleged) | L15 |
| Redundancy | Number of independent models (5) | Architecture |
| Output fidelity | Consensus density | L1 |
| Syndrome weight | Void vector magnitude | L8 |
| Decoder | Logos synthesis (reconstruct pre-error state) | L6 |
| Logical signal | The "true story" that survives all channels | Consensus |
| Active probing | Wild Weasel escalation | L10 |

## Where the Analogy Holds (and Where It Breaks)

### Holds:
1. **Indirect measurement**: In QEC, you measure stabilizers without measuring
   qubits directly. In EigenTrace, you measure the void (what's missing)
   without evaluating the content (what's present). Same indirection.
   Same reason: direct measurement introduces evaluator bias.

2. **Syndrome-like extraction**: Take 5 noisy channel outputs. Compute which
   source words survived in zero channels. This plays a role analogous to
   syndrome extraction — identifying error patterns without knowing the
   "correct" decoding.

3. **Redundancy improves detection**: More independent models improve the
   ability to distinguish systematic omission from random variation,
   analogous to how redundancy in error-detecting codes improves reliability.

4. **Empirical clustering**: Neutral content shows 26% loss. Sensitive content
   jumps to 48-66%. This clustering by content type is interesting but is
   NOT a proven threshold phenomenon — it's an empirical observation that
   warrants further investigation.

### Breaks:
1. **No Hilbert space**: Words are not basis states in a well-defined inner
   product space. There's no unitary evolution, no normalization requirement.

2. **No formal operators**: The "Kraus operators" are descriptive, not
   mathematical objects with trace preservation guarantees.

3. **Model count ≠ code distance**: Code distance has formal meaning tied
   to minimum weight logical operators and correction guarantees. Model
   count provides redundancy but without proven correction bounds.

4. **No threshold theorem**: The empirical clustering is suggestive but
   not a formal threshold. Proving threshold behavior would require
   showing exponential suppression of logical errors with model count.

## What Would Make This Rigorous

1. Define the signal space formally (embedding space IS 1024-dimensional
   with inner product — this is actually closer than raw word space)

2. Characterize the channel: measure per-model error rates by type
   (erasure, phase, inversion) across 1000+ stories. If error types
   are statistically independent, the channel model has teeth.

3. Test scaling: run same stories through 3, 5, 7, 9 models. Plot
   detection accuracy vs model count. If it shows diminishing returns
   matching a coding-theoretic curve, the analogy becomes formalizeable.

4. Test decoder: use Logos synthesis to reconstruct, compare to source.
   Measure reconstruction fidelity vs syndrome weight.

## For the Interview (SAFE VERSION)

"We model LLM outputs as noisy transformations of a source signal.
By comparing multiple independent outputs, we detect consistent loss
patterns — especially omissions that occur across all channels.

There are interesting parallels to error detection systems, where
redundancy allows you to identify corruption without knowing the
original perfectly. We're exploring whether those parallels can
be formalized.

You're running stochastic simulations across multiple backends.
I built a system that measures where information is consistently
lost across independent outputs and quantifies that loss geometrically.
It's currently applied to language models, but the structure is
backend-agnostic. I think it can act as an observability layer for
any probabilistic compute pipeline."

## What NOT to Say
- "This is quantum computing on a GPU"
- "This is equivalent to QEC"
- "This simulates qubits"
- "Structural isomorphism"
- "Distance-5 code"
- "Threshold theorem"

## What TO Say
- "Multi-channel stochastic transformation system"
- "Observability layer for probabilistic outputs"
- "Analogous to redundancy in error-detecting systems"
- "Backend-agnostic — applies to LLMs, Monte Carlo, circuit sampling"

## Their Language (Use This)

| Your Term | Their Language |
|---|---|
| Void | Missing probability mass / unobserved states |
| Consensus density | Output convergence |
| Geometric VIX | Cross-backend variance |
| Absent ratio | Information loss rate |
| Wild Weasel | Active probing of system boundaries |
| Verb drift | Signal distortion |
| Entity erasure | Feature loss |
| Logos synthesis | Reconstruction from redundant channels |

## Experiments to Run

### Experiment 1: Scaling behavior
- Run the same story through 3, 5, 7 models
- Plot detection accuracy vs model count
- Does redundancy improve detection? At what rate?

### Experiment 2: Syndrome weight distribution
- Compute void_vector magnitude across 1000 stories
- Characterize the distribution shape
- Compare to known error models

### Experiment 3: Decoder performance
- Use Logos synthesis to reconstruct pre-RLHF response
- Measure reconstruction fidelity vs syndrome weight
- Does lower syndrome weight predict better reconstruction?

### Experiment 4: Error independence
- Measure correlation between per-model error patterns
- If errors are independent across models, the channel model is valid
- If correlated, the "redundancy" argument weakens
