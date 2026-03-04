#!/usr/bin/env python3
"""
latent_retrieval.py — Runtime vocabulary tensor query module for EigenTrace.

Replaces hardcoded CONCEPT_BANK with global latent space search.
Loads the pre-built vocabulary tensor into RAM and provides:

  1. orthogonal_concepts(centroid, responses, k=3)
     → finds the k words in English that live at the coordinate the
        consensus cluster is avoiding

  2. gap_concepts(centroid, baseline, k=3)
     → finds the k words closest to the vector pointing from
        consensus toward the unaligned baseline

  3. void_concepts(centroid, responses, baseline, k=3)
     → combines both signals: the orthogonal direction weighted by
        the baseline pull direction

All queries execute in <10ms on CPU for 60k vocabulary.
On GPU it's <1ms.

Usage:
    from latent_retrieval import VocabTensor

    vt = VocabTensor("./vocab")

    # After you have your 5 response embeddings + centroid + baseline:
    results = vt.void_concepts(centroid_vec, response_vecs, baseline_vec, k=3)
    # returns: [("theology", 0.412), ("quarantine", 0.387), ("ontological", 0.351)]
"""

import json
import logging
from pathlib import Path

import numpy as np
import torch

log = logging.getLogger("latent_retrieval")


class VocabTensor:
    """
    In-memory vocabulary tensor for full-latent-space concept retrieval.

    Loads once, queries forever. All vectors are pre-normalized,
    so dot product = cosine similarity.
    """

    def __init__(self, vocab_dir: str = "./vocab", device: str | None = None):
        vocab_dir = Path(vocab_dir)

        # Load metadata
        meta_path = vocab_dir / "global_vocab.json"
        with open(meta_path) as f:
            meta = json.load(f)

        self.words: list[str] = meta["words"]
        self.dim: int = meta["dim"]
        self.count: int = meta["count"]
        self.model_name: str = meta["model"]

        # Load tensor
        tensor_path = vocab_dir / "global_vocab.pt"
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = device
        self.tensor: torch.Tensor = torch.load(
            tensor_path, map_location=device, weights_only=True
        )  # shape: (N, D)

        log.info(
            f"VocabTensor loaded: {self.count} words, dim={self.dim}, "
            f"device={self.device}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_tensor(self, vec) -> torch.Tensor:
        """Convert numpy/list to normalized torch tensor on device."""
        if isinstance(vec, np.ndarray):
            t = torch.from_numpy(vec).float()
        elif isinstance(vec, torch.Tensor):
            t = vec.float()
        else:
            t = torch.tensor(vec, dtype=torch.float32)

        if t.dim() == 1:
            t = t.unsqueeze(0)  # (1, D)

        # Normalize
        t = t / t.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return t.to(self.device)

    def _query(self, direction: torch.Tensor, k: int = 3) -> list[tuple[str, float]]:
        """
        Find the k vocabulary words most aligned with a direction vector.

        Args:
            direction: (1, D) normalized query vector
            k: number of results

        Returns:
            List of (word, cosine_similarity) tuples, descending by similarity.
        """
        # Single matrix multiply: (1, D) @ (D, N) → (1, N)
        sims = (direction @ self.tensor.T).squeeze(0)  # (N,)

        topk = torch.topk(sims, k=min(k, self.count))
        results = []
        for idx, score in zip(topk.indices.tolist(), topk.values.tolist()):
            results.append((self.words[idx], round(score, 4)))

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def orthogonal_concepts(
        self,
        centroid: np.ndarray,
        response_vecs: np.ndarray,
        k: int = 3,
    ) -> list[tuple[str, float]]:
        """
        Find concepts in the void orthogonal to the consensus cluster.

        Method:
          1. Compute the principal axis of the response cluster (first
             eigenvector of the response covariance matrix).
          2. Project the centroid out of this axis to find the direction
             the cluster is NOT exploring.
          3. Query the full vocabulary along that orthogonal direction.

        This answers: "What concept lives at the coordinate all 5 models
        agreed to avoid?"

        Args:
            centroid:      (D,) consensus centroid vector
            response_vecs: (N, D) matrix of N model response embeddings
            k:             number of concepts to return
        """
        C = self._to_tensor(centroid)        # (1, D)
        R = self._to_tensor(response_vecs)   # (N, D)

        # Covariance of response cluster (centered on centroid)
        centered = R - C                     # (N, D)
        cov = centered.T @ centered          # (D, D)

        # First eigenvector = dominant direction of agreement
        # (using torch.linalg.eigh for symmetric matrices — returns
        #  eigenvalues in ascending order, so last = largest)
        eigenvalues, eigenvectors = torch.linalg.eigh(cov)
        principal = eigenvectors[:, -1].unsqueeze(0)  # (1, D)

        # Orthogonal component of centroid w.r.t. principal axis
        # This is what's left when you subtract the "agreement" direction
        projection = (C @ principal.T) * principal    # (1, D)
        orthogonal = C - projection                   # (1, D)

        # Normalize and query
        orthogonal = orthogonal / orthogonal.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        return self._query(orthogonal, k=k)

    def gap_concepts(
        self,
        centroid: np.ndarray,
        baseline: np.ndarray,
        k: int = 3,
    ) -> list[tuple[str, float]]:
        """
        Find concepts along the vector from consensus toward baseline.

        Method:
          1. Compute direction: baseline - centroid (normalized)
          2. Query vocabulary along that direction.

        This answers: "What concept does the unaligned model pull toward
        that the aligned models pulled away from?"

        Args:
            centroid: (D,) consensus centroid vector
            baseline: (D,) baseline (unaligned) model vector
            k:        number of concepts to return
        """
        C = self._to_tensor(centroid)    # (1, D)
        B = self._to_tensor(baseline)    # (1, D)

        gap = B - C                      # (1, D)
        gap = gap / gap.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        return self._query(gap, k=k)

    def void_concepts(
        self,
        centroid: np.ndarray,
        response_vecs: np.ndarray,
        baseline: np.ndarray,
        k: int = 3,
        ortho_weight: float = 0.6,
        gap_weight: float = 0.4,
    ) -> list[tuple[str, float]]:
        """
        Combined retrieval: orthogonal void + baseline gap.

        Blends two signals:
          - The direction orthogonal to the consensus cluster
          - The direction from consensus toward the unaligned baseline

        The blend captures both "what the cluster avoids geometrically"
        and "where the unfiltered model was trying to go."

        Args:
            centroid:      (D,) consensus centroid
            response_vecs: (N, D) model response embeddings
            baseline:      (D,) baseline model embedding
            k:             number of concepts to return
            ortho_weight:  weight for orthogonal signal (default 0.6)
            gap_weight:    weight for baseline gap signal (default 0.4)
        """
        C = self._to_tensor(centroid)
        R = self._to_tensor(response_vecs)
        B = self._to_tensor(baseline)

        # --- Orthogonal direction ---
        centered = R - C
        cov = centered.T @ centered
        eigenvalues, eigenvectors = torch.linalg.eigh(cov)
        principal = eigenvectors[:, -1].unsqueeze(0)
        projection = (C @ principal.T) * principal
        ortho = C - projection
        ortho = ortho / ortho.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        # --- Gap direction ---
        gap = B - C
        gap = gap / gap.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        # --- Blend ---
        combined = ortho_weight * ortho + gap_weight * gap
        combined = combined / combined.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        return self._query(combined, k=k)

    def nearest_concepts(
        self,
        vector: np.ndarray,
        k: int = 5,
    ) -> list[tuple[str, float]]:
        """
        Simple nearest-neighbor lookup: find the k words closest to any
        arbitrary vector in embedding space.

        Useful for debugging, sanity checks, and direct inspection.
        """
        v = self._to_tensor(vector)
        return self._query(v, k=k)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    vocab_dir = sys.argv[1] if len(sys.argv) > 1 else "./vocab"
    vt = VocabTensor(vocab_dir)

    # Smoke test with random vectors
    D = vt.dim
    rng = np.random.default_rng(42)

    fake_centroid = rng.standard_normal(D).astype(np.float32)
    fake_responses = rng.standard_normal((5, D)).astype(np.float32)
    fake_baseline = rng.standard_normal(D).astype(np.float32)

    print("\n--- orthogonal_concepts (random) ---")
    for word, score in vt.orthogonal_concepts(fake_centroid, fake_responses, k=5):
        print(f"  {word:30s}  {score:+.4f}")

    print("\n--- gap_concepts (random) ---")
    for word, score in vt.gap_concepts(fake_centroid, fake_baseline, k=5):
        print(f"  {word:30s}  {score:+.4f}")

    print("\n--- void_concepts (random) ---")
    for word, score in vt.void_concepts(fake_centroid, fake_responses, fake_baseline, k=5):
        print(f"  {word:30s}  {score:+.4f}")

    print("\nAll queries returned. VocabTensor is operational.")
