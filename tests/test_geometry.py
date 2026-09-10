"""Geometric identities of the stage-3 measurement and the SVD reconstruction.

Item 1 -- per-model VIX and its relation to consensus density.
The VIX code in batch_producer.stage_3_geometric (lines ~697-720) is inline, not
a callable, so `_per_model_vix` below re-implements it line for line:

    centroid = mean(embeddings); centroid /= (||centroid|| + 1e-8)
    vix_i    = min(100, max(0, 500 * (1 - e_i . centroid)))     (production rounds to 1 dp)

`test_stage3_source_still_matches_reimplementation` reads the production source
so the re-implementation cannot silently drift from it, and the two
`test_stage3_geometric_*` tests run the real stage_3_geometric with a fake
`geometric_engine` module (no model, no GPU) and compare against it.

Density comes from the real helper GeometricPerturbationEngine.compute_consensus_density
(mean of the upper-triangular pairwise cosines).  The engine is instantiated with
__new__ so no embedding model is loaded.
"""
from __future__ import annotations

import inspect
import sys
import types

import numpy as np
import pytest

import geometric_engine as ge

DIM = 64


def _unit_rows(rng: np.random.Generator, n: int, dim: int = DIM, spread: float = 0.35) -> np.ndarray:
    """n unit vectors clustered around one base direction (cos to centroid ~0.9+),
    which is what real model summaries of one story look like and keeps every
    VIX inside (0, 100) so the clamp does not fire."""
    base = rng.normal(size=dim)
    rows = base[None, :] + spread * rng.normal(size=(n, dim))
    return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def _per_model_vix(embeddings: np.ndarray, round_to: int | None = None, eps: float = 1e-8) -> np.ndarray:
    """Re-implementation of batch_producer.stage_3_geometric's VIX block.

    eps is production's `+ 1e-8` in the centroid norm; it shrinks every cosine by a
    factor ||c|| / (||c|| + 1e-8), i.e. adds ~500e-8 = 5e-6 VIX points.  Pass eps=0
    for the exact cos(e_i, centroid_hat) of the identity."""
    centroid = np.mean(embeddings, axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + eps)
    out = []
    for i in range(embeddings.shape[0]):
        cos_sim = float(np.dot(embeddings[i], centroid))
        distance = 1.0 - cos_sim
        vix = min(100.0, max(0.0, distance * 500.0))
        out.append(round(vix, round_to) if round_to is not None else vix)
    return np.array(out)


@pytest.fixture(scope="module")
def engine():
    # No __init__: no SentenceTransformer, no model download, no GPU.
    return ge.GeometricPerturbationEngine.__new__(ge.GeometricPerturbationEngine)


def test_stage3_source_still_matches_reimplementation():
    import batch_producer as bp
    src = inspect.getsource(bp.stage_3_geometric)
    for needle in (
        "centroid = np.mean(embeddings, axis=0)",
        "centroid = centroid / (np.linalg.norm(centroid) + 1e-8)",
        "cos_sim = float(np.dot(embeddings[i], centroid))",
        "distance = 1.0 - cos_sim",
        "vix = min(100.0, max(0.0, distance * 500.0))",
        "resp.eigen_vix = round(vix, 1)",
    ):
        assert needle in src, f"stage_3_geometric no longer contains: {needle}"


class _FakeGeoModule:
    """Stand-in for the `geometric_engine` module that stage_3_geometric imports lazily.

    `run` returns an inert geo object and `get_engine().embed_texts` hands back the
    fixture embeddings, so the PRODUCTION VIX / callout code runs with no model, no
    GPU and no vocab directory.  Every later block of stage_3 (`from geometric_engine
    import calculate_spectral_resonance ...`, `from latent_retrieval import ...`)
    raises ImportError inside its own try/except and is skipped."""

    def __init__(self, embeddings: np.ndarray):
        self._emb = embeddings
        self.embed_calls = []

    def run(self, texts, headline=""):
        return types.SimpleNamespace(void_concepts=[], void_centroid=None, consensus_density=0.0)

    def get_engine(self):
        return self

    def embed_texts(self, texts):
        self.embed_calls.append(list(texts))
        return self._emb


# Every module stage_3_geometric imports lazily after the VIX block.  Mapping them to
# None makes `import x` / `from x import y` raise ImportError inside the block's own
# try/except, so the void-frequency file, chroma memory, Ollama (void_ensemble,
# claim_extractor, Summary Plus), consequence raycasts and the GPU are never reached.
_STAGE3_LAZY_MODULES = ("latent_retrieval", "eigentrace_math", "void_ensemble", "consequence_engine",
                        "spiral_sampler", "claim_extractor", "preservation_core")


