"""
omnibus_wide.py — All six channels, top-50 words each, side by side,
on recent stories from the live segment store. Zero API calls.

CHANNELS (full set — segments carry source_body, so nothing is undefined):
  lex_void   : source content stems no summary used, ranked by source TF
  void_vec   : compute_void_vector (truth - consensus) kNN, top 50
  logos_v9   : production LogosLoss V9 synthesis -> kNN 50
  logos_v10  : cosine attraction + 0.75 gravity + tether -> kNN 50
  spiral     : convergence_spiral concepts+entities (topk raised; may
               return fewer — count reported honestly)
  null_space : least-variance direction of the 5 responses -> kNN 50

OUTPUT
  * terminal: side-by-side 6-column table (words truncated to fit),
    spec/novel/escape per channel, pairwise overlap counts, and the
    MULTI-CHANNEL CONSENSUS list — stems that >=2 and >=3 independent
    methods put in their top-50 (the dual-confirmation view at scale).
  * disk: omnibus_wide_<timestamp>.md with the FULL untruncated lists.

Run:  python3 omnibus_wide.py             (5 newest eligible stories)
      python3 omnibus_wide.py 3           (3 stories)
      python3 omnibus_wide.py 5 iran      (5 stories, title filter)
"""

import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
sys.path.insert(0, "/home/remvelchio/eigentrace")

SEG_GLOB = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"
K = 50
STEPS, LR, TOPIC_W, COL = 150, 0.05, 0.30, 16

try:
    from preservation_core import porter_stem, content_words
except Exception:
    _TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]*")
    def porter_stem(w):
        w = w.lower()
        for s in ("ing", "ed", "es", "s"):
            if w.endswith(s) and len(w) - len(s) >= 3:
                return w[: -len(s)]
        return w
    def content_words(t):
        return [x.lower() for x in _TOK.findall(t or "") if len(x) > 2]


def stems_of(text):
    return frozenset(porter_stem(w) for w in content_words(text))


def word_stems(w):
    return frozenset(porter_stem(t) for t in content_words(w))


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


def knn(vec, vm_t, vw, k=K):
    v = vec if isinstance(vec, torch.Tensor) else torch.tensor(
        vec, dtype=torch.float32)
    v = F.normalize(v.float(), p=2, dim=0)
    idx = torch.topk(vm_t @ v.cpu(), k).indices.tolist()
    return [vw[i] for i in idx]


def lexical_void(source, summaries, title, k=K):
    tstems = stems_of(title)
    sumstems = frozenset().union(*(stems_of(s) for s in summaries))
    counts = {}
    for w in content_words(source):
        st = porter_stem(w)
        if st in sumstems or st in tstems:
            continue
        counts.setdefault(st, [0, w])
        counts[st][0] += 1
    ranked = sorted(counts.values(), key=lambda cv: -cv[0])
    return [w for _, w in ranked[:k]]


def null_space(embs_np, anchor_np):
    X = embs_np - embs_np.mean(axis=0, keepdims=True)
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    d = Vt[-1]
    if np.dot(d, anchor_np - embs_np.mean(axis=0)) < 0:
        d = -d
    return d / (np.linalg.norm(d) + 1e-8)


def spec_score(words, own_t, other_ts, model):
    if not words:
        return float("nan")
    wv = F.normalize(torch.tensor(model.encode(list(words)),
                                  dtype=torch.float32), p=2, dim=1)
    own = (wv @ own_t).mean().item()
    oth = (wv @ other_ts.T).mean().item() if other_ts.shape[0] else 0.0
    return own - oth


def novelty(words, resp_stems):
    if not words:
        return float("nan")
    hits = sum(1 for w in words if content_words(w) and
               word_stems(w).isdisjoint(resp_stems))
    return hits / len(words)


