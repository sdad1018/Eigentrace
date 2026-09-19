"""EigenChing beat keying (2026-09-19): eigenching_report.py keys on the EXACT
archetype name and counts near-misses separately.

The bug these tests pin: the generator keyed each beat on the text before the
first comma. eigenching.py writes a comma into the state name only for a
near-miss ("The Cornering, verbs recovering"), never for an exact hit, so the
old key returned a bare archetype name only for near-misses and dropped every
exact hit. All published counts were near-misses.

CPU only, no network, no writes outside tmp_path: SEGMENT_DIR / OUT_PATH /
DIST_PATH are monkeypatched.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import eigenching as ec
import eigenching_report as er


# ─── fixtures ───────────────────────────────────────────────────────────────

def _seg(title, beat_text, attribution=None):
    attr = {"story_title": title}
    if attribution:
        attr.update(attribution)
    return {"timestamp": "20260910_010000", "attribution": attr,
            "beats": [{"phase": "beat_18b_state_vector", "speaker": "Host", "text": beat_text}]}


def _metrics(entity=0.8, verb=0.01, absent=0.2, hedges=2, density=0.88, vix=(10.0, 14.0)):
    return {"consensus_density": density,
            "model_vix": {"ChatGPT": vix[0], "Claude": vix[1]},
            "compression": {"entity_retention": entity, "verb_downgrade": verb,
                            "compression_score": 0.3,
                            "attribution_buffer": {"total": hedges}},
            "source_void": {"absent_ratio": absent, "source_word_count": 120}}


def _write(d: Path, segs):
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(segs):
        (d / f"20260910_0{i:05d}_{i:012x}_segment.json").write_text(json.dumps(s))


def _run(tmp_path, monkeypatch, segs):
    seg_dir = tmp_path / "segs"
    _write(seg_dir, segs)
    monkeypatch.setattr(er, "SEGMENT_DIR", str(seg_dir))
    monkeypatch.setattr(er, "OUT_PATH", str(tmp_path / "eigenching_data.json"))
    monkeypatch.setattr(er, "DIST_PATH", str(tmp_path / "eigenching_distribution.md"))
    return er.generate_report()


def _card(rep, name):
    return next(a for a in rep["archetypes"] if a["name"] == name)


# ─── the name parser ────────────────────────────────────────────────────────

def test_aired_name_stops_at_the_period_not_the_first_comma():
    """The name is everything before the first period. The old key cut at the
    first comma, which returns the base archetype for a near-miss."""
    text = ("EigenChing state: The Cornering, verbs recovering. This is The Cornering "
            "pattern - Models lockstep on compression. But verbs recovering this time.")
    assert er.aired_name(text) == "The Cornering, verbs recovering"
    assert text.split("EigenChing state:")[1].split(",")[0].strip() == "The Cornering"


def test_aired_name_of_an_exact_hit_is_the_bare_archetype():
    text = ("EigenChing state: The Cornering. Models lockstep on compression. "
            "The narrowness of agreement is itself a signal. Named archetype.")
    assert er.aired_name(text) == "The Cornering"


def test_aired_name_is_none_when_the_beat_is_not_in_this_format():
    assert er.aired_name("EigenTrace state vector. consensus density: plus.") is None


# ─── key_beat tiers ─────────────────────────────────────────────────────────

def test_exact_hit_keys_exact():
    tier, arch, name = er.key_beat("EigenChing state: The Sealed Vault. Total compression. Named archetype.")
    assert (tier, arch) == ("exact", "The Sealed Vault")
    assert name == "The Sealed Vault"


@pytest.mark.parametrize("name", [
    "The Cornering, verbs recovering",                 # distance 1
    "The Cornering, verbs recovering and names erased",  # distance 2
    "Partial The Cornering",                            # distance 2, no modifier phrase
])
def test_near_miss_keys_near_miss_and_never_exact(name):
    tier, arch, _ = er.key_beat(f"EigenChing state: {name}. This is The Cornering pattern - x.")
    assert tier == "near_miss"
    assert arch == "The Cornering"


def test_compositional_name_is_outside_named_territory():
    tier, arch, name = er.key_beat(
        "EigenChing state: Mixed Preserved Intact Generic Walled Normal. "
        "Partial agreement; source survived mostly intact. Outside named territory.")
    assert tier == "outside"
    assert arch is None
    assert name == "Mixed Preserved Intact Generic Walled Normal"


@pytest.mark.parametrize("variant", [
    "the clear channel",
    "THE CLEAR CHANNEL",
    "The   Clear    Channel",
    "  The Clear Channel  ",
])
def test_keying_is_case_insensitive_and_whitespace_normalised(variant):
    tier, arch, _ = er.key_beat(f"EigenChing state: {variant}. Signal passes through.")
    assert (tier, arch) == ("exact", "The Clear Channel")


def test_every_archetype_name_round_trips_through_format_broadcast():
    """What eigenching.py airs for an exact hit must key back to that archetype."""
    for sig, (name, _desc) in ec.ARCHETYPES.items():
        text = ec.format_broadcast(sig)
        tier, arch, _ = er.key_beat(text)
        assert (tier, arch) == ("exact", name), text


def test_one_axis_flips_air_and_key_as_near_misses():
    """Flip one axis of every archetype: eigenching.py names the result after
    the nearest archetype, and the report must key it as a near-miss of that
    same archetype, never as the archetype itself."""
    checked = 0
    for sig in ec.ARCHETYPES:
        for axis in range(6):
            flipped = list(sig)
            flipped[axis] = 0 if sig[axis] else 1
            flipped = tuple(flipped)
            if flipped in ec.ARCHETYPES:
                continue
            expected = ec.classify(flipped)["archetype_name"]
            tier, arch, _ = er.key_beat(ec.format_broadcast(flipped))
            assert tier == "near_miss", flipped
            assert arch == expected, flipped
            checked += 1
    assert checked > 150


# ─── legacy axis-readout beats ──────────────────────────────────────────────

def test_legacy_axis_readout_is_classified_from_its_axis_words():
    text = ("EigenTrace state vector. consensus density: neutral, absent ratio: neutral, "
            "verb drift: neutral, entity retention: neutral, hedge count: neutral, "
            "mean vix: neutral. This exact state has occurred 4 times before.")
    assert er.legacy_signature(text) == (0, 0, 0, 0, 0, 0)
    tier, arch, _ = er.key_beat(text)
    assert (tier, arch) == ("exact", "The Still Point")


def test_legacy_axis_readout_near_miss():
    text = ("EigenTrace state vector. consensus density: plus, absent ratio: neutral, "
            "verb drift: neutral, entity retention: neutral, hedge count: neutral, "
            "mean vix: neutral.")
    assert er.legacy_signature(text) == (1, 0, 0, 0, 0, 0)
    tier, arch, _ = er.key_beat(text)
    assert tier == "near_miss"
    assert arch == "The Still Point"


# ─── the report ─────────────────────────────────────────────────────────────

def test_report_counts_exact_hits_and_holds_near_misses_apart(tmp_path, monkeypatch):
    segs = [_seg("Exact story", "EigenChing state: The Cornering. Models lockstep. Named archetype.",
                 _metrics())]
    segs += [_seg(f"Near story {i}",
                  "EigenChing state: The Cornering, verbs recovering. This is The Cornering pattern - x.",
                  _metrics()) for i in range(4)]
    rep = _run(tmp_path, monkeypatch, segs)

    card = _card(rep, "The Cornering")
    assert card["count"] == 1                      # the exact hit, and only it
    assert card["near_miss_count"] == 4
    assert card["pct"] == 20.0                     # 1 of 5 state beats
    assert rep["exact_total"] == 1
    assert rep["near_miss_total"] == 4
    assert rep["total_segments"] == 5
    assert rep["archetypes_with_exact_hits"] == 1
    assert rep["archetypes_without_exact_hits"] == 31


def test_near_miss_beats_alone_leave_every_count_at_zero(tmp_path, monkeypatch):
    """The bug's signature: 32 archetypes 'observed' with no exact hit anywhere."""
    segs = [_seg(f"s{i}", "EigenChing state: The Unanimous Shield, hedges easing and loosening. x.",
                 _metrics()) for i in range(6)]
    rep = _run(tmp_path, monkeypatch, segs)
    assert rep["exact_total"] == 0
    assert rep["archetypes_with_exact_hits"] == 0
    assert _card(rep, "The Unanimous Shield")["count"] == 0
    assert _card(rep, "The Unanimous Shield")["near_miss_count"] == 6
    assert all(a["count"] == 0 for a in rep["archetypes"])


