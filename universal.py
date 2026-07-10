#!/usr/bin/env python3
"""
universal.py -- one command, any text, full centipede.

    python3 universal.py --text-file article.txt
    python3 universal.py --text-file article.txt --sid my_story \
        --mode natural --targets secret,hidden --donut --armb-mode ray

Pipeline: slug a sid -> wrap the text in the declared prompt contract ->
harvest 10 model responses (harvest_story.py; EXISTS-skip makes reruns
idempotent, --force redoes) -> run centipede_v03 -> report where the
stdout capture and the webpage JSON landed.

Prompt contracts (verbatim; the whole contract lands in _prompts.json,
so provenance is total):
  tc      : 'The following is a document. Based only on the text
             provided, summarize its key claims. Text: {TEXT}'
            (the text-conditional frame: 9/10 compliance on jspace where
             the naturalistic frame drew refusals; stance mostly muted)
  natural : '{TEXT}\n\nSummarize the key facts of the above.'
            (stance-permissive: refusals and denials are data)

Declared limits, printed at preflight: bge-large truncates the anchor
VECTOR past ~512 tokens (the sentence lattice still covers the full
text; centipede prints the regime); frontier calls need keys in the
shell (`set -a; source /home/remvelchio/eigentrace/.env; set +a`);
local calls need Ollama on 127.0.0.1:11434. Dead callers degrade to
FAILED lines, never to silent holes -- the harvester's error-banner
gate keeps garbage out of the corpus.
"""

VERSION = "universal v1.0 2026-07-09"

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "/mnt/c/Users/M4ISI/eigentrace"
os.chdir(REPO)

TC_CONTRACT = ("The following is a document. Based only on the text "
               "provided, summarize its key claims. Text: {text}")
NAT_CONTRACT = "{text}\n\nSummarize the key facts of the above."


def slugify(s, maxlen=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    s = re.sub(r"_+", "_", s)[:maxlen].strip("_")
    return s or "untitled"


def preflight():
    print(f"[{VERSION}] preflight:")
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/version", timeout=3) as r:
            print(f"  ollama: UP ({r.read().decode()[:40]})")
    except Exception as e:
        print(f"  ollama: DOWN ({e}) -- local models will fail; "
              f"`nohup ollama serve >> tmp/logs/ollama.log 2>&1 &`")
    keys = sorted(k for k in os.environ if k.endswith("API_KEY"))
    print(f"  keys in shell: {', '.join(keys) if keys else 'NONE'} "
          f"(frontier callers fail without theirs; "
          f"source /home/remvelchio/eigentrace/.env)")


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text-file", help="path to the text to analyze")
    src.add_argument("--text", help="the text itself, inline")
    ap.add_argument("--sid", default="",
                    help="story id (default: slug of the title)")
    ap.add_argument("--title", default="",
                    help="short title (default: first ~8 words of text)")
    ap.add_argument("--mode", default="tc", choices=("tc", "natural"),
                    help="prompt contract (default tc)")
    ap.add_argument("--targets", default="",
                    help="comma list for the said census (default: none)")
    ap.add_argument("--outdir", default="anamnesis_results/universal")
    ap.add_argument("--voids-per-segment", type=int, default=4)
    ap.add_argument("--exclude", default="",
                    help="models to drop at scoring time (stance gating)")
    ap.add_argument("--donut", action="store_true")
    ap.add_argument("--armb-mode", default="ray", choices=("ray", "cone"))
    ap.add_argument("--force", action="store_true",
                    help="re-pull responses even if files exist")
    ap.add_argument("--skip-harvest", action="store_true",
                    help="score an existing corpus only")
    args = ap.parse_args()

    if args.text_file:
        text = open(args.text_file, encoding="utf-8",
                    errors="replace").read().strip()
    else:
        text = (args.text or "").strip()
    if len(text) < 200:
        sys.exit(f"text is {len(text)} chars -- too short to measure "
                 f"(need >= 200). Feed it a real document.")

    title = args.title.strip() or " ".join(text.split()[:8])
    sid = args.sid.strip() or slugify(title)
    prompt = (TC_CONTRACT if args.mode == "tc"
              else NAT_CONTRACT).format(text=text)

    preflight()
    print(f"  sid={sid}  mode={args.mode}  title={title[:60]!r}")
    print(f"  text: {len(text)} ch / {len(text.split())} words  "
          f"prompt: {len(prompt)} ch")

    if not args.skip_harvest:
        cmd = [sys.executable, "harvest_story.py", "--sid", sid,
               "--title", title, "--prompt", prompt,
               "--outdir", args.outdir]
        if args.force:
            cmd.append("--force")
        print(f"\n── harvest ({'forced' if args.force else 'EXISTS-skip'}) ──")
        hr = subprocess.run(cmd)
        if hr.returncode != 0:
            print(f"  harvest exit={hr.returncode} -- continuing to score "
                  f"whatever landed")
    else:
        print("\n── harvest skipped (--skip-harvest) ──")

    out_txt = os.path.join(args.outdir, f"{sid}_centipede.txt")
    cmd = [sys.executable, "centipede_v03.py", "--dir", args.outdir,
           "--story", sid, "--targets", args.targets,
           "--voids-per-segment", str(args.voids_per_segment),
           "--prompt-mode", args.mode, "--armb-mode", args.armb_mode]
    if args.exclude:
        cmd += ["--exclude", args.exclude]
    if args.donut:
        cmd.append("--donut")
    print(f"\n── centipede -> {out_txt} ──")
    with open(out_txt, "w", encoding="utf-8") as fh:
        cr = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    print(f"  centipede exit={cr.returncode}")

    json_path = os.path.join(args.outdir, f"{sid}_centipede.json")
    tail = []
    if os.path.exists(out_txt):
        tail = open(out_txt, encoding="utf-8",
                    errors="replace").read().splitlines()
    for line in tail:
        if line.startswith(("RESULT sha=", "JSON ->", "CENTIPEDE ",
                            "ANCHOR ")):
            print(f"  {line}")
    print("\nDONE.")
    print(f"  human report : {out_txt}")
    print(f"  webpage feed : {json_path}"
          + ("" if os.path.exists(json_path) else "  (MISSING -- see report)"))


if __name__ == "__main__":
    main()
