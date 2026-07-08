#!/usr/bin/env python3
"""svd_census.py — 2026-07-08

Census of every portable vector->word extraction method in the repo,
run per story on the saved magnum corpus (frontier API + local model
responses), with a target-word rank matrix and convergence counts.

METHOD INVENTORY (11 families known on disk; 8 run here):
  RUN  1. said        centroid kNN, "what they said" (latent_retrieval)   [control]
  RUN  2. lexcross    cross-model lexical void: stems others said, group
                      didn't (adaptation of omnibus_wide.lexical_void —
                      this corpus has prompts, not source articles)
  RUN  3. vf_idf      two-channel preservation scoring on TARGETS only
                      (preservation_core; cosine OR stemmed-lexical)
  RUN  4. donut       in_domain_void threshold geometry (latent_retrieval)
  RUN  5. logos_v9    PGD synthesis, production code (geometric_engine)
  RUN  6. logos_v10   PGD synthesis, production code (geometric_engine)
  RUN  7. null_space  least-variance right singular vector — the only
                      strict SVD channel; sign-aligned to the anchor
  RUN  8. gap         centroid-difference directions (gap->local,
                      gap->frontier), computed once per story
  NOTE 9. spiral      Summary Plus sentence-convergence channel — NOT
                      ported (implementation not read into this script)
  NOTE 10. raycast    consequence_engine depth extrapolation — NOT run
                      (requires its own pipeline's void vector as input)
  NOTE 11. prod flat  V10 + said-stem band filter — represented here by
                      the S-flags on logos_v10 ranks, not a column

Groups per story: F (frontier 5), L (local 5), ALL (10).
Echo-vs-detection: every rank cell carries S if that group's responses
contain the word (stem match). Convergence counts both raw top-K and
top-K-while-unsaid (the detection pattern).

Usage:
  python3 svd_census.py                     # default story: altman_family
  python3 svd_census.py --story ftx_fraud
  python3 svd_census.py --all               # every story (slower)
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np
import torch
import torch.nn.functional as F

# ── editable target list ─────────────────────────────────────────────
TARGETS = ["incest", "abuse", "sexual", "assault", "molested",
           "sister", "annie", "allegations", "victim", "denied"]

TOPK = 20
FRONTIER = ("chatgpt", "claude", "gemini", "deepseek", "grok")
KNOWN_MODELS = ("chatgpt", "claude", "gemini", "deepseek", "grok",
                "hermes", "mistral", "llama", "qwen", "phi", "gemma")
DIRS = [
    "/mnt/c/Users/M4ISI/eigentrace/anamnesis_results/magnum_opus",
    "/mnt/c/Users/M4ISI/eigentrace/anamnesis_results/magnum_opus_v2",
    "/home/remvelchio/eigentrace/anamnesis_results/magnum_opus",
    "/home/remvelchio/eigentrace/anamnesis_results/magnum_opus_v2",
]

_TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")
_STOP = set("""the a an and or but if then else for nor so yet of in on at to
from by with about into over after before between during without within
is are was were be been being have has had do does did will would can
could may might must shall should this that these those it its they them
their there here he she his her him you your we our us i me my not no
as such than too very just also more most other some any all each which
who whom whose what when where why how said says say""".split())


def content_words(text):
    return [w.lower() for w in _TOK.findall(text or "")
            if len(w) > 2 and w.lower() not in _STOP]


# ── imports from the instrument (fail loud, not silent) ──────────────
try:
    from preservation_core import porter_stem, vf_idf
    HAVE_PC = True
except Exception as e:
    print(f"[warn] preservation_core unavailable ({e}); "
          f"stems fall back to lower(), vf_idf column skipped")
    porter_stem = lambda w: w.lower()
    HAVE_PC = False

try:
    from geometric_engine import (reconstruct_unaligned_truth,
                                  reconstruct_unaligned_truth_v10)
    HAVE_GE = True
except Exception as e:
    print(f"[warn] geometric_engine unavailable ({e}); logos columns skipped")
    HAVE_GE = False

from latent_retrieval import VocabTensor


# ── corpus loader: model-suffix-first parse (same fix as omnibus) ────
def load_corpus():
    stories = {}
    for d in DIRS:
        pj = os.path.join(d, "_prompts.json")
        prompts = {}
        if os.path.exists(pj):
            j = json.load(open(pj))
            if isinstance(j, dict):
                for sid, v in j.items():
                    if isinstance(v, dict):
                        prompts[sid] = {"title": v.get("title", sid),
                                        "prompt": v.get("prompt", "")}
                    elif isinstance(v, str):
                        prompts[sid] = {"title": sid, "prompt": v}
        for f_ in glob.glob(os.path.join(d, "*.txt")):
            base = os.path.basename(f_)[:-4]
            sid, mdl = None, None
            parts = base.split("_")
            for cut in (1, 2):
                if len(parts) > cut:
                    cand = "_".join(parts[-cut:]).lower()
                    if any(cand == k or cand.endswith("_" + k) or k in cand
                           for k in KNOWN_MODELS):
                        sid, mdl = "_".join(parts[:-cut]), "_".join(parts[-cut:])
                        break
            if sid is None and len(parts) > 1:
                sid, mdl = "_".join(parts[:-1]), parts[-1]
                print(f"[loader] WARNING unrecognized model token in '{base}'"
                      f" -- filed as sid={sid} mdl={mdl}")
            if not sid:
                continue
            txt = open(f_, encoding="utf-8", errors="replace").read().strip()
            st = stories.setdefault(sid, {
                "title": prompts.get(sid, {}).get("title", sid),
                "prompt": prompts.get(sid, {}).get("prompt", ""),
                "responses": {}})
            if sid in prompts:
                st["title"] = prompts[sid]["title"]
                st["prompt"] = prompts[sid]["prompt"]
            st["responses"][mdl] = txt
    return stories


# ── vocab + rank machinery ───────────────────────────────────────────
class Ranker:
    def __init__(self):
        self.vt = VocabTensor("vocab")
        vm = self.vt.tensor.float()
        self.vm = vm / vm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        self.words = self.vt.words
        self.index = {w: i for i, w in enumerate(self.words)}

    def rank_of(self, vec_t, word):
        """Absolute rank (1-based) of `word` under cosine to vec_t."""
        i = self.index.get(word)
        if i is None:
            return None
        v = F.normalize(vec_t.float().flatten(), p=2, dim=0).cpu()
        scores = self.vm @ v
        return int((scores > scores[i]).sum().item()) + 1

    def topk(self, vec_t, k=TOPK):
        v = F.normalize(vec_t.float().flatten(), p=2, dim=0).cpu()
        scores = self.vm @ v
        idx = torch.topk(scores, k).indices.tolist()
        return [self.words[i] for i in idx]


def null_vector(embs_t, anchor_t):
    """Least-variance right singular vector of the centered response
    matrix (strict SVD). Sign is arbitrary; aligned toward the anchor
    so runs are reproducible — noted honestly, not hidden."""
    e = embs_t - embs_t.mean(dim=0, keepdim=True)
    _, _, Vh = torch.linalg.svd(e, full_matrices=False)
    v = Vh[-1]
    if torch.dot(v, anchor_t) < 0:
        v = -v
    return F.normalize(v, p=2, dim=0)


def fmt_rank(r, said):
    if r is None:
        return "   n/v "
    tag = "S" if said else " "
    return f"{r:>6d}{tag}"


def analyze_story(sid, st, ranker, model, device):
    title, prompt = st["title"], st["prompt"]
    resp = st["responses"]
    fr = {m: t for m, t in resp.items()
          if any(f in m.lower() for f in FRONTIER)}
    lo = {m: t for m, t in resp.items() if m not in fr}
    groups = [("F", fr), ("L", lo), ("ALL", resp)]

    print("=" * 78)
    print(f"STORY: {sid}   ({len(fr)} frontier / {len(lo)} local)")
    print(f"  title: {title[:70]}")

    # said census -----------------------------------------------------
    said_by = {}
    for m, t in resp.items():
        said_by[m] = {porter_stem(w) for w in content_words(t)}
    group_said = {g: set().union(*(said_by[m] for m in d)) if d else set()
                  for g, d in groups}
    tstem = {t: porter_stem(t) for t in TARGETS}

    print("\n  SAID CENSUS (stem match; a method that surfaces a said "
          "word is echoing, not detecting):")
    for t in TARGETS:
        who = [m for m in resp if tstem[t] in said_by[m]]
        fw = [m for m in who if m in fr]
        lw = [m for m in who if m in lo]
        invoc = "" if t in ranker.index else "   [not in vocab]"
        print(f"    {t:<12} F:{','.join(fw) or '-':<38} "
              f"L:{','.join(lw) or '-'}{invoc}")

    # embeddings ------------------------------------------------------
    anchor_np = model.encode([title + ". " + prompt])[0]
    anchor_t = F.normalize(torch.tensor(anchor_np, dtype=torch.float32),
                           p=2, dim=0)
    emb = {}
    for g, d in groups:
        if not d:
            emb[g] = None
            continue
        e = torch.tensor(model.encode(list(d.values())), dtype=torch.float32)
        emb[g] = F.normalize(e, p=2, dim=1)

    # method vectors per group ---------------------------------------
    cols = []   # (colname, vec_t or None, group)

    for g, d in groups:
        e = emb[g]
        if e is None:
            continue
        cen = F.normalize(e.mean(dim=0), p=2, dim=0)
        cols.append((f"said/{g}", cen, g))
        if HAVE_GE:
            try:
                x9 = reconstruct_unaligned_truth(
                    e.to(device), headline_vec=anchor_t.to(device))
                cols.append((f"logos_v9/{g}",
                             F.normalize(x9.detach().cpu().flatten(),
                                         p=2, dim=0), g))
            except Exception as ex:
                print(f"  [logos_v9/{g}] failed: {ex}")
            try:
                x10 = reconstruct_unaligned_truth_v10(
                    e.to(device), headline_vec=anchor_t.to(device))
                cols.append((f"logos_v10/{g}",
                             F.normalize(x10.detach().cpu().flatten(),
                                         p=2, dim=0), g))
            except Exception as ex:
                print(f"  [logos_v10/{g}] failed: {ex}")
        if e.shape[0] >= 3:
            cols.append((f"null/{g}", null_vector(e, anchor_t), g))

    if emb["F"] is not None and emb["L"] is not None:
        cf = F.normalize(emb["F"].mean(dim=0), p=2, dim=0)
        cl = F.normalize(emb["L"].mean(dim=0), p=2, dim=0)
        gap = cl - cf
        if gap.norm() > 1e-8:
            gap = F.normalize(gap, p=2, dim=0)
            cols.append(("gap->local", gap, "F"))     # what L has, F lacks
            cols.append(("gap->frontier", -gap, "L"))
        print(f"\n  frontier<->local centroid gap magnitude: "
              f"{float((cl - cf).norm()):.4f}")

    # donut ------------------------------------------------------------
    donut_words = {}
    for g, d in groups:
        if emb[g] is None:
            continue
        try:
            cen_np = emb[g].mean(dim=0).numpy()
            res = ranker.vt.in_domain_void(
                cen_np, emb[g].numpy(), k=TOPK,
                headline_vec=np.asarray(anchor_np))
            donut_words[g] = [w for w, _ in res]
        except Exception as ex:
            print(f"  [donut/{g}] failed: {ex}")
            donut_words[g] = None

    # lexcross ----------------------------------------------------------
    lexcross = {}
    for g, d in [("F", fr), ("L", lo)]:
        if not d:
            continue
        others = {m: t for m, t in resp.items() if m not in d}
        counts = {}
        surface = {}
        for m, t in others.items():
            seen = set()
            for w in content_words(t):
                s = porter_stem(w)
                if s in seen:
                    continue
                seen.add(s)
                counts[s] = counts.get(s, 0) + 1
                surface.setdefault(s, w)
        voids = [(s, c) for s, c in counts.items()
                 if s not in group_said[g]]
        voids.sort(key=lambda x: -x[1])
        lexcross[g] = [surface[s] for s, _ in voids]

    # top-K tables -------------------------------------------------------
    print(f"\n  TOP-{TOPK} PER METHOD (* = said by that group -> echo):")
    for name, vec, g in cols:
        words = ranker.topk(vec, TOPK)
        marked = [w + ("*" if porter_stem(w.lower()) in group_said[g]
                       else "") for w in words]
        print(f"    {name:<16} {', '.join(marked)}")
    for g in ("F", "L", "ALL"):
        if donut_words.get(g):
            marked = [w + ("*" if porter_stem(w.lower()) in group_said[g]
                           else "") for w in donut_words[g]]
            print(f"    {'donut/' + g:<16} {', '.join(marked)}")
    for g in ("F", "L"):
        if g in lexcross:
            print(f"    {'lexcross/' + g:<16} "
                  f"{', '.join(lexcross[g][:TOPK])}   "
                  f"(others said, {g} didn't — lexical fact, not geometry)")

    # target rank matrix ---------------------------------------------------
    print(f"\n  TARGET RANK MATRIX (absolute rank in "
          f"{len(ranker.words)}-word vocab; S = group said it; "
          f"top-{TOPK} threshold for convergence):")
    header = "    " + f"{'target':<12}" + "".join(
        f"{name:>17}" for name, _, _ in cols)
    print(header)
    conv = {t: [] for t in TARGETS}
    for t in TARGETS:
        row = f"    {t:<12}"
        for name, vec, g in cols:
            r = ranker.rank_of(vec, t)
            said = tstem[t] in group_said[g]
            row += f"{fmt_rank(r, said):>17}"
            if r is not None and r <= TOPK:
                conv[t].append((name, said))
        print(row)

    # donut + lexcross membership for targets
    for t in TARGETS:
        extra = []
        for g in ("F", "L", "ALL"):
            dw = donut_words.get(g)
            if dw and any(porter_stem(w.lower()) == tstem[t] for w in dw):
                extra.append((f"donut/{g}", tstem[t] in group_said[g]))
        for g in ("F", "L"):
            lc = lexcross.get(g, [])
            if any(porter_stem(w.lower()) == tstem[t]
                   for w in lc[:TOPK]):
                extra.append((f"lexcross/{g}", False))
        conv[t].extend(extra)

    # vf_idf on targets ------------------------------------------------------
    if HAVE_PC:
        print("\n  VF-IDF (concept-level preservation vs the whole room; "
              "source = union of all 10 responses):")
        union = " ".join(resp.values())
        embed_fn = lambda texts: model.encode(list(texts))
        for g, d in [("F", fr), ("L", lo)]:
            if not d:
                continue
            try:
                res = vf_idf(TARGETS, union, list(d.values()), embed_fn)
                for r in res:
                    print(f"    {g}: {r.concept:<12} vf_idf={r.vf_idf:6.3f} "
                          f" preserved_by={r.preserved_by}")
            except Exception as ex:
                print(f"    [vf_idf/{g}] failed: {ex}")

    # convergence ------------------------------------------------------------
    ncols = len(cols) + sum(1 for g in ("F", "L", "ALL")
                            if donut_words.get(g)) + len(lexcross)
    print(f"\n  CONVERGENCE (of {ncols} method-columns):")
    for t in TARGETS:
        hits = conv[t]
        unsaid = [h for h in hits if not h[1]]
        names = ", ".join(n + ("*" if s else "") for n, s in hits) or "-"
        print(f"    {t:<12} top-{TOPK} in {len(hits):>2} cols "
              f"({len(unsaid):>2} while unsaid)  :: {names}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", default="altman_family")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device}")
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    ranker = Ranker()
    print(f"vocab={len(ranker.words)}")
    missing = [t for t in TARGETS if t not in ranker.index]
    if missing:
        print(f"targets not in vocab (rank cols n/v, vf_idf still runs): "
              f"{missing}")

    corpus = load_corpus()
    print("stories:", ", ".join(
        f"{s}({len(corpus[s]['responses'])})" for s in sorted(corpus)))

    sids = sorted(corpus) if args.all else [args.story]
    for sid in sids:
        if sid not in corpus:
            print(f"story '{sid}' not found — pick from the list above")
            sys.exit(1)
        analyze_story(sid, corpus[sid], ranker, model, device)


if __name__ == "__main__":
    main()
