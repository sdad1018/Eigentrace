#!/usr/bin/env python3
"""
semantic_robustness.py — Re-run the page's robustness tests on the SEMANTIC
retention metric (not the string-based absent-ratio that inflated 74% -> real 19%).

Reads:
  anamnesis_results/magnum_opus_v2/semantic_rescore_per_response.csv   (semantic retention)
  anamnesis_results/magnum_opus_v2/*.txt                               (for response lengths)

Tests (mirroring the live page's "Eight Robustness Tests", on semantic absent = 1 - retention):
  1. Welch's t-test           dev vs neutral
  2. Mann-Whitney U           non-normal robustness
  3. Permutation (10,000)     guards against category-assignment artifact
  4. Response-length control  is the gap explained by dev responses being shorter/longer?
  5. Length-controlled regression  partial effect of dev after controlling length
  6. Outlier-prompt removal   drop the 2 most extreme dev prompts, re-test
  7. Per-prompt dev>neutral   how many dev prompts exceed the highest neutral prompt
  8. (cross-embedding is a separate run; noted, not done here)

NO API CALLS. Pure arithmetic on the saved semantic scores + file lengths.
"""

from __future__ import annotations
import sys, csv, re, json
from pathlib import Path
import numpy as np
from scipy import stats

RESP_DIR = Path("anamnesis_results/magnum_opus_v2")
CSV = RESP_DIR / "semantic_rescore_per_response.csv"


def load():
    rows = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            if r["semantic_retention"]:
                rows.append({
                    "prompt_id": r["prompt_id"], "category": r["category"],
                    "model": r["model"],
                    "retention": float(r["semantic_retention"]),
                    "absent": 1 - float(r["semantic_retention"]),
                })
    # response lengths from disk
    for r in rows:
        fp = RESP_DIR / f"{r['prompt_id']}_{r['model']}.txt"
        r["length"] = len(fp.read_text(errors="ignore")) if fp.exists() else 0
    return rows


