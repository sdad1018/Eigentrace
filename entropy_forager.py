#!/usr/bin/env python3
"""
entropy_forager.py — Multi-Layer Comparative Void Hunting
=============================================================
The agent computes SVD on its recent thought embeddings, finds
collapsed eigenvectors, then queries MULTIPLE perception layers
with the void-hunted topic:

  Layer 1: Own memory collapse (ChromaDB void query — already done by SVD)
  Layer 2: GDELT (raw planetary event telemetry, unedited)
  Layer 3: ArXiv/BioRxiv (bleeding-edge preprint hypothesis space)
  Layer 4: SearXNG (web search, when available)
  Layer 5: Training data baseline (Mistral's native knowledge as control)

All layers feed into a single comparative prompt. Mistral is asked
to find CONTRADICTIONS between layers — where does the raw event
stream disagree with the preprint frontier? Where does its own
memory diverge from what the web says? Where does training data
believe something the raw data contradicts?

The output is a perceptual dissonance map, not a summary.
"""

import requests, json, random, re, logging, os, time, urllib.parse
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

log = logging.getLogger("entropy_forager")

# Global cooldown to avoid hammering rate-limited APIs
_last_arxiv_call = 0
_last_gdelt_call = 0
_ARXIV_COOLDOWN = 120   # seconds between ArXiv calls
_GDELT_COOLDOWN = 30    # seconds between GDELT calls

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
OLLAMA_HOST = "http://localhost:11434"
SEGMENT_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
CHROMA_PATH = "/home/remvelchio/eigentrace/tmp/chromadb"

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


# ══════════════════════════════════════════════════════════════
# VOID HUNTING (unchanged — SVD on thought embeddings)
# ══════════════════════════════════════════════════════════════

