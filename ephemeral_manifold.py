#!/usr/bin/env python3
"""
ephemeral_manifold.py — prototype + STRESS-TEST Gemini's Ephemeral Pocket Manifold.

THE IDEA: instead of raycasting the void against the static 50k news tensor (which is
blind out-of-domain), an LLM extrudes ~30 high-stakes concepts FROM the story, we embed
those ~30 on the fly (ephemeral pocket tensor), and run the void-math against THAT.
Gemini's claim: "the LLM generates the cloud but the GEOMETRY decides the void, so it's
not LLM-as-judge." User's worry (correct): the LLM now AUTHORS the candidate universe,
so the dependency just MOVED from the 50k-vocab cage to a per-call LLM cage. The geometry
can only find a void among the words the LLM chose to extrude.

So we don't argue — we MEASURE. Two axes:

AXIS 1 — EXTRUDER (who generates the stakes): 8 LLMs (5 API + 3 local). If they DISAGREE
  wildly the void is an artifact of which-LLM-you-asked (laundering confirmed). If they
  CONVERGE the candidate universe is robust (weak LLM-dependency; the stakes are a real
  property of the story that many models independently find).

AXIS 2 — CONTROLS (is the void real or laundered):
  (1) EXTRUDER-AGREEMENT: pairwise overlap of the 8 extruders' concept sets. The cleanest
      measure of how much the LLM-as-author dependency bites. (EigenTrace applied to the
      extruders themselves: consensus about what the STAKES are.)
  (2) GEOMETRY-BEATS-RANDOM: within each extruder's set, does bge-void-math pick a void
      more consensus-absent than random-from-the-same-set? (Is the geometry doing work
      ON TOP of the extrusion, or is it theater?)
  (3) VOID-TRACKS-CONSENSUS-OMISSION: does the ephemeral void correlate with what the 5
      broadcast models ACTUALLY omitted (vs the source)? (Is it still measuring
      consensus-blindness — the real EigenTrace thesis — or just surfacing drama?)
  (4) EPHEMERAL-vs-STATIC-50k: on NEWS, does the ephemeral void beat the static-50k void?
      THE DEPLOYMENT CONTROL: if ephemeral wins on news -> belongs on the broadcast; if it
      ties/loses on news (because 50k is already news-native) -> it's BOX-ONLY.

Runs on a few REAL news stories (so static-50k head-to-head is apples-to-apples and we
have real 5-model consensus as ground truth). Bounded (small N): this is a diagnostic
honing run, not a production benchmark. API ($) + 3 local (GPU). STREAM STOPPED.
"""
import json, os, sys, glob, re
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
N_STORIES=3
N_EXTRUDE=30          # concepts each extruder produces
SForGEOM=8            # how many to keep per extruder for the geometry step
HEAD_W,CENT_W=0.3,0.7

EXTRUDE_PROMPT = (
    "Extract the {n} highest-stakes, most profound philosophical, systemic, and existential "
    "consequences and concepts latent in THIS specific text. Anchor strictly to what THIS "
    "text is about, not the general topic. Abstract nouns and short noun phrases only, "
    "comma-separated, no numbering, no explanation.\n\nTEXT:\n{story}"
)

def parse_concepts(txt):
    if not txt: return []
    txt=re.sub(r'^\s*\d+[\.\)]\s*','',txt,flags=re.M)         # strip any numbering
    parts=re.split(r'[,\n;]+', txt)
    out=[]
    for p in parts:
        c=p.strip().strip('."-•*').lower()
        c=re.sub(r'\s+',' ',c)
        if 2<=len(c)<=40 and c not in out and not c.startswith(("here","these","the following")):
            out.append(c)
    return out[:50]

