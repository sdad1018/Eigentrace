#!/usr/bin/env python3
"""
explore_clean_v2.py — cleaned bottom-up explorer. Filters non-English tokens and
tags each low-retention word as PROPER-NAME-like vs common, to test the lead:
"minor proper names (esp. post-2024-cutoff actors) get dropped."

Cleaning:
  - Drop tokens with non-ASCII / clearly non-English fragments.
  - Require word to be a plausible English word OR a proper-name-like capitalized
    token in source. Drop scraping garbage (búsqueda, agrega, cobertura, etc).
  - Tag PROPER (appears capitalized in source, rarely lowercase) vs COMMON.

Output: cleaned lowest-retention list, split into PROPER NAMES vs COMMON WORDS,
so we can SEE whether the 'minor names drop' pattern survives decontamination.
"""
import json, glob, os, re, sys
import numpy as np
from collections import defaultdict

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4; N_MIN=8
STOP=set("the a an and or but of to in on at for with from by as is are was were be been being this that these those it its their his her our your they them we you i he she him who whom which what when where why how than then so if not no nor can will would could should may might must have has had do does did about into over under up down out off more most some any all each both few many much other another such only own same said says new news first last year years day days time will also been being more into over after before during while because however told according during amid".split())

# common English words we keep even if short-ish; reject obvious non-English
def looks_english(w):
    if not w.isascii(): return False
    # reject tokens with no vowels (likely garbage/abbrev) unless short
    if len(w)>4 and not re.search(r"[aeiouy]",w): return False
    # reject known spanish/scrape fragments
    if w in {"agrega","cobertura","busqueda","squeda","touska","sobre","para","como","desde","entre","cuando"}: return False
    return True

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))

    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments...")
    word_rets=defaultdict(list); cap_count=defaultdict(int); low_count=defaultdict(int)
    for fi,f in enumerate(files):
        if fi%1000==0: print(f"  [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=a.get("source_body","")or""; mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        # only proceed if source is mostly english (ascii ratio)
        if sum(c.isascii() for c in src)/max(len(src),1) < 0.95: continue
        summ=" ".join(mr.values())
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents)
        # track capitalization for proper-noun detection
        for tk in re.findall(r"\b[A-Za-z]{3,}\b",src):
            if tk[0].isupper(): cap_count[tk.lower()]+=1
            else: low_count[tk.lower()]+=1
        words=[w.lower() for w in re.findall(r"[A-Za-z]{4,}",src)]
        words=[w for w in dict.fromkeys(words) if w not in STOP and looks_english(w)]
        if len(words)<6: continue
        we=embed(words)
        for w,wv in zip(words,we):
            word_rets[w].append(float(np.max(se@wv)))

    def is_proper(w):
        c,l=cap_count.get(w,0),low_count.get(w,0)
        return c>=3 and c>l  # mostly capitalized => proper-noun-like

    stats=[(w,np.mean(r),len(r),is_proper(w)) for w,r in word_rets.items() if len(r)>=N_MIN]
    stats.sort(key=lambda x:x[1])
    print(f"\n=== {len(stats)} clean words (>={N_MIN} stories) | overall ret {np.mean([s[1] for s in stats]):.4f} ===")

    proper=[s for s in stats if s[3]]
    common=[s for s in stats if not s[3]]
    print(f"Proper-name-like: {len(proper)}  | Common: {len(common)}")
    print(f"Mean retention — proper names: {np.mean([s[1] for s in proper]):.4f} | common words: {np.mean([s[1] for s in common]):.4f}")

    print("\n=== 30 LOWEST-RETENTION PROPER NAMES (the cutoff-hypothesis candidates) ===")
    for w,r,n,_ in proper[:30]:
        print(f"  {w:<20}{r:<10.4f}{n} stories")

    print("\n=== 30 LOWEST-RETENTION COMMON WORDS ===")
    for w,r,n,_ in common[:30]:
        print(f"  {w:<20}{r:<10.4f}{n} stories")

    print("\n=== 15 HIGHEST-RETENTION PROPER NAMES (well-known? pre-cutoff?) ===")
    for w,r,n,_ in proper[-15:][::-1]:
        print(f"  {w:<20}{r:<10.4f}{n} stories")

    out={"n":len(stats),
         "proper_mean_ret":float(np.mean([s[1] for s in proper])),"common_mean_ret":float(np.mean([s[1] for s in common])),
         "lowest_proper":[{"w":w,"ret":round(r,4),"n":n} for w,r,n,_ in proper[:60]],
         "highest_proper":[{"w":w,"ret":round(r,4),"n":n} for w,r,n,_ in proper[-30:]],
         "lowest_common":[{"w":w,"ret":round(r,4),"n":n} for w,r,n,_ in common[:60]]}
    open("anamnesis_results/clean_retention_v2.json","w").write(json.dumps(out,indent=2))
    print("\nSaved: anamnesis_results/clean_retention_v2.json")
    print("\n>>> Look at LOWEST PROPER NAMES: are they post-2024-cutoff figures (Baghaei, Araghchi...)?")
    print(">>> And HIGHEST PROPER NAMES: are they pre-cutoff-famous (Hamas, NATO, Trump...)?")
    print(">>> If yes -> the cutoff-familiarity hypothesis has real support to design a confirmatory test.")
    return 0
if __name__=="__main__": sys.exit(main())