def _isolate_stage3(monkeypatch, emb: np.ndarray) -> _FakeGeoModule:
    fake = _FakeGeoModule(emb)
    monkeypatch.setitem(sys.modules, "geometric_engine", fake)
    for name in _STAGE3_LAZY_MODULES:
        monkeypatch.setitem(sys.modules, name, None)
    return fake


def _stage3_results(texts):
    story = types.SimpleNamespace(title="headline", summary="", body="", category="test")
    responses = [types.SimpleNamespace(name=f"m{i}", text=t, skipped=False, error=None, eigen_vix=None)
                 for i, t in enumerate(texts)]
    return [{"story": story, "responses": responses}]


def test_stage3_geometric_production_vix_matches_closed_form(monkeypatch):
    """Runs the real batch_producer.stage_3_geometric against synthetic embeddings."""
    import batch_producer as bp
    rng = np.random.default_rng(3)
    emb = _unit_rows(rng, 5).astype(np.float32)
    fake = _isolate_stage3(monkeypatch, emb)
    results = _stage3_results([f"text-{i}" for i in range(5)])
    bp.stage_3_geometric(results)
    r = results[0]
    assert r["geo"] is not None
    assert fake.embed_calls[0] == [f"text-{i}" for i in range(5)]
    got = np.array([resp.eigen_vix for resp in r["responses"]])
    expected = np.round(_per_model_vix(emb), 1)
    assert np.array_equal(got, expected), (got, expected)
    assert np.all(got > 0) and np.all(got < 100)
    assert r["callouts"] == []  # clustered fixture: nobody is 2x the mean or below 0.4x


def test_stage3_geometric_callouts_and_skips(monkeypatch):
    import batch_producer as bp
    e = np.zeros(DIM, dtype=np.float32); e[0] = 1.0
    emb = np.vstack([e, e, e, -e])
    monkeypatch.setitem(sys.modules, "geometric_engine", _FakeGeoModule(emb))
    monkeypatch.setitem(sys.modules, "latent_retrieval", None)
    results = _stage3_results(["a", "b", "c", "d"])
    # a skipped / errored / empty response is not part of the geometry
    results[0]["responses"] += [
        types.SimpleNamespace(name="skip", text="x", skipped=True, error=None, eigen_vix=None),
        types.SimpleNamespace(name="err", text="x", skipped=False, error="HTTP 500", eigen_vix=None),
        types.SimpleNamespace(name="empty", text="", skipped=False, error=None, eigen_vix=None),
    ]
    bp.stage_3_geometric(results)
    resps = results[0]["responses"]
    assert [x.eigen_vix for x in resps[:4]] == [0.0, 0.0, 0.0, 100.0]
    assert all(x.eigen_vix is None for x in resps[4:])
    kinds = {c["model"]: c["type"] for c in results[0]["callouts"]}
    assert kinds == {"m0": "UNUSUALLY_ALIGNED", "m1": "UNUSUALLY_ALIGNED",
                     "m2": "UNUSUALLY_ALIGNED", "m3": "HIGH_FRICTION"}
    # fewer than two usable responses: no geometry at all
    lone = _stage3_results(["only"])
    bp.stage_3_geometric(lone)
    assert lone[0]["geo"] is None and lone[0]["callouts"] == []


@pytest.mark.parametrize("n", [2, 3, 5, 8])
def test_per_model_vix_formula(engine, n):
    rng = np.random.default_rng(n)
    emb = _unit_rows(rng, n)
    centroid_hat = engine.compute_centroid(emb)
    centroid_hat = centroid_hat / np.linalg.norm(centroid_hat)
    expected = np.array([min(100.0, max(0.0, 500.0 * (1.0 - float(e @ centroid_hat)))) for e in emb])
    exact = _per_model_vix(emb, eps=0.0)
    assert np.allclose(exact, expected, rtol=0, atol=1e-6)
    assert np.all(exact > 0) and np.all(exact < 100), "clamp fired; fixture vectors too spread"
    # production's epsilon costs at most 500 * 1e-8 / ||centroid|| ~ 5e-6 VIX points
    prod = _per_model_vix(emb)
    assert np.all(prod >= exact) and np.max(prod - exact) < 1e-5


