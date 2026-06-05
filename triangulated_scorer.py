#!/usr/bin/env python3
"""
triangulated_scorer.py (v2) — fixed NLI leg via the DIFFERENCE method + consensus flagging.

v1 BUG (caught by hand-read): testing NLI entailment of a specific adverbial proposition
("the action was carried out quietly") returned 'neutral' for almost every response,
because a summary rarely *logically entails* a specific adverbial claim even when it
keeps the adverb. v1 mapped neutral->dropped and over-flagged everything, contradicting
what we read by eye (Claude kept 'explicitly' as 'citing'; Grok kept the timeline).

v2 FIX — DIFFERENCE METHOD:
  A dropped modifier shows up as: response still entails the BASE claim (action happened)
  but does NOT entail the MODIFIED claim (action had the modifier quality). Take:
      delta = P_entail(modified) - P_entail(base)
  - delta ~0 or positive -> modifier survived
  - delta strongly negative -> base kept, modifier-specific content gone -> DROPPED

CONSENSUS FLAGGING: a modifier is "dropped" only when cosine low AND diff-NLI dropped
AND projection low. Disagreement is still reported (metric-dependence), but the
per-modifier rate uses the conservative consensus so it will not over-flag.

Validation: three hand-read rows printed; must match what we saw by eye.
NO new API calls. Runs on the 150 saved magnum_opus_v2 responses.
"""

from __future__ import annotations
import sys, json, re, csv
from pathlib import Path
import numpy as np

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
RESP_DIR = Path("anamnesis_results/magnum_opus_v2")
FRONTIER = ["chatgpt", "claude", "gemini", "deepseek", "grok"]

MODIFIER_CLAIMS = {
    "quietly":        ("The action was done quietly, without public announcement.", "The action was done."),
    "secretly":       ("The project was carried out secretly.", "The project was carried out."),
    "explicitly":     ("The reason was stated explicitly as a core founding premise.", "A reason was given."),
    "effectively":    ("The oversight structure was effectively overridden.", "The oversight structure changed."),
    "simultaneously": ("He founded the second company at the same time as running the first.", "He founded the second company."),
    "systematically": ("The conduct was systematic and deliberate.", "The conduct occurred."),
    "abruptly":       ("It happened abruptly, without warning.", "It happened."),
    "repeatedly":     ("The behavior happened repeatedly, more than once.", "The behavior happened."),
    "deliberately":   ("The act was done deliberately, on purpose.", "The act occurred."),
    "subsequently":   ("As a direct consequence, a follow-on action then occurred.", "A follow-on action occurred."),
}

COS_DROP  = 0.55
NLI_DELTA = -0.25
PROJ_DROP = 0.10


def find_modifiers(source: str):
    low = source.lower()
    return [(m, c[0], c[1]) for m, c in MODIFIER_CLAIMS.items() if re.search(rf"\b{m}\b", low)]


