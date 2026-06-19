#!/usr/bin/env python3
"""
harden_gpu.py — GPU hardening battery. NEEDS broadcast stopped (bash ainn.sh stop) and a second
embedding model. Addresses the critic's two deepest falsification items:

  TEST 1 — Does the ABSENT-SNAP survive a DIFFERENT embedding model?
           The whole instrument rests on bge-large. We recompute source-retention (the absent
           axis) for the Iran stories using a SECOND embedding model (default: intfloat/e5-large-v2,
           a different family/training) and check the -0.17 -> +0.95 weekly trajectory survives.
           If it does, the snap is not a bge artifact. If it vanishes, Finding 1 is embedding-bound.

           Method note: the live "absent" axis is LEXICAL overlap quantized to a trit. To make a
           clean cross-embedding test we compute a CONTINUOUS semantic retention: for each story,
           mean over source sentences of max cosine(sentence, any summary sentence), under each
           embedding model. Then correlate the two models' weekly means, and check both show the
           early-negative -> late-high rise. (This ALSO partially addresses "lexical vs semantic
           omission": e5 retention is semantic, so if it tracks the lexical absent axis, the proxy
           is validated; if not, that's the honest limit.)

  TEST 4 — Does the VOID/LOGOS direction survive RANDOMIZATION + nearest-neighbor stability?
           The novel claim (2b). Two checks per story:
             (i) PERMUTATION NULL: the real anti-consensus direction's nearest topical word vs the
                 nearest word for the SAME SVD on SHUFFLED/random summary sets. Is the real
                 direction's topical-relatedness better than the null? (If random five-text sets
                 produce equally "topical" void words, the signal is an artifact.)
             (ii) PERTURBATION STABILITY: add small Gaussian noise to the embeddings, recompute the
                  anti-consensus direction, measure cosine to the unperturbed direction. Stable =
                  robust geometry; unstable = reading tea leaves in a noisy residual.

Requires: sentence-transformers (e5), the existing bge embeddings or ability to recompute them.
Edit MODEL2 if e5 isn't available; gte-large or all-mpnet-base-v2 are fine alternates.
"""
import json, glob, os, re, sys
from collections import defaultdict
import numpy as np

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
MODEL1="BAAI/bge-large-en-v1.5"     # the instrument's model
MODEL2="intfloat/e5-large-v2"        # the independent check (different family)
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]
N_PERM=200      # permutation null iterations per story (sampled)
N_STORIES_VOID=120   # subsample for the expensive void test
NOISE=0.01      # perturbation stddev for stability

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

def load_rows():
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
        summaries=[v for v in (mr.get(m,"") for m in ALLMODELS) if v and len(v)>40]
        src=a.get("source_body","") or ""
        if len(summaries)<3 or len(src)<200: continue
        rows.append({"w":wk(d),"src":src,"summaries":summaries,
                     "void":[w for w in (a.get("void_words",[]) or []) if w]})
    rows.sort(key=lambda r:r["w"])
    return rows

