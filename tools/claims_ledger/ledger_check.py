#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_check.py - enforce the charter's claim-ledger authority against the public docs.

For every claim that carries site_pages, find the registered anchor sentence or number in
the public docs tree, classify the prose around it as asserting MEASURED, ARGUED,
WITHDRAWN or UNFENCED, and flag any page whose asserted status is stronger than the status
the ledger records.

Read-only. Writes nothing under the public repo tree; the two reports go next to the
ledger. Dry run: no page is edited.

2026-09-16, PROSECUTOR_REVIEW.md required changes 10-13:
 10. The WITHDRAWN cue lexicon now covers withdraw / withdraws / withdrew / withdrawn /
     withdrawal / withdrawals. The old `\\bwithdraw(n|al|s|)\\b` matched neither
     `withdrawals` nor `withdrew` - the two most common forms on this site.
 11. WITHDRAWN cues are matched in the ANCHOR'S OWN SENTENCE only, and page furniture
     (<nav>, <header>, <footer>, <aside> and their link text) is stripped before
     classification. Before this, any withdrawal-shaped word within three lines of the
     anchor suppressed the violation, so a sidebar, breadcrumb or footer link silenced a
     live one. Verified on case T5 in cktest/.
 12. Both counts are reported: distinct sentences (places) and (claim, place) pairs. The
     old headline published the pair count as a count of places.
 13. The five synthetic cases in cktest/ run as a regression suite BEFORE the scan. A
     failing suite aborts the run unless --skip-regression is passed.

Repo copy, 2026-09-17. Differences from the runtime original, all of them about
portability and about where output is allowed to land:
  * defaults are derived from this file's own location, not from any machine path;
  * site_pages entries may be repo-relative and are resolved against --root;
  * nothing is written unless an output path is given, and an output path inside this
    repository is refused - this repository is public and commits itself hourly, so a
    violations report must never land in it;
  * --advisory / --blocking choose the exit code. Advisory is the installed default and
    always exits 0 on violations. See README.md for the flip rule.

Usage:
  python3 ledger_check.py [--ledger PATH] [--docs PATH] [--root PATH]
                          [--md-out FILE] [--json-out FILE] [--out DIR]
                          [--date YYYY-MM-DD] [--radius N]
                          [--advisory | --blocking] [--skip-regression]

Exit codes: 0 clean or advisory; 1 regression suite failed or bad arguments;
            2 violations found and --blocking was given.
