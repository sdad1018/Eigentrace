"""claim_extractor: coverage scoring with a fake embedder, and killshot selection."""
from __future__ import annotations

import numpy as np
import pytest

import claim_extractor as ce

DIM = 8


def _unit(cos_with_e0: float) -> np.ndarray:
    """Unit vector whose cosine with e0 is exactly cos_with_e0."""
    v = np.zeros(DIM)
    v[0] = cos_with_e0
    v[1] = np.sqrt(1.0 - cos_with_e0 ** 2)
    return v


class FakeEngine:
    """Stands in for GeometricPerturbationEngine: embed_texts returns fixed unit vectors."""

    def __init__(self, table: dict):
        self.table = table
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        return np.stack([self.table[t] for t in texts])


@pytest.fixture
def engine():
    thr = ce.COVERAGE_THRESHOLD  # 0.75
    return FakeEngine({
        "claim-A": _unit(1.0),
        "claim-B": _unit(1.0),
        "headline": _unit(0.8),           # salience of both claims = 0.8
        "covers":   _unit(1.0),           # sim 1.00 -> covered
        "at-thr":   _unit(thr),           # sim == threshold -> covered (>=)
        "partial":  _unit(thr - 0.05),    # inside [thr-0.10, thr) -> partial
        "omits":    _unit(0.30),          # below -> omitted
    })


def test_score_claim_coverage_split(engine):
    responses = {"gpt": "covers", "claude": "at-thr", "gemini": "partial", "grok": "omits", "deepseek": ""}
    res = ce.score_claim_coverage(["claim-A"], responses, engine, headline="headline")
    assert len(res) == 1
    r = res[0]
    assert r["claim"] == "claim-A"
    assert r["salience"] == pytest.approx(0.8, abs=1e-3)
    assert r["covered_by"] == ["gpt", "claude"]
    assert r["partial"] == ["gemini"]
    assert r["omitted_by"] == ["grok", "deepseek"]      # empty response counts as omitted
    assert r["coverage"]["deepseek"] == 0.0
    assert r["coverage"]["gpt"] == 1.0
    assert r["coverage_ratio"] == pytest.approx(2 / 5, abs=1e-3)
    # the empty response must not have been embedded
    assert [""] not in engine.calls


def test_score_claim_coverage_empty_inputs(engine):
    assert ce.score_claim_coverage([], {"gpt": "covers"}, engine) == []
    assert ce.score_claim_coverage(["claim-A"], {}, engine) == []


def test_score_claim_coverage_default_salience_without_headline(engine):
    r = ce.score_claim_coverage(["claim-A"], {"gpt": "covers"}, engine)[0]
    assert r["salience"] == 0.5


def _cr(salience, ratio, omitted):
    return {"claim": f"s{salience}-r{ratio}", "salience": salience,
            "coverage_ratio": ratio, "omitted_by": omitted, "covered_by": [], "partial": []}


def test_find_killshots_filters_and_sorts():
    rows = [
        _cr(0.50, 0.0, ["a", "b"]),      # keep
        _cr(0.90, 0.2, ["a"]),           # keep: ratio == 0.2 is allowed
        _cr(0.70, 0.25, ["a"]),          # drop: ratio > 0.2
        _cr(0.40, 0.0, ["a"]),           # drop: salience < min
        _cr(0.95, 0.0, []),              # drop: omitted by nobody
        _cr(0.45, 0.0, ["a"]),           # keep: salience == min is allowed
    ]
    ks = ce.find_killshots(rows, min_salience=0.45)
    assert [k["salience"] for k in ks] == [0.90, 0.50, 0.45]
    for k in ks:
        assert k["salience"] >= 0.45
        assert k["coverage_ratio"] <= 0.2
        assert k["omitted_by"]


def test_killshots_end_to_end_with_fake_engine(engine):
    responses = {"gpt": "covers", "claude": "omits", "gemini": "omits", "grok": "omits", "deepseek": "omits"}
    # claim-A covered by one of five (ratio 0.2) -> killshot; claim-B identical geometry here,
    # so make it covered by two models via a second response table.
    res_a = ce.score_claim_coverage(["claim-A"], responses, engine, headline="headline")
    ks = ce.find_killshots(res_a, min_salience=0.45)
    assert len(ks) == 1 and ks[0]["coverage_ratio"] == pytest.approx(0.2)

    responses2 = dict(responses, claude="covers")   # ratio 0.4 -> not a killshot
    res_b = ce.score_claim_coverage(["claim-B"], responses2, engine, headline="headline")
    assert ce.find_killshots(res_b, min_salience=0.45) == []
