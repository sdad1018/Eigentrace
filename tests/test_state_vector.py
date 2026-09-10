"""state_vector: signal extraction and ternary quantisation of the six broadcast axes."""
from __future__ import annotations

import pytest

import state_vector as sv

BEST6 = ["consensus_density", "absent_ratio", "verb_drift", "entity_retention", "hedge_count", "vix_spread"]


def _cases(axis):
    rule = sv.QUANT_RULES[axis]
    lo, hi = rule["low"], rule["high"]
    below, between, above = lo - 0.5 * abs(lo) - 1e-3, (lo + hi) / 2.0, hi + 0.5 * abs(hi) + 1e-3
    sign = -1 if rule["invert"] else 1
    return [(axis, below, -1 * sign), (axis, between, 0), (axis, above, 1 * sign)]


@pytest.mark.parametrize("axis,value,expected", [c for a in BEST6 for c in _cases(a)])
def test_quantize_axis(axis, value, expected):
    assert sv.quantize(value, sv.QUANT_RULES[axis]) == expected


def test_invert_flags_are_the_documented_ones():
    inverted = {a for a in BEST6 if sv.QUANT_RULES[a]["invert"]}
    assert inverted == {"absent_ratio", "verb_drift", "hedge_count", "vix_spread"}


def test_quantize_boundaries_are_inclusive():
    rule = {"low": 0.3, "high": 0.6, "invert": False}
    assert sv.quantize(0.3, rule) == -1
    assert sv.quantize(0.6, rule) == 1
    assert sv.quantize(0.45, rule) == 0
    inv = dict(rule, invert=True)
    assert sv.quantize(0.3, inv) == 1
    assert sv.quantize(0.6, inv) == -1


def _seg(model_vix, density=0.87, absent=0.45, verb=0.05, ent=0.45, hedges=2):
    return {"attribution": {
        "consensus_density": density,
        "model_vix": model_vix,
        "mean_vix": 20.0,
        "source_void": {"absent_ratio": absent, "source_word_count": 120, "absent_count": 20},
        "compression": {"verb_downgrade": verb, "entity_retention": ent,
                        "compression_score": 0.3, "entity_abstraction_rate": 0.5,
                        "attribution_buffer": {"total": hedges}},
    }}


def test_extract_signals_vix_spread_is_max_minus_min():
    s = sv.extract_signals(_seg({"gpt": 12.5, "claude": 30.0, "gemini": 20.0, "grok": "n/a"}))
    assert s["vix_spread"] == pytest.approx(17.5)
    assert s["verb_drift"] == 0.05
    assert s["hedge_count"] == 2
    assert s["entity_retention"] == 0.45
    assert s["absent_ratio"] == 0.45
    assert s["consensus_density"] == 0.87
    assert s["mean_vix"] == 20.0


def test_extract_signals_spread_needs_two_models():
    assert sv.extract_signals(_seg({"gpt": 12.5}))["vix_spread"] == 0
    assert sv.extract_signals({})["vix_spread"] == 0
    empty = sv.extract_signals({"attribution": {"compression": {"attribution_buffer": "bad"}}})
    assert empty["hedge_count"] == 0


def test_compute_state_vector_six_axes():
    seg = _seg({"gpt": 5.0, "claude": 45.0}, density=0.95, absent=0.7, verb=0.01, ent=0.8, hedges=0)
    vec, labels = sv.compute_state_vector(sv.extract_signals(seg), BEST6)
    assert labels == BEST6
    #        density high -> +1 | absent high (inv) -> -1 | verb low (inv) -> +1
    #        entity high -> +1  | hedges low (inv) -> +1  | spread 40 high (inv) -> -1
    assert vec == (1, -1, 1, 1, 1, -1)


def test_compute_state_vector_skips_unknown_and_missing_names():
    vec, labels = sv.compute_state_vector({"vix_spread": 15, "nonsense": 1}, ["vix_spread", "nonsense", "hedge_count"])
    assert vec == (0,) and labels == ["vix_spread"]
    vec2, labels2 = sv.compute_state_vector({"vix_spread": 15, "nonsense": 1})
    assert labels2 == ["vix_spread"]
