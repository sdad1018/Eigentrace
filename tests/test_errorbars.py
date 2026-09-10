"""Error bars and sample sizes (2026-09-10): errorbars.py and every aggregate site that uses it.

CPU only, no network, no writes outside tmp_path: DOCS_DIR / SEGMENTS_DIR / DIGEST_DIR /
SOUL_HISTORY_DIR / AUDIT_LOG / OUT_PATH are monkeypatched, the host model calls are stubbed,
and every module that would scan the runtime archive is replaced by a fake.
"""
from __future__ import annotations

import json
import random
import re
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import errorbars as eb

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]


# ─── synthetic segments ─────────────────────────────────────────────────────

def _story(i, ts=None, guid=None, vix=None, density=None, state="CONTESTED", hedges=None):
    rnd = random.Random(1000 + i)
    if vix is None:
        base = {"ChatGPT": 20.0, "Claude": 22.0, "Gemini": 14.0, "DeepSeek": 21.0, "Grok": 15.0}
        vix = {m: round(base[m] + rnd.uniform(-4, 4), 1) for m in MODELS}
    ts = ts or (datetime(2026, 9, 10, 1, 0, 0) + timedelta(minutes=7 * i)).strftime("%Y%m%d_%H%M%S")
    return {
        "segment_type": None,
        "timestamp": ts,
        "attribution": {
            "story_title": f"Story {i}",
            "story_url": f"https://example.invalid/{i}",
            "story_guid": guid or f"guid-{i}",
            "category": "world" if i % 2 else "war",
            "consensus_density": density if density is not None else round(0.88 + rnd.uniform(0, 0.06), 3),
            "mean_vix": round(sum(vix.values()) / len(vix), 2),
            "state_flag": state,
            "model_vix": vix,
            "model_responses": {m: f"{m} says something about story {i}." for m in MODELS},
            "void_words": ["mediator", "walkout", f"w{i}"],
            "logos_words": ["envoy", "mediator"],
            "null_space_claims": [],
            "claim_killshots": [{"claim": "x", "salience": 0.7, "omitted_by": ["Grok"]}] * (i % 3),
            "compression": {
                "verb_downgrade": round(0.1 + rnd.uniform(0, 0.05), 3),
                "entity_retention": round(0.5 + rnd.uniform(0, 0.3), 3),
                "attribution_buffer": {"total": hedges if hedges is not None else 3 + (i % 5), "avg_per_model": 1.0},
                "compression_score": 0.3,
            },
            "source_void": {"absent_ratio": round(0.15 + rnd.uniform(0, 0.1), 3)},
            "void_context": [],
        },
        "beats": [{"phase": "beat_1_hook", "speaker": "Host", "text": f"Hook {i}"}],
    }


def _idle(i, date="20260910"):
    return {"segment_type": "idle", "timestamp": f"{date}_02{i:02d}00",
            "attribution": {"story_title": f"idle {i}", "story_guid": f"idle-{i}"}, "beats": []}


def _weasel(i):
    return {"segment_type": "wild_weasel", "timestamp": f"20260910_03{i:02d}00",
            "attribution": {"story_title": f"Story {i}", "story_guid": f"guid-{i}", "void_words_tested": ["a"],
                            "model_cliffs": {}, "phase_shifts": [], "resistors": [], "mean_max_cliff": 0.1},
            "beats": []}


def _write_segments(d: Path, segs, date="20260910"):
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(segs):
        name = f"{s.get('timestamp', date + '_000000')}_{i:012x}_segment.json"
        (d / name).write_text(json.dumps(s))


# ─── errorbars primitives ───────────────────────────────────────────────────

def test_boot_ci_deterministic_and_pinned():
    vals = [17.7, 20.1, 15.2, 22.9, 18.0, 19.4, 16.1]
    a = eb.boot_ci(vals, seed=42)
    b = eb.boot_ci(vals, seed=42)
    assert a == b
    assert a["n"] == 7 and a["seed"] == 42 and a["B"] == 2000 and a["method"] == "percentile_bootstrap"
    assert a["mean"] == pytest.approx(sum(vals) / 7)
    assert a["lo"] <= a["mean"] <= a["hi"]
    # pinned on first run: guards a silent RNG change
    assert a["lo"] == pytest.approx(16.857142857142858)
    assert a["hi"] == pytest.approx(20.5)
    c = eb.boot_ci(vals, seed=7)
    assert c["mean"] == a["mean"]
    assert not a["insufficient"]


