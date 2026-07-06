"""
logos_ablation.py — Does the spectral suite in LogosLoss V9 actually matter?

THE QUESTION
    V9 = material(MSE) + 0.4*spectral + 0.1*phase + 0.2*transport
         + 0.05*curvature + 0.02*entropy   (five FFT-over-embedding-dim terms)
    plus, in the synthesis loop: +0.15*cos(x,centroid) repulsion and
    -0.30*cos(x,headline) tether, PGD on the unit sphere.

    The FFT terms are basis-dependent (embedding dims have no canonical
    order), so they are either (a) inert decoration around a working
    material+gravity+tether core, or (b) doing real, if unprincipled, work.

THE TEST
    Run the exact synthesis loop twice per story on real archived segments:
      FULL : LogosLossV9 with default weights (production behavior)
      CORE : LogosLossV9 with grace/phase/transport/geometry/entropy = 0
             (pure MSE material term; gravity + tether unchanged)
    Compare where x_star lands.

READING THE RESULT
    mean cos(FULL, CORE) >= 0.98  -> FFT terms are inert. Simplify to V10
        (material + gravity + tether), publish the simplification on the
        withdrawals page, keep every downstream number honest.
    mean cos(FULL, CORE) <  0.95  -> FFT terms move the optimum. They then
        need to EARN the movement: rerun ASI story-specificity per variant
        before any writeup, and describe them as fixed engineered features,
        never as "spectral consistency."
    Between: gray zone — raise N, then decide.

Self-contained: reads segments from the HOME store, embeds with frozen BGE,
replicates the synthesis loop verbatim (150 steps, AdamW lr=0.05,
temperature_adapt=False, centroid init). Optional vocab kNN if
consequence_engine loads. Read-only; touches nothing in production.

Run:  python3 logos_ablation.py [N_stories, default 8]
"""

import glob
import json
import sys

import numpy as np
import torch
import torch.nn.functional as F

SEG_GLOB = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"
N_STORIES = int(sys.argv[1]) if len(sys.argv) > 1 else 8
STEPS, LR = 150, 0.05
GRAVITY_W, TOPIC_W = 0.15, 0.30


def load_stories(n):
    out, seen = [], set()
    for f in sorted(glob.glob(SEG_GLOB), reverse=True):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        a = d.get("attribution") or {}
        title = a.get("story_title") or ""
        mr = a.get("model_responses") or {}
        texts = [t for t in mr.values() if isinstance(t, str) and len(t) > 80]
        if len(texts) >= 3 and title and title not in seen:
            seen.add(title)
            out.append((title, texts[:5]))
        if len(out) >= n:
            break
    return out


def synthesize(model_embs, headline_vec, criterion, device):
    """Verbatim replica of geometric_engine's synthesis loop."""
    raw_centroid = model_embs.mean(dim=0)
    x = F.normalize(raw_centroid, p=2, dim=0).detach().clone().requires_grad_(True)
    opt = torch.optim.AdamW([x], lr=LR, weight_decay=1e-4)
    centroid = F.normalize(raw_centroid, p=2, dim=0).detach()
    anchor = F.normalize(headline_vec, p=2, dim=0).detach()
    N = model_embs.shape[0]
    for _ in range(STEPS):
        opt.zero_grad()
        loss = criterion(x.unsqueeze(0).expand(N, -1), model_embs)
        gravity = F.cosine_similarity(x.unsqueeze(0), centroid.unsqueeze(0))
        pull = F.cosine_similarity(x.unsqueeze(0), anchor.unsqueeze(0))
        (loss + GRAVITY_W * gravity - TOPIC_W * pull).backward()
        opt.step()
        with torch.no_grad():
            x.data = F.normalize(x.data, p=2, dim=0)
    return x.detach()


def main():
    sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
    from geometric_engine import LogosLossV9
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} | stories={N_STORIES} | steps={STEPS}")
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device=device)

    # optional vocab kNN for a word-level view
    vocab_words, vocab_mat = None, None
    try:
        import consequence_engine as CE
        vocab_words, vocab_mat = CE._load_vocab()
        vocab_mat = torch.tensor(np.asarray(vocab_mat), dtype=torch.float32)
        vocab_mat = F.normalize(vocab_mat, p=2, dim=1)
        print(f"vocab loaded: {len(vocab_words)} concepts (kNN view enabled)")
    except Exception as e:
        print(f"vocab kNN disabled ({type(e).__name__}: {e}) — vector metrics only")

    FULL = LogosLossV9(temperature_adapt=False).to(device)
    CORE = LogosLossV9(grace_coeff=0.0, phase_weight=0.0, transport_weight=0.0,
                       geometry_weight=0.0, entropy_weight=0.0,
                       temperature_adapt=False).to(device)

    stories = load_stories(N_STORIES)
    if not stories:
        print("no usable segments found"); return
    print(f"loaded {len(stories)} stories\n")

    agree, jaccards = [], []
    for title, texts in stories:
        embs = torch.tensor(model.encode(texts), dtype=torch.float32, device=device)
        embs = F.normalize(embs, p=2, dim=1)
        head = torch.tensor(model.encode([title])[0], dtype=torch.float32, device=device)

        xf = synthesize(embs, head, FULL, device)
        xc = synthesize(embs, head, CORE, device)

        cos_fc = float(F.cosine_similarity(xf.unsqueeze(0), xc.unsqueeze(0)))
        cen = F.normalize(embs.mean(dim=0), p=2, dim=0)
        row = (f"cos(FULL,CORE)={cos_fc:+.4f} | "
               f"FULL->cen {float(F.cosine_similarity(xf.unsqueeze(0), cen.unsqueeze(0))):+.3f} "
               f"CORE->cen {float(F.cosine_similarity(xc.unsqueeze(0), cen.unsqueeze(0))):+.3f}")
        agree.append(cos_fc)

        if vocab_mat is not None:
            k = 8
            wf = [vocab_words[i] for i in torch.topk(vocab_mat @ xf.cpu(), k).indices.tolist()]
            wc = [vocab_words[i] for i in torch.topk(vocab_mat @ xc.cpu(), k).indices.tolist()]
            j = len(set(wf) & set(wc)) / len(set(wf) | set(wc))
            jaccards.append(j)
            row += f" | top{k} Jaccard={j:.2f}"
            print(f"  {title[:52]}\n    {row}")
            print(f"    FULL: {', '.join(wf[:6])}\n    CORE: {', '.join(wc[:6])}")
        else:
            print(f"  {title[:52]}\n    {row}")

    a = np.array(agree)
    print("\n" + "=" * 64)
    print(f"mean cos(FULL, CORE) = {a.mean():.4f}  (sd {a.std():.4f}, "
          f"min {a.min():.4f}, n={len(a)})")
    if jaccards:
        print(f"mean top-8 word Jaccard = {np.mean(jaccards):.2f}")
    print("=" * 64)
    if a.mean() >= 0.98:
        print("VERDICT: FFT suite is inert -> simplify to V10 "
              "(material + gravity + tether); log on /withdrawals.")
    elif a.mean() < 0.95:
        print("VERDICT: FFT terms move the optimum -> they must now earn it: "
              "rerun ASI story-specificity per variant before any writeup.")
    else:
        print("VERDICT: gray zone -> rerun with more stories "
              f"(python3 logos_ablation.py {max(16, N_STORIES * 2)}).")


if __name__ == "__main__":
    main()
