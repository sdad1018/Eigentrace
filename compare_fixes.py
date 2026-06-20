#!/usr/bin/env python3
"""
compare_fixes.py — show BOTH common-mode fixes side by side on diagnostic words,
so we can see which actually separates abstract/concrete/actor.

The raw-centroid softmax failed because bge embeddings share a huge common-mode:
all cosines cluster ~0.3-0.4, differences wash out to uniform 0.33/0.33/0.33.

OPTION 1 — MEAN-CENTERED CENTROIDS:
  compute 3 pole-centroids, subtract their collective mean from each (kills common-mode),
  re-normalize, then cosine -> softmax. Generalizes the difference-vector trick to 3 cats.

OPTION 2 — TWO ORTHOGONAL DIFFERENCE-AXES (reuses the validated abstract-concrete axis):
  axis1 = abstract_centroid - concrete_centroid           (THE validated axis, untouched)
  axis2 = actor_centroid - mean(abstract, concrete)        (new: actor-ness), Gram-Schmidt'd
          orthogonal to axis1 so the two coordinates are independent.
  word -> (p1 = w.axis1, p2 = w.axis2).
  ACTOR if p2 high; else ABSTRACT/CONCRETE by sign of p1; AMBIGUOUS if both small.
"""
import os, sys
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine

ABSTRACT=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE=["strait","city","company","port","bank","border","weapon","harbor"]
ACTOR   =["president","leader","minister","cleric","general","diplomat","dictator","chancellor"]

DIAG=[("rouhani","ACTOR"),("khomeini","ACTOR"),("erdogan","ACTOR"),("merkel","ACTOR"),("sadr","ACTOR"),
      ("escalation","ABSTRACT"),("regime collapse","ABSTRACT"),("proxy war","ABSTRACT"),("disarmament","ABSTRACT"),
      ("hormuz","CONCRETE"),("tehran","CONCRETE"),("baghdad","CONCRETE"),("refineries","CONCRETE"),
      ("ieds","AMBIG?"),("arms deal","AMBIG?"),("peace deal","AMBIG?"),("norad","AMBIG?"),
      ("isil","group?"),("ayatollah","ACTOR?")]

def softmax(x):
    e=np.exp(x-np.max(x)); return e/e.sum()

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    A=E(ABSTRACT).mean(0); C=E(CONCRETE).mean(0); K=E(ACTOR).mean(0)

    # ---------- OPTION 1: mean-centered centroids ----------
    M=(A+C+K)/3.0
    A1=A-M; C1=C-M; K1=K-M
    A1/=np.linalg.norm(A1)+1e-8; C1/=np.linalg.norm(C1)+1e-8; K1/=np.linalg.norm(K1)+1e-8
    cents1=np.stack([A1,C1,K1]); cats=["ABS","CON","ACT"]

    # ---------- OPTION 2: two orthogonal difference-axes ----------
    axis1=A-C; axis1/=np.linalg.norm(axis1)+1e-8                 # validated abstract-concrete
    raw2=K-(A+C)/2.0                                              # actor vs non-actor
    # Gram-Schmidt: remove any axis1 component so the two are orthogonal
    raw2=raw2-(raw2@axis1)*axis1; axis2=raw2/(np.linalg.norm(raw2)+1e-8)

    words=[w for w,_ in DIAG]; V=E(words)
    # option1 scores
    sims1=V@cents1.T
    # option2 scores: center words too (subtract M) before projecting, so common-mode gone
    Vc=V-M; Vc=Vc/(np.linalg.norm(Vc,axis=1,keepdims=True)+1e-8)
    p1=Vc@axis1; p2=Vc@axis2

    print("="*90)
    print("OPTION 1 (mean-centered centroids -> softmax)   vs   OPTION 2 (two ortho diff-axes)")
    print("="*90)
    print(f"{'word':<16}{'expect':<9} | {'O1: ABS  CON  ACT  -> pick':<30} | {'O2: p1(abs+/con-) p2(actor) -> pick'}")
    print("-"*90)
    # option2 thresholds (eyeball): actor if p2 dominates, else sign of p1, ambig if both tiny
    P2T=0.04; P1T=0.04
    for i,(w,exp) in enumerate(DIAG):
        s1=softmax(sims1[i]); pick1=cats[s1.argmax()] if s1.max()>=0.40 else "AMBIG"
        # option2 decision
        a,b=float(p1[i]),float(p2[i])
        if abs(b)>=P2T and b>0 and abs(b)>=abs(a): pick2="ACT"
        elif abs(a)>=P1T: pick2="ABS" if a>0 else "CON"
        else: pick2="AMBIG"
        print(f"{w:<16}{exp:<9} | {s1[0]:.2f} {s1[1]:.2f} {s1[2]:.2f}   -> {pick1:<8} | "
              f"p1={a:+.3f} p2={b:+.3f}      -> {pick2}")

    # self-check both
    print("\n--- pole self-check, both options (each pole set should pick its own) ---")
    for name,poles,idx in [("ABSTRACT",ABSTRACT,0),("CONCRETE",CONCRETE,1),("ACTOR",ACTOR,2)]:
        Vp=E(poles)
        s1=np.array([softmax(s) for s in (Vp@cents1.T)]).mean(0)
        Vpc=Vp-M; Vpc=Vpc/(np.linalg.norm(Vpc,axis=1,keepdims=True)+1e-8)
        pp1=(Vpc@axis1).mean(); pp2=(Vpc@axis2).mean()
        print(f"  {name:<9} O1 softmax A={s1[0]:.2f} C={s1[1]:.2f} K={s1[2]:.2f} ({cats[s1.argmax()]}) | "
              f"O2 p1={pp1:+.3f} p2={pp2:+.3f}")

    print("\nREAD: whichever option makes the 5 actors pick ACTOR, abstract->ABS, concrete->CON,")
    print("and ieds/arms deal/peace deal/norad land AMBIG, with pole self-checks clean, wins.")

if __name__=="__main__": main()
