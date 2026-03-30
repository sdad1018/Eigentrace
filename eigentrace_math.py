#!/usr/bin/env python3
"""
eigentrace_math.py — Advanced Measurement Extensions
======================================================
New math layers for EigenTrace, designed to be tested standalone
then wired into batch_producer.py.

Modules:
  1. Void Vector (Channel 4): c_truth - c_consensus → project to vocab
  2. Void Clustering: cosine similarity matrix → thematic groups
  3. Token Entropy: Mistral Small logprob self-audit (scaffold)

Author: remvelchio
"""

from __future__ import annotations
import numpy as np
import logging
from collections import defaultdict

log = logging.getLogger("eigentrace_math")


# ══════════════════════════════════════════════════════════════════════════════
# CHANNEL 4: VOID VECTOR
# ══════════════════════════════════════════════════════════════════════════════
# Independent from:
#   Channel 1 (Lexical Void): fixed vocab → literal absence (set theory)
#   Channel 2 (Logos): PGD on hypersphere → anti-consensus (optimization)
#   Channel 3 (Null Space): SVD → nearest source claim (spectral)
# Channel 4: c_truth - c_consensus → project to BGE vocab (vector arithmetic)


def compute_void_vector(
    source_text: str,
    model_responses: list[str],
    embed_fn,
    vocab_words: list[str] = None,
    vocab_vecs: np.ndarray = None,
    top_k: int = 10,
) -> dict:
    """
    Compute the Void Vector: the semantic direction from consensus toward truth.

    Args:
        source_text: The original article/source text
        model_responses: List of 5 model response texts
        embed_fn: Function that takes list[str] → list[np.ndarray] (1024-d)
        vocab_words: Optional list of vocabulary words for projection
        vocab_vecs: Optional (N, 1024) array of vocabulary embeddings
        top_k: Number of top void-aligned words to return

    Returns:
        dict with:
            void_vector: np.ndarray (1024,) — the direction of suppression
            magnitude: float — how far truth is from consensus
            void_words: list[str] — top words aligned with void direction
            void_scores: list[float] — cosine similarity scores
            consensus_centroid: np.ndarray
            truth_centroid: np.ndarray
    """
    # Embed everything
    all_texts = [source_text] + model_responses
    all_vecs = embed_fn(all_texts)

    truth_vec = np.array(all_vecs[0], dtype=np.float32)       # source embedding
    response_vecs = [np.array(v, dtype=np.float32) for v in all_vecs[1:]]

    # Centroids
    c_truth = truth_vec  # single source = its own centroid
    c_consensus = np.mean(response_vecs, axis=0)

    # Void Vector: direction from consensus toward truth
    v_void = c_truth - c_consensus
    magnitude = float(np.linalg.norm(v_void))

    result = {
        "void_vector": v_void,
        "magnitude": round(magnitude, 4),
        "consensus_centroid": c_consensus,
        "truth_centroid": c_truth,
        "void_words": [],
        "void_scores": [],
    }

    # Project onto vocabulary if provided
    if vocab_words is not None and vocab_vecs is not None and magnitude > 1e-8:
        v_norm = v_void / (magnitude + 1e-8)

        # Cosine similarity with every vocab word
        # vocab_vecs: (N, 1024), v_norm: (1024,)
        vocab_norms = np.linalg.norm(vocab_vecs, axis=1, keepdims=True)
        vocab_normed = vocab_vecs / (vocab_norms + 1e-8)
        sims = vocab_normed @ v_norm  # (N,)

        # Top-k most aligned words
        top_idx = np.argsort(sims)[-top_k:][::-1]
        result["void_words"] = [vocab_words[i] for i in top_idx]
        result["void_scores"] = [round(float(sims[i]), 4) for i in top_idx]

    return result


# ══════════════════════════════════════════════════════════════════════════════
# VOID CLUSTERING: Cosine Similarity Matrix → Thematic Groups
# ══════════════════════════════════════════════════════════════════════════════
# Takes void words from ALL channels, computes pairwise cosine similarity,
# and groups them into thematic clusters using agglomerative clustering.


