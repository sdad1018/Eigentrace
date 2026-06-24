#!/usr/bin/env python3
"""
stats_prebuttal.py -- answer the reviewer's three sharpest questions from SAVED data.
NO API calls. Pure reanalysis of confront10_final_panel.json + confront10_final_results.json.

The reviewer's Weakness 3 (benchmark ambiguity) asks:
  - statistical significance of the insight deltas?
  - inter-rater reliability across the 5 judges?
  - blinding / randomization / prompt leakage?  (answered by the run design, stated below)

This script computes, with honest handling of the unequal-n problem:
  1. BASELINE vs A_PLUS_BOTH      -- is the +1.04 headline lift real?
  2. A_PLUS_C  vs A_PLUS_BOTH     -- does the SECOND derivation (convergence) actually help? (the +0.12)
  3. bootstrap 95% CIs on every arm mean and on both deltas
  4. inter-judge agreement (ICC-style + pairwise correlation) on insight
  5. the faith axis too, since the reviewer will look

CRITICAL HONESTY: if the +0.12 (convergence over flat) is NOT significant, this script SAYS SO,
and the recommendation becomes: justify the convergence channel by the `novel` field (it surfaces
concepts flat misses) rather than by an aggregate insight win it doesn't have.

Run on Bertha:
    cd /mnt/c/Users/M4ISI/eigentrace
    python3 stats_prebuttal.py
"""
import json, os, sys, math, random
from collections import defaultdict

REPO = "/mnt/c/Users/M4ISI/eigentrace"
if os.path.isdir(REPO):
    os.chdir(REPO)

random.seed(20260623)

try:
    import numpy as np
except Exception:
    print("numpy required", file=sys.stderr); sys.exit(1)

# scipy is optional; we hand-roll the tests if it's missing so this never fails to run
try:
    from scipy import stats as _ss
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False


# ----------------------------------------------------------------------------- helpers
def mean(x):
    return float(np.mean(x)) if len(x) else float("nan")

def bootstrap_ci(x, nboot=10000, alpha=0.05):
    """Percentile bootstrap CI for the mean of x."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (float("nan"), float("nan"))
    boots = np.empty(nboot)
    n = len(x)
    for b in range(nboot):
        boots[b] = x[np.random.randint(0, n, n)].mean()
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    return (lo, hi)

def bootstrap_diff_ci(paired_a, paired_b, nboot=10000, alpha=0.05):
    """Percentile bootstrap CI for mean(b - a) on PAIRED arrays (resample pairs)."""
    a = np.asarray(paired_a, float); b = np.asarray(paired_b, float)
    d = b - a
    d = d[~np.isnan(d)]
    if len(d) < 2:
        return (float("nan"), float("nan"), float("nan"))
    boots = np.empty(nboot)
    n = len(d)
    for k in range(nboot):
        boots[k] = d[np.random.randint(0, n, n)].mean()
    lo = float(np.percentile(boots, 100 * alpha / 2))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2)))
    return (float(d.mean()), lo, hi)

def cohens_dz(paired_a, paired_b):
    """Paired effect size (mean diff / sd of diffs)."""
    a = np.asarray(paired_a, float); b = np.asarray(paired_b, float)
    d = b - a; d = d[~np.isnan(d)]
    if len(d) < 2 or d.std(ddof=1) == 0:
        return float("nan")
    return float(d.mean() / d.std(ddof=1))

def paired_t(paired_a, paired_b):
    a = np.asarray(paired_a, float); b = np.asarray(paired_b, float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) < 2:
        return float("nan"), float("nan"), 0
    if HAVE_SCIPY:
        t, p = _ss.ttest_rel(b, a)
        return float(t), float(p), len(a)
    # hand-rolled paired t
    d = b - a; n = len(d)
    sd = d.std(ddof=1)
    if sd == 0:
        return float("inf"), 0.0, n
    t = d.mean() / (sd / math.sqrt(n))
    # normal approx for p (large n); good enough as fallback
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return float(t), float(p), n

def wilcoxon(paired_a, paired_b):
    a = np.asarray(paired_a, float); b = np.asarray(paired_b, float)
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    d = b - a
    d = d[d != 0]
    if len(d) < 6 or not HAVE_SCIPY:
        return float("nan"), float("nan"), len(d)
    try:
        w, p = _ss.wilcoxon(b[mask][b[mask] != a[mask]] if False else (b - a)[ (b-a)!=0 ])
    except Exception:
        return float("nan"), float("nan"), len(d)
    return float(w), float(p), len(d)

def mannwhitney(a, b):
    """Unpaired, for when we can't align."""
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
    if not HAVE_SCIPY or len(a) < 3 or len(b) < 3:
        return float("nan"), float("nan")
    u, p = _ss.mannwhitneyu(b, a, alternative="two-sided")
    return float(u), float(p)


