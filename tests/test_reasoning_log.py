import json, os, importlib


def test_persist_writes_full_text_one_row_per_call(tmp_path, monkeypatch):
    monkeypatch.setenv("REASONING_DIR", str(tmp_path))
    import reasoning_log
    importlib.reload(reasoning_log)
    long = "x" * 5000
    reasoning_log.persist("scratchpad", long, prompt_head="p", spoken_head="s")
    reasoning_log.persist("director", "THESIS: a. TONE: clinical. REVELATION: b.", story_title="T", state_flag="CONTESTED")
    files = list(tmp_path.glob("reasoning_*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and rows[0]["kind"] == "scratchpad" and len(rows[0]["text"]) == 5000
    assert rows[1]["story_title"] == "T" and rows[1]["state_flag"] == "CONTESTED" and rows[1]["ts"]


def test_persist_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("REASONING_DIR", "/proc/definitely/not/writable")
    import reasoning_log
    importlib.reload(reasoning_log)
    reasoning_log.persist("director", "x")  # must swallow the error