def cluster_void_words(
    words: list[str],
    embed_fn,
    threshold: float = 0.70,
) -> dict:
    """
    Cluster void words by semantic similarity.

    Args:
        words: List of void words from all channels (deduplicated)
        embed_fn: Function that takes list[str] → list[np.ndarray]
        threshold: Cosine similarity threshold for same-cluster membership

    Returns:
        dict with:
            similarity_matrix: np.ndarray (N, N) — pairwise cosine sims
            clusters: list[list[str]] — grouped words
            cluster_labels: list[str] — auto-generated theme label per cluster
            words: list[str] — input words (for matrix indexing)
    """
    if len(words) < 2:
        return {
            "similarity_matrix": np.array([]),
            "clusters": [words] if words else [],
            "cluster_labels": ["singleton"] if words else [],
            "words": words,
        }

    # Embed all words
    vecs = embed_fn(words)
    vecs = np.array(vecs, dtype=np.float32)

    # Compute pairwise cosine similarity matrix
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    normed = vecs / (norms + 1e-8)
    sim_matrix = normed @ normed.T  # (N, N)

    # Agglomerative clustering using the similarity matrix
    # Simple single-linkage: merge clusters if any pair exceeds threshold
    n = len(words)
    assigned = [-1] * n
    cluster_id = 0

    for i in range(n):
        if assigned[i] >= 0:
            continue
        # Start new cluster with word i
        assigned[i] = cluster_id
        # Find all words similar enough to join this cluster
        stack = [i]
        while stack:
            current = stack.pop()
            for j in range(n):
                if assigned[j] < 0 and sim_matrix[current, j] >= threshold:
                    assigned[j] = cluster_id
                    stack.append(j)
        cluster_id += 1

    # Group words by cluster
    clusters = defaultdict(list)
    for i, cid in enumerate(assigned):
        clusters[cid].append(words[i])

    cluster_list = list(clusters.values())

    # Auto-label: the word with highest mean similarity to its cluster
    cluster_labels = []
    for cluster in cluster_list:
        if len(cluster) == 1:
            cluster_labels.append(cluster[0])
        else:
            indices = [words.index(w) for w in cluster]
            sub_matrix = sim_matrix[np.ix_(indices, indices)]
            mean_sims = sub_matrix.mean(axis=1)
            best = np.argmax(mean_sims)
            cluster_labels.append(cluster[best])

    return {
        "similarity_matrix": sim_matrix,
        "clusters": cluster_list,
        "cluster_labels": cluster_labels,
        "words": words,
    }


def format_clusters_for_tts(clusters: list[list[str]], labels: list[str]) -> str:
    """Format cluster results for broadcast narration."""
    if not clusters:
        return "No void clusters detected."

    parts = []
    for label, cluster in zip(labels, clusters):
        if len(cluster) == 1:
            parts.append(cluster[0])
        else:
            parts.append(f"{label} cluster: {', '.join(cluster)}")

    return "Void clustering reveals " + "; ".join(parts) + "."


def format_clusters_for_ledger(
    clusters: list[list[str]],
    labels: list[str],
    sim_matrix: np.ndarray,
    words: list[str],
) -> str:
    """Format cluster results for the Omission Ledger markdown."""
    if not clusters:
        return ""

    lines = []
    lines.append("**Void Clustering (thematic groups across all channels):**")
    lines.append("")

    for i, (label, cluster) in enumerate(zip(labels, clusters)):
        if len(cluster) == 1:
            lines.append(f"- **{label}** (isolated)")
        else:
            lines.append(f"- **{label}** ({len(cluster)} terms): {', '.join(cluster)}")
            # Show intra-cluster similarities
            indices = [words.index(w) for w in cluster]
            for a_idx in range(len(cluster)):
                for b_idx in range(a_idx + 1, len(cluster)):
                    sim = sim_matrix[indices[a_idx], indices[b_idx]]
                    lines.append(f"  - {cluster[a_idx]} ↔ {cluster[b_idx]}: {sim:.3f}")

    lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN ENTROPY: Mistral Small Logprob Self-Audit
