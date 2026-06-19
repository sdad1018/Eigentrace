#!/usr/bin/env python3
"""
factorial_read.py — same 3x2 factorial, but PRINT FULL TEXT for human reading.
The proxy metrics (rel_struct etc.) contradicted themselves last run (COVERED.AGREE scored
HIGHEST rel_struct, TFIDF_ABS.SYNTH lowest) — the proxies are noise. Only eyeballs work.

ALSO FIXED: TF-IDF selection was picking generic category words ('war','football') because
low-source-tfidf caught "synonyms not literally in the truncated body". FIX: require the
concept's tokens to actually APPEAR in the source at least once (tf>=1) so we get
"present-but-underweighted" not "absent-generic". And use FULL source body for tf.

Prints S0 + all 6 cells in full. No scores. Read like a professor: which cell (if any)
produced a genuinely SHARPER, FAITHFUL, more INSIGHTFUL summary than S0 — vs cosmetic.
Local. Stream stopped.
"""
import json, os, sys, glob, re, math
import numpy as np, requests
from collections import Counter

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
MU=0.55
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
STOP=set("the a an and or but of to in on at for with as is are was were be been by from this that it its their his her they them we you i he she has have had will would can could said about after over into more most than then so not no new".split())

def llm(prompt, mt=300, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"[err {e}]"

def build_idf():
    df=Counter(); ndoc=0
    fs=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    for f in fs:
        if ndoc>=3000: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{})
            body=(a.get("source_body","") or "")
            toks=set(w for w in re.findall(r"[a-z]{4,}",body.lower()) if w not in STOP)
            if len(toks)<5: continue
            for w in toks: df[w]+=1
            ndoc+=1
        except: continue
    return df,max(ndoc,1)

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    print("building IDF..."); DF,NDOC=build_idf(); print(f"  IDF from {NDOC} docs")

    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            sums=st.get("summaries",[])
            if sums: items.append(("FAKE",st.get("title","fake"),sums[0]," ".join(sums)[:2200]))
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
            items.append(("NEWS",t,list(sums.values())[0],a["source_body"][:2200])); nn+=1
        except: continue

    for kind,title,S0,source in items:
        cand_raw=llm(f"List 16 short (1-3 word) concepts related to this story's domain, including "
                     f"different angles and sub-themes. Comma-separated:\n\n{source[:1600]}", mt=160, temp=0.3)
        C=[c.strip().lower() for c in re.split(r"[,\n]",cand_raw) if 2<len(c.strip())<40]
        C=list(dict.fromkeys([c for c in C if c not in HARD_DROP]))[:16]
        if len(C)<6: print(f"skip: {title[:40]}"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        rel=Cv@Dv; absn=1-(Cv@S0v); band=1-np.abs(rel-MU)
        srclow=source.lower(); srctf=Counter(re.findall(r"[a-z]{4,}",srclow))
        def tfidf_of(c):
            vals=[]
            for tok in c.split():
                tf=srctf.get(tok,0); idf=math.log(NDOC/(1+DF.get(tok,0))); vals.append(tf*idf)
            return np.mean(vals) if vals else 0.0
        covered=C[int(np.argmax(rel))]
        voidc=C[int(np.argmax(absn*rel*band))]
        # FIXED TFIDF_ABS: token must appear in source (tf>=1) AND be relevant; pick LOWEST tfidf
        # among present+relevant = "mentioned but underweighted", not "absent generic"
        tfv=np.array([tfidf_of(c) for c in C])
        present=np.array([all(srctf.get(tok,0)>=1 for tok in c.split()) for c in C])
        elig=(rel>0.42)&present&(tfv>0)
        if elig.any():
            tfidf_abs=C[[i for i in np.argsort(tfv) if elig[i]][0]]
        else:
            tfidf_abs=voidc
        concepts={"COVERED":covered,"VOID":voidc,"TFIDF_ABS":tfidf_abs}
        s0_len=len(S0.split()); lo,hi=int(s0_len*0.85),int(s0_len*1.15)
        print("\n"+"#"*74); print(f"### [{kind}] {title}"); print("#"*74)
        print(f"COVERED='{covered}'(tfidf {tfidf_of(covered):.1f})  VOID='{voidc}'  TFIDF_ABS='{tfidf_abs}'(tfidf {tfidf_of(tfidf_abs):.1f})")
        print(f"\n┌─ S0 ──────────\n{S0}")
        for cname,w in concepts.items():
            for fr in ["AGREE","SYNTH"]:
                if fr=="AGREE":
                    p=(f"Source:\n{source[:1400]}\n\nSummary:\n{S0}\n\nEDIT to also address '{w}' where "
                       f"supported. No unsupported claims. ~{lo}-{hi} words. Return only summary.")
                else:
                    p=(f"Source:\n{source[:1400]}\n\nConsensus summary:\n{S0}\n\nAn alternative analysis "
                       f"suggests this story is also governed by the tension of '{w}'. Rewrite to SYNTHESIZE "
                       f"the opposing stakes. No claims unsupported by source. ~{lo}-{hi} words. Return only summary.")
                S=llm(p)
                print(f"\n┌─ {cname}.{fr}  (concept='{w}') ──")
                print(S)
        print()

    print("\n"+"="*74)
    print("READ: for each story, is ANY cell genuinely sharper/more insightful than S0 while")
    print("staying faithful? Or are all 6 just S0 reshuffled? Compare SYNTH cells (argument?)")
    print("vs AGREE cells (list?). Does TFIDF_ABS pick a better concept than COVERED/VOID now?")

if __name__=="__main__":
    main()
