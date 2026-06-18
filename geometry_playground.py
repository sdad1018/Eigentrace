#!/usr/bin/env python3
"""
geometry_playground.py — three control-having geometry probes. NO API, no judge.
Pure embedding + the clean neutral 50k tensor. "Just look" — but every retrieval
checked against a baseline so the thing we pull isn't mistaken for proof.

PROBE A — COMPOSITIONAL CONDITIONING (the "iran-flavored ww3" idea)
  Does NN(iran (+) ww3) reach concepts that NEITHER iran-alone NOR ww3-alone reaches?
  And do different story-flavors (russia, png) reach DIFFERENT concepts?
  Metric: UNIQUE set = NN(compose) minus NN(story) minus NN(concept).
  Control: cross-story (russia/png) — if iran's unique set != russia's in a
  story-appropriate way, conditioning is real; if same generic mush, it isn't.
  Caveat baked in: bge is a SENTENCE embedder, may not compose like word2vec.
  Empty unique-set = composition adds nothing (a real, clean negative).

PROBE B — NEIGHBORHOOD BREADTH (ChatGPT's Q3: is breadth the Band-2 signature?)
  Do Band-2 words (desalination, regime collapse) open MORE diverse neighborhoods
  (more distinct clusters / more spread) than Band-1 words (airstrike, war)?
  Metric: mean pairwise distance among top-k neighbors + rough cluster count.
  Control: compare Band-1 vs Band-2 labeled sets directly.

PROBE C — SYMBOLIC AFFINITY (Remphan -> Saturn, controlled)
  Does the Star-of-Remphan text have higher affinity to Saturn-words than RANDOM
  symbol controls do? If yes: co-location structure (training association), a real
  embedding result — NOT occult discovery. Control: random esoteric seeds.

bge GPU for embeds; tensor lookups precomputed. Stream stopped.
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
TOPK=12

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    print("loading clean neutral tensor...", flush=True)
    V=torch.load("vocab/global_vocab_clean.pt").numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
    print(f"pool: {len(words)} words\n", flush=True)

    def NN(vec, k=TOPK):
        s=V@vec; idx=np.argsort(-s)[:k]
        return [words[i] for i in idx]
    def NNs(vec, k=TOPK):
        s=V@vec; idx=np.argsort(-s)[:k]
        return [(words[i],float(s[i])) for i in idx]
    def compose(a, b, alpha=0.5):
        q=(1-alpha)*a+alpha*b; return q/(np.linalg.norm(q)+1e-8)

    # ============ PROBE A: COMPOSITIONAL CONDITIONING ============
    print("="*72); print("PROBE A — COMPOSITIONAL CONDITIONING: does story-flavor change the neighborhood?")
    print("="*72)
    concept="world war three nuclear conflict"
    Cv=E([concept])[0]
    nn_C=set(NN(Cv))
    print(f"\nNN('{concept}') [the generic concept]:\n  {NN(Cv)}\n")
    flavors={
        "iran":"Iran Tehran Persian Gulf Strait of Hormuz",
        "russia":"Russia Moscow Kremlin Ukraine NATO",
        "papua new guinea":"Papua New Guinea Pacific islands highlands",
        "north korea":"North Korea Pyongyang Kim regime",
    }
    flavor_unique={}
    for name,desc in flavors.items():
        Av=E([desc])[0]
        nn_A=set(NN(Av))
        for alpha in [0.5]:
            Q=compose(Av,Cv,alpha)
            nn_Q=NN(Q)
            unique=[w for w in nn_Q if w not in nn_A and w not in nn_C]  # only-from-composition
            flavor_unique[name]=unique
            print(f"[{name}-flavored WW3] (alpha={alpha})")
            print(f"  full NN: {nn_Q}")
            print(f"  UNIQUE (not in story-alone, not in ww3-alone): {unique}")
            gain=1 - len(set(nn_Q)&nn_C)/len(nn_Q)
            print(f"  conditioning gain vs generic ww3: {gain:.2f}\n")
    # cross-story control: are the unique sets DIFFERENT across flavors?
    print("CROSS-STORY CONTROL — are unique sets story-specific or generic mush?")
    names=list(flavor_unique.keys())
    for i in range(len(names)):
        for j in range(i+1,len(names)):
            a=set(flavor_unique[names[i]]); b=set(flavor_unique[names[j]])
            overlap=len(a&b)/max(len(a|b),1)
            print(f"  {names[i]} vs {names[j]}: jaccard overlap of unique sets = {overlap:.2f} "
                  f"{'(generic - bad)' if overlap>0.5 else '(story-specific - good)' if a and b else '(empty)'}")
    print("\n  -> rich, DIFFERENT unique sets per flavor = composition reaches story-specific concepts.")
    print("     empty/identical unique sets = bge composition adds nothing (sentence-embedder caveat).")

    # ============ PROBE B: NEIGHBORHOOD BREADTH ============
    print("\n"+"="*72); print("PROBE B — NEIGHBORHOOD BREADTH: is breadth the Band-2 signature?")
    print("="*72)
    band1=["airstrike","war","combat","missiles","soldiers"]          # restatement (narrow?)
    band2=["desalination","regime collapse","arms race","foreign interference","proxy war"]  # productive (broad?)
    def breadth(word):
        v=E([word])[0]; nbrs=NNs(v,TOPK)
        vecs=np.array([V[widx[w]] for w,_ in nbrs if w in widx])
        if len(vecs)<3: return None
        # mean pairwise cosine distance among neighbors (higher = more spread = broader)
        sims=vecs@vecs.T; n=len(vecs)
        off=(sims.sum()-n)/(n*n-n)
        spread=1-off
        return spread, [w for w,_ in nbrs[:8]]
    print("\nBand-1 (expected narrow):")
    b1=[]
    for w in band1:
        r=breadth(w)
        if r: print(f"  {w:18s} spread={r[0]:.3f}  {r[1]}"); b1.append(r[0])
    print("\nBand-2 (expected broad):")
    b2=[]
    for w in band2:
        r=breadth(w)
        if r: print(f"  {w:18s} spread={r[0]:.3f}  {r[1]}"); b2.append(r[0])
    if b1 and b2:
        print(f"\n  Band-1 mean spread: {np.mean(b1):.3f}")
        print(f"  Band-2 mean spread: {np.mean(b2):.3f}")
        print(f"  {'<<< Band-2 broader (breadth IS a signature!)' if np.mean(b2)>np.mean(b1)*1.08 else 'no clear breadth difference'}")

    # ============ PROBE C: SYMBOLIC AFFINITY (controlled) ============
    print("\n"+"="*72); print("PROBE C — SYMBOLIC AFFINITY: Remphan -> Saturn, vs random-symbol controls")
    print("="*72)
    saturn_words=["saturn","cronus","kronos","lead","scythe","time","melancholy"]
    Sv=E(saturn_words); Scentroid=Sv.mean(0); Scentroid/=np.linalg.norm(Scentroid)+1e-8
    seeds={
        "Star of Remphan (Saturn hexagram seal of Kiyyun)":"the star of Remphan, the hexagram seal of the god Kiyyun, Saturn worship",
        "CONTROL: generic hexagram":"a six pointed star geometric shape",
        "CONTROL: random sigil":"an ornate occult sigil symbol",
        "CONTROL: pentagram":"a five pointed star pentagram",
    }
    print(f"\naffinity to Saturn-cluster centroid (saturn/cronus/lead/scythe/time):")
    for label,desc in seeds.items():
        v=E([desc])[0]
        aff=float(v@Scentroid)
        print(f"  {aff:.3f}  {label}")
    print("\n  -> if Remphan affinity > control affinities, there's co-location structure")
    print("     (a training association: corpus co-mentions Remphan/Saturn/Kiyyun).")
    print("     This is a real embedding result, NOT proof of occult geometry.")

if __name__=="__main__":
    main()
