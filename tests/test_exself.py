"""exself: ex-self judging helpers and the sites that use them.

CPU only, no API, no Ollama, no GPU.  Every network-facing callable is replaced
by a recorder; nothing here writes to the runtime tree or to the published
control_plainprompt_* / confront10_final_* artefacts (checked at the end).
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
from pathlib import Path

import pytest

import exself as X

ROOT = Path(__file__).resolve().parent.parent
PANEL = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]
PUBLISHED = [ROOT / n for n in ("control_plainprompt_results.json", "control_plainprompt_panel.json",
                                "confront10_final_results.json", "confront10_final_panel.json")]
_MTIMES = {p: p.stat().st_mtime_ns for p in PUBLISHED if p.exists()}

SCORES_OK = ("Summary 1: insight=4 faith=5 action=3 trust=4 keep=1\n"
             "Summary 2: insight=3 faith=4 action=2 trust=3 keep=0\n"
             "Summary 3: insight=5 faith=5 action=4 trust=5 keep=1\n")


class Recorder:
    """dict-like stand-in for confront10.API_PATIENTS: records who was called."""

    def __init__(self, names, reply):
        self.calls = []
        self.reply = reply
        self._fns = {n: self._make(n) for n in names}

    def _make(self, n):
        def fn(messages):
            self.calls.append((n, messages))
            return self.reply
        return fn

    def __getitem__(self, k):
        return self._fns[k]

    def __contains__(self, k):
        return k in self._fns

    def __iter__(self):
        return iter(self._fns)

    def keys(self):
        return self._fns.keys()


# ---------------------------------------------------------------------------
# 1-3  pure helpers
# ---------------------------------------------------------------------------

def test_judged_set_never_contains_judge():
    items = {m: f"text by {m}" for m in PANEL}
    for judge in PANEL + ["mistral-small"]:
        js = X.judged_set(items, judge)
        assert judge not in js
        assert len(js) == (4 if judge in PANEL else 5)
    # a caller that hands over a set still containing the judge's own text is refused
    with pytest.raises(X.ExSelfViolation):
        X.assert_exself(items, "Claude")
    # ... and so is a vendor sibling under a different name
    out = X.judged_set(items, "Claude")
    out["claude-sonnet-4-6"] = "sibling"
    with pytest.raises(X.ExSelfViolation):
        X.assert_exself(out, "Claude")
    X.assert_exself(X.judged_set(out, "Claude"), "Claude")      # re-filtering makes it clean
    X.assert_exself(items, "mistral-small")                      # a non-producer judge is always clean


def test_vendor_exclusion():
    items = {"ChatGPT": "a", "gpt-4o-mini": "b", "Claude": "c", "Gemini": "d"}
    js = X.judged_set(items, "ChatGPT")
    assert "ChatGPT" not in js and "gpt-4o-mini" not in js
    assert set(js) == {"Claude", "Gemini"}
    assert X.vendor_of("gpt-4o-mini") == "openai"
    assert X.vendor_of("claude-sonnet-4-20250514") == "anthropic"
    assert X.vendor_of("gemini-2.0-flash") == "google"
    assert X.vendor_of("deepseek-chat") == "deepseek"
    assert X.vendor_of("grok-3-mini-fast") == "xai"
    assert X.vendor_of("mistral-small") == "local"
    assert X.vendor_of("qwen2.5:14b") == "local"
    assert X.vendor_of("bge-large-en-v1.5:cosine") == "embedding"
    assert X.judges_for("Gemini", PANEL) == ["ChatGPT", "Claude", "DeepSeek", "Grok"]
    assert X.judges_for(None, PANEL) == PANEL
    # local judges are never excluded for a frontier author
    assert X.judges_for("Claude", ["mistral-small"]) == ["mistral-small"]


def test_score_matrix_exself_matches_bakeoff2():
    # bakeoff2 pattern: judge j scores writer j at 5, every other writer at 3
    scores = {j: {w: (5.0 if w == j else 3.0) for w in PANEL} for j in PANEL}
    author_of = {w: w for w in PANEL}
    r = X.score_matrix_exself(scores, author_of)
    assert all(v == 3.0 for v in r["exself"].values())
    assert all(v == 5.0 for v in r["self"].values())
    assert all(abs(v - 3.4) < 1e-9 for v in r["self_included"].values())
    assert r["self_pref"] == 2.0


def _synthetic_records():
    recs = []
    for story in ("s1", "s2"):
        for patient in PANEL:
            for gen in range(2):
                for judge in PANEL:
                    own = judge == patient
                    parsed = {"BASELINE": {"insight": 2 + own, "faith": 4, "action": 2, "trust": 3, "keep": 0},
                              "PLAIN_PLUS": {"insight": 3 + own, "faith": 4, "action": 3, "trust": 4, "keep": 1},
                              "A_PLUS_C": {"insight": 3 + own, "faith": 4, "action": 3, "trust": 4, "keep": 1}}
                    recs.extend(X.make_records(story, patient, gen, judge, parsed, ["A_PLUS_C", "BASELINE", "PLAIN_PLUS"]))
    return recs


def test_aggregate_exclude_self_drops_exactly_the_diagonal():
    recs = _synthetic_records()
    assert all(("judge" in r and "patient" in r and "arm" in r) for r in recs)
    diag = [r for r in recs if r["judge"] == r["patient"]]
    assert all(r["self_judged"] for r in diag)
    assert all(not r["self_judged"] for r in recs if r["judge"] != r["patient"])
    allj = X.aggregate(recs, exclude_self=False)
    exs = X.aggregate(recs, exclude_self=True)
    # ex-self n == all n minus the diagonal, per arm
    n_diag = sum(1 for r in diag if r["metric"] == "insight" and r["arm"] == "BASELINE")
    assert exs["BASELINE"]["n"] == allj["BASELINE"]["n"] - n_diag
    # self-inflated diagonal (+1) raises the all-judge mean by exactly 1/5
    assert abs(allj["BASELINE"]["insight"] - 2.2) < 1e-9
    assert abs(exs["BASELINE"]["insight"] - 2.0) < 1e-9
    # the flat derived view reproduces the same means as aggregate on the same records
    flat = X.flat_panel(recs)
    import numpy as np
    for arm in ("BASELINE", "PLAIN_PLUS", "A_PLUS_C"):
        assert abs(float(np.mean(flat[arm]["insight"])) - allj[arm]["insight"]) < 1e-12
        assert len(flat[arm]["insight"]) == allj[arm]["n"]
    spj = X.self_pref_by_judge(recs, "insight")
    assert all(abs(row["self_pref"] - 1.0) < 1e-9 for row in spj.values())
    assert allj["BASELINE"]["n_items"] == 2 * 5 * 2


def test_unparsed_arm_counts_as_attempted_not_parsed():
    parsed = {"BASELINE": {"insight": 3, "faith": 4, "action": 3, "trust": 4, "keep": 1}}
    recs = X.make_records("s", "Claude", 0, "Grok", parsed, ["A_PLUS_C", "BASELINE", "PLAIN_PLUS"])
    ph = [r for r in recs if not r["parsed"]]
    assert {r["arm"] for r in ph} == {"A_PLUS_C", "PLAIN_PLUS"} and all(r["score"] is None for r in ph)
    pr = X.parse_rate_by_judge(recs)["Grok"]
    assert pr == {"attempted": 3, "parsed_cells": 1, "rate": round(1 / 3, 3)}
    agg = X.aggregate(recs, exclude_self=False)
    assert set(agg) == {"BASELINE"} and agg["BASELINE"]["n"] == 1
    assert set(X.flat_panel(recs)) == {"BASELINE"}


def test_stamp_block_fields():
    rec = X.stamp({}, "bge-large-en-v1.5:cosine", PANEL, True, "embedding",
                  self_in_set_reason="revision requires own text (subject, not scored)")
    assert rec["judge_vendor"] == "embedding" and rec["scorer_kind"] == "embedding"
    assert rec["judged_set"] == PANEL and rec["self_excluded"] is True
    assert len(rec["exself_helper_sha"]) == 12


# ---------------------------------------------------------------------------
# 4  roundtable: provenance block, summary-only r3 distance, optional ablation
# ---------------------------------------------------------------------------

R3_REPLY = ("1. Yes, I acknowledge the omissions.\n"
            "2. They were absent because I compressed the article.\n"
            "3. Final summary: The council approved the budget after a long debate, "
            "and the mayor said the shortfall would be covered by reserves.")


def test_extract_final_summary():
    import roundtable as rt
    s = rt.extract_final_summary(R3_REPLY)
    assert s and s.startswith("The council approved") and "acknowledge" not in s
    s2 = rt.extract_final_summary("Intro.\n\n**Final Summary**\nThe river flooded the valley and forty homes were lost overnight.")
    assert s2 and s2.startswith("The river flooded")
    assert rt.extract_final_summary("no heading here at all, just prose about a thing") is None
    assert rt.extract_final_summary("") is None and rt.extract_final_summary(None) is None


@pytest.fixture
def rt_stub(monkeypatch):
    import roundtable as rt
    prompts = []

    def fake_query(model_name, prompt, system="x"):
        prompts.append((model_name, prompt))
        return f"{model_name} says: " + R3_REPLY

    monkeypatch.setattr(rt, "query_model", fake_query)
    monkeypatch.setattr(rt, "compute_vix", lambda a, b: 0.1)
    return rt, prompts


def test_roundtable_provenance_block_and_shape(rt_stub, monkeypatch):
    rt, prompts = rt_stub
    monkeypatch.delenv("ROUNDTABLE_ABLATE", raising=False)
    res = rt.run_roundtable("t", "source text " * 20, void_words=["a", "b", "c"])
    # aired keys unchanged
    for k in ("title", "timestamp", "rounds", "round1_vix", "round2_vix", "round3_vix"):
        assert k in res
    assert set(res["rounds"]) == {"round1", "round2", "round3"}
    assert len(prompts) == 15                        # 3 rounds x 5 models, no ablation by default
    assert "round2_vix_selfonly" not in res
    # behaviour unchanged: round 2 still shows all five including own
    for name, p in prompts[5:10]:
        assert p.count("'s response ---") == 5 and f"--- {name}'s response ---" in p
    prov = res["provenance"]
    assert prov["llm_judge"] is None and prov["scorer_kind"] == "embedding"
    assert prov["judge"] == "bge-large-en-v1.5:cosine"
    assert prov["self_read"] is True and prov["self_excluded_from_scored_set"] is True
    assert prov["self_in_set_reason"] == "revision requires own text (subject, not scored)"
    assert prov["round2_shown"] == "all five round-1 responses including own"
    assert prov["r3_scored_on"].startswith("full reply")
    assert set(prov["model_ids"]) == set(rt.MODELS)
    for name in rt.MODELS:
        peers = [m for m in rt.MODELS if m != name]
        assert prov["per_model"][name]["round2_saw"]["peers"] == peers
        assert prov["per_model"][name]["round2_saw"]["self"] is True
    assert set(res["round3_vix_summary"]) == set(rt.MODELS)
    assert "off" in prov["ablation"]
    json.dumps(res, default=str)                     # serialisable like the segment writer needs


def test_roundtable_ablation_when_enabled(rt_stub, monkeypatch):
    rt, prompts = rt_stub
    monkeypatch.setenv("ROUNDTABLE_ABLATE", "1")
    res = rt.run_roundtable("t", "source text " * 20, void_words=["a"])
    assert len(prompts) == 20
    assert set(res["round2_vix_selfonly"]) == set(rt.MODELS)
    selfonly = [p for n, p in prompts if "Your own Round 1 response" in p]
    assert len(selfonly) == 5 and all("'s response ---" not in p for p in selfonly)
    assert res["provenance"]["ablation"] == "round2_vix_selfonly present"


# ---------------------------------------------------------------------------
# 6  summary_plus_production: the checker is never the writer's vendor
# ---------------------------------------------------------------------------

def test_summary_plus_production_selfcheck_judge_differs(monkeypatch):
    import confront10 as C
    import summary_plus_production as SPP
    rec = Recorder(PANEL, "1: O\n2: I\n3: O\n")
    monkeypatch.setattr(C, "API_PATIENTS", rec)
    local_calls = []
    monkeypatch.setattr(C, "mt_local", lambda msgs, model: (local_calls.append(model), "1: O\n2: O\n")[1])
    monkeypatch.delenv("SP_CHECKER", raising=False)
    src = "The council met. It approved a budget. The mayor spoke."
    summ = "The council approved a budget after meeting. The mayor spoke about reserves. Silence on the shortfall is telling."
    prof, gold, checked_by = SPP.self_check(src, summ, writer="Claude")
    called = {n for n, _ in rec.calls}
    assert called == {checked_by} and X.vendor_of(checked_by) != "anthropic"
    assert prof["checked_by"] == checked_by and prof["author"] == "Claude" and prof["self_excluded"] is True
    with pytest.raises(X.ExSelfViolation):
        SPP.self_check(src, summ, model_for_check="Claude", author="Claude")
    assert X.vendor_of(SPP.choose_checker("ChatGPT")) != "openai"
    assert X.vendor_of(SPP.choose_checker("Claude")) != "anthropic"
    monkeypatch.setenv("SP_CHECKER", "Gemini")
    with pytest.raises(X.ExSelfViolation):
        SPP.choose_checker("Gemini")                 # an explicit same-vendor override is refused
    # local checker path keeps the checker off the panel entirely
    monkeypatch.setenv("SP_CHECKER", "local")
    assert SPP.choose_checker("Claude") == "mistral:latest"
    rec.calls.clear()
    prof2, _, cb2 = SPP.self_check(src, summ, author="Claude")
    assert cb2 == "mistral:latest" and local_calls == ["mistral:latest"] and not rec.calls


# ---------------------------------------------------------------------------
# 7  experiment scripts: judge() takes the author, logs per-score records
# ---------------------------------------------------------------------------

@pytest.fixture
def cp(monkeypatch):
    import confront10 as C
    import control_plainprompt as CP
    rec = Recorder(PANEL, SCORES_OK)
    monkeypatch.setattr(C, "API_PATIENTS", rec)
    return CP, rec


def test_experiment_judge_skips_author_when_asked(cp):
    CP, rec = cp
    texts = {"BASELINE": "b " * 20, "PLAIN_PLUS": "p " * 20, "A_PLUS_C": "a " * 20}
    recs = []
    random.seed(0)
    out = CP.judge("src", texts, author="Gemini", skip_self=True, story="s", gen=0, records=recs)
    called = [n for n, _ in rec.calls]
    assert "Gemini" not in called and len(called) == 4 and set(out) == set(called)
    assert recs and all(r["self_excluded"] and not r["self_judged"] and r["judge"] != "Gemini" for r in recs)
    assert all(r["story"] == "s" and r["patient"] == "Gemini" and r["gen"] == 0 for r in recs)


def test_experiment_judge_default_calls_all_and_marks_diagonal(cp):
    CP, rec = cp
    texts = {"BASELINE": "b " * 20, "PLAIN_PLUS": "p " * 20, "A_PLUS_C": "a " * 20}
    recs = []
    random.seed(0)
    CP.judge("src", texts, author="Gemini", skip_self=False, story="s", gen=1, records=recs)
    assert sorted(n for n, _ in rec.calls) == sorted(PANEL)
    gem = [r for r in recs if r["judge"] == "Gemini"]
    assert gem and all(r["self_judged"] for r in gem)
    assert all(not r["self_judged"] for r in recs if r["judge"] != "Gemini")
    # every record: judge, patient, arm, metric, score, order, position (all parsed here)
    assert all(r["parsed"] for r in recs)
    for r in recs:
        assert r["arm"] in texts and r["metric"] in X.METRICS and r["position"] in (1, 2, 3)
        assert r["order"] and r["judge_vendor"] in {"openai", "anthropic", "google", "deepseek", "xai"}
    ex = X.aggregate(recs, exclude_self=True)
    al = X.aggregate(recs, exclude_self=False)
    for arm in texts:
        assert al[arm]["n"] == 5 and ex[arm]["n"] == 4


def test_seeded_shuffle_is_reproducible(cp):
    CP, rec = cp
    texts = {"BASELINE": "b " * 20, "PLAIN_PLUS": "p " * 20, "A_PLUS_C": "a " * 20}
    orders = []
    for _ in range(2):
        random.seed(0)
        recs = []
        CP.judge("src", texts, author="Grok", skip_self=False, records=recs)
        orders.append(tuple(recs[0]["order"]))
    assert orders[0] == orders[1]


def test_judge_only_loader_and_summary_on_synthetic_results(cp, tmp_path, monkeypatch):
    CP, rec = cp
    results = [{"story": "s1", "shape": "x", "source": "src " * 50,
                "rows": [{"patient": p, "gens": [{"BASELINE": "b " * 20, "PLAIN_PLUS": "p " * 20, "A_PLUS_C": "a " * 20}]}
                         for p in PANEL]}]
    f = tmp_path / "results.json"
    f.write_text(json.dumps(results))
    loaded = CP.load_results(str(f))
    assert loaded == results
    # judge monkeypatched: deterministic per-judge parse, records appended
    calls = []

    def fake_judge(src, texts, author=None, judges=None, skip_self=None, story=None, gen=None, records=None):
        calls.append((author, story, gen))
        for jn in PANEL:
            own = jn == author
            parsed = {a: {"insight": 3 + own, "faith": 4, "action": 3, "trust": 4, "keep": 1} for a in texts}
            records.extend(X.make_records(story, author, gen, jn, parsed, list(texts)))
        return {}

    monkeypatch.setattr(CP, "judge", fake_judge)
    recs = CP.run_panel(loaded)
    assert len(calls) == 5 and all(c[1] == "s1" for c in calls)
    summary = CP.summarize(recs)
    assert set(summary["self_included"]) == {"BASELINE", "PLAIN_PLUS", "A_PLUS_C"}
    assert summary["n_self_included"]["A_PLUS_C"] == 25 and summary["n_exself"]["A_PLUS_C"] == 20
    assert abs(summary["self_included"]["A_PLUS_C"]["insight"] - 3.2) < 1e-9
    assert abs(summary["exself"]["A_PLUS_C"]["insight"] - 3.0) < 1e-9
    assert abs(summary["delta_self_included"]) < 1e-9 and abs(summary["delta_exself"]) < 1e-9
    assert all(row["self_pref"] == 1.0 for row in summary["self_pref_by_judge"].values())
    assert summary["parse_rate_by_judge"]["Claude"]["rate"] == 1.0
    CP.print_report(recs, summary)          # must not raise
    assert not rec.calls                    # the real judge was never reached


def test_confront10_final_judge_gold_is_never_self_judged(monkeypatch):
    import confront10 as C
    import confront10_final as F
    rec = Recorder(PANEL, SCORES_OK)
    monkeypatch.setattr(C, "API_PATIENTS", rec)
    texts = {"BASELINE": "b " * 20, "A_PLUS_C": "a " * 20, "GOLD": "g " * 20}
    recs = []
    random.seed(0)
    F.judge("src", texts, author="Claude", skip_self=False, story="mexico_cia", gen=0, records=recs)
    gold = [r for r in recs if r["arm"] == "GOLD"]
    assert gold and all(r["author"] is None and not r["self_judged"] for r in gold)
    own = [r for r in recs if r["arm"] != "GOLD" and r["judge"] == "Claude"]
    assert own and all(r["self_judged"] for r in own)
    # code_sentences skips the author's vendor
    rec.calls.clear()
    monkeypatch.setattr(C, "API_PATIENTS", Recorder(PANEL, "1: O\n2: I\n"))
    F.code_sentences("src", "First sentence is here now. Second sentence is here too.", PANEL, author="DeepSeek")
    assert "DeepSeek" not in {n for n, _ in C.API_PATIENTS.calls} and len(C.API_PATIENTS.calls) == 4
    # GOLD (author None) is coded by all judges
    monkeypatch.setattr(C, "API_PATIENTS", Recorder(PANEL, "1: O\n2: I\n"))
    F.code_sentences("src", "First sentence is here now. Second sentence is here too.", PANEL, author=None)
    assert len(C.API_PATIENTS.calls) == 5


# ---------------------------------------------------------------------------
# 8  qwen research scripts: judge() posts to JUDGE_MODEL, never the generator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("modname", ["summary_plus", "summary_plus_v3", "summary_plus_clean"])
def test_summary_plus_scripts_judge_with_a_different_model(modname, monkeypatch):
    mod = __import__(modname)
    assert mod.JUDGE_MODEL != mod.MODEL and mod.JUDGE_MODEL == "mistral:latest"
    posted = []

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "FAITH=7 COV=8"}}]}

    monkeypatch.setattr(mod.requests, "post", lambda url, json=None, timeout=None: (posted.append(json), R())[1])
    assert mod.judge("source", "summary") == (7, 8)
    assert posted and posted[-1]["model"] == "mistral:latest"
    mod.llm("x")
    assert posted[-1]["model"] == mod.MODEL         # the generator path is unchanged


# ---------------------------------------------------------------------------
# 9  tools/roundtable_null.py on synthetic files (never the runtime tree)
# ---------------------------------------------------------------------------

def _load_tool():
    spec = importlib.util.spec_from_file_location("roundtable_null", ROOT / "tools" / "roundtable_null.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_roundtable_null_tool(tmp_path):
    tool = _load_tool()
    r1 = {m: 0.15 for m in PANEL}
    for i, r3 in enumerate([{m: 0.30 for m in PANEL},                       # all double down
                            {m: 0.30 for m in PANEL},
                            {**{m: 0.30 for m in PANEL}, "Claude": 0.10}]):   # Claude opens up once
        (tmp_path / f"2026091{i}_000000_roundtable.json").write_text(
            json.dumps({"title": "t", "rounds": {}, "round1_vix": r1, "round3_vix": r3}))
    (tmp_path / "junk_roundtable.json").write_text("not json")
    (tmp_path / "20260910_000000_roundtable_segment.json").write_text("{}")
    rts = tool.load_roundtables(str(tmp_path))
    assert len(rts) == 3
    res = tool.summarize(rts)
    assert res["overall"]["n_pairs"] == 15
    assert abs(res["overall"]["frac_doubled_down"] - 14 / 15) < 1e-9
    assert abs(res["per_model"]["Claude"]["frac_opened_up"] - 1 / 3) < 1e-9
    assert abs(res["per_model"]["Grok"]["mean_delta"] - 0.15) < 1e-9
    assert tool.verdict(res["overall"]).startswith("FORMAT ARTEFACT")
    assert tool.main(["--dir", str(tmp_path)]) == 0
    assert tool.main(["--dir", str(tmp_path / "empty")]) == 1


# ---------------------------------------------------------------------------
# 10  nothing above touched the published artefacts
# ---------------------------------------------------------------------------

def test_published_artefacts_untouched():
    for p, m in _MTIMES.items():
        assert p.stat().st_mtime_ns == m, f"{p.name} was modified by the test run"
    assert not (ROOT / "control_plainprompt_panel_v2.json").exists() or True   # a real re-judge may exist; never asserted absent
