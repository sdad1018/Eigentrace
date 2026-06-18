#!/usr/bin/env python3
"""
stress_ab.py — harden the two geometry findings that PASSED controls (composition,
breadth). The planetary detour proved our controls bite; it did NOT replicate A/B.
This does. No API. bge + clean neutral tensor. Stream stopped.

PROBE A REPLICATION — COMPOSITIONAL CONDITIONING across MANY story-flavors x voids.
  Claim: NN(story (+) void) reaches concepts NEITHER alone reaches, and DIFFERENT
  stories reach DIFFERENT concepts (story-conditioned, not generic mush).
  Prior: n=4 flavors, one void (ww3), cross-story jaccard ~0.00.
  Now: many flavors x several void-concepts. Metrics per (flavor,void):
    - unique set = NN(compose) - NN(flavor) - NN(void)
    - conditioning gain = 1 - |NN(compose) ∩ NN(void)| / k
  Cross-story control: mean pairwise jaccard of unique sets ACROSS flavors for the
  SAME void. Low overlap = story-specific (real). High = generic mush (fail).
  Also a NULL: compose flavor with a RANDOM concept — should NOT yield a coherent
  story-specific unique set (if random composition also "works", A is an artifact).

PROBE B REPLICATION — NEIGHBORHOOD BREADTH across a BIGGER labeled vocab.
  Claim: Band-2 (productive latent) words open broader neighborhoods than Band-1
  (restatement) words. Prior: n=5+5, gap 0.233 vs 0.309.
  Now: ~15 Band-1 vs ~15 Band-2, report distributions + separation + a simple
  classifier threshold (does spread alone separate the two bands?).
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
TOPK=12

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    print("loading clean neutral tensor...", flush=True)
    V=torch.load("vocab/global_vocab_clean.pt").numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
    print(f"pool: {len(words)} words\n", flush=True)

    def NN(vec,k=TOPK): 
        s=V@vec; return [words[i] for i in np.argsort(-s)[:k]]
    def NNs(vec,k=TOPK):
        s=V@vec; idx=np.argsort(-s)[:k]; return [(words[i],float(s[i])) for i in idx]
    def compose(a,b,alpha=0.5):
        q=(1-alpha)*a+alpha*b; return q/(np.linalg.norm(q)+1e-8)
    def jac(a,b):
        a,b=set(a),set(b); return len(a&b)/max(len(a|b),1)

    # ================= PROBE A: composition across many pairs =================
    print("="*72); print("PROBE A REPLICATION — composition across flavors x voids")
    print("="*72)
    flavors={
      "iran":"Iran Tehran Persian Gulf Strait of Hormuz",
      "russia":"Russia Moscow Kremlin Ukraine NATO",
      "china":"China Beijing Taiwan South China Sea",
      "north korea":"North Korea Pyongyang Kim regime",
      "israel":"Israel Jerusalem Gaza IDF",
      "papua new guinea":"Papua New Guinea Pacific islands highlands",
    }
    voids={
      "ww3":"world war three nuclear conflict",
      "regime collapse":"regime collapse government overthrow",
      "currency collapse":"currency collapse financial crisis",
      "naval blockade":"naval blockade shipping lane closure",
    }
    Fv={n:E([d])[0] for n,d in flavors.items()}
    Cv={n:E([d])[0] for n,d in voids.items()}
    nnF={n:set(NN(v)) for n,v in Fv.items()}
    nnC={n:set(NN(v)) for n,v in Cv.items()}

    overlaps_by_void={}
    for vn,vv in Cv.items():
        print(f"\n--- void: '{vn}' ---")
        uniques={}
        for fn,fv in Fv.items():
            Q=compose(fv,vv); nnQ=NN(Q)
            uniq=[w for w in nnQ if w not in nnF[fn] and w not in nnC[vn]]
            uniques[fn]=uniq
            gain=1-len(set(nnQ)&nnC[vn])/len(nnQ)
            print(f"  {fn:16s} gain={gain:.2f}  unique={uniq[:6]}")
        # cross-story overlap of unique sets for THIS void
        fs=list(uniques); ov=[]
        for i in range(len(fs)):
            for j in range(i+1,len(fs)):
                ov.append(jac(uniques[fs[i]],uniques[fs[j]]))
        mo=np.mean(ov) if ov else 0
        overlaps_by_void[vn]=mo
        print(f"  >> mean cross-story jaccard of unique sets: {mo:.3f} "
              f"{'(story-specific - REPLICATES)' if mo<0.2 else '(generic mush - FAILS)'}")

    # NULL control: compose flavors with a RANDOM concept
    print("\n--- NULL: compose flavors with a RANDOM word (should NOT be story-coherent) ---")
    rng=np.random.default_rng(3)
    randw=[words[i] for i in rng.choice(len(words),3,replace=False)]
    print(f"  random 'voids': {randw}")
    null_ov=[]
    for rw in randw:
        rv=V[widx[rw]]
        uq={}
        for fn,fv in Fv.items():
            Q=compose(fv,rv); nnQ=NN(Q)
            uq[fn]=[w for w in nnQ if w not in nnF[fn] and w not in set(NN(rv))]
        fs=list(uq)
        for i in range(len(fs)):
            for j in range(i+1,len(fs)): null_ov.append(jac(uq[fs[i]],uq[fs[j]]))
    print(f"  null mean cross-story jaccard: {np.mean(null_ov):.3f}")
    print(f"  (real voids should be similarly LOW overlap but yield MEANINGFUL unique concepts;")
    print(f"   the test is whether real-void unique sets are interpretable & random ones aren't)")

    print(f"\n  SUMMARY — mean cross-story overlap per void:")
    for vn,mo in overlaps_by_void.items():
        print(f"    {vn:18s} {mo:.3f}")
    print(f"  overall: {np.mean(list(overlaps_by_void.values())):.3f} "
          f"{'<<< composition is story-conditioned across the board' if np.mean(list(overlaps_by_void.values()))<0.2 else 'mixed'}")

    # ================= PROBE B: breadth across bigger vocab =================
    print("\n"+"="*72); print("PROBE B REPLICATION — breadth across bigger Band-1/Band-2 sets")
    print("="*72)
    band1=["airstrike","war","combat","missiles","soldiers","tanks","bombing","gunfire",
           "troops","artillery","casualties","wounded","battle","explosion","sanctions"]
    band2=["desalination","regime collapse","arms race","foreign interference","proxy war",
           "currency collapse","market manipulation","regime change","arms embargo","price gouging",
           "nuclear deterrence","trade war","political prisoner","targeted killing","naval blockade"]
    def spread(word):
        v=E([word])[0]; nbrs=NNs(v,TOPK)
        vecs=np.array([V[widx[w]] for w,_ in nbrs if w in widx])
        if len(vecs)<3: return None
        S=vecs@vecs.T; n=len(vecs); return 1-(S.sum()-n)/(n*n-n)
    s1=[]; s2=[]
    print("\nBand-1:")
    for w in band1:
        r=spread(w)
        if r: s1.append(r); print(f"  {w:20s} {r:.3f}")
    print("\nBand-2:")
    for w in band2:
        r=spread(w)
        if r: s2.append(r); print(f"  {w:20s} {r:.3f}")
    s1,s2=np.array(s1),np.array(s2)
    print(f"\n  Band-1: mean={s1.mean():.3f} sd={s1.std():.3f} range=[{s1.min():.3f},{s1.max():.3f}]")
    print(f"  Band-2: mean={s2.mean():.3f} sd={s2.std():.3f} range=[{s2.min():.3f},{s2.max():.3f}]")
    # separation: t-like effect size + threshold classifier
    pooled_sd=np.sqrt((s1.var()+s2.var())/2)
    d=(s2.mean()-s1.mean())/(pooled_sd+1e-9)
    # best threshold accuracy
    allv=np.concatenate([s1,s2]); lab=np.array([0]*len(s1)+[1]*len(s2))
    best_acc=0; best_t=0
    for t in np.linspace(allv.min(),allv.max(),200):
        acc=max(((allv>t)==lab).mean(), ((allv<=t)==lab).mean())
        if acc>best_acc: best_acc,best_t=acc,t
    print(f"\n  Cohen's d (effect size): {d:.2f}  ({'large' if d>0.8 else 'medium' if d>0.5 else 'small'})")
    print(f"  best single-threshold classification accuracy: {best_acc:.0%} at spread={best_t:.3f}")
    print(f"  overlap in ranges: {'YES (imperfect separator)' if s1.max()>s2.min() else 'NONE (clean separator)'}")
    print(f"  {'<<< breadth REPLICATES as a Band-2 signature' if d>0.8 and best_acc>0.75 else 'breadth weaker at scale - partial'}")

    print("\n"+"="*72)
    print("VERDICT: A replicates if cross-story overlap stays LOW (<0.2) with meaningful")
    print("unique concepts. B replicates if Cohen's d is large (>0.8) and threshold acc >75%.")
    print("If both hold: the pure-geometry beat-3 (compose -> breadth-rank -> surface) is real.")

if __name__=="__main__":
    main()
