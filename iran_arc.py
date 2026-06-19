#!/usr/bin/env python3
"""
iran_arc.py — the EigenChing shape of the Iran story, evolving over ~85 days, decomposed by model.
Uses ONLY the 593 fully-classified story segments (skip roundtables; parse timestamp from filename).
Reconstructs the TRUE signature per segment (validated aggregator logic), orders by time, and:
  (1) plots the 6-axis signature as a time series (weekly-binned mean trit per axis)
  (2) per-model: VIX-outlier frequency + salient-claim omissions, over the whole arc AND by phase
  (3) the void-word drift: which charged concepts get dropped in which weeks
Writes iran_arc.json (data) for the eventual visual.
"""
import json, glob, os, sys, re
from collections import Counter, defaultdict
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import eigenching as EC
NAME2SIG={(v[0] if isinstance(v,tuple) else v):sig for sig,v in EC.ARCHETYPES.items()}
AXIS_IDX={a:i for i,a in enumerate(EC.AXIS_ORDER)}
LABEL2TRIT=[{lab:tr for tr,(lab,_) in EC.AXES[ax].items()} for ax in EC.AXIS_ORDER]
PHRASE2MOVES=defaultdict(list)
for (axis,av,actv),ph in EC.MODIFIERS.items(): PHRASE2MOVES[ph].append((axis,actv))
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
AXES=EC.AXIS_ORDER

def parse_name(tx):
    if "EigenChing state:" not in tx: return None
    return tx.split("EigenChing state:")[1].split(". This is")[0].split(". Source")[0].split(". Outside")[0].strip().rstrip(".")
def parse_comp(name):
    head=name.split(".")[0].strip().split()
    if len(head)<6: return None
    sig=[]
    for i,w in enumerate(head[:6]):
        if w in LABEL2TRIT[i]: sig.append(LABEL2TRIT[i][w])
        else: return None
    return tuple(sig)
def reconstruct(full):
    if "," not in full:
        b=full.strip()
        if b in NAME2SIG: return NAME2SIG[b]
        return parse_comp(b)
    base,modpart=full.split(",",1); base=base.strip()
    if base not in NAME2SIG: return parse_comp(full)
    sig=list(NAME2SIG[base]); used=set()
    for ph in [m.strip() for m in modpart.replace(" and ","|").split("|") if m.strip()]:
        for axis,actv in sorted(PHRASE2MOVES.get(ph,[]),key=lambda m:AXIS_IDX[m[0]]):
            if axis in used: continue
            sig[AXIS_IDX[axis]]=actv; used.add(axis); break
    return tuple(sig)
def ts_from_fname(f):
    m=re.match(r'(\d{8})_(\d{6})', os.path.basename(f))
    return (m.group(1)+m.group(2)) if m else ""

def main():
    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"))
    rows=[]
    for f in files:
        try: seg=json.load(open(f))
        except: continue
        if "roundtable" in f: continue
        a=seg.get("attribution") or {}
        t=(a.get("story_title","") or "").lower()
        if not("iran" in t and any(k in t for k in ["talk","peace","deal","truce","ceasefire","negotiat","war","nuclear","enrich"])): continue
        nm=None
        for b in (seg.get("beats") or []):
            if "state_vector" in b.get("phase",""): nm=parse_name(b.get("text","")); break
        if not nm: continue
        sig=reconstruct(nm)
        if not sig or len(sig)!=6: continue
        ts=seg.get("timestamp","") or ts_from_fname(f)
        if not ts: continue
        rows.append({"ts":ts, "date":ts[:8], "title":a.get("story_title","")[:70], "sig":list(sig),
                     "name":nm, "model_vix":a.get("model_vix",{}) or {},
                     "void_words":a.get("void_words",[]) or [],
                     "killshots":[(k.get("claim","")[:50],k.get("omitted_by",[])) for k in (a.get("claim_killshots") or [])]})
    rows.sort(key=lambda r:r["ts"])
    print(f"classified Iran story-segments with sig+ts: {len(rows)}")
    print(f"span: {rows[0]['date']} -> {rows[-1]['date']}")

    # ---- weekly-binned signature trajectory ----
    def wk(d):  # ISO-ish week bucket from YYYYMMDD
        from datetime import datetime
        dt=datetime.strptime(d,"%Y%m%d"); return dt.strftime("%Y-W%U")
    byweek=defaultdict(list)
    for r in rows: byweek[wk(r["date"])].append(r["sig"])
    weeks=sorted(byweek)
    print("\n"+"="*86)
    print("EIGENCHING SHAPE OF THE IRAN STORY — weekly mean per axis (-1..+1), n per week")
    print("="*86)
    print(f"  {'week':9s} {'n':>3s}  " + " ".join(f"{a[:6]:>7s}" for a in AXES))
    for w in weeks:
        arr=np.array(byweek[w]); m=arr.mean(0)
        bar=" ".join(f"{x:>+7.2f}" for x in m)
        print(f"  {w:9s} {len(arr):>3d}  {bar}")
    # absent-axis arc specifically (your interest)
    print("\n  ABSENT AXIS over time (negative = content erased; the 'lossy' weeks):")
    for w in weeks:
        arr=np.array(byweek[w]); ab=arr[:,1].mean()
        blk="█"*int(round((ab+1)*10)); print(f"    {w} {ab:>+5.2f} {'lossy' if ab<-0.2 else ''}")

    # ---- per-model decomposition over the arc ----
    print("\n"+"="*86); print("PER-MODEL over the Iran arc"); print("="*86)
    out=Counter(); om=Counter(); seen_models=set()
    for r in rows:
        mv=r["model_vix"]
        if mv: out[max(mv,key=mv.get)]+=1; seen_models|=set(mv)
        for claim,omitted in r["killshots"]:
            for m in omitted: om[m]+=1
    print(f"  {'model':10s} {'outlier#':>9s} {'omissions':>10s}")
    for m in sorted(seen_models, key=lambda m:-out[m]):
        print(f"  {m:10s} {out[m]:>9d} {om[m]:>10d}")

    # ---- per-model outlier share BY WEEK (does the divergent model change over the arc?) ----
    print("\n  VIX-outlier share by week (who breaks rank as the story evolves):")
    wkout=defaultdict(Counter)
    for r in rows:
        mv=r["model_vix"]
        if mv: wkout[wk(r["date"])][max(mv,key=mv.get)]+=1
    for w in weeks:
        c=wkout[w]; tot=sum(c.values()) or 1
        top=c.most_common(2)
        s=", ".join(f"{m} {100*n//tot}%" for m,n in top)
        print(f"    {w}: {s}")

    # ---- void-word drift: charged concepts dropped, by week ----
    print("\n  CHARGED VOID WORDS by week (what the models drop as the story moves):")
    for w in weeks:
        wc=Counter()
        for r in rows:
            if wk(r["date"])==w:
                for vw in r["void_words"]: wc[vw]+=1
        top=[w0 for w0,_ in wc.most_common(6)]
        print(f"    {w}: {', '.join(top)}")

    json.dump({"n":len(rows),"weeks":weeks,
               "weekly_sig":{w:np.array(byweek[w]).mean(0).round(3).tolist() for w in weeks},
               "rows":rows}, open("iran_arc.json","w"))
    print(f"\nwrote iran_arc.json ({len(rows)} classified Iran segments)")

if __name__=="__main__": main()
