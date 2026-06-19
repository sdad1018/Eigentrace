#!/usr/bin/env python3
"""
summary_plus_v3.py — bugs fixed AND placebo-build made fast. Fakes WILL run this time.

Fixes carried from v2 (both confirmed working on the 1 story that ran):
  BUG 1 (placebo contamination): disjoint from void. KEPT.
  BUG 2 (length collapse): edit-in-place, length held (S0=283 -> Svoid=265, confirmed). KEPT.
NEW FIX:
  BUG 3 (placebo build hung the run): the old code did per-word E(w) embedding in a widening
  vocab window — hundreds of GPU calls/story, strangled the run at n=1, fakes never reached.
  FIX: placebo = the LOWEST-relevance candidates (off-topic), which we ALREADY computed as
  r=Cv@Dv. No new embeddings. Disjoint-token enforced. Instant. Fakes run.

Protocol (ChatGPT spec): V(c)=a(c)*r(c)*(1-|r(c)-mu|), mu=0.55, top-k absent-but-adjacent.
Edit-in-place injection (length held). Q=faithfulness+coverage judge. Δreal vs Δplacebo.

TARGET: 2 FAKES (internet-alive, UAP) + 3 erased news. Local. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np, requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
MU=0.55; K=3
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

def llm(prompt, mt=200, temp=0.2):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

def judge(source, summary):
    out=llm(f"Source:\n{source[:1800]}\n\nSummary:\n{summary}\n\nScore 0-10 each:\n"
            f"FAITHFULNESS: all claims supported by source?\nCOVERAGE: captures key points?\n"
            f"Reply EXACTLY: FAITH=<n> COV=<n>", mt=20, temp=0.0)
    f=re.search(r"FAITH=(\d+)",out); c=re.search(r"COV=(\d+)",out)
    return (int(f.group(1)) if f else None, int(c.group(1)) if c else None)

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
    except Exception as e:
        print(f"(fakes load issue: {e})")
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]; nnews=0
    for f in sorted(SEGS,reverse=True):
        if nnews>=3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<400: continue
            items.append(("NEWS", t, list(sums.values())[0], a["source_body"][:2200])); nnews+=1
        except: continue
    print(f"items queued: {[k for k,_,_,_ in items]}")

    def candidates(source):
        out=llm(f"List 12 short (1-3 word) key concepts/topics from this text, comma-separated, "
                f"no numbering:\n\n{source[:1800]}", mt=120, temp=0.0)
        cs=[c.strip().lower() for c in re.split(r"[,\n]",out) if 2<len(c.strip())<40]
        return list(dict.fromkeys(cs))[:14]

    real_d=[]; plac_d=[]
    for kind,title,S0,source in items:
        C=candidates(source)
        if len(C)<6: print(f"skip (few candidates): {title[:40]}"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)          # ONE embed of candidates, reused
        r=Cv@Dv; a=1-(Cv@S0v); band=1-np.abs(r-MU); V=a*r*band
        order=np.argsort(-V)
        void=[C[i] for i in order if C[i] not in HARD_DROP][:K]
        void_tokens=set(t for w in void for t in w.lower().split())
        # BUG 3 FIX: placebo = lowest-relevance candidates (already computed r), disjoint from void
        off_order=np.argsort(r)   # most off-topic first
        placebo=[]
        for i in off_order:
            w=C[i]
            if w in HARD_DROP: continue
            if any(tok in void_tokens for tok in w.lower().split()): continue
            placebo.append(w)
            if len(placebo)>=K: break
        if len(placebo)<K: print(f"skip (placebo<{K}): {title[:40]}"); continue

        s0_len=len(S0.split()); lo,hi=int(s0_len*0.85),int(s0_len*1.15)
        def regen(concepts):
            return llm(f"Source:\n{source[:1500]}\n\nSummary ({s0_len} words):\n{S0}\n\n"
                       f"EDIT this summary so it ALSO addresses, WHERE SUPPORTED BY THE SOURCE: "
                       f"{', '.join(concepts)}. Keep ~same length ({lo}-{hi} words), keep what's "
                       f"correct, introduce NO claims absent from source. Return only the summary.",
                       mt=320, temp=0.3)
        Sv=regen(void); Sp=regen(placebo)
        if not Sv or not Sp: continue
        f0,c0=judge(source,S0); fv,cv=judge(source,Sv); fp,cp=judge(source,Sp)
        if None in (f0,c0,fv,cv,fp,cp): print(f"skip (judge parse): {title[:40]}"); continue
        dr=(fv+cv)-(f0+c0); dp=(fp+cp)-(f0+c0)
        real_d.append((dr,kind)); plac_d.append((dp,kind))
        print(f"\n[{kind}] {title[:48]}")
        print(f"  void(absent-adjacent)={void}")
        print(f"  placebo(off-topic candidate)={placebo}")
        print(f"  Q0={f0},{c0}  Qvoid={fv},{cv}  Qplacebo={fp},{cp}")
        print(f"  Δreal={dr:+d}  Δplacebo={dp:+d}   len: S0={s0_len} Sv={len(Sv.split())} Sp={len(Sp.split())}")

    print("\n"+"="*68); print("AGGREGATE — clean+fast (disjoint placebo, length held, fakes incl.)"); print("="*68)
    if real_d:
        dr=np.array([x[0] for x in real_d],float); dp=np.array([x[0] for x in plac_d],float); diff=dr-dp
        print(f"  n={len(dr)}  fakes={sum(1 for _,k in real_d if k=='FAKE')} news={sum(1 for _,k in real_d if k=='NEWS')}")
        print(f"  mean Δreal={dr.mean():+.3f}  mean Δplacebo={dp.mean():+.3f}  diff={diff.mean():+.3f}")
        if len(diff)>1 and diff.std()>0:
            t=diff.mean()/(diff.std(ddof=1)/np.sqrt(len(diff)))
            print(f"  paired t≈{t:.2f}  void beat placebo in {int((diff>0).sum())}/{len(diff)}")
        fk=[(r,p) for (r,kr),(p,kp) in zip(real_d,plac_d) if kr=='FAKE']
        if fk: print(f"  FAKES ONLY: " + "  ".join(f"Δreal={r:+d}/Δplac={p:+d}" for r,p in fk))
        print("\nVERDICT: Δreal>Δplacebo consistent+sig+length-held -> REAL | Δreal≈Δplacebo -> cosmetic")
        print("  FAKES: were the void concepts real stakes (consciousness/disclosure) or news-junk?")
    else:
        print("  no valid rows")

if __name__=="__main__":
    main()
