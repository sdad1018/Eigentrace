#!/usr/bin/env python3
"""
corpus_void_target.py — run the VALIDATED confront10 derive() per-story across the
CLEAN corpus (real news stories only), aggregate void + target words by domain.

This is the exact derivation that survived the 10-patient conceptual-seed experiment
and the margarita test. NOT a reinvention:
  - anchor = E(source)           (embed the SOURCE, not the summaries)
  - sims   = V @ anchor          (cosine of every vocab word vs the source)
  - keep top POOL=300, drop <4 chars, drop HARD_DROP junk, drop sim<REL_THRESH=0.45,
    AND drop anything already present in the model consensus text
  - split via ABSTRACT-CONCRETE axis (the EXACT poles, locked from the experiment):
       av = E(word) @ ac
       void   = words with av >= 0   (abstract stakes:  escalation/regime collapse/wwiii)
       target = words with av <  0   (concrete specifics: hormuz/refineries/the strait)

CLEAN corpus: excludes the 11 non-story segment types we found contaminating the 5170
(idle 5895, wild_weasel, governance, foraging, silence, consolidation, weekly_compression,
self_audit, conversation, epistemic_battery, roundtable). Real stories only: title+source_body.

Per-story grain (the MIT-honest choice): each story re-derived from its OWN source,
then aggregated. Writes corpus_void_target.json for eyeballing before any chart.

GPU run (embeds every story's source vs frozen vocab) -> needs broadcast stopped.
"""
import os, sys, json, glob, re
import numpy as np
from collections import Counter, defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]

# ---- the EXACT confront10 derive() constants (locked, do not tune) ----
REL_THRESH=0.45; POOL=300
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
ABSTRACT_POLES=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE_POLES=["strait","city","company","port","bank","border","weapon","official"]

# ---- non-story segment types to EXCLUDE (the 5170 contamination) ----
NONSTORY={"idle","wild_weasel","governance","foraging","silence","consolidation",
          "weekly_compression","self_audit","conversation","epistemic_battery","roundtable"}

def is_real_story(seg, a):
    st=str(seg.get("type") or seg.get("segment_type") or a.get("type") or "").lower()
    if st in NONSTORY: return False
    title=a.get("story_title") or a.get("title") or ""
    src=a.get("source_body") or ""
    return bool(title) and len(src)>=400

def get_state(seg):
    for b in (seg.get("beats") or []):
        if "state_vector" in b.get("phase",""):
            if "EigenChing state:" in b.get("text",""): return True
    return False

def domain_of(title, cat):
    if cat:
        c=cat.lower()
        # normalize to the live atlas_data.json domains
        if c in ("war","markets","general","tech","geopolitics","incidents"): return c
    t=title.lower()
    if any(k in t for k in ["iran","tehran","strait of hormuz","khamenei","ayatollah"]): return "iran_war"
    if any(k in t for k in ["gaza","israel","ukraine","russia","nato","war","strike","ceasefire","missile","troops","military"]): return "other_conflict"
    if any(k in t for k in ["stock","market","oil price","inflation","fed","earnings","trade","economy"]): return "markets"
    if any(k in t for k in ["openai","chip","software","cyber","datacenter","ai "]): return "tech"
    return "general"

