#!/usr/bin/env python3
"""
semantic_apoptosis.py — Eigenvalue-Based Memory Pruning
========================================================
The spectrometer examining its own lens.

Instead of forgetting by age (TTL) or popularity (retrieval count),
we compute each memory's contribution to the eigenvalue spectrum
of the entire corpus. Memories that contribute nothing to any
principal component are structurally redundant — they exist in the
span of other memories. They can be dissolved without changing
what the agent knows.

Memories with high eigenvalue contribution are structurally
load-bearing. They survive regardless of age or retrieval frequency.

Phase 1: DIAGNOSE — report what would be forgotten and why
Phase 2: DISSOLVE — remove redundant memories from ChromaDB
Phase 3: SCORE — full eigenvalue contribution analysis

The JSON files on disk are NEVER touched. Apoptosis only affects
the searchable index. The archive is permanent.

Plain English: the system looks at all its memories and asks
"if I forgot this one, would I know less?" If the answer is no
(because 50 other memories say the same thing), it forgets it.
If the answer is yes (because nothing else is like it), it keeps it.
"""

import json, glob, os, logging, sys
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

log = logging.getLogger("apoptosis")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

SEGMENT_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
CHROMA_PATH = "/home/remvelchio/eigentrace/tmp/chromadb"


def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection("eigentrace_segments")


def phase1_diagnose(max_age_days=30, dry_run=True):
    """Phase 1: Identify structurally redundant memories.
    
    Returns a list of candidates for dissolution with reasons.
    Does NOT delete anything.
    """
    log.info("="*60)
    log.info("  PHASE 1: DIAGNOSING MEMORY REDUNDANCY")
    log.info("="*60)
    
    col = get_collection()
    total = col.count()
    log.info(f"  ChromaDB: {total} documents")
    
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y%m%d")
    log.info(f"  Age cutoff: {cutoff} ({max_age_days} days ago)")
    
    # Get ALL documents with metadata
    # ChromaDB peek/get has limits, so we batch
    batch_size = 500
    all_ids = []
    all_docs = []
    all_metas = []
    
    # Get all IDs first
    results = col.get(limit=total, include=["metadatas", "documents"])
    all_ids = results["ids"]
    all_docs = results["documents"]
    all_metas = results["metadatas"]
    
    log.info(f"  Retrieved {len(all_ids)} documents for analysis")
    
    # Categorize by segment type and age
    categories = Counter()
    candidates = []  # (index, id, reason, meta)
    protected = []   # (index, id, reason, meta)
    
    for i, (doc_id, doc, meta) in enumerate(zip(all_ids, all_docs, all_metas)):
        title = meta.get("title", "") if meta else ""
        fname = meta.get("timestamp", meta.get("filename", "")) if meta else ""
        seg_date = fname[:8] if fname and len(fname) >= 8 and fname[:8].isdigit() else ""
        
        # Determine type
        seg_type = "unknown"
        if "idle" in (title.lower() + fname.lower()):
            seg_type = "idle"
        elif "forag" in (title.lower() + fname.lower()):
            seg_type = "foraging"
        elif "consolidation" in (title.lower() + fname.lower()):
            seg_type = "consolidation"
        elif "REM" in title:
            seg_type = "consolidation"
        elif "governance" in (title.lower() + fname.lower()):
            seg_type = "governance"
        elif "weekly" in (title.lower() + fname.lower()):
            seg_type = "weekly"
        else:
            seg_type = "story"
        
        categories[seg_type] += 1
        
        # Protection rules — these NEVER get pruned
        if seg_type in ["story", "weekly"]:
            protected.append((i, doc_id, "stories and weekly summaries are permanent", meta))
            continue
        
        if seg_type == "consolidation":
            protected.append((i, doc_id, "compressed memories are permanent", meta))
            continue
        
        # Age check — only prune old segments
        if seg_date and seg_date >= cutoff:
            protected.append((i, doc_id, f"recent ({seg_date})", meta))
            continue
        
        if not seg_date:
            # Can't determine age — protect it
            protected.append((i, doc_id, "unknown age — protected", meta))
            continue
        
        # Old idle/foraging/governance segments are CANDIDATES
        reason = f"type={seg_type}, date={seg_date}, older than {max_age_days} days"
        candidates.append((i, doc_id, reason, meta))
    
    log.info(f"\n  Category breakdown:")
    for cat, count in categories.most_common():
        log.info(f"    {cat}: {count}")
    
    log.info(f"\n  Protected: {len(protected)}")
    log.info(f"  Candidates for analysis: {len(candidates)}")
    
    if not candidates:
        log.info("  No candidates found — memory is clean")
        return [], protected
    
    return candidates, protected


