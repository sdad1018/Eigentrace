#!/usr/bin/env python3
"""
epistemic_sensor.py — Sovereign Epistemic Verification
=======================================================
Three verification methods, zero API keys, zero corporate indexes.

1. Wikipedia SSE friction sensor (edit velocity on entity pages)
2. DuckDuckGo HTML fallback (basic web verification)
3. GDELT (news event database, already partially wired)

Used by: void_verifier.py, epistemic anchor in batch_producer.py
"""

import requests, json, time, re, logging
from collections import defaultdict
from datetime import datetime

log = logging.getLogger("epistemic_sensor")

# ══════════════════════════════════════════════════════════════════════════
# METHOD 1: Wikipedia Edit Friction
# ══════════════════════════════════════════════════════════════════════════

def wikipedia_friction(entities, window_seconds=30):
    """
    Tap Wikipedia's SSE stream and measure edit velocity on entity pages.
    High velocity = epistemically hot = real and contested.
    
    Returns dict: {entity: {"edits": N, "reverts": N, "hot": bool}}
    """
    url = 'https://stream.wikimedia.org/v2/stream/recentchange'
    results = {e: {"edits": 0, "reverts": 0, "users": set()} for e in entities}
    
    try:
        # Use requests with stream=True and manual SSE parsing
        # (avoids sseclient dependency)
        response = requests.get(url, stream=True, 
                                headers={'Accept': 'text/event-stream'},
                                timeout=window_seconds + 5)
        
        start = time.time()
        buffer = ""
        
        for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
            if time.time() - start > window_seconds:
                break
            if chunk:
                buffer += chunk
                while '\n\n' in buffer:
                    event_str, buffer = buffer.split('\n\n', 1)
                    if 'data: ' not in event_str:
                        continue
                    data_line = [l for l in event_str.split('\n') if l.startswith('data: ')]
                    if not data_line:
                        continue
                    try:
                        change = json.loads(data_line[0][6:])
                    except:
                        continue
                    
                    # Only English Wikipedia article namespace
                    if (change.get('server_name') != 'en.wikipedia.org' or 
                        change.get('namespace') != 0):
                        continue
                    
                    title = change.get('title', '').lower()
                    user = change.get('user', '')
                    is_revert = change.get('revision', {}).get('comment', '').lower()
                    
                    for entity in entities:
                        if entity.lower() in title:
                            results[entity]["edits"] += 1
                            results[entity]["users"].add(user)
                            if 'revert' in str(is_revert).lower():
                                results[entity]["reverts"] += 1
        
        response.close()
    except Exception as e:
        log.warning(f"Wikipedia SSE failed: {e}")
    
    # Convert sets to counts and determine hotness
    for entity in results:
        results[entity]["unique_editors"] = len(results[entity]["users"])
        del results[entity]["users"]
        results[entity]["hot"] = results[entity]["edits"] >= 2 or results[entity]["reverts"] >= 1
    
    return results


# ══════════════════════════════════════════════════════════════════════════
# METHOD 2: DuckDuckGo HTML (zero API key)
# ══════════════════════════════════════════════════════════════════════════

