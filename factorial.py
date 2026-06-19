#!/usr/bin/env python3
"""
factorial.py — isolate every knob. CONCEPT-TYPE x FRAMING, each axis clean.

The last runs bundled changes and we couldn't read which moved the needle. This separates:

AXIS 1 — CONCEPT SELECTION (what to inject):
  COVERED   : high-relevance bge concept (the already-covered trap — control floor)
  VOID      : bge absent-but-adjacent (a(c)*r(c)*band, mu=0.55) — the old donut band
  TFIDF_ABS : high bge-relevance to source domain INTERSECT low source TF-IDF
              (IDF over the 23k segment corpus) = genuinely domain-relevant but NOT
              foregrounded in THIS source. The "adjacent-but-absent" band done with
              lexical precision instead of bge fuzziness. (your TF-IDF pusher idea)

AXIS 2 — FRAMING (how to inject):
  AGREE  : "edit to also address X, where supported" (additive — produced LISTS)
  SYNTH  : "consensus is X but tension of [concept] — synthesize" (relational — produced
           however/despite/at-the-cost-of ARGUMENT, faithfully, in the last run)

3x2 = 6 conditions per story. Plus S0 baseline. Measures, each clean:
  fabrication  : new claims with no source-sentence support (the faithfulness knife)
  rel_structure: count of relational connectives (however/despite/while/although/yet/
                 whereas/at the cost of/even as) MINUS additive (and/also/furthermore)
                 -> proxy for "argument vs list" (the one real effect we found)
  new_content  : new content words coherent with STORY (not graft)
  length       : held ~constant by prompt

Read which CELL produces faithful + relational + content-rich. If TFIDF_ABS x SYNTH wins,
that's the combined best-of-worlds. If framing dominates regardless of concept, it's the
PROMPT not the selection. If nothing beats COVERED, cosmetic confirmed across the board.

Local. Stream stopped.
"""
import json, os, sys, glob, re, math
import numpy as np, requests
from collections import Counter

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); MODEL="qwen2.5:14b"
MU=0.55
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
REL=["however","despite","although","though","while","whereas","yet","even as","at the cost",
     "nevertheless","nonetheless","in tension","paradox","contrast","but ","rather than"]
ADD=["furthermore","additionally","also ","moreover","in addition","as well as"]
STOP=set("the a an and or but of to in on at for with as is are was were be been by from this that it its their his her they them we you i he she has have had will would can could said about after over into more most than then so not no new".split())

def llm(prompt, mt=300, temp=0.3):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=150)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"[err {e}]"

def sentences(t): return [s.strip() for s in re.split(r"(?<=[.!?])\s+",t) if len(s.strip())>15]

