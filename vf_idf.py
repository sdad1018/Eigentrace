"""
vf_idf.py — Void Frequency–Inverse Document Fidelity.

The negative-space sibling of TF-IDF.

TF-IDF(term)  = term_frequency(term, doc) * inverse_document_frequency(term, corpus)
                -> weights what a document is ABOUT, by what it CONTAINS.

VF-IDF(concept) = void_frequency(concept, source) * inverse_document_fidelity(concept, summaries)
                -> weights what a document is about, by what its readers DROP.

  void_frequency(c)            how strongly the SOURCE points at concept c
                               (source-salience: TF-IDF weight of c in the source,
                                boosted for named entities) — high = the source is
                                "about" c.

  inverse_document_fidelity(c) how little the SUMMARIES preserved c
                               = 1 - max cosine(c, any summary sentence)
                               high = every summary dropped it.

A concept scores high on VF-IDF when the source makes it salient AND every summary
let it fall — i.e. a *consequential omission*, not a stopword and not a faithfully
retained fact.

This is a measurement, not a motive detector. A high VF-IDF score means a concept is
salient-in-source and absent-from-summaries; it does NOT claim the omission was
deliberate. Validation that the surfaced concepts are real and story-specific (not
nearest-neighbour noise) is the random-word baseline in void_proper_test.py
(Wilcoxon p < 1e-5, two embedding families).

Deterministic: frozen BAAI/bge-large-en-v1.5, same inputs -> same scores.
"""
from __future__ import annotations
import numpy as np


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def inverse_document_fidelity(
    concept_vec: np.ndarray,
    summary_sentence_vecs: list[np.ndarray],
) -> float:
    """1 - (best cosine between the concept and any summary sentence).

    0.0  -> some summary preserved the concept's meaning well (high fidelity)
    1.0  -> no summary came near it (it was dropped)
    Scored on MEANING, so a reworded synonym counts as retained — only genuine
    loss of meaning raises the score. This is the inverse of TF-IDF's IDF term:
    IDF rewards rareness-across-corpus; IDFid rewards absence-across-summaries.
    """
    if not summary_sentence_vecs:
        return 1.0
    best = max(_cos(concept_vec, s) for s in summary_sentence_vecs)
    return float(np.clip(1.0 - best, 0.0, 1.0))


def vf_idf(
    concepts: list[str],
    concept_vecs: dict[str, np.ndarray],
    source_salience: dict[str, float],
    summary_sentence_vecs: list[np.ndarray],
    normalize_salience: bool = True,
) -> list[tuple[str, float, float, float]]:
    """Score every candidate concept by VF-IDF.

    Args:
      concepts:               candidate concept strings (e.g. the surfaced void words).
      concept_vecs:           {concept: frozen embedding vector}.
      source_salience:        {concept: void-frequency weight} — how much the SOURCE
                              points at it. From source_salience.compute_source_salience
                              (TF-IDF in source + entity boost).
      summary_sentence_vecs:  frozen embeddings of every sentence across all summaries.
      normalize_salience:     scale void-frequency to [0,1] across the candidate set so
                              the two factors are comparable (recommended).

    Returns:
      list of (concept, vf_idf_score, void_frequency, inverse_document_fidelity),
      sorted by vf_idf_score descending. The top entries are the consequential
      omissions: salient in the source, absent from every summary.
    """
    if not concepts:
        return []

    vf_raw = {c: float(source_salience.get(c, 0.0)) for c in concepts}
    if normalize_salience:
        mx = max(vf_raw.values()) if vf_raw else 0.0
        vf = {c: (v / mx if mx > 0 else 0.0) for c, v in vf_raw.items()}
    else:
        vf = vf_raw

    out = []
    for c in concepts:
        v = concept_vecs.get(c)
        if v is None:
            continue
        idfid = inverse_document_fidelity(v, summary_sentence_vecs)
        score = vf[c] * idfid                       # the VF-IDF product
        out.append((c, round(score, 4), round(vf[c], 4), round(idfid, 4)))

    out.sort(key=lambda r: -r[1])
    return out


# ---------------------------------------------------------------------------
# Worked example (no embeddings needed — uses tiny stand-in vectors so the
# arithmetic is inspectable). Run:  python3 vf_idf.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # toy 4-d vectors standing in for frozen bge embeddings
    cvec = {
        "blockade":   np.array([1.0, 0.0, 0.0, 0.0]),
        "ceasefire":  np.array([0.0, 1.0, 0.0, 0.0]),
        "sanctions":  np.array([0.0, 0.0, 1.0, 0.0]),  # this one WAS summarized
        "the":        np.array([0.2, 0.2, 0.2, 0.2]),  # stopword-ish, low salience
    }
    # the source points hard at blockade/ceasefire, less at sanctions, barely at "the"
    salience = {"blockade": 9.0, "ceasefire": 8.0, "sanctions": 6.0, "the": 0.5}
    # the summaries between them covered "sanctions" well, nothing else
    summary_sents = [np.array([0.0, 0.0, 0.97, 0.0])]   # ~ sanctions

    ranked = vf_idf(list(cvec), cvec, salience, summary_sents)
    print(f"{'concept':<12}{'VF-IDF':>9}{'void_freq':>11}{'inv_fidelity':>14}")
    for c, score, vf, idfid in ranked:
        print(f"{c:<12}{score:>9}{vf:>11}{idfid:>14}")
    print("\nReading: 'blockade' and 'ceasefire' top the list — salient in source,")
    print("absent from every summary. 'sanctions' is salient but was retained, so its")
    print("inverse-fidelity is low and it drops out. 'the' is absent but not salient,")
    print("so its void-frequency is low and it drops out. VF-IDF isolates the")
    print("consequential omissions from both the retained facts and the noise.")
