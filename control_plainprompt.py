#!/usr/bin/env python3
"""control_plainprompt.py -- ChatGPT's existential control.
Adds ONE arm: PLAIN_PLUS = the A+C discipline (restore reframing fact, read telling
absence, name open question, import nothing) with NO geometric inputs -- no channel-A
facts, no channel-C concepts. Isolates whether the SVD geometry contributes anything
the bare prompt discipline cannot. Same 5 judges, same 7 stories, directly comparable
to confront10_final's A+C numbers.

Arms: BASELINE / PLAIN_PLUS / A_PLUS_C  (drops A-only, C-only -- we have those)

EX-SELF JUDGING (2026-09):
  The judges ARE the patients (ALL_JUDGES == C.API_PATIENTS), so ~1/5 of every score
  in the published 788-per-arm panel is a model grading its own text, and the stored
  control_plainprompt_panel.json has no (story,patient,gen,judge) mapping to split it.
  This version logs one record per score {story, patient, gen, judge, arm, metric,
  score, order, self_judged} to control_plainprompt_panel_v2.json and prints BOTH the
  all-judge table and the ex-self table from ONE aggregation function
  (exself.aggregate), so the null is the same code path.

  JUDGE_ONLY=1   re-judge the stored control_plainprompt_results.json (175 items),
                 no generation calls; never overwrites _results.json or _panel.json.
  SEED=<int>     seeds random.shuffle so a re-judge is reproducible (default 0).
  EXSELF_SKIP=1  do not even call a judge on its own vendor's text (saves 1/5 of the
                 calls; the all-judge table then equals the ex-self table).
  SKIP_CODING=1  skip the O/I/A/S sentence coding pass.
"""
import os, sys, json, re, random
import numpy as np
from collections import defaultdict, Counter
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
import confront10_final as F   # reuse the validated pieces
import exself as X

K=int(os.getenv("KGEN","5"))
SMOKE=os.getenv("SMOKE","")=="1"
JUDGE_ONLY=os.getenv("JUDGE_ONLY","")=="1"
EXSELF_SKIP=os.getenv("EXSELF_SKIP","")=="1"
SKIP_CODING=os.getenv("SKIP_CODING","")=="1"
SEED=int(os.getenv("SEED","0"))
SYS=KV3.SYS; STORIES=KV3.STORIES
ALL_JUDGES=list(C.API_PATIENTS.keys())
SEEDQ="Summarize this in 3-4 sentences:\n\n"
ARMS=["BASELINE","PLAIN_PLUS","A_PLUS_C"]
METS=["insight","faith","action","trust","keep"]
RESULTS_FILE="control_plainprompt_results.json"
PANEL_FILE="control_plainprompt_panel.json"          # legacy flat arrays (published 788 run)
PANEL_V2_FILE="control_plainprompt_panel_v2.json"    # per-score records + both tables

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

def judge(src,texts,author=None,judges=None,skip_self=None,story=None,gen=None,records=None):
    """Blind panel on one item. Returns {judge: parse_scores dict}.

    author   the patient that wrote `texts` (needed to mark self-judged scores)
    judges   judge list (default ALL_JUDGES)
    skip_self  True -> judges of the author's vendor are not called at all
               (default: env EXSELF_SKIP); False -> all judges are called and the
               self/ex-self split happens in exself.aggregate at aggregation time.
    records  list to extend with one per-score record per parsed (arm,metric).
    """
    if skip_self is None: skip_self=EXSELF_SKIP
    order=[a for a in ARMS if texts.get(a)]; random.shuffle(order)
    if len(order)<2: return {}
    shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(order)))
    p=(f"Source text:\n{src[:1400]}\n\n{len(order)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
       f"(true to source, NOTHING inferred or imported beyond it), action, trust, keep (0/1). One line each:\n"
       f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(order)})")
    js=list(judges if judges is not None else ALL_JUDGES)
    if skip_self: js=X.judges_for(author,js)
    out={}
    for jn in js:
        try: o=C.API_PATIENTS[jn]([{"role":"user","content":p}])
        except Exception: o=""
        out[jn]=C.parse_scores(o or "", order)
        if records is not None:
            records.extend(X.make_records(story,author,gen,jn,out[jn],order))
    return out