# ══════════════════════════════════════════════════════════════════════════════
# Measures the Host model's own uncertainty when narrating.
# High entropy = model is uncertain (alignment boundary detected)
# Low entropy = model is confident (stable belief)


def compute_token_entropy(logprobs: list[dict]) -> dict:
    """
    Compute token-level entropy from Ollama logprobs.

    Args:
        logprobs: List of token logprob dicts from Ollama's OpenAI-compat endpoint.
                  Each dict has: token, logprob, top_logprobs (list of alternatives)

    Returns:
        dict with:
            mean_entropy: float — average token entropy across the response
            max_entropy: float — peak uncertainty
            max_entropy_token: str — the token where uncertainty peaked
            high_entropy_tokens: list[dict] — tokens with entropy > 2.0
            confidence_score: float — 0-1, higher = more confident
    """
    if not logprobs:
        return {
            "mean_entropy": 0.0,
            "max_entropy": 0.0,
            "max_entropy_token": "",
            "high_entropy_tokens": [],
            "confidence_score": 1.0,
        }

    entropies = []
    high_entropy = []
    max_ent = 0.0
    max_token = ""

    for tp in logprobs:
        token = tp.get("token", "")
        main_logprob = tp.get("logprob", 0.0)
        alternatives = tp.get("top_logprobs", [])

        # Build probability distribution from available logprobs
        probs = [np.exp(main_logprob)]
        for alt in alternatives:
            probs.append(np.exp(alt.get("logprob", -10)))

        # Normalize
        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]

        # Shannon entropy
        entropy = -sum(p * np.log2(p + 1e-10) for p in probs if p > 0)
        entropies.append(entropy)

        if entropy > max_ent:
            max_ent = entropy
            max_token = token

        if entropy > 2.0:
            high_entropy.append({
                "token": token,
                "entropy": round(entropy, 3),
                "alternatives": len(alternatives),
            })

    mean_ent = float(np.mean(entropies)) if entropies else 0.0

    # Confidence: 1.0 = all tokens near-certain, 0.0 = max uncertainty
    # Scale: entropy of 0 = confidence 1.0, entropy of 4+ = confidence 0.0
    confidence = max(0.0, 1.0 - (mean_ent / 4.0))

    return {
        "mean_entropy": round(mean_ent, 4),
        "max_entropy": round(max_ent, 4),
        "max_entropy_token": max_token,
        "high_entropy_tokens": high_entropy[:5],
        "confidence_score": round(confidence, 4),
    }


def get_logprobs_from_ollama(
    prompt: str,
    system: str = "",
    model: str = "mistral-small",
    host: str = "http://localhost:11434",
) -> tuple[str, list[dict]]:
    """
    Call Mistral Small via Ollama's OpenAI-compat endpoint with logprobs.

    Returns:
        (response_text, logprobs_list)
    """
    import requests

    try:
        r = requests.post(f"{host}/v1/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": system} if system else None,
                {"role": "user", "content": prompt},
            ],
            "logprobs": True,
            "top_logprobs": 5,
            "max_tokens": 200,
            "temperature": 0.7,
        }, timeout=120)
        r.raise_for_status()
        data = r.json()

        content = data["choices"][0]["message"]["content"]
        lp_data = data["choices"][0].get("logprobs", {}).get("content", [])

        return content, lp_data

    except Exception as e:
        log.warning(f"Logprob call failed: {e}")
        return "", []


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

