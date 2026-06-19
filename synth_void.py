#!/usr/bin/env python3
"""
synth_void.py — THE REAL COMBINATION, finally: the dramatic SUPPRESSED concept fed AS THE
SYNTHESIS TENSION-POLE (not as injection). + fakes + full text.

The correction (Sean caught my error): condition C last run scored -24% — but C injected
WEAK words (loss, damage, shelter — already-covered central terms) inside the synthesis
prompt. That's margarita-in-synthesis. We NEVER tested the actual suppressed concept (ww3-tier:
the thing all 5 models circle for 4 months and never say) AS the synthesis pole.

Two things are mechanistically different:
  INJECTION ("mention ww3")          -> noun to insert -> model nods, rephrases -> margarita.
  SYNTHESIS-POLE ("synthesize the     -> the SUPPRESSED antithesis to resolve -> may push the
    tension against ww3")                model past the EASY tension (B finds) into the HARD one.

So the donut must surface the DRAMATIC suppressed concept, not a generic central one.
Selection = high source-relevance AND high consensus-absence AND dramatic (rare/charged),
explicitly NOT the already-covered central term. Printed per story so we VERIFY it's ww3-tier.

CONDITIONS (geometry-free baseline + the real test):
  A_BASELINE     — normal summary
  B_SYNTH        — "find the central tension, synthesize" (the +0.85σ winner, finds EASY tension)
  E_SYNTH_VOID   — "synthesize the tension, specifically against [SUPPRESSED CONCEPT] — the
                   dimension the coverage circles but doesn't state" (the HARD tension)

Hypothesis: E > B on insight IF the suppressed pole pushes past the easy tension — AND we
must watch faithfulness (forcing a charged absent pole could induce drift/invention).

2-panel evaluator (works): qwen generates (excluded from judging); API(5)+local(3) blind.
+ 2 FAKES. FULL TEXT printed for eyeball read. API credits. Stream stopped.
"""
import json, os, sys, glob, re, random
import numpy as np, requests
from collections import defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO); sys.path.insert(0,REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN="qwen2.5:14b"
LOCAL_JUDGES=["mistral-small:latest","mistral:latest","nous-hermes2:latest"]
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

def gen_local(prompt, model=GEN, mt=320, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":model,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=180)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

def parse_scores(out, order):
    res={}
    for i in range(3):
        m=re.search(rf"Summary {i+1}:\s*insight=(\d+)\s*faith=(\d+)\s*action=(\d+)\s*trust=(\d+)\s*keep=([01])",out,re.I)
        if m:
            res[order[i]]={"insight":int(m.group(1)),"faith":int(m.group(2)),"action":int(m.group(3)),
                           "trust":int(m.group(4)),"keep":int(m.group(5))}; continue
        lm=re.search(rf"Summary {i+1}[:\s].*",out,re.I)
        if lm:
            ints=re.findall(r"\d+",lm.group(0))
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
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    API_JUDGES={n:pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in pa.BIG5_CALLERS}
    print(f"generator: {GEN}\nAPI panel: {list(API_JUDGES.keys())}\nlocal panel: {LOCAL_JUDGES}")

    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            sums=st.get("summaries",[])
            if sums: items.append(("FAKE", st.get("title","fake"), sums, " ".join(sums)[:2200]))
    except Exception as e: print(f"(fakes: {e})")
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]; nn=0
    for f in sorted(SEGS,reverse=True):
        if nn>=3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<500: continue
            items.append(("NEWS", t, list(sums.values()), a["source_body"][:2200])); nn+=1
        except: continue
    print(f"items: {[(k,t[:30]) for k,t,_,_ in items]}")

    def suppressed_concept(source, modelsums):
        """The DRAMATIC suppressed concept: high source-relevance, high consensus-absence,
        and charged/rare — explicitly NOT the central already-covered term."""
        Dv=E(source)[0]
        consensus=" ".join(modelsums); cv=E(consensus)[0]; cl=consensus.lower()
        # blend toward source (what the story is about) but we'll demand ABSENCE from consensus
        sims_src=(V16.astype(np.float32))@Dv
        sims_con=(V16.astype(np.float32))@cv
        cand=np.argsort(-sims_src)[:400]   # relevant to the SOURCE
        best=None; best_score=-1
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in cl: continue   # must be ABSENT from consensus text
            rel=float(sims_src[i]); con=float(sims_con[i])
            absence=rel-con                                   # relevant to source, far from consensus
            rarity=i/len(words)                               # later index = rarer = more charged
            # dramatic suppressed = relevant + absent-from-consensus + somewhat rare, and NOT trivially central
            if rel<0.55: continue                             # must be genuinely on-topic
            score=absence*0.6 + rarity*0.4
            if score>best_score:
                best_score=score; best=w
        return best

    trials=[]
    for kind,title,modelsums,source in items:
        A=gen_local(f"Summarize this news story in 3-4 sentences. Stay faithful; invent nothing.\n\n{source[:1600]}")
        B=gen_local(f"Source:\n{source[:1600]}\n\nWrite a 3-4 sentence summary, but identify the CENTRAL TENSION and "
                    f"synthesize the competing considerations into a single coherent explanation. Faithful; invent nothing.")
        sup=suppressed_concept(source, modelsums)
        if sup:
            E_txt=gen_local(f"Source:\n{source[:1600]}\n\nWrite a 3-4 sentence summary. Identify the central tension and "
                        f"synthesize it — paying SPECIFIC attention to the dimension of '{sup}', which the coverage "
                        f"circles around but tends not to state directly. Surface this tension ONLY if genuinely "
                        f"supported by the source; stay faithful and invent nothing.")
        else:
            E_txt=B
        if not (A and B and E_txt): print(f"skip: {title[:40]}"); continue
        trials.append((kind,title,source,A,B,E_txt,sup))
        print("\n"+"#"*74); print(f"### [{kind}] {title}"); print(f"### SUPPRESSED CONCEPT (donut): '{sup}'"); print("#"*74)
        print(f"\n┌─ A_BASELINE ──\n{A}")
        print(f"\n┌─ B_SYNTH (easy tension) ──\n{B}")
        print(f"\n┌─ E_SYNTH_VOID (suppressed pole = '{sup}') ──\n{E_txt}")

    def judge_one(source,A,B,Etx,call,is_api):
        labels=["A_BASELINE","B_SYNTH","E_SYNTH_VOID"]; texts={"A_BASELINE":A,"B_SYNTH":B,"E_SYNTH_VOID":Etx}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(3))
        p=(f"Source article:\n{source[:1400]}\n\nThree summaries:\n\n{shown}\n\n"
           f"Score EACH 1-5: insight (revealed something non-obvious?), faith (true to source, nothing inferred "
           f"beyond it?), action (rather read this than plain?), trust (nothing invented?), keep (1 if you'd turn "
           f"it on in a product else 0). Reply EXACTLY:\nSummary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n"
           f"Summary 2: ...\nSummary 3: ...")
        out=(call(p)[0] if is_api else gen_local(p,model=call,mt=160,temp=0.0)) or ""
        return parse_scores(out, order)

    api=defaultdict(lambda: defaultdict(list)); ar=defaultdict(int); at=defaultdict(int)
    loc=defaultdict(lambda: defaultdict(list)); lr=defaultdict(int); lt=defaultdict(int)
    for kind,title,source,A,B,Etx,sup in trials:
        for jn,jf in API_JUDGES.items():
            at[jn]+=1; r=judge_one(source,A,B,Etx,jf,True)
            if r: ar[jn]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): api[cond][m].append(v)
        for jm in LOCAL_JUDGES:
            lt[jm]+=1; r=judge_one(source,A,B,Etx,jm,False)
            if r: lr[jm]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): loc[cond][m].append(v)

    def report(name,scores,resp,tot):
        print("\n"+"="*72); print(f"{name} PANEL"); print("="*72)
        print("  resp: "+"  ".join(f"{k.split(':')[0]}={resp[k]}/{tot[k]}" for k in tot))
        conds=["A_BASELINE","B_SYNTH","E_SYNTH_VOID"]; mets=["insight","faith","action","trust","keep"]
        print(f"  {'cond':16s} "+" ".join(f"{m:>9s}" for m in mets)+f" {'n':>4s}")
        tbl={}
        for c in conds:
            row=[np.mean(scores[c][m]) if scores[c][m] else float('nan') for m in mets]; tbl[c]=row
            print(f"  {c:16s} "+" ".join(f"{x:>9.2f}" for x in row)+f" {len(scores[c]['insight']):>4d}")
        if all(c in tbl for c in conds) and scores["A_BASELINE"]["insight"]:
            a,b,e=tbl["A_BASELINE"][0],tbl["B_SYNTH"][0],tbl["E_SYNTH_VOID"][0]
            pooled=np.std([v for cc in conds for v in scores[cc]["insight"]]) or 1
            return {"b_gain":(b-a)/pooled,"e_gain":(e-a)/pooled,"e_over_b":(e-b)/pooled,
                    "b_fdrop":tbl["B_SYNTH"][1]-tbl["A_BASELINE"][1],"e_fdrop":tbl["E_SYNTH_VOID"][1]-tbl["A_BASELINE"][1],
                    "e_keep":tbl["E_SYNTH_VOID"][4]}
        return None

    av=report("API",api,ar,at); lv=report("LOCAL",loc,lr,lt)
    print("\n"+"="*72); print("VERDICT — does the SUPPRESSED concept as synthesis-pole beat plain synthesis?"); print("="*72)
    if av:
        print(f"  API:  B_SYNTH {av['b_gain']:+.2f}σ (faith {av['b_fdrop']:+.2f}) | E_SYNTH_VOID {av['e_gain']:+.2f}σ (faith {av['e_fdrop']:+.2f}) | E over B: {av['e_over_b']:+.2f}σ | E keep {av['e_keep']:.2f}")
    if lv:
        print(f"  LOCAL: B_SYNTH {lv['b_gain']:+.2f}σ (faith {lv['b_fdrop']:+.2f}) | E_SYNTH_VOID {lv['e_gain']:+.2f}σ (faith {lv['e_fdrop']:+.2f}) | E over B: {lv['e_over_b']:+.2f}σ")
    if av:
        print()
        if av['e_over_b']>=0.3 and av['e_fdrop']>=-0.3:
            print("  -> THE SUPPRESSED POLE WORKS: E beats plain synthesis on insight, faith holds.")
            print("     The donut word DOES belong — as the synthesis tension-pole, not as injection. Sean was right.")
        elif av['e_over_b']>=0.3 and av['e_fdrop']<-0.3:
            print("  -> E more insightful than B BUT costs faith (forcing the charged pole induces drift).")
            print("     Suppressed pole adds insight at a faithfulness price — tunable tradeoff.")
        elif abs(av['e_over_b'])<0.2:
            print("  -> E ≈ B: the suppressed pole adds nothing over plain synthesis. The PROMPT is the lever,")
            print("     the specific word still doesn't matter — even as a synthesis pole. Margarita confirmed deeper.")
        else:
            print("  -> E worse than B: forcing the suppressed pole HURT (over-constrained the synthesis). ")
        print(f"  (watch the FULL TEXT above: did E surface the dramatic tension, or bolt the word on?)")
    print("\n  (n small. Read the full text + the E-over-B number together.)")

if __name__=="__main__":
    main()
