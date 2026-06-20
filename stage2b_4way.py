#!/usr/bin/env python3
"""
STAGE 2b: the 4-way split (abstract/concrete/actor/ambiguous) over the FULL corpus,
using Option 2 (two orthogonal difference-axes) + relabel backstop for actors.
Shows bucket counts at THREE threshold settings so Sean picks before locking.

Geometry (validated): center words by the 3-pole mean, then
  p1 = w_centered . axis1   (axis1 = abstract_centroid - concrete_centroid)   abstract +/concrete -
  p2 = w_centered . axis2   (axis2 = actor - mean(abs,con), Gram-Schmidt'd orthogonal to axis1)

Assignment (belt & suspenders for actors):
  ACTOR     if p2 >= AT  OR  the consensus role-string contains a person-role-noun
  ABSTRACT  elif p1 >= PT
  CONCRETE  elif p1 <= -PT
  AMBIGUOUS else   (both axes near zero: the honest fence — ieds/arms deal/norad)

Reads corpus_void_target.json + stage1_result.json (roles). Writes nothing yet — prints
the three-threshold comparison so we lock AT/PT, THEN a final run writes atlas_final4.json.
"""
import os, sys, json
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine

ABSTRACT=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE=["strait","city","company","port","bank","border","weapon","harbor"]
ACTOR   =["president","leader","minister","cleric","general","diplomat","dictator","chancellor"]

# person-role-nouns: if a word's consensus ROLE string contains one, it's an actor (backstop)
ROLE_NOUNS=["president","leader","minister","cleric","general","diplomat","dictator",
            "chancellor","prime minister","official","politician","spokesman"]

# three candidate threshold settings to compare (actor p2 cutoff, abstract/concrete p1 cutoff)
SETTINGS=[("A: symmetric .12/.12", 0.12, 0.12),
          ("B: looser p1 .12/.06", 0.12, 0.06),
          ("C: tighter .15/.10",   0.15, 0.10)]

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    A=E(ABSTRACT).mean(0); C=E(CONCRETE).mean(0); K=E(ACTOR).mean(0)
    M=(A+C+K)/3.0
    axis1=A-C; axis1/=np.linalg.norm(axis1)+1e-8
    raw2=K-(A+C)/2.0; raw2=raw2-(raw2@axis1)*axis1; axis2=raw2/(np.linalg.norm(raw2)+1e-8)

    data=json.load(open("corpus_void_target.json"))
    s1=json.load(open("stage1_result.json"))
    roles=dict(s1["accepted"])
    # also load tail roles if stage2 already produced them
    if os.path.exists("stage2_tail_ckpt.json"):
        roles.update(json.load(open("stage2_tail_ckpt.json")).get("roles",{}))
    def role_of(w): return roles.get(w,w)
    def is_actor_role(w):
        r=role_of(w).lower()
        return any(n in r for n in ROLE_NOUNS)

    # all distinct words + their corpus frequency (void+target merged, overall)
    freq={}
    for d in (data["void_overall"],data["target_overall"]):
        for w,c in d.items(): freq[w]=freq.get(w,0)+c
    words=list(freq)
    V=E(words); Vc=V-M; Vc=Vc/(np.linalg.norm(Vc,axis=1,keepdims=True)+1e-8)
    P1=Vc@axis1; P2=Vc@axis2

    def classify(i, AT, PT):
        w=words[i]
        if P2[i]>=AT or is_actor_role(w): return "ACTOR"
        if P1[i]>=PT: return "ABSTRACT"
        if P1[i]<=-PT: return "CONCRETE"
        return "AMBIG"

    print("="*78)
    print("THREE-THRESHOLD COMPARISON — bucket counts (distinct words) + top words each")
    print("="*78)
    for label,AT,PT in SETTINGS:
        buckets={"ABSTRACT":[],"CONCRETE":[],"ACTOR":[],"AMBIG":[]}
        for i,w in enumerate(words):
            buckets[classify(i,AT,PT)].append((w,freq[w]))
        print(f"\n### {label}  (actor p2>={AT}, |p1|>={PT}) ###")
        for b in ["ABSTRACT","CONCRETE","ACTOR","AMBIG"]:
            lst=sorted(buckets[b],key=lambda x:-x[1])
            top=[f"{role_of(w)}({c})" for w,c in lst[:6]]
            print(f"  {b:<9} n={len(lst):>3} | {', '.join(top)}")
        # diagnostic: where did our 8 test words land?
        tests=["rouhani","khomeini","sadr","hormuz","tehran","ieds","arms deal","escalation"]
        tl=[]
        for tw in tests:
            if tw in words:
                tl.append(f"{tw}->{classify(words.index(tw),AT,PT)[:3]}")
        print(f"  test words: {'  '.join(tl)}")

    print("\nactor-by-relabel backstop hits (role-string contains person-noun):")
    actor_relabel=[w for w in words if is_actor_role(w) and P2[words.index(w)]<0.12]
    print(f"  {len(actor_relabel)} words caught by relabel that geometry (<0.12) would miss:")
    print(f"  e.g. {[(w, role_of(w)) for w in actor_relabel[:8]]}")
    print("\nPick a setting (A/B/C). Then I lock it + write atlas_final4.json with per-domain 4-way.")

if __name__=="__main__": main()
