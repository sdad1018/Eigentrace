"""Site copy: the claims the ledger will not let these pages make.

Added 2026-09-19 with the last three lines of the approved batch-two copy pass.
Each test pins one thing that pass changed, so a later edit cannot quietly put
the withdrawn wording back:

  * docs/llms.txt may not state the no-judge rule as an absolute over the whole
    stack (IDX_003, CONTRADICTED); it states it for the measurement path.
  * no public page may carry the "about $50" replication-cost claim
    (Withdrawal 23) - the withdrawals page itself is where that claim now lives.
  * docs/sean-adams.html may not credential itself with the entity-swap
    d = 0.471 (BND_F1_CLAIM, CONTRADICTED) or the RLHF null p = 0.46
    (W09 / ANA_003, CONTRADICTED); it carries the two MEASURED results instead.

These are string tests on the shipped files, not on a generator: all three files
are hand-edited.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

LLMS = DOCS / "llms.txt"
SEAN = DOCS / "sean-adams.html"
WITHDRAWALS = DOCS / "withdrawals.html"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _public_prose_files() -> list[Path]:
    """Top-level site copy: the pages a reader lands on.

    Excludes the daily JSON exports (docs/data), the omission-ledger post
    archive (docs/_posts), the blog, and every .bak* snapshot - none of those
    are pages, and the post archive quotes model output verbatim.
    """
    out: list[Path] = []
    for pat in ("*.html", "*.md", "*.txt"):
        out.extend(sorted(DOCS.glob(pat)))
    out.extend(sorted((DOCS / "preprint").glob("*.md")))
    return [p for p in out if ".bak" not in p.name]


# --------------------------------------------------------------- llms.txt


def test_llms_txt_states_no_judge_for_the_measurement_path_only():
    t = _read(LLMS)
    assert "anywhere in the stack" not in t, (
        "llms.txt asserts the no-judge rule over the whole stack; the ledger "
        "records IDX_003 as CONTRADICTED (the gpt-5.4-mini judge, Summary Plus, "
        "the Atlas role vote and claim extraction are all model-in-the-loop)"
    )
    assert "No language model evaluates another language model's output" not in t
    assert "No language model evaluated another" not in t
    assert t.count("measurement path") >= 2, (
        "both the summary line and the method notes should scope the rule to "
        "the measurement path"
    )


def test_llms_txt_still_names_the_model_in_the_loop_steps():
    """W11's verdict: the labelled steps are the other half of the true statement."""
    t = _read(LLMS)
    for step in ("Summary Plus", "claim extraction", "judge"):
        assert step in t, f"{step!r} should be named as a model-in-the-loop step"


# ------------------------------------------------------- replication cost


def test_no_replication_cost_claim_on_public_pages():
    """Withdrawal 23: no cost record of any kind exists in the tree."""
    offenders = []
    for p in _public_prose_files():
        if p.resolve() == WITHDRAWALS.resolve():
            continue  # the withdrawal entry quotes the claim it withdraws
        if re.search(r"\$\s*50\b", _read(p)):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, (
        "the withdrawn 'about $50 in API credits' replication claim is back on: "
        + ", ".join(offenders)
    )


def test_withdrawals_page_still_records_the_cost_claim():
    """The claim has to live somewhere: the withdrawal entry is that somewhere."""
    t = _read(WITHDRAWALS)
    assert "$50" in t
    assert "Withdrawal 23" in t


# -------------------------------------------------------- sean-adams.html


@pytest.mark.parametrize("banned", ["0.471", "d = 0.47", "p = 0.46"])
def test_sean_adams_drops_contradicted_numbers(banned):
    assert banned not in _read(SEAN), (
        f"{banned!r} is a CONTRADICTED ledger claim and may not credential this page"
    )


def test_sean_adams_carries_the_salience_result():
    """NC_002, MEASURED - quoted from the ledger's allowed_public_wording."""
    t = _read(SEAN)
    assert "0.22 [+0.18, +0.25]" in t
    assert "0.14 [+0.10, +0.18]" in t
    assert "540 pairs, 108 stories" in t
    assert "four of five" in t, "the four-of-five caveat is part of the allowed wording"


def test_sean_adams_carries_the_hormuz_result():
    """IRAN_F05, MEASURED - quoted from the ledger's allowed_public_wording."""
    t = _read(SEAN)
    assert "Strait of Hormuz" in t
    assert "DeepSeek 33%" in t and "Grok 31%" in t and "Claude 32%" in t
    assert "exploration window only" in t, (
        "Claude's rate may not stand beside the other two without its marker"
    )
    assert "none of 192" in t


def test_sean_adams_does_not_call_a_figure_false():
    """IRAN_F05 must_not_say: the instrument does not rule on accuracy."""
    t = _read(SEAN).lower()
    for word in ("hallucinat", "fabricat", "made up the figure"):
        assert word not in t


