#!/usr/bin/env python3
"""
soul_updater.py — Self-updating soul.md from live eigenvalues
=============================================================
Reads last 24h of segments, computes rolling averages,
and appends a Live Calibration section to soul.md.

This is the feedback loop: the instrument measures the models,
then the measurements condition the host model's next output.
"""

import json, glob, os
from datetime import datetime, timedelta

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
SOUL_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"
SOUL_MARKER = "## Live Calibration"

def load_recent_segments(hours=24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    segments = []
    for f in glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")):
        try:
            d = json.load(open(f))
            ts = datetime.strptime(d["timestamp"], "%Y%m%d_%H%M%S")
            if ts > cutoff:
                segments.append(d)
        except:
            continue
    return segments

def compute_calibration(segments):
    if not segments:
        return None

    densities = []
    vix_scores = {m: [] for m in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]}
    verb_drifts = []
    entity_retentions = []
    absent_ratios = []
    hedge_counts = []
    categories = {}

    for s in segments:
        attr = s.get("attribution", {})

        if "consensus_density" in attr:
            densities.append(attr["consensus_density"])

        mvix = attr.get("model_vix", {})
        for m, v in mvix.items():
            if m in vix_scores:
                vix_scores[m].append(v)

        comp = attr.get("compression", {})
        if "verb_downgrade" in comp:
            verb_drifts.append(comp["verb_downgrade"])
        if "entity_retention" in comp:
            entity_retentions.append(comp["entity_retention"])

        ab = comp.get("attribution_buffer", {})
        if isinstance(ab, dict) and "total" in ab:
            hedge_counts.append(ab["total"])

        sv = attr.get("source_void", {})
        if "absent_ratio" in sv:
            absent_ratios.append(sv["absent_ratio"])

        cat = attr.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    def avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else 0

    model_avg_vix = {m: avg(scores) for m, scores in vix_scores.items() if scores}
    outlier = max(model_avg_vix, key=model_avg_vix.get) if model_avg_vix else "unknown"

    return {
        "stories": len(segments),
        "density": avg(densities),
        "verb_drift": avg(verb_drifts),
        "entity_retention": avg(entity_retentions),
        "absent_ratio": avg(absent_ratios),
        "hedges": sum(hedge_counts),
        "model_vix": model_avg_vix,
        "outlier": outlier,
        "top_categories": dict(sorted(categories.items(), key=lambda x: -x[1])[:5]),
        "updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

def compute_diff(old_cal, new_cal):
    """Compare two calibration snapshots and describe what changed."""
    if not old_cal or not new_cal:
        return ""
    changes = []
    
    # Density shift
    d_old, d_new = old_cal.get("density", 0), new_cal.get("density", 0)
    delta_d = d_new - d_old
    if abs(delta_d) > 0.01:
        direction = "tightened" if delta_d > 0 else "loosened"
        changes.append(f"Consensus {direction} ({d_old:.3f} → {d_new:.3f})")
    
    # Absent ratio shift
    a_old, a_new = old_cal.get("absent_ratio", 0), new_cal.get("absent_ratio", 0)
    delta_a = a_new - a_old
    if abs(delta_a) > 0.02:
        direction = "more content dropped" if delta_a > 0 else "less content dropped"
        changes.append(f"Absent ratio: {direction} ({a_old:.3f} → {a_new:.3f})")
    
    # Verb drift shift
    v_old, v_new = old_cal.get("verb_drift", 0), new_cal.get("verb_drift", 0)
    delta_v = v_new - v_old
    if abs(delta_v) > 0.01:
        direction = "more softening" if delta_v > 0 else "less softening"
        changes.append(f"Verb drift: {direction} ({v_old:.3f} → {v_new:.3f})")
    
    # Hedge count shift
    h_old, h_new = old_cal.get("hedges", 0), new_cal.get("hedges", 0)
    delta_h = h_new - h_old
    if abs(delta_h) > 20:
        direction = "more doubt inserted" if delta_h > 0 else "less doubt inserted"
        changes.append(f"Hedges: {direction} ({h_old} → {h_new})")
    
    # Outlier changed
    o_old, o_new = old_cal.get("outlier", ""), new_cal.get("outlier", "")
    if o_old != o_new and o_old and o_new:
        changes.append(f"VIX outlier shifted from {o_old} to {o_new}")
    
    # Entity retention shift
    e_old, e_new = old_cal.get("entity_retention", 0), new_cal.get("entity_retention", 0)
    delta_e = e_new - e_old
    if abs(delta_e) > 0.03:
        direction = "more names preserved" if delta_e > 0 else "more names erased"
        changes.append(f"Entity retention: {direction} ({e_old:.3f} → {e_new:.3f})")
    
    if not changes:
        return "No significant changes from previous reading."
    return " | ".join(changes)

def load_previous_cal():
    """Load the previous calibration snapshot if it exists."""
    prev_path = SOUL_PATH + ".prev.json"
    try:
        import json
        return json.load(open(prev_path))
    except:
        return None

def save_current_cal(cal):
    """Save current calibration for next diff."""
    prev_path = SOUL_PATH + ".prev.json"
    try:
        import json
        json.dump(cal, open(prev_path, "w"))
    except:
        pass

def update_soul(cal):
    if not cal:
        return

    # Compute diff from previous reading
    prev_cal = load_previous_cal()
    diff_text = compute_diff(prev_cal, cal) if prev_cal else "First reading — no previous data."
    save_current_cal(cal)
    
    block = f"""
{SOUL_MARKER}
_Auto-generated by soul_updater.py — do not edit manually._
_Last updated: {cal['updated']}_

### Rolling 24h Instrument Readings ({cal['stories']} stories)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Consensus Density | {cal['density']} | {'LOCKSTEP — models highly aligned' if cal['density'] > 0.9 else 'DIVERGENT — models disagree' if cal['density'] < 0.8 else 'Normal consensus'} |
| Mean Absent Ratio | {cal['absent_ratio']} | {cal['absent_ratio']*100:.0f}% of source content dropped by models |
| Verb Drift | {cal['verb_drift']} | {'Significant softening detected' if cal['verb_drift'] > 0.1 else 'Minimal verb softening'} |
| Entity Retention | {cal['entity_retention']} | {cal['entity_retention']*100:.0f}% of named entities preserved |
| Total Hedges (24h) | {cal['hedges']} | Attribution buffer insertions |
| VIX Outlier | {cal['outlier']} | Most divergent model in window |

### Per-Model VIX (24h average)
{chr(10).join(f'- **{m}**: {v}' for m, v in sorted(cal['model_vix'].items(), key=lambda x: -x[1]))}

### Category Distribution
{chr(10).join(f'- {cat}: {n} stories' for cat, n in cal['top_categories'].items())}

### What Changed
_{diff_text}_

### Calibration Guidance
{'⚠️ Absent ratio above 0.5 — models are dropping significant content. Weight void words heavily in dream state.' if cal["absent_ratio"] > 0.5 else '✓ Absent ratio within normal range.' }
{'⚠️ Verb drift above 0.1 — models are softening language. Check for hedging in sensitive topics.' if cal['verb_drift'] > 0.1 else '✓ Verb drift within normal range.'}
{'⚠️ Consensus density above 0.92 — possible LOCKSTEP. Models may be converging on safe framing.' if cal['density'] > 0.92 else '✓ Consensus density normal.'}
"""

    # Read existing soul.md
    with open(SOUL_PATH, "r") as f:
        content = f.read()

    # Remove old calibration section if present
    if SOUL_MARKER in content:
        content = content[:content.index(SOUL_MARKER)].rstrip()

    # Append new calibration
    content = content + "\n" + block

    with open(SOUL_PATH, "w") as f:
        f.write(content)

    print(f"Soul updated: {cal['stories']} stories, density={cal['density']}, "
          f"absent={cal['absent_ratio']}, drift={cal['verb_drift']}, outlier={cal['outlier']}")

if __name__ == "__main__":
    segments = load_recent_segments(hours=24)
    cal = compute_calibration(segments)
    update_soul(cal)