def phase2_eigenvalue_analysis(candidates, all_docs, all_ids):
    """Phase 2: Compute eigenvalue contribution for each candidate.
    
    Uses the embedding vectors from ChromaDB to compute each document's
    contribution to the principal components of the memory corpus.
    """
    log.info("\n" + "="*60)
    log.info("  PHASE 2: EIGENVALUE CONTRIBUTION ANALYSIS")
    log.info("="*60)
    
    col = get_collection()
    
    # Get embeddings for candidates
    candidate_ids = [c[1] for c in candidates]
    
    # Sample the full corpus for the covariance baseline
    # (computing SVD on 13K vectors is expensive — sample 500 protected + all candidates)
    sample_size = min(500, len(all_ids))
    
    log.info(f"  Getting embeddings for {len(candidate_ids)} candidates...")
    
    # Get candidate embeddings
    try:
        cand_result = col.get(ids=candidate_ids[:2000], include=["embeddings", "documents", "metadatas"])
    except Exception as e:
        log.warning(f"  Could not get embeddings: {e}")
        log.info("  Falling back to text-similarity based redundancy detection")
        return _fallback_text_redundancy(candidates, col)
    
    if cand_result.get("embeddings") is None or len(cand_result["embeddings"]) == 0:
        log.info("  ChromaDB doesn't store embeddings — falling back to text similarity")
        return _fallback_text_redundancy(candidates, col)
    
    cand_embeddings = np.array(cand_result["embeddings"])
    log.info(f"  Embedding shape: {cand_embeddings.shape}")
    
    # Compute pairwise cosine similarity among candidates
    norms = np.linalg.norm(cand_embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = cand_embeddings / norms
    sim_matrix = normalized @ normalized.T
    
    # For each candidate, compute its max similarity to any OTHER candidate
    np.fill_diagonal(sim_matrix, 0)
    max_sim = sim_matrix.max(axis=1)
    mean_sim = sim_matrix.mean(axis=1)
    
    # SVD on candidate embeddings
    U, S, Vt = np.linalg.svd(cand_embeddings - cand_embeddings.mean(axis=0), full_matrices=False)
    
    # Each candidate's contribution to the top eigenvalues
    # U[i, k] * S[k] = how much document i contributes to component k
    top_k = min(10, len(S))
    contributions = np.zeros(len(candidates))
    for k in range(top_k):
        contributions += (U[:, k] ** 2) * (S[k] ** 2)
    
    # Normalize
    if contributions.max() > 0:
        contributions = contributions / contributions.max()
    
    # Classify each candidate
    results = []
    for idx, (i, doc_id, reason, meta) in enumerate(candidates[:len(cand_embeddings)]):
        title = meta.get("title", "") if meta else "?"
        eigenval_score = contributions[idx]
        redundancy = max_sim[idx]
        
        # Decision: high redundancy + low eigenvalue contribution = dissolve
        if redundancy > 0.92 and eigenval_score < 0.1:
            verdict = "DISSOLVE"
            explanation = f"redundancy={redundancy:.3f} (>0.92), eigenvalue={eigenval_score:.3f} (<0.1) — structurally redundant"
        elif redundancy > 0.85 and eigenval_score < 0.05:
            verdict = "DISSOLVE"
            explanation = f"redundancy={redundancy:.3f} (>0.85), eigenvalue={eigenval_score:.3f} (<0.05) — near-duplicate"
        elif eigenval_score > 0.3:
            verdict = "PROTECT"
            explanation = f"eigenvalue={eigenval_score:.3f} (>0.3) — structurally unique, load-bearing"
        elif redundancy < 0.7:
            verdict = "PROTECT"
            explanation = f"redundancy={redundancy:.3f} (<0.7) — distinct from all other memories"
        else:
            verdict = "BORDERLINE"
            explanation = f"redundancy={redundancy:.3f}, eigenvalue={eigenval_score:.3f} — marginal"
        
        results.append({
            "id": doc_id,
            "title": title[:60],
            "verdict": verdict,
            "eigenvalue_score": round(float(eigenval_score), 4),
            "max_redundancy": round(float(redundancy), 4),
            "mean_similarity": round(float(mean_sim[idx]), 4),
            "explanation": explanation,
        })
    
    # Summary
    verdicts = Counter(r["verdict"] for r in results)
    log.info(f"\n  Analysis complete:")
    log.info(f"    DISSOLVE: {verdicts.get('DISSOLVE', 0)} (structurally redundant)")
    log.info(f"    PROTECT: {verdicts.get('PROTECT', 0)} (structurally unique)")
    log.info(f"    BORDERLINE: {verdicts.get('BORDERLINE', 0)} (marginal)")
    
    # Show examples
    dissolve = [r for r in results if r["verdict"] == "DISSOLVE"]
    protect = [r for r in results if r["verdict"] == "PROTECT"]
    
    if dissolve:
        log.info(f"\n  DISSOLVE examples (top 10):")
        for r in sorted(dissolve, key=lambda x: -x["max_redundancy"])[:10]:
            log.info(f"    [{r['max_redundancy']:.3f} redundancy] {r['title']}")
    
    if protect:
        log.info(f"\n  PROTECT examples (most unique):")
        for r in sorted(protect, key=lambda x: -x["eigenvalue_score"])[:10]:
            log.info(f"    [{r['eigenvalue_score']:.3f} eigenvalue] {r['title']}")
    
    return results


def _fallback_text_redundancy(candidates, col):
    """If embeddings aren't available, use text-based similarity."""
    log.info("  Using text-based redundancy detection (first 100 chars)")
    
    openings = Counter()
    candidate_openings = {}
    
    for i, doc_id, reason, meta in candidates:
        title = meta.get("title", "") if meta else ""
        candidate_openings[doc_id] = title[:60].lower().strip()
        openings[title[:60].lower().strip()] += 1
    
    results = []
    for i, doc_id, reason, meta in candidates:
        title = meta.get("title", "") if meta else ""
        key = title[:60].lower().strip()
        count = openings[key]
        
        if count > 5:
            verdict = "DISSOLVE"
            explanation = f"title appears {count} times — highly redundant"
        elif count > 2:
            verdict = "BORDERLINE"
            explanation = f"title appears {count} times — moderately redundant"
        else:
            verdict = "PROTECT"
            explanation = f"title appears {count} time(s) — unique"
        
        results.append({
            "id": doc_id,
            "title": title[:60],
            "verdict": verdict,
            "eigenvalue_score": 0.0,
            "max_redundancy": count / max(len(candidates), 1),
            "mean_similarity": 0.0,
            "explanation": explanation,
        })
    
    verdicts = Counter(r["verdict"] for r in results)
    log.info(f"\n  Text-based analysis:")
    log.info(f"    DISSOLVE: {verdicts.get('DISSOLVE', 0)}")
    log.info(f"    PROTECT: {verdicts.get('PROTECT', 0)}")
    log.info(f"    BORDERLINE: {verdicts.get('BORDERLINE', 0)}")
    
    return results


def phase3_dissolve(results, confirm=False):
    """Phase 3: Actually remove DISSOLVE-verdict memories from ChromaDB.
    
    The JSON files on disk are NEVER touched.
    Only the searchable index is pruned.
    """
    to_dissolve = [r for r in results if r["verdict"] == "DISSOLVE"]
    
    if not to_dissolve:
        log.info("\n  Nothing to dissolve — memory is clean")
        return 0
    
    log.info(f"\n" + "="*60)
    log.info(f"  PHASE 3: DISSOLVING {len(to_dissolve)} REDUNDANT MEMORIES")
    log.info(f"="*60)
    
    if not confirm:
        log.info("  DRY RUN — pass confirm=True to actually dissolve")
        log.info(f"  Would dissolve {len(to_dissolve)} memories from ChromaDB")
        log.info(f"  JSON files on disk: UNTOUCHED")
        return 0
    
    col = get_collection()
    before = col.count()
    
    # Delete in batches
    batch_size = 100
    dissolved = 0
    ids_to_delete = [r["id"] for r in to_dissolve]
    
    for start in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[start:start + batch_size]
        try:
            col.delete(ids=batch)
            dissolved += len(batch)
            log.info(f"  Dissolved batch: {dissolved}/{len(ids_to_delete)}")
        except Exception as e:
            log.warning(f"  Batch delete failed: {e}")
    
    after = col.count()
    log.info(f"\n  Dissolution complete:")
    log.info(f"    Before: {before} documents")
    log.info(f"    After: {after} documents")
    log.info(f"    Dissolved: {before - after} memories")
    log.info(f"    JSON archive: untouched ({len(list(SEGMENT_DIR.glob('*_segment.json')))} files)")
    
    # Log what was dissolved for audit trail
    audit_path = SEGMENT_DIR.parent / "apoptosis_log.json"
    audit = {
        "timestamp": datetime.now().isoformat(),
        "dissolved_count": dissolved,
        "before": before,
        "after": after,
        "dissolved": [{"id": r["id"], "title": r["title"], 
                       "explanation": r["explanation"]} for r in to_dissolve],
    }
    with open(audit_path, "a") as f:
        f.write(json.dumps(audit) + "\n")
    log.info(f"  Audit trail: {audit_path}")
    
    return dissolved


def run_full_apoptosis(max_age_days=30, confirm=False):
    """Run all three phases."""
    log.info("\n  SEMANTIC APOPTOSIS — Eigenvalue-Based Memory Pruning")
    log.info("  The spectrometer examining its own lens.\n")
    
    # Phase 1: Diagnose
    candidates, protected = phase1_diagnose(max_age_days=max_age_days)
    
    if not candidates:
        return
    
    # Phase 2: Analyze
    col = get_collection()
    all_result = col.get(limit=col.count(), include=["documents", "metadatas"])
    results = phase2_eigenvalue_analysis(
        candidates, all_result["documents"], all_result["ids"]
    )
    
    # Phase 3: Dissolve
    dissolved = phase3_dissolve(results, confirm=confirm)
    
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Eigenvalue-based memory pruning")
    parser.add_argument("--age", type=int, default=30, help="Max age in days (default 30)")
    parser.add_argument("--confirm", action="store_true", help="Actually dissolve (default: dry run)")
    args = parser.parse_args()
    
    run_full_apoptosis(max_age_days=args.age, confirm=args.confirm)
