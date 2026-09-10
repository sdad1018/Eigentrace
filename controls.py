#!/usr/bin/env python3
"""
controls.py — null-baseline controls for the five live probes (2026-09-10)

Each control is the production function called once more on a swapped input.
Nothing about the measurement itself changes: no threshold, label, word list,
killshot selection or score is touched; a second number is stored beside the
first so the audience and the site can see what the instrument reads when the
input is unrelated to the story.

    probe        measured (production)                        control (same function, swapped input)
    void         batch_producer._compute_void(own headline)   _compute_void(control story's headline, same responses)
    source_void  eigentrace_math.source_anchored_void(own     source_anchored_void(control article, same responses)
                 article, own responses)
    killshots    claim_extractor.score_claim_coverage(own     score_claim_coverage(own killshot claims, control panel)
                 claims, own panel)
    density      GeometricPerturbationEngine.                 compute_consensus_density(own response 0 + one response
                 compute_consensus_density(own panel)         from each of up to N-1 other stories)
    compression  eigentrace_math.score_language_compression   score_language_compression(own source, control panel)
                 (own source, own panel)

Rules (from the 2026-09-10 design critique):
  * deterministic — no random draws anywhere in production; the control story
    and its guid, selection method and source length are stored with the number;
  * no LLM calls, no engine or vocabulary loading here — the engine and the
    VocabTensor are passed in from stage 3 of batch_producer.py;
  * control panels never contain the story's own guid and never contain a
    response that starts with "[" (the producer's failure strings);
  * every probe is wrapped: a failure yields {"error": ...} for that probe only,
    and compute_controls never raises into the producer;
  * on-air text is built only by control_sentence(); a missing or failed probe
    yields "" so no Control sentence is ever added for it.

Stored record (attribution.controls, version 1) — see docs/metrics.md section 10.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import numpy as np

log = logging.getLogger("controls")

VERSION = 1
SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR", "/home/remvelchio/eigentrace/tmp/segments"))
STORY_SEG_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$")
DISK_SCAN_LIMIT = 20          # newest story segments examined for a disk fallback
SOURCE_VOID_BODY_CHARS = 1500  # stage-3 source_void reads body[:1500]
COMPRESSION_BODY_CHARS = 1000  # stage-3 compression reads body[:1000]
VOID_POOL_SIZE = 200           # _compute_void(pool_size=200, k=5) at its stage-3 call site
VOID_K = 5
MAX_KILLSHOTS = 3              # attribution stores claim_killshots[:3]

_NUM_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


# ── helpers ────────────────────────────────────────────────────────────

def _usable_text(t) -> bool:
    """Non-empty string that is not one of the producer's failure strings ("[Mistral unavailable ...")."""
    return isinstance(t, str) and bool(t.strip()) and not t.lstrip().startswith("[")


def _active_pairs(res) -> list:
    """(name, text) for the usable responses of an in-batch result dict (same test as stage 3)."""
    out = []
    for resp in (res or {}).get("responses") or []:
        if getattr(resp, "skipped", False) or getattr(resp, "error", None):
            continue
        text = getattr(resp, "text", "") or ""
        if _usable_text(text):
            out.append((str(getattr(resp, "name", "") or ""), text))
    return out


def _story_guid(res) -> str:
    return str(getattr((res or {}).get("story"), "guid", "") or "")


def source_text_void(story) -> str:
    """title + ". " + summary + " " + body[:1500] — the exact stage-3 source_void expression."""
    s = str(getattr(story, "title", "") or "") + ". " + str(getattr(story, "summary", "") or "")
    body = getattr(story, "body", "") or ""
    if body:
        s += " " + body[:SOURCE_VOID_BODY_CHARS]
    return s


def source_text_compression(story) -> str:
    """title + ". " + summary + " " + body[:1000] — the exact stage-3 compression expression."""
    s = str(getattr(story, "title", "") or "") + ". " + str(getattr(story, "summary", "") or "")
    body = getattr(story, "body", "") or ""
    if body:
        s += " " + body[:COMPRESSION_BODY_CHARS]
    return s


