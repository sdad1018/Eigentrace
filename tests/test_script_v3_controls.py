"""script_v3 + void_ensemble: the Control sentences are appended to existing beats only.

Every host call is stubbed to "", every optional module that would touch the
network or the runtime segment archive (RAG, verifier, wiki sensor, state
vector, eigenching, broadcast state, ...) is replaced by an empty module so its
try-wrapped beat skips. Without "controls" in the attribution the script must be
byte-identical to the current output.
"""
from __future__ import annotations

import random
import sys
import types

import pytest

import script_v3
import void_ensemble

OPTIONAL_MODULES = [
    "broadcast_state", "segment_rag", "void_verifier", "wiki_edit_sensor", "source_salience",
    "cross_story_freq", "ablation_engine", "soul_updater", "state_vector", "eigenching",
    "preregistration",
]

CONTROLS = {
    "version": 1,
    "void": {"pool_n": 186, "absent_n": 173, "absent_frac": 0.9301, "control_pool_n": 184,
             "control_absent_n": 183, "control_absent_frac": 0.9946},
    "source_void": {"absent_ratio": 0.42, "control_absent_ratio": 0.719},
    "killshots": {"n_claims": 2, "per_claim": [
        {"claim": "The talks collapsed on Tuesday", "max_sim_own": 0.734, "max_sim_control": 0.457, "n_omitted_control": 5},
        {"claim": "Mediators left Geneva", "max_sim_own": 0.71, "max_sim_control": 0.40, "n_omitted_control": 5},
    ]},
    "density": {"measured": 0.9291, "control_mixed": 0.5517, "n_panel": 5},
    "compression": {"hedges_total": 2, "hedges_total_control": 9, "entity_retention": 0.69,
                    "entity_retention_control": 0.104, "n_control_responses": 5},
}


def _attr(with_controls):
    a = {
        "story_title": "Geneva ceasefire talks collapse",
        "story_url": "https://example.invalid/geneva",
        "story_guid": "guid-own",
        "category": "world",
        "source_body": "Geneva ceasefire talks collapse. Mediators said the talks collapsed on Tuesday. " * 5,
        "mean_vix": 17.2,
        "consensus_density": 0.929,
        "state_flag": "LOCKSTEP",
        "void_words": ["mediator", "walkout", "delegation"],
        "logos_words": ["armistice", "envoy"],
        "compression": {"verb_downgrade": 0.0, "entity_retention": 0.69,
                        "attribution_buffer": {"total": 2, "avg_per_model": 0.4}, "compression_score": 0.13},
        "source_void": {"absent_words": ["mediator", "walkout", "delegation", "tuesday"], "absent_ratio": 0.42,
                        "absent_count": 4, "source_word_count": 10, "absent_phrases": []},
        "void_context": [],
        "model_vix": {"ChatGPT": 12.0, "Claude": 20.1, "Gemini": 15.5, "DeepSeek": 22.7, "Grok": 15.7},
        "model_responses": {n: f"{n} says the talks collapsed." for n in ("ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok")},
        "claim_killshots": [
            {"claim": "The talks collapsed on Tuesday", "salience": 0.81, "omitted_by": ["Grok", "Gemini"]},
            {"claim": "Mediators left Geneva", "salience": 0.62, "omitted_by": ["Claude"]},
        ],
        "null_space_claims": [],
        "preregistration": {},
    }
    if with_controls:
        a["controls"] = CONTROLS
    return a


@pytest.fixture
def quiet(monkeypatch):
    for name in OPTIONAL_MODULES:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setattr(script_v3, "_call_host", lambda *a, **k: "")
    monkeypatch.setattr(script_v3, "_call_host_think", lambda *a, **k: "")
    monkeypatch.setattr(script_v3, "_call_host_confident", lambda *a, **k: "")
    monkeypatch.setattr(script_v3, "_call_host_with_swerves", lambda *a, **k: ("", []))
    monkeypatch.setattr(script_v3, "_rag_context", lambda *a, **k: "")
    return True


def _run(with_controls):
    random.seed(0)
    return script_v3.generate_script_v3({"beats": [], "attribution": _attr(with_controls)}, {})


def _by_phase(beats):
    out = {}
    for b in beats:
        out.setdefault(b["phase"], []).append(b["text"])
    return out