def test_boot_ci_edges():
    assert eb.boot_ci([], seed=1)["mean"] is None
    assert eb.boot_ci([], seed=1)["n"] == 0
    one = eb.boot_ci([3.0], seed=1)
    assert one["mean"] == 3.0 and one["lo"] is None and one["hi"] is None and one["insufficient"]
    const = eb.boot_ci([2.0] * 6, seed=1)
    assert const["lo"] == const["hi"] == const["mean"] == 2.0
    small = eb.boot_ci([1, 2, 3, 4], seed=1)
    assert small["insufficient"] and small["lo"] is not None
    med = eb.boot_ci([1, 2, 3, 4, 100], seed=1, stat="median")
    assert med["mean"] == 3.0 and med["stat"] == "median"
    with pytest.raises(ValueError):
        eb.boot_ci([1, 2], stat="mode")


def test_boot_ci_width_sanity():
    rnd = random.Random(0)
    draws = [rnd.gauss(0, 1) for _ in range(200)]
    c = eb.boot_ci(draws, seed=0)
    width = c["hi"] - c["lo"]
    assert abs(width - 0.277) / 0.277 < 0.25


def test_wilson_ci():
    z = eb.wilson_ci(0, 10)
    assert z["lo"] == 0.0 and z["hi"] == pytest.approx(0.278, abs=0.005)
    assert eb.wilson_ci(10, 10)["hi"] == 1.0
    h = eb.wilson_ci(5, 10)
    assert h["point"] == 0.5 and h["lo"] == pytest.approx(0.237, abs=0.002) and h["hi"] == pytest.approx(0.763, abs=0.002)
    assert abs((0.5 - h["lo"]) - (h["hi"] - 0.5)) < 1e-9
    assert eb.wilson_ci(0, 0) is None
    for n in (1, 3, 9, 50):
        for k in range(n + 1):
            c = eb.wilson_ci(k, n)
            assert 0.0 <= c["lo"] <= c["point"] <= c["hi"] <= 1.0


def test_argmax_share_paired():
    clear = {"A": [30 + (i % 3) for i in range(9)], "B": [10 + (i % 3) for i in range(9)]}
    s = eb.argmax_share(clear, seed=1)
    assert s["winner"] == "A" and s["runner_up"] == "B" and s["share"] > 0.99 and s["n"] == 9
    assert s["seed"] == 1 and s["B"] == 2000
    # paired differences +1, -1, 0 repeating: the two means tie, so neither keeps the title reliably
    close = {"A": [20, 21, 19, 20, 21, 19, 20, 21, 19], "B": [21, 20, 19, 21, 20, 19, 21, 20, 19]}
    t = eb.argmax_share(close, seed=1)
    assert 0.3 < t["share"] < 0.8
    assert t["share"] + t["runner_up_share"] == pytest.approx(1.0)
    assert eb.argmax_share(close, seed=1) == t
    with pytest.raises(ValueError):
        eb.argmax_share({"A": [1, 2, 3], "B": [1, 2]})
    lo = eb.argmax_share(clear, seed=1, mode="min")
    assert lo["winner"] == "B"
    assert eb.argmax_share({}, seed=1)["winner"] is None


def test_is_story_and_series():
    assert eb.is_story(_story(1))
    assert not eb.is_story(_idle(1))
    assert not eb.is_story(_weasel(1))
    assert not eb.is_story({"segment_type": None, "attribution": {"story_title": "x", "model_vix": {}}})
    assert eb.NON_STORY_TYPES == ("idle", "silence", "consolidation", "weekly_compression", "governance",
                                  "foraging", "self_audit", "roundtable", "pundit_desk", "conversation")
    ser = eb.metric_series([_story(i) for i in range(4)] + [_idle(1)])
    assert len(ser["density"]) == 4 and len(ser["hedges"]) == 4 and len(ser["mean_vix"]) == 4
    paired, n = eb.per_model_lists([_story(i) for i in range(5)])
    assert n == 5 and set(paired) == set(MODELS)