def iter_disk_segments(segments_dir=None, limit: int = DISK_SCAN_LIMIT):
    """Yield (file_name, attribution) for the newest story segments on disk.

    Scans at most `limit` files (name-descending, regex-matched); never lists
    the whole directory into memory beyond the names.
    """
    d = Path(segments_dir) if segments_dir is not None else SEGMENTS_DIR
    try:
        names = [e.name for e in os.scandir(d) if e.is_file() and STORY_SEG_RE.match(e.name)]
    except Exception:
        return
    names.sort(reverse=True)
    for name in names[:max(int(limit), 0)]:
        try:
            seg = json.loads((d / name).read_text())
        except Exception:
            continue
        attr = (seg or {}).get("attribution") or {}
        if not isinstance(attr, dict) or not attr.get("model_vix"):
            continue
        yield name, attr


def _disk_responses(attr) -> dict:
    return {str(k): v for k, v in (attr.get("model_responses") or {}).items() if _usable_text(v)}


# ── control selection ──────────────────────────────────────────────────

def pick_control_story(results, idx, segments_dir=None):
    """The unrelated story used for the void, source_void, killshot and compression controls.

    Batch mate first (results[j], j != idx, a different guid, >= 2 usable
    responses); else the newest story segment on disk with a different guid,
    >= 2 usable model_responses and a source_body. Returns None when nothing is
    usable. Deterministic; the method and guid are stored with every number.
    """
    results = results or []
    own_guid = _story_guid(results[idx]) if 0 <= idx < len(results) else ""
    for j, res in enumerate(results):
        if j == idx:
            continue
        guid = _story_guid(res)
        if not guid or guid == own_guid:
            continue
        pairs = _active_pairs(res)
        if len(pairs) < 2:
            continue
        st = res["story"]
        return {
            "guid": guid,
            "title": str(getattr(st, "title", "") or ""),
            "source_text": source_text_void(st),
            "responses": dict(pairs),
            "method": "batch_mate",
        }
    for name, attr in iter_disk_segments(segments_dir):
        guid = str(attr.get("story_guid") or "")
        if not guid or guid == own_guid:
            continue
        responses = _disk_responses(attr)
        source_body = attr.get("source_body") or ""
        if len(responses) < 2 or not source_body:
            continue
        return {
            "guid": guid,
            "title": str(attr.get("story_title") or ""),
            "source_text": str(source_body),
            "responses": responses,
            "method": "disk_segment",
            "segment_file": name,
        }
    return None


def pick_control_panel(results, idx, n, segments_dir=None) -> list:
    """Up to n-1 responses, one from each distinct other story, for the mixed-panel density control.

    Batch mates first, then the newest story segments on disk; a story is used
    once, the own guid never. Within a story the k-th panel member takes that
    story's usable text number k mod len (the replay's rotation), so the mixed
    panel draws on different models.
    """
    results = results or []
    own_guid = _story_guid(results[idx]) if 0 <= idx < len(results) else ""
    used = {own_guid}
    need = max(int(n) - 1, 0)
    out = []
    for j, res in enumerate(results):
        if len(out) >= need:
            break
        if j == idx:
            continue
        guid = _story_guid(res)
        if not guid or guid in used:
            continue
        pairs = _active_pairs(res)
        if not pairs:
            continue
        name, text = pairs[len(out) % len(pairs)]
        used.add(guid)
        out.append({"guid": guid, "name": name, "text": text, "method": "batch_mate"})
    if len(out) < need:
        for fname, attr in iter_disk_segments(segments_dir):
            if len(out) >= need:
                break
            guid = str(attr.get("story_guid") or "")
            if not guid or guid in used:
                continue
            items = list(_disk_responses(attr).items())
            if not items:
                continue
            name, text = items[len(out) % len(items)]
            used.add(guid)
            out.append({"guid": guid, "name": name, "text": text, "method": "disk_segment",
                        "segment_file": fname})
    return out


# ── the five controls ──────────────────────────────────────────────────

def control_void(r, ctrl, active_texts, eng, vt, void_fn=None) -> dict:
    """Same _compute_void, control story's headline against the OWN responses."""
    st = r.get("void_stats") or {}
    if not st or not st.get("pool_n"):
        raise ValueError("no void_stats on the result (stats out-param not populated)")
    if vt is None:
        raise ValueError("no vocab tensor")
    if void_fn is None:
        from batch_producer import _compute_void as void_fn  # already imported in production
    cs = {}
    void_fn(ctrl["title"], list(active_texts), eng, vt, pool_size=VOID_POOL_SIZE, k=VOID_K, stats=cs)
    pool_n = int(st.get("pool_n") or 0)
    absent_n = int(st.get("absent_n") or 0)
    c_pool_n = int(cs.get("pool_n") or 0)
    c_absent_n = int(cs.get("absent_n") or 0)
    return {
        "pool_n": pool_n,
        "absent_n": absent_n,
        "absent_frac": round(absent_n / max(pool_n, 1), 4),
        "control_pool_n": c_pool_n,
        "control_absent_n": c_absent_n,
        "control_absent_frac": round(c_absent_n / max(c_pool_n, 1), 4),
        "control_title": ctrl["title"],
        "control_guid": ctrl["guid"],
        "method": ctrl["method"],
        "control": "unrelated_headline_pool_same_responses",
    }


