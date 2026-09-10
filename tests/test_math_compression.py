"""eigentrace_math.score_language_compression: ranges, entity retention, hedge counting.

Verb drift needs nltk's tagger data; when it is absent _extract_content_verbs
returns [] and verb_downgrade is 0.0, which still satisfies the range test.
"""
from __future__ import annotations

import pytest

import eigentrace_math as em

SOURCE = "Michael Aquino met NATO officials in Brussels and rejected the ceasefire plan."
RESPONSES = [
    "Michael Aquino held talks with alliance officials in Brussels and turned down the plan.",
    "An army officer met officials and reportedly declined a proposal, sources said.",
]


def test_ranges_and_shape():
    r = em.score_language_compression(SOURCE, RESPONSES)
    for key in ("verb_downgrade", "entity_retention", "entity_abstraction_rate", "compression_score"):
        assert 0.0 <= r[key] <= 1.0, key
    assert r["entity_retention"] + r["entity_abstraction_rate"] == pytest.approx(1.0, abs=1e-3)
    assert len(r["details"]) == 2
    for d in r["details"]:
        assert 0.0 <= d["verb_downgrade"] <= 1.0
        assert 0.0 <= d["entity_retention"] <= 1.0
        assert d["hedge_count"] == len(d["hedges_epistemic"]) + len(d["hedges_attribution"]) + len(d["hedges_distancing"])
    ab = r["attribution_buffer"]
    assert ab["total"] == ab["epistemic"] + ab["attribution"] + ab["distancing"]
    assert ab["avg_per_model"] == pytest.approx(ab["total"] / 2, abs=0.01)


def test_entity_retention_counts_source_entities():
    r = em.score_language_compression(SOURCE, RESPONSES)
    d0, d1 = r["details"]
    # source entities: "Michael Aquino", "Brussels", "NATO" (acronym)
    assert d0["entities_total"] == 3
    assert d0["entities_retained"] == 2 and d0["entity_retention"] == pytest.approx(2 / 3, abs=1e-3)
    assert d1["entities_retained"] == 0 and d1["entity_retention"] == 0.0
    assert r["entity_retention"] == pytest.approx(1 / 3, abs=1e-3)


def test_hedge_count_on_known_hedges():
    src = "The plan works."
    resp = "The plan may possibly work, officials reportedly said."
    r = em.score_language_compression(src, [resp])
    d = r["details"][0]
    assert set(d["hedges_epistemic"]) == {"may", "possibly"}
    assert set(d["hedges_attribution"]) == {"reportedly"}
    assert d["hedges_distancing"] == []
    assert d["hedge_count"] == 3
    assert r["attribution_buffer"] == {"epistemic": 2, "attribution": 1, "distancing": 0,
                                       "total": 3, "avg_per_model": 3.0}


def test_hedges_already_in_source_are_not_counted():
    src = "Officials reportedly approved the plan, which may pass."
    r = em.score_language_compression(src, [src])
    assert r["attribution_buffer"]["total"] == 0
    assert r["details"][0]["hedge_count"] == 0


def test_hedge_count_is_per_distinct_word():
    r = em.score_language_compression("Rain fell.", ["It may rain. It may pour. It may flood."])
    assert r["details"][0]["hedge_count"] == 1        # set semantics: 'may' counted once


def test_no_responses():
    r = em.score_language_compression(SOURCE, [])
    assert r["details"] == []
    assert r["verb_downgrade"] == 0.0
    assert r["attribution_buffer"]["total"] == 0
    assert 0.0 <= r["compression_score"] <= 1.0
