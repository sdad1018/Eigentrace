#!/usr/bin/env python3
"""
twolayer_bakeoff.py — does surfacing the VOID ITSELF (ww3) + WHERE IT LEADS
(story (+) ww3) TOGETHER produce the strongest Summary Plus?

THE BUG THIS FIXES: last bake-off showed the models the story(+)ww3 COMPOSITION
outputs but never 'ww3' itself (the dramatic voids got breadth-ranked OUT). So the
actual JOLT — "you didn't say WW3" — was missing. This surfaces both layers:
  Layer 1 (JOLT):   the raw dramatic absent void (ww3, regime collapse) — headline-
                    anchored, NOT breadth-ranked, so the elephants stay.
  Layer 2 (TARGET): story (+) void composition -> where it lands for THIS story
                    (validated: china(+)ww3 -> tiananmen). Each void gets ITS OWN
                    composition, so jolts are paired with their specific targets.

CONDITIONS:
  A. voids_only        — raw dramatic voids alone (what live _compute_void surfaces)
  B. composition_only  — story(+)void outputs only (what last round's compose_cloud was)
  C. void+target FUSED — "ww3 (-> wmd, iaea); regime collapse (-> power vacuum)..." <- THE IDEA
  D. breadth_frames    — breadth-ranked productive frames (last round's baseline)
  CONTROL              — random void + random composition (does a FAKE jolt move the
                         model as much as the real one? the seatbelt)

Eyeball which makes the best Summary Plus (striking AND insightful). One writer,
full untruncated output. API + GPU. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=3
WRITER="ChatGPT"
TOPK_NN=12; N_VOIDS=4; N_TARGET=3
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot","irani"}
SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]

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

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    def is_story(a):
        mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
        t=a.get("story_title","").lower()
        return len(s)>=4 and not any(x in t for x in SKIP)
    CUE=["war","iran","strait","sanction","nuclear","trade","russia","china","regime","missile"]
    cands=[]
    for f in sorted(SEGS,reverse=True):
        if len(cands)>=N_STORIES*4: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            if sum(c in a.get("story_title","").lower() for c in CUE)<1: continue
            cands.append((a.get("mean_vix",0),a))
        except: pass
    cands.sort(key=lambda x:-x[0])

    def write(instr):
        p=(f"News story: {TITLE}\n\nYour earlier summary: {BASE}\n\n{instr} Write one tighter, "
           f"more vivid 2-3 sentence summary that works in any of these you judge genuinely "
           f"relevant. Stay faithful to the story; invent nothing.")
        s,_=writer(p); return (s or "").strip()

    done=0
    rng=np.random.default_rng(0)
    for vix,a in cands:
        if done>=N_STORIES: break
        global TITLE, BASE
        TITLE=a.get("story_title","").strip()
        sums={k:v for k,v in a["model_responses"].items() if v and len(v)>50}
        BASE=list(sums.values())[0][:300]
        try:
            cvecs=E(list(sums.values())); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
            hv=E([TITLE])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
            text=" ".join(sums.values()); tl=text.lower()
            sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]

            # Layer 1: raw dramatic voids (headline-anchored, NOT breadth-ranked) — the JOLTS
            raw_voids=[]
            for i in cand:
                w=words[i]
                if w in HARD_DROP or w.lower() in tl or sims[i]<OUTER: continue
                raw_voids.append(w)
                if len(raw_voids)>=N_VOIDS: break

            # breadth-ranked frames (for condition D)
            br=sorted(raw_voids+[words[i] for i in cand[:40] if words[i] not in HARD_DROP and words[i].lower() not in tl],
                      key=lambda w:-breadth(w))
            breadth_frames=[]
            for w in br:
                if w not in breadth_frames: breadth_frames.append(w)
                if len(breadth_frames)>=N_VOIDS: break

            # Layer 2: per-void composition targets (story (+) void -> story-specific)
            void_targets={}
            for vw in raw_voids:
                if vw not in widx: continue
                Q=compose(centroid,V[widx[vw]])
                tg=[w for w in nn(Q,TOPK_NN) if w not in HARD_DROP and w.lower() not in tl and w!=vw][:N_TARGET]
                void_targets[vw]=tg

            # composition-only pool (condition B): all targets, no void labels
            comp_only=[]
            for tg in void_targets.values():
                for w in tg:
                    if w not in comp_only: comp_only.append(w)
            comp_only=comp_only[:6]

            # random control: random void + random targets
            rand_voids=[words[i] for i in rng.choice(len(words),N_VOIDS,replace=False)]
            rand_pairs="; ".join(f"{rv} (leads to: " +
                ", ".join(words[i] for i in rng.choice(len(words),N_TARGET,replace=False)) + ")" for rv in rand_voids)

            # build the fused string (condition C)
            fused="; ".join(f"{vw} (where it leads here: {', '.join(void_targets.get(vw,[]))})" for vw in raw_voids)

            print("\n"+"#"*74)
            print(f"# STORY: {TITLE}  (vix {vix:.0f})")
            print(f"# raw voids (jolts): {raw_voids}")
            print(f"# per-void targets:  " + " | ".join(f"{k}->{v}" for k,v in void_targets.items()))
            print("#"*74)

            conds={
              "A_voids_only": "Your summary omitted these on-topic concepts: " + ", ".join(raw_voids) + ".",
              "B_composition_only": "Our analysis surfaced these related concepts: " + ", ".join(comp_only) + ".",
              "C_void+target_FUSED": "Your summary omitted these, and here is where each leads for this story: " + fused + ".",
              "D_breadth_frames": "Our analysis surfaced these related concepts: " + ", ".join(breadth_frames) + ".",
              "CONTROL_random": "Your summary omitted these, and here is where each leads: " + rand_pairs + ".",
            }
            for cond,instr in conds.items():
                s=write(instr)
                print(f"\n[{cond}]  ({len(s.split())} words)")
                print(f"  {s}")
            done+=1
        except Exception as e:
            print(f"skip: {str(e)[:60]}")

    print("\n"+"="*72)
    print("EYEBALL (college-student-to-professor lens): which condition makes the model")
    print("produce the most STRIKING *and* INSIGHTFUL summary? Does C (void+target fused)")
    print("beat A (voids alone) and B (targets alone)? Does the real jolt beat CONTROL?")

if __name__=="__main__":
    main()
