#!/usr/bin/env python3
"""
iran_arc_v2.py — REBUILD on the full corpus (780 classified Iran segments, current through 6/18),
with denominator-honest per-model analysis. Answers the red-team's two strongest hits:

  CONFOUND 1 (source density): already ruled out separately — sources stayed flat (~210 words,
  propn ~0.21) across the arc while the absent axis snapped. Recomputed here for the record.

  CONFOUND 2 (ensemble size): Gemini dropped OUT of the pipeline W16-W18 (0 stories some weeks),
  so the "five models" was 4 in exactly the pivot weeks, and VIX-outlier share (relative) was
  computed on a shifting denominator. FIX: report Finding 3 two ways —
    (a) ALL weeks, with per-week ensemble size N disclosed
    (b) STABLE-5 subset: only weeks where all 5 models fired on >=80% of stories — robustness check
  If the Claude->Grok handoff survives (b), it's denominator-honest and bulletproof.

All-weeks axis trajectory (Findings 1,2,4) is kept — those are ensemble-AGGREGATE, not
per-model-relative, so the denominator shift barely touches them. Only Finding 3 needs the dual report.
"""
import json, glob, os, re
from collections import Counter, defaultdict
import numpy as np
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
import sys; sys.path.insert(0,'.'); import eigenching as EC
NAME2SIG={(v[0] if isinstance(v,tuple) else v):sig for sig,v in EC.ARCHETYPES.items()}
AXIS_IDX={a:i for i,a in enumerate(EC.AXIS_ORDER)}
LABEL2TRIT=[{lab:tr for tr,(lab,_) in EC.AXES[ax].items()} for ax in EC.AXIS_ORDER]
PH2MOVES=defaultdict(list)
for (ax,av,actv),ph in EC.MODIFIERS.items(): PH2MOVES[ph].append((ax,actv))
AXES=EC.AXIS_ORDER
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]

def ts(f):
    m=re.match(r'(\d{8})_(\d{6})', os.path.basename(f)); return m.group(1)+m.group(2) if m else ""
def wk(d):
    from datetime import datetime
    return datetime.strptime(d[:8],"%Y%m%d").strftime("%Y-W%U")
def pname(tx):
    if "EigenChing state:" not in tx: return None
    return tx.split("EigenChing state:")[1].split(". This is")[0].split(". Source")[0].split(". Outside")[0].strip().rstrip(".")
def pcomp(name):
    head=name.split(".")[0].strip().split()
    if len(head)<6: return None
    s=[]
    for i,w in enumerate(head[:6]):
        if w in LABEL2TRIT[i]: s.append(LABEL2TRIT[i][w])
        else: return None
    return tuple(s)
