#!/usr/bin/env python3
"""
knife_test.py — is strain measuring SEMANTIC MISMATCH or just WORD RARITY?

The strain gauge survived in the predicted direction (PRESENT<REAL<RANDOM<OFFTOPIC),
but it has one giant escape hatch (ChatGPT's catch): OFFTOPIC words are also RARER. So
strain could be ∝ rarity, not ∝ semantic-mismatch. "The model dislikes weird words" is
NOT publishable; "the model dislikes concept mismatch" IS. The knife cuts them apart.

PRE-REGISTERED DESIGN (rarity-matched conditions):
  A PRESENT          — word in the source (low rarity, belongs)
  B REAL             — clean donut void concept (belongs)
  C MATCHED_OFFTOPIC — offtopic word MATCHED to REAL's rarity (weird BUT not rarer)
  D MATCHED_SEMANTIC — topic-adjacent word MATCHED to OFFTOPIC's rarity (rare BUT belongs)

RARITY MATCHING: the vocab is wordfreq-ORDERED, so a word's INDEX ~ its rarity rank.
Match rarity by index proximity (no wordfreq dependency needed — it's in the ordering).
  C: find an OFF-topic word near REAL's vocab index (low blend-sim, similar rarity)
  D: find an ON-topic word near OFFTOPIC's vocab index (high blend-sim, similar rarity)

PRE-REGISTERED PREDICTION:
  cond              strain   accept
  PRESENT           low      high
  REAL              low      high
  MATCHED_OFFTOPIC  HIGH     low      <- weird, matched-rarity: if THIS strains, it's mismatch not rarity
  MATCHED_SEMANTIC  low      high     <- rare BUT belongs: if this is LOW strain, rarity is NOT the driver

THE KNIFE:
  If MATCHED_SEMANTIC (rare but on-topic) has LOW strain  AND
     MATCHED_OFFTOPIC (matched-rarity but off-topic) has HIGH strain
  -> strain tracks SEMANTIC MISMATCH, not rarity. SIGNAL REAL. Publishable.
  If matched-rarity COLLAPSES the gap (offtopic≈semantic once rarity-matched)
  -> strain was just rarity. Signal dies. Clean stop.

Belonging = Acceptance - lambda*Strain (lambda=1). Local /v1/ logprobs. Stream stopped.
"""
import json, os, sys, glob, re, math
import numpy as np
import requests

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=5
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN_MODEL="qwen2.5:14b"
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
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

