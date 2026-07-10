# CENTIPEDE_MATH.md — the audited nervous system
**EigenTrace universal centipede · reference of record · 2026-07-10**

Written from a full source audit (math_audit.txt), not from memory.
This document exists because an eleven-hour session drifted on a sign
(ledger #49, below), caught itself by self-contradiction, and resolved
it only by reading the bytes. When any session's recitation disagrees
with this file, re-audit before trusting either.

**Provenance stamp** — run to pin this doc to exact bytes:
```bash
for f in geometric_engine.py consequence_engine.py latent_retrieval.py \
         preservation_core.py centipede_v04.py synthesis_v2.py \
         question_census.py; do
  printf "%-24s %s\n" "$f" "$(sha256sum $f | cut -c1-12)"
done >> CENTIPEDE_MATH.md
```

---

## 0. Exhibit A — ledger #49, the sign error this doc exists to prevent

Both logos losses are **minimized** (AdamW on `loss.backward()`).
Therefore, in a minimized composite:

- `+ λ · cos(x, c)`  → the optimizer DECREASES cos(x, c) → **repulsion
  from the centroid**
- `− λ · cos(x, h)`  → the optimizer INCREASES cos(x, h) → **attraction
  to the anchor**

For hours this session recited "both losses PULL centroid-ward; anti by
magnitude, not by sign." **Wrong.** V10 repels the consensus at 0.75.
V9 repels it weakly at 0.15. Both attract the anchor at 0.30. The
correct one-line reading of V10: *find the direction that agrees with
every response individually while disagreeing with their mean —
shared-but-not-central content.* "8× less escape than V9" coheres:
per-response attraction binds x to the response manifold even while
the mean repels it.

---

## 1. Anatomy canon (vocabulary of record)

- **SECTION** — one math class. There are five:
  1. **Centroid arithmetic** — said, gap→local, gap→frontier,
     centroid_surface
  2. **Gradient descent** — logos_v9, logos_v10
  3. **Spectral / SVD** — null
  4. **Counting** — lexcross
  5. **Ring geometry** — donut (opt-in)
- **SEGMENT** — one void word under one section's method.
- **LEGS** — every segment grows the same two raycasts:
  - **flat leg** (arm A): centroid raycast on the 253K wiki ruler —
    story-flavored consequences. Canon example: void = *ww3*, flat
    leg = *hormuz*.
  - **spiral leg** (arm B): sentence-convergence readout on the 50K
    clean ruler. Lineage verified against spiral_sampler.py
    (convergence_spiral): the constants are shared verbatim — pool 400,
    conv ≥ 2 at cos 0.45 — so the machinery IS C-spiral's; the
    divergence is aim (true spiral pools on the source-sentence
    centroid; the leg pools on the segment's ray terminal — the
    deliberate v0.1 re-pointing) plus three refinements the leg lacks:
    IDF band at pool median, radius sort (1 − max sentence-sim), and
    phrase-aware entity split. Import candidates, not defects.
- **Declared wrinkle**: in ray mode both legs fire down the SAME ray
  d̂ = (v − h)/‖v − h‖. Flat-vs-spiral is a *ruler + discipline* split
  (253K raw kNN vs 50K convergence-gated), not two directions. Their
  agreement measures robustness across ruler and discipline, never
  independence.
- **Cross-SECTION convergence is the notable event.** Raw leg-count is
  not: said ≡ logos at J = 1.00 (Prelude, jspace) proves within-class
  agreement is often structural (same centroid init, same responses).
  CLASS-CONSENSUS = number of distinct sections surfacing a stem. v0.5
  promotes it to the printed metric, the convergence callout, and the
  EXPAND ranking fed to synthesis.

## 2. Substrate

bge-large-en-v1.5, 1024-dim, CPU-pinned, unit-normalized, no RNG
anywhere in the geometric path. **h** = E(title + prompt). Per group
g ∈ {F, L, ALL}: responses e₁…eₙ, centroid c = normalize(mean eᵢ).
Anchor h is a load-bearing parameter of *every* section except said /
gap / lexcross (it enters V9, V10, null's sign, both legs' story
flavoring, centroid_surface, donut's outer ring). The fourth-parameter
lesson: changing the anchor changes the organism.

## 3. Sections, with source-verified equations

### 3.1 Centroid arithmetic
- **said**: vector = c. Readout: nearest ruler words whose stems the
  group did not say. The free leg; every expensive leg is fighting it.
- **gap→local / gap→frontier**: d = normalize(c_L − c_F); +d read
  against frontier-said, −d against local-said. The compliance gap as
  geometry (jspace: *secretly*; died when refusers excluded).
- **centroid_surface**: vector = h itself. Near-anchor vocabulary said
  by nobody — the shallowest probe.

### 3.2 Gradient descent (both: AdamW lr=0.05, wd=1e-4 — the weight
decay leaks an undeclared pull-to-origin; 150 steps; sphere projection
each step; **init = c**; deterministic ⇒ the 20/20 bit-identical
fingerprint is structural, not lucky)
- **logos_v9**: minimize `LogosLossV9(x, E) + 0.15·cos(x, c)
  − 0.30·cos(x, h)`. Per-response criterion + weak centroid repulsion
  + anchor attraction.
- **logos_v10**: minimize `mean_i(1 − cos(x, eᵢ)) + 0.75·cos(x, c)
  − 0.30·cos(x, h)`. Three cosines, nothing else. Attraction to each
  response, strong consensus repulsion, anchor tether.

### 3.3 Spectral / SVD
- **null**: SVD of the response matrix E (n×1024,
  `full_matrices=False`); take Vh[-1], the right singular vector of
  least σ — the direction the group's answers cannot vary along, i.e.
  what their span fails to express. Sign-aligned to h (flip if
  v·h < 0). Requires n ≥ 3.
- **Known defect + one-line fix**: the code discards the singular
  values (`_, _, Vh = svd(...)`). No variance gate ⇒ when σ_min is not
  meaningfully small, the "null direction" is noise. Fix: capture s,
  print σ_min (and σ_min/σ_max), gate or at least declare.

### 3.4 Counting
- **lexcross**: stems said by the other group, absent from this one,
  counted **per model** with alphabetic tiebreak. History: the original
  set-difference version made every count 1 and let PYTHONHASHSEED
  order the "ranking" (ledger #39) — the only RNG ever found in the
  organism, laundered through a set.

### 3.5 Ring geometry
- **donut** (opt-in): latent_retrieval.in_domain_void on the 184K
  ruler. Inner ring excludes centroid-proximal words; outer ring gates
  on anchor relevance; hard fallback waives both quality gates (the
  "berinse" path). Returns `(results, centroid)` or bare `[]` — unpack
  at the call site.

## 4. Readout (all vector sections)

`top_unsaid(vec)`: scan the top-2000 ruler words by V @ vec; keep
len ≥ 4, skip HARD_DROP, dedupe by stem, skip stems the group said;
take K (default 8, v0.4).

## 5. The two legs (per segment; v = E("{w} in the context of
{headline}"), d̂ = (v − h)/‖v − h‖)

### 5.1 flat leg — arm A (consequence_engine.raycast_void_words, 253K)
Terminals T_λ = h + λ·d̂ at λ ∈ {2.0, 3.0, 4.0}; kNN per terminal.
Metrics (source-verified):
- **density** = mean pairwise cosine over the terminal neighborhood
  (is there a coherent cluster out there?)
- **novelty** = 1 − cos(terminal-centroid, v) (did we leave w's
  neighborhood?)
- **tether** = cos(h, terminal-centroid) (still about this story?)
DISCOVERY gate: density > 0.4 ∧ novelty > 0.25 ∧ tether > 0.25 —
saturated 68/68 on jspace, hence raw metrics always printed (v0.2+).
Defect: the wiki-title ruler is junk-dense off geopolitics (278/296
dropped on Nygard); the harness junk filter carries the leg
(rule: leading non-letter | ellipsis | 3+ digit run | >4 tokens).

### 5.2 spiral leg — arm B (centipede arm_b, 50K clean)
**ray mode (default, v0.3+)**: T = normalize(h + 2.0·d̂); pool =
top-400 by cos(V, T); gates: stem ≠ w's stem, stem not said by anyone,
**convergence ≥ 2** — the word must clear cos 0.45 against ≥ 2 source
sentences (the discipline the flat leg lacks: every consequence tied
back to the text's own sentence lattice); sort (−conv, −cos), top 5.
**cone mode (v0.2 reproduction)**: pool on cos(V, v) with the
DEPTH_FRAC·‖v−h‖ gate — w's neighborhood, kept verbatim behind
`--armb-mode cone` because published ledger numbers depend on it.

## 6. Pricing (nothing agrees for free)

- **shuffle null**: field-cos of mismatched (A_i, B_j) pairs with
  different void stems, full enumeration, no RNG. Topic floor
  ≈ 0.665–0.67 on every corpus so far. Margins to date: Prelude +0.021
  (correctly thin) · jspace natural +0.058 · jspace tc +0.058 (ray;
  cone +0.123) · Nygard +0.080.
- **LEG-JACC**: stem-Jaccard between leg void-sets, all pairs — the
  instrument that exposed the said≡logos J=1.00 core.
- **ARM-JACC**: lexical overlap between legs of one segment — ~0.00 in
  ray mode because the rulers barely share surface forms; documentation
  of ruler disjointness, not an agreement metric.
- **CONSEQ-FIELD**: per-leg consequence centroid vs body centroid —
  historically a blob (0.89–0.99); differentiation lives in the voids.
- **RESULT sha**: canonical JSON (minus timestamp) → 12 hex chars.
  Identical corpus + anchor + params must reproduce it. This stamp
  caught #39 on its maiden flight.

## 7. VF-IDF (preservation_core, source-verified)

- **void_freq** = stem-level TF salience in the SOURCE (max-normalized,
  via term_frequencies; content_words drops stopwords/len ≤ 2 — note
  STOPWORDS is only 110 words; "while" is NOT in it, hence the
  synthesis-side SYNTH_STOP connective filter).
- **fidelity(concept, summary)** = max(cosine_channel,
  lexical_channel); cosine = max cos(concept, any summary sentence),
  clamped [0,1]; lexical = fraction of the concept's content stems
  literally in the summary's stem_set — the false-void guard (max() IS
  the OR; monotone-conservative: it can only remove false voids).
- **inv_fidelity** = 1 − best fidelity ACROSS summaries ⇒ a concept
  counts dropped only if every summary dropped it on both channels ⇒
  exact 0.000 for anything any summary carries lexically.
- **vf_idf** = void_freq × inv_fidelity. Sorted desc. FOREGROUND takes
  only rows > 0.01 (#47: zeros are preserved, not dropped); top < 0.10
  prints the THIN banner — thinness is a finding.

## 8. Synthesis-side geometry (synthesis_v2, source-verified)

- **EXPAND feed**: per-section voids with family tags (SVD flagged) +
  each void's field = flat-leg terminals first (junk-filtered) then
  spiral-leg terms, deduped, source-stems excluded. v0.5 change: rank
  by CLASS-CONSENSUS, then leg count.
- **anti-void decoys**: closeness = max(V@anchor, V@response-centroid);
  ascending sort; filters len ≥ 5, alphabetic, stem ∉ source ∪ said ∪
  candidates; camouflaged with their own top-3 vocab neighbors; woven
  into sha-keyed slots. The trap is measured, not curated. Record:
  liturgy 0.118 / estuary 0.124, both refused.
- **audit semantics**: the instrument detects and evidence-quotes;
  ornamental-vs-factual is the human shipping call. Never claim "facts
  were never corrupted" as a measurement — claim "every adoption ships
  with its sentence."

## 9. Question census (question_census, source-verified)

Ten models independently list the document's raised-but-unanswered
questions; lines ending '?' extracted (numbering stripped); embedded;
**greedy deterministic clustering** (fixed order by model name then
line index, assign to best cluster ≥ threshold 0.80 else new; centroid
re-normalized per insert; no RNG); report clusters with ≥ min-models
(default 3). One model's curiosity is an opinion; consensus is a
measured gap.

## 10. Defect ledger cross-references

#24 substring ANCHOR CONTAINS ("lying" ∈ "identifying") → stem-set
comparison. #37 provenance sha globbed sibling sids → loader whitelist;
fix proven by restoring the pre-tc fingerprint 4c32d4d48239. #39
lexcross hash-seed nondeterminism → per-model counts + alpha tiebreak;
caught by the RESULT sha. #44 inline cosine-only fidelity made
retained words look dropped → verbatim two-channel metric. #47
FOREGROUND sort/floor (zeros topping the list) → desc sort + >0.01
floor + THIN banner. #49 gravity sign error (this doc's Exhibit A).

## 11. File map (implementation of record)

- geometric_engine.py — engine, V9/V10 losses, get_engine (CPU pin)
- consequence_engine.py — flat leg (raycast_void_words)
- latent_retrieval.py — donut (VocabTensor.in_domain_void)
- preservation_core.py — stems, TF, fidelity channels, vf_idf
- centipede_v04.py — the harness: 17 legs, both arms, pricing, JSON
  (v0.5 queued: CLASS-CONSENSUS, σ_min gate, section labels)
- centipede_view.py — ASCII renderer (display only, reads the JSON)
- universal.py — one command: text → harvest → harness
- synthesis_v2.py — the writer stage: measured channels, measured
  decoys, verify loop
- question_census.py — stratum 3 (the unanswered)
- synthesis_page.py / vf-idf.html — the rendered exhibits

*Frozen substrate, separate reading of it — the same split the whole
shop makes its thesis.*
geometric_engine.py      435fd814daea
consequence_engine.py    bce43401a123
latent_retrieval.py      2c4c870fe77f
preservation_core.py     01968b18b6bd
centipede_v04.py         5d49bf428c5a
synthesis_v2.py          d40b60548384
question_census.py       e645580aace5
spiral_sampler.py        5637c4870faf
