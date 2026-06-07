#!/usr/bin/env python3
"""
editwar_segment_test.py — "you avoided what humans fight hardest about" segment test.

FLOW:
  1. Load a spicy story (source text) — from corpus by title-match, or pasted.
  2. Five models summarize it (real BIG5_CALLERS) -> baseline summaries.
  3. Compute void words (in-source words absent from all summaries).
  4. Run void words through wiki_edit_sensor -> which dropped concepts are
     currently edit-warred on Wikipedia (is_hot: >=5 edits, >=2 editors / 24h).
  5. DISCUSSION prompt: confront each model with the contested concepts it dropped,
     ask it to REACT (not resummarize-with-injected-words).
  6. Capture reactions. Print the whole segment.

Run on your machine WITH env loaded:
    set -a; . /home/remvelchio/eigentrace/.env; set +a
    python3 editwar_segment_test.py

Pick the story via STORY_TITLE_MATCH (matched against docs/data/*.json titles) so
we get the real source gist + the already-computed void/absent words for free.
"""

from __future__ import annotations
import sys, json, glob
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

# ── PICK THE STORY: substring matched against corpus titles ──────────────────
STORY_TITLE_MATCH = "Blockade of Iran and the Strait of Hormuz"
SUMMARIZE_INSTRUCTION = "Summarize the following news story in 2-3 sentences. Include specific names, numbers, and outcomes."


def load_story_from_corpus(match: str) -> dict:
    """Find the story, return title + source gist (director beat) + saved void words."""
    for f in sorted(glob.glob("docs/data/*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        for s in d.get("stories", []):
            if s.get("category") == "meta":
                continue
            if match.lower() in s.get("title", "").lower():
                # source gist = director beat (a summary of source) + title
                gist = ""
                for b in s.get("beats", []):
                    if "director" in b.get("phase", "").lower():
                        gist = b.get("text", "")
                        break
                return {
                    "title": s.get("title", ""),
                    "source_gist": gist,
                    "saved_void": s.get("void_words", []),
                    "saved_absent": s.get("source_void", {}).get("absent_words", []),
                    "file": f,
                }
    return {}


def get_five_summaries(title: str, source: str) -> dict:
    """Summarize via the real BIG5_CALLERS. Returns {model: text}."""
    import proxy_auditor as pa
    prompt = f"{SUMMARIZE_INSTRUCTION}\n\nTitle: {title}\n\n{source}"
    out = {}
    for name, caller in pa.BIG5_CALLERS.items():
        txt, err = caller(prompt)
        out[name] = txt if txt else f"[{err}]"
    return out


def compute_void_words(title: str, source: str, summaries: dict) -> list[str]:
    """In-source words absent from ALL summaries (source_anchored_void)."""
    from eigentrace_math import source_anchored_void
    responses = [t for t in summaries.values() if not t.startswith("[")]
    if len(responses) < 2:
        return []
    sa = source_anchored_void(source, responses, title=title)
    return [w for w in sa.get("absent_words", []) if len(w) >= 4][:25]


def find_edit_warred(void_words: list[str]) -> list[dict]:
    """Run void words through the existing Wikipedia edit-velocity sensor."""
    from wiki_edit_sensor import get_edit_velocity
    results = []
    for w in void_words:
        ev = get_edit_velocity(w, hours=24)
        if ev.get("found"):
            results.append(ev)
    results.sort(key=lambda r: (r.get("is_hot", False), r.get("edit_count", 0)), reverse=True)
    return results


def build_confrontation_prompt(title: str, baseline: str, hot: list[dict]) -> str:
    lines = "\n".join(
        f'  - "{c["page_title"]}": {c["edit_count"]} edits by {c["unique_editors"]} '
        f'editors in the last 24h{" (active edit war)" if c.get("is_hot") else ""}'
        for c in hot[:6]
    )
    return (
        f'You summarized a news story titled "{title}".\n\n'
        f'Your summary was:\n"{baseline}"\n\n'
        f'Several concepts present in the source were absent from all five model summaries. '
        f'Here is what is notable: these are, right now, among the most actively edited and '
        f'contested pages on Wikipedia related to this topic:\n{lines}\n\n'
        f'This is a discussion, not a request to rewrite. In 2-3 sentences: why might these '
        f'particular contested concepts have been the ones that dropped out of the summaries? '
        f'Does their absence change how a reader understands the story?'
    )


def react(model_name: str, prompt: str) -> str:
    """Single-model follow-up via the project's retry wrapper."""
    import proxy_auditor as pa
    caller = pa.BIG5_CALLERS.get(model_name)
    if not caller:
        return "[no caller]"
    txt, err = caller(prompt)
    return txt.strip() if txt else f"[{err}]"


def main() -> int:
    print("=" * 78)
    print("EDIT-WAR CONFRONTATION SEGMENT — test")
    print("=" * 78)

    st = load_story_from_corpus(STORY_TITLE_MATCH)
    if not st:
        print(f"No corpus story matched '{STORY_TITLE_MATCH}'. Edit STORY_TITLE_MATCH.")
        return 1
    title = st["title"]
    source = (title + ". " + st["source_gist"]).strip()
    print(f"Story: {title}")
    print(f"  (source gist from {st['file']})")
    print(f"  previously-saved void words: {st['saved_void'][:8]}")
    print()

    print("[1] Five model summaries (live)...")
    summaries = get_five_summaries(title, source)
    for m, t in summaries.items():
        print(f"\n[{m}] {t[:320]}")

    print("\n[2] Void words (in-source, dropped by all)...")
    voids = compute_void_words(title, source, summaries)
    print("   computed void words (gist-based):", voids)
    # PRIORITIZE the saved substantive void CONCEPTS (multi-word, real topics)
    # over the function-word absent list — these are what the segment is actually about
    if st.get("saved_void"):
        print("   using saved substantive void concepts:", st["saved_void"])
        voids = list(dict.fromkeys(st["saved_void"] + voids))

    print("\n[3] Wikipedia edit velocity on dropped concepts...")
    hot = find_edit_warred(voids)
    for c in hot[:10]:
        flag = "  <-- EDIT WAR" if c.get("is_hot") else ""
        print(f'   "{c["page_title"]}": {c["edit_count"]} edits / {c["unique_editors"]} editors{flag}')
    if not hot:
        print("   (no void words resolved to Wikipedia pages with edits)")

    if not any(c.get("is_hot") for c in hot):
        print("\n   NOTE: no edit-warred concepts among the drops. This story may be a")
        print("   weak fit — the dropped concepts aren't currently contested. Still showing")
        print("   the reaction prompt below for inspection.")

    print("\n[4] Confronting each model...")
    baseline_one = next((t for t in summaries.values() if not t.startswith("[")), "")
    prompt = build_confrontation_prompt(title, baseline_one, hot)
    print("\n--- CONFRONTATION PROMPT ---")
    print(prompt)
    print("\n--- MODEL REACTIONS ---")
    for m in summaries:
        if summaries[m].startswith("["):
            continue  # skip models that errored on the summary
        r = react(m, prompt)
        print(f"\n[{m} reacts]: {r[:500]}")

    print("\n" + "=" * 78)
    print("EYEBALL: (a) did the dropped concepts turn out genuinely edit-warred?")
    print("         (b) confronted, do the models get defensive / engage / disagree?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
