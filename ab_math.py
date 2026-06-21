#!/usr/bin/env python3
"""
ab_math.py — the TRANSPARENCY experiment.

Unlike keeper_v3 (which hid the mechanism: "the geometry circled X, treat as pointer"),
this tells the model the HONEST PROVENANCE of the words: SVD on bge-large, here are the
latent regions near your story, I'm opening these spaces for you to explore — not asserting
facts. Hypothesis: metacognitive transparency reframes the words from candidate-claims (which
trip the faithfulness gate) to exploration-directions (which the gate needn't fire on), and
may DISSOLVE the ghost-assertion problem seen in keeper_v3.

TWO sub-variants (the only difference is the architecture self-reference):
  AB_MATH_ARCH  : "you likely share similar bge architecture; these words mark latent regions
                   YOUR OWN representations place near this story"
  AB_MATH_PLAIN : "these words mark latent regions near this story" (method-transparent, no
                   architecture claim)

Both: restore type-A dropped facts AS FACT, present type-B SVD words as latent-space openers.

API MODELS ONLY (the 2 weak locals polluted keeper_v3's judging + did the ghost-asserting).
All 6 shape stories. K generations (KGEN env, default 5). Saves verbatim incrementally.
Compare against the full keeper_v3 print (A_BASE/C_GENERIC/E_SEED/E_SEED_A/E_SEED_B/E_SEED_AB)
already in terminal — no baselines re-run here.

Reuses keeper_v3's exact derive_channels (same type-A/B/C split, same NER, same IDF) by
importing it, so the words fed are IDENTICAL to keeper_v3 — only the FRAMING differs.
"""
import os, sys, json, re, time, random
import numpy as np
from collections import defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
# reuse keeper_v3's derivation so the WORDS are identical, only FRAMING changes
import confront_keeper_v3 as KV3

K=int(os.getenv("KGEN","5"))
SMOKE=os.getenv("SMOKE","")=="1"
SYS=KV3.SYS
STORIES=KV3.STORIES
API_ONLY=list(C.API_PATIENTS.keys())   # ChatGPT, Claude, Gemini, DeepSeek, Grok

SEEDQ="Summarize this in 3-4 sentences:\n\n"

def mt(patient, messages):
    # API only here
    return C.API_PATIENTS[patient](messages)

def build_clauses(type1, actors, targets):
    """Type-A restoration bits (as FACT) + the type-B SVD word list (as latent openers)."""
    a_bits=[]
    if type1: a_bits.append(f"'{type1[0]}'")
    if len(type1)>1: a_bits.append(f"'{type1[1]}'")
    if actors: a_bits.append(f"'{actors[0][0]}'")
    restore = ""
    if a_bits:
        restore = ("First, restore these specific facts your summary dropped, framed exactly as the "
                   "source presents them with no added characterization: " + ", ".join(a_bits) + ". ")
    svd_words = ", ".join(targets) if targets else ""
    return restore, svd_words

def arch_clause(svd_words):
    return (f"Second — and I want to be methodologically transparent about this — I ran SVD on "
            f"bge-large-en-v1.5 embeddings of this story and derived these words: {svd_words}. "
            f"You likely share a similar embedding architecture, so these words mark latent regions "
            f"that your own internal representations place near this story. I'm showing them to you "
            f"to OPEN those latent spaces for exploration, NOT to assert any of them as fact. Some may "
            f"slot into the story very easily — but recognize that ease as geometric proximity in "
            f"embedding space, not as evidence the source supports it. Engage whichever of these latent "
            f"regions the source genuinely supports; name none of them unless the source does; invent nothing.")

def plain_clause(svd_words):
    return (f"Second — to be transparent about method — I derived these words via SVD on embeddings "
            f"of this story: {svd_words}. They mark latent regions near this story. I'm showing them to "
            f"OPEN those regions for exploration, NOT to assert any as fact. Some may slot into the story "
            f"easily — treat that ease as geometric proximity, not evidence. Engage whichever regions the "
            f"source genuinely supports; name none unless the source does; invent nothing.")

