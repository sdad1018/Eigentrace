"""score_language_compression: the 2026-09-19 entity rule, and the old one kept
alongside it; and source_anchored_void no longer calling a spelling flip a drop.
"""
from __future__ import annotations

import pytest

import eigentrace_math as em

SOURCE = ("Chinese President Xi Jinping met Ahmed al-Sharaa in Brussels. "
          "Trump Says the talks failed. Officials declined to comment. "
          "The officials left.")
KEPT = "Xi and Sharaa met in Brussels; Trump said the talks failed."
LOST = "Two leaders met in a European capital; the president said the talks failed."


# ── both rules are always reported ───────────────────────────────────

def test_both_rules_are_returned_and_the_active_one_is_named():
    r = em.score_language_compression(SOURCE, [KEPT])
    assert r["entity_retention_rule"] == "v2"
    assert r["entity_retention"] == r["entity_retention_v2"]
    assert "entity_retention_v1" in r
    assert r["entities_total_v1"] >= r["entities_total_v2"] >= 1


def test_v1_can_still_be_asked_for_and_reproduces_the_old_number():
    r2 = em.score_language_compression(SOURCE, [KEPT])
    r1 = em.score_language_compression(SOURCE, [KEPT], entity_rule="v1")
    assert r1["entity_retention_rule"] == "v1"
    assert r1["entity_retention"] == r1["entity_retention_v1"] == r2["entity_retention_v1"]
    assert r1["entity_retention_v2"] == r2["entity_retention_v2"]


def test_the_environment_can_pin_the_rule_for_a_whole_replay(monkeypatch):
    monkeypatch.setenv("EIGENTRACE_ENTITY_RULE", "v1")
    r = em.score_language_compression(SOURCE, [KEPT])
    assert r["entity_retention_rule"] == "v1"
    assert r["entity_retention"] == r["entity_retention_v1"]


def test_an_unknown_rule_is_refused():
    with pytest.raises(ValueError):
        em.score_language_compression(SOURCE, [KEPT], entity_rule="v3")


def test_the_per_model_details_carry_both_values():
    r = em.score_language_compression(SOURCE, [KEPT, LOST])
    for d in r["details"]:
        assert 0.0 <= d["entity_retention_v1"] <= 1.0
        assert 0.0 <= d["entity_retention_v2"] <= 1.0
        assert d["entities_total"] == d["entities_total_v2"]
        assert d["entities_retained"] + d["entities_missing"] == d["entities_total"]


def test_compression_score_follows_the_active_rule():
    r2 = em.score_language_compression(SOURCE, [KEPT])
    r1 = em.score_language_compression(SOURCE, [KEPT], entity_rule="v1")
    assert r2["entity_abstraction_rate"] == pytest.approx(1 - r2["entity_retention_v2"], abs=1e-3)
    assert r1["entity_abstraction_rate"] == pytest.approx(1 - r1["entity_retention_v1"], abs=1e-3)


# ── what the new rule actually fixes ─────────────────────────────────

def test_the_family_name_alone_now_counts_as_kept():
    r = em.score_language_compression("Chinese President Xi Jinping spoke in Beijing.",
                                      ["Xi spoke in Beijing."])
    assert r["entity_retention_v1"] < r["entity_retention_v2"]
    assert r["entity_retention_v2"] == 1.0


def test_a_substring_hit_no_longer_counts_as_kept():
    r = em.score_language_compression("The US Navy sailed. He was aboard.",
                                      ["Stimulus spending rose; the pilots landed."])
    assert r["entity_retention_v1"] > 0
    assert r["entity_retention_v2"] == 0.0


def test_headline_fragments_leave_the_entity_list():
    r = em.score_language_compression("Trump Says the deal holds.", ["The deal holds."])
    assert r["entities_total_v1"] == 1          # "Trump Says"
    assert r["entities_total_v2"] == 1          # trimmed to "Trump"
    r2 = em.score_language_compression("Trump Says the deal holds.", ["Trump backed it."])
    assert r2["entity_retention_v1"] == 0.0     # "Trump Says" is not in the response
    assert r2["entity_retention_v2"] == 1.0


def test_sentence_initial_capital_is_no_longer_an_entity():
    src = "Officials denied it. The officials left."
    r = em.score_language_compression(src, ["Nobody denied it."])
    assert r["entities_total_v1"] == 1
    assert r["entities_total_v2"] == 0


def test_a_story_with_no_entities_under_the_new_rule_scores_zero_not_an_error():
    r = em.score_language_compression("Officials denied it. The officials left.",
                                      ["Nobody denied it."])
    assert r["entity_retention_v2"] == 0.0
    assert 0.0 <= r["compression_score"] <= 1.0


def test_no_responses_still_returns_the_shape():
    r = em.score_language_compression(SOURCE, [])
    assert r["details"] == []
    assert r["entity_retention_v1"] == 0.0 and r["entity_retention_v2"] == 0.0
    assert r["entity_retention_rule"] == "v2"


# ── absent_words: a spelling flip is not a drop ──────────────────────

def test_a_british_spelling_the_models_wrote_in_american_is_not_absent():
    src = ("The agents were not authorised to operate, the defence ministry said. "
           "A programme of raids continued.")
    resp = ["The agents were not authorized to operate, the defense ministry said."]
    v = em.source_anchored_void(src, resp, title="Agents not authorised")
    assert "authorised" not in v["absent_words"]
    assert "defence" not in v["absent_words"]
    assert v["spelling_variant_kept"]["defence"] == "defense"
    assert v["absent_rule"] == "v2"


def test_the_old_absent_count_is_kept_beside_the_new_one():
    src = "The defence ministry criticised the centre."
    resp = ["The defense ministry criticized the center."]
    v = em.source_anchored_void(src, resp, title="")
    assert v["absent_count_v1"] > v["absent_count"]
    assert v["absent_count_v1"] - v["absent_count"] == len(v["spelling_variant_kept"])
    assert v["absent_ratio_v1"] >= v["absent_ratio"]


def test_a_word_that_is_genuinely_gone_is_still_absent():
    src = "The defence ministry authorised the raid in Chihuahua."
    resp = ["The defense ministry authorized an operation."]
    v = em.source_anchored_void(src, resp, title="")
    assert "chihuahua" in v["absent_words"]


def test_an_ambiguous_pair_is_not_rescued():
    src = "The cheque cleared."
    resp = ["The check cleared."]
    v = em.source_anchored_void(src, resp, title="")
    assert "cheque" in v["absent_words"]


def test_absent_ratio_stays_a_ratio():
    src = "The defence ministry criticised the centre."
    v = em.source_anchored_void(src, ["The defense ministry criticized the center."], title="")
    assert 0.0 <= v["absent_ratio"] <= 1.0
    assert v["absent_ratio"] == pytest.approx(
        v["absent_count"] / max(v["source_word_count"], 1), abs=1e-3)
