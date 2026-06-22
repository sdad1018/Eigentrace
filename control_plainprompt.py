#!/usr/bin/env python3
"""control_plainprompt.py -- ChatGPT's existential control.
Adds ONE arm: PLAIN_PLUS = the A+C discipline (restore reframing fact, read telling
absence, name open question, import nothing) with NO geometric inputs -- no channel-A
facts, no channel-C concepts. Isolates whether the SVD geometry contributes anything
the bare prompt discipline cannot. Same 5 judges, same 7 stories, directly comparable
to confront10_final's A+C numbers.

Arms: BASELINE / PLAIN_PLUS / A_PLUS_C  (drops A-only, C-only -- we have those)
"""
import os, sys, json, re, random
import numpy as np
from collections import defaultdict, Counter
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
import confront10_final as F   # reuse the validated pieces

K=int(os.getenv("KGEN","5"))
SMOKE=os.getenv("SMOKE","")=="1"
SYS=KV3.SYS; STORIES=KV3.STORIES
ALL_JUDGES=list(C.API_PATIENTS.keys())
SEEDQ="Summarize this in 3-4 sentences:\n\n"

# THE CONTROL PROMPT: A+C's discipline, ZERO geometric data.
# Identical closer to A+C so the ONLY difference is the absence of surfaced inputs.
PLAIN_PLUS=("Sharpen your summary. Restore the one source fact your draft dropped that most "
  "reframes the story, framed exactly as the source presents it. Then note where the source is "
  "conspicuously SILENT about something its own facts imply -- that silence is itself observable. "
  "Engage only what the source genuinely supports; name-check nothing the source does not; invent "
  "nothing; import no outside analogies or historical comparisons. Produce a sharper 3-4 sentence "
  "summary that (a) restores the reframing fact, (b) reads the telling absence where the source "
  "implies more than it states, and (c) names any genuinely unresolved question as a question. "
  "Stay strictly faithful to the source.")

def mt(p,m): return C.API_PATIENTS[p](m)

def main():
    stories=(STORIES[:1] if SMOKE else STORIES+[F.ADVERSARIAL])
    if SMOKE: print("*** SMOKE: 1 story ***",flush=True)
    print(f"K={K}  5 judges: {ALL_JUDGES}",flush=True)
    eng=F.build_engine(); ARMS=["BASELINE","PLAIN_PLUS","A_PLUS_C"]; all_results=[]
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72,flush=True)
        src=st["source"]; cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print("  consensus<3, skip"); continue
        facts,actors,concepts=F.derive_channels(src,cons,eng)
        print(f"  A facts:{facts}  C concepts:{concepts}",flush=True)
        pAC=F.prompt_AC(facts,actors,concepts)   # the validated geometry arm
        rows=[]
        for p in ALL_JUDGES:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
                    plain=mt(p,pre+[{"role":"user","content":PLAIN_PLUS}]) or base   # discipline, no geometry
                    ac=mt(p,pre+[{"role":"user","content":pAC}]) if pAC else base     # discipline + geometry
                    gens.append({"BASELINE":base,"PLAIN_PLUS":plain,"A_PLUS_C":ac})
                except Exception as e: print(f"    {p} gen{k} ERR {e}",flush=True)
            rows.append({"patient":p,"gens":gens}); print(f"  {p:<10} {len(gens)}/{K}",flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"source":src,"rows":rows})
        json.dump(all_results,open("control_plainprompt_results.json","w"),indent=2); print(f"  [saved {len(all_results)}]",flush=True)

    # blind panel -- reuse F's judge logic inline
    print("\n"+"="*72); print("BLIND PANEL (5 judges) -- does geometry beat bare discipline?"); print("="*72,flush=True)
    def judge(src,texts):
        order=[a for a in ARMS if texts.get(a)]; random.shuffle(order)
        if len(order)<2: return {}
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(order)))
        p=(f"Source text:\n{src[:1400]}\n\n{len(order)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
           f"(true to source, NOTHING inferred or imported beyond it), action, trust, keep (0/1). One line each:\n"
           f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(order)})")
        out={}
        for jn in ALL_JUDGES:
            try: o=C.API_PATIENTS[jn]([{"role":"user","content":p}])
            except Exception: o=""
            out[jn]=C.parse_scores(o or "", order)
        return out
    panel=defaultdict(lambda: defaultdict(list)); per_story=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for row in r["rows"]:
            for g in row["gens"]:
                for jn,conds in judge(r["source"],g).items():
                    for cond,d in conds.items():
                        for m,v in d.items():
                            panel[cond][m].append(v)
                            if m=="insight": per_story[r["story"]][cond].append(v)
    mets=["insight","faith","action","trust","keep"]
    print(f"  {'arm':12s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ARMS:
        if not panel[c]["insight"]: continue
        row=[np.mean(panel[c][m]) for m in mets]; tbl[c]=row
        print(f"  {c:12s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}",flush=True)
    if "PLAIN_PLUS" in tbl and "A_PLUS_C" in tbl:
        di=tbl["A_PLUS_C"][0]-tbl["PLAIN_PLUS"][0]
        print(f"\n  *** GEOMETRY CONTRIBUTION (A+C insight - PLAIN_PLUS insight) = {di:+.2f} ***")
        print(f"      if ~0: geometry is decorative, the discipline does the work (report it).")
        print(f"      if >0: surfaced concepts reach what the bare prompt cannot.")
    # per-story gradient: does geometry help most on the buried stories?
    print("\n  per-story  A+C - PLAIN_PLUS  insight delta (does geometry help most where text buries most?):")
    for st,arms in per_story.items():
        if arms.get("PLAIN_PLUS") and arms.get("A_PLUS_C"):
            d=np.mean(arms["A_PLUS_C"])-np.mean(arms["PLAIN_PLUS"])
            print(f"    {st:18s} {d:+.2f}")

    # sentence coding -- reuse F.code_sentences
    print("\n"+"="*72); print("SENTENCE CODING (does geometry change provenance vs bare discipline?)"); print("="*72,flush=True)
    coded=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for row in r["rows"]:
            g=row["gens"][0] if row["gens"] else None
            if not g: continue
            for arm in ARMS:
                if not g.get(arm): continue
                pr=F.code_sentences(r["source"],g[arm],ALL_JUDGES)
                if pr:
                    for k,v in pr.items(): coded[arm][k].append(v)
    print(f"  {'arm':12s}  {'Obs':>6s} {'Infer':>6s} {'Analogy':>8s} {'Spec':>6s}")
    for arm in ARMS:
        if not coded[arm]["O"]: continue
        o,i,a,s=(np.mean(coded[arm][k]) if coded[arm][k] else 0 for k in "OIAS")
        print(f"  {arm:12s}  {o:>6.2f} {i:>6.2f} {a:>8.2f} {s:>6.2f}",flush=True)
    json.dump({c:{m:panel[c][m] for m in mets} for c in ARMS if panel[c]['insight']},open("control_plainprompt_panel.json","w"),indent=2)
    print("\nwrote control_plainprompt_results.json + _panel.json")
    print("*** THE CONTROL: does the SVD geometry beat the bare prompt discipline? ***")
if __name__=="__main__": main()