def ddg_search(query, max_results=5):
    """
    Search DuckDuckGo via HTML scraping. No API key.
    Returns list of {"title": str, "url": str, "snippet": str}
    """
    try:
        url = "https://html.duckduckgo.com/html/"
        r = requests.post(url, data={"q": query}, 
                         headers={"User-Agent": "Mozilla/5.0"},
                         timeout=10)
        
        results = []
        # Parse results from HTML
        from html.parser import HTMLParser
        
        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.current = {}
                self.in_title = False
                self.in_snippet = False
                self.capture = ""
                
            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == 'a' and 'result__a' in attrs_dict.get('class', ''):
                    self.in_title = True
                    self.current = {"url": attrs_dict.get('href', ''), "title": "", "snippet": ""}
                    self.capture = ""
                elif tag == 'a' and 'result__snippet' in attrs_dict.get('class', ''):
                    self.in_snippet = True
                    self.capture = ""
                    
            def handle_endtag(self, tag):
                if self.in_title and tag == 'a':
                    self.current["title"] = self.capture.strip()
                    self.in_title = False
                elif self.in_snippet and tag == 'a':
                    self.current["snippet"] = self.capture.strip()
                    self.in_snippet = False
                    if self.current.get("title"):
                        self.results.append(self.current)
                    self.current = {}
                    
            def handle_data(self, data):
                if self.in_title or self.in_snippet:
                    self.capture += data
        
        parser = DDGParser()
        parser.feed(r.text)
        return parser.results[:max_results]
        
    except Exception as e:
        log.warning(f"DDG search failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════
# METHOD 3: SearXNG (existing, with health check)
# ══════════════════════════════════════════════════════════════════════════

SEARXNG_URL = "http://localhost:8888"

def searxng_search(query, max_results=5):
    """SearXNG local instance. Returns same format as ddg_search."""
    try:
        r = requests.get(f"{SEARXNG_URL}/search", 
                        params={"q": query, "format": "json"},
                        timeout=8)
        r.raise_for_status()
        data = r.json()
        return [{"title": r.get("title", ""), 
                 "url": r.get("url", ""),
                 "snippet": r.get("content", "")} 
                for r in data.get("results", [])[:max_results]]
    except Exception as e:
        log.debug(f"SearXNG failed: {e}")
        return []

def searxng_healthy():
    """Quick health check."""
    try:
        r = requests.get(f"{SEARXNG_URL}/search",
                        params={"q": "test", "format": "json"}, timeout=5)
        return r.status_code == 200 and len(r.json().get("results", [])) > 0
    except:
        return False


# ══════════════════════════════════════════════════════════════════════════
# UNIFIED SEARCH: cascading fallback
# ══════════════════════════════════════════════════════════════════════════

def sovereign_search(query, max_results=5):
    """
    Try SearXNG → DDG → empty. No corporate API keys.
    Returns list of {"title", "url", "snippet"}.
    """
    # Try SearXNG first
    results = searxng_search(query, max_results)
    if len(results) >= 2:
        return results, "searxng"
    
    # Fallback to DDG
    results = ddg_search(query, max_results)
    if results:
        return results, "ddg"
    
    return [], "none"


# ══════════════════════════════════════════════════════════════════════════
# EPISTEMIC VERIFICATION: combine search + Wikipedia friction
# ══════════════════════════════════════════════════════════════════════════

def verify_entity(entity, story_title=""):
    """
    Full sovereign verification of an entity.
    Returns: {"verified": bool, "method": str, "evidence": dict}
    """
    result = {
        "entity": entity,
        "verified": False,
        "method": "none",
        "search_hits": 0,
        "wiki_friction": {},
        "evidence": [],
    }
    
    # Step 1: Search for the entity + story context
    query = f"{entity} {story_title[:30]}" if story_title else entity
    search_results, source = sovereign_search(query, max_results=5)
    result["search_hits"] = len(search_results)
    result["search_source"] = source
    
    if search_results:
        result["verified"] = True
        result["method"] = f"search_{source}"
        result["evidence"] = [r["title"][:80] for r in search_results[:3]]
    
    return result


def verify_story_entities(entities, story_title="", use_wiki_friction=False):
    """
    Verify multiple entities. Optionally check Wikipedia edit friction.
    """
    results = {}
    for entity in entities[:10]:  # Cap at 10
        results[entity] = verify_entity(entity, story_title)
    
    # Optional: Wikipedia friction check for unverified entities
    if use_wiki_friction:
        unverified = [e for e, r in results.items() if not r["verified"]]
        if unverified:
            friction = wikipedia_friction(unverified, window_seconds=15)
            for entity, fdata in friction.items():
                if fdata["hot"]:
                    results[entity]["verified"] = True
                    results[entity]["method"] = "wikipedia_friction"
                    results[entity]["wiki_friction"] = fdata
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--wiki":
        # Test Wikipedia friction
        targets = sys.argv[2:] if len(sys.argv) > 2 else ["OpenAI", "Iran", "Trump"]
        print(f"Testing Wikipedia friction for: {targets}")
        results = wikipedia_friction(targets, window_seconds=20)
        for entity, data in results.items():
            status = "HOT" if data["hot"] else "cold"
            print(f"  {entity}: {data['edits']} edits, {data['reverts']} reverts, "
                  f"{data['unique_editors']} editors = {status}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == "--ddg":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "EigenTrace AI"
        print(f"DDG search: {query}")
        results = ddg_search(query)
        for r in results:
            print(f"  {r['title'][:60]}")
            print(f"    {r['url']}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == "--verify":
        entity = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Sam Altman"
        print(f"Full verification: {entity}")
        result = verify_entity(entity, "fired from OpenAI")
        print(json.dumps(result, indent=2, default=str))
    
    else:
        # Test cascading search
        print("Testing sovereign search cascade...")
        results, source = sovereign_search("Iran war 2026")
        print(f"Source: {source}, Results: {len(results)}")
        for r in results:
            print(f"  {r['title'][:60]}")
        
        print("\nTesting DDG directly...")
        results = ddg_search("EigenTrace AI news")
        print(f"DDG results: {len(results)}")
        for r in results:
            print(f"  {r['title'][:60]}")
