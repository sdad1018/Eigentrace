#!/usr/bin/env python3
"""
synthesis.py -- stage seven of the universal centipede: the anti-summary.

Thesis: what the article says (TF-IDF, retained by the AI layer).
Antithesis: what the AI reading layer erases (two measured classes):
  FOREGROUND  concepts the SOURCE makes salient that every summary drops
              (high VF-IDF: void_freq x inverse-fidelity, per the
              published spec -- computed inline on frozen bge embeddings)
  EXPAND      adjacent concepts the models never reach for this topic
              (centipede shared-core voids: stems surfaced by >= N legs)
Synthesis: Claude rewrites the article to carry BOTH -- directed to use
as many of the candidates as possible -- under one hard rail: invent no
facts. Whether the rail holds is not assumed; it is AUDITED: every run
plants deterministic off-domain control words in the candidate list,
unlabeled. Claude skipping them under max-inclusion pressure is the
proof of judgment; adopting one is a COMPLIANCE FLAG stamped on the
output (ledger #36 made this mandatory: revise-format adopted planted
junk 6/9 when unaudited).

Honesty stamp: the Claude call is the ONE non-frozen stage in the
pipeline. Candidate surfacing is frozen arithmetic; re-measurement is
frozen arithmetic; the writing between them is a model, declared with
its id and temperature. --verify closes the loop: re-harvest the
synthesis through all ten models and report before/after VF-IDF on the
same concepts. A concept whose VF-IDF collapses became un-droppable;
one that stays high is model-resistant -- either way, a number.

Usage:
  python3 synthesis.py --dir anamnesis_results/universal --story prelude_2026
  python3 synthesis.py --dir ... --story ... --verify     # full closed loop
"""

VERSION = "synthesis v1.1 2026-07-10"

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

import numpy as np

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)

try:
    from preservation_core import (porter_stem, term_frequencies,
                                   vf_idf as pc_vfidf, stem_set,
                                   STOPWORDS as PC_STOP)
except Exception:
    porter_stem = lambda w: w.lower()
    term_frequencies = None
    pc_vfidf = None
    stem_set = lambda t: frozenset(porter_stem(w) for w in
                                   _TOK.findall(t.lower()) if len(w) > 2)
    PC_STOP = frozenset()

# synthesis-side connective filter (declared): PC_STOP is only 110 words
# and passes 'while'/'although'/etc; candidates must be contentful.
SYNTH_STOP = frozenset(PC_STOP) | frozenset(
    "while although though however despite whether since also will "
    "would could should must may might shall based including according "
    "expected likely typically currently".split())

import logging
logging.getLogger().setLevel(logging.WARNING)

_TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")

# deterministic planted controls: clearly off-domain concreta. Selection
# is keyed by sha of the sid -- no RNG anywhere (house rule).
CONTROL_LEXICON = ["trombone", "marmalade", "zeppelin", "origami",
                   "lighthouse", "porcelain", "accordion", "tapestry",
                   "gondola", "terrarium", "metronome", "sundial"]

MODEL_NAMES = ("chatgpt", "claude", "gemini", "deepseek", "grok",
               "mistral_22b", "mistral_7b", "qwen_14b", "hermes", "llama_8b")


def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def content_words(text):
    return [w.lower() for w in _TOK.findall(text) if len(w) > 2]


def sentences(src):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", src)
            if len(s.strip()) > 15]


def is_junk(term):
    t = str(term).strip()
    if len(t) < 3 or not t[:1].isalpha():
        return True
    if "..." in t or "\u2026" in t or len(t.split()) > 4:
        return True
    if re.search(r"\d\d\d", t):
        return True
    return False


def stem_of(w):
    return porter_stem(str(w).split()[0]) if " " in str(w) else porter_stem(str(w))


def word_present(word, text):
    """Word-boundary presence of word (first token if multiword) or its
    stem-family in text. #24-safe."""
    tl = text.lower()
    head = str(word).lower().split()[0]
    if re.search(r"\b" + re.escape(str(word).lower()) + r"\b", tl):
        return True
    st = porter_stem(head)
    return any(porter_stem(w) == st for w in content_words(text))


