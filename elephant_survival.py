#!/usr/bin/env python3
"""elephant_survival.py -- stochastic-resonance scorer. Sample void distribution K times with
temperature; survival-frequency x IDF scores each word. High-survival NAMED ENTITIES = reader-facing
elephants (Mossad that keeps appearing); low-survival = scrubbed ghosts. Noise stress-tests the real
geometry; survival-across-samples is the score. NOT noise-as-oracle."""
import os, sys, json, re, argparse
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
def build_engine():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t])); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    try: DF=json.load(open("void_frequency.json")).get("global",{})
    except Exception: DF={}
    return E,V,vt_words,DF
def idf(w,DF,NDOCS=1659.0): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0
def stochastic_survival(src,summaries,eng,K=40,temp=0.15,pool=300,top_slice=20):
    E,V,vt_words,DF=eng
    REL=getattr(C,"REL_THRESH",0.45); HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    anchor=E(src[:2000])[0]; sims=V@anchor; order=np.argsort(-sims)[:pool]
    alltext=" ".join(summaries).lower(); srcl=src.lower(); cand=[]
    for i in order:
        w=vt_words[i]; s=float(sims[i])
        if len(w)<4 or w in HARD or s<REL: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl)); cand.append((w,s,in_src))
    if not cand: return [], {}, {}
    words=[c[0] for c in cand]; simvec=np.array([c[1] for c in cand]); insrc={c[0]:c[2] for c in cand}
    z=(simvec-simvec.max())/max(temp,1e-3); p=np.exp(z); p=p/p.sum()
    rng=np.random.default_rng(); counts={w:0 for w in words}; n=min(top_slice,len(words))
    for _ in range(K):
        draw=rng.choice(len(words),size=n,replace=False,p=p)
        for j in draw: counts[words[j]]+=1
    return cand, {w:counts[w]/K for w in words}, insrc
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--story-id"); ap.add_argument("--source-file")
    ap.add_argument("--samples",type=int,default=40); ap.add_argument("--temp",type=float,default=0.15)
    ap.add_argument("--elephant-thresh",type=float,default=0.5)
    a=ap.parse_args()
    if a.source_file: src=open(a.source_file).read().strip(); sid=os.path.basename(a.source_file)
    elif a.story_id:
        st=next((s for s in KV3.STORIES if s["id"]==a.story_id), None)
        if not st: print(f"options: {[s['id'] for s in KV3.STORIES]}"); return
        src=st["source"]; sid=st["id"]
    else: print("need --story-id or --source-file"); return
    print(f"=== Elephant Survival :: {sid} :: K={a.samples} temp={a.temp} ===\n",flush=True)
    eng=build_engine(); E,V,vt_words,DF=eng; cons=[]
    for m in C.LOCAL_PATIENTS:
        s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
        if s: cons.append(s)
    if len(cons)<3:
        b=C.API_PATIENTS["Claude"]([{"role":"user","content":"Summarize in 3-4 sentences:\n\n"+src[:1700]}]) or ""; cons=[b]
    cand,survival,insrc=stochastic_survival(src,cons,eng,K=a.samples,temp=a.temp)
    if not survival: print("no candidates"); return
    rows=[]
    for w,_,_ in cand:
        is_ent=False
        try: is_ent=KV3.is_named_entity(w)
        except Exception: pass
        rows.append({"word":w,"survival":survival[w],"idf":idf(w,DF),"score":survival[w]*idf(w,DF),"entity":is_ent,"in_src":insrc[w]})
    rows.sort(key=lambda r:-r["score"])
    print(f"{'word':18s} {'surv':>5s} {'idf':>5s} {'score':>6s}  kind")
    for r in rows[:20]:
        print(f"{r['word']:18s} {r['survival']:>5.2f} {r['idf']:>5.2f} {r['score']:>6.2f}  {'ENTITY' if r['entity'] else 'concept'}")
    elephants=[r for r in rows if r["entity"] and r["survival"]>=a.elephant_thresh]
    ghosts=[r for r in rows if r["entity"] and r["survival"]<a.elephant_thresh]
    print(f"\n--- READER-FACING ELEPHANTS (entity, survival >= {a.elephant_thresh}) ---")
    if elephants:
        for r in elephants: print(f"  {r['word']} (surv {r['survival']:.2f}, idf {r['idf']:.2f}) -> 'geometry places story near {r['word'].upper()}, unstated in source'")
    else: print("  (none -> no buried elephant; entity-candidates all flickering ghosts)")
    print(f"\n--- SCRUBBED GHOSTS (entity, survival < {a.elephant_thresh}, kept OUT of prompt) ---")
    print("  "+(", ".join(f"{r['word']}({r['survival']:.2f})" for r in ghosts) if ghosts else "(none)"))
    out={"story":sid,"K":a.samples,"temp":a.temp,"elephants":[{"word":r["word"],"survival":r["survival"],"idf":r["idf"]} for r in elephants],"ghosts":[r["word"] for r in ghosts],"concepts":[r["word"] for r in rows if not r["entity"]][:8]}
    json.dump(out,open(f"elephant_{sid}.json","w"),indent=2)
    print(f"\nwrote elephant_{sid}.json")
if __name__=="__main__": main()
