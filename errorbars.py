#!/usr/bin/env python3
"""
errorbars.py -- sample sizes and 95% intervals for every published aggregate
============================================================================
One module, one code path (2026-09-10).  Every rolling number EigenTrace
publishes (docs/data/YYYYMMDD.json, the Omission Ledger, model_profiles.json,
soul.md, the on-air trajectory beat) gets its n and a seeded percentile
bootstrap interval from here, over the SAME definition of "story".

stdlib + numpy only.  Never imports torch, never touches the network.

Seed convention: daily artifacts use int(YYYYMMDD); hourly artifacts use
int(YYYYMMDDHH); the seed is stored next to every interval so any reader can
reproduce it from the published file.
"""
from __future__ import annotations

import glob
import math
import os
import re
from datetime import datetime, timedelta

import numpy as np

# Copied verbatim from data_exporter.py (2026-09-04 filter): the system's own
# segments are not stories.
NON_STORY_TYPES = ("idle", "silence", "consolidation", "weekly_compression", "governance",
                   "foraging", "self_audit", "roundtable", "pundit_desk", "conversation")

STORY_FILE_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$")

DEFAULT_B = 2000
LEVEL = 0.95
INSUFFICIENT_N = 5


def is_story(seg) -> bool:
    """One shared definition: not a system segment, has per-model VIX, has a title.
    wild_weasel probes carry no model_vix and are therefore not stories either."""
    if not isinstance(seg, dict):
        return False
    if seg.get("segment_type") in NON_STORY_TYPES:
        return False
    attr = seg.get("attribution") or {}
    if not isinstance(attr, dict):
        return False
    return bool(attr.get("model_vix")) and bool(attr.get("story_title"))


def _clean(values):
    out = []
    for v in values or ():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and math.isfinite(v):
            out.append(float(v))
    return out


def boot_ci(values, B=DEFAULT_B, seed=0, stat="mean"):
    """Percentile bootstrap interval on a list of per-story numbers.

    Returns a dict {mean, lo, hi, n, seed, B, method, level, stat, insufficient}.
    n == 0 -> mean None and lo/hi None; n < 2 -> lo/hi None (no interval);
    n < 5 -> insufficient True.  Deterministic for a given (values, B, seed).
    `stat` is "mean" or "median" (the point and the resampled statistic).
    """
    vals = _clean(values)
    n = len(vals)
    if stat == "mean":
        fn = np.mean
    elif stat == "median":
        fn = np.median
    elif callable(stat):
        fn = stat
    else:
        raise ValueError(f"unknown stat {stat!r}")
    out = {
        "mean": None, "lo": None, "hi": None, "n": n,
        "seed": int(seed), "B": int(B), "method": "percentile_bootstrap",
        "level": LEVEL, "stat": stat if isinstance(stat, str) else "callable",
        "insufficient": n < INSUFFICIENT_N,
    }
    if n == 0:
        return out
    arr = np.asarray(vals, dtype=float)
    out["mean"] = float(fn(arr))
    if n < 2:
        return out
    rng = np.random.default_rng(int(seed))
    idx = rng.integers(0, n, size=(int(B), n))
    stats = fn(arr[idx], axis=1)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    out["lo"] = float(lo)
    out["hi"] = float(hi)
    return out


def wilson_ci(k, n, z=1.96):
    """Wilson score interval for a proportion k/n.  n == 0 -> None."""
    n = int(n)
    k = int(k)
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return {"n": n, "k": k, "point": p, "lo": lo, "hi": hi, "method": "wilson", "level": LEVEL}


def argmax_share(per_model, B=DEFAULT_B, seed=0, mode="max"):
    """Bootstrap share of resamples in which the observed argmax (or argmin with
    mode="min") of the per-model means keeps its title.

    per_model: {model: [one value per story]} -- lists must be equal length
    (the resampling is paired: the same story indices are drawn for every model).
    Returns {winner, runner_up, share, runner_up_share, shares{model: share},
    n, seed, B, mode}; winner None when there is nothing to rank.
    """
    if mode not in ("max", "min"):
        raise ValueError("mode must be 'max' or 'min'")
    names = [m for m in per_model if per_model[m]]
    out = {"winner": None, "runner_up": None, "share": None, "runner_up_share": None,
           "shares": {}, "n": 0, "seed": int(seed), "B": int(B), "mode": mode}
    if not names:
        return out
    lengths = {len(per_model[m]) for m in names}
    if len(lengths) != 1:
        raise ValueError(f"per-model lists must have equal length, got {sorted(lengths)}")
    n = lengths.pop()
    out["n"] = n
    if n == 0:
        return out
    mat = np.asarray([_clean(per_model[m]) for m in names], dtype=float)
    if mat.shape[1] != n:
        raise ValueError("per-model lists must be numeric and equal length")
    means = mat.mean(axis=1)
    order = np.argsort(-means if mode == "max" else means, kind="stable")
    winner = names[int(order[0])]
    runner_up = names[int(order[1])] if len(names) > 1 else None
    if len(names) == 1:
        out.update({"winner": winner, "runner_up": None, "share": 1.0,
                    "runner_up_share": None, "shares": {winner: 1.0}})
        return out
    rng = np.random.default_rng(int(seed))
    idx = rng.integers(0, n, size=(int(B), n))
    # resampled means: (B, models)
    res = mat[:, idx].mean(axis=2).T
    pick = res.argmax(axis=1) if mode == "max" else res.argmin(axis=1)
    counts = np.bincount(pick, minlength=len(names))
    shares = {names[i]: float(counts[i]) / int(B) for i in range(len(names))}
    out.update({
        "winner": winner,
        "runner_up": runner_up,
        "share": shares[winner],
        "runner_up_share": shares.get(runner_up),
        "shares": shares,
    })
    return out


