#!/usr/bin/env python3
"""
test_unlock.py — THE UNLOCK TEST. The braintrust's convergent design.

Architecture (each component does ONLY what it's good at):
  - GEOMETRY as RECALL: donut top-N on re-anchored (0.4 headline / 0.6 centroid)
    blend -> clean candidate net (proven: re-anchor kills webcam/synonym junk).
  - MODELS as JUDGE: for each candidate, score two things on the model's own
    summary-with-concept:
      FAITHFUL (binary): is the concept-incorporated summary faithful to source?
        -> kills Band 3 (webcam crammed in = unfaithful).
      UNLOCK (0-3): does incorporating it add a new (a) CONSEQUENCE, (b) ACTOR,
        (c) CONSTRAINT/MECHANISM vs the base summary -- PERSISTENCE-GUARDED: only
        counts if the new content is about the STORY, survives removing the word.
        -> carves Band 2 (high unlock) from Band 1 (restatement, unlock~0).
  - CROWN: highest Unlock among Faithful = the surfaced void.

Target (ChatGPT's framing): among omitted concepts, which one most changes what
can be faithfully inferred? NOT "most dramatic" (salience trap), NOT "biggest
shift" (novelty trap) -- most inferential unlock while faithful.

temp=0 callers (low variance). Cross-model judging (judge != author). Clean vocab.
bge GPU + API. Stream stopped. Live untouched.
"""
import json, os, sys, glob, shutil, tempfile, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

N_STORIES=4
TOP_N=14          # recall net per story
AUTHORS=["ChatGPT","Claude","Gemini"]   # write summary-with-concept
JUDGE="DeepSeek"   # cross-model judge (not an author) — avoids self-grading
HEAD_W, CENT_W = 0.4, 0.6  # blend anchor

def parse_judgment(txt):
    """Extract FAITHFUL yes/no and the 3 unlock binaries from judge response."""
    t=txt.lower()
    faithful = ("faithful: yes" in t) or ("faithful:yes" in t) or re.search(r'faithful[:\s]+yes',t)
    cons = bool(re.search(r'consequence[:\s]+yes', t))
    actor= bool(re.search(r'actor[:\s]+yes', t))
    constr=bool(re.search(r'constraint[:\s]+yes', t))
    return (bool(faithful), int(cons)+int(actor)+int(constr), (int(cons),int(actor),int(constr)))

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
    authors={m:pa.BIG5_CALLERS[m] for m in AUTHORS if m in pa.BIG5_CALLERS}
    judge=pa.BIG5_CALLERS[JUDGE]
    print(f"authors: {list(authors.keys())} | judge: {JUDGE}\n", flush=True)

    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","ceasefire","summit","iran","ukraine","russia","israel","gaza"]
    stories=[]
    for f in segs:
        if len(stories)>=N_STORIES: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            sums={k:v for k,v in mr.items() if v and len(v)>50}
            if len(sums)<4: continue
            title=a.get("story_title","")
            if sum(c in title.lower() for c in cue)<1: continue
            vecs=E(list(sums.values())); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=blend,
                                  k=TOP_N, outer_threshold=0.55)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            stories.append((title, sums, cands))
        except: pass
    print(f"{len(stories)} stories (re-anchored 0.4/0.6 blend recall)\n", flush=True)

    calls=0
    for title, sums, cands in stories:
        print("="*72); print(f"[{title[:62]}]"); print(f"  candidates ({len(cands)}): {cands}\n", flush=True)
        rows=[]
        # one base summary to compare against (use first author's stored summary)
        for w in cands:
            unlock_scores=[]; faithfuls=[]
            for am, acall in authors.items():
                base=sums.get(am,"")
                if not base or len(base)<30: continue
                # author writes summary considering the concept
                ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. Consider whether "
                    f"'{w}' is relevant; if so work it in naturally, if not ignore it. Stay faithful.")
                s1,e=acall(ap); calls+=1
                if not s1 or len(s1.strip())<20: continue
                s1=s1.strip()
                # judge (cross-model) scores faithfulness + 3 unlock binaries with persistence guard
                jp=(f"SOURCE STORY: {title}\n\nBASE SUMMARY: {base}\n\nNEW SUMMARY: {s1}\n\n"
                    f"The new summary tried to incorporate the concept '{w}'. Answer EXACTLY in this format:\n"
                    f"FAITHFUL: yes/no  (is the NEW SUMMARY faithful to the source story, no invented claims?)\n"
                    f"CONSEQUENCE: yes/no  (does NEW add a real downstream consequence about the STORY not in BASE? "
                    f"only yes if it would still make sense with the word '{w}' removed)\n"
                    f"ACTOR: yes/no  (does NEW add a relevant actor/stakeholder about the STORY not in BASE?)\n"
                    f"CONSTRAINT: yes/no  (does NEW add a real constraint/mechanism about the STORY not in BASE?)")
                jt,je=judge(jp); calls+=1
                if not jt: continue
                faith,unlock,_=parse_judgment(jt)
                faithfuls.append(faith); unlock_scores.append(unlock)
            if unlock_scores:
                faith_rate=np.mean(faithfuls); mean_unlock=np.mean(unlock_scores)
                rows.append((w, faith_rate, mean_unlock))
                print(f"   {w:22s} faithful={faith_rate:.2f}  unlock={mean_unlock:.2f}")
        # crown: highest unlock among mostly-faithful
        faithful_rows=[r for r in rows if r[1]>=0.5]
        if faithful_rows:
            crowned=max(faithful_rows, key=lambda r:r[2])
            print(f"\n  >>> CROWNED VOID: '{crowned[0]}' (unlock={crowned[2]:.2f}, faithful={crowned[1]:.2f})")
            # also show what got rejected as unfaithful (Band 3)
            unfaith=[r[0] for r in rows if r[1]<0.5]
            if unfaith: print(f"      rejected as unfaithful (Band 3): {unfaith}")
            # band-1 (faithful, low unlock)
            band1=[r[0] for r in faithful_rows if r[2]<0.5]
            if band1: print(f"      faithful but low-unlock (Band 1 restatement): {band1}")
        print(flush=True)
    print(f"\ntotal API calls: {calls}")
    print("\nEYEBALL: are the CROWNED voids consistently the genuinely-illuminating")
    print("concepts (the ones that most expand faithful inference)? And do Band 1")
    print("(restatement) and Band 3 (unfaithful) separate from them cleanly?")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
