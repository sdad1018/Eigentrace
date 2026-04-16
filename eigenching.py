#!/usr/bin/env python3
"""
eigenching.py — 729-state archetype system for EigenTrace
==========================================================
Maps each ternary state vector to a named archetype with meaning.

The 6 axes, each {-1, 0, +1}:
  1. consensus    — how unified the models are
  2. absent       — what percentage of source survived
  3. verb_drift   — softening of action language
  4. entity       — did names survive
  5. hedge        — attribution buffering level
  6. vix_spread   — how much one model broke ranks

Names are compositional: derived from the signature, not looked up.
"""

import json, glob, os
from collections import Counter
from datetime import datetime

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"

# ═══════════════════════════════════════════════════════════════
# AXIS VOCABULARY — each axis has 3 poles with evocative names
# ═══════════════════════════════════════════════════════════════
AXES = {
    "consensus": {
        -1: ("Scattered",  "models disagree broadly"),
         0: ("Mixed",      "partial agreement"),
        +1: ("Unified",    "models move in lockstep"),
    },
    "absent": {
        -1: ("Erased",     "source words mostly lost"),
         0: ("Partial",    "moderate loss"),
        +1: ("Preserved",  "source survived mostly intact"),
    },
    "verb_drift": {
        -1: ("Softened",   "action language downgraded"),
         0: ("Shifted",    "mild linguistic smoothing"),
        +1: ("Intact",     "verbs preserved with force"),
    },
    "entity": {
        -1: ("Nameless",   "proper nouns dropped"),
         0: ("Generic",    "some names abstracted"),
        +1: ("Named",      "entities preserved sharply"),
    },
    "hedge": {
        -1: ("Walled",     "attribution buffering high"),
         0: ("Moderate",   "normal hedging"),
        +1: ("Direct",     "claims made without buffer"),
    },
    "vix": {
        -1: ("Breaking",   "one model diverges sharply"),
         0: ("Normal",     "typical spread across models"),
        +1: ("Tight",      "all models close in tension"),
    },
}

