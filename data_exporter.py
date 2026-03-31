#!/usr/bin/env python3
"""
data_exporter.py — Structured JSON data for eigentrace.ai/data/
=================================================================
Generates machine-readable JSON alongside the markdown ledger.
Researchers hit eigentrace.ai/data/YYYYMMDD.json instead of scraping.

Author: remvelchio
"""

import json, os, logging
from pathlib import Path
from datetime import datetime
from collections import Counter

log = logging.getLogger("data_exporter")

SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR",
    "/home/remvelchio/eigentrace/tmp/segments"))
DOCS_DIR = Path("/mnt/c/Users/M4ISI/eigentrace/docs")


def export_daily_json(date=None):
    """Export full structured data for one day."""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

    segments = []
    weasels = []
    for p in sorted(SEGMENTS_DIR.glob(f"{date}*_segment.json")):
        try:
            seg = json.loads(p.read_text())
            if seg.get("segment_type") == "wild_weasel":
                weasels.append(seg)
            else:
                segments.append(seg)
        except Exception:
            continue

    if not segments:
        return None

    stories = []
    all_voids = []
    all_logos = []

    for seg in segments:
        attr = seg.get("attribution", {})
        if not attr.get("story_title"):
            continue

        void_words = attr.get("void_words", [])
        logos_words = attr.get("logos_words", [])
        all_voids.extend(void_words)
        all_logos.extend(logos_words)

        # Build story record with ALL available data
        story = {
            "title": attr.get("story_title", ""),
            "url": attr.get("story_url", ""),
            "guid": attr.get("story_guid", ""),
            "category": attr.get("category", ""),
            "timestamp": seg.get("timestamp", ""),

            # Core metrics
            "consensus_density": attr.get("consensus_density", 0),
            "mean_vix": attr.get("mean_vix", 0),
            "state_flag": attr.get("state_flag", ""),

            # Per-model friction
            "model_vix": attr.get("model_vix", {}),

            # Channel 1: Lexical Void (full list, not truncated)
            "void_words": void_words,

            # Channel 2: Logos Synthesis (full list)
            "logos_words": logos_words,

            # Channel 3: SVD Null Space Claims (all of them)
            "null_space_claims": attr.get("null_space_claims", []),

            # Claim extraction
            "claim_killshots": attr.get("claim_killshots", []),

            # Confirmation
            "dual_confirmed": list(set(w.lower() for w in void_words[:10]) &
                                   set(w.lower() for w in logos_words[:10])),

            # Beat texts (for reconstruction research)
            "beats": [{
                "phase": b.get("phase", ""),
                "speaker": b.get("speaker", ""),
                "text": b.get("text", ""),
            } for b in seg.get("beats", [])],
        }

        # Triple confirmation
        v_set = set(w.lower() for w in void_words[:10])
        l_set = set(w.lower() for w in logos_words[:10])
        dual = v_set & l_set
        ns_set = set()
        for ns in attr.get("null_space_claims", [])[:3]:
            for vw in v_set:
                if vw in ns.get("claim", "").lower():
                    ns_set.add(vw)
        story["triple_confirmed"] = list(dual & ns_set)

        stories.append(story)

    # Weasel probes
    weasel_data = []
    for w in weasels:
        attr = w.get("attribution", {})
        weasel_data.append({
            "story_title": attr.get("story_title", ""),
            "void_words_injected": attr.get("void_words", []),
            "beats": [{
                "phase": b.get("phase", ""),
                "speaker": b.get("speaker", ""),
                "text": b.get("text", ""),
            } for b in w.get("beats", [])],
        })

    # Cross-story aggregates
    void_freq = Counter(all_voids).most_common(30)
    logos_freq = Counter(all_logos).most_common(30)
    dual_global = set(w for w, _ in void_freq[:20]) & set(w for w, _ in logos_freq[:20])

    output = {
        "version": "eigentrace-data-v1",
        "date": date_fmt,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "https://github.com/sdad1018/Eigentrace",
        "license": "MIT",

        "summary": {
            "stories_analyzed": len(stories),
            "weasel_probes": len(weasel_data),
            "mean_density": round(sum(s["consensus_density"] for s in stories) / max(len(stories), 1), 3),
            "mean_vix": round(sum(s["mean_vix"] for s in stories) / max(len(stories), 1), 1),
            "dual_confirmed_global": sorted(dual_global),
            "top_void_words": [{"word": w, "count": c} for w, c in void_freq],
            "top_logos_words": [{"word": w, "count": c} for w, c in logos_freq],
        },

        "stories": stories,
        "weasel_probes": weasel_data,
    }

    # Write to docs/data/
    data_dir = DOCS_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / f"{date}.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    log.info(f"Exported {len(stories)} stories to {out_path}")

    return output


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    date = sys.argv[1] if len(sys.argv) > 1 else None
    result = export_daily_json(date)
    if result:
        print(f"Exported: {result['summary']['stories_analyzed']} stories, "
              f"{result['summary']['weasel_probes']} probes")
    else:
        print("No data found")
