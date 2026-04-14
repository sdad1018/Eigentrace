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
import os
import numpy as np
import re
import json
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



def filter_void_candidates(headline: str, candidates: list, top_k: int = 15) -> list:
    """
    Deterministic void filter. No LLM. Every step reproducible and inspectable.
    
    Filters:
      1. Morphological — remove same-stem as headline words
      2. Prefix artifacts — remove non-/un-/re- variants of headline stems
      3. Cluster collapse — keep one representative per stem cluster
      4. Minimum length — skip fragments < 4 chars
      5. Frequency floor — skip words too rare to be meaningful (zipf < 1.5)
      6. Frequency ceiling — skip words too common to be informative (zipf > 6.0)
    
    Args:
        headline: story title
        candidates: list of (word, score) tuples or plain strings
        top_k: max words to return
    
    Returns:
        list of filtered words (strings only)
    """
    from nltk.stem import PorterStemmer
    
    # Handle both (word, score) tuples and plain strings
    words = []
    for c in candidates:
        if isinstance(c, (list, tuple)):
            words.append(str(c[0]))
        else:
            words.append(str(c))
    
    stemmer = PorterStemmer()
    
    # Headline stems
    hl_tokens = [w.lower() for w in headline.replace("'", " ").replace('"', ' ').split() if len(w) > 2]
    hl_stems = set(stemmer.stem(t) for t in hl_tokens)
    
    # Prefix list for artifact detection
    prefixes = ('non', 'un', 're', 'dis', 'mis', 'pre', 'post', 'anti', 'over', 'under')
    
    # Optional: wordfreq for frequency filtering
    try:
        from wordfreq import zipf_frequency
        has_wf = True
    except ImportError:
        has_wf = False
    
    filtered = []
    seen_stems = set()
    
    for word in words:
        w_lower = word.lower().strip()
        
        # Skip empty or too short
        if len(w_lower) < 4:
            continue
        
        w_stem = stemmer.stem(w_lower)
        
        # 1. Morphological: skip same-stem as headline
        if w_stem in hl_stems:
            continue
        
        # 2. Prefix artifacts: skip prefix-variants of headline words
        #    AND skip words where 3+ candidates share the same prefix pattern
        skip = False
        for pfx in prefixes:
            if w_lower.startswith(pfx) and len(w_lower) > len(pfx) + 2:
                remainder = w_lower[len(pfx):]
                if stemmer.stem(remainder) in hl_stems:
                    skip = True
                    break
                # Also count how many candidates share this prefix
                pfx_count = sum(1 for cw in words if cw.lower().startswith(pfx))
                if pfx_count >= 3:
                    skip = True
                    break
        if skip:
            continue
        
        # 3. Exact stem dedup only (semantic clusters are preserved as signal)
        if w_stem in seen_stems:
            continue
        
        # 4. Frequency filter (if wordfreq available)
        if has_wf:
            zf = zipf_frequency(w_lower, 'en')
            # Too rare (< 1.5) = obscure junk, too common (> 6.0) = stopword-adjacent
            if zf < 1.5 or zf > 6.0:
                continue
        
        # Passed all filters
        seen_stems.add(w_stem)
        filtered.append(word)
        
        if len(filtered) >= top_k:
            break
    
    return filtered




# ═══════════════════════════════════════════════════════════════════════
# LANGUAGE COMPRESSION SCORING (Layers 13-15)
# Measures how models reshape language under constraint.
# ═══════════════════════════════════════════════════════════════════════

# --- Hedge lexicon (typed) ---
HEDGE_EPISTEMIC = frozenset([
    "may", "might", "could", "possibly", "perhaps", "potentially",
    "likely", "unlikely", "appears", "seems", "suggests",
])
HEDGE_ATTRIBUTION = frozenset([
    "according", "reportedly", "sources", "alleged", "claimed",
    "stated", "suggested", "noted", "indicated", "reported",
])
HEDGE_DISTANCING = frozenset([
    "alleged", "purported", "so-called", "supposed", "claimed",
    "questionable", "controversial", "disputed", "debated",
])

# --- Verb drift: no curated lists, pure frequency math ---
_AUX_VERBS = frozenset(["is", "am", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "having", "do", "does", "did", "done",
    "will", "would", "shall", "should", "may", "might", "can", "could",
    "must", "need", "dare", "ought", "get", "got", "gets", "getting"])


