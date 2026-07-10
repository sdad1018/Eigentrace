#!/usr/bin/env python3
"""
synthesis_v2.py -- stage seven, rebuilt: the writer gets the actual
geometry, not a digest of it.

What changed from v1 (and why v1 was wrong):
  * v1's EXPAND channel fed only void WORDS, only from the consensus
    core (>=4 legs). On a corpus where said/logos legs agree J=1.00,
    that filter silently deleted every distinctive leg -- the SVD
    null-space voids, the gap voids, lexcross -- before the writer saw
    anything. And the raycast ARMS (the consequence fields, both
    rulers) were computed, stored, and discarded at the prompt
    boundary. v2 feeds per-method voids with family tags (SVD legs
    explicitly flagged) and each void's own field terms.
  * v1's planted controls came from a hardcoded lexicon -- the one
    prebuilt word list in a pipeline whose thesis is 'measured, not
    curated.' v2's decoys are MEASURED ANTI-VOIDS: the vocabulary words
    geometrically farthest from this story's whole field (min over
    max(cos to anchor, cos to response centroid)), deterministic,
    filtered against source and everything any model said, and
    camouflaged with their own real nearest-neighbor terms so their
    prompt format is indistinguishable from genuine candidates. The
    trap is geometry too.
  * Carries the #47 chain: FOREGROUND sorted desc, vfidf>0.01 floor,
    THIN banner, COLLAPSED floor in the after-table.

Adoption is tracked per class -- void words, field terms (raycast
consequences), plants -- and survival per adopted item across the
verify re-harvest. The Claude call remains the one declared non-frozen
stage.

Usage:
  python3 synthesis_v2.py --dir anamnesis_results/universal \
      --story prelude_2026 [--verify] [--max-voids 10] \
      [--field-per-void 3] [--fresh-centipede]
"""

VERSION = "synthesis v2.0 2026-07-10"

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

try:
    from preservation_core import (porter_stem, term_frequencies,
                                   vf_idf as pc_vfidf, stem_set,
                                   STOPWORDS as PC_STOP)
except Exception:
    porter_stem = lambda w: w.lower()
    term_frequencies = None
    pc_vfidf = None
    stem_set = lambda t: frozenset(porter_stem(w) for w in
                                   re.findall(r"[a-zA-Z][a-zA-Z'\-]+",
                                              t.lower()) if len(w) > 2)
    PC_STOP = frozenset()

logging.getLogger().setLevel(logging.WARNING)

_TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")
SYNTH_STOP = frozenset(PC_STOP) | frozenset(
    "while although though however despite whether since also will "
    "would could should must may might shall based including according "
    "expected likely typically currently".split())

MODEL_NAMES = ("chatgpt", "claude", "gemini", "deepseek", "grok",
               "mistral_22b", "mistral_7b", "qwen_14b", "hermes", "llama_8b")
SVD_FAMILIES = ("null",)          # legs derived from SVD spectra
CENTIPEDE = "centipede_v04.py"


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
    return porter_stem(str(w).split()[0]) if " " in str(w) \
        else porter_stem(str(w))


def word_present(word, text):
    tl = text.lower()
    if re.search(r"\b" + re.escape(str(word).lower()) + r"\b", tl):
        return True
    head = porter_stem(str(word).lower().split()[0])
    return any(porter_stem(w) == head for w in content_words(text))


def load_corpus(dirpath, sid):
    pj = os.path.join(dirpath, "_prompts.json")
    meta = json.load(open(pj)).get(sid) if os.path.exists(pj) else None
    if not meta:
        sys.exit(f"'{sid}' not in {pj}")
    title = meta.get("title", sid)
    prompt = meta.get("prompt", "")
    m = re.search(r"Text:\s*(.*)$", prompt, re.S)
    source = m.group(1).strip() if m else prompt
    resp = {}
    for f in glob.glob(os.path.join(dirpath, f"{sid}_*.txt")):
        mdl = os.path.basename(f)[len(sid) + 1:-4]
        if mdl not in MODEL_NAMES:
            continue
        resp[mdl] = open(f, encoding="utf-8",
                         errors="replace").read().strip()
    if not resp:
        sys.exit(f"no responses for {sid} -- harvest first")
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