def test_control_sentences_are_appended_once_and_nothing_else_changes(quiet):
    base = _by_phase(_run(False))
    with_c = _by_phase(_run(True))
    assert set(base) == set(with_c)
    for phase in base:
        assert len(base[phase]) == len(with_c[phase]), phase

    d4 = " Control: a panel of one summary from each of 5 different stories scores 0.552 on the same measure."
    assert with_c["beat_04_density"][0] == base["beat_04_density"][0] + d4
    assert with_c["beat_04_density"][0].count("Control:") == 1

    d4b = " Control: another article's content words were 72 percent absent from these same responses."
    assert with_c["beat_04b_absent_words"][0] == base["beat_04b_absent_words"][0] + d4b

    d11 = (" Control: five summaries of an unrelated story scored against this article insert 9 attribution "
           "buffers and retain 0.10 of its entities.")
    assert with_c["beat_11_compression_report"][0] == base["beat_11_compression_report"][0] + d11
    assert with_c["beat_11_compression_report"][0].startswith("Language compression report. ")

    ks_base, ks_ctl = base["beat_15_killshots"][0], with_c["beat_15_killshots"][0]
    assert ks_base.endswith("Omitted by: Grok, Gemini. The claim: Mediators left Geneva. Salience: 0.62. Omitted by: Claude. ")
    assert ks_ctl == (
        "Source fact killshots. The claim: The talks collapsed on Tuesday. Salience: 0.81. Omitted by: Grok, Gemini."
        " Nearest response scored 0.73 here, 0.46 against an unrelated panel; omitted means below 0.65. "
        "The claim: Mediators left Geneva. Salience: 0.62. Omitted by: Claude."
        " Nearest response scored 0.71 here, 0.40 against an unrelated panel; omitted means below 0.65. ")

    # every other beat is byte-identical; no beat carries a Control sentence but the four targets
    targets = {"beat_04_density", "beat_04b_absent_words", "beat_11_compression_report", "beat_15_killshots"}
    for phase in base:
        if phase in targets:
            continue
        assert base[phase] == with_c[phase], phase
        assert all("Control:" not in t for t in with_c[phase]), phase
    assert not any("beat_20_archive" in p and "Control" in t for p, ts in with_c.items() for t in ts)
    assert "controls" not in " ".join(t for ts in with_c.values() for t in ts).lower()


def test_no_controls_means_no_control_text_and_beat_06_untouched(quiet):
    beats = _run(False)
    assert not any("Control:" in b["text"] for b in beats)
    assert any(b["phase"] == "beat_06_void_reveal" for b in beats)     # beat 06 is never given a sentence in script_v3


def test_partial_controls_only_affect_their_own_beat(quiet):
    attr = _attr(True)
    attr["controls"] = {"version": 1, "density": {"measured": 0.93, "control_mixed": 0.51, "n_panel": 4},
                        "killshots": {"error": "no control story"}}
    random.seed(0)
    beats = _by_phase(script_v3.generate_script_v3({"beats": [], "attribution": attr}, {}))
    assert beats["beat_04_density"][0].endswith(
        " Control: a panel of one summary from each of 4 different stories scores 0.510 on the same measure.")
    assert "Control" not in beats["beat_11_compression_report"][0]
    assert "Nearest response" not in beats["beat_15_killshots"][0]
    assert "Control" not in beats["beat_04b_absent_words"][0]


# ── the ensemble path: where the void words actually air ───────────────

ENS = {"top5": [{"word": "mediator", "votes": 2, "channels": ["a", "b"], "geo": None},
                {"word": "walkout", "votes": 1, "channels": ["a"], "geo": None}],
       "channels_run": ["a", "b"], "n_candidates": 9, "drops": {"said": 1, "title": 0, "geo_merged": 0},
       "absorbs": ["beat_06_void_reveal", "beat_07_void_analysis", "beat_09_confirmation"]}

VOID_SENTENCE = (" Control: of the 186 words nearest this headline, 93 percent were absent from the responses; "
                 "of the 184 words nearest an unrelated headline, 99 percent were absent.")


def test_build_ensemble_beats_appends_void_control_to_top5():
    plain = void_ensemble.build_ensemble_beats(ENS)
    ctl = void_ensemble.build_ensemble_beats(ENS, controls=CONTROLS)
    assert [b["phase"] for b in plain] == [b["phase"] for b in ctl]
    top_plain = next(b for b in plain if b["phase"] == "ensemble_top5")["text"]
    top_ctl = next(b for b in ctl if b["phase"] == "ensemble_top5")["text"]
    assert top_ctl == top_plain + VOID_SENTENCE
    assert top_ctl.count("Control:") == 1
    for a, b in zip(plain, ctl):
        if a["phase"] != "ensemble_top5":
            assert a == b
    assert void_ensemble.build_ensemble_beats(ENS, controls={}) == plain
    assert void_ensemble.build_ensemble_beats(ENS, controls={"void": {"error": "x"}}) == plain
    assert void_ensemble.build_ensemble_beats(ENS, controls=None) == plain


def test_weave_beats_passes_controls_and_retires_beat_06():
    beats = [{"phase": "beat_04_density", "speaker": "Host", "text": "d"},
             {"phase": "beat_06_void_reveal", "speaker": "Host", "text": "void"},
             {"phase": "beat_outro", "speaker": "Host", "text": "bye"}]
    woven = void_ensemble.weave_beats(beats, {"ensemble": ENS, "controls": CONTROLS})
    phases = [b["phase"] for b in woven]
    assert "beat_06_void_reveal" not in phases and phases[-1] == "beat_outro"
    top = next(b for b in woven if b["phase"] == "ensemble_top5")["text"]
    assert top.endswith(VOID_SENTENCE)
    woven_plain = void_ensemble.weave_beats(beats, {"ensemble": ENS})
    assert not any("Control:" in b["text"] for b in woven_plain)
    assert void_ensemble.weave_beats(beats, {}) == beats
