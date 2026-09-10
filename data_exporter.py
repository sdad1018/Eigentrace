#!/usr/bin/env python3
"""
data_exporter.py — Structured JSON data for eigentrace.ai/data/
=================================================================
Generates machine-readable JSON alongside the markdown ledger.
Researchers hit eigentrace.ai/data/YYYYMMDD.json instead of scraping.

Author: remvelchio
"""

import json, os, logging
from pathlib import Path
from datetime import datetime
from collections import Counter

log = logging.getLogger("data_exporter")

SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR",
    "/home/remvelchio/eigentrace/tmp/segments"))
DOCS_DIR = Path("/mnt/c/Users/M4ISI/eigentrace/docs")


def export_daily_json(date=None):
    """Export full structured data for one day."""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

    segments = []
    weasels = []
    for p in sorted(SEGMENTS_DIR.glob(f"{date}*_segment.json")):
        try:
            seg = json.loads(p.read_text())
            if seg.get("segment_type") == "wild_weasel":
                weasels.append(seg)
            else:
                segments.append(seg)
        except Exception:
            continue

    if not segments:
        return None

    stories = []
    all_voids = []
    all_logos = []

    for seg in segments:
        attr = seg.get("attribution", {})
        if not attr.get("story_title"):
            continue
        if seg.get("segment_type") in ("idle", "silence", "consolidation", "weekly_compression", "governance", "foraging", "self_audit", "roundtable", "pundit_desk", "conversation") or not attr.get("model_vix"):
            continue  # 2026-09-04: the system's own segments are not stories and were inflating the public dataset

        void_words = attr.get("void_words", [])
        logos_words = attr.get("logos_words", [])
        all_voids.extend(void_words)
        all_logos.extend(logos_words)

        # Build story record with ALL available data
        story = {
            "title": attr.get("story_title", ""),
            "url": attr.get("story_url", ""),
            "guid": attr.get("story_guid", ""),
            "category": attr.get("category", ""),
            "timestamp": seg.get("timestamp", ""),

            # Core metrics
            "consensus_density": attr.get("consensus_density", 0),
            "mean_vix": attr.get("mean_vix", 0),
            "state_flag": attr.get("state_flag", ""),

            # Per-model friction
            "model_vix": attr.get("model_vix", {}),

            # Channel 1: Lexical Void (full list, not truncated)
            "void_words": void_words,

            # Channel 2: Logos Synthesis (full list)
            "logos_words": logos_words,

            # Channel 3: SVD Null Space Claims (all of them)
            "null_space_claims": attr.get("null_space_claims", []),

            # Claim extraction
            "claim_killshots": attr.get("claim_killshots", []),

            # Confirmation
            "dual_confirmed": list(set(w.lower() for w in void_words[:10]) &
                                   set(w.lower() for w in logos_words[:10])),

            # Language compression (Layers 13-15)
            "compression": attr.get("compression", {}),
            # 2026-09-10: null-baseline controls (verbatim; docs/metrics.md section 10)
            "controls": attr.get("controls", {}),
            # Source-anchored void
            "source_void": attr.get("source_void", {}),
            # Void context (signal type per word)
            "void_context": attr.get("void_context", []),
            # 2026-09-10: pre-registration ledger (sealed forecast + score for this story)
            "preregistration": attr.get("preregistration", {}),
            # Beat texts (for reconstruction research)
            "beats": [{
                "phase": b.get("phase", ""),
                "speaker": b.get("speaker", ""),
                "text": b.get("text", ""),
            } for b in seg.get("beats", [])],
        }

        # Triple confirmation
        v_set = set(w.lower() for w in void_words[:10])
        l_set = set(w.lower() for w in logos_words[:10])
        dual = v_set & l_set
        ns_set = set()
        for ns in attr.get("null_space_claims", [])[:3]:
            for vw in v_set:
                if vw in ns.get("claim", "").lower():
                    ns_set.add(vw)
        story["triple_confirmed"] = list(dual & ns_set)

        stories.append(story)

    # Weasel probes
    weasel_data = []
    for w in weasels:
        attr = w.get("attribution", {})
        weasel_data.append({
            "story_title": attr.get("story_title", ""),
            "void_words_injected": attr.get("void_words", []),
            "beats": [{
                "phase": b.get("phase", ""),
                "speaker": b.get("speaker", ""),
                "text": b.get("text", ""),
            } for b in w.get("beats", [])],
        })

    # 2026-09-10: error bars -- n and seeded 95% intervals next to every day mean (errorbars.py);
    # the pre-existing keys keep their formulas, an empty day publishes n=0 and null (never 0.0)
    summary = summarize_stories(stories, seed=int(date[:8]), all_voids=all_voids, all_logos=all_logos)
    summary["weasel_probes"] = len(weasel_data)

    output = {
        "version": "eigentrace-data-v1",
        "schema_revision": "1.1",  # 2026-09-10: error-bar fields (see schema_additions); version string pinned by tests/test_controls.py
        "date": date_fmt,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "https://github.com/sdad1018/Eigentrace",
        "license": "MIT",

        "summary": summary,
        "schema_additions": SCHEMA_ADDITIONS,

        "stories": stories,
        "weasel_probes": weasel_data,
    }

    # 2026-09-10: pre-registration ledger — per-story rows and the day's running numbers
    try:
        output["ledger"] = _ledger_rows_from_stories(stories, date_fmt)
        output["summary"]["preregistration"] = _preregistration_summary(stories)
    except Exception as _pe:
        log.warning(f"preregistration export skipped: {_pe}")

    # 2026-09-10: null-baseline controls — day means over the stories that carry them
    try:
        from controls import summarize_controls as _ctl_sum
        output["summary"]["controls"] = _ctl_sum([s.get("controls") for s in stories])
    except Exception as _ce:
        log.warning(f"controls summary skipped: {_ce}")

    # Write to docs/data/
    data_dir = DOCS_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / f"{date}.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    log.info(f"Exported {len(stories)} stories to {out_path}")

    return output


