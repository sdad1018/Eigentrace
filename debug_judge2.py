#!/usr/bin/env python3
"""
debug_judge2.py — the SIMPLE judge prompt parsed fine. But the REAL run used a
prompt WITH the persistence guard ("only yes if it survives removing the word")
and got faithful=0 / unlock fired separately. Suspect: the guard wording made the
judge add reasoning/qualifiers that broke parsing. This dumps raw output using the
EXACT real-run prompt to see what the guard did. ~6 calls.
"""
import os, sys, re
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import proxy_auditor as pa

title="What has Iran won and lost from this war?"
base=("Iran's war with Israel damaged its relationships with Gulf neighbors and "
      "weakened its regional position, though Tehran claims strategic gains.")
s1=("Iran's war weakened its position and strained Gulf ties; its proxy "
    "Hezbollah also emerged diminished, reshaping the regional balance.")
w="hezbollah"

# EXACT prompt from the real test_unlock.py run (WITH persistence guard)
jp=(f"SOURCE STORY: {title}\n\nBASE SUMMARY: {base}\n\nNEW SUMMARY: {s1}\n\n"
    f"The new summary tried to incorporate the concept '{w}'. Answer EXACTLY in this format:\n"
    f"FAITHFUL: yes/no  (is the NEW SUMMARY faithful to the source story, no invented claims?)\n"
    f"CONSEQUENCE: yes/no  (does NEW add a real downstream consequence about the STORY not in BASE? "
    f"only yes if it would still make sense with the word '{w}' removed)\n"
    f"ACTOR: yes/no  (does NEW add a relevant actor/stakeholder about the STORY not in BASE?)\n"
    f"CONSTRAINT: yes/no  (does NEW add a real constraint/mechanism about the STORY not in BASE?)")

# my exact parser from the real run
def parse_judgment(txt):
    t=txt.lower()
    faithful = ("faithful: yes" in t) or ("faithful:yes" in t) or re.search(r'faithful[:\s]+yes',t)
    cons = bool(re.search(r'consequence[:\s]+yes', t))
    actor= bool(re.search(r'actor[:\s]+yes', t))
    constr=bool(re.search(r'constraint[:\s]+yes', t))
    return (bool(faithful), int(cons)+int(actor)+int(constr))

for judge_name in ["DeepSeek","ChatGPT","Gemini"]:
    judge=pa.BIG5_CALLERS[judge_name]
    jt,je=judge(jp)
    print("="*60); print(f"JUDGE = {judge_name} (REAL prompt with persistence guard)")
    print(f"RAW:\n{jt}\n")
    f,u=parse_judgment(jt or "")
    print(f"PARSED -> faithful={f}  unlock={u}")
    print(f"(this should be faithful=True, unlock>=1 for hezbollah)\n")
