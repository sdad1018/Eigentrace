#!/usr/bin/env python3
"""
summary_plus.py — the ABSENT-BUT-ADJACENT protocol (ChatGPT's spec), built as a TEST.

The night's resolution: high-similarity voids are "already-covered" (inject -> ~0 new
content); the band that DROVE coherent expansion was PLAUSIBLE/medium-relevance concepts.
So Summary Plus is redefined to target that survivor band: Absent-but-Adjacent.

V(c) void score (the entire model — no metaphysics):
  r(c) = cos(E(c), E(source))           source relevance
  a(c) = 1 - cos(E(c), E(S0))           summary absence
  band = 1 - |r(c) - mu|                plausibility band (mu~0.55) — kills BOTH
                                        margarita (low r) AND already-covered (high r)
  V(c) = a(c) * r(c) * band             rank candidates, take top-k

Injection = COVERAGE CONSTRAINT on regeneration (not raw-token perturbation):
  "Rewrite ensuring it addresses, where supported by the source: {void words}.
   Do not introduce claims absent from the source."

THE VALIDATION (non-negotiable, the whole point):
  PLACEBO = k off-topic candidates rarity-matched to the void words (the knife, repurposed).
  Delta_real    = Q(S_void)    - Q(S0)
  Delta_placebo = Q(S_placebo) - Q(S0)
  Summary Plus WORKS iff  Delta_real > Delta_placebo  with significance across the corpus.
  If equal -> rebuilt the margarita result, protocol is cosmetic.

Q = faithfulness + coverage (LLM judge). WATCH: if gain is just verbosity/coverage-tautology
  (void words say "cover more" -> judge rewards "more"), that's NOT improvement. We log
  faithfulness and coverage SEPARATELY and watch length, so verbosity can't masquerade as quality.

Local (gen + judge via qwen) + GPU embeds. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np, requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=8
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
MU=0.55; K=3
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

def llm(prompt, mt=200, temp=0.2):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return ""

def judge(source, summary):
    """Q = faithfulness + coverage, scored 0-10 each by the model. Returns (faith, cov)."""
    p=(f"Source:\n{source[:1800]}\n\nSummary:\n{summary}\n\n"
       f"Score this summary on two axes, 0-10 each:\n"
       f"FAITHFULNESS: are all claims supported by the source (no invention)?\n"
       f"COVERAGE: does it capture the source's most important points?\n"
       f"Reply EXACTLY as: FAITH=<n> COV=<n>  (integers, nothing else)")
    out=llm(p, mt=20, temp=0.0)
    f=re.search(r"FAITH=(\d+)", out); c=re.search(r"COV=(\d+)", out)
    return (int(f.group(1)) if f else None, int(c.group(1)) if c else None)

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words; widx={w:i for i,w in enumerate(words)}

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]
    stories=[]
    for f in sorted(SEGS,reverse=True):
        if len(stories)>=N_STORIES*2: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<400: continue
            stories.append((t,list(sums.values())[0],a["source_body"][:2200]))
        except: continue

    def candidates(source):
        # LLM extraction of salient noun-phrase concepts from the SOURCE (not imagination)
        out=llm(f"List 12 short (1-3 word) key concepts/topics from this text, comma-separated, "
                f"no numbering:\n\n{source[:1800]}", mt=120, temp=0.0)
        cs=[c.strip().lower() for c in re.split(r"[,\n]", out) if 2<len(c.strip())<40]
        return list(dict.fromkeys(cs))[:14]

    real_deltas=[]; placebo_deltas=[]; rows=[]
    done=0
    for title,S0,source in stories:
        if done>=N_STORIES: break
        C=candidates(source)
        if len(C)<6: continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        r=Cv@Dv                          # source relevance
        a=1-(Cv@S0v)                     # summary absence
        band=1-np.abs(r-MU)              # plausibility band
        V=a*r*band
        order=np.argsort(-V)
        void=[C[i] for i in order if C[i] not in HARD_DROP][:K]
        # PLACEBO: off-topic (low r) candidates rarity-matched to void words via vocab index
        void_idx=[widx.get(w.split()[0],5000) for w in void]
        med_idx=int(np.median(void_idx)) if void_idx else 5000
        offpool=[C[i] for i in np.argsort(r) if r[i]<MU-0.15][:6]  # genuinely off-topic candidates
        placebo=offpool[:K] if len(offpool)>=K else [words[min(med_idx+j*50,len(words)-1)] for j in range(K)]

        def regen(concepts):
            return llm(f"News source summary task.\nSource:\n{source[:1500]}\n\nCurrent summary: {S0}\n\n"
                       f"Rewrite the summary (2-3 sentences) ensuring it addresses, WHERE SUPPORTED BY THE "
                       f"SOURCE, these dimensions: {', '.join(concepts)}. Do NOT introduce claims absent "
                       f"from the source. Stay concise.", mt=160, temp=0.3)
        Sv=regen(void); Sp=regen(placebo)
        if not Sv or not Sp: continue
        f0,c0=judge(source,S0); fv,cv=judge(source,Sv); fp,cp=judge(source,Sp)
        if None in (f0,c0,fv,cv,fp,cp): continue
        Q0=f0+c0; Qv=fv+cv; Qp=fp+cp
        dr=Qv-Q0; dp=Qp-Q0
        real_deltas.append(dr); placebo_deltas.append(dp)
        rows.append((title[:40],void,dr,dp,(f0,c0),(fv,cv),(fp,cp),len(S0.split()),len(Sv.split())))
        print(f"\n{title[:50]}")
        print(f"  void(absent-adjacent)={void}")
        print(f"  placebo(off-topic)   ={placebo}")
        print(f"  Q0(f,c)={f0},{c0}  Qvoid={fv},{cv}  Qplacebo={fp},{cp}")
        print(f"  Δreal={dr:+d}  Δplacebo={dp:+d}   len: S0={len(S0.split())} Svoid={len(Sv.split())}")
        done+=1

    print("\n"+"="*68); print("AGGREGATE — does Δreal beat Δplacebo? (the only question)"); print("="*68)
    if real_deltas:
        dr=np.array(real_deltas,float); dp=np.array(placebo_deltas,float)
        diff=dr-dp
        print(f"  n={len(dr)}")
        print(f"  mean Δreal    = {dr.mean():+.3f}  (faithfulness+coverage gain from void words)")
        print(f"  mean Δplacebo = {dp.mean():+.3f}  (gain from rarity-matched off-topic control)")
        print(f"  mean (Δreal - Δplacebo) = {diff.mean():+.3f}")
        # paired test
        if len(diff)>1 and diff.std()>0:
            t_stat=diff.mean()/(diff.std(ddof=1)/np.sqrt(len(diff)))
            wins=int((diff>0).sum())
            print(f"  paired t≈{t_stat:.2f}   void beat placebo in {wins}/{len(diff)} stories")
        print("\nVERDICT:")
        print("  Δreal > Δplacebo, consistent + significant -> Summary Plus is REAL (absent-but-adjacent works)")
        print("  Δreal ≈ Δplacebo -> cosmetic; rebuilt the margarita result. Dead, honestly.")
        print("  WATCH: if Δreal is all COVERAGE and no FAITHFULNESS (and Svoid much longer than S0),")
        print("         it's verbosity/coverage-tautology, NOT quality. Check the per-story f,c split + lengths.")
    else:
        print("  no valid rows — check decoy/judge parsing")

if __name__=="__main__":
    main()
