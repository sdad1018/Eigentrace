#!/usr/bin/env python3
"""
eyeball_anchor.py — NO API. Tests whether re-anchoring the donut's outer ring
fixes the 'Live Updates -> webcam' pollution.

HYPOTHESIS (from last eyeball): the garbage on format-y-headline stories comes
from anchoring the outer ring on the polluted HEADLINE ('Live Updates' embeds
near streaming vocab). The models already stripped 'Live Updates' from their
summaries. So anchoring the outer ring on the SUMMARY CONSENSUS (or a blend)
should collapse the streaming junk and surface real concepts.

Tests 3 anchors side-by-side on the same stories:
  1. HEADLINE (current) -> produced webcam/porn/esports
  2. CENTROID-as-anchor -> pass centroid as the headline_vec param (so outer ring
     uses consensus topic; inner hole still uses centroid). NOTE: outer & inner
     both centroid-based shrinks the donut, so we widen outer_threshold to compensate.
  3. BLEND (0.5 headline + 0.5 centroid, renormalized) -> dilute format-noise,
     keep real headline topic signal.

Look at the POISONED stories (Live Updates, Summit): does centroid/blend kill
the streaming junk? Clean vocab, bge embeddings only, stream can stay up.
"""
import json, os, sys, glob, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

B3={"esports","content","videotape","webcam","porn","vids","footage","livestream",
    "subscription","wifi","feed","feeds","multiplayer","vid","video","videos","vod",
    "rewatch","replay","replays","lobbies","warcraft","stream","tmz","podcasts"}
def is_b3(w): return w.lower() in B3

def main():
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp,"global_vocab.pt"))
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    cue=["war","strike","nuclear","ceasefire","summit","live updates","iran","ukraine"]
    # bias toward INCLUDING the poisoned format-y headlines
    stories=[]
    for f in segs:
        if len(stories)>=4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([t for t in mr.values() if t and len(t)>50])<4: continue
            title=a.get("story_title","")
            if not any(c in title.lower() for c in cue): continue
            vecs=E([t for t in mr.values() if t]); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([title])[0]
            stories.append((title, centroid, vecs, hv))
        except: pass

    def donut(centroid, vecs, anchor_vec, outer_thresh):
        res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=anchor_vec,
                              k=30, outer_threshold=outer_thresh)
        return [w for w,_ in (res[0] if isinstance(res,tuple) else res)]

    for title, centroid, vecs, hv in stories:
        print("="*72); print(f"[{title[:64]}]\n")
        # anchor 1: headline (current)
        a_head = donut(centroid, vecs, hv, 0.52)
        # anchor 2: centroid-as-outer-anchor (widen outer since outer~inner now)
        a_cent = donut(centroid, vecs, centroid, 0.62)
        # anchor 3: blend
        blend = 0.5*hv + 0.5*centroid; blend/=np.linalg.norm(blend)+1e-8
        a_blend = donut(centroid, vecs, blend, 0.55)

        def fmt(words): 
            return ", ".join((f"**{w}**" if is_b3(w) else w) for w in words[:18])
        def b3count(words): return sum(is_b3(w) for w in words)

        print(f"  1. HEADLINE anchor  (B3 junk: {b3count(a_head)}):\n     {fmt(a_head)}")
        print(f"\n  2. CENTROID anchor  (B3 junk: {b3count(a_cent)}):\n     {fmt(a_cent)}")
        print(f"\n  3. BLEND anchor     (B3 junk: {b3count(a_blend)}):\n     {fmt(a_blend)}")
        print()

    print("="*72)
    print("EYEBALL: on the POISONED stories (Live Updates / Summit):")
    print("  - does CENTROID or BLEND kill the **streaming junk** that HEADLINE surfaced?")
    print("  - and do they surface REAL concepts (diplomacy, escalation, deal) instead?")
    print("  - if centroid/blend cleans them AND keeps good words on clean stories ->")
    print("    re-anchor the donut, then build Unlock test on clean recall everywhere.")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
