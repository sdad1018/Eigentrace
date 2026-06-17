#!/usr/bin/env python3
"""
eyeball_top50.py — NO API, NO crowning. Just pull the donut's TOP-50 candidates
(not top-8) on a few charged stories so we can EYEBALL whether the good Band-2
words (deterrence, legitimacy, refugee flows, reconstruction, foreign interference)
are actually IN the wider net.

This validates the load-bearing assumption of the Unlock architecture:
"geometry as RECALL" — geometry can't RANK well (proven, 9 nulls), but can it at
least RECALL the good words somewhere in top-50, so the models can then crown them?

If top-50 CONTAINS good Band-2 candidates the top-8 missed -> geometry-as-recall
works, build the Unlock test. If top-50 is just MORE noise with no good words
present at all -> geometry can't even recall, need models-propose instead.

Clean vocab, bge GPU (embeddings only, no model calls), stream can stay up.
"""
import json, os, sys, glob, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# rough band tags for eyeballing (illustrative, not a gate)
BAND2_HINTS={"deterrence","legitimacy","reconstruction","refugee","refugees","displacement",
    "foreign interference","regime change","proxy war","sanctions","annexation","insurgency",
    "occupation","sovereignty","proliferation","escalation","blockade","ceasefire","diplomacy",
    "negotiation","embargo","arms race","nuclear","autonomy","secession","partition","famine",
    "reparations","genocide","ethnic","sectarian","insurrection","coup","mobilization",
    "conscription","austerity","inflation","infrastructure","desalination","reconstruction"}
BAND1_HINTS={"war","wars","wartime","combat","airstrike","missiles","soldiers","military",
    "fighting","battle","conflict","hostilities","troops","casualties","death toll"}
BAND3_HINTS={"webcam","porn","vids","footage","livestream","subscription","wifi","esports",
    "content","stream","videotape","multiplayer","pewdiepie","wrestlemania","chat","feed"}

def tag(w):
    wl=w.lower()
    if any(h in wl or wl in h for h in BAND3_HINTS): return "B3"
    if wl in BAND1_HINTS: return "B1"
    if any(h==wl or h in wl for h in BAND2_HINTS): return "B2"
    return "  "

def main():
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    print("clean vocab loaded\n", flush=True)

    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","missile","ceasefire","invasion","escalat","sanctions","troops"]
    stories=[]
    for f in segs:
        if len(stories)>=4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([t for t in mr.values() if t and len(t)>50])<4: continue
            title=a.get("story_title","")
            if sum(c in title.lower() for c in cue)<1: continue
            vecs=E([t for t in mr.values() if t]); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            stories.append((title, centroid, vecs, hv))
        except: pass

    for title, centroid, vecs, hv in stories:
        print("="*72)
        print(f"[{title[:64]}]")
        # top-8 (current) vs top-50 (proposed recall net)
        res8=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=8)
        c8=[w for w,_ in (res8[0] if isinstance(res8,tuple) else res8)]
        res50=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=50)
        c50=[w for w,_ in (res50[0] if isinstance(res50,tuple) else res50)]
        print(f"\n  TOP-8 (current): {c8}")
        # tag the top-50 so we can see band structure + whether good words appear deeper
        print(f"\n  TOP-50 (recall net) — tagged [B1=restate B2=productive B3=derail]:")
        for i in range(0, len(c50), 5):
            row=c50[i:i+5]
            print("    " + "  ".join(f"{tag(w)}:{w}" for w in row))
        # count bands in top-50, and whether B2 words appear PAST rank 8
        b2_all=[w for w in c50 if tag(w)=="B2"]
        b2_deep=[w for w in c50[8:] if tag(w)=="B2"]
        b3_all=[w for w in c50 if tag(w)=="B3"]
        print(f"\n  Band-2 candidates in top-50: {len(b2_all)}  ({b2_all})")
        print(f"  Band-2 that appear ONLY past rank 8 (top-8 missed them): {b2_deep}")
        print(f"  Band-3 noise in top-50: {len(b3_all)}  ({b3_all[:10]})")
        print()

    print("="*72)
    print("EYEBALL: ")
    print("  1. Does TOP-50 CONTAIN good Band-2 words the TOP-8 missed? (b2_deep非empty)")
    print("     -> if yes: geometry-as-RECALL works, build Unlock test on top-50.")
    print("  2. Or is top-50 just more B3/B1 noise with no real B2 present?")
    print("     -> if so: geometry can't recall either, need models-propose.")
    print("  (tags are rough hints — read the actual words, not just the counts.)")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
