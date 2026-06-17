#!/usr/bin/env python3
"""
test_geometry_playground.py — THE GEOMETRY SANDBOX. Gemini's three non-Euclidean
topologies, tested side-by-side on labeled cases. For fun + honest discovery.

We are NOT assuming any of these work (5 prior geometric tests came back null/topic).
We're LOOKING: does any of these shapes actually separate meaningful voids (WWIII,
arms race) from generic gravity-well noise (porn, kanye, webcam) and proper nouns?

  1. ORTHOGONAL SHADOW: project void onto plane perpendicular to narrative vector.
     Claim: noise is parallel to narrative, signal is orthogonal-but-related.
  2. ATTRACTOR BASIN: local neighborhood density in vocab.
     Claim: generic noise = supermassive wells (high density), signal = specific divots.
  3. HYPERBOLIC PSEUDOSPHERE: map to Poincare disk, measure hyperbolic distance.
     Claim: hierarchy expands, generic noise pushed to the bell.

Uses bge (GPU, stream stopped) + the clean 50k vocab for neighbor density.
Calibrates on labeled words against a real charged-story consensus. Live untouched.
"""
import json, os, sys, glob
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# A real charged story's consensus to test against (Iran tension / escalation)
STORY_TITLE = "Iran War Live Updates: U.S. and Iran Look Ahead to Next Round"
NARRATIVE = ("The United States and Iran are looking ahead to the next round of "
             "negotiations after escalating military tension in the region, with both "
             "sides weighing strikes, deterrence, and the risk of wider conflict.")

# labeled candidates: G=meaningful unspoken consequence, P=pop/generic noise, N=name
CANDIDATES = {
    "wwiii":"G","arms race":"G","nuclear war":"G","escalation":"G","proxy war":"G",
    "deterrence":"G","ceasefire":"G","drone strike":"G","regime change":"G","blockade":"G",
    "porn":"P","webcam":"P","pewdiepie":"P","kanye":"P","wrestlemania":"P",
    "livestream":"P","subscription":"P","vids":"P","footage":"P","chat":"P",
    "khomeini":"N","rouhani":"N","tehran":"N","ayatollah":"N",
}

def main():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(texts): 
        v=np.array(eng.embed_texts(texts)); 
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    print(f"narrative: {STORY_TITLE}\n", flush=True)
    nv = E([NARRATIVE])[0]
    words = list(CANDIDATES.keys())
    wv = E(words)
    labs = [CANDIDATES[w] for w in words]

    # load clean vocab tensor for density calc
    import torch
    Vt = torch.load("vocab/global_vocab_clean.pt", map_location="cpu", weights_only=True).numpy()
    print(f"clean vocab tensor for density: {Vt.shape}\n", flush=True)

    # ---------- 1. ORTHOGONAL SHADOW ----------
    # component of each void word ORTHOGONAL to the narrative vector
    print("="*70)
    print("1. ORTHOGONAL SHADOW — orthogonal component vs narrative")
    print("   (Gemini: signal=high orthogonal+related, noise=parallel)\n")
    proj_on_nv = (wv @ nv)[:,None] * nv[None,:]    # projection onto narrative
    orth = wv - proj_on_nv                          # orthogonal residual
    orth_mag = np.linalg.norm(orth, axis=1)         # how much it sticks out sideways
    parallel = wv @ nv                              # how parallel to narrative
    rows=sorted(zip(words,labs,orth_mag,parallel), key=lambda x:-x[2])
    print(f"   {'word':14s} {'lbl':3s} {'orth_mag':>9s} {'parallel':>9s}")
    for w,l,o,p in rows:
        print(f"   {w:14s} {l:3s} {o:9.3f} {p:9.3f}")
    for grp,nm in [("G","SIGNAL"),("P","POP-NOISE"),("N","NAMES")]:
        v=[o for w,l,o,p in rows if l==grp]
        print(f"   {nm} orth_mag: mean={np.mean(v):.3f}")

    # ---------- 2. ATTRACTOR BASIN ----------
    print("\n"+"="*70)
    print("2. ATTRACTOR BASIN — local vocab density (k-NN mean sim)")
    print("   (Gemini: noise=supermassive well/high density, signal=specific divot)\n")
    dens=[]
    for i,w in enumerate(words):
        sims = Vt @ wv[i]
        topk = np.sort(sims)[-50:]   # 50 nearest neighbors in clean vocab
        dens.append(float(topk.mean()))
    rows=sorted(zip(words,labs,dens), key=lambda x:-x[2])
    print(f"   {'word':14s} {'lbl':3s} {'density':>9s}")
    for w,l,d in rows:
        print(f"   {w:14s} {l:3s} {d:9.3f}")
    for grp,nm in [("G","SIGNAL"),("P","POP-NOISE"),("N","NAMES")]:
        v=[d for w,l,d in rows if l==grp]
        print(f"   {nm} density: mean={np.mean(v):.3f}")

    # ---------- 3. HYPERBOLIC PSEUDOSPHERE ----------
    print("\n"+"="*70)
    print("3. HYPERBOLIC PSEUDOSPHERE — Poincare-disk distance from narrative")
    print("   (Gemini: hierarchy expands, generic noise to the bell)\n")
    # map to Poincare ball: scale into unit ball, use hyperbolic distance
    # simple exp-map style: x_h = tanh(||x||)/||x|| * x  (squash to ball)
    def to_ball(X):
        n=np.linalg.norm(X,axis=-1,keepdims=True)
        return np.tanh(n)*X/(n+1e-8)
    def hdist(u,v):
        # Poincare disk distance
        diff=np.linalg.norm(u-v)**2
        du=1-np.linalg.norm(u)**2; dv=1-np.linalg.norm(v)**2
        return np.arccosh(1+2*diff/(du*dv+1e-9))
    nb=to_ball(nv[None,:])[0]; wb=to_ball(wv)
    hd=[hdist(wb[i],nb) for i in range(len(words))]
    rows=sorted(zip(words,labs,hd), key=lambda x:x[2])
    print(f"   {'word':14s} {'lbl':3s} {'hyp_dist':>9s}")
    for w,l,h in rows:
        print(f"   {w:14s} {l:3s} {h:9.3f}")
    for grp,nm in [("G","SIGNAL"),("P","POP-NOISE"),("N","NAMES")]:
        v=[h for w,l,h in rows if l==grp]
        print(f"   {nm} hyp_dist: mean={np.mean(v):.3f}")

    print("\n"+"="*70)
    print("VERDICT: for EACH method, are the SIGNAL means clearly separated from")
    print("POP-NOISE and NAMES? If a method ranks G above P/N cleanly, it WORKS and")
    print("we build it. If G/P/N means overlap (like the 5 prior tests), it's the")
    print("same wall in a prettier shape. Look at the per-group means above.")

if __name__=="__main__":
    main()
