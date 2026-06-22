#!/usr/bin/env python3
"""control_recall.py -- tests whether the BARE PROMPT (PLAIN_PLUS) misses the concepts
the SVD geometry surfaced, vs A_PLUS_C which was handed them. Not a quality test (panel
did that) -- a RECALL test. Semantic presence via bge cosine (paraphrase-proof, same
metric as the entity-swap). If PLAIN_PLUS misses the loaded/operational concepts that
A+C contains, the geometry surfaced something the prompt routed around."""
import os, sys, json, re
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront10_final as F
from geometric_engine import get_engine
eng=get_engine()
def E(t):
    v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
    return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

R=json.load(open("control_plainprompt_results.json"))
THRESH=0.55   # semantic-presence: concept embedding vs any sentence of the arm's output

def present(concept, text):
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip())>8]
    if not sents: return 0.0
    cv=E([concept])[0]; sv=E(sents)
    return float(np.max(sv@cv))

# re-derive each story's channel-C concepts (results.json didn't save them)
eng2=F.build_engine()
print(f"semantic-presence threshold = {THRESH} (bge cosine, paraphrase counts)\n")
agg={'PLAIN_PLUS':[], 'A_PLUS_C':[]}; rows_out=[]
for r in R:
    story=r["story"]; src=r["source"]
    cons=[]
    for m in C.LOCAL_PATIENTS:
        s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
        if s: cons.append(s)
    _,_,concepts=F.derive_channels(src,cons,eng2)
    plain_text=" ".join(g.get("PLAIN_PLUS","") for row in r["rows"] for g in row["gens"])
    ac_text   =" ".join(g.get("A_PLUS_C","")   for row in r["rows"] for g in row["gens"])
    print(f"=== {story} ===  concepts: {concepts}")
    for c in concepts:
        pr=present(c, plain_text); ar=present(c, ac_text)
        flag = "  << PLAIN MISSES (A+C has it)" if (pr<THRESH and ar>=THRESH) else ""
        print(f"   {c:18s}  plain={pr:.2f}  A+C={ar:.2f}{flag}")
        agg['PLAIN_PLUS'].append(pr>=THRESH); agg['A_PLUS_C'].append(ar>=THRESH)
        rows_out.append({"story":story,"concept":c,"plain":pr,"ac":ar})
    print()
print("="*64)
pr=np.mean(agg['PLAIN_PLUS']); ar=np.mean(agg['A_PLUS_C'])
print(f"OVERALL recall of geometry-surfaced concepts:")
print(f"   PLAIN_PLUS (no geometry, just discipline): {pr:.0%}")
print(f"   A_PLUS_C   (handed the concepts):          {ar:.0%}")
print(f"   gap = {ar-pr:+.0%}  -- what the bare prompt misses that A+C contains")
print(f"\n   high PLAIN recall -> flat raycast adds nothing on any axis (fully retire it)")
print(f"   low PLAIN recall on loaded concepts -> geometry surfaced what the prompt routed around")
json.dump(rows_out, open("control_recall.json","w"), indent=2)
print("\nwrote control_recall.json")
