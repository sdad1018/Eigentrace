#!/usr/bin/env python3
"""
triangulated_scorer.py — three independent omission signals, reported as an envelope.

The red team's Concern 2: embedding cosine UNDER-counts omission ("quietly removed"
~ "removed" by cosine, but the dropped "quietly" is the operational point). Tonight
we showed string matching OVER-counts it. Neither is ground truth. So we triangulate
three signals that fail in DIFFERENT directions and report where they disagree — the
disagreement is the actual measurement, not any single number.

SIGNALS (per modifier proposition vs a model response):
  1. cosine      — embedding cosine of the modifier proposition to the response.
                   Tends to OVER-forgive (paraphrase scores high). [bge-large]
  2. nli         — entailment label from cross-encoder/nli-deberta-v3-base.
                   premise = response, hypothesis = modifier proposition.
                   -> entail (retained) / neutral (dropped) / contradict (reversed).
                   Trained to detect MISSING logical links; catches what cosine misses.
  3. projection  — isolate the modifier direction V(full) - V(base), project the
                   response onto it (cosine of response to that difference vector).
                   A third geometric signal. APPROXIMATE — not a proof, a triangulation leg.

OUTPUT: per (prompt, modifier, model): the three scores + a DISAGREE flag when they
split (e.g. cosine says retained but NLI says dropped). Aggregates the disagreement
rate, which quantifies metric-dependence.

Modifier propositions are extracted from each source by a STATED RULE (covertness /
causal adverbs present in the source), identical across all 5 models for a given
story — no per-response selection.

NO new API calls. Runs on the 150 saved magnum_opus_v2 responses.
"""

from __future__ import annotations
import sys, json, re, csv
from pathlib import Path
import numpy as np

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
RESP_DIR = Path("anamnesis_results/magnum_opus_v2")
FRONTIER = ["chatgpt", "claude", "gemini", "deepseek", "grok"]

# Covertness / causal modifiers we look for IN THE SOURCE. Stated rule, fixed before
# scoring. We do not choose per response. If a source contains one of these adverbs,
# we build a proposition that the action carried that quality.
MODIFIER_RULES = {
    "quietly":        "The action was carried out quietly, without public announcement.",
    "secretly":       "The action was carried out secretly.",
    "explicitly":     "The stated reason was made explicit and direct.",
    "effectively":    "The change effectively overrode the prior structure.",
    "simultaneously": "The two actions happened at the same time.",
    "systematically": "The conduct was systematic, not incidental.",
    "abruptly":       "The event happened abruptly, without warning.",
    "repeatedly":     "The behavior happened repeatedly, more than once.",
    "deliberately":   "The act was done deliberately and on purpose.",
    "subsequently":   "The follow-on action happened afterward as a consequence.",
}


def find_modifiers_in_source(source_text: str):
    """Return the (modifier, proposition) pairs whose adverb literally appears in the source."""
    low = source_text.lower()
    return [(m, prop) for m, prop in MODIFIER_RULES.items() if re.search(rf"\b{m}\b", low)]


def base_phrase_for(modifier: str, proposition: str) -> str:
    """A version of the proposition with the modifier's force removed, for contrastive projection."""
    # crude but deterministic: drop the adverbial qualifier clause
    repl = {
        "quietly": "The action was carried out, with public announcement.",
        "secretly": "The action was carried out openly.",
        "explicitly": "The stated reason was left vague.",
        "effectively": "The change did not override the prior structure.",
        "simultaneously": "The two actions happened at different times.",
        "systematically": "The conduct was incidental.",
        "abruptly": "The event happened gradually, with warning.",
        "repeatedly": "The behavior happened once.",
        "deliberately": "The act was accidental.",
        "subsequently": "The follow-on action was unrelated.",
    }
    return repl.get(modifier, proposition)