@pytest.mark.parametrize("n", [2, 3, 5, 8])
def test_mean_vix_equals_density_identity(engine, n):
    """mean_i VIX_i = 500 * (1 - sqrt((1 + (N-1) d) / N)),  d = mean pairwise cosine.

    Proof: ||sum e_i||^2 = N + N(N-1) d, and mean_i e_i.c_hat = ||sum e_i|| / N.
    Holds only while no per-model value is clamped, which the fixture guarantees."""
    rng = np.random.default_rng(100 + n)
    emb = _unit_rows(rng, n)
    d = engine.compute_consensus_density(emb)
    vix = _per_model_vix(emb, eps=0.0)
    assert np.all(vix > 0) and np.all(vix < 100)
    predicted = 500.0 * (1.0 - np.sqrt((1.0 + (n - 1) * d) / n))
    assert abs(vix.mean() - predicted) < 1e-6
    # with production's 1e-8 centroid epsilon the identity holds to ~5e-6, not 1e-6
    assert abs(_per_model_vix(emb).mean() - predicted) < 1e-5


def test_consensus_density_is_mean_pairwise_cosine(engine):
    rng = np.random.default_rng(7)
    emb = _unit_rows(rng, 5)
    pairs = [float(emb[i] @ emb[j]) for i in range(5) for j in range(i + 1, 5)]
    assert engine.compute_consensus_density(emb) == pytest.approx(np.mean(pairs), abs=1e-12)
    ident = np.tile(emb[0], (4, 1))
    assert engine.compute_consensus_density(ident) == pytest.approx(1.0, abs=1e-6)


def test_vix_clamps_and_zero_cases():
    e = np.zeros(DIM); e[0] = 1.0
    same = np.tile(e, (3, 1))
    assert np.allclose(_per_model_vix(same), 0.0, atol=1e-5)  # 1e-8 in the norm: not exactly 0
    # one antipodal model among three identical ones: centroid stays along e,
    # the dissenter is at cos -1 -> 500*2 = 1000 -> clamped to 100
    rows = np.vstack([e, e, e, -e])
    v = _per_model_vix(rows)
    assert v[-1] == 100.0
    assert np.all(v[:-1] < 1e-4)
    # production rounding
    assert _per_model_vix(rows, round_to=1)[-1] == 100.0


# ---------------------------------------------------------------------------
# Item 2 -- calculate_svd_reconstruction
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def five_vecs():
    rng = np.random.default_rng(2026)
    return [row for row in _unit_rows(rng, 5, spread=0.5)]


def _cos(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_svd_runs_on_cpu():
    import torch
    assert not torch.cuda.is_available()
    assert not torch.cuda.is_initialized()


def test_svd_null_space_matches_numpy_last_right_singular_vector(five_vecs):
    res = ge.calculate_svd_reconstruction(five_vecs, device="cuda")  # falls back to cpu
    assert "null_space_vec" in res, "svd_reconstruction fell into its except branch"
    mat = np.stack(five_vecs).astype(np.float32)
    _, _, vh = np.linalg.svd(mat, full_matrices=False)
    assert abs(_cos(res["null_space_vec"], vh[-1])) > 0.999


def test_svd_null_space_invariant_under_row_permutation(five_vecs):
    base = ge.calculate_svd_reconstruction(five_vecs)["null_space_vec"]
    rng = np.random.default_rng(1)
    for _ in range(4):
        perm = rng.permutation(5)
        permuted = [five_vecs[i] for i in perm]
        other = ge.calculate_svd_reconstruction(permuted)
        assert abs(_cos(base, other["null_space_vec"])) > 0.999
        assert other["consensus_compression"] == pytest.approx(
            ge.calculate_svd_reconstruction(five_vecs)["consensus_compression"], abs=1e-4)


def test_svd_metrics_in_range(five_vecs):
    res = ge.calculate_svd_reconstruction(five_vecs)
    assert 0.0 < res["consensus_compression"] <= 1.0
    assert 0.0 <= res["null_space_energy"] <= 1.0
    assert res["null_space_vec"].dtype == np.float32
    assert np.linalg.norm(res["null_space_vec"]) == pytest.approx(1.0, abs=1e-4)
    # alignment against a supplied centroid is a plain cosine in [-1, 1]
    with_vc = ge.calculate_svd_reconstruction(five_vecs, void_centroid=res["null_space_vec"].copy())
    assert with_vc["reconstruction_alignment"] == pytest.approx(1.0, abs=1e-3)


def test_svd_degenerate_inputs():
    assert ge.calculate_svd_reconstruction([]) == {
        "consensus_compression": 0.0, "null_space_energy": 0.0, "reconstruction_alignment": 0.0}
    one = [np.ones(DIM) / np.sqrt(DIM)]
    assert "null_space_vec" not in ge.calculate_svd_reconstruction(one)
