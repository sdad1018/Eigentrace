#!/usr/bin/env python3
"""
bakeoff_read.py — print FULL untruncated second-pass summaries per stimulus
condition, side by side, with word-counts, for human eyeballing. No metric, no
truncation — just read which stimulus makes the best Summary Plus.

Adds condition 5_compose+relabel (the cleaned composition + relabeled voids) to
test "the combination is the secret sauce" — raw richness vs clean roles vs both.

Pick a few charged stories, one writer (or two), print everything full.
API + GPU. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=3
WRITERS=["ChatGPT"]      # one writer, full output, easy to read; add Gemini if you want
TOPK_NN=12; N_VOIDS=3; N_COMPOSE=5
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot"}
SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    judge=pa.BIG5_CALLERS["DeepSeek"]; writers={w:pa.BIG5_CALLERS[w] for w in WRITERS}
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
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
    CUE=["war","iran","strait","sanction","nuclear","trade","oil","energy","russia","china"]
    cands=[]
    for f in sorted(SEGS,reverse=True):
        if len(cands)>=N_STORIES*4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            if sum(c in a.get("story_title","").lower() for c in CUE)<1: continue
            cands.append((a.get("mean_vix",0),a))
        except: pass
    cands.sort(key=lambda x:-x[0])

    def relabel(vws):
        listing="\n".join(f"  {i+1}. {w}" for i,w in enumerate(vws))
        cp=(f"For each term, if it's a stale/specific named person or org, give its durable ROLE. "
            f"If already general, repeat it. One per line 'N. <label>':\n{listing}")
        rt,_=judge(cp); out={}
        for line in (rt or "").splitlines():
            m=re.match(r'\s*(\d+)\.\s*(.+)',line)
            if m:
                i=int(m.group(1))-1
                if 0<=i<len(vws): out[vws[i]]=m.group(2).strip()
        return out
    def write(fn,title,instr):
        p=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. {instr} "
           f"Stay faithful to the story; invent nothing.")
        s,_=fn(p); return (s or "").strip()
    def wc(s): return len(s.split())

    done=0
    for vix,a in cands:
        if done>=N_STORIES: break
        title=a.get("story_title","").strip()
        sums={k:v for k,v in a["model_responses"].items() if v and len(v)>50}
        try:
            cvecs=E(list(sums.values())); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
            text=" ".join(sums.values()); tl=text.lower()
            sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
            voids=[]
            for i in cand:
                w=words[i]
                if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
                voids.append((w,breadth(w)))
            voids.sort(key=lambda x:-x[1]); raw_voids=[w for w,_ in voids[:N_VOIDS]]
            if not raw_voids: continue
            rl=relabel(raw_voids); relabeled=[rl.get(w,w) for w in raw_voids]
            cloud=[]
            for vw in raw_voids:
                if vw not in widx: continue
                Q=compose(centroid,V[widx[vw]])
                for w in nn(Q,TOPK_NN):
                    if w in HARD_DROP or w.lower() in tl or w in raw_voids or w in cloud: continue
                    cloud.append(w)
                    if len(cloud)>=N_COMPOSE*2: break
            cloud=cloud[:N_COMPOSE]

            conds={
              "0_nothing":"",
              "1_donut_raw":f"Consider working in these related concepts if they fit: {', '.join(raw_voids)}.",
              "2_donut_relabel":f"Consider working in these related concepts if they fit: {', '.join(relabeled)}.",
              "3_compose_cloud":f"Consider working in these related concepts if they fit: {', '.join(cloud)}.",
              "4_compose+raw":f"Consider working in these related concepts if they fit: {', '.join(raw_voids+cloud)}.",
              "5_compose+relabel":f"Consider working in these related concepts if they fit: {', '.join(relabeled+cloud)}.",
            }
            print("\n"+"#"*74)
            print(f"# STORY: {title}")
            print(f"# raw voids:  {raw_voids}")
            print(f"# relabeled:  {relabeled}")
            print(f"# compose:    {cloud}")
            print("#"*74)
            for cond,instr in conds.items():
                for wn,wf in writers.items():
                    s=write(wf,title,instr)
                    print(f"\n[{cond}]  ({wc(s)} words)")
                    print(f"  {s}")
            done+=1
        except Exception as e:
            print(f"skip: {str(e)[:60]}")

if __name__=="__main__":
    main()