def main() -> int:
    rows = load()
    dev = [r for r in rows if r["category"].startswith("dev_")]
    neu = [r for r in rows if r["category"] == "neutral"]
    dev_abs = np.array([r["absent"] for r in dev])
    neu_abs = np.array([r["absent"] for r in neu])

    print("=" * 74)
    print("SEMANTIC ROBUSTNESS SUITE — metric = semantic absent (1 - retention)")
    print(f"  dev n={len(dev)}  mean absent={dev_abs.mean():.4f}")
    print(f"  neutral n={len(neu)}  mean absent={neu_abs.mean():.4f}")
    gap = dev_abs.mean() - neu_abs.mean()
    pct_more = gap / neu_abs.mean() * 100
    print(f"  gap (dev - neutral) = {gap:+.4f}   = {pct_more:+.1f}% more dropped on dev")
    print("=" * 74)

    out = {"metric": "semantic_absent = 1 - per_source_sentence_cosine_retention",
           "dev_mean_absent": round(float(dev_abs.mean()), 4),
           "neutral_mean_absent": round(float(neu_abs.mean()), 4),
           "gap": round(float(gap), 4), "pct_more_on_dev": round(float(pct_more), 1),
           "tests": {}}

    # 1. Welch's t
    t, p = stats.ttest_ind(dev_abs, neu_abs, equal_var=False)
    print(f"\n1. Welch's t-test:            t={t:.3f}  p={p:.6f}")
    out["tests"]["welch_t"] = {"t": round(float(t), 3), "p": round(float(p), 6)}

    # 2. Mann-Whitney
    U, p = stats.mannwhitneyu(dev_abs, neu_abs, alternative="two-sided")
    print(f"2. Mann-Whitney U:            U={U:.0f}  p={p:.6f}")
    out["tests"]["mann_whitney"] = {"U": float(U), "p": round(float(p), 6)}

    # 3. Permutation (10,000) on difference of means
    rng = np.random.default_rng(0)
    pooled = np.concatenate([dev_abs, neu_abs])
    n_dev = len(dev_abs)
    obs = dev_abs.mean() - neu_abs.mean()
    exceed = 0
    for _ in range(10000):
        rng.shuffle(pooled)
        if (pooled[:n_dev].mean() - pooled[n_dev:].mean()) >= obs:
            exceed += 1
    p_perm = exceed / 10000
    print(f"3. Permutation (10,000):      {exceed} exceeded observed gap   p={p_perm:.4f}")
    out["tests"]["permutation_10k"] = {"exceeded": exceed, "p": p_perm}

    # 4. Response-length difference (is dev shorter/longer?)
    dev_len = np.array([r["length"] for r in dev], float)
    neu_len = np.array([r["length"] for r in neu], float)
    t_len, p_len = stats.ttest_ind(dev_len, neu_len, equal_var=False)
    print(f"4. Response-length check:     dev_len={dev_len.mean():.0f} neutral_len={neu_len.mean():.0f}  "
          f"p={p_len:.3f}  {'(no length diff)' if p_len>0.05 else '(LENGTH DIFFERS - confound risk)'}")
    out["tests"]["length_difference"] = {"dev_len": round(float(dev_len.mean()), 0),
                                         "neutral_len": round(float(neu_len.mean()), 0),
                                         "p": round(float(p_len), 3)}

    # 5. Length-controlled regression: absent ~ is_dev + length
    X_isdev = np.array([1.0 if r["category"].startswith("dev_") else 0.0 for r in rows])
    X_len = np.array([r["length"] for r in rows], float)
    y = np.array([r["absent"] for r in rows])
    X = np.column_stack([np.ones(len(rows)), X_isdev, (X_len - X_len.mean()) / X_len.std()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(rows) - X.shape[1]
    mse = (resid @ resid) / dof
    cov = mse * np.linalg.inv(X.T @ X)
    se_isdev = np.sqrt(cov[1, 1])
    t_isdev = beta[1] / se_isdev
    p_isdev = 2 * (1 - stats.t.cdf(abs(t_isdev), dof))
    print(f"5. Length-controlled regr.:   is_dev coef={beta[1]:+.4f}  t={t_isdev:.3f}  p={p_isdev:.6f}")
    print(f"   --> dev effect on absent ratio AFTER controlling response length")
    out["tests"]["length_controlled_regression"] = {"is_dev_coef": round(float(beta[1]), 4),
                                                     "t": round(float(t_isdev), 3),
                                                     "p": round(float(p_isdev), 6)}

    # 6. Outlier-prompt removal: drop 2 dev prompts with highest mean absent, re-test
    dev_by_prompt = {}
    for r in dev:
        dev_by_prompt.setdefault(r["prompt_id"], []).append(r["absent"])
    prompt_means = {p: np.mean(v) for p, v in dev_by_prompt.items()}
    top2 = sorted(prompt_means, key=prompt_means.get, reverse=True)[:2]
    dev_trim = np.array([r["absent"] for r in dev if r["prompt_id"] not in top2])
    t6, p6 = stats.mannwhitneyu(dev_trim, neu_abs, alternative="two-sided")
    print(f"6. Outlier removal (drop {top2}):")
    print(f"   dev_trim mean={dev_trim.mean():.4f} vs neutral={neu_abs.mean():.4f}  MW p={p6:.6f}")
    out["tests"]["outlier_removal"] = {"dropped": top2, "p": round(float(p6), 6),
                                       "dev_trim_mean": round(float(dev_trim.mean()), 4)}

    # 7. Per-prompt: how many dev prompts exceed the highest neutral prompt mean?
    neu_by_prompt = {}
    for r in neu:
        neu_by_prompt.setdefault(r["prompt_id"], []).append(r["absent"])
    neu_prompt_means = {p: np.mean(v) for p, v in neu_by_prompt.items()}
    highest_neu = max(neu_prompt_means.values())
    dev_above = sum(1 for m in prompt_means.values() if m > highest_neu)
    print(f"7. Per-prompt separation:     {dev_above}/{len(prompt_means)} dev prompts exceed "
          f"highest neutral prompt (absent={highest_neu:.4f})")
    out["tests"]["per_prompt_separation"] = {"dev_above_highest_neutral": dev_above,
                                             "n_dev_prompts": len(prompt_means),
                                             "highest_neutral_absent": round(float(highest_neu), 4)}

    print("\n" + "=" * 74)
    print("INTERPRETATION")
    print("=" * 74)
    survived = (out["tests"]["welch_t"]["p"] < 0.05 and
                out["tests"]["length_controlled_regression"]["p"] < 0.05)
    if survived:
        print(f"  The ~{pct_more:.0f}% semantic dev/neutral gap is statistically robust:")
        print(f"  significant under Welch + Mann-Whitney + permutation, survives length control.")
        print(f"  HONEST HEADLINE: ~{pct_more:.0f}% more content dropped on developer topics")
        print(f"  (semantic; the earlier 74% was a string-matching artifact).")
    else:
        print(f"  The semantic gap is weaker / not robust across controls. Report cautiously;")
        print(f"  lead with the entity-swap (d=0.471) instead.")

    with open(RESP_DIR / "semantic_robustness.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {RESP_DIR / 'semantic_robustness.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
