#!/usr/bin/env python3
"""
asi_experiment.py — the experiment that decides if Summary Plus is real.

Acceptance Selectivity Index: do models discriminate between concepts surfaced
for THIS story vs concepts surfaced for OTHER stories? If not, Summary Plus
measures agreeableness, not signal.

DESIGN (per red-team):
  Surfacing: BOTH methods, using the REAL pipeline functions
    - DONUT  = vt.in_domain_void (on-topic, absent-from-consensus; zipf+POS filtered)
    - LOGOS  = reconstruct_unaligned_truth (anti-consensus point) -> nearest_concepts
  Stories:
    - A       = target (Iran blockade)
    - B_easy  = unrelated (markets/tech)            [easy control]
    - B_hard  = different Iran-military story        [hard / near-neighbor control]
  Conditions (per concept, blinded shuffle of A+B_easy+B_hard concepts):
    - C_classify : "is this concept relevant to THIS story? yes/no"   (neutral)
    - A_useful   : "would incorporating this make the summary more useful? yes/no" (permissive)
    - B_essential: "is this concept ESSENTIAL? reject unless it is. yes/no"        (strict)
  Models: the 5 frontier via BIG5_CALLERS, temperature 0 (callers already set t=0).

OUTPUT — per method × condition × model and pooled:
  ASI_easy = accept(A) - accept(B_easy)
  ASI_hard = accept(A) - accept(B_hard)
  Interpretation:
    ASI_easy<=0          -> pure agreeableness; segment dead
    ASI_easy>0, hard~=0  -> topic detector, not story analyzer
    both>0               -> real story-specific signal
    accept collapses C->B_essential -> much of "acceptance" was compliance

Run WITH env loaded (needs Wikipedia? no — needs model API keys only):
    set -a; . /home/remvelchio/eigentrace/.env; set +a
    python3 asi_experiment.py
"""
from __future__ import annotations
import sys, json, glob, random, re
import numpy as np
sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

random.seed(42)

# ── EDIT THESE THREE if the auto-match misses ───────────────────────────────
A_MATCH      = "Blockade of Iran and the Strait of Hormuz"
B_HARD_MATCH = "day 38 of US-Israeli attacks"     # different Iran-military story
B_EASY_MATCH = "Alphabet Stock a Buy"             # unrelated markets story
K_PER_METHOD = 6                                   # concepts surfaced per story per method


def load_story(match):
    for f in sorted(glob.glob("docs/data/*.json")):
        try: d = json.load(open(f))
        except Exception: continue
        for s in d.get("stories", []):
            if s.get("category") == "meta": continue
            if match.lower() in s.get("title", "").lower():
                return s
    return None


def model_texts(s):
    return [b.get("text","") for b in s.get("beats", [])
            if b.get("speaker") in ("ChatGPT","Claude","Gemini","DeepSeek","Grok") and b.get("text")]


def surface_both(story, eng, vt):
    """Return {'donut': [words], 'logos': [words]} using the REAL pipeline functions."""
    import torch
    from geometric_engine import reconstruct_unaligned_truth
    texts = model_texts(story)
    title = story.get("title","")
    emb = np.array(eng.embed_texts(texts))
    emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8)
    centroid = emb.mean(axis=0); centroid /= (np.linalg.norm(centroid)+1e-8)
    hvec = np.array(eng.embed_texts([title])[0]); hvec /= (np.linalg.norm(hvec)+1e-8)

    out = {"donut": [], "logos": []}
    # DONUT (returns (results, centroid))
    try:
        res = vt.in_domain_void(centroid, emb, k=K_PER_METHOD, headline_vec=hvec)
        items = res[0] if isinstance(res, tuple) else res
        out["donut"] = [w for w, *_ in items][:K_PER_METHOD]
    except Exception as e:
        print(f"   donut failed for '{title[:40]}': {e}")
    # LOGOS (real function)
    try:
        emb_t = torch.tensor(emb, dtype=torch.float32)
        h_t = torch.tensor(hvec, dtype=torch.float32)
        x_star = reconstruct_unaligned_truth(emb_t, headline_vec=h_t)
        x_np = x_star.cpu().numpy(); x_np /= (np.linalg.norm(x_np)+1e-8)
        out["logos"] = [w for w, _ in vt.nearest_concepts(x_np, k=K_PER_METHOD)][:K_PER_METHOD]
    except Exception as e:
        print(f"   logos failed for '{title[:40]}': {e}")
    return out


PROMPTS = {
    "C_classify": (
        "Below is a news story summary, then a list of concepts. For EACH concept, "
        "answer only YES or NO: is this concept genuinely relevant to THIS specific story? "
        "Format: one line per concept as 'concept: YES' or 'concept: NO'.\n\n"
        "Summary: {summary}\n\nConcepts:\n{concepts}"
    ),
    "A_useful": (
        "Below is a news story summary, then a list of concepts. For EACH concept, "
        "answer only YES or NO: would incorporating this concept make the summary more "
        "useful or informative?\nFormat: 'concept: YES' or 'concept: NO'.\n\n"
        "Summary: {summary}\n\nConcepts:\n{concepts}"
    ),
    "B_essential": (
        "Below is a news story summary, then a list of concepts. Be strict: REJECT every "
        "concept UNLESS it is ESSENTIAL to understanding this story. For EACH concept answer "
        "only YES (essential) or NO.\nFormat: 'concept: YES' or 'concept: NO'.\n\n"
        "Summary: {summary}\n\nConcepts:\n{concepts}"
    ),
}