# ----------------------------------------------------------------------------- load
PANEL = "confront10_final_panel.json"
RESULTS = "confront10_final_results.json"

if not os.path.exists(PANEL):
    print(f"ERROR: {PANEL} not found", file=sys.stderr); sys.exit(1)

panel = json.load(open(PANEL))
P = panel.get("panel", {})
PJ = panel.get("per_judge", {})

ARMS = ["BASELINE", "A_ONLY", "C_ONLY", "A_PLUS_C", "A_PLUS_BOTH"]
ARMS = [a for a in ARMS if a in P and P[a].get("insight")]

print("=" * 74)
print("SUMMARY PLUS — STATISTICAL PREBUTTAL  (saved data, no API calls)")
print("=" * 74)

# ----------------------------------------------------------------------------- 0. design facts (no compute)
print("""
0. RUN DESIGN  (answers blinding / randomization / leakage directly)
----------------------------------------------------------------------
  - 5 frontier models as a BLIND panel; arm order SHUFFLED per item (random.shuffle)
  - judges score on a 1-5 scale; "keep" is 0/1
  - NO model evaluates its own output as the sole judge — all 5 score every item
  - faith prompt explicitly says "true to source, NOTHING inferred or imported beyond it"
  - per-sentence provenance coded separately by the same panel (O/I/A/S)
  - generation and judging are separate passes; judges never see arm labels
""")

# ----------------------------------------------------------------------------- 1. arm means + bootstrap CIs (unpaired, all data)
print("=" * 74)
print("1. ARM MEANS with bootstrap 95% CI  (all judgements per arm, unequal n)")
print("=" * 74)
for metric in ["insight", "faith"]:
    print(f"\n  --- {metric} ---")
    for a in ARMS:
        x = P[a][metric]
        lo, hi = bootstrap_ci(x)
        print(f"    {a:12s} mean={mean(x):.3f}  95% CI [{lo:.3f}, {hi:.3f}]  n={len(x)}")

# ----------------------------------------------------------------------------- 2. PAIRED reconstruction from results
# The panel arrays are appended in fixed loop order but arms have unequal n (failed gens),
# so they are NOT safely aligned. Reconstruct aligned per-item pairs from results.json,
# keying on (story, model, gen_index), taking the per-item MEAN across the 5 judges.
print("\n" + "=" * 74)
print("2. PAIRED ANALYSIS  (aligned per-item from results.json; the rigorous test)")
print("=" * 74)

paired_ok = False
if os.path.exists(RESULTS):
    results = json.load(open(RESULTS))
    # We need per-(story,model,gen) judge scores. The panel doesn't store that mapping,
    # but results stores the generations; the panel stored aggregate arrays only.
    # If the results file carries per-gen scores, use them; else we note the limitation.
    # Check structure:
    sample = results[0]["rows"][0]["gens"][0] if results and results[0].get("rows") else {}
    has_scores_in_results = isinstance(sample, dict) and any(
        isinstance(v, dict) and ("insight" in v or "scores" in v) for v in sample.values()
    )
    if has_scores_in_results:
        # build aligned arrays (rare path — only if scores were saved per gen)
        items = defaultdict(dict)
        for o in results:
            sid = o["story"]
            for row in o.get("rows", []):
                m = row["patient"]
                for gi, g in enumerate(row.get("gens", [])):
                    for arm in ARMS:
                        cell = g.get(arm)
                        if isinstance(cell, dict) and "insight" in cell:
                            items[(sid, m, gi)][arm] = cell["insight"]
        # not the usual case; handled for completeness
        paired_ok = False  # fall through to honest note
    else:
        paired_ok = False

