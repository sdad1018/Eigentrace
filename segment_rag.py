#!/usr/bin/env python3
"""
segment_rag.py — RAG over past EigenTrace broadcast segments
=============================================================
Ingests segments into ChromaDB with semantic search.
Query: "what did we see last time AI regulation came up?"
Returns: relevant past segments with measurements.

Usage:
  python3 segment_rag.py --ingest          # Load all segments
  python3 segment_rag.py --query "topic"   # Search
"""

import json, glob, os, logging, hashlib
import chromadb
from datetime import datetime

log = logging.getLogger("segment_rag")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
CHROMA_DIR = "/home/remvelchio/eigentrace/chroma_segments"

def get_client():
    return chromadb.PersistentClient(path=CHROMA_DIR)

def get_collection(client=None):
    if client is None:
        client = get_client()
    return client.get_or_create_collection(
        name="eigentrace_segments",
        metadata={"hnsw:space": "cosine"},
    )

def segment_to_doc(seg):
    """Extract searchable text + metadata from a segment."""
    attr = seg.get("attribution", {})
    title = attr.get("story_title", "")
    category = attr.get("category", "unknown")
    density = attr.get("consensus_density", 0)
    state = attr.get("state_flag", "")
    void_words = attr.get("void_words", [])
    
    comp = attr.get("compression", {})
    verb_drift = comp.get("verb_downgrade", 0)
    entity_ret = comp.get("entity_retention", 0)
    hedges = comp.get("attribution_buffer", {})
    hedge_count = hedges.get("total", 0) if isinstance(hedges, dict) else 0
    
    sv = attr.get("source_void", {})
    absent_ratio = sv.get("absent_ratio", 0)
    absent_words = sv.get("absent_words", [])[:10]
    
    # Model responses summary
    responses = attr.get("model_responses", {})
    resp_summary = " ".join(v[:150] for v in responses.values() if v)
    
    # Build searchable document
    doc = (
        f"{title}. Category: {category}. State: {state}. "
        f"Void words: {', '.join(void_words[:8])}. "
        f"Absent words: {', '.join(absent_words)}. "
        f"{resp_summary[:300]}"
    )
    
    meta = {
        "title": title[:200],
        "category": category,
        "timestamp": seg.get("timestamp", ""),
        "density": round(density, 3),
        "absent_ratio": round(absent_ratio, 3),
        "verb_drift": round(verb_drift, 3),
        "entity_retention": round(entity_ret, 3),
        "hedge_count": hedge_count,
        "state_flag": state,
        "segment_id": seg.get("id", ""),
    }
    
    doc_id = hashlib.md5(f"{seg.get('id','')}{seg.get('timestamp','')}".encode()).hexdigest()
    return doc_id, doc, meta

def ingest_all(batch_size=200):
    """Load all segments into ChromaDB."""
    client = get_client()
    coll = get_collection(client)
    
    existing = coll.count()
    log.info(f"Collection has {existing} documents")
    
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")))
    log.info(f"Found {len(files)} segment files")
    
    ids, docs, metas = [], [], []
    skipped = 0
    
    for f in files:
        try:
            seg = json.load(open(f))
            attr = seg.get("attribution", {})
            if not attr.get("story_title"):
                skipped += 1
                continue
            doc_id, doc, meta = segment_to_doc(seg)
            ids.append(doc_id)
            docs.append(doc)
            metas.append(meta)
        except:
            skipped += 1
            continue
        
        if len(ids) >= batch_size:
            coll.upsert(ids=ids, documents=docs, metadatas=metas)
            log.info(f"Upserted {len(ids)} docs (total: {coll.count()})")
            ids, docs, metas = [], [], []
    
    if ids:
        coll.upsert(ids=ids, documents=docs, metadatas=metas)
    
    log.info(f"Ingest complete: {coll.count()} total docs, {skipped} skipped")
    return coll.count()

def query(text, n_results=5, category=None):
    """Search past segments by topic."""
    coll = get_collection()
    
    where = {"category": category} if category else None
    results = coll.query(
        query_texts=[text],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    
    hits = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        hits.append({
            "title": meta.get("title", ""),
            "category": meta.get("category", ""),
            "timestamp": meta.get("timestamp", ""),
            "density": meta.get("density", 0),
            "absent_ratio": meta.get("absent_ratio", 0),
            "verb_drift": meta.get("verb_drift", 0),
            "state_flag": meta.get("state_flag", ""),
            "distance": round(results["distances"][0][i], 3),
        })
    
    return hits

def format_context(hits, max_items=3):
    """Format RAG results for injection into host prompt."""
    if not hits:
        return ""
    lines = ["HISTORICAL CONTEXT (from past broadcasts):"]
    for h in hits[:max_items]:
        lines.append(
            f"- [{h['timestamp'][:8]}] {h['title'][:80]} "
            f"(density={h['density']}, absent={h['absent_ratio']}, "
            f"state={h['state_flag']})"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--query", type=str, default="")
    parser.add_argument("--category", type=str, default="")
    parser.add_argument("-n", type=int, default=5)
    args = parser.parse_args()
    
    if args.ingest:
        ingest_all()
    elif args.query:
        hits = query(args.query, n_results=args.n, 
                     category=args.category or None)
        for h in hits:
            print(f"  [{h['timestamp'][:8]}] dist={h['distance']} "
                  f"density={h['density']} absent={h['absent_ratio']} "
                  f"| {h['title'][:60]}")
    else:
        parser.print_help()