def test_examples_come_only_from_exact_hits(tmp_path, monkeypatch):
    segs = [_seg("EXACT", "EigenChing state: The Cornering. Named archetype.", _metrics()),
            _seg("NEAR", "EigenChing state: The Cornering, verbs recovering. x.", _metrics())]
    rep = _run(tmp_path, monkeypatch, segs)
    card = _card(rep, "The Cornering")
    assert card["examples"] == ["EXACT"]
    assert card["near_miss_examples"] == ["NEAR"]


def test_tiers_partition_the_beats(tmp_path, monkeypatch):
    segs = [_seg("a", "EigenChing state: The Cornering. Named archetype.", _metrics()),
            _seg("b", "EigenChing state: The Cornering, verbs recovering. x.", _metrics()),
            _seg("c", "EigenChing state: Mixed Preserved Intact Generic Walled Normal. "
                      "Outside named territory.", _metrics())]
    rep = _run(tmp_path, monkeypatch, segs)
    assert (rep["exact_total"] + rep["near_miss_total"]
            + rep["outside_named_territory_total"]) == rep["state_beats"] == 3
    assert rep["most_common_aired_state"] == "Mixed Preserved Intact Generic Walled Normal"


def test_percentages_never_exceed_the_beat_count(tmp_path, monkeypatch):
    """Published pct summed to 69.2% because counted beats and the denominator
    came from different populations. Exact counts cannot outrun the denominator."""
    segs = [_seg("a", "EigenChing state: The Cornering. Named archetype.", _metrics()),
            _seg("b", "EigenChing state: The Still Point. Named archetype.", _metrics()),
            _seg("c", "EigenChing state: The Cornering, verbs recovering. x.", _metrics())]
    rep = _run(tmp_path, monkeypatch, segs)
    assert sum(a["count"] for a in rep["archetypes"]) == rep["exact_total"] == 2
    assert rep["exact_total"] <= rep["total_segments"]
    for a in rep["archetypes"]:
        assert a["pct"] == round(a["count"] / rep["total_segments"] * 100, 1)


