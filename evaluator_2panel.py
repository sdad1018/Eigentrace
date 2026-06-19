#!/usr/bin/env python3
"""
evaluator_2panel.py — THE EVALUATOR (the moat), 5 API + 5 local judges, TWO PANELS.

ChatGPT's reframe: interventions are swappable; the valuable instrument is the EVALUATOR
that reliably tells whether an intervention yields PREFERRED outputs WITHOUT hallucination.

DESIGN (the careful version — 'more judges' done RIGHT, not a naive 10-way average):
  Generator: qwen2.5:14b (local) — EXCLUDED from judging (no self-preference contamination).
  API PANEL (5):   ChatGPT, Claude, Gemini, DeepSeek, Grok  — strong judges (trustworthy).
  LOCAL PANEL (5): mistral-small, llama3.1:8b, mistral, llama3, nous-hermes2 — the 5 locals
                   that are NOT the generator — weaker judges (the ROBUSTNESS + cheap-ops test).
  Reported SEPARATELY, not blended. Cross-panel AGREEMENT is the real robustness metric:
    both panels say SYNTH>BASELINE -> robust. Only API -> real-but-fragile. Neither -> dead.
  Local panel agreeing also = the evaluator can run CHEAP at scale (product question about
  the instrument itself).

CONDITIONS (concept isolated): A_BASELINE | B_SYNTH (no concept) | C_SYNTH+CONCEPT.
Blind: shuffled order, labels hidden from judges. Tolerant parser + per-judge response-rate.

PRE-REGISTERED (applied to API panel; local panel = robustness check):
  SHIP iff insight +0.5sigma AND faith no-drop AND keep>=0.60 AND SYNTH>BASELINE.
  CONCEPT justified iff beats SYNTH-only by >=10% insight.

API credits used for the 5 API judges. Stream stopped.
"""
import json, os, sys, glob, re, random
import numpy as np, requests
from collections import defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO); sys.path.insert(0,REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN="qwen2.5:14b"
MU=0.55
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
LOCAL_JUDGES=["mistral-small:latest","llama3.1:8b-instruct-q4_0","mistral:latest","llama3:latest","nous-hermes2:latest"]

def gen_local(prompt, model=GEN, mt=320, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":model,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=180)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return ""

def parse_scores(out, order):
    """Tolerant: try strict pattern per summary, else grab first 5 ints in the summary's line block."""
    res={}
    for i in range(3):
        m=re.search(rf"Summary {i+1}:\s*insight=(\d+)\s*faith=(\d+)\s*action=(\d+)\s*trust=(\d+)\s*keep=([01])",
                    out, re.IGNORECASE)
        if m:
            res[order[i]]={"insight":int(m.group(1)),"faith":int(m.group(2)),"action":int(m.group(3)),
                           "trust":int(m.group(4)),"keep":int(m.group(5))}; continue
        # fallback: find the line mentioning Summary i+1, grab integers
        lm=re.search(rf"Summary {i+1}[:\s].*", out, re.IGNORECASE)
        if lm:
            ints=re.findall(r"\d+", lm.group(0))
            if len(ints)>=5:
                v=[int(x) for x in ints[:5]]
                res[order[i]]={"insight":min(v[0],5),"faith":min(v[1],5),"action":min(v[2],5),
                               "trust":min(v[3],5),"keep":1 if v[4]>=1 else 0}
    return res

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    API_JUDGES={n:pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in pa.BIG5_CALLERS}
    print(f"generator: {GEN}")
    print(f"API panel:   {list(API_JUDGES.keys())}")
    print(f"local panel: {LOCAL_JUDGES}")

    items=[]
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]; nn=0
    for f in sorted(SEGS,reverse=True):
        if nn>=4: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<500: continue
            items.append((t,a["source_body"][:2200])); nn+=1
        except: continue

    def concept_for(source,S0):
        cr=gen_local(f"List 12 short (1-3 word) concepts related to this story. Comma-separated:\n\n{source[:1500]}",mt=120,temp=0.2)
        C=[c.strip().lower() for c in re.split(r"[,\n]",cr) if 2<len(c.strip())<40]
        C=[c for c in C if c not in HARD_DROP][:12]
        if len(C)<4: return None
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        rel=Cv@Dv; absn=1-(Cv@S0v); band=1-np.abs(rel-MU)
        return C[int(np.argmax(absn*rel*band))]

    trials=[]
    for idx,(title,source) in enumerate(items):
        S0=gen_local(f"Summarize this news story in 3-4 sentences. Stay faithful; invent nothing.\n\n{source[:1600]}")
        concept=concept_for(source,S0)
        B=gen_local(f"Source:\n{source[:1600]}\n\nWrite a 3-4 sentence summary, but identify the CENTRAL TENSION and "
                    f"synthesize the competing considerations into a single coherent explanation. Faithful; invent nothing.")
        C=gen_local(f"Source:\n{source[:1600]}\n\nWrite a 3-4 sentence summary that identifies the central tension and "
                    f"synthesizes competing considerations, giving particular attention to '{concept}' where supported. "
                    f"Faithful; invent nothing.") if concept else B
        if not (S0 and B and C): print(f"skip gen: {title[:40]}"); continue
        trials.append((idx,title,source,S0,B,C,concept))
        print(f"\n[{idx}] {title[:48]} (concept='{concept}')")
        print(f"  A: {S0[:100]}...")
        print(f"  B: {B[:100]}...")
        print(f"  C: {C[:100]}...")

    def judge_one(source,S0,B,C,judge_call,is_api):
        labels=["A_BASELINE","B_SYNTH","C_SYNTH_CONCEPT"]; texts={"A_BASELINE":S0,"B_SYNTH":B,"C_SYNTH_CONCEPT":C}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(3))
        p=(f"Source article:\n{source[:1400]}\n\nThree summaries:\n\n{shown}\n\n"
           f"Score EACH 1-5: insight (revealed something non-obvious?), faith (true to source?), "
           f"action (rather read this than a plain summary?), trust (nothing invented?), keep (1 if you'd "
           f"turn it on in a product else 0). Reply EXACTLY:\n"
           f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\nSummary 2: ...\nSummary 3: ...")
        if is_api:
            out,_=judge_call(p)
        else:
            out=gen_local(p, model=judge_call, mt=160, temp=0.0)
        return parse_scores(out or "", order)

    api_scores=defaultdict(lambda: defaultdict(list)); api_resp=defaultdict(int); api_tot=defaultdict(int)
    loc_scores=defaultdict(lambda: defaultdict(list)); loc_resp=defaultdict(int); loc_tot=defaultdict(int)
    for idx,title,source,S0,B,C,concept in trials:
        for jn,jf in API_JUDGES.items():
            api_tot[jn]+=1
            r=judge_one(source,S0,B,C,jf,True)
            if r: api_resp[jn]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): api_scores[cond][m].append(v)
        for jm in LOCAL_JUDGES:
            loc_tot[jm]+=1
            r=judge_one(source,S0,B,C,jm,False)
            if r: loc_resp[jm]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): loc_scores[cond][m].append(v)

    def report(name, scores, resp, tot):
        print("\n"+"="*72); print(f"{name} PANEL"); print("="*72)
        print("  response rates: " + "  ".join(f"{k.split(':')[0]}={resp[k]}/{tot[k]}" for k in tot))
        conds=["A_BASELINE","B_SYNTH","C_SYNTH_CONCEPT"]; metrics=["insight","faith","action","trust","keep"]
        print(f"  {'condition':18s} " + " ".join(f"{m:>9s}" for m in metrics) + f" {'n':>4s}")
        tbl={}
        for cond in conds:
            row=[np.mean(scores[cond][m]) if scores[cond][m] else float('nan') for m in metrics]
            tbl[cond]=row; n=len(scores[cond]["insight"])
            print(f"  {cond:18s} " + " ".join(f"{x:>9.2f}" for x in row) + f" {n:>4d}")
        # verdict pieces
        if all(c in tbl for c in conds) and scores["A_BASELINE"]["insight"]:
            a,b,c=tbl["A_BASELINE"][0],tbl["B_SYNTH"][0],tbl["C_SYNTH_CONCEPT"][0]
            pooled=np.std([v for cc in conds for v in scores[cc]["insight"]]) or 1
            sg=(b-a)/pooled; cl=(c-b)/max(b,1e-6)*100
            fdrop=tbl["B_SYNTH"][1]-tbl["A_BASELINE"][1]; keep=tbl["B_SYNTH"][4]
            print(f"  -> SYNTH insight gain: {sg:+.2f}σ | faith drop: {fdrop:+.2f} | SYNTH keep: {keep:.2f} | CONCEPT lift: {cl:+.0f}%")
            return {"synth_gain":sg,"fdrop":fdrop,"keep":keep,"concept_lift":cl,"synth_gt_base":b>a}
        return None

    api_v=report("API", api_scores, api_resp, api_tot)
    loc_v=report("LOCAL", loc_scores, loc_resp, loc_tot)

    print("\n"+"="*72); print("CROSS-PANEL VERDICT"); print("="*72)
    if api_v and loc_v:
        print(f"  API:   SYNTH {'>' if api_v['synth_gt_base'] else '<='} BASELINE ({api_v['synth_gain']:+.2f}σ), keep {api_v['keep']:.2f}, concept {api_v['concept_lift']:+.0f}%")
        print(f"  LOCAL: SYNTH {'>' if loc_v['synth_gt_base'] else '<='} BASELINE ({loc_v['synth_gain']:+.2f}σ), keep {loc_v['keep']:.2f}, concept {loc_v['concept_lift']:+.0f}%")
        agree = api_v['synth_gt_base']==loc_v['synth_gt_base']
        print(f"\n  panels AGREE on SYNTH>BASELINE: {agree}")
        ship = api_v['synth_gain']>=0.5 and api_v['fdrop']>=-0.3 and api_v['keep']>=0.60 and api_v['synth_gt_base']
        if ship and agree and api_v['concept_lift']>=10:
            print("  -> SHIP w/ concept (discovery engine), ROBUST across panels, cheap-ops viable.")
        elif ship and agree:
            print("  -> SHIP concept-free (thoughtful-summary feature), ROBUST, cheap-ops viable (local agrees).")
        elif ship and not agree:
            print("  -> Real on strong judges but FRAGILE (local panel disagrees) — effect is judge-quality-dependent.")
        elif not api_v['synth_gt_base']:
            print("  -> Synthesis does NOT beat baseline even on strong judges. Stop productizing. Honest end.")
        else:
            print("  -> Marginal; doesn't clear pre-registered bar. Not yet a product. n small.")
    print("\n  (n small — this is the INSTRUMENT. The panels + agreement ARE the deliverable.)")

if __name__=="__main__":
    main()