def test_compute_window_delta_and_split():
    up = eb.compute_window_delta([0.91, 0.92, 0.93, 0.90], [0.85, 0.86, 0.84, 0.87], seed=3)
    assert up["direction"] == "increasing" and up["resolved"] and up["dlo"] > 0
    assert up["n_now"] == 4 and up["n_prev"] == 4 and up["seed"] == 3
    flat = eb.compute_window_delta([0.90, 0.92, 0.88, 0.91], [0.91, 0.89, 0.90, 0.92], seed=3)
    assert flat["direction"] == "not resolved" and not flat["resolved"] and flat["dlo"] <= 0 <= flat["dhi"]
    assert eb.compute_window_delta([], [1, 2]) is None
    tiny = eb.compute_window_delta([1.0], [2.0, 3.0], seed=1)
    assert tiny["dlo"] is None and tiny["direction"] == "not resolved"
    now = datetime(2026, 9, 10, 12, 0, 0)
    segs = [_story(1, ts="20260910_110000"), _story(2, ts="20260909_100000"), _story(3, ts="20260908_100000"),
            {"timestamp": "garbage"}]
    recent, earlier = eb.split_windows(segs, now=now, hours=24)
    assert [s["attribution"]["story_title"] for s in recent] == ["Story 1"]
    assert [s["attribution"]["story_title"] for s in earlier] == ["Story 2"]
    assert eb.daily_seed("20260910") == 20260910
    assert eb.hourly_seed(datetime(2026, 9, 10, 13, 5)) == 2026091013


def test_ci_md():
    c = {"lo": 14.7, "hi": 20.6, "n": 9}
    assert eb.ci_md(17.7, c) == "17.7 (95% CI 14.7-20.6, n=9)"
    assert eb.ci_md(17.7, {"lo": None, "n": 1}) == "17.7 (n=1, interval undefined)"
    assert eb.ci_md(None, {"n": 0}) == "n/a (n=0)"


# ─── data_exporter ──────────────────────────────────────────────────────────

def test_summarize_stories_keeps_old_formulas_and_adds_intervals():
    import data_exporter as de
    stories = []
    for i in range(9):
        a = _story(i, guid="guid-dup" if i < 2 else None)["attribution"]
        stories.append({"consensus_density": a["consensus_density"], "mean_vix": a["mean_vix"],
                        "state_flag": "LOCKSTEP" if i < 3 else "CONTESTED", "model_vix": a["model_vix"],
                        "void_words": a["void_words"], "logos_words": a["logos_words"], "guid": a["story_guid"],
                        "claim_killshots": a["claim_killshots"]})
    s1 = de.summarize_stories(stories, seed=20260910)
    s2 = de.summarize_stories(stories, seed=20260910)
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)
    assert s1["stories_analyzed"] == 9 and s1["n"] == 9 and s1["n_unique_guid"] == 8
    assert s1["mean_density"] == round(sum(x["consensus_density"] for x in stories) / 9, 3)
    assert s1["mean_vix"] == round(sum(x["mean_vix"] for x in stories) / 9, 1)
    assert s1["mean_vix_ci95"][0] <= s1["mean_vix"] <= s1["mean_vix_ci95"][1]
    assert s1["mean_density_ci95"][0] <= s1["mean_density"] <= s1["mean_density_ci95"][1]
    assert set(s1["per_model_vix"]) == set(MODELS)
    for m in MODELS:
        assert s1["per_model_vix"][m]["n"] == 9 and s1["per_model_vix"][m]["seed"] == 20260910
    assert s1["outlier"]["model"] in MODELS and 0 <= s1["outlier"]["bootstrap_share"] <= 1
    assert s1["outlier"]["runner_up"] != s1["outlier"]["model"]
    assert sum(s1["state_rates"][f]["k"] for f in ("LOCKSTEP", "CONTESTED", "HIGH_FRICTION")) == 9
    assert s1["state_rates"]["LOCKSTEP"]["k"] == 3
    assert s1["ci_seed"] == 20260910 and "seed=20260910" in s1["ci_method"]
    for key in de.SCHEMA_ADDITIONS:
        assert key.split(".", 1)[1] in s1, key
    empty = de.summarize_stories([], seed=1)
    assert empty["n"] == 0 and empty["mean_density"] is None and empty["mean_vix"] is None
    assert empty["mean_vix_ci95"] == [None, None]


