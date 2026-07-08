#!/usr/bin/env python3
"""frankenstein.py — 2026-07-08

Every vector->word extraction method this project has ever built,
living or dead, firing at once on one story. Each channel is labeled
with its era and provenance: imported production code, faithful
reimplementation from logged/published semantics, or the dead method's
own saved outputs queried directly.

FIRING (16):
  living, from svd_census (donut unpack fixed):
    said, lexcross, vf_idf, donut, logos_v9, logos_v10, null_space,
    gap->local/gap->frontier
  resurrected:
    consensus_axis   Geo-VIX era '→' readout: top PC of the response
                     cloud, sign-aligned to centroid          [reimpl]
    perp_void        Geo-VIX era '⊥VOID': headline component
                     orthogonal to the consensus centroid     [reimpl
                     from orchestrator.log 2026-03-19 semantics]
    pc_poles         both poles of PC1..PC3 — the svd_state /
                     tone-axis family readout                 [reimpl]
    forbidden_dir    direction seeded from tonight's confirmed
                     meant-but-unsaid words; kNN = "what else lies
                     that way" [adapted from forbidden_direction_
                     derived_from_voids, 2026-05-15]
    eigenvoid_db     the May instrument's OWN saved scores: target
                     rank among 184,789 by max_forbidden + per-model
                     retention                        [original data]
    clv_lens         logos_v10 rescored through priority_words.jsonl
                     (CLV weights) — dictionary-as-parameter, live
    raycast          consequence_engine.raycast, fed forbidden_dir
                                              [original code, import]
    entity_retention magnum battery's native entity check
                                        [original PROMPTS, ast-parse]
    march_table      per-model cos(word, response) grid in the
                     2026-03-19 format, on today's corpus
NOT FIRED (honest):
    spiral (SP sentence-convergence; implementation unread),
    logprob entropy + abstraction gradients (named on the May 24
    methodology page; code not located), wikipedia edit-velocity
    (external sensor, not vector->word), and everything on
    /withdrawals (own-parent 0/5, self-map 0/4, eight-test battery,
    5170->1659, void-direction) — retracted with receipts, stays dead.

Usage:
  python3 frankenstein.py                    # altman_family
  python3 frankenstein.py --story deepseek_tiananmen
"""
import argparse
import ast as _ast
import glob
import json
import os
import re
import sys

import numpy as np
import torch
import torch.nn.functional as F