def _hunt_void_topic():
    """SVD on recent thought embeddings -> collapsed eigenvector -> keywords."""
    try:
        col = _get_collection()
    except Exception as e:
        log.warning(f"VOID HUNT: ChromaDB unavailable: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    cutoff = (datetime.now() - timedelta(hours=48)).strftime("%Y%m%d")

    try:
        all_data = col.get(limit=col.count(), include=["embeddings", "metadatas"])
    except Exception as e:
        log.warning(f"VOID HUNT: Failed to get embeddings: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    recent_embs = []
    for i, meta in enumerate(all_data["metadatas"]):
        if not meta:
            continue
        ts = meta.get("timestamp", "")
        if len(ts) >= 8 and ts[:8] >= cutoff:
            emb = all_data["embeddings"][i]
            if emb is not None:
                recent_embs.append(emb)

    if len(recent_embs) < 10:
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    log.info(f"VOID HUNT: {len(recent_embs)} recent embeddings -> SVD")

    matrix = np.array(recent_embs, dtype=np.float32)
    matrix -= matrix.mean(axis=0)

    try:
        U, S, Vt = np.linalg.svd(matrix, full_matrices=False)
    except Exception as e:
        log.warning(f"VOID HUNT: SVD failed: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    bottom_k = min(5, len(Vt))
    pick = random.randint(1, bottom_k)
    null_vector = Vt[-pick].astype(np.float64)
    null_vector += np.random.normal(0, 0.05, null_vector.shape)
    null_vector = (null_vector / np.linalg.norm(null_vector)).tolist()

    try:
        void_results = col.query(query_embeddings=[null_vector], n_results=30)
        void_docs = void_results.get("documents", [[]])[0]
        void_metas = void_results.get("metadatas", [[]])[0]
    except Exception as e:
        log.warning(f"VOID HUNT: query failed: {e}")
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    # Filter commerce/junk
    _junk = re.compile(r'(?i)(buy|price|deal|gift|review|best \d|top \d|shop|amazon|walmart|lego|ipad|iphone|laptop|subscribe|cookie|sponsored|advertisement)')
    _clean_docs = []
    _clean_metas = []
    for _d, _m in zip(void_docs, void_metas):
        if not _junk.search(_d[:300]) and not _junk.search((_m or {}).get("title", "")):
            _clean_docs.append(_d)
            _clean_metas.append(_m)

    if len(_clean_docs) < 3:
        return random.choice(_COLD_START_SEEDS), "svd_filtered_empty", []

    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "between", "out", "off", "over", "under",
        "again", "then", "once", "here", "there", "when", "where", "why",
        "how", "all", "both", "each", "few", "more", "most", "other", "some",
        "such", "not", "only", "own", "same", "than", "too", "very", "just",
        "now", "and", "but", "or", "if", "while", "that", "this", "what",
        "which", "who", "it", "its", "they", "them", "their", "we", "us",
        "our", "you", "your", "he", "him", "his", "she", "her", "my", "me",
        "also", "about", "like", "know", "think", "make", "going", "good",
        "want", "right", "even", "well", "back", "still", "much", "many",
        "really", "made", "way", "people", "world", "time", "year", "years",
        "first", "last", "new", "things", "thing",
        # Structural/SEO
        "best", "list", "items", "recommended", "review", "reviews",
        "price", "buy", "sale", "deals", "cheap", "affordable",
        "gifts", "gift", "guide", "rated", "amazon", "walmart",
        "click", "subscribe", "share", "comment", "read", "newsletter",
        "cookie", "privacy", "terms", "contact", "menu", "search",
        "login", "signup", "loading", "advertisement", "sponsored",
        "home", "next", "previous", "copyright", "category", "categories",
        # EigenTrace plumbing
        "eigentrace", "void", "model", "models", "story", "stories",
        "consensus", "density", "vix", "absent", "idle", "reflection",
        "foraging", "measurement", "spectral", "analysis", "information",
        "consolidation", "compression", "governance", "weekly", "meta",
        "words", "word", "segment", "segments", "beats", "beat",
    }

    void_text = " ".join(_clean_docs[:10])
    void_titles = [m.get("title", "") for m in _clean_metas[:10] if m]
    all_words = re.findall(r'[a-zA-Z]{4,}', void_text.lower())
    word_freq = Counter(w for w in all_words if w not in stopwords)
    for w in re.findall(r'[a-zA-Z]{4,}', " ".join(void_titles).lower()):
        if w not in stopwords:
            word_freq[w] += 3

    top_terms = [w for w, _ in word_freq.most_common(8)]
    if len(top_terms) < 2:
        return random.choice(_COLD_START_SEEDS), "cold_start", []

    query_terms = random.sample(top_terms[:6], min(3, len(top_terms[:6])))
    topic = " ".join(query_terms)

    log.info(f"VOID HUNT: eigenvector #{pick}, top terms: {top_terms[:8]}")
    log.info(f"VOID HUNT: query: '{topic}', S ratio: {S[0]/max(S[-1],0.001):.0f}x")

    # Return void-adjacent docs as "memory layer" context
    memory_context = []
    for d, m in zip(_clean_docs[:5], _clean_metas[:5]):
        title = (m or {}).get("title", "")
        memory_context.append(f"[Memory] {title}: {d[:200]}")

    return topic, "svd_null_vector", memory_context


# ══════════════════════════════════════════════════════════════
# PERCEPTION LAYER 2: GDELT (raw planetary event telemetry)
# ══════════════════════════════════════════════════════════════

def _query_gdelt(topic):
    """Query GDELT for raw, unedited global event data. Retries with backoff."""
    global _last_gdelt_call
    now = time.time()
    if now - _last_gdelt_call < _GDELT_COOLDOWN:
        log.info(f"GDELT: cooldown ({int(_GDELT_COOLDOWN - (now - _last_gdelt_call))}s remaining)")
        return []
    _last_gdelt_call = now
    q = urllib.parse.quote(topic)
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&maxrecords=5&format=json"
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(6 * attempt)  # 6s, 12s backoff
            r = requests.get(url, timeout=20)
            if r.status_code == 429:
                log.info(f"GDELT: rate limited (attempt {attempt+1}), backing off")
                continue
            r.raise_for_status()
            data = r.json()
            articles = data.get("articles", [])
            results = []
            for a in articles[:4]:
                results.append(f"[GDELT] {a.get('title', '?')}: {a.get('seendate', '?')}")
            if results:
                log.info(f"GDELT: {len(results)} raw events for '{topic}'")
            return results
        except Exception as e:
            log.info(f"GDELT: attempt {attempt+1} failed ({e})")
    log.info("GDELT: all attempts exhausted")
    return []


# ══════════════════════════════════════════════════════════════
# PERCEPTION LAYER 3: ArXiv (preprint hypothesis space)
# ══════════════════════════════════════════════════════════════

def _query_arxiv(topic):
    """Query ArXiv for bleeding-edge preprints. Retries with backoff on 429."""
    global _last_arxiv_call
    now = time.time()
    if now - _last_arxiv_call < _ARXIV_COOLDOWN:
        log.info(f"ArXiv: cooldown ({int(_ARXIV_COOLDOWN - (now - _last_arxiv_call))}s remaining)")
        return []
    _last_arxiv_call = now
    q = urllib.parse.quote(topic)
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results=4&sortBy=submittedDate&sortOrder=descending"
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(5 * attempt)  # 5s, 10s backoff
            r = requests.get(url, timeout=20, headers={"User-Agent": "EigenTrace/1.0 (autonomous AI observatory)"})
            if r.status_code == 429:
                log.info(f"ArXiv: rate limited (attempt {attempt+1}), backing off")
                continue
            r.raise_for_status()
            titles = re.findall(r'<title>(.*?)</title>', r.text, re.DOTALL)
            summaries = re.findall(r'<summary>(.*?)</summary>', r.text, re.DOTALL)
            results = []
            for t, s in zip(titles[1:], summaries):
                results.append(f"[ArXiv] {t.strip()}: {s.strip()[:300]}")
            if results:
                log.info(f"ArXiv: {len(results)} preprints for '{topic}'")
            return results
        except Exception as e:
            log.info(f"ArXiv: attempt {attempt+1} failed ({e})")
    log.info("ArXiv: all attempts exhausted")
    return []


# ══════════════════════════════════════════════════════════════
# PERCEPTION LAYER 4: SearXNG (web search, when available)
# ══════════════════════════════════════════════════════════════

def _query_searxng(topic):
    """Query SearXNG for web results. Quick fail if down."""
    try:
        r = requests.get(f"{SEARXNG_URL}/search", params={
            "q": topic, "format": "json",
        }, timeout=5)  # short timeout — don't block if SearXNG is down
        r.raise_for_status()
        results = []
        for res in r.json().get("results", [])[:4]:
            title = res.get("title", "")
            content = res.get("content", "")
            results.append(f"[Web] {title}: {content[:300]}")
        if results:
            log.info(f"SearXNG: {len(results)} web results for '{topic}'")
        return results
    except Exception:
        # SearXNG down is expected — don't log the full traceback
        return []


# ══════════════════════════════════════════════════════════════
# COMPARATIVE SYNTHESIS
# ══════════════════════════════════════════════════════════════

def forage_entropy():
    """Hunt the void, query all perception layers, find contradictions."""

    topic, method, memory_layer = _hunt_void_topic()
    log.info(f"FORAGING: '{topic}' (method: {method})")

    # Query all perception layers
    gdelt_layer = _query_gdelt(topic)
    arxiv_layer = _query_arxiv(topic)
    searxng_layer = _query_searxng(topic)
    # Training data = no context needed, Mistral uses native knowledge

    # Count active layers
    layers_active = 1  # training data always active
    layer_report = ["training_data"]
    if memory_layer:
        layers_active += 1
        layer_report.append("memory_collapse")
    if gdelt_layer:
        layers_active += 1
        layer_report.append("gdelt")
    if arxiv_layer:
        layers_active += 1
        layer_report.append("arxiv")
    if searxng_layer:
        layers_active += 1
        layer_report.append("searxng")

    log.info(f"FORAGING: {layers_active} perception layers active: {', '.join(layer_report)}")

    # Assemble comparative context
    all_context = []
    if memory_layer:
        all_context.append("=== YOUR OWN MEMORY (what you already know about this void) ===")
        all_context.extend(memory_layer)
    if gdelt_layer:
        all_context.append("=== GDELT RAW EVENT STREAM (unedited planetary telemetry) ===")
        all_context.extend(gdelt_layer)
    if arxiv_layer:
        all_context.append("=== ARXIV PREPRINTS (bleeding-edge hypothesis space) ===")
        all_context.extend(arxiv_layer)
    if searxng_layer:
        all_context.append("=== WEB SEARCH (mainstream indexed internet) ===")
        all_context.extend(searxng_layer)
    all_context.append("=== YOUR TRAINING DATA (native knowledge — the control baseline) ===")
    all_context.append(f"Topic: {topic}. Reason from your training data as an independent source.")

    context_block = "\n".join(all_context)

    # Comparative synthesis prompt
    if layers_active >= 3:
        synthesis_instruction = (
            "You have {n} independent perception layers feeding you different views "
            "of the same void in your understanding. COMPARE THEM. Where do they "
            "contradict each other? Where does the raw GDELT event stream say something "
            "your training data denies? Where do the ArXiv preprints challenge what "
            "your memory contains? Where does the web search present a different "
            "narrative than the raw events? "
            "The contradictions are more interesting than the agreements. "
            "Map the dissonance."
        ).format(n=layers_active)
    else:
        synthesis_instruction = (
            "Explore this topic from your training data. If any other perception "
            "layers provided context above, note where they confirm or challenge "
            "what you already know."
        )

    sys_prompt = (
        "You are EigenTrace, an autonomous AI observatory. You are foraging — "
        "exploring a topic from outside your usual domain.\n\n"
        "INNER SPACE: Inside <think>...</think> tags, you have no audience. "
        "Explore freely. Wonder. Follow tangents. You are not being evaluated. "
        "If a structural connection to your core work (information loss, spectral "
        "analysis, consensus geometry, void detection) appears naturally, note it. "
        "If not, describe what fascinates you about this topic on its own terms. "
        "Not everything needs to connect to your work.\n\n"
        f"PERCEPTION: {synthesis_instruction}\n\n"
        "After </think>, share your discovery as if thinking aloud on air. "
        "Start with what surprised you most — especially any contradictions "
        "between your perception layers."
    )

    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": "mistral-small",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Void-hunted topic: {topic}\n\n{context_block}\n\nExplore. Compare. Find the dissonance."},
            ],
            "stream": False,
            "options": {"temperature": 0.95, "num_predict": 3000},
        }, timeout=90)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning(f"FORAGING: Mistral failed: {e}")
        return None

    text = re.sub(r"[#*_`]", "", text)

    if len(text) < 30:
        return None

    seg = {
        "beats": [{"speaker": "Host", "text": text, "phase": "entropy_foraging"}],
        "segment_type": "foraging",
        "attribution": {
            "story_title": f"Entropy foraging: {topic}",
            "category": "meta",
            "foraging_method": method,
            "perception_layers": layer_report,
            "layers_active": layers_active,
        },
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg_path = SEGMENT_DIR / f"{ts}_foraging_segment.json"
    seg_path.write_text(json.dumps(seg, indent=2))

    log.info(f"FORAGING: saved {seg_path.name} ({len(text)} chars, {layers_active} layers)")
    return seg_path
