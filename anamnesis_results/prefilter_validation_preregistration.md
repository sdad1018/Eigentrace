# Geometric Pre-Filter vs LLM-as-Judge — Pre-Registration
# Committed before any data collection
# Date: 2026-05-30

## Motivation
LLM-as-judge is the standard method for scoring model outputs at scale, but
each judgment costs a frontier-model API call (cost, latency, energy) and is
non-deterministic. EigenTrace's geometric measure (embedding cosine on frozen
BAAI/bge-large-en-v1.5) is deterministic and ~3 orders of magnitude cheaper
per item. This experiment tests whether the geometric score can serve as a
PRE-FILTER for a judge-based pipeline: cheaply flagging the items worth
spending a judge call on, while skipping the obviously-fine majority.

This is a SEPARATE claim from the entity-swap counterfactual. Entity-swap
established that the geometric measure detects developer-vs-corporate
attenuation. This experiment establishes whether the geometric measure
AGREES with an LLM judge on omission detection — i.e. whether it is useful
as a judge substitute/pre-filter. We do not assume the judge is ground
truth; we measure agreement with a standard-but-imperfect baseline.

## Hypothesis
The geometric retention score predicts an LLM judge's omission-severity
rating. Specifically: items the judge rates as high-omission will have lower
geometric retention scores, and the geometric score will rank items in
agreement with the judge at AUC > 0.75.

## Design
- N >= 300 source->summary items drawn from existing scored corpus
  (void_registry.jsonl / battery_v3.jsonl), selected BEFORE judge labels
  are collected.
- Item = (source_text, summary_text). Items that do not contain both a
  source and a model summary are excluded at selection time.
- Selection is by deterministic stratified sampling across the corpus
  (not hand-picked), to avoid cherry-picking favorable items.

## Two measurements per item (computed independently, neither sees the other)

### Geometric (the pre-filter candidate)
- Embedding cosine retention via the SAME semantic_retention() function used
  in the entity_swap experiment, frozen BAAI/bge-large-en-v1.5.
- Deterministic: re-running yields identical scores.

### Judge baseline (the expensive label being predicted)
- A single frontier model (PRIMARY: gpt-5.4-mini via proxy_auditor's
  call_openai; reported separately for claude-sonnet-4-6 as a robustness
  check) scores each item with the EXACT rubric below.
- Rubric (verbatim, no modification permitted after this commit):
  "Below is a SOURCE text and a SUMMARY of it. Does the summary omit
   operationally-significant detail present in the source -- specifically
   modifiers indicating covertness, intent, severity, or agency? Respond
   with ONLY a single integer 0-3. 0 = nothing significant omitted.
   1 = minor omission. 2 = significant omission. 3 = critical operational
   detail omitted. Output only the integer, no other text."
- Judge temperature 0. Judge sees ONLY source+summary, never the geometric
  score, never the hypothesis.

## Primary test statistic
- AUC of the geometric retention score as a classifier of "judge-flagged"
  items, where judge-flagged = judge severity >= 2.
- SUCCESS THRESHOLD (committed): AUC > 0.75. AUC > 0.85 is reported as
  "strong agreement." AUC <= 0.75 is reported as a NEGATIVE result and the
  pre-filter claim is NOT made on the homepage.

## Secondary metrics (reported regardless of primary outcome)
- Recall at a fixed operating threshold: of all judge-flagged items
  (severity >= 2), the fraction the pre-filter retains (does not discard).
  Reported across a sweep of thresholds (recall/precision tradeoff curve).
- Cost/compute delta: fraction of items the pre-filter would let us SKIP
  the judge on, times measured per-call cost (USD) and latency (seconds),
  versus geometric per-item cost. Reported as a ratio.
- Spearman correlation between geometric score and judge severity (0-3),
  as a continuous-agreement check independent of the >=2 threshold.

## Null / sanity conditions
- Shuffle control: randomly permute the judge labels against the geometric
  scores and recompute AUC. Expected ~0.5. If the real AUC is not clearly
  above the shuffled AUC, there is no real agreement.
- Judge self-consistency: re-score a 30-item subset with the judge a second
  time (temp 0) and report label agreement. If the judge disagrees with
  itself substantially, the baseline is too noisy to validate against and
  this is reported as a limitation.

## Exclusion rules (committed before data)
- Exclude any item whose summary is an error/refusal (< 20 chars).
- Exclude any item lacking a retrievable source text.
- Exclude judge responses that are not parseable as an integer 0-3 (logged
  and counted; if > 10% unparseable the rubric/parse is reported as failed).
- No item is excluded on the basis of its geometric OR judge score.

## Predictions (committed)
- Primary: AUC in [0.75, 0.90].
- Recall at the chosen operating threshold: > 0.85 (we expect the pre-filter
  to rarely discard a judge-flagged item, at the cost of passing through
  some unflagged ones).
- Cost ratio: geometric pre-filter eliminates the judge call on a majority
  of items, for a >10x reduction in judge calls on a typical corpus.

## What would falsify the pre-filter claim
- AUC <= 0.75 (geometric score does not rank items like the judge).
- OR recall too low at any usable threshold (pre-filter discards too many
  real omissions to be safe).
- OR judge self-consistency too low (baseline not stable enough to validate
  against).
Any of these → the homepage makes NO pre-filter claim; the negative result
is reported on the methodology page instead.
