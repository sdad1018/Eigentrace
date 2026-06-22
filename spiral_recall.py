#!/usr/bin/env python3
"""spiral_recall.py -- does a BARE PROMPT miss the clean spiral concepts?
Reads spiral_concepts.json (the entity-scrubbed convergence-spiral concepts) and checks
each against the EXISTING PLAIN_PLUS summaries (control_plainprompt_results.json) -- no new
generation. Reports PER-CONCEPT whether the bare prompt reached it, so we can separate:
  - concepts the prompt MISSES (your idea: geometry found something a prompt can't)
  - concepts the prompt REACHES (geometry adds nothing there)
And flag whether misses cluster on defensible source-implied concepts (failed state, air strike)
vs corpus-habit concepts (coup attempt) the prompt may correctly avoid."""
import os, sys, json, re
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine
eng=get_engine()
def E(t):
    v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
    return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

SPIRAL=json.load(open("spiral_concepts.json"))
PLAIN=json.load(open("control_plainprompt_results.json"))
THRESH=0.55

# index PLAIN_PLUS text by story
plain_by_story={}
for r in PLAIN:
    txt=" ".join(g.get("PLAIN_PLUS","") for row in r["rows"] for g in row["gens"])
    plain_by_story[r["story"]]=txt

def present(concept, text):
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip())>8]
    if not sents: return 0.0
    cv=E([concept])[0]; sv=E(sents)
    return float(np.max(sv@cv))

print(f"SPIRAL CONCEPT RECALL by bare prompt (threshold {THRESH})\n")
all_reached=[]; missed_rows=[]; reached_rows=[]
for o in SPIRAL:
    story=o["story"]; concepts=o["spiral"]
    ptext=plain_by_story.get(story,"")
    if not ptext: print(f"  {story}: no PLAIN_PLUS text, skip"); continue
    print(f"=== {story} ===")
    for c in concepts:
        pr=present(c, ptext)
        reached = pr>=THRESH
        all_reached.append(reached)
        tag = "reached" if reached else "MISSED"
        novel = "  (novel-vs-flat)" if c in o.get("novel",[]) else ""
        print(f"   {c:20s} prompt={pr:.2f}  {tag}{novel}")
        (reached_rows if reached else missed_rows).append((story,c,pr,c in o.get("novel",[])))
    print()

print("="*64)
rate=np.mean(all_reached) if all_reached else 0
print(f"OVERALL: bare prompt reached {rate:.0%} of clean spiral concepts")
print(f"\nCONCEPTS THE PROMPT MISSED (geometry surfaced, prompt did not):")
if missed_rows:
    for story,c,pr,nv in sorted(missed_rows, key=lambda x:x[2]):
        print(f"   {c:20s} ({story}, prompt={pr:.2f}){'  NOVEL' if nv else ''}")
else:
    print("   (none -- prompt reached everything the spiral surfaced)")
print(f"\n   {len(missed_rows)} missed / {len(all_reached)} total")
print(f"   READ THESE: are the misses defensible source-implied concepts (failed state,")
print(f"   air strike) -> your idea found something real. Or corpus-habit (coup attempt)")
print(f"   -> the prompt correctly avoided what the geometry wrongly surfaced.")
json.dump({"missed":[(s,c,pr,nv) for s,c,pr,nv in missed_rows],
           "reached":[(s,c,pr,nv) for s,c,pr,nv in reached_rows]},
          open("spiral_recall.json","w"),indent=2)
print("\nwrote spiral_recall.json")
