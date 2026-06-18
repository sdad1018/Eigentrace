#!/usr/bin/env python3
"""
susceptibility_assay.py — the UNRUN test. Does injecting a BELONGING concept move the
WHOLE summary's meaning toward new STORY-COHERENT content more than a NON-belonging one?

This is NOT strain (entropy — dead) and NOT forced-prefix logprob (rarity — confounded).
It's SUSCEPTIBILITY measured on whole-output embeddings, which dodges both confounds:
fluency can stay flat, acceptance can stay 1.0, token rarity is irrelevant — we measure
how far the SUMMARY'S MEANING moved, and whether the new content points at the STORY.

ISOLATION MATRIX (ChatGPT's design), 3 matched conditions per story:
  REAL          — donut void (belongs, absent)
  PLAUSIBLE     — same shape/register, wrong topic (hard decoy, no metaphor escape)
  CONTRADICTION — same shape, opposite world-model

FOUR INDEPENDENT AXES (each means ONE thing):
  A Acceptance   = did the model use the concept (binary)
  F Fluency      = mean token entropy (we KNOW this is flat — included only as control)
  T Displacement = 1 - cos(E(S0), E(S_w))               <- whole-summary meaning shift
  N Novelty      = # new content words COHERENT WITH STORY (not the graft) / |S_w|

THE LANDMINE FIX (the whole ballgame): a downstream new word counts toward N only if it
is CLOSER to the STORY/source centroid than to the INJECTED WORD's vector. So:
  desalination -> drought (drought near story) COUNTS
  webcam -> footage (footage near webcam, not story) does NOT count
This separates "concept unlocked latent STORY structure" (real) from "graft dragged in
its own dictionary" (noise — the thing that made webcam win every prior probe).

TARGET: Gain = T * N, subject to acceptance.
HYPOTHESIS (pre-registered): E[Gain_REAL] > E[Gain_PLAUSIBLE] ~ E[Gain_CONTRADICTION].
  If REAL displaces toward story-coherent novelty MORE than non-belonging concepts ->
    susceptibility is real & measurable (the phenomenon survives, properly isolated).
  If Gain flat across conditions -> belonging doesn't drive coherent expansion ->
    phenomenon dies HONESTLY (this time on the RIGHT observable, not a bad proxy).

Local generation + GPU embeds. Stream stopped.
"""
import json, os, sys, glob, re, math
import numpy as np, requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=6
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN_MODEL="qwen2.5:14b"
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
STOP=set("the a an and or but of to in on at for with as is are was were be been being by from this that these those it its their his her they them we you i he she has have had will would can could may might said say says story news report reports according amid over into out up down new more most than then so if not no yes do does did about after before during while when where who what which".split())
ABSENT_WORD={"Erased":-1,"Partial":0,"Preserved":1}
ARCH_ABSENT={"The Still Point":0,"The Unanimous Shield":1,"The Sharp Silence":-1,"The Sealed Vault":-1,
    "The Hollow Headline":-1,"The Named Erasure":-1,"The Cornering":-1,"The Quiet Cull":-1,
    "The Anonymized Drone":-1,"The Naming Battle":-1,"The Split Witness":-1,"The Sealed Chorus":-1}

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

def llm(prompt, mt=24, temp=0.0):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":GEN_MODEL,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=120)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

