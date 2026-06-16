#!/usr/bin/env python3
"""
test_omission_band.py — OUT-OF-TREE. The FINAL gate test (Gemini's Option 3,
calibrated honestly for bge's actual geometry).

HYPOTHESIS: cosine distance between the void word and the CONSENSUS TEXT
separates three classes:
  - RESTATEMENT (too close):  'coalmining' vs a coal-mine story
  - NOISE (too far):          'steaua','españa' — orthographic/foreign junk
  - ORTHOGONAL INFERENCE:     'WWIII' vs an Iran-tension story  <-- the target

CRITICAL CORRECTION vs Gemini's spec:
  - Uses bge-large-en-v1.5 (the LIVE system's embedder), NOT MiniLM, so the
    geometry matches the actual void words. bge is ANISOTROPIC (sims squished
    high: unrelated~0.4-0.5, identical~0.85), so Gemini's 0.25/0.75 bands are
    WRONG for this space.
  - Does NOT hardcode the band. CALIBRATES it: computes distances for KNOWN
    restatements / KNOWN noise / KNOWN good cases, and checks whether any band
    actually separates them. If coalmining and WWIII land in the same band,
    no threshold works and the gate is dead.

Requires GPU (bge). RUN WITH STREAM STOPPED. Reads stored segments + embeds.
Writes nothing to live code.
"""
import json, glob, re, sys
import numpy as np

SEG_DIR = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"

# Ground-truth labels from our eyeball (void_word, class) for CALIBRATION.
# class: R=restatement, N=noise, G=good/orthogonal-inference
CALIB = [
    ("coalmining","R"),("coalmine","R"),("coalminers","R"),("mineworkers","R"),
    ("airstrikes","R"),("air strike","R"),("rescuers","R"),("death toll","R"),
    ("explosions","R"),("blasts","R"),("automobile","R"),("vehicular","R"),
    ("steaua","N"),("españa","N"),("espana","N"),("roumania","N"),("moldavia","N"),
    ("msgt","N"),("usna","N"),("orphic","N"),("beryllium","N"),("alfresco","N"),
    ("wwiii","G"),("cyberwarfare","G"),("arms embargo","G"),("arms deal","G"),
    ("information warfare","G"),("proxy war","G"),("trade war","G"),
    ("market manipulation","G"),("foreign interference","G"),("genocidal","G"),
]

def load_embedder():
    from sentence_transformers import SentenceTransformer
    print("loading bge-large-en-v1.5 (the live embedder)...", flush=True)
    return SentenceTransformer("BAAI/bge-large-en-v1.5", device="cuda")

def emb(model, texts):
    v = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.array(v)

def harvest():
    rows=[]
    for f in glob.glob(SEG_DIR):
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([m for m,t in mr.items() if t and len(t)>50])<4: continue
            vw=a.get("synthesis_words") or a.get("void_words") or []
            if not vw: continue
            # consensus text = concatenation of the 5 summaries
            consensus=" ".join(t for t in mr.values() if t)[:2000]
            rows.append({"title":(a.get("story_title") or d.get("title") or "")[:70],
                         "void":vw[:5], "consensus":consensus})
        except: pass
    return rows

def main():
    model=load_embedder()

    # ---- STEP 1: calibrate on known cases ----
    # Embed each calib void word and a generic "the news story" anchor isn't enough;
    # we need per-class distance behavior. Use a representative consensus text per
    # word by finding a story whose void contains it. Simpler robust proxy: measure
    # cosine of the word to the MEAN of all consensus texts that surfaced it.
    rows=harvest()
    print(f"harvested {len(rows)} stories\n", flush=True)

    # Build: for each calib word, gather consensus texts of stories that surfaced it
    word_consensus={}
    for r in rows:
        for w in r["void"]:
            wl=w.lower()
            word_consensus.setdefault(wl,[]).append(r["consensus"])

    print("=== CALIBRATION: cosine(void_word, its own consensus text) by class ===")
    print("(R=restatement should be HIGH sim; N=noise LOW/erratic; G=good MIDDLE)\n")
    by_class={"R":[],"N":[],"G":[]}
    for word,cls in CALIB:
        wl=word.lower()
        texts=word_consensus.get(wl,[])
        if not texts: 
            continue
        wv=emb(model,[word])[0]
        cvs=emb(model,texts[:20])
        sims=cvs@wv
        msim=float(np.mean(sims))
        by_class[cls].append(msim)
        print(f"  [{cls}] {word:22s} mean cos to consensus = {msim:.3f}  (n={len(texts)} stories)")

    print("\n=== CLASS DISTRIBUTIONS ===")
    for cls,lab in [("R","RESTATEMENT"),("G","GOOD/orthogonal"),("N","NOISE")]:
        v=by_class[cls]
        if v:
            print(f"  {lab:16s}: n={len(v)} min={min(v):.3f} mean={np.mean(v):.3f} max={max(v):.3f}")

    # ---- STEP 2: does a band separate G from R and N? ----
    R=np.array(by_class["R"]); G=np.array(by_class["G"]); N=np.array(by_class["N"])
    print("\n=== SEPARATION VERDICT ===")
    if len(R) and len(G) and len(N):
        print(f"  RESTATEMENT mean {R.mean():.3f} | GOOD mean {G.mean():.3f} | NOISE mean {N.mean():.3f}")
        # Is GOOD a distinct middle band?
        if G.mean() < R.mean()-0.02 and G.mean() > N.mean()+0.02:
            lo=(G.mean()+N.mean())/2; hi=(G.mean()+R.mean())/2
            print(f"  GOOD sits between -> candidate band: {lo:.3f} to {hi:.3f}")
            # overlap check
            R_in=np.mean((R>=lo)&(R<=hi)); N_in=np.mean((N>=lo)&(N<=hi)); G_in=np.mean((G>=lo)&(G<=hi))
            print(f"  band captures: GOOD {100*G_in:.0f}% | leaks RESTATEMENT {100*R_in:.0f}% | leaks NOISE {100*N_in:.0f}%")
            if G_in>=0.6 and R_in<=0.3 and N_in<=0.3:
                print("  >>> BAND SEPARATES. Proceed to apply on all 881 + eyeball top 20.")
                band=(lo,hi)
            else:
                print("  >>> band leaks too much — classes OVERLAP. No clean cosine threshold. Gate likely dead.")
                band=(lo,hi)  # still show what it'd catch
        else:
            print("  >>> GOOD does NOT sit in a distinct middle band. Restatement/inference/noise")
            print("      are NOT separable by cosine-to-consensus. GATE IS DEAD -> default to Curated Gallery.")
            return
    else:
        print("  insufficient calibration data"); return

    # ---- STEP 3: apply band to all void words, eyeball ----
    print("\n=== APPLYING BAND TO ALL VOID WORDS — top candidates in the band ===")
    hits=[]
    for r in rows:
        cv=emb(model,[r["consensus"]])[0]
        for w in r["void"]:
            wv=emb(model,[w])[0]
            s=float(wv@cv)
            if band[0]<=s<=band[1]:
                hits.append((s,w,r["title"]))
    hits.sort(key=lambda x:abs(x[0]-(band[0]+band[1])/2))  # closest to band center
    print(f"  {len(hits)} void words landed in band across {len(rows)} stories")
    print("  TOP 25 (eyeball: are these clean orthogonal inferences?):\n")
    for s,w,t in hits[:25]:
        print(f"   [{s:.3f}] {w:22s} <- {t}")

if __name__=="__main__":
    main()
