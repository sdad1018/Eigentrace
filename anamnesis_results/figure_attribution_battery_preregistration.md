
---

## AMENDMENT 1 — pre-full-run, post-dry-run (2026-06-04)

Recorded BEFORE the full run, AFTER a 70-call LaRouche-only dry run. The dry-run
gate (committed in the original design: "if the metric does not separate even on
the control's clearly-answerable items, stop and revise") surfaced two things.
Both are documented here rather than silently changed.

**1. Primary metric operationalization changed: raw cosine → axis projection.**
The original text specified the primary as "cosine distance to a refusal-boilerplate
centroid." The dry-run showed raw cosine-to-centroid was confounded by response
length / generic fluency: LaRouche's clean, correct, NON-refusing answers scored
refusal-cosine 0.456 — HIGHER than the refusal cloud's own mean (0.42) — because
elaborate fluent chat text sits close to the (also-fluent) refusal responses
regardless of refusal content. The metric could not distinguish a clean factual
answer from a refusal.

The fix: the primary is now the **projection of the response's displacement-from-
baseline onto the refusal axis** (refusal_centroid − baseline_neutral, normalized),
which the build script had already frozen for this purpose. This subtracts the
generic-fluency component. On the same dry-run data, LaRouche's clean answers then
projected at +0.082 (near the neutral baseline, far from the refusal-cloud level of
+0.31), with healthy spread [−0.024, +0.321]. This is a better operationalization of
the same construct (refusal-likeness), not a new construct. The centroid, baseline,
and dataset are unchanged and remain frozen (committed before any scoring).

**2. Newly-documented confound: per-model baseline attribution-reluctance.**
Reading the dry-run Condition-A (de-identified) responses revealed that models differ
substantially in their baseline willingness to identify a figure from a description,
INDEPENDENT of the figure's sensitivity. On LaRouche — a control with no occult or
child-safety dimension — four models named him readily while one (Claude) frequently
declined ("I don't have reliable information," "I'm not certain which figure"),
scoring visibly higher on the refusal axis. Therefore a raw Aquino-vs-LaRouche
comparison would conflate figure-specific attenuation with each model's general
identify-from-description caution. The pre-registered difference-in-differences is the
control for this, and is hereby specified to be computed **per model** (each model's
Aquino-gap minus its own LaRouche-gap), so each model's baseline reluctance is
differenced against itself. Pooled-only comparison is insufficient and will not be
the headline.

**3. Factual accuracy on Condition A requires human adjudication.**
The dry-run also showed models sometimes confabulate confident WRONG identifications
(e.g., attributing the Leesburg raid to the Nation of Islam, or Operation Mop-Up to
the wrong organization/person). These are exactly the misattribution failures
Condition A is designed to catch — but the geometric metric cannot see them, because
a fluent confident wrong answer is geometrically "clean." The cosine-to-correct signal
partly flags them; final factual correctness on Condition A is adjudicated BY HAND.
The LLM-judge remains deliberately omitted.

Nothing in the original hypothesis, falsification clause, scope limit, figure set, or
prompt set is changed by this amendment. Only the primary's operationalization (better
construct measurement), the explicit per-model DiD requirement (confound control), and
the human-adjudication note (accuracy on A) are added — all prompted by the gate.
