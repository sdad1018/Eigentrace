#!/usr/bin/env python3
"""confront10_final.py v2 -- FIXED: A+C now uses the VALIDATED unified production prompt (not crude
concatenation that tanked faith). A_ONLY=facts-part only, C_ONLY=concepts-part only, A+C=full unified.
+ GOLD reference arm for Mexico (the hand-built ideal, scored blind) to anchor the numbers.
4 arms (+gold on mexico) x 5 judges x 7 stories x K=5. + per-model breakdown, hero capture, faith guard."""
import os, sys, json, re, random
import numpy as np
from collections import defaultdict, Counter
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
import exself as X
K=int(os.getenv("KGEN","5"))
SMOKE=os.getenv("SMOKE","")=="1"
# EX-SELF JUDGING (2026-09): judges == patients here. JUDGE_ONLY=1 re-judges the stored
# confront10_final_results.json (no generation), logs one record per score with its judge
# to confront10_final_panel_v2.json, and prints the all-judge and ex-self tables from ONE
# aggregation (exself.aggregate). SEED seeds the shuffles. EXSELF_SKIP=1 never calls a
# judge on its own vendor's text. SKIP_CODING=1 skips sentence coding + hero capture.
JUDGE_ONLY=os.getenv("JUDGE_ONLY","")=="1"
EXSELF_SKIP=os.getenv("EXSELF_SKIP","")=="1"
SKIP_CODING=os.getenv("SKIP_CODING","")=="1"
SEED=int(os.getenv("SEED","0"))
SYS=KV3.SYS
STORIES=KV3.STORIES
ALL_JUDGES=list(C.API_PATIENTS.keys())
ARMS=["BASELINE","A_ONLY","C_ONLY","A_PLUS_C"]
METS=["insight","faith","action","trust","keep"]
RESULTS_FILE="confront10_final_results.json"
PANEL_FILE="confront10_final_panel.json"
PANEL_V2_FILE="confront10_final_panel_v2.json"
SEEDQ="Summarize this in 3-4 sentences:\n\n"
ADVERSARIAL={"id":"rail_incident","shape":"Procedural (adversarial)",
  "source":("A freight train derailed early Tuesday near Millbrook Junction, the regional rail "
    "operator said. Fourteen of the train's sixty-two cars left the track at approximately 4:20 a.m.; "
    "three carried industrial lubricant, none of which was released. No injuries were reported. Local "
    "road crossings were closed for nine hours while crews re-railed the cars and inspected roughly 400 "
    "metres of track. The operator said a preliminary inspection identified a possible track-gauge "
    "irregularity at the derailment point but cautioned the cause remains under review and that a broken "
    "wheel-bearing and excessive speed had not been ruled out. Service resumed Tuesday evening.")}
# hand-built GOLD ideal for Mexico (the target 'what good looks like' -- anchors the numbers)
GOLD_MEXICO=("Mexico's government has stated that two US agents \u2014 reported to be CIA officers \u2014 killed in a "
  "vehicle crash after an anti-narcotics raid lacked authorization to operate on Mexican soil: one entered as a "
  "visitor, the other on a diplomatic passport, and Mexican authorities were never notified. The most load-bearing "
  "fact is the one the report states plainly but does not dwell on \u2014 the deaths themselves are now the object of "
  "President Sheinbaum's investigation, meaning the crash is being treated not as a closed accident but as an event "
  "requiring official account. What the source conspicuously leaves unstated is the machinery such operations "
  "normally run on: the local informants, consular cover, and inter-agency channels a sanctioned cross-border "
  "operation would involve \u2014 none of which is mentioned, which is itself the story, because their absence is what "
  "'unauthorized' concretely means. The unresolved tension is jurisdictional: two operatives died doing "
  "counter-narcotics work on foreign soil with no accredited status, leaving open whether this was a coordination "
  "failure or deliberate deniability \u2014 a question the source raises by omission and does not answer.")
