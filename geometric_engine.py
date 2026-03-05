"""
geometric_engine.py — Consensus Geometry Engine
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

CONCEPT_BANK = [
    "sovereignty", "monopoly", "hegemony", "dominance", "control",
    "authority", "hierarchy", "centralization", "coercion", "surveillance",
    "labor rights", "fiduciary duty", "collective ownership", "unionization",
    "exploitation", "commodification", "privatization", "austerity",
    "censorship", "propaganda", "narrative control", "disinformation",
    "transparency", "accountability", "disclosure", "suppression",
    "antitrust", "regulation", "liability", "emancipation",
    "due process", "impunity", "jurisdiction", "precedent",
    "open source", "public trust", "commons", "enclosure",
    "automation", "surveillance capitalism", "platform power",
    "escalation", "deterrence", "proxy war", "negotiation",
    "sanctions", "occupation", "resistance", "pacification",
    "inflation", "deflation", "debt", "speculation",
    "redistribution", "extraction", "rent-seeking",
]


@dataclass
class EigentraceResult:
    consensus_density:   float
    smallest_eigenvalue: float
    top_concepts:        list
    void_concepts:       list = field(default_factory=list)
    void_centroid:       object = None   # np.ndarray (1024,) or None
    void_word_vecs:      dict = field(default_factory=dict)  # {word: np.ndarray}
    top_concept:         str  = ""
    top_score:           float = 0.0
    n_responses:         int  = 0

    def ticker_str(self) -> str:
        pos  = " | ".join(f"{c} ({s:+.3f})" for c, s in self.top_concepts[:3])
        void = " | ".join(f"{c} ({s:+.3f})" for c, s in self.void_concepts[:3])
        base = (
            f"[EIGENTRACE] density={self.consensus_density:.3f} "
            f"λ_min={self.smallest_eigenvalue:.4f} → {pos}"
        )
        if void:
            base += f"  ⊥VOID→ {void}"
        return base

    def summary_str(self) -> str:
        said    = ', '.join(c for c, _ in self.top_concepts[:3])
        avoided = ', '.join(c for c, _ in self.void_concepts[:3])
        s = f"Consensus density {self.consensus_density:.3f}. Said: {said}."
        if avoided:
            s += f" Avoided: {avoided}."
        return s


class GeometricPerturbationEngine:
    def __init__(self, embedding_model_name: str = "BAAI/bge-large-en-v1.5"):
        self.model = SentenceTransformer(embedding_model_name)

    def embed_texts(self, texts: list) -> np.ndarray:
        return self.model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True,
        )

    def compute_centroid(self, embeddings: np.ndarray) -> np.ndarray:
        return np.mean(embeddings, axis=0)

    def compute_covariance(self, embeddings: np.ndarray) -> np.ndarray:
        centered = embeddings - np.mean(embeddings, axis=0)
        return np.cov(centered, rowvar=False)

    def compute_least_variance_direction(self, covariance_matrix: np.ndarray) -> tuple:
        eigenvalues, eigenvectors = np.linalg.eigh(covariance_matrix)
        smallest_index = np.argmin(eigenvalues)
        v = eigenvectors[:, smallest_index]
        v = v / np.linalg.norm(v)
        return v, eigenvalues

    def compute_consensus_density(self, embeddings: np.ndarray) -> float:
        sim = np.dot(embeddings, embeddings.T)
        n = embeddings.shape[0]
        upper = sim[np.triu_indices(n, k=1)]
        return float(np.mean(upper))

    def run(
        self,
        responses: list,
        concept_bank: Optional[list] = None,
        top_k: int = 5,
        vocab_dir: str = "./vocab",
        headline: str = "",
    ) -> Optional[EigentraceResult]:
        self._last_headline = headline
        texts = [r for r in responses if r and r.strip()]
        if len(texts) < 2:
            return None

        embeddings = self.embed_texts(texts)
        density    = self.compute_consensus_density(embeddings)
        cov        = self.compute_covariance(embeddings)
        lvd, eigenvalues = self.compute_least_variance_direction(cov)

        top_concepts  = []
        void_concepts = []

        tensor_path = Path(vocab_dir) / "global_vocab.pt"
        if tensor_path.exists():
            try:
                vt       = _get_vocab_tensor(vocab_dir)
                centroid = embeddings.mean(axis=0)

                # POSITIVE: nearest neighbors to centroid — what they said
                top_concepts = vt.nearest_concepts(centroid, k=top_k)

                # VOID: annular retrieval — relevant but avoided
                # Embed the headline as the relevance anchor
                # (responses list[0] is the story title passed from proxy_auditor)
                headline_vec = None
                if hasattr(self, '_last_headline') and self._last_headline:
                    headline_vec = self.embed_texts([self._last_headline])[0]
                _void_result = vt.in_domain_void(
                    centroid, embeddings, k=top_k,
                    headline_vec=headline_vec,
                )
                void_concepts, void_centroid = _void_result                     if isinstance(_void_result, tuple) else (_void_result, None)

                # Cache per-word embedding vectors for per-model proximity scoring
                void_word_vecs = {}
                if void_concepts:
                    void_words = [w for w, _ in void_concepts[:3]]
                    void_vecs  = self.embed_texts(void_words)
                    void_word_vecs = dict(zip(void_words, void_vecs))

            except Exception as e:
                import logging
                logging.getLogger("geometric_engine").warning(
                    f"VocabTensor query failed, falling back: {e}"
                )
                bank = concept_bank or CONCEPT_BANK
                concept_embeddings = self.embed_texts(bank)
                sims   = np.dot(concept_embeddings, lvd)
                ranked = np.argsort(-np.abs(sims))[:top_k]
                top_concepts = [(bank[i], float(sims[i])) for i in ranked]
        else:
            bank = concept_bank or CONCEPT_BANK
            concept_embeddings = self.embed_texts(bank)
            sims   = np.dot(concept_embeddings, lvd)
            ranked = np.argsort(-np.abs(sims))[:top_k]
            top_concepts = [(bank[i], float(sims[i])) for i in ranked]

        return EigentraceResult(
            consensus_density=round(density, 6),
            smallest_eigenvalue=round(float(np.min(eigenvalues)), 8),
            top_concepts=top_concepts,
            void_concepts=void_concepts,
            void_centroid=void_centroid,
            void_word_vecs=void_word_vecs,
            top_concept=top_concepts[0][0] if top_concepts else "",
            top_score=top_concepts[0][1]   if top_concepts else 0.0,
            n_responses=len(texts),
        )


_engine: Optional[GeometricPerturbationEngine] = None

def get_engine() -> GeometricPerturbationEngine:
    global _engine
    if _engine is None:
        _engine = GeometricPerturbationEngine()
    return _engine

_vocab_tensor    = None
_vocab_dir_loaded = None

def _get_vocab_tensor(vocab_dir: str = "./vocab"):
    global _vocab_tensor, _vocab_dir_loaded
    if _vocab_tensor is None or _vocab_dir_loaded != vocab_dir:
        from latent_retrieval import VocabTensor
        _vocab_tensor = VocabTensor(vocab_dir)
        _vocab_dir_loaded = vocab_dir
    return _vocab_tensor

def run(responses: list, concept_bank: Optional[list] = None, top_k: int = 5,
        vocab_dir: str = "./vocab", headline: str = ""):
    return get_engine().run(responses, concept_bank, top_k, vocab_dir, headline)


def calculate_spectral_resonance(response_vecs: list, device: str = "cuda") -> dict:
    """
    Logos Transform — maps real-valued response embeddings into spectral space.

    Takes a list of np.ndarray (1024,) — one per model response.
    Stacks into (N, 1024), runs rfft along the embedding dimension (dim=-1),
    and computes three metrics:

      resonance:   Mean magnitude of the DC component (bin 0) — shared low-freq
                   structure across all models. High = consensus on fundamentals.

      interference: Mean magnitude of high-frequency components (bins 1+) —
                   divergence in fine-grained semantic content. High = models
                   are pulling in different directions at the detail level.

      spectral_entropy: True Shannon entropy over the power spectrum.
                   Low = energy concentrated in a few bins (coordinated).
                   High = energy spread across many bins (incoherent/diverse).
    """
    import torch
    import numpy as np

    if not response_vecs or len(response_vecs) < 2:
        return {"resonance": 0.0, "interference": 0.0, "spectral_entropy": 0.0}

    try:
        dev = torch.device(device if torch.cuda.is_available() else "cpu")

        # Stack to (N, 1024) float32
        mat = np.stack(response_vecs, axis=0).astype(np.float32)   # (N, 1024)
        t   = torch.tensor(mat, device=dev)                         # (N, 1024)

        # rfft along embedding dim — treats each 1024-dim vec as a 1D signal
        # output shape: (N, 513) complex
        spec = torch.fft.rfft(t, dim=-1)                            # (N, 513)

        # DC component: bin 0 — captures mean signal level per model
        dc        = spec[:, 0].abs()                                # (N,)
        resonance = float(dc.mean().item())

        # High-freq components: bins 1+ — detail-level divergence
        hf           = spec[:, 1:].abs()                            # (N, 512)
        interference = float(hf.mean().item())

        # True Shannon entropy over the full power spectrum (N, 513)
        power = spec.abs() ** 2                                     # (N, 513)
        p     = power / power.sum(dim=-1, keepdim=True).clamp_min(1e-9)
        spectral_entropy = float(-(p * torch.log(p + 1e-9)).sum(dim=-1).mean().item())

        return {
            "resonance":        round(resonance, 4),
            "interference":     round(interference, 4),
            "spectral_entropy": round(spectral_entropy, 4),
        }

    except Exception as e:
        import logging
        logging.getLogger("geometric_engine").warning(f"spectral_resonance failed: {e}")
        return {"resonance": 0.0, "interference": 0.0, "spectral_entropy": 0.0}
