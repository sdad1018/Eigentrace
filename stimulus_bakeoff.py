#!/usr/bin/env python3
"""
stimulus_bakeoff.py — which STIMULUS makes the models do the best Summary Plus work?

The void words aren't the product; they're STIMULUS to prime the models into a
productive region. So we hold the story fixed, vary the stimulus, let models write
the second-pass summary for each, and score which stimulus yielded the most
genuinely-new, self-standing, on-topic content.

Tests the hypothesis: messy/specific words (tillerson) may be BETTER stimulus than
clean role-labels ("former Secretary of State") because they open richer latent
nodes (the "oil fascism node") — IF that produces real new on-topic ground, not
derailment or name-parroting.

STIMULUS CONDITIONS per story:
  0. NOTHING        — plain re-summarize (floor)
  1. DONUT_RAW      — the raw donut void words (tillerson, brics, ...)
  2. DONUT_RELABEL  — same voids, relabeled to roles (former US Secretary of State)
  3. COMPOSE_CLOUD  — the composition concepts (story (+) void -> petro-diplomacy...)
  4. COMPOSE+RAW    — raw voids AND their composition concepts together

METRIC (b) — PersistentRelevantNovelty (the metric we evolved):
  new units = Units(S1) minus Units(S0)
  keep units that are:
    PERSISTENT  — NOT just a lexical echo of the stimulus (low cosine to stimulus
                  words / different stem). webcam->'media feed' fails (echo);
                  desalination->'water infrastructure' passes (real consequence).
    RELEVANT    — near the STORY centroid (on-topic). catches derailment:
                  tillerson->'refinery throughput' fails (off-topic) even though
                  it persists.
  score = |new AND persistent AND relevant|   + CoverageGain fraction
Also prints all summaries labeled for (a) eyeball.

API (model calls) + GPU (embeds). Stream stopped. ~4 stories x 5 conditions x 2 models.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

N_STORIES=4
WRITERS=["ChatGPT","Gemini"]      # 2 models write second-pass (comparing stimuli, not models)
TOPK_NN=12; N_VOIDS=3; N_COMPOSE=5
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
RELEVANCE_THRESH=0.35             # new unit must be >= this cosine to story centroid
ECHO_THRESH=0.62                  # new unit >= this cosine to a stimulus word = echo (non-persistent)
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot"}
SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    judge=pa.BIG5_CALLERS["DeepSeek"]   # for relabel only
    writers={w:pa.BIG5_CALLERS[w] for w in WRITERS}

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

    # ---- content unit extraction (noun-phrase-ish: content words, drop stopwords) ----
    STOP=set("the a an and or but of to in on at for with as by from is are was were be been being "
             "this that these those it its their there here said says will would could can may has have "
             "had do does did not no than then so such also more most into over under after before "
             "about against between during which who whom whose what when where why how".split())
    def units(text):
        toks=re.findall(r"[a-z][a-z\-']+", text.lower())
        toks=[t for t in toks if t not in STOP and len(t)>3]
        # bigrams + unigrams as candidate units
        bigrams=[f"{toks[i]} {toks[i+1]}" for i in range(len(toks)-1)]
        return set(toks)|set(bigrams)

    # ---- pick charged stories ----
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
        cp=(f"For each term, if it's a stale/specific named person or org, give its durable ROLE "
            f"(e.g. 'tillerson' -> 'a former US Secretary of State'; 'brics' -> 'an emerging-economy bloc'). "
            f"If it's already a general concept, repeat it. One per line 'N. <label>':\n{listing}")
        rt,_=judge(cp); out={}
        for line in (rt or "").splitlines():
            m=re.match(r'\s*(\d+)\.\s*(.+)',line)
            if m:
                i=int(m.group(1))-1
                if 0<=i<len(vws): out[vws[i]]=m.group(2).strip()
        return out

    def write(model_fn, title, instruction):
        p=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. {instruction} "
           f"Stay faithful to the story; invent nothing.")
        s,_=model_fn(p); return (s or "").strip()

    results=[]   # per story: condition -> {summaries, score}
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
            # composition cloud
            cloud=[]
            for vw in raw_voids:
                if vw not in widx: continue
                Q=compose(centroid,V[widx[vw]])
                for w in nn(Q,TOPK_NN):
                    if w in HARD_DROP or w.lower() in tl or w in raw_voids or w in cloud: continue
                    cloud.append(w)
                    if len(cloud)>=N_COMPOSE*2: break
            cloud=cloud[:N_COMPOSE]

            conditions={
              "0_nothing":      "",
              "1_donut_raw":    f"Consider working in these related concepts if they fit: {', '.join(raw_voids)}.",
              "2_donut_relabel":f"Consider working in these related concepts if they fit: {', '.join(relabeled)}.",
              "3_compose_cloud":f"Consider working in these related concepts if they fit: {', '.join(cloud)}.",
              "4_compose+raw":  f"Consider working in these related concepts if they fit: {', '.join(raw_voids+cloud)}.",
            }
            stimulus_words={
              "0_nothing":[], "1_donut_raw":raw_voids, "2_donut_relabel":relabeled,
              "3_compose_cloud":cloud, "4_compose+raw":raw_voids+cloud}

            print("="*72); print(f"STORY: {title[:60]} (vix {vix:.0f})")
            print(f"  raw voids: {raw_voids}")
            print(f"  relabeled: {relabeled}")
            print(f"  compose cloud: {cloud}")
            story_res={"title":title,"raw_voids":raw_voids,"relabeled":relabeled,"cloud":cloud,"conditions":{}}

            # baseline S0 per writer (nothing condition)
            for cond,instr in conditions.items():
                cond_scores=[]; cond_summaries={}
                for wn,wf in writers.items():
                    s1=write(wf,title,instr)
                    cond_summaries[wn]=s1
                    # baseline = this writer's "nothing" summary
                    if cond=="0_nothing":
                        cond_scores.append(0); continue
                    s0=story_res["conditions"]["0_nothing"]["summaries"][wn]
                    u0=units(s0); u1=units(s1)
                    new=u1-u0
                    # filter: persistent (not echo of stimulus) AND relevant (near story)
                    stim=stimulus_words[cond]
                    stim_vecs=E(stim) if stim else np.zeros((1,1024))
                    keep=[]
                    for u in new:
                        uv=E([u])[0]
                        rel=float(uv@centroid)
                        echo=float(np.max(stim_vecs@uv)) if stim else 0
                        if rel>=RELEVANCE_THRESH and echo<ECHO_THRESH:
                            keep.append(u)
                    prn=len(keep)
                    cg=len(new)/max(len(u1),1)
                    cond_scores.append(prn)
                    cond_summaries[f"{wn}_kept"]=keep
                story_res["conditions"][cond]={"summaries":cond_summaries,
                    "persistent_relevant_novelty":np.mean(cond_scores) if cond!="0_nothing" else 0}
            # print
            for cond in conditions:
                cr=story_res["conditions"][cond]
                sc=cr["persistent_relevant_novelty"]
                print(f"\n  [{cond}] PersistentRelevantNovelty={sc:.1f}")
                for wn in writers:
                    print(f"    {wn}: {cr['summaries'][wn][:160]}")
                    if cond!="0_nothing" and f"{wn}_kept" in cr['summaries']:
                        print(f"      ^new/persistent/relevant: {cr['summaries'][f'{wn}_kept']}")
            results.append(story_res); done+=1
        except Exception as e:
            print(f"skip: {str(e)[:60]}")

    # aggregate ranking
    print("\n"+"="*72); print("AGGREGATE — mean PersistentRelevantNovelty per stimulus condition")
    print("="*72)
    conds=["0_nothing","1_donut_raw","2_donut_relabel","3_compose_cloud","4_compose+raw"]
    agg={c:np.mean([r["conditions"][c]["persistent_relevant_novelty"] for r in results]) for c in conds}
    for c in sorted(conds,key=lambda c:-agg[c]):
        print(f"  {c:18s} {agg[c]:.2f}")
    best=max(agg,key=agg.get)
    print(f"\n  WINNER: {best}")
    print("  (does raw beat relabel? does composition beat raw donut? does the messy")
    print("   stimulus open richer on-topic nodes, or derail? the number + your eyeball decide.)")

if __name__=="__main__":
    main()
