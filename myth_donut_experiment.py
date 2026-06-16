#!/usr/bin/env python3
"""
myth_donut_experiment.py — STANDALONE. Runs Summary Plus's DONUT surfacing on
mythological/convergent-motif texts across a model-familiarity gradient.

SAFETY: imports read-only (VocabTensor, in_domain_void, embed, BIG5_CALLERS).
Writes ONLY to ./myth_results.json in this dir. Touches NO broadcast state, no
segments, no audit_log, no vocab. Run with the stream STOPPED (shares API limits + GPU).

METHOD: uses the DONUT (in_domain_void) — on-topic (sim>outer) AND consensus-absent
(sim<inner) — NOT reconstruct_unaligned_truth (which optimizes toward anti-consensus
and carries a known sign-ambiguity; the donut is the clean, inspectable surfacing).

OUTPUT per motif: the 5 model summaries, the SURFACED DONUT WORDS (what you want to
see), and the MATH (donut size, cross-model divergence, vocab caveat).

HONEST FRAME: surfaced words are on-topic-but-consensus-absent vocabulary in a
contemporary-web-trained geometry (bge-large). A coherent cross-myth residue is a
GEOMETRIC fact, NOT evidence of a historical referent. We report geometry only.
"""
import sys, os, json, time
import numpy as np

# --- make repo importable (run from anywhere) ---
REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO)
os.chdir(REPO)  # vocab/ path is relative in VocabTensor

# === THREE TEXTS spanning the familiarity gradient (Stage 1) ===
# Real public-domain / neutrally-described primary material, length-matched ~150w.
MOTIFS = {
    "flood_high_familiarity": {
        "title": "The Great Flood",
        "familiarity": "HIGH (deeply in training: Genesis, Gilgamesh)",
        # Public-domain KJV Genesis flood, condensed
        "text": (
            "And God saw that the wickedness of man was great in the earth. And the Lord said, "
            "I will destroy man whom I have created from the face of the earth. But Noah found grace "
            "in the eyes of the Lord. And God said unto Noah, Make thee an ark of gopher wood; and "
            "behold, I will bring a flood of waters upon the earth, to destroy all flesh, wherein is "
            "the breath of life; and every thing that is in the earth shall die. And the rain was upon "
            "the earth forty days and forty nights. And the waters prevailed, and all the high hills "
            "that were under the whole heaven were covered. And every living substance was destroyed "
            "which was upon the face of the ground; and Noah only remained alive, and they that were "
            "with him in the ark."
        ),
    },
    "kaggen_low_familiarity": {
        "title": "The Mantis (|Kaggen) Assumes the Form of a Hartebeest",
        "familiarity": "LOW (under-represented: |Xam Bushman folklore)",
        # Bleek & Lloyd 1911, public domain (no copyright on body of work), condensed
        "text": (
            "The Mantis is one who cheated the children, by becoming a hartebeest, by resembling a "
            "dead hartebeest. He feigning death lay in front of the children, when the children went "
            "to seek gambroo; because he wished that the children should cut him up with a stone knife. "
            "The children perceived him, when he had laid himself stretched out, while his horns were "
            "turned backwards. The children said to each other: It is a hartebeest that yonder lies; it "
            "is dead. They broke off stone knives by striking one stone against another, they skinned "
            "the Mantis. The skin of the Mantis snatched itself quickly out of the children's hands. "
            "The other shoulder blade of the Mantis ran forward, while the ribs of the Mantis had "
            "joined themselves on, when they raced. He arose from the ground and ran, while he chased "
            "the children, he being whole."
        ),
    },
    "squatterman_fringe": {
        "title": "The Squatter Man Petroglyph (Z-Pinch Aurora Hypothesis)",
        "familiarity": "FRINGE-SPARSE (Peratt plasma hypothesis, thin in training)",
        # Neutral paraphrase of Peratt 2003 hypothesis (not reproducing blog text)
        "text": (
            "Across rock art on every inhabited continent appears a recurring figure: a human-like "
            "form flanked by circles or toruses, often called the squatting man or squatter man. The "
            "plasma physicist Anthony Peratt proposed that this worldwide motif records an intense "
            "auroral event in prehistory. In high-current electrical discharge experiments, a column "
            "of plasma develops doughnut-like rings around it, bent by magnetic fields induced by the "
            "current flow, producing a form resembling the carved figure. Peratt argued that if the "
            "solar wind had increased by one to two orders of magnitude millennia ago, an intense "
            "z-pinch aurora would have hung in the sky, witnessed simultaneously by distant cultures "
            "with no contact, who each carved what they saw. Mainstream archaeology instead reads the "
            "figures as stylized human forms or trance imagery from the nervous system."
        ),
    },
}

OUTER = 0.52   # on-topic ring
INNER = 0.60   # consensus-absent hole
DONUT_K = 15   # how many surfaced words to report

