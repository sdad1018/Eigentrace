#!/usr/bin/env python3
"""
test_unlock_v4.py — Unlock pipeline, parser now resolves BOTH formats.

v3 WORKED on all 5 stories — but DeepSeek answered some as concept WORDS
(Lebanon: 'arms embargo, death toll, peacekeepers') and some as LIST NUMBERS
('TOP3: 11, 4, 9'). Decoding the numbers by hand showed the picks were GOOD
(arms race, civilian casualties, isil). So the metric is consistent; only the
display broke.

FIX: parse_top3 now accepts words OR numbers, resolving numbers back to the
concept word via the listing index. Also harden the prompt to prefer words.

This is the confirmation run: do the crowns display cleanly as Band-2 concepts
(arms race / arms embargo / proxy war / civilian casualties / isil) over the
demoted obvious/restatement (war / trump / tehran / controversy) across all 5?

Re-anchored 0.3/0.7 recall, clean vocab, fabrication-faithfulness, comparative
ranking. temp=0. bge+API. Stream stopped.
"""
import json, os, sys, glob, shutil, tempfile, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=5; TOP_N=12; AUTHOR="ChatGPT"; JUDGE="DeepSeek"
HEAD_W, CENT_W = 0.3, 0.7; OUTER=0.58

def parse_top3(txt, clean_cands):
    """Accept words OR list-numbers; resolve numbers to concept words."""
    if not txt: return []
    m=re.search(r'top\s*3?\s*:?\s*(.+)', txt, re.I)
    tail=m.group(1) if m else txt
    tail=tail.replace('[','').replace(']','')
    raw=[x.strip().strip('.').strip() for x in re.split(r'[,\n]', tail)]
    out=[]
    low_map={c.lower():c for c in clean_cands}
    for x in raw:
        if not x: continue
        # is it a pure number? -> resolve via 1-based index into clean_cands
        if re.fullmatch(r'\d+', x):
            idx=int(x)-1
            if 0<=idx<len(clean_cands): out.append(clean_cands[idx])
        else:
            # match to a candidate word (exact or contained)
            xl=x.lower()
            if xl in low_map: out.append(low_map[xl])
            else:
                hit=[c for c in clean_cands if c.lower()==xl or c.lower() in xl or xl in c.lower()]
                if hit: out.append(hit[0])
                elif len(x)<40: out.append(x)  # keep as-is fallback
        if len(out)>=3: break
    return out

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
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=blend, k=TOP_N, outer_threshold=OUTER)
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
            ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary that MUST meaningfully "
                f"incorporate the concept '{w}'. Do not refuse or hedge; work it in naturally. "
                f"Stay consistent with the story; do not invent specific facts.")
            s1,e=author(ap); calls+=1
            if s1 and len(s1.strip())>20: summaries[w]=s1.strip()
        faithful={}
        for w,s1 in summaries.items():
            fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\nDoes this summary assert any SPECIFIC "
                f"FACT the source contradicts or can't support? Interpretation/context/implications "
                f"are FINE — only flag INVENTED specifics. Answer one word: CLEAN or FABRICATED.")
            ft,e=judge(fp); calls+=1
            faithful[w]="clean" in (ft or "").lower()
        clean_cands=[w for w in summaries if faithful.get(w)]
        fab=[w for w in summaries if not faithful.get(w)]
        if fab: print(f"  FABRICATED (excluded): {fab}")
        if len(clean_cands)>=2:
            listing="\n".join(f"  {i+1}. [{w}] {summaries[w]}" for i,w in enumerate(clean_cands))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {base}\n\nBelow are candidate summaries, each "
                f"built around a different concept. Rank the TOP 3 that add the most SPECIFIC, "
                f"NON-OBVIOUS explanatory dimension — a new consequence, actor, or mechanism a reader "
                f"wouldn't already assume. Penalize ones that just restate the obvious topic.\n\n{listing}\n\n"
                f"Answer using the CONCEPT WORDS in brackets, exactly: TOP3: word1, word2, word3")
            rt,e=judge(rp); calls+=1
            top3=parse_top3(rt, clean_cands)
            print(f"  JUDGE RAW: {(rt or '').strip()[:90]}")
            print(f"  >>> CROWNED: {top3}")
            demoted=[w for w in clean_cands if w.lower() not in [t.lower() for t in top3]]
            print(f"      demoted: {demoted}")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: do crowns display cleanly as Band-2 (arms race/embargo/proxy war/")
    print("civilian casualties/isil) over demoted obvious (war/trump/tehran)? all 5 stories?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
