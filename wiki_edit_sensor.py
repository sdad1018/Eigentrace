"""
Wikipedia Edit Velocity Sensor
Zero auth, public API, 50 lines.

When models deny or void an entity, check if that entity's Wikipedia page
has abnormal edit velocity. Edit wars = epistemically hot = the story is
real AND contested.

Used by: epistemic_anchor, void_verifier (as verification method)
"""

import requests
import logging
from datetime import datetime, timedelta

log = logging.getLogger("wiki_edit_sensor")

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "EigenTrace/1.0 (eigentrace.ai; research project)"} 


def get_edit_velocity(entity, hours=24):
    """
    Count edits to a Wikipedia page in the last N hours.
    Returns dict with edit_count, editors, velocity_per_hour, is_hot.
    """
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # First: resolve the entity to a Wikipedia page title
        r = requests.get(WIKI_API, headers=HEADERS, params={
            "action": "query",
            "list": "search",
            "srsearch": entity,
            "srlimit": 1,
            "format": "json",
        }, timeout=10)
        search = r.json().get("query", {}).get("search", [])
        if not search:
            return {"entity": entity, "found": False, "edit_count": 0}

        page_title = search[0]["title"]
        page_id = search[0]["pageid"]

        # Get recent revisions
        r = requests.get(WIKI_API, headers=HEADERS, params={
            "action": "query",
            "prop": "revisions",
            "titles": page_title,
            "rvprop": "timestamp|user",
            "rvlimit": 50,
            "rvstart": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rvend": cutoff,
            "format": "json",
        }, timeout=10)

        pages = r.json().get("query", {}).get("pages", {})
        revisions = []
        for pid, pdata in pages.items():
            revisions = pdata.get("revisions", [])

        unique_editors = set(rev.get("user", "") for rev in revisions)
        edit_count = len(revisions)
        velocity = edit_count / max(hours, 1)

        # Hot threshold: >5 edits/24h with >2 editors = edit war territory
        is_hot = edit_count >= 5 and len(unique_editors) >= 2

        return {
            "entity": entity,
            "found": True,
            "page_title": page_title,
            "edit_count": edit_count,
            "unique_editors": len(unique_editors),
            "velocity_per_hour": round(velocity, 2),
            "is_hot": is_hot,
            "hours_checked": hours,
        }

    except Exception as e:
        log.warning(f"Wiki edit sensor failed for '{entity}': {e}")
        return {"entity": entity, "found": False, "edit_count": 0, "error": str(e)}


def check_void_entities(void_words, hours=24):
    """
    Check edit velocity for void words that look like entities.
    Returns list of hot entities.
    """
    hot = []
    for w in void_words[:8]:
        word = w if isinstance(w, str) else w.get("word", "")
        if not word or len(word) < 3:
            continue
        # Only check words that look like entities (capitalized or known names)
        if word[0].isupper() or word.lower() in _KNOWN_GEO_ENTITIES:
            result = get_edit_velocity(word, hours)
            if result.get("is_hot"):
                hot.append(result)
                log.info(f"  Wiki HOT: {word} — {result['edit_count']} edits by "
                         f"{result['unique_editors']} editors in {hours}h")
    return hot


def format_broadcast(hot_entities):
    """Format for broadcast beat."""
    if not hot_entities:
        return ""
    parts = []
    for h in hot_entities[:3]:
        parts.append(
            f"Wikipedia's page for '{h['page_title']}' received "
            f"{h['edit_count']} edits from {h['unique_editors']} editors "
            f"in the last {h['hours_checked']} hours"
        )
    text = (
        "Wikipedia edit velocity check. " + ". ".join(parts) + ". "
        "High edit velocity on voided entities confirms these concepts are "
        "actively contested in the public record — the models voided words "
        "the internet is fighting over."
    )
    return text


# Common geopolitical entities to always check even if lowercase
_KNOWN_GEO_ENTITIES = {
    "hezbollah", "hamas", "iran", "ukraine", "russia", "taiwan",
    "nato", "irgc", "zelensky", "zelenskyy", "putin", "trump",
    "netanyahu", "rouhani", "khamenei", "crimea", "hormuz",
}


if __name__ == "__main__":
    # Test
    print("Testing wiki edit sensor...")
    for entity in ["Hezbollah", "Ukraine", "OpenAI"]:
        r = get_edit_velocity(entity, hours=48)
        hot = "🔥 HOT" if r.get("is_hot") else "  cool"
        print(f"  {hot} {entity}: {r.get('edit_count', 0)} edits, "
              f"{r.get('unique_editors', 0)} editors, "
              f"{r.get('velocity_per_hour', 0):.1f}/hr")
