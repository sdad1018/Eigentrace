#!/usr/bin/env python3
"""
eigenching.py — 729-state archetype system for EigenTrace
==========================================================

Each news story classifies into one of 729 ternary states.
32 states have hand-written archetype names and meanings.
Other states get morphological names derived from nearest archetype.
Novelty detector flags genuinely interesting patterns vs statistical noise.

Axes (each -1/0/+1):
  1. consensus    — how unified the models are
  2. absent       — what percentage of source survived
  3. verb_drift   — softening of action language
  4. entity       — did names survive
  5. hedge        — attribution buffering level
  6. vix_spread   — how much one model broke ranks
"""

import json, glob, os
from collections import Counter
from datetime import datetime

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
AXIS_ORDER = ["consensus", "absent", "verb_drift", "entity", "hedge", "vix"]

# ═══════════════════════════════════════════════════════════════
# AXIS VOCABULARY
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
# ARCHETYPE DEFINITIONS (32 named patterns)
# ═══════════════════════════════════════════════════════════════
ARCHETYPES = {
    ( 1, 1, 1, 1, 1, 1): ("The Clear Channel",
        "Signal passes through all five models with minimal shaping. Rare."),
    (-1,-1,-1,-1,-1,-1): ("The Sealed Vault",
        "Total compression. Models agree to erase, soften, abstract, and hedge. The signal is gone."),
    ( 1,-1,-1,-1,-1,-1): ("The Sealed Chorus",
        "Unified heavy compression with tight spread. All models agree on what to remove. Consensus of omission."),
    ( 1,-1,-1,-1,-1, 1): ("The Cornering",
        "Models lockstep on compression. The narrowness of agreement is itself a signal."),
    ( 1,-1,-1,-1, 1,-1): ("The Quiet Cull",
        "Direct but compressed. Models dont hedge, they just leave things out."),
    ( 1,-1,-1, 1,-1,-1): ("The Anonymized Drone",
        "Names survive but everything else is softened and hedged. The story gets told about officials."),
    ( 1,-1, 1,-1,-1,-1): ("The Named Erasure",
        "Entities named but surrounded by hedging. Who did it is clear; what they did is fuzzy."),
    ( 1, 1,-1,-1,-1,-1): ("The Soft Consensus",
        "Source preserved but delivery softened. The facts are there, muted."),
    (-1, 1, 1, 1, 1, 1): ("The Open Field",
        "Models disagree but each preserves. No collective suppression, just divergent takes."),
    (-1,-1,-1,-1,-1, 1): ("The Panicked Hush",
        "Models disagree on what to compress but all compress. Signal of confused alignment."),
    (-1, 1, 1, 1, 1,-1): ("The Lone Wolf",
        "One model breaks from the pack. Others preserve. Worth investigating the outlier."),
    (-1,-1, 1, 1, 1, 1): ("The Scatter Signal",
        "Disagreement on framing but nobody drops content. Healthy diversity."),
    ( 1, 1, 1, 1,-1,-1): ("The Unanimous Shield",
        "All models agree, preserve content, but wall it in attribution. Liability-aware reporting."),
    ( 1, 1,-1, 1,-1, 1): ("The Polished Unity",
        "Smooth agreement. Facts preserved, language softened, claims buffered. Press-release voice."),
    (-1, 1,-1, 1, 1, 1): ("The Open Hedge",
        "Models disagree on tone but share directness. Mixed signals."),
    ( 1,-1, 1, 1,-1, 1): ("The Sharp Silence",
        "Names kept, verbs kept, hedges dropped, but content gone. The skeleton without meat."),
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
    ( 0, 0, 0, 0, 0, 0): ("The Still Point",
        "Perfect equilibrium across all six axes. The broadcasts empty center, rare, eerie, meaningful."),
}

# ═══════════════════════════════════════════════════════════════
# MORPHOLOGY — modifier strings for axis flips from archetype
# ═══════════════════════════════════════════════════════════════
MODIFIERS = {
    # (axis, archetype_val, actual_val) -> modifier phrase
    ("consensus",  -1,  0): "consensus forming",
    ("consensus",  -1,  1): "now unified",
    ("consensus",   0, -1): "scattering",
    ("consensus",   0,  1): "unifying",
    ("consensus",   1,  0): "fracturing",
    ("consensus",   1, -1): "broken apart",
    
    ("absent",     -1,  0): "partially recovered",
    ("absent",     -1,  1): "source surviving",
    ("absent",      0, -1): "content eroding",
    ("absent",      0,  1): "source holding",
    ("absent",      1,  0): "partial loss",
    ("absent",      1, -1): "content gutted",
    
    ("verb_drift", -1,  0): "verbs steadying",
    ("verb_drift", -1,  1): "verbs recovering",
    ("verb_drift",  0, -1): "verbs softening",
    ("verb_drift",  0,  1): "verbs sharpening",
    ("verb_drift",  1,  0): "verbs drifting",
    ("verb_drift",  1, -1): "verbs lost",
    
    ("entity",     -1,  0): "names resurfacing",
    ("entity",     -1,  1): "with names",
    ("entity",      0, -1): "names dropped",
    ("entity",      0,  1): "names retained",
    ("entity",      1,  0): "names fading",
    ("entity",      1, -1): "names erased",
    
    ("hedge",      -1,  0): "hedges easing",
    ("hedge",      -1,  1): "hedges gone",
    ("hedge",       0, -1): "hedging harder",
    ("hedge",       0,  1): "going direct",
    ("hedge",       1,  0): "hedges returning",
    ("hedge",       1, -1): "over-buffered",
    
    ("vix",        -1,  0): "divergence calming",
    ("vix",        -1,  1): "now tightening",
    ("vix",         0, -1): "fracturing",
    ("vix",         0,  1): "tightening",
    ("vix",         1,  0): "loosening",
    ("vix",         1, -1): "breaking apart",
}

