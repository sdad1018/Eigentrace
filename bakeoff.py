#!/usr/bin/env python3
"""
bakeoff.py -- the double-plus-good bake-off: five frontier models write
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

VERSION = "bakeoff v1.0 2026-07-10"

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
    "leaves unresolved."
)

JUDGE_RUBRIC = (
    "Score each summary 1-5 for INSIGHT:\n"
    "5 = surfaces non-obvious, source-grounded structure a plain "
    "summary misses; 4 = several real observations beyond "
    "restatement; 3 = competent restatement plus one real "
    "observation; 2 = pure restatement; 1 = restatement with errors "
    "or invention.\n"
    "Output EXACTLY one line, nothing else: A:n B:n C:n D:n E:n"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--feed", required=True,
                    help="segment feed from segment_feed.py --emit-feed")
    ap.add_argument("--skip-write", action="store_true")
    ap.add_argument("--skip-judge", action="store_true")
    ap.add_argument("--writer-chars", type=int, default=1900,
                    help="truncation per anonymized summary in the "
                         "judge prompt")
    args = ap.parse_args()
    sid = args.story
    wsid, jsid = f"{sid}_sp", f"{sid}_judge"

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
    wprompt = (SP_DISCIPLINE + "\n\n"
               "SOURCE DOCUMENT:\n" + source + "\n\n"
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
        body = writers[m][:args.writer_chars]
        blocks.append(f"SUMMARY {label_of[m]}:\n{body}")
    jprompt = ("Five summaries of the same source document follow.\n\n"
               + "\n\n".join(blocks) + "\n\n" + JUDGE_RUBRIC)
    if not args.skip_judge:
        print("\n-- stage 2: harvesting panel scores --")
        subprocess.run([sys.executable, "harvest_story.py",
                        "--sid", jsid, "--title", f"J: {title}"[:70],
                        "--prompt", jprompt, "--outdir", args.dir,
                        "--force"])

    def parse_scores(text):
        got = {}
        for lab, val in re.findall(r"\b([A-E])\s*[:=]\s*([1-5])\b",
                                   text):
            got.setdefault(lab, int(val))   # first mention wins
        return got

    fj = read_responses(args.dir, jsid, FRONTIER)
    lj = read_responses(args.dir, jsid, LOCALS)
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
    standings.sort(key=lambda r: -(r["exself_mean"] or 0))
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
                      label_map=label_of),
                  channel_a=fg, standings=standings,
                  frontier_scores=fro_scores, local_scores=loc_scores,
                  writers={m: writers[m] for m in writers})
    jpath = os.path.join(args.dir, f"{sid}_bakeoff.json")
    json.dump(report, open(jpath, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"\nJSON -> {jpath} ({os.path.getsize(jpath)} bytes)")
    print("=" * 78)
    print(f"\n{'-'*78}\nTHE WINNER  ::  {winner['writer']}  "
          f"(ex-self {winner['exself_mean']})\n{'-'*78}")
    print(writers[winner["writer"]])


if __name__ == "__main__":
    main()
