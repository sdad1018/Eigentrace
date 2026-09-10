"""reasoning_log.py — keep the producer's pre-aired reasoning in full (2026-09-10).

Until now the director's three-line note was logged at 80 characters and the host model's
<think> scratchpad at 200; the full text was discarded. Both are appended here, one JSON line
each, one file per day, under the PRIVATE runtime tree (they contain raw model output about
copyrighted articles). Never blocks the producer.
"""
import json
import os
import time

REASONING_DIR = os.getenv("REASONING_DIR", "/home/remvelchio/eigentrace/tmp/reasoning")


def persist(kind: str, text: str, **fields) -> None:
    try:
        os.makedirs(REASONING_DIR, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "text": text}
        row.update({k: v for k, v in fields.items() if v is not None})
        path = os.path.join(REASONING_DIR, "reasoning_" + time.strftime("%Y%m%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
