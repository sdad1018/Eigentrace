#!/usr/bin/env python3
"""
test_delta_v.py — CALIBRATION. Tests Gemini's Context-Delta (ΔV) fix.

DIAGNOSIS (Gemini, correct): bge is a SENTENCE transformer. Bare tokens lack
syntax, so it dumps 'cyberwarfare' and 'unlashed' into the same context-missing
region -> that's why raw-token PCA couldn't separate concepts from junk.

FIX (Gemini, UNTESTED): embed the word inside a carrier frame, subtract the
baseline. The delta = pure contextual semantic weight.
  V_target = embed("The underlying concept here is cyberwarfare.")
  V_base   = embed("The underlying concept here is something.")
  dV = V_target - V_base

CLAIMS TO TEST (against labeled words, before believing):
  1. MAGNITUDE separates concepts from junk:  ||dV(cyberwarfare)|| >> ||dV(unlashed)||
  2. PC1 of deltas isolates NAMES (steaua, poroshenko at a pole)
  3. concepts (incl. low-freq cyberwarfare) get high magnitude

BASELINE TO BEAT: frequency (zipf) already does 95% signal / 85% junk separation.
ΔV must beat that to justify replacing it. If it smears, use frequency.

KEEPS bge. Small GPU job (embed ~60 words x2). STREAM STOPPED.
"""
import numpy as np

SIGNAL = ["cyberwarfare","genocidal","airstrike","deterrence","embargo","insurgency",
          "ceasefire","escalation","annexation","proliferation","sanctions","occupation",
          "warfare","blockade","militia","propaganda","surveillance","insurrection",
          "arms deal","foreign interference","proxy war","regime change"]
JUNK   = ["unlashed","robotism","detribalize","drowsily","infernally","orphic",
          "alfresco","beryllium","fogged","indenture","unrelieved","detribalize"]
NAMES  = ["poroshenko","steaua","narodnaya","palestina","roumania","chavez",
          "zelensky","netanyahu","khamenei","meriweather"]

# carrier frame: rigid neutral syntax; [MASK]->'something' as a real baseline token
FRAME = "The underlying concept being discussed here is {}."
BASE_FILL = "something"

def main():
    from sentence_transformers import SentenceTransformer
    print("loading bge-large-en-v1.5 (KEEPING it — ΔV uses bge better, not replaces)...", flush=True)
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cuda")
    def E(texts): return np.array(model.encode(texts, normalize_embeddings=True, show_progress_bar=False))

    v_base = E([FRAME.format(BASE_FILL)])[0]

    def deltas(words):
        out=[]
        for w in words:
            vt = E([FRAME.format(w)])[0]
            dv = vt - v_base
            out.append((w, dv, float(np.linalg.norm(dv))))
        return out

    print("computing ΔV for SIGNAL / JUNK / NAMES...\n", flush=True)
    sig = deltas(SIGNAL); jnk = deltas(JUNK); nam = deltas(NAMES)

    # ---- CLAIM 1: magnitude separates concepts from junk ----
    print("=== CLAIM 1: does ΔV MAGNITUDE separate concepts from junk? ===")
    print("  (Gemini predicts SIGNAL high magnitude, JUNK low magnitude)\n")
    print("  SIGNAL magnitudes (sorted):")
    for w,_,m in sorted(sig,key=lambda x:x[2]): print(f"    {m:.3f}  {w}")
    print("  JUNK magnitudes (sorted):")
    for w,_,m in sorted(jnk,key=lambda x:x[2]): print(f"    {m:.3f}  {w}")
    s_mags=[m for _,_,m in sig]; j_mags=[m for _,_,m in jnk]
    print(f"\n  SIGNAL mag: mean={np.mean(s_mags):.3f} min={min(s_mags):.3f}")
    print(f"  JUNK   mag: mean={np.mean(j_mags):.3f} max={max(j_mags):.3f}")
    # separation: is there a magnitude threshold splitting them?
    overlap = max(min(s_mags), 0) <= max(j_mags)
    print(f"  SIGNAL.min={min(s_mags):.3f} vs JUNK.max={max(j_mags):.3f} -> "
          f"{'OVERLAP (no clean threshold)' if min(s_mags)<=max(j_mags) else 'SEPARABLE by magnitude'}")
    # threshold test
    print("\n  magnitude threshold test:")
    allm = [(m,'S') for m in s_mags]+[(m,'J') for m in j_mags]
    for cut in np.percentile([m for m,_ in allm],[40,50,60]):
        s_keep=sum(1 for m in s_mags if m>=cut); j_cut=sum(1 for m in j_mags if m<cut)
        print(f"    mag>={cut:.3f}: SIGNAL kept {s_keep}/{len(s_mags)} | JUNK cut {j_cut}/{len(j_mags)}")

    # ---- CLAIM 2: PC1 of deltas isolates names ----
    print("\n=== CLAIM 2: does PC1 of ΔV isolate NAMES? ===")
    allw = sig+jnk+nam
    M = np.vstack([dv for _,dv,_ in allw])
    Mc = M - M.mean(0)
    U,S_,Vt = np.linalg.svd(Mc, full_matrices=False)
    pc = Mc @ Vt[:3].T
    labels = ['S']*len(sig)+['J']*len(jnk)+['N']*len(nam)
    for pcn in range(3):
        svals=[pc[i,pcn] for i in range(len(allw)) if labels[i]=='S']
        jvals=[pc[i,pcn] for i in range(len(allw)) if labels[i]=='J']
        nvals=[pc[i,pcn] for i in range(len(allw)) if labels[i]=='N']
        print(f"  PC{pcn+1}: SIGNAL {np.mean(svals):+.3f}±{np.std(svals):.2f} | "
              f"JUNK {np.mean(jvals):+.3f}±{np.std(jvals):.2f} | NAMES {np.mean(nvals):+.3f}±{np.std(nvals):.2f}")

    # ---- VERDICT ----
    print("\n=== VERDICT ===")
    mag_works = min(s_mags) > max(j_mags)*0.95  # rough: signal floor near/above junk ceiling
    print(f"  CLAIM 1 (magnitude separates concept/junk): "
          f"{'PLAUSIBLE — check threshold table' if np.mean(s_mags)>np.mean(j_mags)+0.02 else 'FAILS — junk magnitudes overlap signal'}")
    print(f"  Compare to FREQUENCY baseline: zipf already gives 95%/85% separation.")
    print(f"  -> If ΔV magnitude beats that cleanly, build eigen-vocab (Gemini wins).")
    print(f"  -> If it overlaps like the table shows, use frequency floor + PC1 name-filter.")

if __name__=="__main__":
    main()