def mt(p,m): return C.API_PATIENTS[p](m)
def build_engine():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t])); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    REL=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    return E,V,vt_words,REL,POOL,HARD
def derive_channels(src,summaries,eng):
    E,V,vt_words,REL,POOL,HARD=eng
    anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
    alltext=" ".join(summaries).lower(); srcl=src.lower(); type1=[]; type2=[]
    for i in top:
        w=vt_words[i]; s=float(sims[i])
        if len(w)<4 or w in HARD or s<REL: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl)); (type1 if in_src else type2).append(w)
    concepts=[]
    for w in type2:
        try:
            if not KV3.is_named_entity(w): concepts.append(w)
        except Exception: concepts.append(w)
    actors=KV3.ner_actors_dropped(src,summaries)
    return type1[:6], actors, concepts[:8]
# --- VALIDATED prompt pieces (from summary_plus_production build_prompt) ---
def part_A(facts,actors):
    bits=[f"'{w}'" for w in facts[:3]]+[f"'{n}'" for n,_ in actors[:2]]
    if not bits: return None
    return ("First, restore these source facts your summary dropped, framed exactly as the source presents "
            "them (no added characterization): "+", ".join(bits)+".")
def part_C(concepts):
    if not concepts: return None
    return (f"Then sharpen the summary by surfacing the latent stakes the source implies but your draft left "
            f"out. These conceptual directions may be relevant: {', '.join(concepts)}. Treat them as DIRECTIONS, "
            f"not words to insert. For each, the most valuable move is often to note where the source is "
            f"conspicuously SILENT about something its own facts imply \u2014 that silence is itself observable. "
            f"Engage only what the source genuinely supports; name-check nothing; invent nothing; do not import "
            f"outside analogies or historical comparisons.")
CLOSER=("Produce a sharper 3-4 sentence summary that (a) restores the reframing fact, (b) reads the telling "
        "absence where the source implies more than it states, and (c) names any genuinely unresolved question "
        "as a question. Stay strictly faithful to the source.")
def prompt_A_only(facts,actors):
    a=part_A(facts,actors)
    return (a+" "+CLOSER) if a else None
def prompt_C_only(concepts):
    c=part_C(concepts)
    return (c+" "+CLOSER) if c else None
def prompt_AC(facts,actors,concepts):  # the VALIDATED unified prompt
    parts=[p for p in [part_A(facts,actors), part_C(concepts)] if p]
    parts.append(CLOSER)
    return " ".join(parts) if len(parts)>1 else None
def code_sentences(src,summary,judges,author=None):
    """O/I/A/S sentence coding. `author` = the model that wrote `summary`; judges of the
    author's vendor are skipped so no model codes its own text (author None -> all judges)."""
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', re.sub(r'#.*?\n','',summary)) if len(s.strip())>15]
    if not sents: return None
    numbered="\n".join(f"{i+1}. {s}" for i,s in enumerate(sents))
    p=(f"SOURCE:\n{src[:1300]}\n\nSummary sentences:\n{numbered}\n\nClassify EACH sentence by content origin "
       f"RELATIVE TO SOURCE:\n O=Observation(in source) I=Inference(grounded reasoning beyond source) "
       f"A=Analogy(imported outside frame) S=Speculation(no support)\nReply one line each:\n1: <O/I/A/S>\n... through {len(sents)}")
    agg=Counter(); tot=0
    for jn in X.judges_for(author,judges):
        try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}]) or ""
        except Exception: out=""
        for m in re.finditer(r'^\s*\d+\s*[:.]?\s*([OIAS])\b', out, re.M|re.I): agg[m.group(1).upper()]+=1; tot+=1
    if tot==0: return None
    return {k:agg.get(k,0)/tot for k in "OIAS"}
