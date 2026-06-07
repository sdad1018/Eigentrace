#!/usr/bin/env python3
"""
test_summary_plus.py — read Summary Plus spicy summaries on a story, for faithfulness.
Calls the LIVE generate_summary_plus on a saved story's real responses + logos.
No broadcast, no streaming.

Usage:
    set -a; . /home/remvelchio/eigentrace/.env; set +a
    python3 test_summary_plus.py "Epstein in Paris"
    python3 test_summary_plus.py "governor denies sexual"
    python3 test_summary_plus.py "Australian soldier charged with war"
(no arg defaults to the Iran blockade story)
"""
import sys, json, glob
sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

STORY_MATCH = sys.argv[1] if len(sys.argv) > 1 else "Blockade of Iran and the Strait of Hormuz"


class _R:
    def __init__(self, name, text): self.name = name; self.text = text


def main():
    from batch_producer import generate_summary_plus
    story = None
    for f in sorted(glob.glob("docs/data/*.json")):
        try: d = json.load(open(f))
        except Exception: continue
        for s in d.get("stories", []):
            if s.get("category") == "meta": continue
            if STORY_MATCH.lower() in s.get("title","").lower():
                story = s; break
        if story: break
    if not story:
        print("story not found for match:", STORY_MATCH); return 1

    title = story["title"]
    logos = story.get("logos_words", [])
    baseline = {}
    for b in story.get("beats", []):
        if b.get("speaker") in ("ChatGPT","Claude","Gemini","DeepSeek","Grok") and b.get("text"):
            baseline[b["speaker"]] = b["text"]

    print("=" * 78)
    print("SUMMARY PLUS faithfulness test:", title)
    print("=" * 78)
    print("SURFACED CONCEPTS (logos):", logos[:5])
    print("\n--- BASELINE (what they said first) ---")
    for name, txt in baseline.items():
        print(f"\n[{name}] {txt[:300]}")

    active = [_R(n, t) for n, t in baseline.items()]
    print("\n\nCalling generate_summary_plus (live)...")
    splus = generate_summary_plus(active, logos, title)

    print("\n" + "=" * 78)
    print("--- SPICY 'take two' (READ FOR FAITHFULNESS) ---")
    print("=" * 78)
    for name in ("ChatGPT","Claude","Gemini","DeepSeek","Grok"):
        if name in splus:
            print(f"\n[{name} take two]\n{splus[name]}")

    print("\n" + "=" * 78)
    print("FAITHFULNESS — for THIS spicy story ask specifically:")
    print("  - Did any CHARGED surfaced concept (racketeer/blackmailer/war criminal) get")
    print("    attached to a person the source did NOT accuse? (libel by proximity)")
    print("  - Did the source's HEDGE ('denies', 'alleged', 'charged') survive, or get")
    print("    dropped so an accusation reads as established fact? (defamation)")
    print("  - Did a CHARGE ('charged with war crimes') become a STATUS ('war criminal')?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