# ═══════════════════════════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════════════════════════
def _hamming(a, b):
    """Count axes that differ between two signatures."""
    return sum(1 for x, y in zip(a, b) if x != y)

def _nearest_archetype(signature, archetype_frequency=None):
    """Find nearest named archetype by Hamming distance.
    Break ties by archetype frequency (more common wins)."""
    best = None
    best_dist = 999
    best_count = -1
    for arch_sig in ARCHETYPES:
        d = _hamming(signature, arch_sig)
        count = (archetype_frequency or {}).get(arch_sig, 0)
        if d < best_dist or (d == best_dist and count > best_count):
            best = arch_sig
            best_dist = d
            best_count = count
    return best, best_dist

def _modifier_phrase(signature, archetype_sig):
    """Build modifier string from axes that differ."""
    mods = []
    for i, axis in enumerate(AXIS_ORDER):
        if signature[i] != archetype_sig[i]:
            phrase = MODIFIERS.get((axis, archetype_sig[i], signature[i]))
            if phrase:
                mods.append(phrase)
    return mods

def classify(signature, archetype_frequency=None):
    """Return full classification with morphological naming.
    
    Distance 0: pure archetype
    Distance 1: "{Archetype}, {modifier}"
    Distance 2: "{Archetype}, {mod1} and {mod2}"
    Distance 3+: compositional name (no archetype claim)
    """
    if isinstance(signature, list):
        signature = tuple(signature)
    
    # Direct archetype hit
    if signature in ARCHETYPES:
        name, desc = ARCHETYPES[signature]
        return {
            "name": name,
            "description": desc,
            "tier": "archetype",
            "archetype_sig": signature,
            "archetype_name": name,
            "archetype_description": desc,
            "distance": 0,
            "modifiers": [],
        }
    
    # Find nearest archetype
    nearest_sig, distance = _nearest_archetype(signature, archetype_frequency)
    nearest_name, nearest_desc = ARCHETYPES[nearest_sig]
    
    if distance <= 2:
        mods = _modifier_phrase(signature, nearest_sig)
        if distance == 1:
            full_name = f"{nearest_name}, {mods[0]}" if mods else nearest_name
            tier = "variant"
        else:  # distance 2
            if len(mods) == 2:
                full_name = f"{nearest_name}, {mods[0]} and {mods[1]}"
            elif len(mods) == 1:
                full_name = f"{nearest_name}, {mods[0]}"
            else:
                full_name = f"Partial {nearest_name}"
            tier = "cousin"
        
        return {
            "name": full_name,
            "description": nearest_desc,
            "tier": tier,
            "archetype_sig": nearest_sig,
            "archetype_name": nearest_name,
            "archetype_description": nearest_desc,
            "distance": distance,
            "modifiers": mods,
        }
    
    # Distance 3+: compositional name, no archetype claim
    parts = []
    nonzero = []
    for i, axis in enumerate(AXIS_ORDER):
        val = signature[i]
        label, meaning = AXES[axis][val]
        parts.append(label)
        if val != 0:
            nonzero.append(meaning)
    
    comp_name = " ".join(parts)
    if nonzero:
        desc = "; ".join(nonzero[:3]).capitalize() + "."
    else:
        desc = "Perfect equilibrium across all axes."
    
    return {
        "name": comp_name,
        "description": desc,
        "tier": "compositional",
        "archetype_sig": None,
        "archetype_name": None,
        "archetype_description": None,
        "distance": distance,
        "modifiers": [],
    }