def load_stories(n, filt):
    out, seen = [], set()
    for f in sorted(glob.glob(SEG_GLOB), reverse=True):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        a = d.get("attribution") or {}
        title = a.get("story_title") or ""
        src = a.get("source_body") or ""
        mr = a.get("model_responses") or {}
        texts = [t for t in mr.values() if isinstance(t, str) and len(t) > 80]
        if (len(texts) >= 4 and len(src) > 800 and title
                and title not in seen and filt in title.lower()):
            seen.add(title)
            out.append({"title": title, "source": src[:5000],
                        "summaries": texts[:5]})
        if len(out) >= n:
            break
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    filt = sys.argv[2].lower() if len(sys.argv) > 2 else ""
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
    embed_fn = lambda texts: [np.asarray(v, dtype=np.float32)
                              for v in model.encode(list(texts))]
    print(f"device={device} | vocab={len(vw)} | top-{K} per channel")

    stories = load_stories(n, filt)
    if not stories:
        raise SystemExit("no eligible segments (need source_body>800 + "
                         ">=4 model_responses)")
    print("stories:", " | ".join(s["title"][:40] for s in stories), "\n")
    titles_t = F.normalize(torch.tensor(
        model.encode([s["title"] for s in stories]), dtype=torch.float32),
        p=2, dim=1)

    V9 = LogosLossV9(temperature_adapt=False).to(device)
    V10 = CosAttract().to(device)
    CH = ["lex_void", "vf_idf", "void_vec", "logos_v9", "logos_v10",
          "spiral", "null_space"]
    md = [f"# Omnibus wide run — {datetime.now():%Y-%m-%d %H:%M}",
          f"top-{K} per channel, {len(stories)} stories\n"]

    for si, s in enumerate(stories):
        summaries = s["summaries"]
        resp_stems = frozenset().union(*(stems_of(x) for x in summaries))
        embs = F.normalize(torch.tensor(model.encode(summaries),
                                        dtype=torch.float32, device=device),
                           p=2, dim=1)
        head = torch.tensor(model.encode([s["title"]])[0],
                            dtype=torch.float32, device=device)
        cen = F.normalize(embs.mean(dim=0), p=2, dim=0)
        src_vec = np.asarray(model.encode([s["source"]])[0], dtype=np.float32)

        W = {}
        W["lex_void"] = lexical_void(s["source"], summaries, s["title"])
        try:
            import preservation_core as pc
            _tf = pc.term_frequencies(s["source"])
            _seen, _cand = set(), []
            for w in pc.content_words(s["source"]):
                _st = pc.porter_stem(w)
                if _st not in _seen:
                    _seen.add(_st)
                    _cand.append((w, _tf.get(_st, 0.0)))
            _cand = [w for w, _ in sorted(_cand, key=lambda t: -t[1])[:120]]
            _res = pc.vf_idf(_cand, s["source"], summaries,
                             embed_fn=lambda ts: np.asarray(
                                 model.encode(list(ts))))
            W["vf_idf"] = [r.concept for r in _res if r.vf_idf > 0][:K]
        except Exception as _ve:
            W["vf_idf"] = []
            print(f"  vf_idf error: {_ve}")
        vv = compute_void_vector(s["source"], summaries, embed_fn,
                                 vocab_words=vw, vocab_vecs=vm_np, top_k=K)
        W["void_vec"] = vv["void_words"]
        x9 = synthesize(embs, head, V9, 0.15, device)
        x10 = synthesize(embs, head, V10, 0.75, device)
        W["logos_v9"] = knn(x9, vm_t, vw)
        W["logos_v10"] = knn(x10, vm_t, vw)
        esc = {"logos_v9": 1 - float(F.cosine_similarity(
                   x9.unsqueeze(0), cen.unsqueeze(0))),
               "logos_v10": 1 - float(F.cosine_similarity(
                   x10.unsqueeze(0), cen.unsqueeze(0)))}
        try:
            try:
                cw_, ew_, _ = SP.convergence_spiral(s["source"], summaries,
                                                    topk=K)
            except TypeError:
                cw_, ew_, _ = SP.convergence_spiral(s["source"], summaries)
            W["spiral"] = (list(cw_) + list(ew_))[:K]
        except Exception as e:
            W["spiral"] = []
            print(f"  spiral error: {e}")
        W["null_space"] = knn(torch.tensor(
            null_space(embs.cpu().numpy().astype(np.float32), src_vec),
            dtype=torch.float32), vm_t, vw)

        # header + metrics
        others = torch.cat([titles_t[:si], titles_t[si + 1:]], dim=0)
        print("=" * (COL * 6 + 6))
        print(f"STORY {si+1}: {s['title'][:90]}")
        print(f"  void magnitude={vv['magnitude']} | spiral returned "
              f"{len(W['spiral'])} | " + " ".join(
                  f"{c} esc={esc[c]:.3f}" for c in esc))
        for c in CH:
            sp = spec_score(W[c], titles_t[si], others, model)
            nv = novelty(W[c], resp_stems)
            print(f"  {c:<11} n={len(W[c]):>2} spec={sp:+.4f} novel={nv:.2f}")

        # side-by-side table
        hdr = "".join(f"{c:<{COL}}" for c in CH)
        print("\n  #  " + hdr)
        for i in range(K):
            row = "".join(
                f"{(W[c][i][:COL-1] if i < len(W[c]) else ''):<{COL}}"
                for c in CH)
            print(f"  {i+1:>2} " + row)

        # pairwise overlap + multi-channel consensus
        print("\n  pairwise |top50 ∩ top50| (stem level):")
        for a in CH:
            A = frozenset().union(*(word_stems(w) for w in W[a])) \
                if W[a] else frozenset()
            row = []
            for b in CH:
                B = frozenset().union(*(word_stems(w) for w in W[b])) \
                    if W[b] else frozenset()
                row.append(f"{len(A & B):>3}")
            print(f"    {a:<11} " + " ".join(row))
        cnt = Counter()
        rep = {}
        for c in CH:
            seen_c = set()
            for w in W[c]:
                for st in word_stems(w):
                    if st not in seen_c:
                        cnt[st] += 1
                        seen_c.add(st)
                        rep.setdefault(st, w)
        multi3 = sorted([rep[s_] for s_, k_ in cnt.items() if k_ >= 3])
        multi2 = sorted([rep[s_] for s_, k_ in cnt.items() if k_ == 2])
        print(f"\n  CONFIRMED BY >=3 CHANNELS ({len(multi3)}): "
              + (", ".join(multi3[:20]) or "(none)"))
        print(f"  confirmed by exactly 2 ({len(multi2)}): "
              + (", ".join(multi2[:20]) or "(none)"))

        # markdown dump (full, untruncated)
        md.append(f"\n## {s['title']}\n")
        md.append(f"void magnitude {vv['magnitude']}; "
                  + "; ".join(f"{c} escape {esc[c]:.3f}" for c in esc))
        for c in CH:
            md.append(f"\n**{c}** ({len(W[c])}):\n"
                      + ", ".join(W[c]))
        md.append(f"\n**>=3-channel consensus:** "
                  + (", ".join(multi3) or "(none)"))
        md.append(f"**2-channel:** " + (", ".join(multi2) or "(none)"))

    out = f"omnibus_wide_{datetime.now():%Y%m%d_%H%M}.md"
    open(out, "w").write("\n".join(md))
    print(f"\nfull untruncated lists written to: {out}")


if __name__ == "__main__":
    main()
