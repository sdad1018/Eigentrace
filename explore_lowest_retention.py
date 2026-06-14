#!/usr/bin/env python3
"""
explore_lowest_retention.py — BOTTOM-UP: let the data hand us the next hypothesis.

For every source word across all stories, compute SEMANTIC retention (max cosine to
the model summaries — paraphrase-proof, NOT string matching). Aggregate per word
across all stories it appears in. Rank by LOWEST mean retention = words whose meaning
most reliably fails to survive summarization.

CRITICAL: semantic (not "did the string reappear") so this does NOT rebuild the
discredited absent-ratio metric. Frequency shown alongside so we don't mistake
'rare' for 'dropped'. Requires a word appear in >=N_MIN stories to rank (stable signal).

Output: lowest-retention words (the candidates for 'what models drop'), highest-retention
words (what survives), and a category peek. We READ this to FORM the next hypothesis —
which then needs its own confirmatory test. Exploratory, not confirmatory.
"""
import json, glob, os, re, sys
import numpy as np
from collections import defaultdict

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4
N_MIN_STORIES=8   # word must appear in >=8 stories to get a stable retention estimate
STOP=set("the a an and or but of to in on at for with from by as is are was were be been being this that these those it its their his her our your they them we you i he she him who whom which what when where why how than then so if not no nor can will would could should may might must have has had do does did about into over under up down out off more most some any all each both few many much other another such only own same said says new news first last year years day days time will also been being more into over after before during while because however".split())

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))

    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments...")
    word_rets=defaultdict(list)
    for fi,f in enumerate(files):
        if fi%1000==0: print(f"  [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=a.get("source_body","")or""; mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        summ=" ".join(mr.values())
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents)
        words=[w.lower() for w in re.findall(r"[A-Za-z]{4,}",src)]
        words=[w for w in dict.fromkeys(words) if w not in STOP]
        if len(words)<6: continue
        we=embed(words)
        for w,wv in zip(words,we):
            word_rets[w].append(float(np.max(se@wv)))

    # aggregate words appearing in enough stories
    stats=[(w,np.mean(r),len(r)) for w,r in word_rets.items() if len(r)>=N_MIN_STORIES]
    stats.sort(key=lambda x:x[1])  # lowest retention first
    print(f"\n=== {len(stats)} words appearing in >={N_MIN_STORIES} stories ===")
    print(f"Overall mean retention: {np.mean([s[1] for s in stats]):.4f}")

    print("\n=== 50 LOWEST-RETENTION WORDS (meaning most reliably NOT preserved) ===")
    print(f"{'word':<22}{'retention':<12}{'#stories'}")
    for w,r,n in stats[:50]:
        print(f"  {w:<20}{r:<12.4f}{n}")

    print("\n=== 25 HIGHEST-RETENTION WORDS (most reliably preserved) ===")
    for w,r,n in stats[-25:][::-1]:
        print(f"  {w:<20}{r:<12.4f}{n}")

    # save full ranking for offline inspection
    out={"n_words":len(stats),"min_stories":N_MIN_STORIES,
         "lowest":[{"word":w,"retention":round(r,4),"stories":n} for w,r,n in stats[:150]],
         "highest":[{"word":w,"retention":round(r,4),"stories":n} for w,r,n in stats[-50:]]}
    open("anamnesis_results/lowest_retention_words.json","w").write(json.dumps(out,indent=2))
    print("\nSaved full ranking: anamnesis_results/lowest_retention_words.json")
    print("\n>>> READ the lowest-retention list. What do those words have in common?")
    print(">>> That shared property = the next hypothesis (which then needs its OWN confirmatory test).")
    return 0
if __name__=="__main__": sys.exit(main())
