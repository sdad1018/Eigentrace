#!/usr/bin/env python3
"""exself.py -- ex-self judging helpers (pure python + numpy, no GPU, no API).

Principle: the judged set never contains the judge's own text.  Where a format
requires a model to see its own text (roundtable revision, Summary Plus rewrite)
that text is the SUBJECT, not part of a scored set, and the record says so.

Every judged score carries {judge, judge_vendor, self_judged}; every aggregate is
computed by ONE function, aggregate(records, exclude_self), so the all-judge table
and the ex-self table are the same code path over the same log.

Reference implementations lifted here:
  bakeoff2.py:314-316   exself_mean per writer excludes the judge's own column
  sp_page.py:147-153    self_pref = mean(self scores) - mean(ex-self received)
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict

VENDOR = {
    # frontier panel (production names)
    "ChatGPT": "openai", "Claude": "anthropic", "Gemini": "google",
    "DeepSeek": "deepseek", "Grok": "xai",
    # local models (never a producer of any panel summary)
    "mistral-small": "local", "mistral-small:latest": "local",
    "mistral": "local", "mistral:latest": "local", "mistral:7b-text": "local",
    "qwen2.5:14b": "local", "llama3:latest": "local", "nous-hermes2:latest": "local",
    "llama3.1:8b-instruct-q4_0": "local",
    # embedding scorer (arithmetic, not a judge)
    "bge-large-en-v1.5": "embedding", "bge-large-en-v1.5:cosine": "embedding",
}

# model-id prefixes -> vendor, so a sibling id (gpt-4o-mini, claude-sonnet-4-6,
# gemini-2.0-flash, deepseek-chat, grok-3-mini-fast) maps to its vendor too.
_PREFIX = (
    ("gpt-", "openai"), ("o1", "openai"), ("o3", "openai"), ("o4", "openai"), ("chatgpt", "openai"),
    ("claude", "anthropic"), ("gemini", "google"), ("deepseek", "deepseek"), ("grok", "xai"),
    ("mistral", "local"), ("qwen", "local"), ("llama", "local"), ("nous-hermes", "local"),
    ("bge", "embedding"),
)


class ExSelfViolation(AssertionError):
    """Raised when a judged set still contains the judge's (or its vendor's) own text."""


def vendor_of(name) -> str:
    """Vendor for a panel name or a raw model id; 'unknown' when it cannot be placed."""
    if name is None:
        return "unknown"
    s = str(name)
    if s in VENDOR:
        return VENDOR[s]
    low = s.lower()
    for k, v in VENDOR.items():
        if k.lower() == low:
            return v
    for pre, v in _PREFIX:
        if low.startswith(pre):
            return v
    return "unknown"


def same_vendor(a, b) -> bool:
    """True when a and b belong to the same vendor (or are the same name)."""
    if a is None or b is None:
        return False
    if str(a) == str(b):
        return True
    va, vb = vendor_of(a), vendor_of(b)
    return va != "unknown" and va == vb


def judged_set(items: dict, judge: str, exclude_vendor: bool = True) -> dict:
    """items {author: text} minus every author the judge must not score.

    exclude_vendor=True drops every author of the judge's vendor (ChatGPT and
    gpt-4o-mini both go for an openai judge); False drops only the exact name.
    Raises ExSelfViolation if the judge's own text would still be present.
    """
    out = {}
    for author, text in items.items():
        if exclude_vendor:
            if same_vendor(author, judge):
                continue
        elif str(author) == str(judge):
            continue
        out[author] = text
    if judge in out:
        raise ExSelfViolation(f"judge {judge!r} still present in its own judged set")
    if exclude_vendor:
        for author in out:
            if same_vendor(author, judge):
                raise ExSelfViolation(f"judge {judge!r} vendor text {author!r} still in judged set")
    return out


def assert_exself(items: dict, judge: str, exclude_vendor: bool = True) -> None:
    """Raise ExSelfViolation if `items` (an already-built judged set) still holds the
    judge's own text (or, with exclude_vendor, any text of the judge's vendor)."""
    for author in items:
        if str(author) == str(judge) or (exclude_vendor and same_vendor(author, judge)):
            raise ExSelfViolation(f"judge {judge!r} would score its own vendor's text {author!r}")


def judges_for(author, all_judges, exclude_vendor: bool = True) -> list:
    """The judges allowed to score text written by `author` (None -> every judge)."""
    if author is None:
        return list(all_judges)
    if exclude_vendor:
        return [j for j in all_judges if not same_vendor(j, author)]
    return [j for j in all_judges if str(j) != str(author)]


def score_matrix_exself(scores: dict, author_of: dict) -> dict:
    """scores[judge][item] -> float ; author_of[item] -> model.

    Returns exself (mean over judges whose vendor != author's), self (own score or
    None), self_included (mean over all judges), self_pref = mean(self) -
    mean(exself received).  bakeoff2.py:314-316 / sp_page.py:147-153, verbatim in
    spirit: the judge's own column is excluded from its row's use.
    """
    items = sorted({it for j in scores for it in scores[j]})
    exself, selfs, incl = {}, {}, {}
    for it in items:
        author = author_of.get(it)
        ex = [scores[j][it] for j in scores if it in scores[j] and not same_vendor(j, author)]
        own = [scores[j][it] for j in scores if it in scores[j] and same_vendor(j, author)]
        al = [scores[j][it] for j in scores if it in scores[j]]
        exself[it] = (sum(ex) / len(ex)) if ex else None
        selfs[it] = (sum(own) / len(own)) if own else None
        incl[it] = (sum(al) / len(al)) if al else None
    s_vals = [v for v in selfs.values() if v is not None]
    e_vals = [exself[it] for it in items if selfs.get(it) is not None and exself.get(it) is not None]
    self_pref = (round(sum(s_vals) / len(s_vals) - sum(e_vals) / len(e_vals), 4)
                 if s_vals and e_vals else None)
    return {"exself": exself, "self": selfs, "self_included": incl, "self_pref": self_pref}


# ---------------------------------------------------------------- per-score records
METRICS = ("insight", "faith", "action", "trust", "keep")


def make_records(story, patient, gen, judge, parsed: dict, order=None, arm_author=None):
    """Flatten one judge's parse_scores() output into per-score records.

    parsed: {arm: {metric: score}} as returned by confront10.parse_scores.
    arm_author: optional {arm: author} override (GOLD is hand-built: author None).
    Every record carries judge, judge_vendor, patient, self_judged so aggregate()
    can drop the diagonal at aggregation time.  An arm that was offered (in
    `order`) but not parsed gets ONE placeholder record with metric/score None so
    the per-judge parse rate is recoverable from the log; every aggregate skips
    score None.
    """
    recs = []
    order = list(order or [])

    def _author(arm):
        if arm_author and arm in arm_author:
            return arm_author[arm]
        return patient

    for arm, d in (parsed or {}).items():
        author = _author(arm)
        selfj = same_vendor(judge, author)
        pos = order.index(arm) + 1 if arm in order else None
        for metric, score in (d or {}).items():
            recs.append({
                "story": story, "patient": patient, "author": author, "gen": gen,
                "judge": judge, "judge_vendor": vendor_of(judge), "arm": arm,
                "metric": metric, "score": score, "order": order, "position": pos,
                "self_judged": bool(selfj), "self_excluded": not selfj, "parsed": True,
            })
    for arm in order:
        if arm not in (parsed or {}):
            author = _author(arm)
            selfj = same_vendor(judge, author)
            recs.append({
                "story": story, "patient": patient, "author": author, "gen": gen,
                "judge": judge, "judge_vendor": vendor_of(judge), "arm": arm,
                "metric": None, "score": None, "order": order, "position": order.index(arm) + 1,
                "self_judged": bool(selfj), "self_excluded": not selfj, "parsed": False,
            })
    return recs


def aggregate(records, exclude_self: bool, metrics=METRICS):
    """ONE aggregation for both tables.

    Returns {arm: {metric: mean, ..., "n": n_insight_scores, "n_items": distinct
    (story,patient,gen)}}.  exclude_self=True drops exactly the records with
    self_judged True (judge vendor == author vendor).
    """
    pool = defaultdict(lambda: defaultdict(list))
    items = defaultdict(set)
    for r in records:
        if exclude_self and r.get("self_judged"):
            continue
        if r.get("score") is None:
            continue
        pool[r["arm"]][r["metric"]].append(float(r["score"]))
        items[r["arm"]].add((r.get("story"), r.get("patient"), r.get("gen")))
    out = {}
    for arm, mets in pool.items():
        row = {}
        for m in metrics:
            xs = mets.get(m, [])
            row[m] = (sum(xs) / len(xs)) if xs else None
        row["n"] = len(mets.get("insight", []))
        row["n_items"] = len(items[arm])
        out[arm] = row
    return out


def flat_panel(records, exclude_self: bool = False, metrics=METRICS):
    """Derived view: the legacy {arm: {metric: [scores]}} flat panel dict."""
    pool = defaultdict(lambda: {m: [] for m in metrics})
    for r in records:
        if exclude_self and r.get("self_judged"):
            continue
        if r.get("score") is None or r.get("metric") not in metrics:
            continue
        pool[r["arm"]][r["metric"]].append(r["score"])
    return {a: dict(v) for a, v in pool.items()}


def self_pref_by_judge(records, metric: str = "insight"):
    """Per judge: mean(own scores) - mean(ex-self received by that judge's texts).

    sp_page.py:147-153 pattern: self-preference = mean self-score minus mean
    ex-self received.  Positive = the judge marks its own text up.
    """
    own = defaultdict(list)
    received = defaultdict(list)
    for r in records:
        if r.get("metric") != metric or r.get("score") is None:
            continue
        author = r.get("author", r.get("patient"))
        if author is None:
            continue
        if r.get("self_judged"):
            own[author].append(float(r["score"]))
        else:
            received[author].append(float(r["score"]))
    out = {}
    for a in sorted(set(own) | set(received)):
        o, e = own.get(a, []), received.get(a, [])
        out[a] = {
            "self_mean": (sum(o) / len(o)) if o else None, "n_self": len(o),
            "exself_received_mean": (sum(e) / len(e)) if e else None, "n_exself": len(e),
            "self_pref": (round(sum(o) / len(o) - sum(e) / len(e), 3) if o and e else None),
        }
    return out


def parse_rate_by_judge(records):
    """Per judge: (story,patient,gen,arm) cells parsed / cells attempted (placeholders
    from make_records count as attempted, not parsed)."""
    attempted = defaultdict(set)
    parsed = defaultdict(set)
    for r in records:
        cell = (r.get("story"), r.get("patient"), r.get("gen"), r.get("arm"))
        attempted[r["judge"]].add(cell)
        if r.get("score") is not None:
            parsed[r["judge"]].add(cell)
    out = {}
    for j in attempted:
        a, p = len(attempted[j]), len(parsed[j])
        out[j] = {"attempted": a, "parsed_cells": p, "rate": round(p / a, 3) if a else None}
    return out


# ---------------------------------------------------------------- attribution block
def helper_sha() -> str:
    try:
        with open(os.path.abspath(__file__), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except Exception:
        return "unknown"


def stamp(record: dict, judge: str, judged_ids, self_excluded: bool, scorer_kind: str,
          self_in_set_reason=None) -> dict:
    """Write the attribution block next to a score.  Mutates and returns record."""
    if not isinstance(record, dict):
        return record
    record["judge"] = judge
    record["judge_vendor"] = vendor_of(judge)
    record["scorer_kind"] = scorer_kind
    record["judged_set"] = list(judged_ids or [])
    record["self_excluded"] = bool(self_excluded)
    record["self_in_set_reason"] = self_in_set_reason
    record["exself_helper_sha"] = helper_sha()
    return record


def format_table(agg: dict, arms, metrics=METRICS, label: str = "") -> str:
    """Printable table for one aggregate() result (rows = arms)."""
    lines = []
    if label:
        lines.append(f"  [{label}]")
    lines.append(f"  {'arm':12s} " + " ".join(f"{m:>8s}" for m in metrics) + f" {'n':>5s} {'items':>5s}")
    for a in arms:
        row = agg.get(a)
        if not row or not row.get("n"):
            continue
        cells = " ".join(f"{(row[m] if row[m] is not None else float('nan')):>8.2f}" for m in metrics)
        lines.append(f"  {a:12s} {cells} {row['n']:>5d} {row['n_items']:>5d}")
    return "\n".join(lines)