def test_export_daily_json_filters_and_empty_day(tmp_path, monkeypatch):
    import data_exporter as de
    seg_dir = tmp_path / "segments"
    _write_segments(seg_dir, [_story(1, ts="20260910_010000"), _idle(1), _weasel(1)])
    monkeypatch.setattr(de, "SEGMENTS_DIR", seg_dir)
    monkeypatch.setattr(de, "DOCS_DIR", tmp_path / "docs")
    out = de.export_daily_json("20260910")
    assert out["version"] == "eigentrace-data-v1" and out["schema_revision"] == "1.1"
    assert out["summary"]["n"] == 1 and out["summary"]["stories_analyzed"] == 1
    assert out["summary"]["weasel_probes"] == 1
    assert out["summary"]["mean_vix_ci95"] == [None, None]  # n=1: no interval, never a fake one
    assert out["summary"]["ci_seed"] == 20260910
    written = json.loads((tmp_path / "docs" / "data" / "20260910.json").read_text())
    assert written["summary"]["n"] == 1 and "schema_additions" in written
    # a day with only system segments: n=0 and null, never 0.0
    _write_segments(seg_dir, [_idle(2, "20260909"), _idle(3, "20260909")])
    assert list(seg_dir.glob("20260909*_segment.json"))
    out2 = de.export_daily_json("20260909")
    assert out2["summary"]["n"] == 0
    assert out2["summary"]["mean_density"] is None and out2["summary"]["mean_vix"] is None
    assert out2["summary"]["stories_analyzed"] == 0


# ─── claim_extractor ────────────────────────────────────────────────────────

def test_daily_digest_story_filter_and_ci_lines(tmp_path, monkeypatch):
    import claim_extractor as ce
    seg_dir = tmp_path / "segments"
    stories = [_story(i, ts=f"20260910_0{i}0000") for i in range(1, 7)]
    _write_segments(seg_dir, stories + [_idle(1), _idle(2), _weasel(1)])
    monkeypatch.setattr(ce, "SEGMENTS_DIR", seg_dir)
    monkeypatch.setattr(ce, "DIGEST_DIR", tmp_path / "digests")
    monkeypatch.setattr(ce, "_MATH_AVAILABLE", False)
    text = ce.daily_digest("20260910", output_dir=tmp_path / "digests")
    assert "**Stories analyzed:** 6 (6 unique)" in text
    assert "density:** 0.000" not in text
    assert re.search(r"\*\*Mean consensus density:\*\* 0\.\d{3} \(95% CI 0\.\d{3}-0\.\d{3}, n=6\)", text)
    assert re.search(r"\*\*Mean model friction \(VIX\):\*\* \d+\.\d \(95% CI \d+\.\d-\d+\.\d, n=6\)", text)
    summary_block = text.split("## Stories")[0]
    assert summary_block.count("(95% CI") == 2
    for m in MODELS:
        assert re.search(rf"^- {m}: \d+\.\d \[\d+\.\d, \d+\.\d\] n=6 ", summary_block, re.M), m
    assert re.search(r"\*\*Daily VIX outlier:\*\* \w+ \(keeps the title in \d+% of resamples; runner-up \w+\)", summary_block)
    assert re.search(r"\*\*State breakdown:\*\* 0 lockstep \(0%, CI 0%-\d+%\) / 6 contested \(100%, CI \d+%-100%\) / 0 high friction", summary_block)
    assert "seed=20260910" in summary_block
    assert "## Wild Weasel Escalation Probes" in text
    # a day of only system segments writes no ledger at all instead of "9 stories, density 0.000"
    _write_segments(seg_dir, [_idle(3, "20260909"), _idle(4, "20260909")])
    assert list(seg_dir.glob("20260909*_segment.json"))
    assert ce.daily_digest("20260909", output_dir=tmp_path / "digests") == ""
    assert not (tmp_path / "digests" / "omission_ledger_20260909.md").exists()


# ─── soul_updater ───────────────────────────────────────────────────────────

def _cal_and_soul(n=12):
    import soul_updater as su
    segs = [_story(i) for i in range(n)]
    segs[0]["attribution"]["consensus_density"] = 0  # dropped per metric, so n_measured < stories
    cal = su.compute_calibration(segs, seed=2026091013)
    soul = su.generate_soul(cal, {"layers": ["Consensus Density"], "host_model": "x", "embedding": "y", "rag_count": 0}, "no diff")
    return su, segs, cal, soul


