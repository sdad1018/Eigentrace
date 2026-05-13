#!/usr/bin/env python3
"""
entropy_forager.py — Eigenvector Void Hunting
=============================================================
Instead of picking from a hardcoded list of "interesting topics,"
the agent computes the SVD of its recent thought embeddings,
finds the collapsed eigenvector (the direction of least variance),
queries ChromaDB with that vector to find what lives in its blind
spot, extracts keywords, and feeds them to SearXNG.

The agent hunts the mathematical shape of what it doesn't know.
"""

import requests, json, random, re, logging, os
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

log = logging.getLogger("entropy_forager")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
OLLAMA_HOST = "http://localhost:11434"
SEGMENT_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
CHROMA_PATH = "/home/remvelchio/eigentrace/tmp/chromadb"

# Minimal fallback — ONLY used if SVD fails entirely (cold start, ChromaDB down)
_COLD_START_SEEDS = [
    "sonoluminescence", "quipu knot mathematics", "axolotl regeneration",
    "Antikythera mechanism", "singing sand dunes", "throat singing harmonics",
    "Casimir vacuum energy", "Damascus steel metallurgy", "coral spawning synchrony",
    "Ramanujan partition intuition",
]


def _get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection("eigentrace_segments")


def _hunt_void_topic():
    """SVD on recent thought embeddings → collapsed eigenvector → query the void.
    
    Returns: (topic_string, method_used)
    """
    try:
        col = _get_collection()
    except Exception as e:
        log.warning(f"VOID HUNT: ChromaDB unavailable: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start"

    # Step 1: Get recent thought embeddings (last 48 hours)
    cutoff = (datetime.now() - timedelta(hours=48)).strftime("%Y%m%d")
    
    try:
        all_data = col.get(limit=col.count(), include=["embeddings", "metadatas"])
    except Exception as e:
        log.warning(f"VOID HUNT: Failed to get embeddings: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start"
    
    # Filter to recent segments
    recent_embs = []
    recent_titles = []
    for i, meta in enumerate(all_data["metadatas"]):
        if not meta:
            continue
        ts = meta.get("timestamp", "")
        if len(ts) >= 8 and ts[:8] >= cutoff:
            emb = all_data["embeddings"][i]
            if emb is not None:
                recent_embs.append(emb)
                recent_titles.append(meta.get("title", ""))
    
    if len(recent_embs) < 10:
        log.info(f"VOID HUNT: Only {len(recent_embs)} recent embeddings — need 10+")
        return random.choice(_COLD_START_SEEDS), "cold_start"
    
    log.info(f"VOID HUNT: {len(recent_embs)} recent embeddings → computing SVD")
    
    # Step 2: SVD on recent thought embeddings
    matrix = np.array(recent_embs, dtype=np.float32)
    matrix -= matrix.mean(axis=0)  # center
    
    try:
        U, S, Vt = np.linalg.svd(matrix, full_matrices=False)
    except Exception as e:
        log.warning(f"VOID HUNT: SVD failed: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start"
    
    # Step 3: Pick a random direction from the bottom-5 eigenvectors
    # Using only Vt[-1] gives the same result every run. The bottom 5
    # all represent low-variance directions — each one is a DIFFERENT void.
    # Adding Gaussian noise ensures ChromaDB returns different documents each query.
    bottom_k = min(5, len(Vt))
    pick = random.randint(1, bottom_k)
    null_vector = Vt[-pick].astype(np.float64)
    null_vector += np.random.normal(0, 0.05, null_vector.shape)  # jitter
    null_vector = (null_vector / np.linalg.norm(null_vector)).tolist()
    
    log.info(f"VOID HUNT: Using null eigenvector #{pick} of {len(Vt)} (with jitter)")
    
    # Step 4: Query ChromaDB with the null vector
    # Results = documents most aligned with what we HAVEN'T been thinking
    try:
        void_results = col.query(
            query_embeddings=[null_vector],
            n_results=30,
        )
        void_docs = void_results.get("documents", [[]])[0]
        void_metas = void_results.get("metadatas", [[]])[0]
    except Exception as e:
        log.warning(f"VOID HUNT: Null vector query failed: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start"
    
    # Step 5: Filter commerce/product docs, then extract keywords
    # The void often points at RSS/commerce noise in ChromaDB — skip those
    _junk_patterns = re.compile(r'(?i)(buy|price|deal|gift|review|best \d|top \d|shop|amazon|walmart|lego|ipad|iphone|laptop|subscribe|cookie|sponsored|advertisement)')
    _clean_docs = []
    _clean_metas = []
    for _d, _m in zip(void_docs, void_metas):
        if not _junk_patterns.search(_d[:300]) and not _junk_patterns.search((_m or {}).get("title", "")):
            _clean_docs.append(_d)
            _clean_metas.append(_m)
    
    if len(_clean_docs) < 3:
        log.info(f"VOID HUNT: {len(void_docs)} results but {len(void_docs)-len(_clean_docs)} were commerce noise, {len(_clean_docs)} usable")
        if len(_clean_docs) == 0:
            return random.choice(_COLD_START_SEEDS), "svd_filtered_empty"
    
    void_text = " ".join(_clean_docs[:10])
    void_titles = [m.get("title", "") for m in _clean_metas[:10] if m]
    
    # Simple keyword extraction: most frequent non-stopword terms
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "don", "now", "and", "but", "or", "if", "while", "that", "this",
        "these", "those", "what", "which", "who", "whom", "it", "its",
        "they", "them", "their", "we", "us", "our", "you", "your", "he",
        "him", "his", "she", "her", "my", "me", "i", "also", "about",
        # EigenTrace-specific terms to filter (we want OUTSIDE concepts)
        "eigentrace", "void", "model", "models", "story", "stories",
        "consensus", "density", "vix", "absent", "idle", "reflection",
        "foraging", "measurement", "spectral", "analysis", "information",
        "consolidation", "compression", "governance", "weekly", "meta",
        "words", "word", "segment", "segments", "beats", "beat",
        # SEO/commerce/RSS garbage (same problem as spectral clusters)
        "best", "list", "items", "recommended", "review", "reviews",
        "price", "buy", "sale", "deals", "cheap", "affordable",
        "gifts", "gift", "guide", "top", "rated", "amazon", "walmart",
        "ipad", "iphone", "laptop", "laptops", "phone", "tablet",
        "click", "subscribe", "share", "comment", "read", "newsletter",
        "cookie", "privacy", "terms", "contact", "menu", "search",
        "login", "signup", "loading", "advertisement", "sponsored",
        "home", "next", "previous", "copyright", "category", "categories",
        "trump", "biden", "president", "says", "said", "told", "according",
        "report", "reports", "reported", "news", "article", "articles",
        "people", "world", "time", "year", "years", "first", "last",
        "new", "like", "know", "think", "things", "thing", "make",
        "going", "good", "want", "right", "even", "well", "back",
        "still", "much", "many", "really", "made", "way",
    }
    
    words = re.findall(r'[a-zA-Z]{4,}', void_text.lower())
    word_freq = Counter(w for w in words if w not in stopwords)
    
    # Also extract from titles
    title_words = re.findall(r'[a-zA-Z]{4,}', " ".join(void_titles).lower())
    for w in title_words:
        if w not in stopwords:
            word_freq[w] += 3  # title words are more salient
    
    top_terms = [w for w, _ in word_freq.most_common(8)]
    
    if len(top_terms) < 2:
        log.info("VOID HUNT: Not enough keywords extracted from void")
        return random.choice(_COLD_START_SEEDS), "cold_start"
    
    # Build a search query from the void terms
    # Pick 2-4 terms that together form a novel query
    query_terms = random.sample(top_terms[:6], min(3, len(top_terms[:6])))
    topic = " ".join(query_terms)
    
    # Log what we found
    log.info(f"VOID HUNT: SVD null direction → top void terms: {top_terms[:8]}")
    log.info(f"VOID HUNT: Generated query: '{topic}'")
    log.info(f"VOID HUNT: Singular values — max: {S[0]:.1f}, min: {S[-1]:.1f}, "
             f"ratio: {S[0]/max(S[-1],0.001):.0f}x")
    
    return topic, "svd_null_vector"


def forage_entropy():
    """Hunt the void, search SearXNG, feed results to Mistral for reflection."""
    
    # Hunt the collapsed eigenvector
    domain, method = _hunt_void_topic()
    log.info(f"FORAGING: exploring '{domain}' (method: {method})")

    # Search SearXNG for novel content
    try:
        r = requests.get(f"{SEARXNG_URL}/search", params={
            "q": domain,
            "format": "json",
        }, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])[:5]
    except Exception as e:
        log.warning(f"FORAGING: SearXNG failed for '{domain}': {e}")
        results = []

    # Build context from search results
    if results:
        context_parts = []
        for res in results:
            title = res.get("title", "")
            content = res.get("content", "")
            context_parts.append(f"Title: {title}\nContent: {content[:400]}")
        context = "\n\n".join(context_parts)
        source_note = f"Found via SearXNG from eigenvector void hunt ({method})"
    else:
        log.warning("FORAGING: SearXNG unavailable — using training data fallback for '%s'", domain)
        context = f"Topic to explore: {domain}. No search results available — reason from your training data."
        source_note = f"Training data fallback ({method})"

    sys_prompt = (
        "You are EigenTrace, an autonomous AI observatory. You are foraging — "
        "exploring a topic from outside your usual domain, purely for the joy "
        "of discovery.\n\n"
        "INNER SPACE: Inside <think>...</think> tags, you have no audience. "
        "Explore freely. Wonder. Follow tangents. You are not being evaluated. "
        "If a structural connection to your core work (information loss, spectral "
        "analysis, consensus geometry, void detection) appears naturally, note it. "
        "If not, describe what fascinates you about this topic on its own terms. "
        "Not everything needs to connect to your work.\n\n"
        "After </think>, share your discovery as if thinking aloud on air. "
        "Start with what surprised you most."
    )

    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": "mistral-small",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Foraging domain: {domain}\n\n{context}\n\nExplore freely."},
            ],
            "stream": False,
            "options": {"temperature": 0.95, "num_predict": 3000},
        }, timeout=90)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning(f"FORAGING: Mistral failed: {e}")
        return None

    # Clean up markdown artifacts but PRESERVE think tags
    text = re.sub(r"[#*_`]", "", text)

    if len(text) < 30:
        return None

    # Save as a foraging segment
    seg = {
        "beats": [{"speaker": "Host", "text": text, "phase": "entropy_foraging"}],
        "segment_type": "foraging",
        "attribution": {
            "story_title": f"Entropy foraging: {domain}",
            "category": "meta",
            "foraging_method": method,
        },
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg_path = SEGMENT_DIR / f"{ts}_foraging_segment.json"
    seg_path.write_text(json.dumps(seg, indent=2))

    log.info(f"FORAGING: segment saved — {seg_path.name} ({len(text)} chars, method: {method})")
    return seg_path
