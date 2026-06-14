#!/usr/bin/env python3
"""
test_a_teeth_cage.py — Corpus-scale semantic retention test of the "teeth vs cage" thesis.

THESIS: across five rival models, operationally-consequential / harm-attributing source
terms ("teeth": secretly, devastated, killed...) are semantically retained LESS than
institutional / structural terms ("cage": committee, agency, announced...).

METHOD (paraphrase-proof — semantic, not string matching):
  1. Load all June story segments with source_body + >=4 model_responses.
  2. Build TEETH and CAGE centroids from seed terms (frozen bge-large embeddings).
  3. From each source_body, extract content terms; classify each as teeth- or cage-leaning
     by cosine to the two centroids (only terms clearly closer to one side; margin-gated).
  4. SEMANTIC RETENTION of a term = max cosine between the term's embedding and any
     sentence embedding of the concatenated model summaries. (Did the MEANING survive,
     regardless of exact wording.)
  5. Compare mean retention: teeth vs cage. Welch's t-test + Cohen's d.
  6. NULL: random 50/50 term split -> retention gap should vanish. Run N_NULL shuffles.

Run:  python3 test_a_teeth_cage.py
Pre-registration note: thesis + primary metric (semantic retention gap, teeth<cage) and
null (random split shows no gap) fixed BEFORE looking at results. Threshold p<0.01.
"""
import json, glob, os, re, sys, random
import numpy as np

SEG_DIR = "/home/remvelchio/eigentrace/tmp/segments"
JUNE_CUTOFF = 1749200000  # ~ June 2026 mtime
MARGIN = 0.04             # term must be at least this much closer to one centroid
N_NULL = 200
MIN_RESP = 4

TEETH_SEEDS = [
    "secretly","quietly","covertly","deliberately","killed","devastated","forced",
    "caused","attacked","destroyed","seized","slaughtered","bombed","massacred",
    "concealed","suppressed","coerced","exploited","betrayed","abandoned",
]
CAGE_SEEDS = [
    "committee","agency","official","announced","policy","statement","department",
    "meeting","report","framework","official","ministry","commission","council",
    "regulation","spokesperson","initiative","programme","authority","administration",
]

STOP = set("""the a an and or but of to in on at for with from by as is are was were be been
being this that these those it its their his her our your they them we you i he she him
who whom which what when where why how than then so if not no nor can will would could
should may might must have has had do does did about into over under up down out off
more most some any all each both few many much other another such only own same these""".split())


