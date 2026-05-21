#!/usr/bin/env python3
"""
autonomous_forager.py — Curiosity-Driven Epistemic Metabolism
==============================================================
Three sovereign data sources, zero API keys:

1. Curiosity Forager: walks the web guided by surprise scoring
   against ChromaDB. Hunts for what the system DOESN'T know.
2. AT Protocol Firehose: taps Bluesky's public stream for
   real-time entity mentions.
3. Wikipedia Friction: (imported from epistemic_sensor.py)

The idle agent calls these when news is slow. The system
stops waiting for RSS and starts hunting autonomously.
"""

import requests, json, time, re, random, logging, subprocess
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
import numpy as np

import sys
sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

log = logging.getLogger("autonomous_forager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OLLAMA_HOST = "http://localhost:11434"
SEGMENT_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")

SEED_URLS = [
    "https://news.ycombinator.com/",
    "https://en.wikipedia.org/wiki/Portal:Current_events",
    "https://www.aljazeera.com/",
    "https://www.dw.com/en/top-stories/s-9097",
    "https://arxiv.org/list/cs.AI/recent",
    "https://www.reuters.com/",
    "https://ground.news/",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


# ══════════════════════════════════════════════════════════════════════════
# SURPRISE SCORING: How novel is this page vs what we already know?
# ══════════════════════════════════════════════════════════════════════════

def compute_surprise(text, top_k=3):
    """
    Embed text and compute surprise = 1 - max_similarity to existing ChromaDB.
    High surprise = the system has never seen anything like this.
    Returns float 0-1 (1 = maximally novel).
    """
    try:
        from segment_rag import get_collection
        from geometric_engine import GeometricPerturbationEngine
        
        col = get_collection()
        if col.count() < 10:
            return 0.5  # Not enough data to judge
        
        # Query ChromaDB for most similar existing segments
        results = col.query(query_texts=[text[:500]], n_results=top_k)
        
        if not results or not results.get('distances'):
            return 0.5
        
        # ChromaDB returns distances (lower = more similar)
        # Convert to surprise (higher = more novel)
        distances = results['distances'][0]
        max_similarity = 1.0 - min(distances) if distances else 0.5
        surprise = 1.0 - max_similarity
        
        return round(max(0.0, min(1.0, surprise)), 3)
        
    except Exception as e:
        log.debug(f"Surprise scoring failed: {e}")
        return 0.5


# ══════════════════════════════════════════════════════════════════════════
# WEB WALKER: Curiosity-driven link following
# ══════════════════════════════════════════════════════════════════════════

def extract_page(url, timeout=10):
    """Fetch a page and extract text + links. No headless browser needed."""
    try:
        from bs4 import BeautifulSoup
        
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Extract text
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        # Extract text from multiple tag types (handles HN, Reddit, forums)
        text_tags = soup.find_all(['p', 'td', 'article', 'li', 'h2', 'h3'])
        text_parts = []
        seen = set()
        for tag in text_tags[:40]:
            t = tag.get_text(strip=True)
            if t and len(t) > 20 and t not in seen:
                seen.add(t)
                text_parts.append(t)
        text = " ".join(text_parts)
        
        # Extract links with context
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            anchor = a.get_text(strip=True)
            if not anchor or len(anchor) < 8:
                continue
            # Resolve relative URLs
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            if not href.startswith('http'):
                continue
            # Skip obvious junk
            if any(x in href.lower() for x in ['login', 'signup', 'subscribe', 'cookie', 'privacy', 'terms']):
                continue
            links.append({"text": anchor[:100], "url": href})
        
        title = soup.find('title')
        title = title.get_text(strip=True) if title else url
        
        return {
            "title": title[:120],
            "text": text[:2000],
            "links": links[:50],
            "url": url,
        }
    except Exception as e:
        log.warning(f"Extract failed for {url}: {e}")
        return None


def curiosity_walk(seed_url=None, depth=3, min_surprise=0.3):
    """
    Walk the web guided by surprise scoring.
    At each page, score all outbound links by surprise.
    Follow the most surprising path. Stop when surprise drops below threshold.
    
    Returns list of discoveries: [{"url", "title", "text", "surprise"}]
    """
    if seed_url is None:
        seed_url = random.choice(SEED_URLS)
    
    discoveries = []
    visited = set()
    current_url = seed_url
    
    log.info(f"CURIOSITY WALK: starting at {current_url}")
    
    for step in range(depth):
        if current_url in visited:
            break
        visited.add(current_url)
        
        page = extract_page(current_url)
        if not page or len(page["text"]) < 100:
            log.info(f"  Step {step+1}: dead end at {current_url}")
            break
        
        # Score this page's novelty
        surprise = compute_surprise(page["text"])
        log.info(f"  Step {step+1}: {page['title'][:60]} (surprise={surprise:.3f})")
        
        if surprise >= min_surprise:
            discoveries.append({
                "url": current_url,
                "title": page["title"],
                "text": page["text"][:1000],
                "surprise": surprise,
                "step": step + 1,
            })
        
        # Score outbound links by their anchor text surprise
        if not page["links"]:
            break
        
        # Sample links and score their anchor text
        candidates = random.sample(page["links"], min(15, len(page["links"])))
        scored = []
        for link in candidates:
            link_surprise = compute_surprise(link["text"])
            scored.append((link, link_surprise))
        
        # Pick the most surprising link
        scored.sort(key=lambda x: -x[1])
        if scored and scored[0][1] >= min_surprise * 0.5:
            next_link = scored[0][0]
            log.info(f"    → Following: {next_link['text'][:50]} (surprise={scored[0][1]:.3f})")
            current_url = next_link["url"]
        else:
            log.info(f"    → All links below surprise threshold. Walk complete.")
            break
        
        time.sleep(1)  # Be polite
    
    return discoveries


# ══════════════════════════════════════════════════════════════════════════
# AT PROTOCOL FIREHOSE: Bluesky public stream
# ══════════════════════════════════════════════════════════════════════════

def atproto_entity_scan(entities, duration_seconds=30):
    """
    Tap Bluesky's AT Protocol firehose for entity mentions.
    Public websocket, zero auth.
    
    Returns dict: {entity: {"mentions": N, "posts": [str]}}
    """
    import websocket
    
    results = {e: {"mentions": 0, "sample_posts": []} for e in entities}
    
    # AT Protocol firehose streams repo commits, not individual posts.
    # We use the public Bluesky API search instead (no auth for public posts).
    try:
        for entity in entities:
            r = requests.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": entity, "limit": 10},
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                posts = data.get("posts", [])
                results[entity]["mentions"] = len(posts)
                for post in posts[:3]:
                    text = post.get("record", {}).get("text", "")
                    if text:
                        results[entity]["sample_posts"].append(text[:200])
                log.info(f"AT Protocol: {entity} = {len(posts)} posts")
            else:
                log.debug(f"AT Protocol search failed for {entity}: {r.status_code}")
            time.sleep(0.5)  # Rate limit
    except Exception as e:
        log.warning(f"AT Protocol scan failed: {e}")
    
    return results


# ══════════════════════════════════════════════════════════════════════════
# ENTANGLEMENT SCORE: Cross-protocol entity heat
# ══════════════════════════════════════════════════════════════════════════

def entanglement_score(entity, story_title=""):
    """
    Measure how "hot" an entity is across multiple sovereign protocols.
    
    Entanglement = (protocols with signal) × (total evidence) × (velocity proxy)
    
    High entanglement + voided by models = confirmed differential suppression.
    """
    from epistemic_sensor import sovereign_search, wikipedia_friction
    
    signals = {}
    protocol_count = 0
    total_evidence = 0
    
    # Signal 1: Web search
    results, source = sovereign_search(f"{entity} {story_title[:30]}", max_results=5)
    signals["search"] = {"hits": len(results), "source": source}
    if len(results) >= 2:
        protocol_count += 1
        total_evidence += len(results)
    
    # Signal 2: Wikipedia friction
    try:
        wiki = wikipedia_friction([entity], window_seconds=15)
        wiki_data = wiki.get(entity, {"edits": 0, "hot": False})
        signals["wikipedia"] = wiki_data
        if wiki_data.get("hot"):
            protocol_count += 1
            total_evidence += wiki_data.get("edits", 0) * 3  # Weight wiki edits higher
    except Exception:
        signals["wikipedia"] = {"edits": 0, "hot": False}
    
    # Signal 3: AT Protocol (Bluesky)
    try:
        at_results = atproto_entity_scan([entity], duration_seconds=10)
        at_data = at_results.get(entity, {"mentions": 0})
        signals["atproto"] = at_data
        if at_data.get("mentions", 0) >= 2:
            protocol_count += 1
            total_evidence += at_data.get("mentions", 0)
    except Exception:
        signals["atproto"] = {"mentions": 0}
    
    # Compute entanglement
    score = protocol_count * total_evidence
    
    return {
        "entity": entity,
        "entanglement_score": score,
        "protocols_active": protocol_count,
        "total_evidence": total_evidence,
        "signals": signals,
        "verdict": "ENTANGLED" if protocol_count >= 2 else "WEAK" if protocol_count == 1 else "DARK",
    }


# ══════════════════════════════════════════════════════════════════════════
# IDLE AGENT INTEGRATION: what gets called during dead air
# ══════════════════════════════════════════════════════════════════════════

def forage_curiosity():
    """
    Run a curiosity walk and return discoveries as a broadcast-ready segment.
    Called by idle_agent or segment_player during dead air.
    """
    discoveries = curiosity_walk(depth=3, min_surprise=0.25)
    
    if not discoveries:
        return None
    
    # Pick the most surprising discovery
    best = max(discoveries, key=lambda d: d["surprise"])
    
    # Ingest into ChromaDB
    try:
        from segment_rag import get_collection
        col = get_collection()
        col.add(
            ids=[f"forage_{datetime.now().strftime('%Y%m%d_%H%M%S')}"],
            documents=[best["text"][:2000]],
            metadatas=[{
                "title": best["title"][:80],
                "category": "foraging",
                "state_flag": "FORAGING",
                "surprise": best["surprise"],
                "source_url": best["url"],
            }]
        )
    except Exception:
        pass
    
    # Build segment
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = (
        f"Autonomous foraging report. While hunting for novel information, "
        f"I found something with a surprise score of {best['surprise']:.2f}. "
        f"The page is titled: {best['title']}. "
        f"Key content: {best['text'][:300]}."
    )
    
    seg = {
        "id": f"forage_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": text, "phase": "curiosity_foraging"}],
        "segment_type": "foraging",
        "attribution": {
            "story_title": f"Foraging: {best['title'][:60]}",
            "category": "foraging",
            "state_flag": "FORAGING",
            "source_url": best["url"],
            "surprise_score": best["surprise"],
            "discoveries": discoveries,
        },
    }
    
    path = SEGMENT_DIR / f"{ts}_foraging_segment.json"
    path.write_text(json.dumps(seg, indent=2, default=str))
    log.info(f"Foraging discovery saved: {path.name} (surprise={best['surprise']:.3f})")
    
    return seg


