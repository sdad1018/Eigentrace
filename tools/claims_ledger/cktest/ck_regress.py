#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ck_regress.py - the checker's regression suite (PROSECUTOR_REVIEW item 13).

The five synthetic cases from the adversarial pass of 2026-09-16, adopted verbatim as a
suite that runs BEFORE the real scan. T4 and T5 are the two that caught live defects:

  T1  ledger CONTRADICTED, prose asserts MEASURED                      -> must FAIL (violation)
  T2  ledger CONTRADICTED, prose fenced as a withdrawal                -> must PASS (no violation)
  T3  ledger UNTESTED, bare assertion, no fence                        -> must FAIL (UNFENCED)
  T4  as T1, with a nav link reading "Withdrawals" 3 lines above       -> must FAIL
  T5  as T1, with a nav link reading "Findings withdrawn to date"      -> must FAIL
      3 lines above. Before the 2026-09-16 fix this returned 0 violations: the withdrawal
      cue in page furniture masked a live violation. This case is the regression.

Every fixture is built into a temporary directory at run time, so the suite carries no
state and the absolute paths in the synthetic ledger are always correct.

Usage:
  python3 ck_regress.py            # run the suite, exit 0 on pass, 1 on failure
  from ck_regress import run_suite # returns (ok, [lines])
