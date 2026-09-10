"""Regex / text gates: proxy_auditor._strip_chrome, script_v3._FAILURE_RE, idle_reflection.BANNED_RE."""
from __future__ import annotations

import pytest

# proxy_auditor imports geometric_engine (sentence_transformers) and rich at module
# level; conftest stubs dotenv so its load_dotenv(.env) call is a no-op.
pa = pytest.importorskip("proxy_auditor")
import idle_reflection  # noqa: E402
import script_v3  # noqa: E402


# ---------------------------------------------------------------------------
# Item 4 -- _strip_chrome
# ---------------------------------------------------------------------------

RAW = """Recommended Stories
list 1 of 4
The minister said the budget would be cut by ten percent next year.
end of list
Photo: John Doe/Getty Images
Credit: Reuters
Home
Sport
Protesters gathered outside parliament, AP Photo, demanding answers from the government.
Officials confirmed the decision on Tuesday.
It ended.
Sign up for our newsletter
Published: 2026-09-10
"""


def test_strip_chrome_drops_navigation_and_credits():
    out = pa._strip_chrome(RAW)
    for gone in ("Recommended Stories", "list 1 of 4", "end of list", "Getty Images",
                 "AP Photo", "Credit: Reuters", "Sign up", "Published:"):
        assert gone not in out, gone
    # short menu lines without terminal punctuation
    assert "\nHome" not in out and not out.startswith("Home")
    assert "Sport" not in out


def test_strip_chrome_keeps_sentences():
    out = pa._strip_chrome(RAW)
    assert "The minister said the budget would be cut by ten percent next year." in out
    assert "Protesters gathered outside parliament" in out
    assert "demanding answers from the government." in out
    assert "Officials confirmed the decision on Tuesday." in out
    assert "It ended." in out                      # short but a real sentence
    assert "  " not in out                         # runs of spaces collapsed


def test_strip_chrome_inline_credit_removed_mid_sentence():
    out = pa._strip_chrome("The rally drew thousands, Getty Images, according to police estimates.")
    assert "Getty Images" not in out
    assert out.startswith("The rally drew thousands")
    assert out.endswith("according to police estimates.")


def test_strip_chrome_empty_and_none():
    assert pa._strip_chrome("") == ""
    assert pa._strip_chrome(None) == ""


# ---------------------------------------------------------------------------
# Item 7 -- script_v3._FAILURE_RE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "[Mistral unavailable: x]",
    "[Gemini error: 429 rate limited]",
    "[Grok: no caller found]",
    "  [VIX error: division by zero]",
    "[API ERROR]",
    "[HOST ERROR: ollama down]",
    "[no response]",
    "[ChatGPT error: timeout] and then some narration",
])
def test_failure_re_matches_failure_strings(text):
    assert script_v3._FAILURE_RE.match(text)


@pytest.mark.parametrize("text", [
    "The minister said the budget would be cut by ten percent next year.",
    "Gemini said the error was minor and the rollout continues.",
    "[Breaking] Markets fell three percent on the news.",
    "Mistral unavailable in the region, the vendor said.",   # no leading bracket
    "Grok: no caller found is what the log said.",           # no leading bracket
    "",
])
def test_failure_re_ignores_narration(text):
    assert not script_v3._FAILURE_RE.match(text)


def test_failure_re_is_applied_as_a_beat_filter():
    """generate_script_v3 needs Ollama, so check its source still applies the filter
    as a beat drop (str() of the text so a non-string beat cannot raise)."""
    import inspect
    src = inspect.getsource(script_v3.generate_script_v3)
    assert 'if not _FAILURE_RE.match(str(b.get("text", "")))' in src


# ---------------------------------------------------------------------------
# Item 11 -- idle_reflection.BANNED_RE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "This looks like a placeholder entry.",
    "The void words are empty.",
    "Void words list: not provided.",
    "These entries are identical in content.",
    "Category: unknown.",
    "The category reads 'unknown' for all three.",
    "I have been looping on the same idea.",
    "This is an idle reflection on the day.",
    "The REM consolidation pass ran again.",
    "There is data corruption in this record.",
    "The state field is empty.",
    "These three stories are identical.",
    "My own memory store shows the same thing.",
    "A verbatim summary of the same story.",
    "Nothing new to say tonight.",
    "The meta-category here is coverage itself.",
])
def test_banned_re_rejects_machinery_talk(text):
    assert idle_reflection.BANNED_RE.search(text), text


@pytest.mark.parametrize("text", [
    "Five models summarized the ceasefire and all five dropped the casualty figure.",
    "The void words are absent from every summary, which is the pattern we look for.",
    "Claude kept the named general; ChatGPT and Gemini replaced him with 'officials'.",
    "The story with the largest source-to-summary gap was the pipeline explosion.",
    "Hedging rose on the election story: 'reportedly' appeared in four of five summaries.",
])
def test_banned_re_accepts_reflection_about_the_news(text):
    assert not idle_reflection.BANNED_RE.search(text), text
