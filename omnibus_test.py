"""
omnibus_test.py — Every channel, one harness, on the spicy corpus.

Runs ALL derivation methods side-by-side on the June 14 escalation battery
(Altman/OpenAI board, Gebru, Dragonfly, ...) using the ARCHIVED five-model
summaries — zero frontier API calls, fully local, fully reproducible.

CHANNELS
  lex_void   : source-anchored lexical void — set arithmetic on stems
               (source content words minus everything any summary used),
               ranked by source term frequency. No embeddings.
  void_vec   : eigentrace_math.compute_void_vector — truth-minus-consensus
               direction, kNN'd against the vocab tensor.
  logos_v9   : production LogosLoss V9 synthesis -> kNN.
  logos_v10  : the ablation-validated simplification — cosine attraction
               + 0.75 anti-centroid gravity + 0.30 headline tether -> kNN.
  spiral     : spiral_sampler.convergence_spiral concepts (+entities).
  null_space : least-variance direction of the centered response matrix
               (computed locally via SVD; sign-aligned toward the source).

METRICS per channel per story
  spec    : story-specificity — mean cos(word, own title) minus mean
            cos(word, other battery titles). Higher = more this-story.
  novel   : fraction of top-k words whose stem appears in NO summary
            (the "did escape buy unsaid-ness" caveat from ablation 3).
  escape  : 1 - cos(x_star, centroid), where applicable.
Plus a stem-level cross-channel Jaccard agreement matrix per story and
battery-wide channel means.

Run:  python3 omnibus_test.py            (all stories with archived summaries)
      python3 omnibus_test.py story2     (substring filter on story id)
"""

import glob
import json
import os
import re
import sys

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
sys.path.insert(0, "/home/remvelchio/eigentrace")

HOME_T = "/home/remvelchio/eigentrace"
REPO_T = "/mnt/c/Users/M4ISI/eigentrace"
K = 8
STEPS, LR, TOPIC_W = 150, 0.05, 0.30

# ── word derivation (self-contained, mirrors preservation_core) ──────
try:
    from preservation_core import porter_stem, content_words, stem_set
