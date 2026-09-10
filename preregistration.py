#!/usr/bin/env python3
"""
preregistration.py — the pre-registration ledger (2026-09-10)
==============================================================
A sealed, per-story forecast of which model will have the highest VIX,
made AFTER the model texts arrive (stage 2) and BEFORE any of them is read
or embedded (stage 3), then scored against the measurement and spoken on air
with its two controls.

What the forecast is
--------------------
A base-rate prior: the model that was most often the outlier over the last
K scored stories of the same category (fallback: any category).  It is not
foresight and must never be spoken as foresight; the on-air sentence says so.

The seal (two-row scheme)
-------------------------
  kind="predicted"  written in stage 2b with flush+fsync BEFORE stage 3 runs.
                    prereg_id = sha256(line bytes)[:16] identifies the line.
  kind="scored"     written in stage 3 after model_vix exists; carries the
                    prereg_id so any reader can find the sealed line and check
                    predicted_at < scored_at on disk.
  kind="aired"      written in stage 7 once the segment file exists (linkage).
  kind="bootstrap"  outcome-only history reconstructed from stored segments;
                    predicted=null, feeds the prior, never the accuracy.

content_hash is a linkage field (sha256 of the canonical {name: text} map),
not a truth claim.  The truth claim is the on-disk order of the two rows.

Ledger path: env PREREG_LEDGER, default
  /home/remvelchio/eigentrace/tmp/preregistration_ledger.jsonl
Segments dir: env SEGMENTS_DIR, default /home/remvelchio/eigentrace/tmp/segments

Pure python (json, hashlib, collections): no numpy, no torch, no engines.
CLI:
  python3 preregistration.py --bootstrap [N]   write bootstrap rows (only if the ledger is empty)
  python3 preregistration.py --replay [N]      score the prior on the last N stored stories (read-only)
"""
from __future__ import annotations

import os
import re
import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER_PATH = "/home/remvelchio/eigentrace/tmp/preregistration_ledger.jsonl"
DEFAULT_SEGMENTS_DIR = "/home/remvelchio/eigentrace/tmp/segments"

K_PRIOR = 50
MIN_CATEGORY = 5
M_RUNNING = 100
PRIOR_VERSION = "outlier-freq-v1"
PRIOR_TEXT = ("per-category outlier frequency over last K=50 scored stories, "
              "fallback global; a base-rate forecast, not foresight")

STORY_SEG_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$")


# ─── paths / time ─────────────────────────────────────────────────────────

def ledger_path() -> Path:
    """Read the env var at call time so tests can point it at tmp_path."""
    return Path(os.getenv("PREREG_LEDGER", DEFAULT_LEDGER_PATH))


def segments_dir() -> Path:
    return Path(os.getenv("SEGMENTS_DIR", DEFAULT_SEGMENTS_DIR))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def filename_ts_to_iso(ts: str) -> str:
    """'20260910_130939' -> '2026-09-10T13:09:39.000000Z' (segment timestamps are UTC)."""
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[9:11]}:{ts[11:13]}:{ts[13:15]}.000000Z"


def _norm_ts(ts) -> str:
    """Normalise ISO-ish UTC stamps to a fixed-width form so string comparison is ordering."""
    s = str(ts or "")
    if not s:
        return ""
    if s.endswith("Z"):
        s = s[:-1]
    if "." not in s:
        s = s + ".000000"
    return s


# ─── canonical helpers (shared by producer, bootstrap, replay, export) ────

