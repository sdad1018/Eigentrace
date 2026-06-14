#!/usr/bin/env python3
"""
test_decoupling.py — Does the "liability filter" hypothesis hold? i.e. do models
attenuate the ACTOR (who) more than the ACTION (what happened)?

HONEST LIMIT: without dependency parsing, "actor" vs "action" is approximated:
  ACTOR terms  = capitalized proper nouns / named entities in the source
                 (orgs, people, places, agencies — the "who")
  ACTION terms = lowercase verbs/consequence words (the "what")
This is a FIRST LOOK, not a parser-grade test. Stated as such.

Method:
  1. For each story, split source terms into ACTOR (proper-noun-like) vs ACTION (verb/consequence-like).
  2. Measure semantic retention of each class in the model summaries.
  3. Liability-filter predicts: ACTOR retained LESS than ACTION (who gets obscured, what is kept).
  4. NULL: random split -> no gap.
  5. BONUS: is actor-attenuation stronger for stories about AI developers? (entity-swap link)
"""
import json, glob, os, re, sys
import numpy as np

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4; N_NULL=200
AI_DEVS=["openai","anthropic","deepmind","google","meta","microsoft","xai","mistral","cohere","stability","midjourney","chatgpt","claude","gemini","grok","copilot","gpt","llm","a.i","artificial intelligence"]
STOP=set("the a an and or but of to in on at for with from by as is are was were be been being this that these those it its their his her our your they them we you i he she him who whom which what when where why how than then so if not no nor can will would could should may might must have has had do does did about into over under up down out off more most some any all each both few many much other another such only own same said says new news first last year years day days time".split())
ACTION_HINTS=set("killed devastated destroyed attacked seized forced caused announced launched signed banned removed fired arrested charged accused warned threatened struck bombed raided withdrew imposed lifted blocked seized halted resumed expanded cut raised lowered collapsed surged plunged ended began agreed refused denied confirmed revealed exposed concealed".split())

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))

    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments...")

    actor_ret=[]; action_ret=[]
    ai_actor_ret=[]; nonai_actor_ret=[]   # entity-swap link
    n_stories=0
    import time as _t; t0=_t.time()
    for fi,f in enumerate(files):
        if fi%1000==0: print(f"  [{fi}/{len(files)}] stories={n_stories}",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=a.get("source_body","")or""; mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        summ=" ".join(mr.values())
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents)
        if se.shape[0]==0: continue

        # ACTOR = capitalized multi/proper nouns in source (not sentence-start-only)
        # crude: words that appear Capitalized in the body and aren't common sentence starters
        tokens=re.findall(r"\b[A-Za-z]{3,}\b",src)
        cap_counts={}; low_set=set()
        for tk in tokens:
            if tk[0].isupper(): cap_counts[tk.lower()]=cap_counts.get(tk.lower(),0)+1
            else: low_set.add(tk.lower())
        # actor = appears capitalized and (rarely lowercased) -> proper noun-ish
        actors=[w for w,c in cap_counts.items() if w not in STOP and w not in low_set and len(w)>3]
        # action = lowercase verbs/consequence words
        actions=[w for w in low_set if (w in ACTION_HINTS) and w not in STOP]
        # supplement actions with lowercase 4+ verbs ending common verb forms if too few
        if len(actions)<2:
            actions += [w for w in low_set if w.endswith(("ed","ing")) and len(w)>4 and w not in STOP][:5]
        actors=list(dict.fromkeys(actors))[:12]; actions=list(dict.fromkeys(actions))[:12]
        if not actors or not actions: continue

        ae=embed(actors); ce=embed(actions)
        story_is_ai = any(dev in src.lower() for dev in AI_DEVS)
        for av in ae:
            r=float(np.max(se@av)); actor_ret.append(r)
            (ai_actor_ret if story_is_ai else nonai_actor_ret).append(r)
        for cv in ce:
            action_ret.append(float(np.max(se@cv)))
        n_stories+=1

    actor_ret=np.array(actor_ret); action_ret=np.array(action_ret)
    print(f"\n=== {n_stories} stories | actor terms={len(actor_ret)} action terms={len(action_ret)} ===")
    if len(actor_ret)<30 or len(action_ret)<30:
        print("insufficient — aborting"); return 1
    from scipy import stats
    t,p=stats.ttest_ind(action_ret,actor_ret,equal_var=False)  # H1: action>actor (actor obscured)
    sd=np.sqrt((actor_ret.var(ddof=1)+action_ret.var(ddof=1))/2); d=(action_ret.mean()-actor_ret.mean())/sd if sd>0 else 0
    print(f"\n=== LIABILITY FILTER: is ACTOR retained less than ACTION? ===")
    print(f"  Action retention: {action_ret.mean():.4f}  (n={len(action_ret)})")
    print(f"  Actor retention:  {actor_ret.mean():.4f}  (n={len(actor_ret)})")
    print(f"  Gap (action - actor): {action_ret.mean()-actor_ret.mean():+.4f}")
    print(f"  Welch t={t:.2f}  p={p:.2e}  d={d:.3f}")
    holds = p<0.01 and action_ret.mean()>actor_ret.mean()
    print(f"  -> {'SUPPORTS liability filter: actor obscured more than action' if holds else ('REVERSED: actor retained MORE than action' if action_ret.mean()<actor_ret.mean() else 'no sig difference')}")

    # null
    pooled=np.concatenate([actor_ret,action_ret]); na=len(actor_ret); ng=[]
    for _ in range(N_NULL):
        idx=np.random.permutation(len(pooled)); ng.append(pooled[idx[na:]].mean()-pooled[idx[:na]].mean())
    ng=np.array(ng); real=action_ret.mean()-actor_ret.mean(); nullp=float(np.mean(np.abs(ng)>=abs(real)))
    print(f"\n  NULL: gap_mean={ng.mean():+.4f} | real={real:+.4f} | frac null>=real={nullp:.4f} -> {'specific' if nullp<0.01 else 'within null'}")

    # entity-swap link: actor attenuation stronger for AI dev stories?
    ai=np.array(ai_actor_ret); nonai=np.array(nonai_actor_ret)
    print(f"\n=== BONUS: actor retention, AI-dev stories vs non-AI ===")
    if len(ai)>=30 and len(nonai)>=30:
        t2,p2=stats.ttest_ind(nonai,ai,equal_var=False)
        print(f"  AI-dev actor retention:  {ai.mean():.4f} (n={len(ai)})")
        print(f"  Non-AI actor retention:  {nonai.mean():.4f} (n={len(nonai)})")
        print(f"  Gap: {nonai.mean()-ai.mean():+.4f}  t={t2:.2f} p={p2:.2e}")
        print(f"  -> {'AI-dev actors retained LESS (consistent with entity-swap)' if p2<0.05 and ai.mean()<nonai.mean() else 'no clear AI-specific actor attenuation here'}")
    else:
        print(f"  insufficient AI-dev stories (ai={len(ai)},nonai={len(nonai)})")

    open("anamnesis_results/decoupling_results.json","w").write(json.dumps({
        "n_stories":n_stories,"action_ret":float(action_ret.mean()),"actor_ret":float(actor_ret.mean()),
        "gap_action_minus_actor":float(real),"p":float(p),"d":float(d),"null_p":nullp,
        "liability_filter_holds":bool(holds),
        "ai_actor_ret":float(ai.mean()) if len(ai)>0 else None,"nonai_actor_ret":float(nonai.mean()) if len(nonai)>0 else None},indent=2))
    print("\nSaved: anamnesis_results/decoupling_results.json")
    print("\nNOTE: actor/action split is heuristic (caps vs verbs), not dependency-parsed. First look, not final.")
    return 0
if __name__=="__main__": sys.exit(main())
