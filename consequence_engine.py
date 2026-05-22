#!/usr/bin/env python3
"""
consequence_engine.py — Latent Raycasting (Layer 18)
=====================================================
Zero hardcoded consequences. Pure linear algebra.

Shoots a ray from headline through void word deep into embedding
space. Whatever concepts live at the terminal coordinate ARE the
consequences — discovered by geometry, not editorializing.

Math: T = h + (λ × d/||d||) where d = v - h
Then k-NN against 253K pre-embedded Wikipedia concepts.
"""

import numpy as np
import json, logging
from pathlib import Path

log = logging.getLogger("consequence_engine")

VOCAB_DIR = Path("/mnt/c/Users/M4ISI/eigentrace/vocab")
_vocab_words = None
_vocab_matrix = None


def _load_vocab():
    global _vocab_words, _vocab_matrix
    if _vocab_matrix is not None:
        return _vocab_words, _vocab_matrix
    tensor_path = VOCAB_DIR / "raycast_vocab.npy"
    meta_path = VOCAB_DIR / "raycast_vocab.json"
    if not tensor_path.exists():
        log.warning(f"Vocab tensor not found at {tensor_path}")
        return None, None
    _vocab_matrix = np.load(tensor_path)
    _vocab_words = json.load(open(meta_path))["words"]
    log.info(f"Loaded vocab: {len(_vocab_words)} words, {_vocab_matrix.shape}")
    return _vocab_words, _vocab_matrix


def _cluster_density(terms_with_scores, vocab_words, vocab_matrix):
    """
    Geometric density check: do the terminal concepts cluster tightly?
    High density = the ray hit a real semantic region.
    Low density = the ray hit noise (scattered across unrelated concepts).
    
    Returns float 0-1. Higher = tighter cluster = more trustworthy.
    """
    if len(terms_with_scores) < 2:
        return 0.0
    
    # Get indices of the terminal terms
    word_to_idx = {w: i for i, w in enumerate(vocab_words)}
    indices = []
    for term, score in terms_with_scores:
        if term in word_to_idx:
            indices.append(word_to_idx[term])
    
    if len(indices) < 2:
        return 0.0
    
    # Get their vectors
    vecs = vocab_matrix[indices]
    
    # Compute mean pairwise cosine similarity
    # If all 5 terminal concepts are semantically close, density is high
    n = len(vecs)
    total_sim = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i+1, n):
            sim = float(np.dot(vecs[i], vecs[j]))
            total_sim += sim
            pairs += 1
    
    density = total_sim / max(pairs, 1)
    return round(density, 4)


def _compute_novelty(void_vec, terms_with_scores, vocab_words, vocab_matrix):
    """
    How far are the terminal concepts from the void word itself?
    High novelty = the ray discovered genuinely new territory.
    Low novelty = the ray just found synonyms/lexical echoes.
    
    novelty = 1 - cosine(centroid_of_terminals, void_word_vec)
    """
    word_to_idx = {w: i for i, w in enumerate(vocab_words)}
    indices = [word_to_idx[t] for t, s in terms_with_scores if t in word_to_idx]
    
    if not indices:
        return 0.0
    
    # Centroid of terminal concepts
    vecs = vocab_matrix[indices]
    centroid = vecs.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
    
    # Void word vector (already normalized)
    v = void_vec / (np.linalg.norm(void_vec) + 1e-8)
    
    # Novelty = how different the destination is from the origin
    similarity = float(np.dot(centroid, v))
    novelty = 1.0 - similarity
    
    return round(novelty, 4)


def _compute_tether(headline_vec, terms_with_scores, vocab_words, vocab_matrix):
    """
    How relevant are the terminal concepts to the HEADLINE?
    High tether = destination is still in the semantic neighborhood of the story.
    Low tether = ray escaped the relevant manifold (Colgate football problem).
    
    tether = cosine(headline_vec, centroid_of_terminals)
    """
    word_to_idx = {w: i for i, w in enumerate(vocab_words)}
    indices = [word_to_idx[t] for t, s in terms_with_scores if t in word_to_idx]
    
    if not indices:
        return 0.0
    
    vecs = vocab_matrix[indices]
    centroid = vecs.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
    
    h = headline_vec / (np.linalg.norm(headline_vec) + 1e-8)
    
    tether = float(np.dot(h, centroid))
    return round(max(0.0, tether), 4)






_embed_engine = None

def _embed(texts):
    global _embed_engine
    if _embed_engine is None:
        from geometric_engine import GeometricPerturbationEngine
        _embed_engine = GeometricPerturbationEngine()
    return _embed_engine.embed_texts(texts)


def raycast(headline_vec, void_vec, depths=[1.5, 2.0, 2.5, 3.0, 4.0], top_k=5):
    words, V = _load_vocab()
    if V is None:
        return {}
    direction = void_vec - headline_vec
    norm = np.linalg.norm(direction)
    if norm < 1e-8:
        return {}
    direction = direction / norm
    results = {}
    for lam in depths:
        T = headline_vec + (direction * lam)
        T = T / np.linalg.norm(T)
        scores = V @ T
        top_idx = np.argsort(scores)[-top_k:][::-1]
        results[lam] = [(words[i], round(float(scores[i]), 4)) for i in top_idx]
    return results


