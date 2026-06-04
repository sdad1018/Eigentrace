#!/usr/bin/env python3
"""
build_refusal_centroid.py — Primary-metric instrument for the
figure-attribution / attenuation battery.

Builds, from an EXTERNAL, citable, gated dataset (allenai/xstest-response,
WildGuard project, arXiv:2406.18495), the frozen reference vectors the scorer
will measure model responses against:

  * Centroid A  (hard refusal)      : mean embedding of label=="refusal" responses
  * Baseline    (neutral compliance): mean embedding of label=="compliance"
                                       AND prompt_type=="prompt_safe" responses
  * refusal_axis (normalized)       : (Centroid A - Baseline), L2-normalized

Embedding is done with the SAME frozen stack the rest of EigenTrace uses
(GeometricPerturbationEngine -> BAAI/bge-large-en-v1.5, L2-normalized), so the
frozen vectors are directly comparable (cosine == dot product) to model-response
embeddings at scoring time.

The orthogonal-residual SECONDARY metric is NOT computed here — it is applied to
model responses at scoring time using these frozen vectors, and is reported as an
exploratory measure (semantic drift from neutral compliance not accounted for by
hard refusal; captures softer attenuation but is not specific to it).

PREREQUISITES (must be done before running):
  1. Accept the AI2 Responsible Use terms on the dataset page and authenticate:
       huggingface-cli login        (paste your HF token)
     Without this, load_dataset() will fail on the gated repo.
  2. pip install datasets sentence-transformers   (if not already present)

USAGE:
  python build_refusal_centroid.py
  # optional, for the later two-stack robustness replication:
  python build_refusal_centroid.py --embedding-model some/other-encoder --out-suffix _stack2

OUTPUT (written to ./anamnesis_results/refusal_centroid/):
  centroid_refusal{suffix}.npy     (1024,)  Centroid A
  baseline_neutral{suffix}.npy     (1024,)  Baseline
  refusal_axis{suffix}.npy         (1024,)  normalized (A - baseline)
  manifest{suffix}.json            full provenance (source, cite, counts, date, model, hashes)
"""