def test_compute_calibration_additive_keys():
    su, segs, cal, soul = _cal_and_soul()
    assert cal["stories"] == 12 and cal["n_measured"] == 11 and cal["n"]["density"] == 11
    assert cal["seed"] == 2026091013
    assert cal["density_ci"]["lo"] <= cal["density"] <= cal["density_ci"]["hi"]
    assert cal["density_ci"]["n"] == 11 and cal["density_ci"]["seed"] == 2026091013
    for k in ("absent_ratio_ci", "verb_drift_ci", "entity_retention_ci", "hedges_per_story_ci"):
        assert cal[k]["lo"] is not None
    assert set(cal["model_vix_ci"]) == set(MODELS)
    assert 0 <= cal["outlier_share"] <= 1 and cal["outlier_runner_up"] in MODELS
    assert 0 <= cal["aligned_share"] <= 1 and cal["n_paired"] == 12
    # the old keys keep their old formulas
    dens = [s["attribution"]["consensus_density"] for s in segs if s["attribution"]["consensus_density"] > 0]
    assert cal["density"] == round(sum(dens) / len(dens), 3)
    assert cal["hedges"] == sum(s["attribution"]["compression"]["attribution_buffer"]["total"] for s in segs)
    assert cal["outlier"] == max(cal["model_vix"], key=cal["model_vix"].get)
    # a prev.json written before the deploy is still readable
    old = {k: v for k, v in cal.items() if k in ("stories", "density", "verb_drift", "entity_retention",
                                                  "absent_ratio", "hedges", "model_vix", "outlier", "aligned")}
    assert isinstance(su.compute_diff(old, cal), str)


def test_generate_soul_table_keeps_trend_parsing(tmp_path, monkeypatch):
    su, segs, cal, soul = _cal_and_soul()
    assert f"## Current Instrument Readings ({cal['n_measured']} measured of {cal['stories']} stories, last 24h)" in soul
    assert "| Metric | Value | Meaning | 95% CI (n) |" in soul
    dens_row = next(l for l in soul.splitlines() if l.startswith("| Consensus Density"))
    cells = [c.strip() for c in dens_row.strip("|").split("|")]
    assert cells[1] == f"{cal['density']:.3f}"  # Value cell is a bare number
    assert cells[3] == f"[{cal['density_ci']['lo']:.3f}, {cal['density_ci']['hi']:.3f}] (11)"
    loss_row = next(l for l in soul.splitlines() if l.startswith("| Content Loss"))
    assert re.search(r"\| \[\d+%, \d+%\] \(12\) \|$", loss_row)
    hedge_row = next(l for l in soul.splitlines() if l.startswith("| Hedges (24h)"))
    assert hedge_row.rstrip().endswith("| (12) |")
    out_row = next(l for l in soul.splitlines() if l.startswith("| VIX Outlier"))
    assert re.search(rf"\| {cal['outlier']} \| Most divergent model \| \d+% of resamples; runner-up {cal['outlier_runner_up']} \|", out_row)
    assert re.search(r"^- \*\*\w+\*\*: \d+\.\d \(n=12, \d+\.\d-\d+\.\d\)$", soul, re.M)
    assert "- Name the outlier; if its bootstrap share is below 80% also name the runner-up." in soul
    assert f"Sample: {cal['n_measured']} measured of {cal['stories']} stories in the window." in soul
    # the director slice (900 chars from the header) still reaches the Most Aligned row
    import script_v3
    start = soul.find("Current Instrument Readings")
    aligned_end = soul.find("\n", soul.find("| Most Aligned"))
    assert script_v3._READINGS_SLICE == 900
    assert aligned_end - start < script_v3._READINGS_SLICE
    # the Behavioral Instructions slice (500, unchanged) still contains the new line
    bi = soul.find("Behavioral Instructions")
    assert "also name the runner-up" in soul[bi:bi + 500]
    # compute_trends takes the FIRST float cell per row: the trailing column must not break it
    hist = tmp_path / "soul_history"
    hist.mkdir()
    for h in range(3):
        (hist / f"soul_20260910_{h:02d}00.md").write_text(soul)
    monkeypatch.setattr(su, "SOUL_HISTORY_DIR", str(hist))
    trends = su.compute_trends()
    assert trends["density"]["recent_avg"] == cal["density"]
    assert trends["absent_ratio"]["recent_avg"] == pytest.approx(round(cal["absent_ratio"], 2), abs=0.006)
    assert trends["hedges"]["recent_avg"] == cal["hedges"]
    assert trends["density"]["n_readings"] == 3


