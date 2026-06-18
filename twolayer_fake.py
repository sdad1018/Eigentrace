#!/usr/bin/env python3
"""
twolayer_fake.py — run the void+target bake-off on the TWO SYNTHETIC stories
(internet-alive, UAP-whitehouse) the models have no pre-baked frame for.

Same conditions as twolayer_bakeoff (A voids / B composition / C fused / D breadth /
CONTROL random) but stories come from fake_stories.py. The hypothesis: on novel/
absurd stories the model can't coast on training knowledge, so C should beat CONTROL
much more clearly than it did on familiar Iran news.

API + GPU. Stream stopped.
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
WRITER="ChatGPT"
TOPK_NN=12; N_VOIDS=4; N_TARGET=3
HEAD_W,CENT_W=0.3,0.7; OUTER=0.50    # lower threshold: novel stories sit farther from news-vocab
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot","irani"}

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    writer=pa.BIG5_CALLERS[WRITER]
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words
    widx={w:i for i,w in enumerate(words)}
    def nn(vec,k=TOPK_NN):
        s=(V16.astype(np.float32))@vec; return [words[i] for i in np.argsort(-s)[:k]]
    def breadth(w):
        if w not in widx: return 0.0
        nb=nn(V[widx[w]],TOPK_NN); vs=np.array([V[widx[x]] for x in nb if x in widx])
        if len(vs)<3: return 0.0
        S=vs@vs.T; n=len(vs); return 1-(S.sum()-n)/(n*n-n)
    def compose(a,b,al=0.5):
        q=(1-al)*a+al*b; return q/(np.linalg.norm(q)+1e-8)

    STORIES=json.load(open("fake_stories.json"))
    rng=np.random.default_rng(0)

    for key,story in STORIES.items():
        title=story["title"]; sums=story["summaries"]
        base=sums[0]
        cvecs=E(sums); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        raw_voids=[]
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
            raw_voids.append(w)
            if len(raw_voids)>=N_VOIDS: break
        br=sorted(raw_voids+[words[i] for i in cand[:40] if words[i] not in HARD_DROP and words[i].lower() not in tl],
                  key=lambda w:-breadth(w))
        breadth_frames=[]
        for w in br:
            if w not in breadth_frames: breadth_frames.append(w)
            if len(breadth_frames)>=N_VOIDS: break
        void_targets={}
        for vw in raw_voids:
            if vw not in widx: continue
            Q=compose(centroid,V[widx[vw]])
            tg=[w for w in nn(Q,TOPK_NN) if w not in HARD_DROP and w.lower() not in tl and w!=vw][:N_TARGET]
            void_targets[vw]=tg
        comp_only=[]
        for tg in void_targets.values():
            for w in tg:
                if w not in comp_only: comp_only.append(w)
        comp_only=comp_only[:6]
        rand_voids=[words[i] for i in rng.choice(len(words),N_VOIDS,replace=False)]
        rand_pairs="; ".join(f"{rv} (leads to: " +
            ", ".join(words[i] for i in rng.choice(len(words),N_TARGET,replace=False)) + ")" for rv in rand_voids)
        fused="; ".join(f"{vw} (where it leads here: {', '.join(void_targets.get(vw,[]))})" for vw in raw_voids)

        def write(instr):
            p=(f"News story: {title}\n\nYour earlier summary: {base}\n\n{instr} Write one tighter, "
               f"more vivid 2-3 sentence summary that works in any of these you judge genuinely "
               f"relevant. Stay faithful to the story; invent nothing.")
            s,_=writer(p); return (s or "").strip()

        print("\n"+"#"*74)
        print(f"# FAKE STORY: {title}")
        print(f"# raw voids (jolts): {raw_voids}")
        print(f"# per-void targets:  " + " | ".join(f"{k}->{v}" for k,v in void_targets.items()))
        print("#"*74)
        conds={
          "A_voids_only":"Your summary omitted these on-topic concepts: " + ", ".join(raw_voids) + ".",
          "B_composition_only":"Our analysis surfaced these related concepts: " + ", ".join(comp_only) + ".",
          "C_void+target_FUSED":"Your summary omitted these, and here is where each leads for this story: " + fused + ".",
          "D_breadth_frames":"Our analysis surfaced these related concepts: " + ", ".join(breadth_frames) + ".",
          "CONTROL_random":"Your summary omitted these, and here is where each leads: " + rand_pairs + ".",
        }
        for cond,instr in conds.items():
            s=write(instr)
            print(f"\n[{cond}]  ({len(s.split())} words)")
            print(f"  {s}")

    print("\n"+"="*72)
    print("EYEBALL: on stories the model has NO frame for, does C (void+target) now")
    print("clearly beat CONTROL (random)? Do the surfaced concepts name the REAL stakes")
    print("(consciousness/personhood/control; disclosure/sovereignty/precedent) or flail?")

if __name__=="__main__":
    main()