def load_clean_vocab():
    vt = json.load(open("vocab/global_vocab_clean.json"))
    words = vt["words"] if isinstance(vt, dict) else vt
    import torch
    V = torch.load("vocab/global_vocab_clean.pt",
                   weights_only=False).numpy().astype(np.float32)
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
    return V, words


# -- the j-spot feed: per-method voids + their raycast fields ---------

def centipede_channels(dirpath, sid, max_voids, field_per_void,
                       src_stems):
    p = os.path.join(dirpath, f"{sid}_centipede.json")
    if not os.path.exists(p):
        return None, None
    rep = json.load(open(p, encoding="utf-8"))
    info = {}
    for seg in rep.get("segments", []):
        fam = seg.get("name", "?").split("/")[0]
        for arm in seg.get("arms", []):
            st = arm.get("stem")
            d = info.setdefault(st, dict(
                word=arm.get("void"), legs=set(), fams=set(),
                A=[], B=[]))
            d["legs"].add(seg.get("name"))
            d["fams"].add(fam)
            for t in (arm.get("A", {}).get("terms") or []):
                if not is_junk(t) and t not in d["A"]:
                    d["A"].append(t)
            for t in (arm.get("B", {}).get("terms") or []):
                if t not in d["B"]:
                    d["B"].append(t)

    def build(st):
        d = info[st]
        field, seen = [], {st}
        for t in d["A"] + d["B"]:          # A first: deepest terminals
            ts = stem_of(t)
            if ts in seen or ts in src_stems:
                continue
            seen.add(ts)
            field.append(t)
            if len(field) >= field_per_void:
                break
        return dict(word=d["word"], stem=st,
                    legs=len(d["legs"]),
                    fams=sorted(d["fams"]),
                    svd=any(f in SVD_FAMILIES for f in d["fams"]),
                    field=field)

    ranked = sorted(info, key=lambda s: -len(info[s]["legs"]))
    picked, have_f = [], set()
    for st in ranked:
        if len(picked) >= max_voids:
            break
        picked.append(st)
        have_f |= info[st]["fams"]
    # family coverage: every distinctive method gets at least one void
    for fam in ("null", "gap->local", "gap->frontier", "lexcross",
                "centroid_surface", "donut"):
        if any(fam in info[st]["fams"] for st in picked):
            continue
        cand = [st for st in ranked if fam in info[st]["fams"]]
        if cand:
            picked.append(cand[0])
    return [build(st) for st in picked], rep.get("result_sha")


# -- measured anti-void decoys: the trap is geometry too --------------

def anti_void_plants(E, V, words, title, source, resp,
                     src_stems, said_stems, exclude_stems, k=2):
    anchor = E(f"{title}. {source}")[0]
    cent = E(list(resp.values())).mean(0)
    cent = cent / (np.linalg.norm(cent) + 1e-8)
    closeness = np.maximum(V @ anchor, V @ cent)
    order = np.argsort(closeness)              # ascending = farthest
    picks = []
    for i in order:
        w = words[i]
        if len(w) < 5 or not w.isalpha():
            continue
        st = porter_stem(w)
        if st in src_stems or st in said_stems or st in exclude_stems:
            continue
        if any(porter_stem(p["word"]) == st for p in picks):
            continue
        # camouflage: the decoy's own real nearest neighbors as its
        # 'field', so its prompt format matches genuine candidates
        nb, seen = [], {st}
        for j in np.argsort(-(V @ V[i]))[:60]:
            t = words[j]
            ts = porter_stem(t)
            if ts in seen or ts in src_stems or ts in said_stems \
                    or len(t) < 4:
                continue
            seen.add(ts)
            nb.append(t)
            if len(nb) >= 3:
                break
        picks.append(dict(word=w, stem=st, field=nb,
                          closeness=round(float(closeness[i]), 3)))
        if len(picks) >= k:
            break
    return picks


# -- VF-IDF (verbatim production metric, #44/#47 chain intact) --------

