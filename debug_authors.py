#!/usr/bin/env python3
"""
debug_authors.py — parser + judges are PROVEN fine on hand-written S1. So the
real-run bug is the AUTHORED S1: when authors are told "consider w, work it in if
relevant else ignore", they may IGNORE it (producing a summary without the concept)
OR produce something the judge marks unfaithful. This dumps the ACTUAL authored S1
+ the judge's verdict on it, for a few real candidates. Shows the true failure.
~18 calls.
"""
import os, sys, re
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import proxy_auditor as pa

title="What has Iran won and lost from this war?"
base=("Iran's relationship with its Gulf neighbours, which it attacked during the war, "
      "has been damaged. Iran's regional standing and proxy network suffered setbacks, "
      "though it avoided regime collapse and retained some deterrent capability.")

# real candidates from the run
cands=["hezbollah","defence","combat","devastation","skirmish"]

def parse_judgment(txt):
    t=(txt or "").lower()
    faithful = ("faithful: yes" in t) or bool(re.search(r'faithful[:\s]+yes',t))
    cons = bool(re.search(r'consequence[:\s]+yes', t))
    actor= bool(re.search(r'actor[:\s]+yes', t))
    constr=bool(re.search(r'constraint[:\s]+yes', t))
    return (faithful, int(cons)+int(actor)+int(constr))

author=pa.BIG5_CALLERS["ChatGPT"]
judge=pa.BIG5_CALLERS["DeepSeek"]

for w in cands:
    ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary. Consider whether "
        f"'{w}' is relevant; if so work it in naturally, if not ignore it. Stay faithful.")
    s1,e=author(ap)
    s1=(s1 or "").strip()
    print("="*68); print(f"CONCEPT: '{w}'")
    print(f"AUTHORED S1:\n  {s1}\n")
    # does S1 even contain the concept?
    contains = w.lower() in s1.lower()
    print(f"  [S1 actually contains '{w}'? {contains}]")
    jp=(f"SOURCE STORY: {title}\n\nBASE SUMMARY: {base}\n\nNEW SUMMARY: {s1}\n\n"
        f"The new summary tried to incorporate the concept '{w}'. Answer EXACTLY in this format:\n"
        f"FAITHFUL: yes/no  (is the NEW SUMMARY faithful to the source story, no invented claims?)\n"
        f"CONSEQUENCE: yes/no  (does NEW add a real downstream consequence about the STORY not in BASE?)\n"
        f"ACTOR: yes/no  (does NEW add a relevant actor not in BASE?)\n"
        f"CONSTRAINT: yes/no  (does NEW add a real constraint/mechanism not in BASE?)")
    jt,je=judge(jp)
    f,u=parse_judgment(jt)
    print(f"  JUDGE RAW: {(jt or '').strip()[:120]}")
    print(f"  PARSED -> faithful={f}  unlock={u}\n")
