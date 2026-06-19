#!/usr/bin/env python3
"""
harden_reanalysis.py — NO-GPU hardening tests on existing data. Pure reanalysis.
Addresses two of the critic's falsification items without re-embedding anything:

  TEST 3  — Claude->Grok handoff survives ALTERNATIVE distance metrics?
            Current outlier = argmax(model_vix). We recompute the "outlier" three other ways
            and check the handoff direction (Claude high early, Grok high late) survives:
              (a) argmax of model_vix  (the current method, baseline)
              (b) SECOND-farthest model (is it just the argmax-winner that hands off, or the
                  whole tail shifting Claude->Grok?)
              (c) "share of total spread": each model's VIX / sum(VIX) that week — continuous,
                  no argmax. Does Grok's continuous share rise and Claude's fall?

  CONFOUND (summary length) — did SUMMARIES get longer as the war escalated? If yes, lexical
            retention (absent axis) rises mechanically. Same shape as the source-density confound.
            We measure mean summary length per week against the absent-axis trajectory.
"""
import json, glob, os, re
from collections import defaultdict, Counter
import numpy as np
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]
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

def main():
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
        mv=a.get("model_vix",{}) or a.get("mv",{}) or {}
        mr=a.get("model_responses",{}) or {}
        sumlens={m:len((mr.get(m,"") or "").split()) for m in ALLMODELS if mr.get(m)}
        rows.append({"w":wk(d),"mv":mv,"sumlens":sumlens})
    rows.sort(key=lambda r:r["w"])
    weeks=sorted(set(r["w"] for r in rows))
    # stable-5 weeks (recompute to be self-contained)
    wk_n=Counter(); wk_pres=defaultdict(Counter)
    for r in rows:
        wk_n[r["w"]]+=1
        for m in r["mv"]: wk_pres[r["w"]][m]+=1
    stable5=[w for w in weeks if all(wk_pres[w].get(m,0)/max(wk_n[w],1)>=0.8 for m in ALLMODELS)]
    print(f"rows={len(rows)}  stable5 weeks={stable5}\n")

    # ============ TEST 3: handoff under alternative distance metrics ============
    print("="*88)
    print("TEST 3 — does the Claude->Grok handoff survive alternative outlier definitions?")
    print("         (reported on stable-5 weeks only, the denominator-honest subset)")
    print("="*88)

    def argmax_share(rows_w):
        out=Counter(); n=0
        for r in rows_w:
            if not r["mv"]: continue
            out[max(r["mv"],key=r["mv"].get)]+=1; n+=1
        return {m:100*out[m]/max(n,1) for m in ALLMODELS}
    def second_share(rows_w):
        out=Counter(); n=0
        for r in rows_w:
            if len(r["mv"])<2: continue
            srt=sorted(r["mv"],key=r["mv"].get,reverse=True)
            out[srt[1]]+=1; n+=1   # second-farthest
        return {m:100*out[m]/max(n,1) for m in ALLMODELS}
    def continuous_share(rows_w):
        # each model's mean (VIX / sum-of-VIX-that-story), averaged over stories
        acc=defaultdict(list)
        for r in rows_w:
            s=sum(r["mv"].values())
            if s<=0: continue
            for m in ALLMODELS:
                if m in r["mv"]: acc[m].append(r["mv"][m]/s)
        return {m:100*np.mean(acc[m]) if acc[m] else 0 for m in ALLMODELS}

    half=len(stable5)//2
    early_w=set(stable5[:half]); late_w=set(stable5[half:])
    er=[r for r in rows if r["w"] in early_w]; lr=[r for r in rows if r["w"] in late_w]
    print(f"  early stable weeks: {sorted(early_w)}   late: {sorted(late_w)}\n")
    for name,fn in [("(a) argmax [baseline]",argmax_share),
                    ("(b) second-farthest  ",second_share),
                    ("(c) continuous share ",continuous_share)]:
        e=fn(er); l=fn(lr)
        dC=l["Claude"]-e["Claude"]; dG=l["Grok"]-e["Grok"]
        survives = (dC<0 and dG>0)
        print(f"  {name}:  Claude {e['Claude']:.0f}%->{l['Claude']:.0f}% (Δ{dC:+.0f})   "
              f"Grok {e['Grok']:.0f}%->{l['Grok']:.0f}% (Δ{dG:+.0f})   "
              f"handoff {'SURVIVES' if survives else 'does NOT survive'}")
    print("\n  -> handoff = Claude DROPS and Grok RISES early->late. If it holds under (b) and (c),")
    print("     it is not an argmax artifact; the whole divergence tail shifts, not just the winner.")

    # ============ CONFOUND: did summaries get longer as the war escalated? ============
    print("\n"+"="*88)
    print("CONFOUND — did SUMMARY length grow with escalation? (would inflate lexical retention)")
    print("="*88)
    print(f"  {'week':9s} {'n':>4s} {'mean_summary_words':>18s}")
    sl_by_wk={}
    for w in weeks:
        lens=[]
        for r in rows:
            if r["w"]!=w: continue
            lens+=list(r["sumlens"].values())
        sl_by_wk[w]=np.mean(lens) if lens else 0
        print(f"  {w:9s} {sum(1 for r in rows if r['w']==w):>4d} {sl_by_wk[w]:>18.0f}")
    early_sl=np.mean([sl_by_wk[w] for w in weeks[:3]])
    late_sl=np.mean([sl_by_wk[w] for w in weeks[-3:]])
    print(f"\n  early-3-week mean summary length: {early_sl:.0f} words")
    print(f"  late-3-week  mean summary length: {late_sl:.0f} words")
    print(f"  -> absent axis went -0.17 -> +0.95 over this span.")
    print(f"  -> if summary length is ~FLAT, the absent snap is NOT a summary-length artifact.")
    print(f"  -> if summaries got much LONGER late, that's a confound to disclose.")

if __name__=="__main__": main()