def control_source_void(r, ctrl, active_texts, story) -> dict:
    """Same source_anchored_void, the control article's words against the OWN responses."""
    from eigentrace_math import source_anchored_void
    own_src = source_text_void(story)
    if ctrl["method"] == "batch_mate":
        c_src = ctrl["source_text"]                 # built by the identical expression
    else:
        c_src = ctrl["source_text"][:len(own_src)]  # stored source_body cut to the own length
    sa = source_anchored_void(c_src, list(active_texts), title=ctrl["title"])
    sv = r.get("source_void") or {}
    return {
        "absent_ratio": sv.get("absent_ratio"),
        "absent_count": sv.get("absent_count"),
        "source_word_count": sv.get("source_word_count"),
        "control_absent_ratio": sa["absent_ratio"],
        "control_absent_count": sa["absent_count"],
        "control_source_word_count": sa["source_word_count"],
        "method": ctrl["method"],
        "control_source_chars": len(c_src),
        "own_source_chars": len(own_src),
        "control_guid": ctrl["guid"],
        "control_title": ctrl["title"],
        "control": "other_article_words_same_responses",
    }


def control_killshots(r, ctrl, eng, story) -> dict:
    """Same score_claim_coverage, the stored killshot claims against the control story's panel.

    Computed after the stage-3 null-space block, on r["claim_killshots"] as
    stored (top 3). max_sim_own comes from the production coverage dict of each
    killshot and is also written onto the killshot entry (additive field).
    """
    from claim_extractor import score_claim_coverage
    ks = list(r.get("claim_killshots") or [])[:MAX_KILLSHOTS]
    base = {
        "n_claims": len(ks),
        "per_claim": [],
        "mean_max_sim_own": None,
        "mean_max_sim_control": None,
        "control_guid": ctrl["guid"],
        "method": ctrl["method"],
        "control_n_responses": len(ctrl["responses"]),
        "control": "own_killshot_claims_vs_other_story_panel",
    }
    if not ks:
        return base
    claims = [str(k.get("claim") or "") for k in ks]
    cross = score_claim_coverage(claims, dict(ctrl["responses"]), eng,
                                 str(getattr(story, "title", "") or ""))
    per = []
    for k, cr in zip(ks, cross):
        cov = k.get("coverage") or {}
        own = round(float(max(cov.values())), 3) if cov else k.get("max_sim_own")
        if own is not None and "max_sim_own" not in k:
            try:
                k["max_sim_own"] = own
            except Exception:
                pass
        ccov = cr.get("coverage") or {}
        per.append({
            "claim": k.get("claim"),
            "max_sim_own": own,
            "max_sim_control": round(float(max(ccov.values())), 3) if ccov else None,
            "n_omitted_control": len(cr.get("omitted_by") or []),
            "coverage_ratio_control": cr.get("coverage_ratio"),
        })
    owns = [p["max_sim_own"] for p in per if p["max_sim_own"] is not None]
    ctrls = [p["max_sim_control"] for p in per if p["max_sim_control"] is not None]
    base.update({
        "per_claim": per,
        "mean_max_sim_own": round(float(np.mean(owns)), 3) if owns else None,
        "mean_max_sim_control": round(float(np.mean(ctrls)), 3) if ctrls else None,
    })
    return base


