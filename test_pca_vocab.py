#!/usr/bin/env python3
"""
test_pca_vocab.py — CHEAP CHECK. Does the vocab tensor's OWN geometry (PCA)
separate abstract-concepts from proper-nouns from junk? (Gemini's claim)

If yes -> use the eigen-vocab (principled, no Zipf/whitelist). Gemini's right.
If it smears them (like the 4 prior geometric tests) -> use frequency, which we
MEASURED works (95% signal / 85% junk separation). 

Settles geometry-vs-frequency with data. No GPU needed (PCA on cached tensor).
Reads vocab/global_vocab.{json,pt}. Writes nothing live.
"""
import json, numpy as np

def main():
    import torch
    print("loading global_vocab.pt (184k x 1024)...", flush=True)
    meta = json.load(open("vocab/global_vocab.json"))
    words = meta["words"]
    T = torch.load("vocab/global_vocab.pt", map_location="cpu", weights_only=True).numpy().astype(np.float32)
    print(f"  tensor: {T.shape}", flush=True)

    # center + PCA via SVD (top 5 PCs)
    print("centering + PCA (SVD)...", flush=True)
    mu = T.mean(0)
    X = T - mu
    # randomized-ish: full SVD on 184k x 1024 is fine (1024 is small dim)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    PCs = X @ Vt[:5].T   # (184k, 5) projection onto first 5 PCs
    print(f"  projected onto 5 PCs. variance explained: "
          f"{[round(float(s**2/ (S**2).sum()),3) for s in S[:5]]}\n", flush=True)

    # labeled probe words
    SIGNAL = ["cyberwarfare","genocidal","airstrike","deterrence","embargo","insurgency",
              "ceasefire","escalation","annexation","proliferation","sanctions","occupation",
              "warfare","blockade","militia","insurrection","propaganda","surveillance"]
    JUNK   = ["unlashed","robotism","detribalize","electrostate","drowsily","infernally",
              "orphic","alfresco","beryllium"]
    NAMES  = ["poroshenko","steaua","narodnaya","palestina","roumania","meriweather",
              "chavez","zelensky","netanyahu","khamenei"]

    widx = {w:i for i,w in enumerate(words)}
    def show(group, label):
        print(f"=== {label} — PC coordinates ===")
        rows=[]
        for w in group:
            if w in widx:
                p = PCs[widx[w]]
                rows.append((w,p))
                print(f"  {w:16s} PC1={p[0]:+.3f} PC2={p[1]:+.3f} PC3={p[2]:+.3f} PC4={p[3]:+.3f}")
            else:
                print(f"  {w:16s} (not in vocab)")
        return rows

    sig = show(SIGNAL, "SIGNAL (abstract concepts)")
    print()
    jnk = show(JUNK, "JUNK (obscure tail)")
    print()
    nam = show(NAMES, "PROPER NOUNS / transliterations")

    # Does any PC separate the groups? compute per-group means on each PC
    def gmean(rows, pc): 
        v=[p[pc] for _,p in rows]; return (np.mean(v), np.std(v)) if v else (0,0)
    print("\n=== GROUP MEANS per PC (does any PC separate the 3 groups?) ===")
    print(f"{'PC':>4} | {'SIGNAL':>16} | {'JUNK':>16} | {'NAMES':>16}")
    for pc in range(5):
        sm=gmean(sig,pc); jm=gmean(jnk,pc); nm=gmean(nam,pc)
        print(f"{pc+1:>4} | {sm[0]:+.3f}±{sm[1]:.2f}     | {jm[0]:+.3f}±{jm[1]:.2f}     | {nm[0]:+.3f}±{nm[1]:.2f}")

    print("\n=== VERDICT ===")
    print("Look at the group means above:")
    print("  - If some PC cleanly separates SIGNAL from JUNK *and* from NAMES")
    print("    (means far apart relative to the ±std), Gemini is right -> eigen-vocab works.")
    print("  - If SIGNAL/JUNK/NAMES overlap on every PC (means within ~1 std of each other),")
    print("    the geometry does NOT encode the concept/junk/name split -> use frequency (measured 95/85).")
    print("  - PC1 likely tracks frequency (junk extreme on it); that just replicates Zipf.")
    print("    The real question is whether PC2/PC3 split CONCEPTS from NAMES, as Gemini claims.")

if __name__=="__main__":
    main()
