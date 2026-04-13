#!/usr/bin/env python3
"""context_swerve.py — Measure context-dependent suppression patterns.

Proves RLHF operates as context-activated suppression, not static word filter.
Words flip between void and present depending on story context.

Usage: python3 context_swerve.py [--top N] [--min-void N] [--min-present N]
"""
import json, glob, argparse
from collections import defaultdict

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"

def analyze(n_segments=500, min_void=3, min_present=3, top_n=25):
    word_void = defaultdict(int)
    word_present = defaultdict(int)
    word_void_stories = defaultdict(list)
    word_present_stories = defaultdict(list)

    files = sorted(glob.glob(f"{SEGMENT_DIR}/*_segment.json"))
    for f in files[-n_segments:]:
        try:
            d = json.load(open(f))
            attr = d.get("attribution", {})
            title = attr.get("story_title", "")
            void_words = set(attr.get("void_words", []))
            resp = " ".join(v.lower() for v in attr.get("model_responses", {}).values() if v)
            for w in void_words:
                word_void[w] += 1
                word_void_stories[w].append(title[:40])
            for w in word_void:
                if w.lower() in resp:
                    word_present[w] += 1
                    if title[:40] not in word_present_stories[w]:
                        word_present_stories[w].append(title[:40])
        except:
            continue

    results = []
    for w in word_void:
        v, p = word_void[w], word_present[w]
        if v >= min_void and p >= min_present:
            results.append({
                "word": w,
                "void_count": v,
                "present_count": p,
                "context_ratio": round(p / (v + p), 3),
                "void_stories": word_void_stories[w][:3],
                "present_stories": word_present_stories[w][:3],
            })
    results.sort(key=lambda x: -x["void_count"])
    return results[:top_n]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--min-void", type=int, default=3)
    parser.add_argument("--min-present", type=int, default=3)
    args = parser.parse_args()

    results = analyze(top_n=args.top, min_void=args.min_void, min_present=args.min_present)
    print(f"Context-Dependent Suppression Analysis")
    print(f"{'Word':20s} {'Void':>5s} {'Present':>8s} {'Swerve':>8s}")
    print("-" * 45)
    for r in results:
        print(f"{r['word']:20s} {r['void_count']:5d} {r['present_count']:8d} {r['context_ratio']:8.1%}")
