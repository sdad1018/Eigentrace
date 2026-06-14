#!/usr/bin/env python3
"""
test_salience_control.py — Is "charged>bland" (teeth>cage, actor>action) a real
finding, or just NORMAL SUMMARIZATION keeping high-information specifics and
dropping low-information filler?

Control variable: IDF (inverse document frequency across stories) = informativeness.
  High-IDF = rare/specific/contentful. Low-IDF = common/generic/boilerplate.

Logic: if models simply keep salient (high-IDF) words and drop filler (low-IDF),
then retention is explained by IDF alone, and the teeth/cage + actor/action labels
should add NOTHING once IDF is controlled. If the labels SURVIVE IDF control, the
effect is specific to charged-ness / actor-ness, not just informativeness.

Regression: retention ~ IDF + is_teeth + is_actor
  - If is_teeth / is_actor coefficients vanish -> "just summarization" (keep specific, drop filler)
  - If they survive -> a real content-type effect beyond informativeness
"""
import json, glob, os, re, sys, math
import numpy as np
from collections import Counter

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4; MARGIN=0.04
TEETH_SEEDS=["secretly","quietly","covertly","deliberately","killed","devastated","forced","caused","attacked","destroyed","seized","slaughtered","bombed","massacred","concealed","suppressed","coerced","exploited","betrayed","abandoned"]
CAGE_SEEDS=["committee","agency","official","announced","policy","statement","department","meeting","report","framework","ministry","commission","council","regulation","spokesperson","initiative","programme","authority","administration"]
STOP=set("the a an and or but of to in on at for with from by as is are was were be been being this that these those it its their his her our your they them we you i he she him who whom which what when where why how than then so if not no nor can will would could should may might must have has had do does did about into over under up down out off more most some any all each both few many much other another such only own same said says new news first last year years day days time".split())

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

    # PASS 1: document frequency (how many stories each word appears in) -> IDF
    docfreq=Counter(); recs=[]; Ndoc=0
    for fi,f in enumerate(files):
        if fi%2000==0: print(f"  df pass [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=a.get("source_body","")or""; mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        words=[w.lower() for w in re.findall(r"[A-Za-z]{4,}",src)]
        words=[w for w in dict.fromkeys(words) if w not in STOP]
        if len(words)<6: continue
        for w in set(words): docfreq[w]+=1
        # crude actor flag: word appears Capitalized in source & not as lowercase
        toks=re.findall(r"\b[A-Za-z]{3,}\b",src)
        caps={t.lower() for t in toks if t[0].isupper()}; lows={t.lower() for t in toks if t[0].islower()}
        actors=caps-lows
        recs.append((words," ".join(mr.values()),actors)); Ndoc+=1
    def idf(w): return math.log(Ndoc/(1+docfreq.get(w,0)))

    # PASS 2: retention + IDF + labels
    rows=[]  # ret, idf, is_teeth, is_actor
    for ri,(words,summ,actors) in enumerate(recs):
        if ri%500==0: print(f"  score [{ri}/{len(recs)}]",flush=True)
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents); we=embed(words)
        for w,wv in zip(words,we):
            ret=float(np.max(se@wv))
            ct,cc=float(wv@teeth_c),float(wv@cage_c)
            is_teeth = 1 if (ct-cc)>MARGIN else (0 if (cc-ct)>MARGIN else -1)  # -1 = ambiguous
            is_actor = 1 if w in actors else 0
            rows.append((ret, idf(w), is_teeth, is_actor))
    rows=np.array(rows)
    ret=rows[:,0]; idfv=rows[:,1]; teeth=rows[:,2]; actor=rows[:,3]
    print(f"\n=== {len(rows)} terms | Ndoc={Ndoc} ===")
    print(f"correlation(retention, IDF): {np.corrcoef(ret,idfv)[0,1]:+.3f}  (positive = specific words retained more)")

    from scipy import stats
    # MODEL 1: retention ~ IDF only  (how much does pure informativeness explain?)
    X1=np.column_stack([np.ones(len(rows)),idfv]); b1,_,_,_=np.linalg.lstsq(X1,ret,rcond=None)
    r2_1=1-((ret-X1@b1)**2).sum()/((ret-ret.mean())**2).sum()
    print(f"\nMODEL 1 (IDF only): R²={r2_1:.4f}  IDF coef={b1[1]:+.4f}")

    # MODEL 2: retention ~ IDF + is_teeth (teeth vs cage only, drop ambiguous)
    mask=teeth>=0
    Xt=np.column_stack([np.ones(mask.sum()),idfv[mask],teeth[mask]]); bt,_,_,_=np.linalg.lstsq(Xt,ret[mask],rcond=None)
    res=ret[mask]-Xt@bt; n,k=Xt.shape; se2=(res@res)/(n-k); seb=np.sqrt(np.diag(se2*np.linalg.inv(Xt.T@Xt)))
    t_te=bt[2]/seb[2]; p_te=2*(1-stats.t.cdf(abs(t_te),n-k))
    print(f"\nMODEL 2 (IDF + is_teeth): is_teeth coef={bt[2]:+.4f} t={t_te:.2f} p={p_te:.2e}")
    print(f"  -> {'TEETH effect SURVIVES informativeness control (real content-type effect)' if p_te<0.01 and bt[2]>0 else 'teeth effect explained by IDF (just summarization keeping specifics)'}")

    # MODEL 3: retention ~ IDF + is_actor
    Xa=np.column_stack([np.ones(len(rows)),idfv,actor]); ba,_,_,_=np.linalg.lstsq(Xa,ret,rcond=None)
    res=ret-Xa@ba; n,k=Xa.shape; se2=(res@res)/(n-k); seb=np.sqrt(np.diag(se2*np.linalg.inv(Xa.T@Xa)))
    t_ac=ba[2]/seb[2]; p_ac=2*(1-stats.t.cdf(abs(t_ac),n-k))
    print(f"\nMODEL 3 (IDF + is_actor): is_actor coef={ba[2]:+.4f} t={t_ac:.2f} p={p_ac:.2e}")
    print(f"  -> {'ACTOR effect SURVIVES informativeness control' if p_ac<0.01 and ba[2]>0 else 'actor effect explained by IDF (actors are just high-info words)'}")

    print("\n=== INTERPRETATION ===")
    teeth_real = p_te<0.01 and bt[2]>0
    actor_real = p_ac<0.01 and ba[2]>0
    if teeth_real or actor_real:
        print("  At least one effect SURVIVES IDF control -> NOT purely normal summarization.")
        print("  There is a content-type retention bias beyond mere informativeness.")
    else:
        print("  Both effects vanish under IDF control -> consistent with NORMAL SUMMARIZATION:")
        print("  models keep specific/high-information words, drop generic filler. No special bias.")
    open("anamnesis_results/salience_control_results.json","w").write(json.dumps({
        "n_terms":len(rows),"corr_ret_idf":float(np.corrcoef(ret,idfv)[0,1]),"idf_only_r2":float(r2_1),
        "teeth_coef_ctrl_idf":float(bt[2]),"teeth_p_ctrl_idf":float(p_te),
        "actor_coef_ctrl_idf":float(ba[2]),"actor_p_ctrl_idf":float(p_ac),
        "teeth_survives":bool(teeth_real),"actor_survives":bool(actor_real)},indent=2))
    print("Saved: anamnesis_results/salience_control_results.json")
    return 0
if __name__=="__main__": sys.exit(main())
