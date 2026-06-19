#!/usr/bin/env python3
"""
stage1_panel.py — STAGE 1: 5-API-model consensus relabel of the top-60 void/target words
per chartable domain, with centroid-density agreement (tau=0.85, >=4/5), non-template gate,
batched 20 words/call. Checkpoints, picks the delegate, then STOPS for inspection.

Decisions locked with Sean:
  - panel = 5 API models only (locals echoed the template -> fake agreement). Honest caveat:
    these share RLHF lineage, so it's "5 frontier models agree", not 5 independent observers.
  - agreement = embed each model's role-string -> centroid -> a role counts if cosine>=TAU
    AND passes the non-template gate; accept the canonical role if >=4 of 5 clean roles agree.
  - batched 20 words/call (the original relabel_batch chunking) -> ~15 calls/domain not 300.
  - prompt = original KEEP/CATEGORY/DROP + an explicit anti-echo line.
  - top 60 per domain get the panel; the tail later goes to the delegate (most-frequently-close model).
  - reads corpus_void_target.json (the per-story derive() output) for the word lists.

Run: needs API keys (.env) + the embedder (GPU). Broadcast can stay down; no locals used here.
"""
import os, sys, json, re, time
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
from geometric_engine import get_engine

TAU=0.85; MIN_AGREE=4; TOPN=60; CHUNK=20
CKPT="stage1_checkpoint.json"

# ---- the 5 API callers (clean panel) ----
API=C.API_PATIENTS   # {name: fn(messages)->str}
API_NAMES=list(API.keys())

# ---- hardened batch relabel prompt (original + anti-echo line) ----
def batch_prompt(words):
    listing="\n".join(f"  {j+1}. {w}" for j,w in enumerate(words))
    return (f"These are concepts AI news summaries often OMIT, surfaced from a frozen embedding space. "
            f"For EACH numbered item answer 'N. <action>':\n"
            f"KEEP <term> — durable concept (e.g. 'civilian casualties','arms deal','regime change').\n"
            f"CATEGORY <label> — STALE named person/org/place -> its durable ROLE "
            f"(e.g. 'rouhani' -> 'an Iranian president'). A fillable role, not a bare generic.\n"
            f"DROP — pure noise, ticker, handle, not a real concept.\n\n"
            f"IMPORTANT: Answer about the ACTUAL word given. Do NOT echo the literal placeholders "
            f"'<term>' or '<label>', and do NOT repeat the examples above — give the real role for each word.\n\n"
            f"{listing}\n\n"
            f"Answer one line per item: N. KEEP <term>  /  N. CATEGORY <label>  /  N. DROP")

TEMPLATE_JUNK=["<term>","<label>","keep <","category <","civilian casualties','arms deal",
               "n. keep","n. category","/ category","/ drop"]
def is_template_junk(role):
    if not role: return True
    rl=role.lower().strip()
    if rl in ("drop","(drop)","keep","category"): return True
    return any(j in rl for j in TEMPLATE_JUNK)

def parse_batch(raw, words):
    """Map model's numbered answers back to words. Returns {word: role or None}."""
    out={w:None for w in words}
    for line in (raw or "").splitlines():
        m=re.match(r'\s*(\d+)\.\s*(KEEP|CATEGORY|DROP)\b\s*(.*)', line, re.I)
        if not m: continue
        j=int(m.group(1))-1
        if not (0<=j<len(words)): continue
        act=m.group(2).lower(); lab=m.group(3).strip().strip('.').strip()
        if act=="drop": out[words[j]]="(drop)"
        elif act=="keep": out[words[j]]=lab or words[j]
        else: out[words[j]]=lab or words[j]   # category -> role label
    return out

def call_api(name, prompt):
    try:
        r=API[name]([{"role":"user","content":prompt}])
        return r or ""
    except Exception as e:
        return f"(ERR {type(e).__name__}: {e})"

