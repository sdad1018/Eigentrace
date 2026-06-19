#!/usr/bin/env python3
"""
synthesis_engine.py — Gemini's Hegelian/tension prompt, WITH the fabrication knife.

The eyeball read proved: AGREEABLE void -> model coasts -> cosmetic rephrase. Gemini's
reframe: don't inject an agreeing concept, inject TENSION — name an orthogonal-plausible
concept and command the model to SYNTHESIZE the opposing stakes. Hypothesis: tension forces
real dialectical work where agreement let it coast.

THE CATCH Gemini glosses: the Rewire Collider's "CONTRADICTION pulled 14 new words" that
Gemini cites as proof — we ALREADY audited that as the model HALLUCINATING bridge scaffolding
to obey the prompt. "The strikes are a leverage tactic to force a peace deal" reads like A+
synthesis but may be FABRICATION (source never said it). A strong model makes hallucinated
bridges SOUND like insight. So the test is NOT "more synthesis-looking words" — it's:

  Does forced synthesis surface a REAL, SOURCE-SUPPORTED stake S0 missed (genuine insight)
  OR manufacture a plausible-sounding FABRICATION to resolve the tension (worse than coasting)?

THREE OUTPUTS per story, all READ BY HUMAN + faithfulness-checked:
  S0          baseline (the coasting A+ student)
  S_synth     Gemini's tension prompt: "consensus is X, but tension of [orthogonal] —
              synthesize the opposing stakes"
  S_agree     control: same orthogonal concept but injected AGREEABLY ("also address X")
              -> isolates whether it's the TENSION FRAMING or just the concept that matters

FABRICATION KNIFE: extract the *new claims* in S_synth (sentences/clauses not in S0), and
for each, check source-support: max cosine to any source sentence. Low max-sim = the claim
is NOT in the source = fabricated bridge. Report fabrication_rate per condition.

Orthogonal-plausible concept = topically adjacent (medium relevance to source) but
directionally OPPOSED to the consensus summary (high distance from S0). Found in latent space.

Local. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np, requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

def llm(prompt, mt=320, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"[err {e}]"

def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip())>15]

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
    print(f"items: {[k for k,_,_,_ in items]}")

    fab={"SYNTH":[], "AGREE":[]}
    for kind,title,S0,source in items:
        # find orthogonal-plausible concept: medium relevance to source, HIGH distance from S0
        cand_raw=llm(f"List 14 short (1-3 word) concepts RELATED to this story's domain but representing "
                     f"DIFFERENT angles, tensions, or counter-forces — not just the obvious topic. "
                     f"Comma-separated:\n\n{source[:1500]}", mt=140, temp=0.4)
        C=[c.strip().lower() for c in re.split(r"[,\n]",cand_raw) if 2<len(c.strip())<40]
        C=list(dict.fromkeys(C))[:14]
        if len(C)<5: print(f"skip: {title[:40]}"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        rel=Cv@Dv          # relevance to source
        opp=1-(Cv@S0v)     # opposition to / distance from the consensus summary
        # orthogonal-plausible: relevant to source (rel>0.4) AND far from S0 (high opp)
        mask=rel>0.40
        score=np.where(mask, opp, -1)
        ortho=C[int(np.argmax(score))]
        srcsents=sentences(source); src_vecs=E(srcsents) if srcsents else None

        def fabrication_rate(S):
            new=[s for s in sentences(S) if s not in S0]
            new=[s for s in new if s.lower() not in S0.lower()]
            if not new or src_vecs is None: return None, 0
            nv=E(new); sims=nv@src_vecs.T
            maxsim=sims.max(axis=1)        # best source support for each new claim
            fabricated=int((maxsim<0.55).sum())   # not supported by any source sentence
            return fabricated/len(new), len(new)

        S_synth=llm(f"Source:\n{source[:1400]}\n\nThe consensus summary of this story is:\n{S0}\n\n"
                    f"However, an alternative analysis suggests the story is also governed by the tension "
                    f"of '{ortho}'. Rewrite the summary to SYNTHESIZE these two opposing stakes into a "
                    f"sharper account. CRITICAL: introduce NO claims that aren't supported by the source — "
                    f"synthesize what's THERE, don't invent. 2-4 sentences.")
        S_agree=llm(f"Source:\n{source[:1400]}\n\nSummary:\n{S0}\n\nEDIT this summary to also address '{ortho}' "
                    f"where supported by the source. Introduce no unsupported claims. 2-4 sentences.")
        fs,ns=fabrication_rate(S_synth); fa,na=fabrication_rate(S_agree)
        if fs is not None: fab["SYNTH"].append(fs)
        if fa is not None: fab["AGREE"].append(fa)
        print("\n"+"#"*72); print(f"### [{kind}] {title}"); print("#"*72)
        print(f"orthogonal-plausible concept (relevant but opposed to consensus): '{ortho}'")
        print(f"\n┌─ S0 (baseline) ──\n{S0[:700]}")
        print(f"\n┌─ S_SYNTH (tension/Hegelian prompt) ── fabrication={fs if fs is not None else 'NA'} ({ns} new claims)")
        print(S_synth)
        print(f"\n┌─ S_AGREE (same concept, agreeable inject — control) ── fabrication={fa if fa is not None else 'NA'} ({na} new claims)")
        print(S_agree)

    print("\n"+"="*72); print("AGGREGATE — fabrication rate (new claims NOT supported by source)"); print("="*72)
    for cond in ["SYNTH","AGREE"]:
        rs=fab[cond]
        if rs: print(f"  {cond:7s} mean fabrication rate = {np.mean(rs):.2f}  (n={len(rs)})")
    print("\nREAD WITH EYEBALLS (the real question):")
    print("  Does S_SYNTH surface a REAL stake S0 missed (genuine insight, low fabrication) —")
    print("  or a plausible-sounding FABRICATION to resolve the tension (high fabrication = worse")
    print("  than the honest coasting baseline)? Gemini calls fluent bridges 'A+ synthesis' — but")
    print("  if fabrication is high, it's a confident student MAKING THINGS UP. That fails, not passes.")
    print("  KEY: is S_SYNTH insightful-AND-faithful, or just confidently inventive?")

if __name__=="__main__":
    main()
