"""segment_player.update_ticker.

segment_player.py takes an exclusive flock on /tmp/segment_player.lock at import
(and sys.exit(1)s if the live player holds it), so the function is lifted out of
the file with ast and compiled into a namespace that supplies os, log and a
TICKER_FILE under tmp_path.  Nothing from the live player is imported or touched.

Current contract (2026-09-09 rewrite): Friction = attribution.mean_vix (fallback:
mean of attribution.model_vix, then top-level gap_vix), formatted .1f; state =
attribution.state_flag (fallback: top-level state_flag, then ACTIVE); the file is
written to <name>.tmp and os.replace'd so ffmpeg's drawtext never sees a truncated file.
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "segment_player.py"


def _extract_update_ticker(ticker_path: Path, namespace_extra: dict | None = None):
    tree = ast.parse(SRC.read_text(encoding="utf-8"), filename=str(SRC))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "update_ticker"]
    assert len(fns) == 1, "expected exactly one top-level update_ticker in segment_player.py"
    module = ast.Module(body=[fns[0]], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "__name__": "segment_player_extract",
        "os": os,
        "re": __import__("re"),
        "Path": Path,
        "log": logging.getLogger("segment_player_extract"),
        "TICKER_FILE": ticker_path,
    }
    ns.update(namespace_extra or {})
    exec(compile(module, str(SRC), "exec"), ns)
    return ns["update_ticker"]


@pytest.fixture
def ticker(tmp_path):
    path = tmp_path / "ticker.txt"
    return path, _extract_update_ticker(path)


def test_update_ticker_writes_atomically_and_leaves_no_tmp(ticker):
    path, update_ticker = ticker
    update_ticker("Ceasefire talks stall", ["casualties", " ", "", "envoy"], {})
    assert path.exists()
    assert sorted(p.name for p in path.parent.iterdir()) == ["ticker.txt"], "stray .tmp / partial file"
    line = path.read_text()
    assert line.count("Ceasefire talks stall") == 4          # repeated 4x for the scroll
    assert "Core Factors: casualties | envoy" in line         # blanks scrubbed
    assert "Friction:" in line


def test_update_ticker_goes_through_os_replace(tmp_path):
    """The write must land in a sibling .tmp and be renamed over the target, never truncate in place."""
    path = tmp_path / "ticker.txt"
    path.write_text("old")
    seen = []

    def spy_replace(src, dst):
        seen.append((Path(src).name, Path(dst).name, Path(src).read_text()))
        return os.replace(src, dst)

    fake_os = type("FakeOS", (), {"replace": staticmethod(spy_replace)})
    update_ticker = _extract_update_ticker(path, {"os": fake_os})
    update_ticker("Budget vote", ["deficit"], {})
    assert len(seen) == 1
    src_name, dst_name, tmp_content = seen[0]
    assert src_name == "ticker.txt.tmp" and dst_name == "ticker.txt"
    assert "Budget vote" in tmp_content                     # fully written before the rename
    assert path.read_text() == tmp_content
    assert not (tmp_path / "ticker.txt.tmp").exists()


def test_update_ticker_friction_from_attribution_mean_vix_and_state_flag(ticker):
    path, update_ticker = ticker
    seg = {"attribution": {"mean_vix": 23.46, "state_flag": "LOCKSTEP", "model_vix": {"gpt": 5.0}}}
    update_ticker("Budget vote", ["deficit"], seg)
    line = path.read_text()
    assert "[LOCKSTEP]" in line
    assert "Friction: 23.5" in line                         # .1f of attribution.mean_vix
    assert "Friction: 5.0" not in line                      # mean_vix wins over model_vix


def test_update_ticker_falls_back_to_model_vix_mean(ticker):
    path, update_ticker = ticker
    seg = {"attribution": {"model_vix": {"gpt": 10.0, "claude": 30.0, "grok": "n/a"}}}
    update_ticker("Budget vote", ["deficit"], seg)
    line = path.read_text()
    assert "Friction: 20.0" in line
    assert "[ACTIVE]" in line


def test_update_ticker_fallbacks_and_defaults(ticker):
    path, update_ticker = ticker
    update_ticker("Quiet hour", [], None)
    line = path.read_text()
    assert "Core Factors: Analyzing" in line
    assert "[ACTIVE]" in line
    assert "Friction: 0.0" in line
    # legacy top-level keys still honoured when attribution carries nothing
    update_ticker("Quiet hour", [], {"gap_vix": "12.5", "state_flag": "FRACTURED"})
    line = path.read_text()
    assert "[FRACTURED]" in line and "Friction: 12.5" in line
    # garbage never raises
    update_ticker("Quiet hour", [], {"attribution": {"mean_vix": "not-a-number"}})
    assert "Friction: 0.0" in path.read_text()


def test_update_ticker_overwrites_previous_line(ticker):
    path, update_ticker = ticker
    update_ticker("First", ["a"], {})
    update_ticker("Second", ["b"], {})
    line = path.read_text()
    assert "First" not in line and "Second" in line
    assert line.count("Second") == 4