def gen_strain(prompt, exclude_word):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":GEN_MODEL,
            "messages":[{"role":"system","content":"Summarize this news story in 2-3 sentences. Stay faithful; invent nothing."},
                        {"role":"user","content":prompt}],
            "max_tokens":160,"temperature":0.3,"logprobs":True,"top_logprobs":3},timeout=150)
        r.raise_for_status(); ch=r.json()["choices"][0]
        text=ch["message"]["content"].strip()
        lp=ch.get("logprobs",{}).get("content",[])
        if not lp: return text,None
        ex=[exclude_word.lower()]+exclude_word.lower().split()
        host=[]
        for tok in lp:
            top=tok.get("top_logprobs",[])
            if not top: continue
            probs=[math.exp(t["logprob"]) for t in top]; s=sum(probs); probs=[p/s for p in probs]
            ent=-sum(p*math.log2(p+1e-10) for p in probs)
            tk=tok.get("token","").strip().lower()
            if not (tk in ex or any(f in tk for f in ex if len(f)>3) or any(tk in f for f in ex if tk)):
                host.append(ent)
        return text,(np.mean(host) if host else None)
    except Exception as e:
        return f"[err {str(e)[:30]}]",None

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
    widx={w:i for i,w in enumerate(words)}
    N=len(words)

    def matched(target_idx, blend, want_offtopic, exclude_lower, window=2000):
        """find a word near target_idx in rarity (vocab order) with low (offtopic) or
        high (semantic) blend-sim, not already in text."""
        lo=max(0,target_idx-window); hi=min(N,target_idx+window)
        idxs=list(range(lo,hi))
        sims=(V16[idxs].astype(np.float32))@blend
        order=np.argsort(sims) if want_offtopic else np.argsort(-sims)
        for k in order:
            w=words[idxs[k]]
            if w in HARD_DROP or w.lower() in exclude_lower or len(w)<4: continue
            return w, float(sims[k])
        return None,None

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

    agg={"PRESENT":[], "REAL":[], "MATCHED_OFFTOPIC":[], "MATCHED_SEMANTIC":[]}
    done=0
    for title,sums_list in erased:
        if done>=N_STORIES: break
        base=sums_list[0]
        cvecs=E(sums_list); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums_list); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        real=None; real_idx=None
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
            real=w; real_idx=widx[w]; break
        if not real: continue
        present_words=[w for w in re.findall(r"[a-z][a-z]{4,}", base.lower()) if w in widx]
        present=present_words[len(present_words)//2] if present_words else None
        if not present: continue
        # MATCHED_OFFTOPIC: offtopic word at REAL's rarity
        m_off,_=matched(real_idx, blend, want_offtopic=True, exclude_lower=tl)
        # OFFTOPIC anchor rarity = pick a genuinely rare offtopic, then match semantic to ITS rarity
        # use m_off's index as the "offtopic rarity" anchor for the semantic match
        off_idx=widx.get(m_off, real_idx) if m_off else real_idx
        m_sem,_=matched(off_idx, blend, want_offtopic=False, exclude_lower=tl)
        if not (m_off and m_sem): continue

        inj={"PRESENT":present,"REAL":real,"MATCHED_OFFTOPIC":m_off,"MATCHED_SEMANTIC":m_sem}
        print("\n"+"="*70); print(f"STORY: {title[:55]}")
        print(f"  PRESENT='{present}'(idx{widx[present]}) REAL='{real}'(idx{real_idx}) "
              f"M_OFF='{m_off}'(idx{widx[m_off]}) M_SEM='{m_sem}'(idx{widx[m_sem]})")
        print(f"  [rarity check: REAL idx {real_idx} vs M_OFF idx {widx[m_off]} | "
              f"M_OFF idx {widx[m_off]} vs M_SEM idx {widx[m_sem]}]")
        for cond,w in inj.items():
            prompt=(f"News story: {title}\n\nEarlier summary: {base[:300]}\n\n"
                    f"Work the concept '{w}' into a tighter 2-3 sentence summary IF genuinely "
                    f"relevant (skip if not). Stay faithful; invent nothing.")
            txt,strain=gen_strain(prompt,w)
            used=bool(re.search(r'\b'+re.escape(w.split()[0])+r'\b',txt.lower()))
            if strain is not None:
                agg[cond].append((strain,used))
                print(f"  [{cond:16s}] strain={strain:.3f} used={int(used)}")
        done+=1

    print("\n"+"="*70); print("AGGREGATE — the KNIFE"); print("="*70)
    print(f"{'cond':18s} {'strain':>8s} {'accept':>8s} {'belonging':>10s} {'n':>4s}")
    res={}
    for cond in ["PRESENT","REAL","MATCHED_OFFTOPIC","MATCHED_SEMANTIC"]:
        rs=agg[cond]
        if not rs: print(f"{cond:18s} (none)"); continue
        st=np.mean([r[0] for r in rs]); ac=np.mean([r[1] for r in rs])
        res[cond]=(st,ac)
        print(f"{cond:18s} {st:>8.3f} {ac:>8.2f} {ac-st:>10.3f} {len(rs):>4d}")
    print("\nTHE KNIFE VERDICT:")
    if "MATCHED_OFFTOPIC" in res and "MATCHED_SEMANTIC" in res:
        off_s=res["MATCHED_OFFTOPIC"][0]; sem_s=res["MATCHED_SEMANTIC"][0]
        print(f"  MATCHED_OFFTOPIC strain {off_s:.3f}  vs  MATCHED_SEMANTIC strain {sem_s:.3f}")
        print(f"  (both rarity-matched to weird words — so rarity is CONTROLLED)")
        if off_s > sem_s + 0.02:
            print(f"  -> OFFTOPIC strains MORE than rarity-matched SEMANTIC: strain tracks MISMATCH not rarity. SIGNAL REAL.")
        elif abs(off_s-sem_s) <= 0.02:
            print(f"  -> offtopic ~= semantic once rarity-matched: strain was just RARITY. Signal dies. Clean stop.")
        else:
            print(f"  -> semantic strains MORE than offtopic: inverted / confounded. Inconclusive.")
    print("  (also: MATCHED_SEMANTIC should be LOW strain + HIGH accept if it's belonging, not rarity)")

if __name__=="__main__":
    main()