def recon(full):
    if "," not in full:
        b=full.strip(); return NAME2SIG.get(b) or pcomp(b)
    base,mp=full.split(",",1); base=base.strip()
    if base not in NAME2SIG: return pcomp(full)
    s=list(NAME2SIG[base]); used=set()
    for ph in [m.strip() for m in mp.replace(" and ","|").split("|") if m.strip()]:
        for ax,actv in sorted(PH2MOVES.get(ph,[]),key=lambda m:AXIS_IDX[m[0]]):
            if ax in used: continue
            s[AXIS_IDX[ax]]=actv; used.add(ax); break
    return tuple(s)

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
        nm=None
        for b in (seg.get("beats") or []):
            if "state_vector" in b.get("phase",""): nm=pname(b.get("text","")); break
        if not nm: continue
        sig=recon(nm)
        if not sig or len(sig)!=6: continue
        d=ts(f)
        if not d: continue
        rows.append({"d":d,"w":wk(d),"sig":list(sig),"mv":a.get("mv") or a.get("model_vix",{}) or {},
                     "void":a.get("void_words",[]) or []})
    rows.sort(key=lambda r:r["d"])
    weeks=sorted(set(r["w"] for r in rows))
    print(f"FULL CORPUS: {len(rows)} classified Iran segments, {rows[0]['d'][:8]} -> {rows[-1]['d'][:8]}")
    print(f"weeks: {weeks[0]} -> {weeks[-1]} ({len(weeks)} weeks)\n")

    # ---- AXIS TRAJECTORY (all weeks) ----
    byweek=defaultdict(list)
    for r in rows: byweek[r["w"]].append(r["sig"])
    print("="*92)
    print("AXIS TRAJECTORY (all weeks, full corpus) — ensemble-aggregate, denominator-robust")
    print("="*92)
    print(f"  {'week':9s} {'n':>4s}  "+" ".join(f"{a[:6]:>7s}" for a in AXES))
    traj={}
    for w in weeks:
        arr=np.array(byweek[w]); m=arr.mean(0); traj[w]=m
        print(f"  {w:9s} {len(arr):>4d}  "+" ".join(f"{x:>+7.2f}" for x in m))

    # ---- ENSEMBLE SIZE per week (the Gemini confound, quantified) ----
    print("\n"+"="*92)
    print("ENSEMBLE SIZE per week — how many of the 5 models actually fired (the denominator)")
    print("="*92)
    wk_modelpresence=defaultdict(lambda: Counter()); wk_n=Counter()
    for r in rows:
        wk_n[r["w"]]+=1
        for mdl in r["mv"]: wk_modelpresence[r["w"]][mdl]+=1
    stable5=[]
    print(f"  {'week':9s} {'n':>4s}  "+" ".join(f"{m[:4]:>6s}" for m in ALLMODELS)+"   stable5?")
    for w in weeks:
        n=wk_n[w]; pres=wk_modelpresence[w]
        shares=[pres.get(m,0)/max(n,1) for m in ALLMODELS]
        is_stable = all(s>=0.8 for s in shares)
        if is_stable: stable5.append(w)
        print(f"  {w:9s} {n:>4d}  "+" ".join(f"{100*s:>5.0f}%" for s in shares)+f"   {'YES' if is_stable else 'no'}")
    print(f"\n  stable-5 weeks (all models >=80% present): {stable5}")

    # ---- FINDING 3 — dual report ----
    def outlier_share(week_filter):
        out=defaultdict(Counter); tot=Counter()
        for r in rows:
            if r["w"] not in week_filter: continue
            mv=r["mv"]
            if not mv: continue
            tot[r["w"]]+=1; out[r["w"]][max(mv,key=mv.get)]+=1
        return out,tot
    print("\n"+"="*92)
    print("FINDING 3 (a) — VIX-outlier share, ALL weeks (denominator varies, disclosed)")
    print("="*92)
    out_all,tot_all=outlier_share(set(weeks))
    print(f"  {'week':9s} {'n':>4s}  "+" ".join(f"{m[:4]:>6s}" for m in ALLMODELS))
    for w in weeks:
        t=tot_all[w] or 1
        print(f"  {w:9s} {t:>4d}  "+" ".join(f"{100*out_all[w][m]//t:>5d}%" for m in ALLMODELS))
    print("\n"+"="*92)
    print("FINDING 3 (b) — STABLE-5 weeks only (denominator-honest robustness check)")
    print("="*92)
    out_s,tot_s=outlier_share(set(stable5))
    print(f"  {'week':9s} {'n':>4s}  "+" ".join(f"{m[:4]:>6s}" for m in ALLMODELS))
    for w in stable5:
        t=tot_s[w] or 1
        print(f"  {w:9s} {t:>4d}  "+" ".join(f"{100*out_s[w][m]//t:>5d}%" for m in ALLMODELS))
    # does the handoff survive? compare Claude vs Grok early-vs-late within stable5
    if len(stable5)>=4:
        half=len(stable5)//2
        early=stable5[:half]; late=stable5[half:]
        def share(model,wks):
            tn=sum(tot_s[w] for w in wks) or 1
            return 100*sum(out_s[w][model] for w in wks)//tn
        print(f"\n  HANDOFF TEST on stable-5 weeks:")
        print(f"    early {early}: Claude {share('Claude',early)}%  Grok {share('Grok',early)}%")
        print(f"    late  {late}: Claude {share('Claude',late)}%  Grok {share('Grok',late)}%")
        print(f"    -> handoff survives if Claude DROPS and Grok RISES early->late on clean 5-model weeks")

    # ---- per-model totals, stable5 only ----
    print("\n"+"="*92)
    print("PER-MODEL outlier totals — full vs stable-5")
    print("="*92)
    of,_=outlier_share(set(weeks)); os_,_=outlier_share(set(stable5))
    tot_full=Counter(); tot_st=Counter()
    for w in weeks:
        for m in ALLMODELS: tot_full[m]+=of[w][m]
    for w in stable5:
        for m in ALLMODELS: tot_st[m]+=os_[w][m]
    print(f"  {'model':10s} {'full':>6s} {'stable5':>8s}")
    for m in sorted(ALLMODELS,key=lambda m:-tot_full[m]):
        print(f"  {m:10s} {tot_full[m]:>6d} {tot_st[m]:>8d}")

    json.dump({"n":len(rows),"weeks":weeks,"stable5":stable5,
               "traj":{w:traj[w].round(3).tolist() for w in weeks}}, open("iran_arc_v2.json","w"))
    print(f"\nwrote iran_arc_v2.json")

if __name__=="__main__": main()
