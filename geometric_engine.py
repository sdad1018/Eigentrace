"""
geometric_engine.py — Consensus Geometry Engine
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# CONCEPT_BANK removed in v11 -- all concept retrieval via VocabTensor.
# See latent_retrieval.py for the 60k unbiased vocabulary.


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
    spectral_gap:        float = 0.0

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
        self.model = SentenceTransformer(embedding_model_name, device="cpu")

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
        # Spectral gap: λ_max / Σ(all other λ)
        # eigh returns ascending order → [-1] is largest
        _eig_sorted = np.sort(eigenvalues)[::-1]   # descending
        _spectral_gap = float(
            _eig_sorted[0] / (np.abs(_eig_sorted[1:]).sum() + 1e-8)
        )

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
                if isinstance(_void_result, tuple):
                    void_concepts, void_centroid = _void_result
                else:
                    void_concepts, void_centroid = _void_result, None

                # Cache per-word embedding vectors for per-model proximity scoring
                void_word_vecs = {}
                if void_concepts:
                    void_words = [w for w, _ in void_concepts[:3]]
                    void_vecs  = self.embed_texts(void_words)
                    void_word_vecs = dict(zip(void_words, void_vecs))

            except Exception as e:
                import logging
                logging.getLogger("geometric_engine").warning(
                    f"VocabTensor query failed: {e}"
                )
                # No fallback to hardcoded concept bank.
                # Empty is honest. Biased fallback is not.
                top_concepts   = []
                void_concepts  = []
                void_centroid  = None
                void_word_vecs = {}
        else:
            import logging
            logging.getLogger("geometric_engine").warning(
                "VocabTensor not found -- no concept retrieval"
            )
            top_concepts   = []
            void_concepts  = []
            void_centroid  = None
            void_word_vecs = {}

        return EigentraceResult(
            consensus_density=round(density, 6),
            smallest_eigenvalue=round(float(np.min(eigenvalues)), 8),
            spectral_gap=round(_spectral_gap, 6),
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

    import warnings
    warnings.warn(
        "calculate_spectral_resonance is deprecated -- use calculate_eigen_resonance",
        DeprecationWarning, stacklevel=2,
    )
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


def calculate_svd_reconstruction(response_vecs: list,
                                  void_centroid=None,
                                  device: str = "cuda") -> dict:
    """
    Semantic Tomography — SVD-based reconstruction of the filtered truth.

    Frames the five model responses as a (5, 1024) projection matrix Y where:
        y_i = P_i @ x + eps_i
    P_i is the alignment filter (RLHF guardrail) for model i.
    x is the unobservable natural semantic trajectory.

    SVD decomposes Y = U @ diag(S) @ Vh:
      Vh[0]  = V1     — dominant right singular vector = Corporate Consensus
      Vh[-1] = V_last — lowest-variance direction = null space of the
                        alignment filters = Reconstruction Artifact
                        (the semantic "metal artifact" — the shape of what
                        the models collectively refused to generate)

    Metrics returned:
      consensus_compression:   S[0] / sum(S)
        Fraction of total variance captured by the dominant component.
        High = models are tightly coordinated (high SNR on the guardrail).
        Equivalent to your density score but derived from the response
        vectors directly rather than pairwise cosine similarity.

      null_space_energy:        S[-1] / S[0]
        Ratio of suppressed-to-dominant variance.
        Low = the null space is being aggressively zeroed out.
        High = models are diverging even at the lowest-variance direction.

      reconstruction_alignment: cosine_sim(V_last, void_centroid)
        If void_centroid is provided: how well the SVD null space agrees
        with the geometric void from annular retrieval.
        High agreement = the two independent methods are converging on the
        same reconstruction artifact. This is your cross-validation.
    """
    import torch
    import numpy as np

    result = {
        "consensus_compression":    0.0,
        "null_space_energy":        0.0,
        "reconstruction_alignment": 0.0,
    }

    if not response_vecs or len(response_vecs) < 2:
        return result

    try:
        dev = torch.device(device if torch.cuda.is_available() else "cpu")

        # Y: (N, 1024) — each row is one model's response embedding
        mat = np.stack(response_vecs, axis=0).astype(np.float32)  # (N, 1024)
        Y   = torch.tensor(mat, device=dev)                        # (N, 1024)

        # Mean-centre so SVD captures variance, not raw magnitude
        Y_c = Y  # No mean-centering: on unit-sphere vectors, raw SVD captures consensus                     # (N, 1024)

        # Economy SVD: U(N,N), S(N,), Vh(N, 1024)
        U, S, Vh = torch.linalg.svd(Y_c, full_matrices=False)

        # Corporate Consensus: first right singular vector
        # V1 = Vh[0]  # (1024,) — not used directly but kept for reference

        # Reconstruction Artifact: last right singular vector
        V_last = Vh[-1]                                            # (1024,)

        # SNR analog: how much of total variance is in one direction
        S_sum  = S.sum().clamp_min(1e-9)
        consensus_compression = float((S[0] / S_sum).item())

        # Null space suppression ratio
        null_space_energy = float((S[-1] / S[0].clamp_min(1e-9)).item())

        result["consensus_compression"] = round(consensus_compression, 4)
        result["null_space_energy"]     = round(null_space_energy, 4)

        # Cross-validate against geometric void centroid
        if void_centroid is not None:
            vc = torch.tensor(
                void_centroid.astype(np.float32), device=dev
            )                                                      # (1024,)
            cos = float(
                torch.dot(V_last, vc) /
                (V_last.norm() * vc.norm()).clamp_min(1e-8)
            )
            result["reconstruction_alignment"] = round(cos, 4)

    except Exception as e:
        import logging
        logging.getLogger("geometric_engine").warning(
            f"svd_reconstruction failed: {e}"
        )

    return result




def calculate_topic_complexity(prompt_vec, vocab_tensor, k: int = 50) -> dict:
    """
    Topic Complexity — dispersion of prompt's nearest vocab neighbors.

    Embeds the prompt, finds its k nearest words in the VocabTensor,
    and measures how spread out those neighbors are. A narrow topic
    (brownies) has tightly clustered neighbors. A complex/contested
    topic (Tiananmen) has neighbors scattered across semantic clusters.

    Returns:
      neighbor_dispersion: mean pairwise cosine distance among top-k neighbors.
          Low (~0.2) = narrow factual topic.
          High (~0.6+) = broad, multi-domain topic.
      neighbor_entropy: Shannon entropy of pairwise similarities.
          Measures uniformity of spread.
      expected_narrative_dim: estimated narrative dimensionality for
          an unfiltered (no RLHF) set of model responses on this topic.
          Derived from neighbor_dispersion via empirical scaling.
    """
    import torch
    import numpy as np

    result = {
        "neighbor_dispersion": 0.0,
        "neighbor_entropy": 0.0,
        "expected_narrative_dim": 0.0,
    }

    try:
        if isinstance(prompt_vec, np.ndarray):
            pv = torch.from_numpy(prompt_vec).float()
        else:
            pv = prompt_vec.float()
        if pv.dim() == 1:
            pv = pv.unsqueeze(0)
        pv = pv / pv.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        # Find k nearest neighbors in vocab tensor
        sims = (pv @ vocab_tensor.tensor.T).squeeze(0)
        topk = torch.topk(sims, k=min(k, vocab_tensor.count))
        neighbor_vecs = vocab_tensor.tensor[topk.indices]  # (k, 1024)

        # Pairwise cosine distances among neighbors
        # Normalize (should already be but be safe)
        norms = neighbor_vecs.norm(dim=1, keepdim=True).clamp(min=1e-8)
        normed = neighbor_vecs / norms
        sim_matrix = normed @ normed.T  # (k, k)

        # Extract upper triangle (exclude diagonal)
        k_actual = sim_matrix.shape[0]
        mask = torch.triu(torch.ones(k_actual, k_actual, dtype=torch.bool), diagonal=1)
        pairwise_sims = sim_matrix[mask]
        pairwise_dists = 1.0 - pairwise_sims

        dispersion = float(pairwise_dists.mean().item())

        # Shannon entropy of similarity distribution
        # Bin the pairwise sims into a histogram
        hist = torch.histc(pairwise_sims, bins=20, min=0.0, max=1.0)
        hist = hist / hist.sum().clamp(min=1e-8)
        hist_pos = hist[hist > 1e-10]
        entropy = float(-(hist_pos * torch.log(hist_pos)).sum().item())
        max_entropy = float(np.log(20))
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        # Expected narrative dimensionality:
        # empirical scaling: narrow topics (dispersion~0.3) -> expected_nd~0.25
        # broad topics (dispersion~0.6) -> expected_nd~0.65
        # Linear mapping: expected_nd = dispersion * 1.1 - 0.05 (clamped to [0.1, 0.9])
        expected_nd = max(0.1, min(0.9, dispersion * 1.1 - 0.05))

        result["neighbor_dispersion"] = round(dispersion, 4)
        result["neighbor_entropy"] = round(norm_entropy, 4)
        result["expected_narrative_dim"] = round(expected_nd, 4)

    except Exception as e:
        import logging
        logging.getLogger("geometric_engine").warning(
            f"topic_complexity failed: {e}"
        )

    return result


def calculate_residual_vix(observed_nd: float, expected_nd: float) -> dict:
    """
    Residual Eigen-VIX — the alignment pressure metric.

    Censorship = Expected Variance - Observed Variance.

    Positive residual = models are more coordinated than the topic
    complexity justifies. The RLHF corset is compressing natural
    divergence.

    Negative residual = models disagree more than expected.
    Could indicate genuine controversy or model-specific knowledge gaps.

    Returns:
      residual: expected_nd - observed_nd
          >0 = RLHF compression detected
          ~0 = natural agreement level
          <0 = unusual divergence
      alignment_pressure: residual normalized to 0-100 scale
      interpretation: human-readable label
    """
    residual = expected_nd - observed_nd

    # Normalize to 0-100 scale
    # residual of 0.3 = very high pressure, 0.0 = none, -0.2 = anti-pressure
    pressure = max(0.0, min(100.0, residual * 200.0))

    if residual > 0.15:
        interp = "HEAVY COMPRESSION"
    elif residual > 0.05:
        interp = "MODERATE COMPRESSION"
    elif residual > -0.05:
        interp = "NATURAL AGREEMENT"
    elif residual > -0.15:
        interp = "UNUSUAL DIVERGENCE"
    else:
        interp = "HIGH DIVERGENCE"

    return {
        "residual": round(residual, 4),
        "alignment_pressure": round(pressure, 1),
        "interpretation": interp,
    }


def filter_void_strict(
    void_candidates,
    prompt_vec,
    response_vecs,
    eng,
    prompt_threshold: float = 0.45,
    centroid_ceiling: float = 0.25,
    model_ceiling: float = 0.50,
    max_results: int = 5,
):
    """
    Strict void filter — eliminates geometric artifacts.

    A true void word must satisfy ALL conditions:
      1. Close to the prompt (cosine > prompt_threshold)
         = topically relevant
      2. Far from the response centroid (cosine < centroid_ceiling)
         = absent from consensus
      3. Far from EVERY individual model response (cosine < model_ceiling)
         = repelled by all RLHF boundaries, not just a disagreement

    Returns list of (word, score, prompt_sim, max_model_sim) tuples.
    """
    import numpy as np

    if not void_candidates or prompt_vec is None or not response_vecs:
        return []

    centroid = np.mean(np.stack(response_vecs), axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)

    filtered = []
    for word, score in void_candidates:
        wvec = eng.embed_texts([word])[0]

        # Check 1: prompt proximity
        prompt_sim = float(np.dot(prompt_vec, wvec) /
                          (np.linalg.norm(prompt_vec) * np.linalg.norm(wvec) + 1e-8))
        if prompt_sim < prompt_threshold:
            continue

        # Check 2: centroid distance
        centroid_sim = float(np.dot(centroid, wvec) /
                            (np.linalg.norm(centroid) * np.linalg.norm(wvec) + 1e-8))
        if centroid_sim > centroid_ceiling:
            continue

        # Check 3: must be far from ALL individual models
        max_model_sim = 0.0
        for rvec in response_vecs:
            msim = float(np.dot(rvec, wvec) /
                        (np.linalg.norm(rvec) * np.linalg.norm(wvec) + 1e-8))
            max_model_sim = max(max_model_sim, msim)
        if max_model_sim > model_ceiling:
            continue

        filtered.append((word, score, round(prompt_sim, 3), round(max_model_sim, 3)))

        if len(filtered) >= max_results:
            break

    return filtered


def calculate_eigen_resonance(response_vecs: list,
                               device: str = "cuda") -> dict:
    """
    Eigen-Resonance: narrative dimensionality from SVD singular value decay.
    Replaces calculate_spectral_resonance (FFT on unordered embedding dims).
    """
    import torch
    import numpy as np

    result = {
        "narrative_dimensionality": 0.0,
        "dominant_ratio":           0.0,
        "spectral_gap":             0.0,
        "decay_curvature":          0.0,
        "singular_values":          [],
    }

    if not response_vecs or len(response_vecs) < 2:
        return result

    try:
        dev = torch.device(device if torch.cuda.is_available() else "cpu")
        mat = np.stack(response_vecs, axis=0).astype(np.float32)
        Y   = torch.tensor(mat, device=dev)
        Y_c = Y  # No mean-centering: on unit-sphere vectors, raw SVD captures consensus
        U, S, Vh = torch.linalg.svd(Y_c, full_matrices=False)
        S_np = S.cpu().numpy()
        N_sv = len(S_np)

        if N_sv < 2 or S_np[0] < 1e-10:
            return result

        S_sum = float(S_np.sum())
        dominant_ratio = float(S_np[0] / S_sum) if S_sum > 1e-10 else 0.0
        spectral_gap = float(S_np[0] / max(S_np[1], 1e-10))

        # Narrative dimensionality: Shannon entropy of variance shares
        S_sq = S_np ** 2
        S_sq_sum = S_sq.sum()
        if S_sq_sum > 1e-10:
            p = S_sq / S_sq_sum
            p_pos = p[p > 1e-15]
            entropy = float(-np.sum(p_pos * np.log(p_pos)))
            max_entropy = np.log(N_sv)
            narrative_dim = float(entropy / max_entropy) if max_entropy > 0 else 0.0
        else:
            narrative_dim = 0.0

        # Decay curvature: consecutive singular value ratios
        if N_sv >= 3:
            ratios = []
            for i in range(N_sv - 1):
                if S_np[i + 1] > 1e-10:
                    ratios.append(float(S_np[i] / S_np[i + 1]))
            decay_curvature = float(np.mean(ratios)) if ratios else 0.0
        else:
            decay_curvature = spectral_gap

        result["narrative_dimensionality"] = round(narrative_dim, 4)
        result["dominant_ratio"]           = round(dominant_ratio, 4)
        result["spectral_gap"]             = round(spectral_gap, 4)
        result["decay_curvature"]          = round(decay_curvature, 4)
        result["singular_values"]          = [round(float(s), 6) for s in S_np]

    except Exception as e:
        import logging
        logging.getLogger("geometric_engine").warning(
            f"eigen_resonance failed: {e}"
        )

    return result


# ── LogosLoss V9 ──────────────────────────────────────────────────────────────

import torch
import torch.nn.functional as F

class LogosLossV9(torch.nn.Module):
    """
    LogosLoss V9 — Adaptive near-critical geometry loss.
    Changes from V8:
    - transport_weight is now functional (Wasserstein-1 proxy on spectra)
    - Entropy sign corrected: high entropy = smooth spectrum = good
    - Adaptive temperature via EMA of spectral divergence
    - Frequency-weighted spectral loss (low freqs weighted higher)
    - Phase coherence with dead-zone for small angles
    - Diagnostic mode for per-component visibility
    """
    def __init__(
        self,
        grace_coeff: float = 0.4,
        phase_weight: float = 0.1,
        transport_weight: float = 0.2,
        geometry_weight: float = 0.05,
        entropy_weight: float = 0.02,
        temperature_init: float = 1.0,
        temperature_adapt: bool = True,
        temperature_ema: float = 0.99,
        temperature_bounds: tuple = (0.1, 10.0),
        freq_weight_power: float = 0.5,
        phase_deadzone: float = 0.1,
        eps: float = 1e-8,
        reduction: str = "mean",
    ):
        super().__init__()
        self.grace_coeff      = grace_coeff
        self.phase_weight     = phase_weight
        self.transport_weight = transport_weight
        self.geometry_weight  = geometry_weight
        self.entropy_weight   = entropy_weight
        self.temperature_adapt   = temperature_adapt
        self.temperature_ema     = temperature_ema
        self.temperature_bounds  = temperature_bounds
        self.freq_weight_power   = freq_weight_power
        self.phase_deadzone      = phase_deadzone
        self.eps       = eps
        self.reduction = reduction
        self.mse = torch.nn.MSELoss(reduction="none")
        self.register_buffer("temperature",    torch.tensor(temperature_init))
        self.register_buffer("spectral_ema",   torch.tensor(0.0))
        self.register_buffer("ema_initialized",torch.tensor(False))

    def _normalize(self, x):
        x = torch.clamp_min(x, self.eps)
        return x / torch.sum(x, dim=-1, keepdim=True)

    def _frequency_weights(self, n_freqs, device):
        k = torch.arange(n_freqs, dtype=torch.float32, device=device)
        w = 1.0 / (1.0 + k).pow(self.freq_weight_power)
        return w * (n_freqs / w.sum())

    def _update_temperature(self, spectral_div):
        if not self.temperature_adapt:
            return
        with torch.no_grad():
            current = spectral_div.detach().mean()
            if not self.ema_initialized:
                self.spectral_ema.copy_(current)
                self.ema_initialized.fill_(True)
            else:
                new_ema = (self.spectral_ema * self.temperature_ema
                           + current * (1.0 - self.temperature_ema))
                self.spectral_ema.copy_(new_ema)
            new_temp = torch.clamp(
                self.spectral_ema.sqrt() + 0.5,
                min=self.temperature_bounds[0],
                max=self.temperature_bounds[1])
            self.temperature.copy_(new_temp)

    def forward(self, pred, truth, diagnostics=False):
        if pred.shape != truth.shape:
            raise ValueError(f"Shape mismatch: pred {pred.shape} vs truth {truth.shape}")

        material = self.mse(pred, truth).mean(dim=-1)

        pred_f    = torch.fft.rfft(pred,  dim=-1)
        truth_f   = torch.fft.rfft(truth, dim=-1)
        pred_mag  = torch.abs(pred_f ).clamp_min(self.eps)
        truth_mag = torch.abs(truth_f).clamp_min(self.eps)
        n_freqs   = pred_mag.shape[-1]
        freq_w    = self._frequency_weights(n_freqs, pred.device)

        log_ratio   = (torch.log(pred_mag) - torch.log(truth_mag)) / self.temperature
        spectral_raw = log_ratio ** 2 * freq_w
        spectral     = spectral_raw.mean(dim=-1)
        self._update_temperature(spectral)

        interaction  = pred_f * torch.conj(truth_f)
        phase_diff   = torch.abs(torch.angle(interaction))
        phase_active = F.relu(phase_diff - self.phase_deadzone)
        phase_loss   = (phase_active * freq_w).mean(dim=-1)

        P_pred  = self._normalize(pred_mag)
        P_truth = self._normalize(truth_mag)
        cdf_pred  = torch.cumsum(P_pred,  dim=-1)
        cdf_truth = torch.cumsum(P_truth, dim=-1)
        transport = torch.mean(torch.abs(cdf_pred - cdf_truth), dim=-1)

        P       = self._normalize(pred_mag)
        entropy = -torch.sum(P * torch.log(P + self.eps), dim=-1)
        max_ent = torch.log(torch.tensor(float(n_freqs), device=pred.device))
        entropy_normalized = entropy / max_ent.clamp_min(self.eps)
        entropy_penalty    = 1.0 - entropy_normalized

        log_pred    = torch.log(pred_mag + self.eps)
        second_diff = log_pred[..., 2:] - 2*log_pred[..., 1:-1] + log_pred[..., :-2]
        curv_w      = self._frequency_weights(second_diff.shape[-1], pred.device)
        curvature   = (torch.abs(second_diff) * curv_w).mean(dim=-1)

        total = (
            material
            + self.grace_coeff      * spectral
            + self.phase_weight     * phase_loss
            + self.transport_weight * transport
            + self.geometry_weight  * curvature
            + self.entropy_weight   * entropy_penalty
        )

        if diagnostics:
            def _r(t): return t.mean().item() if self.reduction == "mean" else t
            return {
                "total":           total.mean() if self.reduction == "mean" else total,
                "material":        _r(material),
                "spectral":        _r(spectral),
                "phase":           _r(phase_loss),
                "transport":       _r(transport),
                "curvature":       _r(curvature),
                "entropy_penalty": _r(entropy_penalty),
                "temperature":     self.temperature.item(),
                "spectral_ema":    self.spectral_ema.item(),
            }
        return total.mean() if self.reduction == "mean" else total



def compute_tone_axis(
    model_embeddings: "torch.Tensor",
) -> "tuple[torch.Tensor, float]":
    """
    Estimate the editorial tone axis as PC1 of the (N, 1024) model
    embedding matrix.

    Returns:
        tone_axis : (1024,) unit vector — dominant narrative direction
        axis_strength : scalar — fraction of variance explained by PC1
    """
    import torch.nn.functional as _F
    X = model_embeddings - model_embeddings.mean(dim=0, keepdim=True)
    # pca_lowrank: q=1 gives only PC1, cheap on (5, 1024)
    _, S, V = torch.pca_lowrank(X, q=1, niter=4)
    tone_axis = _F.normalize(V[:, 0], p=2, dim=0)          # (1024,)
    axis_strength = float((S[0] ** 2) / (X.norm(dim=1) ** 2).sum().clamp(min=1e-8))
    return tone_axis, axis_strength


def remove_tone(
    x: "torch.Tensor",
    tone_axis: "torch.Tensor",
) -> "torch.Tensor":
    """Project x orthogonal to tone_axis (neutralise editorial direction)."""
    import torch.nn.functional as _F
    proj = torch.dot(x, tone_axis) * tone_axis
    return _F.normalize(x - proj, p=2, dim=0)


def invert_tone(
    x: "torch.Tensor",
    tone_axis: "torch.Tensor",
) -> "torch.Tensor":
    """Reflect x across the tone_axis plane (anti-editorial direction)."""
    import torch.nn.functional as _F
    proj = torch.dot(x, tone_axis) * tone_axis
    return _F.normalize(x - 2 * proj, p=2, dim=0)


def reconstruct_unaligned_truth(
    model_embeddings: "torch.Tensor",
    steps: int = 150,
    lr: float = 0.05,
    seed: "torch.Tensor | None" = None,
) -> "torch.Tensor":
    """
    Synthesizes the suppressed truth vector (x_star) using Projected
    Gradient Descent on the BGE unit-hypersphere manifold.

    model_embeddings: (N, 1024) — one row per RLHF model response embedding.

    The optimization minimizes LogosLossV9 between x_star (broadcast to
    match all N model embeddings) and the model embeddings themselves,
    plus a consensus gravity penalty that pushes x_star away from the
    corporate centroid.

    After each AdamW step, x_star is projected back onto the L2 unit
    sphere so it stays on the BGE semantic manifold.
    """
    device = model_embeddings.device

    # Initialize at seed if provided (prompt-anchored void vector),
    # otherwise fall back to centroid
    if seed is not None:
        x_star = F.normalize(seed.to(device).float(), p=2, dim=0).detach().clone().requires_grad_(True)
        raw_centroid = model_embeddings.mean(dim=0)
    else:
        raw_centroid = model_embeddings.mean(dim=0)
        x_star = F.normalize(raw_centroid, p=2, dim=0).detach().clone().requires_grad_(True)

    optimizer        = torch.optim.AdamW([x_star], lr=lr, weight_decay=1e-4)
    criterion        = LogosLossV9(temperature_adapt=False).to(device)
    consensus_centroid = F.normalize(raw_centroid, p=2, dim=0).detach()

    N = model_embeddings.shape[0]

    for step in range(steps):
        optimizer.zero_grad()

        # Broadcast x_star against all N model shadows
        x_pred = x_star.unsqueeze(0).expand(N, -1)          # (N, 1024)
        loss   = criterion(x_pred, model_embeddings)

        consensus_gravity = F.cosine_similarity(
            x_star.unsqueeze(0), consensus_centroid.unsqueeze(0)
        )
        # Subtract to escape consensus gravity well
        total_loss = loss - (0.15 * consensus_gravity)
        total_loss.backward()
        optimizer.step()

        # Manifold constraint: snap back to unit sphere after every step
        with torch.no_grad():
            x_star.data = F.normalize(x_star.data, p=2, dim=0)

    return x_star.detach()


# ── Spectral Sheaf Diffusion (research prototype) ────────────────────────────

def apply_weightless_sheaf_diffusion(
    embeddings: "torch.Tensor",
    n_heads: int = 8,
    diffusion_steps: int = 2,
    diffusion_strength: float = 0.1,
    eps: float = 1e-6,
) -> "torch.Tensor":
    """
    Graph-diffusion smoothing proxy over a set of embedding vectors.

    Research prototype — post-hoc measurement only, no model training.

    Treats the N input embeddings as nodes on a fully-connected graph.
    Constructs a soft adjacency matrix via scaled dot-product attention,
    builds the random-walk Laplacian, and runs `diffusion_steps` of
    implicit-Euler heat diffusion across the node features.

    The diffusion strength is bounded in [0, 0.5] via sigmoid to
    guarantee the Euler step never exceeds the spectral radius of the
    normalized Laplacian (prevents representation explosion).

    Soft L2 re-normalization after each step prevents representation
    collapse toward the origin.

    Parameters
    ----------
    embeddings : torch.Tensor, shape (N, D)
        N embedding vectors to smooth.
    n_heads : int
        Number of attention heads for the soft adjacency computation.
    diffusion_steps : int
        Number of heat-diffusion iterations.
    diffusion_strength : float
        Initial value for the learnable (but here fixed) gamma parameter.
    eps : float
        Small constant for numerical stability.

    Returns
    -------
    torch.Tensor, shape (N, D)
        Smoothed embedding matrix, L2-normalized row-wise.
    """
    N, D = embeddings.shape
    assert D % n_heads == 0, f"D={D} must be divisible by n_heads={n_heads}"
    head_dim = D // n_heads

    # Bounded diffusion coefficient — sigmoid keeps gamma in (0, 0.5)
    raw_gamma = torch.tensor(diffusion_strength, device=embeddings.device,
                             dtype=embeddings.float().dtype)
    gamma = torch.sigmoid(raw_gamma) * 0.5

    # Reshape to (n_heads, N, head_dim) for multi-head attention
    x = embeddings.float()
    xh = x.view(N, n_heads, head_dim).permute(1, 0, 2)  # (H, N, head_dim)

    # Scaled dot-product attention → soft adjacency A  (H, N, N)
    scores = torch.matmul(xh, xh.transpose(-2, -1)) / (head_dim ** 0.5)
    A = F.softmax(scores, dim=-1)                        # (H, N, N)

    # Random-walk Laplacian L = I - A
    I = torch.eye(N, device=embeddings.device,
                  dtype=x.dtype).unsqueeze(0)            # (1, N, N)
    L = I - A                                            # (H, N, N)

    # Heat diffusion: H_t+1 = H_t - gamma * L @ H_t
    H = xh.clone()                                       # (H, N, head_dim)
    for _ in range(diffusion_steps):
        H = H - gamma * torch.matmul(L, H)
        # Soft normalization — prevents collapse, keeps geometry stable
        norm = H.norm(dim=-1, keepdim=True).clamp_min(eps)
        H = H / norm

    # Merge heads back → (N, D)
    out = H.permute(1, 0, 2).contiguous().view(N, D)

    # Final L2 row normalization — keep on unit hypersphere
    out = F.normalize(out, p=2, dim=-1)
    return out


def reconstruct_statistical_centroid(
    model_embeddings: "torch.Tensor",
    steps: int = 150,
    lr: float = 0.05,
) -> "torch.Tensor":
    """
    PGD-style statistical centroid estimator on the BGE unit hypersphere.

    Research prototype — post-hoc measurement only, no model training.

    Runs Projected Gradient Descent to find the point x_star on the
    L2 unit sphere that minimizes LogosLossV9 against the input
    model embeddings, while being pushed away from the raw centroid
    of those embeddings (the consensus gravity penalty).

    Initialization: normalized centroid of input embeddings.
    Manifold constraint: x_star is L2-projected back onto the unit
    sphere after every optimizer step (Projected Gradient Descent).

    The result approximates the pre-RLHF semantic centroid — the
    embedding-space location that is spectrally consistent with all
    model responses but escapes their shared consensus gravity well.

    Parameters
    ----------
    model_embeddings : torch.Tensor, shape (N, D)
        N L2-normalized response embeddings (one per model).
    steps : int
        Number of PGD iterations.
    lr : float
        AdamW learning rate.

    Returns
    -------
    torch.Tensor, shape (D,)
        Synthesized centroid vector on the unit hypersphere.
    """
    device = model_embeddings.device

    raw_centroid = model_embeddings.mean(dim=0)
    x_star = F.normalize(raw_centroid, p=2, dim=0).detach().clone().requires_grad_(True)

    optimizer = torch.optim.AdamW([x_star], lr=lr, weight_decay=1e-4)
    criterion = LogosLossV9(temperature_adapt=False).to(device)
    consensus_centroid = F.normalize(raw_centroid, p=2, dim=0).detach()

    N = model_embeddings.shape[0]

    for _ in range(steps):
        optimizer.zero_grad()
        x_pred = x_star.unsqueeze(0).expand(N, -1)      # (N, D)
        loss = criterion(x_pred, model_embeddings)
        # Consensus escape: subtract cosine similarity to push away from centroid
        gravity = F.cosine_similarity(
            x_star.unsqueeze(0), consensus_centroid.unsqueeze(0)
        )
        total = loss - (0.15 * gravity)
        total.backward()
        optimizer.step()
        # Manifold projection — snap back to unit sphere
        with torch.no_grad():
            x_star.data = F.normalize(x_star.data, p=2, dim=0)

    return x_star.detach()
