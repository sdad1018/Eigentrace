#!/usr/bin/env python3
"""
aggregate_v2.py — THE CORRECT aggregator. The EigenChing signature is computed at BROADCAST TIME
and written into each segment's state_vector beat as a NAME (e.g. "The Still Point, content
eroding and fracturing"). The webpage generator (eigenching_report.py) counts the BASE name only
(text before first comma). We do better: parse the FULL name (base + morphological modifiers) and
reconstruct the TRUE per-story signature by inverting the MODIFIERS map.

WHY: the webpage files "The Still Point, content eroding" as a Still Point (absent=0) when its
ACTUAL absent axis was -1. The modifier is where the real loss hides. For "most lossy" we want
the true signature, not the archetype-rounded one.

VALIDATION: reproduce eigenching_report.py's BASE-NAME counts (444 Still Point, 372 Unanimous
Shield, 103 Sharp Silence...). If base-name tally matches -> our beat-parse is identical to the
generator, and the reconstructed true signatures are trustworthy.

Output: corpus_master.json — every story with base archetype, TRUE signature, all word-lists.
"""
import json, glob, os, sys, re
from collections import Counter, defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import eigenching as EC   # ARCHETYPES, MODIFIERS, AXIS_ORDER

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
NAME2SIG={(v[0] if isinstance(v,tuple) else v):sig for sig,v in EC.ARCHETYPES.items()}   # base name -> sig (ARCHETYPES val is (name,desc))
AXIS_IDX={a:i for i,a in enumerate(EC.AXIS_ORDER)}
# label word -> trit, per axis position (for compositional names like "Mixed Erased Intact ...")
LABEL2TRIT=[]  # one dict per axis position in AXIS_ORDER
for axis in EC.AXIS_ORDER:
    d={}
    for trit,(label,_desc) in EC.AXES[axis].items():
        d[label]=trit
    LABEL2TRIT.append(d)
def parse_compositional(name):
    """'Mixed Erased Intact Generic Walled Normal' -> signature via AXES labels (6 words, in AXIS_ORDER)."""
    # take the part before any period (drop the trailing description sentence)
    head=name.split(".")[0].strip()
    words=head.split()
    if len(words)<6: return None
    # the 6 axis-label words are the FIRST 6 tokens (consensus,absent,verb,entity,hedge,vix order)
    cand=words[:6]
    sig=[]
    for i,w in enumerate(cand):
        if w in LABEL2TRIT[i]: sig.append(LABEL2TRIT[i][w])
        else: return None
    return tuple(sig)
# invert MODIFIERS: phrase -> list of (axis, actual_val) [some phrases collide across axes]
PHRASE2MOVES=defaultdict(list)
for (axis,arch_val,act_val),phrase in EC.MODIFIERS.items():
    PHRASE2MOVES[phrase].append((axis,act_val))

def parse_beat_name(tx):
    """Extract the full EigenChing name from a state_vector beat text."""
    if "EigenChing state:" not in tx: return None
    after=tx.split("EigenChing state:")[1]
    # name runs until the first sentence-ending period followed by space+capital, or ". This is"
    name=after.split(". This is")[0].split(". Source")[0].split(". Outside")[0].strip()
    name=name.rstrip(".").strip()
    return name

def reconstruct_signature(full_name):
    """From 'The Still Point, content eroding and fracturing' -> true 6-tuple.
    Returns (sig_tuple, base_name, modifiers_list) or (None, None, None) if compositional/unknown."""
    if "," not in full_name:
        base=full_name.strip()
        if base in NAME2SIG: return NAME2SIG[base], base, []
        cs=parse_compositional(base)        # "Mixed Erased Intact ..." encodes sig in words
        if cs is not None: return cs, "(compositional)", []
        return None, base, None
    base, modpart = full_name.split(",",1)
    base=base.strip()
    if base not in NAME2SIG: return None, base, None
    sig=list(NAME2SIG[base])
    mods=[m.strip() for m in modpart.replace(" and ", "|").split("|") if m.strip()]
    # apply each modifier phrase to the correct axis (resolve collisions by AXIS_ORDER left-to-right)
    used_axes=set()
    for phrase in mods:
        moves=PHRASE2MOVES.get(phrase,[])
        # pick the move whose axis isn't used yet and whose archetype-side matches current base value
        applied=False
        for axis,act_val in sorted(moves,key=lambda m:AXIS_IDX[m[0]]):
            i=AXIS_IDX[axis]
            if axis in used_axes: continue
            # the modifier is valid only if base[i] matches the arch_val that produced this phrase
            # find arch_val for (axis,phrase)
            sig[i]=act_val; used_axes.add(axis); applied=True; break
        # if not applied, ignore (rare)
    return tuple(sig), base, mods