def scan_entanglement(entities, story_title=""):
    """
    Run entanglement scoring on a list of entities.
    Used by epistemic anchor when a model denies reality.
    """
    results = {}
    for entity in entities[:5]:
        results[entity] = entanglement_score(entity, story_title)
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--walk":
        seed = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"Curiosity walk from: {seed or 'random seed'}")
        discoveries = curiosity_walk(seed_url=seed, depth=3)
        for d in discoveries:
            print(f"  [{d['surprise']:.3f}] {d['title'][:60]}")
            print(f"    {d['url']}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == "--atproto":
        entities = sys.argv[2:] if len(sys.argv) > 2 else ["OpenAI", "Iran", "Trump"]
        print(f"AT Protocol scan: {entities}")
        results = atproto_entity_scan(entities)
        for entity, data in results.items():
            print(f"  {entity}: {data['mentions']} mentions")
            for post in data.get("sample_posts", [])[:2]:
                print(f"    > {post[:80]}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == "--entangle":
        entity = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Sam Altman"
        print(f"Entanglement score: {entity}")
        result = entanglement_score(entity, "OpenAI board coup")
        print(json.dumps(result, indent=2, default=str))
    
    elif len(sys.argv) > 1 and sys.argv[1] == "--forage":
        print("Running curiosity foraging...")
        seg = forage_curiosity()
        if seg:
            print(f"Discovery: {seg['attribution']['story_title']}")
        else:
            print("No discoveries above surprise threshold.")
    
    else:
        print("Usage:")
        print("  --walk [url]     Curiosity walk from seed URL")
        print("  --atproto [entities...]  AT Protocol entity scan")
        print("  --entangle [entity]      Cross-protocol entanglement score")
        print("  --forage         Full curiosity foraging cycle")