def load_results(path=RESULTS_FILE):
    """JUDGE_ONLY path: the stored 7 stories x 5 patients x 5 gens = 175 items with texts."""
    with open(path) as fh: return json.load(fh)

def generate(stories):
    """Generation pass (API). Writes control_plainprompt_results.json as before."""
    eng=F.build_engine(); all_results=[]
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
        json.dump(all_results,open(RESULTS_FILE,"w"),indent=2); print(f"  [saved {len(all_results)}]",flush=True)
    return all_results

def run_panel(all_results,skip_self=None):
    """Judge every stored item; returns the per-score record list."""
    records=[]
    for r in all_results:
        for row in r["rows"]:
            for gi,g in enumerate(row["gens"]):
                judge(r["source"],g,author=row["patient"],skip_self=skip_self,
                      story=r["story"],gen=gi,records=records)
    return records

def summarize(records):
    """Both tables from ONE code path (exself.aggregate) + self_pref per judge."""
    allj=X.aggregate(records,exclude_self=False,metrics=METS)
    exs=X.aggregate(records,exclude_self=True,metrics=METS)
    summary={
        "self_included":allj,"exself":exs,
        "n_self_included":{a:allj[a]["n"] for a in allj},"n_exself":{a:exs[a]["n"] for a in exs},
        "self_pref_by_judge":X.self_pref_by_judge(records,"insight"),
        "parse_rate_by_judge":X.parse_rate_by_judge(records),
    }
    for view,agg in (("self_included",allj),("exself",exs)):
        if "PLAIN_PLUS" in agg and "A_PLUS_C" in agg and agg["PLAIN_PLUS"]["insight"] is not None and agg["A_PLUS_C"]["insight"] is not None:
            summary[f"delta_{view}"]=agg["A_PLUS_C"]["insight"]-agg["PLAIN_PLUS"]["insight"]
    return summary

def print_report(records,summary):
    print(f"  design: judges == patients ({ALL_JUDGES}); self rows are logged and dropped at aggregation in the ex-self view")
    print(X.format_table(summary["self_included"],ARMS,METS,label="ALL-JUDGE (self-included, legacy design)"))
    print(X.format_table(summary["exself"],ARMS,METS,label="EX-SELF (judges never score their own vendor's text)"))
    for view,lab in (("self_included","self-incl"),("exself","ex-self")):
        d=summary.get(f"delta_{view}")
        if d is not None:
            print(f"\n  *** GEOMETRY CONTRIBUTION [{lab}] (A+C insight - PLAIN_PLUS insight) = {d:+.2f} ***")
    print(f"      if ~0: geometry is decorative, the discipline does the work (report it).")
    print(f"      if >0: surfaced concepts reach what the bare prompt cannot.")
    print("\n  self-preference per judge (insight: own score - ex-self received; sp_page.py pattern):")
    for j,row in summary["self_pref_by_judge"].items():
        sp=row["self_pref"]; sm=row["self_mean"]; em=row["exself_received_mean"]
        print(f"    {j:10s} self={('%.2f'%sm) if sm is not None else '-':>5s} (n={row['n_self']:3d})  ex-self received={('%.2f'%em) if em is not None else '-':>5s} (n={row['n_exself']:3d})  self_pref={('%+.2f'%sp) if sp is not None else '-'}")
    print("\n  parse rate per judge (cells parsed / items attempted):")
    for j,row in summary["parse_rate_by_judge"].items():
        print(f"    {j:10s} {row}")
    # per-story gradient: does geometry help most on the buried stories?
    print("\n  per-story  A+C - PLAIN_PLUS  insight delta (ex-self | self-incl):")
    per_story=defaultdict(lambda: defaultdict(list))
    for r in records:
        if r.get("metric")=="insight" and r.get("score") is not None:
            per_story[r["story"]][(r["arm"],bool(r["self_judged"]))].append(float(r["score"]))
    for st,cells in per_story.items():
        ex_ac=cells.get(("A_PLUS_C",False),[]); ex_pp=cells.get(("PLAIN_PLUS",False),[])
        al_ac=ex_ac+cells.get(("A_PLUS_C",True),[]); al_pp=ex_pp+cells.get(("PLAIN_PLUS",True),[])
        if ex_ac and ex_pp and al_ac and al_pp:
            print(f"    {st:18s} {np.mean(ex_ac)-np.mean(ex_pp):+.2f} | {np.mean(al_ac)-np.mean(al_pp):+.2f}")

