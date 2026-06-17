#!/usr/bin/env python3
"""
test_unlock_v5.py — Unlock pipeline + CATEGORY-RELABEL step.

THE STALENESS PROBLEM (user-diagnosed, on-air): bge surfaces geometrically-good
but temporally-dead named entities (isil, pompeo, tpp). bge's weights are frozen;
the judge model's almanac is ALSO frozen (thinks it's ~2023, Biden admin), so a
"is this current?" gate is broken at the root — can't ask a stopped clock what
time it is. And hand-swapping bge vectors (isil->'sunni militants') is editorial
+ a manual treadmill that breaks the instrument's zero-editorial claim.

THE FIX (user's idea, placed correctly): don't swap in bge. The geometry surfaces
the HOLE with whatever stale label it has. Then the MODEL, at judgment time, RIPS
THE CATEGORY from the surfaced actor (pompeo -> "a national chief diplomat";
isil -> "a transnational Sunni jihadist organization") and SEPARATELY decides
whether any CURRENT instance of that category fits the story. The actor that
surfaced is just bge's frozen handle on a category; the category is what matters.
Auto-updates with model checkpoints, no hand table, model uses its own knowledge.

CRITICAL INSTRUCTION TO MODEL: rip the CATEGORY, not the actor. The actor may or
may not still be relevant — that's a separate question from what category it marks.

Residual known limit: model almanac is itself stale, so "current instance" may be
model-current not 2026-current. Still strictly better than raw stale label or a
frozen hand-table, and improves with model updates.

Pipeline: clean recall -> fabrication gate -> CATEGORY RELABEL -> comparative
unlock ranking -> crown. Re-anchored 0.3/0.7. temp=0. bge+API. Stream stopped.
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
                out.append(h[0] if h else (x if len(x)<40 else None))
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
    print(f"author: {AUTHOR} | judge: {JUDGE} | anchor: {HEAD_W}h/{CENT_W}c | + category-relabel\n", flush=True)

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

        # --- CATEGORY RELABEL: rip the category from each surfaced term ---
        # one batched call: for each surfaced word, give (category, current_instance_or_KEEP_or_DEAD)
        listing="\n".join(f"  {i+1}. {w}" for i,w in enumerate(cands))
        cp=(f"Story: {title}\n\nThese terms surfaced from a FROZEN embedding space as concepts "
            f"latent to this story. Some are durable concepts (e.g. 'civilian casualties') and some "
            f"are NAMED ACTORS that may be temporally stale (e.g. a former official, a degraded org).\n\n"
            f"For EACH term, do this: RIP THE CATEGORY it represents, NOT the specific actor. The "
            f"specific actor may or may not still be relevant — that is a SEPARATE question from what "
            f"category it marks. Then give the best label to USE:\n"
            f"  - If it's already a durable concept or a still-relevant actor: output it unchanged.\n"
            f"  - If it's a stale named actor: output the CATEGORY or a current instance of that "
            f"category that fits the story (e.g. 'pompeo' -> 'the US chief diplomat'; 'isil' -> "
            f"'a transnational Sunni jihadist faction'). Do NOT just keep the stale name.\n"
            f"  - If it marks a category with NO live relevance to this story at all: output DEAD.\n\n"
            f"{listing}\n\n"
            f"Answer one per line, EXACTLY: N. <label to use>   (or  N. DEAD)")
        ct,e=judge(cp); calls+=1
        relabel={}
        for line in (ct or "").splitlines():
            m=re.match(r'\s*(\d+)\.\s*(.+)', line)
            if m:
                i=int(m.group(1))-1
                if 0<=i<len(cands): relabel[cands[i]]=m.group(2).strip()
        # build working candidate list: relabeled, drop DEAD
        working=[]   # (orig, label_to_use)
        for w in cands:
            lab=relabel.get(w, w)
            if lab.upper().strip()=="DEAD": continue
            working.append((w, lab))
        print(f"  CATEGORY RELABEL:")
        for w,lab in [(w,relabel.get(w,w)) for w in cands]:
            tag = "DEAD (dropped)" if lab.upper().strip()=="DEAD" else (f"-> {lab}" if lab.lower()!=w.lower() else "(kept)")
            print(f"     {w:18s} {tag}")
        print()

        # --- author writes summary using the LABEL TO USE ---
        summaries={}  # key = orig word, summary built around the relabeled concept
        for w,lab in working:
            ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary that MUST meaningfully "
                f"incorporate the concept of '{lab}'. Work it in naturally; stay consistent with the "
                f"story; do not invent specific facts.")
            s1,e=author(ap); calls+=1
            if s1 and len(s1.strip())>20: summaries[w]=(lab, s1.strip())

        # --- fabrication gate ---
        clean=[]
        for w,(lab,s1) in summaries.items():
            fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\nDoes this summary assert any SPECIFIC "
                f"FACT the source contradicts or can't support? Interpretation/context are FINE — only "
                f"flag INVENTED specifics. Answer one word: CLEAN or FABRICATED.")
            ft,e=judge(fp); calls+=1
            if "clean" in (ft or "").lower(): clean.append(w)
        fab=[w for w in summaries if w not in clean]
        if fab: print(f"  FABRICATED (excluded): {[(w,summaries[w][0]) for w in fab]}")

        # --- comparative ranking (over relabeled concepts) ---
        if len(clean)>=2:
            labels=[summaries[w][0] for w in clean]
            listing2="\n".join(f"  {i+1}. [{summaries[w][0]}] {summaries[w][1]}" for i,w in enumerate(clean))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {base}\n\nRank the TOP 3 candidate summaries that "
                f"add the most SPECIFIC, NON-OBVIOUS explanatory dimension — a new consequence, actor, or "
                f"mechanism a reader wouldn't already assume. Penalize ones that restate the obvious.\n\n"
                f"{listing2}\n\nAnswer EXACTLY: TOP3: concept1, concept2, concept3")
            rt,e=judge(rp); calls+=1
            top3=parse_top3(rt, labels)
            print(f"  JUDGE RAW: {(rt or '').strip()[:90]}")
            print(f"  >>> CROWNED: {top3}")
            demoted=[summaries[w][0] for w in clean if summaries[w][0].lower() not in [t.lower() for t in top3]]
            print(f"      demoted: {demoted}")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: did relabel rip CATEGORIES from stale actors (pompeo->chief diplomat,")
    print("isil->sunni jihadist faction) while keeping durable concepts (civilian casualties,")
    print("arms embargo) and live actors (hezbollah) UNCHANGED? Any over-DEAD-ing of good ones?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
