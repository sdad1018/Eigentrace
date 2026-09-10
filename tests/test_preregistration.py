"""preregistration: the pre-registration ledger (2026-09-10).

CPU only, no live processes, no GPU, no network. The ledger is always pointed
at tmp_path through PREREG_LEDGER; the runtime ledger is never touched.
Stored segments are read (never written) by two tests that skip when the
runtime segments dir is absent.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

import preregistration as pr

STORY = "20260910_1200{:02d}_{}_segment.json"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    p = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("PREREG_LEDGER", str(p))
    return p


def _row(actual, kind="bootstrap", category="war", panel=None, guid=None,
         ts="2026-09-01T00:00:00.000000Z", predicted=None, hit=None, flag="CONTESTED",
         prob=None, prereg_id=None):
    return {
        "kind": kind, "ts": ts, "scored_at": ts, "story_guid": guid or f"g-{actual}-{ts}",
        "category": category, "panel": panel or ["ChatGPT", "DeepSeek", "Gemini", "Grok"],
        "predicted": predicted, "actual": actual, "hit": hit, "state_flag": flag,
        "prediction_prob": prob, "prereg_id": prereg_id,
    }


# ---------------------------------------------------------------------------
# 1. shared outlier rule
# ---------------------------------------------------------------------------

def test_actual_outlier_tie_break_alphabetical():
    mv = {"Grok": 20.0, "ChatGPT": 20.0, "DeepSeek": 5.0}
    assert pr.actual_outlier(mv) == "ChatGPT"
    assert pr.actual_outlier(mv) == sorted(mv.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    assert pr.actual_margin(mv) == 0.0                      # exact tie is visible
    assert pr.actual_margin({"A": 10.0, "B": 7.5}) == 2.5
    assert pr.actual_outlier({}) is None
    assert pr.actual_margin({"A": 1.0}) == 0.0


def test_content_hash_order_independent_and_sensitive():
    a = pr.content_hash({"ChatGPT": "x", "Grok": "y"})
    b = pr.content_hash({"Grok": "y", "ChatGPT": "x"})
    c = pr.content_hash({"Grok": "y", "ChatGPT": "x."})
    assert a == b and a != c and len(a) == 64


# ---------------------------------------------------------------------------
# 2. the prior
# ---------------------------------------------------------------------------

def test_predict_outlier_category_prior_and_global_fallback():
    hist = [_row("DeepSeek") for _ in range(25)] + [_row("ChatGPT") for _ in range(15)]
    hist += [_row("Grok", category="tech") for _ in range(3)]
    panel = ["ChatGPT", "DeepSeek", "Gemini", "Grok"]
    now = "2026-09-10T00:00:00.000000Z"

    war = pr.predict_outlier(hist, "war", panel, "new-guid", now)
    assert war["predicted"] == "DeepSeek"
    assert war["prior_source"] == "category:war"
    assert war["n_used"] == 40 and war["counts"] == {"ChatGPT": 15, "DeepSeek": 25}
    assert war["prediction_prob"] == round(25 / 40, 4)
    assert war["predicted_flag"] == "CONTESTED"
    assert war["K"] == pr.K_PRIOR and war["prior_version"] == pr.PRIOR_VERSION

    tech = pr.predict_outlier(hist, "tech", panel, "new-guid", now)   # 3 < MIN_CATEGORY
    assert tech["prior_source"] == "global"
    assert tech["n_used"] == 43 and tech["predicted"] == "DeepSeek"

    cold = pr.predict_outlier([], "war", panel, "new-guid", now)
    assert cold["predicted"] is None and cold["prior_source"] == "none" and cold["n_used"] == 0
    assert cold["prediction_prob"] is None


def test_predict_outlier_ignores_leaky_off_panel_and_outcome_free_rows():
    panel = ["ChatGPT", "DeepSeek", "Gemini", "Grok"]
    now = "2026-09-10T00:00:00.000000Z"
    base = [_row("ChatGPT") for _ in range(6)] + [_row("DeepSeek") for _ in range(4)]
    assert pr.predict_outlier(base, "war", panel, "me", now)["predicted"] == "ChatGPT"

    # (a) Claude dominates history but is not on this panel -> never predicted
    with_claude = base + [_row("Claude", panel=["ChatGPT", "Claude", "DeepSeek"]) for _ in range(7)]
    p = pr.predict_outlier(with_claude, "war", panel, "me", now)
    assert p["predicted"] == "ChatGPT" and p["n_used"] == 10 and "Claude" not in p["counts"]
    p5 = pr.predict_outlier(with_claude, "war", panel + ["Claude"], "me", now)
    assert p5["predicted"] == "Claude"                     # same rows, Claude on the panel -> flips

    # (b) the story's own outcome (same guid) is never in its prior
    own = base + [_row("DeepSeek", guid="me") for _ in range(3)]
    assert pr.predict_outlier(own, "war", panel, "me", now)["predicted"] == "ChatGPT"
    assert pr.predict_outlier(own, "war", panel, "someone-else", now)["predicted"] == "DeepSeek"

    # (c) rows scored at or after now_ts are the future and are ignored
    later = base + [_row("DeepSeek", ts="2026-09-10T00:00:00.000000Z") for _ in range(3)]
    assert pr.predict_outlier(later, "war", panel, "me", now)["predicted"] == "ChatGPT"
    assert pr.predict_outlier(later, "war", panel, "me", "2026-09-11T00:00:00.000000Z")["predicted"] == "DeepSeek"

    # (d) sealed-but-unscored rows and aired rows carry no outcome
    noise = base + [_row(None, kind="predicted", predicted="DeepSeek") for _ in range(5)]
    noise += [_row("DeepSeek", kind="aired") for _ in range(5)]
    p = pr.predict_outlier(noise, "war", panel, "me", now)
    assert p["predicted"] == "ChatGPT" and p["n_used"] == 10


def test_predict_outlier_filters_then_tails_k():
    panel = ["ChatGPT", "DeepSeek", "Gemini", "Grok"]
    now = "2026-09-10T00:00:00.000000Z"
    hist = [_row("Grok", ts=f"2026-08-01T00:00:{i:02d}.000000Z") for i in range(40)]
    hist += [_row("Gemini", category="tech", ts=f"2026-08-02T00:00:{i:02d}.000000Z") for i in range(40)]
    hist += [_row("DeepSeek", ts=f"2026-08-03T00:00:{i:02d}.000000Z") for i in range(30)]
    p = pr.predict_outlier(hist, "war", panel, "me", now, K=50)
    assert p["n_used"] == 50                                   # category filter first, THEN the last K
    assert p["counts"] == {"DeepSeek": 30, "Grok": 20} and p["predicted"] == "DeepSeek"


# ---------------------------------------------------------------------------
# 3. the two-row seal through the producer's stage 2b / stage 3 helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeResp:
    name: str
    text: str
    skipped: bool = False
    error: str = ""
    eigen_vix: float = 0.0


@dataclass
class FakeStory:
    title: str
    guid: str
    category: str
    url: str = "https://example.invalid/x"
    summary: str = ""


def _seed_history(path, n_chatgpt=7, n_deepseek=3):
    for i in range(n_chatgpt):
        pr.append_row(_row("ChatGPT", ts=f"2026-09-01T00:00:{i:02d}.000000Z"), path)
    for i in range(n_deepseek):
        pr.append_row(_row("DeepSeek", ts=f"2026-09-01T00:01:{i:02d}.000000Z"), path)


def test_stage_2b_seals_before_stage_3_scores(ledger):
    import batch_producer as bp
    _seed_history(ledger)
    results = [{
        "story": FakeStory("A war story about something", "guid-1", "war"),
        "responses": [FakeResp("ChatGPT", "alpha"), FakeResp("DeepSeek", "beta"),
                      FakeResp("Grok", "", error="boom"), FakeResp("Claude", "", skipped=True)],
    }]
    bp.stage_2b_preregister(results, write=True)
    pre = results[0]["preregistration"]
    assert pre["sealed"] is True and pre["predicted"] == "ChatGPT"
    assert pre["panel"] == ["ChatGPT", "DeepSeek"]                # errors and skips are not seated
    assert pre["prior_source"] == "category:war" and pre["n_used"] == 10
    assert pre["content_hash"] == pr.content_hash({"ChatGPT": "alpha", "DeepSeek": "beta"})
    assert "actual" not in pre

    lines = ledger.read_text(encoding="utf-8").splitlines()
    sealed_line = lines[-1]
    sealed = json.loads(sealed_line)
    assert sealed["kind"] == "predicted" and "actual" not in sealed and "prereg_id" not in sealed
    assert sealed["predicted"] == "ChatGPT" and sealed["content_hash"] == pre["content_hash"]
    assert pre["prereg_id"] == hashlib.sha256(sealed_line.encode("utf-8")).hexdigest()[:16]
    assert pre["prereg_id"] == pr.line_id(sealed_line)
    n_lines = len(lines)

    # stage 3: score against model_vix computed later; the scored row links back by prereg_id
    bp._prereg_score(results[0], {"ChatGPT": 10.0, "DeepSeek": 30.0}, 20.0, 0.5)
    pre = results[0]["preregistration"]
    assert pre["actual"] == "DeepSeek" and pre["hit"] is False and pre["actual_margin"] == 20.0
    assert pre["state_flag"] == "CONTESTED" and pre["flag_hit"] is True
    assert pre["n_scored"] == 1 and pre["hits"] == 0 and pre["running_accuracy"] == 0.0
    assert pre["majority_base"] == 1.0 and pre["chance"] == 0.5
    assert pre["mean_prediction_prob"] == 0.7
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == n_lines + 1
    scored = json.loads(lines[-1])
    assert scored["kind"] == "scored" and scored["prereg_id"] == pre["prereg_id"]
    assert pr._norm_ts(sealed["predicted_at"]) <= pr._norm_ts(scored["scored_at"])
    assert scored["actual"] == "DeepSeek" and scored["predicted"] == "ChatGPT"

    # the ledger reader re-derives the id of the sealed line, so any reader can find it
    rows = pr.read_ledger(ledger)
    ids = [r.get("prereg_id") for r in rows if r.get("kind") == "predicted"]
    assert ids == [pre["prereg_id"]]

    # the next story's prior now sees this outcome (kind='scored') but not the sealed row
    nxt = pr.predict_outlier(rows, "war", ["ChatGPT", "DeepSeek"], "guid-2", pr.utc_now_iso())
    assert nxt["n_used"] == 11 and nxt["counts"] == {"ChatGPT": 7, "DeepSeek": 4}


def test_stage_2b_dry_run_and_thin_panels_write_nothing(ledger):
    import batch_producer as bp
    _seed_history(ledger)
    n_before = len(ledger.read_text(encoding="utf-8").splitlines())

    dry = [{"story": FakeStory("t", "g-dry", "war"),
            "responses": [FakeResp("ChatGPT", "a"), FakeResp("DeepSeek", "b")]}]
    bp.stage_2b_preregister(dry, write=False)
    assert dry[0]["preregistration"]["sealed"] is False
    assert dry[0]["preregistration"]["predicted"] == "ChatGPT"     # forecast still computed in memory
    bp._prereg_score(dry[0], {"ChatGPT": 40.0, "DeepSeek": 1.0}, 20.5, 0.3)
    assert dry[0]["preregistration"]["hit"] is True
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == n_before

    thin = [{"story": FakeStory("t", "g-thin", "war"), "responses": [FakeResp("ChatGPT", "a")]}]
    bp.stage_2b_preregister(thin, write=True)
    assert thin[0]["preregistration"]["sealed"] is False
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == n_before

    # an empty results list and a story with no responses never raise
    assert bp.stage_2b_preregister([], write=True) == []
    odd = [{"story": FakeStory("t", "g-odd", "war"), "responses": []}]
    bp.stage_2b_preregister(odd, write=True)
    assert odd[0]["preregistration"]["predicted"] is None


# ---------------------------------------------------------------------------
# 4. running window excludes bootstrap rows
# ---------------------------------------------------------------------------

def test_running_stats_uses_only_scored_predicted_rows():
    rows = [_row("ChatGPT", ts=f"2026-08-01T00:{i // 60:02d}:{i % 60:02d}.000000Z") for i in range(600)]
    for i in range(10):
        pid = f"id{i:02d}"
        hit = i < 7
        rows.append(_row(None, kind="predicted", predicted="ChatGPT", prob=0.6, prereg_id=pid,
                         ts=f"2026-09-01T01:00:{i:02d}.000000Z"))
        rows.append(_row("ChatGPT" if hit else "DeepSeek", kind="scored", predicted="ChatGPT",
                         hit=hit, prereg_id=pid, ts=f"2026-09-01T01:01:{i:02d}.000000Z",
                         panel=["ChatGPT", "DeepSeek", "Gemini", "Grok"] if i % 2 else
                               ["ChatGPT", "Claude", "DeepSeek", "Gemini", "Grok"]))
    rows.append(_row(None, kind="predicted", predicted="ChatGPT", prob=0.9, prereg_id="orphan"))
    st = pr.running_stats(rows, None)
    assert st["n_scored"] == 10 and st["hits"] == 7 and st["running_accuracy"] == 0.7
    assert st["majority_base"] == 0.7                          # 7 of 10 actuals are ChatGPT
    assert st["chance"] == round((5 * 0.25 + 5 * 0.2) / 10, 4)
    assert st["mean_prediction_prob"] == 0.6                   # from the sealed rows, not the scored ones
    assert st["n_unscored"] == 1

    # this_row is counted once even if its scored row is already in the ledger
    this = dict(rows[-2]); this["hit"] = True
    assert pr.running_stats(rows, this)["n_scored"] == 10
    new = _row("ChatGPT", kind="scored", predicted="ChatGPT", hit=True, prereg_id="new", prob=0.5)
    st2 = pr.running_stats(rows, new)
    assert st2["n_scored"] == 11 and st2["hits"] == 8
    assert pr.running_stats([], None)["n_scored"] == 0
    assert pr.running_stats(rows, None, M=4)["n_scored"] == 4


# ---------------------------------------------------------------------------
# 5. the shared state-flag rule
# ---------------------------------------------------------------------------

def test_state_flag_rule_thresholds():
    import batch_producer as bp
    assert bp._state_flag(30.01, 0.1) == "HIGH_FRICTION"
    assert bp._state_flag(30.0, 0.99) == "CONTESTED"
    assert bp._state_flag(15.01, 0.99) == "CONTESTED"
    assert bp._state_flag(15.0, 0.91) == "LOCKSTEP"
    assert bp._state_flag(15.0, 0.9) == "NOMINAL"
    assert bp._state_flag(0.0, 0.0) == "NOMINAL"


def _stored_story_files(limit):
    d = pr.segments_dir()
    if not d.exists():
        return d, []
    names = sorted(f for f in os.listdir(d) if pr.STORY_SEG_RE.match(f))
    return d, names[-limit:]


def test_state_flag_matches_stored_segments():
    import batch_producer as bp
    d, names = _stored_story_files(400)
    if len(names) < 50:
        pytest.skip("runtime segments dir absent or too small")
    checked = 0
    for name in names:
        try:
            seg = json.loads((d / name).read_text(encoding="utf-8"))
        except Exception:
            continue
        attr = seg.get("attribution") or {}
        if seg.get("segment_type") or not attr.get("model_vix") or not attr.get("state_flag"):
            continue
        assert bp._state_flag(attr["mean_vix"], attr["consensus_density"]) == attr["state_flag"], name
        checked += 1
    assert checked >= 50


# ---------------------------------------------------------------------------
# 6. bootstrap + replay on stored history: the forecast is a base rate
# ---------------------------------------------------------------------------

def test_bootstrap_and_replay_document_the_base_rate(ledger):
    _, names = _stored_story_files(600)
    if len(names) < 200:
        pytest.skip("runtime segments dir absent or too small")
    written = pr.bootstrap_ledger_from_segments(300)
    assert written > 100
    assert pr.bootstrap_ledger_from_segments(300) == 0            # never re-runs on a non-empty ledger
    rows = pr.read_ledger(ledger)
    assert all(r["kind"] == "bootstrap" and r["predicted"] is None and r["actual"] for r in rows)
    assert pr.running_stats(rows, None)["n_scored"] == 0          # bootstrap rows never feed the accuracy
    rep = pr.replay(300)
    assert rep["n_scored"] > 100
    assert abs(rep["accuracy"] - rep["majority_base"]) <= 0.05
    assert rep["accuracy"] > rep["chance"]


def test_bootstrap_skips_non_story_files(tmp_path, ledger):
    seg_dir = tmp_path / "segments"
    seg_dir.mkdir()
    good = {"timestamp": "20260910_120001", "attribution": {
        "story_guid": "g1", "story_title": "T" * 100, "category": "war", "state_flag": "CONTESTED",
        "model_vix": {"ChatGPT": 21.4, "Claude": 27.4, "Gemini": 21.2}}}
    (seg_dir / STORY.format(1, "0123456789ab")).write_text(json.dumps(good))
    weasel = dict(good, segment_type="wild_weasel")
    (seg_dir / STORY.format(2, "0123456789ac")).write_text(json.dumps(weasel))
    (seg_dir / STORY.format(3, "0123456789ad")).write_text(json.dumps({"attribution": {"story_title": "x"}}))
    (seg_dir / STORY.format(4, "0123456789ae")).write_text("not json")
    (seg_dir / "20260910_120005_idle_segment.json").write_text(json.dumps(good))
    (seg_dir / "20260910_120006_roundtable_segment.json").write_text(json.dumps(good))
    (seg_dir / "20260910_120007_0123456789ab_pundit_segment.json").write_text(json.dumps(good))
    assert pr.bootstrap_ledger_from_segments(600, seg_dir=seg_dir) == 1
    rows = pr.read_ledger()
    assert len(rows) == 1
    r = rows[0]
    assert r["kind"] == "bootstrap" and r["actual"] == "Claude" and r["predicted"] is None
    assert r["panel"] == ["ChatGPT", "Claude", "Gemini"] and r["actual_margin"] == 6.0
    assert r["scored_at"] == "2026-09-10T12:00:01.000000Z" and len(r["story_title"]) == 80
    assert pr.bootstrap_ledger_from_segments(600, seg_dir=seg_dir) == 0
    assert pr.bootstrap_ledger_from_segments(600, seg_dir=seg_dir, force=True) == 1
    assert pr.read_ledger_tail(1)[0]["kind"] == "bootstrap"


def test_ledger_round_trip_skips_bad_lines(ledger):
    pr.append_row({"kind": "bootstrap", "actual": "Grok"})
    ledger.write_text(ledger.read_text() + "garbage\n\n[1,2]\n", encoding="utf-8")
    pid = pr.seal_prediction({"predicted": "Grok", "prereg_id": "must-be-dropped"})
    rows = pr.read_ledger()
    assert [r["kind"] for r in rows] == ["bootstrap", "predicted"]
    assert rows[1]["prereg_id"] == pid and "must-be-dropped" not in ledger.read_text()
    assert pr.read_ledger(tmp := ledger.with_name("missing.jsonl")) == [] and not tmp.exists()


# ---------------------------------------------------------------------------
# 7/8. the on-air sentence and the script beat
# ---------------------------------------------------------------------------

MISS = {"predicted": "ChatGPT", "actual": "DeepSeek", "hit": False, "running_accuracy": 0.56,
        "hits": 56, "n_scored": 100, "majority_base": 0.56, "chance": 0.24, "n_used": 50,
        "prior_source": "category:war", "category": "war",
        "counts": {"ChatGPT": 28, "DeepSeek": 12, "Gemini": 5, "Grok": 5}}

MISS_TEXT = ("Prediction check. Before any model text was read or embedded, the ledger forecast "
             "from base rates that ChatGPT would diverge most: it was the outlier in 28 of the last "
             "50 war stories. DeepSeek did. Miss. Running tally: 56 of 100 correct. Always guessing "
             "the commonest model would score 56 percent; chance is 24 percent. This is a base-rate "
             "forecast, not foresight.")


def test_ledger_sentence_templates_exact():
    assert pr.build_ledger_sentence(MISS) == MISS_TEXT
    hit = dict(MISS, actual="ChatGPT", hit=True, hits=57, running_accuracy=0.57)
    assert pr.build_ledger_sentence(hit) == MISS_TEXT.replace("DeepSeek did. Miss.", "ChatGPT did. Hit.") \
        .replace("56 of 100", "57 of 100")
    glob = dict(MISS, prior_source="global", category="tech", n_used=43, counts={"ChatGPT": 20})
    assert pr.build_ledger_sentence(glob) == (
        "Prediction check. Before any model text was read or embedded, the ledger forecast from base "
        "rates that ChatGPT would diverge most: it was the outlier in 20 of the last 43 stories of any "
        "kind, because it has too few tech stories. DeepSeek did. Miss. Running tally: 56 of 100 "
        "correct. Always guessing the commonest model would score 56 percent; chance is 24 percent. "
        "This is a base-rate forecast, not foresight.")
    # the gate: silent without a prediction, without an outcome, or with a thin prior
    assert pr.build_ledger_sentence(dict(MISS, n_used=4)) == ""
    assert pr.build_ledger_sentence(dict(MISS, predicted=None)) == ""
    assert pr.build_ledger_sentence({k: v for k, v in MISS.items() if k != "actual"}) == ""
    assert pr.build_ledger_sentence({}) == "" and pr.build_ledger_sentence(None) == ""


def test_script_v3_beat_18d_reads_the_sealed_row():
    import script_v3

    class S:                       # stand-in for BroadcastState after predict()+score
        prediction_score = 0.5
        predicted_void_words = ["gaza", "minister"]
        predicted_outlier_model = None

    void_tail = ("I predicted these blind spots from past coverage: gaza, minister. Prediction "
                 "accuracy on this story: 50 percent. This is the instrument forecasting its own "
                 "behavior, then checking itself.")
    beat = script_v3._prediction_scorecard_beat({"preregistration": MISS}, None)
    assert beat == {"speaker": "Host", "text": MISS_TEXT, "phase": "beat_18d_prediction_scorecard"}
    both = script_v3._prediction_scorecard_beat({"preregistration": MISS}, S())
    assert both["text"] == MISS_TEXT + " " + void_tail
    only_void = script_v3._prediction_scorecard_beat({}, S())
    assert only_void["text"] == "Prediction check. " + void_tail        # the old sentence, unchanged
    assert script_v3._prediction_scorecard_beat({}, None) is None
    assert script_v3._prediction_scorecard_beat({"preregistration": dict(MISS, n_used=3)}, None) is None
    assert "would diverge most. " not in only_void["text"]              # the dead branch is gone


# ---------------------------------------------------------------------------
# 9. the exporter (tmp docs dir only)
# ---------------------------------------------------------------------------

def test_data_exporter_writes_ledger_fields(tmp_path, ledger, monkeypatch):
    import data_exporter as de
    seg_dir = tmp_path / "segments"
    docs = tmp_path / "docs"
    seg_dir.mkdir()
    monkeypatch.setattr(de, "SEGMENTS_DIR", seg_dir)
    monkeypatch.setattr(de, "DOCS_DIR", docs)

    scored = dict(MISS, sealed=True, prereg_id="abcdef0123456789", panel=["ChatGPT", "DeepSeek"],
                  K=50, prediction_prob=0.56, predicted_at="2026-09-10T12:00:00.000000Z",
                  scored_at="2026-09-10T12:00:05.000000Z", actual_margin=3.2,
                  mean_prediction_prob=0.55, n_unscored=0, prior_version=pr.PRIOR_VERSION)
    seg = {"timestamp": "20260910_120000", "beats": [], "attribution": {
        "story_title": "T", "story_guid": "g1", "category": "war", "model_vix": {"ChatGPT": 10, "DeepSeek": 13.2},
        "mean_vix": 11.6, "consensus_density": 0.5, "state_flag": "NOMINAL", "preregistration": scored}}
    (seg_dir / STORY.format(0, "0123456789ab")).write_text(json.dumps(seg))
    plain = {"timestamp": "20260910_120100", "beats": [], "attribution": {
        "story_title": "U", "story_guid": "g2", "category": "war", "model_vix": {"ChatGPT": 1, "Grok": 2},
        "mean_vix": 1.5, "consensus_density": 0.5, "state_flag": "NOMINAL"}}
    (seg_dir / STORY.format(1, "0123456789ac")).write_text(json.dumps(plain))

    out = de.export_daily_json("20260910")
    assert out["stories"][0]["preregistration"]["predicted"] == "ChatGPT"
    assert out["stories"][1]["preregistration"] == {}
    assert len(out["ledger"]) == 1
    led = out["ledger"][0]
    assert led["hit"] is False and led["prereg_id"] == "abcdef0123456789"
    assert led["in_sample_constant_guesser_share"] == 0.56 and led["date"] == "2026-09-10"
    s = out["summary"]["preregistration"]
    assert s["n_scored"] == 100 and s["hits"] == 56 and s["stories_scored_today"] == 1
    assert s["hits_today"] == 0 and s["in_sample_constant_guesser_share"] == 0.56
    assert s["prior_version"] == pr.PRIOR_VERSION
    assert json.loads((docs / "data" / "20260910.json").read_text())["ledger"][0]["predicted"] == "ChatGPT"

    # the full series from the ledger file: predicted + scored + aired joined by prereg_id
    pid = pr.seal_prediction({"predicted": "ChatGPT", "predicted_at": "2026-09-10T12:00:00.000000Z",
                              "story_guid": "g1", "category": "war", "n_used": 50, "prediction_prob": 0.56})
    pr.append_row({"kind": "scored", "prereg_id": pid, "predicted": "ChatGPT", "actual": "DeepSeek",
                   "hit": False, "majority_base": 0.56, "scored_at": "2026-09-10T12:00:05.000000Z"})
    pr.append_row({"kind": "aired", "prereg_id": pid, "segment_file": STORY.format(0, "0123456789ab")})
    pr.seal_prediction({"predicted": None, "story_guid": "cold"})          # cold start: not exported
    pr.seal_prediction({"predicted": "Grok", "story_guid": "orphan"})      # sealed, never scored
    series = de.export_preregistration_series(docs_dir=docs)
    assert series["version"] == "eigentrace-prereg-v1" and series["n_rows"] == 2
    assert series["n_scored"] == 1 and series["n_hits"] == 0 and series["accuracy_all_time"] == 0.0
    row = series["rows"][0]
    assert row["prereg_id"] == pid and row["actual"] == "DeepSeek" and row["scored"] is True
    assert row["in_sample_constant_guesser_share"] == 0.56
    assert row["aired_segment_file"] == STORY.format(0, "0123456789ab")
    assert series["rows"][1]["scored"] is False and series["rows"][1]["predicted"] == "Grok"
    on_disk = json.loads((docs / "data" / "preregistration_ledger.json").read_text())
    assert on_disk["n_rows"] == 2 and on_disk["prior_version"] == pr.PRIOR_VERSION