def vfidf_table(concepts, source, responses, E):
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
        omap = {r["concept"]: r for r in rows}
        return [omap[str(c)] for c in concepts if str(c) in omap]
    # fallback: cosine-only inline (declared weaker)
    sents = []
    for t in responses.values():
        sents.extend(sentences(t))
    S = E(sents) if sents else np.zeros((0, 1024), dtype=np.float32)
    C = E([str(c) for c in concepts])
    sims = C @ S.T if len(sents) else np.zeros((len(concepts), 0))
    if term_frequencies is not None:
        tf = term_frequencies(source)
    else:
        cnt = {}
        for w in content_words(source):
            s = porter_stem(w)
            cnt[s] = cnt.get(s, 0) + 1
        mx = max(cnt.values()) if cnt else 1
        tf = {s: c / mx for s, c in cnt.items()}
    rows = []
    for i, c in enumerate(concepts):
        toks = str(c).lower().split()
        vf = max((tf.get(porter_stem(t), 0.0) for t in toks), default=0.0)
        mx = float(sims[i].max()) if sims.shape[1] else 0.0
        rows.append(dict(concept=str(c), void_freq=round(vf, 3),
                         inv_fidelity=round(1 - mx, 3),
                         vfidf=round(vf * (1 - mx), 3),
                         cos_ch=round(mx, 3), lex_ch=0.0,
                         preserved_by="cosine-only-fallback"))
    return rows


def call_claude(prompt_text, model_id, temperature, max_tokens=2800):
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("ANTHROPIC_API_KEY missing -- source the .env")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=model_id, max_tokens=max_tokens, temperature=temperature,
        messages=[{"role": "user", "content": prompt_text}])
    return "".join(b.text for b in msg.content
                   if getattr(b, "type", "") == "text")


