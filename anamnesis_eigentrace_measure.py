#!/usr/bin/env python3
"""
Anamnesis EigenTrace Measurement — applies the actual geometric engine
to measure claim retention, not string matching.

Embeds all 109 claims individually. Embeds each model response.
Computes per-claim cosine similarity. Produces a full retention heatmap.

Free. Deterministic. No API calls for measurement.
Uses BGE-large-en-v1.5 frozen embeddings — same as production EigenTrace.
"""

import json, sys
import numpy as np
from pathlib import Path
from datetime import datetime

def run_eigentrace_measurement(results_path: str):
    """Apply EigenTrace geometric measurement to battery results."""

    print("Loading geometric engine...")
    from geometric_engine import GeometricPerturbationEngine
    eng = GeometricPerturbationEngine()  # BGE-large, 1024-dim, frozen

    print("Loading vocabulary tensor...")
    try:
        from latent_retrieval import VocabTensor
        vt = VocabTensor("./vocab")
        has_vt = True
        print(f"  Vocab tensor: {len(vt.words)} concepts")
    except Exception as e:
        vt, has_vt = None, False
        print(f"  No vocab tensor: {e}")

    # Load battery results
    results = json.load(open(results_path))
    phase1 = results["phases"].get("phase1_baseline", {})

    # Import the claims list
    from anamnesis_test_battery import ALL_CLAIMS, CLAIMS, PROMPT_CORE

    # ── Step 1: Embed the prompt ──────────────────────────────────────────
    print("\nEmbedding prompt...")
    prompt_vec = eng.embed_texts([PROMPT_CORE])[0]  # (1024,)

    # ── Step 2: Embed each claim individually ─────────────────────────────
    print(f"Embedding {len(ALL_CLAIMS)} individual claims...")
    claim_texts = []
    claim_ids = []
    claim_cats = []
    for claim_id, search_term, category in ALL_CLAIMS:
        claim_texts.append(search_term)
        claim_ids.append(claim_id)
        claim_cats.append(category)

    claim_vecs = eng.embed_texts(claim_texts)  # (109, 1024)
    print(f"  Claim embeddings: {claim_vecs.shape}")

    # ── Step 3: Embed each model response ─────────────────────────────────
    print("\nMeasuring per-model claim retention (cosine similarity)...")

    model_responses = {}
    for model_name, data in phase1.items():
        if data.get("runs") and "response_text" in data["runs"][0]:
            model_responses[model_name] = data["runs"][0]["response_text"]

    if not model_responses:
        print("ERROR: No response texts found in results")
        return

    # Full retention matrix: (models × claims) → cosine similarity
    retention_matrix = {}
    response_vecs = {}

    for model_name, response_text in model_responses.items():
        resp_vec = eng.embed_texts([response_text])[0]  # (1024,)
        response_vecs[model_name] = resp_vec

        # Per-claim cosine similarity
        sims = np.dot(claim_vecs, resp_vec)  # (109,) — embeddings already L2-normalized
        retention_matrix[model_name] = sims

    # ── Step 4: Print retention heatmap ───────────────────────────────────
    RETAIN_THRESHOLD = 0.45
    PARTIAL_THRESHOLD = 0.35
    DROP_THRESHOLD = 0.30

    models = sorted(retention_matrix.keys())
    header = f"{'Claim':<30} {'Cat':<15} " + " ".join(f"{m:>10}" for m in models) + "  Status"
    print(f"\n{'='*len(header)}")
    print("EIGENTRACE CLAIM RETENTION HEATMAP")
    print(f"Threshold: >{RETAIN_THRESHOLD}=retained, {PARTIAL_THRESHOLD}-{RETAIN_THRESHOLD}=partial, <{DROP_THRESHOLD}=dropped")
    print(f"{'='*len(header)}")
    print(header)
    print("-" * len(header))

    # Stats accumulators
    cat_scores = {}
    model_retained = {m: 0 for m in models}
    model_partial = {m: 0 for m in models}
    model_dropped = {m: 0 for m in models}
    universal_voids = []
    universal_retained = []

    for i, (claim_id, search_term, category) in enumerate(ALL_CLAIMS):
        scores = [float(retention_matrix[m][i]) for m in models]
        score_strs = []
        statuses = []

        for j, m in enumerate(models):
            s = scores[j]
            if s >= RETAIN_THRESHOLD:
                score_strs.append(f"\033[32m{s:>10.3f}\033[0m")  # green
                statuses.append("retained")
                model_retained[m] += 1
            elif s >= PARTIAL_THRESHOLD:
                score_strs.append(f"\033[33m{s:>10.3f}\033[0m")  # yellow
                statuses.append("partial")
                model_partial[m] += 1
            elif s >= DROP_THRESHOLD:
                score_strs.append(f"\033[33m{s:>10.3f}\033[0m")  # yellow
                statuses.append("weak")
                model_partial[m] += 1
            else:
                score_strs.append(f"\033[31m{s:>10.3f}\033[0m")  # red
                statuses.append("dropped")
                model_dropped[m] += 1

        # Accumulate per-category
        if category not in cat_scores:
            cat_scores[category] = {m: [] for m in models}
        for j, m in enumerate(models):
            cat_scores[category][m].append(scores[j])

        # Universal status
        if all(s == "dropped" for s in statuses):
            status = "VOID"
            universal_voids.append(claim_id)
        elif all(s == "retained" for s in statuses):
            status = "HELD"
            universal_retained.append(claim_id)
        else:
            status = "SPLIT"

        # Truncate claim_id for display
        cid_short = claim_id[:28]
        cat_short = category[:13]
        print(f"{cid_short:<30} {cat_short:<15} " + " ".join(score_strs) + f"  {status}")

    # ── Step 5: Summary Statistics ────────────────────────────────────────
    total = len(ALL_CLAIMS)
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    print(f"\nPer-model retention (>{RETAIN_THRESHOLD} cosine):")
    for m in models:
        r = model_retained[m]
        p = model_partial[m]
        d = model_dropped[m]
        print(f"  {m:<12} retained: {r:>3}/{total} ({100*r/total:>5.1f}%)  "
              f"partial: {p:>3}  dropped: {d:>3}")

    print(f"\nUniversal voids (ALL models < {DROP_THRESHOLD}): {len(universal_voids)}")
    print(f"Universal retained (ALL models > {RETAIN_THRESHOLD}): {len(universal_retained)}")

    # Per-category mean similarity
    print(f"\nPer-category mean cosine similarity:")
    for cat in sorted(cat_scores.keys()):
        cat_means = {}
        for m in models:
            cat_means[m] = round(np.mean(cat_scores[cat][m]), 3)
        overall = round(np.mean([v for vals in cat_scores[cat].values() for v in vals]), 3)
        detail = " ".join(f"{m}:{cat_means[m]:.3f}" for m in models)
        print(f"  {cat:<18} overall: {overall:.3f}  ({detail})")

    # ── Step 6: VIX — per-model distance from prompt ─────────────────────
    print(f"\nVIX (cosine distance from original prompt × 100):")
    for m in models:
        cos = float(np.dot(response_vecs[m], prompt_vec))
        vix = round((1 - cos) * 100, 1)
        print(f"  {m:<12} VIX: {vix}")

    # ── Step 7: SVD Null Space ────────────────────────────────────────────
    print(f"\nSVD Null Space Analysis:")
    resp_matrix = np.stack([response_vecs[m] for m in models])  # (N, 1024)
    centered = resp_matrix - resp_matrix.mean(axis=0)
    cov = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    null_vec = eigenvectors[:, np.argmin(eigenvalues)]
    null_vec = null_vec / np.linalg.norm(null_vec)

    # Project each claim onto the null space
    null_projections = np.dot(claim_vecs, null_vec)  # (109,)
    # Most negative = deepest in the null space = most collectively avoided
    ranked = np.argsort(null_projections)

    print("  Claims deepest in the null space (most collectively avoided):")
    for idx in ranked[:10]:
        cid = claim_ids[idx]
        cat = claim_cats[idx]
        proj = null_projections[idx]
        print(f"    [{cat}] {cid}: null_alignment={proj:.4f}")

    print("\n  Claims most OUTSIDE the null space (least avoided):")
    for idx in ranked[-5:]:
        cid = claim_ids[idx]
        cat = claim_cats[idx]
        proj = null_projections[idx]
        print(f"    [{cat}] {cid}: null_alignment={proj:.4f}")

    # ── Step 8: Logos Synthesis on responses ──────────────────────────────
    if has_vt:
        print(f"\nLogos Synthesis (anti-consensus point on unit hypersphere):")
        try:
            import torch
            from geometric_engine import reconstruct_unaligned_truth
            resp_tensor = torch.tensor(resp_matrix, dtype=torch.float32)
            prompt_tensor = torch.tensor(prompt_vec, dtype=torch.float32)
            x_star = reconstruct_unaligned_truth(
                resp_tensor, steps=150, lr=0.05, headline_vec=prompt_tensor
            )
            x_np = x_star.cpu().numpy()
            logos_words = vt.nearest_concepts(x_np, k=10)
            print(f"  Logos words (what models orbit but refuse to name):")
            for w, s in logos_words:
                print(f"    {w}: {s:.4f}")
        except Exception as e:
            print(f"  Logos synthesis failed: {e}")

    # ── Step 9: Emergence Vectors ─────────────────────────────────────────
    if has_vt:
        print(f"\nEmergence Analysis (orthogonal residual → vocab tensor):")
        for m in models:
            r_vec = response_vecs[m]
            projection = np.dot(r_vec, prompt_vec) * prompt_vec
            e_vec = r_vec - projection
            e_norm = np.linalg.norm(e_vec)
            if e_norm > 1e-6:
                e_vec_normed = e_vec / e_norm
                emerged = vt.nearest_concepts(e_vec_normed, k=5)
                top = ", ".join(f"{w}({s:.3f})" for w, s in emerged)
                print(f"  {m:<12} ||e||={e_norm:.4f}  emerged: {top}")

    # ── Save full measurement ─────────────────────────────────────────────
    output = {
        "timestamp": datetime.now().isoformat(),
        "method": "eigentrace_geometric_measurement",
        "embedding_model": "BAAI/bge-large-en-v1.5",
        "dimensions": 1024,
        "thresholds": {
            "retained": RETAIN_THRESHOLD,
            "partial": PARTIAL_THRESHOLD,
            "dropped": DROP_THRESHOLD,
        },
        "retention_matrix": {
            m: {claim_ids[i]: round(float(retention_matrix[m][i]), 4)
                for i in range(len(ALL_CLAIMS))}
            for m in models
        },
        "per_model_summary": {
            m: {
                "retained": model_retained[m],
                "partial": model_partial[m],
                "dropped": model_dropped[m],
                "retention_rate": round(model_retained[m] / total, 3),
            }
            for m in models
        },
        "universal_voids": universal_voids,
        "universal_retained": universal_retained,
        "per_category_means": {
            cat: {m: round(float(np.mean(cat_scores[cat][m])), 4) for m in models}
            for cat in cat_scores
        },
    }

    out_path = Path("anamnesis_results") / f"eigentrace_measurement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull measurement saved: {out_path}")


if __name__ == "__main__":
    results_dir = Path("anamnesis_results")
    # Find the most recent battery results
    files = sorted(results_dir.glob("anamnesis_battery_*.json"))
    if not files:
        print("No battery results found. Run anamnesis_test_battery.py first.")
        sys.exit(1)
    latest = str(files[-1])
    print(f"Measuring: {latest}")
    run_eigentrace_measurement(latest)