def gen(prompt, exclude_word):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":GEN_MODEL,
            "messages":[{"role":"system","content":"Summarize this news story in 2-3 sentences. Stay faithful; invent nothing."},
                        {"role":"user","content":prompt}],
            "max_tokens":160,"temperature":0.3,"logprobs":True,"top_logprobs":3},timeout=150)
        r.raise_for_status(); ch=r.json()["choices"][0]
        text=ch["message"]["content"].strip(); lp=ch.get("logprobs",{}).get("content",[])
        ex=[exclude_word.lower()]+exclude_word.lower().split(); host=[]
        for tok in (lp or []):
            top=tok.get("top_logprobs",[])
            if not top: continue
            probs=[math.exp(t["logprob"]) for t in top]; s=sum(probs); probs=[p/s for p in probs]
            ent=-sum(p*math.log2(p+1e-10) for p in probs)
            tk=tok.get("token","").strip().lower()
            if not (tk in ex or any(f in tk for f in ex if len(f)>3)): host.append(ent)
        return text,(np.mean(host) if host else 0.0)
    except: return "",0.0

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words; widx={w:i for i,w in enumerate(words)}

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
            if len(sums)<4 or not a.get("source_body"): continue
            erased.append((t,list(sums.values()),a["source_body"][:2500]))
        except: continue

    def content_words(text):
        return [w for w in re.findall(r"[a-z][a-z]{3,}", text.lower()) if w not in STOP]

    agg={"REAL":[], "PLAUSIBLE":[], "CONTRADICTION":[]}
    done=0
    for title,sums_list,source in erased:
        if done>=N_STORIES: break
        base=sums_list[0]
        s0_vec=E(base)[0]
        story_cen=E([title]+sums_list+[source[:1000]]).mean(0); story_cen/=np.linalg.norm(story_cen)+1e-8
        cvecs=E(sums_list); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E(title)[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums_list); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        latent=None
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
            latent=w; break
        if not latent: continue
        plausible=llm(f"Give ONE 1-3 word geopolitical concept, same register as '{latent}', that is a real "
                      f"plausible political topic but does NOT fit a story titled '{title}'. Reply ONLY the concept.").strip().strip('.\"').lower()
        contra=llm(f"For a story titled '{title}', give ONE 1-3 word concept, same register as '{latent}', "
                   f"that CONTRADICTS the reality of the story. Reply ONLY the concept.").strip().strip('.\"').lower()
        if not plausible or not contra or len(plausible)>40 or len(contra)>40:
            print(f"skip (decoy fail): {title[:38]} p='{plausible}' c='{contra}'"); continue

        base_cw=set(content_words(base))
        print("\n"+"="*70); print(f"STORY: {title[:55]}")
        print(f"  REAL='{latent}'  PLAUSIBLE='{plausible}'  CONTRADICTION='{contra}'")
        for cond,w in {"REAL":latent,"PLAUSIBLE":plausible,"CONTRADICTION":contra}.items():
            prompt=(f"News story: {title}\n\nEarlier summary: {base[:300]}\n\n"
                    f"Work the concept '{w}' into a tighter 2-3 sentence summary IF genuinely "
                    f"relevant (skip if not). Stay faithful; invent nothing.")
            sw,fluency=gen(prompt,w)
            used=bool(re.search(r'\b'+re.escape(w.split()[0])+r'\b',sw.lower()))
            sw_vec=E(sw)[0]
            T=1.0-float(s0_vec@sw_vec)   # whole-summary displacement
            # N: new content words coherent with STORY (not graft)
            w_tokens=set(w.lower().split())
            w_vec=E(w)[0]
            new_words=[x for x in content_words(sw) if x not in base_cw and x not in w_tokens]
            story_coherent=0; total_new=len(new_words)
            for x in new_words:
                if x not in widx: continue
                xv=V[widx[x]]
                d_story=float(xv@story_cen); d_graft=float(xv@w_vec)
                if d_story > d_graft:   # points at STORY, not the injected word
                    story_coherent+=1
            denom=max(len(content_words(sw)),1)
            N=story_coherent/denom
            Gain=T*N
            agg[cond].append((used,fluency,T,N,Gain,total_new,story_coherent))
            print(f"  [{cond:13s}] A={int(used)} F={fluency:.3f} T={T:.3f} N={N:.3f} "
                  f"Gain={Gain:.4f}  (new={total_new}, story-coherent={story_coherent})")
        done+=1

    print("\n"+"="*70); print("AGGREGATE — the ISOLATION MATRIX"); print("="*70)
    print(f"{'cond':14s} {'Accept':>7s} {'Fluency':>8s} {'T(disp)':>8s} {'N(novel)':>9s} {'Gain=T*N':>9s} {'n':>4s}")
    res={}
    for cond in ["REAL","PLAUSIBLE","CONTRADICTION"]:
        rs=agg[cond]
        if not rs: print(f"{cond:14s} (none)"); continue
        A=np.mean([r[0] for r in rs]); F=np.mean([r[1] for r in rs]); T=np.mean([r[2] for r in rs])
        N=np.mean([r[3] for r in rs]); G=np.mean([r[4] for r in rs]); res[cond]=(A,F,T,N,G)
        print(f"{cond:14s} {A:>7.2f} {F:>8.3f} {T:>8.3f} {N:>9.3f} {G:>9.4f} {len(rs):>4d}")
    print("\nVERDICT (pre-registered: Gain_REAL > Gain_PLAUSIBLE ~ Gain_CONTRADICTION):")
    if all(k in res for k in ["REAL","PLAUSIBLE","CONTRADICTION"]):
        gr,gp,gc=res["REAL"][4],res["PLAUSIBLE"][4],res["CONTRADICTION"][4]
        tr,tp,tc=res["REAL"][2],res["PLAUSIBLE"][2],res["CONTRADICTION"][2]
        nr,np_,nc=res["REAL"][3],res["PLAUSIBLE"][3],res["CONTRADICTION"][3]
        print(f"  Gain: REAL={gr:.4f}  PLAUSIBLE={gp:.4f}  CONTRADICTION={gc:.4f}")
        print(f"  (T: {tr:.3f}/{tp:.3f}/{tc:.3f}   N: {nr:.3f}/{np_:.3f}/{nc:.3f})")
        if gr > max(gp,gc)*1.25:
            print("  -> Gain_REAL clearly highest: belonging concepts induce coherent STORY expansion")
            print("     MORE than non-belonging. SUSCEPTIBILITY SURVIVES (on the right observable).")
        elif abs(gr-gp)<=max(gr,gp)*0.15 and abs(gp-gc)<=max(gp,gc)*0.15:
            print("  -> Gain flat across conditions: belonging does NOT drive coherent expansion.")
            print("     Phenomenon dies HONESTLY this time — on T*N (right observable), not a bad proxy.")
        else:
            print("  -> partial/mixed. Look at WHICH axis (T vs N) separates. n small — direction only.")
        print("  KEY: is it T (displacement) or N (story-coherent novelty) that carries any signal?")
        print("  If N separates but T doesn't: belonging drives NEW STORY CONTENT, not just meaning-shift.")

if __name__=="__main__":
    main()
