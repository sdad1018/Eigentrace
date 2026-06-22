#!/usr/bin/env python3
"""summary_plus_production.py -- THE SHIPPABLE PIPELINE. SVD raycast -> is_named_entity route
-> keep channel A (dropped facts) + C (concepts), DISCARD B (named entities) -> faithfulness synthesis.
Capitalization is NOT the scrubber (vocab is lowercased); dictionary+NER is."""
import os, sys, json, re, argparse
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
SYS=KV3.SYS
SEEDQ="Summarize this in 3-4 sentences:\n\n"
def build_engine():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t])); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    REL=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    return E,V,vt_words,REL,POOL,HARD
def derive_channels(src, summaries, eng):
    E,V,vt_words,REL,POOL,HARD=eng
    anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
    alltext=" ".join(summaries).lower(); srcl=src.lower(); type1=[]; type2=[]
    for i in top:
        w=vt_words[i]; sim=float(sims[i])
        if len(w)<4 or w in HARD or sim<REL: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
        in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl)); (type1 if in_src else type2).append(w)
    concepts=[]; discarded=[]
    for w in type2:
        try:
            if KV3.is_named_entity(w): discarded.append(w)
            else: concepts.append(w)
        except Exception: concepts.append(w)
    actors=KV3.ner_actors_dropped(src, summaries)
    return {"channel_A_facts":type1[:6],"channel_A_actors":actors,"channel_C_concepts":concepts[:8],"discarded_entities_B":discarded[:8]}
def build_prompt(ch):
    parts=[]
    if ch["channel_A_facts"] or ch["channel_A_actors"]:
        bits=[f"'{w}'" for w in ch["channel_A_facts"][:3]]+[f"'{n}'" for n,_ in ch["channel_A_actors"][:2]]
        parts.append("First, restore these source facts your summary dropped, framed exactly as the source presents them (no added characterization): "+", ".join(bits)+".")
    if ch["channel_C_concepts"]:
        parts.append(f"Then sharpen the summary by surfacing the latent stakes the source implies but your draft left out. "
            f"These conceptual directions may be relevant: {', '.join(ch['channel_C_concepts'])}. Treat them as DIRECTIONS, "
            f"not words to insert. For each, the most valuable move is often to note where the source is conspicuously SILENT "
            f"about something its own facts imply \u2014 that silence is itself observable. Engage only what the source "
            f"genuinely supports; name-check nothing; invent nothing; do not import outside analogies or historical comparisons.")
    parts.append("Produce a sharper 3-4 sentence summary that (a) restores the reframing fact, (b) reads the telling absence "
        "where the source implies more than it states, and (c) names any genuinely unresolved question as a question. Stay strictly faithful to the source.")
    return " ".join(parts)
def self_check(src, summary, model_for_check="Claude"):
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', re.sub(r'#.*?\n','',summary)) if len(s.strip())>15]
    if not sents: return None
    numbered="\n".join(f"{i+1}. {s}" for i,s in enumerate(sents))
    p=(f"SOURCE:\n{src[:1300]}\n\nSummary sentences:\n{numbered}\n\nClassify EACH sentence by content origin RELATIVE TO SOURCE:\n"
       f" O=Observation(in source) I=Inference(grounded reasoning beyond source) A=Analogy(imported outside frame) S=Speculation(no support)\n"
       f"Reply one line each:\n1: <O/I/A/S>\n... through {len(sents)}")
    try: out=C.API_PATIENTS[model_for_check]([{"role":"user","content":p}]) or ""
    except Exception: return None
    from collections import Counter
    c=Counter(m.group(1).upper() for m in re.finditer(r'^\s*\d+\s*[:.]?\s*([OIAS])\b', out, re.M|re.I)); tot=sum(c.values()) or 1
    prof={k:c.get(k,0)/tot for k in "OIAS"}
    return prof, (prof["A"]<0.06 and prof["I"]>0.30)
def get_story(sid):
    for st in KV3.STORIES:
        if st["id"]==sid: return st
    return None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--story-id"); ap.add_argument("--source-file"); ap.add_argument("--model",default="Claude")
    ap.add_argument("--show-channels",action="store_true"); ap.add_argument("--no-check",action="store_true")
    a=ap.parse_args()
    if a.source_file: src=open(a.source_file).read().strip(); sid=os.path.basename(a.source_file)
    elif a.story_id:
        st=get_story(a.story_id)
        if not st: print(f"options: {[s['id'] for s in KV3.STORIES]}"); return
        src=st["source"]; sid=st["id"]
    else: print("need --story-id or --source-file"); return
    print(f"=== Summary Plus :: {sid} :: model={a.model} ===\n",flush=True)
    eng=build_engine()
    cons=[]
    for m in C.LOCAL_PATIENTS:
        s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
        if s: cons.append(s)
    if len(cons)<3:
        b=C.API_PATIENTS[a.model]([{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
        cons=[b]
    ch=derive_channels(src,cons,eng)
    if a.show_channels:
        print("CHANNEL A facts :",ch["channel_A_facts"]); print("CHANNEL A actors:",ch["channel_A_actors"])
        print("CHANNEL C concepts (KEPT):",ch["channel_C_concepts"])
        print("CHANNEL B entities (DISCARDED, never sent):",ch["discarded_entities_B"]); print(flush=True)
    base=C.API_PATIENTS[a.model]([{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
    print("--- BASELINE SUMMARY ---"); print(base); print(flush=True)
    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
    plus=C.API_PATIENTS[a.model](pre+[{"role":"user","content":build_prompt(ch)}]) or ""
    print("--- SUMMARY PLUS (channel A + C) ---"); print(plus); print(flush=True)
    if not a.no_check:
        res=self_check(src,plus)
        if res:
            prof,gold=res
            print("--- GOLD-PROFILE SELF-CHECK ---")
            print(f"   Obs {prof['O']:.2f}  Infer {prof['I']:.2f}  Analogy {prof['A']:.2f}  Spec {prof['S']:.2f}")
            print(f"   {'GOLD-LIKE (grounded, low import)' if gold else 'OFF-TARGET (imported analogy/speculation present)'}")
if __name__=="__main__": main()
