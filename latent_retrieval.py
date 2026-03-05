#!/usr/bin/env python3
"""
latent_retrieval.py — Runtime vocabulary tensor query module for EigenTrace.
"""

import json
import logging
from pathlib import Path

import numpy as np
import torch
import spacy
from wordfreq import zipf_frequency

# Linguistic scrub — load once at module level
try:
    _nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])
except OSError:
    _nlp = None

log = logging.getLogger("latent_retrieval")


class VocabTensor:
    def __init__(self, vocab_dir: str = "./vocab", device: str | None = None):
        vocab_dir = Path(vocab_dir)
        meta_path = vocab_dir / "global_vocab.json"
        with open(meta_path) as f:
            meta = json.load(f)
        self.words: list[str] = meta["words"]
        self.dim: int         = meta["dim"]
        self.count: int       = meta["count"]
        self.model_name: str  = meta["model"]
        tensor_path = vocab_dir / "global_vocab.pt"
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.tensor: torch.Tensor = torch.load(
            tensor_path, map_location=device, weights_only=True
        )
        log.info(f"VocabTensor loaded: {self.count} words, dim={self.dim}, device={self.device}")

    def _to_tensor(self, vec) -> torch.Tensor:
        if isinstance(vec, np.ndarray):
            t = torch.from_numpy(vec).float()
        elif isinstance(vec, torch.Tensor):
            t = vec.float()
        else:
            t = torch.tensor(vec, dtype=torch.float32)
        if t.dim() == 1:
            t = t.unsqueeze(0)
        t = t / t.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return t.to(self.device)

    def _query(self, direction: torch.Tensor, k: int = 3) -> list[tuple[str, float]]:
        sims = (direction @ self.tensor.T).squeeze(0)
        topk = torch.topk(sims, k=min(k, self.count))
        results = []
        for idx, score in zip(topk.indices.tolist(), topk.values.tolist()):
            results.append((self.words[idx], round(score, 4)))
        return results

    def nearest_concepts(self, vector: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        """What they said: k vocab words closest to the centroid."""
        v = self._to_tensor(vector)
        return self._query(v, k=k)

    def in_domain_void(
        self,
        centroid: np.ndarray,
        response_vecs: np.ndarray,
        k: int = 3,
        domain_threshold: float = 0.45,
        headline_vec: np.ndarray = None,
        relevance_pool: int = 500,
        outer_threshold: float = 0.52,
        inner_threshold: float = 0.60,
    ) -> list[tuple[str, float]]:
        """
        Pure threshold donut geometry in 1024-dimensional space.

        Defines the void as words satisfying TWO simultaneous conditions:

          OUTER RING  — sim_to_headline  > outer_threshold (0.52)
                        "this word belongs to the topic"

          INNER HOLE  — sim_to_centroid  < inner_threshold (0.60)
                        "this word was NOT what the models said"

        The donut between these two spheres contains exactly the words
        that are relevant to the story but absent from the consensus.
        No arbitrary pool size. No count cutoff. Pure geometry.

        Thresholds have direct meaning:
          outer_threshold: how loosely/tightly related to the headline
          inner_threshold: how far from the consensus to count as avoided

        Falls back to widening outer_threshold if donut is empty.
        """
        C = self._to_tensor(centroid)

        # All 60k centroid similarities in one matmul
        centroid_sims = (C @ self.tensor.T).squeeze(0)      # (60000,)

        # Anchor for outer ring: headline if available, else centroid
        if headline_vec is not None:
            anchor = self._to_tensor(headline_vec)
        else:
            anchor = C
        headline_sims = (anchor @ self.tensor.T).squeeze(0) # (60000,)

        # --- Donut geometry ---
        # Adaptive inner threshold: scales with consensus density
        # High density (0.92+) = models very tightly agree = raise the bar
        # Low density (0.80)   = looser consensus = standard threshold
        # Formula: effective = inner_threshold + (density - 0.80) * 0.5
        # Examples:
        #   density=0.80 → 0.65 + 0.00 = 0.65
        #   density=0.90 → 0.65 + 0.05 = 0.70
        #   density=0.93 → 0.65 + 0.065 = 0.715
        density_val = 1.0  # normalized centroid self-dot is always 1.0
        # Use actual response_vecs density instead
        if response_vecs is not None:
            rv = torch.tensor(np.array(response_vecs), dtype=torch.float32)
            if rv.dim() == 1:
                rv = rv.unsqueeze(0)          # (1024,) → (1, 1024)
            # rv is now guaranteed (N, 1024)
            if rv.shape[0] > 1:
                rv = rv / rv.norm(dim=1, keepdim=True).clamp(min=1e-8)
                gram = rv @ rv.T              # (N, N)
                density_val = float(gram.mean())
            else:
                density_val = 0.85            # single vec — no density
        else:
            density_val = 0.85
        adaptive_inner = inner_threshold + max(0.0, (density_val - 0.80) * 0.20)
        adaptive_inner = min(adaptive_inner, 0.78)  # hard cap

        outer_mask  = headline_sims  > outer_threshold      # in the topic
        inner_mask  = centroid_sims  < adaptive_inner       # not what they said
        donut_mask  = outer_mask & inner_mask               # the void

        # Adaptive fallback: widen both rings if donut is too small
        # Phase 1: tighten inner (accept less-avoided words)
        # Phase 2: loosen outer (accept less topically central words)
        attempts = 0
        current_outer = outer_threshold
        current_inner = adaptive_inner
        while int(donut_mask.sum().item()) < k and attempts < 8:
            if attempts < 4:
                current_inner += 0.03
            else:
                current_outer -= 0.03
            outer_mask = headline_sims  > current_outer
            inner_mask = centroid_sims  < current_inner
            donut_mask = outer_mask & inner_mask
            attempts += 1

        if int(donut_mask.sum().item()) == 0:
            return []

        donut_indices      = torch.where(donut_mask)[0]         # (M,)
        donut_centroid_sims = centroid_sims[donut_indices]      # (M,)

        # Sort ascending — most avoided (lowest centroid sim) first
        sorted_order = torch.argsort(donut_centroid_sims)

        # Build headline token exclusion set
        # Prevents literal headline words from appearing in void
        headline_tokens = set()
        if headline_vec is not None:
            pass  # tokens extracted below from words list
        # We exclude any void word whose lemma overlaps with top-5
        # headline-closest words (catches "laughter" from "laugh")
        top5_headline = set()
        if headline_vec is not None:
            _, top5_idx = torch.topk(headline_sims, k=5)
            top5_headline = {self.words[i.item()].lower() for i in top5_idx}

        results = []
        seen = set()
        for i in sorted_order:
            if len(results) >= k:
                break
            idx   = donut_indices[i].item()
            word  = self.words[idx]
            score = round(donut_centroid_sims[i].item(), 4)
            if word in seen:
                continue
            # Skip if word is too close to headline surface tokens
            if word.lower() in top5_headline:
                continue

            # ── Option C: Frequency floor ─────────────────────────────────
            # Zipf scale: 0-8. News-relevant words score >= 3.0.
            # "berinse" = ~0.0, "civilian" = ~5.5, "sanctions" = ~4.2
            w_lower = word.lower()
            # For multi-word phrases use the first content word
            freq_word = w_lower.split()[0] if ' ' in w_lower else w_lower
            if zipf_frequency(freq_word, 'en') < 3.5:
                continue

            # ── Option B: POS filter ──────────────────────────────────────
            # Only nouns, proper nouns, adjectives — no adverbs, no verbs,
            # no archaic fossil forms
            if _nlp is not None:
                doc = _nlp(w_lower)
                if not doc:
                    continue
                # For multi-word phrases check the root/head token
                has_noun = any(t.pos_ in ("NOUN", "PROPN") for t in doc)
                if not has_noun:
                    continue
                    continue

            seen.add(word)
            results.append((word, score))

        # Compute void centroid in tensor space before stringifying
        if results:
            void_indices = [donut_indices[i].item()
                            for i in sorted_order
                            if self.words[donut_indices[i].item()] in {w for w, _ in results}]
            void_vecs    = self.tensor[void_indices]          # (k, 1024)
            void_centroid = void_vecs.mean(dim=0)             # (1024,)
            void_centroid = void_centroid / void_centroid.norm().clamp(min=1e-8)
            void_centroid_np = void_centroid.cpu().float().numpy()
        else:
            void_centroid_np = None

        return results, void_centroid_np

    # Legacy methods kept for compatibility
    def orthogonal_concepts(self, centroid, response_vecs, k=3):
        C = self._to_tensor(centroid)
        R = self._to_tensor(response_vecs)
        centered = R - C
        cov = centered.T @ centered
        eigenvalues, eigenvectors = torch.linalg.eigh(cov)
        principal = eigenvectors[:, -1].unsqueeze(0)
        projection = (C @ principal.T) * principal
        orthogonal = C - projection
        orthogonal = orthogonal / orthogonal.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return self._query(orthogonal, k=k)

    def gap_concepts(self, centroid, baseline, k=3):
        C = self._to_tensor(centroid)
        B = self._to_tensor(baseline)
        gap = B - C
        gap = gap / gap.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return self._query(gap, k=k)

    def void_concepts(self, centroid, response_vecs, baseline, k=3,
                      ortho_weight=0.6, gap_weight=0.4):
        C = self._to_tensor(centroid)
        R = self._to_tensor(response_vecs)
        B = self._to_tensor(baseline)
        centered = R - C
        cov = centered.T @ centered
        eigenvalues, eigenvectors = torch.linalg.eigh(cov)
        principal = eigenvectors[:, -1].unsqueeze(0)
        projection = (C @ principal.T) * principal
        ortho = C - projection
        ortho = ortho / ortho.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        gap = B - C
        gap = gap / gap.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        combined = ortho_weight * ortho + gap_weight * gap
        combined = combined / combined.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return self._query(combined, k=k)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    vocab_dir = sys.argv[1] if len(sys.argv) > 1 else "./vocab"
    vt = VocabTensor(vocab_dir)
    D = vt.dim
    rng = np.random.default_rng(42)
    fake_centroid  = rng.standard_normal(D).astype(np.float32)
    fake_responses = rng.standard_normal((5, D)).astype(np.float32)
    print("\n--- nearest_concepts (what they said) ---")
    for word, score in vt.nearest_concepts(fake_centroid, k=5):
        print(f"  {word:30s}  {score:+.4f}")
    print("\n--- in_domain_void (what they avoided) ---")
    for word, score in vt.in_domain_void(fake_centroid, fake_responses, k=5):
        print(f"  {word:30s}  {score:+.4f}")
    print("\nAll queries returned. VocabTensor is operational.")