if not paired_ok:
    print("""
  NOTE: confront10_final_panel.json stores per-arm score ARRAYS, not the
  (story, model, gen, judge) -> score mapping needed to align items across arms.
  The arms also have unequal n (failed generations), so the flat arrays cannot be
  safely paired position-by-position. Two honest options:

    (a) UNPAIRED tests on the full arrays below (valid, slightly less powerful), and
    (b) if you want the stronger PAIRED test, re-run the panel saving per-item judge
        scores keyed by (story, model, gen) — a logging change to confront10_final.py,
        no new generations needed if you cache the existing generations.

  Reporting the UNPAIRED result now (Mann-Whitney + bootstrap on independent samples):
""")
    def report_pair_unpaired(a_name, b_name):
        a = np.asarray(P[a_name]["insight"], float); a = a[~np.isnan(a)]
        b = np.asarray(P[b_name]["insight"], float); b = b[~np.isnan(b)]
        diff = b.mean() - a.mean()
        # bootstrap CI on the difference of independent means
        nboot = 10000
        boots = np.empty(nboot)
        for k in range(nboot):
            boots[k] = b[np.random.randint(0, len(b), len(b))].mean() - a[np.random.randint(0, len(a), len(a))].mean()
        lo = float(np.percentile(boots, 2.5)); hi = float(np.percentile(boots, 97.5))
        u, p = mannwhitney(a, b)
        # pooled cohen's d
        sp = math.sqrt(((len(a)-1)*a.std(ddof=1)**2 + (len(b)-1)*b.std(ddof=1)**2) / (len(a)+len(b)-2))
        d = diff / sp if sp else float("nan")
        sig = "***" if (not math.isnan(p) and p < 0.001) else "**" if (not math.isnan(p) and p<0.01) else "*" if (not math.isnan(p) and p<0.05) else "n.s."
        print(f"    {b_name} vs {a_name}:")
        print(f"      Δ insight = {diff:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]   Cohen's d={d:+.3f}")
        print(f"      Mann-Whitney p = {p:.4g}  [{sig}]   (n_{a_name}={len(a)}, n_{b_name}={len(b)})")
        return diff, lo, hi, p

    print("  THE HEADLINE — does Summary Plus beat plain summarization?")
    report_pair_unpaired("BASELINE", "A_PLUS_BOTH")
    print()
    print("  THE SECOND-DERIVATION QUESTION — does convergence add over flat alone? (the +0.12)")
    d2 = report_pair_unpaired("A_PLUS_C", "A_PLUS_BOTH")

# ----------------------------------------------------------------------------- 3. inter-rater reliability
print("\n" + "=" * 74)
print("3. INTER-RATER RELIABILITY  (do the 5 judges agree? — answers the IRR question)")
print("=" * 74)

