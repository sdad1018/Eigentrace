#!/usr/bin/env python3
"""
test_precision.py — does float16 change what the box surfaces vs float32?
Runs the compose->breadth-rank pipeline on the full 50k tensor in BOTH precisions
and measures whether the surfaced concepts differ. If float16 matches float32, we
run a cheaper VPS for free. If it diverges, we pay for float32.

Measures:
  - top-k retrieval AGREEMENT (jaccard) f32 vs f16, for plain NN and for composition
  - breadth-rank ORDER agreement (does the ranking flip?)
  - worst-case concept drift (any concept that appears in f32 top-k but not f16)
  - memory footprint of each tensor

NO API. bge GPU for the query embeds; tensor held both ways. Stream stopped.
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

    print("loading full clean tensor in float32 and float16...", flush=True)
    V32=torch.load("vocab/global_vocab_clean.pt").numpy().astype(np.float32)
    V32=V32/(np.linalg.norm(V32,axis=1,keepdims=True)+1e-8)
    V16=V32.astype(np.float16)   # the candidate: half precision
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
    print(f"  float32 tensor: {V32.nbytes/1e6:.0f} MB")
    print(f"  float16 tensor: {V16.nbytes/1e6:.0f} MB")
    print(f"  pool: {len(words)} words\n", flush=True)

    def NN32(vec,k=TOPK):
        s=V32@vec; return [words[i] for i in np.argsort(-s)[:k]]
    def NN16(vec,k=TOPK):
        # query stays f32, tensor is f16 -> compute in f16 then compare (realistic: matmul upcast)
        s=(V16.astype(np.float32))@vec  # how it'd actually run if stored f16, computed f32
        return [words[i] for i in np.argsort(-s)[:k]]
    def NN16_pure(vec,k=TOPK):
        # fully f16 matmul (most aggressive: store AND compute f16)
        s=V16@vec.astype(np.float16); return [words[i] for i in np.argsort(-s.astype(np.float32))[:k]]
    def compose(a,b,alpha=0.5):
        q=(1-alpha)*a+alpha*b; return q/(np.linalg.norm(q)+1e-8)
    def jac(a,b):
        a,b=set(a),set(b); return len(a&b)/max(len(a|b),1)
    def breadth(word,NNfn):
        v=E([word])[0]; nbrs=NNfn(v,TOPK)
        vecs=np.array([V32[widx[w]] for w in nbrs if w in widx])
        if len(vecs)<3: return 0
        S=vecs@vecs.T; n=len(vecs); return 1-(S.sum()-n)/(n*n-n)

    # test stories x voids (the composition cases that matter)
    flavors={"iran":"Iran Tehran Persian Gulf Strait of Hormuz",
             "russia":"Russia Moscow Kremlin Ukraine NATO",
             "china":"China Beijing Taiwan South China Sea"}
    voids={"ww3":"world war three nuclear conflict",
           "currency collapse":"currency collapse financial crisis"}

    print("="*72); print("COMPOSITION: f32 vs f16 (stored-f16/computed-f32) vs pure-f16")
    print("="*72)
    agg_jac=[]; agg_jac_pure=[]; drift=[]
    for fn,fd in flavors.items():
        fv=E([fd])[0]
        for vn,vd in voids.items():
            vv=E([vd])[0]; Q=compose(fv,vv)
            t32=NN32(Q); t16=NN16(Q); t16p=NN16_pure(Q)
            j=jac(t32,t16); jp=jac(t32,t16p)
            agg_jac.append(j); agg_jac_pure.append(jp)
            missing=[w for w in t32 if w not in t16]
            drift.extend(missing)
            print(f"\n  {fn} (+) {vn}")
            print(f"    f32 : {t32}")
            print(f"    f16 : {t16}")
            if t16p!=t16: print(f"    f16*: {t16p}  (pure-f16 matmul)")
            print(f"    agreement f32~f16: {j:.2f}  | f32~pure-f16: {jp:.2f}"
                  + (f"  MISSING in f16: {missing}" if missing else "  (identical)"))

    print("\n"+"="*72); print("BREADTH-RANK ORDER: does the ranking flip between precisions?")
    print("="*72)
    testwords=["arms race","desalination","airstrike","war","regime collapse","combat",
               "proxy war","missiles","currency collapse","tanks"]
    b32={w:breadth(w,NN32) for w in testwords}
    b16={w:breadth(w,NN16) for w in testwords}
    order32=sorted(testwords,key=lambda w:-b32[w])
    order16=sorted(testwords,key=lambda w:-b16[w])
    print("  rank by breadth (f32):", order32)
    print("  rank by breadth (f16):", order16)
    # rank correlation (kendall-ish: count inversions)
    same=sum(1 for i in range(len(testwords)) if order32[i]==order16[i])
    print(f"  positions identical: {same}/{len(testwords)}")
    maxdiff=max(abs(b32[w]-b16[w]) for w in testwords)
    print(f"  max breadth-value difference: {maxdiff:.5f}")

    print("\n"+"="*72)
    print("VERDICT:")
    print(f"  mean composition agreement f32~f16 (stored-f16): {np.mean(agg_jac):.3f}")
    print(f"  mean composition agreement f32~pure-f16:         {np.mean(agg_jac_pure):.3f}")
    print(f"  unique concepts that drifted out in f16: {sorted(set(drift)) if drift else 'NONE'}")
    print(f"  memory saving: {V32.nbytes/1e6:.0f}MB -> {V16.nbytes/1e6:.0f}MB ({V16.nbytes/V32.nbytes*100:.0f}%)")
    print("\n  If agreement ~1.0 and no drift -> float16 is free; run the cheaper box.")
    print("  If concepts drift / ranking flips -> float32, pay for the RAM.")

if __name__=="__main__":
    main()