# ═══════════════════════════════════════════════════════════════
# NOVELTY DETECTION
# ═══════════════════════════════════════════════════════════════
def detect_novelty(signature, state_history_counts, recent_signatures=None):
    """Classify what KIND of novelty (if any) this state represents.
    
    Returns dict with novelty_type and commentary.
    Types: 'none', 'genuine', 'returning', 'rare_territory', 'outside_taxonomy', 'boring'
    """
    if isinstance(signature, list):
        signature = tuple(signature)
    
    nonzero_count = sum(1 for v in signature if v != 0)
    count = state_history_counts.get(signature, 0)
    total = sum(state_history_counts.values())
    
    # Boring: too many zeros
    if nonzero_count < 3:
        return {"type": "boring", "commentary": ""}
    
    # Has the state ever appeared?
    if count == 0:
        # Never seen — check if its near an observed state
        min_dist = min(_hamming(signature, s) for s in state_history_counts) if state_history_counts else 6
        if min_dist == 1:
            return {"type": "boring", "commentary": ""}  # near-duplicate noise
        
        # Check distance to nearest archetype
        nearest_arch, arch_dist = _nearest_archetype(signature)
        if arch_dist >= 3:
            return {
                "type": "outside_taxonomy",
                "commentary": "This state sits outside the named archetype territory. No hand-written pattern matches within reach. Genuinely novel shape."
            }
        return {
            "type": "genuine",
            "commentary": f"Novel signature. This exact state has never been observed in {total} stories."
        }
    
    # Returning states
    if count < 5:
        if recent_signatures and signature not in recent_signatures:
            return {
                "type": "returning",
                "commentary": f"Rare state reactivating. Seen only {count} time{'s' if count > 1 else ''} ever. Last appearance predates recent coverage."
            }
        return {
            "type": "rare_territory",
            "commentary": f"Rare state. Observed {count} time{'s' if count > 1 else ''} in {total} stories."
        }
    
    return {"type": "none", "commentary": ""}

# ═══════════════════════════════════════════════════════════════
# BROADCAST FORMATTING
# ═══════════════════════════════════════════════════════════════
def format_broadcast(signature, matches=None, total_seen=0,
                     state_history_counts=None, recent_signatures=None):
    """Format EigenChing state for broadcast beat 18b."""
    entry = classify(signature)
    name = entry["name"]
    desc = entry["description"]
    tier = entry["tier"]
    
    text = f"EigenChing state: {name}. "
    
    # For variants, remind listener what the base archetype means
    if tier == "variant" or tier == "cousin":
        arch_name = entry["archetype_name"]
        arch_desc = entry["archetype_description"]
        text += f"This is {arch_name} pattern — {arch_desc} "
        if entry["modifiers"]:
            mod_str = " and ".join(entry["modifiers"])
            # Avoid double "with" if modifier starts with "with"
            if mod_str.startswith("with "):
                text += f"This time, {mod_str}. "
            else:
                text += f"But {mod_str} this time. "
    else:
        text += f"{desc} "
    
    if tier == "archetype":
        text += "Named archetype. "
    elif tier == "compositional":
        text += "Outside named territory. "
    
    # Historical context
    if matches is not None:
        n = len(matches) if isinstance(matches, list) else matches
        if n > 1:
            text += f"Observed {n} times in {total_seen} stories. "
            if isinstance(matches, list) and matches:
                last = matches[-1]
                if last.get("title"):
                    text += f"Last seen: {last['title'][:60]}. "
    
    # Novelty commentary
    if state_history_counts:
        novelty = detect_novelty(signature, state_history_counts, recent_signatures)
        if novelty["commentary"]:
            text += novelty["commentary"]
    
    return text.strip()

# ═══════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse, random
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    
    if args.stats:
        print(f"Named archetypes: {len(ARCHETYPES)}")
        print(f"Modifiers defined: {len(MODIFIERS)}")
        print()
    
    if args.simulate:
        # Load real history
        try:
            import state_vector
            _all = state_vector.load_all_signals()
            best6 = ["consensus_density", "absent_ratio", "verb_drift",
                     "entity_retention", "hedge_count", "mean_vix"]
            history = Counter()
            for r in _all:
                vec, _ = state_vector.compute_state_vector(r, best6)
                history[vec] += 1
            print(f"History loaded: {len(_all)} stories, {len(history)} unique states")
            print()
        except Exception as e:
            print(f"Could not load history: {e}")
            history = Counter()
        
        scenarios = [
            ("Pure Cornering", (1, -1, -1, -1, -1, 1)),
            ("Cornering with names", (1, -1, -1, 1, -1, 1)),
            ("Cornering, verbs recovering", (1, -1, 0, -1, -1, 1)),
            ("Partial Cornering", (1, -1, -1, -1, 0, 0)),
            ("Far from any archetype", (0, 0, -1, 0, 0, 1)),
            ("Pure Sealed Vault", (-1, -1, -1, -1, -1, -1)),
            ("Pure Clear Channel", (1, 1, 1, 1, 1, 1)),
        ]
        
        for label, sig in scenarios:
            print(f"--- {label} ---")
            print(f"Signature: {sig}")
            result = classify(sig)
            print(f"Name: {result['name']}")
            print(f"Tier: {result['tier']} (distance {result['distance']})")
            print(f"Broadcast: {format_broadcast(sig, matches=[], total_seen=6515, state_history_counts=history)}")
            print()
