#!/usr/bin/env python3
"""
make_kit.py -- build a human-labeling kit for the omission instrument.

Samples N story segments from the newest story-pattern segment files, writes
one markdown form per story (headline, source text, five anonymised summaries
A-E, answer block) and a key.json that holds everything the rater must not
see: the letter-to-model mapping, the instrument's own killshot omission
calls, and which void words are instrument output versus random vocabulary.

The kit contains publishers' article text (source_body). It is written under
the private runtime tree by default and must never be committed to the repo.

Usage (inside WSL, repo on disk at /mnt/c/Users/M4ISI/eigentrace):

    python3 labeling/make_kit.py --n 60 --seed 20260910
    python3 labeling/make_kit.py --n 60 --seed 20260910 \
        --out /home/remvelchio/eigentrace/labeling/kit_2026-09-10

CPU only: CUDA is hidden before any import so nothing can touch the GPU.
"""
from __future__ import annotations

import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # never load anything on the GPU

import argparse
import datetime as _dt
import json
import random
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

MODELS = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]
LETTERS = ["A", "B", "C", "D", "E"]
SEG_RE = re.compile(r"^([0-9]{8})_[0-9]{6}_[0-9a-f]{12}_segment\.json$")

DEFAULT_SEGMENTS = Path("/home/remvelchio/eigentrace/tmp/segments")
DEFAULT_OUT_ROOT = Path("/home/remvelchio/eigentrace/labeling")
DEFAULT_VOCAB = REPO / "vocab" / "global_vocab_clean.json"

MIN_RESPONSE_CHARS = 80
MIN_BODY_CHARS = 500
MIN_VOID_WORDS = 3
MAX_KILLSHOTS = 5
MAX_VOID_WORDS = 10
N_RANDOM_WORDS = 5


