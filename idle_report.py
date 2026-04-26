#!/usr/bin/env python3
"""Generate idle_thoughts.json for the website."""
import json, glob, os, re
from datetime import datetime

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"

def generate_report():
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*idle_segment.json")))
    
    thoughts = []
    for f in files:
        try:
            seg = json.load(open(f))
            title = seg.get("attribution", {}).get("story_title", "unknown")
            text = seg["beats"][0]["text"]
            ts = os.path.basename(f)[:15]
            
            # Separate think block from reflection
            think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
            reasoning = think_match.group(1).strip() if think_match else ""
            reflection = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if not reflection:
                reflection = text.replace("<think>", "").replace("</think>", "").strip()
            
            # Clean up
            reflection = re.sub(r"[#*_`]", "", reflection)
            reasoning = re.sub(r"[#*_`]", "", reasoning)
            
            topic = title.replace("Idle reflection: ", "") if "Idle reflection:" in title else title
            
            thoughts.append({
                "timestamp": ts,
                "topic": topic,
                "reflection": reflection[:1000],
                "reasoning": reasoning[:800] if reasoning else None,
                "chars": len(text),
                "has_reasoning": bool(reasoning),
            })
        except:
            continue
    
    report = {
        "generated": datetime.utcnow().isoformat(),
        "total": len(thoughts),
        "with_reasoning": sum(1 for t in thoughts if t["has_reasoning"]),
        "thoughts": thoughts,
    }
    
    out = "/mnt/c/Users/M4ISI/eigentrace/docs/idle_thoughts.json"
    json.dump(report, open(out, "w"), indent=2)
    print(f"Idle thoughts: {len(thoughts)} total, {report['with_reasoning']} with reasoning")

if __name__ == "__main__":
    generate_report()
