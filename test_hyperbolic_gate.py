#!/usr/bin/env python3
"""
test_hyperbolic_gate.py — does the hyperbolic gate hold across MULTIPLE stories
on REAL donut output? (The playground worked on 1 Iran story w/ hand-picked words.)

The donut's noise comes from the FLAT outer_threshold (cosine>0.52 to headline):
words like 'livestream'/'footage' pass because they embed near 'live updates',
but they're hierarchically irrelevant. The hyperbolic gate should push them to
the bell while keeping on-topic concepts.

This test:
  - clean 50k vocab
  - for several CHARGED + several MUNDANE stories:
    - run real in_domain_void -> raw donut candidates (pull ~15)
    - compute hyperbolic distance of each to the headline narrative
    - show RAW top-8 vs HYPERBOLIC-GATED top-8 side by side
  - HONEST CHECKS: (1) does it kill SUBTLE noise (livestream/footage), not just
    cartoonish? (2) does ONE threshold work across DIFFERENT stories? (3) does it
    keep meaningful concepts? (4) does it break mundane stories?

bge GPU, stream stopped. clean vocab via temp dir. live untouched.
"""
import json, os, sys, glob, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

def to_ball(X):
    X=np.atleast_2d(X); n=np.linalg.norm(X,axis=-1,keepdims=True)
    return np.tanh(n)*X/(n+1e-8)
def hdist(u,v):
    diff=np.linalg.norm(u-v)**2
    du=1-np.linalg.norm(u)**2; dv=1-np.linalg.norm(v)**2
    return float(np.arccosh(1+2*diff/(du*dv+1e-9)))

def main():
    tmp=tempfile.mkdtemp(prefix="cleanvocab_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))

    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    print(f"clean vocab {vt.count} words loaded\n", flush=True)

    # harvest recent stories, split charged vs mundane by simple title cue
    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    charged_cue=["war","iran","strike","nuclear","missile","ceasefire","attack","russia","ukraine","gaza","israel"]
    charged=[]; mundane=[]
    for f in segs:
        if len(charged)>=6 and len(mundane)>=4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{}); sums=[t for t in mr.values() if t and len(t)>50]
            if len(sums)<4: continue
            title=(a.get("story_title") or d.get("title") or "")
            is_charged=any(c in title.lower() for c in charged_cue)
            if is_charged and len(charged)<6: charged.append((title[:60],sums))
            elif not is_charged and len(mundane)<4: mundane.append((title[:60],sums))
        except: pass

    # collect hyp distances across stories to calibrate threshold
    all_hyp=[]

    def process(title, sums, tag):
        vecs=E(sums)
        centroid=vecs.mean(0); centroid/=(np.linalg.norm(centroid)+1e-8)
        hv=E([title])[0]
        # raw donut: pull more candidates (k=15)
        try:
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=15)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
        except Exception as e:
            print(f"[{tag}] {title}\n   ERR {e}"); return
        if not cands: 
            print(f"[{tag}] {title}\n   (no candidates)"); return
        cv=E(cands)
        hb_n=to_ball(hv)[0]; hb_c=to_ball(cv)
        hyps=[hdist(hb_c[i],hb_n) for i in range(len(cands))]
        all_hyp.extend(hyps)
        ranked=sorted(zip(cands,hyps), key=lambda x:x[1])
        print(f"\n[{tag}] {title}")
        print(f"   RAW donut top-8:   {cands[:8]}")
        print(f"   HYP-closest top-8: {[w for w,_ in ranked[:8]]}")
        print(f"   HYP-farthest (bell, should be noise): {[w for w,_ in ranked[-5:]]}")

    print("="*70); print("CHARGED STORIES"); print("="*70)
    for t,s in charged: process(t,s,"CHARGED")
    print("\n"+"="*70); print("MUNDANE STORIES (gate should not break these)"); print("="*70)
    for t,s in mundane: process(t,s,"MUNDANE")

    # threshold distribution
    ah=np.array(all_hyp)
    print("\n"+"="*70)
    print("HYP DISTANCE DISTRIBUTION across all stories' candidates:")
    print(f"  n={len(ah)} min={ah.min():.3f} p25={np.percentile(ah,25):.3f} "
          f"median={np.percentile(ah,50):.3f} p75={np.percentile(ah,75):.3f} max={ah.max():.3f}")
    print("\nEYEBALL CHECKS:")
    print("  1. Do the HYP-farthest words (the bell) look like NOISE consistently?")
    print("  2. Do HYP-closest keep the MEANINGFUL concepts (drone strike, arms race)?")
    print("  3. Is there ONE threshold (~p75?) that works across charged AND mundane?")
    print("  4. Did it kill SUBTLE noise (livestream/footage) not just pewdiepie?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