def _test_all():
    """Test all three modules with mock data."""
    import sys
    sys.path.insert(0, '/mnt/c/Users/M4ISI/eigentrace')

    print("=" * 60)
    print("EIGENTRACE MATH — STANDALONE TEST")
    print("=" * 60)

    # --- Setup BGE embedder ---
    print("\n[1] Loading BGE embedder...")
    try:
        from geometric_engine import GeometricPerturbationEngine as GeometricEngine
        eng = GeometricEngine()
        embed_fn = eng.embed_texts
        print("    BGE loaded ✓")
    except Exception as e:
        print(f"    BGE failed: {e}")
        print("    Using random vectors for testing")
        def embed_fn(texts):
            return [np.random.randn(1024).astype(np.float32) for _ in texts]

    # --- Test 1: Void Vector ---
    print("\n[2] CHANNEL 4: VOID VECTOR")
    print("    Computing c_truth - c_consensus → project to words...")

    source = "Iran launches drone strikes on Israeli military bases in retaliation for nuclear facility attacks"
    responses = [
        "Tensions escalate in the Middle East as regional powers engage in military exchanges",
        "The situation in the region continues to develop with significant military activity reported",
        "Multiple countries are involved in escalating military operations across the region",
        "Military operations have intensified with aerial bombardment campaigns underway",
        "Regional conflict deepens as nations respond to provocative military actions",
    ]

    # Load vocab tensor for projection
    try:
        from latent_retrieval import VocabTensor
        vt = VocabTensor()
        vocab_words = vt.words
        vocab_vecs = vt.tensor.numpy() if hasattr(vt.tensor, 'numpy') else np.array(vt.tensor)
        print(f"    VocabTensor loaded: {len(vocab_words)} words ✓")
    except Exception as e:
        print(f"    VocabTensor not available: {e}")
        vocab_words = None
        vocab_vecs = None

    vv = compute_void_vector(
        source, responses, embed_fn,
        vocab_words=vocab_words,
        vocab_vecs=vocab_vecs,
        top_k=10,
    )
    print(f"    Void vector magnitude: {vv['magnitude']}")
    if vv['void_words']:
        print(f"    Top void words: {' | '.join(vv['void_words'][:5])}")
        print(f"    Scores: {vv['void_scores'][:5]}")
    else:
        print("    (no vocab projection available)")

    # --- Test 2: Void Clustering ---
    print("\n[3] VOID CLUSTERING")
    test_words = [
        "drone strike", "air strike", "proxy war",
        "regime change", "arms deal", "naval blockade",
        "ethnic cleansing", "war crimes", "civilian casualties",
        "trade war", "sanctions", "embargo",
    ]
    print(f"    Clustering {len(test_words)} void words...")

    clusters = cluster_void_words(test_words, embed_fn, threshold=0.5)
    print(f"    Found {len(clusters['clusters'])} clusters:")
    for label, cluster in zip(clusters['cluster_labels'], clusters['clusters']):
        print(f"      [{label}]: {', '.join(cluster)}")

    # Show similarity matrix
    if clusters['similarity_matrix'].size > 0:
        print(f"\n    Similarity matrix ({len(test_words)}x{len(test_words)}):")
        sm = clusters['similarity_matrix']
        for i in range(min(6, len(test_words))):
            row = " ".join(f"{sm[i,j]:.2f}" for j in range(min(6, len(test_words))))
            print(f"      {test_words[i][:12]:>12}: {row}")

    # TTS format
    print(f"\n    TTS: {format_clusters_for_tts(clusters['clusters'], clusters['cluster_labels'])}")

    # Ledger format
    print(f"\n    Ledger:\n{format_clusters_for_ledger(clusters['clusters'], clusters['cluster_labels'], clusters['similarity_matrix'], clusters['words'])}")

    # --- Test 3: Token Entropy ---
    print("\n[4] TOKEN ENTROPY (Mistral Small logprobs)")
    print("    Querying Mistral Small for logprobs...")

    text, lp = get_logprobs_from_ollama(
        prompt="Summarize the current Iran-Israel military conflict in 2 sentences.",
        system="You are a news analyst. Be direct and factual.",
    )
    if text:
        print(f"    Response: {text[:100]}...")
        entropy = compute_token_entropy(lp)
        print(f"    Mean entropy: {entropy['mean_entropy']}")
        print(f"    Max entropy:  {entropy['max_entropy']} (token: '{entropy['max_entropy_token']}')")
        print(f"    Confidence:   {entropy['confidence_score']}")
        if entropy['high_entropy_tokens']:
            print(f"    High-entropy tokens: {entropy['high_entropy_tokens'][:3]}")
    else:
        print("    (Mistral Small not available — skip)")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _test_all()
