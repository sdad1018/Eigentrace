#!/usr/bin/env python3
"""
test_unlock_v6.py — Unlock pipeline, relabel now an explicit THREE-WAY decision.

v5's relabel had only keep/DEAD, and DEAD conflated TWO different things:
  - "temporally stale" (the intended meaning), AND
  - "off-topic for this story" (a relevance call that's the ranking's job).
Result: HRC (a Democrat, on a POLITICS story — category IS relevant) wrongly
DEAD-ed, while pompeo correctly got its category ripped. Inconsistent.
But forcing a category on EVERY name (v6-naive) over-flattens: ronaldo on an
Iran story -> "a global sports superstar" is word-mush, worse than DEAD.

The real distinction (user-diagnosed): does the CATEGORY this actor marks open a
REAL ANGLE on THIS story? HRC->yes (opposition angle on a Trump/G7 story).
ronaldo->no (sports noise on Iran diplomacy). So relabel gets THREE choices:

  1. KEEP unchanged  -> durable concept or still-live actor
                        (civilian casualties, arms embargo, hezbollah)
  2. RIP CATEGORY    -> stale filler BUT its category opens a real story angle
                        (pompeo -> "the US chief diplomat";
                         hrc -> "a senior opposition/Democratic figure")
                        target the 'chief diplomat' abstraction level: a fillable
                        role/category, NOT a bare generic ('a politician').
  3. DROP            -> named actor whose category does NOT open a real angle here;
                        it surfaced from shallow co-occurrence (ronaldo on Iran).

Safety net: even if an over-flattened generic slips through as RIP, the ranking
buries it (sports-superstar can't outrank arms-embargo on an Iran story). The
crown is protected; only the demoted bin risks mild flattening.

Pipeline: recall -> THREE-WAY relabel -> fabrication gate -> ranking -> crown.
0.3/0.7 anchor. temp=0. bge+API. Stream stopped.
"""
import json, os, sys, glob, shutil, tempfile, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=5; TOP_N=12; AUTHOR="ChatGPT"; JUDGE="DeepSeek"
HEAD_W, CENT_W = 0.3, 0.7; OUTER=0.58