def build_idf():
    """IDF over the segment corpus (document frequency of each content word)."""
    df=Counter(); ndoc=0
    for f in glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")[:4000]:
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{})
            body=(a.get("source_body","") or "")[:1500]
            toks=set(w for w in re.findall(r"[a-z]{4,}",body.lower()) if w not in STOP)
            if not toks: continue
            for w in toks: df[w]+=1
            ndoc+=1
        except: continue
    return df, max(ndoc,1)

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    print("building IDF over segment corpus...")
    DF,NDOC=build_idf(); print(f"  IDF from {NDOC} docs, {len(DF)} terms")

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

    def rel_score(text):
        tl=" "+text.lower()+" "
        return sum(tl.count(x) for x in REL) - sum(tl.count(x) for x in ADD)
    def new_content_story_coherent(S, S0, w, story_cen):
        base=set(re.findall(r"[a-z]{4,}",S0.lower()))
        wt=set(w.lower().split())
        new=[x for x in re.findall(r"[a-z]{4,}",S.lower()) if x not in base and x not in wt and x not in STOP]
        if not new: return 0
        # coherent = closer to story than to graft
        wv=E(w)[0]; cnt=0
        for x in set(new):
            xv=E(x)[0]
            if float(xv@story_cen) > float(xv@wv): cnt+=1
        return cnt
    def fabrication(S, S0, src_vecs):
        new=[s for s in sentences(S) if s.lower() not in S0.lower()]
        if not new or src_vecs is None: return 0.0
        nv=E(new); m=(nv@src_vecs.T).max(axis=1)
        return float((m<0.55).sum())/len(new)

    cells=["COVERED","VOID","TFIDF_ABS"]
    frames=["AGREE","SYNTH"]
    agg={f"{c}.{fr}":{"fab":[],"rel":[],"new":[]} for c in cells for fr in frames}

    for kind,title,S0,source in items:
        cand_raw=llm(f"List 16 short (1-3 word) concepts related to this story's domain, including "
                     f"different angles and sub-themes. Comma-separated:\n\n{source[:1600]}", mt=160, temp=0.3)
        C=[c.strip().lower() for c in re.split(r"[,\n]",cand_raw) if 2<len(c.strip())<40]
        C=list(dict.fromkeys([c for c in C if c not in HARD_DROP]))[:16]
        if len(C)<6: print(f"skip: {title[:40]}"); continue
        Dv=E(source)[0]; S0v=E(S0)[0]; Cv=E(C)
        rel=Cv@Dv; absn=1-(Cv@S0v); band=1-np.abs(rel-MU)
        story_cen=E([title,source[:800],S0]).mean(0); story_cen/=np.linalg.norm(story_cen)+1e-8
        src_vecs=E(sentences(source)) if sentences(source) else None
        srclow=source.lower(); srctf=Counter(re.findall(r"[a-z]{4,}",srclow))

        def tfidf_of(c):
            # mean tf-idf of the concept's tokens IN THIS SOURCE
            vals=[]
            for tok in c.split():
                tf=srctf.get(tok,0)
                idf=math.log(NDOC/(1+DF.get(tok,0)))
                vals.append(tf*idf)
            return np.mean(vals) if vals else 0.0

        # AXIS 1 concept selection
        covered = C[int(np.argmax(rel))]                              # most relevant = central
        void_score=absn*rel*band; voidc = C[int(np.argmax(void_score))]
        # TFIDF_ABS: high bge-relevance to domain (rel>0.4) AND low source tf-idf (not foregrounded)
        tfidf_vals=np.array([tfidf_of(c) for c in C])
        elig=rel>0.40
        # want high relevance, LOW source tfidf -> rank by rel * (1/(1+tfidf))
        absness=rel*(1.0/(1.0+tfidf_vals))
        absness=np.where(elig,absness,-1)
        tfidf_abs = C[int(np.argmax(absness))]

        concepts={"COVERED":covered,"VOID":voidc,"TFIDF_ABS":tfidf_abs}
        s0_len=len(S0.split()); lo,hi=int(s0_len*0.85),int(s0_len*1.15)
        print("\n"+"#"*70); print(f"### [{kind}] {title[:50]}")
        print(f"  COVERED='{covered}' (tfidf={tfidf_of(covered):.2f})  VOID='{voidc}'  TFIDF_ABS='{tfidf_abs}' (tfidf={tfidf_of(tfidf_abs):.2f})")
        for cname,w in concepts.items():
            for fr in frames:
                if fr=="AGREE":
                    p=(f"Source:\n{source[:1400]}\n\nSummary:\n{S0}\n\nEDIT to also address '{w}' where "
                       f"supported by the source. No unsupported claims. ~{lo}-{hi} words. Return only summary.")
                else:
                    p=(f"Source:\n{source[:1400]}\n\nConsensus summary:\n{S0}\n\nAn alternative analysis "
                       f"suggests this story is also governed by the tension of '{w}'. Rewrite to SYNTHESIZE "
                       f"the opposing stakes. No claims unsupported by the source. ~{lo}-{hi} words. Return only summary.")
                S=llm(p)
                fb=fabrication(S,S0,src_vecs); rs=rel_score(S); nc=new_content_story_coherent(S,S0,w,story_cen)
                k=f"{cname}.{fr}"; agg[k]["fab"].append(fb); agg[k]["rel"].append(rs); agg[k]["new"].append(nc)
                print(f"  [{k:18s}] fab={fb:.2f} rel_struct={rs:+d} new_story={nc}  '{S[:90]}...'")

    print("\n"+"="*72); print("AGGREGATE FACTORIAL — concept x framing (each axis isolated)"); print("="*72)
    print(f"{'cell':20s} {'fabric':>7s} {'rel_struct':>11s} {'new_story':>10s} {'n':>4s}")
    for c in cells:
        for fr in frames:
            k=f"{c}.{fr}"; d=agg[k]
            if d["fab"]:
                print(f"{k:20s} {np.mean(d['fab']):>7.2f} {np.mean(d['rel']):>+11.2f} {np.mean(d['new']):>10.1f} {len(d['fab']):>4d}")
    print("\nREAD:")
    print("  rel_struct UP = argument not list (the real effect from last run — does SYNTH drive it?)")
    print("  Does FRAMING (SYNTH>AGREE) dominate regardless of concept? -> it's the PROMPT.")
    print("  Does CONCEPT (TFIDF_ABS>VOID>COVERED) dominate regardless of framing? -> it's SELECTION.")
    print("  Does TFIDF_ABS x SYNTH win on rel_struct + new_story at fab~0? -> combined best-of-worlds.")
    print("  All ~equal at low rel_struct -> cosmetic, framing+selection both inert. Honest end.")

if __name__=="__main__":
    main()
