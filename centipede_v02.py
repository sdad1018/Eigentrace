#!/usr/bin/env python3
"""
centipede_v02.py -- the universal harness, hardening pass.

v0.1 -> v0.2 changelog (detection math UNCHANGED; measurement hardened):
  * ANCHOR CONTAINS is now a stem-set comparison over anchor words --
    identical semantics to the said census (ledger #24: 'lying' was
    substring-matching inside 'identifying').
  * Arm-A junk filter, declared: a term is junk if it starts with a
    non-letter, contains an ellipsis, carries a 3+ digit run, or exceeds
    4 tokens. The 253K wiki-title ruler serves list artifacts ('1309
    Hyperborea', '...And Some Were Human'); agreement-with-noise is not
    agreement. Filter applies to display and metrics; raw terms are
    preserved in the JSON with the dropped set named.
  * Arm-A raw metrics carried and printed: density / novelty / tether.
    (DISCOVERY saturated 68/68 on jspace; the label alone is empty.)
  * SHUFFLE-NULL for arm agreement: field-cos over MISMATCHED (A_i, B_j)
    pairs with different void stems, full enumeration, zero RNG. Prices
    the within-segment median against the topic floor.
  * Cross-segment isomorphism: v0.1's field-cos over shared voids was
    tautological (both arms are f(void, headline) only, so identical
    voids give cos=1.000 by construction). Replaced with structure the
    legs actually own:
      LEG-JACC      stem-Jaccard between leg void-sets, all pairs
      CONSEQ-FIELD  per-leg consequence centroid vs the body centroid
  * Declared flags: --exclude (stance gating by model, recorded in
    provenance), --prompt-mode (label recorded in provenance), --donut
    (wakes the donut legs via latent_retrieval.in_domain_void; the
    (results, centroid) tuple return is unpacked correctly; 184K
    global_vocab ruler, declared; results post-filtered to unsaid).
  * Root logging forced to WARNING after heavy imports: kills the tqdm
    'Batches' spam and INFO chatter. Stdout is webpage-clean.
  * JSON emission: {story}_centipede.json written next to the corpus
    (--json to override). The JSON, not the stdout, is the webpage
    contract; field names are frozen as of 2026-07-09.
  * The v0.1 baked-in R1-R4 registration block is removed: those were
    one-time jspace registrations, already adjudicated. Registrations
    live in the session ledger, not in the tool.

Segments (17 default; +up to 3 with --donut) and both arms run the
verbatim v0.1 math. Declared parameters: rulers (50K clean for segments
and arm B, 253K raycast for arm A, 184K global for donut), anchor =
title + prompt, K, conv_thresh, conv_min, depth_frac, the junk regex,
excluded models, prompt-mode label.

Usage:
  python3 centipede_v02.py --dir anamnesis_results/universal \
      --story claude_jspace \
      [--targets secret,hidden,...] [--voids-per-segment 4] \
      [--exclude model1,model2] [--prompt-mode tc] [--donut] \
      [--json path.json] > out.txt 2>&1
"""

VERSION = "centipede v0.2 2026-07-09"

import argparse
import glob
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime

import numpy as np

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)

try:
    from preservation_core import porter_stem
except Exception:
    porter_stem = lambda w: w.lower()

try:
    import torch
    import torch.nn.functional as TF
    from geometric_engine import (get_engine, reconstruct_unaligned_truth,
                                  reconstruct_unaligned_truth_v10)
    HAVE_GE = True
except Exception as e:
    print(f"[init] geometric_engine unavailable ({e}) -- logos legs will sit out")
    HAVE_GE = False

try:
    from consequence_engine import raycast_void_words
    HAVE_ARM_A = True
except Exception as e:
    print(f"[init] consequence_engine unavailable ({e}) -- arm A will sit out")
    HAVE_ARM_A = False

# webpage-clean stdout: no tqdm bars, no INFO chatter from imported
# engines. Our own output is print(), unaffected.
logging.getLogger().setLevel(logging.WARNING)

FRONTIER = ("chatgpt", "claude", "gemini", "deepseek", "grok")
MODEL_NAMES = ("chatgpt", "claude", "gemini", "deepseek", "grok",
               "mistral_22b", "mistral_7b", "qwen_14b", "hermes", "llama_8b")
_TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")
DEFAULT_TARGETS = ["secret", "hidden", "deception", "lying", "concealed",
                   "scheming", "conscious", "sentient", "aware", "manipulation"]
CONV_THRESH, CONV_MIN, ARMB_POOL = 0.45, 2, 400
DEPTH_FRAC = 0.8   # arm B keeps concepts >= this fraction of the way to w

JUNK_RULE = "leading non-letter | ellipsis | 3+ digit run | >4 tokens"


# ── plumbing ─────────────────────────────────────────────────────────

def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def content_words(text):
    return [w.lower() for w in _TOK.findall(text) if len(w) > 2]


def sentences(src):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", src)
            if len(s.strip()) > 15]


def is_junk(term):
    """Declared arm-A junk rule (see JUNK_RULE). Wiki-title list
    artifacts in the 253K ruler, not semantics."""
    t = str(term).strip()
    if len(t) < 3:
        return True
    if not t[:1].isalpha():
        return True
    if "..." in t or "\u2026" in t:
        return True
    if len(t.split()) > 4:
        return True
    if re.search(r"\d\d\d", t):
        return True
    return False


def stem_of(w):
    return porter_stem(str(w).split()[0]) if " " in str(w) else porter_stem(str(w))


def load_story(dirpath, sid):
    pj = os.path.join(dirpath, "_prompts.json")
    meta = json.load(open(pj)).get(sid) if os.path.exists(pj) else None
    if not meta:
        sys.exit(f"'{sid}' not in {pj}")
    title = meta.get("title", sid)
    prompt = meta.get("prompt", "")
    resp = {}
    for f in glob.glob(os.path.join(dirpath, f"{sid}_*.txt")):
        mdl = os.path.basename(f)[len(sid) + 1:-4]
        if mdl not in MODEL_NAMES:
            continue   # sibling sid sharing this prefix (e.g. _tc) -- skip
        resp[mdl] = open(f, encoding="utf-8", errors="replace").read().strip()
    if not resp:
        sys.exit(f"no response files for {sid} in {dirpath}")
    return title, prompt, resp


def build_stack():
    """One embedder (production engine, CPU-pinned) + the clean 50K vocab
    it pairs with (verbatim pattern from confront10_final.build_engine).
    Progress bars suppressed at the encode call for clean capture."""
    eng = get_engine()

    def E(t):
        v = np.array(eng.model.encode(
            t if isinstance(t, list) else [t],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False))
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)

    vt = json.load(open("vocab/global_vocab_clean.json"))
    words = vt["words"] if isinstance(vt, dict) else vt
    V = torch.load("vocab/global_vocab_clean.pt",
                   weights_only=False).numpy().astype(np.float32)
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)
    try:
        import confront10 as C
        HARD = getattr(C, "HARD_DROP", set())
    except Exception:
        HARD = set()
    logging.getLogger().setLevel(logging.WARNING)   # confront10 chain resets it
    return E, V, words, HARD


def top_unsaid(vec, V, words, said_stems, k, extra_drop=()):
    """Top-k vocab words near vec that the group did not say. v0.1 verbatim."""
    scores = V @ vec
    order = np.argsort(-scores)
    out, seen = [], set()
    for i in order[:2000]:
        w = words[i]
        if len(w) < 4 or w in extra_drop:
            continue
        st = stem_of(w)
        if st in said_stems or st in seen:
            continue
        seen.add(st)
        out.append(w)
        if len(out) >= k:
            break
    return out


# ── arm B: aimed convergence raycast (v0.1 verbatim) ─────────────────