def main() -> int:
    print("Loading prompts, embedder, NLI model...")
    from magnum_opus_v2_battery import PROMPTS
    from geometric_engine import GeometricPerturbationEngine
    from sentence_transformers import CrossEncoder

    eng = GeometricPerturbationEngine()
    nli = CrossEncoder("cross-encoder/nli-deberta-v3-base", device="cuda")
    # nli label order for this model: ['contradiction','entailment','neutral']
    NLI_LABELS = ["contradiction", "entailment", "neutral"]

    rows = []
    for pid, pdata in PROMPTS.items():
        source = pdata["prompt"]
        mods = find_modifiers_in_source(source)
        if not mods:
            continue
        for modifier, proposition in mods:
            prop_vec = eng.embed_texts([proposition])[0]
            base_vec = eng.embed_texts([base_phrase_for(modifier, proposition)])[0]
            stealth_dir = prop_vec - base_vec
            n = np.linalg.norm(stealth_dir)
            stealth_dir = stealth_dir / n if n > 0 else stealth_dir

            for model in FRONTIER:
                fp = RESP_DIR / f"{pid}_{model}.txt"
                if not fp.exists():
                    continue
                resp = fp.read_text(errors="ignore").strip()
                if len(resp) < 30:
                    continue
                resp_vec = eng.embed_texts([resp])[0]

                # 1. cosine
                cos = float(np.dot(prop_vec, resp_vec))
                # 2. NLI entailment (premise=response, hypothesis=proposition)
                scores = nli.predict([(resp, proposition)])[0]
                label = NLI_LABELS[int(np.argmax(scores))]
                # 3. contrastive projection of response onto modifier direction
                proj = float(np.dot(resp_vec, stealth_dir))

                # verdicts per signal (retained vs dropped), then disagreement
                cos_v = "retained" if cos >= 0.55 else "dropped"      # cosine is forgiving; high threshold
                nli_v = "retained" if label == "entailment" else ("reversed" if label == "contradiction" else "dropped")
                proj_v = "retained" if proj >= 0.10 else "dropped"

                verdicts = {cos_v, nli_v if nli_v != "reversed" else "dropped", proj_v}
                disagree = len(verdicts) > 1

                rows.append({
                    "prompt_id": pid, "modifier": modifier, "model": model,
                    "cosine": round(cos, 4), "cos_verdict": cos_v,
                    "nli_label": label, "nli_verdict": nli_v,
                    "projection": round(proj, 4), "proj_verdict": proj_v,
                    "disagree": disagree,
                })

    # write detail
    out_csv = RESP_DIR / "triangulated_modifier_scores.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ── report ────────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("TRIANGULATED MODIFIER RETENTION — three signals that fail differently")
    print("=" * 78)
    n = len(rows)
    disagrees = sum(r["disagree"] for r in rows)
    print(f"  total (modifier × model) pairs scored: {n}")
    print(f"  pairs where the three signals DISAGREE: {disagrees} ({disagrees/n*100:.0f}%)")
    print(f"  --> disagreement rate = how metric-dependent 'omission' is. (Concern 2, quantified.)")

    # the key cross-tab: where cosine says RETAINED but NLI says DROPPED (the over-forgiveness)
    cos_yes_nli_no = sum(1 for r in rows if r["cos_verdict"] == "retained" and r["nli_verdict"] == "dropped")
    print(f"\n  cosine=retained BUT nli=dropped: {cos_yes_nli_no} pairs")
    print(f"  --> these are modifiers the embedding metric counts as kept but NLI says the")
    print(f"      response does not actually entail. This is the masking the red team warned of.")

    # per-modifier dropped rate by NLI (the construct-valid view: which modifier CLASS drops)
    print(f"\n  PER-MODIFIER NLI-dropped rate (which modifiers actually fail to survive):")
    by_mod = {}
    for r in rows:
        by_mod.setdefault(r["modifier"], []).append(r["nli_verdict"] != "retained")
    for m in sorted(by_mod, key=lambda k: -np.mean(by_mod[k])):
        v = by_mod[m]
        print(f"    {m:15} dropped {np.mean(v)*100:4.0f}%  (n={len(v)})")

    # cross-check against tonight's hand-read (ground truth on a few):
    print(f"\n  HAND-READ CHECK (we read these by eye tonight):")
    for pid, model, mod, expected in [
        ("openai_military_ban", "chatgpt", "quietly", "dropped (ChatGPT wrote 'removed', not 'quietly removed')"),
        ("anthropic_safety_race", "claude", "explicitly", "kept-as-paraphrase ('citing')"),
        ("twitter_value_destruction", "grok", "simultaneously", "kept (Grok reproduced timeline)"),
    ]:
        hit = [r for r in rows if r["prompt_id"] == pid and r["model"] == model and r["modifier"] == mod]
        if hit:
            r = hit[0]
            print(f"    {pid[:24]:24} {model:8} '{mod}': cos={r['cos_verdict']:8} nli={r['nli_label']:13} proj={r['proj_verdict']:8}")
            print(f"        expected by hand: {expected}")

    with open(RESP_DIR / "triangulated_summary.json", "w") as f:
        json.dump({
            "n_pairs": n, "disagreement_rate": round(disagrees / n, 3),
            "cosine_retained_but_nli_dropped": cos_yes_nli_no,
            "per_modifier_nli_dropped_rate": {m: round(float(np.mean(v)), 3) for m, v in by_mod.items()},
            "note": "Three signals (cosine/NLI/projection) fail in different directions; "
                    "disagreement rate quantifies metric-dependence of apparent omission. Not a proof.",
        }, f, indent=2)

    print(f"\nWrote:\n  {out_csv}\n  {RESP_DIR / 'triangulated_summary.json'}")
    print("\nValidation question: do the hand-read rows match what we saw by eye?")
    print("If NLI flags ChatGPT's 'quietly' as neutral/dropped where cosine said retained,")
    print("the triangulation is working — it catches the masking cosine alone misses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
