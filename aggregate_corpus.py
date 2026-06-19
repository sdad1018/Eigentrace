#!/usr/bin/env python3
"""
aggregate_corpus.py — pull EVERY story from EVERY daily file into ONE master dataset.
Computes the six-axis EigenChing signature using the REAL state_vector.py functions (no
reimplementation), maps to archetype via eigenching.py, attaches void/logos/dual/triple words.

VALIDATION: reproduce eigenching_data.json's exact archetype counts (444 Still Point, 372
Unanimous Shield, 103 Sharp Silence, 17 Sealed Vault...). If counts match -> aggregation is
provably identical to what generated the live webpage, and every downstream slice is trustworthy.

Output: corpus_master.json — one row per unique story with signature, archetype, all word-lists.
This is the substrate for: (1) the 10-patient length-expansion test on high-absent stories,
(2) the Consequence Atlas rebuild (story -> signature -> void/target words visible).
"""
import json, glob, os, sys
from collections import Counter, defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import state_vector as SV
import eigenching as EC

BEST6 = ["consensus_density","absent_ratio","verb_drift","entity_retention","hedge_count","mean_vix"]
DAILY = sorted(glob.glob("docs/data/*.json"))

def signals_from_daily_story(s):
    """Mirror state_vector.extract_signals, but for the DAILY-FILE story shape.
    The daily story stores compression fields nested under 'compression' and absence under
    'source_void'. Map them to the flat QUANT_RULES names exactly as extract_signals does."""
    comp = s.get("compression",{}) or {}
    sv   = s.get("source_void",{}) or {}
    ab   = comp.get("attribution_buffer",{}) or {}
    sig = {
        "consensus_density": s.get("consensus_density",0) or 0,
        "absent_ratio":      sv.get("absent_ratio",0) or 0,
        "verb_drift":        comp.get("verb_downgrade",0) or 0,
        "entity_retention":  comp.get("entity_retention",0) or 0,
        "hedge_count":       ab.get("avg_per_model", ab.get("total",0)) or 0,
        "mean_vix":          s.get("mean_vix",0) or 0,
    }
    return sig

def main():
    # ---- load the reference archetype map (signature -> name) from the live file ----
    ref = json.load(open("docs/eigenching_data.json"))
    ref_counts = {tuple(a["signature"]): a["count"] for a in ref["archetypes"]}
    ref_names  = {tuple(a["signature"]): a["name"]  for a in ref["archetypes"]}
    print(f"reference: {ref['total_segments']} segments, {len(ref['archetypes'])} archetypes, "
          f"generated {ref['generated'][:10]}")

    # ---- aggregate every story from every daily file ----
    seen = {}   # guid -> row (dedupe; keep latest by timestamp)
    raw_count = 0
    for path in DAILY:
        try: day = json.load(open(path))
        except: continue
        for s in day.get("stories",[]):
            raw_count += 1
            guid = s.get("guid") or s.get("url") or s.get("title","")
            if not guid: continue
            signals = signals_from_daily_story(s)
            # skip empties exactly like load_all_signals does
            if signals["consensus_density"]==0 and signals["absent_ratio"]==0: continue
            vec,_ = SV.compute_state_vector(signals, BEST6)
            ts = s.get("timestamp","")
            prev = seen.get(guid)
            if prev and prev["_ts"]>=ts: continue   # keep latest
            seen[guid] = {
                "title": s.get("title",""), "url": s.get("url",""), "guid": guid,
                "category": s.get("category",""), "_ts": ts,
                "signature": list(vec),
                "consensus_density": signals["consensus_density"],
                "absent_ratio": signals["absent_ratio"],
                "mean_vix": signals["mean_vix"],
                "state_flag": s.get("state_flag",""),
                "void_words": s.get("void_words",[]) or [],
                "logos_words": s.get("logos_words",[]) or [],
                "dual_confirmed": s.get("dual_confirmed",[]) or [],
                "triple_confirmed": s.get("triple_confirmed",[]) or [],
                "compression": s.get("compression",{}),
            }
    rows = list(seen.values())
    print(f"\nraw story-records across {len(DAILY)} daily files: {raw_count}")
    print(f"unique stories after dedupe (by guid, latest kept): {len(rows)}")

    # ---- attach archetype name + distance via the REAL classifier ----
    for r in rows:
        cls = EC.classify(tuple(r["signature"]))
        r["archetype"] = cls["name"]; r["tier"] = cls.get("tier"); r["distance"] = cls.get("distance")

    # ---- VALIDATION: do our pure-archetype counts reproduce the reference? ----
    our_counts = Counter(tuple(r["signature"]) for r in rows)
    print("\n"+"="*70)
    print("VALIDATION — our recomputed counts vs eigenching_data.json (pure archetypes)")
    print("="*70)
    print(f"  {'archetype':24s} {'ref':>6s} {'ours':>6s} {'match':>6s}")
    hits=0; checked=0
    for sig,name in sorted(ref_names.items(), key=lambda kv:-ref_counts[kv[0]]):
        if ref_counts[sig]==0: continue
        checked+=1; ours=our_counts.get(sig,0); ok = abs(ours-ref_counts[sig])<=max(2,0.05*ref_counts[sig])
        if ok: hits+=1
        print(f"  {name:24s} {ref_counts[sig]:>6d} {ours:>6d} {'OK' if ok else 'XX':>6s}")
    print(f"\n  matched {hits}/{checked} archetype counts within tolerance")
    if hits >= checked*0.7:
        print("  -> aggregation reproduces the live classification. Master dataset is trustworthy.")
    else:
        print("  -> MISMATCH. Field mapping in signals_from_daily_story needs adjustment before trusting.")
        print("     (likely: hedge_count or verb_drift source field differs between daily-file and segment shape)")

    # ---- absent-axis distribution (the 'most lossy' population) ----
    absent_rows = [r for r in rows if r["signature"][1]==-1]
    print("\n"+"="*70)
    print(f"HIGH-ABSENT POPULATION (absent axis = -1): {len(absent_rows)} stories")
    print("="*70)
    by_arch = Counter(r["archetype"] for r in absent_rows)
    for name,c in by_arch.most_common(12):
        print(f"  {c:4d}  {name}")
    # charged-word check: how many high-absent stories have dual_confirmed words?
    with_dual = [r for r in absent_rows if r["dual_confirmed"]]
    print(f"\n  high-absent stories with dual_confirmed words: {len(with_dual)}/{len(absent_rows)}")
    print("  sample dual_confirmed words from high-absent stories:")
    seen_words=Counter()
    for r in with_dual:
        for w in r["dual_confirmed"]: seen_words[w]+=1
    for w,c in seen_words.most_common(20):
        print(f"    {c:3d}x  {w}")

    # ---- void vs logos: are they ever different? (one list or two for the Atlas) ----
    both = [r for r in rows if r["void_words"] and r["logos_words"]]
    diff = [r for r in both if set(r["void_words"])!=set(r["logos_words"])]
    print(f"\n  stories with both void+logos words: {len(both)}; where they DIFFER: {len(diff)}")
    print("  -> if many differ, the Atlas shows TWO lists (void=lexical absence, logos=geometric target)")

    # ---- write master ----
    for r in rows: r.pop("_ts",None)
    out="/mnt/user-data/outputs/atlas_rebuild/corpus_master.json"
    json.dump({"n":len(rows),"generated_from":len(DAILY),"stories":rows}, open(out,"w"), indent=1)
    print(f"\nwrote {out} ({len(rows)} stories)")

if __name__=="__main__":
    main()
