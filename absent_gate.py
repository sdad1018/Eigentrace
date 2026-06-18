#!/usr/bin/env python3
"""
absent_gate.py — does Summary Plus surfacing matter MORE when the EigenChing
'absent' axis says content was lost?

THE INSIGHT (from recon): every bake-off story was absent=Preserved/Partial — the
source largely survived into consensus. That's WHY the random control was close:
on Preserved stories the models already said the important things, so void-surfacing
has little to recover. We were testing the intervention on patients who weren't sick.

THE GATE HYPOTHESIS: surfacing has real uplift only when absent=Erased/Partial
(content was lost -> there's something to recover). On absent=Preserved, skip it.

THIS SCRIPT (zero model calls, pure lookup): read every story's EigenChing signature
from its state_vector beat, bucket by the 'absent' axis, and measure — for each
bucket — how RICH the void is (how much on-topic content the models omitted). If
void-richness tracks the absent axis (Erased stories have fat voids, Preserved thin),
the gate is real: surface when Erased, skip when Preserved.

Void-richness proxies (already in attribution, no models):
  - source_void.absent_count / absent ratio  (how much source vocab the models dropped)
  - void_words count
  - state_flag distribution per bucket
"""
import json, glob, os, re
from collections import defaultdict, Counter
import numpy as np

SEG="/home/remvelchio/eigentrace/tmp/segments"
AXIS_ORDER=["consensus","absent","verb_drift","entity","hedge","vix"]
# the word->value maps from eigenching.py AXES
ABSENT_WORD={"Erased":-1,"Partial":0,"Preserved":1}
# archetype name -> its absent-axis value (for stories tagged by archetype name not raw words)
ARCH_ABSENT={
    "The Still Point":0,"The Unanimous Shield":1,"The Clear Channel":1,"The Sharp Silence":-1,
    "The Polished Unity":1,"The Hollow Headline":-1,"The Named Erasure":-1,"The Phantom Chorus":1,
    "The Cornering":-1,"The Soft Consensus":1,"The Lone Wolf":1,"The Sealed Vault":-1,
    "The Quiet Cull":-1,"The Namedrop":1,"The Anonymized Drone":-1,"The Naming Battle":-1,
    "The Smoothed Pact":1,"The Split Witness":-1,"The Divided Softening":1,"The Faceless Signal":1,
    "The Open Hedge":1,"The Sealed Chorus":-1,
}

def absent_from_beat(text):
    if "EigenChing state:" not in text: return None
    tail=text.split("EigenChing state:")[1].strip()
    head=tail.split(".")[0]  # first sentence
    # case 1: archetype name ("The Unanimous Shield, fracturing...")
    name=head.split(",")[0].strip()
    if name in ARCH_ABSENT: return ARCH_ABSENT[name]
    # case 2: raw six words ("Scattered Preserved Shifted Generic Walled Breaking")
    words=name.split()
    if len(words)>=2 and words[1] in ABSENT_WORD:  # 2nd word = absent axis
        return ABSENT_WORD[words[1]]
    # also scan for any absent word
    for w,v in ABSENT_WORD.items():
        if w in head: return v
    return None

buckets=defaultdict(list)
flag_by_bucket=defaultdict(Counter)
n=0
for f in sorted(glob.glob(os.path.join(SEG,"*_segment.json")),reverse=True):
    try:
        seg=json.load(open(f)); a=seg.get("attribution",{})
        t=a.get("story_title","")
        if any(x in t.lower() for x in ["compression","governance","weekly","audit","self-audit"]): continue
        av=None
        for b in seg.get("beats",[]):
            if "state_vector" in b.get("phase",""):
                av=absent_from_beat(b.get("text","")); break
        if av is None: continue
        # void richness proxies
        sv=a.get("source_void",{}) or {}
        absent_ratio=sv.get("absent_ratio", None)
        absent_count=sv.get("absent_count", None)
        nvoid=len(a.get("void_words",[]) or [])
        rec={"title":t,"absent_ratio":absent_ratio,"absent_count":absent_count,
             "n_void":nvoid,"vix":a.get("mean_vix"),"flag":a.get("state_flag")}
        buckets[av].append(rec)
        if a.get("state_flag"): flag_by_bucket[av][a["state_flag"]]+=1
        n+=1
    except: continue

label={-1:"Erased (-1)",0:"Partial (0)",1:"Preserved (+1)"}
print(f"classified {n} stories by EigenChing 'absent' axis\n")
print(f"{'bucket':16s} {'count':>6s} {'mean absent_ratio':>18s} {'mean absent_count':>18s} {'mean n_void':>12s}")
for av in (-1,0,1):
    rs=buckets[av]
    if not rs: 
        print(f"{label[av]:16s} {0:>6d}   (none)"); continue
    ar=[r['absent_ratio'] for r in rs if r['absent_ratio'] is not None]
    ac=[r['absent_count'] for r in rs if r['absent_count'] is not None]
    nv=[r['n_void'] for r in rs]
    print(f"{label[av]:16s} {len(rs):>6d} {np.mean(ar) if ar else float('nan'):>18.3f} "
          f"{np.mean(ac) if ac else float('nan'):>18.1f} {np.mean(nv):>12.1f}")

print("\nstate_flag distribution per absent-bucket:")
for av in (-1,0,1):
    if flag_by_bucket[av]:
        print(f"  {label[av]:16s} {dict(flag_by_bucket[av])}")

print("\nbake-off stories — what was THEIR absent axis?")
TARGETS=["Trump Defends Deal","Demanded Iran","Details Agreement","Hormuz","Look Ahead to Next"]
for av in (-1,0,1):
    for r in buckets[av]:
        if any(tg in r['title'] for tg in TARGETS):
            print(f"  [{label[av]:14s}] {r['title'][:55]}  (void_words={r['n_void']}, absent_ratio={r['absent_ratio']})")

print("\nREAD: if absent_ratio / n_void RISES as we go Erased<-Partial<-Preserved is BACKWARDS;")
print("we EXPECT Erased stories to have the FATTEST voids (most omitted) and Preserved the thinnest.")
print("If so: the 'absent' axis predicts where surfacing has something to recover -> GATE IS REAL.")
print("And note: if all bake-off stories were Preserved, that explains the weak/close control.")
