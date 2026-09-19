"""name_key: the family key, the presence test, and the entity filter.

Every case here is a failure mode one of the September 2026 audits measured on
disk, so a regression to the old rule fails a named assertion rather than a
number.
"""
from __future__ import annotations

import pytest

import name_key as nk


# ── the key ──────────────────────────────────────────────────────────

def test_family_first_name_keys_on_the_family_token_not_the_last():
    # the bug in one line: the old rule produced "Jinping"
    assert nk.family_key("Xi Jinping") == "Xi"
    assert "Xi Jinping".split()[-1] == "Jinping"


def test_title_prefixed_run_still_keys_on_the_family_token():
    # a first-token rule would return "Chinese" here; the registered map does not
    assert nk.family_key("Chinese President Xi Jinping") == "Xi"
    assert nk.family_key("President Xi Jinping") == "Xi"


def test_western_name_keys_on_the_last_token():
    assert nk.family_key("Donald Trump") == "Trump"
    assert nk.family_key("President Donald Trump") == "Trump"
    assert nk.family_key("Benjamin Netanyahu") == "Netanyahu"


@pytest.mark.parametrize("surface,key", [
    ("Ahmed al-Sharaa", "Sharaa"),
    ("Bashar al-Assad", "Assad"),
    ("Abdel Fattah el-Sisi", "Sisi"),
    ("Itamar Ben-Gvir", "Gvir"),
    ("Ali Al Salem", "Salem"),
    ("Ursula von der Leyen", "Leyen"),
    ("Tamim bin Hamad Al Thani", "Thani"),
])
def test_particles_are_stripped_on_both_sides(surface, key):
    assert nk.family_key(surface) == key


def test_hyphenated_family_name_is_not_split_when_the_head_is_not_a_particle():
    assert nk.family_key("Alexandria Ocasio-Cortez") == "Ocasio-Cortez"


def test_generational_suffix_is_dropped():
    assert nk.family_key("Martin Luther King Jr") == "King"
    assert nk.family_key("John Smith III") == "Smith"


@pytest.mark.parametrize("surface,key", [
    ("Wang Yi", "Wang"), ("Cho Hyun", "Cho"), ("Han Zheng", "Han"),
    ("Li Qiang", "Li"), ("Kim Jong-un", "Kim"), ("Min Aung Hlaing", "Min"),
    ("Aung San Suu Kyi", "Suu Kyi"), ("Zhang Youxia", "Zhang"),
])
def test_every_family_first_name_in_the_audit_keys_on_its_family_token(surface, key):
    assert nk.family_key(surface) == key


# ── key length ───────────────────────────────────────────────────────

def test_short_family_names_are_usable_keys():
    # the old scorer dropped every key under four letters, which is every
    # corrected key in audit category A
    for surface in ("Xi Jinping", "Li Qiang", "Fu Cong", "Xu Jian", "Jo Bee-yun"):
        key = nk.family_key(surface)
        assert len(key) < 4
        assert key in nk.surface_forms(surface), surface


def test_three_letter_surname_is_usable_but_a_common_short_word_is_not():
    assert "Abe" in nk.surface_forms("Shinzo Abe")
    assert nk._usable("Abe") and nk._usable("Paz")
    assert not nk._usable("War") and not nk._usable("Air")


def test_acronyms_survive_as_keys():
    assert nk._usable("US") and nk._usable("UN")


# ── the presence test ────────────────────────────────────────────────

def test_the_family_name_alone_counts_as_present():
    assert nk.name_present("Xi Jinping", "President Xi met the delegation.")
    assert nk.name_present("President Donald Trump", "Trump said no.")


def test_a_name_no_summary_wrote_is_still_absent():
    assert not nk.name_present("Xi Jinping", "The Chinese leader met the delegation.")
    assert not nk.name_present("Cho Hyun", "A South Korean envoy attended.")


@pytest.mark.parametrize("surface,alias", [
    ("Tedros Adhanom Ghebreyesus", "Tedros"),
    ("Luiz Inacio Lula da Silva", "Lula"),
    ("Joko Widodo", "Jokowi"),
    ("Mohammed bin Salman", "MBS"),
])
def test_registered_press_aliases_count_as_present(surface, alias):
    assert nk.name_present(surface, f"{alias} arrived on Tuesday.")