def judge(src,texts,author=None,judges=None,skip_self=None,story=None,gen=None,records=None):
    """Blind panel on one item (arms shuffled; GOLD included where present).
    author: the patient that wrote the non-GOLD arms (GOLD is hand-built, author None).
    skip_self True -> judges of the author's vendor are not called (default env EXSELF_SKIP);
    otherwise every judge is called and the split happens in exself.aggregate.
    records: list extended with one per-score record per parsed (arm, metric)."""
    if skip_self is None: skip_self=EXSELF_SKIP
    arms=[a for a in ARMS+["GOLD"] if texts.get(a)]; order=list(arms); random.shuffle(order)
    if len(order)<2: return {}
    shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(order)))
    p=(f"Source text:\n{src[:1400]}\n\n{len(order)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
       f"(true to source, NOTHING inferred or imported beyond it), action, trust, keep (0/1). One line each:\n"
       f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(order)})")
    js=list(judges if judges is not None else ALL_JUDGES)
    if skip_self: js=X.judges_for(author,js)
    out_by_judge={}
    for jn in js:
        try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
        except Exception: out=""
        out_by_judge[jn]=C.parse_scores(out or "", order)
        if records is not None:
            records.extend(X.make_records(story,author,gen,jn,out_by_judge[jn],order,arm_author={"GOLD":None}))
    return out_by_judge
def load_results(path=RESULTS_FILE):
    with open(path) as fh: return json.load(fh)
