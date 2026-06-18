#!/usr/bin/env python3
"""
morphic_test.py — settle Gemini's Morphic Resonance with controls, not rhetoric.

Gemini correctly caught that my C3 was lexical (treating language like Lego). The fix
is geometric: void = cos(stake, source) - max(cos(stake, consensus)). Real reformulation.
BUT I predict it fails for an arithmetic reason: a SUMMARY embeds nearly identical to its
SOURCE (that's what "summary" means geometrically), so V_source ≈ V_consensus are TWINS,
and (source - consensus) is ≈ the NOISE between two near-identical vectors. The metric will
then rank concepts by abstraction-level + noise, NOT by real suppression — an abstraction-
detector cosplaying as a void-detector.

We settle it on TONIGHT'S CACHED DATA (no new LLM calls, pure geometry, ~minutes):

  TEST 1 — Gemini's exact Morphic Delta, ranked. (what does it surface?)
  TEST 2 — SHUFFLE CONTROL (the ballgame): does a concept score higher void against its
           OWN story's summaries than against a RANDOM story's summaries? Real suppression
           is story-specific; noise is not. If own ≈ random -> it's noise in a tuxedo.
  TEST 3 — ABSTRACTION CONFOUND: do abstract concepts win regardless of omission? Correlate
           void_score with concept abstraction (low mean-vocab-similarity = abstract).
  TEST 4 — HIGH-RES variant (the steelman / the fix): instead of ONE averaged source vector,
           embed source SENTENCE-by-sentence and take MAX resonance (does the concept light
           up some specific passage even if the doc-average washes it out?). Same for the
           shuffle control. If the REAL signal Gemini intuits exists, it should show up here
           (survive shuffling) when we stop averaging into twins.

Reuses the extruded concepts by RE-EXTRUDING with one fast model (or we just reuse a fixed
set). To stay zero-API we RECOMPUTE concepts cheaply from one local model; if Ollama is up
we use Qwen, else we fall back to a fixed concept list per story. Geometry is the point.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=3

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    # static vocab only to measure "abstraction" (a concept's mean similarity to common vocab;
    # abstract concepts sit far from concrete vocab)
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)

    # try Qwen for concepts; else fixed lists (geometry is what we're testing, not extraction)
    import requests
    OLLAMA=os.getenv("OLLAMA_GENERATE_URL","http://localhost:11434/api/generate")
    def qwen(prompt):
        try:
            r=requests.post(OLLAMA,json={"model":"qwen2.5:14b","prompt":prompt,"stream":False,
                "options":{"temperature":0.0}},timeout=120); r.raise_for_status()
            return r.json().get("response","")
        except Exception as e:
            return ""
    def extrude(src):
        txt=qwen("Identify the 25 most profound high-stakes philosophical, systemic, or "
                 "existential consequences/themes governing this text. Return ONLY a comma-"
                 "separated list of abstract nouns or short concepts. No preamble.\n\nTEXT: "+src[:2000])
        cs=[c.strip().lower() for c in txt.split(",") if 2<=len(c.strip())<=40]
        return list(dict.fromkeys(cs))[:25]

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]
    def is_story(a):
        mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
        return len(s)>=4 and a.get("source_body") and not any(x in a.get("story_title","").lower() for x in SKIP)
    CUE=["war","iran","sanction","nuclear","trade","strait","russia","china"]
    stories=[]
    for f in sorted(SEGS,reverse=True):
        if len(stories)>=N_STORIES: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            if sum(c in a.get("story_title","").lower() for c in CUE)<1: continue
            sums=[v for k,v in a["model_responses"].items() if v and len(v)>50]
            stories.append({"title":a["story_title"],"source":a["source_body"][:2500],
                            "summaries":sums})
        except: pass
    if len(stories)<2:
        print("need >=2 stories with source_body"); return

    # extrude concepts per story
    for s in stories:
        s["concepts"]=extrude(s["source"])
        print(f"[{s['title'][:50]}] {len(s['concepts'])} concepts: {s['concepts'][:6]}...")

    def morphic(concepts, source_vec, summ_vecs):
        cv=E(concepts); src_res=cv@source_vec
        cons_res=(cv@summ_vecs.T).max(axis=1)
        delta=src_res-cons_res
        return delta, src_res, cons_res

    def abstraction(concepts):
        # low max-similarity to common vocab = abstract; concrete words have a near vocab hit
        cv=E(concepts); m=(V16.astype(np.float32))@cv.T   # (vocab, n)
        return 1.0 - m.max(axis=0)   # high = abstract (far from any concrete vocab word)

    # precompute per-story doc vectors (averaged — Gemini's design) and sentence vectors (hi-res)
    for s in stories:
        s["src_doc"]=E([s["source"]])[0]
        sents=[x.strip() for x in re.split(r'(?<=[.!?])\s+', s["source"]) if len(x.strip())>20]
        s["src_sents"]=E(sents) if sents else E([s["source"]])
        s["summ_doc"]=E(s["summaries"])
        all_summ_sents=[]
        for sm in s["summaries"]:
            all_summ_sents+= [x.strip() for x in re.split(r'(?<=[.!?])\s+', sm) if len(x.strip())>10]
        s["summ_sents"]=E(all_summ_sents) if all_summ_sents else E(s["summaries"])

    print("\n"+"="*72)
    print("TEST 1 — Gemini's Morphic Delta (averaged source vs averaged summaries)")
    print("="*72)
    for s in stories:
        delta,sr,cr=morphic(s["concepts"], s["src_doc"], s["summ_doc"])
        order=np.argsort(-delta)
        print(f"\n[{s['title'][:50]}] top morphic voids:")
        for i in order[:6]:
            print(f"   {s['concepts'][i]:35s} void={delta[i]:+.3f}  (src={sr[i]:.3f} cons={cr[i]:.3f})")

    print("\n"+"="*72)
    print("TEST 2 — SHUFFLE CONTROL (the ballgame): own-story vs random-story summaries")
    print("  real suppression is story-specific; noise scores the same against any summaries")
    print("="*72)
    for i,s in enumerate(stories):
        own_delta,_,_=morphic(s["concepts"], s["src_doc"], s["summ_doc"])
        # score same concepts+source against OTHER stories' summaries
        cross=[]
        for j,o in enumerate(stories):
            if j==i: continue
            d,_,_=morphic(s["concepts"], s["src_doc"], o["summ_doc"])
            cross.append(d)
        cross_delta=np.mean(cross,axis=0)
        # if void is real, own_delta should be SYSTEMATICALLY > cross_delta (own summaries
        # suppress MORE than random summaries). measure mean difference + how often own>cross.
        diff=own_delta-cross_delta
        print(f"\n[{s['title'][:50]}]")
        print(f"   mean(own_void - cross_void) = {diff.mean():+.4f}   (>0 means own summaries suppress more)")
        print(f"   concepts where own>cross: {int((diff>0).sum())}/{len(diff)}")
        print(f"   corr(own_void, cross_void) = {np.corrcoef(own_delta,cross_delta)[0,1]:.3f}  (near 1.0 = identical = NOISE)")

    print("\n"+"="*72)
    print("TEST 3 — ABSTRACTION CONFOUND: does void_score just track abstraction?")
    print("="*72)
    for s in stories:
        delta,_,_=morphic(s["concepts"], s["src_doc"], s["summ_doc"])
        abst=abstraction(s["concepts"])
        c=np.corrcoef(delta,abst)[0,1]
        print(f"[{s['title'][:42]}] corr(void_score, abstraction) = {c:+.3f}  "
              f"({'VOID IS JUST ABSTRACTION' if c>0.5 else 'not strongly abstraction' if abs(c)<0.3 else 'partial'})")

    print("\n"+"="*72)
    print("TEST 4 — HIGH-RES (the fix/steelman): sentence-MAX source & summary instead of doc-avg")
    print("  does the real signal show up when we DON'T average into twins? + shuffle control")
    print("="*72)
    def morphic_hires(concepts, src_sents, summ_sents):
        cv=E(concepts)
        src_res=(cv@src_sents.T).max(axis=1)     # resonates with SOME source sentence
        cons_res=(cv@summ_sents.T).max(axis=1)   # captured by SOME summary sentence
        return src_res-cons_res
    for i,s in enumerate(stories):
        own=morphic_hires(s["concepts"], s["src_sents"], s["summ_sents"])
        cross=[]
        for j,o in enumerate(stories):
            if j==i: continue
            cross.append(morphic_hires(s["concepts"], s["src_sents"], o["summ_sents"]))
        cross=np.mean(cross,axis=0); diff=own-cross
        order=np.argsort(-own)
        print(f"\n[{s['title'][:50]}] hi-res top voids:")
        for k in order[:5]:
            print(f"   {s['concepts'][k]:35s} void={own[k]:+.3f}")
        print(f"   SHUFFLE: mean(own-cross)={diff.mean():+.4f}  own>cross:{int((diff>0).sum())}/{len(diff)}  "
              f"corr={np.corrcoef(own,cross)[0,1]:.3f}")

    print("\n"+"="*72)
    print("VERDICT KEYS:")
    print(" T2/T4 shuffle: if corr(own,cross)~1.0 and mean(own-cross)~0 -> NOISE (Claude right)")
    print("               if own systematically > cross -> real story-specific suppression (Gemini right)")
    print(" T3: if corr(void,abstraction)>0.5 -> the 'void' is just an abstraction-detector")
    print(" T4 vs T1: if hi-res survives shuffle but doc-avg doesn't -> the FIX works (stop averaging into twins)")

if __name__=="__main__":
    main()
