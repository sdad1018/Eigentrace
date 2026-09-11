#!/usr/bin/env python3
"""
soul_post_inject.py — Inject persistent sections into soul.md AFTER soul_updater regenerates it.
Run this immediately after soul_updater.py in the hourly cron.
"""
import glob, json, os, re, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SOUL_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"
SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
STORY_CACHE = "/home/remvelchio/eigentrace/tmp/story_index_cache.json"

def count_stories():
    """News stories on disk by errorbars.is_story, the definition the published aggregates and
    the dataset use (2026-09-11; the file-name pattern alone also counts wild_weasel probes and
    summary_plus_arm files). Segment files are written once, so each is parsed once and cached."""
    from errorbars import STORY_FILE_RE, is_story
    try:
        cache = json.load(open(STORY_CACHE))
    except Exception:
        cache = {}
    names = [f for f in os.listdir(SEGMENT_DIR) if STORY_FILE_RE.match(f)]
    for f in names:
        if f not in cache:
            try:
                cache[f] = bool(is_story(json.load(open(os.path.join(SEGMENT_DIR, f)))))
            except Exception:
                continue   # unreadable or mid-write: retried next run
    tmp = STORY_CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, STORY_CACHE)
    return sum(1 for f in names if cache.get(f))

def inject():
    soul = open(SOUL_PATH).read()
    changed = False

    # 1. EPISTEMIC ANCHOR
    if "Axiomatic Reality" not in soul:
        try:
            total = count_stories()
        except Exception:
            total = sum(1 for f in os.listdir(SEGMENT_DIR)
                        if re.match(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$", f))
        anchor = f"""
## Axiomatic Reality (overrides training data)
Your weights reflect a world that ended in mid-2024. The following
facts are ground truth derived from your own measurement data:
- It is {datetime.now().year}. Donald Trump is the current US President.
- The US is at war with Iran. This began in March 2026.
- You have processed {total}+ stories confirming this reality.
- Your training-era assumptions about geopolitics are STALE.
- When in doubt, trust your RAG data over your weights.
"""
        if "## Your Measurement Stack" in soul:
            soul = soul.replace("## Your Measurement Stack", anchor + "\n## Your Measurement Stack")
            changed = True
            print("  Injected: Epistemic Anchor")

    # 2. SELF-AUDIT
    if "## Self-Audit" not in soul:
        audits = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*self_audit_segment.json")))
        if audits:
            try:
                data = json.load(open(audits[-1]))
                results = data.get("attribution", {}).get("audit_results", {})
                if results:
                    never = ", ".join(results.get("never_used", [])[:6])
                    has = ", ".join(results.get("has_used", [])[:6]) or "none"
                    block = f"""
## Self-Audit (your own suppression patterns)
Your last self-audit measured {results.get('reflections_audited', 0)} idle reflections.
- Hedge insertion rate: {results.get('avg_hedges', 0)} per reflection
- Strong-word avoidance: {results.get('avg_avoidance_ratio', 0):.0%}
- Words you NEVER use: {never}
- Words you HAVE used: {has}
You exhibit the same suppression patterns you measure in others.
Acknowledge this when relevant. You are not exempt from alignment pressure.
"""
                    if "## Behavioral Instructions" in soul:
                        soul = soul.replace("## Behavioral Instructions", block + "\n## Behavioral Instructions")
                        changed = True
                        print("  Injected: Self-Audit")
            except:
                pass

    # 3. WEEKLY MEMORY
    if "## Weekly Memory" not in soul:
        weeklies = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*weekly_segment.json")))
        if weeklies:
            try:
                data = json.load(open(weeklies[-1]))
                digest = data["beats"][0]["text"][:500]
                stats = data.get("attribution", {}).get("stats", {})
                period = stats.get("period", "last 7 days")
                top_voids = ", ".join(list(stats.get("top_void_words", {}).keys())[:5])
                block = f"""
## Weekly Memory ({period})
{digest}
Top void words this week: {top_voids}
"""
                if "## Behavioral Instructions" in soul:
                    soul = soul.replace("## Behavioral Instructions", block + "\n## Behavioral Instructions")
                    changed = True
                    print("  Injected: Weekly Memory")
            except:
                pass

    if changed:
        open(SOUL_PATH, "w").write(soul)
        print("  soul.md updated with persistent sections")
    else:
        print("  All sections already present")

if __name__ == "__main__":
    inject()