def main():
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    data=json.load(open("corpus_void_target.json"))
    # build the word set: top-60 from void_overall + target_overall + per chartable domain
    chartable=["war","other_conflict","general","iran_war"]  # iran_war via void_iran/target_iran
    wordset=[]
    def add(words):
        for w in words:
            if w not in wordset: wordset.append(w)
    add(list(data["void_overall"].keys())[:TOPN])
    add(list(data["target_overall"].keys())[:TOPN])
    for dom in ["war","other_conflict","general"]:
        if dom in data.get("void_by_dom",{}):   add(list(data["void_by_dom"][dom].keys())[:TOPN])
        if dom in data.get("target_by_dom",{}): add(list(data["target_by_dom"][dom].keys())[:TOPN])
    add(list(data.get("void_iran",{}).keys())[:TOPN])
    add(list(data.get("target_iran",{}).keys())[:TOPN])
    print(f"distinct words for the 5-model panel: {len(wordset)}", flush=True)

    # resume from checkpoint if present
    answers={n:{} for n in API_NAMES}   # name -> {word: role}
    done_chunks=set()
    if os.path.exists(CKPT):
        ck=json.load(open(CKPT))
        answers=ck.get("answers",answers); done_chunks=set(tuple(c) for c in ck.get("done_chunks",[]))
        print(f"[resumed checkpoint: {sum(len(v) for v in answers.values())} answers cached]", flush=True)

    chunks=[wordset[i:i+CHUNK] for i in range(0,len(wordset),CHUNK)]
    total_calls=0
    for ci,chunk in enumerate(chunks):
        for name in API_NAMES:
            key=(ci,name)
            if key in done_chunks: continue
            raw=call_api(name, batch_prompt(chunk))
            if raw.startswith("(ERR"):
                print(f"  chunk {ci} {name}: {raw[:60]}", flush=True)
            parsed=parse_batch(raw, chunk)
            answers[name].update({w:r for w,r in parsed.items() if r is not None})
            done_chunks.add(key); total_calls+=1
            time.sleep(0.3)
        # checkpoint after each chunk (all 5 models)
        json.dump({"answers":answers,"done_chunks":[list(c) for c in done_chunks]},
                  open(CKPT,"w"))
        print(f"  chunk {ci+1}/{len(chunks)} done ({total_calls} calls so far)", flush=True)

    # ---- per-word centroid-density agreement ----
    print(f"\n[computing centroid-density agreement, tau={TAU}, need >={MIN_AGREE}/5]\n", flush=True)
    accepted={}; literal=[]; model_hits={n:0 for n in API_NAMES}
    detail=[]
    for w in wordset:
        roles={n:answers[n].get(w) for n in API_NAMES}
        clean=[(n,r) for n,r in roles.items()
               if r and r!="(drop)" and not r.startswith("(ERR") and not is_template_junk(r)]
        if len(clean)<MIN_AGREE:
            literal.append(w); detail.append((w,"LITERAL",len(clean),None)); continue
        names=[n for n,_ in clean]; strs=[r for _,r in clean]
        V=E(strs); centroid=V.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        cos=V@centroid
        within=[(names[i],strs[i],float(cos[i])) for i in range(len(clean)) if cos[i]>=TAU]
        if len(within)>=MIN_AGREE:
            # canonical role = the within-cluster string closest to centroid
            best=max(within,key=lambda x:x[2]); role=best[1]
            accepted[w]=role
            for n,_,_ in within: model_hits[n]+=1
            detail.append((w,role,len(within),round(best[2],3)))
        else:
            literal.append(w); detail.append((w,"LITERAL(scatter)",len(within),None))

    # ---- pick the delegate: model most often in accepting clusters ----
    delegate=max(model_hits,key=model_hits.get) if any(model_hits.values()) else API_NAMES[0]

    print("="*72); print(f"ACCEPTED RELABELS: {len(accepted)} | LITERAL: {len(literal)}"); print("="*72)
    for w,role,k,c in detail:
        if role.startswith("LITERAL"):
            print(f"  [{role:<16}] {w}  (clean/within<{MIN_AGREE})")
        else:
            print(f"  {w:<22} -> {role!r}   ({k}/5 agree, dens {c})")
    print(f"\nmodel agreement hits (times in accepting cluster): {model_hits}")
    print(f"DELEGATE (most frequently close): {delegate}")

    json.dump({"tau":TAU,"min_agree":MIN_AGREE,"accepted":accepted,"literal":literal,
               "model_hits":model_hits,"delegate":delegate,"detail":detail,
               "note":"5 API models, shared RLHF lineage; centroid-density agreement; non-template gated"},
              open("stage1_result.json","w"),indent=2)
    print(f"\nwrote stage1_result.json  (+ checkpoint {CKPT})")
    print("\n*** STAGE 1 COMPLETE — inspect accepted/literal + delegate BEFORE running the tail pass ***")

if __name__=="__main__": main()
