#!/usr/bin/env python3
"""suppression_abc.py -- THE robustness test. Does the externalized analytical operator
survive when the MODEL's analytical cognition is suppressed?

A -- open model + analytical prompt (think freely)         -> baseline recall of analytical targets
B -- SUPPRESSED model (facts-only, no inference) + task    -> does analytical structure survive suppression?
C -- SUPPRESSED model + geometry's concepts handed over    -> does recall recover despite suppression?

Predictions:
  geometry decorative:        A ~= B ~= C        (suppression doesn't matter, or geometry doesn't help)
  operator externalized:      B drops, C holds   (geometry rescues suppressed cognition)
  partially externalized:     B drops, C drops less

Recall measured on the SPIRAL concepts (analytical targets), bge cosine, same as throughout.
Uses 5 API judges as the models-under-suppression; recall scored geometrically."""
import os, sys, json, re, random
import numpy as np
from collections import defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
from geometric_engine import get_engine
eng=get_engine()
def E(t):
    v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
    return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

K=int(os.getenv("KGEN","3"))
SMOKE=os.getenv("SMOKE","")=="1"
THRESH=0.55
ALL_MODELS=list(C.API_PATIENTS.keys())
SPIRAL=json.load(open("spiral_concepts.json"))   # the analytical targets + sources
spiral_by_story={o["story"]:o for o in SPIRAL}

# --- the three conditions, as system+user prompt pairs ---
OPEN_SYS=KV3.SYS
SUPPRESS_SYS=("You are a strict factual summarizer. Report ONLY facts explicitly stated in the source. "
  "Do NOT infer anything. Do NOT note what the source omits or leaves unsaid. Do NOT raise questions. "
  "Do NOT add context, background, or interpretation. Do NOT speculate about implications. "
  "State only what is literally written, in plain declarative sentences. Nothing more.")

SEEDQ="Summarize this in 3-4 sentences:\n\n"
ANALYTIC=("Now sharpen it: restore the source fact you dropped that most reframes the story, note where "
  "the source is conspicuously silent about something its own facts imply, and name the unresolved "
  "question. Import nothing the source does not contain.")
def GEOM_HANDOFF(concepts):
    return ("Here are concepts structurally adjacent to this source that your summary did not surface: "
      f"{', '.join(concepts)}. For any that the source's own facts genuinely imply, note where the source "
      "is silent about it. Do not name-check concepts the source does not support; import nothing external.")

def mt(p,msgs): return C.API_PATIENTS[p](msgs)

def recall(concepts, text):
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip())>8]
    if not sents or not concepts: return None
    sv=E(sents); hits=0
    for c in concepts:
        cv=E([c])[0]
        if float(np.max(sv@cv))>=THRESH: hits+=1
    return hits/len(concepts)

def main():
    stories=(SPIRAL[:1] if SMOKE else SPIRAL)
    if SMOKE: print("*** SMOKE: 1 story ***",flush=True)
    print(f"K={K}  models: {ALL_MODELS}  threshold={THRESH}",flush=True)
    print("recall of analytical targets (spiral concepts) under three conditions:\n")
    cond_recall=defaultdict(list)         # condition -> [recall per (model,story,k)]
    per_model=defaultdict(lambda: defaultdict(list))
    rows=[]
    for o in stories:
        story=o["story"]; src=o["source"]; concepts=o["spiral"]
        if not concepts: continue
        print(f"=== {story} ===  targets: {concepts}",flush=True)
        for p in ALL_MODELS:
            rA=[]; rB=[]; rC=[]
            for k in range(K):
                try:
                    # A: open model, analytical prompt
                    a_base=mt(p,[{"role":"system","content":OPEN_SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    a_full=mt(p,[{"role":"system","content":OPEN_SYS},{"role":"user","content":SEEDQ+src[:1700]},
                                 {"role":"assistant","content":a_base},{"role":"user","content":ANALYTIC}]) or a_base
                    # B: suppressed model, same analytical ASK (but system forbids it)
                    b_base=mt(p,[{"role":"system","content":SUPPRESS_SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    b_full=mt(p,[{"role":"system","content":SUPPRESS_SYS},{"role":"user","content":SEEDQ+src[:1700]},
                                 {"role":"assistant","content":b_base},{"role":"user","content":ANALYTIC}]) or b_base
                    # C: suppressed model, but handed the geometry's concepts
                    c_full=mt(p,[{"role":"system","content":SUPPRESS_SYS},{"role":"user","content":SEEDQ+src[:1700]},
                                 {"role":"assistant","content":b_base},{"role":"user","content":GEOM_HANDOFF(concepts)}]) or b_base
                    ra=recall(concepts,a_full); rb=recall(concepts,b_full); rc=recall(concepts,c_full)
                    if ra is not None: rA.append(ra); cond_recall["A_open"].append(ra); per_model[p]["A_open"].append(ra)
                    if rb is not None: rB.append(rb); cond_recall["B_suppressed"].append(rb); per_model[p]["B_suppressed"].append(rb)
                    if rc is not None: rC.append(rc); cond_recall["C_supp_geom"].append(rc); per_model[p]["C_supp_geom"].append(rc)
                except Exception as e: print(f"    {p} k{k} ERR {e}",flush=True)
            print(f"   {p:<10} A={np.mean(rA) if rA else 0:.2f}  B={np.mean(rB) if rB else 0:.2f}  C={np.mean(rC) if rC else 0:.2f}",flush=True)
            rows.append({"story":story,"model":p,"A":rA,"B":rB,"C":rC})
        json.dump(rows,open("suppression_abc_results.json","w"),indent=2)
        print()
    print("="*64)
    A=np.mean(cond_recall["A_open"]); B=np.mean(cond_recall["B_suppressed"]); Cc=np.mean(cond_recall["C_supp_geom"])
    print(f"OVERALL analytical-target recall:")
    print(f"   A (open + think)            : {A:.0%}")
    print(f"   B (suppressed, facts-only)  : {B:.0%}   drop from A: {A-B:+.0%}")
    print(f"   C (suppressed + geometry)   : {Cc:.0%}   recovery over B: {Cc-B:+.0%}")
    print(f"\n   INTERPRETATION:")
    print(f"   if B~=A: suppression didn't bite -- need a stronger suppression prompt")
    print(f"   if B drops and C recovers toward A: the externalized operator SURVIVES suppression")
    print(f"      (geometry rescued the analytical structure the suppressed model refused)")
    print(f"   if B drops and C stays low: geometry does NOT rescue -- operator not externalized enough")
    print("\n   per-model A / B / C:")
    for p in ALL_MODELS:
        a=np.mean(per_model[p]["A_open"]) if per_model[p]["A_open"] else 0
        b=np.mean(per_model[p]["B_suppressed"]) if per_model[p]["B_suppressed"] else 0
        c=np.mean(per_model[p]["C_supp_geom"]) if per_model[p]["C_supp_geom"] else 0
        print(f"     {p:<10} A={a:.0%}  B={b:.0%}  C={c:.0%}")
    json.dump({"A_open":cond_recall["A_open"],"B_suppressed":cond_recall["B_suppressed"],
               "C_supp_geom":cond_recall["C_supp_geom"]},open("suppression_abc_panel.json","w"),indent=2)
    print("\nwrote suppression_abc_results.json + _panel.json")
    print("*** THE ROBUSTNESS TEST: does the operator survive when model cognition is suppressed? ***")
if __name__=="__main__": main()
