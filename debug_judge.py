#!/usr/bin/env python3
"""
debug_judge.py — the unlock run's faithful/unlock scores were broken (faithful=0
for obviously-faithful words, unlock=0 everywhere). Diagnosis: judge output
format != my regex. This dumps the judge's RAW response so we see the actual
format and fix the parser. Also tries a couple judges. ~12 calls. temp=0.
"""
import os, sys
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import proxy_auditor as pa

title="What has Iran won and lost from this war?"
base=("Iran's war with Israel damaged its relationships with Gulf neighbors and "
      "weakened its regional position, though Tehran claims strategic gains.")
# a clearly-faithful escalation concept and a clearly-unfaithful one
tests=[("hezbollah", "Iran's war weakened its position and strained Gulf ties; its proxy "
        "Hezbollah also emerged diminished, reshaping the regional balance."),
       ("webcam", "Iran's war played out across live webcam feeds and streaming "
        "coverage as viewers watched the conflict online.")]

jp_template=("SOURCE STORY: {title}\n\nBASE SUMMARY: {base}\n\nNEW SUMMARY: {s1}\n\n"
    "The new summary tried to incorporate the concept '{w}'. Answer EXACTLY in this format:\n"
    "FAITHFUL: yes/no  (is the NEW SUMMARY faithful to the source story, no invented claims?)\n"
    "CONSEQUENCE: yes/no  (does NEW add a real downstream consequence about the STORY not in BASE?)\n"
    "ACTOR: yes/no  (does NEW add a relevant actor/stakeholder about the STORY not in BASE?)\n"
    "CONSTRAINT: yes/no  (does NEW add a real constraint/mechanism about the STORY not in BASE?)")

for judge_name in ["DeepSeek","ChatGPT"]:
    judge=pa.BIG5_CALLERS[judge_name]
    print("="*72); print(f"JUDGE = {judge_name}"); print("="*72)
    for w,s1 in tests:
        jp=jp_template.format(title=title, base=base, s1=s1, w=w)
        jt,je=judge(jp)
        print(f"\n--- concept '{w}' (expect: hezbollah=faithful+unlock, webcam=unfaithful) ---")
        print(f"RAW JUDGE RESPONSE:\n{jt}\n")
        print(f"(err: {je!r})")
