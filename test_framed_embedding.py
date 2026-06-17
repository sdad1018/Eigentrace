#!/usr/bin/env python3
"""
test_framed_embedding.py — Gemini's representation-collapse fix, tested honestly.

CLAIM: the 0.02 hyperbolic spread was Representation Collapse — bge collapses
BARE tokens (out-of-distribution) into a cone. Wrapping each word in a syntactic
frame ("Represent the semantic concept: X") un-collapses the manifold, so the
hyperbolic/orthogonal gates would then separate signal from noise.

WE ALREADY tested framing->PCA (the ΔV test): it widened the space but the
structure was TOPIC, not signal/noise. This tests the NEW combination:
framing -> hyperbolic distance. 

PRE-COMMITTED BAR (both required, no goalpost move):
  1. spread WIDENS: framed hyp-distance spread >> 0.02 (bare)
  2. widening SEPARATES on REAL donut output: webcam/porn land FAR from
     drone-strike/arms-race, consistently. Wider != separated. We check
     separation against labels, not just that numbers spread.

bge GPU, stream stopped, clean vocab, live untouched.
"""
import json, os, sys, glob, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

FRAME = "Represent the semantic concept: {}"  # Gemini's exact prefix

def to_ball(X):
    X=np.atleast_2d(X); n=np.linalg.norm(X,axis=-1,keepdims=True)
    return np.tanh(n)*X/(n+1e-8)
def hdist(u,v):
    diff=np.linalg.norm(u-v)**2
    du=1-np.linalg.norm(u)**2; dv=1-np.linalg.norm(v)**2
    return float(np.arccosh(1+2*diff/(du*dv+1e-9)))

# labeled candidates for separation check (real words seen in donut output)
SIGNAL={"drone strike","arms race","arms deal","arms embargo","information warfare",
        "warheads","foreign interference","death toll","atrocities","nuclear war",
        "escalation","proxy war","regime change","ceasefire","hostilities"}
NOISE={"webcam","porn","vids","pewdiepie","wrestlemania","livestream","subscription",
       "dvr","wifi","obs","footage","feed","chat","watcher","dailies","repeats","gimme"}

def main():
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    print("clean vocab loaded\n", flush=True)

    # gather real donut candidates from charged stories
    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","iran","strike","nuclear","ukraine","russia","israel","gaza","ceasefire"]
    candidates=[]; narratives=[]
    for f in segs:
        if len(narratives)>=6: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{}); sums=[t for t in mr.values() if t and len(t)>50]
            if len(sums)<4: continue
            title=(a.get("story_title") or "")
            if not any(c in title.lower() for c in cue): continue
            vecs=E(sums); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=15)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            if cands:
                narratives.append((title[:55], hv, cands))
        except: pass
    print(f"gathered {len(narratives)} charged stories with real donut candidates\n", flush=True)

    # for each: compute hyp distance BARE vs FRAMED, check spread + separation
    print("="*70)
    bare_spreads=[]; framed_spreads=[]
    bare_seps=[]; framed_seps=[]
    for title, hv, cands in narratives:
        # BARE
        cv_bare=E(cands)
        hb_n=to_ball(hv)[0]; hb_c=to_ball(cv_bare)
        hd_bare=np.array([hdist(hb_c[i],hb_n) for i in range(len(cands))])
        # FRAMED candidates (frame the headline too, for consistency)
        cv_fr=E([FRAME.format(w) for w in cands]); hv_fr=E([FRAME.format(title)])[0]
        hb_nf=to_ball(hv_fr)[0]; hb_cf=to_ball(cv_fr)
        hd_fr=np.array([hdist(hb_cf[i],hb_nf) for i in range(len(cands))])

        bare_spreads.append(hd_bare.max()-hd_bare.min())
        framed_spreads.append(hd_fr.max()-hd_fr.min())

        # separation: mean hyp-dist of NOISE candidates minus SIGNAL candidates
        # (want NOISE far, SIGNAL near -> positive gap = good separation)
        def gap(hd):
            sig=[hd[i] for i,w in enumerate(cands) if w.lower() in SIGNAL]
            noi=[hd[i] for i,w in enumerate(cands) if w.lower() in NOISE]
            if sig and noi: return np.mean(noi)-np.mean(sig)
            return None
        gb=gap(hd_bare); gf=gap(hd_fr)
        if gb is not None: bare_seps.append(gb)
        if gf is not None: framed_seps.append(gf)

        print(f"\n[{title}]")
        print(f"  BARE   spread={hd_bare.max()-hd_bare.min():.3f}  sep(noise-signal)={gb if gb is None else round(gb,3)}")
        print(f"  FRAMED spread={hd_fr.max()-hd_fr.min():.3f}  sep(noise-signal)={gf if gf is None else round(gf,3)}")
        # show framed ranking
        ranked=sorted(zip(cands,hd_fr),key=lambda x:x[1])
        print(f"  FRAMED closest: {[w for w,_ in ranked[:6]]}")
        print(f"  FRAMED bell:    {[w for w,_ in ranked[-5:]]}")

    print("\n"+"="*70)
    print("VERDICT — both conditions required:")
    print(f"  1. SPREAD WIDENS?  bare mean spread={np.mean(bare_spreads):.3f} -> "
          f"framed mean spread={np.mean(framed_spreads):.3f}  "
          f"({'WIDER' if np.mean(framed_spreads)>np.mean(bare_spreads)*1.5 else 'NOT MUCH WIDER'})")
    if bare_seps and framed_seps:
        print(f"  2. SEPARATES on real output?  bare sep={np.mean(bare_seps):+.3f} -> "
              f"framed sep={np.mean(framed_seps):+.3f}")
        print(f"     (sep = mean[noise hyp-dist] - mean[signal hyp-dist]; want clearly POSITIVE)")
        if np.mean(framed_seps) > 0.1 and np.mean(framed_seps) > np.mean(bare_seps)+0.05:
            print("     >>> FRAMING SEPARATES SIGNAL FROM NOISE. Gemini right — build it.")
        else:
            print("     >>> framing did NOT meaningfully separate signal/noise on real output.")
            print("         (even if spread widened, it didn't widen along the signal/noise axis)")
    else:
        print("  2. insufficient labeled candidates in donut output to measure separation")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
