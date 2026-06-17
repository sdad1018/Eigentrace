#!/usr/bin/env python3
"""
test_suppression_vector.py — Gemini's 8th method (ΔS), fair test on RICH-source
stories only. THE final geometric shot.

ΔS = Embed(Source) - Embed(Summary). A DIRECTION (not radius) pointing from the
sanitized consensus toward what the source contained but the summary dropped.
Project donut candidates onto ΔS: meaningful suppressed concepts should align
(high projection), pop-noise should be orthogonal (~0, source wasn't about it).

PREMISE REQUIREMENT: source must be RICHER than summary (else ΔS points wrong way).
Recon showed source_body median=267 chars (headline+lead) — too thin for most.
So we ONLY test stories with source_body >= 800 chars (real article text), and
report source/summary length ratio per story so we see if ΔS has a valid direction.

PRE-COMMITTED BAR (eyes open: even success here = proof-of-concept, NOT deployable,
since rich source exists for only ~15% of stories):
  1. pop-noise (webcam/porn) projects ~0 or negative on ΔS
  2. meaningful (foreign interference/wwiii/warheads) projects HIGH
  3. HARD: meaningful projects HIGHER than in-source restatement/detail
     (Tehran/death toll/airstrike — also in source but not "consequences")

bge GPU, stream stopped, clean vocab, live untouched.
"""
import json, os, sys, glob, shutil, tempfile
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

SIGNAL={"drone strike","arms race","arms deal","arms embargo","information warfare",
        "warheads","foreign interference","nuclear war","escalation","proxy war",
        "regime change","atrocities","annexation","blockade","genocidal"}
RESTATE={"tehran","death toll","airstrike","air strike","casualties","beirut",
         "soldiers","combat","war","wars","wartime","hostilities","ceasefire"}
NOISE={"webcam","porn","vids","pewdiepie","wrestlemania","livestream","subscription",
       "dvr","wifi","footage","feed","chat","multiplayer","horny","videotape","rewatch"}

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

    # only RICH-source stories (>=800 chars)
    segs=sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    rich=[]
    for f in segs:
        if len(rich)>=12: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{}); sums=[t for t in mr.values() if t and len(t)>50]
            sb=a.get("source_body","") or ""
            if len(sums)>=4 and len(sb)>=800:
                rich.append((a.get("story_title","")[:50], sb, sums))
        except: pass
    print(f"found {len(rich)} RICH-source stories (>=800 char source_body)\n", flush=True)
    if not rich:
        print("no rich-source stories — ΔS cannot be tested fairly"); return

    sig_proj_all=[]; noise_proj_all=[]; restate_proj_all=[]
    print("="*70)
    for title, sb, sums in rich:
        sum_text=" ".join(sums)
        src_v=E([sb])[0]; sum_v=E([sum_text])[0]
        ratio=len(sb)/max(1,len(sum_text))
        # ΔS = source - summary, normalized
        dS=src_v - sum_v; dSn=np.linalg.norm(dS)
        dS=dS/(dSn+1e-8)
        # donut candidates
        vecs=E(sums); centroid=vecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]
        try:
            res=vt.in_domain_void(centroid=centroid, response_vecs=vecs, headline_vec=hv, k=15)
            cands=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
        except Exception as e:
            print(f"[{title}] ERR {e}"); continue
        if not cands: continue
        cv=E(cands)
        proj=cv @ dS   # projection of each candidate onto suppression vector
        ranked=sorted(zip(cands,proj), key=lambda x:-x[1])

        # bucket projections by label
        for w,p in zip(cands,proj):
            wl=w.lower()
            if wl in SIGNAL: sig_proj_all.append(p)
            elif wl in NOISE: noise_proj_all.append(p)
            elif wl in RESTATE: restate_proj_all.append(p)

        print(f"\n[{title}]  src/sum len ratio={ratio:.2f}  ||ΔS||={dSn:.3f}")
        print(f"  HIGHEST ΔS-projection (should be suppressed consequences): {[f'{w}:{p:.2f}' for w,p in ranked[:6]]}")
        print(f"  LOWEST  ΔS-projection (should be off-source noise):        {[f'{w}:{p:.2f}' for w,p in ranked[-5:]]}")

    print("\n"+"="*70)
    print("VERDICT — projections onto ΔS by label (across rich-source stories):")
    def stat(name,arr):
        if arr: print(f"  {name:12s}: n={len(arr)} mean_proj={np.mean(arr):+.3f} (want: SIGNAL high, NOISE ~0/neg, RESTATE between)")
        else: print(f"  {name:12s}: no labeled candidates appeared")
    stat("SIGNAL", sig_proj_all)
    stat("RESTATE", restate_proj_all)
    stat("NOISE", noise_proj_all)
    print()
    if sig_proj_all and noise_proj_all:
        c1 = np.mean(noise_proj_all) < np.mean(sig_proj_all) - 0.03
        print(f"  COND 1 (noise < signal): {'PASS' if c1 else 'FAIL'} "
              f"(noise {np.mean(noise_proj_all):+.3f} vs signal {np.mean(sig_proj_all):+.3f})")
    if sig_proj_all and restate_proj_all:
        c3 = np.mean(sig_proj_all) > np.mean(restate_proj_all) + 0.03
        print(f"  COND 3 (signal > restatement, THE HARD ONE): {'PASS' if c3 else 'FAIL'} "
              f"(signal {np.mean(sig_proj_all):+.3f} vs restate {np.mean(restate_proj_all):+.3f})")
        print("  -> COND 3 PASS = ΔS truly separates meaning from mere dropped-detail = real.")
        print("  -> COND 3 FAIL = ΔS kills pop-noise but not restatement = partial tool only.")
    print("\n  (Reminder: even full PASS here = proof-of-concept on rich-source subset,")
    print("   NOT a deployable atlas engine — only ~15% of stories have rich source.)")
    shutil.rmtree(tmp, ignore_errors=True)

if __name__=="__main__":
    main()
