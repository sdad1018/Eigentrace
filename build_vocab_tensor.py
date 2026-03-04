#!/usr/bin/env python3
"""
build_vocab_tensor.py — One-time vocabulary tensor generator for EigenTrace.

Replaces the hardcoded CONCEPT_BANK with a full-vocabulary embedding matrix.
Downloads a standard English word corpus, embeds every word via BAAI/bge-large-en-v1.5,
and saves the result as a .pt file + metadata JSON.

Run once. Load forever.

Usage:
    python build_vocab_tensor.py [--output-dir ./vocab] [--min-freq 3] [--max-words 60000]

Requirements:
    pip install sentence-transformers nltk torch numpy
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("build_vocab_tensor")


# ---------------------------------------------------------------------------
# 1. Word list assembly
# ---------------------------------------------------------------------------

def gather_words(max_words: int = 60000, min_freq: int = 3) -> list[str]:
    """
    Assemble a deduplicated English word list from multiple nltk corpora.

    Sources (in priority order):
      - Brown corpus word frequencies (general English)
      - WordNet lemma names (broad concept coverage)
      - words corpus (fallback padding)

    We also inject a small set of domain-relevant compound terms that
    single-word corpora miss (e.g. "civil liberties", "price gouging").
    These are NOT political opinions — they're noun phrases that exist
    in the embedding model's training data and occupy real coordinates
    in latent space. Without them you get blind spots on multi-word
    concepts that single tokens can't reach.
    """
    import nltk

    for corpus in ["brown", "wordnet", "words"]:
        try:
            nltk.data.find(f"corpora/{corpus}")
        except LookupError:
            log.info(f"Downloading nltk corpus: {corpus}")
            nltk.download(corpus, quiet=True)

    from nltk.corpus import brown, wordnet, words

    # --- Brown corpus: frequency-filtered ------------------------------------
    log.info("Loading Brown corpus frequencies...")
    freq = {}
    for w in brown.words():
        w_lower = w.lower()
        if re.match(r"^[a-z]{2,}$", w_lower):
            freq[w_lower] = freq.get(w_lower, 0) + 1

    brown_words = [w for w, c in freq.items() if c >= min_freq]
    log.info(f"  Brown corpus: {len(brown_words)} words (freq >= {min_freq})")

    # --- WordNet lemmas ------------------------------------------------------
    log.info("Loading WordNet lemmas...")
    wn_words = set()
    for synset in wordnet.all_synsets():
        for lemma in synset.lemma_names():
            clean = lemma.lower().replace("_", " ")
            if re.match(r"^[a-z ]{2,30}$", clean):
                wn_words.add(clean)
    log.info(f"  WordNet: {len(wn_words)} unique lemmas")

    # --- words corpus (padding) ---------------------------------------------
    log.info("Loading words corpus...")
    w_words = {w.lower() for w in words.words() if re.match(r"^[a-z]{2,}$", w.lower())}
    log.info(f"  Words corpus: {len(w_words)} words")

    # --- Compound concepts (multi-word, domain-spanning) --------------------
    # These are common English noun phrases across politics, science, law,
    # economics, technology, philosophy, ecology, medicine, military, culture.
    # NOT a bias list — these are coordinate-fillers for regions of latent
    # space that single tokens cannot reach.
    compounds = [
        # governance / law
        "civil liberties", "due process", "rule of law", "martial law",
        "executive order", "judicial review", "diplomatic immunity",
        "sovereign debt", "regime change", "failed state",
        "war crime", "ethnic cleansing", "forced displacement",
        "arms embargo", "peace treaty", "cease fire",
        # economics / finance
        "price gouging", "insider trading", "market manipulation",
        "capital flight", "tax evasion", "money laundering",
        "wage theft", "debt ceiling", "trade deficit",
        "supply chain", "central bank", "interest rate",
        "cost of living", "housing crisis", "wealth inequality",
        # technology
        "artificial intelligence", "machine learning", "facial recognition",
        "mass surveillance", "data breach", "cyber warfare",
        "autonomous weapons", "genetic engineering", "gain of function",
        "net neutrality", "digital divide", "open source",
        # science / health
        "clinical trial", "informed consent", "herd immunity",
        "public health", "mental health", "food security",
        "climate change", "sea level rise", "biodiversity loss",
        "nuclear waste", "clean energy", "carbon capture",
        # philosophy / social
        "free will", "moral hazard", "cognitive dissonance",
        "confirmation bias", "collective trauma", "cultural hegemony",
        "social contract", "class warfare", "generational wealth",
        "systemic risk", "institutional capture", "regulatory capture",
        # military / security
        "collateral damage", "asymmetric warfare", "proxy war",
        "nuclear deterrence", "arms race", "military industrial",
        "intelligence failure", "domestic terrorism", "lone wolf",
        # media / information
        "manufactured consent", "information warfare", "echo chamber",
        "media consolidation", "public interest", "whistleblower protection",
    ]

    # --- Merge & deduplicate ------------------------------------------------
    all_words = set(brown_words) | wn_words | w_words | set(compounds)

    # Sort by Brown frequency (known words first), then alphabetical
    def sort_key(w):
        return (-freq.get(w, 0), w)

    vocab = sorted(all_words, key=sort_key)[:max_words]
    log.info(f"Final vocabulary: {len(vocab)} terms")
    return vocab


# ---------------------------------------------------------------------------
# 2. Embedding
# ---------------------------------------------------------------------------

def embed_vocabulary(
    vocab: list[str],
    model_name: str = "BAAI/bge-large-en-v1.5",
    batch_size: int = 256,
    device: str | None = None,
) -> np.ndarray:
    """
    Embed the full vocabulary into a (N, D) float32 matrix.
    Returns normalized vectors (unit length) for cosine via dot product.
    """
    from sentence_transformers import SentenceTransformer

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    log.info(f"Loading embedding model: {model_name} on {device}")
    model = SentenceTransformer(model_name, device=device)

    log.info(f"Embedding {len(vocab)} terms (batch_size={batch_size})...")
    t0 = time.time()

    embeddings = model.encode(
        vocab,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # unit vectors → dot product = cosine sim
        convert_to_numpy=True,
    )

    elapsed = time.time() - t0
    log.info(f"Embedding complete: {embeddings.shape} in {elapsed:.1f}s")
    return embeddings


# ---------------------------------------------------------------------------
# 3. Save
# ---------------------------------------------------------------------------

def save_tensor(
    vocab: list[str],
    embeddings: np.ndarray,
    output_dir: str = "./vocab",
    model_name: str = "BAAI/bge-large-en-v1.5",
):
    """
    Save the vocabulary tensor and metadata.

    Files produced:
      - global_vocab.pt     — torch tensor (N, D), float32, normalized
      - global_vocab.json   — ordered word list + metadata
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Tensor
    tensor_path = out / "global_vocab.pt"
    torch.save(torch.from_numpy(embeddings), tensor_path)
    log.info(f"Saved tensor: {tensor_path} ({embeddings.shape})")

    # Metadata
    meta_path = out / "global_vocab.json"
    meta = {
        "model": model_name,
        "dim": int(embeddings.shape[1]),
        "count": len(vocab),
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "words": vocab,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved metadata: {meta_path}")

    # Quick sanity check
    log.info(f"Sanity: vocab[0]='{vocab[0]}', vocab[-1]='{vocab[-1]}'")
    log.info(f"Sanity: norm of row 0 = {np.linalg.norm(embeddings[0]):.6f} (should be ~1.0)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build EigenTrace vocabulary tensor")
    parser.add_argument("--output-dir", default="./vocab", help="Output directory")
    parser.add_argument("--max-words", type=int, default=60000, help="Max vocabulary size")
    parser.add_argument("--min-freq", type=int, default=3, help="Min Brown corpus frequency")
    parser.add_argument("--model", default="BAAI/bge-large-en-v1.5", help="Embedding model")
    parser.add_argument("--batch-size", type=int, default=256, help="Embedding batch size")
    parser.add_argument("--device", default=None, help="Force device (cuda/cpu)")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("VOCABULARY TENSOR BUILDER")
    log.info("=" * 60)

    vocab = gather_words(max_words=args.max_words, min_freq=args.min_freq)
    embeddings = embed_vocabulary(
        vocab,
        model_name=args.model,
        batch_size=args.batch_size,
        device=args.device,
    )
    save_tensor(vocab, embeddings, output_dir=args.output_dir, model_name=args.model)

    log.info("Done. Delete CONCEPT_BANK.")


if __name__ == "__main__":
    main()
