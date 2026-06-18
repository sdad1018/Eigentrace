#!/usr/bin/env python3
"""
test_clean_raycast.py — is beat 3 (the raycast payoff) REAL or an artifact of the
planted vocab?

THE PROBLEM (confirmed by recon):
  - The live raycast k-NNs against raycast_vocab.npy = 253,813 entries that are
    mostly WIKIPEDIA TITLES ('1979 NASCAR Winston West Series') + 2,847 PLANTED
    doom-phrases ('fertilizer contagion'). So "void -> consequence" terminals are
    either planted doom or random wiki titles. Circular / noise.
  - raycast_vocab_clean (548 words) is ALSO bad: it's just the surviving doom-
    phrases ('mining paralysis','pharmaceutical contagion'), so raycasting through
    it GUARANTEES doom. Maximally circular.

THE MATH IS FINE: T = h + lambda*(v-h)/||v-h||, then k-NN the terminal coordinate.
The only problem is the POOL. So this swaps the pool to the NEUTRAL clean 50k
tensor (global_vocab_clean: real English, no planted doom, no wiki titles) and
runs the REAL projection. What does 'WW3' actually project to through honest
language?

For each void word: project at depths, k-NN the clean tensor, show terminals.
Compares: does it reach genuine consequence-concepts, or just synonyms/noise?
Also tests a 'surprise' void ('desalination') to see if the raycast is the
surprise engine we hoped.

bge GPU (embeds void words + terminals lookup uses precomputed tensor). No API.
Stream stopped.
"""
import json, os, sys, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

DEPTHS=[1.5, 2.0, 2.5, 3.0, 4.0]
TOP_K=8

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    # load the NEUTRAL clean tensor as the raycast pool
    print("loading clean neutral tensor as raycast pool...", flush=True)
    V=torch.load("vocab/global_vocab_clean.pt").numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    print(f"pool: {len(words)} neutral words, tensor {V.shape}\n", flush=True)

    def knn(vec, k=TOP_K):
        sims=V@vec
        idx=np.argsort(-sims)[:k]
        return [(words[i], float(sims[i])) for i in idx]

    def raycast(h, v, depths=DEPTHS, k=TOP_K):
        d=v-h; n=np.linalg.norm(d)
        if n==0: return {}
        d=d/n
        out={}
        for lam in depths:
            T=h+d*lam; T=T/(np.linalg.norm(T)+1e-8)
            out[lam]=knn(T,k)
        return out

    # test cases: (headline context, void word, note)
    cases=[
        ("Iran War Live Updates: Tensions Rise as Iran Threatens Retaliation", "ww3", "the dramatic one"),
        ("Israel Counts the Ways Netanyahu's Iran Strategy Failed", "regime collapse", "consequence"),
        ("Trump Defends Deal to End the War With Iran", "arms race", "escalation"),
        ("War Hangs Over American Farmers as Fertilizer Prices Rise", "desalination", "the SURPRISE one"),
        ("U.S.-Iran Agreement Includes Strait of Hormuz", "naval blockade", "mechanism"),
        ("Iran Will Enter Nuclear Talks Feeling Emboldened", "nuclear deterrence", "concept"),
    ]

    for headline, void, note in cases:
        h=E([headline])[0]; v=E([void])[0]
        print("="*72)
        print(f"[{headline[:54]}]")
        print(f"  VOID: '{void}'  ({note})")
        ray=raycast(h, v)
        for lam in DEPTHS:
            terms=ray.get(lam,[])
            tstr=", ".join(f"{w}({s:.2f})" for w,s in terms[:6])
            print(f"    depth {lam}: {tstr}")
        # the "terminal" the live system would report = deepest
        deep=ray.get(max(DEPTHS),[])
        print(f"  >>> DEEPEST TERMINAL: {[w for w,_ in deep[:5]]}")
        print()

    print("="*72)
    print("EYEBALL: does 'ww3' project to genuine consequence-language (holocaust,")
    print("annihilation, fallout, catastrophe) through the NEUTRAL pool — or to noise/")
    print("synonyms? Does 'desalination' reach a surprising-but-real chain (water/scarcity)?")
    print("If terminals are real consequences -> beat 3 is honest. If noise -> the old")
    print("'profound' terminals were the planted doom-pool, and we rethink beat 3.")

if __name__=="__main__":
    main()
