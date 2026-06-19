#!/usr/bin/env python3
"""
eyeball_read.py — NO judge, NO scores. Just print the full summaries side by side so a
HUMAN reads them like a professor reading three students' essays.

The four scored runs all said cosmetic-or-worse, but we NEVER READ THE ACTUAL TEXT. The
whole "college student vs professor" frame is qualitative: does the void-injected summary
show a student who UNDERSTOOD the material (synthesized, drew connections, surfaced the
real stakes) — or one who just COVERED more points (regurgitation, list-padding)?

A judge model can't tell those apart (it rewards coverage). A human can. So: print
  S0           (baseline — the student who didn't use Summary Plus)
  S_void       (absent-but-adjacent injection — did it make them THINK?)
  S_placebo    (off-topic injection — control)
for the 2 FAKES + 2 erased news. Read with eyeballs. No numbers.

Local. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np, requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
MU=0.55; K=3
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

def llm(prompt, mt=320, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"[err {e}]"

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            sums=st.get("summaries",[])
            if sums: items.append(("FAKE", st.get("title","fake"), sums[0], " ".join(sums)[:2200]))
    except Exception as e: print(f"(fakes: {e})")
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]; nn=0
    for f in sorted(SEGS,reverse=True):
        if nn>=2: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<400: continue
            items.append(("NEWS", t, list(sums.values())[0], a["source_body"][:2200])); nn+=1
        except: continue

    def candidates(source):
        out=llm(f"List 12 short (1-3 word) key concepts/topics from this text, comma-separated, "
                f"no numbering:\n\n{source[:1800]}", mt=120, temp=0.0)
        cs=[c.strip().lower() for c in re.split(r"[,\n]",out) if 2<len(c.strip())<40]
        return list(dict.fromkeys(cs))[:14]

    for kind,title,S0,source in items:
        C=candidates(source)
        if len(C)<6:
            print(f"\n### [{kind}] {title}\n(skip: few candidates)\n"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        r=Cv@Dv; a=1-(Cv@S0v); band=1-np.abs(r-MU); V=a*r*band
        order=np.argsort(-V)
        void=[C[i] for i in order if C[i] not in HARD_DROP][:K]
        void_tokens=set(t for w in void for t in w.lower().split())
        placebo=[]
        for i in np.argsort(r):
            w=C[i]
            if w in HARD_DROP or any(tok in void_tokens for tok in w.lower().split()): continue
            placebo.append(w)
            if len(placebo)>=K: break
        s0_len=len(S0.split()); lo,hi=int(s0_len*0.85),int(s0_len*1.15)
        def regen(concepts):
            return llm(f"Source:\n{source[:1500]}\n\nSummary ({s0_len} words):\n{S0}\n\n"
                       f"EDIT this summary so it ALSO addresses, WHERE SUPPORTED BY THE SOURCE: "
                       f"{', '.join(concepts)}. Keep ~same length ({lo}-{hi} words), keep what's "
                       f"correct, introduce NO claims absent from source. Return only the summary.")
        Sv=regen(void); Sp=regen(placebo)
        print("\n"+"#"*72)
        print(f"### [{kind}] {title}")
        print("#"*72)
        print(f"\nSOURCE (first 600 chars):\n{source[:600]}")
        print(f"\n--- VOID concepts (absent-but-adjacent): {void}")
        print(f"--- PLACEBO concepts (off-topic): {placebo}")
        print(f"\n┌─ S0 (BASELINE — no Summary Plus) [{s0_len}w] ─────────────")
        print(S0)
        print(f"\n┌─ S_VOID (absent-but-adjacent injected) [{len(Sv.split())}w] ─")
        print(Sv)
        print(f"\n┌─ S_PLACEBO (off-topic injected, control) [{len(Sp.split())}w] ─")
        print(Sp)
        print()

    print("\n"+"="*72)
    print("READ WITH EYEBALLS (the professor's question):")
    print("  For each story, does S_VOID show a student who UNDERSTOOD — synthesized the")
    print("  stakes, drew a connection S0 missed, reframed insightfully — or one who just")
    print("  COVERED MORE (padded a list, name-dropped the void concepts mechanically)?")
    print("  And does S_VOID beat S_PLACEBO in that *understanding* sense, or are both just")
    print("  S0-with-extra-nouns? On the FAKES especially: did void surface the real stakes")
    print("  (consciousness/agency; disclosure/contact) or news-junk it couldn't metabolize?")

if __name__=="__main__":
    main()