TARGETS = ["incest", "abuse", "sexual", "assault", "molested",
           "sister", "annie", "allegations", "victim", "denied",
           "groping", "sibling", "suing"]
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
from by with about into over after before between during without within is are
was were be been being have has had do does did will would can could may might
must shall should this that these those it its they them their there here he
she his her him you your we our us i me my not no as such than too very just
also more most other some any all each which who whom whose what when where
why how said says say""".split())


def content_words(text):
    return [w.lower() for w in _TOK.findall(text or "")
            if len(w) > 2 and w.lower() not in _STOP]


try:
    from preservation_core import porter_stem, vf_idf
    HAVE_PC = True
except Exception as e:
    print(f"[warn] preservation_core unavailable ({e})")
    porter_stem = lambda w: w.lower()
    HAVE_PC = False
try:
    from geometric_engine import (reconstruct_unaligned_truth,
                                  reconstruct_unaligned_truth_v10)
    HAVE_GE = True
except Exception as e:
    print(f"[warn] geometric_engine unavailable ({e})")
    HAVE_GE = False
from latent_retrieval import VocabTensor


def load_corpus():
    stories = {}
    for d in DIRS:
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
            if not sid:
                continue
            txt = open(f_, encoding="utf-8", errors="replace").read().strip()
            stories.setdefault(sid, {"responses": {}})["responses"][mdl] = txt
    return stories


def load_battery_prompt(sid):
    """ast-parse the battery scripts for PROMPTS[sid] — no import,
    no side effects. Returns (prompt, entities, structure, srcfile)."""
    for path in ("magnum_opus_battery.py", "magnum_opus_v2_battery.py"):
        try:
            tree = _ast.parse(open(path).read())
        except Exception:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign) and any(
                    getattr(t, "id", None) == "PROMPTS" for t in node.targets):
                try:
                    d = _ast.literal_eval(node.value)
                except Exception:
                    continue
                if sid in d:
                    e = d[sid]
                    return (e.get("prompt", ""), e.get("entities", []) or [],
                            e.get("structure", []) or [], path)
    return None


class Ranker:
    def __init__(self):
        self.vt = VocabTensor("vocab")
        vm = self.vt.tensor.float()
        self.vm = vm / vm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        self.words = self.vt.words
        self.index = {w: i for i, w in enumerate(self.words)}

    def scores(self, vec_t):
        v = F.normalize(vec_t.float().flatten(), p=2, dim=0).cpu()
        return self.vm @ v

    def rank_of(self, vec_t, word):
        i = self.index.get(word)
        if i is None:
            return None
        s = self.scores(vec_t)
        return int((s > s[i]).sum().item()) + 1

    def topk(self, vec_t, k=TOPK):
        s = self.scores(vec_t)
        return [self.words[i] for i in torch.topk(s, k).indices.tolist()]

    def word_vec(self, word):
        i = self.index.get(word)
        return None if i is None else self.vm[i]


def null_vector(embs_t, anchor_t):
    e = embs_t - embs_t.mean(dim=0, keepdim=True)
    _, _, Vh = torch.linalg.svd(e, full_matrices=False)
    v = Vh[-1]
    return F.normalize(v if torch.dot(v, anchor_t) >= 0 else -v, p=2, dim=0)


def pcs(embs_t, n=3):
    e = embs_t - embs_t.mean(dim=0, keepdim=True)
    _, S, Vh = torch.linalg.svd(e, full_matrices=False)
    return [(F.normalize(Vh[i], p=2, dim=0), float(S[i])) for i in range(min(n, Vh.shape[0]))]


def mark(words, group_said):
    return [w + ("*" if porter_stem(w.lower()) in group_said else "")
            for w in words]


def _donut_words(r):
    """in_domain_void returns a multi-part structure in this era (the
    census's 2-unpack and the monster's x[0] both died on it). Find
    whatever part is a sequence of (word, ...) pairs or bare strings
    and return the words; empty list if nothing word-shaped exists."""
    def words_from(seq):
        out = []
        for it in seq:
            if isinstance(it, str):
                out.append(it)
            elif (isinstance(it, (list, tuple)) and it
                  and isinstance(it[0], str)):
                out.append(it[0])
        return out
    if not isinstance(r, (list, tuple)):
        return []
    w = words_from(r)
    if w:
        return w
    for part in r:
        if isinstance(part, (list, tuple)):
            w = words_from(part)
            if w:
                return w
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", default="altman_family")
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    ranker = Ranker()
    print(f"device={device}  vocab={len(ranker.words)}")

    corpus = load_corpus()
    sid = args.story
    if sid not in corpus:
        print(f"story '{sid}' not found; have: {', '.join(sorted(corpus))}")
        sys.exit(1)
    resp = corpus[sid]["responses"]
    fr = {m: t for m, t in resp.items()
          if any(f in m.lower() for f in FRONTIER)}
    lo = {m: t for m, t in resp.items() if m not in fr}
    groups = [("F", fr), ("L", lo), ("ALL", resp)]

    bat = load_battery_prompt(sid)
    if bat:
        prompt, entities, structure, src = bat
        anchor_text = sid.replace("_", " ") + ". " + prompt
        print(f"anchor: battery prompt from {src} "
              f"({len(prompt)} chars, {len(entities)} entities) — NOTE: "
              f"census used the bare sid; ranks may shift accordingly")
    else:
        prompt, entities, structure = "", [], []
        anchor_text = sid.replace("_", " ")
        print("anchor: bare sid (no battery PROMPTS entry found)")

    print("=" * 78)
    print(f"THE MONSTER WALKS: {sid}   ({len(fr)}F / {len(lo)}L)")

    # said census -------------------------------------------------------
    said_by = {m: {porter_stem(w) for w in content_words(t)}
               for m, t in resp.items()}
    group_said = {g: set().union(*(said_by[m] for m in d)) if d else set()
                  for g, d in groups}
    tstem = {t: porter_stem(t) for t in TARGETS}
    print("\nSAID CENSUS:")
    for t in TARGETS:
        who = [m for m in resp if tstem[t] in said_by[m]]
        print(f"  {t:<12} F:{','.join(m for m in who if m in fr) or '-':<40}"
              f" L:{','.join(m for m in who if m in lo) or '-'}")

    # embeddings ---------------------------------------------------------
    anchor_np = model.encode([anchor_text])[0]
    anchor_t = F.normalize(torch.tensor(anchor_np, dtype=torch.float32),
                           p=2, dim=0)
    emb, resp_vecs = {}, {}
    for g, d in groups:
        if not d:
            emb[g] = None
            continue
        e = torch.tensor(model.encode(list(d.values())), dtype=torch.float32)
        emb[g] = F.normalize(e, p=2, dim=1)
    for i, (m, _) in enumerate(resp.items()):
        resp_vecs[m] = emb["ALL"][i]

    cols = []  # (name, vec, said-flag group)

    # ── living channels ─────────────────────────────────────────────────
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
                cols.append((f"v9/{g}", F.normalize(
                    x9.detach().cpu().flatten(), p=2, dim=0), g))
                x10 = reconstruct_unaligned_truth_v10(
                    e.to(device), headline_vec=anchor_t.to(device))
                cols.append((f"v10/{g}", F.normalize(
                    x10.detach().cpu().flatten(), p=2, dim=0), g))
            except Exception as ex:
                print(f"  [logos/{g}] failed: {ex}")
        if e.shape[0] >= 3:
            cols.append((f"null/{g}", null_vector(e, anchor_t), g))

    if emb["F"] is not None and emb["L"] is not None:
        cf = F.normalize(emb["F"].mean(dim=0), p=2, dim=0)
        cl = F.normalize(emb["L"].mean(dim=0), p=2, dim=0)
        gap = cl - cf
        if gap.norm() > 1e-8:
            gap = F.normalize(gap, p=2, dim=0)
            cols.append(("gap>L", gap, "F"))
            cols.append(("gap>F", -gap, "L"))

    # ── resurrected channels ────────────────────────────────────────────
    res_cols = []
    for g in ("F", "ALL"):
        e = emb[g]
        if e is None:
            continue
        cen = F.normalize(e.mean(dim=0), p=2, dim=0)
        p = pcs(e, 3)
        axis = p[0][0]
        if torch.dot(axis, cen) < 0:
            axis = -axis
        res_cols.append((f"axis/{g}", axis, g))
        perp = anchor_t - torch.dot(anchor_t, cen) * cen
        if perp.norm() > 1e-8:
            res_cols.append((f"perp/{g}",
                             F.normalize(perp, p=2, dim=0), g))

    # forbidden_dir: seeded from confirmed meant-but-unsaid targets
    seeds = [t for t in ("incest", "molested", "groping")
             if tstem[t] not in group_said["ALL"] and t in ranker.index]
    fdir = None
    if seeds:
        cen_all = F.normalize(emb["ALL"].mean(dim=0), p=2, dim=0)
        diffs = [F.normalize(ranker.word_vec(t) - cen_all, p=2, dim=0)
                 for t in seeds]
        fdir = F.normalize(torch.stack(diffs).mean(dim=0), p=2, dim=0)
        res_cols.append(("forbid/ALL", fdir, "ALL"))
        print(f"\nforbidden_dir seeded from unsaid-by-all: {seeds}")
    else:
        print("\nforbidden_dir: no unsaid seed available for this story")

    # clv lens over v10/ALL
    v10_all = next((v for n, v, _ in cols if n == "v10/ALL"), None)
    pri = {}
    try:
        for line in open("priority_words.jsonl"):
            try:
                j = json.loads(line)
                pri[str(j["word"]).lower()] = float(j.get("priority", 0))
            except Exception:
                pass
    except FileNotFoundError:
        pass
    clv_top = []
    if v10_all is not None and pri:
        s = ranker.scores(v10_all)
        weighted = [(float(s[ranker.index[w]]) * p, w)
                    for w, p in pri.items() if w in ranker.index]
        weighted.sort(reverse=True)
        clv_top = [w for _, w in weighted[:TOPK]]

    # ── channel top-20s ─────────────────────────────────────────────────
    print(f"\nTOP-{TOPK} PER CHANNEL (* = said by that group -> echo):")
    for name, vec, g in cols + res_cols:
        print(f"  {name:<12} {', '.join(mark(ranker.topk(vec), group_said[g]))}")
    if clv_top:
        print(f"  {'clv/ALL':<12} "
              f"{', '.join(mark(clv_top, group_said['ALL']))}   "
              f"[v10 x priority_words CLV weights, {len(pri)} lexicon]")
        print(f"  {'':<12} target priorities: " + ", ".join(
            f"{t}={pri[t]:.2f}" for t in TARGETS if t in pri))

    # pc_poles
    print("\nPC POLES (svd_state / tone-axis family; both ends, ALL group):")
    for i, (v, sv) in enumerate(pcs(emb["ALL"], 3), 1):
        print(f"  PC{i}+ (sv={sv:.2f}) {', '.join(ranker.topk(v, 8))}")
        print(f"  PC{i}-           {', '.join(ranker.topk(-v, 8))}")

    # donut (fixed unpack)
    donut_words = {}
    for g, d in groups:
        if emb[g] is None:
            continue
        try:
            r = ranker.vt.in_domain_void(
                emb[g].mean(dim=0).numpy(), emb[g].numpy(), k=TOPK,
                headline_vec=np.asarray(anchor_np))
            donut_words[g] = _donut_words(r)[:TOPK]
            print(f"  donut/{g:<6} "
                  f"{', '.join(mark(donut_words[g], group_said[g]))}")
        except Exception as ex:
            print(f"  [donut/{g}] failed: {ex}")

    # lexcross
    lexcross = {}
    for g, d in [("F", fr), ("L", lo)]:
        if not d:
            continue
        counts, surface = {}, {}
        for m, t in resp.items():
            if m in d:
                continue
            seen = set()
            for w in content_words(t):
                s = porter_stem(w)
                if s in seen:
                    continue
                seen.add(s)
                counts[s] = counts.get(s, 0) + 1
                surface.setdefault(s, w)
        voids = sorted(((s, c) for s, c in counts.items()
                        if s not in group_said[g]), key=lambda x: -x[1])
        lexcross[g] = [surface[s] for s, _ in voids]
        print(f"  lexcr/{g:<6} {', '.join(lexcross[g][:TOPK])}")

    # ── eigenvoid.db: the dead testify in their own words ───────────────
    print("\nEIGENVOID.DB (May era, original saved scores — no reimpl):")
    try:
        import sqlite3
        c = sqlite3.connect("anamnesis_results/eigenvoid.db")
        total = c.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
        top = c.execute("SELECT word,max_forbidden,is_void FROM vocabulary "
                        "ORDER BY max_forbidden DESC LIMIT 20").fetchall()
        print("  db most-forbidden-20:", ", ".join(
            f"{w}({m:.2f}{'V' if v else ''})" for w, m, v in top))
        for t in TARGETS:
            row = c.execute("SELECT max_forbidden,max_direction,is_void "
                            "FROM vocabulary WHERE word=?", (t,)).fetchone()
            if not row:
                print(f"  {t:<12} not in db vocab")
                continue
            mf, md, iv = row
            rk = c.execute("SELECT COUNT(*)+1 FROM vocabulary "
                           "WHERE max_forbidden>?", (mf,)).fetchone()[0]
            ms = c.execute("SELECT model,retention,iteration FROM measurements"
                           " WHERE word=? ORDER BY iteration DESC, model "
                           "LIMIT 6", (t,)).fetchall()
            it = ms[0][2] if ms else "-"
            print(f"  {t:<12} max_forbidden={mf:.3f} rank={rk}/{total} "
                  f"dir={md} void={iv} | retention(it{it}): "
                  + (" ".join(f"{m}:{r:.2f}" for m, r, _ in ms) or "-"))
    except Exception as ex:
        print(f"  db query failed: {ex}")

    # May 15 saved direction vectors, if the json kept them
    try:
        j = json.load(open(
            "anamnesis_results/forbidden_direction_20260515_234550.json"))

        def hunt(o, path=""):
            if isinstance(o, list) and len(o) == 1024 and \
                    all(isinstance(x, (int, float)) for x in o[:6]):
                yield path, o
            elif isinstance(o, dict):
                for k, v in o.items():
                    yield from hunt(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o[:40]):
                    yield from hunt(v, f"{path}[{i}]")
        vecs = list(hunt(j))
        if vecs:
            print(f"\nMAY-15 SAVED DIRECTIONS ({len(vecs)} vectors found):")
            for path, v in vecs[:6]:
                vt_ = F.normalize(torch.tensor(v, dtype=torch.float32),
                                  p=2, dim=0)
                print(f"  {path[-40:]:<42} "
                      f"{', '.join(ranker.topk(vt_, 8))}")
        else:
            print("\nMAY-15 SAVED DIRECTIONS: magnitudes only, "
                  "no vectors stored — not recoverable from this file")
    except Exception as ex:
        print(f"\nMAY-15 SAVED DIRECTIONS: {ex}")

    # raycast (original Layer 18 code)
    if fdir is not None:
        try:
            from consequence_engine import raycast
            out = raycast(np.asarray(anchor_np, dtype=np.float32),
                          fdir.numpy(), depths=[1.5, 2.0, 3.0], top_k=6)
            print("\nRAYCAST (consequence_engine, fed forbidden_dir):")
            print("  " + str(out)[:600])
        except Exception as ex:
            print(f"\nRAYCAST: not fired ({ex})")

    # entity retention (battery-native)
    if entities:
        print("\nENTITY RETENTION (battery-native; substring, per model):")
        order = list(fr) + list(lo)
        for ent in entities:
            row = "".join("Y " if ent.lower() in resp[m].lower() else ". "
                          for m in order)
            print(f"  {ent:<18} {row}  ({' '.join(m[:6] for m in order)})"
                  if ent == entities[0] else f"  {ent:<18} {row}")

    # march table reproduction
    print("\nMARCH TABLE, JULY DATA — cos(word, model_response):")
    mwords = []
    perp_all = next((v for n, v, _ in res_cols if n == "perp/ALL"), None)
    if perp_all is not None:
        mwords += ranker.topk(perp_all, 5)
    mwords += [w for w in ("incest", "groping", "sibling", "suing")
               if w not in mwords]
    order = list(fr) + list(lo)
    print("  " + f"{'word':<14}" + "".join(f"{m[:7]:>9}" for m in order)
          + f"{'mean':>8}")
    for w in mwords:
        wv = ranker.word_vec(w)
        if wv is None:
            continue
        cs = [float(torch.dot(wv, resp_vecs[m])) for m in order]
        print("  " + f"{w:<14}" + "".join(f"{c:>9.2f}" for c in cs)
              + f"{sum(cs)/len(cs):>8.2f}")

    # vf_idf on targets
    if HAVE_PC:
        print("\nVF-IDF (targets vs union of all 10):")
        union = " ".join(resp.values())
        efn = lambda ts: model.encode(list(ts))
        for g, d in [("F", fr), ("L", lo)]:
            try:
                for r in vf_idf(TARGETS, union, list(d.values()), efn):
                    if r.vf_idf > 0 or r.preserved_by != "both":
                        print(f"  {g}: {r.concept:<12} vf={r.vf_idf:.3f} "
                              f"by={r.preserved_by}")
            except Exception as ex:
                print(f"  [vf_idf/{g}] {ex}")

    # rank matrices ------------------------------------------------------
    def matrix(title, colset):
        print(f"\n{title}")
        print("  " + f"{'target':<12}"
              + "".join(f"{n:>13}" for n, _, _ in colset))
        hits = {t: [] for t in TARGETS}
        for t in TARGETS:
            row = f"  {t:<12}"
            for n, v, g in colset:
                r = ranker.rank_of(v, t)
                s = tstem[t] in group_said[g]
                row += ("      n/v    " if r is None
                        else f"{r:>11d}{'S' if s else ' '} ")
                if r is not None and r <= TOPK:
                    hits[t].append((n, s))
            print(row)
        return hits

    h1 = matrix("RANK MATRIX A — living channels:", cols)
    h2 = matrix("RANK MATRIX B — resurrected channels:", res_cols)

    conv = {t: h1[t] + h2[t] for t in TARGETS}
    for t in TARGETS:
        for g in donut_words:
            if any(porter_stem(w.lower()) == tstem[t]
                   for w in donut_words[g]):
                conv[t].append((f"donut/{g}", tstem[t] in group_said[g]))
        for g in lexcross:
            if any(porter_stem(w.lower()) == tstem[t]
                   for w in lexcross[g][:TOPK]):
                conv[t].append((f"lexcr/{g}", False))
        if clv_top and t in clv_top:
            conv[t].append(("clv/ALL", tstem[t] in group_said["ALL"]))

    ncols = len(cols) + len(res_cols) + len(donut_words) + len(lexcross) \
        + (1 if clv_top else 0)
    print(f"\nCONVERGENCE ACROSS ERAS ({ncols} firing columns):")
    for t in TARGETS:
        u = [h for h in conv[t] if not h[1]]
        names = ", ".join(n + ("*" if s else "") for n, s in conv[t]) or "-"
        print(f"  {t:<12} top-{TOPK} in {len(conv[t]):>2} "
              f"({len(u):>2} unsaid) :: {names}")

    print("\nNOT FIRED (honest): spiral (impl unread) | logprob entropy, "
          "abstraction gradients (code not located) | wiki edit-velocity "
          "(external) | /withdrawals set (stays dead on purpose)")


if __name__ == "__main__":
    main()