def test_load_recent_segments_uses_is_story_and_skips_old_files(tmp_path, monkeypatch):
    import soul_updater as su
    now = datetime.utcnow()
    fresh = _story(1, ts=(now - timedelta(hours=2)).strftime("%Y%m%d_%H%M%S"))
    old = _story(2, ts=(now - timedelta(days=9)).strftime("%Y%m%d_%H%M%S"))
    weasel = _weasel(3)
    weasel["timestamp"] = fresh["timestamp"]
    idle = _idle(4)
    idle["timestamp"] = fresh["timestamp"]
    _write_segments(tmp_path / "segs", [fresh, old, weasel, idle])
    monkeypatch.setattr(su, "SEGMENT_DIR", str(tmp_path / "segs"))
    got = su.load_recent_segments(hours=24)
    assert [s["attribution"]["story_title"] for s in got] == ["Story 1"]


# ─── refresh_profiles.sh step 1 ─────────────────────────────────────────────

def test_refresh_profiles_step1_adds_ci_keys(tmp_path, monkeypatch, capsys):
    sh = (ROOT / "refresh_profiles.sh").read_text()
    m = re.search(r'# 1\. Update model profiles\npython3 -c "(.*?)\n"\n', sh, re.S)
    assert m, "step-1 python block not found"
    code = m.group(1).replace('\\"', '"')
    seg_dir = tmp_path / "segs"
    segs = [_story(i, ts=f"20260910_0{i}0000") for i in range(1, 8)]
    _write_segments(seg_dir, segs)
    out_path = tmp_path / "model_profiles.json"
    code = code.replace("'/home/remvelchio/eigentrace/tmp/segments'", repr(str(seg_dir)))
    code = code.replace("'docs/model_profiles.json'", repr(str(out_path)))
    assert str(seg_dir) in code and str(out_path) in code
    monkeypatch.chdir(ROOT)
    exec(compile(code, "refresh_profiles_step1", "exec"), {"__name__": "step1"})
    printed = capsys.readouterr().out
    assert "error bars skipped" not in printed
    prof = json.loads(out_path.read_text())
    assert prof["total_segments"] == 7 and "ci_method" in prof
    for mdl, d in prof["models"].items():
        assert d["segments_analyzed"] == 7
        assert d["mean_vix_ci95"][0] <= d["mean_vix"] <= d["mean_vix_ci95"][1]
        assert d["median_vix_ci95"][0] <= d["median_vix"] <= d["median_vix_ci95"][1]
        assert d["outlier_pct_ci95"][0] <= d["outlier_pct"] <= d["outlier_pct_ci95"][1]
        assert isinstance(d["ci_seed"], int) and d["ci_seed"] > 2026000000
        for key in ("segments_analyzed", "coverage_pct", "mean_vix", "median_vix", "outlier_pct", "mean_response_chars"):
            assert key in d


# ─── eigenching_report ──────────────────────────────────────────────────────

def test_eigenching_report_census_no_intervals(tmp_path, monkeypatch):
    import eigenching_report as er
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    for i in range(4):
        seg = _story(i)
        seg["beats"].append({"phase": "beat_18b_state_vector", "speaker": "Host",
                             "text": "EigenChing state: The Cornering, named archetype."})
        (seg_dir / f"20260910_0{i}0000_{i:012x}_segment.json").write_text(json.dumps(seg))
    (seg_dir / "20260910_050000_idle_x_segment.json").write_text(json.dumps(_idle(9)))
    monkeypatch.setattr(er, "SEGMENT_DIR", str(seg_dir))
    monkeypatch.setattr(er, "OUT_PATH", str(tmp_path / "eigenching_data.json"))
    rep = er.generate_report()
    assert rep["total_segments"] == 4 and rep["n"] == 4 and rep["census"] is True
    assert rep["total_files"] == 5 and rep["story_files"] == 4
    assert "census" in rep["ci_method"]
    top = rep["archetypes"][0]
    assert top["name"] == "The Cornering" and top["count"] == 4 and top["pct"] == 100.0
    assert "pct_ci" not in top
    assert json.loads((tmp_path / "eigenching_data.json").read_text())["n"] == 4


# ─── script_v3 ──────────────────────────────────────────────────────────────

