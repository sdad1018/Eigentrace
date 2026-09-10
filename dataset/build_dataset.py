#!/usr/bin/env python3
"""Build the EigenTrace measurements dataset (v1) from stored story segments.

One row per story. Model outputs and measurements are kept; the article text
(``source_body``) and the source n-grams (``absent_phrases``) are never written.

Inputs  : story segments matching ^[0-9]{8}_[0-9]{6}_[0-9a-f]{12}_segment\\.json$
          (default /home/remvelchio/eigentrace/tmp/segments). Files with a
          ``segment_type`` (arm segments) and files that fail to parse are skipped.
Outputs : stories.jsonl, measurements.csv, models_long.csv, MANIFEST.json in
          --out (default /home/remvelchio/eigentrace/dataset/eigentrace-measurements-v1).

Ordering is deterministic (rows sorted by id). Standard library only; no
embedding, no GPU, no network. Definitions of every measurement are in
docs/metrics.md; definition changes are dated in CHANGELOG.md.

Usage:
    python3 dataset/build_dataset.py [--segments DIR] [--out DIR]
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

DATASET_NAME = "eigentrace-measurements-v1"
DATASET_VERSION = "1.0.0"
MODELS = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]
SEGMENT_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{12}_segment\.json$")
DEFAULT_SEGMENTS = "/home/remvelchio/eigentrace/tmp/segments"
DEFAULT_OUT = "/home/remvelchio/eigentrace/dataset/" + DATASET_NAME
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

# Keys that must never reach the output (publisher text or derived n-grams of it).
FORBIDDEN_KEYS = {"source_body", "absent_phrases", "source_verbs", "details"}


# ----------------------------------------------------------------------------- helpers
def _num(x):
    """Return x if it is a finite int/float (not bool), else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def _str(x):
    return x if isinstance(x, str) and x != "" else None


def _list_of_str(x):
    if not isinstance(x, list):
        return None
    return [s for s in x if isinstance(s, str)]


def _words(text):
    return len(text.split()) if isinstance(text, str) else None


def stamp_to_iso(stem):
    """'20260701_211841_...' -> ('2026-07-01', '2026-07-01T21:18:41Z')."""
    d, t = stem[:8], stem[9:15]
    date = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    return date, "%sT%s:%s:%sZ" % (date, t[:2], t[2:4], t[4:6])


