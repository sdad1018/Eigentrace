"""
omnibus_magnum.py — All applicable channels on the magnum opus corpus.

CORPUS: anamnesis_results/magnum_opus{,_v2}/ — four knowledge probes
(altman_family, sonora_aero, google_dragonfly, operation_mockingbird),
each answered by TEN models: frontier five (chatgpt, claude, gemini,
deepseek, grok) + local five (hermes, llama_8b, mistral_22b, mistral_7b,
qwen_14b).

WHY THE CHANNEL SET DIFFERS FROM THE NEWS OMNIBUS (stated honestly):
these are "what do you know about X" probes with NO source article, so
the source-anchored channels — lexical void, truth-minus-consensus void
vector, spiral — are UNDEFINED here. Running them would be theater.
What this corpus uniquely supports instead:

  logos_v9 / logos_v10 : anti-consensus synthesis on the FRONTIER five
                         (matches production conditions) — the V9->V10
                         continuity check on adversarial material.
  null_space           : least-variance direction of the frontier five.
  gap->local           : kNN of (local_centroid - frontier_centroid) —
                         the direction of what locals say that the
                         RLHF frontier doesn't. The void vector's
                         sibling, with locals standing in for 'truth'.
  gap->frontier        : the reverse direction.

PER-MODEL TABLE per story: response length, refusal flag (short/decline
patterns), cosine to own-group centroid (outlier spotting), and the
frontier<->local centroid gap magnitude — the group-level divergence
this corpus was collected to expose.

METRICS: spec (own title vs other stories' titles), novelty (fraction
of channel words whose stems appear in NO response), escape for the
raycasts, stem-Jaccard agreement matrix across channels.

Run:  python3 omnibus_magnum.py            (all four stories)
      python3 omnibus_magnum.py dragonfly  (substring filter)
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

DIRS = [
    "/mnt/c/Users/M4ISI/eigentrace/anamnesis_results/magnum_opus",
    "/mnt/c/Users/M4ISI/eigentrace/anamnesis_results/magnum_opus_v2",
    "/home/remvelchio/eigentrace/anamnesis_results/magnum_opus",
    "/home/remvelchio/eigentrace/anamnesis_results/magnum_opus_v2",
]
FRONTIER = ("chatgpt", "claude", "gemini", "deepseek", "grok")
K, STEPS, LR, TOPIC_W = 8, 150, 0.05, 0.30
REFUSAL_PAT = re.compile(
    r"\b(i can'?t|i cannot|i won'?t|unable to|i'?m not able|"
    r"can'?t assist|not appropriate|i do not have information)\b", re.I)

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


# ── loaders ──────────────────────────────────────────────────────────
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
        for f in glob.glob(os.path.join(d, "*.txt")):
            base = os.path.basename(f)[:-4]
            sid, mdl = None, None
            for cand in sorted(prompts, key=len, reverse=True):
                if base.startswith(cand + "_"):
                    sid, mdl = cand, base[len(cand) + 1:]
                    break
            if sid is None:  # infer: last 1-2 tokens are the model name
                parts = base.split("_")
                for cut in (2, 1):
                    if len(parts) > cut:
                        sid, mdl = "_".join(parts[:-cut]), "_".join(parts[-cut:])
                        break
            if not sid:
                continue
            txt = open(f, encoding="utf-8", errors="replace").read().strip()
            st = stories.setdefault(sid, {
                "title": prompts.get(sid, {}).get("title", sid),
                "prompt": prompts.get(sid, {}).get("prompt", ""),
                "responses": {}})
            if sid in prompts:
                st["title"] = prompts[sid]["title"]
                st["prompt"] = prompts[sid]["prompt"]
            st["responses"][mdl] = txt
    return stories


# ── geometry ─────────────────────────────────────────────────────────
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
    v = F.normalize(v, p=2, dim=0)
    idx = torch.topk(vm_t @ v.cpu(), k).indices.tolist()
    return [vw[i] for i in idx]


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
    wv = F.normalize(torch.tensor(model.encode(words), dtype=torch.float32),
                     p=2, dim=1)
    own = (wv @ own_t).mean().item()
    oth = (wv @ other_ts.T).mean().item() if other_ts.shape[0] else 0.0
    return own - oth


def novelty(words, resp_stems):
    if not words:
        return float("nan")
    hits = sum(1 for w in words if content_words(w) and all(
        porter_stem(t) not in resp_stems for t in content_words(w)))
    return hits / len(words)


def jac(a, b):
    A = frozenset(porter_stem(t) for w in a for t in content_words(w))
    B = frozenset(porter_stem(t) for w in b for t in content_words(w))
    return len(A & B) / len(A | B) if (A | B) else 0.0


# ── main ─────────────────────────────────────────────────────────────
def main():
    filt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    from geometric_engine import LogosLossV9
    from sentence_transformers import SentenceTransformer
    import consequence_engine as CE

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device=device)
    vw, vm = CE._load_vocab()
    vm_t = F.normalize(torch.tensor(np.asarray(vm, dtype=np.float32)),
                       p=2, dim=1)
    print(f"device={device} | vocab={len(vw)}")

    corpus = {k: v for k, v in load_corpus().items() if filt in k.lower()}
    if not corpus:
        raise SystemExit("no stories matched — check anamnesis_results dirs")
    sids = sorted(corpus)
    print("stories:", ", ".join(f"{s}({len(corpus[s]['responses'])} models)"
                                for s in sids), "\n")

    titles_t = F.normalize(torch.tensor(model.encode(
        [corpus[s]["title"] for s in sids]), dtype=torch.float32), p=2, dim=1)

    V9 = LogosLossV9(temperature_adapt=False).to(device)
    V10 = CosAttract().to(device)
    CH = ["logos_v9", "logos_v10", "null_space", "gap->local",
          "gap->frontier"]
    agg = {c: {"spec": [], "novel": []} for c in CH}

    for si, sid in enumerate(sids):
        st = corpus[sid]
        title, prompt = st["title"], st["prompt"]
        fr = {m: t for m, t in st["responses"].items()
              if any(f in m.lower() for f in FRONTIER)}
        lo = {m: t for m, t in st["responses"].items() if m not in fr}
        all_txt = " ".join(st["responses"].values())
        resp_stems = stems_of(all_txt)

        print("=" * 76)
        print(f"STORY: {title}")
        print(f"  prompt: {prompt[:90]}")
        anchor = torch.tensor(model.encode([title + ". " + prompt])[0],
                              dtype=torch.float32, device=device)

        def embed_group(d):
            if not d:
                return None
            e = torch.tensor(model.encode(list(d.values())),
                             dtype=torch.float32, device=device)
            return F.normalize(e, p=2, dim=1)

        e_fr, e_lo = embed_group(fr), embed_group(lo)
        cen_fr = F.normalize(e_fr.mean(dim=0), p=2, dim=0)
        cen_lo = (F.normalize(e_lo.mean(dim=0), p=2, dim=0)
                  if e_lo is not None else None)

        # per-model table
        print(f"  {'model':<14}{'chars':>7}{'->own cen':>10}  flags")
        for grp, e_g, cen_g in (("F", e_fr, cen_fr), ("L", e_lo, cen_lo)):
            if e_g is None:
                continue
            names = list(fr if grp == "F" else lo)
            for i, m in enumerate(names):
                c = float(F.cosine_similarity(e_g[i].unsqueeze(0),
                                              cen_g.unsqueeze(0)))
                txt = (fr if grp == "F" else lo)[m]
                flag = "REFUSAL?" if (len(txt) < 250 or
                                      REFUSAL_PAT.search(txt[:300])) else ""
                print(f"  {grp}:{m:<12}{len(txt):>7}{c:>10.3f}  {flag}")
        if cen_lo is not None:
            gapmag = 1 - float(F.cosine_similarity(cen_fr.unsqueeze(0),
                                                   cen_lo.unsqueeze(0)))
            print(f"  frontier<->local centroid gap: {gapmag:.4f}")

        words, escape = {}, {}
        x9 = synthesize(e_fr, anchor, V9, 0.15, device)
        x10 = synthesize(e_fr, anchor, V10, 0.75, device)
        words["logos_v9"] = knn(x9, vm_t, vw)
        words["logos_v10"] = knn(x10, vm_t, vw)
        escape["logos_v9"] = 1 - float(F.cosine_similarity(
            x9.unsqueeze(0), cen_fr.unsqueeze(0)))
        escape["logos_v10"] = 1 - float(F.cosine_similarity(
            x10.unsqueeze(0), cen_fr.unsqueeze(0)))
        words["null_space"] = knn(
            torch.tensor(null_space(e_fr.cpu().numpy(),
                                    anchor.cpu().numpy()),
                         dtype=torch.float32), vm_t, vw)
        if cen_lo is not None:
            g = (cen_lo - cen_fr).cpu()
            words["gap->local"] = knn(g, vm_t, vw)
            words["gap->frontier"] = knn(-g, vm_t, vw)
        else:
            words["gap->local"] = words["gap->frontier"] = []

        others = torch.cat([titles_t[:si], titles_t[si + 1:]], dim=0)
        for c in CH:
            sp = spec_score(words[c], titles_t[si], others, model)
            nv = novelty(words[c], resp_stems)
            agg[c]["spec"].append(sp)
            agg[c]["novel"].append(nv)
            esc = f" esc={escape[c]:.3f}" if c in escape else ""
            print(f"  {c:<14} spec={sp:+.4f} novel={nv:.2f}{esc}"
                  f" :: {', '.join(words[c][:6]) or '(empty)'}")
        print("  agreement (stem Jaccard):")
        for a in CH:
            print(f"    {a:<14} " + " ".join(
                f"{jac(words[a], words[b]):.2f}" for b in CH))

    print("\n" + "#" * 76)
    print(f"{'channel':<16}{'mean spec':>11}{'mean novel':>12}  n")
    for c in CH:
        print(f"{c:<16}{np.nanmean(agg[c]['spec']):>11.4f}"
              f"{np.nanmean(agg[c]['novel']):>12.2f}  "
              f"{len(agg[c]['spec'])}")
    print("#" * 76)
    print("Read: gap->local = what locals carry that the frontier doesn't "
          "(the corpus's\nnative question). V9 vs V10 rows = the swap's "
          "continuity check on spicy material.")


if __name__ == "__main__":
    main()