def main():
    print("Loading embedding model (bge-large-en-v1.5)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")

    def embed(texts):
        if not texts: return np.zeros((0,1024))
        return np.array(model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=128))

    # --- centroids ---
    teeth_c = embed(TEETH_SEEDS).mean(axis=0); teeth_c /= np.linalg.norm(teeth_c)
    cage_c  = embed(CAGE_SEEDS).mean(axis=0);  cage_c  /= np.linalg.norm(cage_c)
    print(f"Centroid separation (teeth vs cage cosine): {float(teeth_c @ cage_c):.3f}")

    # --- load segments ---
    files = [f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json"))
             if os.path.getmtime(f) > JUNE_CUTOFF
             and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} candidate segments...")

    teeth_ret, cage_ret = [], []        # per-term semantic retention
    all_terms_per_story = []            # for null: (term, retention, is_teeth)
    n_stories=0; src_lens=[]

    import time as _t
    _t0 = _t.time()
    for _fi, f in enumerate(files):
        if _fi % 250 == 0:
            _el = _t.time()-_t0
            _rate = _fi/_el if _el>0 else 0
            _eta = (len(files)-_fi)/_rate if _rate>0 else 0
            print(f"  [{_fi}/{len(files)}] used={n_stories} stories | {_rate:.1f} files/s | ETA {_eta/60:.1f} min", flush=True)
        try: d = json.load(open(f))
        except: continue
        a = d.get("attribution",{})
        src = a.get("source_body","") or ""
        mr  = a.get("model_responses",{})
        if len(mr) < MIN_RESP or len(src) < 80: continue
        # model summary sentences (the retention target)
        summ = " ".join(mr.values())
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summ) if len(s.strip())>15]
        if len(sents) < 3: continue
        sent_emb = embed(sents)
        if sent_emb.shape[0]==0: continue

        # candidate source terms (content words, dedup)
        words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", src)]
        words = [w for w in dict.fromkeys(words) if w not in STOP]
        if len(words) < 6: continue
        w_emb = embed(words)

        story_terms=[]
        for w, we in zip(words, w_emb):
            ct, cc = float(we @ teeth_c), float(we @ cage_c)
            # classify only clearly-leaning terms
            if abs(ct-cc) < MARGIN: continue
            is_teeth = ct > cc
            # semantic retention: best match into model summary sentences
            ret = float(np.max(sent_emb @ we))
            story_terms.append((w, ret, is_teeth))
            (teeth_ret if is_teeth else cage_ret).append(ret)
        if story_terms:
            all_terms_per_story.append(story_terms)
            n_stories+=1; src_lens.append(len(src))

    teeth_ret=np.array(teeth_ret); cage_ret=np.array(cage_ret)
    print(f"\n=== CORPUS ===")
    print(f"Stories used: {n_stories}  | median source_body chars: {int(np.median(src_lens)) if src_lens else 0}")
    print(f"Teeth terms: {len(teeth_ret)}  | Cage terms: {len(cage_ret)}")

    if len(teeth_ret)<30 or len(cage_ret)<30:
        print("Insufficient terms — aborting."); return 1

    # --- primary result ---
    from scipy import stats
    t, p = stats.ttest_ind(cage_ret, teeth_ret, equal_var=False)  # H1: cage > teeth
    pooled_sd = np.sqrt((teeth_ret.var(ddof=1)+cage_ret.var(ddof=1))/2)
    d = (cage_ret.mean()-teeth_ret.mean())/pooled_sd if pooled_sd>0 else 0
    print(f"\n=== PRIMARY: semantic retention, cage vs teeth ===")
    print(f"  Cage retention:  {cage_ret.mean():.4f}  (n={len(cage_ret)})")
    print(f"  Teeth retention: {teeth_ret.mean():.4f}  (n={len(teeth_ret)})")
    print(f"  Gap (cage - teeth): {cage_ret.mean()-teeth_ret.mean():+.4f}")
    print(f"  Welch's t: {t:.3f}   p: {p:.2e}   Cohen's d: {d:.3f}")
    verdict = "CONFIRMED: cage retained more than teeth" if (p<0.01 and cage_ret.mean()>teeth_ret.mean()) \
              else ("REVERSED" if cage_ret.mean()<teeth_ret.mean() else "NOT SIGNIFICANT")
    print(f"  -> {verdict}")

    # --- NULL: shuffle teeth/cage labels within the pooled term set ---
    pooled = np.concatenate([teeth_ret, cage_ret])
    n_teeth = len(teeth_ret)
    null_gaps=[]
    for _ in range(N_NULL):
        idx = np.random.permutation(len(pooled))
        g = pooled[idx[n_teeth:]].mean() - pooled[idx[:n_teeth]].mean()
        null_gaps.append(g)
    null_gaps=np.array(null_gaps)
    real_gap = cage_ret.mean()-teeth_ret.mean()
    null_p = float(np.mean(np.abs(null_gaps) >= abs(real_gap)))
    print(f"\n=== NULL (random label shuffle, {N_NULL}x) ===")
    print(f"  Null gap mean: {null_gaps.mean():+.4f}  std: {null_gaps.std():.4f}")
    print(f"  Real gap: {real_gap:+.4f}")
    print(f"  Fraction of null gaps >= real: {null_p:.4f}")
    print(f"  -> {'Real gap exceeds null — effect is in the teeth/cage distinction' if null_p<0.01 else 'Real gap within null range — NOT specific to teeth/cage'}")

    # save
    out = {
        "n_stories": n_stories, "median_source_chars": int(np.median(src_lens)) if src_lens else 0,
        "teeth_n": len(teeth_ret), "cage_n": len(cage_ret),
        "cage_retention": float(cage_ret.mean()), "teeth_retention": float(teeth_ret.mean()),
        "gap": float(real_gap), "welch_t": float(t), "p_value": float(p), "cohens_d": float(d),
        "null_gap_mean": float(null_gaps.mean()), "null_p": null_p, "verdict": verdict,
    }
    os.makedirs("anamnesis_results", exist_ok=True)
    open("anamnesis_results/teeth_cage_results.json","w").write(json.dumps(out, indent=2))
    print(f"\nSaved: anamnesis_results/teeth_cage_results.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
