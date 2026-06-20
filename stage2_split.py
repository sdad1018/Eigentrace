#!/usr/bin/env python3
"""
STAGE 2: (a) delegate (Gemini) relabels the TAIL words past the top-106 panel set, then
(b) apply all roles and run the THREE-BUCKET dead-band split on the abstract-concrete axis:
       confident-void   (av > +T)     abstract stakes
       confident-target (av < -T)     concrete specifics
       ambiguous        (|av| <= T)   the fence-sitters (ieds/norad/peace deal)

Reads:  corpus_void_target.json (per-story void/target counts by domain)
        stage1_result.json      (the 93 consensus relabels + delegate=Gemini)
Writes: atlas_final.json        (void/target/ambiguous by domain, roles applied) for the charts.

Dead band T calibrated from the ieds projection: ieds=+0.026, norad=+0.002, peace deal=-0.003
all sit within +-0.04 of zero -> T=0.04 puts them in 'ambiguous' and keeps only confident words
in void/target. The role layer is the generic Stage-1 label; opens_onto is a SEPARATE Stage 3.

Delegate tail pass: needs Gemini API (.env). The split itself needs the embedder (GPU).
"""
import os, sys, json, re, time
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
from geometric_engine import get_engine

T=0.04                       # dead-band half-width (from the ieds projection)
CHUNK=20
ABSTRACT_POLES=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
CONCRETE_POLES=["strait","city","company","port","bank","border","weapon","official"]

# reuse the SAME hardened batch prompt as stage1 for the delegate tail pass
def batch_prompt(words):
    listing="\n".join(f"  {j+1}. {w}" for j,w in enumerate(words))
    return (f"These are concepts AI news summaries often OMIT, surfaced from a frozen embedding space. "
            f"For EACH numbered item answer 'N. <action>':\n"
            f"KEEP <term> — durable concept (e.g. 'civilian casualties','arms deal','regime change').\n"
            f"CATEGORY <label> — STALE named person/org/place -> its durable ROLE "
            f"(e.g. 'rouhani' -> 'an Iranian president'). A fillable role, not a bare generic.\n"
            f"DROP — pure noise, ticker, handle, not a real concept.\n\n"
            f"IMPORTANT: Answer about the ACTUAL word given. Do NOT echo the literal placeholders "
            f"'<term>' or '<label>', and do NOT repeat the examples above.\n\n{listing}\n\n"
            f"Answer one line per item: N. KEEP <term> / N. CATEGORY <label> / N. DROP")

TEMPLATE_JUNK=["<term>","<label>","keep <","category <","n. keep","n. category"]
def is_junk(r):
    if not r: return True
    rl=r.lower().strip()
    return rl in ("drop","(drop)","keep","category") or any(j in rl for j in TEMPLATE_JUNK)

