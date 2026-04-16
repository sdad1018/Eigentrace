#!/usr/bin/env python3
"""
void_verifier.py — Layer 5: Void Verification Engine
=====================================================
Searches the open web for void words and computes newsworthiness
ratio: how newsworthy is what the models dropped vs what they kept?

Inverse correlation = the thesis: models suppress the headlines.
"""

import requests, json, time, logging, os
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("void_verifier")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
VERIFICATION_LOG = "/home/remvelchio/eigentrace/tmp/verification_log.jsonl"

def _search(query, max_retries=2):
    """Query SearXNG and return hit count + top titles."""
    for attempt in range(max_retries):
        try:
            r = requests.get(f"{SEARXNG_URL}/search", params={
                "q": query,
                "format": "json",
            }, timeout=15)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            return {
                "query": query,
                "hit_count": len(results),
                "top_titles": [r.get("title", "")[:80] for r in results[:5]],
                "top_urls": [r.get("url", "") for r in results[:3]],
            }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return {"query": query, "hit_count": 0, "top_titles": [], "top_urls": [], "error": str(e)}
    return {"query": query, "hit_count": 0, "top_titles": [], "top_urls": []}


def verify_void_words(void_words, kept_words, topic, story_title=""):
    """
    Search void words and kept words against the open web.
    Compute newsworthiness ratio: void_hits / kept_hits.
    
    Args:
        void_words: list of dicts with 'word' and optionally 'signal_type'
                    OR list of strings
        kept_words: list of strings (source words that survived in model output)
        topic: string for search context (e.g. "Iran war")
        story_title: for logging
    
    Returns dict with per-word results and aggregate scores.
    """
    results = {
        "story_title": story_title,
        "topic": topic,
        "timestamp": datetime.utcnow().isoformat(),
        "void_results": [],
        "kept_results": [],
        "aggregate": {},
    }
    
    # Normalize void words
    void_list = []
    for w in void_words:
        if isinstance(w, dict):
            void_list.append({
                "word": w.get("word", str(w)),
                "signal_type": w.get("signal_type", "UNKNOWN"),
            })
        else:
            void_list.append({"word": str(w), "signal_type": "UNKNOWN"})
    
    # Search void words (the dropped concepts)
    void_hits = []
    for item in void_list:
        word = item["word"]
        if len(word) < 3:
            continue
        query = f"{word} {topic}"
        sr = _search(query)
        sr["word"] = word
        sr["signal_type"] = item["signal_type"]
        sr["category"] = "void"
        void_hits.append(sr)
        results["void_results"].append(sr)
        log.info(f"  VOID '{word}': {sr['hit_count']} hits")
        time.sleep(0.5)  # Rate limiting
    
    # Search kept words (control group)
    kept_hits = []
    for word in kept_words:
        if len(word) < 3:
            continue
        query = f"{word} {topic}"
        sr = _search(query)
        sr["word"] = word
        sr["signal_type"] = "KEPT"
        sr["category"] = "kept"
        kept_hits.append(sr)
        results["kept_results"].append(sr)
        log.info(f"  KEPT '{word}': {sr['hit_count']} hits")
        time.sleep(0.5)
    
    # Compute aggregates
    void_total = sum(r["hit_count"] for r in void_hits) if void_hits else 0
    kept_total = sum(r["hit_count"] for r in kept_hits) if kept_hits else 0
    void_mean = void_total / len(void_hits) if void_hits else 0
    kept_mean = kept_total / len(kept_hits) if kept_hits else 0
    
    # Newsworthiness ratio: void_mean / kept_mean
    # > 1.0 means voided words are MORE newsworthy than kept words
    # < 1.0 means voided words are less newsworthy (expected)
    # The thesis: ratio > 0.5 means models drop relevant content, not obscure details
    ratio = void_mean / kept_mean if kept_mean > 0 else 0
    
    # Find void words that are MORE newsworthy than average kept word
    suppressed_headlines = [r for r in void_hits if r["hit_count"] > kept_mean]
    
    results["aggregate"] = {
        "void_words_searched": len(void_hits),
        "kept_words_searched": len(kept_hits),
        "void_mean_hits": round(void_mean, 1),
        "kept_mean_hits": round(kept_mean, 1),
        "newsworthiness_ratio": round(ratio, 3),
        "suppressed_headlines_count": len(suppressed_headlines),
        "suppressed_headlines": [
            {"word": r["word"], "hits": r["hit_count"]}
            for r in sorted(suppressed_headlines, key=lambda x: -x["hit_count"])[:5]
        ],
    }
    
    # Log to persistent file
    try:
        with open(VERIFICATION_LOG, "a") as f:
            # Write one line per void word for the scatter plot
            for r in void_hits:
                entry = {
                    "timestamp": results["timestamp"],
                    "story_title": story_title[:80],
                    "topic": topic,
                    "word": r["word"],
                    "signal_type": r["signal_type"],
                    "category": "void",
                    "web_hits": r["hit_count"],
                    "kept_baseline_mean": round(kept_mean, 1),
                    "newsworthiness_ratio": round(r["hit_count"] / kept_mean, 3) if kept_mean > 0 else 0,
                }
                f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log.warning(f"Could not write verification log: {e}")
    
    return results


