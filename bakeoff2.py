#!/usr/bin/env python3
"""
bakeoff2.py -- the evidence-aware bake-off (v1.1): five frontier models write
a Summary Plus from the full geometry; the panel judges, ex-self.

Prompt discipline copied verbatim from the Summary Plus capstone
(confront10 lineage): channel items are DIRECTIONS FOR ATTENTION, not
words to insert. Follow each direction into the source; surface what
the source licenses; drop silently what finds nothing; invent nothing;
zero analogies; lead with what the piece leaves unresolved.

Channels:
  A -- source facts the reading layer drops (VF-IDF foreground, read
       from {sid}_synthesis2.json if present)
  C -- the segment feed: every void with both legs (flat consequence
       field + spiral converged terms), emitted by segment_feed.py

Judging: the five frontier outputs are anonymized A..E in deterministic
(alphabetical-writer) order and scored 1-5 on the capstone's insight
rubric by all ten models in one harvest; the frontier panel's EX-SELF
means are the standings (nobody grades their own homework); the local
five print as a second panel. Writer and judge stages are the declared
non-frozen stages, stamped in the JSON.

  python3 bakeoff.py --dir anamnesis_results/universal \
      --story prelude_2026 --feed prelude_feed.txt \
      [--skip-write] [--skip-judge]
"""

VERSION = "bakeoff v1.2 2026-07-10"

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)

FRONTIER = ["chatgpt", "claude", "deepseek", "gemini", "grok"]  # alpha
LOCALS = ["hermes", "llama_8b", "mistral_22b", "mistral_7b", "qwen_14b"]
LABELS = ["A", "B", "C", "D", "E"]

SP_DISCIPLINE = (
    "You will write a SUMMARY PLUS of the source document: a summary "
    "that also reads the source's negative space.\n"
    "Measured channels follow. Treat every channel item as a DIRECTION "
    "FOR ATTENTION, not a word to insert. Follow each direction into "
    "the source; where the source licenses it, surface what you find; "
    "if a direction finds nothing in the source, drop it silently. "
    "Invent nothing. Use zero analogies. Lead with what the piece "
    "leaves unresolved.\n"
    "The source's paragraphs are numbered p1..pn. After your reading, "
    "output a line 'LEDGER:' and then one line per claim, strict "
    "format TYPE|claim|refs where TYPE is F (fact, traceable to the "
    "cited paragraphs), I (inference from structure), or S "
    "(speculation -- may draw on the consequence-field terms in "
    "Channel C, hedged). refs = comma-separated paragraph ids (e.g. "
    "p2,p4) for F and I; S may cite or leave refs empty. Every "
    "paragraph of your reading must be covered by at least one ledger "
    "line. Absence claims (things the source does NOT say) are F "
    "lines citing the paragraphs searched or 'all'."
)

JUDGE_RUBRIC = (
    "Score each summary 1-5 for INSIGHT:\n"
    "5 = surfaces non-obvious, source-grounded structure a plain "
    "summary misses; 4 = several real observations beyond "
    "restatement; 3 = competent restatement plus one real "
    "observation; 2 = pure restatement; 1 = restatement with errors "
    "or invention.\n"
    "Line 1 EXACTLY: A:n B:n C:n D:n E:n\n"
    "Then one line per summary, A through E: its label and the "
    "single strongest reason for its score, grounded in its text."
)


def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def load_source(dirpath, sid):
    pj = os.path.join(dirpath, "_prompts.json")
    meta = json.load(open(pj)).get(sid) if os.path.exists(pj) else None
    if not meta:
        sys.exit(f"'{sid}' not in {pj}")
    prompt = meta.get("prompt", "")
    m = re.search(r"Text:\s*(.*)$", prompt, re.S)
    return meta.get("title", sid), (m.group(1).strip() if m else prompt)


def read_responses(dirpath, prefix, names):
    out = {}
    for f in glob.glob(os.path.join(dirpath, f"{prefix}_*.txt")):
        mdl = os.path.basename(f)[len(prefix) + 1:-4]
        if mdl in names:
            t = open(f, encoding="utf-8", errors="replace").read().strip()
            if t:
                out[mdl] = t
    return out