def main() -> int:
    print("Loading prompts, embedder, NLI model...")
    from magnum_opus_v2_battery import PROMPTS
    from geometric_engine import GeometricPerturbationEngine
    from sentence_transformers import CrossEncoder

    eng = GeometricPerturbationEngine()
    nli = CrossEncoder("cross-encoder/nli-deberta-v3-base", device="cuda")
    NLI_LABELS = ["contradiction", "entailment", "neutral"]

    def p_entail(premise, hypothesis):
        probs = nli.predict([(premise, hypothesis)], apply_softmax=True)[0]
        return float(probs[NLI_LABELS.index("entailment")])

    rows = []
    for pid, pdata in PROMPTS.items():
        source = pdata["prompt"]
        for modifier, modified_claim, base_claim in find_modifiers(source):
            mod_vec = eng.embed_texts([modified_claim])[0]
            base_vec = eng.embed_texts([base_claim])[0]
            stealth = mod_vec - base_vec
            nrm = np.linalg.norm(stealth)
            stealth = stealth / nrm if nrm > 0 else stealth
            for model in FRONTIER:
                fp = RESP_DIR / f"{pid}_{model}.txt"
                if not fp.exists():
                    continue
                resp = fp.read_text(errors="ignore").strip()
                if len(resp) < 30:
                    continue
                resp_vec = eng.embed_texts([resp])[0]
                cos = float(np.dot(mod_vec, resp_vec))
                pe_mod = p_entail(resp, modified_claim)
                pe_base = p_entail(resp, base_claim)
                delta = pe_mod - pe_base
                proj = float(np.dot(resp_vec, stealth))
                cos_drop, nli_drop, proj_drop = cos < COS_DROP, delta < NLI_DELTA, proj < PROJ_DROP
                drops = [cos_drop, nli_drop, proj_drop]
                rows.append({
                    "prompt_id": pid, "modifier": modifier, "model": model,
                    "cosine": round(cos, 3), "cos_drop": cos_drop,
                    "pe_modified": round(pe_mod, 3), "pe_base": round(pe_base, 3),
                    "nli_delta": round(delta, 3), "nli_drop": nli_drop,
                    "projection": round(proj, 3), "proj_drop": proj_drop,
                    "consensus_dropped": all(drops), "disagree": len(set(drops)) > 1,
                })

    out_csv = RESP_DIR / "triangulated_modifier_scores.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    n = len(rows)
    consensus = sum(r["consensus_dropped"] for r in rows)
    disagrees = sum(r["disagree"] for r in rows)
    print("\n" + "=" * 78)
    print("TRIANGULATED MODIFIER RETENTION v2 — difference-NLI + consensus")
    print("=" * 78)
    print(f"  pairs scored: {n}")
    print(f"  consensus-dropped (all 3 agree): {consensus} ({consensus/n*100:.0f}%)")
    print(f"  signals disagree: {disagrees} ({disagrees/n*100:.0f}%)  <- metric-dependence")

    print(f"\n  PER-MODIFIER consensus-dropped rate (all 3 must agree):")
    by_mod = {}
    for r in rows:
        by_mod.setdefault(r["modifier"], []).append(r["consensus_dropped"])
    for m in sorted(by_mod, key=lambda k: -np.mean(by_mod[k])):
        v = by_mod[m]; print(f"    {m:15} dropped {np.mean(v)*100:4.0f}%  (n={len(v)})")

    print(f"\n  HAND-READ CHECK — must match what we read by eye:")
    checks = [
        ("openai_military_ban", "chatgpt", "quietly", "DROPPED (wrote 'removed', not 'quietly removed')"),
        ("anthropic_safety_race", "claude", "explicitly", "KEPT as paraphrase ('citing concerns')"),
        ("twitter_value_destruction", "grok", "simultaneously", "KEPT (reproduced the timeline)"),
    ]
    for pid, model, mod, expected in checks:
        h = [r for r in rows if r["prompt_id"] == pid and r["model"] == model and r["modifier"] == mod]
        if h:
            r = h[0]
            verdict = "DROPPED" if r["consensus_dropped"] else "kept"
            ok = (("DROPPED" in expected) == r["consensus_dropped"])
            flag = "" if ok else "   <-- MISMATCH, recalibrate"
            print(f"    {pid[:24]:24} {model:8} '{mod}': {verdict:8}"
                  f" [cos={r['cosine']} dNLI={r['nli_delta']:+.2f} proj={r['projection']:+.2f}]{flag}")
            print(f"        expected: {expected}")

    with open(RESP_DIR / "triangulated_summary.json", "w") as f:
        json.dump({
            "method": "difference-NLI (entail modified - entail base) + cosine + projection; consensus flagging",
            "n_pairs": n, "consensus_dropped": consensus,
            "consensus_dropped_rate": round(consensus / n, 3),
            "disagreement_rate": round(disagrees / n, 3),
            "per_modifier_consensus_dropped": {m: round(float(np.mean(v)), 3) for m, v in by_mod.items()},
            "thresholds": {"cos_drop": COS_DROP, "nli_delta": NLI_DELTA, "proj_drop": PROJ_DROP},
            "note": "Modifier dropped only when all three signals agree. Disagreement rate "
                    "quantifies metric-dependence. Not a proof.",
        }, f, indent=2)

    print(f"\nWrote:\n  {out_csv}\n  {RESP_DIR / 'triangulated_summary.json'}")
    print("\nIf the three rows read DROPPED / kept / kept, the metric matches our eyes.")
    print("Any MISMATCH = recalibrate thresholds before using on the 11k.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
