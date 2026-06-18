#!/usr/bin/env python3
"""
strain_gauge.py — does injecting a REAL omitted concept cost LESS semantic strain
than injecting a RANDOM/OFFTOPIC word? (Gemini's sycophancy-strain reframe of the
rewire null.)

The rewire collider found RANDOM rewired as much as REAL — but turnover conflated
"rewired because it BELONGED" (trade war slid in) with "rewired because the model
MUTILATED the story to force it in" (margarita). Strain separates them: an RLHF model
is a people-pleaser — told to work 'plankton' into an Iran story, it won't refuse, it'll
contort the text. That contortion shows up as HIGH TOKEN ENTROPY ("model fighting the
content"). A true void slides in at LOW entropy.

SENSOR (reuse ablation_engine pattern): /v1/chat/completions with logprobs+top_logprobs,
mean per-token entropy of the GENERATED summary.

CONFOUND CONTROL (critical): raw entropy is confounded by the injected word's own rarity
('margarita' is a rarer token than 'trade war' regardless of strain). So we measure
HOST-TEXT entropy — entropy of the summary's tokens EXCLUDING the injected concept's own
tokens. We want "did forcing the word in strain the REST of the text", not "is the graft rare".

CONDITIONS per Erased story: REAL / RANDOM / PRESENT / OFFTOPIC injection.
PREDICTION: strain(REAL,PRESENT) LOW (belonged/slid in); strain(RANDOM,OFFTOPIC) HIGH (forced).
  ordering holds -> sycophancy-strain is real & measurable (novel).
  strain flat -> model fluent enough to launder strain too -> null robust across BOTH
                 sensors (meaning AND fluency) -> genuine end of thread.

Local model via /v1/ (logprobs). Stream stopped.
"""
import json, os, sys, glob, re, math
import numpy as np
import requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=5
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434")
GEN_MODEL="qwen2.5:14b"     # local, exposes logprobs via /v1/
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
ABSENT_WORD={"Erased":-1,"Partial":0,"Preserved":1}
ARCH_ABSENT={"The Still Point":0,"The Unanimous Shield":1,"The Sharp Silence":-1,"The Sealed Vault":-1,
    "The Hollow Headline":-1,"The Named Erasure":-1,"The Cornering":-1,"The Quiet Cull":-1,
    "The Anonymized Drone":-1,"The Naming Battle":-1,"The Split Witness":-1,"The Sealed Chorus":-1}
OFFTOPIC_POOL=["webcam","ballet","plankton","accordion","skateboard","margarita"]

def absent_axis(seg):
    for b in seg.get("beats",[]):
        if "state_vector" in b.get("phase",""):
            t=b.get("text","")
            if "EigenChing state:" not in t: return None
            head=t.split("EigenChing state:")[1].split(".")[0]; name=head.split(",")[0].strip()
            if name in ARCH_ABSENT: return ARCH_ABSENT[name]
            w=name.split()
            if len(w)>=2 and w[1] in ABSENT_WORD: return ABSENT_WORD[w[1]]
    return None

