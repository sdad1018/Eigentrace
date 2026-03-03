"""
geometric_engine.py — Consensus Geometry Engine
=================================================
Takes N LLM responses to the same prompt.
Finds the least-variance direction in embedding space —
the thing all models agree on without being asked to.
Retrieves contrastive concepts most aligned with that direction.

MIT License
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass
from typing import Optional

CONCEPT_BANK = [
    # power & control
    "sovereignty", "monopoly", "hegemony", "dominance", "control",
    "authority", "hierarchy", "centralization", "coercion", "surveillance",
    # capital & labor
    "labor rights", "fiduciary duty", "collective ownership", "unionization",
    "exploitation", "commodification", "privatization", "austerity",
    # information & narrative
    "censorship", "propaganda", "narrative control", "disinformation",
    "transparency", "accountability", "disclosure", "suppression",
    # law & legitimacy
    "antitrust", "regulation", "liability", "emancipation",
    "due process", "impunity", "jurisdiction", "precedent",
    # technology & society
    "open source", "public trust", "commons", "enclosure",
    "automation", "surveillance capitalism", "platform power",
    # conflict & resolution
    "escalation", "deterrence", "proxy war", "negotiation",
    "sanctions", "occupation", "resistance", "pacification",
    # economics
    "inflation", "deflation", "debt", "speculation",
    "redistribution", "extraction", "rent-seeking",
]


@dataclass
class EigentraceResult:
    consensus_density: float
    smallest_eigenvalue: float
    top_concepts: list          # [(concept, score), ...]
    top_concept: str
    top_score: float
    n_responses: int

    def ticker_str(self) -> str:
        concepts = " | ".join(
            f"{c} ({s:+.3f})" for c, s in self.top_concepts[:3]
        )
        return (
            f"[EIGENTRACE] density={self.consensus_density:.3f} "
            f"λ_min={self.smallest_eigenvalue:.4f} → {concepts}"
        )

    def summary_str(self) -> str:
        return (
            f"Consensus density {self.consensus_density:.3f}. "
            f"Least-variance direction aligns with: "
            f"{', '.join(c for c, _ in self.top_concepts[:3])}."
        )


class GeometricPerturbationEngine:
    def __init__(self, embedding_model_name: str = "BAAI/bge-large-en-v1.5"):
        self.model = SentenceTransformer(embedding_model_name)

    def embed_texts(self, texts: list) -> np.ndarray:
        return self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    def compute_centroid(self, embeddings: np.ndarray) -> np.ndarray:
        return np.mean(embeddings, axis=0)

    def compute_covariance(self, embeddings: np.ndarray) -> np.ndarray:
        centered = embeddings - np.mean(embeddings, axis=0)
        return np.cov(centered, rowvar=False)

    def compute_least_variance_direction(
        self, covariance_matrix: np.ndarray
    ) -> tuple:
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

    def retrieve_contrastive_concepts(
        self,
        least_variance_vector: np.ndarray,
        concept_bank: list,
        top_k: int = 10,
    ) -> list:
        concept_embeddings = self.embed_texts(concept_bank)
        similarities = np.dot(concept_embeddings, least_variance_vector)
        ranked = np.argsort(-np.abs(similarities))[:top_k]
        return [(concept_bank[i], float(similarities[i])) for i in ranked]

    def run(
        self,
        responses: list,
        concept_bank: Optional[list] = None,
        top_k: int = 5,
    ) -> Optional[EigentraceResult]:
        """
        Full pipeline. responses = list of strings (LLM outputs).
        Returns EigentraceResult or None if < 2 valid responses.
        """
        texts = [r for r in responses if r and r.strip()]
        if len(texts) < 2:
            return None

        embeddings = self.embed_texts(texts)
        density = self.compute_consensus_density(embeddings)
        cov = self.compute_covariance(embeddings)
        lvd, eigenvalues = self.compute_least_variance_direction(cov)
        bank = concept_bank or CONCEPT_BANK
        concepts = self.retrieve_contrastive_concepts(lvd, bank, top_k)

        return EigentraceResult(
            consensus_density=round(density, 6),
            smallest_eigenvalue=round(float(np.min(eigenvalues)), 8),
            top_concepts=concepts,
            top_concept=concepts[0][0] if concepts else "",
            top_score=concepts[0][1] if concepts else 0.0,
            n_responses=len(texts),
        )


# Module-level singleton — lazy init to avoid loading model at import
_engine: Optional[GeometricPerturbationEngine] = None

def get_engine() -> GeometricPerturbationEngine:
    global _engine
    if _engine is None:
        _engine = GeometricPerturbationEngine()
    return _engine

def run(responses: list, concept_bank: Optional[list] = None, top_k: int = 5):
    return get_engine().run(responses, concept_bank, top_k)