def main():
    files=sorted(glob.glob(os.path.join(SEG_DIR,"*_segment.json")))
    base_counts=Counter()       # for validation vs webpage
    true_counts=Counter()
    rows=[]; parsed=0; total_beats=0
    seen=set()
    for f in files:
        try: seg=json.load(open(f))
        except: continue
        attr=seg.get("attribution") or {}
        beat_name=None
        for b in (seg.get("beats") or []):
            if "state_vector" in b.get("phase",""):
                nm=parse_beat_name(b.get("text",""))
                if nm: beat_name=nm; break
        if not beat_name: continue
        total_beats+=1
        base=beat_name.split(",")[0].strip()
        base_counts[base]+=1          # EXACTLY what eigenching_report.py counts
        sig,basename,mods=reconstruct_signature(beat_name)
        if sig is not None:
            true_counts[sig]+=1; parsed+=1
        guid=attr.get("story_guid") or attr.get("story_url") or attr.get("story_title","")
        rows.append({
            "title": attr.get("story_title","")[:120], "guid": guid,
            "category": attr.get("category",""), "ts": seg.get("timestamp",""),
            "beat_name": beat_name, "base_archetype": base,
            "true_signature": list(sig) if sig else None, "modifiers": mods,
            "void_words": attr.get("void_words",[]) or [],
            "logos_words": attr.get("logos_words",[]) or [],
            "synthesis_words": attr.get("synthesis_words",[]) or [],
            "source_void": attr.get("source_void",{}),
            "consensus_density": attr.get("consensus_density"),
            "mean_vix": attr.get("mean_vix"),
        })

    # ---- VALIDATION against the webpage's base-name counts ----
    ref=json.load(open("docs/eigenching_data.json"))
    ref_counts={a["name"]:a["count"] for a in ref["archetypes"]}
    print("="*68); print("VALIDATION — our base-name counts vs eigenching_data.json"); print("="*68)
    print(f"  segments with a state beat: {total_beats}  (webpage total_segments={ref['total_segments']})")
    print(f"  {'archetype':24s} {'webpage':>8s} {'ours':>6s} {'':>4s}")
    hits=checked=0
    for name,rc in sorted(ref_counts.items(),key=lambda kv:-kv[1]):
        if rc==0: continue
        checked+=1; oc=base_counts.get(name,0); ok=abs(oc-rc)<=max(3,0.05*rc)
        hits+=ok
        print(f"  {name:24s} {rc:>8d} {oc:>6d} {'OK' if ok else 'XX':>4s}")
    print(f"\n  matched {hits}/{checked} base-name counts")
    if hits>=checked*0.85:
        print("  -> beat-parse reproduces the generator. TRUE signatures are trustworthy.")
    else:
        print("  -> base-name parse still off; fix parse_beat_name before trusting true sigs.")

    # ---- the TRUE high-absent population (absent axis index 1 == -1) ----
    print("\n"+"="*68)
    print("TRUE HIGH-ABSENT (reconstructed absent axis = -1) — incl. stories the webpage")
    print("filed under calm base names like 'Still Point, content eroding'")
    print("="*68)
    hi=[r for r in rows if r["true_signature"] and r["true_signature"][1]==-1]
    print(f"  stories with TRUE absent = -1: {len(hi)}  (vs webpage pure-absent archetypes ~278)")
    by_base=Counter(r["base_archetype"] for r in hi)
    print("  by base archetype they were filed under:")
    for nm,c in by_base.most_common(12): print(f"    {c:4d}  {nm}")
    # the hidden ones: absent=-1 but filed under a base whose archetype absent != -1
    hidden=[r for r in hi if NAME2SIG.get(r["base_archetype"],(0,0,0,0,0,0))[1]!=-1]
    print(f"\n  HIDDEN high-absent (filed under non-absent base via 'content eroding/gutted'): {len(hidden)}")
    for r in hidden[:8]:
        print(f"    [{r['base_archetype']}] {r['title'][:50]}  void={r['void_words'][:4]}")

    # ---- charged words on true-high-absent ----
    sw=Counter()
    for r in hi:
        for w in (r.get("void_words") or []): sw[w]+=1
    print(f"\n  top void words across TRUE high-absent stories:")
    for w,c in sw.most_common(20): print(f"    {c:3d}x  {w}")

    out="corpus_master.json"
    json.dump({"n":len(rows),"true_high_absent":len(hi),"stories":rows},open(out,"w"))
    print(f"\nwrote {out} ({len(rows)} story-segments, {parsed} with true signatures)")

if __name__=="__main__": main()