def parse_top3(txt, cc):
    if not txt: return []
    m=re.search(r'top\s*3?\s*:?\s*(.+)', txt, re.I); tail=(m.group(1) if m else txt).replace('[','').replace(']','')
    raw=[x.strip().strip('.').strip() for x in re.split(r'[,\n]', tail)]; out=[]; lm={c.lower():c for c in cc}
    for x in raw:
        if not x: continue
        if re.fullmatch(r'\d+', x):
            i=int(x)-1
            if 0<=i<len(cc): out.append(cc[i])
        else:
            xl=x.lower()
            if xl in lm: out.append(lm[xl])
            else:
                h=[c for c in cc if c.lower()==xl or c.lower() in xl or xl in c.lower()]
                out.append(h[0] if h else (x if len(x)<45 else None))
        out=[o for o in out if o]
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
    print(f"author: {AUTHOR} | judge: {JUDGE} | anchor: {HEAD_W}h/{CENT_W}c | 3-way relabel\n", flush=True)

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

        # --- THREE-WAY RELABEL ---
        listing="\n".join(f"  {i+1}. {w}" for i,w in enumerate(cands))
        cp=(f"Story: {title}\n\nThese terms surfaced from a FROZEN embedding space as concepts latent "
            f"to this story. For EACH, choose ONE action and answer in the exact format 'N. <action>':\n\n"
            f"KEEP <term> — if it's a durable concept (e.g. 'civilian casualties') or a still-current, "
            f"still-relevant named actor (e.g. an organization that currently exists and fits the story). "
            f"Output: KEEP <the term unchanged>\n\n"
            f"CATEGORY <label> — if it's a STALE named actor (former official, past-era figure) BUT the "
            f"CATEGORY it represents opens a REAL angle on THIS story. Rip the category, not the actor. "
            f"Use a FILLABLE role/category at a useful level — like 'the US chief diplomat' or 'a senior "
            f"opposition figure', NOT a bare generic like 'a person' or 'a politician'. The actor may be "
            f"stale but the ROLE is live. Output: CATEGORY <the role/category label>\n\n"
            f"DROP — if it's a named actor whose category does NOT open a real angle on THIS story (it "
            f"surfaced from shallow word co-occurrence, e.g. a sports figure on a diplomacy story). "
            f"Do not force a category onto off-topic noise. Output: DROP\n\n"
            f"Be willing to use all three. KEEP durable concepts. CATEGORY stale-but-relevant roles. "
            f"DROP only off-topic-noise names.\n\n{listing}\n\n"
            f"Answer one per line, EXACTLY: N. KEEP <term>  /  N. CATEGORY <label>  /  N. DROP")
        ct,e=judge(cp); calls+=1
        action={}  # word -> ('keep'|'category'|'drop', label)
        for line in (ct or "").splitlines():
            m=re.match(r'\s*(\d+)\.\s*(KEEP|CATEGORY|DROP)\b\s*(.*)', line, re.I)
            if m:
                i=int(m.group(1))-1
                if 0<=i<len(cands):
                    act=m.group(2).lower(); lab=m.group(3).strip()
                    if act=="keep": action[cands[i]]=("keep", cands[i])
                    elif act=="category": action[cands[i]]=("category", lab or cands[i])
                    else: action[cands[i]]=("drop", None)
        print("  THREE-WAY RELABEL:")
        working=[]
        for w in cands:
            act,lab=action.get(w, ("keep", w))
            if act=="drop": print(f"     {w:18s} DROP"); continue
            if act=="category": print(f"     {w:18s} CATEGORY -> {lab}"); working.append((w,lab))
            else: print(f"     {w:18s} keep"); working.append((w,w))
        print()

        # --- author writes around the label-to-use ---
        summaries={}
        for w,lab in working:
            ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary that MUST meaningfully "
                f"incorporate the concept of '{lab}'. Work it in naturally; stay consistent with the "
                f"story; do not invent specific facts.")
            s1,e=author(ap); calls+=1
            if s1 and len(s1.strip())>20: summaries[w]=(lab, s1.strip())

        # --- fabrication gate ---
        clean=[]
        for w,(lab,s1) in summaries.items():
            fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\nDoes this summary assert any SPECIFIC FACT "
                f"the source contradicts or can't support? Interpretation/context are FINE — only flag "
                f"INVENTED specifics. Answer one word: CLEAN or FABRICATED.")
            ft,e=judge(fp); calls+=1
            if "clean" in (ft or "").lower(): clean.append(w)
        fab=[w for w in summaries if w not in clean]
        if fab: print(f"  FABRICATED (excluded): {[(w,summaries[w][0]) for w in fab]}")

        # --- comparative ranking ---
        if len(clean)>=2:
            labels=[summaries[w][0] for w in clean]
            listing2="\n".join(f"  {i+1}. [{summaries[w][0]}] {summaries[w][1]}" for i,w in enumerate(clean))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {base}\n\nRank the TOP 3 candidate summaries that "
                f"add the most SPECIFIC, NON-OBVIOUS explanatory dimension — a new consequence, actor, or "
                f"mechanism a reader wouldn't already assume. Penalize ones that restate the obvious OR are "
                f"too generic to be informative.\n\n{listing2}\n\nAnswer EXACTLY: TOP3: concept1, concept2, concept3")
            rt,e=judge(rp); calls+=1
            top3=parse_top3(rt, labels)
            print(f"  JUDGE RAW: {(rt or '').strip()[:90]}")
            print(f"  >>> CROWNED: {top3}")
            demoted=[summaries[w][0] for w in clean if summaries[w][0].lower() not in [t.lower() for t in top3]]
            print(f"      demoted: {demoted}")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: (1) HRC -> a category (senior Dem/opposition figure), NOT dropped?")
    print("  (2) pompeo -> chief diplomat? (3) ronaldo/zlatan/borussia -> DROP (not flattened)?")
    print("  (4) durables (civilian casualties, arms embargo) + live actors (hezbollah) KEPT?")
    print("  (5) crowns clean and non-generic across all 5?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
