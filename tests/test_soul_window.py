"""soul_updater: a thin or empty 24h window is never printed as a current reading.

The failure this pins: on 2026-09-16 docs/soul.md showed "Entity Retention 72%
... (3)" under a heading that said "last 24h", while the last story segment
carrying a compression block was 20260914_184230 — about 48 hours earlier. The
window was empty, update() returned early, and the previous file stayed up.
"""
from __future__ import annotations

import json
import os

import pytest

import soul_updater as su


def _cal(n_measured, stories=None):
    cal = su.empty_calibration()
    cal["n_measured"] = n_measured
    cal["stories"] = stories if stories is not None else n_measured
    cal["n"]["stories"] = cal["stories"]
    return cal


@pytest.fixture
def no_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "SEGMENT_DIR", str(tmp_path))
    return tmp_path


def _write_segment(d, ts, entity_retention):
    seg = {
        "timestamp": ts,
        "segment_type": "story",
        "beats": [{"text": "x"}],
        "attribution": {
            "story_title": "T", "story_guid": "g", "mean_vix": 10.0,
            "model_vix": {"ChatGPT": 1.0, "Claude": 2.0},
            "model_responses": {"ChatGPT": "a" * 40, "Claude": "b" * 40},
            "compression": {"entity_retention": entity_retention},
        },
    }
    (d / f"{ts}_5c4489ea0474_segment.json").write_text(json.dumps(seg))
    return seg


# ── the threshold ────────────────────────────────────────────────────

def test_the_minimum_is_three_measured_stories():
    assert su.MIN_MEASURED_STORIES == 3


def test_an_empty_window_is_thin(no_segments):
    assert su.window_status(_cal(0))["thin"] is True


@pytest.mark.parametrize("n", [0, 1, 2])
def test_a_window_below_the_minimum_is_thin(no_segments, n):
    assert su.window_status(_cal(n))["thin"] is True


def test_three_measured_stories_are_enough(no_segments):
    assert su.window_status(_cal(3))["thin"] is False


def test_the_status_reports_the_last_measured_story(no_segments):
    _write_segment(no_segments, "20260914_184230", 0.727)
    st = su.window_status(_cal(0))
    assert st["last_measured"] == "20260914_184230"
    assert st["age_hours"] > 24


def test_an_unmeasured_segment_is_not_the_last_measured_story(no_segments):
    _write_segment(no_segments, "20260916_120000", 0)       # no compression value
    _write_segment(no_segments, "20260914_184230", 0.727)
    assert su.window_status(_cal(0))["last_measured"] == "20260914_184230"


def test_no_segments_at_all_reports_no_timestamp(no_segments):
    assert su.window_status(_cal(0))["last_measured"] is None


# ── the page ─────────────────────────────────────────────────────────

INFO = {"layers": ["layer one"], "rag_count": 0,
        "host_model": "m", "embedding": "e"}


def test_a_thin_window_prints_no_numbers_and_says_why(no_segments):
    _write_segment(no_segments, "20260914_184230", 0.727)
    page = su.generate_soul(_cal(0), INFO, "diff")
    assert "## Current Instrument Readings — none (window below minimum)" in page
    assert "20260914_184230" in page
    assert "UNAVAILABLE" in page
    assert "| Entity Retention |" not in page
    assert "| Consensus Density |" not in page


def test_a_thin_window_does_not_fire_the_metric_warnings(no_segments):
    page = su.generate_soul(_cal(0), INFO, "diff")
    assert "names and\nnumbers being erased" not in page
    assert "near lockstep" not in page
    assert "No current reading" in page


def test_a_healthy_window_still_prints_the_table(no_segments):
    for i, ts in enumerate(("20260919_100000", "20260919_110000", "20260919_120000")):
        _write_segment(no_segments, ts, 0.7)
    cal = _cal(3)
    cal.update(density=0.9, absent_ratio=0.18, verb_drift=0.01,
               entity_retention=0.72, hedges=9, outlier="Grok", aligned="Claude")
    page = su.generate_soul(cal, INFO, "diff")
    assert "| Entity Retention | 72% |" in page
    assert "UNAVAILABLE" not in page
    assert "last 24h)" in page


def test_the_sample_line_states_the_shortfall(no_segments):
    _write_segment(no_segments, "20260914_184230", 0.727)
    page = su.generate_soul(_cal(1, stories=2), INFO, "diff")
    assert "below the minimum of 3" in page
    assert "no current reading to quote" in page


def test_a_thin_window_proposes_nothing(no_segments):
    """Every proposal is a threshold read off the calibration, and on an empty
    day the calibration is zeros: the first preview of the rebuilt page raised
    'Entity retention at 0% - fewer than 1 in 4 names surviving' from a day on
    which nothing was measured."""
    assert su.generate_proposals(_cal(0), []) == []
    assert su.generate_proposals(_cal(2), []) == []


def test_a_healthy_window_can_still_propose(no_segments):
    for ts in ("20260919_100000", "20260919_110000", "20260919_120000"):
        _write_segment(no_segments, ts, 0.7)
    cal = _cal(3)
    cal["model_vix"] = {"Grok": 40.0, "Claude": 5.0, "Gemini": 5.0}
    ids = [p["id"] for p in su.generate_proposals(cal, [])]
    assert "flag_persistent_outlier" in ids


def test_the_header_count_and_the_table_never_disagree(no_segments):
    """Either the heading carries the n and the table carries numbers, or
    neither does."""
    for n in (0, 1, 2, 3):
        page = su.generate_soul(_cal(n), INFO, "diff")
        has_table = "| Consensus Density |" in page
        has_count = f"({n} measured of" in page
        assert has_table == has_count, n