"""
import argparse, json, os, re, sys, html, datetime
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))   # tools/claims_ledger -> tools -> repo
DEF_LEDGER = os.path.join(HERE, "claims_ledger.json")
DEF_DOCS = os.path.join(REPO_ROOT, "docs")
DEF_OUT = None          # write nothing unless an output path is asked for

SCAN_EXT = (".html", ".md", ".txt", ".jsonld")
SKIP_DIR = {"og", "assets", "soul_history", "_site", ".git"}
SKIP_FILE_RE = re.compile(r"\.bak|~$|\.orig")
# Hourly machine-generated snapshots. They are data, not prose the ledger governs, and an
# anchor that matches them matches hundreds of near-identical lines. Excluded from the
# spread scan only; a file registered in site_pages is always scanned wherever it lives.
SPREAD_SKIP_DIR = {"_posts"}
# An anchor is specific enough to chase across the tree only if it is wordy and not a bare
# number, and only if it does not already match half the site.
SPREAD_MIN_LEN = 12
SPREAD_MAX_HITS = 12

# Strength order: index 0 is the strongest assertion a page can make.
HIERARCHY = ["MEASURED", "DERIVED", "ARGUED", "THEOLOGICAL", "SYMBOLIC", "SPECULATIVE",
             "CONTRADICTED", "WITHDRAWN", "UNTESTED"]
RANK = {s: i for i, s in enumerate(HIERARCHY)}
RANK["ISOMORPHISM"] = -1          # reserved for a proven bijection
RANK["UNFENCED"] = RANK["ARGUED"]  # a bare assertion is at least an argued assertion

# --- cue lexicons -----------------------------------------------------------
# WITHDRAWN cues are checked first: prose that is disclosing a retraction is not asserting.
# They are matched in the anchor's own sentence ONLY (item 11), because a withdrawal cue
# anywhere else on the page is furniture, not a fence on this sentence.
WITHDRAWN_CUES = [
    r"\bwithdr(aw|aws|ew|awn|awal|awals)\b",       # item 10: withdrew / withdrawals covered
    r"\bretract(ed|ion|s|)\b", r"\bcorrection\b", r"\bcorrected\b",
    r"\bno longer (claim|presented|stated|say)", r"\bwas wrong\b", r"\bdowngrad(ed|e)\b",
    r"\bfalsifi(ed|es)\b", r"\bthe control that killed it\b", r"\bunder revision\b",
    r"\bfails\b(?!af)", r"\bdoes not survive\b",
]
MEASURED_CUES = [
    r"\bmeasured\b", r"\bwe measured\b", r"\bmeasurement\b", r"\breplicat(ed|es|ion)\b",
    r"\breproduc(ed|es|ible)\b", r"\bpre-?registered\b", r"\bthe instrument (shows|records|measures)\b",
    r"\bp\s*[=<>]\s*0?\.", r"\bp\s*[=<]\s*1e", r"\bd\s*=\s*0?\.", r"\bt\s*=\s*\d",
    r"\b95%\s*(CI|confidence)", r"\bCohen'?s d\b", r"\bWilcoxon\b", r"\bMcNemar\b",
    r"\bMann-?Whitney\b", r"\bpermutation\b", r"\bbootstrap\b", r"\bAUC\b",
    r"\bn\s*=\s*\d", r"\bof\s*\d[\d,]*\s*stories\b", r"\bdeterministic\b", r"\bexactly\b",
    r"\bcontrol(?:s|led)? (?:that|for|rule)", r"\bstatistically\b", r"\bsignifican(t|ce)\b",
]
ARGUED_CUES = [
    r"\bargued\b", r"\bwe read\b", r"\bour reading\b", r"\binterpretation\b", r"\bwe interpret\b",
    r"\bwe find that reading\b", r"\bhypothes(is|ise|ize|es)\b", r"\bsuggests\b", r"\bwe think\b",
    r"\bplausible\b", r"\bwe believe\b", r"\bit looks like\b", r"\bmay (be|mean|point)\b",
    r"\bwhere measurement ends\b", r"\bnot the measurement\b",
]
WITHDRAWN_RE = [re.compile(p, re.I) for p in WITHDRAWN_CUES]
MEASURED_RE = [re.compile(p, re.I) for p in MEASURED_CUES]
ARGUED_RE = [re.compile(p, re.I) for p in ARGUED_CUES]

TAG_RE = re.compile(r"<[^>]+>")
# Blank out behavioural script and style bodies, but never application/ld+json or an
# inline DATA block: those are the page's machine-readable surface and a claim asserted
# there is asserted.
SCRIPT_RE = re.compile(r"<script(?![^>]*ld\+json)[^>]*>.*?</script>|<style\b[^>]*>.*?</style>",
                       re.S | re.I)
# meta/og descriptions live inside the tag, so pull their content out before stripping.
META_RE = re.compile(r"<meta\b[^>]*\bcontent\s*=\s*([\"'])(.*?)\1", re.S | re.I)

# --- item 11: page furniture -------------------------------------------------
# Navigation, headers, footers and sidebars are chrome, not prose the ledger governs. A
# withdrawal cue in them is not a fence on the claim three lines below, and a MEASURED cue
# in them is not an assertion of it either. These bodies are blanked (space-for-character,
# newlines kept) so that line indexing is unchanged, before the classification context is
# built. Anchor matching still runs against the UNBLANKED text, so a claim that lives
# inside a nav is still found and still flagged.
FURNITURE_RE = re.compile(
    r"<(nav|header|footer|aside)\b[^>]*>.*?</\1>", re.S | re.I)
# A bare <a>...</a> outside those elements is usually a breadcrumb, a "see also" or a
# card link. Its own text is stripped for classification purposes; the surrounding
# sentence is untouched.
LINK_TEXT_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.S | re.I)
# Markdown equivalents: a link-only line, a nav list item, a breadcrumb line.
MD_LINK_ONLY_RE = re.compile(r"^\s*[-*>|]?\s*\[[^\]]*\]\([^)]*\)\s*[|,]?\s*$")


def _blank(m):
    """Replace a match with spaces, preserving newlines so line indexing survives."""
    return re.sub(r"[^\n]", " ", m.group(0))


def visible_lines(path):
    """Return (raw_lines, visible_lines, prose_lines).

    `visible` has tags stripped. `prose` is the same, with page furniture blanked; it is
    what classification reads. Both are indexed identically to `raw`.
    """
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return [], [], []
    is_markup = path.endswith((".html", ".jsonld"))
    if is_markup:
        raw = SCRIPT_RE.sub(_blank, raw)
    # the furniture-blanked copy of the source, built before tags are stripped
    if is_markup:
        praw = FURNITURE_RE.sub(_blank, raw)
        praw = LINK_TEXT_RE.sub(lambda m: m.group(0).replace(m.group(1),
                                                             re.sub(r"[^\n]", " ", m.group(1))),
                                praw)
    else:
        praw = raw

    def render(line):
        meta = " ".join(m.group(2) for m in META_RE.finditer(line))
        v = html.unescape(TAG_RE.sub(" ", line))
        if meta:
            v = v + " " + html.unescape(meta)
        # non-breaking and narrow spaces read as ordinary spaces; typographic dashes and
        # quotes are folded so a registered anchor matches the rendered prose.
        return (v.replace(" ", " ").replace(" ", " ").replace(" ", " ")
                 .replace("−", "-").replace("–", "-").replace("—", "-")
                 .replace("’", "'").replace("‘", "'")
                 .replace("“", '"').replace("”", '"'))

    rawl = raw.split("\n")
    prawl = praw.split("\n")
    if len(prawl) != len(rawl):          # defensive: never let the indexes drift apart
        prawl = rawl
    vis = [render(ln) for ln in rawl]
    prose = [render(ln) for ln in prawl]
    if not is_markup:
        # markdown / txt: blank link-only lines, which are nav in these files
        prose = ["" if MD_LINK_ONLY_RE.match(p) else p for p in prose]
    return rawl, vis, prose


def fold(s):
    """Same folding applied to a registered anchor, so both sides match."""
    return (s.replace(" ", " ").replace("−", "-").replace("–", "-")
             .replace("—", "-").replace("’", "'").replace("“", '"')
             .replace("”", '"').lower())


def context(lines, i, radius=3):
    lo, hi = max(0, i - radius), min(len(lines), i + radius + 1)
    return re.sub(r"\s+", " ", " ".join(lines[lo:hi])).strip()


def split_sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def anchor_sentence(vis, i, anchor):
    """The anchor's OWN sentence (item 11).

    Preference order: the sentence of the anchor's own line; then the sentence of a
    one-line window, for an anchor that straddles a line break; then the line itself.
    This is deliberately much tighter than the +/-3-line classification window: it is what
    the WITHDRAWN cues are matched against, so that furniture cannot fence a live claim.
    """
    low = fold(anchor)
    line = re.sub(r"\s+", " ", vis[i]).strip() if i < len(vis) else ""
    for s in split_sentences(line):
        if low in fold(s):
            return s
    if low in fold(line):
        return line
    wide = context(vis, i, 1)
    for s in split_sentences(wide):
        if low in fold(s):
            return s
    return line or wide[:400]


def classify(sentence, ctx):
    """Classify one anchor occurrence.

    WITHDRAWN cues are read from `sentence` - the anchor's own sentence - only.
    MEASURED and ARGUED cues are read from `ctx`, the furniture-stripped context window,
    plus the sentence itself.
    """
    scope = (sentence + " " + ctx) if ctx else sentence
    hits = {"WITHDRAWN": [m.pattern for m in WITHDRAWN_RE if m.search(sentence)],
            "MEASURED": [m.pattern for m in MEASURED_RE if m.search(scope)],
            "ARGUED": [m.pattern for m in ARGUED_RE if m.search(scope)]}
    if hits["WITHDRAWN"]:
        return "WITHDRAWN", hits
    if hits["MEASURED"]:
        return "MEASURED", hits
    if hits["ARGUED"]:
        return "ARGUED", hits
    return "UNFENCED", hits


def collect_docs(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIR]
        for f in sorted(fn):
            if f.endswith(SCAN_EXT) and not SKIP_FILE_RE.search(f):
                out.append(os.path.join(dp, f))
    return out


def run_scan(ledger_path, docs_root, radius=3, root=None):
    """Scan the docs tree against the ledger. Returns a result dict. Writes nothing.

    site_pages[].file may be absolute (runtime ledger) or repo-relative (repo copy).
    A relative entry is resolved against `root`, which defaults to the parent of
    docs_root - so a staged copy of the tree can be checked by pointing --docs at it.
    """
    if root is None:
        root = os.path.dirname(os.path.abspath(docs_root))
    led = json.load(open(ledger_path, encoding="utf-8"))
    claims = led["claims"]
    docs = collect_docs(docs_root)
    cache = {}

    def load(p):
        if p not in cache:
            cache[p] = visible_lines(p)
        return cache[p]

    spread_pool = [p for p in docs
                   if not any(d in p.split(os.sep) for d in SPREAD_SKIP_DIR)]

    def anchor_hits(paths, anchor):
        out = []
        low = fold(anchor)
        for p in paths:
            _, vis, _ = load(p)
            for i, ln in enumerate(vis):
                if low in fold(ln):
                    out.append((p, i))
        return out

    violations, findings, unresolved, spread = [], [], [], []
    scanned_anchors = 0

    for c in claims:
        cstat = c["status"]
        crank = RANK.get(cstat, RANK["UNTESTED"])
        for sp in c.get("site_pages", []):
            f, anchor = sp.get("file", ""), (sp.get("sentence") or "").strip()
            if f and not os.path.isabs(f):
                f = os.path.normpath(os.path.join(root, f))
            note = sp.get("note", "") or ""
            exempt = "withdrawal entry itself" in note
            if not anchor:
                unresolved.append({"claim_id": c["id"], "file": f,
                                   "reason": "no anchor registered (page listed for provenance only)",
                                   "note": note})
                continue
            scanned_anchors += 1
            if not os.path.exists(f):
                unresolved.append({"claim_id": c["id"], "file": f, "anchor": anchor,
                                   "reason": "registered file does not exist"})
                continue

            # (1) primary scan: the registered page only. This is what site_pages means.
            hits = anchor_hits([f], anchor)
            if not hits:
                unresolved.append({"claim_id": c["id"], "file": f, "anchor": anchor,
                                   "reason": "anchor not found on the registered page - the "
                                             "claim may already have been removed or reworded"})

            # (2) spread scan: chase a distinctive anchor onto other pages. A short or
            # purely numeric anchor, or one that already matches much of the site, is not
            # specific enough to attribute to this claim.
            specific = (len(anchor) >= SPREAD_MIN_LEN and re.search(r"[A-Za-z]{3}", anchor))
            if specific:
                others = anchor_hits([p for p in spread_pool if p != f], anchor)
                if len(others) <= SPREAD_MAX_HITS:
                    hits += others
                else:
                    spread.append({"claim_id": c["id"], "anchor": anchor,
                                   "other_pages_matched": len(set(p for p, _ in others)),
                                   "lines_matched": len(others),
                                   "reason": "anchor not specific enough to attribute; "
                                             "registered page scanned only"})
            else:
                n_other = len(anchor_hits([p for p in spread_pool if p != f], anchor))
                if n_other:
                    spread.append({"claim_id": c["id"], "anchor": anchor,
                                   "other_pages_matched": None, "lines_matched": n_other,
                                   "reason": "anchor too short or numeric for a spread scan; "
                                             "registered page scanned only"})

            for p, i in hits:
                _, vis, prose = load(p)
                sent = anchor_sentence(vis, i, anchor)
                ctx = context(prose, i, radius)
                asserted, cues = classify(sent, ctx)
                arank = RANK[asserted]
                rec = {
                    "page": os.path.relpath(p, docs_root),
                    "page_abs": p,
                    "line": i + 1,
                    "claim_id": c["id"],
                    "working_name": c["working_name"],
                    "ledger_status": cstat,
                    "asserted_status": asserted,
                    "anchor": anchor,
                    "sentence": sent[:600],
                    "cue_hits": {k: v for k, v in cues.items() if v},
                    "registered_page": (p == f),
                    "exempt_corrections_page": exempt,
                    "allowed_public_wording": c.get("allowed_public_wording"),
                    "must_not_say": c.get("must_not_say", []),
                }
                findings.append(rec)
                if exempt and p == f:
                    continue
                if arank < crank:
                    rec2 = dict(rec)
                    rec2["why"] = (f"page asserts {asserted} (rank {arank}) for a claim the "
                                   f"ledger records as {cstat} (rank {crank})")
                    violations.append(rec2)

    # de-duplicate violations on (page, line, claim_id)
    seen, dedup = set(), []
    for v in violations:
        k = (v["page"], v["line"], v["claim_id"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(v)
    violations = sorted(dedup, key=lambda v: (RANK[v["asserted_status"]],
                                              -RANK[v["ledger_status"]], v["page"], v["line"]))

    # ---- item 12: BOTH counts -------------------------------------------------
    places = sorted(set((v["page"], v["line"]) for v in violations))
    multi = Counter((v["page"], v["line"]) for v in violations)
    multi_claim_places = {k: n for k, n in multi.items() if n > 1}

    return {
        "ledger": ledger_path, "ledger_version": led.get("version"), "docs_root": docs_root,
        "claims": claims, "docs": docs,
        "violations": violations, "findings": findings,
        "unresolved": unresolved, "spread": spread,
        "scanned_anchors": scanned_anchors,
        "n_violation_pairs": len(violations),
        "n_violation_places": len(places),
        "places": places,
        "multi_claim_places": multi_claim_places,
        "max_claims_on_one_place": max(multi.values()) if multi else 0,
        "n_on_registered_page": sum(1 for v in violations if v["registered_page"]),
        "n_from_spread_scan": sum(1 for v in violations if not v["registered_page"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=DEF_LEDGER)
    ap.add_argument("--docs", default=DEF_DOCS)
    ap.add_argument("--root", default=None,
                    help="root that repo-relative site_pages resolve against "
                         "(default: the parent of --docs)")
    ap.add_argument("--out", default=DEF_OUT,
                    help="directory for dated reports; omit to write no reports")
    ap.add_argument("--md-out", default=None, help="exact path for the markdown report")
    ap.add_argument("--json-out", default=None, help="exact path for the JSON report")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--radius", type=int, default=3)
    ap.add_argument("--advisory", action="store_true",
                    help="report only; always exit 0 on violations (installed default)")
    ap.add_argument("--blocking", action="store_true",
                    help="exit 2 if any violation is found (owner flips this on; README)")
    ap.add_argument("--skip-regression", action="store_true",
                    help="do not run cktest/ before the scan (not for CI)")
    a = ap.parse_args()
    if a.advisory and a.blocking:
        print("ABORTED: --advisory and --blocking are mutually exclusive.")
        return 1

    # This repository is public and commits itself hourly. A violations report quotes
    # every failing sentence, so it must not be written where that commit would find it.
    def _outside_repo(p, what):
        if p is None:
            return True
        full = os.path.abspath(p)
        if full == REPO_ROOT or full.startswith(REPO_ROOT + os.sep):
            print("ABORTED: %s would write inside the repository (%s). "
                  "Reports must land outside it." % (what, full))
            return False
        return True

    # ---- item 13: regression suite runs BEFORE the scan ----------------------
    regression = "SKIPPED"
    if not a.skip_regression:
        here = os.path.dirname(os.path.abspath(__file__))
        ckdir = os.path.join(here, "cktest")
        if os.path.isdir(ckdir):
            sys.path.insert(0, ckdir)
            try:
                import ck_regress
                ok, lines = ck_regress.run_suite()
            except Exception as exc:                      # a broken suite is a failed suite
                ok, lines = False, ["  FAIL suite raised %s: %s" % (type(exc).__name__, exc)]
            print("regression suite (cktest/):")
            for ln in lines:
                print(ln)
            regression = "PASS" if ok else "FAIL"
            print("  -> %s\n" % regression)
            if not ok:
                print("ABORTED: the checker's own regression suite failed. The scan was not run.")
                return 1
        else:
            regression = "MISSING"
            print("ABORTED: cktest/ not found; the regression suite is mandatory. "
                  "Pass --skip-regression to override.")
            return 1

    json_path, md_path = a.json_out, a.md_out
    if a.out:
        json_path = json_path or os.path.join(a.out, "violations_%s.json" % a.date)
        md_path = md_path or os.path.join(a.out, "violations_%s.md" % a.date)
    for p, what in ((json_path, "--json-out/--out"), (md_path, "--md-out/--out")):
        if not _outside_repo(p, what):
            return 1

    res = run_scan(a.ledger, a.docs, a.radius, a.root)
    violations = res["violations"]
    claims, docs = res["claims"], res["docs"]

    for p in (json_path, md_path):
        if p and os.path.dirname(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_page = Counter(v["page"] for v in violations)
    by_claim = Counter(v["claim_id"] for v in violations)
    by_pair = Counter((v["ledger_status"], v["asserted_status"]) for v in violations)
    by_page_places = Counter(p for p, _ in res["places"])

    out = {
        "generated": stamp,
        "ledger": a.ledger,
        "ledger_version": res["ledger_version"],
        "docs_root": a.docs,
        "dry_run": True,
        "regression_suite": regression,
        "files_scanned": len(docs),
        "claims_in_ledger": len(claims),
        "claims_with_site_pages": sum(1 for c in claims if c.get("site_pages")),
        "anchors_scanned": res["scanned_anchors"],
        "matches_found": len(res["findings"]),
        # ---- item 12: both counts, named for what they are ----
        "violation_places": res["n_violation_places"],
        "violation_claim_place_pairs": res["n_violation_pairs"],
        "count_note": ("violation_places counts DISTINCT (page, line) sentences; "
                       "violation_claim_place_pairs counts (claim, place) attributions. "
                       "One sentence can carry several claims, so the pair count is the "
                       "larger of the two and must never be published as a count of places."),
        "places_carrying_more_than_one_claim": len(res["multi_claim_places"]),
        "max_claims_on_one_place": res["max_claims_on_one_place"],
        "violations_on_registered_page": res["n_on_registered_page"],
        "violations_from_spread_scan": res["n_from_spread_scan"],
        "violations_by_page_pairs": by_page.most_common(),
        "violations_by_page_places": by_page_places.most_common(),
        "violations_by_claim": by_claim.most_common(),
        "violations_by_status_pair": [{"ledger": k[0], "asserted": k[1], "n": n}
                                      for k, n in by_pair.most_common()],
        "unresolved_anchors": res["unresolved"],
        "non_specific_anchors": res["spread"],
        "records": violations,
    }
    out["mode"] = "BLOCKING" if a.blocking else "ADVISORY"
    if json_path:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)

    L = []
    L.append(f"# Claim-ledger violations - {a.date}")
    L.append("")
    L.append(f"Generated {stamp}. Dry run: no page was edited and nothing under the public "
             f"repo tree was written.")
    L.append("")
    L.append("Mode: **%s**. %s" % (
        "BLOCKING" if a.blocking else "ADVISORY",
        "A non-zero violation count fails the caller."
        if a.blocking else
        "The gate reports and never fails the caller; see tools/claims_ledger/README.md "
        "for the rule that flips it to blocking and who flips it."))
    L.append("")
    L.append(f"- ledger: `{a.ledger}` (v{res['ledger_version']}, {len(claims)} claims, "
             f"{out['claims_with_site_pages']} carrying site_pages)")
    L.append(f"- docs tree: `{a.docs}` - {len(docs)} files scanned "
             f"({', '.join(SCAN_EXT)}; backups and `og/`, `assets/`, `soul_history/` skipped)")
    L.append(f"- anchors scanned: {res['scanned_anchors']}; anchor matches: {len(res['findings'])}")
    L.append(f"- regression suite (`cktest/`): **{regression}**")
    L.append("")
    L.append(f"- **violations: {res['n_violation_places']} distinct sentences "
             f"({res['n_violation_pairs']} (claim, place) pairs)**")
    L.append("")
    L.append(f"Two counts are reported and they are not interchangeable. "
             f"**{res['n_violation_places']}** is the number of distinct `(page, line)` "
             f"sentences that fail the gate - the number of places on the site that need an "
             f"edit. **{res['n_violation_pairs']}** is the number of (claim, place) "
             f"attributions: {out['places_carrying_more_than_one_claim']} sentences carry more "
             f"than one claim, the maximum being {res['max_claims_on_one_place']}. A document "
             f"whose purpose is to stop status inflation must not inflate its own count, so the "
             f"pair count is never published as a count of places. "
             f"{res['n_on_registered_page']} violations sit on the registered page and "
             f"{res['n_from_spread_scan']} were found by the spread scan.")
    L.append("")
    L.append("A violation is a page whose prose asserts a status stronger than the ledger "
             "records. `UNFENCED` means the claim appears with no measured, argued or "
             "withdrawn marker; it is ranked with ARGUED, so any CONTRADICTED or WITHDRAWN "
             "claim still standing on a page is a violation. Withdrawal cues are read from the "
             "anchor's own sentence only, and page furniture (`<nav>`, `<header>`, `<footer>`, "
             "`<aside>`, link text) is stripped before classification, so a sidebar or "
             "breadcrumb cannot fence a live claim. The corrections page `/withdrawals` is "
             "exempt where it is quoting its own entry. Each anchor is scanned on its "
             "registered page; a distinctive anchor is also chased onto other pages, and one "
             "that is short, numeric or already everywhere is listed under non-specific "
             "anchors instead.")
    L.append("")
    L.append("## Violations by page")
    L.append("")
    L.append("| page | distinct sentences | (claim, place) pairs |")
    L.append("|---|---|---|")
    for p, n in by_page.most_common():
        L.append(f"| `{p}` | {by_page_places.get(p, 0)} | {n} |")
    L.append("")
    L.append("## Violations by ledger status")
    L.append("")
    L.append("| ledger status | asserted on page | (claim, place) pairs |")
    L.append("|---|---|---|")
    for k, n in by_pair.most_common():
        L.append(f"| {k[0]} | {k[1]} | {n} |")
    L.append("")
    if res["multi_claim_places"]:
        L.append("## Sentences carrying more than one claim")
        L.append("")
        L.append("These are the places where the pair count exceeds the place count.")
        L.append("")
        L.append("| page:line | claims attributed |")
        L.append("|---|---|")
        for (pg, ln), n in sorted(res["multi_claim_places"].items(), key=lambda kv: -kv[1]):
            ids = ", ".join(sorted(v["claim_id"] for v in violations
                                   if v["page"] == pg and v["line"] == ln))
            L.append(f"| `{pg}:{ln}` | {n} - {ids} |")
        L.append("")
    L.append("## Every violation")
    L.append("")
    cur = None
    for v in violations:
        if v["claim_id"] != cur:
            cur = v["claim_id"]
            L.append("")
            L.append(f"### {v['claim_id']} - {v['working_name']}  (ledger: **{v['ledger_status']}**)")
            if v.get("allowed_public_wording"):
                L.append("")
                L.append(f"Allowed wording: {v['allowed_public_wording']}")
            if v.get("must_not_say"):
                L.append("")
                L.append("Must not say: " + "; ".join(v["must_not_say"]))
            L.append("")
        L.append(f"- `{v['page']}:{v['line']}` asserts **{v['asserted_status']}** "
                 f"(anchor `{v['anchor']}`)")
        L.append(f"  > {v['sentence']}")
    L.append("")
    L.append("## Unresolved anchors")
    L.append("")
    if not res["unresolved"]:
        L.append("None.")
    else:
        L.append("| claim | registered file | reason |")
        L.append("|---|---|---|")
        for u in res["unresolved"]:
            fn = os.path.relpath(u["file"], a.docs) if u.get("file") else "-"
            L.append(f"| {u['claim_id']} | `{fn}` | {u['reason']} |")
    L.append("")
    L.append("## Non-specific anchors (registered page scanned only)")
    L.append("")
    if not res["spread"]:
        L.append("None.")
    else:
        L.append("| claim | anchor | other lines matched | reason |")
        L.append("|---|---|---|---|")
        for s in res["spread"]:
            L.append(f"| {s['claim_id']} | `{s['anchor']}` | {s['lines_matched']} | "
                     f"{s['reason']} |")
    if md_path:
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")

    print(f"regression suite   {regression}")
    print(f"files scanned      {len(docs)}")
    print(f"claims             {len(claims)} ({out['claims_with_site_pages']} with site_pages)")
    print(f"anchors scanned    {res['scanned_anchors']}")
    print(f"anchor matches     {len(res['findings'])}")
    print(f"VIOLATIONS         {res['n_violation_places']} distinct sentences   "
          f"({res['n_violation_pairs']} (claim, place) pairs)")
    print(f"  on registered page {res['n_on_registered_page']}; "
          f"from spread scan {res['n_from_spread_scan']}")
    print(f"  sentences carrying >1 claim: {len(res['multi_claim_places'])} "
          f"(max {res['max_claims_on_one_place']})")
    print(f"unresolved anchors {len(res['unresolved'])}")
    print(f"mode               {'BLOCKING' if a.blocking else 'ADVISORY'}")
    _written = [p for p in (json_path, md_path) if p]
    for p in _written:
        print(f"wrote {p}")
    if not _written:
        print("wrote nothing  (no --md-out / --json-out / --out given)")
    print()
    print("top pages (distinct sentences / pairs):")
    for p, n in by_page.most_common(15):
        print(f"  {by_page_places.get(p, 0):4d} / {n:4d}  {p}")
    print()
    print("by status pair:")
    for k, n in by_pair.most_common():
        print(f"  {n:4d}  ledger {k[0]:13s} -> page asserts {k[1]}")

    if res["n_violation_places"] and a.blocking:
        print("\nBLOCKING: %d place(s) assert more than the ledger records."
              % res["n_violation_places"])
        return 2
    if res["n_violation_places"]:
        print("\nADVISORY: %d place(s) assert more than the ledger records; not failing."
              % res["n_violation_places"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
