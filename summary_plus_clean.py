#!/usr/bin/env python3
"""
summary_plus_clean.py — Summary Plus, TWO BUGS FIXED, pointed at the FAKES (out-of-domain).

Bugs in the prior run (both faked Δreal≈Δplacebo):
  BUG 1 — placebo CONTAMINATION: placebo[0] was the SAME word as void[0] almost every time
          (drawn from the same candidate list). The control shared the real injection's
          strongest word. FIX: placebo must share ZERO tokens with the void set, and be
          genuinely off-topic, rarity-matched via vocab index.
  BUG 2 — LENGTH COLLAPSE: "rewrite ensuring it addresses X, stay concise" REPLACED a
          ~200-word summary with a fresh ~50-word one. Q then measured "short beats long",
          not "void improved summary". FIX: EDIT the existing summary in place, hold length
          within ~±15% of S0, so Q measures ENRICHMENT not normalization.

Protocol unchanged (ChatGPT's spec): V(c)=a(c)*r(c)*(1-|r(c)-mu|), mu=0.55, top-k absent-
but-adjacent. Inject as coverage constraint. Q = faithfulness+coverage (judge). Verdict:
Δreal > Δplacebo with significance, AND not just verbosity (length held, faithfulness holds).

TARGET: the two FAKE out-of-domain stories (internet-alive, UAP) — harshest test: no
training coast, and absent-but-adjacent must be found in genuinely novel text. Plus a few
real ERASED news stories alongside for contrast.

Local (gen+judge qwen) + GPU embeds. Stream stopped.
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
    p=(f"Source:\n{source[:1800]}\n\nSummary:\n{summary}\n\n"
       f"Score 0-10 each:\nFAITHFULNESS: all claims supported by source (no invention)?\n"
       f"COVERAGE: captures the source's most important points?\n"
       f"Reply EXACTLY: FAITH=<n> COV=<n>")
    out=llm(p, mt=20, temp=0.0)
    f=re.search(r"FAITH=(\d+)",out); c=re.search(r"COV=(\d+)",out)
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
    N=len(words)

    # ---- assemble items: the 2 fakes + a few erased news for contrast ----
    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            title=st.get("title","fake")
            sums=st.get("summaries") or st.get("model_responses") or []
            if isinstance(sums,dict): sums=list(sums.values())
            src=st.get("source_body") or st.get("source") or " ".join(sums)
            if sums: items.append(("FAKE", title, sums[0], src[:2200]))
    except Exception as e:
        print(f"(fakes load issue: {e})")
    # a few erased news for contrast
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]
    nnews=0
    for f in sorted(SEGS,reverse=True):
        if nnews>=3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<3 or not a.get("source_body") or len(a["source_body"])<400: continue
            items.append(("NEWS", t, list(sums.values())[0], a["source_body"][:2200])); nnews+=1
        except: continue

    def candidates(source):
        out=llm(f"List 12 short (1-3 word) key concepts/topics from this text, comma-separated, "
                f"no numbering:\n\n{source[:1800]}", mt=120, temp=0.0)
        cs=[c.strip().lower() for c in re.split(r"[,\n]",out) if 2<len(c.strip())<40]
        return list(dict.fromkeys(cs))[:14]

    real_d=[]; plac_d=[]
    for kind,title,S0,source in items:
        C=candidates(source)
        if len(C)<6:
            print(f"skip (few candidates): {title[:40]}"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        r=Cv@Dv; a=1-(Cv@S0v); band=1-np.abs(r-MU); V=a*r*band
        order=np.argsort(-V)
        void=[C[i] for i in order if C[i] not in HARD_DROP][:K]
        void_tokens=set(t for w in void for t in w.lower().split())

        # BUG 1 FIX: placebo shares ZERO tokens with void, genuinely off-topic, rarity-matched.
        void_idx=[widx.get(w.split()[0],8000) for w in void]
        anchor=int(np.median(void_idx)) if void_idx else 8000
        placebo=[]
        # draw off-topic vocab words near the void's rarity, sharing no token with void/source
        src_low=source.lower()
        win=0
        while len(placebo)<K and win< N:
            for j in (anchor+win, anchor-win):
                if 0<=j<N:
                    w=words[j]
                    if (w not in HARD_DROP and w not in void_tokens and w.lower() not in src_low
                        and len(w)>3 and float(E(w)[0]@Dv) < MU-0.15):  # genuinely off-topic
                        placebo.append(w)
                        if len(placebo)>=K: break
            win+=25
        if len(placebo)<K:
            print(f"skip (placebo build failed): {title[:40]}"); continue

        s0_len=len(S0.split())
        lo,hi=int(s0_len*0.85), int(s0_len*1.15)
        def regen(concepts):
            # BUG 2 FIX: EDIT in place, hold length ~constant.
            return llm(f"Source:\n{source[:1500]}\n\nHere is a summary ({s0_len} words):\n{S0}\n\n"
                       f"EDIT this summary so it also addresses, WHERE SUPPORTED BY THE SOURCE, these "
                       f"dimensions: {', '.join(concepts)}. Keep it roughly the same length "
                       f"({lo}-{hi} words). Keep everything already correct. Do NOT introduce claims "
                       f"absent from the source. Return only the edited summary.", mt=320, temp=0.3)
        Sv=regen(void); Sp=regen(placebo)
        if not Sv or not Sp: continue
        f0,c0=judge(source,S0); fv,cv=judge(source,Sv); fp,cp=judge(source,Sp)
        if None in (f0,c0,fv,cv,fp,cp): continue
        dr=(fv+cv)-(f0+c0); dp=(fp+cp)-(f0+c0)
        real_d.append((dr,kind)); plac_d.append((dp,kind))
        print(f"\n[{kind}] {title[:48]}")
        print(f"  void(absent-adjacent)={void}")
        print(f"  placebo(disjoint off-topic)={placebo}")
        print(f"  Q0={f0},{c0}  Qvoid={fv},{cv}  Qplacebo={fp},{cp}")
        print(f"  Δreal={dr:+d}  Δplacebo={dp:+d}   len: S0={s0_len} Svoid={len(Sv.split())} Splac={len(Sp.split())}")

    print("\n"+"="*68); print("AGGREGATE — clean test (disjoint placebo, length held)"); print("="*68)
    if real_d:
        dr=np.array([x[0] for x in real_d],float); dp=np.array([x[0] for x in plac_d],float)
        diff=dr-dp
        print(f"  n={len(dr)}  (fakes + {sum(1 for _,k in real_d if k=='NEWS')} news)")
        print(f"  mean Δreal={dr.mean():+.3f}  mean Δplacebo={dp.mean():+.3f}  diff={diff.mean():+.3f}")
        if len(diff)>1 and diff.std()>0:
            t=diff.mean()/(diff.std(ddof=1)/np.sqrt(len(diff)))
            print(f"  paired t≈{t:.2f}  void beat placebo in {int((diff>0).sum())}/{len(diff)}")
        # fakes specifically
        fk=[(r,p) for (r,_),(p,k) in zip(real_d,plac_d) if k=='FAKE']
        if fk:
            print(f"\n  FAKES ONLY: " + "  ".join(f"Δreal={r:+d}/Δplac={p:+d}" for r,p in fk))
        print("\nVERDICT:")
        print("  Δreal > Δplacebo consistent+significant AND length held AND faithfulness up -> REAL")
        print("  Δreal ≈ Δplacebo -> cosmetic, honest death (clean control this time)")
        print("  FAKES: did absent-but-adjacent even FIND good concepts out-of-domain, or off-topic junk?")
    else:
        print("  no valid rows")

if __name__=="__main__":
    main()