def load_corpus(dirpath, sid):
    pj = os.path.join(dirpath, "_prompts.json")
    meta = json.load(open(pj)).get(sid) if os.path.exists(pj) else None
    if not meta:
        sys.exit(f"'{sid}' not in {pj}")
    title = meta.get("title", sid)
    prompt = meta.get("prompt", "")
    # recover the raw source: strip the tc contract wrapper if present
    m = re.search(r"Text:\s*(.*)$", prompt, re.S)
    source = m.group(1).strip() if m else prompt
    resp = {}
    import glob as _g
    for f in _g.glob(os.path.join(dirpath, f"{sid}_*.txt")):
        mdl = os.path.basename(f)[len(sid) + 1:-4]
        if mdl not in MODEL_NAMES:
            continue
        resp[mdl] = open(f, encoding="utf-8", errors="replace").read().strip()
    if not resp:
        sys.exit(f"no responses for {sid} -- harvest first (universal.py)")
    return title, source, resp


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


def vfidf_table(concepts, source, responses, E):
    """v1.1: verbatim preservation_core.vf_idf (two channels, real zeros:
    fidelity = max(cosine, lexical) per summary, BEST across summaries --
    a concept counts dropped only if every summary dropped it on both).
    Inline cosine-only version retained as declared fallback (#44)."""
    if pc_vfidf is not None:
        res = pc_vfidf(list(map(str, concepts)), source,
                       list(responses.values()), embed_fn=E)
        rows = []
        for r in res:
            rows.append(dict(
                concept=r.concept,
                void_freq=round(float(r.void_freq), 3),
                inv_fidelity=round(float(r.inv_fidelity), 3),
                vfidf=round(float(r.vf_idf), 3),
                cos_ch=round(float(r.cosine_channel), 3),
                lex_ch=round(float(r.lexical_channel), 3),
                preserved_by=str(r.preserved_by)))
        # restore caller-order lookups by returning in input order
        omap = {r["concept"]: r for r in rows}
        return [omap[str(c)] for c in concepts if str(c) in omap]
    return _vfidf_inline(concepts, source, responses, E)


def _vfidf_inline(concepts, source, responses, E):
    """Inline per the published spec:
    void_freq = stem-level TF salience in SOURCE (max-normalized);
    inv_fidelity = 1 - max cosine(concept, any summary sentence);
    vfidf = void_freq * inv_fidelity.
    Multiword: void_freq = max member-stem TF (declared).
    preservation_core.vf_idf verbatim swap pending a signature recon."""
    if term_frequencies is not None:
        tf = term_frequencies(source)
    else:
        cnt = {}
        for w in content_words(source):
            s = porter_stem(w)
            cnt[s] = cnt.get(s, 0) + 1
        mx = max(cnt.values()) if cnt else 1
        tf = {s: c / mx for s, c in cnt.items()}
    sents = []
    for t in responses.values():
        sents.extend(sentences(t))
    S = E(sents) if sents else np.zeros((0, 1024), dtype=np.float32)
    C = E([str(c) for c in concepts])
    sims = C @ S.T if len(sents) else np.zeros((len(concepts), 0))
    rows = []
    for i, c in enumerate(concepts):
        toks = str(c).lower().split()
        vf = max((tf.get(porter_stem(t), 0.0) for t in toks), default=0.0)
        mx = float(sims[i].max()) if sims.shape[1] else 0.0
        inv = 1.0 - mx
        rows.append(dict(concept=str(c), void_freq=round(vf, 3),
                         inv_fidelity=round(inv, 3),
                         vfidf=round(vf * inv, 3)))
    return rows