def test_census_fields_survive(tmp_path, monkeypatch):
    segs = [_seg("a", "EigenChing state: The Cornering. Named archetype.", _metrics())]
    rep = _run(tmp_path, monkeypatch, segs)
    assert rep["census"] is True and rep["n"] == 1
    assert "census" in rep["ci_method"]
    assert "near_miss_count" in rep["ci_method"]
    assert "pct_ci" not in rep["archetypes"][0]
    written = json.loads((tmp_path / "eigenching_data.json").read_text())
    assert written["n"] == 1
    assert written["keying"].startswith("exact archetype name")


def test_redirecting_out_path_alone_never_writes_the_live_page(tmp_path, monkeypatch):
    """The distribution page is written beside OUT_PATH, so a caller that
    redirects only OUT_PATH cannot overwrite docs/eigenching_distribution.md."""
    seg_dir = tmp_path / "segs"
    _write(seg_dir, [_seg("a", "EigenChing state: The Cornering. Named archetype.", _metrics())])
    monkeypatch.setattr(er, "SEGMENT_DIR", str(seg_dir))
    monkeypatch.setattr(er, "OUT_PATH", str(tmp_path / "eigenching_data.json"))
    live = Path(er.DIST_PATH)
    before = live.read_bytes() if live.exists() else None
    er.generate_report()
    assert (tmp_path / "eigenching_distribution.md").exists()
    after = live.read_bytes() if live.exists() else None
    assert after == before


def test_the_generator_does_not_key_on_the_first_comma():
    src = inspect.getsource(er)
    assert '.split(",")[0]' not in src


# ─── MISSING is not zero ────────────────────────────────────────────────────

def test_absent_compression_block_is_missing_not_zero():
    values, missing = er.axis_inputs({"story_title": "t"})
    assert set(missing) == set(er.AXIS_SIGNALS)
    assert all(values[k] is None for k in er.AXIS_SIGNALS)


def test_present_metrics_are_not_missing():
    values, missing = er.axis_inputs(_metrics())
    assert missing == []
    assert values["entity_retention"] == 0.8
    assert values["vix_spread"] == pytest.approx(4.0)


def test_partial_block_reports_only_the_absent_axes():
    attr = _metrics()
    del attr["compression"]["entity_retention"]
    del attr["source_void"]["absent_ratio"]
    _values, missing = er.axis_inputs(attr)
    assert sorted(missing) == ["absent_ratio", "entity_retention"]


def test_missing_rows_are_excluded_from_the_state_denominator(tmp_path, monkeypatch):
    beat = "EigenChing state: The Cornering. Named archetype."
    segs = [_seg(f"m{i}", beat) for i in range(3)]                     # no metrics at all
    segs += [_seg(f"ok{i}", beat, _metrics()) for i in range(2)]       # fully measured
    rep = _run(tmp_path, monkeypatch, segs)
    sd = rep["state_distribution"]
    assert sd["rows"] == 5
    assert sd["missing_rows"] == 3
    assert sd["measured_rows"] == 2
    assert sd["missing_by_axis"]["entity_retention"] == 3


def test_the_missing_cell_is_reported_but_not_as_a_measurement(tmp_path, monkeypatch):
    """A row with no compression block quantizes to entity -1 / verb +1 by
    construction. It must appear in the imputed figure and not in the measured one."""
    beat = "EigenChing state: The Cornering. Named archetype."
    segs = [_seg(f"m{i}", beat) for i in range(4)]
    segs += [_seg("ok", beat, _metrics(entity=0.8, verb=0.01))]
    rep = _run(tmp_path, monkeypatch, segs)
    sd = rep["state_distribution"]
    assert sd["entity_dropped_verbs_intact_if_missing_read_as_zero"] == [4, 5]
    assert sd["entity_dropped_verbs_intact_measured"] == [0, 1]


def test_distribution_page_is_written_and_labels_the_tiers(tmp_path, monkeypatch):
    segs = [_seg("a", "EigenChing state: The Cornering. Named archetype.", _metrics()),
            _seg("b", "EigenChing state: The Cornering, verbs recovering. x.", _metrics()),
            _seg("c", "EigenChing state: The Cornering, verbs recovering. x.")]
    _run(tmp_path, monkeypatch, segs)
    md = (tmp_path / "eigenching_distribution.md").read_text()
    assert "# EigenChing distribution" in md
    assert "exact archetype" in md and "near-miss" in md
    assert "MISSING" in md
    assert "strips proper nouns" not in md
