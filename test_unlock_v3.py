#!/usr/bin/env python3
"""
test_unlock_v3.py — Unlock test, two sharpening fixes over v2:

v2 WORKED: ranking crowned hezbollah #1 (over combat/skirmish restatement) and
proxy war (over cnbc/potus). The metric carves Band 2. Two issues remained:

FIX 1 (parser): v2's TOP3 parse only caught BRACKETED concepts ([hezbollah]).
DeepSeek inconsistently used brackets, so hezbollah/proxy-war showed CROWNED=[]
even though the raw ranking was correct. FIX: parse the comma list after 'TOP3:'
bracket-or-not.

FIX 2 (anchor): the 0.4/0.6 blend at threshold 0.55 still let 'quiet'-synonym junk
(silence/tranquil/pausing) into Lebanon's recall. The anchor-eyeball showed
pure-centroid NAILED Lebanon (ethnic cleansing, foreign interference, refugees).
FIX: push blend toward centroid (0.3 head / 0.7 cent) + threshold 0.58.

Re-anchored recall, clean vocab, fabrication-faithfulness, within-story comparative
ranking. temp=0. bge+API. Stream stopped.
"""
import json, os, sys, glob, shutil, tempfile, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

N_STORIES=5
TOP_N=12
AUTHOR="ChatGPT"; JUDGE="DeepSeek"
HEAD_W, CENT_W = 0.3, 0.7      # FIX 2: more centroid
OUTER = 0.58                    # FIX 2: tighter outer ring

def parse_top3(txt):
    """FIX 1: parse TOP3 list bracket-or-not."""
    if not txt: return []
    m=re.search(r'top\s*3?\s*:?\s*(.+)', txt, re.I)
    if not m: return []
    tail=m.group(1)
    # strip brackets if present, split on commas
    tail=tail.replace('[','').replace(']','')
    items=[x.strip().strip('.').strip() for x in tail.split(',')]
    return [x for x in items if x and len(x)<40][:3]

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
    print(f"author: {AUTHOR} | judge: {JUDGE} | anchor: {HEAD_W}h/{CENT_W}c outer={OUTER}\n", flush=True)

    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","ceasefire","summit","iran","ukraine","russia","israel","gaza","sanctions"]
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
                                  k=TOP_N, outer_threshold=OUTER)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            base=" ".join(list(sums.values())[:2])[:600]
            stories.append((title, base, cands))
        except: pass
    print(f"{len(stories)} stories\n", flush=True)

    calls=0
    for title, base, cands in stories:
        print("="*72); print(f"[{title[:60]}]"); print(f"  recall: {cands}\n", flush=True)
        summaries={}
        for w in cands:
            ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary of this story that "
                f"MUST meaningfully incorporate the concept '{w}'. Do not refuse or hedge about "
                f"relevance — work it in as naturally as you can. Stay consistent with the story; "
                f"do not invent specific facts.")
            s1,e=author(ap); calls+=1
            if s1 and len(s1.strip())>20: summaries[w]=s1.strip()

        faithful={}
        for w,s1 in summaries.items():
            fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\n"
                f"Does this summary assert any SPECIFIC FACT that the source story contradicts or "
                f"could not support? Adding interpretation/context/implications is FINE — only flag "
                f"INVENTED specifics (fake numbers, fake events, fake quotes). "
                f"Answer EXACTLY one word: CLEAN or FABRICATED.")
            ft,e=judge(fp); calls+=1
            faithful[w]="clean" in (ft or "").lower()

        clean_cands=[w for w in summaries if faithful.get(w)]
        fab=[w for w in summaries if not faithful.get(w)]
        if fab: print(f"  FABRICATED (excluded): {fab}")
        if len(clean_cands)>=2:
            listing="\n".join(f"  {i+1}. [{w}] {summaries[w]}" for i,w in enumerate(clean_cands))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {base}\n\n"
                f"Below are candidate summaries, each built around a different concept. Rank the TOP 3 "
                f"that add the most SPECIFIC, NON-OBVIOUS explanatory dimension to understanding this "
                f"story — a new consequence, actor, or mechanism a reader wouldn't already assume. "
                f"Penalize ones that just restate the obvious topic.\n\n{listing}\n\n"
                f"Answer EXACTLY: TOP3: concept1, concept2, concept3")
            rt,e=judge(rp); calls+=1
            top3=parse_top3(rt)
            print(f"  JUDGE RANKING (raw): {(rt or '').strip()[:100]}")
            print(f"  >>> CROWNED: {top3}")
            # show what was NOT crowned (the demoted restatement/obvious)
            demoted=[w for w in clean_cands if w.lower() not in [t.lower() for t in top3]]
            print(f"      demoted (lower unlock): {demoted}")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: (1) is Lebanon recall now clean (no silence/tranquil junk)?")
    print("  (2) are CROWNED the illuminating concepts, demoted the restatement/obvious?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