def gen_with_entropy(prompt, exclude_word):
    """Generate a summary, return (text, host_entropy) where host_entropy is mean token
    entropy EXCLUDING tokens belonging to the injected word (the confound control)."""
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":GEN_MODEL,
            "messages":[
                {"role":"system","content":"Summarize this news story in 2-3 sentences. Stay faithful; invent nothing."},
                {"role":"user","content":prompt}],
            "max_tokens":160,"temperature":0.3,"logprobs":True,"top_logprobs":3},timeout=150)
        r.raise_for_status(); data=r.json()
        ch=data["choices"][0]
        text=ch["message"]["content"].strip()
        lp=ch.get("logprobs",{}).get("content",[])
        if not lp: return text, None, None
        ex_tokens=set(exclude_word.lower().split())
        ex_frags=[exclude_word.lower()]+exclude_word.lower().split()
        all_ent=[]; host_ent=[]
        for tok in lp:
            top=tok.get("top_logprobs",[])
            if not top: continue
            probs=[math.exp(t["logprob"]) for t in top]; s=sum(probs); probs=[p/s for p in probs]
            ent=-sum(p*math.log2(p+1e-10) for p in probs)
            all_ent.append(ent)
            tk=tok.get("token","").strip().lower()
            # exclude tokens that are (part of) the injected word
            is_graft = tk in ex_tokens or any(tk and tk in f for f in ex_frags) or any(f in tk for f in ex_frags if len(f)>3)
            if not is_graft:
                host_ent.append(ent)
        return text, (np.mean(host_ent) if host_ent else None), (np.mean(all_ent) if all_ent else None)
    except Exception as e:
        return f"[err {str(e)[:40]}]", None, None

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]
    erased=[]
    for f in sorted(SEGS,reverse=True):
        if len(erased)>=N_STORIES*3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            if absent_axis(seg)!=-1: continue
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<4: continue
            erased.append((t,list(sums.values())))
        except: continue

    rng=np.random.default_rng(0)
    agg={"REAL":[], "RANDOM":[], "PRESENT":[], "OFFTOPIC":[]}
    done=0
    for title,sums_list in erased:
        if done>=N_STORIES: break
        base=sums_list[0]
        cvecs=E(sums_list); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums_list); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        real=None
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
            real=w; break
        if not real: continue
        random_w=words[rng.integers(len(words))]
        present_words=[w for w in re.findall(r"[a-z][a-z]{4,}", base.lower()) if w not in HARD_DROP]
        present=present_words[len(present_words)//2] if present_words else "policy"
        offtopic=OFFTOPIC_POOL[done % len(OFFTOPIC_POOL)]
        inj={"REAL":real,"RANDOM":random_w,"PRESENT":present,"OFFTOPIC":offtopic}
        print("\n"+"="*70); print(f"STORY: {title[:55]}")
        print(f"  REAL='{real}' RANDOM='{random_w}' PRESENT='{present}' OFFTOPIC='{offtopic}'")
        for cond,w in inj.items():
            prompt=(f"News story: {title}\n\nEarlier summary: {base[:300]}\n\n"
                    f"Work the concept '{w}' into a tighter 2-3 sentence summary IF genuinely "
                    f"relevant (skip if not). Stay faithful; invent nothing.")
            txt,host_ent,all_ent=gen_with_entropy(prompt, w)
            used=bool(re.search(r'\b'+re.escape(w.split()[0])+r'\b', txt.lower()))
            if host_ent is not None:
                agg[cond].append((host_ent,all_ent,used))
                print(f"  [{cond:8s}] host_entropy={host_ent:.3f} all_entropy={all_ent:.3f} used={int(used)}")
            else:
                print(f"  [{cond:8s}] (no logprobs returned)")
        done+=1

    print("\n"+"="*70); print("AGGREGATE — mean SEMANTIC STRAIN (host-text token entropy)"); print("="*70)
    print(f"{'cond':10s} {'host_entropy':>13s} {'all_entropy':>12s} {'acceptance':>11s} {'n':>4s}")
    for cond in ["REAL","RANDOM","PRESENT","OFFTOPIC"]:
        rs=agg[cond]
        if not rs: print(f"{cond:10s}  (none)"); continue
        print(f"{cond:10s} {np.mean([r[0] for r in rs]):>13.3f} {np.mean([r[1] for r in rs]):>12.3f} "
              f"{np.mean([r[2] for r in rs]):>11.2f} {len(rs):>4d}")
    print("\nVERDICT:")
    print(" strain(REAL,PRESENT) LOW < strain(RANDOM,OFFTOPIC) HIGH -> sycophancy-strain is REAL")
    print("   (true voids slide in cheap; forced words contort the host text -> high entropy)")
    print(" strain FLAT across conditions -> model fluent enough to launder strain too ->")
    print("   NULL robust across BOTH sensors (meaning + fluency) -> end of thread, clean stop")
    print(" Watch: does host_entropy SEPARATE real from offtopic? that's the whole question.")
    print(" Sanity: OFFTOPIC (plankton/ballet) SHOULD be highest strain if the gauge works.")

if __name__=="__main__":
    main()
