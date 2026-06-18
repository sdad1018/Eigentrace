#!/usr/bin/env python3
"""
build_composition_reveal.py — the Atlas v2 centerpiece data: the void->composition
reveal. For each story: the on-topic-ABSENT void (donut) AND the story-specific
concepts that void COMPOSES to (validated: china (+) ww3 -> tiananmen).

This is the thing Atlas v1 never showed. v1 stopped at "here's the absent void"
(the old crowning). v2 shows where the void LEADS when conditioned on the story:
  story -> [donut void: ww3] -> [compose story(+)void: tiananmen, nanking, kuomintang]

The composition step is VALIDATED (stress_ab: cross-story overlap ~0.03, interpretable
story-specific concepts, random-word null produces higher overlap + junk). Breadth-rank
(also validated) keeps the productive composition concepts.

Honest label: story-specific concepts the omission OPENS ONTO. Not causal consequences
(bge = similarity, not causality); composition reaches story-conditioned associations.

Writes docs/atlas_data.json with a new 'reveals' block (keeps v1 landscape/domains).
bge GPU + clean tensor. API only for the optional void-relabel. Stream stopped.
"""
import json, os, sys, glob, time, shutil
from collections import Counter
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OUT="/mnt/c/Users/M4ISI/eigentrace/docs/atlas_data.json"

SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]
N_STORIES=18                 # high-signal stories to reveal
TOPK_NN=12; N_VOIDS=3        # voids per story to show
N_COMPOSE=5                  # composition concepts per void
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","linus","scotus","gops","wot"}

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t): 
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    print("loading clean tensor...", flush=True)
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
    print(f"  {len(words)} concepts\n", flush=True)

    def nn(vec,k=TOPK_NN):
        s=(V16.astype(np.float32))@vec; return [words[i] for i in np.argsort(-s)[:k]]
    def breadth(w):
        if w not in widx: return 0.0
        nb=nn(V[widx[w]],TOPK_NN); vs=np.array([V[widx[x]] for x in nb if x in widx])
        if len(vs)<3: return 0.0
        S=vs@vs.T; n=len(vs); return 1-(S.sum()-n)/(n*n-n)
    def compose(a,b,al=0.5):
        q=(1-al)*a+al*b; return q/(np.linalg.norm(q)+1e-8)

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    def is_story(a):
        mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
        t=a.get("story_title","").lower()
        return len(s)>=4 and not any(x in t for x in SKIP)
    CUE=["war","strike","nuclear","ceasefire","sanction","missile","iran","ukraine","russia",
         "china","israel","gaza","strait","blockade","escalat","regime","collapse","trade"]

    cands=[]
    for f in sorted(SEGS,reverse=True):
        if len(cands)>=N_STORIES*4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            t=a.get("story_title","")
            if sum(c in t.lower() for c in CUE)<1: continue
            cands.append((a.get("mean_vix",0),a))
        except: pass
    cands.sort(key=lambda x:-x[0])

    reveals=[]; seen=set()
    print("building void->composition reveals...", flush=True)
    for vix,a in cands:
        if len(reveals)>=N_STORIES: break
        title=a.get("story_title","").strip()
        if title.lower() in seen: continue
        seen.add(title.lower())
        sums={k:v for k,v in a["model_responses"].items() if v and len(v)>50}
        try:
            text=" ".join(sums.values()); tl=text.lower()
            cvecs=E(list(sums.values())); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8

            # DONUT: on-topic absent voids (re-anchored), breadth-ranked to keep productive
            sims=(V16.astype(np.float32))@blend
            cand=np.argsort(-sims)[:200]; voids=[]
            for i in cand:
                w=words[i]
                if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
                voids.append((w,breadth(w)))
            voids.sort(key=lambda x:-x[1])         # productive (broad) voids first
            top_voids=[w for w,_ in voids[:N_VOIDS]]
            if not top_voids: continue

            # COMPOSITION: each void (+) story -> story-specific concepts (breadth-ranked)
            void_blocks=[]
            for vw in top_voids:
                if vw not in widx: continue
                Q=compose(centroid, V[widx[vw]])
                reach=nn(Q,TOPK_NN)
                comp=[]
                for w in reach:
                    if w in HARD_DROP or w.lower() in tl or w==vw: continue
                    if w in top_voids: continue
                    comp.append({"c":w,"b":round(breadth(w),3)})
                comp=comp[:N_COMPOSE]
                void_blocks.append({"void":vw,"leads_to":comp})
            if not void_blocks: continue

            reveals.append({
                "title":title,"url":a.get("story_url",""),"category":a.get("category",""),
                "mean_vix":round(vix,1),
                "consensus":" ".join(list(sums.values())[:2])[:340],
                "voids":void_blocks,    # [{void, leads_to:[{c,b}]}]
            })
            lead_demo=void_blocks[0]
            print(f"  [{len(reveals)}/{N_STORIES}] {title[:38]:40s} {lead_demo['void']} -> {[x['c'] for x in lead_demo['leads_to'][:3]]}", flush=True)
        except Exception as e:
            print(f"   skip: {str(e)[:40]}")

    # merge into existing atlas_data.json (keep v1 blocks)
    try: payload=json.load(open(OUT))
    except: payload={}
    payload["reveals"]=reveals
    payload["reveals_generated_at"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    payload["reveals_method"]=("story -> donut (on-topic absent, breadth-ranked) -> "
        "composition story(+)void -> story-specific concepts the omission opens onto. "
        "composition & breadth validated against controls; not causal consequences.")
    with open(OUT,"w") as fh: json.dump(payload,fh,indent=2)
    shutil.copy(OUT,"atlas_data.json")
    print(f"\nwrote {len(reveals)} reveals -> {OUT}")
    print("\nSAMPLE (the chart data):")
    for r in reveals[:3]:
        print(f"\n  {r['title'][:55]}")
        for vb in r['voids']:
            print(f"    [{vb['void']}] -> {', '.join(x['c'] for x in vb['leads_to'])}")

if __name__=="__main__":
    main()