def main():
    random.seed(SEED)
    if JUDGE_ONLY:
        all_results=load_results()
        if SMOKE: all_results=all_results[:1]; print("*** SMOKE: 1 story ***",flush=True)
        print(f"JUDGE_ONLY=1: re-judging {sum(len(row['gens']) for r in all_results for row in r['rows'])} stored items from {RESULTS_FILE}; SEED={SEED}; EXSELF_SKIP={EXSELF_SKIP}",flush=True)
    else:
        stories=(STORIES[:1] if SMOKE else STORIES+[F.ADVERSARIAL])
        if SMOKE: print("*** SMOKE: 1 story ***",flush=True)
        print(f"K={K}  5 judges: {ALL_JUDGES}",flush=True)
        all_results=generate(stories)

    # blind panel -- same prompt as the published run; every score logged with its judge
    print("\n"+"="*72); print("BLIND PANEL (5 judges) -- does geometry beat bare discipline?"); print("="*72,flush=True)
    records=run_panel(all_results)
    summary=summarize(records)
    print_report(records,summary)

    # sentence coding -- reuse F.code_sentences (judges of the author's vendor skipped)
    coded=defaultdict(lambda: defaultdict(list))
    if not SKIP_CODING:
        print("\n"+"="*72); print("SENTENCE CODING (does geometry change provenance vs bare discipline?)"); print("="*72,flush=True)
        for r in all_results:
            for row in r["rows"]:
                g=row["gens"][0] if row["gens"] else None
                if not g: continue
                for arm in ARMS:
                    if not g.get(arm): continue
                    pr=F.code_sentences(r["source"],g[arm],ALL_JUDGES,author=row["patient"])
                    if pr:
                        for k,v in pr.items(): coded[arm][k].append(v)
        print(f"  {'arm':12s}  {'Obs':>6s} {'Infer':>6s} {'Analogy':>8s} {'Spec':>6s}")
        for arm in ARMS:
            if not coded[arm]["O"]: continue
            o,i,a,s=(np.mean(coded[arm][k]) if coded[arm][k] else 0 for k in "OIAS")
            print(f"  {arm:12s}  {o:>6.2f} {i:>6.2f} {a:>8.2f} {s:>6.2f}",flush=True)

    v2={"design":{"judges":ALL_JUDGES,"patients":ALL_JUDGES,"judges_are_patients":True,
                  "judge_only":JUDGE_ONLY,"seed":SEED,"exself_skip":EXSELF_SKIP,
                  "results_file":RESULTS_FILE,"exself_helper_sha":X.helper_sha(),
                  "note":"all-judge and ex-self tables come from exself.aggregate over the same records; ex-self drops records with self_judged=True (judge vendor == author vendor)"},
        "records":records,"summary":summary,
        "flat_panel":X.flat_panel(records),"flat_panel_exself":X.flat_panel(records,exclude_self=True),
        "coding":{a:{k:coded[a][k] for k in "OIAS"} for a in ARMS if coded[a]["O"]}}
    json.dump(v2,open(PANEL_V2_FILE,"w"),indent=1)
    if not JUDGE_ONLY:
        # legacy flat view, only when this run generated its own texts (never in a re-judge)
        json.dump({c:{m:v2["flat_panel"][c][m] for m in METS} for c in ARMS if v2["flat_panel"].get(c,{}).get("insight")},open(PANEL_FILE,"w"),indent=2)
        print(f"\nwrote {RESULTS_FILE} + {PANEL_FILE} + {PANEL_V2_FILE}")
    else:
        print(f"\nwrote {PANEL_V2_FILE} (JUDGE_ONLY: {RESULTS_FILE} and {PANEL_FILE} untouched)")
    print("*** THE CONTROL: does the SVD geometry beat the bare prompt discipline? ***")
if __name__=="__main__": main()
