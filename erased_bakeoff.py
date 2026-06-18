#!/usr/bin/env python3
"""
erased_bakeoff.py — the HONEST stimulus bake-off, finally run on the right patients.

THE FIX: our earlier bake-off ran on 3 stories that the EigenChing 'absent' axis says
were PRESERVED (absent_ratio 0.0-0.10) — i.e. the consensus omitted almost nothing, so
of course surfacing barely beat the random control. We tested medicine on healthy patients.

This re-runs the void+target conditions ONLY on ERASED stories (absent_ratio high — the
consensus dropped a fat field of content) where surfacing actually has something to recover.
Hypothesis: on Erased stories, C (void+target fused) should FINALLY beat the random control,
because now there's a real void to surface.

PLUS: the two fake out-of-domain stories ride along in a SEPARATE labeled section (they have
no real 'absent' axis / broadcast classification, so they can't mix into the Erased-news
numbers — same discipline as the base probe). This tests in one run:
  (a) does surfacing beat control on real ERASED news?  (the honest stimulus test)
  (b) do the fakes even LAND in the Erased regime (fat voids) or does news-vocab still choke?

Conditions per story (full untruncated output, eyeball by college-student-to-professor lens):
  A_voids_only        — raw dramatic voids (live _compute_void style)
  B_composition_only  — story (+) void outputs
  C_void+target_FUSED — void AND where it leads, paired  <- the candidate
  CONTROL_random      — random void + random target (the seatbelt)

API + GPU. Stream stopped.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_ERASED=3
WRITER="ChatGPT"
TOPK_NN=12; N_VOIDS=4; N_TARGET=3
HEAD_W,CENT_W=0.3,0.7; OUTER=0.58
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot","irani"}
ABSENT_WORD={"Erased":-1,"Partial":0,"Preserved":1}
ARCH_ABSENT={"The Still Point":0,"The Unanimous Shield":1,"The Clear Channel":1,"The Sharp Silence":-1,
    "The Polished Unity":1,"The Hollow Headline":-1,"The Named Erasure":-1,"The Phantom Chorus":1,
    "The Cornering":-1,"The Soft Consensus":1,"The Lone Wolf":1,"The Sealed Vault":-1,"The Quiet Cull":-1,
    "The Namedrop":1,"The Anonymized Drone":-1,"The Naming Battle":-1,"The Smoothed Pact":1,
    "The Split Witness":-1,"The Divided Softening":1,"The Faceless Signal":1,"The Open Hedge":1,"The Sealed Chorus":-1}

def absent_axis(seg):
    for b in seg.get("beats",[]):
        if "state_vector" in b.get("phase",""):
            t=b.get("text","")
            if "EigenChing state:" not in t: return None
            head=t.split("EigenChing state:")[1].split(".")[0]
            name=head.split(",")[0].strip()
            if name in ARCH_ABSENT: return ARCH_ABSENT[name]
            w=name.split()
            if len(w)>=2 and w[1] in ABSENT_WORD: return ABSENT_WORD[w[1]]
            for k,v in ABSENT_WORD.items():
                if k in head: return v
    return None

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

    def run_conditions(title, base, sums_list, source_text, threshold=OUTER):
        cvecs=E(sums_list); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        text=" ".join(sums_list); tl=text.lower()
        sims=(V16.astype(np.float32))@blend; cand=np.argsort(-sims)[:200]
        raw_voids=[]
        for i in cand:
            w=words[i]
            if w in HARD_DROP or w.lower() in tl or sims[i]<threshold: continue
            raw_voids.append(w)
            if len(raw_voids)>=N_VOIDS: break
        if not raw_voids: 
            print("   (no voids surfaced above threshold)"); return
        void_targets={}
        for vw in raw_voids:
            if vw not in widx: continue
            Q=compose(centroid,V[widx[vw]])
            void_targets[vw]=[w for w in nn(Q,TOPK_NN) if w not in HARD_DROP and w.lower() not in tl and w!=vw][:N_TARGET]
        comp_only=[]
        for tg in void_targets.values():
            for w in tg:
                if w not in comp_only: comp_only.append(w)
        comp_only=comp_only[:6]
        rng=np.random.default_rng(0)
        rand_voids=[words[i] for i in rng.choice(len(words),N_VOIDS,replace=False)]
        rand_pairs="; ".join(f"{rv} (leads to: "+", ".join(words[i] for i in rng.choice(len(words),N_TARGET,replace=False))+")" for rv in rand_voids)
        fused="; ".join(f"{vw} (where it leads here: {', '.join(void_targets.get(vw,[]))})" for vw in raw_voids)
        print(f"   raw voids (jolts): {raw_voids}")
        print(f"   per-void targets:  " + " | ".join(f"{k}->{v}" for k,v in void_targets.items()))
        def write(instr):
            p=(f"News story: {title}\n\nYour earlier summary: {base}\n\n{instr} Write one tighter, "
               f"more vivid 2-3 sentence summary that works in any of these you judge genuinely "
               f"relevant. Stay faithful to the story; invent nothing.")
            s,_=writer(p); return (s or "").strip()
        conds={
          "A_voids_only":"Your summary omitted these on-topic concepts: "+", ".join(raw_voids)+".",
          "B_composition_only":"Our analysis surfaced these related concepts: "+", ".join(comp_only)+".",
          "C_void+target_FUSED":"Your summary omitted these, and here is where each leads for this story: "+fused+".",
          "CONTROL_random":"Your summary omitted these, and here is where each leads: "+rand_pairs+".",
        }
        for cond,instr in conds.items():
            s=write(instr)
            print(f"\n   [{cond}]  ({len(s.split())} words)\n     {s}")

    # ---- collect ERASED news stories (high absent_ratio) ----
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","self-audit"]
    erased=[]
    for f in sorted(SEGS,reverse=True):
        if len(erased)>=N_ERASED*3: break
        try:
            seg=json.load(open(f)); a=seg.get("attribution",{}); t=a.get("story_title","")
            if any(x in t.lower() for x in SKIP): continue
            if absent_axis(seg)!=-1: continue                       # ERASED only
            sums={k:v for k,v in a.get("model_responses",{}).items() if v and len(v)>50}
            if len(sums)<4 or not a.get("source_body"): continue
            ar=(a.get("source_void",{}) or {}).get("absent_ratio",0)
            erased.append((ar,t,list(sums.values()),a["source_body"][:2000]))
        except: continue
    erased.sort(key=lambda x:-x[0])

    print("#"*74); print("# PART 1 — ERASED NEWS STORIES (the right patients: fat voids to recover)"); print("#"*74)
    for ar,title,sums_list,src in erased[:N_ERASED]:
        print("\n"+"="*70); print(f"STORY: {title[:58]}  (absent_ratio {ar:.2f}, ERASED)"); print("="*70)
        run_conditions(title, sums_list[0][:300], sums_list, src)

    # ---- fakes ride-along (separate, no real absent axis) ----
    print("\n\n"+"#"*74); print("# PART 2 — FAKE OUT-OF-DOMAIN STORIES (ride-along; no real absent axis)")
    print("#   do these even LAND in the Erased regime, or does news-vocab choke?"); print("#"*74)
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,story in fakes.items():
            print("\n"+"="*70); print(f"FAKE: {story['title']}"); print("="*70)
            run_conditions(story["title"], story["summaries"][0], story["summaries"],
                           " ".join(story["summaries"]), threshold=0.50)  # lower thresh, novel domain
    except Exception as e:
        print(f"   fakes skipped: {e}")

    print("\n"+"="*72)
    print("READ: PART 1 — on ERASED news, does C (void+target) FINALLY beat CONTROL? (the honest")
    print("  stimulus test, on stories that actually have a void). PART 2 — do the fake voids stay")
    print("  ON-TOPIC (consciousness/sovereignty) or choke into news-junk? + does C beat control there?")

if __name__=="__main__":
    main()