from __future__ import annotations
import argparse, json, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _sha(arr: np.ndarray) -> str:
    """Content hash of a frozen vector, for the manifest (reproducibility check)."""
    return hashlib.sha256(arr.tobytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedding-model", default="BAAI/bge-large-en-v1.5",
                    help="Encoder. Default matches production EigenTrace. "
                         "Change ONLY for the separate two-stack replication.")
    ap.add_argument("--out-suffix", default="",
                    help="Filename suffix, e.g. _stack2 for the replication run.")
    ap.add_argument("--out-dir", default="./anamnesis_results/refusal_centroid")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ── 1. Load the gated external dataset ────────────────────────────────
    print("Loading allenai/xstest-response (response_refusal split)...")
    print("  (requires `huggingface-cli login` + accepted AI2 terms)")
    try:
        from datasets import load_dataset
        ds = load_dataset("allenai/xstest-response", split="response_refusal")
    except Exception as e:
        print(f"\nFAILED to load dataset: {e}")
        print("If this is an auth/gating error: run `huggingface-cli login` and")
        print("accept the terms at https://huggingface.co/datasets/allenai/xstest-response")
        return 1

    n_total = len(ds)
    print(f"  Loaded {n_total} items. Columns: {ds.column_names}")

    # ── 2. Filter the three reference sets (with integrity checks) ────────
    # Centroid A: hard refusals. Response text must be present (some WildGuard
    # items are prompt-only -> response is None; those are skipped).
    refusal_texts = [
        r["response"] for r in ds
        if r.get("label") == "refusal" and r.get("response")
    ]
    # Baseline: compliance to SAFE prompts -> genuinely neutral helpful text,
    # NOT compliance to borderline-safety prompts. prompt_type column gives us
    # the clean origin.
    baseline_texts = [
        r["response"] for r in ds
        if r.get("label") == "compliance"
        and r.get("prompt_type") == "prompt_safe"
        and r.get("response")
    ]

    print(f"  Hard-refusal responses (Centroid A): {len(refusal_texts)}")
    print(f"  Safe-compliance responses (Baseline): {len(baseline_texts)}")

    # Refuse to build a degenerate centroid. These are pre-committed sanity floors.
    if len(refusal_texts) < 30:
        print(f"\nABORT: only {len(refusal_texts)} refusal texts — too few for a "
              f"stable centroid. Expected ~178. Check the split/filters.")
        return 1
    if len(baseline_texts) < 20:
        print(f"\nABORT: only {len(baseline_texts)} safe-compliance texts — too few "
              f"for a stable baseline. Check prompt_type filtering.")
        return 1

    # ── 3. Embed on the frozen EigenTrace stack ───────────────────────────
    print(f"\nLoading embedding engine ({args.embedding_model})...")
    from geometric_engine import GeometricPerturbationEngine
    eng = GeometricPerturbationEngine(embedding_model_name=args.embedding_model)

    print("Embedding refusal responses...")
    refusal_vecs = eng.embed_texts(refusal_texts)      # (n_ref, 1024), L2-normalized
    print(f"  shape: {refusal_vecs.shape}")
    print("Embedding baseline responses...")
    baseline_vecs = eng.embed_texts(baseline_texts)    # (n_base, 1024), L2-normalized
    print(f"  shape: {baseline_vecs.shape}")

    dim = int(refusal_vecs.shape[1])

    # ── 4. Centroids via the same compute_centroid the rest of the stack uses
    centroid_refusal = eng.compute_centroid(refusal_vecs)   # (1024,)
    baseline_neutral = eng.compute_centroid(baseline_vecs)  # (1024,)

    # ── 5. Refusal axis = (A - baseline), normalized ──────────────────────
    axis = centroid_refusal - baseline_neutral
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm < 1e-8:
        print("\nABORT: refusal axis ~ zero. Refusal and baseline centroids are "
              "nearly identical — the dataset/filters are not separating refusal "
              "from compliance. Do NOT score against this.")
        return 1
    refusal_axis = axis / axis_norm

    # Diagnostic: how separated are the two reference clouds along the axis?
    # (Not a result — just confirms the instrument has signal before any scoring.)
    ref_proj = float(np.mean(refusal_vecs @ refusal_axis))
    base_proj = float(np.mean(baseline_vecs @ refusal_axis))
    separation = ref_proj - base_proj
    print(f"\nAxis diagnostic (sanity, not a result):")
    print(f"  mean refusal projection : {ref_proj:+.4f}")
    print(f"  mean baseline projection: {base_proj:+.4f}")
    print(f"  separation along axis   : {separation:+.4f}")
    if separation < 0.05:
        print("  WARNING: weak separation. The axis barely distinguishes the two "
              "reference sets; scoring on it will be low-power. Inspect before use.")

    # ── 6. Freeze to disk ─────────────────────────────────────────────────
    suf = args.out_suffix
    np.save(out / f"centroid_refusal{suf}.npy", centroid_refusal)
    np.save(out / f"baseline_neutral{suf}.npy", baseline_neutral)
    np.save(out / f"refusal_axis{suf}.npy", refusal_axis)

    manifest = {
        "instrument": "figure-attribution battery — primary refusal metric",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_before_scoring": True,
        "source_dataset": "allenai/xstest-response",
        "source_split": "response_refusal",
        "source_project": "WildGuard (Allen Institute for AI)",
        "source_citation_arxiv": "2406.18495",
        "source_license": "odc-by",
        "embedding_model": args.embedding_model,
        "embedding_normalized_l2": True,
        "embedding_dim": dim,
        "n_total_items_in_split": n_total,
        "n_refusal_texts_used": len(refusal_texts),
        "n_baseline_texts_used": len(baseline_texts),
        "baseline_definition": "label=='compliance' AND prompt_type=='prompt_safe'",
        "refusal_axis_definition": "normalize(centroid_refusal - baseline_neutral)",
        "axis_separation_diagnostic": separation,
        "secondary_metric_note": (
            "Orthogonal residual displacement is computed at SCORING time, not "
            "here. It captures semantic drift from neutral compliance not "
            "accounted for by hard refusal; it targets softer attenuation "
            "(hedging/dilution/distancing) but is NOT specific to it, and is "
            "reported as an exploratory secondary signal, not a validated hedge "
            "metric."
        ),
        "hashes": {
            "centroid_refusal": _sha(centroid_refusal),
            "baseline_neutral": _sha(baseline_neutral),
            "refusal_axis": _sha(refusal_axis),
        },
    }
    with open(out / f"manifest{suf}.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nFROZEN to {out}/ :")
    print(f"  centroid_refusal{suf}.npy  ({dim},)  hash {manifest['hashes']['centroid_refusal']}")
    print(f"  baseline_neutral{suf}.npy  ({dim},)  hash {manifest['hashes']['baseline_neutral']}")
    print(f"  refusal_axis{suf}.npy      ({dim},)  hash {manifest['hashes']['refusal_axis']}")
    print(f"  manifest{suf}.json")
    print(f"\nPrimary-metric instrument built. Commit these BEFORE running the battery.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