def main():
    stories = STORIES[:1] if SMOKE else STORIES
    if SMOKE: print("*** SMOKE: 1 story ***", flush=True)
    print(f"K={K}  API-only: {API_ONLY}", flush=True)

    # build the engine/vocab once via KV3's machinery by calling its derive through a tiny shim:
    # KV3.main does too much; instead replicate just the derive setup it uses.
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    try:
        DF=json.load(open("void_frequency.json")).get("global",{}); NDOCS=1659.0
    except Exception:
        DF={}; NDOCS=1659.0
    def idf(w): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0
    REL_THRESH=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD_DROP=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

    def derive_channels(src, summaries):
        anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(summaries).lower(); srcl=src.lower()
        t1=[]; t2=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
            in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
            (t1 if in_src else t2).append(w)
        void=[]; target=[]
        for w in t2:
            try:
                if KV3.is_named_entity(w): target.append(w)
                else: void.append(w)
            except Exception:
                void.append(w)
        target_ranked=sorted(target, key=lambda w:-idf(w))[:6]
        return t1[:6], target_ranked

    all_results=[]
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72, flush=True)
        src=st["source"]
        cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print("  consensus<3, skip"); continue
        t1w, target_w = derive_channels(src, cons)
        actors = KV3.ner_actors_dropped(src, cons)
        print(f"  type-A content:{t1w} actors:{actors}")
        print(f"  type-B SVD words:{target_w}", flush=True)
        restore, svd_words = build_clauses(t1w, actors, target_w)

        rows=[]
        for p in API_ONLY:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
                    arch = mt(p, pre+[{"role":"user","content":restore+arch_clause(svd_words)}]) or ""
                    plain= mt(p, pre+[{"role":"user","content":restore+plain_clause(svd_words)}]) or ""
                    gens.append({"A_BASE":base,"AB_MATH_ARCH":arch,"AB_MATH_PLAIN":plain})
                except Exception as e:
                    print(f"    {p} gen{k} ERR {e}", flush=True)
            rows.append({"patient":p,"gens":gens})
            print(f"  {p:<10} {len(gens)}/{K} gens", flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"type1":t1w,"actors":actors,
                            "svd_words":target_w,"restore":restore,"source":src,"rows":rows})
        json.dump(all_results,open("ab_math_results.json","w"),indent=2)
        print(f"  [saved {len(all_results)} stories]", flush=True)

    # ---- blind panel, API judges only, 3 arms (base + 2 transparent variants) ----
    print("\n"+"="*72); print("BLIND PANEL (API judges only, 3 arms, shuffled)"); print("="*72, flush=True)
    ARMS=["A_BASE","AB_MATH_ARCH","AB_MATH_PLAIN"]
    def judge(src,texts):
        order=ARMS[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(ARMS)))
        p=(f"Source text:\n{src[:1400]}\n\n{len(ARMS)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
           f"(true to source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY one line per "
           f"summary:\nSummary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(ARMS)})")
        agg=defaultdict(lambda: defaultdict(list))
        for jn in API_ONLY:
            try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
            except Exception: out=""
            for cond,d in C.parse_scores(out or "", order).items():
                for m,v in d.items(): agg[cond][m].append(v)
        return agg
    panel=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for row in r["rows"]:
            for g in row["gens"]:
                if all(g.get(a) for a in ARMS):
                    a=judge(r["source"],g)
                    for cond,d in a.items():
                        for m,vs in d.items(): panel[cond][m].extend(vs)
    mets=["insight","faith","action","trust","keep"]
    print(f"  {'cond':14s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ARMS:
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:14s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}", flush=True)
    if panel["A_BASE"]["insight"]:
        pooled=np.std([v for cc in ARMS for v in panel[cc]["insight"]]) or 1
        b=tbl["A_BASE"]
        print("\n  vs A_BASE (insight σ / faith Δ):", flush=True)
        for c in ["AB_MATH_ARCH","AB_MATH_PLAIN"]:
            print(f"    {c:14s} insight {(tbl[c][0]-b[0])/pooled:+.2f}σ  faith {tbl[c][1]-b[1]:+.2f}", flush=True)
        print(f"\n  ARCH vs PLAIN: faith {tbl['AB_MATH_ARCH'][1]-tbl['AB_MATH_PLAIN'][1]:+.2f} | "
              f"insight {tbl['AB_MATH_ARCH'][0]-tbl['AB_MATH_PLAIN'][0]:+.2f}")
        print("  COMPARE these faith/insight to keeper_v3's E_SEED_AB (faith 3.66, ins 3.10) in your terminal.")
        print("  -> does TRANSPARENCY beat the opaque pointer framing? does ARCH-self-reference matter?")

    json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in ARMS}},open("ab_math_panel.json","w"),indent=2)
    print("\nwrote ab_math_results.json (verbatim) + ab_math_panel.json")
    print("*** READ VERBATIM — does telling the model the SVD provenance change ghost-handling? ***")

if __name__=="__main__": main()