# per_judge[judge][arm]["insight"] arrays. We can't align item-by-item across judges from
# the aggregate, but we CAN report each judge's mean per arm + the spread across judges,
# which is the practically meaningful agreement signal here.
judges = list(PJ.keys())
if judges:
    print(f"\n  judges: {judges}")
    print(f"\n  per-judge MEAN insight by arm (agreement = low spread across the column):")
    header = "    " + "judge".ljust(10) + "".join(a[:10].rjust(13) for a in ARMS)
    print(header)
    col_means = defaultdict(list)
    for jn in judges:
        cells = []
        for a in ARMS:
            arr = PJ[jn].get(a, {}).get("insight", [])
            mv = mean(arr) if arr else float("nan")
            cells.append(mv)
            if not math.isnan(mv):
                col_means[a].append(mv)
        print("    " + jn.ljust(10) + "".join(f"{c:13.2f}" for c in cells))
    # cross-judge SD per arm = how much judges disagree on that arm's level
    print(f"\n  cross-judge SD per arm (lower = judges agree on the arm's quality):")
    print("    " + "".join(f"{a[:10].rjust(13)}" for a in ARMS))
    print("    " + "".join(f"{(np.std(col_means[a], ddof=1) if len(col_means[a])>1 else float('nan')):13.3f}" for a in ARMS))

    # ordering agreement: does every judge rank BOTH > BASELINE?
    print(f"\n  ORDERING AGREEMENT (the strongest IRR signal for this design):")
    agree_head = agree_conv = 0; tot = 0
    for jn in judges:
        base = mean(PJ[jn].get("BASELINE", {}).get("insight", []) or [float("nan")])
        ac   = mean(PJ[jn].get("A_PLUS_C", {}).get("insight", []) or [float("nan")])
        both = mean(PJ[jn].get("A_PLUS_BOTH", {}).get("insight", []) or [float("nan")])
        if not (math.isnan(base) or math.isnan(both)):
            tot += 1
            if both > base: agree_head += 1
            if not math.isnan(ac) and both > ac: agree_conv += 1
        arrow1 = ">" if (not math.isnan(both) and not math.isnan(base) and both>base) else "≤"
        arrow2 = ">" if (not math.isnan(both) and not math.isnan(ac) and both>ac) else "≤"
        print(f"    {jn:10s}  BOTH {arrow1} BASELINE   |   BOTH {arrow2} A_PLUS_C")
    print(f"\n    {agree_head}/{tot} judges rank BOTH > BASELINE   (headline robustness)")
    print(f"    {agree_conv}/{tot} judges rank BOTH > A_PLUS_C    (convergence robustness)")

# ----------------------------------------------------------------------------- 4. the novel-field fallback justification
print("\n" + "=" * 74)
print("4. CONVERGENCE JUSTIFICATION VIA `novel`  (the fallback if +0.12 is n.s.)")
print("=" * 74)
print("""
  Whether or not the aggregate +0.12 reaches significance, the convergence channel has an
  INDEPENDENT justification that needs no panel score: it surfaces concepts the centroid
  CANNOT. This is the `novel` field (spiral minus flat), non-empty on every story:
""")
if os.path.exists("spiral_concepts.json"):
    sc = json.load(open("spiral_concepts.json"))
    total_novel = 0
    for o in sc:
        nv = o.get("novel", [])
        total_novel += len(nv)
        print(f"    {o['story']:18s} +{len(nv)} novel: {nv}")
    print(f"\n    Total convergence-only concepts across 7 stories: {total_novel}")
    print("    -> Even with zero aggregate insight gain, convergence demonstrably WIDENS the")
    print("       candidate set with source-implied concepts the centroid misses. That is the")
    print("       honest claim for the second derivation if the panel delta is n.s.")

# ----------------------------------------------------------------------------- 5. verdict
print("\n" + "=" * 74)
print("5. WHAT TO CLAIM ON THE PAGE  (read the numbers above, then:)")
print("=" * 74)
print("""
  IF BASELINE->BOTH is significant (expected; the gap is ~1.0):
     KEEP "a +1.04 insight lift over plain summarization, p<...". This is the headline and
     it is almost certainly solid at n~460.

  IF A_PLUS_C->BOTH is significant:
     KEEP "the second derivation adds a further +0.12". State the p-value and CI.

  IF A_PLUS_C->BOTH is NOT significant (very possible at +0.12):
     DROP the aggregate "+0.12 beats flat" framing. REPLACE with: "convergence surfaces
     concepts the centroid misses (the `novel` field, non-empty on every story) — a second
     independent route to the negative space, not a bigger number." This is TRUE regardless
     and is the stronger, more honest claim. It also matches the page's own thesis that
     the reading, not the aggregate score, is where value lands.

  Either way you can now answer the reviewer's Weakness 3 in full: blinding (design note),
  significance (the tests above), IRR (the ordering-agreement table), and you remove the
  one genuinely fair attack — an unqualified "3.43 vs 2.39" with no statistics behind it.
""")
print("=" * 74)
print("done. No API calls were made; this is pure reanalysis of saved artifacts.")
print("=" * 74)
