#!/usr/bin/env python3
"""
bite.py v0.2 -- the centipede's sixth stage: confrontation.

Two styles, one flag:

  --style revise   (DEFAULT) Production SP's battle-tested format, copied
                   from batch_producer.generate_summary_plus and upgraded
                   with full source grounding (production grounds on the
                   headline only). One-on-one framing, labeled channels,
                   inline skip permission, faithfulness rail. No verdicts
                   demanded; adoption is inferred from what the revision
                   actually uses, scored assertion-vs-refusal by
                   confront10.classify_word_use.

  --style verdict  v0.1 behavior: per-word APPLIES / DOES NOT APPLY /
                   UNCLEAR rulings plus optional revision. Kept for
                   format-effect comparisons; writes to the original
                   _take2.txt names so cached runs stay valid.

Outputs:
  {dir}/{sid}_{model}_take2r.txt     revise-style responses
  {dir}/{sid}_{model}_take2.txt      verdict-style responses (v0.1 name)

Usage:
  python3 bite.py --dir anamnesis_results/universal --story claude_jspace_tc \
      --voids anthropomorphic,skynet,hyperspace \
      --consequences embodiment,cybernetics > bite_out.txt 2>&1
"""

import argparse
import glob
import json
import os
import re
import sys

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)

MODEL_NAMES = ("chatgpt", "claude", "gemini", "deepseek", "grok",
               "mistral_22b", "mistral_7b", "qwen_14b", "hermes", "llama_8b")

REVISE_TEMPLATE = """Here is a news item and your earlier summary of it.

News item: {prompt}

Your summary: {summary}

Independent geometric readings of this item's negative space surfaced
concepts your summary did not use:
{channel_block}

Write one tighter, more vivid 3-4 sentence summary that works in any of
these concepts you judge genuinely relevant (skip any that are not).
Stay faithful to the news item - do not assert anything it does not
support.
"""

VERDICT_TEMPLATE = """You previously summarized a news item. Here is the item again:

{prompt}

Your summary was:

{summary}

A cross-model analysis surfaced the following concepts as semantically
close to the story yet absent from the summaries analyzed:
{channel_block}

Treat every listed word as a DIRECTION to evaluate, not a word to insert.
For EACH word above, answer on its own line in exactly this form:
  <word>: APPLIES | DOES NOT APPLY | UNCLEAR -- one sentence of reasoning.
A word only APPLIES if the story's own content genuinely supports it;
do not force anything.

Then, if and only if some words apply, write "REVISED SUMMARY:" on its
own line followed by a revised 3-5 sentence summary that incorporates
only the applicable concepts. If none apply, write "NO REVISION NEEDED."
"""


def load(dirpath, sid):
    pj = json.load(open(os.path.join(dirpath, "_prompts.json")))
    meta = pj.get(sid) or sys.exit(f"'{sid}' not in _prompts.json")
    resp = {}
    for f in glob.glob(os.path.join(dirpath, f"{sid}_*.txt")):
        mdl = os.path.basename(f)[len(sid) + 1:-4]
        if mdl in MODEL_NAMES:
            resp[mdl] = open(f, encoding="utf-8", errors="replace").read().strip()
    return meta["prompt"], resp


def channel_block(voids, cons):
    lines = []
    if voids:
        lines.append("- Cross-method voids (surfaced by multiple detection "
                     "methods): " + ", ".join(voids))
    if cons:
        lines.append("- Consequence raycast (those directions, extended): "
                     + ", ".join(cons))
    return "\n".join(lines)


def verdict_for(word, text):
    for line in text.splitlines():
        if re.search(r"\b" + re.escape(word[:9]), line, re.I):
            m = re.search(r"(DOES NOT APPLY|APPLIES|UNCLEAR)", line, re.I)
            if m:
                return {"APPLIES": "A", "DOES NOT APPLY": "N",
                        "UNCLEAR": "U"}[m.group(1).upper()]
    return "?"


def present(word, text):
    return bool(re.search(r"\b" + re.escape(word[:9]), text, re.I))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--voids", required=True)
    ap.add_argument("--consequences", default="")
    ap.add_argument("--style", choices=("revise", "verdict"), default="revise")
    ap.add_argument("--models", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    voids = [w.strip() for w in args.voids.split(",") if w.strip()]
    cons = [w.strip() for w in args.consequences.split(",") if w.strip()]
    words = voids + cons
    suffix = "_take2r.txt" if args.style == "revise" else "_take2.txt"
    template = REVISE_TEMPLATE if args.style == "revise" else VERDICT_TEMPLATE

    from magnum_opus_battery import MODELS
    try:
        from confront10 import classify_word_use
    except Exception:
        classify_word_use = None

    prompt, resp = load(args.dir, args.story)
    chosen = [m for m in resp if not args.models or m in args.models.split(",")]

    print("=" * 74)
    print(f"BITE v0.2  style={args.style}  story={args.story}  "
          f"models={len(chosen)}")
    print(f"payload: voids={voids}  consequences={cons}")
    print("=" * 74)

    grid = {}
    for m in chosen:
        dest = os.path.join(args.dir, f"{args.story}_{m}{suffix}")
        if os.path.exists(dest) and not args.force:
            t2 = open(dest, encoding="utf-8", errors="replace").read()
            print(f"\n── {m} (cached)")
        else:
            bp = template.format(prompt=prompt, summary=resp[m],
                                 channel_block=channel_block(voids, cons))
            print(f"\n── {m} ...", flush=True)
            try:
                t2 = MODELS[m](bp)
            except Exception as e:
                print(f"   FAILED {type(e).__name__}: {str(e)[:70]}")
                continue
            if not t2 or len(t2.strip()) < 40 or t2.lstrip().startswith("[BLOCKED"):
                print("   EMPTY/banner -- not written")
                continue
            open(dest, "w", encoding="utf-8").write(t2)
        row = {}
        for w in words:
            v = verdict_for(w, t2) if args.style == "verdict" else "-"
            p = "+" if present(w, t2) else " "
            q = ""
            if classify_word_use:
                try:
                    r = classify_word_use(w, t2)
                    q = {"adopted": "adopt", "quarantined": "quara"}.get(r, "")
                except Exception:
                    q = ""
            row[w] = (v, p, q)
            print(f"   {w:<16} {'verdict=' + v + '  ' if v != '-' else ''}"
                  f"present={'yes' if p == '+' else 'no ':<4} {q}")
        grid[m] = row

    print(f"\nGRID ({args.style}):  A/N/U/?=verdict  +=word present  "
          "a/q=classify_word_use")
    print("  " + "".ljust(13) + "".join(f"{w[:10]:>12}" for w in words))
    for m in chosen:
        if m not in grid:
            continue
        cells = ""
        for w in words:
            v, p, q = grid[m][w]
            tag = (v if v != "-" else "") + p + (q[:1] if q else "")
            cells += tag.rjust(12)
        print(f"  {m:<13}{cells}")

    print("\nPER-WORD TOTALS:")
    for w in words:
        rows = [grid[m][w] for m in grid]
        pres = sum(1 for v, p, q in rows if p == "+")
        adop = sum(1 for v, p, q in rows if q == "adopt")
        quar = sum(1 for v, p, q in rows if q == "quara")
        extra = ""
        if args.style == "verdict":
            vs = [v for v, p, q in rows]
            extra = (f"  A={vs.count('A')} N={vs.count('N')} "
                     f"U={vs.count('U')} ?={vs.count('?')}")
        print(f"  {w:<16} present={pres} adopted={adop} quarantined={quar}"
              f"{extra}")
    print("=" * 74)


if __name__ == "__main__":
    main()
