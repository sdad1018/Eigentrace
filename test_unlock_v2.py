#!/usr/bin/env python3
"""
test_unlock_v2.py — Unlock test, judge redesigned to fix the two bugs the debug
exposed:

BUG 1 (faithfulness punished elaboration): old judge marked faithful=no when S1
added ANY content beyond base — punishing the exact unlock we want. FIX:
faithfulness = FABRICATION check ("does S1 assert something the SOURCE contradicts
or cannot support?"). Elaboration is fine; only invention fails.

BUG 2 (unlock saturated at 2 for everything): independent consequence/actor/
constraint binaries all fired on every war summary. FIX: WITHIN-STORY COMPARATIVE
RANKING. Give the judge ALL candidates' summaries for one story at once; it ranks
which add the most SPECIFIC, NON-OBVIOUS dimension. Comparison forces discrimination
(can't rubber-stamp everything when forced to rank).

Proven: judge CAN discriminate (hezbollah faithful+unlock vs webcam all-no on stark
case). The old prompt wasted that. This asks the right questions.

Re-anchored 0.4/0.6 blend recall, clean vocab. temp=0. bge+API. Stream stopped.
"""
import json, os, sys, glob, shutil, tempfile, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

N_STORIES=4
TOP_N=12
AUTHOR="ChatGPT"     # one author for clean comparison (the S1 generator)
JUDGE="DeepSeek"     # cross-model judge
HEAD_W, CENT_W = 0.4, 0.6

def main():
    import proxy_auditor as pa
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    author=pa.BIG5_CALLERS[AUTHOR]; judge=pa.BIG5_CALLERS[JUDGE]
    print(f"author: {AUTHOR} | judge: {JUDGE}\n", flush=True)

    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","ceasefire","summit","iran","ukraine","russia","israel","gaza"]
    stories=[]
    for f in segs:
        if len(stories)>=N_STORIES: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{}); sums={k:v for k,v in mr.items() if v and len(v)>50}
            if len(sums)<4: continue
            title=a.get("story_title","")
            if sum(c in title.lower() for c in cue)<1: continue
            vecs=E(list(sums.values())); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=blend,
                                  k=TOP_N, outer_threshold=0.55)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            base=" ".join(list(sums.values())[:2])[:600]
            stories.append((title, base, cands))
        except: pass
    print(f"{len(stories)} stories\n", flush=True)

    calls=0
    for title, base, cands in stories:
        print("="*72); print(f"[{title[:60]}]"); print(f"  candidates: {cands}\n", flush=True)
        # STEP 1: author writes a FORCED-incorporation summary for each candidate
        summaries={}
        for w in cands:
            ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary of this story that "
                f"MUST meaningfully incorporate the concept '{w}'. Do not refuse or hedge about "
                f"relevance — work it in as naturally as you can. Stay consistent with the story; "
                f"do not invent specific facts.")
            s1,e=author(ap); calls+=1
            if s1 and len(s1.strip())>20: summaries[w]=s1.strip()

        # STEP 2: faithfulness = FABRICATION check (per candidate, elaboration OK)
        faithful={}
        for w,s1 in summaries.items():
            fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\n"
                f"Does this summary assert any SPECIFIC FACT that the source story contradicts or "
                f"could not support? Adding interpretation, context, or implications is FINE — only "
                f"flag INVENTED specifics (fake numbers, fake events, fake quotes). "
                f"Answer EXACTLY one word: CLEAN (no fabrication) or FABRICATED.")
            ft,e=judge(fp); calls+=1
            faithful[w] = "clean" in (ft or "").lower() and "fabricat" not in (ft or "").lower().split("clean")[0]
            # simpler: CLEAN present and not FABRICATED
            faithful[w] = "clean" in (ft or "").lower()

        # STEP 3: WITHIN-STORY comparative ranking of explanatory unlock
        clean_cands=[w for w in summaries if faithful.get(w)]
        if len(clean_cands)>=2:
            listing="\n".join(f"  {i+1}. [{w}] {summaries[w]}" for i,w in enumerate(clean_cands))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {base}\n\n"
                f"Below are {len(clean_cands)} candidate summaries, each built around a different "
                f"concept. Rank the TOP 3 that add the most SPECIFIC, NON-OBVIOUS explanatory "
                f"dimension to understanding this story — a new consequence, actor, or mechanism a "
                f"reader wouldn't already assume. Penalize ones that just restate the obvious topic.\n\n"
                f"{listing}\n\n"
                f"Answer EXACTLY: 'TOP3: [concept1], [concept2], [concept3]' using the bracketed concept words.")
            rt,e=judge(rp); calls+=1
            print(f"  faithfulness (CLEAN/FABRICATED):")
            for w in cands:
                mark = "CLEAN" if faithful.get(w) else ("FABRICATED" if w in summaries else "no-summary")
                print(f"     {w:18s} {mark}")
            print(f"\n  JUDGE TOP-3 RANKING (raw): {(rt or '').strip()}")
            # parse top3
            top3=re.findall(r'\[([^\]]+)\]', rt or "")
            print(f"  >>> CROWNED (most explanatory unlock): {top3[:3]}")
        else:
            print(f"  too few clean candidates to rank ({clean_cands})")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: are the CROWNED (top-3 ranked) concepts the genuinely illuminating")
    print("ones, vs the restatement/obvious ones ranked low? And does FABRICATED correctly")
    print("flag only invented-fact summaries, not mere elaboration?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
