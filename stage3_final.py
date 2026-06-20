#!/usr/bin/env python3
"""
STAGE 3 (FINAL DATA): lock the 4-way split at CON_T=-0.04 and write atlas_final4.json
with per-domain STAKES/SPECIFIC/ACTOR/AMBIG, roles applied. This is the chart data.

Locked params (all calibrated, all eyeballed on real output):
  axis1 = abstract_centroid - concrete_centroid        (validated; abstract-concrete contrast)
  axis2 = actor - mean(abs,con), Gram-Schmidt orthogonal (actor detection)
  words centered by 3-pole mean before projecting (kills common-mode)
  ACTOR    if p2>=0.12 OR consensus-role-string has a person-noun (geometry+relabel backstop)
  STAKES   elif p1>=0.12   (strong abstract side)
  SPECIFIC elif p1<=-0.04  (weak concrete side, asymmetric per measured range)
  AMBIG    else            (true near-zero fence: ieds/arms deal/norad)
"""
import os, sys, json
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine

ABSTRACT=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE=["strait","city","company","port","bank","border","weapon","harbor"]
ACTOR   =["president","leader","minister","cleric","general","diplomat","dictator","chancellor"]
ROLE_NOUNS=["president","leader","minister","cleric","general","diplomat","dictator",
            "chancellor","prime minister","official","politician","spokesman"]
AT=0.12; ABS_T=0.12; CON_T=-0.04

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    A=E(ABSTRACT).mean(0); C=E(CONCRETE).mean(0); K=E(ACTOR).mean(0); M=(A+C+K)/3.0
    axis1=A-C; axis1/=np.linalg.norm(axis1)+1e-8
    raw2=K-(A+C)/2.0; raw2=raw2-(raw2@axis1)*axis1; axis2=raw2/(np.linalg.norm(raw2)+1e-8)

    data=json.load(open("corpus_void_target.json"))
    s1=json.load(open("stage1_result.json")); roles=dict(s1["accepted"])
    if os.path.exists("stage2_tail_ckpt.json"):
        roles.update(json.load(open("stage2_tail_ckpt.json")).get("roles",{}))
    def role_of(w): return roles.get(w,w)
    def actor_role(w): r=role_of(w).lower(); return any(n in r for n in ROLE_NOUNS)

    # cache p1/p2 for any word
    _cache={}
    def proj(w):
        if w in _cache: return _cache[w]
        v=E(w)[0]-M; v=v/(np.linalg.norm(v)+1e-8)
        r=(float(v@axis1),float(v@axis2)); _cache[w]=r; return r
    def classify(w):
        p1,p2=proj(w)
        if p2>=AT or actor_role(w): return "ACTOR"
        if p1>=ABS_T: return "STAKES"
        if p1<=CON_T: return "SPECIFIC"
        return "AMBIG"

    def split_counts(wc):
        """wc: {word:count} -> {bucket: {role: summed_count}}"""
        out={"STAKES":{},"SPECIFIC":{},"ACTOR":{},"AMBIG":{}}
        for w,c in wc.items():
            b=classify(w); disp=role_of(w)
            out[b][disp]=out[b].get(disp,0)+c
        return {k:dict(sorted(v.items(),key=lambda x:-x[1])) for k,v in out.items()}

    final={"locked":{"actor_p2":AT,"stakes_p1":ABS_T,"specific_p1":CON_T},
           "n_real_stories":data["n_real_stories"],
           "method":("per-story derive() on clean stories -> 5-model consensus relabel "
                     "(centroid-density, tau=0.85, >=4/5) -> 4-way geometric split on two "
                     "orthogonal centered difference-axes + person-noun relabel backstop. "
                     "STAKES=abstract voids, SPECIFIC=concrete, ACTOR=people-as-roles, "
                     "AMBIG=near-zero fence. opens_onto (per-story crown) is future work."),
           "domains":{}}
    for dom in ["war","other_conflict","general"]:
        merged=dict(data.get("void_by_dom",{}).get(dom,{}))
        for w,c in data.get("target_by_dom",{}).get(dom,{}).items(): merged[w]=merged.get(w,0)+c
        if merged:
            final["domains"][dom]={"n_stories":data["domain_counts"].get(dom),
                                   "buckets":split_counts(merged)}
    # iran
    im=dict(data.get("void_iran",{}))
    for w,c in data.get("target_iran",{}).items(): im[w]=im.get(w,0)+c
    final["iran"]=split_counts(im)

    json.dump(final,open("atlas_final4.json","w"),indent=2)

    print("="*72); print("LOCKED 4-WAY SPLIT — atlas_final4.json written"); print("="*72)
    for dom,dd in final["domains"].items():
        print(f"\n### {dom} (n={dd['n_stories']}) ###")
        for b in ["STAKES","SPECIFIC","ACTOR","AMBIG"]:
            items=list(dd["buckets"][b].items())[:7]
            print(f"  {b:<9} | {', '.join(f'{r}({c})' for r,c in items)}")
    print(f"\n### IRAN ###")
    for b in ["STAKES","SPECIFIC","ACTOR","AMBIG"]:
        items=list(final["iran"][b].items())[:8]
        print(f"  {b:<9} | {', '.join(f'{r}({c})' for r,c in items)}")
    print("\n*** DATA LOCKED — ready to build the charts + page ***")

if __name__=="__main__": main()