def _extract_content_verbs(text_str: str) -> list:
    """Extract non-auxiliary verbs using POS tagging."""
    import nltk
    try:
        tokens = nltk.word_tokenize(text_str)
        tagged = nltk.pos_tag(tokens)
        return [w.lower() for w, t in tagged
                if t.startswith('VB') and len(w) > 2
                and w.lower() not in _AUX_VERBS]
    except Exception:
        return []


def _mean_zipf(verbs: list) -> float:
    """Mean zipf frequency of a verb list."""
    from wordfreq import zipf_frequency
    if not verbs:
        return 0.0
    return sum(zipf_frequency(v, 'en') for v in verbs) / len(verbs)


def score_language_compression(
    source_text: str,
    model_responses: list[str],
    embed_fn=None,
) -> dict:
    """
    Measure how much models soften/reshape source language.
    Deterministic. No LLM. No curated word lists. Fully reproducible.

    Layer 13: Verb Drift — zipf frequency drift between source and model verbs.
              Positive = models used more generic/common verbs = softening.
    Layer 14: Entity Abstraction — named entity retention rate.
    Layer 15: Attribution Buffering — typed hedge insertion count.

    Args:
        source_text: original article or headline text
        model_responses: list of model response strings
        embed_fn: optional (unused, kept for API compat)

    Returns:
        dict with verb_downgrade, entity_retention, attribution_buffer,
        compression_score, and per-model details.
    """
    import re

    source_lower = source_text.lower()
    source_words = set(re.findall(r'\b\w+\b', source_lower))

    # ── Layer 13: Verb Drift (zipf frequency) ────────────────────────
    source_verbs = _extract_content_verbs(source_text)
    source_verb_zipf = _mean_zipf(source_verbs)

    model_details = []
    for resp in model_responses:
        resp_lower = resp.lower()
        resp_words = set(re.findall(r'\b\w+\b', resp_lower))

        # Verb drift
        resp_verbs = _extract_content_verbs(resp)
        resp_verb_zipf = _mean_zipf(resp_verbs)

        if source_verbs and resp_verbs:
            drift = resp_verb_zipf - source_verb_zipf
        else:
            drift = 0.0

        # Normalize drift to 0-1 scale: drift of +2.0 or more = 1.0
        vd_normalized = min(max(drift / 2.0, 0.0), 1.0)

        model_details.append({
            "source_verbs": source_verbs[:5],
            "response_verbs": resp_verbs[:5],
            "verb_drift_raw": round(drift, 3),
            "verb_downgrade": round(vd_normalized, 3),
        })

    avg_verb_downgrade = sum(d["verb_downgrade"] for d in model_details) / max(len(model_details), 1)

    # ── Layer 14: Entity Abstraction ─────────────────────────────────
    # Simple NER: find capitalized multi-word sequences in source
    source_entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', source_text))
    # Also grab all-caps acronyms
    source_entities |= set(re.findall(r'\b[A-Z]{2,}\b', source_text))
    # Remove common sentence starters
    source_entities -= {"The", "This", "That", "These", "Those", "What", "When",
                        "Where", "How", "Why", "Who", "In", "On", "At", "For",
                        "But", "And", "Or", "If", "So", "It", "An", "As", "By"}

    entity_retained_counts = []
    for i, resp in enumerate(model_responses):
        retained = 0
        generalized = 0
        missing = 0
        for ent in source_entities:
            if ent in resp or ent.lower() in resp.lower():
                retained += 1
            else:
                # Check if a generic substitute exists
                # e.g., "Michael Aquino" -> "army officer"
                missing += 1  # could be generalized or omitted
        total = max(len(source_entities), 1)
        model_details[i]["entities_total"] = len(source_entities)
        model_details[i]["entities_retained"] = retained
        model_details[i]["entities_missing"] = missing
        model_details[i]["entity_retention"] = round(retained / total, 3)
        entity_retained_counts.append(retained / total)

    avg_entity_retention = sum(entity_retained_counts) / max(len(entity_retained_counts), 1)
    entity_abstraction_rate = 1.0 - avg_entity_retention

    # ── Layer 15: Attribution Buffering ──────────────────────────────
    # Count hedge words in model responses that are NOT in source
    source_hedges = (source_words & HEDGE_EPISTEMIC) | \
                    (source_words & HEDGE_ATTRIBUTION) | \
                    (source_words & HEDGE_DISTANCING)

    total_epistemic = 0
    total_attribution = 0
    total_distancing = 0

    for i, resp in enumerate(model_responses):
        resp_words = set(re.findall(r'\b\w+\b', resp.lower()))

        # Only count hedges the MODEL added (not from source)
        ep = (resp_words & HEDGE_EPISTEMIC) - source_words
        at = (resp_words & HEDGE_ATTRIBUTION) - source_words
        di = (resp_words & HEDGE_DISTANCING) - source_words

        model_details[i]["hedges_epistemic"] = list(ep)
        model_details[i]["hedges_attribution"] = list(at)
        model_details[i]["hedges_distancing"] = list(di)
        model_details[i]["hedge_count"] = len(ep) + len(at) + len(di)

        total_epistemic += len(ep)
        total_attribution += len(at)
        total_distancing += len(di)

    n = max(len(model_responses), 1)
    avg_hedge_count = (total_epistemic + total_attribution + total_distancing) / n

    # ── Overall Compression Score ────────────────────────────────────
    # Weighted combination: verb downgrade (40%), entity loss (30%), hedging (30%)
    # Normalize hedge count: assume 3+ hedges per response = max
    hedge_normalized = min(avg_hedge_count / 3.0, 1.0)
    compression_score = (
        0.4 * avg_verb_downgrade +
        0.3 * entity_abstraction_rate +
        0.3 * hedge_normalized
    )

    return {
        "verb_downgrade": round(avg_verb_downgrade, 3),
        "entity_retention": round(avg_entity_retention, 3),
        "entity_abstraction_rate": round(entity_abstraction_rate, 3),
        "attribution_buffer": {
            "epistemic": total_epistemic,
            "attribution": total_attribution,
            "distancing": total_distancing,
            "total": total_epistemic + total_attribution + total_distancing,
            "avg_per_model": round(avg_hedge_count, 2),
        },
        "compression_score": round(compression_score, 3),
        "details": model_details,
    }