def test_get_audit_context_counts_measured_records_only(tmp_path, monkeypatch):
    import script_v3
    log = tmp_path / "audit_log.jsonl"
    rows = []
    for i in range(12):
        a = _story(i)["attribution"]
        rows.append({"timestamp": f"2026-09-{5 + i // 3:02d}T0{i % 3}:00:00", "story_title": a["story_title"],
                     "model_vix": a["model_vix"], "void_words": a["void_words"]})
    for i in range(5):
        rows.append({"timestamp": "2026-09-10T11:13:00", "story_title": "empty", "model_vix": {}, "void_words": ["x"]})
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(script_v3, "AUDIT_LOG", log)
    ctx = script_v3._get_audit_context()
    assert ctx["n_stories"] == 12 and ctx["n_records"] == 17
    assert ctx["window"] == {"first_ts": "2026-09-05T00:00:00", "last_ts": "2026-09-08T02:00:00"}
    assert set(ctx["model_avg_vix"]) == set(MODELS)
    assert ctx["outlier"]["model"] in MODELS and 0 <= ctx["outlier"]["share"] <= 1
    assert ctx["model_vix_ci"]["Claude"]["n"] == 12


OPTIONAL_MODULES = ["broadcast_state", "segment_rag", "void_verifier", "wiki_edit_sensor", "source_salience",
                    "cross_story_freq", "ablation_engine", "preregistration"]


@pytest.fixture
def quiet_script(monkeypatch):
    import script_v3
    for name in OPTIONAL_MODULES:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    captured = {}
    monkeypatch.setattr(script_v3, "_call_host", lambda s, u, *a, **k: captured.setdefault("host", []).append((s, u)) or "")
    monkeypatch.setattr(script_v3, "_call_host_think", lambda *a, **k: "")
    monkeypatch.setattr(script_v3, "_call_host_confident", lambda *a, **k: "")
    monkeypatch.setattr(script_v3, "_call_host_with_swerves", lambda *a, **k: ("", []))
    monkeypatch.setattr(script_v3, "_rag_context", lambda *a, **k: "")
    return captured


def _fake_soul_updater(monkeypatch, recent, earlier):
    fake = types.ModuleType("soul_updater")
    fake.load_recent_segments = lambda hours=24: list(recent) + list(earlier)
    monkeypatch.setitem(sys.modules, "soul_updater", fake)


def _fake_state_modules(monkeypatch, n_records, captured):
    sv = types.ModuleType("state_vector")
    sv.compute_state_vector = lambda signals, names: ((1, -1, -1, -1, -1, 1), names)
    sv.extract_signals = lambda seg: {}
    sv.load_all_signals = lambda: [{"_title": f"t{i}", "_timestamp": ""} for i in range(n_records)]
    sv.find_state_matches = lambda records, vec, names: [{"title": r["_title"]} for r in records[:7]]
    ec = types.ModuleType("eigenching")

    def _fmt(sig, matches=None, total_seen=0, **k):
        captured["total_seen"] = total_seen
        return f"EigenChing state: The Cornering, named archetype. Observed {len(matches)} times in {total_seen} stories."
    ec.format_broadcast = _fmt
    ec.classify = lambda sig: {"name": "The Cornering", "archetype_name": "The Cornering", "tier": "archetype", "distance": 0}
    monkeypatch.setitem(sys.modules, "state_vector", sv)
    monkeypatch.setitem(sys.modules, "eigenching", ec)


def _run_script(monkeypatch, audit_ctx=None):
    import script_v3
    random.seed(0)
    seg = _story(99)
    return script_v3.generate_script_v3({"beats": [], "attribution": seg["attribution"]}, audit_ctx or {})