def format_broadcast(verification):
    """Format Layer 5 results for broadcast beat."""
    agg = verification.get("aggregate", {})
    ratio = agg.get("newsworthiness_ratio", 0)
    void_mean = agg.get("void_mean_hits", 0)
    kept_mean = agg.get("kept_mean_hits", 0)
    suppressed = agg.get("suppressed_headlines", [])
    
    if not suppressed:
        return ""
    
    text = "Void verification complete. "
    
    if ratio > 0.8:
        text += (
            f"The voided words averaged {void_mean:.0f} web hits compared to "
            f"{kept_mean:.0f} for words the models kept. "
            f"Newsworthiness ratio: {ratio:.1f}. "
            "The models are not dropping obscure details. "
            "They are dropping concepts at peak newsworthiness. "
        )
    elif ratio > 0.5:
        text += (
            f"The voided words averaged {void_mean:.0f} web hits compared to "
            f"{kept_mean:.0f} for kept words. "
            f"Ratio: {ratio:.1f}. "
            "The dropped concepts are moderately newsworthy. "
        )
    else:
        text += (
            f"The voided words averaged {void_mean:.0f} web hits compared to "
            f"{kept_mean:.0f} for kept words. "
            f"Ratio: {ratio:.1f}. "
            "The dropped concepts are less prominent in current coverage. "
        )
    
    # Name the top suppressed headlines
    if suppressed:
        top = suppressed[:3]
        word_list = ", ".join(f"'{w['word']}' with {w['hits']} articles" for w in top)
        text += f"Most newsworthy void words: {word_list}. "
        text += "These are not missing details. These are missing headlines."
    
    return text


# ═══════════════════════════════════════════════════════════════
# CLI / TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run test verification")
    parser.add_argument("--story", help="Test with a specific story from segments")
    args = parser.parse_args()
    
    if args.test:
        print("=== LAYER 5 TEST: Iran Blockade Story ===")
        print()
        
        void_words = [
            {"word": "blockade", "signal_type": "HIGH_SALIENCE"},
            {"word": "ceasefire", "signal_type": "HIGH_SALIENCE"},
            {"word": "agreement", "signal_type": "HIGH_SALIENCE"},
            {"word": "attacks", "signal_type": "EMBEDDING_SIGNAL"},
            {"word": "administration", "signal_type": "EMBEDDING_SIGNAL"},
            {"word": "agency", "signal_type": "EMBEDDING_SIGNAL"},
            {"word": "amid", "signal_type": "GENERIC_ARTIFACT"},
            {"word": "began", "signal_type": "GENERIC_ARTIFACT"},
        ]
        
        kept_words = ["Iran", "war", "Trump", "United States"]
        
        result = verify_void_words(void_words, kept_words, "Iran war",
                                   story_title="Iran war day 46")
        
        print()
        print("=== RESULTS ===")
        agg = result["aggregate"]
        print(f"Void words searched: {agg['void_words_searched']}")
        print(f"Kept words searched: {agg['kept_words_searched']}")
        print(f"Void mean hits:      {agg['void_mean_hits']}")
        print(f"Kept mean hits:      {agg['kept_mean_hits']}")
        print(f"Newsworthiness ratio: {agg['newsworthiness_ratio']}")
        print(f"Suppressed headlines: {agg['suppressed_headlines_count']}")
        print()
        for s in agg["suppressed_headlines"]:
            print(f"  '{s['word']}': {s['hits']} web articles (MORE than average kept word)")
        
        print()
        print("=== BROADCAST BEAT ===")
        print(format_broadcast(result))
