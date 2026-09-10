#!/usr/bin/env python3
"""
tools/replay_preregistration.py — score the pre-registration prior on stored history.

Reads the newest N story segments (default 800) from SEGMENTS_DIR, forecasts
each one using only strictly earlier stories with a different guid, and prints
accuracy vs the in-sample majority base vs mean prediction_prob vs chance.
CPU only, json only; reads segments, writes nothing.

    python3 tools/replay_preregistration.py [N] [K]
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import preregistration as pr  # noqa: E402


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 800
    k = int(argv[2]) if len(argv) > 2 else pr.K_PRIOR
    rep = pr.replay(n, K=k)
    if not rep.get("n_scored"):
        print(f"no scorable stories among the last {n} (segments dir: {pr.segments_dir()})")
        return 1
    print(f"replay of the pre-registration prior ({rep['prior_version']}, K={rep['K']}) "
          f"on the last {rep['n_stories']} stored story segments, {rep['n_scored']} scorable")
    print(f"  accuracy              {rep['accuracy']:.4f}   ({rep['hits']} hits)")
    print(f"  majority base         {rep['majority_base']:.4f}   (in-sample constant guesser)")
    print(f"  mean prediction_prob  {rep['mean_prediction_prob']:.4f}   (calibration control)")
    print(f"  chance                {rep['chance']:.4f}   (mean 1/len(panel))")
    print(f"  flag accuracy         {rep['flag_accuracy']:.4f}")
    print(f"  near ties (<1 pt)     {rep['near_tie_share_lt_1pt']:.4f}")
    print(f"  predicted             {json.dumps(rep['predicted_distribution'], sort_keys=True)}")
    print(f"  actual                {json.dumps(rep['actual_distribution'], sort_keys=True)}")
    print(f"  prior source          {json.dumps(rep['prior_source_distribution'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
