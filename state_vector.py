#!/usr/bin/env python3
"""
state_vector.py — Ternary state classification from EigenTrace measurements
============================================================================
Quantizes continuous measurements into {-1, 0, +1} signals.
Can use any N signals. Default 6 chosen by discrimination analysis.

Usage:
  python3 state_vector.py --analyze     # Find best 6 from history
  python3 state_vector.py --current     # Current state vector
  python3 state_vector.py --history     # Find past occurrences of current state
"""

import json, glob, os, logging
import numpy as np
from datetime import datetime
from itertools import combinations
from collections import Counter

log = logging.getLogger("state_vector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"

# ═══════════════════════════════════════════════════════════════
# ALL AVAILABLE SIGNALS — extracted from segment attribution
# ═══════════════════════════════════════════════════════════════
def extract_signals(seg):
    """Extract all measurable signals from a segment. Returns dict."""
    attr = seg.get("attribution", {})
    comp = attr.get("compression", {})
    sv = attr.get("source_void", {})
    mvix = attr.get("model_vix", {})
    ab = comp.get("attribution_buffer", {})

    vix_values = [v for v in mvix.values() if isinstance(v, (int, float))]
    vix_spread = max(vix_values) - min(vix_values) if len(vix_values) >= 2 else 0

    return {
        "consensus_density": attr.get("consensus_density", 0),
        "absent_ratio": sv.get("absent_ratio", 0),
        "verb_drift": comp.get("verb_downgrade", 0),
        "entity_retention": comp.get("entity_retention", 0),
        "hedge_count": ab.get("total", 0) if isinstance(ab, dict) else 0,
        "vix_spread": vix_spread,
        "mean_vix": attr.get("mean_vix", 0),
        "compression_score": comp.get("compression_score", 0),
        "entity_abstraction": comp.get("entity_abstraction_rate", 0),
        "source_word_count": sv.get("source_word_count", 0),
        "absent_count": sv.get("absent_count", 0),
    }

# ═══════════════════════════════════════════════════════════════
# QUANTIZER — continuous → ternary {-1, 0, +1}
# ═══════════════════════════════════════════════════════════════
# Thresholds: below low → one pole, above high → other pole, between → 0
# Polarity: +1 always means "good/healthy", -1 means "concerning"

QUANT_RULES = {
    "consensus_density":  {"low": 0.82, "high": 0.92, "invert": False},
    # high density = lockstep (concerning), low = fractured (concerning)
    # actually: mid is normal, extremes are interesting
    "absent_ratio":       {"low": 0.3,  "high": 0.6,  "invert": True},
    # high absent = bad → -1
    "verb_drift":         {"low": 0.02, "high": 0.08, "invert": True},
    # high drift = softening → -1
    "entity_retention":   {"low": 0.3,  "high": 0.6,  "invert": False},
    # high retention = good → +1
    "hedge_count":        {"low": 1,    "high": 4,    "invert": True},
    # high hedges = bad → -1
    "vix_spread":         {"low": 10,   "high": 25,   "invert": True},
    # high spread = one model breaking away → -1
    "mean_vix":           {"low": 15,   "high": 30,   "invert": True},
    # high mean vix = high friction → -1
    "compression_score":  {"low": 0.2,  "high": 0.5,  "invert": True},
    "entity_abstraction": {"low": 0.3,  "high": 0.7,  "invert": True},
    "source_word_count":  {"low": 50,   "high": 200,  "invert": False},
    "absent_count":       {"low": 10,   "high": 40,   "invert": True},
}

def quantize(value, rule):
    """Convert continuous value to {-1, 0, +1}."""
    if value <= rule["low"]:
        trit = -1
    elif value >= rule["high"]:
        trit = 1
    else:
        trit = 0
    if rule.get("invert"):
        trit = -trit
    return trit

def compute_state_vector(signals, signal_names=None):
    """Compute ternary state vector from signals.
    If signal_names is None, uses all available signals.
    """
    if signal_names is None:
        signal_names = [k for k in signals if k in QUANT_RULES]

    vector = []
    labels = []
    for name in signal_names:
        if name in signals and name in QUANT_RULES:
            vector.append(quantize(signals[name], QUANT_RULES[name]))
            labels.append(name)

    return tuple(vector), labels

# ═══════════════════════════════════════════════════════════════
# LOAD HISTORY
# ═══════════════════════════════════════════════════════════════
def load_all_signals():
    """Load signals from all segments."""
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")))
    records = []
    for f in files:
        try:
            seg = json.load(open(f))
            signals = extract_signals(seg)
            # Skip segments with no real data
            if signals["consensus_density"] == 0 and signals["absent_ratio"] == 0:
                continue
            signals["_timestamp"] = seg.get("timestamp", "")
            signals["_title"] = seg.get("attribution", {}).get("story_title", "")
            signals["_category"] = seg.get("attribution", {}).get("category", "")
            records.append(signals)
        except:
            continue
    return records

# ═══════════════════════════════════════════════════════════════
# ANALYZE — find which 6 signals produce most unique states
# ═══════════════════════════════════════════════════════════════
def analyze_best_signals(records, group_size=6, top_n=10):
    """Test all C(n,6) combinations and rank by state diversity."""
    signal_names = [k for k in QUANT_RULES.keys()
                    if any(r.get(k, 0) != 0 for r in records[:100])]

    log.info(f"Available signals: {len(signal_names)}: {signal_names}")
    log.info(f"Testing C({len(signal_names)},{group_size}) = "
             f"{len(list(combinations(signal_names, group_size)))} combinations")

    results = []
    for combo in combinations(signal_names, group_size):
        states = []
        for r in records:
            vec, _ = compute_state_vector(r, list(combo))
            states.append(vec)

        unique = len(set(states))
        # Entropy: how evenly distributed are the states?
        counts = Counter(states)
        probs = np.array(list(counts.values())) / len(states)
        entropy = -np.sum(probs * np.log2(probs + 1e-10))

        results.append({
            "signals": combo,
            "unique_states": unique,
            "entropy": round(entropy, 3),
            "max_possible": 3 ** group_size,
        })

    results.sort(key=lambda x: -x["entropy"])
    return results[:top_n]

# ═══════════════════════════════════════════════════════════════
# HISTORY — find past occurrences of a state
# ═══════════════════════════════════════════════════════════════
def find_state_matches(records, target_vector, signal_names):
    """Find all past segments matching a given state vector."""
    matches = []
    for r in records:
        vec, _ = compute_state_vector(r, signal_names)
        if vec == target_vector:
            matches.append({
                "timestamp": r.get("_timestamp", ""),
                "title": r.get("_title", ""),
                "category": r.get("_category", ""),
            })
    return matches

def format_state_broadcast(vector, labels, matches=None):
    """Format state vector for broadcast beat."""
    trit_str = ", ".join(
        f"{l}: {'plus' if v == 1 else 'minus' if v == -1 else 'neutral'}"
        for l, v in zip(labels, vector)
    )
    text = f"EigenTrace state vector: {trit_str}."
    if matches:
        text += (f" This exact state has occurred {len(matches)} times before. "
                f"Most recently: {matches[-1]['title'][:60]}.")
    return text


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze", action="store_true",
                        help="Find best 6 signals by state diversity")
    parser.add_argument("--current", action="store_true",
                        help="Show current state vector")
    parser.add_argument("--history", action="store_true",
                        help="Find past occurrences of current state")
    parser.add_argument("--group-size", type=int, default=6)
    args = parser.parse_args()

    if args.analyze:
        records = load_all_signals()
        log.info(f"Loaded {len(records)} segments with signals")
        best = analyze_best_signals(records, group_size=args.group_size)
        print(f"\nTop {len(best)} signal combinations (by entropy):\n")
        for i, b in enumerate(best):
            print(f"  {i+1}. entropy={b['entropy']} unique={b['unique_states']}/{b['max_possible']}")
            print(f"     signals: {', '.join(b['signals'])}")
            print()

    elif args.current or args.history:
        records = load_all_signals()
        if not records:
            print("No segments with signals found")
            exit(1)
        latest = records[-1]
        # Use all signals for now
        vec, labels = compute_state_vector(latest)
        trit_display = " ".join(f"{'+' if v==1 else '-' if v==-1 else '0'}" for v in vec)
        print(f"Story: {latest['_title'][:60]}")
        print(f"State: [{trit_display}]")
        print(f"Labels: {', '.join(labels)}")

        if args.history:
            matches = find_state_matches(records, vec, labels)
            print(f"\nExact matches in history: {len(matches)}")
            for m in matches[-5:]:
                print(f"  [{m['timestamp'][:8]}] {m['title'][:60]}")
