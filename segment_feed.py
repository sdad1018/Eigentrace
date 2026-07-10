#!/usr/bin/env python3
"""
segment_feed.py -- the centipede, segment-enumerated, plus the feed
for the frontier bake-off.

Layout per the anatomy canon (CENTIPEDE_MATH.md): sections are the five
math classes; within each section, every method-leg in turn; within
each leg, its top voids; each void = one SEGMENT, numbered globally,
carrying both legs:

  SEGMENT n · method (Section) · void
     flat  > story-flavored consequence terminals (253K)
     spiral> sentence-converged terms (50K)

Filters: no title words, no close alternates (stem-family match or
string containment, len >= 4, declared and deterministic -- an
embedding-cosine gate is a queued upgrade). Repeated stems across
segments are cross-referenced, and CLASS-CONSENSUS (distinct math
classes per stem) prints as the footer: independent math landing on
the same word is the notable event; raw leg-count is not.

--emit-feed FILE writes the plain-text segment feed for embedding in
the bake-off prompt (Summary-Plus prompt lineage to be wired verbatim
after the SP prompt recon).

  python3 segment_feed.py anamnesis_results/universal/prelude_2026_centipede.json \
      [--per-method 5] [--emit-feed prelude_feed.txt] [--title "..."]
"""

VERSION = "segment_feed v1.0 2026-07-10"

import argparse
import json
import re

try:
    from preservation_core import porter_stem
except Exception:
    porter_stem = lambda w: w.lower()

SECTION_OF = {
    "said": "Centroid", "gap->local": "Centroid",
    "gap->frontier": "Centroid", "centroid_surface": "Centroid",
    "logos_v9": "Gradient", "logos_v10": "Gradient",
    "null": "Spectral/SVD",
    "lexcross": "Counting",
    "donut": "Ring",
}
SECTION_ORDER = ["Centroid", "Gradient", "Spectral/SVD",
                 "Counting", "Ring"]
ROMAN = {s: r for s, r in zip(SECTION_ORDER,
                              ["I", "II", "III", "IV", "V"])}


def stem_of(w):
    return porter_stem(str(w).split()[0]) if " " in str(w) \
        else porter_stem(str(w))


def title_words(title):
    return [w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z'\-]+", title)
            if len(w) > 2]


def blocked_by_title(word, twords, tstems):
    wl = str(word).lower()
    ws = stem_of(word)
    if ws in tstems:
        return True
    for t in twords:
        if len(t) >= 4 and len(wl) >= 4 and (t in wl or wl in t):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--per-method", type=int, default=5)
    ap.add_argument("--title", default="",
                    help="override title (default: headline up to "
                         "first '. ')")
    ap.add_argument("--emit-feed", default="",
                    help="write the plain-text segment feed here")
    ap.add_argument("--terms", type=int, default=4,
                    help="terms shown per leg")
    args = ap.parse_args()

    rep = json.load(open(args.json_path, encoding="utf-8"))
    headline = (rep.get("anchor") or {}).get("headline", "")
    title = args.title or headline.split(". ")[0]
    twords = title_words(title)
    tstems = {porter_stem(w) for w in twords}

    # order legs: section order, then JSON order within section
    legs = []
    for seg in rep.get("segments", []):
        fam = seg.get("name", "?").split("/")[0]
        sec = SECTION_OF.get(fam, "Centroid")
        legs.append((SECTION_ORDER.index(sec), sec, seg))
    legs.sort(key=lambda t: t[0])

    print("=" * 74)
    print(f"THE CENTIPEDE, SEGMENT-ENUMERATED  ::  "
          f"{rep.get('story','?')}  ::  {VERSION}")
    print(f"title filter: {', '.join(twords)}  "
          f"(stem + containment; no close alternates)")
    print("=" * 74)

    n = 0
    cur_sec = None
    first_seen = {}          # stem -> segment number
    stem_secs = {}           # stem -> set of sections
    stem_word = {}
    feed_lines = []
    dropped_title = 0

    for _, sec, seg in legs:
        name = seg.get("name", "?")
        arms = seg.get("arms", [])
        shown = 0
        rows = []
        for arm in arms:
            w = arm.get("void", "")
            if blocked_by_title(w, twords, tstems):
                dropped_title += 1
                continue
            rows.append(arm)
            shown += 1
            if shown >= args.per_method:
                break
        if not rows:
            continue
        if sec != cur_sec:
            cur_sec = sec
            print(f"\n{'═'*8} SECTION {ROMAN[sec]} · "
                  f"{sec.upper()} {'═'*(46-len(sec))}")
        print(f"  ── {name}")
        for arm in rows:
            n += 1
            w = arm.get("void", "")
            st = arm.get("stem", stem_of(w))
            A = [t for t in (arm.get("A", {}).get("terms") or [])
                 ][:args.terms]
            B = [t for t in (arm.get("B", {}).get("terms") or [])
                 ][:args.terms]
            fc = arm.get("field_cos")
            xref = ""
            if st in first_seen:
                xref = f"   (also §{first_seen[st]})"
            else:
                first_seen[st] = n
                stem_word[st] = w
            stem_secs.setdefault(st, set()).add(sec)
            fct = f"  cos={fc:.2f}" if isinstance(fc, (int, float)) \
                else ""
            print(f"  §{n:<3} {w}{xref}")
            print(f"       flat  ▸ {', '.join(A) or '—'}")
            print(f"       spiral▸ {', '.join(B) or '—'}{fct}")
            feed_lines.append(
                f"VOID '{w}' [{name} | {sec}]"
                f" -- consequence field: {', '.join(A) or '-'}"
                f" | converged: {', '.join(B) or '-'}")

    print(f"\n{'─'*74}")
    cc = sorted(((len(s), st) for st, s in stem_secs.items()
                 if len(s) >= 2), reverse=True)
    print(f"CLASS-CONSENSUS  (independent math classes landing on one "
          f"stem -- the notable event)")
    if cc:
        for k, st in cc:
            secs = ", ".join(sorted(stem_secs[st]))
            print(f"  {stem_word[st]:<18} {k} classes  ({secs})")
    else:
        print("  (none at >= 2 classes -- every stem is single-method)")
    print(f"segments: {n}   title-blocked voids: {dropped_title}   "
          f"unique stems: {len(first_seen)}")

    if args.emit_feed:
        with open(args.emit_feed, "w", encoding="utf-8") as f:
            f.write(f"# segment feed :: {rep.get('story','?')} :: "
                    f"{n} segments\n")
            f.write("\n".join(feed_lines) + "\n")
        print(f"feed -> {args.emit_feed} ({n} segments, "
              f"bake-off ready)")
    print("=" * 74)


if __name__ == "__main__":
    main()
