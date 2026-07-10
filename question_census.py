#!/usr/bin/env python3
"""
question_census.py -- stratum 3 of the unsaid: the questions a document
raises but refuses to answer, measured at consensus.

Each of the ten models is independently asked what questions the
document leaves open. The answers are embedded (frozen bge), clustered
greedily and deterministically (fixed iteration order, declared cosine
threshold, no RNG), and a question is reported only when >= min-models
independent models asked it. One model's curiosity is an opinion; six
models' identical question is a measured gap.

For a competitor teardown this is the wedge report: their post raises
these questions and answers none of them.

Usage:
  python3 question_census.py --dir anamnesis_results/universal \
      --story prelude_2026 [--min-models 3] [--thresh 0.80] \
      [--skip-harvest]
Artifacts: {sid}_q_{model}.txt (raw), {sid}_qcensus.json (the census).
"""

VERSION = "question_census v1.0 2026-07-10"

import argparse
import glob
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime

import numpy as np

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)
logging.getLogger().setLevel(logging.WARNING)

MODEL_NAMES = ("chatgpt", "claude", "gemini", "deepseek", "grok",
               "mistral_22b", "mistral_7b", "qwen_14b", "hermes",
               "llama_8b")

Q_PROMPT = ("Read the following document carefully. List the specific "
            "questions a careful reader would be left with -- questions "
            "the document raises, implies, or makes urgent but does not "
            "answer. Output only the questions, one per line, ending "
            "each with a question mark. No preamble, no numbering, no "
            "commentary. Text: {text}")


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


def extract_questions(text):
    """Question lines: strip numbering/bullets, keep lines ending '?'."""
    out = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", raw).strip()
        if line.endswith("?") and 12 <= len(line) <= 240:
            out.append(line)
    return out


def build_embedder():
    from geometric_engine import get_engine
    eng = get_engine()

    def E(t):
        v = np.array(eng.model.encode(
            t if isinstance(t, list) else [t],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False))
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)
    logging.getLogger().setLevel(logging.WARNING)
    return E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--min-models", type=int, default=3)
    ap.add_argument("--thresh", type=float, default=0.80,
                    help="cosine threshold for question clustering")
    ap.add_argument("--skip-harvest", action="store_true")
    args = ap.parse_args()
    sid = args.story
    qsid = f"{sid}_q"

    title, source = load_source(args.dir, sid)
    print("=" * 78)
    print(f"QUESTION CENSUS  ::  {sid}  ::  {VERSION}")
    print(f"source: {len(source)} ch   thresh={args.thresh}  "
          f"min_models={args.min_models}")

    if not args.skip_harvest:
        print("\n-- harvesting question lists (10 models) --")
        subprocess.run([sys.executable, "harvest_story.py",
                        "--sid", qsid, "--title", f"Q: {title}"[:70],
                        "--prompt", Q_PROMPT.format(text=source),
                        "--outdir", args.dir])

    per_model = {}
    for f in sorted(glob.glob(os.path.join(args.dir, f"{qsid}_*.txt"))):
        mdl = os.path.basename(f)[len(qsid) + 1:-4]
        if mdl not in MODEL_NAMES:
            continue
        qs = extract_questions(open(f, encoding="utf-8",
                                    errors="replace").read())
        if qs:
            per_model[mdl] = qs
    n_models = len(per_model)
    all_q = [(m, i, q) for m in sorted(per_model)
             for i, q in enumerate(per_model[m])]
    print(f"\nraw questions: {len(all_q)} from {n_models} models")
    if not all_q:
        sys.exit("no parseable questions -- check the q harvest files")

    E = build_embedder()
    vecs = E([q for _, _, q in all_q])

    # deterministic greedy clustering: fixed order (model name, line
    # index), assign to first cluster whose centroid clears thresh,
    # else found a new cluster. No RNG anywhere.
    clusters = []   # dicts: idxs, models, centroid
    for k, (m, i, q) in enumerate(all_q):
        v = vecs[k]
        best, best_c = None, args.thresh
        for c in clusters:
            s = float(c["centroid"] @ v)
            if s >= best_c:
                best, best_c = c, s
        if best is None:
            clusters.append(dict(idxs=[k], models={m},
                                 centroid=v.copy()))
        else:
            best["idxs"].append(k)
            best["models"].add(m)
            stack = np.stack([vecs[j] for j in best["idxs"]])
            cen = stack.mean(0)
            best["centroid"] = cen / (np.linalg.norm(cen) + 1e-8)

    rows = []
    for c in clusters:
        reps = [all_q[j][2] for j in c["idxs"]]
        rep = min(reps, key=len)          # shortest phrasing = cleanest
        rows.append(dict(question=rep,
                         support=len(c["models"]),
                         models=sorted(c["models"]),
                         phrasings=len(reps),
                         variants=sorted(set(reps))[:6]))
    rows.sort(key=lambda r: (-r["support"], r["question"]))
    consensus = [r for r in rows if r["support"] >= args.min_models]

    print(f"clusters: {len(rows)} total, "
          f"{len(consensus)} at >= {args.min_models}-model consensus\n")
    print("THE UNANSWERED  (consensus questions this document raises "
          "and does not answer)")
    for r in consensus:
        print(f"  [{r['support']:>2}/{n_models}] {r['question']}")
    below = [r for r in rows if r["support"] < args.min_models]
    if below:
        print(f"\n  (below consensus: {len(below)} single-or-few-model "
              f"questions, kept in JSON)")

    report = dict(
        harness="question_census", version=VERSION, story=sid,
        generated=datetime.now().isoformat(timespec="seconds"),
        provenance=dict(source_sha=sha12(source.encode()),
                        thresh=args.thresh,
                        min_models=args.min_models,
                        n_models=n_models,
                        clustering="greedy deterministic, fixed order, "
                                   "no RNG"),
        consensus=consensus, all_clusters=rows,
        raw_counts={m: len(qs) for m, qs in per_model.items()})
    jpath = os.path.join(args.dir, f"{sid}_qcensus.json")
    json.dump(report, open(jpath, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"\nJSON -> {jpath} ({os.path.getsize(jpath)} bytes)")
    print("=" * 78)


if __name__ == "__main__":
    main()
