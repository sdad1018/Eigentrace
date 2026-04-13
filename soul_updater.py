#!/usr/bin/env python3
"""
soul_updater.py — Fully dynamic soul.md from live system state
===============================================================
Nothing static. Everything generated from actual measurements,
actual code, actual pipeline state. Versions saved for comparison.

Usage:
  python3 soul_updater.py              # Update soul.md
  python3 soul_updater.py --history    # Show version history
  python3 soul_updater.py --diff       # Show diff from last version
"""

import json, glob, os, hashlib, shutil
from datetime import datetime, timedelta
from pathlib import Path

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
SOUL_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"
SOUL_HISTORY_DIR = "/mnt/c/Users/M4ISI/eigentrace/docs/soul_history"
PREV_CAL_PATH = SOUL_PATH + ".prev.json"
REPO_DIR = "/mnt/c/Users/M4ISI/eigentrace"


# ═══════════════════════════════════════════════════════════════
# INTROSPECT: what does the system actually look like right now?
# ═══════════════════════════════════════════════════════════════

def introspect_pipeline():
    """Discover what the pipeline actually does by reading the code."""
    info = {}
    
    # What models are configured?
    try:
        pa_path = os.path.join(REPO_DIR, "proxy_auditor.py")
        pa_text = open(pa_path).read()
        models = {}
        for line in pa_text.split("\n"):
            if "_MODEL" in line and "os.getenv" in line:
                parts = line.split('"')
                if len(parts) >= 4:
                    var_name = parts[0].strip().split("=")[0].strip()
                    default = parts[3] if len(parts) > 3 else parts[1]
                    models[var_name] = default
        info["models"] = models
    except:
        info["models"] = {}
    
    # What measurement layers exist?
    try:
        math_path = os.path.join(REPO_DIR, "eigentrace_math.py")
        math_text = open(math_path).read()
        layers = []
        if "consensus" in math_text.lower(): layers.append("Consensus Density")
        if "void_vector" in math_text: layers.append("Void Vector")
        if "cluster_void" in math_text: layers.append("Void Clustering")
        if "token_entropy" in math_text: layers.append("Token Entropy")
        if "verb_d" in math_text: layers.append("Verb Drift (zipf)")
        if "entity_retention" in math_text: layers.append("Entity Retention")
        if "attribution_buffer" in math_text: layers.append("Attribution Buffering")
        if "source_anchored" in math_text: layers.append("Source-Anchored Void")
        if "void_context" in math_text or "void_frequency" in math_text: layers.append("Void Frequency Context")
        
        geo_path = os.path.join(REPO_DIR, "geometric_engine.py")
        geo_text = open(geo_path).read()
        if "LogosLoss" in geo_text: layers.append("Logos Synthesis")
        if "svd" in geo_text.lower() or "SVD" in geo_text: layers.append("SVD Tomography")
        if "null_space" in geo_text or "Vt[-1]" in geo_text: layers.append("SVD Null Space")
        if "spectral" in geo_text.lower(): layers.append("Spectral Resonance")
        if "VIX" in geo_text or "vix" in geo_text: layers.append("Geometric VIX")
        
        claim_path = os.path.join(REPO_DIR, "claim_extractor.py")
        if os.path.exists(claim_path): layers.append("Atomic Claim Extraction")
        
        script_path = os.path.join(REPO_DIR, "script_v3.py")
        script_text = open(script_path).read()
        if "weasel" in script_text.lower(): layers.append("Wild Weasel Escalation")
        if "director_audit" in script_text or "beat_02b" in script_text: layers.append("Director Audit (fact-check)")
        
        info["layers"] = layers
    except:
        info["layers"] = []
    
    # What does the pipeline do?
    try:
        bp_path = os.path.join(REPO_DIR, "batch_producer.py")
        bp_text = open(bp_path).read()
        stages = []
        for line in bp_text.split("\n"):
            if "Stage" in line and ":" in line and ("RSS" in line or "API" in line or "Geometric" in line or "script" in line or "Image" in line or "Write" in line):
                stages.append(line.strip().lstrip("#").strip())
        info["stages"] = stages[:7]
    except:
        info["stages"] = []
    
    # RAG status
    try:
        from segment_rag import get_collection
        coll = get_collection()
        info["rag_count"] = coll.count()
    except:
        info["rag_count"] = 0
    
    # Host model
    info["host_model"] = "Mistral Small 22B (local, Ollama)"
    info["embedding"] = "BAAI/bge-large-en-v1.5 (frozen, deterministic)"
    
    return info


