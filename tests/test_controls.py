"""controls.py: null-baseline controls for the five live probes (2026-09-10).

CPU only, no network, no live processes. The engine is a FakeEngine (fixed
unit vectors, inheriting compute_consensus_density from the production class),
the vocabulary is a small torch tensor, and the segments directory is tmp_path.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import numpy as np
import pytest
import torch

import controls
import batch_producer as bp
from eigentrace_math import score_language_compression, source_anchored_void
from geometric_engine import GeometricPerturbationEngine

DIM = 8


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


def _axis(i, tilt=0.0, j=1):
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    v[j] = tilt
    return _unit(v)


class FakeEngine(GeometricPerturbationEngine):
    """Fixed table text -> unit vector; unknown texts get a seeded pseudo-random unit vector.

    compute_consensus_density is inherited from the production class (same code path).
    """

    def __init__(self, table):
        self.table = dict(table)
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        out = []
        for t in texts:
            if t not in self.table:
                rng = np.random.default_rng(abs(hash(t)) % (2 ** 32))
                self.table[t] = _unit(rng.normal(size=DIM))
            out.append(self.table[t])
        return np.stack(out).astype(np.float32)


class FakeVocab:
    def __init__(self, words, vecs):
        self.words = list(words)
        self.tensor = torch.tensor(np.stack(vecs), dtype=torch.float32)


def _resp(name, text, vix=10.0, skipped=False, error=None):
    return SimpleNamespace(name=name, text=text, eigen_vix=vix, skipped=skipped, error=error)


def _story(guid, title, summary="", body=""):
    return SimpleNamespace(guid=guid, title=title, summary=summary, body=body, category="world", url=guid)


# ── fixtures: one own story, one unrelated batch mate ──────────────────

OWN_TEXTS = [
    "Alpha bravo reported the ceasefire talks in Geneva collapsed on Tuesday.",
    "Alpha bravo said the Geneva ceasefire talks collapsed on Tuesday after a walkout.",
    "The Geneva talks on a ceasefire collapsed Tuesday, alpha bravo noted.",
    "Alpha bravo: ceasefire talks in Geneva collapsed on Tuesday.",
    "Ceasefire negotiations in Geneva broke down Tuesday, alpha bravo confirmed.",
]
OTHER_TEXTS = [
    "The central bank allegedly raised rates by a quarter point, reportedly citing inflation.",
    "Rates went up a quarter point; officials reportedly pointed to inflation.",
    "A quarter-point rate rise was announced, purportedly over inflation concerns.",
    "The bank raised its benchmark rate, apparently in response to inflation.",
]
OWN_TITLE = "Geneva ceasefire talks collapse"
OTHER_TITLE = "Central bank raises rates a quarter point"
CLAIM = "The ceasefire talks in Geneva collapsed on Tuesday"


def _vocab():
    """4 words present in the own responses near e0 (own headline), 4 absent near e7
    (control headline), 242 seeded fillers absent from everything."""
    rng = np.random.default_rng(7)
    words, vecs = [], []
    for w in ("alpha", "bravo", "geneva", "ceasefire"):
        words.append(w); vecs.append(_axis(0, tilt=0.05 * len(words)))
    for w in ("xylophone", "quantum", "zeppelin", "juniper"):
        words.append(w); vecs.append(_axis(7, tilt=0.05 * len(words), j=6))
    for i in range(242):
        words.append(f"filler{i:03d}")
        vecs.append(_unit(np.r_[rng.normal(size=DIM)]))
    words.append("ab")  # < 4 chars: skipped by the length filter
    vecs.append(_axis(0))
    return FakeVocab(words, vecs)


@pytest.fixture
def engine():
    table = {OWN_TITLE: _axis(0), OTHER_TITLE: _axis(7), CLAIM: _axis(0, tilt=0.02)}
    for k, t in enumerate(OWN_TEXTS):
        table[t] = _axis(0, tilt=0.15 + 0.03 * k)      # own panel: tight around e0
    for k, t in enumerate(OTHER_TEXTS):
        table[t] = _axis(3 + k)                         # control panel: mutually orthogonal, orthogonal to e0
    return FakeEngine(table)


@pytest.fixture
def batch(engine):
    own_story = _story("guid-own", OWN_TITLE,
                       summary="Talks in Geneva on a ceasefire collapsed on Tuesday, mediators said after the delegation walked out.",
                       body="Mediators said the Geneva ceasefire talks collapsed on Tuesday after the delegation walked out. " * 8)
    other_story = _story("guid-other", OTHER_TITLE, summary="The central bank raised rates by a quarter point.",
                         body=("The central bank raised its benchmark rate by a quarter point on Wednesday. Governor Mireille "
                               "Okonkwo told reporters the committee weighed unemployment, housing costs and consumer spending "
                               "before voting seven to two, and signalled further tightening if inflation persists. ") * 4)
    own_resps = [_resp(n, t, vix=8.0 + i) for i, (n, t) in enumerate(zip(["A", "B", "C", "D", "E"], OWN_TEXTS))]
    other_resps = [_resp(n, t) for n, t in zip(["A", "B", "C", "D"], OTHER_TEXTS)]
    other_resps.append(_resp("E", "[Mistral unavailable: timeout]"))   # failure string, must be dropped
    r_own = {"story": own_story, "responses": own_resps}
    r_other = {"story": other_story, "responses": other_resps}
    return [r_own, r_other]


def _prepare_measured(r, engine, vt):
    """Populate r the way stage 3 does, using the production functions."""
    story = r["story"]
    active = [x for x in r["responses"] if not x.skipped and not x.error and x.text]
    texts = [x.text for x in active]
    E = engine.embed_texts(texts)
    r["geo"] = SimpleNamespace(consensus_density=float(engine.compute_consensus_density(E)))
    st = {}
    bp._compute_void(story.title, texts, engine, vt, pool_size=200, k=5, stats=st)
    r["void_stats"] = st
    r["source_void"] = source_anchored_void(controls.source_text_void(story), texts, title=story.title)
    r["compression"] = score_language_compression(controls.source_text_compression(story), texts)
    from claim_extractor import score_claim_coverage
    cov = score_claim_coverage([CLAIM], {x.name: x.text for x in active}, engine, story.title)
    r["claim_results"] = cov
    r["claim_killshots"] = cov
    return texts, E


# ── (ii) _compute_void stats out-param ─────────────────────────────────

def test_compute_void_stats_out_param_matches_plain_call(engine):
    vt = _vocab()
    plain = bp._compute_void(OWN_TITLE, OWN_TEXTS, engine, vt, pool_size=200, k=5)
    st = {}
    with_stats = bp._compute_void(OWN_TITLE, OWN_TEXTS, engine, vt, pool_size=200, k=5, stats=st)
    assert with_stats == plain                          # return value unchanged
    assert st["pool_n"] == 199                          # 251 words, top 200 includes the 2-char "ab" (nearest e0), skipped
    # the 4 present words are the nearest to e0, so absent_n == pool_n - 4
    assert st["absent_n"] == st["pool_n"] - 4
    assert 0 < st["absent_n"] <= st["pool_n"]
    # the short word is skipped by the length filter even when it is nearest
    vt2 = FakeVocab(["ab", "alpha", "quantum"], [_axis(0), _axis(0, 0.1), _axis(7)])
    st2 = {}
    bp._compute_void(OWN_TITLE, OWN_TEXTS, engine, vt2, pool_size=200, k=5, stats=st2)
    assert st2 == {"pool_n": 2, "absent_n": 1}


# ── _panel_vix refactor is behaviour-identical ─────────────────────────

def test_panel_vix_equals_inline_loop_and_density_identity():
    rng = np.random.default_rng(3)
    E = rng.normal(size=(5, 16)).astype(np.float32)
    E += 4.0  # all in one orthant -> realistic cosines
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    centroid = np.mean(E, axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
    expected = [min(100.0, max(0.0, (1.0 - float(np.dot(E[i], centroid))) * 500.0)) for i in range(5)]
    got = bp._panel_vix(E)
    assert got == expected
    d = GeometricPerturbationEngine.compute_consensus_density(None, E)
    ident = 500.0 * (1.0 - np.sqrt((1.0 + 4 * d) / 5))
    assert abs(np.mean(got) - ident) < 0.1
    # orthogonal rows: density 0, VIX 100 after the clip is not reached (cos = 1/sqrt(5) -> 276 -> clipped 100)
    I = np.eye(5, dtype=np.float32)
    assert bp._panel_vix(I) == [100.0] * 5
    assert GeometricPerturbationEngine.compute_consensus_density(None, I) == 0.0
    assert bp._panel_vix(np.ones((3, 4)) / 2.0) == pytest.approx([0.0] * 3, abs=1e-4)   # the 1e-8 in the norm, as in production


# ── (i) control story / panel selection ────────────────────────────────

def test_pick_control_story_prefers_batch_mate_and_drops_failure_strings(batch, tmp_path):
    ctrl = controls.pick_control_story(batch, 0, segments_dir=tmp_path)
    assert ctrl["method"] == "batch_mate" and ctrl["guid"] == "guid-other"
    assert set(ctrl["responses"]) == {"A", "B", "C", "D"}       # "[Mistral unavailable" dropped
    assert ctrl["source_text"] == controls.source_text_void(batch[1]["story"])
    assert ctrl["title"] == OTHER_TITLE


def test_pick_control_story_skips_own_guid_and_thin_mates(batch, tmp_path):
    same = {"story": _story("guid-own", "Same story again"), "responses": [_resp("A", "x y z"), _resp("B", "p q r")]}
    thin = {"story": _story("guid-thin", "Thin"), "responses": [_resp("A", "only one usable"), _resp("B", "[VIX error]")]}
    assert controls.pick_control_story([batch[0], same, thin], 0, segments_dir=tmp_path) is None
    assert controls.pick_control_story([batch[0]], 0, segments_dir=tmp_path / "missing") is None


def _write_segment(d, name, guid, title, responses, source_body="Some article body. " * 20, model_vix=None):
    seg = {"attribution": {"story_guid": guid, "story_title": title, "model_responses": responses,
                           "source_body": source_body, "model_vix": model_vix or {k: 10.0 for k in responses}}}
    (d / name).write_text(json.dumps(seg))


def test_pick_control_story_disk_fallback(batch, tmp_path, monkeypatch):
    monkeypatch.setattr(controls, "SEGMENTS_DIR", tmp_path)
    # newest first: a same-guid segment (skip), a failure-only segment (skip), then a good one
    _write_segment(tmp_path, "20260910_120003_aaaaaaaaaaaa_segment.json", "guid-own", OWN_TITLE, {"A": "x", "B": "y"})
    _write_segment(tmp_path, "20260910_120002_bbbbbbbbbbbb_segment.json", "guid-bad", "Bad",
                   {"A": "[Mistral unavailable]", "B": "[VIX error]", "C": "one good"})
    _write_segment(tmp_path, "20260910_120001_cccccccccccc_segment.json", "guid-disk", "Disk story",
                   {"A": "disk one", "B": "[Mistral unavailable]", "C": "disk three"})
    (tmp_path / "20260910_120004_roundtable.json").write_text("{}")          # not a story segment
    ctrl = controls.pick_control_story([batch[0]], 0)                       # no batch mate
    assert ctrl["method"] == "disk_segment" and ctrl["guid"] == "guid-disk"
    assert ctrl["responses"] == {"A": "disk one", "C": "disk three"}
    assert ctrl["segment_file"].startswith("20260910_120001")
    # explicit segments_dir argument overrides the module constant
    assert controls.pick_control_story([batch[0]], 0, segments_dir=tmp_path / "empty") is None


def test_pick_control_panel_one_per_story_never_own(batch, tmp_path, monkeypatch):
    monkeypatch.setattr(controls, "SEGMENTS_DIR", tmp_path)
    _write_segment(tmp_path, "20260910_120001_dddddddddddd_segment.json", "guid-d1", "D1", {"A": "d1 a", "B": "d1 b"})
    _write_segment(tmp_path, "20260910_120002_eeeeeeeeeeee_segment.json", "guid-d2", "D2", {"A": "d2 a"})
    _write_segment(tmp_path, "20260910_120003_ffffffffffff_segment.json", "guid-own", OWN_TITLE, {"A": "own again"})
    _write_segment(tmp_path, "20260910_120004_abababababab_segment.json", "guid-other", OTHER_TITLE, {"A": "dup mate"})
    panel = controls.pick_control_panel(batch, 0, 5)
    guids = [p["guid"] for p in panel]
    assert len(panel) == 3 and len(set(guids)) == 3
    assert "guid-own" not in guids
    assert guids[0] == "guid-other" and panel[0]["method"] == "batch_mate"
    assert set(guids[1:]) == {"guid-d2", "guid-d1"}                          # newest disk segments, own/dup skipped
    assert all(not p["text"].startswith("[") for p in panel)
    assert controls.pick_control_panel(batch, 0, 1) == []


# ── (iii) compute_controls end-to-end with fakes ──────────────────────

def test_compute_controls_end_to_end(batch, engine, tmp_path):
    vt = _vocab()
    r = batch[0]
    texts, E = _prepare_measured(r, engine, vt)
    out = controls.compute_controls(r, batch, 0, engine, vt, texts, r["story"], embeddings=E,
                                    void_fn=bp._compute_void, panel_vix=bp._panel_vix, segments_dir=tmp_path)
    assert out["version"] == 1
    assert out["control_story"]["guid"] == "guid-other" and out["control_story"]["method"] == "batch_mate"
    for probe in ("void", "source_void", "killshots", "density", "compression"):
        assert probe in out and "error" not in out[probe], out[probe]

    v = out["void"]
    assert v["pool_n"] == r["void_stats"]["pool_n"] and v["absent_n"] == r["void_stats"]["absent_n"]
    assert v["control_absent_frac"] >= v["absent_frac"]
    assert v["control_title"] == OTHER_TITLE and v["control_guid"] == "guid-other"
    assert v["absent_frac"] == pytest.approx(v["absent_n"] / v["pool_n"], abs=1e-4)

    s = out["source_void"]
    assert s["absent_ratio"] == pytest.approx(r["source_void"]["absent_ratio"], abs=1e-9)
    expected = source_anchored_void(controls.source_text_void(batch[1]["story"]), texts, title=OTHER_TITLE)
    assert s["control_absent_ratio"] == expected["absent_ratio"]
    assert s["control_absent_ratio"] > s["absent_ratio"]
    assert s["method"] == "batch_mate" and s["control_source_chars"] == len(controls.source_text_void(batch[1]["story"]))

    k = out["killshots"]
    assert k["n_claims"] == 1 and len(k["per_claim"]) == 1
    pc = k["per_claim"][0]
    assert pc["claim"] == CLAIM
    assert pc["max_sim_own"] == pytest.approx(max(r["claim_killshots"][0]["coverage"].values()), abs=1e-9)
    assert pc["max_sim_own"] > pc["max_sim_control"]
    assert pc["max_sim_control"] == pytest.approx(0.0, abs=1e-6)          # orthogonal control panel
    assert pc["n_omitted_control"] == 4
    assert r["claim_killshots"][0]["max_sim_own"] == pc["max_sim_own"]      # additive field written back

    d = out["density"]
    assert d["measured"] == pytest.approx(r["geo"].consensus_density, abs=1e-9)
    assert d["measured_mean_vix"] == pytest.approx(sum(8.0 + i for i in range(5)) / 5, abs=1e-9)
    assert d["n_panel"] == 2 and d["control_guids"] == ["guid-other"]     # only one other story in the batch
    assert d["control_mixed"] is None                                      # < 2 distinct other stories -> no control
    assert controls.control_sentence("beat_04_density", out) == ""

    c = out["compression"]
    assert c["hedges_total"] == r["compression"]["attribution_buffer"]["total"]
    assert c["entity_retention"] == r["compression"]["entity_retention"]
    exp_c = score_language_compression(controls.source_text_compression(r["story"]), OTHER_TEXTS)
    assert c["hedges_total_control"] == exp_c["attribution_buffer"]["total"]
    assert c["entity_retention_control"] == exp_c["entity_retention"]
    assert c["hedges_total_control"] >= 1          # the control panel hedges ("allegedly", "reportedly") and the source does not
    assert c["n_control_responses"] == 4
    # the summary is not the body's first paragraph -> blurb control computed
    assert c["blurb"] is not None and c["blurb"]["blurb_chars"] == len(r["story"].summary)
    assert json.dumps(out)                          # JSON-serialisable for the segment file


def test_compute_controls_density_with_disk_panel(batch, engine, tmp_path, monkeypatch):
    vt = _vocab()
    r = batch[0]
    texts, E = _prepare_measured(r, engine, vt)
    monkeypatch.setattr(controls, "SEGMENTS_DIR", tmp_path)
    for i, t in enumerate(OTHER_TEXTS):
        _write_segment(tmp_path, f"20260910_12000{i}_{i:012d}_segment.json", f"guid-disk-{i}", f"Disk {i}", {"A": t})
    out = controls.compute_controls(r, batch, 0, engine, vt, texts, r["story"], embeddings=E,
                                    void_fn=bp._compute_void, panel_vix=bp._panel_vix)
    d = out["density"]
    assert d["n_panel"] == 5 and len(set(d["control_guids"])) == 4 and "guid-own" not in d["control_guids"]
    assert d["control_methods"][0] == "batch_mate" and set(d["control_methods"][1:]) == {"disk_segment"}
    assert d["control_mixed"] < d["measured"]
    assert d["vix_method"] == "_panel_vix" and d["control_mean_vix"] > d["measured_mean_vix"]
    # the mixed panel is own response 0 + one text per other story, scored by the production function
    mixed_texts = [texts[0]] + [OTHER_TEXTS[0]] + [OTHER_TEXTS[1], OTHER_TEXTS[2], OTHER_TEXTS[3]]
    exp = engine.compute_consensus_density(engine.embed_texts(mixed_texts))
    assert d["control_mixed"] == pytest.approx(exp, abs=1e-3)
    sent = controls.control_sentence("beat_04_density", out)
    assert sent == f" Control: a panel of one summary from each of 5 different stories scores {d['control_mixed']:.3f} on the same measure."


# ── (v) failures never raise, and produce no sentence ─────────────────

def test_compute_controls_without_control_story_yields_errors_not_exceptions(batch, engine, tmp_path):
    vt = _vocab()
    r = batch[0]
    texts, E = _prepare_measured(r, engine, vt)
    out = controls.compute_controls(r, [r], 0, engine, vt, texts, r["story"], embeddings=E,
                                    void_fn=bp._compute_void, panel_vix=bp._panel_vix, segments_dir=tmp_path / "none")
    assert out["control_story"] is None
    for probe in ("void", "source_void", "killshots", "compression"):
        assert "error" in out[probe]
    assert out["density"]["control_mixed"] is None and out["density"]["n_panel"] == 1
    for kind in ("beat_04_density", "beat_04b_absent_words", "void", "beat_11_compression_report"):
        assert controls.control_sentence(kind, out) == ""
    assert controls.control_sentence("beat_15_killshots", out, claim=CLAIM) == ""


def test_compute_controls_survives_a_broken_picker_and_engine(batch, engine, tmp_path, monkeypatch):
    vt = _vocab()
    r = batch[0]
    texts, E = _prepare_measured(r, engine, vt)

    def boom(*a, **k):
        raise RuntimeError("picker exploded")
    monkeypatch.setattr(controls, "pick_control_story", boom)
    out = controls.compute_controls(r, batch, 0, engine, vt, texts, r["story"], embeddings=E,
                                    void_fn=bp._compute_void, panel_vix=bp._panel_vix, segments_dir=tmp_path)
    assert "picker exploded" in out["control_story_error"]
    assert all("error" in out[p] for p in ("void", "source_void", "killshots", "compression"))
    # an engine that raises breaks only the probes that embed
    monkeypatch.undo()

    class Broken(FakeEngine):
        def embed_texts(self, texts):
            raise RuntimeError("no embeddings today")
    out2 = controls.compute_controls(r, batch, 0, Broken({}), vt, texts, r["story"], embeddings=None,
                                     void_fn=bp._compute_void, panel_vix=bp._panel_vix, segments_dir=tmp_path)
    assert "error" in out2["void"] and "error" in out2["killshots"]
    assert "error" not in out2["source_void"] and "error" not in out2["compression"]
    assert controls.control_sentence("void", out2) == ""
    assert controls.control_sentence("beat_04b_absent_words", out2).startswith(" Control: another article's")


# ── (iv) sentences: exact templates, '' when absent ───────────────────

FIXTURE = {
    "version": 1,
    "void": {"pool_n": 186, "absent_n": 173, "absent_frac": 0.9301, "control_pool_n": 184,
             "control_absent_n": 183, "control_absent_frac": 0.9946},
    "source_void": {"absent_ratio": 0.223, "control_absent_ratio": 0.719},
    "killshots": {"n_claims": 1, "mean_max_sim_own": 0.734, "mean_max_sim_control": 0.4571,
                  "per_claim": [{"claim": "X happened", "max_sim_own": 0.734,
                                 "max_sim_control": 0.4571, "n_omitted_control": 5}]},
    "density": {"measured": 0.9291, "control_mixed": 0.5517, "n_panel": 5},
    "compression": {"hedges_total": 2, "hedges_total_control": 9, "entity_retention": 0.69,
                    "entity_retention_control": 0.104, "n_control_responses": 5},
}


def test_control_sentence_exact_templates():
    assert controls.control_sentence("beat_04_density", FIXTURE) == \
        " Control: a panel of one summary from each of 5 different stories scores 0.552 on the same measure."
    assert controls.control_sentence("beat_04b_absent_words", FIXTURE) == \
        " Control: another article's content words were 72 percent absent from these same responses."
    assert controls.control_sentence("void", FIXTURE) == (
        " Control: of the 186 words nearest this headline, 93 percent were absent from the responses; "
        "of the 184 words nearest an unrelated headline, 99 percent were absent.")
    assert controls.control_sentence("beat_11_compression_report", FIXTURE) == (
        " Control: five summaries of an unrelated story scored against this article insert 9 attribution "
        "buffers and retain 0.10 of its entities.")
    assert controls.control_sentence("beat_15_killshots", FIXTURE, claim="X happened") == \
        " Nearest response scored 0.73 here, 0.46 against an unrelated panel; omitted means below 0.65."
    assert controls.control_sentence("beat_15_killshots", FIXTURE, claim="unknown claim") == ""
    assert controls.control_sentence("beat_15_killshots", FIXTURE) == ""
    four = json.loads(json.dumps(FIXTURE)); four["compression"]["n_control_responses"] = 4
    assert controls.control_sentence("beat_11_compression_report", four).startswith(" Control: four summaries")
    for kind in ("beat_04_density", "beat_04b_absent_words", "void", "beat_11_compression_report"):
        s = controls.control_sentence(kind, FIXTURE)
        assert re.match(r"^ Control: .+\.$", s) and s.count("Control:") == 1
        assert not re.search(r"\b(meaningless|artifact|not evidence|so)\b", s)


@pytest.mark.parametrize("bad", [{}, None, {"version": 1}, {"density": {"error": "x"}, "void": {"error": "y"},
                                                             "source_void": {"error": "z"}, "killshots": {"error": "w"},
                                                             "compression": {"error": "v"}}])
def test_control_sentence_empty_when_missing_or_failed(bad):
    for kind in ("beat_04_density", "beat_04b_absent_words", "void", "beat_11_compression_report",
                 "beat_15_killshots", "beat_20_archive", "nonsense"):
        assert controls.control_sentence(kind, bad, claim="X happened") == ""
    small = {"density": {"measured": 0.9, "control_mixed": 0.5, "n_panel": 2}}   # < 3 stories -> silent
    assert controls.control_sentence("beat_04_density", small) == ""


# ── aggregates for the site and the ledger ────────────────────────────

def test_summarize_controls_and_ledger_line():
    s = controls.summarize_controls([FIXTURE, {}, None, {"density": {"error": "x"}}])
    assert s["stories_with_controls"] == 2                      # {} and None are not records; error rows count as records
    assert s["mean_density_control"] == pytest.approx(0.5517)
    assert s["mean_density_measured"] == pytest.approx(0.9291)
    assert s["mean_void_pool_control"] == pytest.approx(0.9946)
    assert s["mean_killshot_max_sim_own"] == pytest.approx(0.734)
    assert s["mean_killshot_max_sim_control"] == pytest.approx(0.4571)
    assert s["mean_hedges_control_other_panel"] == 9.0
    empty = controls.summarize_controls([])
    assert empty["stories_with_controls"] == 0 and empty["mean_density_control"] is None
    line = controls.ledger_line(FIXTURE)
    assert line == ("density 0.929 vs mixed-panel 0.552; absent 22% vs other-article 72%; "
                    "void pool 93% vs unrelated-headline 99%; killshot nearest-response similarity 0.73 vs "
                    "unrelated-panel 0.46; hedges 2 vs other-panel 9")
    assert controls.ledger_line({}) == "" and controls.ledger_line(None) == ""


# ── exporter and ledger carry the field, default to {} on old segments ─

def _full_segment(guid, title, controls_block, ts="20260910_120000"):
    return {
        "id": "abc", "timestamp": ts,
        "beats": [{"phase": "beat_04_density", "speaker": "Host", "text": "Consensus density is 0.9."}],
        "attribution": {
            "story_title": title, "story_url": guid, "story_guid": guid, "category": "world",
            "consensus_density": 0.9, "mean_vix": 17.0, "state_flag": "CONTESTED",
            "model_vix": {"A": 10.0, "B": 24.0}, "void_words": ["one"], "logos_words": ["two"],
            "null_space_claims": [], "claim_killshots": [], "compression": {}, "source_void": {},
            "void_context": [], "preregistration": {},
            **({"controls": controls_block} if controls_block is not None else {}),
        },
    }


def test_data_exporter_story_and_summary_controls(tmp_path, monkeypatch):
    import data_exporter as de
    seg_dir = tmp_path / "segments"; seg_dir.mkdir()
    docs = tmp_path / "docs"
    monkeypatch.setattr(de, "SEGMENTS_DIR", seg_dir)
    monkeypatch.setattr(de, "DOCS_DIR", docs)
    (seg_dir / "20260910_120000_aaaaaaaaaaaa_segment.json").write_text(json.dumps(_full_segment("g1", "With", FIXTURE)))
    (seg_dir / "20260910_120100_bbbbbbbbbbbb_segment.json").write_text(json.dumps(_full_segment("g2", "Without", None)))
    out = de.export_daily_json("20260910")
    assert out["version"] == "eigentrace-data-v1"                         # unchanged
    by_title = {s["title"]: s for s in out["stories"]}
    assert by_title["With"]["controls"] == FIXTURE
    assert by_title["Without"]["controls"] == {}
    sc = out["summary"]["controls"]
    assert sc["stories_with_controls"] == 1
    assert sc["mean_density_control"] == pytest.approx(0.5517)
    assert sc["mean_absent_ratio_control"] == pytest.approx(0.719)
    assert out["summary"]["mean_density"] == 0.9                          # old keys untouched
    written = json.loads((docs / "data" / "20260910.json").read_text())
    assert written["stories"][0]["controls"]["version"] == 1
    for key in ("compression", "source_void", "claim_killshots", "preregistration"):
        assert key in written["stories"][0]


def test_daily_digest_controls_lines(tmp_path, monkeypatch):
    import claim_extractor as ce
    seg_dir = tmp_path / "segments"; seg_dir.mkdir()
    monkeypatch.setattr(ce, "SEGMENTS_DIR", seg_dir)
    monkeypatch.setattr(ce, "_MATH_AVAILABLE", False)                     # no BGE model in a unit test
    (seg_dir / "20260910_120000_aaaaaaaaaaaa_segment.json").write_text(json.dumps(_full_segment("g1", "With", FIXTURE)))
    (seg_dir / "20260910_120100_bbbbbbbbbbbb_segment.json").write_text(json.dumps(_full_segment("g2", "Without", None)))
    content = ce.daily_digest("20260910", output_dir=tmp_path / "digests")
    assert "**Mean density (mixed-panel null):** 0.552 (1 stories with controls)" in content
    assert content.count("**Controls:** density 0.929 vs mixed-panel 0.552") == 1
    assert (tmp_path / "digests" / "omission_ledger_20260910.md").exists()
    # a day with no controls at all prints neither line
    (seg_dir / "20260910_120000_aaaaaaaaaaaa_segment.json").write_text(json.dumps(_full_segment("g1", "With", None)))
    content2 = ce.daily_digest("20260910", output_dir=tmp_path / "digests")
    assert "Controls:" not in content2 and "mixed-panel null" not in content2