_NEG = re.compile(r"\b(no|not|none|never|absent|omits?|unspecified|"
                  r"lacks?|without|nothing|doesn'?t|does not|is not|"
                  r"are not)\b", re.I)
_STOPP = set("the a an of to in on for with and or is are was were be "
             "been about this that these those it its as by from at "
             "does do not no none never".split())


def _stems(text):
    try:
        from preservation_core import porter_stem as _ps
    except Exception:
        _ps = lambda w: w.lower()
    return [_ps(w) for w in re.findall(r"[a-zA-Z][a-zA-Z'\-]+",
                                       str(text).lower())
            if len(w) > 2 and w not in _STOPP]


def parse_ledger(text):
    """Strict-ish TYPE|claim|refs lines after 'LEDGER:' -- lenient on
    whitespace, tolerant of bullets."""
    m = re.split(r"^LEDGER\s*:", text, flags=re.M)
    if len(m) < 2:
        return []
    rows = []
    for raw in m[1].splitlines():
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "",
                      raw).strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or parts[0].upper()[:1] not in "FIS":
            continue
        refs = re.findall(r"p(\d+)", parts[2] if len(parts) > 2
                          else "", re.I)
        allref = bool(re.search(r"\ball\b",
                                parts[2] if len(parts) > 2 else "",
                                re.I))
        rows.append(dict(type=parts[0].upper()[0], claim=parts[1],
                         refs=[int(r) for r in refs],
                         all=allref))
    return rows


