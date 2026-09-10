"""batch_producer: import hygiene, queue_depth, _call_with_retry.

Importing batch_producer runs load_dotenv (stubbed by conftest), sys.path.insert
and logging.basicConfig; it must not create CUDA tensors.  Nothing here calls
main() or any stage_* function.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

import batch_producer as bp


def test_import_did_not_touch_gpu():
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    torch = sys.modules.get("torch")
    if torch is not None:
        assert not torch.cuda.is_initialized()
        assert not torch.cuda.is_available()
    assert getattr(sys.modules["dotenv"], "__stub__", False), "real dotenv was used at import"


# ---------------------------------------------------------------------------
# Item 5 -- queue_depth
# ---------------------------------------------------------------------------

STORY = "20260910_1200{:02d}_{}_segment.json"


def _touch(path, age_s: float = 0.0):
    path.write_text("{}")
    t = time.time() - age_s
    os.utime(path, (t, t))


@pytest.fixture
def seg_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "SEGMENTS_DIR", tmp_path)
    return tmp_path


def test_queue_depth_counts_only_fresh_unplayed_story_segments(seg_dir):
    _touch(seg_dir / STORY.format(1, "0123456789ab"))                     # fresh, unplayed  -> 1
    _touch(seg_dir / STORY.format(2, "abcdef012345"), age_s=3600)         # 1 h old          -> 1
    played = STORY.format(3, "fedcba987654")
    _touch(seg_dir / played)
    (seg_dir / (played[:-5] + ".played")).write_text("")                   # played           -> 0
    _touch(seg_dir / STORY.format(4, "111111111111"), age_s=7 * 3600)     # older than 6 h   -> 0
    _touch(seg_dir / "20260910_120005_idle_segment.json")                  # not a story      -> 0
    _touch(seg_dir / "20260910_120006_roundtable_segment.json")            # own output       -> 0
    _touch(seg_dir / "20260910_120007_0123456789ab_pundit_segment.json")   # pundit           -> 0
    _touch(seg_dir / "20260910_120008_0123456789ab.json")                  # raw story, no seg-> 0
    _touch(seg_dir / STORY.format(9, "XYZ123456789"))                      # hash not hex     -> 0
    assert bp.queue_depth() == 2


def test_queue_depth_age_boundary(seg_dir):
    _touch(seg_dir / STORY.format(1, "0123456789ab"), age_s=bp._QUEUE_MAX_AGE_S - 30)
    _touch(seg_dir / STORY.format(2, "0123456789ac"), age_s=bp._QUEUE_MAX_AGE_S + 30)
    assert bp.queue_depth() == 1


def test_queue_depth_missing_or_empty_dir(seg_dir, tmp_path):
    assert bp.queue_depth() == 0
    bp.SEGMENTS_DIR = tmp_path / "does-not-exist"
    assert bp.queue_depth() == 0


def test_story_segment_regex_shape():
    assert bp._STORY_SEG_RE.match("20260910_111314_da5ad64ed6fe_segment.json")
    assert not bp._STORY_SEG_RE.match("20260910_111314_da5ad64ed6fe_segment.json.tmp")
    assert not bp._STORY_SEG_RE.match("20260910_111314_da5ad64ed6f_segment.json")   # 11 hex
    assert bp._QUEUE_MAX_AGE_S == 6 * 3600


# ---------------------------------------------------------------------------
# Item 6 -- _call_with_retry
# ---------------------------------------------------------------------------

class Caller:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        return self.script.pop(0)


@pytest.fixture
def sleeps(monkeypatch):
    seen = []
    monkeypatch.setattr(bp.time, "sleep", lambda s: seen.append(s))
    return seen


def test_retry_recovers_from_transient_error(sleeps):
    c = Caller([("", "Connection reset by peer"), ("fine", None)])
    txt, err = bp._call_with_retry("gpt", c, "p", retries=2, backoff=0.01)
    assert (txt, err) == ("fine", None)
    assert c.calls == 2
    assert sleeps == [pytest.approx(0.01)]


def test_retry_backoff_grows_and_gives_up(sleeps):
    c = Caller([("", "HTTP 503"), ("", "HTTP 429"), ("", "timeout")])
    txt, err = bp._call_with_retry("gpt", c, "p", retries=2, backoff=0.01)
    assert txt == "" and err == "timeout"
    assert c.calls == 3
    assert sleeps == [pytest.approx(0.01), pytest.approx(0.02)]


@pytest.mark.parametrize("err", ["HTTP 401 Unauthorized", "no_key", "403 forbidden", "400 bad request", "404"])
def test_retry_never_retries_permanent_errors(sleeps, err):
    c = Caller([("", err), ("should-not-run", None)])
    txt, got = bp._call_with_retry("gpt", c, "p", retries=3, backoff=0.01)
    assert (txt, got) == ("", err)
    assert c.calls == 1
    assert sleeps == []


def test_retry_not_triggered_when_text_present(sleeps):
    c = Caller([("partial answer", "truncated"), ("x", None)])
    txt, err = bp._call_with_retry("gpt", c, "p")
    assert (txt, err) == ("partial answer", "truncated")
    assert c.calls == 1 and sleeps == []


def test_retry_success_first_try(sleeps):
    c = Caller([("ok", None)])
    assert bp._call_with_retry("gpt", c, "p") == ("ok", None)
    assert c.calls == 1 and sleeps == []


def test_permanent_error_regex_word_boundary():
    assert bp._PERMANENT_ERR.search("status 401")
    assert not bp._PERMANENT_ERR.search("request id 14010 timed out")   # 401 inside a longer number
    assert bp._PERMANENT_ERR.search("no_key")
