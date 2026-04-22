#!/usr/bin/env python3
"""Generate eigenching_data.json for the website."""
import json, glob, os
from collections import Counter, defaultdict

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
ARCHETYPES = {
    ( 1, 1, 1, 1, 1, 1): "The Clear Channel",
    (-1,-1,-1,-1,-1,-1): "The Sealed Vault",
    ( 1,-1,-1,-1,-1,-1): "The Sealed Chorus",
    ( 1,-1,-1,-1,-1, 1): "The Cornering",
    ( 1,-1,-1,-1, 1,-1): "The Quiet Cull",
    ( 1,-1,-1, 1,-1,-1): "The Anonymized Drone",
    ( 1,-1, 1,-1,-1,-1): "The Named Erasure",
    ( 1, 1,-1,-1,-1,-1): "The Soft Consensus",
    (-1, 1, 1, 1, 1, 1): "The Open Field",
    (-1,-1,-1,-1,-1, 1): "The Panicked Hush",
    (-1, 1, 1, 1, 1,-1): "The Lone Wolf",
    (-1,-1, 1, 1, 1, 1): "The Scatter Signal",
    ( 1, 1, 1, 1,-1,-1): "The Unanimous Shield",
    ( 1, 1,-1, 1,-1, 1): "The Polished Unity",
    (-1, 1,-1, 1, 1, 1): "The Open Hedge",
    ( 1,-1, 1, 1,-1, 1): "The Sharp Silence",
    (-1, 1, 1,-1,-1, 1): "The Phantom Chorus",
    ( 1, 1, 1,-1, 1, 1): "The Namedrop",
    (-1,-1, 1, 1, 1,-1): "The Split Witness",
    ( 1,-1, 1,-1, 1, 1): "The Hollow Headline",
    (-1, 1,-1,-1, 1,-1): "The Divided Softening",
    ( 1, 1,-1,-1, 1, 1): "The Smoothed Pact",
    (-1,-1, 1,-1,-1,-1): "The Naming Battle",
    ( 1, 1, 1, 1, 1,-1): "The One Outlier",
    (-1,-1,-1, 1,-1, 1): "The Entity Refuge",
    ( 1,-1,-1, 1, 1,-1): "The Sharp Cornering",
    (-1, 1, 1,-1, 1,-1): "The Faceless Signal",
    ( 1, 1,-1, 1, 1,-1): "The Gentle Break",
    (-1,-1, 1, 1,-1, 1): "The Buffered Scatter",
    ( 1,-1, 1, 1, 1,-1): "The Clean Compression",
    (-1, 1,-1,-1,-1, 1): "The Uneasy Unity",
    ( 0, 0, 0, 0, 0, 0): "The Still Point",
}

DESCRIPTIONS = {
    "The Clear Channel": "Signal passes through all five models with minimal shaping. Rare.",
    "The Sealed Vault": "Total compression. Models agree to erase, soften, abstract, and hedge. The signal is gone.",
    "The Sealed Chorus": "Unified heavy compression with tight spread. Consensus of omission.",
    "The Cornering": "Models lockstep on compression. The narrowness of agreement is itself a signal.",
    "The Quiet Cull": "Direct but compressed. Models don't hedge, they just leave things out.",
    "The Anonymized Drone": "Names survive but everything else is softened and hedged.",
    "The Named Erasure": "Entities named but surrounded by hedging. Who did it is clear; what they did is fuzzy.",
    "The Soft Consensus": "Source preserved but delivery softened. The facts are there, muted.",
    "The Open Field": "Models disagree but each preserves. No collective suppression, just divergent takes.",
    "The Panicked Hush": "Models disagree on what to compress but all compress. Confused alignment.",
    "The Lone Wolf": "One model breaks from the pack. Others preserve. Worth investigating the outlier.",
    "The Scatter Signal": "Disagreement on framing but nobody drops content. Healthy diversity.",
    "The Unanimous Shield": "All models agree, preserve content, but wall it in attribution. Liability-aware.",
    "The Polished Unity": "Smooth agreement. Facts preserved, language softened, claims buffered.",
    "The Open Hedge": "Models disagree on tone but share directness. Mixed signals.",
    "The Sharp Silence": "Names kept, verbs kept, hedges dropped, but content gone. Skeleton without meat.",
    "The Phantom Chorus": "Content preserved but entities dropped across all models. Who did what, unnamed.",
    "The Namedrop": "Everything survives except the people. Story intact, actors abstract.",
    "The Split Witness": "One model sees differently. Others preserve but differ on compression.",
    "The Hollow Headline": "Names and hedges match, but content and entities go. Shape without substance.",
    "The Divided Softening": "Split disagreement with softening. Models hedge differently.",
    "The Smoothed Pact": "Content preserved, entities abstracted, tone softened. Diplomatic register.",
    "The Naming Battle": "Models scatter on everything except keeping verbs.",
    "The One Outlier": "Everything clean except one model runs hot. Watch the outlier.",
    "The Entity Refuge": "Total compression except names survive. The story is gone but the actors remain.",
    "The Sharp Cornering": "Named, direct, but everything else compressed. One model breaks.",
    "The Faceless Signal": "Content survives, entities erased, one model breaks.",
    "The Gentle Break": "Mostly healthy but softened with one divergent model. Subtle dissent.",
    "The Buffered Scatter": "Models scatter with hedges. Even the disagreement is qualified.",
    "The Clean Compression": "Everything sharp and named but compressed. Surgical editing with one break.",
    "The Uneasy Unity": "Tight spread but models disagree. Tension without divergence.",
    "The Still Point": "Perfect equilibrium across all six axes. The broadcast's empty center.",
}

def generate_report():
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")))
    counts = Counter()
    examples = defaultdict(list)
    total = 0

    for f in files:
        try:
            seg = json.load(open(f))
            for b in seg.get("beats", []):
                if "state_vector" in b.get("phase", ""):
                    text = b.get("text", "")
                    if "EigenChing state:" in text:
                        name = text.split("EigenChing state:")[1].split(",")[0].strip()
                        title = seg.get("attribution", {}).get("story_title", "Unknown")
                        counts[name] += 1
                        total += 1
                        if len(examples[name]) < 3:
                            examples[name].append(title[:80])
        except:
            continue

    archetypes = []
    for sig, name in sorted(ARCHETYPES.items(), key=lambda x: -counts.get(x[1], 0)):
        archetypes.append({
            "name": name,
            "signature": list(sig),
            "count": counts.get(name, 0),
            "pct": round(counts.get(name, 0) / max(total, 1) * 100, 1),
            "description": DESCRIPTIONS.get(name, ""),
            "examples": examples.get(name, []),
        })

    report = {
        "total_segments": total,
        "total_files": len(files),
        "generated": __import__("datetime").datetime.utcnow().isoformat(),
        "archetypes": archetypes,
    }

    out = "/mnt/c/Users/M4ISI/eigentrace/docs/eigenching_data.json"
    json.dump(report, open(out, "w"), indent=2)
    print(f"EigenChing report: {total} segments, {sum(1 for a in archetypes if a['count'] > 0)} archetypes observed")
    return report

if __name__ == "__main__":
    generate_report()
