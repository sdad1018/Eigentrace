#!/usr/bin/env python3
"""spiral_sampler.py -- the convergence spiral. Negative space = concepts where source
SENTENCES converge but NONE state, ordered by radius outward from the explicit text.
Not single-centroid nearest-cosine (that was the flat raycast, which a bare prompt matched).
This uses per-sentence geometry + an outward traversal, then tests whether the concepts it
surfaces are ones a bare prompt MISSES -- the thing the flat raycast could not show.

Compares THREE concept sources per story:
  FLAT   -- the old top-N raycast (confront10_final.derive_channels)
  SPIRAL -- convergence spiral (this file)
Then measures bare-prompt recall of each (does the prompt independently reach them?).
"""
import os, sys, json, re
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront10_final as F
import confront_keeper_v3 as KV3
from geometric_engine import get_engine
eng=get_engine()
def E(t):
    v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
    return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

# vocab + V matrix + IDF (same sources the flat raycast uses)
import torch
VT=json.load(open("vocab/global_vocab_clean.json")); VOCAB=VT["words"] if isinstance(VT,dict) else VT
V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
try:
    VF=json.load(open("void_frequency.json")); NDOCS=max(VF.values()) if VF else 1659
    def idf(w): return np.log((NDOCS+1)/(VF.get(w,1)+1))
except Exception:
    def idf(w): return 1.0
HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

def sentences(src):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', src) if len(s.strip())>15]

def convergence_spiral(src, summaries, conv_thresh=0.45, conv_min=2, pool=400, topk=8):
    """Surface concepts where >=conv_min source sentences converge but none state,
    ordered outward by radius from explicit text."""
    sents=sentences(src)
    if len(sents)<3: 
        return [], []   # too few sentences for convergence to mean anything
    Sv=E(sents)                                   # (n_sent, 1024) the suns
    said=" ".join(summaries).lower(); srcl=src.lower()
    # candidate pool: words near the source overall (so we don't score all 30k)
    cen=Sv.mean(0); cen/=np.linalg.norm(cen)+1e-8
    pool_idx=np.argsort(-(V@cen))[:pool]
    rows=[]
    for i in pool_idx:
        w=VOCAB[i]
        if len(w)<4 or w in HARD: continue
        wv=V[i]
        sims=Sv@wv                                # cosine to EACH sentence
        conv=int(np.sum(sims>conv_thresh))        # how many sentences converge
        if conv<conv_min: continue                # must be implied by >=2 sentences
        if re.search(r'\b'+re.escape(w.lower())+r'\b', said): continue   # already in summaries
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
        # radius = how far past explicit text. containment = max cosine to an actual source word.
        # approximate containment by max sentence-cosine (high = a sentence nearly says it)
        radius=1.0-float(np.max(sims))
        rows.append({"w":w,"conv":conv,"radius":radius,"idf":float(idf(w)),
                     "agg":float(np.mean(np.sort(sims)[-conv_min:])),"in_src":in_src})
    if not rows: return [], []
    # NEGATIVE-SPACE band: not in source, high convergence, IDF above pool median (meaningful, not noise)
    idf_med=np.median([r["idf"] for r in rows])
    band=[r for r in rows if (not r["in_src"]) and r["idf"]>=idf_med]
    # the SPIRAL ordering: outward by radius (inner=almost-said, outer=faintly-implied)
    band.sort(key=lambda r:(-r["conv"], r["radius"]))   # most-converged first, then outward
    concepts=[r["w"] for r in band][:topk]
    # also return the full traversal for inspection
    traversal=[(r["w"],r["conv"],round(r["radius"],2),round(r["idf"],1)) for r in band][:topk]
    return concepts, traversal

def main():
    stories=KV3.STORIES+[F.ADVERSARIAL]
    print("CONVERGENCE SPIRAL vs FLAT RAYCAST -- concept comparison\n")
    engF=F.build_engine()
    out=[]
    for st in stories:
        src=st["source"]
        cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print(f"{st['id']}: consensus<3 skip"); continue
        flat_facts,_,flat_concepts=F.derive_channels(src,cons,engF)
        spiral_concepts,traversal=convergence_spiral(src,cons)
        flat_set=set(flat_concepts); spiral_set=set(spiral_concepts)
        novel=spiral_set-flat_set      # concepts the spiral found that the flat raycast did NOT
        print(f"=== {st['id']} [{st['shape']}] ===")
        print(f"  FLAT  : {flat_concepts}")
        print(f"  SPIRAL: {spiral_concepts}")
        print(f"  spiral traversal (word, #sentences-converged, radius-outward, idf):")
        for t in traversal: print(f"      {t}")
        print(f"  NOVEL (spiral-only, flat missed): {sorted(novel)}")
        print()
        out.append({"story":st["id"],"source":src,"flat":flat_concepts,"spiral":spiral_concepts,"novel":sorted(novel)})
    json.dump(out,open("spiral_concepts.json","w"),indent=2)
    # overlap summary
    tot_flat=sum(len(o["flat"]) for o in out); tot_spiral=sum(len(o["spiral"]) for o in out)
    tot_novel=sum(len(o["novel"]) for o in out)
    print("="*60)
    print(f"across {len(out)} stories: flat={tot_flat} concepts, spiral={tot_spiral}, "
          f"spiral-novel (flat missed)={tot_novel} ({tot_novel/max(tot_spiral,1):.0%} of spiral concepts are new)")
    print("wrote spiral_concepts.json")
    print("\nNEXT: if spiral surfaces meaningfully different concepts, run spiral_recall.py")
    print("to test whether a bare prompt MISSES them (the test the flat raycast failed).")
if __name__=="__main__": main()