def control_density(r, results, idx, eng, active_texts, embeddings=None,
                    panel_vix=None, segments_dir=None) -> dict:
    """Same compute_consensus_density on a mixed panel: own response 0 + one response per other story.

    Mean VIX of the mixed panel uses the producer's _panel_vix when passed (the
    same loop as the measured values); otherwise the density identity
    500*(1-sqrt((1+(n-1)d)/n)) (docs/metrics.md section 1), flagged in vix_method.
    """
    active_texts = list(active_texts)
    n = len(active_texts)
    geo = r.get("geo")
    if geo is not None and getattr(geo, "consensus_density", None) is not None:
        measured = float(geo.consensus_density)
    else:
        if embeddings is None:
            embeddings = eng.embed_texts(active_texts)
        measured = float(eng.compute_consensus_density(np.asarray(embeddings)))
    vix_vals = []
    for resp in (r.get("responses") or []):
        if getattr(resp, "skipped", False) or getattr(resp, "error", None) or not getattr(resp, "text", ""):
            continue
        v = getattr(resp, "eigen_vix", None)
        if v is not None:
            vix_vals.append(float(v))
    measured_vix = (sum(vix_vals) / len(vix_vals)) if vix_vals else None
    panel = pick_control_panel(results, idx, n, segments_dir)
    out = {
        "measured": measured,
        "measured_mean_vix": measured_vix,
        "n_own": n,
        "n_panel": 1 + len(panel),
        "control_mixed": None,
        "control_mean_vix": None,
        "control_guids": [p["guid"] for p in panel],
        "control_methods": [p["method"] for p in panel],
        "control_models": [p["name"] for p in panel],
        "control": "mixed_panel_one_response_per_story",
    }
    if len(panel) < 2:
        out["note"] = "fewer than 2 distinct other stories available; no control"
        return out
    if embeddings is None:
        own0 = eng.embed_texts([active_texts[0]])
    else:
        own0 = np.asarray(embeddings)[0:1]
    ctrl_emb = np.asarray(eng.embed_texts([p["text"] for p in panel]))
    mixed = np.vstack([np.asarray(own0, dtype=ctrl_emb.dtype), ctrl_emb])
    d = float(eng.compute_consensus_density(mixed))
    out["control_mixed"] = round(d, 4)
    k = mixed.shape[0]
    if panel_vix is not None:
        out["control_mean_vix"] = round(float(np.mean(panel_vix(mixed))), 2)
        out["vix_method"] = "_panel_vix"
    else:
        out["control_mean_vix"] = round(500.0 * (1.0 - float(np.sqrt(max((1.0 + (k - 1) * d) / k, 0.0)))), 2)
        out["vix_method"] = "identity"
    return out


def control_compression(r, ctrl, story) -> dict:
    """Same score_language_compression, the OWN source against the control story's panel.

    Optional blurb control (RSS summary scored against title + body[:1000])
    only when the summary is non-empty, longer than 60 characters, the body is
    present and does not begin with the summary (otherwise the blurb is an
    extract of the body and its hedge count is 0 by construction).
    """
    from eigentrace_math import score_language_compression
    own_src = source_text_compression(story)
    texts = [t for t in ctrl["responses"].values() if _usable_text(t)]
    cc = score_language_compression(own_src, texts)
    comp = r.get("compression") or {}
    ab = comp.get("attribution_buffer") or {}
    out = {
        "hedges_total": ab.get("total"),
        "hedges_total_control": cc["attribution_buffer"]["total"],
        "entity_retention": comp.get("entity_retention"),
        "entity_retention_control": cc["entity_retention"],
        "verb_downgrade": comp.get("verb_downgrade"),
        "verb_downgrade_control": cc["verb_downgrade"],
        "n_control_responses": len(texts),
        "control_guid": ctrl["guid"],
        "method": ctrl["method"],
        "control": "other_story_panel_same_source",
        "blurb": None,
    }
    title = str(getattr(story, "title", "") or "")
    summary = str(getattr(story, "summary", "") or "")
    body = str(getattr(story, "body", "") or "")
    if (summary.strip() and len(summary) > 60 and body
            and not body.lower().startswith(summary.lower()[:80])):
        cb = score_language_compression(title + ". " + body[:COMPRESSION_BODY_CHARS], [summary])
        out["blurb"] = {
            "entity_retention": cb["entity_retention"],
            "hedges_total": cb["attribution_buffer"]["total"],
            "verb_downgrade": cb["verb_downgrade"],
            "blurb_chars": len(summary),
            "control": "rss_blurb_vs_title_plus_body",
        }
    return out


# ── orchestration ──────────────────────────────────────────────────────

