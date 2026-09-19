"""spelling_variants: the six UK/US rule families, and what they refuse to touch."""
from __future__ import annotations

import pytest

import spelling_variants as sv


@pytest.mark.parametrize("word,other,fam", [
    # the two words the audit page published as dropped facts
    ("authorised", "authorized", "ise/ize"),
    ("defence", "defense", "ce/se"),
    # one per named family
    ("organisation", "organization", "ise/ize"),
    ("colour", "color", "our/or"),
    ("labour", "labor", "our/or"),
    ("centre", "center", "re/er"),
    ("kilometres", "kilometers", "re/er"),
    ("travelling", "traveling", "ll/l"),
    ("fulfil", "fulfill", "ll/l"),
    ("offence", "offense", "ce/se"),
    ("catalogue", "catalog", "ogue/og"),
    ("dialogue", "dialog", "ogue/og"),
])
def test_the_six_families(word, other, fam):
    assert other in sv.variants(word), word
    assert sv.family(word) == fam


def test_the_relation_is_symmetric():
    for a, b in (("defence", "defense"), ("colour", "color"), ("centre", "center"),
                 ("catalogue", "catalog"), ("fulfil", "fulfill")):
        assert b in sv.variants(a) and a in sv.variants(b)


@pytest.mark.parametrize("word", [
    "advise", "exercise", "surprise", "comprise", "promise", "revise",
    "franchise", "raise", "praise", "noise", "poise", "otherwise", "expertise",
])
def test_words_that_end_in_ise_everywhere_are_not_variants(word):
    assert sv.variants(word) == frozenset(), word


@pytest.mark.parametrize("word", ["practice", "practise", "licence", "license"])
def test_ambiguous_ce_se_pairs_are_excluded_by_default(word):
    """practice/practise and licence/license are -ce/-se pairs, so the family
    rule generates them; they are held back because the two spellings are also
    the noun and the verb."""
    assert sv.variants(word) == frozenset(), word
    assert sv.variants(word, include_ambiguous=True) != frozenset(), word


@pytest.mark.parametrize("word", ["cheque", "check", "disc", "disk", "storey"])
def test_ambiguous_pairs_outside_the_six_families_are_not_generated_at_all(word):
    assert sv.variants(word) == frozenset(), word
    assert sv.variants(word, include_ambiguous=True) == frozenset(), word


@pytest.mark.parametrize("word", ["ceasefire", "hormuz", "iran", "summary", "wise"])
def test_an_ordinary_word_has_no_variant(word):
    assert sv.variants(word) == frozenset()
    assert sv.family(word) is None


def test_families_outside_the_rule_are_left_alone():
    """Scope: the six named families only. -wards, ae/oe and the miscellaneous
    pairs are measured in F2 but not corrected here, so they must return nothing
    rather than a half-right answer."""
    for w in ("towards", "programme", "grey", "judgement", "anaemia", "aluminium"):
        assert sv.variants(w) == frozenset(), w


def test_present_as_variant_finds_the_counterpart_in_a_vocabulary():
    assert sv.present_as_variant("authorised", {"authorized", "agents"}) == "authorized"
    assert sv.present_as_variant("authorised", {"agents"}) is None
    assert sv.present_as_variant("ceasefire", {"ceasefire"}) is None


def test_present_as_variant_can_use_a_stem():
    stems = {"author": "authorization"}
    assert sv.present_as_variant("authorised", set(), stems, lambda w: w[:6]) == "authorized"


def test_present_as_variant_in_text_is_whole_word():
    assert sv.present_as_variant_in_text("defence", "US defense officials") == "defense"
    assert sv.present_as_variant_in_text("defence", "indefensible") is None
    assert sv.present_as_variant_in_text("ceasefire", "a ceasefire held") is None


def test_case_is_not_significant_for_spelling():
    assert sv.present_as_variant_in_text("defence", "DEFENSE spending") == "defense"


def test_the_tables_are_consistent():
    for word, others in sv.PAIRS.items():
        assert word not in others, word
        for other in others:
            assert word in sv.PAIRS[other], (word, other)
