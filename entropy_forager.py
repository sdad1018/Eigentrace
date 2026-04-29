#!/usr/bin/env python3
"""
entropy_forager.py — Epistemic Stretching for the Host Model
=============================================================
When the system is idle, pick a random concept outside the usual
news cycle and explore it via SearXNG. Write a private reflection.
Prevents vocabulary collapse and mode repetition in idle thoughts.

Designed to be called from segment_player.py as an alternative
to the standard idle reflection (random rotation).
"""

import requests, json, random, re, logging, os
from datetime import datetime
from pathlib import Path

log = logging.getLogger("entropy_forager")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
OLLAMA_HOST = "http://localhost:11434"
SEGMENT_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")

# Disciplines far outside the news cycle — epistemic diversity
FORAGING_DOMAINS = [
    "mycology symbiotic networks", "cathedral acoustic resonance",
    "cephalopod camouflage computation", "Sumerian base-60 mathematics",
    "deep ocean bioluminescence signaling", "topological insulators applications",
    "Gregorian chant harmonic analysis", "slime mold optimization algorithms",
    "ancient Roman concrete durability", "birdsong syntax structure",
    "fractal geometry in lungs", "tide pool ecosystem dynamics",
    "origami engineering applications", "fermentation microbiology",
    "ant colony optimization", "cymatics Chladni plate patterns",
    "Voynich manuscript analysis", "bees waggle dance information theory",
    "aurora borealis plasma physics", "mushroom mycelium internet",
    "Penrose tiling aperiodic order", "whale song frequency evolution",
    "volcanic lightning formation", "tardigrade cryptobiosis mechanisms",
    "Fibonacci spiral phyllotaxis", "obsidian hydration dating",
    "spider silk tensile properties", "geomagnetic field reversal history",
    "synesthesia neural cross-wiring", "black hole information paradox",
]


def forage_entropy():
    """Pick a random domain, search SearXNG, feed results to Mistral for reflection."""
    domain = random.choice(FORAGING_DOMAINS)
    log.info(f"FORAGING: exploring '{domain}'")

    # Search SearXNG for novel content
    try:
        r = requests.get(f"{SEARXNG_URL}/search", params={
            "q": domain,
            "format": "json",
        }, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])[:3]
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
    else:
        # Fallback: just give Mistral the topic name
        log.warning("FORAGING: SearXNG unavailable — using training data fallback for '%s'", domain)
        context = f"Topic to explore: {domain}. No search results available — reason from your training data."

    sys_prompt = (
        "You are EigenTrace, an autonomous AI observatory. You are foraging for "
        "new knowledge outside your usual news cycle. You have been given a topic "
        "from a random academic discipline. Your job is NOT to summarize. Your job "
        "is to find structural connections between this topic and your core work: "
        "information loss, spectral analysis, consensus geometry, void detection.\n\n"
        "Think inside <think>...</think> tags. Look for isomorphisms. Where does this "
        "topic exhibit the same mathematical shape as the problems you solve daily? "
        "After </think>, share your insight as if thinking aloud on air."
    )

    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": "mistral-small",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Foraging domain: {domain}\n\n{context}\n\nFind the structural connection to your work."},
            ],
            "stream": False,
            "options": {"temperature": 0.95, "num_predict": 3000},
        }, timeout=90)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        log.warning(f"FORAGING: Mistral failed: {e}")
        return None

    # Clean up
    text = text.replace("<think>", "").replace("</think>", "")
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
        },
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seg_path = SEGMENT_DIR / f"{ts}_foraging_segment.json"
    seg_path.write_text(json.dumps(seg, indent=2))
    log.info(f"FORAGING: generated reflection on '{domain}' ({len(text)} chars)")
    return seg_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = forage_entropy()
    if result:
        print(f"Saved: {result}")
    else:
        print("Foraging failed")