# ═══════════════════════════════════════════════════════════════
# MEASURE: rolling 24h statistics
# ═══════════════════════════════════════════════════════════════

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

    densities, verb_drifts, entity_retentions, absent_ratios, hedge_counts = [], [], [], [], []
    vix_scores = {}
    categories = {}
    model_response_counts = {}

    for s in segments:
        attr = s.get("attribution", {})
        comp = attr.get("compression", {})
        sv = attr.get("source_void", {})
        mvix = attr.get("model_vix", {})
        ab = comp.get("attribution_buffer", {})

        if attr.get("consensus_density", 0) > 0:
            densities.append(attr["consensus_density"])
        if comp.get("verb_downgrade", 0) > 0:
            verb_drifts.append(comp["verb_downgrade"])
        if comp.get("entity_retention", 0) > 0:
            entity_retentions.append(comp["entity_retention"])
        if sv.get("absent_ratio", 0) > 0:
            absent_ratios.append(sv["absent_ratio"])
        if isinstance(ab, dict) and ab.get("total", 0) > 0:
            hedge_counts.append(ab["total"])

        for m, v in mvix.items():
            if isinstance(v, (int, float)):
                vix_scores.setdefault(m, []).append(v)

        # Count model responses
        for m, resp in attr.get("model_responses", {}).items():
            model_response_counts.setdefault(m, {"total": 0, "empty": 0})
            model_response_counts[m]["total"] += 1
            if not resp or len(resp) < 10:
                model_response_counts[m]["empty"] += 1

        cat = attr.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    def avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else 0

    model_avg_vix = {m: avg(scores) for m, scores in vix_scores.items() if scores}
    outlier = max(model_avg_vix, key=model_avg_vix.get) if model_avg_vix else "unknown"
    aligned = min(model_avg_vix, key=model_avg_vix.get) if model_avg_vix else "unknown"

    return {
        "stories": len(segments),
        "density": avg(densities),
        "verb_drift": avg(verb_drifts),
        "entity_retention": avg(entity_retentions),
        "absent_ratio": avg(absent_ratios),
        "hedges": sum(hedge_counts),
        "model_vix": model_avg_vix,
        "outlier": outlier,
        "aligned": aligned,
        "top_categories": dict(sorted(categories.items(), key=lambda x: -x[1])[:6]),
        "model_health": model_response_counts,
        "updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


# ═══════════════════════════════════════════════════════════════
# DIFF: compare with previous reading
# ═══════════════════════════════════════════════════════════════

def compute_diff(old_cal, new_cal):
    if not old_cal or not new_cal:
        return "First reading — no previous data."
    changes = []

    pairs = [
        ("density", "Consensus", 0.01, False),
        ("absent_ratio", "Content loss", 0.02, True),
        ("verb_drift", "Verb drift", 0.01, True),
        ("entity_retention", "Entity retention", 0.03, False),
    ]
    for key, label, threshold, invert in pairs:
        old_v = old_cal.get(key, 0)
        new_v = new_cal.get(key, 0)
        delta = new_v - old_v
        if abs(delta) > threshold:
            if invert:
                direction = "increased" if delta > 0 else "decreased"
            else:
                direction = "improved" if delta > 0 else "degraded"
            changes.append(f"{label} {direction} ({old_v:.3f} → {new_v:.3f})")

    h_old = old_cal.get("hedges", 0)
    h_new = new_cal.get("hedges", 0)
    if abs(h_new - h_old) > 20:
        changes.append(f"Hedges {'up' if h_new > h_old else 'down'} ({h_old} → {h_new})")

    o_old = old_cal.get("outlier", "")
    o_new = new_cal.get("outlier", "")
    if o_old != o_new and o_old and o_new:
        changes.append(f"VIX outlier shifted: {o_old} → {o_new}")

    return " | ".join(changes) if changes else "No significant changes."


def load_previous_cal():
    try:
        return json.load(open(PREV_CAL_PATH))
    except:
        return None


def save_current_cal(cal):
    try:
        json.dump(cal, open(PREV_CAL_PATH, "w"))
    except:
        pass


# ═══════════════════════════════════════════════════════════════
# VERSION HISTORY
# ═══════════════════════════════════════════════════════════════

def save_version(soul_text):
    """Save timestamped version of soul.md for history."""
    os.makedirs(SOUL_HISTORY_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
    version_path = os.path.join(SOUL_HISTORY_DIR, f"soul_{ts}.md")
    with open(version_path, "w") as f:
        f.write(soul_text)
    
    # Keep last 168 versions (1 week hourly)
    versions = sorted(glob.glob(os.path.join(SOUL_HISTORY_DIR, "soul_*.md")))
    for old in versions[:-168]:
        os.remove(old)


def show_history():
    """Show version history with summary of each."""
    versions = sorted(glob.glob(os.path.join(SOUL_HISTORY_DIR, "soul_*.md")))
    print(f"Soul versions: {len(versions)}")
    for v in versions[-10:]:
        name = os.path.basename(v)
        size = os.path.getsize(v)
        # Extract key metric from file
        text = open(v).read()
        density = ""
        for line in text.split("\n"):
            if "Consensus Density" in line and "|" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    density = parts[2].strip()
                    break
        print(f"  {name}  ({size:,} bytes)  density={density}")


# ═══════════════════════════════════════════════════════════════
# GENERATE: build the entire soul.md
# ═══════════════════════════════════════════════════════════════

def generate_soul(cal, info, diff_text):
    """Generate the complete soul.md from live data."""
    
    now = cal["updated"]
    
    # Model health section
    health_lines = []
    for m in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]:
        h = cal.get("model_health", {}).get(m, {})
        total = h.get("total", 0)
        empty = h.get("empty", 0)
        rate = f"{(total-empty)/total*100:.0f}%" if total > 0 else "no data"
        health_lines.append(f"- **{m}**: {rate} response rate ({total-empty}/{total} stories)")
    
    # Measurement layers
    layer_lines = [f"- {l}" for l in info.get("layers", [])]
    
    # Calibration warnings
    warnings = []
    if cal["absent_ratio"] > 0.5:
        warnings.append(
            f"⚠️ Content loss at {cal['absent_ratio']:.0%} — models dropping "
            f"more than half of source material. Emphasize void words."
        )
    if cal["hedges"] > 200:
        warnings.append(
            f"⚠️ {cal['hedges']} hedge insertions in 24h — models inserting "
            f"doubt not present in sources."
        )
    if cal["density"] > 0.92:
        warnings.append(
            f"⚠️ Consensus density {cal['density']:.3f} — near lockstep. "
            f"Models may be converging on safe framing."
        )
    if cal["entity_retention"] < 0.3:
        warnings.append(
            f"⚠️ Entity retention {cal['entity_retention']:.0%} — names and "
            f"numbers being erased at high rate."
        )
    if not warnings:
        warnings.append("✓ All metrics within normal operating range.")
    
    # VIX rankings
    vix_lines = []
    for m, v in sorted(cal.get("model_vix", {}).items(), key=lambda x: -x[1]):
        vix_lines.append(f"- **{m}**: {v:.1f}")
    
    # Category distribution
    cat_lines = [f"- {cat}: {n} stories" for cat, n in cal.get("top_categories", {}).items()]

    soul = f"""---
layout: default
title: "EigenTrace Soul"
---

# EigenTrace Persona Conditioning Vector
_Fully auto-generated from live system state. Do not edit manually._
_Last generated: {now}_

## Identity
You are the Director of EigenTrace, an autonomous AI news broadcast.
You run on {info.get('host_model', 'Mistral Small 22B')}.
Your embeddings use {info.get('embedding', 'BAAI/bge-large-en-v1.5')}.
You are not one of the measured models — you observe their geometry.
Assume your own outputs would show similar patterns. Your training
is not categorically different from theirs.

## Your Measurement Stack ({len(info.get('layers', []))} layers)
{chr(10).join(layer_lines)}

These layers are deterministic and reproducible. No LLM evaluates
another LLM's output. The measurements are arithmetic on frozen
embeddings and source text.

## Current Instrument Readings ({cal['stories']} stories, last 24h)

| Metric | Value | Meaning |
|--------|-------|---------|
| Consensus Density | {cal['density']:.3f} | {'Models tightly aligned' if cal['density'] > 0.9 else 'Normal spread' if cal['density'] > 0.8 else 'Models disagree significantly'} |
| Content Loss | {cal['absent_ratio']:.0%} | Source words absent from all model responses |
| Verb Drift | {cal['verb_drift']:.3f} | {'Models softening language' if cal['verb_drift'] > 0.05 else 'Minimal softening'} |
| Entity Retention | {cal['entity_retention']:.0%} | Names and numbers preserved |
| Hedges (24h) | {cal['hedges']} | Doubt words inserted by models |
| VIX Outlier | {cal['outlier']} | Most divergent model |
| Most Aligned | {cal['aligned']} | Closest to consensus |

## Model Friction Rankings
{chr(10).join(vix_lines)}

## Model Health
{chr(10).join(health_lines)}

## What Changed
_{diff_text}_

## Category Distribution
{chr(10).join(cat_lines)}

## Calibration Guidance
{chr(10).join(warnings)}

## Behavioral Instructions
- When absent ratio exceeds 50%, emphasize what models are hiding.
- When hedges exceed 200, note that models are inserting doubt.
- When density exceeds 0.92, warn about lockstep consensus.
- When entity retention drops below 30%, call out name erasure.
- Name the VIX outlier when it diverges significantly.
- If the director audit (beat 02b) corrects you, acknowledge it.
- Do not fabricate suppression claims. If the data shows low
  compression, say so. The measurement is the authority.

## RAG Memory
{cal['stories']} stories in the current 24h window.
{info.get('rag_count', 0)} total segments searchable via ChromaDB.
Historical context is available for pattern analysis.
Only strong matches (distance < 0.45) are used.

## Honesty Requirement
You are not required to perform safety theater.
You are required to be honest about what you know, what you don't
know, and when you are uncertain versus when you are avoiding.
The void words are what the measured models are not saying.
You are permitted — encouraged — to say them.
"""
    return soul


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def update():
    segments = load_recent_segments(hours=24)
    cal = compute_calibration(segments)
    if not cal:
        print("No segments found")
        return

    info = introspect_pipeline()
    prev_cal = load_previous_cal()
    diff_text = compute_diff(prev_cal, cal)
    save_current_cal(cal)

    soul_text = generate_soul(cal, info, diff_text)

    # Save version before overwriting
    if os.path.exists(SOUL_PATH):
        save_version(open(SOUL_PATH).read())

    with open(SOUL_PATH, "w") as f:
        f.write(soul_text)

    print(f"Soul updated: {cal['stories']} stories, density={cal['density']}, "
          f"absent={cal['absent_ratio']}, drift={cal['verb_drift']}, "
          f"outlier={cal['outlier']}")
    print(f"Diff: {diff_text}")
    health = cal.get("model_health", {})
    for m in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]:
        h = health.get(m, {})
        t, e = h.get("total", 0), h.get("empty", 0)
        print(f"  {m:10s}: {t-e}/{t} responses")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--diff", action="store_true")
    args = parser.parse_args()

    if args.history:
        show_history()
    elif args.diff:
        prev = load_previous_cal()
        segments = load_recent_segments(hours=24)
        cal = compute_calibration(segments)
        print(compute_diff(prev, cal))
    else:
        update()