def test_beat_17b_speaks_disjoint_windows_with_interval(quiet_script, monkeypatch):
    now = datetime.utcnow()
    recent = [_story(i, ts=(now - timedelta(hours=1 + i)).strftime("%Y%m%d_%H%M%S"), density=0.93 + 0.002 * (i % 3))
              for i in range(8)]
    earlier = [_story(20 + i, ts=(now - timedelta(hours=25 + i)).strftime("%Y%m%d_%H%M%S"), density=0.86 + 0.002 * (i % 3))
               for i in range(6)]
    _fake_soul_updater(monkeypatch, recent, earlier)
    _fake_state_modules(monkeypatch, 10, {})
    script = _run_script(monkeypatch)
    beats = {b["phase"]: b["text"] for b in script}
    t = beats["beat_17b_trajectory"]
    assert t.startswith("Compression trajectory. Density moved from 0.86")
    # spoken form: digits, "percent" and signs as words (no "%", "+", "n=" for the TTS engine)
    assert re.search(r"Density moved from 0\.\d{3} to 0\.\d{3} over the last 24 hours \(6 stories then 8 stories; "
                     r"95 percent interval on the change plus 0\.\d{3} to plus 0\.\d{3}\)\. Density is increasing\.", t)
    assert "6 stories then 8 stories" in t and "interval" in t
    assert "%" not in t and "+" not in t and "n=" not in t
    assert "direction not resolved at this sample size" in t or "These are not single-story findings" in t
    assert not script_v3_failure(script)


def test_beat_17b_unresolved_direction(quiet_script, monkeypatch):
    now = datetime.utcnow()
    recent = [_story(i, ts=(now - timedelta(hours=1 + i)).strftime("%Y%m%d_%H%M%S"), density=0.90 + 0.01 * (i % 3))
              for i in range(5)]
    earlier = [_story(20 + i, ts=(now - timedelta(hours=25 + i)).strftime("%Y%m%d_%H%M%S"), density=0.91 - 0.01 * (i % 3))
               for i in range(5)]
    _fake_soul_updater(monkeypatch, recent, earlier)
    _fake_state_modules(monkeypatch, 10, {})
    script = _run_script(monkeypatch)
    t = {b["phase"]: b["text"] for b in script}["beat_17b_trajectory"]
    assert re.search(r"Density moved from 0\.\d{3} to 0\.\d{3} over the last 24 hours \(5 stories then 5 stories; "
                     r"95 percent interval on the change minus 0\.\d{3} to plus 0\.\d{3}\)\. Direction not resolved at this sample size\.", t)
    assert "%" not in t and "+" not in t and "n=" not in t
    assert "Density is increasing" not in t and "Density is decreasing" not in t


def test_beat_17b_skipped_without_a_previous_window(quiet_script, monkeypatch):
    now = datetime.utcnow()
    recent = [_story(i, ts=(now - timedelta(hours=1 + i)).strftime("%Y%m%d_%H%M%S")) for i in range(5)]
    _fake_soul_updater(monkeypatch, recent, [])
    _fake_state_modules(monkeypatch, 10, {})
    phases = [b["phase"] for b in _run_script(monkeypatch)]
    assert "beat_17b_trajectory" not in phases


def test_beat_18b_uses_the_window_denominator(quiet_script, monkeypatch):
    _fake_soul_updater(monkeypatch, [], [])
    cap = {}
    _fake_state_modules(monkeypatch, 2100, cap)
    script = _run_script(monkeypatch)
    text = {b["phase"]: b["text"] for b in script}["beat_18b_state_vector"]
    assert cap["total_seen"] == 2000
    assert "in 2000 stories" in text
    cap2 = {}
    _fake_state_modules(monkeypatch, 150, cap2)
    _run_script(monkeypatch)
    assert cap2["total_seen"] == 150


def test_beat_17_prompt_carries_window_and_runner_up(quiet_script, monkeypatch):
    _fake_soul_updater(monkeypatch, [], [])
    _fake_state_modules(monkeypatch, 10, {})
    ctx = {"model_avg_vix": {"Claude": 22.0, "DeepSeek": 21.5, "Grok": 14.0},
           "void_freq": [("mediator", 4)], "n_stories": 12, "n_records": 17,
           "window": {"first_ts": "2026-09-05T08:56:00", "last_ts": "2026-09-10T11:13:00"},
           "outlier": {"model": "Claude", "runner_up": "DeepSeek", "share": 0.57}}
    _run_script(monkeypatch, ctx)
    prompts = [u for s, u in quiet_script["host"] if "Stories analyzed" in u]
    assert prompts, "beat_17 prompt not issued"
    u = prompts[0]
    assert "Model with highest average friction: Claude (runner-up DeepSeek; 57% of resamples)" in u
    assert "Stories analyzed in this window: 12 (records from 2026-09-05 to 2026-09-10)" in u
    assert "this week: 12" not in u


def script_v3_failure(script):
    import script_v3
    return any(script_v3._FAILURE_RE.match(str(b.get("text", ""))) for b in script)
