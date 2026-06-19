#!/usr/bin/env python3
"""
void_proper_test.py — test the ACTUAL void-word claim the way Sean means it, NOT a least-variance
SVD residual (that earlier test was the wrong operationalization and likely rigged to fail).

The real claim: a void word like 'wwiii' is a concept TOPICALLY CENTRAL to the story but ABSENT
from all five summaries. The honest question (Sean's "would margarita score the same?"):

  Is the surfaced void word (e.g. 'wwiii') genuinely closer to the story's content than:
    (A) a RANDOM control word (margarita, stapler, photosynthesis, ...)   [does it beat noise?]
    (B) the SAME void word measured against a RANDOM story's summaries     [is it THIS story's?]
    (C) words actually PRESENT in the summaries                            [how close vs the said?]

If the void word beats random words and beats random stories, it's a real topical-but-unsaid
signal. If margarita scores the same, the void words are noise and 2b should be downgraded.

Two embedding spaces measured (bge + e5) so the answer isn't model-bound.
Operationalization of 'closeness to the story': max cosine between the candidate word's embedding
and any SOURCE sentence (the story content), since void words are about the STORY's topical field.
Also report closeness to the SUMMARY field (what the models actually said) to show the gap.
"""
import json, glob, os, re, sys
from collections import defaultdict
import numpy as np
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]
CONTROL_WORDS=["margarita","stapler","photosynthesis","giraffe","tambourine","lasagna",
               "umbrella","glacier","accordion","cardigan","pomegranate","trombone"]
N_STORIES=150
def ts(f):
    m=re.match(r'(\d{8})_(\d{6})', os.path.basename(f)); return m.group(1)+m.group(2) if m else ""
def get_state(seg):
    for b in (seg.get("beats") or []):
        if "state_vector" in b.get("phase",""):
            if "EigenChing state:" in b.get("text",""): return True
    return False
def sent_split(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or "") if len(s.strip())>15]

def main():
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
        from scipy import stats
    except Exception as e:
        print("need sentence-transformers/sklearn/scipy:", e); sys.exit(1)
    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"))
    rows=[]
    for f in files:
        if "roundtable" in f: continue
        try: seg=json.load(open(f))
        except: continue
        a=seg.get("attribution") or {}
        t=(a.get("story_title","") or "").lower()
        if "iran" not in t: continue
        if not get_state(seg): continue
        vw=[w for w in (a.get("void_words",[]) or []) if w and len(w)>2]
        src=a.get("source_body","") or ""
        mr=a.get("model_responses",{}) or {}
        summ=" ".join(v for v in (mr.get(m,"") for m in ALLMODELS) if v)
        if not vw or len(src)<200 or len(summ)<100: continue
        # only keep void words genuinely ABSENT from the summaries (the real definition)
        vw=[w for w in vw if w.lower() not in summ.lower()]
        if not vw: continue
        rows.append({"vw":vw,"src":src,"summ":summ,"title":a.get("story_title","")[:50]})
    if len(rows)>N_STORIES: rows=rows[:N_STORIES]
    print(f"testing {len(rows)} Iran stories with absent void words\n")

    for MODEL,is_e5 in [("BAAI/bge-large-en-v1.5",False),("intfloat/e5-large-v2",True)]:
        print("="*84); print(f"EMBEDDING SPACE: {MODEL}"); print("="*84)
        enc=SentenceTransformer(MODEL)
        def emb(texts):
            tx=[("query: "+t) for t in texts] if is_e5 else list(texts)
            return enc.encode(tx, normalize_embeddings=True, show_progress_bar=False)
        # precompute control-word vectors
        cvecs=emb(CONTROL_WORDS)
        real_to_src=[]; ctrl_to_src=[]; real_to_randstory=[]; real_to_summ=[]
        srcsent_cache=[]
        for r in rows:
            ss=sent_split(r["src"])[:40]
            if not ss: srcsent_cache.append(None); continue
            srcsent_cache.append(emb(ss))
        for i,r in enumerate(rows):
            S=srcsent_cache[i]
            if S is None: continue
            # real void words -> closeness to THIS story's source field
            vv=emb(r["vw"])
            real_to_src.append(float(cosine_similarity(vv,S).max(axis=1).mean()))
            # control words -> same story
            ctrl_to_src.append(float(cosine_similarity(cvecs,S).max(axis=1).mean()))
            # real void words -> a RANDOM other story's source field
            j=(i+ len(rows)//2) % len(rows)
            Sj=srcsent_cache[j]
            if Sj is not None:
                real_to_randstory.append(float(cosine_similarity(vv,Sj).max(axis=1).mean()))
            # real void words -> the SUMMARY field (what models said)
            sm=sent_split(r["summ"])[:40]
            if sm:
                real_to_summ.append(float(cosine_similarity(vv,emb(sm)).max(axis=1).mean()))
            if i%40==0: print(f"  ...{i}/{len(rows)}")
        def m(x): return float(np.mean(x)) if x else float('nan')
        print(f"\n  void word -> THIS story's source field : {m(real_to_src):.3f}   (A: should be HIGH)")
        print(f"  control word -> THIS story's source     : {m(ctrl_to_src):.3f}   (the margarita baseline)")
        print(f"  void word -> RANDOM story's source      : {m(real_to_randstory):.3f}   (B: should be LOWER than A)")
        print(f"  void word -> THIS story's SUMMARY field : {m(real_to_summ):.3f}   (C: present-word ceiling)")
        # significance
        n=min(len(real_to_src),len(ctrl_to_src))
        if n>5:
            t1,p1=stats.wilcoxon(real_to_src[:n],ctrl_to_src[:n])
            print(f"\n  void vs control (margarita) closeness to source: Wilcoxon p={p1:.5f}")
            print(f"    -> {'VOID WORDS BEAT RANDOM WORDS (real signal)' if m(real_to_src)>m(ctrl_to_src) and p1<0.05 else 'void words NOT distinguishable from margarita (DEAD)'}")
        nb=min(len(real_to_src),len(real_to_randstory))
        if nb>5:
            t2,p2=stats.wilcoxon(real_to_src[:nb],real_to_randstory[:nb])
            print(f"  void@thisStory vs void@randomStory: Wilcoxon p={p2:.5f}")
            print(f"    -> {'void words are THIS-story-specific (real)' if m(real_to_src)>m(real_to_randstory) and p2<0.05 else 'void words not story-specific (generic topical words)'}")
        print()

if __name__=="__main__": main()