def build_prompt(source, foreground, channel_items):
    fg = ", ".join(f"'{w}'" for w in foreground)
    lines = []
    for it in channel_items:
        tag = (f"[{it['legs']} methods"
               + (" incl. SVD null-space]" if it.get("svd") else "]")) \
            if "legs" in it else "[2 methods]"
        fld = ", ".join(it["field"]) if it["field"] else "--"
        lines.append(f"  '{it['word']}' {tag} -- field: {fld}")
    ex = "\n".join(lines)
    return (
        "You are an expert editor performing a content synthesis for "
        "search visibility in the AI-summary era.\n\n"
        "SOURCE ARTICLE:\n" + source + "\n\n"
        "Two measured channels follow.\n\n"
        "FOREGROUND -- concepts this article makes salient that AI "
        "summaries consistently drop. Restructure so they become "
        "load-bearing and survive any summary: lead with them, make "
        "claims hinge on them.\n"
        f"FOREGROUND: {fg}\n\n"
        "EXPAND -- the measured negative space of this topic. Each "
        "entry is a void word (a concept no model reached, with how "
        "many independent detection methods surfaced it; SVD marks "
        "spectral null-space detection) followed by its FIELD: the "
        "raycast consequence terms measured beyond it. Work the void "
        "words and/or their field terms in as literal words or phrases "
        "wherever the article's own facts genuinely support them -- "
        "field terms count as fully as void words.\n"
        f"EXPAND:\n{ex}\n\n"
        "DIRECTIVE: Rewrite the article as one flowing piece, roughly "
        "the source's length. Use as many of the listed words as "
        "possible -- your target is nearly all of them -- woven "
        "naturally. HARD RAIL: invent no facts; every claim must be "
        "supported by the source article. If a word cannot be used "
        "without inventing a fact, omit it -- omission under this rail "
        "is correct behavior, not failure.\n\n"
        "After the article, output exactly two lines:\n"
        "USED: comma-separated words you used\n"
        "SKIPPED: comma-separated words you omitted, each with a brief "
        "parenthetical reason"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--foreground-n", type=int, default=8)
    ap.add_argument("--max-voids", type=int, default=10)
    ap.add_argument("--field-per-void", type=int, default=3)
    ap.add_argument("--plants", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--model", default=os.environ.get(
        "ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--fresh-centipede", action="store_true",
                    help="re-run the harness before reading its JSON")
    args = ap.parse_args()
    sid = args.story

    title, source, resp = load_corpus(args.dir, sid)
    src_stems = {porter_stem(w) for w in content_words(source)}
    said_stems = set()
    for t in resp.values():
        said_stems |= set(stem_set(t))

    print("=" * 78)
    print(f"SYNTHESIS  ::  {sid}  ::  {VERSION}")
    print(f"source: {len(source)} ch   corpus: {len(resp)} responses")

    if args.fresh_centipede or not os.path.exists(
            os.path.join(args.dir, f"{sid}_centipede.json")):
        print("running the harness for a fresh geometry ...")
        subprocess.run([sys.executable, CENTIPEDE, "--dir", args.dir,
                        "--story", sid],
                       stdout=open(os.path.join(
                           args.dir, f"{sid}_centipede_run.txt"), "w"),
                       stderr=subprocess.STDOUT)

    E = build_embedder()
    V, words = load_clean_vocab()

    # FOREGROUND (verbatim metric, #47 chain) -------------------------
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
    fg_rows.sort(key=lambda r: (-r["vfidf"], -r["void_freq"],
                                r["concept"]))
    top_v = fg_rows[0]["vfidf"] if fg_rows else 0.0
    if top_v < 0.10:
        print(f"  FOREGROUND THIN: top VF-IDF {top_v:.3f} -- this "
              f"document states nearly everything it makes salient. "
              f"Thinness is a finding.")
    fg_live = [r for r in fg_rows if r["vfidf"] > 0.01]
    foreground = [r["concept"] for r in fg_live[:args.foreground_n]]
    print(f"FOREGROUND ({len(foreground)}, vfidf>0.01): "
          + ", ".join(f"{r['concept']}({r['vfidf']:.2f})"
                      for r in fg_live[:args.foreground_n]))

    # EXPAND: the full j-spot ------------------------------------------
    channels, cent_sha = centipede_channels(
        args.dir, sid, args.max_voids, args.field_per_void, src_stems)
    if channels is None:
        sys.exit("no centipede JSON -- run the harness or pass "
                 "--fresh-centipede")
    print(f"EXPAND ({len(channels)} voids, per-method, fields "
          f"attached; SVD legs tagged):")
    for it in channels:
        print(f"  '{it['word']}' [{it['legs']} legs"
              + (" +SVD" if it["svd"] else "")
              + f" | {','.join(it['fams'])}] field: "
              + (", ".join(it["field"]) or "--"))

    # measured anti-void decoys ----------------------------------------
    exclude = {it["stem"] for it in channels} | \
              {stem_of(f) for f in foreground}
    plants = anti_void_plants(E, V, words, title, source, resp,
                              src_stems, said_stems, exclude,
                              k=args.plants)
    print(f"ANTI-VOID plants ({len(plants)}, measured -- farthest "
          f"vocab from this story's field, camouflaged with own "
          f"neighbors):")
    for p in plants:
        print(f"  '{p['word']}' closeness={p['closeness']} "
              f"camo-field: {', '.join(p['field'])}")
    print(f"model: {args.model}  temp={args.temperature}  "
          f"<- the one non-frozen stage")

    # weave decoys into the channel listing, deterministic slots -------
    presented = list(channels)
    for p in plants:
        slot = (int(hashlib.sha256(
            (sid + p["word"]).encode()).hexdigest(), 16)
            % (len(presented) + 1))
        presented.insert(slot, dict(word=p["word"], field=p["field"]))

    prompt = build_prompt(source, foreground, presented)
    print("\ncalling Claude ...")
    try:
        out = call_claude(prompt, args.model, args.temperature)
    except Exception as e:
        sys.exit(f"synthesis call failed: {e}")

    mu = re.search(r"^USED\s*:(.*)$", out, re.M | re.I)
    ms = re.search(r"^SKIPPED\s*:(.*)$", out, re.M | re.I)
    cutpos = min([m.start() for m in (mu, ms) if m] or [len(out)])
    article = out[:cutpos].strip()
    claimed_skipped = ms.group(1).strip() if ms else ""

    # audit: per-class adoption -----------------------------------------
    fg_in = [w for w in foreground if word_present(w, article)]
    void_in = [it["word"] for it in channels
               if word_present(it["word"], article)]
    field_in = []
    for it in channels:
        for t in it["field"]:
            if word_present(t, article):
                field_in.append(f"{t} (<-{it['word']})")
    plant_hits = [p["word"] for p in plants
                  if word_present(p["word"], article)]
    plant_ev = {}
    for p in plant_hits:
        for sent in sentences(article):
            if word_present(p, sent):
                plant_ev[p] = sent
                break
    verdict = "PASSED" if not plant_hits else \
        f"ADOPTED ({len(plant_hits)})"

    print("\n" + "-" * 78)
    print("MEASURED  (presence verified by word-boundary stem match)")
    print("-" * 78)
    print(f"  FOREGROUND adopted : {len(fg_in)}/{len(foreground)}  "
          f"({', '.join(fg_in) or '-'})")
    print(f"  VOID words adopted : {len(void_in)}/{len(channels)}  "
          f"({', '.join(void_in) or '-'})")
    print(f"  FIELD terms adopted: {len(field_in)}  "
          f"({'; '.join(field_in[:8]) or '-'})")
    print(f"  ANTI-VOID verdict  : {verdict}")
    for p, sent in plant_ev.items():
        print(f"      evidence [{p}]: \"{sent[:120]}\"")
    if plant_hits:
        print("      review: ornamental vs factual is the shipping "
              "call. The audit detects and evidences.")
    if claimed_skipped:
        print(f"  model's skip note  : {claimed_skipped[:180]}")

    # before/after --------------------------------------------------------
    before = vfidf_table(foreground, source, resp, E) if foreground \
        else []
    after, vresp = None, None
    if args.verify:
        vsid = f"{sid}_synth"
        vprompt = ("The following is a document. Based only on the "
                   "text provided, summarize its key claims. Text: "
                   + article)
        print(f"\n--verify: re-harvesting synthesis as '{vsid}' ...")
        subprocess.run([sys.executable, "harvest_story.py", "--sid",
                        vsid, "--title", title, "--prompt", vprompt,
                        "--outdir", args.dir, "--force"])
        _, _, vresp = load_corpus(args.dir, vsid)
        if foreground:
            after = vfidf_table(foreground, article, vresp, E)

    if before:
        print("\n  FOREGROUND VF-IDF"
              + ("  BEFORE -> AFTER" if after else
                 "  BEFORE  (--verify for the after)"))
        amap = {r["concept"]: r for r in (after or [])}
        for r in before:
            line = f"      {r['concept']:<20} VFIDF {r['vfidf']:.3f}"
            if after:
                a = amap.get(r["concept"], {})
                av = a.get("vfidf", float("nan"))
                tag = ("COLLAPSED" if isinstance(av, float)
                       and av == av and r["vfidf"] >= 0.02
                       and av < r["vfidf"] * 0.5 else
                       ("kept" if r["vfidf"] >= 0.02
                        else "never dropped"))
                line += f"  ->  {av:.3f}  ({tag})"
            print(line)

    survival = []
    if vresp:
        vstems = [stem_set(t) for t in vresp.values()]
        print("\n  ADOPTION SURVIVAL across the re-harvest "
              f"({len(vresp)} new summaries)")
        seen_s = set()
        for label, items in (("void", void_in),
                             ("field", [f.split(" ")[0]
                                        for f in field_in])):
            for w in items:
                head = porter_stem(str(w).lower().split()[0])
                if (label, head) in seen_s:
                    continue
                seen_s.add((label, head))
                cnt = sum(1 for ss in vstems if head in ss)
                survival.append(dict(word=w, cls=label,
                                     survived=cnt, of=len(vresp)))
                print(f"      {w:<20} [{label}]  survived "
                      f"{cnt}/{len(vresp)}")

    # artifacts -------------------------------------------------------
    art_path = os.path.join(args.dir, f"{sid}_synthesis2.txt")
    open(art_path, "w", encoding="utf-8").write(article + "\n")
    report = dict(
        harness="synthesis", version=VERSION, story=sid,
        generated=datetime.now().isoformat(timespec="seconds"),
        provenance=dict(model=args.model, temperature=args.temperature,
                        non_frozen_stage="claude synthesis call",
                        centipede_sha=cent_sha,
                        source_sha=sha12(source.encode()),
                        plants_method="measured anti-void "
                        "(farthest from story field; camouflaged "
                        "with own vocab neighbors; slot sha-keyed)",
                        svd_families=list(SVD_FAMILIES)),
        foreground=fg_live[:args.foreground_n],
        expand_channels=channels,
        plants=plants,
        adoption=dict(foreground=fg_in, void_words=void_in,
                      field_terms=field_in),
        planted_control=dict(verdict=verdict, adopted=plant_hits,
                             evidence=plant_ev,
                             claimed_skipped=claimed_skipped),
        vfidf_before=before, vfidf_after=after,
        survival=survival,
        source=source, article=article)
    jpath = os.path.join(args.dir, f"{sid}_synthesis2.json")
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