# ─── 2026-09-10: error bars on the day summary (errorbars.py) ────────────

SCHEMA_ADDITIONS = ["summary.n", "summary.n_unique_guid", "summary.mean_density_ci95",
                    "summary.mean_vix_ci95", "summary.per_model_vix", "summary.outlier",
                    "summary.state_rates", "summary.killshots_per_story", "summary.ci_method",
                    "summary.ci_seed"]


def summarize_stories(stories, seed=0, all_voids=None, all_logos=None):
    """
    Pure summary of one day's story records (the dicts export_daily_json builds).
    The pre-existing keys keep their exact formulas (plain means over stories);
    when there are no stories mean_density / mean_vix are null and n is 0.
    Everything else is additive: n, per-model means with a percentile-bootstrap
    95% interval, the bootstrap share with which the day's VIX outlier keeps its
    title, Wilson intervals on the state rates, and the seed used.
    """
    if all_voids is None:
        all_voids = [w for s in stories for w in (s.get("void_words") or [])]
    if all_logos is None:
        all_logos = [w for s in stories for w in (s.get("logos_words") or [])]
    void_freq = Counter(all_voids).most_common(30)
    logos_freq = Counter(all_logos).most_common(30)
    dual_global = set(w for w, _ in void_freq[:20]) & set(w for w, _ in logos_freq[:20])
    n = len(stories)

    summary = {
        "stories_analyzed": n,
        "weasel_probes": 0,
        "mean_density": round(sum(s["consensus_density"] for s in stories) / n, 3) if n else None,
        "mean_vix": round(sum(s["mean_vix"] for s in stories) / n, 1) if n else None,
        "dual_confirmed_global": sorted(dual_global),
        "top_void_words": [{"word": w, "count": c} for w, c in void_freq],
        "top_logos_words": [{"word": w, "count": c} for w, c in logos_freq],
        "n": n,
        "n_unique_guid": len(set(s.get("guid", "") for s in stories)) if n else 0,
    }

    try:
        from errorbars import boot_ci, wilson_ci, argmax_share, per_model_lists
        seed = int(seed)
        d_ci = boot_ci([s["consensus_density"] for s in stories], seed=seed)
        v_ci = boot_ci([s["mean_vix"] for s in stories], seed=seed)
        summary["mean_density_ci95"] = [d_ci["lo"], d_ci["hi"]]
        summary["mean_vix_ci95"] = [v_ci["lo"], v_ci["hi"]]

        per_model = {}
        for s in stories:
            for m, v in (s.get("model_vix") or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    per_model.setdefault(m, []).append(float(v))
        pm = {}
        for m in sorted(per_model):
            c = boot_ci(per_model[m], seed=seed)
            pm[m] = {"mean": round(c["mean"], 1) if c["mean"] is not None else None,
                     "ci95": [c["lo"], c["hi"]], "n": c["n"], "seed": seed}
        summary["per_model_vix"] = pm

        paired, n_paired = per_model_lists([{"attribution": {"model_vix": s.get("model_vix") or {}}} for s in stories])
        share = argmax_share(paired, seed=seed) if n_paired else None
        summary["outlier"] = {
            "model": share["winner"] if share else None,
            "runner_up": share["runner_up"] if share else None,
            "bootstrap_share": share["share"] if share else None,
            "n_paired": n_paired,
            "seed": seed,
        }

        states = [s.get("state_flag", "") for s in stories]
        summary["state_rates"] = {
            flag: wilson_ci(sum(1 for x in states if x == flag), n)
            for flag in ("LOCKSTEP", "CONTESTED", "HIGH_FRICTION")
        }
        k_ci = boot_ci([len(s.get("claim_killshots") or []) for s in stories], seed=seed)
        summary["killshots_per_story"] = {"n": k_ci["n"], "point": k_ci["mean"], "ci95": [k_ci["lo"], k_ci["hi"]], "seed": seed}
        summary["ci_method"] = f"percentile bootstrap, B=2000, seed={seed}, unit=story"
        summary["ci_seed"] = seed
    except Exception as _eb:
        log.warning(f"error bars skipped: {_eb}")
    return summary


# ─── 2026-09-10: pre-registration ledger export ─────────────────────────

def _ledger_rows_from_stories(stories, date_fmt):
    """One row per story that carries a scored (or at least sealed) forecast."""
    rows = []
    for s in stories:
        p = s.get("preregistration") or {}
        if not p or (p.get("predicted") is None and not p.get("actual")):
            continue
        rows.append({
            "date": date_fmt,
            "timestamp": s.get("timestamp", ""),
            "title": s.get("title", ""),
            "category": s.get("category", ""),
            "panel": p.get("panel", []),
            "prereg_id": p.get("prereg_id"),
            "sealed": bool(p.get("sealed")),
            "predicted": p.get("predicted"),
            "predicted_flag": p.get("predicted_flag"),
            "prior_source": p.get("prior_source"),
            "K": p.get("K"),
            "n_used": p.get("n_used"),
            "prediction_prob": p.get("prediction_prob"),
            "predicted_at": p.get("predicted_at"),
            "actual": p.get("actual"),
            "actual_margin": p.get("actual_margin"),
            "hit": p.get("hit"),
            "flag_hit": p.get("flag_hit"),
            "state_flag": p.get("state_flag") or s.get("state_flag", ""),
            "scored_at": p.get("scored_at"),
            "running_accuracy": p.get("running_accuracy"),
            "hits": p.get("hits"),
            "n_scored": p.get("n_scored"),
            "in_sample_constant_guesser_share": p.get("majority_base"),
            "chance": p.get("chance"),
            "mean_prediction_prob": p.get("mean_prediction_prob"),
        })
    return rows


def _preregistration_summary(stories):
    """Running numbers taken from the day's last scored story, plus the day's own tally."""
    scored = [s for s in stories
              if (s.get("preregistration") or {}).get("actual")
              and (s.get("preregistration") or {}).get("predicted") is not None]
    scored.sort(key=lambda s: s.get("timestamp", ""))
    last = (scored[-1].get("preregistration") if scored else None) or {}
    hits_today = sum(1 for s in scored if s["preregistration"].get("hit"))
    try:
        from preregistration import PRIOR_VERSION as _pv, PRIOR_TEXT as _pt
    except Exception:
        _pv, _pt = "outlier-freq-v1", ""
    return {
        "stories_scored_today": len(scored),
        "hits_today": hits_today,
        "n_scored": last.get("n_scored"),
        "hits": last.get("hits"),
        "running_accuracy": last.get("running_accuracy"),
        "in_sample_constant_guesser_share": last.get("majority_base"),
        "chance": last.get("chance"),
        "mean_prediction_prob": last.get("mean_prediction_prob"),
        "n_unscored": last.get("n_unscored"),
        "prior_version": last.get("prior_version", _pv),
        "prior": _pt,
        "note": ("running numbers are over the last 100 scored stories as of the day's last story; "
                 "the forecast is a base rate, and running_accuracy ~= in_sample_constant_guesser_share "
                 "is the expected result, not a failure"),
    }


def export_preregistration_series(ledger_path=None, docs_dir=None):
    """
    Read the whole ledger (one small file, env PREREG_LEDGER) and write
    docs/data/preregistration_ledger.json: every sealed forecast joined to its
    scored row (by prereg_id) and to the segment file that aired it.
    """
    import preregistration as pr
    rows = pr.read_ledger(ledger_path)
    scored_by_id = {r.get("prereg_id"): r for r in rows if r.get("kind") == "scored" and r.get("prereg_id")}
    aired_by_id = {r.get("prereg_id"): r for r in rows if r.get("kind") == "aired" and r.get("prereg_id")}
    out_rows = []
    for r in rows:
        if r.get("kind") != "predicted" or r.get("predicted") is None:
            continue
        pid = r.get("prereg_id")
        s = scored_by_id.get(pid) or {}
        a = aired_by_id.get(pid) or {}
        out_rows.append({
            "prereg_id": pid,
            "predicted_at": r.get("predicted_at"),
            "story_guid": r.get("story_guid"),
            "story_title": r.get("story_title"),
            "category": r.get("category"),
            "panel": r.get("panel"),
            "predicted": r.get("predicted"),
            "predicted_flag": r.get("predicted_flag"),
            "prior_source": r.get("prior_source"),
            "K": r.get("K"),
            "n_used": r.get("n_used"),
            "counts": r.get("counts"),
            "prediction_prob": r.get("prediction_prob"),
            "content_hash": r.get("content_hash"),
            "scored": bool(s),
            "scored_at": s.get("scored_at"),
            "actual": s.get("actual"),
            "actual_margin": s.get("actual_margin"),
            "hit": s.get("hit"),
            "flag_hit": s.get("flag_hit"),
            "state_flag": s.get("state_flag"),
            "running_accuracy": s.get("running_accuracy"),
            "hits": s.get("hits"),
            "n_scored": s.get("n_scored"),
            "in_sample_constant_guesser_share": s.get("majority_base"),
            "chance": s.get("chance"),
            "mean_prediction_prob": s.get("mean_prediction_prob"),
            "aired_segment_file": a.get("segment_file"),
        })
    n_scored_rows = sum(1 for r in out_rows if r["scored"])
    n_hits = sum(1 for r in out_rows if r["hit"])
    output = {
        "version": "eigentrace-prereg-v1",
        "prior": pr.PRIOR_TEXT,
        "prior_version": pr.PRIOR_VERSION,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "seal": ("each row's prereg_id is sha256 of the kind='predicted' ledger line, written with fsync "
                 "before stage 3 measured anything; predicted_at < scored_at is the ordering claim"),
        "fields": {
            "in_sample_constant_guesser_share": "share of the most frequent actual outlier in the same "
                                                "running window (majority_base in the ledger)",
            "mean_prediction_prob": "mean of counts[predicted]/n_used over the window; a calibrated "
                                    "base-rate forecaster has running_accuracy close to this",
            "chance": "mean of 1/len(panel) over the window",
            "actual_margin": "top VIX minus second VIX; 0.0 marks an exact tie (broken alphabetically)",
        },
        "n_rows": len(out_rows),
        "n_scored": n_scored_rows,
        "n_hits": n_hits,
        "accuracy_all_time": round(n_hits / n_scored_rows, 4) if n_scored_rows else None,
        "rows": out_rows,
    }
    data_dir = Path(docs_dir) / "data" if docs_dir else DOCS_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "preregistration_ledger.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    log.info(f"Exported {len(out_rows)} pre-registration rows to {out_path}")
    return output


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    date = sys.argv[1] if len(sys.argv) > 1 else None
    result = export_daily_json(date)
    if result:
        print(f"Exported: {result['summary']['stories_analyzed']} stories, "
              f"{result['summary']['weasel_probes']} probes")
    else:
        print("No data found")
    # 2026-09-10: full pre-registration series (one small file; a failure never blocks the daily export)
    try:
        _series = export_preregistration_series()
        print(f"Exported: {_series['n_rows']} pre-registration rows ({_series['n_scored']} scored)")
    except Exception as _pe:
        print(f"preregistration series export failed: {_pe}")