def audit_ledger(rows, paras):
    """Mechanical verification. Confidence is earned, not asserted:
    F absence claims searched across the WHOLE source (concept stems);
    F positive claims lexically traced into their cited paragraphs;
    I requires valid refs; S is counted and exempt."""
    out = dict(n=len(rows), F=0, I=0, S=0, f_traced=0, f_total=0,
               absence_supported=0, absence_contested=0,
               contested=[], bad_refs=0)
    n_p = len(paras)
    whole = " ".join(paras).lower()
    whole_st = set(_stems(whole))
    for r in rows:
        out[r["type"]] = out.get(r["type"], 0) + 1
        if any(x < 1 or x > n_p for x in r["refs"]):
            out["bad_refs"] += 1
        if r["type"] == "F":
            out["f_total"] += 1
            cst = [s2 for s2 in _stems(_NEG.sub(" ", r["claim"]))]
            if _NEG.search(r["claim"]):
                hits = [s2 for s2 in cst if s2 in whole_st]
                if hits:
                    # find the offending sentence for the evidence quote
                    sent = ""
                    for p in paras:
                        for s3 in re.split(r"(?<=[.!?])\s+", p):
                            if any(h in set(_stems(s3)) for h in hits):
                                sent = s3.strip()
                                break
                        if sent:
                            break
                    out["absence_contested"] += 1
                    out["contested"].append(
                        dict(claim=r["claim"][:90], hits=hits[:4],
                             evidence=sent[:140]))
                else:
                    out["absence_supported"] += 1
                    out["f_traced"] += 1
            else:
                tgt = r["refs"] if (r["refs"] and not r["all"])                     else list(range(1, n_p + 1))
                cited = " ".join(paras[i - 1] for i in tgt
                                 if 1 <= i <= n_p).lower()
                cst_set = set(_stems(cited))
                if cst and sum(1 for s2 in cst
                               if s2 in cst_set) >= max(
                                   1, len(cst) // 3):
                    out["f_traced"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--feed", required=True,
                    help="segment feed from segment_feed.py --emit-feed")
    ap.add_argument("--skip-write", action="store_true")
    ap.add_argument("--skip-judge", action="store_true")
    ap.add_argument("--writer-chars", type=int, default=6000,
                    help="truncation per anonymized summary in the "
                         "judge prompt")
    args = ap.parse_args()
    sid = args.story
    wsid, jsid = f"{sid}_sp", f"{sid}_judge"
    RUN_T0 = datetime.now().timestamp()

    title, source = load_source(args.dir, sid)
    feed = open(args.feed, encoding="utf-8").read().strip()
    fg = []
    sj = os.path.join(args.dir, f"{sid}_synthesis2.json")
    if os.path.exists(sj):
        fg = [r["concept"] for r in
              json.load(open(sj)).get("foreground", [])]
    print("=" * 78)
    print(f"BAKE-OFF  ::  {sid}  ::  {VERSION}")
    print(f"channel A (dropped facts): {', '.join(fg) or '(none found)'}")
    print(f"channel C: {feed.count(chr(10))} feed lines from "
          f"{args.feed}")

    # ---- stage 1: the writers -----------------------------------------
    paras = [p.strip() for p in re.split(r"\n\s*\n", source)
             if p.strip()]
    numbered = "\n\n".join(f"[p{i+1}] {p}"
                            for i, p in enumerate(paras))
    wprompt = (SP_DISCIPLINE + "\n\n"
               "SOURCE DOCUMENT (paragraphs numbered):\n"
               + numbered + "\n\n"
               + ("CHANNEL A -- source facts the reading layer drops:\n"
                  + ", ".join(fg) + "\n\n" if fg else "")
               + "CHANNEL C -- negative-space directions (each: a void "
               "concept with its measured consequence field and "
               "sentence-converged terms):\n" + feed)
    if not args.skip_write:
        print("\n-- stage 1: harvesting summary-plus from all models --")
        subprocess.run([sys.executable, "harvest_story.py",
                        "--sid", wsid, "--title", f"SP: {title}"[:70],
                        "--prompt", wprompt, "--outdir", args.dir,
                        "--force"])
    writers = read_responses(args.dir, wsid, FRONTIER)
    print(f"frontier outputs: {sorted(writers)}")
    if len(writers) < 3:
        sys.exit("fewer than 3 frontier outputs -- check the harvest")
    label_of = {m: LABELS[i] for i, m in enumerate(FRONTIER)
                if m in writers}
    model_of = {v: k for k, v in label_of.items()}

    # ---- stage 2: the panel -------------------------------------------
    blocks = []
    for m in FRONTIER:
        if m not in writers:
            continue
        prose = re.split(r"^LEDGER\s*:", writers[m],
                         flags=re.M)[0].strip()
        body = prose[:args.writer_chars]
        blocks.append(f"SUMMARY {label_of[m]}:\n{body}")
    jprompt = ("Five summaries of the same source document follow.\n\n"
               + "\n\n".join(blocks) + "\n\n" + JUDGE_RUBRIC)
    if not args.skip_judge:
        print("\n-- stage 2: harvesting panel scores --")
        subprocess.run([sys.executable, "harvest_story.py",
                        "--sid", jsid, "--title", f"J: {title}"[:70],
                        "--prompt", jprompt, "--outdir", args.dir,
                        "--force", "--min-chars", "15"])

    def parse_scores(text):
        got = {}
        for lab, val in re.findall(r"\b([A-E])\s*[:=]\s*([1-5])\b",
                                   text):
            got.setdefault(lab, int(val))   # first mention wins
        return got

    fj = read_responses(args.dir, jsid, FRONTIER)
    lj = read_responses(args.dir, jsid, LOCALS)
    if not args.skip_judge:
        for _pool in (fj, lj):
            for _m in list(_pool):
                _p = os.path.join(args.dir, f"{jsid}_{_m}.txt")
                if os.path.exists(_p) and os.path.getmtime(_p) < RUN_T0:
                    print(f"  STALE-EXCLUDED judge {_m} (mtime predates run)")
                    del _pool[_m]
    fro_scores = {m: parse_scores(t) for m, t in fj.items()}
    loc_scores = {m: parse_scores(t) for m, t in lj.items()}

    # ---- stage 3: the standings ----------------------------------------
    print("\n" + "-" * 78)
    print("PANEL MATRIX  (rows = judges, cols = anonymized writers; "
          "* = judge's own column, excluded from its row's use)")
    labs = [label_of[m] for m in FRONTIER if m in writers]
    print("             " + "   ".join(labs))
    for jm in FRONTIER:
        if jm not in fro_scores:
            continue
        row = []
        for lab in labs:
            v = fro_scores[jm].get(lab)
            mark = "*" if model_of.get(lab) == jm else " "
            row.append(f"{v if v else '-'}{mark} ")
        print(f"  {jm:<10} " + "  ".join(row))

    standings = []
    for m in FRONTIER:
        if m not in writers:
            continue
        lab = label_of[m]
        ex = [fro_scores[j][lab] for j in fro_scores
              if j != m and lab in fro_scores[j]]
        lo = [loc_scores[j][lab] for j in loc_scores
              if lab in loc_scores[j]]
        standings.append(dict(
            writer=m, label=lab,
            exself_mean=round(sum(ex) / len(ex), 2) if ex else None,
            exself_n=len(ex),
            local_mean=round(sum(lo) / len(lo), 2) if lo else None,
            chars=len(writers[m])))
    # ---- stage 2.5: mechanical claim audit (confidence earned) ----
    paras = [p.strip() for p in re.split(r"\n\s*\n", source)
             if p.strip()]
    audits = {}
    print("\nCLAIM AUDIT  (ledger parsed; F-claims traced; absence "
          "claims searched whole-doc)")
    for m in FRONTIER:
        if m not in writers:
            continue
        rows = parse_ledger(writers[m])
        a = audit_ledger(rows, paras)
        audits[m] = a
        tr = (f"{a['f_traced']}/{a['f_total']}" if a["f_total"]
              else "-")
        print(f"  {m:<10} ledger={a['n']:>2}  F/I/S="
              f"{a['F']}/{a['I']}/{a['S']}  F-traced={tr}  "
              f"absence ok/contested="
              f"{a['absence_supported']}/{a['absence_contested']}  "
              f"bad-refs={a['bad_refs']}")
        for c in a["contested"][:2]:
            print(f"      CONTESTED: \"{c['claim']}\" <- "
                  f"\"{c['evidence']}\"")
    for r in standings:
        a = audits.get(r["writer"], {})
        r["ledger_n"] = a.get("n", 0)
        r["f_traced"] = a.get("f_traced", 0)
        r["f_total"] = a.get("f_total", 0)
        r["absence_contested"] = a.get("absence_contested", 0)

    standings.sort(key=lambda r: -(r["exself_mean"] or 0))
    tie = (len(standings) > 1 and standings[0]["exself_mean"] is not None
           and standings[0]["exself_mean"] == standings[1]["exself_mean"])
    tag = ("THE WINNER (TIED at top; alphabetical display)" if tie
           else "THE WINNER")
    if tie:
        print("  TIE at the top of the standings")
    print("\nSTANDINGS  (frontier panel, ex-self; local panel as "
          "second opinion)")
    for r in standings:
        print(f"  {r['writer']:<10} [{r['label']}]  "
              f"ex-self {r['exself_mean']} (n={r['exself_n']})   "
              f"locals {r['local_mean']}   {r['chars']} ch")

    winner = standings[0]
    report = dict(harness="bakeoff", version=VERSION, story=sid,
                  generated=datetime.now().isoformat(timespec="seconds"),
                  provenance=dict(
                      discipline_sha=sha12(SP_DISCIPLINE.encode()),
                      rubric_sha=sha12(JUDGE_RUBRIC.encode()),
                      feed_sha=sha12(feed.encode()),
                      source_sha=sha12(source.encode()),
                      non_frozen_stages="writer harvest + judge harvest",
                      writer_chars=args.writer_chars,
                      label_map=label_of),
                  channel_a=fg, standings=standings, tie_at_top=tie,
                  claim_audits=audits,
                  frontier_scores=fro_scores, local_scores=loc_scores,
                  writers={m: writers[m] for m in writers})
    jpath = os.path.join(args.dir, f"{sid}_bakeoff_v12.json")
    json.dump(report, open(jpath, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"\nJSON -> {jpath} ({os.path.getsize(jpath)} bytes)")
    print("=" * 78)
    print(f"\n{'-'*78}\n{tag}  ::  {winner['writer']}  "
          f"(ex-self {winner['exself_mean']})\n{'-'*78}")
    print(writers[winner["writer"]])


if __name__ == "__main__":
    main()
