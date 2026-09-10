#!/usr/bin/env python3
"""tools/roundtable_null.py -- the roundtable's format null, measured from stored files.

Reads every *_roundtable.json in the segments tree (read-only; nothing is written)
and reports, per model, mean(R3 - R1) cosine distance and the fraction of
(story, model) pairs the on-air rule labels "doubled down" (delta > 0.02) or
"opened up" (delta < -0.02) -- the thresholds batch_producer.py uses on air.

If far more than half of all pairs double down across stories, the label is a
format artefact: round 3 asks for acknowledgement + explanation + summary and
round3_vix is computed on the whole reply, so meta-text raises the distance
regardless of the summary.  When round3_vix_summary (summary-only distance,
written by roundtable.py since 2026-09) is present, the same stats are printed
for it so the two can be compared on direction.

numpy only.  No embedding, no GPU, no API.  CPU-safe during the broadcast.

    python3 tools/roundtable_null.py                # default runtime tree
    python3 tools/roundtable_null.py --dir DIR --last 50
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

DEFAULT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
THRESH = 0.02   # batch_producer.py stage_7 on-air thresholds (1-cos scale; = 10 broadcast VIX points)


def load_roundtables(directory, last=None):
    files = sorted(glob.glob(os.path.join(directory, "*_roundtable.json")))
    if last:
        files = files[-int(last):]
    out = []
    for f in files:
        try:
            with open(f) as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not isinstance(d, dict) or "round1_vix" not in d or "round3_vix" not in d:
            continue
        d["_file"] = os.path.basename(f)
        out.append(d)
    return out


def summarize(roundtables, r3_key="round3_vix"):
    """Per-model and overall stats for delta = R3 - R1 on the stored distances."""
    import numpy as np
    per_model = defaultdict(list)
    herd_conv = herd_div = herd_stable = 0
    n_stories = 0
    for d in roundtables:
        r1 = d.get("round1_vix") or {}
        r3 = d.get(r3_key) or {}
        common = [m for m in r1 if m in r3 and r1[m] is not None and r3[m] is not None]
        if not common:
            continue
        n_stories += 1
        for m in common:
            per_model[m].append(float(r3[m]) - float(r1[m]))
        if len(common) >= 2:
            s1 = float(np.std([r1[m] for m in common])); s3 = float(np.std([r3[m] for m in common]))
            if s3 < s1 * 0.8:
                herd_conv += 1
            elif s3 > s1 * 1.2:
                herd_div += 1
            else:
                herd_stable += 1
    rows = {}
    all_d = []
    for m, ds in per_model.items():
        a = np.asarray(ds, float)
        all_d.extend(ds)
        rows[m] = {
            "n": int(len(a)),
            "mean_delta": float(a.mean()),
            "median_delta": float(np.median(a)),
            "frac_doubled_down": float((a > THRESH).mean()),
            "frac_opened_up": float((a < -THRESH).mean()),
            "frac_unchanged": float((np.abs(a) <= THRESH).mean()),
        }
    a = np.asarray(all_d, float) if all_d else np.zeros(0)
    overall = {
        "n_stories": n_stories,
        "n_pairs": int(len(a)),
        "mean_delta": float(a.mean()) if len(a) else None,
        "frac_doubled_down": float((a > THRESH).mean()) if len(a) else None,
        "frac_opened_up": float((a < -THRESH).mean()) if len(a) else None,
        "herding": {"converged": herd_conv, "diverged": herd_div, "stable": herd_stable},
        "threshold": THRESH,
        "r3_key": r3_key,
    }
    return {"per_model": rows, "overall": overall}


def verdict(overall):
    f = overall.get("frac_doubled_down")
    if f is None:
        return "no data"
    if f > 0.8:
        return ("FORMAT ARTEFACT: >80% of (story, model) pairs 'double down'. Round-3 replies include "
                "acknowledgement and explanation text that counts toward distance; the on-air label "
                "does not measure a change in the summary.")
    if f > 0.5:
        return "SUSPECT: more than half double down; the round-3 reply format likely inflates distance."
    return "label is informative at the story level (doubled-down share is not dominated by format)."


def print_report(res, title=""):
    o = res["overall"]
    print(f"\n{title}")
    print(f"  stories={o['n_stories']}  (story,model) pairs={o['n_pairs']}  threshold=+/-{o['threshold']}  key={o['r3_key']}")
    print(f"  {'model':10s} {'n':>4s} {'mean(R3-R1)':>12s} {'median':>8s} {'doubled':>8s} {'opened':>8s} {'unchg':>7s}")
    for m, r in sorted(res["per_model"].items()):
        print(f"  {m:10s} {r['n']:4d} {r['mean_delta']:+12.4f} {r['median_delta']:+8.4f} {r['frac_doubled_down']:8.1%} {r['frac_opened_up']:8.1%} {r['frac_unchanged']:7.1%}")
    if o["mean_delta"] is not None:
        print(f"  {'ALL':10s} {o['n_pairs']:4d} {o['mean_delta']:+12.4f} {'':>8s} {o['frac_doubled_down']:8.1%} {o['frac_opened_up']:8.1%}")
    h = o["herding"]
    print(f"  herding (std R3 vs R1): converged={h['converged']} diverged={h['diverged']} stable={h['stable']}  [print-only metric, never broadcast]")
    print(f"  verdict: {verdict(o)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--last", type=int, default=None, help="only the last N files")
    ap.add_argument("--json", action="store_true", help="also print the result as JSON (stdout)")
    a = ap.parse_args(argv)
    rts = load_roundtables(a.dir, a.last)
    if not rts:
        print(f"no *_roundtable.json with round1_vix/round3_vix under {a.dir}", file=sys.stderr)
        return 1
    full = summarize(rts, "round3_vix")
    print_report(full, f"ROUNDTABLE NULL  ({len(rts)} files under {a.dir})  -- R3 distance on the FULL reply (what airs)")
    with_summary = [d for d in rts if d.get("round3_vix_summary")]
    if with_summary:
        summ = summarize(with_summary, "round3_vix_summary")
        print_report(summ, f"SUMMARY-ONLY R3 ({len(with_summary)} files carry round3_vix_summary)")
        # direction agreement per pair
        agree = tot = 0
        for d in with_summary:
            r1 = d.get("round1_vix") or {}; f3 = d.get("round3_vix") or {}; s3 = d.get("round3_vix_summary") or {}
            for m in r1:
                if m in f3 and m in s3:
                    tot += 1
                    df = f3[m] - r1[m]; ds = s3[m] - r1[m]
                    lf = 1 if df > THRESH else (-1 if df < -THRESH else 0)
                    ls = 1 if ds > THRESH else (-1 if ds < -THRESH else 0)
                    agree += (lf == ls)
        if tot:
            print(f"  on-air label agreement full-reply vs summary-only: {agree}/{tot} = {agree/tot:.1%}")
    else:
        print("\n  (no file carries round3_vix_summary yet; roundtable.py writes it from 2026-09 on)")
    if a.json:
        print(json.dumps({"full": full, "summary_only": (summarize(with_summary, "round3_vix_summary") if with_summary else None)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
