#!/usr/bin/env python3
"""
harvest_story.py -- pull ten model responses for one story.

Feed it any story (sid + title + prompt) and it writes the corpus files
the census / Summary Plus pipeline reads:

    {outdir}/{sid}_{model}.txt          one file per responding model
    {outdir}/_prompts.json              {sid: {title, prompt}}  (merged)

All clients are imported from magnum_opus_battery.MODELS -- zero
duplicated plumbing. Frontier callers read their API keys from the
environment exactly as the battery does; this script does not preflight
key names (it has not read all of them), it attempts each call and
reports the failure class if one lands.

Usage:
  # any new story
  python3 harvest_story.py --sid my_story --title "My story" \
      --prompt "Full prompt text..."

  # re-pull an existing battery story with the IDENTICAL anchor text,
  # written under a new sid so the frozen June corpus is never touched
  python3 harvest_story.py --from-battery altman_family --as altman_family_r2 \
      --outdir anamnesis_results/repull_20260709

  # subset of models / redo
  python3 harvest_story.py ... --models chatgpt,claude,hermes
  python3 harvest_story.py ... --force

Design rules (house style):
  * Never overwrites an existing response file unless --force. The June
    corpora are the reproducibility exhibit; they stay frozen.
  * A response under 50 chars is treated as empty/refused (battery
    convention): reported, not written. The census loader tolerates a
    missing model -- the group is just smaller, and the output says so.
  * _prompts.json is merged, never clobbered. Re-harvesting a sid whose
    stored prompt text differs requires --force, because that changes
    the ANCHOR and the anchor is a declared parameter.
  * Default title is sid with underscores as spaces, matching the
    re-anchored convention (greps match "altman family").
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid")
    ap.add_argument("--title")
    ap.add_argument("--prompt")
    ap.add_argument("--from-battery", dest="from_battery",
                    help="load title/prompt from magnum_opus_battery.PROMPTS[sid]")
    ap.add_argument("--as", dest="as_sid",
                    help="write under this sid instead (re-pulls: altman_family_r2)")
    ap.add_argument("--outdir",
                    help="default: anamnesis_results/fresh_YYYYMMDD")
    ap.add_argument("--models",
                    help="comma list; default all ten in battery MODELS")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing responses / changed anchor text")
    args = ap.parse_args()

    try:
        from magnum_opus_battery import MODELS, PROMPTS
    except Exception as e:
        sys.exit(f"cannot import magnum_opus_battery (the clients live there): {e}")

    # ── resolve the story ────────────────────────────────────────────
    if args.from_battery:
        if args.from_battery not in PROMPTS:
            sys.exit(f"'{args.from_battery}' not in battery PROMPTS. have: "
                     + ", ".join(sorted(PROMPTS)))
        pd = PROMPTS[args.from_battery]
        sid = args.from_battery
        title = pd.get("title") or sid.replace("_", " ")
        prompt = pd["prompt"]
    else:
        if not (args.sid and args.prompt):
            sys.exit("need --sid and --prompt (or --from-battery SID)")
        sid = args.sid
        prompt = args.prompt
        title = args.title or sid.replace("_", " ")
    if args.as_sid:
        sid = args.as_sid

    chosen = list(MODELS)
    if args.models:
        chosen = [m.strip() for m in args.models.split(",") if m.strip()]
        bad = [m for m in chosen if m not in MODELS]
        if bad:
            sys.exit(f"unknown models {bad}; battery has: {list(MODELS)}")

    outdir = Path(args.outdir or f"anamnesis_results/fresh_{time.strftime('%Y%m%d')}")
    outdir.mkdir(parents=True, exist_ok=True)

    # ── anchor bookkeeping (merged, guarded) ─────────────────────────
    pj_path = outdir / "_prompts.json"
    pj = {}
    if pj_path.exists():
        try:
            pj = json.load(open(pj_path))
        except Exception as e:
            sys.exit(f"{pj_path} unreadable ({e}) -- fix or move it first")
    if sid in pj and pj[sid].get("prompt", "") != prompt and not args.force:
        sys.exit(f"{pj_path} already holds '{sid}' with DIFFERENT prompt text.\n"
                 "That changes the anchor. --force only if you mean it.")
    pj[sid] = {"title": title, "prompt": prompt}
    json.dump(pj, open(pj_path, "w"), indent=2)
    print(f"anchor  : {sid} -> {pj_path}  ({len(prompt)} ch)")
    print(f"title   : {title!r}   (census prints ANCHOR CONTAINS at scoring time)")
    print(f"models  : {', '.join(chosen)}\n")

    # ── harvest ──────────────────────────────────────────────────────
    ok, skipped, failed = [], [], []
    for m in chosen:
        dest = outdir / f"{sid}_{m}.txt"
        if dest.exists() and not args.force:
            print(f"  {m:<12} EXISTS -- skipped (--force to redo)")
            skipped.append(m)
            continue
        print(f"  {m:<12} ", end="", flush=True)
        t0 = time.time()
        try:
            resp = MODELS[m](prompt)
        except Exception as e:
            print(f"FAILED {type(e).__name__}: {str(e)[:70]}")
            failed.append(m)
            continue
        dt = time.time() - t0
        if not resp or len(resp.strip()) < 50:
            print(f"EMPTY/refused ({dt:.0f}s) -- not written")
            failed.append(m)
            continue
        dest.write_text(resp, encoding="utf-8")
        print(f"ok {len(resp):>6} ch  ({dt:.0f}s)")
        ok.append(m)

    # ── report ───────────────────────────────────────────────────────
    print(f"\n{len(ok)}/{len(chosen)} responses written -> {outdir}/")
    if skipped:
        print("skipped (already on disk):", ", ".join(skipped))
    if failed:
        print("failed / empty           :", ", ".join(failed))
    print("\nnote: svd_census.py currently reads hardcoded DIRS; the census")
    print("surgery adds --dirs. Until it lands, append this outdir to DIRS")
    print("(one line) before scoring a fresh harvest.")


if __name__ == "__main__":
    main()
