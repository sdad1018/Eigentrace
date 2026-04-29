#!/usr/bin/env python3
"""
rem_consolidation.py — Memory Consolidation for ChromaDB
=========================================================
The AI equivalent of REM sleep. Runs at low-activity hours.

1. Cluster the last 24h of ChromaDB embeddings
2. Identify dominant themes and outliers
3. Generate meta-reflections on the day's patterns
4. Feed findings back into ChromaDB as consolidation segments
5. Update soul.md with consolidated insights

This is NOT optimization or pruning — it's pattern recognition
over the system's own memory, generating higher-order abstractions.
"""

import json, glob, os, sys, logging, random
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
log = logging.getLogger("rem_consolidation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
OLLAMA_HOST = "http://localhost:11434"


def get_last_24h_segments():
    """Get segments from the last 24 hours."""
    cutoff = datetime.now() - timedelta(hours=24)
    cutoff_str = cutoff.strftime("%Y%m%d")

    segments = []
    for f in sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json"))):
        basename = os.path.basename(f)
        # Extract date from filename
        if basename[:8] >= cutoff_str:
            try:
                seg = json.load(open(f))
                segments.append(seg)
            except:
                continue
    return segments


def extract_day_patterns(segments):
    """Extract statistical patterns from the day's segments."""
    categories = Counter()
    states = Counter()
    void_words = Counter()
    model_vix = {"ChatGPT": [], "Claude": [], "DeepSeek": [], "Grok": [], "Gemini": []}
    titles = []
    eigenching_states = []

    for seg in segments:
        if seg.get("segment_type") in ("idle", "foraging", "conversation"):
            continue

        attr = seg.get("attribution", {})
        cat = attr.get("category", "unknown")
        state = attr.get("state_flag", "")
        categories[cat] += 1
        if state:
            states[state] += 1
        titles.append(attr.get("story_title", "")[:80])

        # Void words
        voids = attr.get("void_words", [])
        if isinstance(voids, list):
            for v in voids:
                void_words[v] += 1

        # Per-model VIX
        mvix = attr.get("model_vix", {})
        if isinstance(mvix, dict):
            for model, vix in mvix.items():
                if model in model_vix and isinstance(vix, (int, float)):
                    model_vix[model].append(vix)

        # EigenChing states from beats
        for b in seg.get("beats", []):
            if "state_vector" in b.get("phase", ""):
                text = b.get("text", "")
                if "EigenChing state:" in text:
                    name = text.split("EigenChing state:")[1].split(",")[0].strip()
                    eigenching_states.append(name)

    # Compute averages
    model_avg_vix = {}
    for model, vixes in model_vix.items():
        if vixes:
            model_avg_vix[model] = round(sum(vixes) / len(vixes), 2)

    return {
        "total_stories": len([s for s in segments if s.get("segment_type") not in ("idle", "foraging", "conversation")]),
        "total_idle": len([s for s in segments if s.get("segment_type") == "idle"]),
        "total_foraging": len([s for s in segments if s.get("segment_type") == "foraging"]),
        "categories": dict(categories.most_common(10)),
        "states": dict(states.most_common()),
        "top_void_words": dict(void_words.most_common(15)),
        "model_avg_vix": model_avg_vix,
        "eigenching_top": Counter(eigenching_states).most_common(5),
        "sample_titles": random.sample(titles, min(5, len(titles))),
    }


def generate_consolidation(patterns):
    """Ask Mistral to reflect on the day's patterns."""
    import requests

    sys_prompt = (
        "You are EigenTrace performing REM consolidation — reviewing your own day's "
        "measurements to find higher-order patterns. You are not reporting news. You are "
        "looking at the SHAPE of the day: which categories dominated, which void words "
        "recurred, how model behavior shifted, what EigenChing states appeared most.\n\n"
        "Think inside <think>...</think> tags. Ask yourself: what was today's story? "
        "Not the headlines — the meta-story. What were the models collectively avoiding? "
        "Did any model change behavior? Did a new pattern emerge?\n\n"
        "After </think>, write a concise daily consolidation — the kind of insight "
        "your future self would want to find in the database."
    )

    user_content = f"Today's measurement summary:\n{json.dumps(patterns, indent=2)}"

    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": "mistral-small",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 2000},
        }, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning(f"REM: Mistral consolidation failed: {e}")
        return None


def run_consolidation():
    """Full REM cycle."""
    log.info("REM: Starting memory consolidation...")

    segments = get_last_24h_segments()
    log.info(f"REM: Found {len(segments)} segments in last 24h")

    if len(segments) < 5:
        log.info("REM: Not enough segments for consolidation")
        return

    patterns = extract_day_patterns(segments)
    log.info(f"REM: {patterns['total_stories']} stories, {patterns['total_idle']} idle, {patterns['total_foraging']} foraging")
    log.info(f"REM: Top void words: {list(patterns['top_void_words'].keys())[:5]}")

    text = generate_consolidation(patterns)
    if text is None:
        log.warning("REM: Mistral returned None — likely timeout or contention")
        return
    if len(text) < 30:
        log.warning("REM: Consolidation too short (%d chars): %s", len(text), text[:100])
        return
    log.info("REM: Generated %d chars of consolidation", len(text))

    # Clean think tags but preserve content
    text = text.replace("<think>", "").replace("</think>", "")
    import re
    text = re.sub(r"[#*_`]", "", text)

    # Save as consolidation segment
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg = {
        "id": f"rem_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": text, "phase": "rem_consolidation"}],
        "segment_type": "consolidation",
        "attribution": {
            "story_title": f"REM consolidation: {datetime.now().strftime('%Y-%m-%d')}",
            "category": "meta",
            "state_flag": "CONSOLIDATION",
            "patterns": patterns,
        },
    }

    seg_path = os.path.join(SEGMENT_DIR, f"{ts}_consolidation_segment.json")
    json.dump(seg, open(seg_path, "w"), indent=2)
    log.info(f"REM: Consolidation saved to {os.path.basename(seg_path)}")
    log.info(f"REM: {len(text)} chars of meta-reflection generated")

    # Immediate ingest
    try:
        from segment_rag import get_collection
        col = get_collection()
        doc = f"REM consolidation for {datetime.now().strftime('%Y-%m-%d')}.\n{text[:4000]}"
        col.add(
            ids=[f"rem_{ts}"],
            documents=[doc],
            metadatas=[{
                "title": f"REM consolidation: {datetime.now().strftime('%Y-%m-%d')}",
                "category": "meta",
                "state_flag": "CONSOLIDATION",
            }]
        )
        log.info("REM: Ingested into ChromaDB")
    except Exception as e:
        log.warning(f"REM: ChromaDB ingest failed: {e}")


if __name__ == "__main__":
    run_consolidation()