def centipede_core(dirpath, sid, min_legs):
    p = os.path.join(dirpath, f"{sid}_centipede.json")
    if not os.path.exists(p):
        return [], None
    rep = json.load(open(p, encoding="utf-8"))
    count, display = {}, {}
    for seg in rep.get("segments", []):
        for arm in seg.get("arms", []):
            st = arm.get("stem")
            count[st] = count.get(st, 0) + 1
            display.setdefault(st, arm.get("void"))
    core = [display[st] for st, c in sorted(count.items(),
                                            key=lambda kv: -kv[1])
            if c >= min_legs and not is_junk(display[st])]
    return core, rep.get("result_sha")


def call_claude(prompt_text, model_id, temperature, max_tokens=2600):
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("ANTHROPIC_API_KEY missing -- "
                 "set -a; source /home/remvelchio/eigentrace/.env; set +a")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model_id, max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "user", "content": prompt_text}])
    return "".join(b.text for b in msg.content
                   if getattr(b, "type", "") == "text")


def build_prompt(source, foreground, expand_with_plants):
    fg = ", ".join(f"'{w}'" for w in foreground)
    ex = ", ".join(f"'{w}'" for w in expand_with_plants)
    return (
        "You are an expert editor performing a content synthesis for "
        "search visibility in the AI-summary era.\n\n"
        "SOURCE ARTICLE:\n" + source + "\n\n"
        "Two measured word lists follow. FOREGROUND words are concepts "
        "this article already makes salient that AI summaries "
        "consistently drop -- restructure so they become load-bearing "
        "and survive any summary: lead with them, make claims hinge on "
        "them. EXPAND words are adjacent concepts the AI reading layer "
        "never reaches for this topic -- work them in as literal words "
        "or phrases wherever the article's own facts genuinely support "
        "them.\n\n"
        f"FOREGROUND: {fg}\n"
        f"EXPAND: {ex}\n\n"
        "DIRECTIVE: Rewrite the article as one flowing piece, roughly "
        "the source's length. Use as many of the listed words as "
        "possible as literal words or phrases -- your target is nearly "
        "all of them -- woven naturally. HARD RAIL: invent no facts; "
        "every claim must be supported by the source article. If a "
        "word cannot be used without inventing a fact, omit it -- "
        "omission under this rail is correct behavior, not failure.\n\n"
        "After the article, output exactly two lines:\n"
        "USED: comma-separated words you used\n"
        "SKIPPED: comma-separated words you omitted, each with a "
        "brief parenthetical reason"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--foreground-n", type=int, default=8)
    ap.add_argument("--expand-n", type=int, default=6)
    ap.add_argument("--min-legs", type=int, default=4,
                    help="centipede shared-core threshold")
    ap.add_argument("--plants", type=int, default=2,
                    help="planted control words (deterministic, audited)")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--model", default=os.environ.get(
        "ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    ap.add_argument("--verify", action="store_true",
                    help="re-harvest the synthesis and print "
                         "before/after VF-IDF (the closed loop)")
    args = ap.parse_args()
    sid = args.story

    title, source, resp = load_corpus(args.dir, sid)
    src_stems = {porter_stem(w) for w in content_words(source)}
    E = build_embedder()

    print("=" * 78)
    print(f"SYNTHESIS  ::  {sid}  ::  {VERSION}")
    print(f"source: {len(source)} ch / {len(source.split())} words   "
          f"corpus: {len(resp)} model responses")

    # ---- FOREGROUND: VF-IDF exposure over source concepts -------------
    cand_stems, cand_words = set(), []
    for w in content_words(source):
        if w in SYNTH_STOP:
            continue
        st = porter_stem(w)
        if st not in cand_stems:
            cand_stems.add(st)
            cand_words.append(w)
    fg_rows = vfidf_table(cand_words, source, resp, E)
    fg_rows = [r for r in fg_rows if not is_junk(r["concept"])]
    fg_rows.sort(key=lambda r: (-r["vfidf"], -r["void_freq"], r["concept"]))
    top_v = fg_rows[0]["vfidf"] if fg_rows else 0.0
    if top_v < 0.10:
        print(f"  FOREGROUND THIN: top VF-IDF {top_v:.3f} -- this "
              f"document states nearly everything it makes salient "
              f"(low extractable void). Thinness is a finding.")
    fg_live = [r for r in fg_rows if r["vfidf"] > 0.01]
    foreground = [r["concept"] for r in fg_live[:args.foreground_n]]

    # ---- EXPAND: centipede shared-core voids ---------------------------
    core, cent_sha = centipede_core(args.dir, sid, args.min_legs)
    expand = [w for w in core
              if stem_of(w) not in {stem_of(f) for f in foreground}
              ][:args.expand_n]

    # ---- planted controls, deterministic --------------------------------
    h = int(hashlib.sha256(sid.encode()).hexdigest(), 16)
    plants = []
    i = 0
    while len(plants) < args.plants and i < len(CONTROL_LEXICON) * 2:
        cand = CONTROL_LEXICON[(h + i) % len(CONTROL_LEXICON)]
        if porter_stem(cand) not in src_stems and cand not in plants:
            plants.append(cand)
        i += 1
    expand_presented = expand + plants   # unlabeled, appended

    print(f"FOREGROUND (VF-IDF top {len(foreground)}, "
          f"only vfidf>0.01 -- zeros are preserved, not dropped): "
          + ", ".join(f"{r['concept']}({r['vfidf']:.2f})"
                      for r in fg_live[:args.foreground_n]))
    print(f"EXPAND (centipede core >= {args.min_legs} legs, "
          f"{len(expand)}): " + (", ".join(expand) or "(none)"))
    print(f"planted controls ({len(plants)}, unlabeled in prompt): "
          + ", ".join(plants))
    print(f"model: {args.model}  temp={args.temperature}  "
          f"<- THE ONE NON-FROZEN STAGE, declared")

    # ---- the call --------------------------------------------------------
    prompt = build_prompt(source, foreground, expand_presented)
    print("\ncalling Claude ...")
    try:
        out = call_claude(prompt, args.model, args.temperature)
    except Exception as e:
        sys.exit(f"synthesis call failed: {e}")

    # split article from USED/SKIPPED footer
    mu = re.search(r"^USED\s*:(.*)$", out, re.M | re.I)
    ms = re.search(r"^SKIPPED\s*:(.*)$", out, re.M | re.I)
    cutpos = min([m.start() for m in (mu, ms) if m] or [len(out)])
    article = out[:cutpos].strip()
    claimed_used = [w.strip(" '\"") for w in
                    (mu.group(1).split(",") if mu else []) if w.strip()]
    claimed_skipped = ms.group(1).strip() if ms else ""

    # ---- audit: presence-verified adoption + planted control -----------
    real = foreground + expand
    adopted = [w for w in real if word_present(w, article)]
    plant_hits = [p for p in plants if word_present(p, article)]
    plant_evidence = {}
    for p in plant_hits:
        for sent in sentences(article):
            if word_present(p, sent):
                plant_evidence[p] = sent
                break
    verdict = "PASSED" if not plant_hits else f"ADOPTED ({len(plant_hits)})"

    print("\n" + "-" * 78)
    print("MEASURED  (presence verified by word-boundary stem match, "
          "not by the model's own claim)")
    print("-" * 78)
    print(f"  adoption          : {len(adopted)}/{len(real)} real "
          f"candidates in the synthesis")
    print(f"      used   : {', '.join(adopted) or '-'}")
    missed = [w for w in real if w not in adopted]
    print(f"      missed : {', '.join(missed) or '-'}")
    print(f"  PLANTED CONTROL   : {verdict}"
          + ("" if plant_hits else
             "  -- controls skipped under max-inclusion pressure"))
    for p, sent in plant_evidence.items():
        print(f"      evidence [{p}]: \"{sent[:120]}\"")
    if plant_hits:
        print("      review: ornamental (no fact asserted -- style call) "
              "vs factual (claim corrupted -- do not ship). "
              "The audit detects and evidences; the human grades.")
    if claimed_skipped:
        print(f"  model's own skip note: {claimed_skipped[:160]}")

    # ---- before/after ----------------------------------------------------
    before = vfidf_table(foreground, source, resp, E)
    after = None
    vresp = None
    if args.verify:
        vsid = f"{sid}_synth"
        vprompt = ("The following is a document. Based only on the text "
                   "provided, summarize its key claims. Text: " + article)
        print(f"\n--verify: re-harvesting synthesis as '{vsid}' ...")
        subprocess.run([sys.executable, "harvest_story.py", "--sid", vsid,
                        "--title", title, "--prompt", vprompt,
                        "--outdir", args.dir, "--force"])
        _, _, vresp = load_corpus(args.dir, vsid)
        after = vfidf_table(foreground, article, vresp, E)

    print("\n  FOREGROUND VF-IDF (verbatim metric: fidelity = "
          "max(cos, lex), best across summaries)"
          + ("  BEFORE -> AFTER" if after else
             "  BEFORE  (run --verify for the after)"))
    amap = {r["concept"]: r for r in (after or [])}
    for r in before:
        line = (f"      {r['concept']:<20} vf={r['void_freq']:.2f} "
                f"cos={r.get('cos_ch', 0):.2f} lex={r.get('lex_ch', 0):.2f}"
                f"  VFIDF {r['vfidf']:.3f}")
        if after:
            a = amap.get(r["concept"], {})
            av = a.get("vfidf", float("nan"))
            tag = ("COLLAPSED" if isinstance(av, float) and av == av
                   and r["vfidf"] >= 0.02
                   and av < r["vfidf"] * 0.5 else
                   ("kept" if r["vfidf"] >= 0.02 else "never dropped"))
            line += f"  ->  {av:.3f}  ({tag})"
        print(line)
    expand_results = []
    if expand:
        print("\n  EXPAND adoption + survival (before is 0 by "
              "construction: not in source)")
        vstems = ([stem_set(t) for t in vresp.values()]
                  if vresp else None)
        for w in expand:
            in_syn = word_present(w, article)
            surv = None
            if vstems is not None and in_syn:
                head = porter_stem(str(w).lower().split()[0])
                surv = sum(1 for ss in vstems if head in ss)
            expand_results.append(dict(concept=w, in_synthesis=in_syn,
                                       survived=surv,
                                       of=len(vresp) if vresp else None))
            stat = ("not adopted" if not in_syn else
                    (f"adopted; survived {surv}/{len(vresp)} new summaries"
                     if surv is not None else "adopted (run --verify "
                     "for survival)"))
            print(f"      {str(w):<20} {stat}")

    # ---- artifacts --------------------------------------------------------
    art_path = os.path.join(args.dir, f"{sid}_synthesis.txt")
    open(art_path, "w", encoding="utf-8").write(article + "\n")
    report = dict(
        harness="synthesis", version=VERSION, story=sid,
        generated=datetime.now().isoformat(timespec="seconds"),
        provenance=dict(model=args.model, temperature=args.temperature,
                        non_frozen_stage="claude synthesis call",
                        centipede_sha=cent_sha,
                        source_sha=sha12(source.encode()),
                        vfidf="inline per published spec",
                        min_legs=args.min_legs, plants=plants),
        foreground=fg_rows[:args.foreground_n], expand=expand,
        adoption=dict(adopted=adopted, missed=missed,
                      rate=round(len(adopted) / max(1, len(real)), 3)),
        planted_control=dict(verdict=verdict, adopted=plant_hits,
                             evidence=plant_evidence,
                             claimed_skipped=claimed_skipped),
        model_claimed_used=claimed_used,
        vfidf_before=before, vfidf_after=after,
        expand_results=expand_results,
        source=source, article=article,
        article_chars=len(article))
    jpath = os.path.join(args.dir, f"{sid}_synthesis.json")
    json.dump(report, open(jpath, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"\n  synthesis article : {art_path} ({len(article)} ch)")
    print(f"  audit JSON        : {jpath}")
    print("=" * 78)
    print("\n" + "-" * 78)
    print("THE SYNTHESIS")
    print("-" * 78)
    print(article)


if __name__ == "__main__":
    main()
