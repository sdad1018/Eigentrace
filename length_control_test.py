#!/usr/bin/env python3
"""
length_control_test.py — the last open thread (all three critics raised it):
does the absent-snap survive LENGTH CONTROL, or is it entangled with summaries growing 138->176 words?

Three independent length controls, two embedding spaces (bge + e5):

  CONTROL 1 — HARD TRUNCATION: cut every summary to the first K words (K=100, below the early-week
              mean so even short summaries aren't padded). Recompute semantic retention trajectory.
              If the snap survives when every summary is the SAME capped length, it's not verbosity.

  CONTROL 2 — FIRST-N-SENTENCES: cut every summary to its first 3 sentences (normalizes structure,
              not just word count). Recompute.

  CONTROL 3 — LENGTH-STRATIFIED: bucket stories by summary length (short/med/long), and within the
              SAME bucket compare early-weeks vs late-weeks retention. If the snap appears WITHIN a
              fixed length band, length cannot be the cause.

Retention = mean over source sentences of max cosine to any (length-capped) summary sentence.
This is length-robust by construction (max-per-source-sentence), but capping removes residual doubt.
"""
import json, glob, os, re, sys
from collections import defaultdict
import numpy as np
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]
CAP_WORDS=100
CAP_SENTS=3
def ts(f):
    m=re.match(r'(\d{8})_(\d{6})', os.path.basename(f)); return m.group(1)+m.group(2) if m else ""
def wk(d):
    from datetime import datetime
    return datetime.strptime(d[:8],"%Y%m%d").strftime("%Y-W%U")
def get_state(seg):
    for b in (seg.get("beats") or []):
        if "state_vector" in b.get("phase",""):
            if "EigenChing state:" in b.get("text",""): return True
    return False
def sent_split(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or "") if len(s.strip())>15]
def cap_words(t,k):
    w=(t or "").split(); return " ".join(w[:k])
def cap_sents(t,k):
    return " ".join(sent_split(t)[:k])

def main():
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception as e:
        print("need sentence-transformers/sklearn:",e); sys.exit(1)
    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"))
    rows=[]
    for f in files:
        if "roundtable" in f: continue
        try: seg=json.load(open(f))
        except: continue
        a=seg.get("attribution") or {}
        t=(a.get("story_title","") or "").lower()
        if not("iran" in t and any(k in t for k in ["talk","peace","deal","truce","negotiat","war","nuclear","enrich","ceasefire"])): continue
        if not get_state(seg): continue
        d=ts(f)
        if not d: continue
        mr=a.get("model_responses",{}) or {}
        summ=[v for v in (mr.get(m,"") for m in ALLMODELS) if v and len(v.split())>=CAP_WORDS//2]
        src=a.get("source_body","") or ""
        if len(summ)<3 or len(src)<200: continue
        rows.append({"w":wk(d),"src":src,"summ":summ})
    rows.sort(key=lambda r:r["w"])
    weeks=sorted(set(r["w"] for r in rows))
    print(f"{len(rows)} Iran stories with summaries >= {CAP_WORDS//2} words, weeks {weeks[0]}..{weeks[-1]}\n")

    for MODEL,is_e5 in [("BAAI/bge-large-en-v1.5",False),("intfloat/e5-large-v2",True)]:
        print("="*86); print(f"EMBEDDING: {MODEL}"); print("="*86)
        enc=SentenceTransformer(MODEL)
        def emb(texts):
            tx=[("query: "+t) for t in texts] if is_e5 else list(texts)
            return enc.encode(tx,normalize_embeddings=True,show_progress_bar=False)
        def retention(src, summaries, capper):
            ss=sent_split(src)[:40]
            if not ss: return None
            capped=[capper(s) for s in summaries]
            allsum=[]
            for c in capped: allsum+=sent_split(c)
            if not allsum: return None
            sim=cosine_similarity(emb(ss),emb(allsum))
            return float(sim.max(axis=1).mean())

        def trajectory(capper,label):
            wkret=defaultdict(list)
            for i,r in enumerate(rows):
                v=retention(r["src"],r["summ"],capper)
                if v is not None: wkret[r["w"]].append(v)
            arr=[np.mean(wkret[w]) if wkret[w] else float('nan') for w in weeks]
            e=np.nanmean(arr[:3]); l=np.nanmean(arr[-3:])
            print(f"\n  [{label}]  early3={e:.3f}  late3={l:.3f}  rise={'YES (+%.3f)'%(l-e) if l>e else 'NO'}")
            print("   " + " ".join(f"{w[-3:]}:{a:.2f}" for w,a in zip(weeks,arr)))
            return e,l,arr

        # uncapped baseline (for reference) + the two caps
        trajectory(lambda t:t, "UNCAPPED baseline")
        trajectory(lambda t:cap_words(t,CAP_WORDS), f"CONTROL 1: first {CAP_WORDS} words")
        trajectory(lambda t:cap_sents(t,CAP_SENTS), f"CONTROL 2: first {CAP_SENTS} sentences")

        # CONTROL 3: length-stratified — does the rise appear WITHIN a fixed length band?
        print(f"\n  [CONTROL 3: length-stratified] — early vs late retention within summary-length bands")
        # compute per-story mean summary length + uncapped retention
        per=[]
        for r in rows:
            L=np.mean([len(s.split()) for s in r["summ"]])
            v=retention(r["src"],r["summ"],lambda t:t)
            if v is not None: per.append((r["w"],L,v))
        Ls=[p[1] for p in per]; q1,q2=np.percentile(Ls,[33,66])
        early_set=set(weeks[:3]); late_set=set(weeks[-3:])
        for name,lo,hi in [("short",0,q1),("med",q1,q2),("long",q2,1e9)]:
            band=[p for p in per if lo<=p[1]<hi]
            e=[p[2] for p in band if p[0] in early_set]; l=[p[2] for p in band if p[0] in late_set]
            if e and l:
                print(f"    {name:5s} ({lo:.0f}-{hi if hi<1e8 else 999:.0f}w, n={len(band)}): "
                      f"early={np.mean(e):.3f} late={np.mean(l):.3f} "
                      f"{'rise' if np.mean(l)>np.mean(e) else 'no rise'}")
        print()
    print("VERDICT GUIDE:")
    print("  - if CONTROL 1 & 2 still show the rise -> snap survives hard length-capping, NOT verbosity")
    print("  - if CONTROL 3 shows rise WITHIN length bands -> length cannot explain it (cleanest proof)")
    print("  - if the rise VANISHES when capped -> snap is partly/mostly a verbosity effect; downgrade F1")

if __name__=="__main__": main()
