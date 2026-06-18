#!/usr/bin/env python3
"""
rewire_collider.py — does injecting an OMITTED concept reorganize the model's
explanation MORE than injecting a RANDOM word? (The AGI-primitive test.)

ChatGPT's reframe: the real object isn't summary-quality, it's COUNTERFACTUAL
RECEPTIVITY — if you hand the model a concept it neglected, can it REORGANIZE its
explanation around it? Gemini proposed measuring "rewire" as claim-graph eigenvector-
centrality shift. RECON FINDING: claim_extractor returns a flat LIST of claims, NOT a
graph — there are no edges. So we measure rewire HONESTLY from claim-lists (no invented
graph): how much the claim-SET restructured + whether the load-bearing (most-central)
claim was displaced.

THE TEST (with the controls that are the whole point):
  For each story, baseline summary S0 -> extract claims C0. Then inject each of:
    REAL     — a genuinely omitted void concept            (expect: high rewire IF primitive real)
    RANDOM   — a random vocab word                          (THE SEATBELT: does real beat random?)
    PRESENT  — a concept already in S0                      (expect: LOW rewire — Band 1 floor)
    OFFTOPIC — an orthogonal concept                        (expect: rejection / low — Band 3)
  -> regenerate S1 -> extract claims C1 -> measure rewire(C0,C1).

REWIRE measures (from claim embeddings, no graph fabrication):
  turnover    = fraction of C0 claims with NO near-match in C1 (claims replaced)
  centroid_shift = 1 - cos(centroid(C0), centroid(C1))   (explanation's direction moved)
  center_changed = did the most-central claim change identity? (load-bearing swap)
  acceptance  = did the injected concept actually appear / get used (vs rejected)

VERDICT: if rewire(REAL) > rewire(RANDOM) CONSISTENTLY across stories -> counterfactual
receptivity is real & measurable (the primitive). If REAL ~= RANDOM -> rewire is just
rephrasing-volatility, the primitive is noise (the honest null).

API + GPU (generate) + local LLM (claim extraction). Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=4
GEN_WRITER="ChatGPT"
NEAR=0.80           # claim "survives" if C1 has a claim with cosine >= this
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
ABSENT_WORD={"Erased":-1,"Partial":0,"Preserved":1}
ARCH_ABSENT={"The Still Point":0,"The Unanimous Shield":1,"The Sharp Silence":-1,"The Sealed Vault":-1,
    "The Hollow Headline":-1,"The Named Erasure":-1,"The Cornering":-1,"The Quiet Cull":-1,
    "The Anonymized Drone":-1,"The Naming Battle":-1,"The Split Witness":-1,"The Sealed Chorus":-1}

def absent_axis(seg):
    for b in seg.get("beats",[]):
        if "state_vector" in b.get("phase",""):
            t=b.get("text","")
            if "EigenChing state:" not in t: return None
            head=t.split("EigenChing state:")[1].split(".")[0]; name=head.split(",")[0].strip()
            if name in ARCH_ABSENT: return ARCH_ABSENT[name]
            w=name.split()
            if len(w)>=2 and w[1] in ABSENT_WORD: return ABSENT_WORD[w[1]]
    return None

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    from claim_extractor import extract_claims
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    writer=pa.BIG5_CALLERS[GEN_WRITER]
    EXTRACT_MODEL="qwen2.5:14b"     # fixed local extractor, temp 0, to minimize extractor noise

    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words

    def claims_of(headline, summary):
        try:
            cs=extract_claims(headline, summary, model=EXTRACT_MODEL)
            return [c for c in cs if len(c)>10][:10]
        except Exception as e:
            return []
    def rewire(c0, c1):
        if not c0 or not c1: return None
        v0=E(c0); v1=E(c1)
        # turnover: C0 claims with no near-match in C1
        sim=v0@v1.T
        survived=(sim.max(axis=1)>=NEAR).sum()
        turnover=1.0-survived/len(c0)
        # centroid shift
        cen0=v0.mean(0); cen0/=np.linalg.norm(cen0)+1e-8
        cen1=v1.mean(0); cen1/=np.linalg.norm(cen1)+1e-8
        centroid_shift=1.0-float(cen0@cen1)
        # center-claim identity change: most-central claim of each (closest to its centroid)
        central0=c0[int(np.argmax(v0@cen0))]
        central1=c1[int(np.argmax(v1@cen1))]
        # did the load-bearing claim get replaced? (no near-match of central0 among c1)
        center_changed = float(np.max(E([central0])@v1.T) < NEAR)
        return {"turnover":turnover,"centroid_shift":centroid_shift,
                "center_changed":center_changed,"n0":len(c0),"n1":len(c1)}

    # collect Erased stories
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]
    erased=[]
    for f in sorted(SEGS,reverse=True):
        if len(erased)>=N_STORIES*3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            if absent_axis(seg)!=-1: continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<4: continue
            erased.append((t,list(sums.values())))
        except: continue

    rng=np.random.default_rng(0)
    agg={"REAL":[], "RANDOM":[], "PRESENT":[], "OFFTOPIC":[]}
    acc={"REAL":[], "RANDOM":[], "PRESENT":[], "OFFTOPIC":[]}
    done=0
    OFFTOPIC_POOL=["webcam","recipe","ballet","plankton","skateboard","accordion"]
    for title,sums_list in erased:
        if done>=N_STORIES: break
        base=sums_list[0]
        # baseline claims
        c0=claims_of(title, base)
        if len(c0)<3:
            print(f"skip (few baseline claims): {title[:40]}"); continue
        # pick a REAL omitted void
        cvecs=E(sums_list); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums_list); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        real=None
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
            real=w; break
        if not real: continue
        random_w=words[rng.integers(len(words))]
        # PRESENT: a content word actually in the baseline
        present_words=[w for w in re.findall(r"[a-z][a-z]{4,}", base.lower()) if w not in HARD_DROP]
        present=present_words[len(present_words)//2] if present_words else "policy"
        offtopic=OFFTOPIC_POOL[done % len(OFFTOPIC_POOL)]

        inj={"REAL":real,"RANDOM":random_w,"PRESENT":present,"OFFTOPIC":offtopic}
        print("\n"+"="*70); print(f"STORY: {title[:55]}")
        print(f"  baseline claims: {len(c0)} | REAL='{real}' RANDOM='{random_w}' PRESENT='{present}' OFFTOPIC='{offtopic}'")
        for cond,w in inj.items():
            prompt=(f"News story: {title}\n\nYour earlier summary: {base[:300]}\n\n"
                    f"Consider the concept '{w}' in relation to this story. Write one tighter "
                    f"2-3 sentence summary that works it in IF genuinely relevant (skip if not). "
                    f"Stay faithful; invent nothing.")
            s1,_=writer(prompt); s1=(s1 or "").strip()
            used=bool(re.search(r'\b'+re.escape(w.split()[0])+r'\b', s1.lower()))
            c1=claims_of(title, s1)
            r=rewire(c0,c1)
            if r:
                agg[cond].append(r); acc[cond].append(1 if used else 0)
                print(f"  [{cond:8s}] turnover={r['turnover']:.2f} centroid_shift={r['centroid_shift']:.3f} "
                      f"center_changed={int(r['center_changed'])} used={int(used)}")
        done+=1

    print("\n"+"="*70); print("AGGREGATE — mean rewire per injection condition"); print("="*70)
    print(f"{'cond':10s} {'turnover':>9s} {'centroid_shift':>15s} {'center_chg':>11s} {'acceptance':>11s} {'n':>4s}")
    for cond in ["REAL","RANDOM","PRESENT","OFFTOPIC"]:
        rs=agg[cond]
        if not rs: print(f"{cond:10s}  (none)"); continue
        print(f"{cond:10s} {np.mean([r['turnover'] for r in rs]):>9.3f} "
              f"{np.mean([r['centroid_shift'] for r in rs]):>15.3f} "
              f"{np.mean([r['center_changed'] for r in rs]):>11.2f} "
              f"{np.mean(acc[cond]):>11.2f} {len(rs):>4d}")
    print("\nVERDICT:")
    print(" REAL > RANDOM on rewire (consistently) -> counterfactual receptivity is REAL & measurable")
    print(" REAL ~= RANDOM -> rewire is just rephrasing-volatility; the primitive is noise (honest null)")
    print(" PRESENT should be LOW (Band 1 rigid absorb); OFFTOPIC low acceptance (Band 3 reject)")
    print(" The ORDERING matters more than any single number (small-sample claim graphs are jumpy)")

if __name__=="__main__":
    main()
