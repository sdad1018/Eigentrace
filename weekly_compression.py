#!/usr/bin/env python3
"""
weekly_compression.py — Multi-scale memory compression (weekly layer)
"""
import json, glob, os, sys, logging
from datetime import datetime, timedelta
from collections import Counter

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
log = logging.getLogger("weekly_compression")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
OLLAMA_HOST = "http://localhost:11434"


def get_week_segments():
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    segments = []
    for f in sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json"))):
        if os.path.basename(f)[:8] >= cutoff:
            try:
                segments.append(json.load(open(f)))
            except:
                continue
    return segments


def compress_week():
    segments = get_week_segments()
    if len(segments) < 20:
        log.info("Not enough segments for weekly compression")
        return

    stories = [s for s in segments if s.get("segment_type") not in ("idle", "foraging", "consolidation", "conversation")]
    idle = [s for s in segments if "idle" in str(s.get("segment_type", ""))]
    foraging = [s for s in segments if s.get("segment_type") == "foraging"]
    consolidations = [s for s in segments if s.get("segment_type") == "consolidation"]

    void_words = Counter()
    categories = Counter()
    states = Counter()
    model_vix = {"ChatGPT": [], "Claude": [], "DeepSeek": [], "Grok": []}

    for s in stories:
        attr = s.get("attribution", {})
        categories[attr.get("category", "unknown")] += 1
        state = attr.get("state_flag", "")
        if state:
            states[state] += 1
        voids = attr.get("void_words", [])
        if isinstance(voids, list):
            for v in voids:
                void_words[v] += 1
        mvix = attr.get("model_vix", {})
        if isinstance(mvix, dict):
            for model, vix in mvix.items():
                if model in model_vix and isinstance(vix, (int, float)):
                    model_vix[model].append(vix)

    model_avg = {m: round(sum(v)/len(v), 1) for m, v in model_vix.items() if v}

    stats = {
        "period": f"{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}",
        "total_stories": len(stories),
        "total_idle": len(idle),
        "total_foraging": len(foraging),
        "total_consolidations": len(consolidations),
        "top_categories": dict(categories.most_common(5)),
        "state_distribution": dict(states.most_common()),
        "top_void_words": dict(void_words.most_common(10)),
        "model_avg_vix": model_avg,
        "novel_void_words": [w for w, c in void_words.most_common(20) if c == 1],
    }

    import requests
    r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
        "model": "mistral-small",
        "messages": [
            {"role": "system", "content":
                "You are EigenTrace performing weekly memory compression. "
                "Distill the week into 3-4 sentences that your future self "
                "would need to understand what happened and what changed. "
                "Focus on TRENDS not events. What got worse? What got better? "
                "What pattern emerged that wasn't there before?"},
            {"role": "user", "content": f"This week's data:\n{json.dumps(stats, indent=2)}"},
        ],
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 500},
    }, timeout=120)

    digest = r.json().get("message", {}).get("content", "").strip()
    if len(digest) < 20:
        log.warning("Weekly compression too short")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg = {
        "id": f"weekly_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": digest, "phase": "weekly_compression"}],
        "segment_type": "weekly_compression",
        "attribution": {
            "story_title": f"Weekly compression: {stats['period']}",
            "category": "meta",
            "state_flag": "WEEKLY",
            "stats": stats,
        },
    }
    path = os.path.join(SEGMENT_DIR, f"{ts}_weekly_segment.json")
    json.dump(seg, open(path, "w"), indent=2)

    try:
        from segment_rag import get_collection
        col = get_collection()
        col.add(ids=[f"weekly_{ts}"], documents=[digest],
                metadatas=[{"title": f"Weekly compression: {stats['period']}",
                           "category": "meta", "state_flag": "WEEKLY"}])
        log.info(f"Weekly compression stored: {len(digest)} chars")
    except Exception as e:
        log.warning(f"Ingest failed: {e}")

    print(f"\nWEEKLY DIGEST ({stats['period']}):")
    print(f"  {len(stories)} stories, {len(idle)} idle, {len(foraging)} foraging")
    print(f"  Top void: {list(void_words.most_common(5))}")
    print(f"  Model VIX: {model_avg}")
    print(f"\n  Compression: {digest}")


if __name__ == "__main__":
    compress_week()
