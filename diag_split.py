#!/usr/bin/env python3
"""diag_split.py — print the ac-axis (abstract-concrete) projection for the exact words
from the mexico_cia smoke, so we SEE why farc/norad landed in void not target."""
import os, sys, json
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
from geometric_engine import get_engine

eng=get_engine()
def E(t):
    v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
    return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

# the CURRENT poles (from keeper v3)
ABS=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CON=["strait","city","company","port","bank","border","weapon","official"]
ac=E(ABS).mean(0)-E(CON).mean(0); ac/=np.linalg.norm(ac)+1e-8

# the exact words from the smoke, both buckets
words_void_bucket=["ntsb","farc","norad","nhtsa","cartels","gchq","coups","accidents"]
words_target_bucket=["consulates","narco","extradited","interagency","expatriates","operators"]
allw=words_void_bucket+words_target_bucket

print("ac-axis projection: POSITIVE=abstract(->void/C)  NEGATIVE=concrete(->target/B)")
print("(current split rule: a>=0 -> void, a<0 -> target)\n")
proj=E(allw)@ac
rows=sorted(zip(allw,proj), key=lambda x:-x[1])
for w,a in rows:
    bucket="VOID/C" if a>=0 else "TARGET/B"
    cur = "(was void/C)" if w in words_void_bucket else "(was target/B)"
    flag=""
    # named orgs/acronyms we EXPECT to be concrete exemplars (channel B)
    if w in ("ntsb","farc","norad","nhtsa","gchq"): flag=" <-- NAMED ORG, expected TARGET/B"
    print(f"  {w:14s} {a:+.4f}  -> {bucket:9s} {cur}{flag}")

print("\n--- diagnosis ---")
named=["ntsb","farc","norad","nhtsa","gchq"]
nm=E(named)@ac
print(f"named orgs mean projection: {nm.mean():+.4f}  (if POSITIVE, the axis calls acronyms 'abstract')")
print("if acronyms score positive/abstract, the CON pole lacks proper-noun/org anchors.")
print("\n--- candidate fix: add named-entity anchors to CON pole ---")
CON2=["strait","city","company","port","border","fbi","cia","reuters","pentagon","interpol"]
ac2=E(ABS).mean(0)-E(CON2).mean(0); ac2/=np.linalg.norm(ac2)+1e-8
proj2=E(allw)@ac2
print("with org-anchored CON pole (fbi/cia/reuters/pentagon/interpol added):")
for w,a in sorted(zip(allw,proj2), key=lambda x:-x[1]):
    bucket="VOID/C" if a>=0 else "TARGET/B"
    print(f"  {w:14s} {a:+.4f}  -> {bucket}")
