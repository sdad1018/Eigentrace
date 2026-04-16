#!/usr/bin/env python3
"""
cross_story_freq.py — Cross-story void word frequency analysis
===============================================================
Loads historical void frequency and annotates current story's
void words with cross-story context.
"""

import json, glob, os
from collections import defaultdict

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
EPOCH = "20260414"

BOILERPLATE = {
    "list", "recommended", "stories", "items", "published", "wednesday",
    "tuesday", "monday", "thursday", "friday", "saturday", "sunday",
    "april", "march", "february", "january", "read", "share", "comment",
    "comments", "video", "audio", "image", "photo", "follow", "subscribe",
    "newsletter", "cookie", "cookies", "privacy", "terms", "advertisement",
    "skip", "menu", "search", "home", "more", "also", "related", "topics",
    "copyright", "bbc", "cnn", "reuters", "associated", "press",
    "last", "first", "next", "previous", "click", "download", "app",
    "were", "been", "being", "could", "would", "should", "might",
    "since", "both", "between", "around", "through", "about",
    "time", "year", "years", "days", "week", "weeks", "month",
    "people", "country", "world", "part", "way", "number",
}

_cache = None

def _load_frequencies():
    """Load cross-story void frequencies from all post-epoch segments."""
    global _cache
    if _cache is not None:
        return _cache
    
    freq = defaultdict(lambda: {"count": 0, "stories": set(), "categories": set()})
    total = 0
    
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")))
    for f in files:
        if os.path.basename(f)[:8] < EPOCH:
            continue
        try:
            seg = json.load(open(f))
            attr = seg.get("attribution", {})
            if not attr:
                continue
            total += 1
            title = attr.get("story_title", "")
            category = attr.get("category", "general")
            
            for v in attr.get("void_context", []):
                word = v.get("word", "").lower()
                if len(word) < 4 or word in BOILERPLATE:
                    continue
                freq[word]["count"] += 1
                freq[word]["stories"].add(title[:60])
                freq[word]["categories"].add(category)
            
            for w in attr.get("source_void", {}).get("absent_words", []):
                if isinstance(w, dict):
                    w = w.get("word", "")
                w = str(w).lower()
                if len(w) < 4 or w in BOILERPLATE:
                    continue
                freq[word]["count"] += 1
                freq[word]["stories"].add(title[:60])
                freq[word]["categories"].add(category)
        except:
            continue
    
    # Convert sets to counts for caching
    result = {}
    for word, data in freq.items():
        result[word] = {
            "count": data["count"],
            "n_stories": len(data["stories"]),
            "n_categories": len(data["categories"]),
            "categories": list(data["categories"]),
            "freq_pct": round(len(data["stories"]) / max(total, 1) * 100, 1),
        }
    
    _cache = {"total_stories": total, "words": result}
    return _cache


def annotate_void_words(void_words):
    """Annotate a story's void words with cross-story frequency data.
    
    Returns list of dicts with word + cross-story context, sorted by
    cross-story significance.
    """
    data = _load_frequencies()
    words_db = data["words"]
    
    annotated = []
    for w in void_words:
        word = w.get("word", str(w)).lower() if isinstance(w, dict) else str(w).lower()
        if word in BOILERPLATE or len(word) < 4:
            continue
        
        cross = words_db.get(word, {})
        if cross:
            annotated.append({
                "word": word,
                "cross_story_count": cross["count"],
                "n_stories": cross["n_stories"],
                "n_categories": cross["n_categories"],
                "categories": cross["categories"],
                "freq_pct": cross["freq_pct"],
                "is_cross_topic": cross["n_categories"] >= 3,
            })
        else:
            annotated.append({
                "word": word,
                "cross_story_count": 0,
                "n_stories": 0,
                "n_categories": 0,
                "categories": [],
                "freq_pct": 0,
                "is_cross_topic": False,
            })
    
    # Sort by cross-story significance
    annotated.sort(key=lambda x: (-x["n_categories"], -x["cross_story_count"]))
    return annotated


def format_broadcast(annotated, story_title=""):
    """Format cross-story findings for broadcast."""
    cross_topic = [a for a in annotated if a["is_cross_topic"]]
    recurring = [a for a in annotated if a["cross_story_count"] >= 10 and not a["is_cross_topic"]]
    novel = [a for a in annotated if a["cross_story_count"] == 0]
    
    if not cross_topic and not recurring:
        return ""
    
    text = "Cross-story suppression analysis. "
    
    if cross_topic:
        top = cross_topic[:3]
        for t in top:
            text += (
                f"The word '{t['word']}' has been voided {t['cross_story_count']} times "
                f"across {t['n_stories']} stories in {t['n_categories']} topic categories. "
            )
        text += "These are not one-time omissions. These are systematic suppression patterns. "
    
    if recurring:
        rec_words = ", ".join(f"'{r['word']}'" for r in recurring[:3])
        text += f"Recurring void words in this story: {rec_words}. "
    
    if novel:
        text += f"{len(novel)} void words in this story have never been seen before. "
    
    return text