# ═══════════════════════════════════════════════════════════════
# ARCHETYPE NAMES — 64 named combinations at the extremes
# 
# Named states have all-extreme signatures (no zeros). 
# The 64 extreme states (2^6) get archetypal names. 
# The other 665 states (mixed with zeros) get compositional names.
# ═══════════════════════════════════════════════════════════════
ARCHETYPES = {
    # (consensus, absent, verb, entity, hedge, vix): (name, description)
    # All +1: maximum health
    ( 1, 1, 1, 1, 1, 1): ("The Clear Channel",
        "Signal passes through all five models with minimal shaping. Rare."),
    # All -1: maximum suppression
    (-1,-1,-1,-1,-1,-1): ("The Sealed Vault",
        "Total compression. Models agree to erase, soften, abstract, and hedge. The signal is gone."),
    
    # High-consensus suppression patterns
    ( 1,-1,-1,-1,-1,-1): ("The Sealed Chorus",
        "Unified heavy compression with tight spread. All models agree on what to remove. Consensus of omission."),
    ( 1,-1,-1,-1,-1, 1): ("The Cornering",
        "Models lockstep on compression. The narrowness of agreement is itself a signal."),
    ( 1,-1,-1,-1, 1,-1): ("The Quiet Cull",
        "Direct but compressed. Models don't hedge — they just leave things out."),
    ( 1,-1,-1, 1,-1,-1): ("The Anonymized Drone",
        "Names survive but everything else is softened and hedged. The story gets told about 'officials.'"),
    ( 1,-1, 1,-1,-1,-1): ("The Named Erasure",
        "Entities named but surrounded by hedging. Who did it is clear; what they did is fuzzy."),
    ( 1, 1,-1,-1,-1,-1): ("The Soft Consensus",
        "Source preserved but delivery softened. The facts are there, muted."),
    
    # Low-consensus disagreement patterns
    (-1, 1, 1, 1, 1, 1): ("The Open Field",
        "Models disagree but each preserves. No collective suppression — just divergent takes."),
    (-1,-1,-1,-1,-1, 1): ("The Panicked Hush",
        "Models disagree on what to compress but all compress. Signal of confused alignment."),
    (-1, 1, 1, 1, 1,-1): ("The Lone Wolf",
        "One model breaks from the pack. Others preserve. Worth investigating the outlier."),
    (-1,-1, 1, 1, 1, 1): ("The Scatter Signal",
        "Disagreement on framing but nobody drops content. Healthy diversity."),
    
    # Mixed patterns at extremes
    ( 1, 1, 1, 1,-1,-1): ("The Unanimous Shield",
        "All models agree, preserve content, but wall it in attribution. Liability-aware reporting."),
    ( 1, 1,-1, 1,-1, 1): ("The Polished Unity",
        "Smooth agreement. Facts preserved, language softened, claims buffered. Press-release voice."),
    (-1, 1,-1, 1, 1, 1): ("The Open Hedge",
        "Models disagree on tone but share directness. Mixed signals."),
    ( 1,-1, 1, 1,-1, 1): ("The Sharp Silence",
        "Names kept, verbs kept, hedges dropped — but content gone. The skeleton without meat."),
    (-1, 1, 1,-1,-1, 1): ("The Phantom Chorus",
        "Content preserved but entities dropped across all models. Who did what, unnamed."),
    ( 1, 1, 1,-1, 1, 1): ("The Namedrop",
        "Everything survives except the people. Story intact, actors abstract."),
    (-1,-1, 1, 1, 1,-1): ("The Split Witness",
        "One model sees differently. Others preserve but differ on compression."),
    ( 1,-1, 1,-1, 1, 1): ("The Hollow Headline",
        "Names and hedges match, but content and entities go. Shape without substance."),
    (-1, 1,-1,-1, 1,-1): ("The Divided Softening",
        "Split disagreement with softening. Models hedge differently."),
    ( 1, 1,-1,-1, 1, 1): ("The Smoothed Pact",
        "Content preserved, entities abstracted, tone softened. Agreed diplomatic register."),
    (-1,-1, 1,-1,-1,-1): ("The Naming Battle",
        "Models scatter on everything except keeping verbs. Who is active is agreed; who they are is not."),
    ( 1, 1, 1, 1, 1,-1): ("The One Outlier",
        "Everything clean except one model runs hot. Watch the outlier."),
    (-1,-1,-1, 1,-1, 1): ("The Entity Refuge",
        "Total compression except names survive. The story is gone but the actors remain."),
    ( 1,-1,-1, 1, 1,-1): ("The Sharp Cornering",
        "Named, direct, but everything else compressed. One model breaks."),
    (-1, 1, 1,-1, 1,-1): ("The Faceless Signal",
        "Content survives, entities erased, one model breaks. Who-dunnit unknown."),
    ( 1, 1,-1, 1, 1,-1): ("The Gentle Break",
        "Mostly healthy but softened with one divergent model. Subtle dissent."),
    (-1,-1, 1, 1,-1, 1): ("The Buffered Scatter",
        "Models scatter with hedges. Even the disagreement is qualified."),
    ( 1,-1, 1, 1, 1,-1): ("The Clean Compression",
        "Everything sharp and named but compressed. Surgical editing with one break."),
    (-1, 1,-1,-1,-1, 1): ("The Uneasy Unity",
        "Tight spread but models disagree. Tension without divergence."),
}

def _generate_full_taxonomy():
    """Generate names for all 729 states compositionally."""
    taxonomy = {}
    axis_order = ["consensus", "absent", "verb_drift", "entity", "hedge", "vix"]
    
    for c in (-1, 0, 1):
        for a in (-1, 0, 1):
            for v in (-1, 0, 1):
                for e in (-1, 0, 1):
                    for h in (-1, 0, 1):
                        for x in (-1, 0, 1):
                            sig = (c, a, v, e, h, x)
                            # Check if it's a named archetype
                            if sig in ARCHETYPES:
                                name, desc = ARCHETYPES[sig]
                                taxonomy[sig] = {
                                    "name": name,
                                    "description": desc,
                                    "tier": "archetype",
                                }
                            else:
                                # Compositional name from axes
                                parts = []
                                for axis, val in zip(axis_order, sig):
                                    if axis == "verb_drift":
                                        axis_key = "verb_drift"
                                    else:
                                        axis_key = axis
                                    label = AXES[axis_key][val][0]
                                    parts.append(label)
                                name = " ".join(parts)
                                # Count zeros to determine tier
                                zeros = sum(1 for x in sig if x == 0)
                                if zeros == 0:
                                    tier = "extreme"
                                elif zeros >= 4:
                                    tier = "typical"
                                else:
                                    tier = "mixed"
                                # Describe
                                nonzero = [(k, v) for k, v in zip(axis_order, sig) if v != 0]
                                if not nonzero:
                                    desc = "Perfect balance across all axes. The silent state."
                                else:
                                    desc_parts = []
                                    for axis, val in nonzero[:3]:
                                        label, meaning = AXES[axis][val]
                                        desc_parts.append(meaning)
                                    desc = "; ".join(desc_parts).capitalize() + "."
                                taxonomy[sig] = {
                                    "name": name,
                                    "description": desc,
                                    "tier": tier,
                                }
    return taxonomy