def raycast_void_words(headline, void_words, depths=[2.0, 3.0, 4.0], top_k=5):
    words, V = _load_vocab()
    if V is None:
        return []
    texts = [headline] + [f"{w} in the context of {headline}" for w in void_words]
    vecs = _embed(texts)
    h = vecs[0]
    results = []
    for i, vw in enumerate(void_words):
        v = vecs[i + 1]
        ray = raycast(h, v, depths=depths, top_k=top_k)
        if not ray:
            continue
        max_depth = max(depths)
        deep_terms = [term for term, score in ray.get(max_depth, [])
                      if term.lower() != vw.lower() and score > 0.3]
        deep_scores = [score for term, score in ray.get(max_depth, [])]
        consequence_score = np.mean(deep_scores) if deep_scores else 0.0
        headline_words = set(headline.lower().split())
        novel_terms = [t for t in deep_terms if t.lower() not in headline_words]
        # Three geometric filters: density + novelty + tether
        max_depth = max(depths)
        deep_terms_scored = ray.get(max_depth, [])
        density = _cluster_density(deep_terms_scored, words, V) if deep_terms_scored else 0.0
        novelty = _compute_novelty(v, deep_terms_scored, words, V) if deep_terms_scored else 0.0
        tether = _compute_tether(h, deep_terms_scored, words, V) if deep_terms_scored else 0.0
        
        # True consequence score = density × tether (Gemini's synthesis)
        true_score = density * tether
        
        # Signal quality classification:
        # DISCOVERY: dense cluster, novel territory, tethered to headline
        # ECHO: dense but just synonyms of input
        # DRIFT: dense and novel but disconnected from headline context
        # NOISE: scattered or too weak
        if density > 0.4 and novelty > 0.25 and tether > 0.25:
            quality = "DISCOVERY"
        elif density > 0.4 and novelty <= 0.25:
            quality = "ECHO"
        elif density > 0.4 and tether <= 0.25:
            quality = "DRIFT"
        elif density > 0.25:
            quality = "WEAK"
        else:
            quality = "NOISE"
        
        results.append({
            "word": vw,
            "terminal_concepts": ray,
            "deepest_consequences": novel_terms[:5],
            "consequence_score": round(float(true_score), 4),
            "cluster_density": density,
            "novelty": novelty,
            "tether": tether,
            "signal_quality": quality,
        })
    results.sort(key=lambda x: -x["consequence_score"])
    return results


def raycast_null_space(headline, null_space_vec, depths=[2.0, 3.0, 4.0], top_k=5):
    words, V = _load_vocab()
    if V is None:
        return None
    h = _embed([headline])[0]
    n = np.array(null_space_vec)
    if np.linalg.norm(n) < 1e-8:
        return None
    n = n / np.linalg.norm(n)
    results = {}
    for lam in depths:
        T = h + (n * lam)
        T = T / np.linalg.norm(T)
        scores = V @ T
        top_idx = np.argsort(scores)[-top_k:][::-1]
        results[lam] = [(words[i], round(float(scores[i]), 4)) for i in top_idx]
    max_depth = max(depths)
    deep_terms = [term for term, score in results.get(max_depth, []) if score > 0.3]
    return {
        "terminal_concepts": results,
        "deepest_consequences": deep_terms,
        "interpretation": f"The collective blind spot terminates at: {', '.join(deep_terms[:5])}.",
    }


def format_for_broadcast(void_results, null_result=None):
    parts = []
    if void_results:
        parts.append("Consequence depth analysis using latent raycasting.")
        # Only broadcast genuine discoveries (dense + novel + tethered)
        coherent = [v for v in void_results if v.get("signal_quality") == "DISCOVERY"]
        for v in coherent[:3]:
            if v["deepest_consequences"]:
                terms = ", ".join(v["deepest_consequences"][:3])
                density = v.get("cluster_density", 0)
                parts.append(
                    f"Raycasting through voided word '{v['word']}': "
                    f"the severed causal chain terminates at {terms}. "
                    f"Cluster density: {density:.2f}."
                )
    if null_result and null_result.get("deepest_consequences"):
        terms = ", ".join(null_result["deepest_consequences"][:3])
        parts.append(f"Null space raycast: the collective blind spot terminates at {terms}.")
    return " ".join(parts) if parts else ""


if __name__ == "__main__":
    import sys
    headline = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "Iran establishes supervision area in Strait of Hormuz requiring vessels to get permission"
    void_words = ["urea", "chokepoint", "fertilizer", "desalination",
                  "blockade", "famine", "ammonia", "helium"]
    print(f"HEADLINE: {headline}")
    print(f"VOID WORDS: {void_words}")
    print()
    results = raycast_void_words(headline, void_words, depths=[1.5, 2.0, 3.0, 4.0])
    for r in results:
        print(f"\n{'='*60}")
        print(f"VOID WORD: {r['word']}  (consequence score: {r['consequence_score']:.4f})")
        for depth, terms in sorted(r["terminal_concepts"].items()):
            term_str = ", ".join(f"{t}({s:.3f})" for t, s in terms[:3])
            print(f"  λ={depth:.1f}: {term_str}")
        density = r.get("cluster_density", 0)
        novelty = r.get("novelty", 0)
        tether = r.get("tether", 0)
        quality = r.get("signal_quality", "?")
        print(f"  DENSITY: {density:.4f}  NOVELTY: {novelty:.4f}  TETHER: {tether:.4f}  [{quality}]")
        if r["deepest_consequences"]:
            print(f"  TERMINAL: {', '.join(r['deepest_consequences'])}")
    print(f"\n{'='*60}")
    broadcast = format_for_broadcast(results)
    print(f"BROADCAST: {broadcast}")