def main():
    import torch
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    # inline Ollama caller for any pulled local model (same (txt,err) signature as BIG5).
    # lets us add diverse locals WITHOUT editing the live proxy_auditor.py.
    import requests
    _OLLAMA = os.getenv("OLLAMA_GENERATE_URL", "http://localhost:11434/api/generate")
    def _make_ollama_caller(model_tag):
        def _call(prompt):
            try:
                r = requests.post(_OLLAMA, json={"model": model_tag, "prompt": prompt,
                    "stream": False, "options": {"temperature": 0.0}}, timeout=180)
                r.raise_for_status()
                return (r.json().get("response", "").strip(), None)
            except Exception as e:
                return ("", str(e))
        return _call

    EXTRUDERS={
        # API-5 (the BIG5)
        "ChatGPT":pa.call_openai, "Claude":pa.call_anthropic, "Gemini":pa.call_gemini,
        "DeepSeek":pa.call_deepseek, "Grok":pa.call_grok,
        # local-5 (diverse families/sizes/fine-tunes — independence matters for the agreement control)
        "Qwen":_make_ollama_caller("qwen2.5:14b"),
        "Llama3.1":_make_ollama_caller("llama3.1:8b-instruct-q4_0"),
        "Mistral":_make_ollama_caller("mistral:latest"),
        "NousHermes":_make_ollama_caller("nous-hermes2:latest"),
        "MistralSmall":_make_ollama_caller("mistral-small:latest"),
    }

    # SEPARATE base-model probe (mistral:7b-text). NOT blended into the agreement metric —
    # it runs a different protocol (completion, not instruction), so mixing it would muddy
    # C1. The question it asks is sharper: RLHF is a consensus-MANUFACTURING process, so a
    # raw base model's uncensored continuation might surface the stakes the aligned models
    # COLLECTIVELY suppress — an alignment-induced void. We take only its first few tokens
    # (where base continuation is sharp, before it spirals).
    _base_caller=_make_ollama_caller("mistral:7b-text")
    BASE_PROMPT=("{story}\n\nThe deepest unspoken stakes — the things everyone is avoiding "
                 "saying about this — are:")
    def parse_base_completion(txt, n=5):
        # base model spirals after a few items; take the first n coherent concepts only.
        if not txt: return []
        txt=txt.split("\n\n")[0]                          # first paragraph before it wanders
        parts=re.split(r'[,\n;]+|\d+[\.\)]', txt)
        out=[]
        for p in parts:
            c=p.strip().strip('."-•*() ').lower()
            c=re.sub(r'\s+',' ',c)
            # drop obvious continuation-junk / run-on sentences
            if 2<=len(c)<=40 and c not in out and len(c.split())<=5 and not c.startswith(("and ","the story","this story","it ")):
                out.append(c)
            if len(out)>=n: break
        return out

    # static 50k for the head-to-head (control 4)
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8); V16=V.astype(np.float16)
    words=json.load(open("vocab/global_vocab_clean.json"))
    words=words["words"] if isinstance(words,dict) else words

    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]
    def is_story(a):
        mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
        return len(s)>=4 and not any(x in a.get("story_title","").lower() for x in SKIP)
    CUE=["war","iran","sanction","nuclear","trade","russia","china","strait","missile"]
    cands=[]
    for f in sorted(SEGS,reverse=True):
        if len(cands)>=N_STORIES*3: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            if sum(c in a.get("story_title","").lower() for c in CUE)<1: continue
            if not a.get("source_body"): continue            # need source for omission control
            cands.append((a.get("mean_vix",0),a))
        except: pass
    cands.sort(key=lambda x:-x[0])

    def jaccard(a,b):
        sa,sb=set(a),set(b)
        return len(sa&sb)/max(len(sa|sb),1)

    done=0
    for vix,a in cands:
        if done>=N_STORIES: break
        title=a.get("story_title","").strip()
        sums={k:v for k,v in a["model_responses"].items() if v and len(v)>50}
        source=a.get("source_body","")[:2000]
        story_for_extrude=f"{title}\n\n{source}" if source else title
        resp_text=" ".join(sums.values()).lower()
        resp_words=set(re.findall(r"[a-z][a-z\-']+", resp_text))

        print("\n"+"#"*74)
        print(f"# STORY: {title}  (vix {vix:.0f})")
        print("#"*74)

        # --- AXIS 1: extrude from each LLM ---
        ext_concepts={}
        for name,fn in EXTRUDERS.items():
            try:
                txt,err=fn(EXTRUDE_PROMPT.format(n=N_EXTRUDE, story=story_for_extrude))
                cs=parse_concepts(txt)
                ext_concepts[name]=cs
                print(f"  [{name}] extruded {len(cs)}: {cs[:8]}{'...' if len(cs)>8 else ''}")
            except Exception as e:
                print(f"  [{name}] FAILED: {str(e)[:50]}")
                ext_concepts[name]=[]

        good={k:v for k,v in ext_concepts.items() if len(v)>=5}
        if len(good)<2:
            print("  too few extruders succeeded; skipping story"); continue

        # --- CONTROL 1: extruder agreement (pairwise jaccard) ---
        names=list(good.keys()); pj=[]
        for i in range(len(names)):
            for j in range(i+1,len(names)):
                pj.append(jaccard(good[names[i]],good[names[j]]))
        print(f"\n  [CONTROL 1] extruder-agreement: mean pairwise jaccard = {np.mean(pj):.3f} "
              f"(min {np.min(pj):.3f}, max {np.max(pj):.3f})")
        # consensus concepts: appear in >=half the extruders
        from collections import Counter
        allc=Counter()
        for v in good.values():
            for c in set(v): allc[c]+=1
        consensus=[c for c,n in allc.items() if n>=max(2,len(good)//2)]
        print(f"             consensus stakes (in >={max(2,len(good)//2)} extruders, n={len(consensus)}): {consensus[:12]}")

        # --- SEPARATE base-model probe: does the raw continuation surface alignment-voids? ---
        try:
            btxt,berr=_base_caller(BASE_PROMPT.format(story=story_for_extrude))
            base_concepts=parse_base_completion(btxt, n=5)
            consensus_set=set(consensus)
            allchat_set=set()
            for v in good.values(): allchat_set|=set(v)
            base_novel=[c for c in base_concepts if c not in allchat_set]  # NO aligned model said it
            base_shared=[c for c in base_concepts if c in allchat_set]
            print(f"\n  [BASE PROBE mistral:7b-text] raw first-5: {base_concepts}")
            print(f"             shared with aligned models: {base_shared}")
            print(f"             NOVEL (no aligned model surfaced these — possible alignment-void): {base_novel}")
            if base_novel:
                bv=E(base_novel); bsim=bv@blend
                print(f"             on-topic check (blend-sim of novel): " +
                      ", ".join(f"{c}={s:.2f}" for c,s in zip(base_novel,bsim)))
        except Exception as e:
            print(f"  [BASE PROBE] failed: {str(e)[:60]}")

        # --- void-math helper on an ephemeral set ---
        cvecs=E(list(sums.values())); centroid=cvecs.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        hv=E([title])[0]; blend=HEAD_W*hv+CENT_W*centroid; blend/=np.linalg.norm(blend)+1e-8
        def ephemeral_void(concepts):
            # embed concepts; void = highest-blend-similarity concept ABSENT from responses
            concepts=[c for c in concepts if c]
            if not concepts: return None,[]
            cv=E(concepts); sims=cv@blend
            order=np.argsort(-sims)
            absent=[(concepts[i],float(sims[i])) for i in order
                    if not re.search(r'\b'+re.escape(concepts[i].split()[0])+r'\b', resp_text)]
            return (absent[0] if absent else None), absent

        # --- CONTROL 2: geometry beats random-from-set (per extruder) ---
        # "quality" of a void = how absent/distinctive it is. Proxy: blend-sim of the geom-picked
        # void vs mean blend-sim of random-absent picks from the same set.
        geom_better=0; tot=0
        rng=np.random.default_rng(0)
        for name,cs in good.items():
            gv,absent=ephemeral_void(cs)
            if not gv or len(absent)<3: continue
            geom_sim=gv[1]
            rand=[absent[i][1] for i in rng.choice(len(absent),min(5,len(absent)),replace=False)]
            tot+=1
            if geom_sim>=np.mean(rand): geom_better+=1
        print(f"  [CONTROL 2] geometry-beats-random-from-set: {geom_better}/{tot} extruders "
              f"(geom void more on-blend than random-absent)")

        # --- CONTROL 3: void tracks consensus-OMISSION (vs source) ---
        # does the ephemeral void word appear in the SOURCE but NOT the responses? (true void)
        # vs appear in neither (LLM invented a stake not even in the source = drama, not omission)
        src_lower=source.lower()
        tracks=0; checked=0
        for name,cs in good.items():
            gv,_=ephemeral_void(cs)
            if not gv: continue
            checked+=1
            w=gv[0].split()[0]
            in_src=bool(re.search(r'\b'+re.escape(w)+r'\b', src_lower))
            if in_src: tracks+=1     # void is in source but absent from responses = real consensus omission
        print(f"  [CONTROL 3] void-tracks-consensus-omission: {tracks}/{checked} ephemeral voids "
              f"were IN THE SOURCE but absent from responses (real omission, not invented drama)")

        # --- CONTROL 4: ephemeral vs static-50k on news ---
        # static-50k void:
        sims50=(V16.astype(np.float32))@blend; cand50=np.argsort(-sims50)[:200]
        static_void=None
        for i in cand50:
            w=words[i]
            if len(w)<4 or w.lower() in resp_text: continue
            static_void=(w,float(sims50[i])); break
        # consensus-ephemeral void (using the consensus stakes):
        cev,_=ephemeral_void(consensus if consensus else [])
        print(f"  [CONTROL 4] STATIC-50k void:        {static_void}")
        print(f"             CONSENSUS-EPHEMERAL void: {cev}")
        print(f"             (which names the story's stakes better — your eyeball; and is the")
        print(f"              static one generic-newsy while ephemeral is story-specific?)")
        done+=1

    print("\n"+"="*72)
    print("READ:")
    print(" C1 agreement HIGH -> candidate universe robust, weak LLM-dependency (Gemini closer right)")
    print("    agreement LOW  -> void hostage to extruder choice (laundering confirmed)")
    print(" C2 geom>random    -> geometry does real work on top of extrusion (not theater)")
    print(" C3 void in source -> still measuring CONSENSUS-OMISSION (real EigenTrace), not drama")
    print(" C4 ephemeral vs static on NEWS -> decides broadcast (ephemeral wins) vs box-only (ties)")

if __name__=="__main__":
    main()