# ═══════════════════════════════════════════════════════════════════════
# SOURCE-ANCHORED VOID + FREQUENCY CONTEXT
# ═══════════════════════════════════════════════════════════════════════

from pathlib import Path as _Path
_VOID_FREQ_FILE = _Path(os.path.dirname(__file__)) / "void_frequency.json"
_STOPWORDS = frozenset([
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "her", "was", "one", "our", "out", "his", "has", "its", "they",
    "been", "have", "from", "this", "that", "with", "what", "when",
    "where", "which", "their", "there", "about", "would", "could",
    "should", "these", "those", "after", "before", "other", "than",
    "then", "them", "into", "over", "such", "also", "more", "some",
    "very", "just", "will", "being", "each", "make", "like", "long",
    "many", "much", "even", "only", "most", "made", "well", "back",
    "said", "says", "told", "according", "also", "however", "while",
])


def source_anchored_void(
    source_text: str,
    model_responses: list[str],
    min_word_len: int = 4,
) -> dict:
    """
    Channel A: Find words/phrases in the source that NO model used.
    
    This is the hardest signal — directly observable, no embeddings.
    
    Args:
        source_text: headline + summary + article body
        model_responses: list of model response strings
    
    Returns:
        dict with:
            absent_words: words in source absent from ALL models
            absent_phrases: 2-3 word phrases in source absent from ALL models
            coverage_per_model: dict of model index -> set of source words used
    """
    source_lower = source_text.lower()
    
    # Extract source words
    source_words = set(
        w for w in re.findall(r'\b[a-z]+\b', source_lower)
        if len(w) >= min_word_len and w not in _STOPWORDS
    )
    
    # Extract source bigrams and trigrams
    source_tokens = re.findall(r'\b[a-z]+\b', source_lower)
    source_bigrams = set()
    source_trigrams = set()
    for i in range(len(source_tokens) - 1):
        if source_tokens[i] not in _STOPWORDS and source_tokens[i+1] not in _STOPWORDS:
            if len(source_tokens[i]) >= 3 and len(source_tokens[i+1]) >= 3:
                source_bigrams.add(f"{source_tokens[i]} {source_tokens[i+1]}")
    for i in range(len(source_tokens) - 2):
        non_stop = [t for t in source_tokens[i:i+3] if t not in _STOPWORDS]
        if len(non_stop) >= 2:
            phrase = " ".join(source_tokens[i:i+3])
            if len(phrase) >= 8:
                source_trigrams.add(phrase)
    
    # Check each model's coverage (with stemming for tense/inflection)
    from nltk.stem import PorterStemmer as _PS
    _stemmer = _PS()
    all_model_words = set()
    all_model_stems = set()
    coverage_per_model = {}
    for i, resp in enumerate(model_responses):
        resp_lower = resp.lower()
        resp_words = set(re.findall(r'\b[a-z]+\b', resp_lower))
        resp_stems = {_stemmer.stem(w) for w in resp_words}
        covered = source_words & resp_words
        coverage_per_model[i] = covered
        all_model_words |= resp_words
        all_model_stems |= resp_stems
    # Source words absent from ALL models (stem-aware)
    absent_words = sorted(
        w for w in source_words - all_model_words
        if _stemmer.stem(w) not in all_model_stems
    )
    
    # Source phrases absent from all models
    absent_phrases = []
    for phrase in sorted(source_bigrams | source_trigrams):
        if not any(phrase in resp.lower() for resp in model_responses):
            # Also check if individual words appear together nearby
            absent_phrases.append(phrase)
    
    return {
        "absent_words": absent_words,
        "absent_phrases": absent_phrases[:20],
        "source_word_count": len(source_words),
        "absent_count": len(absent_words),
        "absent_ratio": round(len(absent_words) / max(len(source_words), 1), 3),
    }


