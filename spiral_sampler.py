#!/usr/bin/env python3
"""spiral_sampler.py v3 -- convergence spiral, PHRASE-AWARE entity scrub.
Fix this round: is_named_entity choked on multi-word phrases, discarding 'coup attempt',
'foreign interference', 'failed state' AS IF entities. New rule: a candidate is an entity
only if it contains a PROPER-NOUN TOKEN (khomeini, mossad). Multi-word concept-phrases with
no proper-noun token are KEPT. This keeps the loaded frame-level concepts while still killing
the corpus stock-actors."""
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

IDF_OK=False; NDOCS=1659
try:
    VF=json.load(open("void_frequency.json"))
    if isinstance(VF,dict) and VF:
        _vals=[v for v in VF.values() if isinstance(v,(int,float))]
        NDOCS=max(_vals) if _vals else 1659; IDF_OK=True
        # report coverage: how many spiral-ish words are actually keys?
        def idf(w): return float(np.log((NDOCS+1)/(VF.get(w,1)+1)))
        def in_vf(w): return w in VF
    else:
        def idf(w): return 1.0
        def in_vf(w): return False
except Exception as e:
    print(f"  [IDF load failed: {e}]")
    def idf(w): return 1.0
    def in_vf(w): return False

HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

def token_is_entity(tok):
    """single-token entity test -- the part is_named_entity does handle."""
    try: return KV3.is_named_entity(tok)
    except Exception: return False

# common concept-phrase heads that should NEVER be treated as entities even if a token trips the probe
CONCEPT_SAFE={"attempt","interference","state","change","strike","deal","fire","embargo",
              "occupation","rights","crisis","conflict","force","action","zone","cover","failure"}

def is_entity_phraseaware(w):
    """A candidate is an entity only if it has a proper-noun token AND isn't a known concept phrase."""
    toks=w.split()
    if len(toks)==1:
        return token_is_entity(w)              # single word: trust the probe
    # multi-word: entity only if SOME token is a proper-noun entity and NO token is a concept-safe head
    if any(t in CONCEPT_SAFE for t in toks):
        return False                            # 'coup attempt','foreign interference','failed state' -> concept
    ent_tokens=[t for t in toks if token_is_entity(t) and len(t)>3]
    return len(ent_tokens)>=1                    # 'al qaeda','kim jong' -> entity; 'arms deal' -> concept

def sentences(src):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', src) if len(s.strip())>15]

def convergence_spiral(src, summaries, conv_thresh=0.45, conv_min=2, pool=400, topk=8):
    sents=sentences(src)
    if len(sents)<3: return [], [], []
    Sv=E(sents); said=" ".join(summaries).lower(); srcl=src.lower()
    cen=Sv.mean(0); cen/=np.linalg.norm(cen)+1e-8
    pool_idx=np.argsort(-(V@cen))[:pool]
    rows=[]; vf_hits=0
    for i in pool_idx:
        w=VOCAB[i]
        if len(w)<4 or w in HARD: continue
        wv=V[i]; sims=Sv@wv
        conv=int(np.sum(sims>conv_thresh))
        if conv<conv_min: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', said): continue
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
        if in_vf(w): vf_hits+=1
        rows.append({"w":w,"conv":conv,"radius":1.0-float(np.max(sims)),"idf":idf(w),"in_src":in_src})
    if not rows: return [], [], []
    idf_med=np.median([r["idf"] for r in rows])
    band=[r for r in rows if (not r["in_src"]) and r["idf"]>=idf_med]
    band.sort(key=lambda r:(-r["conv"], r["radius"]))
    concepts=[r for r in band if not is_entity_phraseaware(r["w"])]
    entities=[r for r in band if is_entity_phraseaware(r["w"])]
    cw=[r["w"] for r in concepts][:topk]; ew=[r["w"] for r in entities][:topk]
    trav=[(r["w"],r["conv"],round(r["radius"],2)) for r in concepts][:topk]
    return cw, ew, trav

def main():
    stories=KV3.STORIES+[F.ADVERSARIAL]
    print(f"[IDF loaded:{IDF_OK} NDOCS:{NDOCS}]  CONVERGENCE SPIRAL v3 (phrase-aware scrub)\n")
    engF=F.build_engine(); out=[]
    for st in stories:
        src=st["source"]; cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print(f"{st['id']}: skip"); continue
        _,_,flat_concepts=F.derive_channels(src,cons,engF)
        sc,se,trav=convergence_spiral(src,cons)
        novel=set(sc)-set(flat_concepts)
        print(f"=== {st['id']} [{st['shape']}] ===")
        print(f"  FLAT            : {flat_concepts}")
        print(f"  SPIRAL concepts : {sc}")
        print(f"  entities (killed): {se}")
        print(f"  NOVEL (spiral-only): {sorted(novel)}")
        print()
        out.append({"story":st["id"],"source":src,"flat":flat_concepts,"spiral":sc,"spiral_entities":se,"novel":sorted(novel)})
    json.dump(out,open("spiral_concepts.json","w"),indent=2)
    ts=sum(len(o["spiral"]) for o in out); tn=sum(len(o["novel"]) for o in out)
    print("="*60)
    print(f"{len(out)} stories: spiral concepts={ts}, novel-vs-flat={tn} ({tn/max(ts,1):.0%})")
    print("wrote spiral_concepts.json")
if __name__=="__main__": main()
