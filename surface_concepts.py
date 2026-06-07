#!/usr/bin/env python3
"""
surface_concepts.py — STAGE 1 of the ASI experiment: surfacing only, no model calls.

Surfaces concepts THREE stories x TWO methods so we can eyeball before spending
API calls on the full ASI run:

  Method DONUT  = in_domain_void: on-topic (sim_to_headline high) but absent from
                  consensus (sim_to_centroid low). The defensible one.
  Method LOGOS  = anti-consensus PGD point's nearest concepts (the spicier one).

Stories:
  A       = Iran blockade (target)
  B_easy  = an unrelated tech/markets story (maximal contrast)
  B_hard  = a DIFFERENT Iran/geopolitics story (near-neighbor adversarial control)

For each story we need the 5 model summaries to build the consensus centroid.
We pull them from the SAVED beats (no re-summarizing, no API calls) — the rollcall
responses already in docs/data. So this stage is FREE.

Run:  python3 surface_concepts.py   (no env / no network needed — all local)
"""
from __future__ import annotations
import sys, json, glob
import numpy as np
sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

# substring matches against corpus titles
STORIES = {
    "A_iran_blockade": "Blockade of Iran and the Strait of Hormuz",
    "B_easy_markets":  None,   # auto-pick a markets/tech story below
    "B_hard_iran":     None,   # auto-pick a DIFFERENT iran/geopolitics story
}


def load_story(match, exclude_title=None):
    for f in sorted(glob.glob("docs/data/*.json")):
        try: d = json.load(open(f))
        except Exception: continue
        for s in d.get("stories", []):
            if s.get("category") == "meta": continue
            if exclude_title and s.get("title") == exclude_title: continue
            if match and match.lower() in s.get("title", "").lower():
                return s
    return None


def autopick(category_keywords, exclude_titles):
    """Find a story in a category with 5 model responses saved."""
    for f in sorted(glob.glob("docs/data/*.json")):
        try: d = json.load(open(f))
        except Exception: continue
        for s in d.get("stories", []):
            if s.get("category") == "meta": continue
            if s.get("title") in exclude_titles: continue
            t = s.get("title", "").lower()
            if not any(k in t for k in category_keywords): continue
            beats = [b for b in s.get("beats", []) if b.get("speaker") in
                     ("ChatGPT","Claude","Gemini","DeepSeek","Grok")]
            if len(beats) >= 4:
                return s
    return None


def model_texts(story):
    return [b.get("text","") for b in story.get("beats", [])
            if b.get("speaker") in ("ChatGPT","Claude","Gemini","DeepSeek","Grok") and b.get("text")]


def main():
    from geometric_engine import GeometricPerturbationEngine
    from latent_retrieval import VocabTensor  # adjust if class name differs
    import inspect

    print("Loading engine + vocab tensor...")
    eng = GeometricPerturbationEngine()
    # locate the vocab tensor the pipeline uses
    try:
        vt = eng.get_vocab_tensor() if hasattr(eng, "get_vocab_tensor") else None
    except Exception:
        vt = None
    if vt is None:
        # construct directly — match how batch_producer builds _vt2
        from latent_retrieval import VocabTensor
        vt = VocabTensor()  # may need a path arg; we'll see the error if so

    # ---- resolve the three stories ----
    A = load_story(STORIES["A_iran_blockade"])
    if not A:
        print("Could not find story A. Edit the match string."); return 1
    A_title = A.get("title","")
    B_hard = autopick(["iran","tehran","hormuz","israel","gaza","nuclear"], {A_title})
    B_easy = autopick(["stock","earnings","amazon","tech","market","nasdaq","shares"], {A_title, B_hard.get("title","") if B_hard else ""})

    stories = {"A (Iran blockade)": A,
               "B_hard (other Iran/geo)": B_hard,
               "B_easy (markets/tech)": B_easy}

    for label, s in stories.items():
        if not s:
            print(f"\n### {label}: NOT FOUND — adjust keywords"); continue
        title = s.get("title","")
        texts = model_texts(s)
        print(f"\n{'='*70}\n### {label}\n{title}\n{'='*70}")
        print(f"  ({len(texts)} model summaries on file)")
        if len(texts) < 2:
            print("  too few summaries to build consensus — skip"); continue

        # embeddings + centroid + headline vec
        emb = np.array(eng.embed_texts(texts))                  # (N,1024)
        emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8)
        centroid = emb.mean(axis=0)
        centroid = centroid / (np.linalg.norm(centroid)+1e-8)
        hvec = np.array(eng.embed_texts([title])[0])
        hvec = hvec / (np.linalg.norm(hvec)+1e-8)

        # ---- METHOD 1: DONUT (in_domain_void) ----
        try:
            donut = vt.in_domain_void(centroid, emb, k=8, headline_vec=hvec)
            print("\n  [DONUT] on-topic, absent-from-consensus:")
            for w, sc in donut[:8]:
                print(f"     {w:24} ({sc:+.3f})")
        except Exception as e:
            print(f"  [DONUT] failed: {e}")

        # ---- METHOD 2: LOGOS (anti-consensus PGD) ----
        # reproduce the pipeline's x_star: push away from centroid, toward headline, project to sphere
        try:
            x = centroid.copy()
            lr = 0.1
            for _ in range(50):
                grad = 0.15 * centroid - 0.30 * hvec   # +away from consensus, -toward topic (per anamnesis_test_battery:215)
                x = x - lr * grad
                x = x / (np.linalg.norm(x)+1e-8)
            logos = vt.nearest_concepts(x, k=8)
            print("\n  [LOGOS] anti-consensus point's nearest concepts:")
            for w, sc in logos[:8]:
                print(f"     {w:24} ({sc:+.3f})")
        except Exception as e:
            print(f"  [LOGOS] failed: {e}")

    print("\n" + "="*70)
    print("EYEBALL CHECK before the full ASI run:")
    print("  1. Do DONUT and LOGOS produce DIFFERENT concepts? (if identical, one is redundant)")
    print("  2. Are A's concepts visibly story-specific, or generic Iran/geopolitics clichés?")
    print("  3. Do A_hard's concepts overlap A's? (high overlap = topic detector, not story analyzer)")
    print("  4. Are the concepts coherent words, or noise/artifacts?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