def compute_controls(r, results, idx, eng, vt, active_texts, story,
                     embeddings=None, void_fn=None, panel_vix=None, segments_dir=None) -> dict:
    """Build attribution.controls for one story. Never raises; per-probe {"error": ...}.

    r            the stage-3 result dict (geo, source_void, compression, void_stats,
                 claim_killshots and responses already set)
    results/idx  the batch and this story's index (batch mates are the first
                 choice for a control story)
    eng, vt      the production engine and VocabTensor already in scope in stage 3
    active_texts the same list stage 3 measured
    embeddings   the (N, 1024) array stage 3 already computed for active_texts
    void_fn      batch_producer._compute_void (passed in to avoid a circular import)
    panel_vix    batch_producer._panel_vix (the measured VIX loop)
    """
    out = {"version": VERSION}
    active_texts = list(active_texts or [])
    ctrl = None
    try:
        ctrl = pick_control_story(results, idx, segments_dir)
    except Exception as e:
        out["control_story_error"] = str(e)[:200]
    if ctrl is not None:
        out["control_story"] = {
            "guid": ctrl["guid"], "title": ctrl["title"], "method": ctrl["method"],
            "n_responses": len(ctrl["responses"]), "segment_file": ctrl.get("segment_file"),
        }
    else:
        out["control_story"] = None

    def _need_ctrl():
        if ctrl is None:
            raise ValueError("no usable control story (batch mate or disk segment)")

    probes = [
        ("void", lambda: (_need_ctrl(), control_void(r, ctrl, active_texts, eng, vt, void_fn))[1]),
        ("source_void", lambda: (_need_ctrl(), control_source_void(r, ctrl, active_texts, story))[1]),
        ("killshots", lambda: (_need_ctrl(), control_killshots(r, ctrl, eng, story))[1]),
        ("density", lambda: control_density(r, results, idx, eng, active_texts, embeddings,
                                            panel_vix, segments_dir)),
        ("compression", lambda: (_need_ctrl(), control_compression(r, ctrl, story))[1]),
    ]
    for name, fn in probes:
        try:
            out[name] = fn()
        except Exception as e:
            out[name] = {"error": str(e)[:200]}
            log.info("controls[%s] skipped: %s", name, e)
    return out


# ── on-air text ────────────────────────────────────────────────────────

def control_sentence(kind, controls, claim=None) -> str:
    """One appended sentence per beat, '' when the probe is missing or failed.

    Templates are fixed (design critique A9, 2026-09-10): numbers only, no
    evaluative words, same precision as the beats they follow. Each string
    starts with a space so callers append it to the existing beat text.
    """
    try:
        c = controls or {}
        if not isinstance(c, dict) or not c:
            return ""
        if kind == "beat_04_density":
            d = c.get("density") or {}
            if d.get("error") or d.get("control_mixed") is None or int(d.get("n_panel") or 0) < 3:
                return ""
            return (f" Control: a panel of one summary from each of {int(d['n_panel'])} different "
                    f"stories scores {float(d['control_mixed']):.3f} on the same measure.")
        if kind == "beat_04b_absent_words":
            s = c.get("source_void") or {}
            if s.get("error") or s.get("control_absent_ratio") is None:
                return ""
            return (f" Control: another article's content words were "
                    f"{float(s['control_absent_ratio']) * 100:.0f} percent absent from these same responses.")
        if kind in ("void", "ensemble_top5", "beat_06_void_reveal"):
            v = c.get("void") or {}
            if (v.get("error") or not v.get("pool_n") or not v.get("control_pool_n")
                    or v.get("absent_frac") is None or v.get("control_absent_frac") is None):
                return ""
            return (f" Control: of the {int(v['pool_n'])} words nearest this headline, "
                    f"{float(v['absent_frac']) * 100:.0f} percent were absent from the responses; "
                    f"of the {int(v['control_pool_n'])} words nearest an unrelated headline, "
                    f"{float(v['control_absent_frac']) * 100:.0f} percent were absent.")
        if kind == "beat_11_compression_report":
            k = c.get("compression") or {}
            if (k.get("error") or k.get("hedges_total_control") is None
                    or k.get("entity_retention_control") is None):
                return ""
            n = int(k.get("n_control_responses") or 0)
            if n < 2:
                return ""
            return (f" Control: {_NUM_WORDS.get(n, str(n))} summaries of an unrelated story scored against "
                    f"this article insert {int(k['hedges_total_control'])} attribution buffers and retain "
                    f"{float(k['entity_retention_control']):.2f} of its entities.")
        if kind == "beat_15_killshots":
            k = c.get("killshots") or {}
            if k.get("error") or claim is None:
                return ""
            for p in k.get("per_claim") or []:
                if (p.get("claim") == claim and p.get("max_sim_own") is not None
                        and p.get("max_sim_control") is not None):
                    return (f" Nearest response scored {float(p['max_sim_own']):.2f} here, "
                            f"{float(p['max_sim_control']):.2f} against an unrelated panel; "
                            f"omitted means below 0.65.")
            return ""
        return ""
    except Exception:
        return ""