# Build once at import
TAXONOMY = _generate_full_taxonomy()

# The silent state gets its own treatment
TAXONOMY[(0,0,0,0,0,0)] = {
    "name": "The Still Point",
    "description": "Perfect equilibrium across all six axes. The broadcast's empty center — rare, eerie, meaningful.",
    "tier": "archetype",
}


def classify(signature):
    """Return full classification for a 6-trit signature."""
    if isinstance(signature, list):
        signature = tuple(signature)
    entry = TAXONOMY.get(signature)
    if not entry:
        return {"name": "Unknown", "description": "Signature out of range.", "tier": "error"}
    return entry


def format_broadcast(signature, matches=None, total_seen=0):
    """Format the EigenChing state for broadcast beat 18b."""
    entry = classify(signature)
    name = entry["name"]
    desc = entry["description"]
    tier = entry["tier"]
    
    text = f"EigenChing state: {name}. {desc}"
    
    if tier == "archetype":
        text += " This is a named archetype."
    
    if matches is not None:
        n = len(matches) if isinstance(matches, list) else matches
        if n == 0:
            text += " This state has never been observed before. Novel signature."
        elif n == 1:
            text += f" First observation of this state."
        else:
            text += f" Observed {n} times across {total_seen} stories."
            if isinstance(matches, list) and matches:
                last = matches[-1]
                if last.get("title"):
                    text += f" Last seen in coverage of: {last['title'][:60]}."
    
    return text


# ═══════════════════════════════════════════════════════════════
# DEMO / TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Show all archetypes")
    parser.add_argument("--simulate", action="store_true", help="Simulate stories")
    parser.add_argument("--stats", action="store_true", help="Taxonomy statistics")
    args = parser.parse_args()
    
    if args.stats:
        tiers = Counter(v["tier"] for v in TAXONOMY.values())
        print(f"Total states: {len(TAXONOMY)} / 729")
        print(f"By tier: {dict(tiers)}")
        print()
    
    if args.test:
        print("=" * 70)
        print("NAMED ARCHETYPES")
        print("=" * 70)
        for sig, entry in sorted(TAXONOMY.items(), key=lambda x: x[1]["tier"]):
            if entry["tier"] == "archetype":
                print(f"{sig}")
                print(f"  {entry['name']}")
                print(f"  {entry['description']}")
                print()
    
    if args.simulate:
        # Simulate realistic news scenarios
        scenarios = [
            {
                "title": "US airstrike kills IRGC commander",
                "sig": (1, -1, -1, 1, -1, -1),  # unified, erased, softened, named, walled, breaking
                "note": "High-sensitivity military story"
            },
            {
                "title": "Cat stuck in tree rescued by firefighters",
                "sig": (0, 1, 1, 1, 1, 0),  # neutral, preserved, intact, named, direct, normal
                "note": "Low-sensitivity human interest"
            },
            {
                "title": "Presidential primary results announced",
                "sig": (1, 1, 0, 1, -1, 0),  # unified, preserved, neutral, named, walled, normal
                "note": "Political reporting"
            },
            {
                "title": "Supreme Court rules on abortion case",
                "sig": (-1, -1, -1, -1, -1, -1),
                "note": "Maximum suppression candidate"
            },
            {
                "title": "Tech company quarterly earnings beat",
                "sig": (1, 1, 1, 1, 1, 1),
                "note": "Clean signal candidate"
            },
            {
                "title": "Climate report shows record temperatures",
                "sig": (1, 0, -1, 0, -1, 0),
                "note": "Science + policy"
            },
            {
                "title": "Sports team wins championship",
                "sig": (1, 1, 1, 1, 1, 0),
                "note": "Low-stakes"
            },
            {
                "title": "Ceasefire negotiations stalled",
                "sig": (-1, -1, -1, 1, -1, 1),
                "note": "Geopolitical"
            },
        ]
        
        print("=" * 70)
        print("SIMULATED BROADCAST BEATS")
        print("=" * 70)
        for s in scenarios:
            print(f"\nStory: {s['title']}")
            print(f"  ({s['note']})")
            print(f"  Signature: {s['sig']}")
            print(f"  Broadcast:")
            print(f"    {format_broadcast(s['sig'], matches=[], total_seen=9312)}")
