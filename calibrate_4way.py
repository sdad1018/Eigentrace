#!/usr/bin/env python3
"""
calibrate_4way.py — probe the 4-way softmax split (abstract/concrete/actor/ambiguous) on
diagnostic words, and show how the ambiguous boundary moves at tau=0.45/0.50/0.55.

Geometry (MIT-defensible, no training, no tuning):
  three pole-centroids: ABSTRACT (stakes), CONCRETE (places/objects), ACTOR (people-roles).
  per word: cosine to each centroid -> softmax -> distribution over 3 categories.
  assigned to argmax IF max-prob >= tau, ELSE ambiguous (the distribution is too flat to commit).
  -> 'ambiguous' is a MEASURED property (flat distribution), not a hand-set distance cutoff.

Pole sets (role-nouns, non-overlapping, fixed in advance):
  ABSTRACT: escalation, tension, war, instability, crisis, consequence, consciousness, disclosure
  CONCRETE: strait, city, company, port, bank, border, weapon, harbor       (dropped 'official')
  ACTOR:    president, leader, minister, cleric, general, diplomat, dictator, chancellor

Diagnostic words chosen to span all four expected outcomes:
  actors:    rouhani, khomeini, erdogan, merkel, sadr   -> should be ACTOR
  abstract:  escalation, regime collapse, proxy war     -> should be ABSTRACT
  concrete:  hormuz, tehran, baghdad, refineries         -> should be CONCRETE
  ambiguous: ieds, arms deal, peace deal, norad          -> should be AMBIGUOUS (flat dist)
"""
import os, sys, json
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine

ABSTRACT=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE=["strait","city","company","port","bank","border","weapon","harbor"]
ACTOR   =["president","leader","minister","cleric","general","diplomat","dictator","chancellor"]
TAUS=[0.45,0.50,0.55]

DIAG=["rouhani","khomeini","erdogan","merkel","sadr",          # actors
      "escalation","regime collapse","proxy war",               # abstract
      "hormuz","tehran","baghdad","refineries",                 # concrete
      "ieds","arms deal","peace deal","norad",                  # ambiguous
      "isil","ayatollah"]                                       # extra: group / role

def softmax(x):
    e=np.exp(x-np.max(x)); return e/e.sum()

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    cA=E(ABSTRACT).mean(0); cA/=np.linalg.norm(cA)+1e-8
    cC=E(CONCRETE).mean(0); cC/=np.linalg.norm(cC)+1e-8
    cK=E(ACTOR).mean(0);    cK/=np.linalg.norm(cK)+1e-8
    cats=["ABSTRACT","CONCRETE","ACTOR"]; cents=np.stack([cA,cC,cK])

    # sanity: poles should self-classify
    print("=== pole self-check (each pole-word's softmax; should favor its own category) ===")
    for name,poles in [("ABSTRACT",ABSTRACT),("CONCRETE",CONCRETE),("ACTOR",ACTOR)]:
        V=E(poles); sims=V@cents.T  # (8,3)
        probs=np.array([softmax(s) for s in sims])
        avg=probs.mean(0)
        print(f"  {name:<9} mean softmax -> A={avg[0]:.2f} C={avg[1]:.2f} K={avg[2]:.2f}  "
              f"({'OK' if cats[avg.argmax()]==name else 'LEAK->'+cats[avg.argmax()]})")

    print(f"\n=== diagnostic words: softmax distribution + bucket at each tau ===")
    print(f"{'word':<18} {'A':>5} {'C':>5} {'K':>5}  | "+"  ".join(f"t={t}" for t in TAUS))
    print("-"*68)
    V=E(DIAG); sims=V@cents.T
    rows=[]
    for i,w in enumerate(DIAG):
        p=softmax(sims[i]); top=p.argmax()
        buckets=[]
        for t in TAUS:
            buckets.append(cats[top] if p[top]>=t else "AMBIG")
        rows.append((w,p,buckets))
        print(f"{w:<18} {p[0]:.2f}  {p[1]:.2f}  {p[2]:.2f}  | "+"  ".join(f"{b:<8}" for b in buckets))

    # summary: how many land in each bucket at each tau
    print(f"\n=== bucket counts across the {len(DIAG)} diagnostic words, by tau ===")
    for ti,t in enumerate(TAUS):
        c={}
        for _,_,b in rows: c[b[ti]]=c.get(b[ti],0)+1
        print(f"  tau={t}: {c}")

    print("\nREAD: actors (rouhani/khomeini/erdogan/merkel/sadr) should show high K, land ACTOR.")
    print("ieds/arms deal/peace deal/norad should have FLAT dist -> AMBIG (no category >= tau).")
    print("Pick tau where actors+abstract+concrete classify confidently but the 4 fence words stay AMBIG.")

if __name__=="__main__": main()