def per_model_lists(segments):
    """Paired per-model VIX lists over stories in which every model reported.
    Returns ({model: [v...]}, n_paired)."""
    rows = []
    for seg in segments:
        mv = ((seg.get("attribution") or {}).get("model_vix") or {}) if isinstance(seg, dict) else {}
        row = {m: float(v) for m, v in mv.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if row:
            rows.append(row)
    if not rows:
        return {}, 0
    models = sorted(set().union(*[set(r) for r in rows]))
    full = [r for r in rows if all(m in r for m in models)]
    if not full:
        # fall back to the most common panel
        return {}, 0
    return {m: [r[m] for r in full] for m in models}, len(full)


def metric_series(segments):
    """Per-story metric lists using the same drop-zero rules as
    soul_updater.compute_calibration, plus per-story mean VIX."""
    out = {"density": [], "absent_ratio": [], "verb_drift": [], "entity_retention": [],
           "hedges": [], "mean_vix": []}
    for s in segments:
        attr = (s.get("attribution") or {}) if isinstance(s, dict) else {}
        comp = attr.get("compression") or {}
        sv = attr.get("source_void") or {}
        ab = comp.get("attribution_buffer") if isinstance(comp, dict) else None
        if attr.get("consensus_density", 0) and attr["consensus_density"] > 0:
            out["density"].append(attr["consensus_density"])
        if isinstance(comp, dict) and comp.get("verb_downgrade", 0) and comp["verb_downgrade"] > 0:
            out["verb_drift"].append(comp["verb_downgrade"])
        if isinstance(comp, dict) and comp.get("entity_retention", 0) and comp["entity_retention"] > 0:
            out["entity_retention"].append(comp["entity_retention"])
        if isinstance(sv, dict) and sv.get("absent_ratio", 0) and sv["absent_ratio"] > 0:
            out["absent_ratio"].append(sv["absent_ratio"])
        if isinstance(ab, dict) and ab.get("total", 0) and ab["total"] > 0:
            out["hedges"].append(ab["total"])
        if isinstance(attr.get("mean_vix"), (int, float)) and attr.get("mean_vix", 0) > 0:
            out["mean_vix"].append(attr["mean_vix"])
    return out


def compute_window_delta(recent_values, earlier_values, B=DEFAULT_B, seed=0):
    """Bootstrap interval on the difference of means between two DISJOINT windows
    (each window resampled independently).  Returns
    {recent, earlier, n_now, n_prev, delta, dlo, dhi, direction, resolved, seed, B}
    where direction is "increasing"/"decreasing" when the interval excludes zero
    and "not resolved" otherwise; None when either window is empty.
    """
    now = _clean(recent_values)
    prev = _clean(earlier_values)
    if not now or not prev:
        return None
    a = np.asarray(now, dtype=float)
    b = np.asarray(prev, dtype=float)
    recent = float(a.mean())
    earlier = float(b.mean())
    delta = recent - earlier
    out = {"recent": recent, "earlier": earlier, "n_now": len(now), "n_prev": len(prev),
           "delta": delta, "dlo": None, "dhi": None, "direction": "not resolved",
           "resolved": False, "seed": int(seed), "B": int(B), "method": "percentile_bootstrap"}
    if len(now) < 2 or len(prev) < 2:
        return out
    rng = np.random.default_rng(int(seed))
    ia = rng.integers(0, len(now), size=(int(B), len(now)))
    ib = rng.integers(0, len(prev), size=(int(B), len(prev)))
    diffs = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    dlo, dhi = np.percentile(diffs, [2.5, 97.5])
    out["dlo"] = float(dlo)
    out["dhi"] = float(dhi)
    if dlo > 0:
        out["direction"], out["resolved"] = "increasing", True
    elif dhi < 0:
        out["direction"], out["resolved"] = "decreasing", True
    return out


def split_windows(segments, now=None, hours=24):
    """Split segments into (recent, earlier): recent = ts in (now-hours, now],
    earlier = ts in (now-2*hours, now-hours].  Timestamps are '%Y%m%d_%H%M%S'."""
    now = now or datetime.utcnow()
    c1 = now - timedelta(hours=hours)
    c2 = now - timedelta(hours=2 * hours)
    recent, earlier = [], []
    for s in segments:
        try:
            ts = datetime.strptime(s["timestamp"], "%Y%m%d_%H%M%S")
        except Exception:
            continue
        if ts > c1:
            recent.append(s)
        elif ts > c2:
            earlier.append(s)
    return recent, earlier


def daily_seed(date: str) -> int:
    """int('20260910') for daily artifacts."""
    return int(str(date)[:8])


def hourly_seed(now=None) -> int:
    """int('2026091013') for hourly artifacts."""
    now = now or datetime.utcnow()
    return int(now.strftime("%Y%m%d%H"))


def count_story_files(segment_dir) -> int:
    """Number of files matching the story filename regex (a census, not a sample)."""
    n = 0
    for f in glob.glob(os.path.join(str(segment_dir), "*_segment.json")):
        if STORY_FILE_RE.match(os.path.basename(f)):
            n += 1
    return n


def ci_md(mean, ci, digits=1) -> str:
    """'17.7 (95% CI 14.7-20.6, n=9)' for markdown; degrades when no interval."""
    n = (ci or {}).get("n", 0) if isinstance(ci, dict) else 0
    if mean is None:
        return f"n/a (n={n})"
    if not ci or ci.get("lo") is None:
        return f"{mean:.{digits}f} (n={n}, interval undefined)"
    return f"{mean:.{digits}f} (95% CI {ci['lo']:.{digits}f}-{ci['hi']:.{digits}f}, n={n})"