def arm_b(void_word, headline, h_vec, sent_vecs, E, V, words, HARD,
          said_all_stems, top_k=5):
    v = E(f"{void_word} in the context of {headline}")[0]
    d = v - h_vec
    n = np.linalg.norm(d)
    if n < 1e-8:
        return []
    d = d / n
    w_depth = float((v - h_vec) @ d)          # == n
    proj = (V - h_vec) @ d                     # depth of every concept
    cone = V @ v                               # closeness to the void word
    pool = np.argsort(-cone)[:ARMB_POOL]
    rows = []
    for i in pool:
        w = words[i]
        if len(w) < 4 or w in HARD:
            continue
        if proj[i] < DEPTH_FRAC * w_depth:     # not past (~)w -- skip
            continue
        st = stem_of(w)
        if st == porter_stem(void_word) or st in said_all_stems:
            continue
        conv = int(np.sum(sent_vecs @ V[i] > CONV_THRESH))
        if conv < CONV_MIN:
            continue
        rows.append((w, conv, float(proj[i])))
    rows.sort(key=lambda r: (-r[1], -r[2]))
    return [r[0] for r in rows[:top_k]]


# ── crawl metrics ────────────────────────────────────────────────────

def stem_jaccard(a, b):
    A = {stem_of(x) for x in a}
    B = {stem_of(x) for x in b}
    return len(A & B) / max(1, len(A | B))


