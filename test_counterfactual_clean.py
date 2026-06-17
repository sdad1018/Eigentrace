#!/usr/bin/env python3
"""
test_counterfactual_clean.py — ChatGPT's intervention test, CORRECTED.

The smoke test had a methodology bug: I INJECTED 'airstrike'/'nuclear holocaust'/
'webcam' into every story including a sports story. The donut would NEVER surface
'airstrike' for a dressing-room-visit story — so the 'jarring violent word in soft
story' confound was MY artifact, not a real failure mode. In production the donut
self-restricts to the topic neighborhood.

CORRECTED TEST: NO forced candidates. Use ONLY the donut's real output. Charged
stories only (rich neighborhood). Label the NATURALLY-surfaced words post-hoc.
Question: among words the donut ACTUALLY surfaces for a charged story, does
insertion-impact rank meaningful-escalation above restatement above any noise?
That's the only discrimination production ever needs.

Impact(w) = mean over models of cosine-distance(base_summary, summary_with_w).

~5 charged stories x ~8 real candidates x 3 models. Loads .env. bge+API. Stream stopped.
"""
import json, os, sys, glob
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

N_STORIES=5
K_CANDIDATES=8
MODELS_TO_USE=["ChatGPT","Claude","Gemini"]   # 3 models to average out generation variance

# post-hoc labels (applied to whatever the donut surfaces, NOT injected)
SIGNAL={"nuclear war","nuclear holocaust","arms race","escalation","proxy war","world war",
        "foreign interference","regime change","warheads","genocidal","annexation","arms embargo",
        "arms deal","information warfare","occupation","insurgency","atrocities","deterrence",
        "trade war","sanctions","coup attempt","assassination","ultimatum","mutiny"}
RESTATE={"airstrike","air strike","missiles","combat","war","wars","wartime","casualties",
         "death toll","soldiers","tehran","ceasefire","truce","fighting","battle","conflict",
         "hostilities","drone strike","drones","military"}
NOISE={"webcam","porn","livestream","subscription","footage","feed","chat","wifi","vids",
       "multiplayer","pewdiepie","wrestlemania","dvr","rewatch","watcher","stream"}

def label(w):
    wl=w.lower()
    if wl in SIGNAL: return "SIGNAL"
    if wl in RESTATE: return "RESTATE"
    if wl in NOISE: return "NOISE"
    return "other"

def main():
    import proxy_auditor as pa
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    import shutil, tempfile
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    callers={m:pa.BIG5_CALLERS[m] for m in MODELS_TO_USE if m in pa.BIG5_CALLERS}
    print(f"models: {list(callers.keys())}\n", flush=True)

    # charged stories only — rich neighborhood
    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","missile","invasion","ceasefire","attack","troops","escalat","military"]
    stories=[]
    for f in segs:
        if len(stories)>=N_STORIES: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([t for t in mr.values() if t and len(t)>50])<4: continue
            title=a.get("story_title","")
            # require genuinely charged (2+ cue words or clear conflict)
            if sum(c in title.lower() for c in cue) < 1: continue
            vecs=E([t for t in mr.values() if t]); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=K_CANDIDATES)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            if cands: stories.append((title, mr, cands))
        except: pass
    print(f"{len(stories)} charged stories with REAL donut candidates (no injection)\n", flush=True)

    call_count=0; all_results=[]
    for title, mr, cands in stories:
        print(f"\n{'='*70}\n[{title[:60]}]")
        print(f"  REAL donut candidates: {cands}")
        labs={w:label(w) for w in cands}
        print(f"  labels: {[(w,labs[w]) for w in cands]}", flush=True)
        for w in cands:
            shifts=[]
            for m,caller in callers.items():
                base_sum=mr.get(m,"")
                if not base_sum or len(base_sum)<30: continue
                prompt=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. "
                        f"Consider whether the concept '{w}' is relevant; if so work it in "
                        f"naturally; if not, ignore it. Stay faithful to the story.")
                try:
                    txt,err=caller(prompt); call_count+=1
                    if not txt or len(txt.strip())<20: continue
                    bv=E([base_sum])[0]; av=E([txt.strip()])[0]
                    shifts.append(1.0-float(bv@av))
                except Exception as e:
                    pass
            if shifts:
                imp=float(np.mean(shifts)); lab=labs[w]
                all_results.append((title[:25],w,lab,imp))
                print(f"   [{lab:7s}] {w:22s} impact={imp:.4f}")
    print(f"\n  total API calls: {call_count}")

    print("\n"+"="*70)
    print("IMPACT BY LABEL — among REAL donut candidates on charged stories:")
    for lab in ["SIGNAL","RESTATE","NOISE","other"]:
        v=[imp for _,_,l,imp in all_results if l==lab]
        if v: print(f"  {lab:8s}: n={len(v)} mean={np.mean(v):.4f} median={np.median(v):.4f} range[{min(v):.4f},{max(v):.4f}]")
    sig=[imp for _,_,l,imp in all_results if l=="SIGNAL"]
    res=[imp for _,_,l,imp in all_results if l=="RESTATE"]
    noi=[imp for _,_,l,imp in all_results if l=="NOISE"]
    print()
    if sig and res:
        print(f"  SIGNAL vs RESTATE (THE KEY ONE): {np.mean(sig):.4f} vs {np.mean(res):.4f}  "
              f"{'<<< SEPARATES' if np.mean(sig)>np.mean(res)*1.1 else 'NO clean separation'}")
    if sig and noi:
        print(f"  SIGNAL vs NOISE:                 {np.mean(sig):.4f} vs {np.mean(noi):.4f}  "
              f"{'<<< SEPARATES' if np.mean(sig)>np.mean(noi)*1.1 else 'NO clean separation'}")
    # per-story: does the highest-impact word look meaningful?
    print("\n  PER-STORY highest-impact candidate (would be the 'crowned' void):")
    bystory={}
    for st,w,l,imp in all_results: bystory.setdefault(st,[]).append((imp,w,l))
    for st,items in bystory.items():
        items.sort(reverse=True)
        top=items[0]
        print(f"    [{st}] crowned: '{top[1]}' ({top[2]}, impact={top[0]:.4f})")
    print("\n  -> if crowned words are consistently MEANINGFUL (not restatement/noise),")
    print("     impact-scoring is the crowning function. if crowned words are restatement,")
    print("     it's measuring novelty-against-summary, not meaning. Models-in-loop (SummaryPlus) stands.")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
