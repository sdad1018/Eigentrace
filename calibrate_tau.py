#!/usr/bin/env python3
"""
calibrate_tau.py — STAGE 0: pick the centroid-density agreement threshold τ from real output.

Relabels 3 spectrum-spanning words with all 10 models (reusing confront10's exact callers),
embeds each model's role-string, computes the centroid, and prints every role's cosine to it.
You read the spread and choose τ: where the obvious word stays unanimous and the ambiguous
word correctly fails to cluster.

Agreement model (your validated centroid method, not crude string-matching):
  embed the 10 role-strings -> centroid -> density = each role's cosine to centroid.
  "k models agree at τ" = how many role-vecs sit within τ cosine of the centroid.

3 calibration words chosen to span the spectrum:
  rouhani  — should be unanimous ("an Iranian president")            -> high density
  isil     — should mostly cluster ("Sunni militants"/"extremists") -> medium
  fars     — likely scatters (province? news agency? name?)          -> low density
"""
import os, sys, json, re
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# import the REAL callers + roster from confront10 (no reconstruction)
import confront10 as C
from geometric_engine import get_engine

CAL_WORDS=["rouhani","isil","fars"]   # obvious / medium / ambiguous

# the verbatim relabel instruction, single-word form (same KEEP/CATEGORY/DROP semantics)
def relabel_prompt(word):
    return (f"This is a concept AI news summaries often OMIT, surfaced from a frozen embedding space: '{word}'.\n"
            f"Answer with EXACTLY ONE line:\n"
            f"KEEP <term> — if it is already a durable concept (e.g. 'civilian casualties','arms deal','regime change').\n"
            f"CATEGORY <label> — if it is a STALE named person/org/place -> give its durable ROLE "
            f"(e.g. 'rouhani' -> 'an Iranian president'). A fillable role, not a bare generic.\n"
            f"DROP — if it is pure noise/ticker/handle.\n\n"
            f"Answer: KEEP <term> / CATEGORY <label> / DROP")

def parse_role(raw, word):
    """Extract the durable role string from a model's KEEP/CATEGORY/DROP answer."""
    if not raw: return None
    m=re.search(r'\b(KEEP|CATEGORY|DROP)\b\s*(.*)', raw, re.I)
    if not m: return None
    act=m.group(1).lower(); lab=m.group(2).strip().strip('.').strip()
    if act=="drop": return "(drop)"
    if act=="keep": return lab or word
    return lab or word   # category -> the role label

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    # the 10 callers: 5 API + 5 local, via confront10's own dispatch
    API=C.API_PATIENTS                      # {name: fn(messages)->str}
    LOCAL=C.LOCAL_PATIENTS                  # [model strings]
    def call_model(name, prompt):
        msgs=[{"role":"user","content":prompt}]
        try:
            if name in API: return API[name](msgs)
            return C.mt_local(msgs, name)
        except Exception as e:
            return f"(ERR {e})"
    roster=list(API.keys())+LOCAL
    print(f"roster ({len(roster)}): {roster}\n")

    for word in CAL_WORDS:
        print("="*72); print(f"WORD: {word}"); print("="*72)
        roles={}; 
        for name in roster:
            raw=call_model(name, relabel_prompt(word))
            role=parse_role(raw, word)
            roles[name]=role
            print(f"  {name:<16} -> {role!r}    [raw: {(raw or '')[:60].strip()!r}]")

        # embed the (non-drop, non-err) role strings, centroid density
        valid=[(n,r) for n,r in roles.items() if r and r!="(drop)" and not r.startswith("(ERR")]
        if len(valid)<3:
            print(f"\n  too few valid roles ({len(valid)}) to compute density\n"); continue
        names=[n for n,_ in valid]; strs=[r for _,r in valid]
        V=E(strs)                       # (k,1024) unit-normalized
        centroid=V.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        cos=V@centroid                  # each role's cosine to centroid
        order=np.argsort(-cos)
        print(f"\n  centroid density (cosine of each role to the centroid), sorted:")
        for i in order:
            print(f"    {cos[i]:+.3f}  {names[i]:<16} {strs[i]!r}")
        density_mean=float(cos.mean())
        print(f"  mean density: {density_mean:+.3f}")
        # how many 'agree' at candidate thresholds
        print(f"  agreement count at candidate τ:")
        for tau in [0.70,0.75,0.80,0.85,0.90]:
            k=int((cos>=tau).sum())
            print(f"    τ={tau:.2f}: {k}/{len(valid)} within τ  {'<-- >=8 ACCEPT' if k>=8 else ''}")
        print()

    print("HOW TO READ: pick τ where 'rouhani' keeps >=8 within τ (true agreement survives)")
    print("but 'fars' drops below 8 (genuine scatter is correctly rejected to literal).")
    print("isil is the interesting middle — its behaviour tells you if τ is too strict/loose.")

if __name__=="__main__": main()
