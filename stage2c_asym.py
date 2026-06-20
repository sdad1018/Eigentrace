#!/usr/bin/env python3
"""
STAGE 2c (LAST PROBE): asymmetric thresholds. The axis separates ABSTRACT strongly
(+0.35) but CONCRETE weakly (concrete words only reach ~-0.05). So use per-axis cutoffs
matched to each pole's MEASURED range, instead of pretending the axis is symmetric.

  ACTOR     if p2 >= AT  OR  role-string has a person-noun
  ABSTRACT  elif p1 >= ABS_T          (strong positive side)
  CONCRETE  elif p1 <= CON_T          (weak negative side, e.g. -0.04)
  AMBIG     else                      (genuinely near-zero on BOTH: the true fence)

Shows a small sweep of the concrete cutoff so Sean sees concrete populate without
swallowing the real fence-words (ieds/arms deal must stay AMBIG).
Writes atlas_final4.json for the CHOSEN setting (passed as argv, default the middle one).
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

AT=0.12; ABS_T=0.12
# sweep the concrete (negative) cutoff — concrete words max out near -0.05
CON_SWEEP=[-0.03,-0.04,-0.05,-0.06]

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

    freq={}
    for d in (data["void_overall"],data["target_overall"]):
        for w,c in d.items(): freq[w]=freq.get(w,0)+c
    words=list(freq); V=E(words); Vc=V-M; Vc=Vc/(np.linalg.norm(Vc,axis=1,keepdims=True)+1e-8)
    P1=Vc@axis1; P2=Vc@axis2

    def classify(i, CON_T):
        if P2[i]>=AT or actor_role(words[i]): return "ACTOR"
        if P1[i]>=ABS_T: return "STAKES"
        if P1[i]<=CON_T: return "SPECIFIC"
        return "AMBIG"

    print("="*76); print(f"ASYMMETRIC SWEEP (actor p2>={AT}, stakes p1>={ABS_T}, specific cutoff varies)"); print("="*76)
    tests=["rouhani","khomeini","sadr","hormuz","tehran","baghdad","ieds","arms deal","escalation","refineries"]
    for CON_T in CON_SWEEP:
        b={"STAKES":[],"SPECIFIC":[],"ACTOR":[],"AMBIG":[]}
        for i,w in enumerate(words): b[classify(i,CON_T)].append((w,freq[w]))
        print(f"\n### concrete cutoff p1<={CON_T} ###")
        for k in ["STAKES","SPECIFIC","ACTOR","AMBIG"]:
            lst=sorted(b[k],key=lambda x:-x[1])
            print(f"  {k:<9} n={len(lst):>3} | {', '.join(role_of(w) for w,_ in lst[:6])}")
        tl=[f"{tw}->{classify(words.index(tw),CON_T)[:4]}" for tw in tests if tw in words]
        print(f"  tests: {'  '.join(tl)}")
        # KEY check: do ieds/arms deal stay AMBIG while tehran/baghdad become SPECIFIC?
        fence_ok = all(classify(words.index(w),CON_T)=="AMBIG" for w in ["ieds","arms deal"] if w in words)
        place_ok = all(classify(words.index(w),CON_T)=="SPECIFIC" for w in ["tehran","baghdad"] if w in words)
        print(f"  -> fence stays AMBIG: {fence_ok} | places become SPECIFIC: {place_ok}  {'<<< CLEAN' if fence_ok and place_ok else ''}")

    print("\nPick a concrete cutoff where places(tehran/baghdad)->SPECIFIC but fence(ieds/arms deal)->AMBIG.")
    print("That's the asymmetric setting. Then say 'lock -0.0X' and I write atlas_final4.json + build the page.")

if __name__=="__main__": main()