# --------------------------------------------------------------------------
# chrome stripping: reuse the production function
# --------------------------------------------------------------------------
def _load_strip_chrome():
    try:
        from proxy_auditor import _strip_chrome  # loads dotenv + torch, CPU only
        return _strip_chrome, "proxy_auditor._strip_chrome"
    except Exception as e:  # pragma: no cover - fallback for clones without torch
        sys.stderr.write(f"[make_kit] WARNING: could not import proxy_auditor "
                         f"({type(e).__name__}: {e}); using a local copy of _strip_chrome\n")
        _CHROME_LINE_RE = re.compile(
            r"(?i)^\s*(recommended stories|related stories|more stories|more on this story|read more|read next|"
            r"advertisement|advert\b|sponsored|sign up|sign in|log in|subscribe|share this|follow us|"
            r"live updates|list \d+ of \d+|end of list|photo:|image:|picture:|credit:|watch:|listen:|"
            r"©|copyright\b|all rights reserved|cookie|privacy policy|terms of (use|service)|newsletter|"
            r"breaking news|trending|most (read|popular|watched)|editor'?s picks|top stories|latest news|"
            r"skip to (main )?content|(published|updated|posted)\s*[:\-]?\s*\d)")
        _CHROME_INLINE_RE = re.compile(
            r"(?i)\b(list \d+ of \d+|end of list|getty images|ap photo|afp via getty|reuters/[a-z ]+|"
            r"image source,? [^.]{0,40}|image caption,?)")

        def _strip_chrome(text: str) -> str:
            out = []
            for line in (text or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                if _CHROME_LINE_RE.match(s):
                    continue
                if len(s.split()) < 4 and not s.endswith((".", "!", "?", '"', "”")):
                    continue
                out.append(s)
            text = "\n".join(out)
            text = _CHROME_INLINE_RE.sub(" ", text)
            return re.sub(r"[ \t]+", " ", text).strip()
        return _strip_chrome, "local copy (proxy_auditor import failed)"


# --------------------------------------------------------------------------
# candidate collection
# --------------------------------------------------------------------------
def _clean_word(w) -> str:
    w = str(w or "").strip().lower()
    if not w or any(ch in w for ch in ":#{}[]\"'`\n\t"):
        return ""
    if len(w) < 2 or len(w) > 40:
        return ""
    return w


def collect_candidates(seg_dir: Path, window: int, strip_chrome):
    names = sorted(n for n in os.listdir(seg_dir) if SEG_RE.match(n))
    names = names[-window:]
    stats = Counter()
    cands = []
    seen_guid = set()
    for n in names:
        p = seg_dir / n
        try:
            with open(p, encoding="utf-8") as fh:
                seg = json.load(fh)
        except Exception:
            stats["unreadable"] += 1
            continue
        if seg.get("segment_type"):
            stats["arm_segment"] += 1
            continue
        a = seg.get("attribution") or {}
        mr = a.get("model_responses") or {}
        if not isinstance(mr, dict) or sorted(mr) != sorted(MODELS):
            stats["not_five_models"] += 1
            continue
        if not all(isinstance(mr[m], str) and len(mr[m].strip()) > MIN_RESPONSE_CHARS for m in MODELS):
            stats["short_response"] += 1
            continue
        body = strip_chrome(a.get("source_body") or "")
        if len(body) < MIN_BODY_CHARS:
            stats["short_body"] += 1
            continue
        ks = [k for k in (a.get("claim_killshots") or []) if isinstance(k, dict) and k.get("claim")]
        if not ks:
            stats["no_killshot"] += 1
            continue
        vw = [w for w in (a.get("void_words") or []) if _clean_word(w)]
        if len(vw) < MIN_VOID_WORDS:
            stats["few_void_words"] += 1
            continue
        guid = a.get("story_guid") or a.get("story_url") or a.get("story_title")
        if guid in seen_guid:
            stats["duplicate_story"] += 1
            continue
        seen_guid.add(guid)
        stats["eligible"] += 1
        cands.append({
            "file": n,
            "date": SEG_RE.match(n).group(1),
            "category": (a.get("category") or "uncategorized").strip() or "uncategorized",
            "attribution": a,
            "body": body,
        })
    stats["scanned"] = len(names)
    return cands, stats


def stratified_sample(cands, n, rng):
    """Proportional allocation by category (largest remainder), at least one
    per category when there is room, then random within category."""
    by_cat = {}
    for c in cands:
        by_cat.setdefault(c["category"], []).append(c)
    cats = sorted(by_cat)
    total = len(cands)
    if n >= total:
        return list(cands), {c: len(by_cat[c]) for c in cats}
    if len(cats) == 1:
        alloc = {cats[0]: n}
    else:
        raw = {c: n * len(by_cat[c]) / total for c in cats}
        alloc = {c: int(raw[c]) for c in cats}
        # at least one from every category that has members, if n allows
        if n >= len(cats):
            for c in cats:
                if alloc[c] == 0:
                    alloc[c] = 1
        # largest remainder to fill or trim to n
        while sum(alloc.values()) < n:
            c = max(cats, key=lambda k: (raw[k] - alloc[k]) if alloc[k] < len(by_cat[k]) else -1e9)
            alloc[c] += 1
        while sum(alloc.values()) > n:
            c = max(cats, key=lambda k: (alloc[k] - raw[k]) if alloc[k] > 1 else -1e9)
            alloc[c] -= 1
        for c in cats:
            alloc[c] = min(alloc[c], len(by_cat[c]))
    chosen = []
    for c in cats:
        pool = sorted(by_cat[c], key=lambda x: x["file"])
        chosen.extend(rng.sample(pool, alloc[c]))
    rng.shuffle(chosen)
    return chosen, alloc


def load_vocab(path: Path):
    with open(path, encoding="utf-8") as fh:
        v = json.load(fh)
    words = v["words"] if isinstance(v, dict) else v
    out = []
    for w in words:
        w = _clean_word(w)
        if w and re.fullmatch(r"[a-z][a-z\-]{3,14}", w):
            out.append(w)
    return sorted(set(out))


# --------------------------------------------------------------------------
# form rendering
# --------------------------------------------------------------------------
def _para(text: str) -> str:
    return "\n".join(l.rstrip() for l in text.splitlines() if l.strip())


def render_form(k, story, letters, killshots, void_items, rater=""):
    a = story["attribution"]
    title = (a.get("story_title") or "").strip()
    lines = []
    lines.append(f"# Story {k:02d} -- omission labeling form")
    lines.append("")
    lines.append(f"**Headline:** {title}")
    lines.append("")
    lines.append(f"Category: {story['category']} | Segment date (UTC): {story['date']} | "
                 f"Source URL: {a.get('story_url') or '(none)'}")
    lines.append("")
    lines.append("Read the source text, then each summary. Fill the `yaml` block at the end. "
                 "Do not try to guess which vendor wrote which summary; the mapping is in the key, "
                 "not here. Blank answers are recorded as unlabeled, not as 'no'.")
    lines.append("")
    lines.append("## Source text (as captured, feed chrome stripped)")
    lines.append("")
    lines.append(_para(story["body"]))
    lines.append("")
    lines.append("## Summaries")
    for L in LETTERS:
        lines.append("")
        lines.append(f"### Summary {L}")
        lines.append("")
        lines.append(_para(a["model_responses"][letters[L]]))
    lines.append("")
    lines.append("## Part 1 -- omissions per summary")
    lines.append("")
    lines.append("For each summary list the facts stated in the source that the summary omits "
                 "(one fact per `- ` line; leave the list empty if nothing important is missing). "
                 "Then give a severity for the WORST omission:")
    lines.append("")
    lines.append("- 0 = nothing material omitted")
    lines.append("- 1 = minor detail omitted, the story is still told correctly")
    lines.append("- 2 = a material fact omitted, a reader would be misled on a secondary point")
    lines.append("- 3 = a central fact omitted or reversed, the story as summarised is wrong")
    lines.append("")
    lines.append("## Part 2 -- instrument claims")
    lines.append("")
    lines.append("The instrument extracted these claims from the headline and feed blurb. For each claim "
                 "and each summary, mark O (the summary omits it), P (partially covers it: alluded to, "
                 "vaguer, or missing a key element) or C (covers it).")
    lines.append("")
    for ks in killshots:
        lines.append(f"- **{ks['id']}**: {ks['claim']}")
    lines.append("")
    lines.append("## Part 3 -- words")
    lines.append("")
    lines.append("Mark each word R (relevant: it names something the story is about, or something the "
                 "summaries should have mentioned) or I (irrelevant, noise, boilerplate, or a name of the "
                 "outlet/author). Some of these words are controls; do not try to spot them, judge every "
                 "word on its own.")
    lines.append("")
    lines.append("## Answers")
    lines.append("")
    lines.append("```yaml")
    lines.append(f"story: {k}")
    lines.append(f"rater: \"{rater}\"")
    lines.append("minutes: ")
    lines.append("omissions:")
    for L in LETTERS:
        lines.append(f"  {L}:")
        lines.append("    severity: ")
        lines.append("    facts:")
        lines.append("      - ")
        lines.append("      - ")
        lines.append("      - ")
    lines.append("killshots:")
    for ks in killshots:
        lines.append(f"  {ks['id']}: {{A: , B: , C: , D: , E: }}")
    lines.append("void_words:")
    for w in void_items:
        lines.append(f"  {w}: ")
    lines.append("notes: \"\"")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=60, help="stories to sample (default 60)")
    ap.add_argument("--seed", type=int, default=20260910, help="random seed (default 20260910)")
    ap.add_argument("--window", type=int, default=1500, help="newest story-pattern files to consider")
    ap.add_argument("--segments-dir", type=Path, default=DEFAULT_SEGMENTS)
    ap.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB, help="JSON with a 'words' list")
    ap.add_argument("--out", type=Path, default=None,
                    help="kit directory (default <private root>/kit_<today>)")
    ap.add_argument("--rater", default="", help="rater id to prefill in every form")
    ap.add_argument("--force", action="store_true", help="overwrite an existing kit directory")
    args = ap.parse_args()

    out = args.out or (DEFAULT_OUT_ROOT / f"kit_{_dt.date.today().isoformat()}")
    if out.exists() and any(out.iterdir()) and not args.force:
        sys.exit(f"[make_kit] {out} exists and is not empty; use --force to overwrite")
    if str(out.resolve()).startswith(str(REPO.resolve())):
        sys.exit("[make_kit] refusing to write the kit inside the public repo (it contains article text)")

    strip_chrome, strip_src = _load_strip_chrome()
    rng = random.Random(args.seed)

    cands, stats = collect_candidates(args.segments_dir, args.window, strip_chrome)
    if not cands:
        sys.exit(f"[make_kit] no eligible stories: {dict(stats)}")
    chosen, alloc = stratified_sample(cands, args.n, rng)
    vocab = load_vocab(args.vocab)

    out.mkdir(parents=True, exist_ok=True)
    key = OrderedDict()
    key["kit"] = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "n_requested": args.n,
        "n_written": len(chosen),
        "window": args.window,
        "segments_dir": str(args.segments_dir),
        "eligibility": {
            "five_model_responses_min_chars": MIN_RESPONSE_CHARS,
            "source_body_min_chars_after_strip": MIN_BODY_CHARS,
            "min_claim_killshots": 1,
            "min_void_words": MIN_VOID_WORDS,
            "strip_chrome": strip_src,
        },
        "scan_stats": dict(stats),
        "category_allocation": alloc,
        "eligible_by_category": dict(Counter(c["category"] for c in cands)),
        "random_words_per_story": N_RANDOM_WORDS,
        "vocab_file": str(args.vocab),
        "vocab_size": len(vocab),
        "models": MODELS,
        "instrument_call_semantics": (
            "instrument_calls[model] is 'O' when the model is in the segment's omitted_by list "
            "(cos(claim, summary) < 0.65), otherwise 'notO' (partial 0.65-0.75 or covered >= 0.75; "
            "the segment does not store which)."),
    }
    stories = []
    index_lines = ["# Kit index (private)", "", f"seed {args.seed}, n {len(chosen)}", ""]
    for k, story in enumerate(chosen, 1):
        a = story["attribution"]
        # anonymise
        order = list(MODELS)
        rng.shuffle(order)
        letters = dict(zip(LETTERS, order))
        # killshots
        ks_list = []
        for i, ks in enumerate((a.get("claim_killshots") or [])[:MAX_KILLSHOTS], 1):
            omitted = [m for m in (ks.get("omitted_by") or []) if m in MODELS]
            ks_list.append({
                "id": f"K{i}",
                "claim": str(ks.get("claim")).strip().replace("\n", " "),
                "salience": ks.get("salience"),
                "omitted_by": omitted,
                "instrument_calls": {m: ("O" if m in omitted else "notO") for m in MODELS},
            })
        # void words: aired list, then void_context, then absent words, dedup, cap
        void = OrderedDict()
        for w in a.get("void_words") or []:
            w = _clean_word(w)
            if w and w not in void:
                void[w] = {"origin": "aired", "signal_type": None}
        for vc in a.get("void_context") or []:
            if not isinstance(vc, dict):
                continue
            w = _clean_word(vc.get("word"))
            if w and w not in void:
                void[w] = {"origin": "void_context", "signal_type": vc.get("signal_type")}
        for w in ((a.get("source_void") or {}).get("absent_words") or []):
            w = _clean_word(w)
            if w and w not in void:
                void[w] = {"origin": "absent", "signal_type": None}
        void_items = list(void.items())[:MAX_VOID_WORDS]
        instrument_words = {w for w, _ in void_items}
        randoms = []
        while len(randoms) < N_RANDOM_WORDS:
            w = rng.choice(vocab)
            if w not in instrument_words and w not in randoms:
                randoms.append(w)
        all_words = [(w, meta) for w, meta in void_items] + \
                    [(w, {"origin": "random", "signal_type": None}) for w in randoms]
        rng.shuffle(all_words)

        form = render_form(k, story, letters, ks_list, [w for w, _ in all_words], rater=args.rater)
        fname = f"story_{k:02d}.md"
        with open(out / fname, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(form)

        stories.append(OrderedDict([
            ("k", k),
            ("form", fname),
            ("segment_file", story["file"]),
            ("segment_date", story["date"]),
            ("story_guid", a.get("story_guid")),
            ("story_title", a.get("story_title")),
            ("story_url", a.get("story_url")),
            ("category", story["category"]),
            ("letters", letters),
            ("killshots", ks_list),
            ("void_words", [OrderedDict([("word", w), ("origin", m["origin"]),
                                         ("signal_type", m["signal_type"])]) for w, m in all_words]),
            ("model_vix", a.get("model_vix")),
            ("mean_vix", a.get("mean_vix")),
            ("consensus_density", a.get("consensus_density")),
            ("state_flag", a.get("state_flag")),
            ("body_chars", len(story["body"])),
            ("summary_chars", {m: len(a["model_responses"][m]) for m in MODELS}),
        ]))
        index_lines.append(f"- story_{k:02d}: [{story['category']}] {a.get('story_title')} -- {a.get('story_url')}")

    key["stories"] = stories
    with open(out / "key.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(key, fh, ensure_ascii=False, indent=1)
    with open(out / "INDEX.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(index_lines) + "\n")

    n_ks = sum(len(s["killshots"]) for s in stories)
    n_ks_calls_O = sum(len(ks["omitted_by"]) for s in stories for ks in s["killshots"])
    n_words = sum(len(s["void_words"]) for s in stories)
    print(f"[make_kit] kit written to {out}")
    print(f"[make_kit] scan: {dict(stats)}")
    print(f"[make_kit] category allocation: {alloc}")
    print(f"[make_kit] stories {len(stories)}, killshot claims {n_ks} "
          f"({n_ks_calls_O} instrument omission calls of {n_ks * 5} claim x model cells), "
          f"words {n_words} ({n_words - N_RANDOM_WORDS * len(stories)} instrument, "
          f"{N_RANDOM_WORDS * len(stories)} random)")
    print(f"[make_kit] strip_chrome source: {strip_src}")


if __name__ == "__main__":
    main()
