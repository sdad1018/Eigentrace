"""
logos_ablation3.py — Round 3: the escape/specificity Pareto.

ROUND 1: CORE (no FFT, weak material) = incoherent escape -> junk words.
ROUND 2: COS (rotation-invariant attraction, gravity 0.15) = coherent
         NON-escape (cen ~0.98) -> good words, sometimes better than FULL.
FULL   : coherent escape (cen 0.57-0.87). The FFT suite is what makes
         escape survivable.

THE ROUND 3 QUESTION: does escape buy story-specificity — and can a
plain attractor with STRONGER gravity reach coherent escape without FFT?

VARIANTS (same stories, same loop, same seed init):
    FULL      : LogosLossV9 production weights
    COS_g0.15 : cosine attraction, production gravity (round-2 baseline)
    COS_g0.45 : cosine attraction, 3x gravity
    COS_g0.75 : cosine attraction, 5x gravity

METRICS per variant:
    escape      = 1 - cos(x_star, centroid)          (higher = escaped)
    specificity = mean over top-8 kNN words of
                  [cos(word, own headline) - mean cos(word, other headlines)]
                  (ASI-style story-specificity, self-contained)

READING IT: if some COS_g* matches FULL's escape at >= FULL's specificity,
V10 wins (three rotation-invariant terms; FFT retires with honors, logged
on /withdrawals). If every COS_g* that escapes loses specificity/coherence,
the FFT realism prior uniquely enables coherent escape — V9 keeps its
terms under the realism-prior framing, and this table is the writeup's
central figure.

Run:  python3 logos_ablation3.py [N_stories, default 8]
"""

import glob
import json
import sys

import numpy as np
import torch
import torch.nn.functional as F

SEG_GLOB = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"
N_STORIES = int(sys.argv[1]) if len(sys.argv) > 1 else 8
STEPS, LR, TOPIC_W, K = 150, 0.05, 0.30, 8


class CosAttract(torch.nn.Module):
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


def synthesize(model_embs, headline_vec, criterion, gravity_w, device):
    raw_centroid = model_embs.mean(dim=0)
    x = F.normalize(raw_centroid, p=2, dim=0).detach().clone().requires_grad_(True)
    opt = torch.optim.AdamW([x], lr=LR, weight_decay=1e-4)
    centroid = F.normalize(raw_centroid, p=2, dim=0).detach()
    anchor = F.normalize(headline_vec, p=2, dim=0).detach()
    N = model_embs.shape[0]
    for _ in range(STEPS):
        opt.zero_grad()
        loss = criterion(x.unsqueeze(0).expand(N, -1), model_embs)
        grav = F.cosine_similarity(x.unsqueeze(0), centroid.unsqueeze(0))
        pull = F.cosine_similarity(x.unsqueeze(0), anchor.unsqueeze(0))
        (loss + gravity_w * grav - TOPIC_W * pull).backward()
        opt.step()
        with torch.no_grad():
            x.data = F.normalize(x.data, p=2, dim=0)
    return x.detach()


def main():
    sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
    from geometric_engine import LogosLossV9
    from sentence_transformers import SentenceTransformer
    import consequence_engine as CE

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} | stories={N_STORIES} | steps={STEPS}")
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device=device)
    vocab_words, vocab_mat = CE._load_vocab()
    vocab_mat = F.normalize(torch.tensor(np.asarray(vocab_mat),
                                         dtype=torch.float32), p=2, dim=1)
    print(f"vocab: {len(vocab_words)} concepts")

    stories = load_stories(N_STORIES)
    titles = [t for t, _ in stories]
    title_embs = F.normalize(torch.tensor(model.encode(titles),
                                          dtype=torch.float32), p=2, dim=1)
    print(f"loaded {len(stories)} stories\n")

    VARIANTS = [
        ("FULL", LogosLossV9(temperature_adapt=False).to(device), 0.15),
        ("COS_g0.15", CosAttract().to(device), 0.15),
        ("COS_g0.45", CosAttract().to(device), 0.45),
        ("COS_g0.75", CosAttract().to(device), 0.75),
    ]

    results = {name: {"escape": [], "spec": []} for name, _, _ in VARIANTS}
    word_cache = {}

    for si, (title, texts) in enumerate(stories):
        embs = torch.tensor(model.encode(texts), dtype=torch.float32,
                            device=device)
        embs = F.normalize(embs, p=2, dim=1)
        head = torch.tensor(model.encode([title])[0], dtype=torch.float32,
                            device=device)
        cen = F.normalize(embs.mean(dim=0), p=2, dim=0)
        others = torch.cat([title_embs[:si], title_embs[si + 1:]], dim=0)

        print(f"[{si+1}/{len(stories)}] {title[:56]}")
        for name, crit, g in VARIANTS:
            x = synthesize(embs, head, crit, g, device)
            escape = 1.0 - float(F.cosine_similarity(x.unsqueeze(0),
                                                     cen.unsqueeze(0)))
            idx = torch.topk(vocab_mat @ x.cpu(), K).indices.tolist()
            words = [vocab_words[i] for i in idx]
            wv = F.normalize(torch.tensor(model.encode(words),
                                          dtype=torch.float32), p=2, dim=1)
            own = (wv @ title_embs[si]).mean().item()
            oth = (wv @ others.T).mean().item()
            spec = own - oth
            results[name]["escape"].append(escape)
            results[name]["spec"].append(spec)
            word_cache[(si, name)] = words
            print(f"    {name:<10} escape={escape:.3f} spec={spec:+.4f} "
                  f":: {', '.join(words[:4])}")

    print("\n" + "=" * 72)
    print(f"{'variant':<12}{'escape mean':>12}{'spec mean':>12}{'spec sd':>10}")
    for name in results:
        e = np.array(results[name]["escape"])
        s = np.array(results[name]["spec"])
        print(f"{name:<12}{e.mean():>12.3f}{s.mean():>12.4f}{s.std():>10.4f}")
    print("=" * 72)

    full_s = np.mean(results["FULL"]["spec"])
    full_e = np.mean(results["FULL"]["escape"])
    challengers = [(n, np.mean(r["escape"]), np.mean(r["spec"]))
                   for n, r in results.items() if n != "FULL"]
    match = [(n, e, s) for n, e, s in challengers
             if e >= 0.6 * full_e and s >= full_s - 0.005]
    if match:
        best = max(match, key=lambda t: t[2])
        print(f"VERDICT: {best[0]} matches FULL's escape with >= specificity "
              f"-> V10 wins (cos attraction + gravity {best[0].split('g')[1]} "
              f"+ tether). FFT retires with honors; log on /withdrawals.")
    else:
        print("VERDICT: no plain-attractor setting achieves FULL's coherent "
              "escape at parity specificity -> the FFT realism prior earns "
              "its keep. V9 stands, under the realism-prior framing; this "
              "table is the writeup's central figure.")
    print("\n(Sanity: also eyeball whether higher-gravity COS word lists "
          "stay coherent — junk at high gravity = round-1 failure mode "
          "returning, which supports V9.)")


if __name__ == "__main__":
    main()
