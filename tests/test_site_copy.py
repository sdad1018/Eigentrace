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


@pytest.mark.parametrize("page", ["sean-adams.html", "withdrawals.html"])
def test_page_tags_balance(page):
    src = _read(DOCS / page)
    assert src.count("<div") == src.count("</div>"), f"{page}: div count mismatch"
    p = _Balance()
    p.feed(src)
    p.close()
    assert not p.unbalanced, f"{page}: stray closing tags {p.unbalanced}"
    assert not p.stack, f"{page}: unclosed tags {p.stack}"