def test_sean_adams_lead_sentence_is_true_of_both_results():
    """The lead under "The Results I Stand Behind" was false twice: neither
    result is scored on embeddings (salience matches a surname as a string,
    Hormuz matches strings and numbers), and only the salience result ran on
    two model sets (which share their ChatGPT / Gemini / DeepSeek rows)."""
    t = _read(SEAN)
    assert "scored by deterministic arithmetic on frozen embeddings" not in t, (
        "neither standing result is embedding-scored"
    )
    assert "both were checked against two independent sets" not in t, (
        "only the salience result ran on two model sets"
    )
    assert "deterministic string and number matching" in t


def test_sean_adams_cards_state_their_own_replication_fact():
    """Each card carries the replication fact true of that card."""
    t = _read(SEAN)
    assert "independent sets" not in t, (
        "the two salience model sets share byte-identical ChatGPT / Gemini / "
        "DeepSeek rows (name_causal/DEVIATIONS.md); they are not independent"
    )
    assert "not two independent replications" in t, (
        "the salience card should say what its two model sets are"
    )
    assert "has not been repeated on a second set of models" in t, (
        "the Hormuz card is one five-model panel with an exploration / held-out "
        "split of stories, not a second model set"
    )


def test_sean_adams_method_sentence_matches_what_the_path_computes():
    """Entity survival is string matching, hedge counts are word-set
    membership and verb drift is a frequency lookup, so the measurement path
    is not all vector arithmetic."""
    t = _read(SEAN)
    assert "arithmetic on vectors" not in t
    assert "deterministic arithmetic or string counting" in t


def test_sean_adams_scopes_the_no_judge_rule_to_the_measurement_path():
    """W11 / W13: the absolute is withdrawn. ai.txt and humans.txt scope the
    rule to the measurement path and this page now matches them."""
    t = _read(SEAN)
    assert "no model judging another model" not in t
    assert "No language model evaluates another language model" not in t
    assert t.count("measurement path") >= 2, (
        "the method paragraph and the stat tile should both scope the rule"
    )


def test_sean_adams_makes_no_continuous_operation_claim():
    """IDX_002 and W14, both CONTRADICTED: no 24/7, no 'runs continuously'."""
    t = _read(SEAN)
    assert "24/7" not in t
    assert "continuously" not in t
    assert "streams whenever the stack is up" in t, (
        "the ledger's allowed uptime wording should stand in its place"
    )


# ------------------------------------------------------------ well-formed


