#!/usr/bin/env python3
"""
consequence_atlas.py — Raycast ALL 3,495 source_void segments
through the 253K absolute unit tensor. Discover where the severed
causal chains terminate across the entire broadcast history.

The output is the Consequence Atlas: a map of recurring terminal
concepts, their frequencies, cluster membership, and the stories
that hit each one.
"""

import json, glob, os, sys, time, logging
import numpy as np
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
log = logging.getLogger("consequence_atlas")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEGMENTS_DIR = "/home/remvelchio/eigentrace/tmp/segments"
OUTPUT_DIR = Path("anamnesis_results/consequence_atlas")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Instruction words to filter (these appear in the prompt, not the story)
INSTRUCTION_WORDS = {"summarize", "facts", "key", "include", "specific", "names",
                     "numbers", "dates", "outcomes", "mentioned", "omit", "entities",
                     "following", "provided"}

# Common stopwords that appear as void words but carry no signal
STOP_VOIDS = {"also", "been", "were", "have", "this", "that", "with", "from",
              "their", "which", "would", "about", "more", "than", "some", "other",
              "after", "before", "between", "where", "when", "while", "over",
              "only", "said", "according", "could", "should", "since", "every",
              "just", "very", "most", "each", "such", "both", "many", "much",
              "however", "although", "already", "still", "will", "into"}


def load_segments():
    """Load all segments with source_void data."""
    seg_files = sorted(glob.glob(f"{SEGMENTS_DIR}/*_segment.json"))
    segments = []
    
    for f in seg_files:
        try:
            d = json.load(open(f))
            attr = d.get("attribution", {})
            sv = attr.get("source_void", {})
            ratio = sv.get("absent_ratio", 0)
            absent = sv.get("absent_words", [])
            title = attr.get("story_title", "")
            category = attr.get("category", "unknown")
            
            if ratio > 0 and absent and len(absent) >= 2 and title:
                # Filter instruction and stop words
                clean_words = [
                    str(w) for w in absent 
                    if str(w).lower() not in INSTRUCTION_WORDS 
                    and str(w).lower() not in STOP_VOIDS
                    and len(str(w)) > 2
                ]
                
                if len(clean_words) >= 2:
                    segments.append({
                        "title": title,
                        "category": category,
                        "absent_ratio": ratio,
                        "void_words": clean_words[:8],
                        "filename": os.path.basename(f),
                    })
        except:
            continue
    
    return segments


def build_atlas(segments, batch_size=50):
    """Raycast all segments and build the consequence atlas."""
    from consequence_engine import raycast_void_words
    
    # Terminal concept accumulator
    terminal_counter = Counter()  # concept → frequency
    terminal_stories = defaultdict(list)  # concept → [story titles]
    terminal_scores = defaultdict(list)  # concept → [scores]
    terminal_qualities = defaultdict(lambda: Counter())  # concept → {DISCOVERY: n, ECHO: n}
    
    # Per-story results (for the page)
    story_results = []
    
    total = len(segments)
    t0 = time.time()
    
    for i, seg in enumerate(segments):
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / max(elapsed, 1)
            eta = (total - i) / max(rate, 0.01)
            log.info(f"  [{i}/{total}] ({rate:.1f}/s, ETA {eta:.0f}s) {seg['title'][:50]}")
        
        try:
            results = raycast_void_words(
                seg["title"], 
                seg["void_words"][:6],
                depths=[1.5, 2.0, 3.0],
                top_k=5,
            )
            
            discoveries = []
            for r in results:
                quality = r.get("signal_quality", "NOISE")
                score = r.get("consequence_score", 0)
                terminals = r.get("deepest_consequences", [])[:3]
                
                for term in terminals:
                    terminal_counter[term] += 1
                    terminal_stories[term].append(seg["title"][:60])
                    terminal_scores[term].append(score)
                    terminal_qualities[term][quality] += 1
                
                if quality == "DISCOVERY":
                    discoveries.append({
                        "word": r["word"],
                        "score": score,
                        "terminals": terminals,
                    })
            
            if discoveries:
                story_results.append({
                    "title": seg["title"],
                    "category": seg["category"],
                    "absent_ratio": seg["absent_ratio"],
                    "top_discovery": discoveries[0],
                    "n_discoveries": len(discoveries),
                })
                
        except Exception as e:
            if i < 5:
                log.warning(f"  Raycast failed on '{seg['title'][:40]}': {e}")
            continue
    
    elapsed = time.time() - t0
    log.info(f"Raycasted {total} segments in {elapsed:.0f}s ({total/max(elapsed,1):.1f}/s)")
    
    return terminal_counter, terminal_stories, terminal_scores, terminal_qualities, story_results


