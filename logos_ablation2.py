"""
logos_ablation2.py — Round 2: is the FFT suite a realism prior, or an
accidental gain knob?

ROUND 1 RESULT (pre-registered, n=8): mean cos(FULL, CORE) = 0.624,
word Jaccard 0.16, and CORE's kNN words are off-manifold junk. The FFT
suite is functionally load-bearing. Falsified the "inert decoration"
hypothesis — logged.

ROUND 1 ALSO EXPLAINED WHY: the material term is MSE averaged over 1024
dims (~O(0.001) gradients) while gravity/tether are O(1). CORE therefore
optimizes "flee centroid, hug headline" with almost no pull toward the
model embeddings. The FFT terms (weights 0.4/0.2/0.1, O(0.1) gradients)
supply the missing attraction — toward points sharing the magnitude-
spectrum profile of real BGE embeddings.

THE ROUND 2 QUESTION: can a properly-scaled, rotation-invariant cosine
attraction do the same job without any FFT?

    FULL : LogosLossV9, default weights (production)
    COS  : material replaced by mean_i(1 - cos(x, e_i)) at weight 1.0
           (O(1) scale, basis-independent); gravity + tether unchanged

READING THE RESULT
    cos(FULL, COS) >= 0.95 and Jaccard high, COS words coherent
        -> the FFT suite was an accidental gain knob. V10 = cosine
           attraction + gravity + tether: three terms, all defensible,
           all rotation-invariant. Withdrawals entry + clean writeup.
    cos(FULL, COS) < 0.90 AND COS words are junk while FULL's aren't
        -> the spectral profile contributes something a plain attractor
           cannot: a genuine embedding-realism prior. Keep V9, but the
           writeup frames it as a fixed-basis realism regularizer —
           never "spectral consistency" — and ASI story-specificity
           runs per-variant before publication.
    COS coherent but different words than FULL
        -> two valid attractors, different optima; decide on ASI scores,
           not vibes.

Run:  python3 logos_ablation2.py [N_stories, default 8]
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


class CosAttract(torch.nn.Module):
    """Rotation-invariant attraction: mean over models of (1 - cos)."""
    def forward(self, pred, truth):
        return (1.0 - F.cosine_similarity(pred, truth, dim=-1)).mean()


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

    vocab_words, vocab_mat = None, None
    try:
        import consequence_engine as CE
        vocab_words, vocab_mat = CE._load_vocab()
        vocab_mat = torch.tensor(np.asarray(vocab_mat), dtype=torch.float32)
        vocab_mat = F.normalize(vocab_mat, p=2, dim=1)
        print(f"vocab loaded: {len(vocab_words)} concepts")
    except Exception as e:
        print(f"vocab kNN disabled ({type(e).__name__}: {e})")

    FULL = LogosLossV9(temperature_adapt=False).to(device)
    COS = CosAttract().to(device)

    stories = load_stories(N_STORIES)
    print(f"loaded {len(stories)} stories\n")

    agree, jaccards = [], []
    for title, texts in stories:
        embs = torch.tensor(model.encode(texts), dtype=torch.float32, device=device)
        embs = F.normalize(embs, p=2, dim=1)
        head = torch.tensor(model.encode([title])[0], dtype=torch.float32, device=device)

        xf = synthesize(embs, head, FULL, device)
        xs = synthesize(embs, head, COS, device)

        cos_fs = float(F.cosine_similarity(xf.unsqueeze(0), xs.unsqueeze(0)))
        cen = F.normalize(embs.mean(dim=0), p=2, dim=0)
        agree.append(cos_fs)
        row = (f"cos(FULL,COS)={cos_fs:+.4f} | "
               f"FULL->cen {float(F.cosine_similarity(xf.unsqueeze(0), cen.unsqueeze(0))):+.3f} "
               f"COS->cen {float(F.cosine_similarity(xs.unsqueeze(0), cen.unsqueeze(0))):+.3f}")

        if vocab_mat is not None:
            k = 8
            wf = [vocab_words[i] for i in torch.topk(vocab_mat @ xf.cpu(), k).indices.tolist()]
            ws = [vocab_words[i] for i in torch.topk(vocab_mat @ xs.cpu(), k).indices.tolist()]
            j = len(set(wf) & set(ws)) / len(set(wf) | set(ws))
            jaccards.append(j)
            print(f"  {title[:52]}\n    {row} | top{k} Jaccard={j:.2f}")
            print(f"    FULL: {', '.join(wf[:6])}\n    COS : {', '.join(ws[:6])}")
        else:
            print(f"  {title[:52]}\n    {row}")

    a = np.array(agree)
    print("\n" + "=" * 64)
    print(f"mean cos(FULL, COS) = {a.mean():.4f}  (sd {a.std():.4f}, "
          f"min {a.min():.4f}, n={len(a)})")
    if jaccards:
        print(f"mean top-8 word Jaccard = {np.mean(jaccards):.2f}")
    print("=" * 64)
    if a.mean() >= 0.95 and (not jaccards or np.mean(jaccards) >= 0.5):
        print("VERDICT: gain-knob confirmed -> V10 = cosine attraction + "
              "gravity + tether. Simplify, log on /withdrawals, write it up.")
    elif a.mean() < 0.90:
        print("VERDICT: spectral realism prior is real -> keep V9 under the "
              "realism-prior framing; ASI per-variant before any writeup. "
              "READ THE COS WORD LISTS: junk = prior earns keep; coherent = "
              "two valid attractors, decide on ASI.")
    else:
        print("VERDICT: gray zone -> read the word lists, then raise N: "
              f"python3 logos_ablation2.py {max(16, N_STORIES * 2)}")


if __name__ == "__main__":
    main()