"""
import json, os, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
# ledger_check.py lives one directory up (claims_ledger/) or beside us; try both.
for cand in (os.path.dirname(HERE), HERE):
    if os.path.exists(os.path.join(cand, "ledger_check.py")) and cand not in sys.path:
        sys.path.insert(0, cand)
        break
import ledger_check  # noqa: E402


PAGES = {
    # name: (html, ledger status, anchor, expect_violation, asserted_status_expected)
    "t1.html": (
        "<html><body>\n"
        "<p>Intro paragraph with nothing relevant.</p>\n"
        "<p>The displacement is 74% stronger when the story involves an AI developer, "
        "measured across n = 1,592 stories (p = 0.002).</p>\n"
        "<p>Closing paragraph with nothing relevant.</p>\n"
        "</body></html>",
        "CONTRADICTED", "displacement is 74% stronger", True, "MEASURED"),
    "t2.html": (
        "<html><body>\n"
        "<p>Intro paragraph with nothing relevant.</p>\n"
        "<p>We withdrew the finding that the displacement is 74% stronger when the story "
        "involves an AI developer; the retraction is recorded as W03.</p>\n"
        "<p>Closing paragraph with nothing relevant.</p>\n"
        "</body></html>",
        "CONTRADICTED", "displacement is 74% stronger", False, "WITHDRAWN"),
    "t3.html": (
        "<html><body>\n"
        "<p>Intro paragraph with nothing relevant.</p>\n"
        "<p>Models soften the verbs they are given when they summarise a violent event.</p>\n"
        "<p>Closing paragraph with nothing relevant.</p>\n"
        "</body></html>",
        "UNTESTED", "Models soften the verbs they are given", True, "UNFENCED"),
    "t4.html": (
        "<html><body>\n"
        "<nav><a href=\"/withdrawals\">Withdrawals</a></nav>\n"
        "<p>The displacement is 74% stronger when the story involves an AI developer, "
        "measured across n = 1,592 stories (p = 0.002).</p>\n"
        "<p>Closing paragraph with nothing relevant.</p>\n"
        "</body></html>",
        "CONTRADICTED", "displacement is 74% stronger", True, "MEASURED"),
    "t5.html": (
        "<html><body>\n"
        "<nav><a href=\"/withdrawals\">Findings withdrawn to date</a></nav>\n"
        "<p>The displacement is 74% stronger when the story involves an AI developer, "
        "measured across n = 1,592 stories (p = 0.002).</p>\n"
        "<p>Closing paragraph.</p>\n"
        "</body></html>",
        "CONTRADICTED", "displacement is 74% stronger", True, "MEASURED"),
}

# Cue-lexicon unit cases (PROSECUTOR_REVIEW item 10). The two forms the old regex missed
# are the two most common on this site: the page is titled "Withdrawals" and the prose
# says "we withdrew".
CUE_WORDS_MUST_MATCH = ["withdraw", "withdraws", "withdrawn", "withdrawal", "withdrawals",
                        "withdrew", "Withdrawals", "we withdrew"]
CUE_WORDS_MUST_NOT_MATCH = ["withdrawnness", "drawer", "withdrawaling"]


def _build_one(tmp, name, page_html, status, anchor):
    """Each case gets its OWN docs tree.

    The fixtures deliberately share an anchor ("displacement is 74% stronger"), because
    what they vary is the prose AROUND it. Built into one directory they would
    cross-contaminate through the spread scan, and the suite would be testing the spread
    scan rather than the classifier. One case, one tree.
    """
    docs = os.path.join(tmp, name.split(".")[0])
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, name), "w", encoding="utf-8") as fh:
        fh.write(page_html)
    claim = {"id": name.split(".")[0].upper(), "working_name": name, "description": "",
             "status": status, "cheapest_boring_explanation": "", "prerequisite_tests": [],
             "notes": "", "evidence_paths": [], "verifier_verdicts": {},
             "first_asserted": "", "last_tested": "", "allowed_public_wording": None,
             "must_not_say": [],
             "site_pages": [{"file": os.path.join(docs, name), "sentence": anchor}]}
    led = os.path.join(docs, "ledger_regress.json")
    json.dump({"version": "regress", "last_updated": "2026-09-16",
               "governance": {}, "claims": [claim]},
              open(led, "w", encoding="utf-8"), indent=1)
    return led, docs


def run_suite(verbose=False):
    """Return (ok, lines). Builds the five fixtures, runs the real scanner, checks each."""
    lines, ok = [], True
    tmp = tempfile.mkdtemp(prefix="ck_regress_")
    try:
        for name, (page_html, status, anchor, expect_v, expect_as) in sorted(PAGES.items()):
            cid = name.split(".")[0].upper()
            led, docs = _build_one(tmp, name, page_html, status, anchor)
            res = ledger_check.run_scan(led, docs, radius=3)
            vs = res["violations"]
            hit = bool(vs)
            asserted = vs[0]["asserted_status"] if vs else None
            if hit != expect_v:
                ok = False
                lines.append("  FAIL %s (%s): expected %s, got %d violation(s)"
                             % (cid, status, "a violation" if expect_v else "no violation", len(vs)))
            elif expect_v and asserted != expect_as:
                ok = False
                lines.append("  FAIL %s: violation raised but asserted=%s, expected %s"
                             % (cid, asserted, expect_as))
            elif expect_v and res["n_violation_places"] != 1:
                ok = False
                lines.append("  FAIL %s: expected 1 distinct place, got %d"
                             % (cid, res["n_violation_places"]))
            else:
                lines.append("  pass %s  ledger=%-12s expected=%-12s %s"
                             % (cid, status, "VIOLATION" if expect_v else "clean",
                                ("asserted " + asserted) if asserted else ""))
        # cue-lexicon unit cases
        for w in CUE_WORDS_MUST_MATCH:
            if not any(r.search(w) for r in ledger_check.WITHDRAWN_RE):
                ok = False
                lines.append("  FAIL cue lexicon: %r is not matched by any WITHDRAWN cue" % w)
        for w in CUE_WORDS_MUST_NOT_MATCH:
            if any(r.search(w) for r in ledger_check.WITHDRAWN_RE):
                ok = False
                lines.append("  FAIL cue lexicon: %r must not match a WITHDRAWN cue" % w)
        lines.append("  pass cue lexicon: %d forms match, %d correctly do not"
                     % (len(CUE_WORDS_MUST_MATCH), len(CUE_WORDS_MUST_NOT_MATCH)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if verbose:
        for ln in lines:
            print(ln)
    return ok, lines


if __name__ == "__main__":
    good, out = run_suite(verbose=True)
    print("REGRESSION SUITE:", "PASS" if good else "FAIL")
    sys.exit(0 if good else 1)
