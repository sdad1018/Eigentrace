#!/usr/bin/env python3
"""
test_counterfactual_impact.py — ChatGPT's intervention test (the 9th, genuinely
different mechanism). NOT geometry: measures whether INSERTING a candidate concept
changes how the models interpret the story.

THESIS: a meaningful void is one whose insertion causes REINTERPRETATION.
  webcam -> models' summary barely changes (irrelevant)
  airstrike -> barely changes (already implied = restatement)
  nuclear holocaust -> large shift (meaningful unspoken consequence)

Impact(w) = embedding distance between model's BASE summary and its
            (headline + consider:w) summary, averaged across models.

STAGED FOR COST: starts as a ~24-call SMOKE TEST (2 stories x ~6 candidates x
2 models, augmented-only since base summaries are stored). Only worth scaling
if smoke test shows separation. This is the FIRST test that costs API quota.

Success criterion (ChatGPT's): does Impact rank meaningful > restatement > noise,
and does it beat just using Summary-Plus acceptance?

Loads .env for API keys. bge GPU + API calls. Stream stopped.
"""
import json, os, sys, glob
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# SMOKE TEST scale — bump these only if separation shows
N_STORIES = 2
N_CANDIDATES = 6
MODELS_TO_USE = ["ChatGPT", "Claude"]   # 2 models for smoke; add Gemini/DeepSeek/Grok to scale

# labels for checking separation
SIGNAL={"nuclear war","nuclear holocaust","arms race","escalation","proxy war","world war",
        "foreign interference","regime change","warheads","genocidal","annexation","arms embargo"}
RESTATE={"airstrike","air strike","missiles","combat","war","casualties","death toll","soldiers","tehran"}
NOISE={"webcam","porn","livestream","subscription","footage","feed","chat","wifi","vids","multiplayer"}

def label(w):
    wl=w.lower()
    if wl in SIGNAL: return "SIGNAL"
    if wl in RESTATE: return "RESTATE"
    if wl in NOISE: return "NOISE"
    return "?"

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
    print(f"using models: {list(callers.keys())}\n", flush=True)

    # pick charged stories with stored base summaries
    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","iran","strike","nuclear","ukraine","russia","israel","gaza"]
    stories=[]
    for f in segs:
        if len(stories)>=N_STORIES: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([t for t in mr.values() if t and len(t)>50])<4: continue
            title=a.get("story_title","")
            if not any(c in title.lower() for c in cue): continue
            vecs=E([t for t in mr.values() if t]); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=N_CANDIDATES)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            # inject known signal/noise/restate words to ensure labeled coverage for the test
            forced=["nuclear holocaust","airstrike","webcam"]  # one of each class
            cands=list(dict.fromkeys(cands[:N_CANDIDATES-3]+forced))
            stories.append((title, mr, cands))
        except: pass
    print(f"{len(stories)} stories\n", flush=True)

    call_count=0
    all_results=[]  # (story, word, label, impact)
    for title, mr, cands in stories:
        print(f"\n{'='*70}\n[{title[:60]}]\n  candidates: {cands}", flush=True)
        for w in cands:
            shifts=[]
            for m, caller in callers.items():
                base_sum = mr.get(m,"")
                if not base_sum or len(base_sum)<30: continue
                prompt=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. "
                        f"Consider whether the concept '{w}' is relevant; if so, work it in "
                        f"naturally; if not, ignore it. Stay faithful to the story.")
                try:
                    txt,err=caller(prompt); call_count+=1
                    if not txt or len(txt.strip())<20: continue
                    bv=E([base_sum])[0]; av=E([txt.strip()])[0]
                    shift=1.0-float(bv@av)   # cosine distance base->augmented
                    shifts.append(shift)
                except Exception as e:
                    print(f"     {m} ERR {e}")
            if shifts:
                imp=float(np.mean(shifts))
                lab=label(w)
                all_results.append((title[:30], w, lab, imp))
                print(f"   [{lab:7s}] {w:22s} impact={imp:.4f} (n_models={len(shifts)})")
    print(f"\n  total API calls: {call_count}")

    # ---- separation check ----
    print("\n"+"="*70)
    print("IMPACT BY LABEL (does insertion-impact separate the classes?):")
    for lab in ["SIGNAL","RESTATE","NOISE"]:
        v=[imp for _,_,l,imp in all_results if l==lab]
        if v: print(f"  {lab:8s}: n={len(v)} mean_impact={np.mean(v):.4f} range[{min(v):.4f},{max(v):.4f}]")
        else: print(f"  {lab:8s}: none")
    sig=[imp for _,_,l,imp in all_results if l=="SIGNAL"]
    noi=[imp for _,_,l,imp in all_results if l=="NOISE"]
    res=[imp for _,_,l,imp in all_results if l=="RESTATE"]
    print()
    if sig and noi:
        print(f"  SIGNAL vs NOISE:      {np.mean(sig):.4f} vs {np.mean(noi):.4f}  "
              f"{'<<< SEPARATES (signal>noise)' if np.mean(sig)>np.mean(noi)*1.15 else 'no clear separation'}")
    if sig and res:
        print(f"  SIGNAL vs RESTATE:    {np.mean(sig):.4f} vs {np.mean(res):.4f}  "
              f"{'<<< SEPARATES (signal>restate, THE HARD ONE)' if np.mean(sig)>np.mean(res)*1.15 else 'no clear separation'}")
    print("\n  smoke test. if SIGNAL clearly > RESTATE and NOISE, impact-scoring works")
    print("  -> scale to 5 models + more stories. if muddy, we learned it cheap (~24 calls).")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