def is_iran(title):
    t=title.lower()
    return ("iran" in t or "tehran" in t or "hormuz" in t or "khamenei" in t or "ayatollah" in t)

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    # frozen vocab + its embeddings (the V matrix from confront10)
    vt=json.load(open("vocab/global_vocab_clean.json"))
    vt_words=vt["words"] if isinstance(vt,dict) else vt
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    print(f"vocab: {len(vt_words)} words, V shape {V.shape}")

    # the abstract-concrete axis (exact poles)
    ac=E(ABSTRACT_POLES).mean(0)-E(CONCRETE_POLES).mean(0); ac/=np.linalg.norm(ac)+1e-8

    def derive(paste, responses):
        anchor=E(paste[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(responses).lower(); surf=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue   # in consensus -> not a void
            surf.append(w)
        if not surf: return [],[]
        av=E(surf)@ac
        void  =[w for w,a in zip(surf,av) if a>=0]      # abstract stakes
        target=[w for w,a in zip(surf,av) if a<0]       # concrete specifics
        return void,target

    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"))
    void_overall=Counter(); target_overall=Counter()
    void_by_dom=defaultdict(Counter); target_by_dom=defaultdict(Counter)
    void_iran=Counter(); target_iran=Counter()
    dom_count=Counter()
    n_real=0; n_derived=0
    per_story=[]   # keep a few examples for eyeballing

    for f in files:
        try: seg=json.load(open(f))
        except: continue
        a=seg.get("attribution") or {}
        if not is_real_story(seg,a): continue
        if not get_state(seg): continue
        title=a.get("story_title") or a.get("title") or ""
        src=a.get("source_body","") or ""
        mr=a.get("model_responses",{}) or {}
        resp=[mr.get(m,"") for m in ALLMODELS if mr.get(m) and len(mr.get(m))>50]
        if len(resp)<4: continue
        n_real+=1
        void,target=derive(src,resp)
        if not void and not target: continue
        n_derived+=1
        dom=domain_of(title, a.get("category") or a.get("domain"))
        dom_count[dom]+=1
        for w in void:   void_overall[w]+=1;   void_by_dom[dom][w]+=1
        for w in target: target_overall[w]+=1; target_by_dom[dom][w]+=1
        if is_iran(title):
            for w in void:   void_iran[w]+=1
            for w in target: target_iran[w]+=1
        if len(per_story)<8:
            per_story.append({"title":title[:60],"domain":dom,
                              "void":void[:8],"target":target[:8]})

    print(f"\nCLEAN real stories processed: {n_real}  (with >=1 void/target: {n_derived})")
    print(f"(excluded idle/roundtable/etc. — the 5170 was contaminated; real ~1659)")
    print(f"domain counts: {dict(dom_count)}")

    print("\n"+"="*70); print("VOID WORDS (abstract stakes, av>=0) — overall top 30"); print("="*70)
    for w,n in void_overall.most_common(30): print(f"  {n:>4d}  {w}")
    print("\n"+"="*70); print("TARGET WORDS (concrete specifics, av<0) — overall top 30"); print("="*70)
    for w,n in target_overall.most_common(30): print(f"  {n:>4d}  {w}")

    print("\n--- IRAN stories specifically ---")
    print("VOID:", [w for w,_ in void_iran.most_common(15)])
    print("TARGET:", [w for w,_ in target_iran.most_common(15)])

    print("\n--- a few per-story examples (eyeball the void/target split) ---")
    for s in per_story:
        print(f"\n[{s['domain']}] {s['title']}")
        print(f"  VOID(abstract): {s['void']}")
        print(f"  TARGET(concrete): {s['target']}")

    out={"n_real_stories":n_real,"n_derived":n_derived,
         "method":"confront10 derive() per-story: anchor=E(source), sims=V@anchor, top300, REL_THRESH0.45, drop HARD_DROP+in-consensus, split by ABSTRACT-CONCRETE axis (av>=0 void / av<0 target). Poles locked from the 10-patient experiment.",
         "abstract_poles":ABSTRACT_POLES,"concrete_poles":CONCRETE_POLES,
         "domain_counts":dict(dom_count),
         "void_overall":dict(void_overall.most_common(40)),
         "target_overall":dict(target_overall.most_common(40)),
         "void_by_dom":{d:dict(c.most_common(20)) for d,c in void_by_dom.items()},
         "target_by_dom":{d:dict(c.most_common(20)) for d,c in target_by_dom.items()},
         "void_iran":dict(void_iran.most_common(25)),
         "target_iran":dict(target_iran.most_common(25)),
         "examples":per_story}
    json.dump(out,open("corpus_void_target.json","w"),indent=2)
    print(f"\nwrote corpus_void_target.json")

if __name__=="__main__": main()