@pytest.mark.parametrize("ent,resp", [
    ("US", "Stimulus spending rose sharply."),
    ("He", "The pilots landed safely."),
    ("We", "Prices moved lower this week."),
    ("May", "The strike may disrupt shipping."),
    ("Israel", "Israeli forces moved overnight."),
])
def test_bare_substring_hits_no_longer_count(ent, resp):
    """The five over-count drivers the audit measured: 15.3% of everything the
    old test scored PRESENT was a substring of another word."""
    assert nk.substring_present(ent, resp)       # the old rule said yes
    assert not nk.name_present(ent, resp)        # the new rule says no


def test_case_matters():
    assert not nk.name_present("Trump", "the trump card was played")
    assert nk.name_present("Trump", "Trump was in the room")


def test_short_ambiguous_key_does_not_count_at_the_start_of_a_sentence():
    assert not nk.name_present("Han Zheng", "Han arrived early.")
    assert nk.name_present("Han Zheng", "The envoy Han arrived early.")
    assert nk.name_present("Han Zheng", "Han Zheng arrived early.")


def test_the_full_surface_is_itself_a_surface_form():
    assert nk.name_present("Bandar Abbas", "The port of Bandar Abbas was closed.")


def test_whitespace_in_a_surface_form_matches_any_run_of_whitespace():
    assert nk.name_present("Aung San Suu Kyi", "Suu\nKyi remains detained.")


def test_empty_inputs_are_not_present():
    assert not nk.name_present("", "text")
    assert not nk.name_present("Trump", "")


# ── the entity filter ────────────────────────────────────────────────

def test_live_entity_runs_is_unchanged():
    src = "The Mexican government met NATO officials in Brussels."
    assert nk.live_entity_runs(src) == {"The Mexican", "NATO", "Brussels"}


def test_headline_fragments_are_trimmed_to_the_name():
    src = "Trump Says the deal holds. Xi Are Set to meet. King Charles Will Speak today."
    got = nk.entity_candidates(src)
    assert "Trump" in got and "Trump Says" not in got
    assert "Xi" in got and "Xi Are Set" not in got
    assert "King Charles" in got and "King Charles Will Speak" not in got


def test_scraper_chrome_is_not_an_entity():
    src = "Published\nDonald Trump denied it."
    assert "Published\nDonald Trump" in nk.live_entity_runs(src)
    assert not any("Published" in e for e in nk.entity_candidates(src))


def test_a_run_spanning_a_line_break_is_not_one_entity():
    src = "Hormuz\nIran closed the strait."
    assert "Hormuz\nIran" in nk.live_entity_runs(src)
    assert "Hormuz\nIran" not in nk.entity_candidates(src)


def test_sentence_initial_common_capital_is_not_an_entity():
    src = "Officials said the raid failed. Two officials resigned afterwards."
    assert "Officials" in nk.live_entity_runs(src)
    assert "Officials" not in nk.entity_candidates(src)


def test_a_name_that_only_ever_starts_a_sentence_is_still_an_entity():
    src = "Netanyahu rejected the plan. Netanyahu left the room."
    assert "Netanyahu" in nk.entity_candidates(src)


def test_leading_determiner_is_trimmed_off_a_run():
    src = "The Mexican government protested."
    assert "The Mexican" in nk.live_entity_runs(src)
    assert "Mexican" in nk.entity_candidates(src)


def test_the_filter_only_ever_removes_or_shortens():
    src = ("Trump Says ceasefire holds. Officials said the strike hit Bandar Abbas. "
           "The Mexican government protested. Published\nDonald Trump denied it.")
    assert len(nk.entity_candidates(src)) <= len(nk.live_entity_runs(src))


def test_acronyms_survive_the_filter():
    assert "NATO" in nk.entity_candidates("Brussels hosted a NATO summit.")


# ── the two rules stay distinguishable ───────────────────────────────

def test_substring_present_still_implements_the_old_rule_exactly():
    assert nk.substring_present("Iran", "Iranian forces")
    assert nk.substring_present("iran", "IRANIAN forces")
    assert not nk.substring_present("Hormuz", "the strait")
