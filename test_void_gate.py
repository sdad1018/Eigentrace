#!/usr/bin/env python3
"""
test_void_gate.py — OUT-OF-TREE A/B test. Does consensus divergence
(consensus_density / mean_vix) cleanly separate MEANINGFUL consensus-void
stories (Iran->WWIII) from NOISE stories (fireworks->solo,idiocy,trump)?

READS STORED DATA ONLY. No embeddings, no GPU, no recompute, no live code
touched. Imports nothing from the repo. Pure scan of segment JSONs.

The question: if we gate void words on divergence, does the fireworks story
(tight consensus -> donut empty -> fallback noise) get correctly EMPTIED,
while the Iran story (real divergence -> real void) gets KEPT?

If divergence separates the buckets, the gate is real and we port it.
If it doesn't, we learn that BEFORE editing anything.
"""
import json, glob, statistics, sys

SEG_DIR = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"

def harvest():
    rows = []
    for f in glob.glob(SEG_DIR):
        try:
            d = json.load(open(f)); a = d.get("attribution", {})
            mr = a.get("model_responses", {})
            if len([m for m,t in mr.items() if t and len(t) > 50]) < 4:  continue
            if len(a.get("source_body","") or a.get("story_title","")) < 1: continue
            vw = a.get("void_words") or []
            if not vw: continue
            rows.append({
                "title": (a.get("story_title") or d.get("title") or "")[:75],
                "density": a.get("consensus_density"),
                "mean_vix": a.get("mean_vix"),
                "model_vix": a.get("model_vix"),
                "void": a.get("synthesis_words") or vw[:5],
                "source_void": (a.get("source_void") or [])[:5],
                "category": a.get("category",""),
            })
        except: pass
    return rows

def dist(label, vals):
    vals = [v for v in vals if isinstance(v,(int,float))]
    if not vals:
        print(f"  {label}: NONE STORED"); return None
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    def pct(p): return vals_sorted[min(n-1, int(p*n))]
    print(f"  {label}: n={n} min={vals_sorted[0]:.3f} "
          f"p10={pct(.10):.3f} p25={pct(.25):.3f} median={pct(.50):.3f} "
          f"p75={pct(.75):.3f} p90={pct(.90):.3f} max={vals_sorted[-1]:.3f}")
    return vals_sorted

def main():
    rows = harvest()
    print(f"=== harvested {len(rows)} stories with void_words + >=4 responses ===\n")

    print("=== DIVERGENCE DISTRIBUTIONS (where to set the gate) ===")
    dens = dist("consensus_density", [r["density"] for r in rows])
    vix  = dist("mean_vix         ", [r["mean_vix"] for r in rows])
    print()

    # How many stories even HAVE each signal?
    have_dens = sum(1 for r in rows if isinstance(r["density"],(int,float)))
    have_vix  = sum(1 for r in rows if isinstance(r["mean_vix"],(int,float)))
    print(f"  stories with density stored: {have_dens}/{len(rows)}")
    print(f"  stories with mean_vix stored: {have_vix}/{len(rows)}\n")

    # ---- The eyeball test: sort stories by density, show the extremes ----
    # Hypothesis: HIGH density (tight agreement) = noise void; LOW density = real void
    have = [r for r in rows if isinstance(r["density"],(int,float))]
    have.sort(key=lambda r: r["density"])

    print("=== LOWEST density (most divergence) — should be MEANINGFUL voids ===")
    for r in have[:12]:
        print(f"  [{r['density']:.3f}] {r['title']}")
        print(f"          void: {r['void']}")

    print("\n=== HIGHEST density (tightest agreement) — should be NOISE/trivial voids ===")
    for r in have[-12:]:
        print(f"  [{r['density']:.3f}] {r['title']}")
        print(f"          void: {r['void']}")

    # ---- Gate simulation at candidate thresholds ----
    print("\n=== GATE SIMULATION: how many stories EMPTIED at each density cutoff ===")
    print("    (gate = if density > cutoff, consensus too tight -> empty the void)")
    for cut in [0.85, 0.88, 0.90, 0.92, 0.94]:
        emptied = sum(1 for r in have if r["density"] > cut)
        kept = len(have) - emptied
        print(f"    density > {cut:.2f}:  {emptied:4d} emptied ({100*emptied/len(have):.0f}%)  |  {kept:4d} kept")

    # ---- Keyword probe: do conflict/escalation words concentrate in low-density? ----
    print("\n=== SIGNAL PROBE: do 'escalation' words concentrate in LOW-density (real) voids? ===")
    esc_terms = {"war","wwiii","wwii","nuclear","arms","blockade","invasion","missile",
                 "strike","genocid","jihad","militar","proxy","ceasefire","casualt","escalat"}
    def has_esc(r): return any(any(e in w.lower() for e in esc_terms) for w in r["void"])
    lo = have[:len(have)//3]; hi = have[-len(have)//3:]
    lo_esc = sum(1 for r in lo if has_esc(r)); hi_esc = sum(1 for r in hi if has_esc(r))
    print(f"    low-density third  (real voids?):  {lo_esc}/{len(lo)} have escalation words ({100*lo_esc/len(lo):.0f}%)")
    print(f"    high-density third (noise voids?): {hi_esc}/{len(hi)} have escalation words ({100*hi_esc/len(hi):.0f}%)")
    print("    -> if low >> high, divergence separates real signal from noise. Gate is real.")

if __name__ == "__main__":
    main()