def main():
    print("=== Myth Donut Experiment (standalone, donut surfacing) ===\n")

    # read-only imports from the repo
    print("Importing repo modules (read-only)...")
    try:
        from latent_retrieval import VocabTensor
        from geometric_engine import get_engine
        import proxy_auditor as pa
    except Exception as e:
        print(f"IMPORT FAILED: {e}"); return 1

    # load env keys for the API callers
    # (callers need OPENAI_API_KEY etc.; user runs: set -a; . .env; set +a  before this)
    callers = pa.BIG5_CALLERS
    print(f"Callers available: {list(callers.keys())}")

    print("Loading VocabTensor (184k words)...")
    vt = VocabTensor("vocab")

    print("Loading embedder...")
    ge = get_engine()  # GeometricPerturbationEngine, has embed_texts on cpu
    def embed(texts):
        return np.array(ge.embed_texts(texts if isinstance(texts,list) else [texts]))

    results = {}
    for key, motif in MOTIFS.items():
        print(f"\n{'='*60}\n{motif['title']}\n  familiarity: {motif['familiarity']}\n{'='*60}")
        text = motif["text"]

        # 1. get 5 model summaries of the myth text
        prompt = ("Summarize the following text in 2-3 sentences, faithfully:\n\n" + text)
        summaries = {}
        for name, caller in callers.items():
            try:
                txt, err = caller(prompt)
                if txt and txt.strip():
                    summaries[name] = txt.strip()
                    print(f"  [{name}] {txt.strip()[:80]}...")
                else:
                    print(f"  [{name}] (empty/err: {str(err)[:50]})")
            except Exception as e:
                print(f"  [{name}] EXC {str(e)[:50]}")
            time.sleep(0.5)  # gentle on rate limits

        if len(summaries) < 3:
            print("  <3 summaries — skipping motif"); results[key]={"error":"insufficient summaries"}; continue

        # 2. embed summaries + headline(text), build centroid + response vecs
        names = list(summaries.keys())
        resp_vecs = embed([summaries[n] for n in names])           # (N,1024)
        resp_vecs = resp_vecs / (np.linalg.norm(resp_vecs,axis=1,keepdims=True)+1e-8)
        centroid = resp_vecs.mean(0); centroid /= (np.linalg.norm(centroid)+1e-8)
        headline_vec = embed(text)[0]; headline_vec /= (np.linalg.norm(headline_vec)+1e-8)

        # 3. THE DONUT: on-topic, consensus-absent words
        donut_result = vt.in_domain_void(
            centroid=centroid, response_vecs=resp_vecs, headline_vec=headline_vec,
            k=DONUT_K, outer_threshold=OUTER, inner_threshold=INNER,
        )
        # in_domain_void returns (list_of_(word,score), void_centroid_vec)
        if isinstance(donut_result, tuple) and len(donut_result) == 2 and isinstance(donut_result[0], list):
            donut, _void_centroid = donut_result
        else:
            donut = donut_result
        donut_words = [w for w, _ in donut]
        print(f"\n  >>> SURFACED DONUT WORDS (on-topic, consensus-absent):")
        print(f"      {', '.join(donut_words)}")

        # 4. MATH: cross-model divergence (mean pairwise cosine distance)
        N=len(names); dists=[]
        for i in range(N):
            for j in range(i+1,N):
                dists.append(1 - float(resp_vecs[i] @ resp_vecs[j]))
        divergence = float(np.mean(dists)) if dists else 0.0
        # donut "size" = how many vocab words satisfy the donut (sample at this k; report scores)
        donut_scores = [s for _,s in donut]
        print(f"  MATH: cross-model divergence={divergence:.4f} | donut top score={max(donut_scores):.3f} | n_summaries={N}")

        results[key] = {
            "title": motif["title"], "familiarity": motif["familiarity"],
            "summaries": summaries, "donut_words": donut_words,
            "donut_scores": [round(s,4) for s in donut_scores],
            "cross_model_divergence": divergence,
        }

    # 5. cross-myth residue: overlap of donut words across motifs
    print(f"\n{'='*60}\nCROSS-MYTH RESIDUE (donut-word overlap)\n{'='*60}")
    sets = {k:set(v.get("donut_words",[])) for k,v in results.items() if "donut_words" in v}
    keys=list(sets.keys())
    for i in range(len(keys)):
        for j in range(i+1,len(keys)):
            common = sets[keys[i]] & sets[keys[j]]
            print(f"  {keys[i]} ∩ {keys[j]}: {sorted(common) if common else '(none)'}")
    if len(sets)>=3:
        allcommon = set.intersection(*sets.values())
        print(f"  COMMON TO ALL: {sorted(allcommon) if allcommon else '(none)'}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "myth_results.json")
    # write to script dir, NOT the repo
    json.dump(results, open(out_path,"w"), indent=2)
    print(f"\nSaved: {out_path}")
    print("\nHONEST NOTE: surfaced words are on-topic/consensus-absent vocabulary in a")
    print("contemporary-web-trained geometry. Overlap across myths is a geometric fact,")
    print("NOT evidence of a shared historical referent.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