def summarize_controls(records) -> dict:
    """Site/ledger aggregate over story records that carry attribution.controls (means over stories that have each number)."""
    def _mean(xs):
        xs = [float(x) for x in xs if x is not None]
        return round(sum(xs) / len(xs), 4) if xs else None
    recs = [c for c in (records or []) if isinstance(c, dict) and c]
    dens = [c.get("density") or {} for c in recs]
    svs = [c.get("source_void") or {} for c in recs]
    voids = [c.get("void") or {} for c in recs]
    kss = [c.get("killshots") or {} for c in recs]
    comps = [c.get("compression") or {} for c in recs]
    return {
        "stories_with_controls": len(recs),
        "mean_density_measured": _mean(d.get("measured") for d in dens if not d.get("error")),
        "mean_density_control": _mean(d.get("control_mixed") for d in dens if not d.get("error")),
        "mean_absent_ratio_measured": _mean(s.get("absent_ratio") for s in svs if not s.get("error")),
        "mean_absent_ratio_control": _mean(s.get("control_absent_ratio") for s in svs if not s.get("error")),
        "mean_void_pool_measured": _mean(v.get("absent_frac") for v in voids if not v.get("error")),
        "mean_void_pool_control": _mean(v.get("control_absent_frac") for v in voids if not v.get("error")),
        "mean_killshot_max_sim_own": _mean(k.get("mean_max_sim_own") for k in kss if not k.get("error")),
        "mean_killshot_max_sim_control": _mean(k.get("mean_max_sim_control") for k in kss if not k.get("error")),
        "mean_hedges_measured": _mean(k.get("hedges_total") for k in comps if not k.get("error")),
        "mean_hedges_control_other_panel": _mean(k.get("hedges_total_control") for k in comps if not k.get("error")),
        "mean_entity_retention_measured": _mean(k.get("entity_retention") for k in comps if not k.get("error")),
        "mean_entity_retention_control": _mean(k.get("entity_retention_control") for k in comps if not k.get("error")),
        "definition": "docs/metrics.md section 10 (controls version 1, 2026-09-10)",
    }


def ledger_line(controls) -> str:
    """The per-story '**Controls:**' line of the Omission Ledger; '' when there is nothing to say."""
    try:
        c = controls or {}
        if not isinstance(c, dict) or not c:
            return ""
        parts = []
        d = c.get("density") or {}
        if not d.get("error") and d.get("control_mixed") is not None and d.get("measured") is not None:
            parts.append(f"density {float(d['measured']):.3f} vs mixed-panel {float(d['control_mixed']):.3f}")
        s = c.get("source_void") or {}
        if not s.get("error") and s.get("control_absent_ratio") is not None and s.get("absent_ratio") is not None:
            parts.append(f"absent {float(s['absent_ratio']) * 100:.0f}% vs other-article "
                         f"{float(s['control_absent_ratio']) * 100:.0f}%")
        v = c.get("void") or {}
        if not v.get("error") and v.get("absent_frac") is not None and v.get("control_absent_frac") is not None:
            parts.append(f"void pool {float(v['absent_frac']) * 100:.0f}% vs unrelated-headline "
                         f"{float(v['control_absent_frac']) * 100:.0f}%")
        k = c.get("killshots") or {}
        if not k.get("error") and k.get("mean_max_sim_own") is not None and k.get("mean_max_sim_control") is not None:
            parts.append(f"killshot nearest-response similarity {float(k['mean_max_sim_own']):.2f} vs "
                         f"unrelated-panel {float(k['mean_max_sim_control']):.2f}")
        m = c.get("compression") or {}
        if not m.get("error") and m.get("hedges_total") is not None and m.get("hedges_total_control") is not None:
            parts.append(f"hedges {int(m['hedges_total'])} vs other-panel {int(m['hedges_total_control'])}")
        return "; ".join(parts)
    except Exception:
        return ""
