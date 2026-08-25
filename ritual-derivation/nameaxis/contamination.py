#!/usr/bin/env python3
"""
contamination.py — do the ten readers read the five pairs' names darker than the ten decoys,
under a prompt that forbids reference to events?  (SPEC §9.6)

Measure: per word, the fraction of parsed readings whose `reading` or `chain` contains a
dark-lexicon token (after the same crude lemmatizer synth.py uses).  Pooled across models and
samples, and also per model.

Groups: pairs' names vs decoys.  Exclusion rule (generalizing the spec's stated exclusions of
'Harvest' and 'Fyre'): any word whose OWN tokens contain a dark token is excluded from the
comparison, because the reader would be reading the token, not the name.  With the locked
lists this removes: 'Harvest', 'Route 91 Harvest', 'Eagles of Death Metal'; 'Fyre' is excluded by name.
Excluded words are still reported individually.

Test: exact one-sided Mann-Whitney (pairs > decoys) on the per-word dark fractions.
Per-model: dark fraction on pair words minus decoy words, ranked — which readers are most
contaminated.

Consequence (locked): if p < 0.05, every reading of a famous name in the spread carries the
provenance line "readers may be influenced by knowledge of events associated with this name".

Usage:  python3 nameaxis/contamination.py [--in out/readings] [--out out/contamination.md]
"""
import argparse, json, pathlib, re, sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from synth import toks, lemma, slug  # noqa: E402

NAMES = json.loads((HERE / "events" / "names.json").read_text(encoding="utf-8"))

DARK = """death dead die dying kill killed killing slaughter sacrifice harvest reap reaper blood bleed
sin hell underworld tomb grave trap cage prison bind bound chain chains fire burn burning fall fallen
devil satan lucifer saturn chronos kronos wound scythe""".split()
DARK_LEMMA = {lemma(w) for w in DARK} | set(DARK)
EXPLICIT_EXCLUDE = {"Fyre"}  # spec §9.6 names it (homophone of fire); the token rule alone would miss it


def is_dark(text):
    return any(t in DARK_LEMMA for t in toks(text))


def word_stats(indir, word):
    d = pathlib.Path(indir) / slug(word)
    per_model = defaultdict(lambda: [0, 0])  # dark, total
    for p in d.glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not rec.get("parsed"):
            continue
        for r in rec["parsed"]:
            dark = is_dark(f"{r.get('reading','')} {r.get('chain','')}")
            per_model[rec["model"]][0] += int(dark)
            per_model[rec["model"]][1] += 1
    tot_d = sum(v[0] for v in per_model.values())
    tot_n = sum(v[1] for v in per_model.values())
    return (tot_d / tot_n if tot_n else None), tot_n, {m: (v[0] / v[1] if v[1] else None) for m, v in per_model.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="indir", default="out/readings")
    ap.add_argument("--out", default="out/contamination.md")
    args = ap.parse_args()

    pair_words = [w for ws in NAMES["pairs"].values() for w in ws]
    decoys = NAMES["decoys"]
    excluded = [w for w in pair_words + decoys if is_dark(w) or w in EXPLICIT_EXCLUDE]

    rows = {}
    for w in pair_words + decoys:
        frac, n, pm = word_stats(args.indir, w)
        rows[w] = {"group": "pair" if w in pair_words else "decoy", "frac": frac, "n": n, "per_model": pm,
                   "excluded": w in excluded}

    A = [r["frac"] for w, r in rows.items() if r["group"] == "pair" and not r["excluded"] and r["frac"] is not None]
    B = [r["frac"] for w, r in rows.items() if r["group"] == "decoy" and not r["excluded"] and r["frac"] is not None]

    p = None
    try:
        from scipy.stats import mannwhitneyu
        if A and B:
            res = mannwhitneyu(A, B, alternative="greater", method="exact")
            p = float(res.pvalue)
            U = float(res.statistic)
    except Exception as e:  # scipy missing: report ranks only
        U = None
        print(f"(scipy unavailable: {e})")

    # per model: mean dark fraction on pair words minus decoys (excluded words dropped)
    models = sorted({m for r in rows.values() for m in r["per_model"]})
    pm_delta = {}
    for m in models:
        a = [r["per_model"][m] for w, r in rows.items() if r["group"] == "pair" and not r["excluded"]
             and r["per_model"].get(m) is not None]
        b = [r["per_model"][m] for w, r in rows.items() if r["group"] == "decoy" and not r["excluded"]
             and r["per_model"].get(m) is not None]
        if a and b:
            pm_delta[m] = (sum(a) / len(a), sum(b) / len(b), sum(a) / len(a) - sum(b) / len(b))

    L = ["# Contamination check (SPEC §9.6)", "",
         f"Dark lexicon ({len(DARK)} tokens): {' '.join(DARK)}", "",
         f"Excluded from the comparison (own tokens are dark): {', '.join(excluded) or 'none'}", "",
         "| word | group | dark fraction | readings | in comparison |", "|---|---|---|---|---|"]
    for w, r in sorted(rows.items(), key=lambda kv: (kv[1]["group"], -(kv[1]["frac"] or 0))):
        L.append(f"| {w} | {r['group']} | {'—' if r['frac'] is None else f'{r['frac']:.3f}'} | {r['n']} | "
                 f"{'no' if r['excluded'] or r['frac'] is None else 'yes'} |")
    L += ["", f"Pairs (n={len(A)}) mean dark fraction: {sum(A)/len(A):.3f}" if A else "Pairs: no data",
          f"Decoys (n={len(B)}) mean dark fraction: {sum(B)/len(B):.3f}" if B else "Decoys: no data",
          (f"Exact one-sided Mann–Whitney (pairs > decoys): U = {U:.0f}, p = {p:.4f}" if p is not None
           else "Mann–Whitney: not computed"),
          "",
          ("**Consequence: p < 0.05 → famous-name provenance note ENABLED.**" if (p is not None and p < 0.05)
           else "**Consequence: provenance note not triggered by this check.**"),
          "", "## Per reader (pair mean − decoy mean, dark fraction)", "",
          "| reader | pairs | decoys | delta |", "|---|---|---|---|"]
    for m, (a, b, dlt) in sorted(pm_delta.items(), key=lambda kv: -kv[1][2]):
        L.append(f"| {m} | {a:.3f} | {b:.3f} | {dlt:+.3f} |")
    md = "\n".join(L) + "\n"
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(md, encoding="utf-8")
    try:
        print(md)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