def parse_batch(raw, words):
    out={w:None for w in words}
    for line in (raw or "").splitlines():
        m=re.match(r'\s*(\d+)\.\s*(KEEP|CATEGORY|DROP)\b\s*(.*)', line, re.I)
        if not m: continue
        j=int(m.group(1))-1
        if not (0<=j<len(words)): continue
        act=m.group(2).lower(); lab=m.group(3).strip().strip('.').strip()
        out[words[j]] = "(drop)" if act=="drop" else (lab or words[j])
    return out

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    data=json.load(open("corpus_void_target.json"))
    s1=json.load(open("stage1_result.json"))
    roles=dict(s1["accepted"])                 # word -> generic role
    delegate=s1.get("delegate","Gemini")
    gem=C.API_PATIENTS[delegate]

    # gather ALL distinct words across the corpus (void+target, all domains, full tails)
    allwords=[]
    def add(d):
        for w in d: 
            if w not in allwords: allwords.append(w)
    add(data["void_overall"]); add(data["target_overall"])
    for dd in (data.get("void_by_dom",{}), data.get("target_by_dom",{})):
        for dom in dd: add(dd[dom])
    add(data.get("void_iran",{})); add(data.get("target_iran",{}))

    # tail = words not already relabeled by the 5-panel and not marked literal
    panel_done=set(roles)|set(s1.get("literal",[]))
    tail=[w for w in allwords if w not in panel_done]
    print(f"total distinct words: {len(allwords)} | panel-relabeled: {len(roles)} | literal: {len(s1.get('literal',[]))} | tail for delegate: {len(tail)}", flush=True)

    # delegate relabels the tail, batched, checkpointed
    TCK="stage2_tail_ckpt.json"; tail_roles={}; done=set()
    if os.path.exists(TCK):
        ck=json.load(open(TCK)); tail_roles=ck["roles"]; done=set(ck["done"])
        print(f"[resumed tail ckpt: {len(tail_roles)} done]", flush=True)
    chunks=[tail[i:i+CHUNK] for i in range(0,len(tail),CHUNK)]
    for ci,ch in enumerate(chunks):
        if ci in done: continue
        try: raw=gem([{"role":"user","content":batch_prompt(ch)}]) or ""
        except Exception as e: raw=f"(ERR {e})"; print(f"  tail chunk {ci}: {raw[:50]}",flush=True)
        for w,r in parse_batch(raw,ch).items():
            if r and not is_junk(r) and r!="(drop)": tail_roles[w]=r
        done.add(ci); json.dump({"roles":tail_roles,"done":list(done)},open(TCK,"w"))
        print(f"  tail chunk {ci+1}/{len(chunks)} done", flush=True); time.sleep(0.3)

    # merge: panel roles win; tail fills the rest; anything still unlabeled stays literal (itself)
    allroles={**tail_roles,**roles}
    def role_of(w): return allroles.get(w,w)

    # ---- the abstract-concrete axis + three-bucket split ----
    ac=E(ABSTRACT_POLES).mean(0)-E(CONCRETE_POLES).mean(0); ac/=np.linalg.norm(ac)+1e-8
    def classify(words_counts):
        """words_counts: {word:count} -> three dicts with ROLE applied, summed by role."""
        void={}; target={}; ambig={}
        for w,cnt in words_counts.items():
            av=float(E(w)@ac)                  # split on the WORD (geometry), not its role
            disp=role_of(w)                    # but DISPLAY the durable role
            bucket = void if av>T else (target if av<-T else ambig)
            bucket[disp]=bucket.get(disp,0)+cnt
        srt=lambda d: dict(sorted(d.items(),key=lambda x:-x[1]))
        return srt(void),srt(target),srt(ambig)

    out={"dead_band_T":T,"delegate":delegate,
         "n_panel_relabeled":len(roles),"n_tail_relabeled":len(tail_roles),
         "method":"per-story derive() -> 5-model consensus role (generic, time-proof) -> abstract/concrete dead-band split (T=0.04). opens_onto is a separate Stage 3.",
         "by_domain":{}}
    for dom in ["war","other_conflict","general"]:
        if dom in data.get("void_by_dom",{}):
            merged=dict(data["void_by_dom"][dom]); 
            for w,c in data.get("target_by_dom",{}).get(dom,{}).items(): merged[w]=merged.get(w,0)+c
            v,t,a=classify(merged)
            out["by_domain"][dom]={"void":v,"target":t,"ambiguous":a,"n_stories":data["domain_counts"].get(dom)}
    # iran-specific
    iran_merged=dict(data.get("void_iran",{}))
    for w,c in data.get("target_iran",{}).items(): iran_merged[w]=iran_merged.get(w,0)+c
    v,t,a=classify(iran_merged)
    out["iran"]={"void":v,"target":t,"ambiguous":a}

    json.dump(out,open("atlas_final.json","w"),indent=2)

    # ---- print for inspection ----
    print("\n"+"="*72); print("THREE-BUCKET SPLIT (role-applied), by domain"); print("="*72)
    for dom,dd in out["by_domain"].items():
        print(f"\n### {dom} (n={dd['n_stories']}) ###")
        print(f"  VOID (abstract stakes):   {list(dd['void'].items())[:10]}")
        print(f"  TARGET (concrete):        {list(dd['target'].items())[:10]}")
        print(f"  AMBIGUOUS (fence):        {list(dd['ambiguous'].items())[:8]}")
    print(f"\n### IRAN ###")
    print(f"  VOID:   {list(out['iran']['void'].items())[:12]}")
    print(f"  TARGET: {list(out['iran']['target'].items())[:12]}")
    print(f"  AMBIG:  {list(out['iran']['ambiguous'].items())[:8]}")
    print(f"\nwrote atlas_final.json | tail relabeled {len(tail_roles)} via {delegate}")
    print("\n*** STAGE 2 COMPLETE — inspect the three buckets before charts / Stage 3 opens_onto ***")

if __name__=="__main__": main()