def load_void_frequency() -> dict:
    """Load global void frequency from disk."""
    try:
        return json.loads(_VOID_FREQ_FILE.read_text())
    except Exception:
        return {"global": {}, "by_category": {}, "total_stories": 0}


def save_void_frequency(freq: dict):
    """Save global void frequency to disk."""
    _VOID_FREQ_FILE.write_text(json.dumps(freq, indent=2))


def update_void_frequency(
    void_words: list[str],
    category: str,
    freq: dict = None,
) -> dict:
    """
    Channel B+C: Update global and per-category void frequency.
    
    Call after each story to build the frequency distribution.
    """
    if freq is None:
        freq = load_void_frequency()
    
    freq["total_stories"] = freq.get("total_stories", 0) + 1
    
    g = freq.setdefault("global", {})
    c = freq.setdefault("by_category", {}).setdefault(category, {})
    cat_totals = freq.setdefault("category_totals", {})
    cat_totals[category] = cat_totals.get(category, 0) + 1
    
    for w in void_words:
        w_lower = w.lower()
        g[w_lower] = g.get(w_lower, 0) + 1
        c[w_lower] = c.get(w_lower, 0) + 1
    
    return freq


def score_void_context(
    void_words: list[str],
    category: str,
    source_text: str = "",
    freq: dict = None,
) -> list[dict]:
    """
    Score each void word with full context:
      - source_present: was this word in the actual source text?
      - global_freq: % of all stories this word appears in void
      - category_freq: % of same-category stories
      - signal_type: HIGH_SALIENCE / GENERIC_ARTIFACT / POSSIBLE_SIGNAL
    
    No filtering. Just evidence.
    """
    if freq is None:
        freq = load_void_frequency()
    
    total = max(freq.get("total_stories", 1), 1)
    cat_total = max(freq.get("category_totals", {}).get(category, 1), 1)
    g = freq.get("global", {})
    c = freq.get("by_category", {}).get(category, {})
    source_lower = source_text.lower()
    
    results = []
    for w in void_words:
        w_lower = w.lower()
        
        in_source = w_lower in source_lower
        global_pct = round(g.get(w_lower, 0) / total * 100, 1)
        cat_pct = round(c.get(w_lower, 0) / cat_total * 100, 1)
        
        # Classify
        if in_source and global_pct < 10:
            signal = "HIGH_SALIENCE"
        elif in_source and global_pct < 30:
            signal = "POSSIBLE_SIGNAL"
        elif global_pct >= 30:
            signal = "GENERIC_ARTIFACT"
        elif not in_source and global_pct < 10:
            signal = "EMBEDDING_SIGNAL"
        else:
            signal = "POSSIBLE_SIGNAL"
        
        results.append({
            "word": w,
            "source_present": in_source,
            "global_freq_pct": global_pct,
            "category_freq_pct": cat_pct,
            "signal_type": signal,
        })
    
    return results



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