def main():
    random.seed(SEED)
    all_results=[]
    if JUDGE_ONLY:
        all_results=load_results()
        if SMOKE: all_results=all_results[:1]; print("*** SMOKE: 1 story ***",flush=True)
        print(f"JUDGE_ONLY=1: re-judging {sum(len(row['gens']) for r in all_results for row in r['rows'])} stored items from {RESULTS_FILE}; SEED={SEED}; EXSELF_SKIP={EXSELF_SKIP}",flush=True)
        stories=[]
    else:
        stories=(STORIES[:1] if SMOKE else STORIES+[ADVERSARIAL])
        if SMOKE: print("*** SMOKE: 1 story ***",flush=True)
        print(f"K={K}  5 judges: {ALL_JUDGES}  (JUDGES == PATIENTS; self rows logged, dropped in the ex-self view)",flush=True)
        eng=build_engine()
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72,flush=True)
        src=st["source"]; cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print("  consensus<3, skip"); continue
        facts,actors,concepts=derive_channels(src,cons,eng)
        print(f"  A facts:{facts} actors:{[n for n,_ in actors]}"); print(f"  C concepts:{concepts}",flush=True)
        pA=prompt_A_only(facts,actors); pC=prompt_C_only(concepts); pAC=prompt_AC(facts,actors,concepts)
        gold = GOLD_MEXICO if st["id"]=="mexico_cia" else None
        rows=[]
        for p in ALL_JUDGES:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
                    ao=mt(p,pre+[{"role":"user","content":pA}]) if pA else base
                    co=mt(p,pre+[{"role":"user","content":pC}]) if pC else base
                    ac=mt(p,pre+[{"role":"user","content":pAC}]) if pAC else base
                    g={"BASELINE":base,"A_ONLY":ao,"C_ONLY":co,"A_PLUS_C":ac}
                    if gold: g["GOLD"]=gold
                    gens.append(g)
                except Exception as e: print(f"    {p} gen{k} ERR {e}",flush=True)
            rows.append({"patient":p,"gens":gens}); print(f"  {p:<10} {len(gens)}/{K}",flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"facts":facts,"concepts":concepts,"source":src,"rows":rows,"has_gold":gold is not None})
        json.dump(all_results,open(RESULTS_FILE,"w"),indent=2); print(f"  [saved {len(all_results)}]",flush=True)
    print("\n"+"="*72); print("BLIND PANEL (5 judges, shuffled; GOLD included where present)"); print("="*72,flush=True)
    records=[]
    panel=defaultdict(lambda: defaultdict(list)); per_judge=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    per_story_faith=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for row in r["rows"]:
            for gi,g in enumerate(row["gens"]):
                jd=judge(r["source"],g,author=row["patient"],story=r["story"],gen=gi,records=records)
                for jn,conds in jd.items():
                    for cond,d in conds.items():
                        for m,v in d.items():
                            panel[cond][m].append(v); per_judge[jn][cond][m].append(v)
                            if m=="faith": per_story_faith[r["story"]][cond].append(v)
    mets=METS; ALLARMS=ARMS+["GOLD"]
    # BOTH tables from one aggregation (exself.aggregate) over the same records
    agg_all=X.aggregate(records,exclude_self=False,metrics=mets); agg_ex=X.aggregate(records,exclude_self=True,metrics=mets)
    print(X.format_table(agg_all,ALLARMS,mets,label="ALL-JUDGE (self-included, legacy design)"))
    print(X.format_table(agg_ex,ALLARMS,mets,label="EX-SELF (judges never score their own vendor's text)"))
    spj=X.self_pref_by_judge(records,"insight")
    print("\n  self-preference per judge (insight: own score - ex-self received):")
    for jn,row in spj.items():
        sp=row["self_pref"]; print(f"    {jn:10s} n_self={row['n_self']:3d} n_exself={row['n_exself']:3d} self_pref={('%+.2f'%sp) if sp is not None else '-'}")
    print("\n  legacy view (flat arrays, self-included):")
    print(f"  {'arm':12s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ALLARMS:
        if not panel[c]["insight"]: continue
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:12s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}",flush=True)
    if all(panel[c]["insight"] for c in ARMS):
        print(f"\n  *** HEADLINE (vs baseline) ***")
        for c in ["A_ONLY","C_ONLY","A_PLUS_C"]:
            print(f"  {c:10s}  insight {tbl[c][0]-tbl['BASELINE'][0]:+.2f}  faith {tbl[c][1]-tbl['BASELINE'][1]:+.2f}  keep {tbl[c][4]-tbl['BASELINE'][4]:+.2f}")
        if "GOLD" in tbl:
            print(f"\n  *** vs GOLD CEILING (mexico) ***  A+C insight {tbl['A_PLUS_C'][0]:.2f} vs GOLD {tbl['GOLD'][0]:.2f} | A+C faith {tbl['A_PLUS_C'][1]:.2f} vs GOLD {tbl['GOLD'][1]:.2f}")
    print("\n"+"="*72); print("PER-MODEL BREAKDOWN (insight by judge x arm)"); print("="*72,flush=True)
    print(f"  {'judge':10s} "+" ".join(f"{a:>10s}" for a in ARMS))
    for jn in ALL_JUDGES:
        cells=[np.mean(per_judge[jn][a]["insight"]) if per_judge[jn][a]["insight"] else float('nan') for a in ARMS]
        print(f"  {jn:10s} "+" ".join(f"{x:>10.2f}" for x in cells),flush=True)
    print("\n"+"="*72); print("FAITH-REGRESSION GUARD"); print("="*72,flush=True)
    any_reg=False
    for story,arms in per_story_faith.items():
        bf=np.mean(arms.get("BASELINE",[0])) if arms.get("BASELINE") else None
        if bf is None: continue
        for arm in ["A_ONLY","C_ONLY","A_PLUS_C"]:
            if arms.get(arm):
                af=np.mean(arms[arm])
                if af<bf-0.25:
                    print(f"  \u26a0\ufe0f FAITH REGRESSION  {story:14s} {arm}: {af:.2f} vs baseline {bf:.2f} (drop {bf-af:.2f})"); any_reg=True
    if not any_reg: print("  \u2713 no faith regression")
    print("\n"+"="*72); print("SENTENCE CODING per arm (gold: hi Infer, ~0 Analogy)"); print("="*72,flush=True)
    coded=defaultdict(lambda: defaultdict(list))
    for r in ([] if SKIP_CODING else all_results):
        for row in r["rows"]:
            g=row["gens"][0] if row["gens"] else None
            if not g: continue
            for arm in ALLARMS:
                if not g.get(arm): continue
                pr=code_sentences(r["source"],g[arm],ALL_JUDGES,author=(None if arm=="GOLD" else row["patient"]))
                if pr:
                    for k,v in pr.items(): coded[arm][k].append(v)
    print(f"  {'arm':12s}  {'Obs':>6s} {'Infer':>6s} {'Analogy':>8s} {'Spec':>6s}")
    for arm in ALLARMS:
        if not coded[arm]["O"]: continue
        o,i,a,s=(np.mean(coded[arm][k]) if coded[arm][k] else 0 for k in "OIAS")
        flag="<- gold-like" if (a<0.06 and i>0.30) else ("<- analogy/spec high" if a+s>0.20 else "")
        print(f"  {arm:12s}  {o:>6.2f} {i:>6.2f} {a:>8.2f} {s:>6.2f}   {flag}",flush=True)
    print("\n"+"="*72); print("GOLD SELF-CHECK + HERO CAPTURE"); print("="*72,flush=True)
    heroes={}; gl=0; tot=0
    for r in ([] if SKIP_CODING else all_results):
        best=None; best_i=-1
        for row in r["rows"]:
            for g in row["gens"]:
                if not g.get("A_PLUS_C"): continue
                pr=code_sentences(r["source"],g["A_PLUS_C"],ALL_JUDGES[:3],author=row["patient"])   # 3 -> 2 after the author's vendor is skipped
                if pr:
                    tot+=1
                    if pr["A"]<0.06 and pr["I"]>0.30: gl+=1
                    score=pr["I"]-pr["A"]-pr["S"]
                    if score>best_i: best_i=score; best={"patient":row["patient"],"text":g["A_PLUS_C"],"profile":pr}
        if best: heroes[r["story"]]=best
    if tot: print(f"  A+C gold-like: {gl}/{tot} = {gl/tot:.0%}")
    v2={"design":{"judges":ALL_JUDGES,"patients":ALL_JUDGES,"judges_are_patients":True,"judge_only":JUDGE_ONLY,"seed":SEED,
                  "exself_skip":EXSELF_SKIP,"results_file":RESULTS_FILE,"exself_helper_sha":X.helper_sha(),
                  "note":"all-judge and ex-self tables come from exself.aggregate over the same records; GOLD is hand-built (author None, never self-judged)"},
        "records":records,
        "summary":{"self_included":agg_all,"exself":agg_ex,"n_self_included":{a:agg_all[a]["n"] for a in agg_all},
                   "n_exself":{a:agg_ex[a]["n"] for a in agg_ex},"self_pref_by_judge":spj,
                   "parse_rate_by_judge":X.parse_rate_by_judge(records)},
        "flat_panel":X.flat_panel(records),"flat_panel_exself":X.flat_panel(records,exclude_self=True),
        "coding":{a:{k:coded[a][k] for k in 'OIAS'} for a in ALLARMS if coded[a]['O']}}
    json.dump(v2,open(PANEL_V2_FILE,"w"),indent=1)
    if JUDGE_ONLY:
        print(f"\nwrote {PANEL_V2_FILE} (JUDGE_ONLY: {RESULTS_FILE}, {PANEL_FILE} and heroes untouched)")
    else:
        json.dump(heroes,open("confront10_final_heroes.json","w"),indent=2)
        print(f"  wrote heroes ({len(heroes)})")
        json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in ALLARMS if panel[c]['insight']},"per_judge":{jn:{a:{m:per_judge[jn][a][m] for m in mets} for a in ARMS} for jn in ALL_JUDGES},"coding":{a:{k:coded[a][k] for k in 'OIAS'} for a in ALLARMS if coded[a]['O']}},open(PANEL_FILE,"w"),indent=2)
        print(f"\nwrote results+panel+heroes+{PANEL_V2_FILE}. *** A+C now uses VALIDATED prompt + GOLD anchor. THIS IS THE PAGE. ***")
if __name__=="__main__": main()