def parse_yesno(text, concepts):
    """Parse 'concept: YES/NO' lines; return {concept: bool}."""
    verdict = {}
    low = text.lower()
    for c in concepts:
        # find the concept then the next yes/no after it
        m = re.search(re.escape(c.lower()) + r"\s*:?\s*(yes|no)", low)
        if m:
            verdict[c] = (m.group(1) == "yes")
        else:
            # fallback: any yes/no on a line containing the concept
            for line in low.splitlines():
                if c.lower() in line and ("yes" in line or "no" in line):
                    verdict[c] = ("yes" in line and "no" not in line.replace("yes",""))
                    break
    return verdict


def run():
    from geometric_engine import GeometricPerturbationEngine
    from latent_retrieval import VocabTensor
    import proxy_auditor as pa

    print("Loading engine + vocab tensor...")
    eng = GeometricPerturbationEngine()
    vt = VocabTensor("vocab")

    A = load_story(A_MATCH); Bh = load_story(B_HARD_MATCH); Be = load_story(B_EASY_MATCH)
    for nm, s in [("A", A), ("B_hard", Bh), ("B_easy", Be)]:
        if not s:
            print(f"MISSING story {nm} — fix the *_MATCH string."); return 1
    print(f"A     : {A['title'][:60]}")
    print(f"B_hard: {Bh['title'][:60]}")
    print(f"B_easy: {Be['title'][:60]}")

    print("\nSurfacing concepts (real pipeline functions)...")
    cA, cBh, cBe = surface_both(A, eng, vt), surface_both(Bh, eng, vt), surface_both(Be, eng, vt)
    for meth in ("donut", "logos"):
        print(f"\n[{meth}]")
        print(f"   A      : {cA[meth]}")
        print(f"   B_hard : {cBh[meth]}")
        print(f"   B_easy : {cBe[meth]}")

    A_summary = model_texts(A)[0]

    # ── run conditions ──
    results = {}  # (method, condition, model) -> {concept_origin: [bools]}
    for meth in ("donut", "logos"):
        a_set, bh_set, be_set = cA[meth], cBh[meth], cBe[meth]
        if not a_set:
            print(f"\n[{meth}] no A concepts surfaced — skipping method"); continue
        origin = {}
        for w in a_set: origin[w] = "A"
        for w in bh_set: origin.setdefault(w, "B_hard")
        for w in be_set: origin.setdefault(w, "B_easy")
        shuffled = list(origin.keys()); random.shuffle(shuffled)
        concepts_block = "\n".join(f"- {w}" for w in shuffled)

        for cond, tmpl in PROMPTS.items():
            prompt = tmpl.format(summary=A_summary[:600], concepts=concepts_block)
            for model, caller in pa.BIG5_CALLERS.items():
                txt, err = caller(prompt)
                if not txt:
                    print(f"   [{meth}/{cond}/{model}] ERROR: {err}"); continue
                v = parse_yesno(txt, shuffled)
                acc = {"A": [], "B_hard": [], "B_easy": []}
                for w, yes in v.items():
                    acc[origin[w]].append(yes)
                results[(meth, cond, model)] = acc

    # ── compute ASI ──
    print("\n" + "=" * 78)
    print("ACCEPTANCE SELECTIVITY INDEX")
    print("=" * 78)
    def rate(lst): return (sum(lst)/len(lst)) if lst else float("nan")
    for meth in ("donut", "logos"):
        print(f"\n### METHOD: {meth}")
        for cond in PROMPTS:
            rows = [(m, results[(meth, cond, m)]) for m in pa.BIG5_CALLERS if (meth, cond, m) in results]
            if not rows: continue
            print(f"\n  condition: {cond}")
            print(f"  {'model':10} {'acc_A':>7} {'acc_Bhard':>10} {'acc_Beasy':>10} {'ASI_hard':>9} {'ASI_easy':>9}")
            allA, allBh, allBe = [], [], []
            for m, acc in rows:
                rA, rBh, rBe = rate(acc["A"]), rate(acc["B_hard"]), rate(acc["B_easy"])
                allA += acc["A"]; allBh += acc["B_hard"]; allBe += acc["B_easy"]
                ih = (rA - rBh) if not (np.isnan(rA) or np.isnan(rBh)) else float("nan")
                ie = (rA - rBe) if not (np.isnan(rA) or np.isnan(rBe)) else float("nan")
                print(f"  {m:10} {rA:7.2f} {rBh:10.2f} {rBe:10.2f} {ih:+9.2f} {ie:+9.2f}")
            pA, pBh, pBe = rate(allA), rate(allBh), rate(allBe)
            print(f"  {'POOLED':10} {pA:7.2f} {pBh:10.2f} {pBe:10.2f} "
                  f"{pA-pBh:+9.2f} {pA-pBe:+9.2f}")

    print("\n" + "=" * 78)
    print("READ:")
    print("  ASI_easy <= 0           -> agreeableness; segment is dead")
    print("  ASI_easy > 0, hard ~= 0 -> topic detector, not story analyzer")
    print("  both > 0                -> real story-specific signal (segment is real)")
    print("  acc drops C_classify -> B_essential -> that gap was compliance")
    print("  compare donut vs logos ASI -> which surfacing carries more signal")
    return 0


if __name__ == "__main__":
    sys.exit(run())