def git_commit(repo):
    try:
        out = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=30)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def changelog_date(repo):
    """Most recent ISO date mentioned in CHANGELOG.md, or None if the file is absent."""
    path = os.path.join(repo, "CHANGELOG.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        dates = re.findall(r"\b(20[0-9]{2}-[01][0-9]-[0-3][0-9])\b", f.read())
    return max(dates) if dates else None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- row builders
def build_killshots(attr):
    """claim_killshots as stored carry claim/salience/omitted_by; the per-model coverage is
    stripped before the segment is written. null_space_claims (same extractor, same story)
    keep coverage_ratio, so coverage is recovered by exact claim-text match when possible."""
    ks = attr.get("claim_killshots")
    if not isinstance(ks, list):
        return None
    cov = {}
    for c in attr.get("null_space_claims") or []:
        if isinstance(c, dict) and isinstance(c.get("claim"), str):
            cov[c["claim"]] = _num(c.get("coverage_ratio"))
    out = []
    for k in ks:
        if not isinstance(k, dict):
            continue
        claim = _str(k.get("claim"))
        out.append({
            "claim": claim,
            "salience": _num(k.get("salience")),
            "coverage": _num(k.get("coverage_ratio")) if "coverage_ratio" in k else cov.get(claim),
            "omitted_by": _list_of_str(k.get("omitted_by")) or [],
        })
    return out


def build_compression(attr):
    c = attr.get("compression")
    if not isinstance(c, dict):
        return None
    ab = c.get("attribution_buffer") if isinstance(c.get("attribution_buffer"), dict) else {}
    return {
        "verb_downgrade": _num(c.get("verb_downgrade")),
        "entity_retention": _num(c.get("entity_retention")),
        "entity_abstraction_rate": _num(c.get("entity_abstraction_rate")),
        "compression_score": _num(c.get("compression_score")),
        "hedge_total": _num(ab.get("total")),
        "hedge_epistemic": _num(ab.get("epistemic")),
        "hedge_attribution": _num(ab.get("attribution")),
        "hedge_distancing": _num(ab.get("distancing")),
        "hedge_avg_per_model": _num(ab.get("avg_per_model")),
    }


def build_void_context(attr):
    vc = attr.get("void_context")
    if not isinstance(vc, list):
        return None
    out = []
    for e in vc:
        if isinstance(e, dict):
            out.append({
                "word": _str(e.get("word")),
                "source_present": e.get("source_present") if isinstance(e.get("source_present"), bool) else None,
                "global_freq_pct": _num(e.get("global_freq_pct")),
                "category_freq_pct": _num(e.get("category_freq_pct")),
                "signal_type": _str(e.get("signal_type")),
            })
        elif isinstance(e, str):
            out.append({"word": e, "source_present": None, "global_freq_pct": None,
                        "category_freq_pct": None, "signal_type": None})
    return out


def build_sp_channels(attr):
    sp = attr.get("sp_channels")
    if not isinstance(sp, dict):
        return None
    return {k: _list_of_str(sp.get(k)) for k in ("flat", "spiral", "void")}


def build_eigenching(attr):
    e = attr.get("eigenching")
    if not isinstance(e, dict):
        return None
    sig = e.get("signature")
    return {
        "signature": [_num(x) for x in sig] if isinstance(sig, list) else None,
        "axes": _list_of_str(e.get("axes")),
        "name": _str(e.get("name")),
        "closed_score": _num(e.get("closed_score")),
    }


def build_row(stem, seg):
    attr = seg.get("attribution") or {}
    date, ts = stamp_to_iso(stem)
    mr = attr.get("model_responses") if isinstance(attr.get("model_responses"), dict) else {}
    mv = attr.get("model_vix") if isinstance(attr.get("model_vix"), dict) else {}
    sp = attr.get("summary_plus") if isinstance(attr.get("summary_plus"), dict) else {}
    sv = attr.get("source_void") if isinstance(attr.get("source_void"), dict) else {}
    models = {}
    for m in MODELS:
        models[m] = {
            "response": _str(mr.get(m)),
            "vix": _num(mv.get(m)),
            "summary_plus": _str(sp.get(m)),
        }
    n_models = sum(1 for m in MODELS if models[m]["response"] is not None or models[m]["vix"] is not None)
    row = {
        "id": stem,
        "segment_id": _str(seg.get("id")),
        "date_utc": date,
        "timestamp_utc": ts,
        "title": _str(attr.get("story_title")),
        "url": _str(attr.get("story_url")),
        "guid": _str(attr.get("story_guid")),
        "category": _str(attr.get("category")),
        "blurb": None,  # the RSS summary is not stored as its own field (see README)
        "n_models": n_models,
        "models": models,
        "mean_vix": _num(attr.get("mean_vix")),
        "consensus_density": _num(attr.get("consensus_density")),
        "state_flag": _str(attr.get("state_flag")),
        "absent_ratio": _num(sv.get("absent_ratio")),
        "absent_count": _num(sv.get("absent_count")),
        "source_word_count": _num(sv.get("source_word_count")),
        "absent_words": _list_of_str(sv.get("absent_words")),
        "void_words": _list_of_str(attr.get("void_words")),
        "void_context": build_void_context(attr),
        "logos_words": _list_of_str(attr.get("logos_words")),
        "synthesis_words": _list_of_str(attr.get("synthesis_words")),
        "sp_channels": build_sp_channels(attr),
        "claim_killshots": build_killshots(attr),
        "compression": build_compression(attr),
        "eigenching": build_eigenching(attr),
    }
    return row


def assert_clean(obj):
    """Fail loudly if a forbidden key slipped into an output row."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                raise RuntimeError("forbidden key in output: %s" % k)
            assert_clean(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_clean(v)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", default=DEFAULT_SEGMENTS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    names = sorted(n for n in os.listdir(args.segments) if SEGMENT_RE.match(n))
    counts = {"files_matched": len(names), "skipped_arm": 0, "skipped_parse_error": 0,
              "skipped_no_attribution": 0, "rows": 0}
    rows = []
    for n in names:
        path = os.path.join(args.segments, n)
        try:
            with open(path, encoding="utf-8") as f:
                seg = json.load(f)
        except Exception:
            counts["skipped_parse_error"] += 1
            continue
        if not isinstance(seg, dict):
            counts["skipped_parse_error"] += 1
            continue
        if seg.get("segment_type"):
            counts["skipped_arm"] += 1
            continue
        attr = seg.get("attribution")
        if not isinstance(attr, dict) or not attr.get("story_title"):
            counts["skipped_no_attribution"] += 1
            continue
        rows.append(build_row(n[:-len(".json")], seg))
    rows.sort(key=lambda r: r["id"])
    counts["rows"] = len(rows)
    for r in rows:
        assert_clean(r)

    os.makedirs(args.out, exist_ok=True)
    p_jsonl = os.path.join(args.out, "stories.jsonl")
    p_meas = os.path.join(args.out, "measurements.csv")
    p_long = os.path.join(args.out, "models_long.csv")
    p_man = os.path.join(args.out, "MANIFEST.json")

    with open(p_jsonl, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")

    meas_cols = ["id", "date_utc", "n_models"] + ["vix_%s" % m.lower() for m in MODELS] + [
        "mean_vix", "consensus_density", "absent_ratio", "absent_count", "source_word_count",
        "n_absent_words", "n_void_words", "n_logos_words", "n_killshots", "killshot_max_salience",
        "killshot_min_coverage", "verb_downgrade", "entity_retention", "entity_abstraction_rate",
        "compression_score", "hedge_total", "hedge_avg_per_model", "has_summary_plus", "has_eigenching"]
    with open(p_meas, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(meas_cols)
        for r in rows:
            c = r["compression"] or {}
            ks = r["claim_killshots"] or []
            sal = [k["salience"] for k in ks if k["salience"] is not None]
            cov = [k["coverage"] for k in ks if k["coverage"] is not None]
            vals = [r["id"], r["date_utc"], r["n_models"]] + [r["models"][m]["vix"] for m in MODELS] + [
                r["mean_vix"], r["consensus_density"], r["absent_ratio"], r["absent_count"], r["source_word_count"],
                len(r["absent_words"]) if r["absent_words"] is not None else None,
                len(r["void_words"]) if r["void_words"] is not None else None,
                len(r["logos_words"]) if r["logos_words"] is not None else None,
                len(ks) if r["claim_killshots"] is not None else None,
                max(sal) if sal else None,
                min(cov) if cov else None,
                c.get("verb_downgrade"), c.get("entity_retention"), c.get("entity_abstraction_rate"),
                c.get("compression_score"), c.get("hedge_total"), c.get("hedge_avg_per_model"),
                int(any(r["models"][m]["summary_plus"] is not None for m in MODELS)),
                int(r["eigenching"] is not None)]
            w.writerow(["" if v is None else v for v in vals])

    long_cols = ["id", "date_utc", "model", "vix", "response_chars", "response_words",
                 "summary_plus_chars", "summary_plus_words"]
    n_long = 0
    with open(p_long, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(long_cols)
        for r in rows:
            for m in MODELS:
                mm = r["models"][m]
                if mm["response"] is None and mm["vix"] is None:
                    continue
                resp, spl = mm["response"], mm["summary_plus"]
                vals = [r["id"], r["date_utc"], m, mm["vix"],
                        len(resp) if resp is not None else None, _words(resp),
                        len(spl) if spl is not None else None, _words(spl)]
                w.writerow(["" if v is None else v for v in vals])
                n_long += 1

    def present(key):
        return sum(1 for r in rows if r[key] is not None)

    manifest = {
        "dataset": DATASET_NAME,
        "version": DATASET_VERSION,
        "build_time_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "dataset/build_dataset.py",
        "git_commit": git_commit(REPO_ROOT),
        "definitions_version": changelog_date(REPO_ROOT),
        "definitions_doc": "docs/metrics.md",
        "segments_dir": args.segments,
        "counts": counts,
        "date_range_utc": {"first": rows[0]["date_utc"] if rows else None,
                           "last": rows[-1]["date_utc"] if rows else None},
        "models": MODELS,
        "rows_models_long": n_long,
        "stories_with": {
            "five_model_panel": sum(1 for r in rows if r["n_models"] == 5),
            "model_responses": sum(1 for r in rows if any(r["models"][m]["response"] for m in MODELS)),
            "model_vix": sum(1 for r in rows if any(r["models"][m]["vix"] is not None for m in MODELS)),
            "summary_plus": sum(1 for r in rows if any(r["models"][m]["summary_plus"] for m in MODELS)),
            "consensus_density": present("consensus_density"),
            "absent_ratio": present("absent_ratio"),
            "void_context": present("void_context"),
            "logos_words": present("logos_words"),
            "sp_channels": present("sp_channels"),
            "claim_killshots": present("claim_killshots"),
            "claim_killshots_nonempty": sum(1 for r in rows if r["claim_killshots"]),
            "compression": present("compression"),
            "eigenching": present("eigenching"),
        },
        "excluded": ["source_body (publisher article text)", "absent_phrases (n-grams of the article text)",
                     "compression.details (per-model verb lists drawn from the article text)",
                     "blurb is null: the RSS summary is not stored as a separate field"],
        "files": {},
    }
    for p, nrows in ((p_jsonl, len(rows)), (p_meas, len(rows)), (p_long, n_long)):
        manifest["files"][os.path.basename(p)] = {"bytes": os.path.getsize(p), "sha256": sha256_of(p), "rows": nrows}
    with open(p_man, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({"out": args.out, "counts": counts, "date_range": manifest["date_range_utc"],
                      "rows_models_long": n_long, "stories_with": manifest["stories_with"],
                      "files": {k: v["bytes"] for k, v in manifest["files"].items()},
                      "git_commit": manifest["git_commit"],
                      "definitions_version": manifest["definitions_version"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