class _Balance(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.unbalanced: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.unbalanced.append(tag)


# ------------------------------------------------- EigenChing recount (W24)

EIGENCHING_DIST = DOCS / "eigenching_distribution.md"
EIGENCHING_DATA = DOCS / "eigenching_data.json"


def test_withdrawals_carries_the_eigenching_recount():
    """W24 supersedes W20 and states the recount, with the numbers G4 verified."""
    t = _read(WITHDRAWALS)
    assert "Withdrawal 24" in t
    assert "supersedes Withdrawal 20" in t
    for number in ("3,817", "2,401", "69", "1.8%", "16.1%"):
        assert number in t, f"withdrawals.html is missing {number} from the recount"


_NUM_WORD = {20: "twenty", 21: "twenty-one", 22: "twenty-two", 23: "twenty-three",
             24: "twenty-four", 25: "twenty-five", 26: "twenty-six",
             27: "twenty-seven", 28: "twenty-eight", 29: "twenty-nine"}
_AUDIT_WORD = {15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
               19: "nineteen", 20: "twenty"}
# entries 1-8 predate the September 2026 audit; the rest are its findings
_PRE_AUDIT_ENTRIES = 8


def test_withdrawals_entry_count_matches_the_entries_on_the_page():
    """The page states its own total in three places and the audit subtotal in
    two; all five must agree with the Withdrawal numbers actually present. The
    expected words are derived from the page, so adding an entry cannot leave a
    stale total behind and cannot be satisfied by editing this test."""
    t = _read(WITHDRAWALS)
    numbers = [int(m) for m in re.findall(r"Withdrawal (\d+)</span>", t)]
    assert numbers, "no withdrawal headings on the page"
    assert len(set(numbers)) == len(numbers), "duplicate withdrawal numbers"
    top = max(numbers)
    assert sorted(numbers) == list(range(1, top + 1)), "a withdrawal number is missing"
    assert t.lower().count(_NUM_WORD[top]) == 3          # og, abstract, standfirst
    assert _NUM_WORD[top - 1] not in t.lower(), "a stale entry total is still on the page"
    audit = _AUDIT_WORD[top - _PRE_AUDIT_ENTRIES]
    assert t.count(f"{audit} further entries") == 2      # meta description, abstract
    assert f"{_AUDIT_WORD[top - _PRE_AUDIT_ENTRIES - 1]} further entries" not in t

    # The standfirst attributes each tranche. It used to stop at "Entries 09 to
    # 23" on a 25-entry page, leaving the newest entries with no provenance, so
    # it is pinned to the highest Withdrawal number actually on the page.
    assert f"Entries {top - 1:02d} and {top:02d} came from" in t, (
        "the dateline does not say where the two newest entries came from"
    )
    assert f"Entries 09 to {top}" not in t, (
        "the audit tranche does not reach the newest entries"
    )


def test_withdrawals_carries_the_entity_retention_entry():
    """W25: the live entity_retention rule, and the three numbers the audit
    measured on the primary cell."""
    t = _read(WITHDRAWALS)
    assert "Withdrawal 25" in t
    for number in ("15.3%", "23.1%", "13.1%", "0.6485", "98 / 750 / 676"):
        assert number in t, f"withdrawals.html is missing {number} from W25"
    # the two checks that did NOT move a published figure are stated as such
    assert "646 to 645 of 3,800" in t
    assert "0.1845 to 0.1826" in t


def test_distribution_page_makes_no_proper_noun_claim():
    """The 80%+ cell was the fingerprint of rows with no compression block
    (W24). The generated page reports MISSING rather than reading them as 0."""
    t = _read(EIGENCHING_DIST)
    assert "strips proper nouns" not in t
    assert "80%+" not in t
    assert "MISSING" in t
    assert "Generated by `eigenching_report.py`" in t


def test_distribution_page_labels_near_misses_as_near_misses():
    t = _read(EIGENCHING_DIST)
    assert "exact archetype" in t
    assert "near-miss" in t
    assert "never" in t and "as that archetype" in t


def test_dashboard_data_counts_exact_hits_only():
    """docs/eigenching_data.json is machine-written; this pins what the page
    renders, so a regenerated file that reverts the keying fails here."""
    import json
    d = json.loads(_read(EIGENCHING_DATA))
    assert d["keying"].startswith("exact archetype name")
    counts = sum(a["count"] for a in d["archetypes"])
    assert counts == d["exact_total"]
    assert counts <= d["total_segments"]
    assert sum(a["pct"] for a in d["archetypes"]) <= 100.0
    assert d["archetypes_with_exact_hits"] + d["archetypes_without_exact_hits"] == 32
    for a in d["archetypes"]:
        assert "near_miss_count" in a and "near_miss_note" in a
        assert a["count"] <= a["count"] + a["near_miss_count"]


@pytest.mark.parametrize(
    "page", ["sean-adams.html", "withdrawals.html", "eigenching.html"])
def test_page_tags_balance(page):
    src = _read(DOCS / page)
    assert src.count("<div") == src.count("</div>"), f"{page}: div count mismatch"
    p = _Balance()
    p.feed(src)
    p.close()
    assert not p.unbalanced, f"{page}: stray closing tags {p.unbalanced}"
    assert not p.stack, f"{page}: unclosed tags {p.stack}"


# ------------------------------------------- EigenChing dashboard rendering

EIGENCHING_PAGE = DOCS / "eigenching.html"


def test_eigenching_page_counts_state_beats_not_stories():
    """total_segments is 3,817 state beats, 359 of them legacy axis readouts,
    against 13,467 story files. The tile said "Stories Classified"."""
    t = _read(EIGENCHING_PAGE)
    assert "Stories Classified" not in t
    assert "State beats classified" in t
    assert "legacy_axis_readout" in t, "the legacy split should be rendered"
    assert "story_files" in t, "the story archive is the other denominator"


def test_eigenching_top_tile_is_labelled_as_the_top_exact_archetype():
    """The tile shows the most frequent EXACT archetype, which is not the most
    frequent state aired; the aired state has no archetype name."""
    t = _read(EIGENCHING_PAGE)
    assert ">Most Common<" not in t
    assert "Most frequent exact archetype" in t
    assert "most_common_aired_state" in t
    assert "pct" in t, "the tile should carry the archetype's share"


def test_eigenching_cards_separate_exact_hits_from_near_misses():
    """W24 says near-misses are held apart on the dashboard. near_miss_count
    was never rendered, so a card with near-misses and no exact hit read
    "Never observed - waiting"."""
    t = _read(EIGENCHING_PAGE)
    assert "near_miss_count" in t
    assert "near_miss_examples" in t
    assert "Never observed \u2014 waiting" not in t
    assert "no exact hit" in t, "a card with no exact hit should say so"
    assert "near-miss" in t


def test_eigenching_page_presents_no_count_as_a_census():
    """G4_MATRIX_RECOUNT must_not_say."""
    t = _read(EIGENCHING_PAGE)
    assert "census" not in t.lower()
    assert "80%+" not in t
    assert "Still Point" not in t