def content_hash(responses: dict) -> str:
    """sha256 of the canonical {name: text} map; order-independent over names."""
    canon = {str(k): str(responses[k]) for k in sorted(responses or {})}
    blob = json.dumps(canon, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def actual_outlier(model_vix: dict):
    """The shared outlier rule: highest VIX, ties broken alphabetically by model name."""
    if not model_vix:
        return None
    return sorted(model_vix.items(), key=lambda kv: (-float(kv[1]), str(kv[0])))[0][0]


def actual_margin(model_vix: dict) -> float:
    """Top VIX minus second VIX (0.0 when fewer than two models). Ties show as 0.0."""
    vals = sorted((float(v) for v in (model_vix or {}).values()), reverse=True)
    if len(vals) < 2:
        return 0.0
    return round(vals[0] - vals[1], 3)


def line_id(line: str) -> str:
    """prereg_id of a ledger line: sha256 of the line bytes (without the newline), first 16 hex."""
    return hashlib.sha256(line.rstrip("\n").encode("utf-8")).hexdigest()[:16]


def _dump(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)


# ─── ledger IO ────────────────────────────────────────────────────────────

def append_row(row: dict, path=None) -> str:
    """Append one JSON line with flush+fsync. Returns the line's prereg_id."""
    p = Path(path) if path else ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = _dump(row)
    with open(p, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line_id(line)


def seal_prediction(row: dict, path=None) -> str:
    """Write the kind='predicted' row before any measurement; return its prereg_id."""
    row = dict(row)
    row["kind"] = "predicted"
    row.pop("prereg_id", None)          # the id is the hash of the line itself
    return append_row(row, path)


# kept for callers that used the design's name
append_ledger = append_row


def read_ledger(path=None) -> list:
    """Whole ledger (it is tiny: ~30 rows/day). kind='predicted' rows get their prereg_id attached."""
    p = Path(path) if path else ledger_path()
    rows = []
    if not p.exists():
        return rows
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("kind") == "predicted" and not row.get("prereg_id"):
                row["prereg_id"] = line_id(line)
            rows.append(row)
    return rows


def read_ledger_tail(n: int, path=None) -> list:
    return read_ledger(path)[-int(n):] if n else read_ledger(path)


# ─── the prior ────────────────────────────────────────────────────────────

def _outcome_rows(history_rows, panel, story_guid, now_ts):
    """Rows that carry an outcome usable by the prior, in ledger order."""
    panel_set = set(panel or [])
    now_n = _norm_ts(now_ts) if now_ts else ""
    out = []
    for row in history_rows or []:
        if row.get("kind") not in (None, "scored", "bootstrap"):
            continue                                   # predicted/aired rows carry no outcome
        act = row.get("actual")
        if not act or act not in panel_set:
            continue
        if story_guid and row.get("story_guid") == story_guid:
            continue
        if now_n:
            sa = _norm_ts(row.get("scored_at") or row.get("ts"))
            if not sa or sa >= now_n:
                continue
        out.append(row)
    return out


def predict_outlier(history_rows, category, panel, story_guid, now_ts,
                    K: int = K_PRIOR, min_category: int = MIN_CATEGORY) -> dict:
    """
    Base-rate forecast of the max-VIX model for this story.
    Filter first (panel, guid, time), then take the LAST K rows of the same
    category; if fewer than min_category, the last K rows of any category.
    """
    usable = _outcome_rows(history_rows, panel, story_guid, now_ts)
    cat_rows = [r for r in usable if r.get("category") == category][-K:]
    if len(cat_rows) >= min_category:
        rows, source = cat_rows, f"category:{category}"
    else:
        rows, source = usable[-K:], "global"
    base = {"K": K, "prior_version": PRIOR_VERSION}
    if not rows:
        base.update({"predicted": None, "predicted_flag": None, "prior_source": "none",
                     "n_used": 0, "counts": {}, "prediction_prob": None})
        return base
    counts = Counter(r["actual"] for r in rows)
    global_counts = Counter(r["actual"] for r in usable[-K:])
    predicted = sorted(counts, key=lambda m: (-counts[m], -global_counts.get(m, 0), m))[0]
    flags = Counter(r.get("state_flag") for r in rows if r.get("state_flag"))
    predicted_flag = sorted(flags, key=lambda f: (-flags[f], f))[0] if flags else None
    base.update({
        "predicted": predicted,
        "predicted_flag": predicted_flag,
        "prior_source": source,
        "n_used": len(rows),
        "counts": {m: int(c) for m, c in sorted(counts.items())},
        "prediction_prob": round(counts[predicted] / len(rows), 4),
    })
    return base


# ─── scoring ──────────────────────────────────────────────────────────────

def score(prereg: dict, model_vix: dict, state_flag=None) -> dict:
    """Add the outcome to a prediction dict (does not write). hit is None when nothing was predicted."""
    out = dict(prereg or {})
    act = actual_outlier(model_vix)
    out["actual"] = act
    out["actual_margin"] = actual_margin(model_vix)
    out["hit"] = (act == out.get("predicted")) if (out.get("predicted") and act) else None
    out["state_flag"] = state_flag
    out["flag_hit"] = ((state_flag == out.get("predicted_flag"))
                       if (out.get("predicted_flag") and state_flag) else None)
    out["scored_at"] = utc_now_iso()
    return out


def running_stats(ledger_rows, this_row=None, M: int = M_RUNNING) -> dict:
    """
    Over the last M rows with kind=='scored' AND predicted != null (bootstrap rows
    excluded), including this_row when it is scored and not already in the ledger:
      running_accuracy       hits / n_scored
      majority_base          share of the single most frequent actual outlier in the
                             window (in-sample constant-guesser share)
      chance                 mean of 1/len(panel)
      mean_prediction_prob   mean of counts[pred]/n_used from the sealed rows
                             (calibration control: a calibrated base-rate forecaster
                             has running_accuracy ~= mean_prediction_prob)
      n_unscored             sealed predictions with no scored row (orphans)
    """
    ledger_rows = list(ledger_rows or [])
    sealed = {r.get("prereg_id"): r for r in ledger_rows
              if r.get("kind") == "predicted" and r.get("prereg_id")}
    scored = [r for r in ledger_rows
              if r.get("kind") == "scored" and r.get("predicted") is not None and r.get("actual")]
    scored_ids = {r.get("prereg_id") for r in scored if r.get("prereg_id")}
    if this_row and this_row.get("predicted") is not None and this_row.get("actual"):
        pid = this_row.get("prereg_id")
        if not pid or pid not in scored_ids:
            scored.append(this_row)
            if pid:
                scored_ids.add(pid)
    window = scored[-M:]
    n = len(window)
    n_unscored = sum(1 for pid in sealed if pid not in scored_ids)
    if n == 0:
        return {"running_accuracy": None, "hits": 0, "n_scored": 0, "majority_base": None,
                "chance": None, "mean_prediction_prob": None, "n_unscored": n_unscored,
                "window_M": M}
    hits = sum(1 for r in window if r.get("hit"))
    majority_base = max(Counter(r["actual"] for r in window).values()) / n
    panels = [len(r.get("panel") or []) for r in window if r.get("panel")]
    chance = (sum(1.0 / k for k in panels) / len(panels)) if panels else None
    probs = []
    for r in window:
        src = sealed.get(r.get("prereg_id"), r)
        p = src.get("prediction_prob", r.get("prediction_prob"))
        if p is not None:
            probs.append(float(p))
    mean_prob = (sum(probs) / len(probs)) if probs else None
    return {
        "running_accuracy": round(hits / n, 4),
        "hits": int(hits),
        "n_scored": n,
        "majority_base": round(majority_base, 4),
        "chance": round(chance, 4) if chance is not None else None,
        "mean_prediction_prob": round(mean_prob, 4) if mean_prob is not None else None,
        "n_unscored": n_unscored,
        "window_M": M,
    }


SCORED_FIELDS = ("prereg_id", "story_guid", "story_title", "category", "panel", "predicted",
                 "predicted_flag", "prior_source", "K", "n_used", "prediction_prob",
                 "prior_version", "content_hash", "predicted_at", "actual", "actual_margin",
                 "hit", "flag_hit", "state_flag", "scored_at", "running_accuracy", "hits",
                 "majority_base", "chance", "mean_prediction_prob", "n_scored", "n_unscored")


def scored_row(prereg: dict) -> dict:
    """The kind='scored' ledger row for a scored prediction dict."""
    row = {"kind": "scored", "ts": prereg.get("scored_at") or utc_now_iso()}
    for k in SCORED_FIELDS:
        if k in prereg:
            row[k] = prereg[k]
    return row


# ─── bootstrap from stored segments ───────────────────────────────────────

def segment_to_bootstrap_row(filename: str, seg: dict):
    """Outcome-only row from a stored story segment, or None if it is not a scored story."""
    if not STORY_SEG_RE.match(filename):
        return None
    if not isinstance(seg, dict) or seg.get("segment_type"):
        return None
    attr = seg.get("attribution") or {}
    mv = attr.get("model_vix") or {}
    if not isinstance(mv, dict) or len(mv) < 2:
        return None
    try:
        mv = {str(k): float(v) for k, v in mv.items()}
    except Exception:
        return None
    ts_iso = filename_ts_to_iso(filename[:15])
    return {
        "kind": "bootstrap",
        "ts": ts_iso,
        "story_guid": attr.get("story_guid", ""),
        "story_title": str(attr.get("story_title", ""))[:80],
        "category": attr.get("category", ""),
        "panel": sorted(mv),
        "predicted": None,
        "predicted_flag": None,
        "prior_source": None,
        "actual": actual_outlier(mv),
        "actual_margin": actual_margin(mv),
        "state_flag": attr.get("state_flag"),
        "scored_at": ts_iso,
        "segment_file": filename,
        "prior_version": PRIOR_VERSION,
    }


def bootstrap_rows_from_segments(n: int = 600, seg_dir=None) -> list:
    """
    The newest n scored STORIES (not files: ~a third of story-pattern files are
    probes/arms without model_vix) -> outcome rows in chronological order. Reads only.
    """
    d = Path(seg_dir) if seg_dir else segments_dir()
    if not d.exists():
        return []
    names = sorted(f for f in os.listdir(d) if STORY_SEG_RE.match(f))
    rows = []
    for name in reversed(names):                       # newest first, stop at n stories
        if len(rows) >= int(n):
            break
        try:
            seg = json.loads((d / name).read_text(encoding="utf-8"))
        except Exception:
            continue
        row = segment_to_bootstrap_row(name, seg)
        if row:
            rows.append(row)
    rows.reverse()
    return rows


def bootstrap_ledger_from_segments(n: int = 600, seg_dir=None, path=None, force: bool = False) -> int:
    """
    Write bootstrap rows to the ledger. Runs only when the ledger has no row of
    any kind (never re-runs automatically; force=True overrides). Returns rows written.
    """
    p = Path(path) if path else ledger_path()
    if not force and read_ledger(p):
        return 0
    rows = bootstrap_rows_from_segments(n, seg_dir)
    for row in rows:
        append_row(row, p)
    return len(rows)


# ─── the on-air sentence (deterministic, no LLM) ──────────────────────────

def _pct(x) -> int:
    return int(round(float(x) * 100))


def build_ledger_sentence(prereg: dict) -> str:
    """
    Exact on-air template. Returns "" (silent) unless the row has a prediction,
    an outcome, and n_used >= MIN_CATEGORY.
    """
    p = prereg or {}
    predicted = p.get("predicted")
    actual = p.get("actual")
    n_used = int(p.get("n_used") or 0)
    if not predicted or not actual or n_used < MIN_CATEGORY:
        return ""
    counts = p.get("counts") or {}
    c = int(counts.get(predicted, 0))
    category = str(p.get("category") or "").strip() or "recent"
    if str(p.get("prior_source") or "").startswith("category:"):
        record = f"it was the outlier in {c} of the last {n_used} {category} stories"
    else:
        record = (f"it was the outlier in {c} of the last {n_used} stories of any kind, "
                  f"because it has too few {category} stories")
    verdict = "Hit" if p.get("hit") else "Miss"
    hits = int(p.get("hits") or 0)
    n_scored = int(p.get("n_scored") or 0)
    mb = p.get("majority_base")
    ch = p.get("chance")
    mb_pct = _pct(mb) if mb is not None else 0
    ch_pct = _pct(ch) if ch is not None else 0
    return (f"Prediction check. Before any model text was read or embedded, the ledger forecast "
            f"from base rates that {predicted} would diverge most: {record}. {actual} did. "
            f"{verdict}. Running tally: {hits} of {n_scored} correct. Always guessing the "
            f"commonest model would score {mb_pct} percent; chance is {ch_pct} percent. "
            f"This is a base-rate forecast, not foresight.")


# ─── replay (read-only, CPU) ──────────────────────────────────────────────

def replay(n: int = 800, K: int = K_PRIOR, seg_dir=None, history_extra: int = 200) -> dict:
    """
    Score the prior on the last n stored story segments using only strictly
    earlier stories (by file order) with a different guid. Reads segments only.
    """
    rows = bootstrap_rows_from_segments(n + K + history_extra, seg_dir)
    target = rows[-int(n):]
    start = len(rows) - len(target)
    scored = []
    for i, row in enumerate(target):
        hist = rows[:start + i]
        pred = predict_outlier(hist, row["category"], row["panel"], row["story_guid"], None, K=K)
        if pred["predicted"] is None:
            continue
        scored.append({
            "predicted": pred["predicted"], "actual": row["actual"],
            "hit": pred["predicted"] == row["actual"],
            "prediction_prob": pred["prediction_prob"], "prior_source": pred["prior_source"],
            "panel": row["panel"], "category": row["category"],
            "predicted_flag": pred["predicted_flag"], "state_flag": row.get("state_flag"),
            "actual_margin": row["actual_margin"],
        })
    out = {"n_stories": len(target), "n_scored": len(scored), "K": K,
           "prior_version": PRIOR_VERSION}
    if not scored:
        return out
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    out.update({
        "hits": hits,
        "accuracy": round(hits / n, 4),
        "majority_base": round(max(Counter(s["actual"] for s in scored).values()) / n, 4),
        "chance": round(sum(1.0 / len(s["panel"]) for s in scored) / n, 4),
        "mean_prediction_prob": round(sum(s["prediction_prob"] for s in scored) / n, 4),
        "predicted_distribution": dict(Counter(s["predicted"] for s in scored)),
        "actual_distribution": dict(Counter(s["actual"] for s in scored)),
        "prior_source_distribution": dict(Counter(
            "category" if s["prior_source"].startswith("category:") else s["prior_source"]
            for s in scored)),
        "flag_accuracy": round(sum(1 for s in scored
                                   if s["predicted_flag"] and s["predicted_flag"] == s["state_flag"])
                               / max(1, sum(1 for s in scored if s["predicted_flag"])), 4),
        "near_tie_share_lt_1pt": round(sum(1 for s in scored if s["actual_margin"] < 1.0) / n, 4),
    })
    return out


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "--bootstrap":
        n = int(args[1]) if len(args) > 1 else 600
        written = bootstrap_ledger_from_segments(n)
        print(f"bootstrap: wrote {written} rows to {ledger_path()}"
              + ("" if written else " (ledger already has rows; nothing written)"))
    elif args and args[0] == "--replay":
        n = int(args[1]) if len(args) > 1 else 800
        print(json.dumps(replay(n), indent=2))
    else:
        print(__doc__)
