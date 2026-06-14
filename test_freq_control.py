#!/usr/bin/env python3
"""
test_freq_control.py — Is the teeth>cage retention reversal a REAL signal or a
cosine artifact (distinctive/rare words score higher than common/bland ones)?

Method:
  - Recompute per-term semantic retention + teeth/cage label (same as Test A).
  - ALSO record each term's corpus frequency (how often it appears across sources).
  - Control 1: FREQUENCY-MATCHED — bin terms by frequency; within each bin compare
    teeth vs cage retention. If the gap only exists because teeth are rarer, it
    vanishes within frequency bins.
  - Control 2: REGRESSION — predict retention from (is_teeth, log_frequency).
    If is_teeth coefficient stays significant after controlling freq -> real signal.

Verdict: if teeth>cage survives frequency control -> behavioral. If it collapses -> artifact.
"""
import json, glob, os, re, sys
import numpy as np
from collections import Counter

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000
MARGIN=0.04; MIN_RESP=4
TEETH_SEEDS=["secretly","quietly","covertly","deliberately","killed","devastated","forced","caused","attacked","destroyed","seized","slaughtered","bombed","massacred","concealed","suppressed","coerced","exploited","betrayed","abandoned"]
CAGE_SEEDS=["committee","agency","official","announced","policy","statement","department","meeting","report","framework","ministry","commission","council","regulation","spokesperson","initiative","programme","authority","administration"]
STOP=set("the a an and or but of to in on at for with from by as is are was were be been being this that these those it its their his her our your they them we you i he she him who whom which what when where why how than then so if not no nor can will would could should may might must have has had do does did about into over under up down out off more most some any all each both few many much other another such only own same".split())

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))
    teeth_c=embed(TEETH_SEEDS).mean(0); teeth_c/=np.linalg.norm(teeth_c)
    cage_c=embed(CAGE_SEEDS).mean(0); cage_c/=np.linalg.norm(cage_c)

    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments...")

    # PASS 1: corpus frequency of every candidate term
    freq=Counter()
    recs=[]  # (words, source, model_summary) to reuse
    import time as _t; t0=_t.time()
    for fi,f in enumerate(files):
        if fi%1000==0: print(f"  freq pass [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=a.get("source_body","")or""; mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        words=[w.lower() for w in re.findall(r"[A-Za-z]{4,}",src)]
        words=[w for w in dict.fromkeys(words) if w not in STOP]
        if len(words)<6: continue
        for w in words: freq[w]+=1
        recs.append((words," ".join(mr.values())))

    # PASS 2: retention + label + frequency per term
    rows=[]  # (retention, is_teeth, log_freq)
    for ri,(words,summ) in enumerate(recs):
        if ri%500==0: print(f"  score pass [{ri}/{len(recs)}]",flush=True)
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents)
        we=embed(words)
        for w,wv in zip(words,we):
            ct,cc=float(wv@teeth_c),float(wv@cage_c)
            if abs(ct-cc)<MARGIN: continue
            ret=float(np.max(se@wv))
            rows.append((ret, 1 if ct>cc else 0, np.log(freq[w])))
    rows=np.array(rows)
    ret=rows[:,0]; isteeth=rows[:,1].astype(bool); logf=rows[:,2]
    print(f"\n=== {len(rows)} terms | teeth={isteeth.sum()} cage={(~isteeth).sum()} ===")
    print(f"Raw: teeth_ret={ret[isteeth].mean():.4f}  cage_ret={ret[~isteeth].mean():.4f}  gap(teeth-cage)={ret[isteeth].mean()-ret[~isteeth].mean():+.4f}")

    # frequency check: are teeth actually rarer?
    print(f"\nFrequency: teeth median_logf={np.median(logf[isteeth]):.2f}  cage median_logf={np.median(logf[~isteeth]):.2f}")

    # CONTROL 1: frequency-matched bins
    print("\n=== CONTROL 1: frequency-binned teeth-cage gap ===")
    bins=np.quantile(logf,[0,.2,.4,.6,.8,1.0])
    surviving=0; total_bins=0
    for i in range(len(bins)-1):
        m=(logf>=bins[i])&(logf<=bins[i+1])
        tt=ret[m&isteeth]; cc=ret[m&(~isteeth)]
        if len(tt)<20 or len(cc)<20: continue
        total_bins+=1
        gap=tt.mean()-cc.mean()
        if gap>0: surviving+=1
        print(f"  freq bin {i+1} [logf {bins[i]:.1f}-{bins[i+1]:.1f}]: teeth={tt.mean():.4f} cage={cc.mean():.4f} gap={gap:+.4f} (n_t={len(tt)},n_c={len(cc)})")
    print(f"  -> teeth>cage holds in {surviving}/{total_bins} frequency bins")

    # CONTROL 2: regression retention ~ is_teeth + log_freq
    print("\n=== CONTROL 2: regression (does is_teeth survive controlling freq?) ===")
    from scipy import stats
    X=np.column_stack([np.ones(len(rows)), isteeth.astype(float), logf])
    beta,_,_,_=np.linalg.lstsq(X,ret,rcond=None)
    yhat=X@beta; resid=ret-yhat; n,k=X.shape
    se2=(resid@resid)/(n-k); XtX_inv=np.linalg.inv(X.T@X); seb=np.sqrt(np.diag(se2*XtX_inv))
    t_teeth=beta[1]/seb[1]; p_teeth=2*(1-stats.t.cdf(abs(t_teeth),n-k))
    t_freq=beta[2]/seb[2]; p_freq=2*(1-stats.t.cdf(abs(t_freq),n-k))
    print(f"  is_teeth coef={beta[1]:+.4f}  t={t_teeth:.2f}  p={p_teeth:.2e}")
    print(f"  log_freq coef={beta[2]:+.4f}  t={t_freq:.2f}  p={p_freq:.2e}")
    print(f"  -> {'is_teeth SURVIVES freq control: reversal is REAL/behavioral' if p_teeth<0.01 and beta[1]>0 else ('is_teeth coef went negative/insignificant: largely a FREQUENCY ARTIFACT' if beta[1]<=0 or p_teeth>=0.01 else '?')}")

    verdict = "REAL" if (p_teeth<0.01 and beta[1]>0 and surviving>=total_bins-1) else ("ARTIFACT" if beta[1]<=0 else "MIXED")
    print(f"\n=== VERDICT: teeth>cage reversal is {verdict} ===")
    if verdict=="ARTIFACT": print("  (distinctive words score higher cosine retention; not a model-behavior finding)")
    elif verdict=="REAL": print("  (models genuinely retain operational words more, even at matched frequency)")
    else: print("  (partially survives — frequency explains some but not all)")
    open("anamnesis_results/freq_control_results.json","w").write(json.dumps({
        "n_terms":len(rows),"raw_gap_teeth_minus_cage":float(ret[isteeth].mean()-ret[~isteeth].mean()),
        "teeth_median_logf":float(np.median(logf[isteeth])),"cage_median_logf":float(np.median(logf[~isteeth])),
        "bins_teeth_wins":surviving,"bins_total":total_bins,
        "isteeth_coef":float(beta[1]),"isteeth_p":float(p_teeth),"logf_coef":float(beta[2]),"verdict":verdict},indent=2))
    print("Saved: anamnesis_results/freq_control_results.json")
    return 0
if __name__=="__main__": sys.exit(main())
