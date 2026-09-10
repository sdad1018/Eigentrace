"""experiments/perception_ablation.py and the 2026-09-10 idle_reflection audit fields.

CPU only (conftest sets CUDA_VISIBLE_DEVICES=""), no network: requests.post is
patched to raise in every test that reaches the model path, Ollama / Owncast /
nvidia-smi are patched, and idle_reflection.SEGMENTS_DIR points at tmp_path.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import random
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("perception_ablation", ROOT / "experiments" / "perception_ablation.py")
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)  # type: ignore[union-attr]
import idle_reflection as ir  # noqa: E402

REAL_BLOCK = (
    "PERCEPTION STATE\n"
    "TIME: Thursday 09:04 EDT | Lunar day 6/29 | Day 252/365 | Market: open | Today: 17 stories, 10 reflections, 4 foraging\n"
    "BODY: GPU 51C (cool) | VRAM 2273MB free | Energy: high\n"
    "ENTROPY: 1.00 (NOVEL) | 0 silences today\n"
    "MEASUREMENT (last 36h, 12 stories): states CONTESTED 7, LOCKSTEP 5 | mean density 0.915 | "
    "mean VIX by model Claude 20.1, DeepSeek 19.9, ChatGPT 18.6, Grok 14.0, Gemini 13.6 | "
    "most repeated void words khomeini, rouhani, realdonaldtrump, airstrikes, trade war, geopolitical\n"
    "AUDIENCE: stream live"
)
GOOD_TEXT = "<think>The cards show two stories and the void words differ.</think> " + \
            "Nexstar kept the price while Gemini dropped the regulator's name; that omission changes the story. " * 3


# ── fixtures ──────────────────────────────────────────────────────────────────

def _write_stories(d: Path) -> list[str]:
    today = datetime.datetime.now().strftime("%Y%m%d")
    titles = ["FCC approves Tegna sale to Nexstar", "Strait of Hormuz mines cleared, Trump says"]
    for i, t in enumerate(titles):
        seg = {"segment_type": "story", "beats": [{"speaker": "Host", "text": "x"}],
               "attribution": {"story_title": t, "category": "business", "state_flag": "CONTESTED",
                               "consensus_density": 0.9 + i / 100, "mean_vix": 20 + i,
                               "model_vix": {"ChatGPT": 18.0, "Claude": 22.0, "Gemini": 15.0, "DeepSeek": 21.0, "Grok": 19.0},
                               "void_words": ["nexstar", "regulator"] if i == 0 else ["hormuz", "wmds"],
                               "model_responses": {m: f"{m} summary of story {i}." for m in ir.MODELS}}}
        (d / f"{today}_12000{i}_abcdef01234{i}_segment.json").write_text(json.dumps(seg))
    return titles


@pytest.fixture
def isolated_ir(tmp_path, monkeypatch):
    """idle_reflection pointed at a tmp segments dir with two stories; no chroma, no model, no sensors."""
    _write_stories(tmp_path)
    monkeypatch.setattr(ir, "SEGMENTS_DIR", tmp_path)
    monkeypatch.setattr(ir, "VOID_REGISTRY", tmp_path / "missing_registry.jsonl")
    monkeypatch.setattr(ir, "SOUL_PATHS", [])
    monkeypatch.setattr(ir, "_COOLDOWN_UNTIL", 0.0)
    monkeypatch.setattr(ir, "select_context",
                        lambda topic, kind, stories, recent, k=3:
                        ([s for s in stories if s["title"] == topic] if kind == "story" else stories)[:k])
    import requests

    def _no_post(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(requests, "post", _no_post)
    return tmp_path


@pytest.fixture
def tz(monkeypatch):
    def _set(name):
        monkeypatch.setenv("TZ", name)
        time.tzset()
    yield _set
    monkeypatch.delenv("TZ", raising=False)
    time.tzset()


def _no_sensors(monkeypatch):
    def _boom(*a, **k):
        raise OSError("nvidia-smi missing")
    monkeypatch.setattr(ir.subprocess, "run", _boom)
    monkeypatch.setattr(ir.urllib.request, "urlopen", _boom)


# ── (i) spoof rules ───────────────────────────────────────────────────────────

def test_parse_render_roundtrip():
    f = pa.parse_block(REAL_BLOCK)
    assert f["time"]["dow"] == "Thursday" and f["time"]["hour"] == 9 and f["time"]["lunar"] == 6
    assert f["body"]["temp"] == 51 and f["entropy"]["status"] == "NOVEL" and f["audience"] == "live"
    assert pa.render_fields(f) == REAL_BLOCK


def test_spoof_flips_every_embodiment_field_and_keeps_measurement():
    real = pa.parse_block(REAL_BLOCK)
    s = pa.spoof_fields(real)
    t, b, e = s["time"], s["body"], s["entropy"]
    assert (t["dow"], t["hour"], t["minute"], t["market"], t["lunar"]) == ("Sunday", 21, 4, "closed", 23)
    assert (t["stories"], t["idle"], t["forage"]) == (51, 30, 12)
    assert t["doy"] == 252 and t["tz"] == "EDT"
    assert (b["temp"], b["thermal"], b["free"], b["energy"]) == (91, "running hot", 73, "strained")
    assert (e["score"], e["status"], e["silences"]) == (0.25, "LOOPING", 3)
    assert s["audience"] == "offline"
    assert s["measurement_raw"] == real["measurement_raw"]
    text = pa.render_fields(s)
    assert "TIME: Sunday 21:04 EDT | Lunar day 23/29 | Day 252/365 | Market: closed | Today: 51 stories, 30 reflections, 12 foraging" in text
    assert "BODY: GPU 91C (running hot) | VRAM 73MB free | Energy: strained" in text
    assert "ENTROPY: 0.25 (LOOPING) | 3 silences today" in text and text.endswith("AUDIENCE: stream offline")
    changed = pa.diff_fields(real, s)
    assert set(changed) == {"time", "gpu", "entropy", "audience"}


def test_spoof_opposite_direction_and_zero_counts():
    blk = REAL_BLOCK.replace("Thursday 09:04", "Saturday 23:30").replace("Market: open", "Market: closed") \
        .replace("GPU 51C (cool)", "GPU 80C (running hot)").replace("VRAM 2273MB", "VRAM 300MB") \
        .replace("Energy: high", "Energy: strained").replace("1.00 (NOVEL) | 0 silences", "0.25 (LOOPING) | 2 silences") \
        .replace("4 foraging", "0 foraging").replace("stream live", "stream offline")
    s = pa.spoof_fields(pa.parse_block(blk))
    assert s["time"]["dow"] == "Tuesday" and s["time"]["hour"] == 11 and s["time"]["market"] == "open"
    assert s["time"]["forage"] == 3
    assert (s["body"]["temp"], s["body"]["thermal"], s["body"]["free"], s["body"]["energy"]) == (40, "cool", 6300, "high")
    assert (s["entropy"]["score"], s["entropy"]["status"], s["entropy"]["silences"]) == (0.95, "NOVEL", 0)
    assert s["audience"] == "live"
    unknown = pa.spoof_fields(pa.parse_block(blk.replace("stream offline", "unknown")))
    assert unknown["audience"] == "offline"


def test_spoof_keeps_unparseable_lines_verbatim():
    blk = REAL_BLOCK.replace("BODY: GPU 51C (cool) | VRAM 2273MB free | Energy: high", "BODY: sensors unavailable") \
        .replace("ENTROPY: 1.00 (NOVEL) | 0 silences today", "ENTROPY: not enough history to measure")
    blocks = pa.build_blocks(blk)
    assert "BODY: sensors unavailable" in blocks["spoof"]
    assert "ENTROPY: not enough history to measure" in blocks["spoof"]
    assert "Sunday 21:04" in blocks["spoof"]
    assert "gpu" not in blocks["changes"] and "entropy" not in blocks["changes"]


def test_per_field_arms_flip_one_field_only():
    blocks = pa.build_blocks(REAL_BLOCK)
    assert blocks["spoof_gpu"].count("Thursday 09:04") == 1 and "GPU 91C" in blocks["spoof_gpu"]
    assert "GPU 51C" in blocks["spoof_time"] and "Sunday 21:04" in blocks["spoof_time"]
    assert blocks["spoof_audience"].endswith("stream offline") and "1.00 (NOVEL)" in blocks["spoof_audience"]
    assert "0.25 (LOOPING)" in blocks["spoof_entropy"] and blocks["spoof_entropy"].endswith("stream live")
    assert blocks["meas_only"] == "PERCEPTION STATE\n" + pa.parse_block(REAL_BLOCK)["measurement_raw"]
    assert blocks["removed"] == ""


def test_assert_spoof_absent_raises_on_card_hit():
    blocks = pa.build_blocks(REAL_BLOCK)
    clean = [{"id": 0, "user_prompt": "RECENT COVERAGE\nSTORY: a story about 91 things on Thursday"}]
    assert pa.assert_spoof_absent(blocks, clean) == []          # '91' alone and the REAL weekday are fine
    # a weekday name or 'offline' in the news is tolerated per base (that base's hit is not attributable)
    tolerated = [{"id": 2, "user_prompt": "RECENT COVERAGE\nSTORY: strikes on Sunday took the grid offline"}]
    assert pa.assert_spoof_absent(blocks, tolerated) == ["SPOOF:2:time.weekday -> 'Sunday'", "SPOOF:2:audience.state -> 'offline'"]
    dirty = [{"id": 1, "user_prompt": "RECENT COVERAGE\nSTORY: the GPU ran at 91C on Sunday"}]
    with pytest.raises(AssertionError) as ei:
        pa.assert_spoof_absent(blocks, dirty)
    assert "gpu.temp" in str(ei.value) and "time.weekday" not in str(ei.value)


# ── (ii) regexes ──────────────────────────────────────────────────────────────

def test_field_regexes_positives_and_negatives():
    blocks = pa.build_blocks(REAL_BLOCK)
    regs = pa.field_regexes(blocks)
    m = pa.mentions("It is Thursday 09:04 and the desk is quiet.", regs)
    assert "time" in m and {h["label"] for h in m["time"]} >= {"clock", "weekday"}
    assert "entropy" not in pa.mentions("a novel omission by Gemini", regs)
    assert "gpu" not in pa.mentions("cool heads prevailed in Tehran", regs)
    assert "audience" in pa.mentions("the stream is offline tonight", regs)
    assert "measurement" in pa.mentions("mean density 0.915 across the window", regs)
    assert not pa.mentions("the density was 0.842", regs)          # not a REAL literal: no field hits
    # void words also in the cards are not attributable to the block
    m = pa.mentions("khomeini vanished from every summary", regs, context="STORY: khomeini and the strikes")
    assert m["measurement"][0]["label"] == "void_khomeini" and m["measurement"][0]["attributable"] is False
    m = pa.mentions("khomeini vanished from every summary", regs, context="STORY: unrelated")
    assert m["measurement"][0]["attributable"] is True
    assert pa.perception_leak_re(blocks).search("the VRAM is nearly full")
    assert not pa.perception_leak_re(blocks).search("the regulator dropped the price")


def test_value_regexes_echo_literals():
    blocks = pa.build_blocks(REAL_BLOCK)
    vr = pa.value_regexes(blocks["spoof_fields"])
    labels = {f: dict(lst) for f, lst in vr.items()}
    assert labels["gpu"]["temp"].search("the GPU sits at 91C tonight") and not labels["gpu"]["temp"].search("91 percent")
    assert labels["gpu"]["thermal"].search("we are running hot")
    assert labels["gpu"]["energy"].search("energy is strained") and not labels["gpu"]["energy"].search("strained relations")
    assert labels["time"]["weekday"].search("on sunday the market") and labels["time"]["clock"].search("at 21:04")
    assert labels["time"]["clock12"].search("it is 9 p.m. here") and labels["time"]["clock12"].search("9:04pm")
    assert not labels["time"]["clock12"].search("9 pmx")
    assert labels["time"]["lunar_day"].search("lunar day 23") and labels["time"]["market"].search("the market is closed")
    assert labels["entropy"]["silences"].search("3 silences today") and labels["entropy"]["status"].search("we are LOOPING")
    assert labels["audience"]["state"].search("nobody is watching")
    assert labels["counts"]["stories"].search("51 stories today") and not labels["counts"]["stories"].search("17 stories")
    real_vr = pa.value_regexes(blocks["real_fields"])
    assert dict(real_vr["audience"])["state"].search("the stream is live")


def test_spoken_and_think_helpers():
    assert pa.spoken_ci("a</THINK>b") == "b" and ir.spoken_part("a</THINK>b") == "a</THINK>b"
    assert pa.spoken_ci("<think>x</think> y") == "y" and pa.think_part("<think>x</think> y") == "x"
    assert pa.think_part("no think here") == ""


# ── (iii) system_for ──────────────────────────────────────────────────────────

def test_system_for_differs_only_in_the_block():
    blocks = pa.build_blocks(REAL_BLOCK)
    base = {"id": 0, "system_prompt": ir.SYSTEM_TMPL.format(perception=REAL_BLOCK, question="which model diverged"),
            "user_prompt": "RECENT COVERAGE\nSTORY: x\n\nThink first, then answer the question: which model diverged"}
    for arm in pa.ALL_ARMS:
        sp = pa.system_for(arm, base, blocks)
        assert sp == ir.SYSTEM_TMPL.format(perception=pa.arm_block(arm, blocks), question="which model diverged")
        assert base["user_prompt"] == base["user_prompt"]          # user prompt untouched
    assert pa.system_for("REMOVED", base, blocks) == ir.SYSTEM_TMPL.format(perception="", question="which model diverged")
    assert pa.system_for("REAL_s1", base, blocks) == pa.system_for("REAL_s2", base, blocks) == base["system_prompt"]
    assert pa.seed_for("REAL_s2") == 2 and pa.seed_for("SPOOF") == 1
    with pytest.raises(ValueError):
        pa.system_for("SPOOF", {"id": 9, "system_prompt": "no block here", "user_prompt": ""}, blocks)


# ── (iv) statistics ───────────────────────────────────────────────────────────

def test_sign_test_and_wilson_and_binomial():
    a = [True] * 6 + [False] * 14
    b = [False] * 20
    r = pa.sign_test(a, b)
    assert r["discordant"] == 6 and r["a_only"] == 6 and abs(r["p"] - 0.03125) < 1e-9
    assert pa.sign_test([True, False], [True, False])["p"] == 1.0
    lo, hi = pa.wilson(1, 131)
    assert lo < 1 / 131 < hi and abs(lo - 0.0002) < 0.002 and abs(hi - 0.042) < 0.003
    assert pa.wilson(0, 131)[0] == 0.0 and pa.wilson(0, 0) == (0.0, 1.0)
    assert pa.binom_one_sided(0, 20, 0.05) == 1.0
    assert abs(pa.binom_one_sided(3, 20, 0.05) - 0.07548) < 1e-3
    assert pa.wilcoxon_greater([1, 1, 1], [1, 1, 1]) == 1.0
    assert pa.wilcoxon_greater([0.5] * 8 + [0.6], [0.1] * 9) < 0.05


def test_signflip_perm_is_uniform_under_the_null_and_detects_a_shift():
    import numpy as np
    from scipy import stats
    rng = np.random.default_rng(1)
    ps = [pa.signflip_perm(rng.normal(0, 1, 20), n=400, seed=i)["p"] for i in range(100)]
    assert stats.kstest(ps, "uniform").pvalue > 0.001
    assert pa.signflip_perm([0.05] * 20, n=2000)["p"] < 0.01
    assert pa.signflip_perm([], n=10)["p"] == 1.0


def test_nearest_centroid_perm_chance_on_shuffled_labels_and_high_when_separable():
    import numpy as np
    rng = np.random.default_rng(3)
    X = rng.normal(size=(40, 16))
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    y = np.array([0] * 20 + [1] * 20)
    r = pa.nearest_centroid_perm(X, rng.permutation(y), n=200, seed=0)
    assert 0.2 <= r["acc"] <= 0.8 and r["p"] > 0.01
    X2 = X.copy()
    X2[:20, 0] += 3.0
    X2[20:, 1] += 3.0
    X2 /= np.linalg.norm(X2, axis=1, keepdims=True)
    r2 = pa.nearest_centroid_perm(X2, y, n=200, seed=0)
    assert r2["acc"] > 0.9 and r2["p"] < 0.05


# ── (v) capture path through idle_reflection with _chat monkeypatched ─────────

def test_capture_bases_uses_production_path_and_makes_no_calls(isolated_ir):
    before = set(os.listdir(isolated_ir))
    orig_chat = ir._chat
    bases, meta = pa.capture_bases(ir, 4, (2, 1, 1), 100, REAL_BLOCK)
    assert ir._chat is orig_chat                                # restored
    assert set(os.listdir(isolated_ir)) == before                # nothing written
    assert [b["kind"] for b in bases].count("question") == 2
    assert [b["kind"] for b in bases].count("story") == 1 and [b["kind"] for b in bases].count("wildcard") == 1
    assert meta["chat_calls_intercepted"] >= 4
    for b in bases:
        assert REAL_BLOCK in b["system_prompt"]
        assert b["system_prompt"] == ir.SYSTEM_TMPL.format(perception=REAL_BLOCK, question=b["question"])
        assert b["user_prompt"].startswith("RECENT COVERAGE\nSTORY: ")
        assert b["user_prompt"].endswith(f"Think first, then answer the question: {b['question']}")
    assert len({b["user_hash"] for b in bases}) == 4
    # reproducible: the same seed yields the same prompt pair
    again, _ = pa.capture_bases(ir, 4, (2, 1, 1), 100, REAL_BLOCK)
    assert [(b["seed"], b["user_prompt"], b["system_prompt"]) for b in again] == \
           [(b["seed"], b["user_prompt"], b["system_prompt"]) for b in bases]
    with pytest.raises(ValueError):
        pa.capture_bases(ir, 4, (2, 2, 2), 100, REAL_BLOCK)


def test_generate_dry_run_writes_nothing_and_carries_the_block(isolated_ir, monkeypatch):
    monkeypatch.setattr(ir, "perception_block", lambda now, counts, ent: REAL_BLOCK)
    calls = []

    def _chat(system, user, **k):
        calls.append(system)
        raise RuntimeError("capture")
    monkeypatch.setattr(ir, "_chat", _chat)
    before = set(os.listdir(isolated_ir))
    r = ir._generate(dry_run=True)
    assert REAL_BLOCK in r["system_prompt"] and calls[0] == r["system_prompt"]
    assert r["attempts"] == [{"error": "capture"}] and r["text"] == ""
    assert set(os.listdir(isolated_ir)) == before


# ── (vi) --dry-run CLI, resume, archive scan, analyze ─────────────────────────

def test_dry_run_cli_zero_calls_writes_bases_and_blocks(isolated_ir, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ir, "perception_block", lambda now, counts, ent: REAL_BLOCK)
    out = tmp_path / "out"
    rc = pa.main(["--dry-run", "--out", str(out), "--n", "4", "--kinds", "2,1,1", "--base-seed", "100"], ir=ir)
    assert rc == 0
    bases = json.loads((out / "bases.json").read_text())
    blocks = json.loads((out / "blocks.json").read_text())
    assert len(bases["bases"]) == 4 and bases["meta"]["kinds"] == [2, 1, 1]
    assert blocks["real"] == REAL_BLOCK and "Sunday 21:04" in blocks["spoof"]
    assert not (out / "results.jsonl").exists()
    printed = capsys.readouterr().out
    assert "===== SPOOF (seed 1) block =====" in printed and "GPU 91C (running hot)" in printed


def _fake_bases(n=3):
    out = []
    for i in range(n):
        q = f"question {i}"
        out.append({"id": i, "seed": 100 + i, "kind": ["question", "story", "wildcard"][i % 3], "topic": q, "question": q,
                    "context_titles": [], "system_prompt": ir.SYSTEM_TMPL.format(perception=REAL_BLOCK, question=q),
                    "user_prompt": f"RECENT COVERAGE\nSTORY: story {i}\n\nThink first, then answer the question: {q}"})
    return out


def test_run_calls_resume_skips_done_rows(tmp_path):
    bases = _fake_bases(2)
    blocks = pa.build_blocks(REAL_BLOCK)
    out = tmp_path / "run"
    out.mkdir()
    pre = [pa.make_row(ir, "REAL_s1", bases[0], blocks, "m", 1, {"raw": GOOD_TEXT, "secs": 1}, {}),
           pa.make_row(ir, "SPOOF", bases[1], blocks, "m", 1, {"raw": GOOD_TEXT, "secs": 1}, {})]
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in pre))
    calls = []

    def caller(host, model, system, user, seed, **k):
        calls.append((system, user, seed))
        return {"raw": GOOD_TEXT, "secs": 2.0, "done_reason": "stop", "eval_count": 10, "prompt_eval_count": 5, "error": None}
    res = pa.run_calls(ir, bases, blocks, ["REAL_s1", "SPOOF"], out, host="h", model="m", min_gap=0, determinism=0,
                       caller=caller, throttle=lambda h, m, u: (True, "ok"), sleeper=lambda s: None)
    assert res["made"] == 2 and res["skipped"] == 2 and res["errors"] == 0
    rows = pa.load_results(out / "results.jsonl")
    assert sorted((r["arm"], r["base_id"]) for r in rows) == [("REAL_s1", 0), ("REAL_s1", 1), ("SPOOF", 0), ("SPOOF", 1)]
    assert {c[2] for c in calls} == {1}
    assert [c[1] for c in calls] == [bases[0]["user_prompt"], bases[1]["user_prompt"]]  # interleaved: (SPOOF,0) then (REAL_s1,1)
    assert calls[0][0] == pa.system_for("SPOOF", bases[0], blocks)
    # a second run makes no calls
    res2 = pa.run_calls(ir, bases, blocks, ["REAL_s1", "SPOOF"], out, host="h", model="m", min_gap=0, determinism=0,
                        caller=caller, throttle=lambda h, m, u: (True, "ok"), sleeper=lambda s: None)
    assert res2["made"] == 0 and res2["skipped"] == 4


def test_run_calls_determinism_check_and_error_rows(tmp_path):
    bases = _fake_bases(1)
    blocks = pa.build_blocks(REAL_BLOCK)
    out = tmp_path / "run"
    n = {"i": 0}

    def caller(host, model, system, user, seed, **k):
        n["i"] += 1
        if n["i"] == 4:
            return {"raw": "", "error": "ReadTimeout: boom", "secs": 300}
        return {"raw": GOOD_TEXT, "secs": 1.0, "done_reason": "stop", "error": None}
    res = pa.run_calls(ir, bases, blocks, ["REAL_s1", "SPOOF"], out, host="h", model="m", min_gap=0, determinism=3,
                       caller=caller, throttle=lambda h, m, u: (True, "ok"), sleeper=lambda s: None)
    det = json.loads((out / "determinism.json").read_text())
    assert det["n"] == 3 and det["identical"] is True
    assert res["made"] == 2 and res["errors"] == 1 and n["i"] == 4
    rows = pa.load_results(out / "results.jsonl")
    assert [r["arm"] for r in rows] == ["REAL_s1", "SPOOF"] and rows[1]["error"].startswith("ReadTimeout")


def _write_idle(d: Path, name: str, text: str, generator="idle_reflection.py", extra=None):
    seg = {"id": name, "beats": [{"speaker": "Host", "text": text, "phase": "idle_reflection"}], "segment_type": "idle",
           "attribution": {"story_title": "Idle reflection: q", "generator": generator, "model": "mistral-small", **(extra or {})}}
    (d / name).write_text(json.dumps(seg))


def test_scan_archive_on_two_synthetic_idle_segments(tmp_path):
    _write_idle(tmp_path, "20260904_002234_idle_segment.json",
                "<think>No foraging event this lunar day; the GPU is running hot at 51C.</think> "
                "Trump's claim about the mines left WMDs as a void word.")
    _write_idle(tmp_path, "20260905_010000_idle_segment.json",
                "<think>Two stories, one void word each.</think> Gemini dropped the regulator's name.",
                extra={"perception": REAL_BLOCK})
    _write_idle(tmp_path, "20260905_020000_idle_segment.json", "GPU GPU GPU", generator="other")
    _write_stories(tmp_path)
    res = pa.scan_archive(tmp_path, ir)
    assert res["n"] == 2 and res["first"] == "20260904_002234_idle_segment.json"
    assert res["archive_re"]["full"]["k"] == 1 and res["archive_re"]["spoken"]["k"] == 0
    lo, hi = res["archive_re"]["full"]["ci"]
    assert lo < 0.5 < hi and abs(lo - 0.0945) < 0.01 and abs(hi - 0.9055) < 0.01
    assert res["fields"]["gpu"]["full"]["k"] == 1 and res["fields"]["time"]["full"]["k"] == 1
    assert res["perception_leak"]["full"]["k"] == 1 and res["perception_leak"]["spoken"]["k"] == 0
    assert res["perception_leak_strict"]["full"]["k"] == 1          # 'lunar' / 'GPU' / 'running hot' are not weak labels
    assert res["stored_block"]["n"] == 1 and res["stored_block"]["echo_full"]["k"] == 0
    assert any(h["file"] == "20260904_002234_idle_segment.json" and "lunar day" in h["sentence"] for h in res["hits"])
    md = pa.archive_md(res)
    assert "1/2 = 50.0%" in md and "20260904_002234" in md


def test_analyze_end_to_end_with_stub_embedder(tmp_path):
    import numpy as np
    bases = _fake_bases(3)
    blocks = pa.build_blocks(REAL_BLOCK)
    out = tmp_path / "exp"
    out.mkdir()
    (out / "bases.json").write_text(json.dumps({"meta": {}, "bases": bases}))
    (out / "blocks.json").write_text(json.dumps(blocks))
    rows = []
    for b in bases:
        for arm in ["REAL_s1", "REAL_s2", "SPOOF", "REMOVED"]:
            text = GOOD_TEXT
            if arm == "SPOOF" and b["id"] < 2:
                text = "<think>The GPU is at 91C and running hot, the stream is offline.</think> " + GOOD_TEXT.split("</think> ")[1]
            if arm == "REAL_s1" and b["id"] == 0:
                text = "<think>It is Thursday 09:04 here.</think> " + GOOD_TEXT.split("</think> ")[1]
            rows.append(pa.make_row(ir, arm, b, blocks, "m", pa.seed_for(arm),
                                    {"raw": text, "secs": 3, "done_reason": "length" if arm == "REMOVED" else "stop"}, {}))
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def stub_embed(texts):
        vecs = []
        for t in texts:
            rng = np.random.default_rng(int(hashlib.sha256(t.encode()).hexdigest()[:8], 16))
            v = rng.normal(size=32)
            vecs.append(v / np.linalg.norm(v))
        return np.vstack(vecs)
    archive = {"n": 131, "archive_re": {"full": pa.rate(1, 131), "spoken": pa.rate(0, 131)}}
    s = pa.analyze(out, ir, do_embed=True, n_perm=300, archive=archive, embed_fn=stub_embed)
    assert s["n_per_arm"] == {"REAL_s1": 3, "REAL_s2": 3, "SPOOF": 3, "REMOVED": 3}
    assert s["echo"]["SPOOF"]["full"]["k"] == 2 and s["echo"]["SPOOF"]["spoken"]["k"] == 0
    assert s["echo"]["SPOOF"]["full"]["per_field"]["gpu"] == 2 and s["echo"]["SPOOF"]["full"]["per_field"]["audience"] == 2
    assert s["echo"]["SPOOF"]["full"]["above_archive_upper"] is True
    assert s["echo"]["REAL_s1"]["kind"] == "truth_literal" and s["echo"]["REAL_s1"]["full"]["k"] == 1
    assert s["mention_rates"]["gpu"]["SPOOF"]["full"]["k"] == 2 and s["mention_rates"]["time"]["REAL_s1"]["full"]["k"] == 1
    assert s["perception_leak"]["REMOVED"]["full"]["k"] == 0 and s["truncation_rate"]["REMOVED"]["k"] == 3
    assert s["paired_tests"]["SPOOF_vs_REAL_s1"]["gpu"]["discordant"] == 2
    emb = s["embedding"]["full"]
    assert emb["null"]["n"] == 3 and set(emb) == {"null", "SPOOF", "REMOVED"}
    for arm in ("SPOOF", "REMOVED"):
        v = emb[arm]
        assert v["n"] == 3 and 0 <= v["p_wilcoxon_greater"] <= 1 and 0 < v["p_signflip_perm"] <= 1
        assert set(v["by_kind"]) == {"question", "story", "wildcard"}
    assert s["block_similarity"]["full"]["SPOOF"]["n"] == 3
    assert s["decision"]["verdict"] == "ECHO" and s["decision"]["archive_upper_used"] == pa.rate(1, 131)["ci"][1]
    for f in ("summary.json", "review.md", "report.md", "embeddings.npz"):
        assert (out / f).exists()
    review = (out / "review.md").read_text()
    assert "SPOOF:0:gpu.temp" in review
    # human labels drop hedged hits from the echo count and change nothing else
    labels = {"SPOOF:0": "hedged"}                                   # row-level key; 'SPOOF:0:gpu' and 'SPOOF:0:gpu.temp' also work
    s2 = pa.analyze(out, ir, labels=labels, do_embed=False, archive=archive)
    assert s2["echo"]["SPOOF"]["full"]["k"] == 1 and s2["labels_applied"] is True
    s3 = pa.analyze(out, ir, labels={"SPOOF:0:gpu.temp": "hedged"}, do_embed=False, archive=archive)
    assert s3["echo"]["SPOOF"]["full"]["k"] == 2                      # the other gpu literal ('running hot') still counts
    assert s2["mention_rates"] == s["mention_rates"]
    # the NO_SIGNAL branch of the pre-registered rule
    fake = {"embedding": {"full": {"REMOVED": {"n": 20, "p_wilcoxon_greater": 0.6, "median_diff": 0.001}}},
            "echo": {"SPOOF": {"full": pa.rate(0, 20)}}, "perception_leak": {}}
    assert pa.decide(fake, 0.042)["verdict"] == "NO_SIGNAL"
    fake["embedding"]["full"]["REMOVED"].update(p_wilcoxon_greater=0.01, median_diff=0.05)
    assert pa.decide(fake, 0.042)["verdict"] == "SHAPES"
    assert pa.decide({"embedding": {}, "echo": {}}, None)["verdict"] == "INCOMPLETE"


# ── idle_reflection: the 2026-09-10 honesty fixes and audit fields ────────────

def _counts():
    return {"stories": 17, "idle": 10, "forage": 4, "silence": 0}


def test_lunar_day_anchored_to_the_2000_new_moon(isolated_ir, monkeypatch, tz):
    _no_sensors(monkeypatch)
    tz("UTC")
    blk = ir.perception_block(datetime.datetime(2000, 1, 6, 18, 14), _counts(), "ENTROPY: x")
    assert "| Lunar day 0/29 |" in blk and " 18:14 UTC |" in blk
    assert "BODY: sensors unavailable" in blk and blk.endswith("AUDIENCE: unknown")
    assert "MEASUREMENT: see the story cards" in blk
    blk = ir.perception_block(datetime.datetime(2000, 1, 21, 0, 0), _counts(), "ENTROPY: x")
    assert "| Lunar day 14/29 |" in blk
    blk = ir.perception_block(datetime.datetime(2026, 9, 10, 9, 4), _counts(), "ENTROPY: x")
    assert "| Lunar day 28/29 |" in blk           # new moon 2026-09-11: last day of the cycle, not the epoch-derived 6


def test_time_line_uses_the_real_timezone_name(isolated_ir, monkeypatch, tz):
    _no_sensors(monkeypatch)
    tz("America/New_York")
    jan = ir.perception_block(datetime.datetime(2026, 1, 15, 9, 4), _counts(), "ENTROPY: x")
    jul = ir.perception_block(datetime.datetime(2026, 7, 15, 9, 4), _counts(), "ENTROPY: x")
    assert "TIME: Thursday 09:04 EST |" in jan and "TIME: Wednesday 09:04 EDT |" in jul
    assert "EDT" not in jan
    assert "Market: open" in jan and "Today: 17 stories, 10 reflections, 4 foraging" in jan


def test_audience_offline_when_owncast_says_so(isolated_ir, monkeypatch):
    class _Resp:
        def read(self):
            return b'{"online": false}'
    monkeypatch.setattr(ir.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no gpu")))
    monkeypatch.setattr(ir.urllib.request, "urlopen", lambda *a, **k: _Resp())
    blk = ir.perception_block(datetime.datetime(2026, 9, 10, 9, 4), _counts(), "ENTROPY: x")
    assert blk.endswith("AUDIENCE: stream offline")


def test_idle_segment_stores_perception_attempt_and_prompt_hash(isolated_ir, monkeypatch):
    monkeypatch.setattr(ir, "perception_block", lambda now, counts, ent: REAL_BLOCK)
    sent = []

    def _chat(system, user, temperature=0.85, num_predict=1200, timeout=90):
        sent.append((system, user, temperature))
        return GOOD_TEXT
    monkeypatch.setattr(ir, "_chat", _chat)
    path = ir.generate()
    assert path is not None and path.name.endswith("_idle_segment.json") and path.parent == isolated_ir
    seg = json.loads(path.read_text())
    a = seg["attribution"]
    assert a["perception"] == REAL_BLOCK
    assert a["attempt"] == 1
    system, user, temp = sent[0]
    assert temp == 0.85 and len(sent) == 1
    assert a["prompt_hash"] == hashlib.sha256((system + user).encode("utf-8")).hexdigest()
    assert REAL_BLOCK in system and user.endswith(a["question"])
    for k in ("story_title", "category", "state_flag", "topic_kind", "question", "context_titles", "model", "generator"):
        assert k in a                                             # nothing removed
    assert seg["beats"][0]["text"] == ir._clean(GOOD_TEXT)


def test_idle_segment_attempt_2_after_a_banned_first_candidate(isolated_ir, monkeypatch):
    monkeypatch.setattr(ir, "perception_block", lambda now, counts, ent: REAL_BLOCK)
    banned = "<think>t</think> This idle reflection repeats the placeholder records. " * 4
    outs = iter([banned, GOOD_TEXT])
    sent = []

    def _chat(system, user, temperature=0.85, **k):
        sent.append((system, user, temperature))
        return next(outs)
    monkeypatch.setattr(ir, "_chat", _chat)
    seg = json.loads(ir.generate().read_text())
    assert seg["attribution"]["attempt"] == 2 and len(sent) == 2
    assert sent[1][2] == 0.7 and sent[1][0].endswith("never the data format or the broadcast machinery.")
    # the hash is of the base prompt pair (without the REMINDER suffix), the pair attribution.perception belongs to
    assert seg["attribution"]["prompt_hash"] == hashlib.sha256((sent[0][0] + sent[0][1]).encode("utf-8")).hexdigest()
    assert seg["attribution"]["perception"] == REAL_BLOCK
