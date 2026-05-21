#!/usr/bin/env python3
"""
build_absolute_unit_tensor.py — The Unfiltered Concept Mesh
===========================================================
Zero editorial bias. Zero hand-picked categories.
Streams 1GB Wikipedia abstract XML dump and extracts every valid
human-verified concept title, combined with systemic n-grams.

Produces raycast_vocab.npy + raycast_vocab.json used by
consequence_engine.py's latent raycasting.

Embed time: ~45 min on RTX 4080 (GPU free).
"""

import json, numpy as np, logging, time
import requests
from pathlib import Path

log = logging.getLogger("absolute_unit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VOCAB_DIR = Path("/mnt/c/Users/M4ISI/eigentrace/vocab")
VOCAB_DIR.mkdir(exist_ok=True)


def stream_wikipedia_api(max_concepts=250000):
    """Pull article titles via Wikipedia API. No dump needed. ~15 min for 250K titles."""
    cache_path = VOCAB_DIR / "wiki_titles_cache.json"
    
    if cache_path.exists():
        titles = json.load(open(cache_path))
        if len(titles) >= max_concepts * 0.9:
            log.info(f"Using cached titles: {len(titles)}")
            return titles
    
    log.info(f"Pulling {max_concepts} Wikipedia article titles via API...")
    concepts = set()
    ap_continue = ""
    calls = 0
    
    while len(concepts) < max_concepts:
        params = {
            "action": "query",
            "list": "allpages",
            "aplimit": 500,
            "apnamespace": 0,  # Main article namespace only
            "apfilterredir": "nonredirects",
            "format": "json",
        }
        if ap_continue:
            params["apcontinue"] = ap_continue
        
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php",
                           params=params, timeout=15,
                           headers={"User-Agent": "EigenTrace/1.0 (eigentraceproject@gmail.com)"})
            data = r.json()
            
            pages = data.get("query", {}).get("allpages", [])
            for page in pages:
                title = page.get("title", "")
                noise = ["List of", "disambiguation", "Template:", "Portal:"]
                if (title and 2 < len(title) < 100 and
                    not any(n in title for n in noise)):
                    concepts.add(title)
            
            # Continue token
            cont = data.get("continue", {})
            ap_continue = cont.get("apcontinue", "")
            if not ap_continue:
                log.info("Reached end of Wikipedia article index.")
                break
            
            calls += 1
            if calls % 100 == 0:
                log.info(f"  API calls: {calls}, titles: {len(concepts)}")
            
            time.sleep(0.05)  # Polite rate limiting
            
        except Exception as e:
            log.warning(f"  API call failed: {e}")
            time.sleep(2)
    
    titles = list(concepts)[:max_concepts]
    log.info(f"Extracted {len(titles)} Wikipedia article titles in {calls} API calls.")
    
    # Cache for next time
    json.dump(titles, open(cache_path, "w"))
    log.info(f"Cached to {cache_path}")
    
    return titles


def generate_systemic_ngrams():
    """Programmatic multi-word consequence phrases."""
    domains = [
        "supply chain", "agricultural", "economic", "financial", "energy",
        "infrastructure", "pharmaceutical", "food", "water", "healthcare",
        "semiconductor", "telecommunications", "transportation", "fuel",
        "fertilizer", "chemical", "industrial", "banking", "housing",
        "labor", "trade", "monetary", "fiscal", "sovereign debt",
        "commodity", "shipping", "logistics", "manufacturing", "mining",
        "refining", "desalination", "electrical grid", "nuclear",
        "cyber", "information", "institutional", "governance",
    ]
    severities = [
        "collapse", "failure", "crisis", "shortage", "disruption",
        "breakdown", "contagion", "paralysis", "shock", "scarcity",
        "emergency", "catastrophe", "meltdown", "cascade failure",
        "systemic risk", "default", "insolvency",
    ]
    modifiers = ["", "global", "regional", "cascading", "systemic", "prolonged"]
    
    ngrams = set()
    for m in modifiers:
        for d in domains:
            for s in severities:
                phrase = f"{m} {d} {s}".strip()
                if len(phrase) > 5:
                    ngrams.add(phrase)
    
    # Add raw consequence endpoints
    endpoints = [
        "mass starvation", "famine", "hyperinflation", "recession",
        "depression", "civil unrest", "mass migration", "refugee crisis",
        "pandemic", "epidemic", "blackout", "rationing",
        "martial law", "state of emergency", "sovereign default",
        "bank run", "currency collapse", "trade embargo", "blockade",
        "siege", "humanitarian crisis", "ecological collapse",
        "supply shock", "demand destruction", "price spike",
        "wage collapse", "unemployment surge", "brain drain",
        "capital flight", "sanctions regime", "arms embargo",
        "proxy war", "total war", "grid failure",
        "communication blackout", "internet shutdown",
        "crop failure", "harvest failure", "soil depletion",
    ]
    ngrams.update(endpoints)
    
    log.info(f"Generated {len(ngrams)} systemic n-grams.")
    return list(ngrams)


def build():
    log.info("=" * 60)
    log.info("BUILDING THE ABSOLUTE UNIT")
    log.info("=" * 60)
    
    wiki_concepts = stream_wikipedia_api(max_concepts=250000)
    systemic = generate_systemic_ngrams()
    
    all_concepts = list(set(wiki_concepts + systemic))
    all_concepts = [c for c in all_concepts if 2 < len(c) < 100]
    log.info(f"Total unique concepts: {len(all_concepts)}")
    
    log.info("Loading BGE-large...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    
    log.info(f"Embedding {len(all_concepts)} concepts...")
    BATCH = 1024
    all_vecs = []
    t0 = time.time()
    
    for i in range(0, len(all_concepts), BATCH):
        batch = all_concepts[i:i+BATCH]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_vecs.append(vecs)
        
        if i % 25000 == 0:
            elapsed = time.time() - t0
            if elapsed > 0 and i > 0:
                rate = i / elapsed
                eta = (len(all_concepts) - i) / rate
                log.info(f"  {i}/{len(all_concepts)} "
                         f"({i/len(all_concepts)*100:.0f}%) "
                         f"ETA: {eta/60:.1f}min")
    
    tensor = np.vstack(all_vecs).astype(np.float32)
    elapsed = time.time() - t0
    log.info(f"Tensor: {tensor.shape} ({tensor.nbytes / 1e6:.1f} MB) in {elapsed/60:.1f}min")
    
    np.save(VOCAB_DIR / "raycast_vocab.npy", tensor)
    json.dump({
        "words": all_concepts,
        "dim": int(tensor.shape[1]),
        "count": len(all_concepts),
        "model": "BAAI/bge-large-en-v1.5",
        "sources": {
            "wikipedia_abstracts": len(wiki_concepts),
            "systemic_ngrams": len(systemic),
        },
        "type": "absolute_unit_unfiltered",
    }, open(VOCAB_DIR / "raycast_vocab.json", "w"))
    
    log.info("=" * 60)
    log.info(f"THE ABSOLUTE UNIT IS BUILT")
    log.info(f"  {tensor.shape[0]} concepts × {tensor.shape[1]}d")
    log.info(f"  {tensor.nbytes / 1e6:.1f} MB on disk")
    log.info("=" * 60)


if __name__ == "__main__":
    build()