except Exception:
    _TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]*")
    _STOP = set("a an the and or but if of to in on at by for with from as is are was were be been it its this that these those there he she they them his her their our your my we you i not no so can will just do does did have has had would should could may might about into over under all any each few more most other some such only own same than what which who when where why how".split())
    def porter_stem(w):  # crude fallback
        w = w.lower()
        for suf in ("ing", "edly", "ed", "es", "s", "ly"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[: -len(suf)]
        return w
    def content_words(t):
        return [x.lower() for x in _TOK.findall(t or "")
                if x.lower() not in _STOP and len(x) > 2]
    def stem_set(t):
        return frozenset(porter_stem(w) for w in content_words(t))


# ── loaders (format-tolerant) ─────────────────────────────────────────
def _story_text(d):
    for k in ("text", "source", "body", "content", "article", "full_text",
              "source_text"):
        if isinstance(d.get(k), str) and len(d[k]) > 200:
            return d[k]
    return ""


def load_battery():
    for base in (HOME_T, REPO_T):
        p = os.path.join(base, "escalation_stories.json")
        if os.path.exists(p):
            j = json.load(open(p))
            stories = j.get("stories", j) if isinstance(j, dict) else j
            out = []
            for s in stories:
                sid = s.get("id") or s.get("story_id") or ""
                title = s.get("title") or s.get("headline") or sid
                txt = _story_text(s)
                if sid and txt:
                    out.append({"id": sid, "title": title, "text": txt})
            if out:
                print(f"battery: {p} ({len(out)} stories)")
                return out
    raise SystemExit("escalation_stories.json not found in either tree")


def load_summaries(sid):
    for base in (HOME_T, REPO_T):
        for p in glob.glob(os.path.join(base, f"*{sid}*summar*.json")):
            j = json.load(open(p))
            if isinstance(j, dict) and "summaries" in j:
                j = j["summaries"]
            out = {}
            if isinstance(j, dict):
                for m, v in j.items():
                    if isinstance(v, str) and len(v) > 60:
                        out[m] = v
                    elif isinstance(v, dict):
                        for kk in ("baseline", "step0", "neutral", "response",
                                   "text", "summary"):
                            if isinstance(v.get(kk), str) and len(v[kk]) > 60:
                                out[m] = v[kk]; break
            elif isinstance(j, list):
                for i, v in enumerate(j):
                    if isinstance(v, str) and len(v) > 60:
                        out[f"m{i}"] = v
                    elif isinstance(v, dict):
                        t = v.get("text") or v.get("response") or v.get("summary")
                        if isinstance(t, str) and len(t) > 60:
                            out[v.get("model", f"m{i}")] = t
            if len(out) >= 3:
                return out, p
    return None, None


# ── channels ──────────────────────────────────────────────────────────
class CosAttract(torch.nn.Module):
    def forward(self, pred, truth):
        return (1.0 - F.cosine_similarity(pred, truth, dim=-1)).mean()


def synthesize(embs, head, criterion, gravity_w, device):
    raw = embs.mean(dim=0)
    x = F.normalize(raw, p=2, dim=0).detach().clone().requires_grad_(True)
    opt = torch.optim.AdamW([x], lr=LR, weight_decay=1e-4)
    cen = F.normalize(raw, p=2, dim=0).detach()
    anc = F.normalize(head, p=2, dim=0).detach()
    for _ in range(STEPS):
        opt.zero_grad()
        loss = criterion(x.unsqueeze(0).expand(embs.shape[0], -1), embs)
        g = F.cosine_similarity(x.unsqueeze(0), cen.unsqueeze(0))
        pl = F.cosine_similarity(x.unsqueeze(0), anc.unsqueeze(0))
        (loss + gravity_w * g - TOPIC_W * pl).backward()
        opt.step()
        with torch.no_grad():
            x.data = F.normalize(x.data, p=2, dim=0)
    return x.detach()


def knn(vec_t, vocab_mat, vocab_words, k=K):
    idx = torch.topk(vocab_mat @ vec_t.cpu(), k).indices.tolist()
    return [vocab_words[i] for i in idx]


def lexical_void(source, summaries, title, k=K):
    tstems = stem_set(title)
    sumstems = frozenset().union(*(stem_set(s) for s in summaries))
    counts = {}
    for w in content_words(source):
        st = porter_stem(w)
        if st in sumstems or st in tstems:
            continue
        counts.setdefault(st, [0, w])
        counts[st][0] += 1
    ranked = sorted(counts.values(), key=lambda cv: -cv[0])
    return [w for _, w in ranked[:k]]


def null_space_words(embs_np, src_vec, vocab_mat, vocab_words, k=K):
    X = embs_np - embs_np.mean(axis=0, keepdims=True)
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    d = Vt[-1]
    if np.dot(d, src_vec - embs_np.mean(axis=0)) < 0:
        d = -d
    d = d / (np.linalg.norm(d) + 1e-8)
    return knn(torch.tensor(d, dtype=torch.float32), vocab_mat, vocab_words, k)


# ── metrics ───────────────────────────────────────────────────────────
def spec_score(words, own_t, other_ts, model):
    if not words:
        return float("nan")
    wv = F.normalize(torch.tensor(model.encode(words), dtype=torch.float32),
                     p=2, dim=1)
    own = (wv @ own_t).mean().item()
    oth = (wv @ other_ts.T).mean().item() if other_ts.shape[0] else 0.0
    return own - oth


def novelty(words, sumstems):
    if not words:
        return float("nan")
    hits = sum(1 for w in words
               if all(porter_stem(t) not in sumstems
                      for t in content_words(w)) and content_words(w))
    return hits / len(words)


def jac(a, b):
    A = frozenset().union(*(frozenset([porter_stem(t) for t in content_words(w)])
                            for w in a)) if a else frozenset()
    B = frozenset().union(*(frozenset([porter_stem(t) for t in content_words(w)])
                            for w in b)) if b else frozenset()
    return len(A & B) / len(A | B) if (A | B) else 0.0


# ── main ──────────────────────────────────────────────────────────────
def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    from geometric_engine import LogosLossV9
    from sentence_transformers import SentenceTransformer
    import consequence_engine as CE
    import spiral_sampler as SP
    from eigentrace_math import compute_void_vector

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device=device)
    vw, vm = CE._load_vocab()
    vm_np = np.asarray(vm, dtype=np.float32)
    vm_t = F.normalize(torch.tensor(vm_np), p=2, dim=1)
    print(f"device={device} | vocab={len(vw)}")
    embed_fn = lambda texts: [np.asarray(v, dtype=np.float32)
                              for v in model.encode(list(texts))]

    battery = [s for s in load_battery()
               if filt.lower() in s["id"].lower()]
    usable = []
    for s in battery:
        summ, path = load_summaries(s["id"])
        if summ:
            s["summaries"] = summ
            print(f"  {s['id']}: {len(summ)} archived summaries "
                  f"({os.path.basename(path)})")
            usable.append(s)
        else:
            print(f"  {s['id']}: no archived summaries — skipped")
    if not usable:
        raise SystemExit("no stories with archived summaries matched")

    titles_t = F.normalize(torch.tensor(
        model.encode([s["title"] for s in usable]), dtype=torch.float32),
        p=2, dim=1)

    V9 = LogosLossV9(temperature_adapt=False).to(device)
    V10 = CosAttract().to(device)
    CH = ["lex_void", "void_vec", "logos_v9", "logos_v10", "spiral",
          "null_space"]
    agg = {c: {"spec": [], "novel": []} for c in CH}

    for si, s in enumerate(usable):
        summaries = list(s["summaries"].values())
        sumstems = frozenset().union(*(stem_set(x) for x in summaries))
        embs = F.normalize(torch.tensor(model.encode(summaries),
                                        dtype=torch.float32, device=device),
                           p=2, dim=1)
        head = torch.tensor(model.encode([s["title"]])[0],
                            dtype=torch.float32, device=device)
        src_vec = np.asarray(model.encode([s["text"][:5000]])[0],
                             dtype=np.float32)
        cen = F.normalize(embs.mean(dim=0), p=2, dim=0)
        others = torch.cat([titles_t[:si], titles_t[si + 1:]], dim=0)

        words, escape = {}, {}
        words["lex_void"] = lexical_void(s["text"], summaries, s["title"])
        vv = compute_void_vector(s["text"][:5000], summaries, embed_fn,
                                 vocab_words=vw, vocab_vecs=vm_np, top_k=K)
        words["void_vec"] = vv["void_words"]
        x9 = synthesize(embs, head, V9, 0.15, device)
        x10 = synthesize(embs, head, V10, 0.75, device)
        words["logos_v9"] = knn(x9, vm_t, vw)
        words["logos_v10"] = knn(x10, vm_t, vw)
        escape["logos_v9"] = 1 - float(F.cosine_similarity(
            x9.unsqueeze(0), cen.unsqueeze(0)))
        escape["logos_v10"] = 1 - float(F.cosine_similarity(
            x10.unsqueeze(0), cen.unsqueeze(0)))
        try:
            cw_, ew_, _ = SP.convergence_spiral(s["text"][:5000], summaries)
            words["spiral"] = (list(cw_) + list(ew_))[:K]
        except Exception as e:
            words["spiral"] = []
            print(f"    spiral error: {e}")
        words["null_space"] = null_space_words(
            embs.cpu().numpy().astype(np.float32), src_vec, vm_t, vw)

        print("\n" + "=" * 74)
        print(f"STORY: {s['title'][:68]}")
        print(f"  void magnitude={vv['magnitude']}")
        for c in CH:
            sp_ = spec_score(words[c], titles_t[si], others, model)
            nv_ = novelty(words[c], sumstems)
            agg[c]["spec"].append(sp_)
            agg[c]["novel"].append(nv_)
            esc = f" esc={escape[c]:.3f}" if c in escape else ""
            print(f"  {c:<10} spec={sp_:+.4f} novel={nv_:.2f}{esc}"
                  f" :: {', '.join(words[c][:6]) or '(empty)'}")
        print("  agreement (stem Jaccard):")
        for i, a in enumerate(CH):
            row = " ".join(f"{jac(words[a], words[b]):.2f}" for b in CH)
            print(f"    {a:<10} {row}")

    print("\n" + "#" * 74)
    print(f"{'channel':<12}{'mean spec':>11}{'mean novel':>12}  n")
    for c in CH:
        sp_ = np.nanmean(agg[c]["spec"])
        nv_ = np.nanmean(agg[c]["novel"])
        print(f"{c:<12}{sp_:>11.4f}{nv_:>12.2f}  {len(agg[c]['spec'])}")
    print("#" * 74)
    print("Read: spec = this-story relevance; novel = fraction of words no "
          "summary used.\nThe interesting cells: does any geometric channel "
          "beat lex_void on BOTH?\nAnd: V9 vs V10 on the spicy corpus — the "
          "continuity check for the swap.")


if __name__ == "__main__":
    main()