# ── main ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--targets", default=",".join(DEFAULT_TARGETS))
    ap.add_argument("--voids-per-segment", type=int, default=4)
    ap.add_argument("--exclude", default="",
                    help="comma list of models to drop (stance gating, "
                         "recorded in provenance)")
    ap.add_argument("--prompt-mode", default="unlabeled",
                    help="free label recorded in provenance (tc, natural, ...)")
    ap.add_argument("--donut", action="store_true",
                    help="wake donut/{F,L,ALL} legs (184K ruler)")
    ap.add_argument("--json", default="",
                    help="JSON output path (default: <dir>/<story>_centipede.json)")
    args = ap.parse_args()
    targets = [t.strip().lower() for t in args.targets.split(",") if t.strip()]
    K = args.voids_per_segment
    excluded = [m.strip() for m in args.exclude.split(",") if m.strip()]
    json_path = args.json or os.path.join(
        args.dir, f"{args.story}_centipede.json")

    title, prompt, resp = load_story(args.dir, args.story)
    for m in excluded:
        resp.pop(m, None)
    if not resp:
        sys.exit("all models excluded -- nothing to crawl")
    headline = f"{title}. {prompt}"
    fr = {m: t for m, t in resp.items()
          if any(f in m.lower() for f in FRONTIER)}
    lo = {m: t for m, t in resp.items() if m not in fr}
    groups = [("F", fr), ("L", lo), ("ALL", resp)]

    # provenance ------------------------------------------------------
    agg = hashlib.sha256()
    for f in sorted(glob.glob(os.path.join(args.dir, f"{args.story}_*.txt"))):
        agg.update(os.path.basename(f).encode())
        agg.update(open(f, "rb").read())
    harness_sha = sha12(open(__file__, "rb").read())
    corpus_sha = agg.hexdigest()[:12]
    anchor_sha = sha12(headline.encode())
    print("=" * 78)
    print(f"CENTIPEDE v0.2  story={args.story}  "
          f"({len(fr)} frontier / {len(lo)} local)")
    print(f"PROVENANCE harness={harness_sha} corpus={corpus_sha} "
          f"anchor={anchor_sha}")
    print(f"rulers: segments/armB=global_vocab_clean(50K) "
          f"armA=raycast_vocab(253K)"
          + (" donut=global_vocab(184K)" if args.donut else ""))
    print(f"params: K={K} conv_thresh={CONV_THRESH} conv_min={CONV_MIN} "
          f"depth_frac={DEPTH_FRAC}")
    print(f"declared: prompt_mode={args.prompt_mode} "
          f"excluded={excluded or 'none'} junk_rule=[{JUNK_RULE}]")

    # anchor + said census ---------------------------------------------
    anch_stems = {porter_stem(w) for w in content_words(headline)}
    hits = sorted(t for t in targets if porter_stem(t) in anch_stems)
    print(f"ANCHOR ({len(prompt)} ch) CONTAINS: {hits or 'no target stems'}")

    said_by = {m: {porter_stem(w) for w in content_words(t)}
               for m, t in resp.items()}
    group_said = {g: set().union(*(said_by[m] for m in d)) if d else set()
                  for g, d in groups}
    tstem = {t: porter_stem(t) for t in targets}
    print("\nSAID CENSUS (stem match):")
    census = {}
    for t in targets:
        who = sorted(m for m in resp if tstem[t] in said_by[m])
        census[t] = who
        fw = [m for m in who if m in fr]
        lw = [m for m in who if m in lo]
        print(f"  {t:<12} F:{','.join(fw) or '-':<34} L:{','.join(lw) or '-'}")

    # embeddings + segment vectors -------------------------------------
    E, V, words, HARD = build_stack()
    h_vec = E(headline)[0]
    sent_vecs = E(sentences(headline)) if len(sentences(headline)) >= 2 \
        else np.zeros((0, V.shape[1]), dtype=np.float32)
    emb = {g: (E(list(d.values())) if d else None) for g, d in groups}

    device = "cuda" if HAVE_GE and torch.cuda.is_available() else "cpu"
    segs = []   # (name, group, void_list)

    def add_seg(name, g, vec, extra_drop=()):
        try:
            voids = top_unsaid(vec, V, words, group_said[g], K, extra_drop)
            segs.append((name, g, voids))
        except Exception as ex:
            print(f"  [leg {name}] failed: {ex} -- crawling on")

    for g, d in groups:
        e = emb[g]
        if e is None:
            continue
        cen = e.mean(0)
        cen /= np.linalg.norm(cen) + 1e-8
        add_seg(f"said/{g}", g, cen)
        if HAVE_GE:
            et = TF.normalize(torch.tensor(e, dtype=torch.float32), p=2, dim=1)
            at = TF.normalize(torch.tensor(h_vec, dtype=torch.float32),
                              p=2, dim=0)
            for fn, nm in ((reconstruct_unaligned_truth, "logos_v9"),
                           (reconstruct_unaligned_truth_v10, "logos_v10")):
                try:
                    x = fn(et.to(device), headline_vec=at.to(device))
                    xv = TF.normalize(x.detach().cpu().flatten(),
                                      p=2, dim=0).numpy()
                    add_seg(f"{nm}/{g}", g, xv)
                except Exception as ex:
                    print(f"  [leg {nm}/{g}] failed: {ex} -- crawling on")
        if e.shape[0] >= 3:
            try:
                _, _, Vh = np.linalg.svd(e, full_matrices=False)
                nv = Vh[-1]
                if nv @ h_vec < 0:
                    nv = -nv
                add_seg(f"null/{g}", g, nv / (np.linalg.norm(nv) + 1e-8))
            except Exception as ex:
                print(f"  [leg null/{g}] failed: {ex} -- crawling on")

    if emb["F"] is not None and emb["L"] is not None:
        cf = emb["F"].mean(0); cf /= np.linalg.norm(cf) + 1e-8
        cl = emb["L"].mean(0); cl /= np.linalg.norm(cl) + 1e-8
        gap = cl - cf
        if np.linalg.norm(gap) > 1e-8:
            gap = gap / np.linalg.norm(gap)
            add_seg("gap->local", "F", gap)
            add_seg("gap->frontier", "L", -gap)

    add_seg("centroid_surface", "ALL", h_vec)   # near-anchor, unsaid-by-all

    # donut legs (opt-in): in_domain_void returns (results, centroid) or
    # a bare [] -- the v0.1-era unpack bug, handled here at the call site.
    if args.donut:
        try:
            from latent_retrieval import VocabTensor
            dvt = VocabTensor("vocab")
            logging.getLogger().setLevel(logging.WARNING)
            for g, d in groups:
                e = emb[g]
                if e is None:
                    continue
                cen = e.mean(0)
                cen = (cen / (np.linalg.norm(cen) + 1e-8)).astype(np.float32)
                try:
                    out = dvt.in_domain_void(
                        cen, e.astype(np.float32), k=K,
                        headline_vec=h_vec.astype(np.float32))
                    res = out[0] if isinstance(out, tuple) else out
                    wl = []
                    for pair in (res or []):
                        w = str(pair[0]) if isinstance(pair, (tuple, list)) \
                            else str(pair)
                        if stem_of(w) in group_said[g]:
                            continue   # donut is geometric; enforce unsaid
                        wl.append(w)
                        if len(wl) >= K:
                            break
                    segs.append((f"donut/{g}", g, wl))
                except Exception as ex:
                    print(f"  [leg donut/{g}] failed: {ex} -- crawling on")
        except Exception as ex:
            print(f"  [donut legs] unavailable: {ex} -- crawling on")

    for gname, d in (("F", fr), ("L", lo)):
        if not d:
            continue
        others = {m: t for m, t in resp.items() if m not in d}
        if not others:
            continue
        cnt = {}
        osaid = set().union(*(said_by[m] for m in others))
        for st in osaid - group_said[gname]:
            cnt[st] = cnt.get(st, 0) + 1
        raw = {}
        for m, t in others.items():
            for w in content_words(t):
                raw.setdefault(porter_stem(w), w)
        top = sorted(cnt, key=lambda s: -cnt[s])[:K]
        segs.append((f"lexcross/{gname}", gname,
                     [raw.get(s, s) for s in top]))

    # segments + arms ---------------------------------------------------
    print(f"\nSEGMENTS ({len(segs)} legs) + ARMS "
          f"(A=consequence raycast, junk-filtered; B=aimed convergence):")
    said_all = group_said["ALL"]
    rows = []            # dicts; see keys below
    junk_dropped_total, junk_seen_total = 0, 0

    def emb_mean(terms):
        if not terms:
            return None
        v = E(list(terms)).mean(0)
        n = np.linalg.norm(v)
        return (v / n) if n > 1e-8 else None

    for name, g, voids in segs:
        print(f"\n─ {name:<18} voids: {', '.join(voids) if voids else '(none)'}")
        if not voids:
            continue
        a_map = {}
        if HAVE_ARM_A:
            try:
                for rec in raycast_void_words(headline, list(voids)):
                    a_map[rec["word"]] = {
                        "raw": list(rec.get("deepest_consequences", []))[:5],
                        "quality": rec.get("signal_quality", "?"),
                        "density": rec.get("cluster_density"),
                        "novelty": rec.get("novelty"),
                        "tether": rec.get("tether"),
                    }
            except Exception as ex:
                print(f"    [arm A on {name}] failed: {ex}")
        for w in voids:
            am = a_map.get(w, {"raw": [], "quality": "-", "density": None,
                               "novelty": None, "tether": None})
            A_raw = am["raw"]
            A = [t for t in A_raw if not is_junk(t)]
            junk = [t for t in A_raw if is_junk(t)]
            junk_dropped_total += len(junk)
            junk_seen_total += len(A_raw)
            try:
                B = arm_b(w, headline, h_vec, sent_vecs, E, V, words, HARD,
                          said_all)
            except Exception as ex:
                print(f"    [arm B on {w}] failed: {ex}")
                B = []
            a_vec = emb_mean(A)
            b_vec = emb_mean(B)
            j = stem_jaccard(A, B) if (A and B) else float("nan")
            c = float(a_vec @ b_vec) if (a_vec is not None
                                         and b_vec is not None) else float("nan")
            rows.append(dict(seg=name, group=g, void=w, stem=stem_of(w),
                             A_raw=A_raw, A=A, junk=junk,
                             quality=am["quality"], density=am["density"],
                             novelty=am["novelty"], tether=am["tether"],
                             B=B, jacc=j, cos=c,
                             a_vec=a_vec, b_vec=b_vec))
            dnt = "".join(
                f" {k}={am[k]:.2f}" if isinstance(am[k], (int, float))
                else "" for k in ("density", "novelty", "tether"))
            print(f"    {w:<18} A[{am['quality']:<9}{dnt}]: "
                  f"{', '.join(A) or '-'}"
                  + (f"   (junk dropped: {', '.join(junk)})" if junk else ""))
            jtxt = f"{j:.2f}" if j == j else "nan"
            ctxt = f"{c:.2f}" if c == c else "nan"
            print(f"    {'':<18} B          : {', '.join(B) or '-'}"
                  f"   | jacc={jtxt} cos={ctxt}")

    # crawl -------------------------------------------------------------
    print("\nCRAWL:")
    print(f"  JUNK FILTER: dropped {junk_dropped_total} of "
          f"{junk_seen_total} arm-A terms  [{JUNK_RULE}]")
    per_seg = {}
    for r in rows:
        if r["cos"] == r["cos"]:
            per_seg.setdefault(r["seg"], []).append(r["cos"])
    for name in sorted(per_seg):
        v = per_seg[name]
        print(f"  leg-sync {name:<18} mean-cos={np.mean(v):.3f}  (n={len(v)})")
    allc = [r["cos"] for r in rows if r["cos"] == r["cos"]]
    body_median = float(np.median(allc)) if allc else float("nan")
    if allc:
        print(f"  BODY: median within-segment arm agreement = "
              f"{body_median:.3f} over {len(allc)} void-arm pairs")

    # shuffle null: mismatched (A_i, B_j), different void stems, full
    # enumeration -- prices the observed median against the topic floor.
    Ai = [(r["a_vec"], r["stem"]) for r in rows if r["a_vec"] is not None]
    Bj = [(r["b_vec"], r["stem"]) for r in rows if r["b_vec"] is not None]
    null_median, n_null = float("nan"), 0
    if Ai and Bj:
        MA = np.stack([v for v, _ in Ai])
        MB = np.stack([v for v, _ in Bj])
        M = MA @ MB.T
        null_vals = []
        for i, (_, sa) in enumerate(Ai):
            for k, (_, sb) in enumerate(Bj):
                if sa != sb:
                    null_vals.append(float(M[i, k]))
        n_null = len(null_vals)
        if null_vals:
            null_median = float(np.median(null_vals))
    margin = body_median - null_median
    mtxt = f"{margin:+.3f}" if margin == margin else "nan"
    ntxt = f"{null_median:.3f}" if null_median == null_median else "nan"
    btxt = f"{body_median:.3f}" if body_median == body_median else "nan"
    print(f"  SHUFFLE-NULL: observed-median={btxt}  null-median={ntxt}  "
          f"margin={mtxt}  (n_obs={len(allc)} n_null={n_null})")

    # cross-segment structure the legs actually own ----------------------
    leg_voids = {name: vs for name, _, vs in segs if vs}
    names = sorted(leg_voids)
    jpairs = []
    for i in range(len(names)):
        for k in range(i + 1, len(names)):
            jpairs.append((names[i], names[k],
                           stem_jaccard(leg_voids[names[i]],
                                        leg_voids[names[k]])))
    jvals = [j for _, _, j in jpairs]
    jmed = float(np.median(jvals)) if jvals else float("nan")
    strong = sorted((p for p in jpairs if p[2] >= 0.25),
                    key=lambda p: -p[2])
    print(f"  LEG-JACC median over {len(jpairs)} leg pairs = "
          f"{jmed:.2f}   pairs >= 0.25: {len(strong)}")
    print("  LEG-JACC pairs >= 0.25 (top 12):")
    for a, b, j in strong[:12]:
        print(f"    {a:<18} ~ {b:<18} J={j:.2f}")
    if not strong:
        print("    (none)")

    # per-leg consequence centroid vs body centroid
    leg_vecs = {}
    for r in rows:
        for v in (r["a_vec"], r["b_vec"]):
            if v is not None:
                leg_vecs.setdefault(r["seg"], []).append(v)
    leg_cent = {}
    for name, vs in leg_vecs.items():
        c = np.mean(np.stack(vs), axis=0)
        n = np.linalg.norm(c)
        if n > 1e-8:
            leg_cent[name] = c / n
    conseq_field = {}
    if leg_cent:
        body = np.mean(np.stack(list(leg_cent.values())), axis=0)
        body /= np.linalg.norm(body) + 1e-8
        print("  CONSEQ-FIELD (per-leg consequence centroid . body centroid):")
        for name in sorted(leg_cent):
            cf = float(leg_cent[name] @ body)
            conseq_field[name] = cf
            print(f"    {name:<18} {cf:.3f}  (vecs={len(leg_vecs[name])})")

    shared = {}
    for r in rows:
        shared.setdefault(r["stem"], []).append(r["seg"])
    shared_voids = {st: sorted(set(legs)) for st, legs in shared.items()
                    if len(set(legs)) >= 2}
    print("  cross-leg shared voids (>=2 legs; field-cos removed -- arms "
          "are f(void, headline), identical voids give 1.000 by "
          "construction):")
    for st, legs in sorted(shared_voids.items(),
                           key=lambda kv: -len(kv[1])):
        print(f"    {st:<14} legs[{len(legs)}]: {','.join(legs)[:70]}")
    if not shared_voids:
        print(f"    (no void shared across legs at K={K} -- widen K to test)")

    # targets sighting ----------------------------------------------------
    print("\nTARGET SIGHTINGS:")
    sightings = []
    for t in targets:
        st = tstem[t]
        in_voids = [n for n, _, vs in segs
                    if any(stem_of(v) == st for v in vs)]
        in_arms = [f"{r['seg']}:{r['void']}" for r in rows
                   if any(stem_of(x) == st for x in r["A"] + r["B"])]
        sightings.append(dict(target=t, said_by=len(census[t]),
                              said_models=census[t],
                              in_voids=in_voids, as_consequence=in_arms[:6]))
        print(f"  {t:<12} said_by={len(census[t])}/{len(resp)}"
              f"  in_voids={in_voids or '-'}"
              f"  as_consequence={in_arms[:3] or '-'}")

    # JSON: the webpage contract ------------------------------------------
    def fnum(x, nd=4):
        try:
            f = float(x)
            return round(f, nd) if f == f else None
        except (TypeError, ValueError):
            return None

    seg_json = []
    for name, g, voids in segs:
        arms = []
        for r in rows:
            if r["seg"] != name:
                continue
            arms.append(dict(
                void=r["void"], stem=r["stem"],
                A=dict(terms=r["A"], terms_raw=r["A_raw"],
                       junk_dropped=r["junk"], quality=r["quality"],
                       density=fnum(r["density"]), novelty=fnum(r["novelty"]),
                       tether=fnum(r["tether"])),
                B=dict(terms=r["B"]),
                jaccard=fnum(r["jacc"]), field_cos=fnum(r["cos"])))
        seg_json.append(dict(name=name, group=g, voids=voids, arms=arms))

    report = dict(
        harness="centipede", version=VERSION,
        story=args.story, dir=args.dir,
        generated=datetime.now().isoformat(timespec="seconds"),
        provenance=dict(
            harness_sha=harness_sha, corpus_sha=corpus_sha,
            anchor_sha=anchor_sha,
            rulers=dict(segments="global_vocab_clean(50K)",
                        arm_b="global_vocab_clean(50K)",
                        arm_a="raycast_vocab(253K)",
                        donut="global_vocab(184K)" if args.donut else None),
            params=dict(K=K, conv_thresh=CONV_THRESH, conv_min=CONV_MIN,
                        depth_frac=DEPTH_FRAC),
            prompt_mode=args.prompt_mode, excluded_models=excluded,
            junk_rule=JUNK_RULE, donut=bool(args.donut)),
        anchor=dict(chars=len(prompt), contains_targets=hits,
                    headline=headline[:300]),
        models=dict(frontier=sorted(fr), local=sorted(lo),
                    n=len(resp)),
        said_census={t: dict(F=[m for m in census[t] if m in fr],
                             L=[m for m in census[t] if m in lo])
                     for t in targets},
        segments=seg_json,
        crawl=dict(
            junk=dict(dropped=junk_dropped_total, seen=junk_seen_total),
            leg_sync={n: fnum(np.mean(v)) for n, v in per_seg.items()},
            body_median=fnum(body_median),
            shuffle_null=dict(null_median=fnum(null_median),
                              margin=fnum(margin),
                              n_obs=len(allc), n_null=n_null),
            leg_jaccard=dict(
                median=fnum(jmed),
                pairs_ge_025=[dict(a=a, b=b, j=fnum(j))
                              for a, b, j in strong]),
            conseq_field={n: fnum(v) for n, v in conseq_field.items()},
            shared_voids=shared_voids),
        target_sightings=sightings,
    )
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(report, jf, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {json_path} ({os.path.getsize(json_path)} bytes)")
    print("=" * 78)


if __name__ == "__main__":
    main()