def main():
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception as e:
        print("need sentence-transformers + scikit-learn:", e); sys.exit(1)
    rows=load_rows()
    weeks=sorted(set(r["w"] for r in rows))
    print(f"loaded {len(rows)} Iran stories, weeks {weeks[0]}..{weeks[-1]}\n")

    print(f"loading embedding models:\n  M1={MODEL1}\n  M2={MODEL2}")
    m1=SentenceTransformer(MODEL1)
    m2=SentenceTransformer(MODEL2)

    def emb(model,texts,is_e5=False):
        if is_e5:  # e5 wants prefixes
            texts=[("query: "+t) for t in texts]
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    # ===================== TEST 1: absent-snap across embeddings =====================
    print("\n"+"="*88)
    print("TEST 1 — absent/retention trajectory under TWO embedding models")
    print("="*88)
    def semantic_retention(model, src, summaries, is_e5):
        ss=sent_split(src)
        if not ss: return None
        allsum=[]; 
        for s in summaries: allsum+=sent_split(s)
        if not allsum: return None
        E_src=emb(model,ss,is_e5); E_sum=emb(model,allsum,is_e5)
        sim=cosine_similarity(E_src,E_sum)   # src_sent x sum_sent
        # retention = mean over source sentences of max similarity to any summary sentence
        return float(np.mean(sim.max(axis=1)))
    wk_ret1=defaultdict(list); wk_ret2=defaultdict(list)
    for i,r in enumerate(rows):
        r1=semantic_retention(m1,r["src"],r["summaries"],False)
        r2=semantic_retention(m2,r["src"],r["summaries"],True)
        if r1 is not None: wk_ret1[r["w"]].append(r1)
        if r2 is not None: wk_ret2[r["w"]].append(r2)
        if i%80==0: print(f"  ...{i}/{len(rows)}")
    print(f"\n  {'week':9s} {'n':>4s} {'M1_retention':>13s} {'M2_retention':>13s}")
    s1=[];s2=[]
    for w in weeks:
        a1=np.mean(wk_ret1[w]) if wk_ret1[w] else float('nan')
        a2=np.mean(wk_ret2[w]) if wk_ret2[w] else float('nan')
        s1.append(a1); s2.append(a2)
        print(f"  {w:9s} {len(wk_ret1[w]):>4d} {a1:>13.3f} {a2:>13.3f}")
    s1=np.array(s1); s2=np.array(s2)
    msk=~(np.isnan(s1)|np.isnan(s2))
    if msk.sum()>3:
        corr=np.corrcoef(s1[msk],s2[msk])[0,1]
        early1,late1=np.nanmean(s1[:3]),np.nanmean(s1[-3:])
        early2,late2=np.nanmean(s2[:3]),np.nanmean(s2[-3:])
        print(f"\n  weekly correlation M1 vs M2: r={corr:.3f}")
        print(f"  M1 early3->late3: {early1:.3f} -> {late1:.3f}  (rise {'YES' if late1>early1 else 'NO'})")
        print(f"  M2 early3->late3: {early2:.3f} -> {late2:.3f}  (rise {'YES' if late2>early2 else 'NO'})")
        print(f"  -> if BOTH rise and r is high, the absent-snap is NOT a bge artifact (Finding 1 hardens).")
        print(f"  -> note: this is SEMANTIC retention; the live axis is LEXICAL. If they agree, the")
        print(f"     lexical proxy is validated against semantics (addresses 'lexical vs semantic').")

    # ===================== TEST 4: void/logos randomization + stability =====================
    print("\n"+"="*88)
    print("TEST 4 — anti-consensus direction: permutation null + perturbation stability")
    print("="*88)
    # Build a corpus sentence pool for the "nearest word" readout proxy:
    # We test STABILITY (perturbation) and a NULL (random summary sets) on the SVD residual direction.
    sub=rows[:N_STORIES_VOID] if len(rows)>N_STORIES_VOID else rows
    def anticonsensus_dir(summaries, model=m1, is_e5=False, noise=0.0):
        vecs=emb(model,[s[:1000] for s in summaries],is_e5)
        if noise>0: vecs=vecs+np.random.normal(0,noise,vecs.shape)
        c=vecs.mean(0)
        # anti-consensus = direction of LEAST variance / residual after removing consensus.
        # Use smallest right-singular vector of centered matrix as the "circled but unoccupied" dir.
        M=vecs-c
        try:
            U,S,Vt=np.linalg.svd(M,full_matrices=False)
            return Vt[-1]   # least-variance direction
        except: return None
    # (i) perturbation stability
    stab=[]
    for r in sub:
        d0=anticonsensus_dir(r["summaries"],noise=0.0)
        if d0 is None: continue
        sims=[]
        for _ in range(10):
            dn=anticonsensus_dir(r["summaries"],noise=NOISE)
            if dn is not None:
                sims.append(abs(float(np.dot(d0,dn))/(np.linalg.norm(d0)*np.linalg.norm(dn)+1e-9)))
        if sims: stab.append(np.mean(sims))
    print(f"\n  (i) PERTURBATION STABILITY (noise sd={NOISE}, {len(stab)} stories):")
    if stab:
        print(f"      mean |cosine| to unperturbed direction: {np.mean(stab):.3f}")
        print(f"      (1.0 = perfectly stable; <0.5 = the direction is noise-dominated)")
    # (ii) permutation null: is the real direction more 'consensus-orthogonal' than random sets?
    # Proxy metric: real anti-consensus dir should have LOWER projection onto the consensus mean
    # than a direction from a RANDOM mix of summaries across stories.
    allsum=[]
    for r in sub: allsum+=r["summaries"]
    real_orth=[]; null_orth=[]
    for r in sub:
        vecs=emb(m1,[s[:1000] for s in r["summaries"]],False)
        c=vecs.mean(0); c=c/(np.linalg.norm(c)+1e-9)
        d=anticonsensus_dir(r["summaries"])
        if d is None: continue
        real_orth.append(abs(float(np.dot(d,c))))   # closeness to consensus (lower=more anti)
        # null: random same-size set from the global pool
        idx=np.random.choice(len(allsum),size=len(r["summaries"]),replace=False)
        rv=emb(m1,[allsum[j][:1000] for j in idx],False)
        rc=rv.mean(0); rc=rc/(np.linalg.norm(rc)+1e-9)
        dn=anticonsensus_dir([allsum[j] for j in idx])
        if dn is not None: null_orth.append(abs(float(np.dot(dn,rc))))
    print(f"\n  (ii) PERMUTATION NULL ({len(real_orth)} real vs {len(null_orth)} random sets):")
    if real_orth and null_orth:
        from scipy import stats
        t,p=stats.mannwhitneyu(real_orth,null_orth,alternative='two-sided')
        print(f"      real anti-consensus |proj onto consensus|: mean={np.mean(real_orth):.3f}")
        print(f"      random-set                       |proj|:   mean={np.mean(null_orth):.3f}")
        print(f"      Mann-Whitney p={p:.4f}")
        print(f"      -> if real != random (low p) AND real is more orthogonal, the anti-consensus")
        print(f"         direction is a REAL property of these 5 summaries, not a generic SVD residual.")
        print(f"      -> if real ~= random, Finding 2b is over-interpreted and should be downgraded.")
    print("\nDONE. Remember to restart the broadcast: bash ainn.sh start")

if __name__=="__main__": main()
