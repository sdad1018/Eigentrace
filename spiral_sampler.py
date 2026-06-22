#!/usr/bin/env python3
"""spiral_sampler.py v2 -- convergence spiral, PATCHED.
Fixes: (1) route output through is_named_entity (discard Channel-B entities from the
concept feed), (2) fix IDF load so radius/band detection fires, (3) LOG discarded
entities separately -- they are a fingerprint of the corpus's stock-actor expectation
for a story-shape (discard from product path, keep as measurement)."""
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

import torch
VT=json.load(open("vocab/global_vocab_clean.json")); VOCAB=VT["words"] if isinstance(VT,dict) else VT
V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)

# --- FIX 2: load IDF robustly, report whether it actually loaded ---
IDF_OK=False
try:
    VF=json.load(open("void_frequency.json"))
    if isinstance(VF,dict) and VF:
        _vals=[v for v in VF.values() if isinstance(v,(int,float))]
        NDOCS=max(_vals) if _vals else 1659
        IDF_OK=True
        def idf(w): return float(np.log((NDOCS+1)/(VF.get(w,1)+1)))
    else:
        def idf(w): return 1.0
except Exception as e:
    print(f"  [IDF load failed: {e} -- falling back to flat idf=1.0]")
    def idf(w): return 1.0
print(f"[IDF source loaded: {IDF_OK}; NDOCS={NDOCS if IDF_OK else 'n/a'}]\n")

HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

def is_entity(w):
    try: return KV3.is_named_entity(w)
    except Exception: return False

def sentences(src):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', src) if len(s.strip())>15]

def convergence_spiral(src, summaries, conv_thresh=0.45, conv_min=2, pool=400, topk=8):
    sents=sentences(src)
    if len(sents)<3: return [], [], []
    Sv=E(sents); said=" ".join(summaries).lower(); srcl=src.lower()
    cen=Sv.mean(0); cen/=np.linalg.norm(cen)+1e-8
    pool_idx=np.argsort(-(V@cen))[:pool]
    rows=[]
    for i in pool_idx:
        w=VOCAB[i]
        if len(w)<4 or w in HARD: continue
        wv=V[i]; sims=Sv@wv
        conv=int(np.sum(sims>conv_thresh))
        if conv<conv_min: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', said): continue
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
        radius=1.0-float(np.max(sims))
        rows.append({"w":w,"conv":conv,"radius":radius,"idf":idf(w),"in_src":in_src})
    if not rows: return [], [], []
    idf_med=np.median([r["idf"] for r in rows])
    # negative-space band: not in source, IDF above median (meaningful, not noise)
    band=[r for r in rows if (not r["in_src"]) and r["idf"]>=idf_med]
    band.sort(key=lambda r:(-r["conv"], r["radius"]))
    # FIX 1+3: split entities (discard from feed, LOG as corpus-expectation fingerprint)
    concepts=[r for r in band if not is_entity(r["w"])]
    entities=[r for r in band if is_entity(r["w"])]
    concept_words=[r["w"] for r in concepts][:topk]
    entity_words=[r["w"] for r in entities][:topk]
    traversal=[(r["w"],r["conv"],round(r["radius"],2),round(r["idf"],2)) for r in concepts][:topk]
    return concept_words, entity_words, traversal

def main():
    stories=KV3.STORIES+[F.ADVERSARIAL]
    print("CONVERGENCE SPIRAL v2 (entity-scrubbed) vs FLAT RAYCAST\n")
    engF=F.build_engine(); out=[]
    for st in stories:
        src=st["source"]; cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print(f"{st['id']}: consensus<3 skip"); continue
        _,_,flat_concepts=F.derive_channels(src,cons,engF)
        spiral_concepts,spiral_entities,traversal=convergence_spiral(src,cons)
        novel=set(spiral_concepts)-set(flat_concepts)
        print(f"=== {st['id']} [{st['shape']}] ===")
        print(f"  FLAT            : {flat_concepts}")
        print(f"  SPIRAL concepts : {spiral_concepts}")
        print(f"  SPIRAL entities (DISCARDED from feed, logged as corpus-expectation): {spiral_entities}")
        print(f"  traversal (word, #conv, radius, idf):")
        for t in traversal: print(f"      {t}")
        print(f"  NOVEL concepts (spiral-only): {sorted(novel)}")
        print()
        out.append({"story":st["id"],"source":src,"flat":flat_concepts,
                    "spiral":spiral_concepts,"spiral_entities":spiral_entities,"novel":sorted(novel)})
    json.dump(out,open("spiral_concepts.json","w"),indent=2)
    ts=sum(len(o["spiral"]) for o in out); tn=sum(len(o["novel"]) for o in out)
    te=sum(len(o["spiral_entities"]) for o in out)
    print("="*60)
    print(f"{len(out)} stories: spiral concepts={ts}, novel-vs-flat={tn} ({tn/max(ts,1):.0%}), "
          f"entities-discarded-and-logged={te}")
    print("wrote spiral_concepts.json")
    print("idf actually loaded:", IDF_OK, "-- if False, radius/band ran on flat idf (convergence-only ranking)")
if __name__=="__main__": main()