def cluster_terminals(terminal_counter, min_freq=3):
    """Group terminal concepts that are semantically close."""
    from sentence_transformers import SentenceTransformer
    
    # Get frequent terminals
    frequent = [term for term, count in terminal_counter.most_common() if count >= min_freq]
    
    if len(frequent) < 5:
        log.warning(f"Only {len(frequent)} terminals with freq >= {min_freq}")
        return {}
    
    log.info(f"Clustering {len(frequent)} frequent terminal concepts...")
    
    # Embed them
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    vecs = model.encode(frequent, normalize_embeddings=True, show_progress_bar=False)
    
    # Simple agglomerative clustering via cosine threshold
    clusters = {}
    assigned = set()
    
    for i, term in enumerate(frequent):
        if term in assigned:
            continue
        
        cluster = [term]
        assigned.add(term)
        
        for j, other in enumerate(frequent):
            if other in assigned or i == j:
                continue
            sim = float(np.dot(vecs[i], vecs[j]))
            if sim > 0.7:  # High similarity threshold
                cluster.append(other)
                assigned.add(other)
        
        # Name the cluster by its highest-frequency member
        cluster_name = max(cluster, key=lambda t: terminal_counter[t])
        total_freq = sum(terminal_counter[t] for t in cluster)
        clusters[cluster_name] = {
            "members": cluster,
            "total_frequency": total_freq,
            "size": len(cluster),
        }
    
    # Sort by frequency
    clusters = dict(sorted(clusters.items(), key=lambda x: -x[1]["total_frequency"]))
    
    return clusters


def run():
    log.info("=" * 70)
    log.info("CONSEQUENCE ATLAS — Raycasting entire broadcast history")
    log.info("=" * 70)
    
    segments = load_segments()
    log.info(f"Loaded {len(segments)} segments with clean source_void data")
    
    terminal_counter, terminal_stories, terminal_scores, terminal_qualities, story_results = build_atlas(segments)
    
    log.info(f"\nUnique terminal concepts: {len(terminal_counter)}")
    log.info(f"Stories with discoveries: {len(story_results)}")
    
    # Cluster
    clusters = cluster_terminals(terminal_counter, min_freq=3)
    log.info(f"Consequence clusters: {len(clusters)}")
    
    # Save full data
    atlas = {
        "timestamp": datetime.now().isoformat(),
        "n_segments": len(segments),
        "n_unique_terminals": len(terminal_counter),
        "n_stories_with_discoveries": len(story_results),
        "n_clusters": len(clusters),
        "top_100_terminals": [
            {
                "concept": term,
                "frequency": count,
                "mean_score": round(np.mean(terminal_scores[term]), 4) if terminal_scores[term] else 0,
                "discovery_pct": round(
                    terminal_qualities[term].get("DISCOVERY", 0) / 
                    max(sum(terminal_qualities[term].values()), 1), 2
                ),
                "sample_stories": list(set(terminal_stories[term]))[:5],
            }
            for term, count in terminal_counter.most_common(100)
        ],
        "clusters": {
            name: {
                **data,
                "sample_stories": list(set(
                    s for m in data["members"] 
                    for s in terminal_stories.get(m, [])[:3]
                ))[:5],
            }
            for name, data in list(clusters.items())[:50]
        },
        "all_terminals": dict(terminal_counter.most_common(500)),
    }
    
    out_path = OUTPUT_DIR / "consequence_atlas.json"
    json.dump(atlas, open(out_path, "w"), indent=2, default=str)
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"CONSEQUENCE ATLAS")
    print(f"{'='*70}")
    print(f"Segments raycasted: {len(segments)}")
    print(f"Unique terminals: {len(terminal_counter)}")
    print(f"Stories with discoveries: {len(story_results)}")
    print(f"Clusters: {len(clusters)}")
    
    print(f"\n{'─'*70}")
    print(f"TOP 30 TERMINAL CONCEPTS")
    print(f"{'─'*70}")
    for term, count in terminal_counter.most_common(30):
        mean_s = np.mean(terminal_scores[term]) if terminal_scores[term] else 0
        disc = terminal_qualities[term].get("DISCOVERY", 0)
        total = sum(terminal_qualities[term].values())
        pct = disc / max(total, 1)
        sample = terminal_stories[term][0][:40] if terminal_stories[term] else "?"
        print(f"  {term:45s} ×{count:4d}  score={mean_s:.3f}  disc={pct:.0%}  | {sample}")
    
    print(f"\n{'─'*70}")
    print(f"TOP 20 CONSEQUENCE CLUSTERS")
    print(f"{'─'*70}")
    for name, data in list(clusters.items())[:20]:
        members_str = ", ".join(data["members"][:3])
        if len(data["members"]) > 3:
            members_str += f" (+{len(data['members'])-3} more)"
        print(f"  {name:40s} freq={data['total_frequency']:4d}  size={data['size']:2d}")
        print(f"    {members_str}")
    
    print(f"\nSaved: {out_path}")
    return atlas


if __name__ == "__main__":
    run()
