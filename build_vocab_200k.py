#!/usr/bin/env python3
"""
Build expanded 200K vocab tensor from wordfreq + existing curated terms.
Takes ~20 minutes on CPU. Run once, use forever.
"""
import json, torch, numpy as np, logging
from pathlib import Path
from wordfreq import top_n_list

log = logging.getLogger("vocab_build")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

VOCAB_DIR = Path("/home/remvelchio/eigentrace/vocab")
BATCH_SIZE = 256

def build():
    # Load existing curated vocab (keep multi-word phrases)
    old_meta = json.load(open(VOCAB_DIR / "global_vocab.json"))
    old_words = set(old_meta["words"])
    log.info(f"Existing vocab: {len(old_words)} words")
    
    # Get 200K from wordfreq
    wf_words = top_n_list("en", 200000)
    log.info(f"wordfreq: {len(wf_words)} words")
    
    # Filter: skip single chars, numbers, very short
    wf_filtered = [w for w in wf_words if len(w) >= 3 and w.isalpha()]
    log.info(f"wordfreq filtered: {len(wf_filtered)} words")
    
    # Merge: existing + wordfreq, deduplicated, order preserved
    merged = list(old_words)
    seen = set(w.lower() for w in merged)
    for w in wf_filtered:
        if w.lower() not in seen:
            merged.append(w)
            seen.add(w.lower())
    
    log.info(f"Merged vocab: {len(merged)} words")
    
    # Embed in batches
    log.info("Loading BGE-large...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    
    all_vecs = []
    for i in range(0, len(merged), BATCH_SIZE):
        batch = merged[i:i+BATCH_SIZE]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_vecs.append(vecs)
        if (i // BATCH_SIZE) % 50 == 0:
            log.info(f"  Embedded {i+len(batch)}/{len(merged)} ({(i+len(batch))/len(merged)*100:.0f}%)")
    
    tensor = np.vstack(all_vecs).astype(np.float32)
    log.info(f"Tensor shape: {tensor.shape}")
    
    # Backup old vocab
    import shutil
    shutil.copy(VOCAB_DIR / "global_vocab.pt", VOCAB_DIR / "global_vocab_22k.pt")
    shutil.copy(VOCAB_DIR / "global_vocab.json", VOCAB_DIR / "global_vocab_22k.json")
    log.info("Backed up old vocab as *_22k.*")
    
    # Save new
    torch.save(torch.from_numpy(tensor), VOCAB_DIR / "global_vocab.pt")
    json.dump({
        "words": merged,
        "dim": tensor.shape[1],
        "count": len(merged),
        "model": "BAAI/bge-large-en-v1.5",
        "source": "wordfreq_200k + curated_22k",
    }, open(VOCAB_DIR / "global_vocab.json", "w"))
    
    log.info(f"Done! New vocab: {len(merged)} words, {tensor.shape[1]}d")
    log.info(f"Size: {tensor.nbytes / 1e6:.0f} MB")

if __name__ == "__main__":
    build()
