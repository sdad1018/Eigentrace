"""
preservation_core.py — EigenTrace fact-preservation and word-derivation math.

Standalone, deterministic, dependency-light. This module contains ONLY the
load-bearing arithmetic for measuring what a summary preserved or dropped:

    1. Word derivation      — frozen Porter stemmer (vendored, no nltk),
                              content-word extraction, stem-set construction.
    2. Salience (void_freq) — TF-IDF salience of a concept in the source.
    3. Fidelity             — TWO independent channels, OR'd:
                                a) cosine channel: max cosine(concept, any
                                   summary sentence) on injected embeddings
                                b) lexical channel: stemmed containment of
                                   the concept's content stems in the summary
                              A concept counts as PRESERVED if EITHER channel
                              says preserved. inv_fidelity = 1 - fidelity.
    4. VF-IDF               — void_freq x inv_fidelity, with per-channel
                              audit trail on every result.

Design rules (match the EigenTrace house standard):
    * No model judges a model. Everything here is arithmetic.
    * The embedding function is INJECTED (embed_fn), never imported —
      this module has no torch/transformers dependency and the same code
      runs identically whether embeddings come from BGE, E5, or a test stub.
    * The stemmer is vendored and frozen. A pip upgrade cannot change what
      counts as a lexical match. Same inputs, same scores, every run.
    * Every VF-IDF result reports WHICH channel preserved the concept
      (or that both missed), so a false-void claim is auditable per-concept.

Why two channels (the honest bound this closes):
    Cosine of a single concept word against a full sentence embedding is a
    noisy preservation proxy — a summary can carry a concept inside a long
    paraphrased clause without any sentence vector sitting near the isolated
    word vector. Word-to-sentence cosine is asymmetric by construction.
    The stemmed-lexical channel catches exactly that case: if the summary
    literally contains the concept's stems, it is preserved regardless of
    what the geometry says. OR-ing the channels is the conservative
    direction — it can only REMOVE false voids, never add them. A concept
    that scores as a void here was missed by geometry AND missed by literal
    stemmed text. That is a strictly harder claim than either alone.

MIT. EigenTrace project.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is required for cosine channel
    np = None


# =====================================================================
# 1. WORD DERIVATION — vendored Porter stemmer (frozen)
# =====================================================================
# Martin Porter's 1980 algorithm, implemented directly from the published
# definition. Vendored so the derivation math cannot drift with a library
# update. Reference: Porter, "An algorithm for suffix stripping" (1980).

_VOWELS = "aeiou"


def _is_cons(word: str, i: int) -> bool:
    ch = word[i]
    if ch in _VOWELS:
        return False
    if ch == "y":
        return i == 0 or not _is_cons(word, i - 1)
    return True


def _measure(stem: str) -> int:
    """Porter's m: number of VC sequences in the stem."""
    m, i, n = 0, 0, len(stem)
    # skip initial consonants
    while i < n and _is_cons(stem, i):
        i += 1
    while i < n:
        # in vowel run
        while i < n and not _is_cons(stem, i):
            i += 1
        if i >= n:
            break
        m += 1
        while i < n and _is_cons(stem, i):
            i += 1
    return m


def _has_vowel(stem: str) -> bool:
    return any(not _is_cons(stem, i) for i in range(len(stem)))


def _ends_double_cons(word: str) -> bool:
    return (
        len(word) >= 2
        and word[-1] == word[-2]
        and _is_cons(word, len(word) - 1)
    )


def _ends_cvc(word: str) -> bool:
    if len(word) < 3:
        return False
    if not (
        _is_cons(word, len(word) - 3)
        and not _is_cons(word, len(word) - 2)
        and _is_cons(word, len(word) - 1)
    ):
        return False
    return word[-1] not in "wxy"


def porter_stem(word: str) -> str:
    """Frozen Porter stemmer. Lowercases input. Deterministic."""
    w = word.lower()
    if len(w) <= 2:
        return w

    # ---- Step 1a
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-2]
    elif w.endswith("ss"):
        pass
    elif w.endswith("s"):
        w = w[:-1]

    # ---- Step 1b
    flag_1b = False
    if w.endswith("eed"):
        if _measure(w[:-3]) > 0:
            w = w[:-1]
    elif w.endswith("ed"):
        if _has_vowel(w[:-2]):
            w = w[:-2]
            flag_1b = True
    elif w.endswith("ing"):
        if _has_vowel(w[:-3]):
            w = w[:-3]
            flag_1b = True
    if flag_1b:
        if w.endswith(("at", "bl", "iz")):
            w += "e"
        elif _ends_double_cons(w) and not w.endswith(("l", "s", "z")):
            w = w[:-1]
        elif _measure(w) == 1 and _ends_cvc(w):
            w += "e"

    # ---- Step 1c
    if w.endswith("y") and _has_vowel(w[:-1]):
        w = w[:-1] + "i"

    # ---- Step 2
    step2 = [
        ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
        ("anci", "ance"), ("izer", "ize"), ("abli", "able"),
        ("alli", "al"), ("entli", "ent"), ("eli", "e"), ("ousli", "ous"),
        ("ization", "ize"), ("ation", "ate"), ("ator", "ate"),
        ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"),
        ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"),
        ("biliti", "ble"),
    ]
    for suf, rep in step2:
        if w.endswith(suf):
            stem = w[: -len(suf)]
            if _measure(stem) > 0:
                w = stem + rep
            break

    # ---- Step 3
    step3 = [
        ("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
        ("ical", "ic"), ("ful", ""), ("ness", ""),
    ]
    for suf, rep in step3:
        if w.endswith(suf):
            stem = w[: -len(suf)]
            if _measure(stem) > 0:
                w = stem + rep
            break

    # ---- Step 4
    step4 = [
        "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement",
        "ment", "ent", "ion", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
    ]
    for suf in step4:
        if w.endswith(suf):
            stem = w[: -len(suf)]
            if suf == "ion" and not stem.endswith(("s", "t")):
                continue
            if _measure(stem) > 1:
                w = stem
            break

    # ---- Step 5a
    if w.endswith("e"):
        stem = w[:-1]
        m = _measure(stem)
        if m > 1 or (m == 1 and not _ends_cvc(stem)):
            w = stem

    # ---- Step 5b
    if _measure(w) > 1 and _ends_double_cons(w) and w.endswith("l"):
        w = w[:-1]

    return w


# =====================================================================
# Tokenization / content words
# =====================================================================

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z'\-]*")

# Frozen stopword list — small on purpose. This is not linguistics, it is
# noise suppression for void_freq; a frozen list beats a drifting import.
STOPWORDS = frozenset("""
a an the and or but if then else of to in on at by for with from as is are
was were be been being am it its it's this that these those there here he
she they them his her their our your my we you i not no nor so too very can
will just do does did doing have has had having would should could may might
must shall about into over under again further once out off up down all any
both each few more most other some such only own same than what which who
whom when where why how s t don now
""".split())


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def content_words(text: str) -> List[str]:
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def stem_set(text: str) -> frozenset:
    """The stemmed content vocabulary of a text. The lexical channel's index."""
    return frozenset(porter_stem(w) for w in content_words(text))


def sentences(text: str) -> List[str]:
    """Deterministic sentence split. Deliberately simple; no ML."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in (s.strip() for s in parts) if p]


# =====================================================================
# 2. SALIENCE — void_freq (TF-IDF salience of a concept in the source)
# =====================================================================

def term_frequencies(text: str) -> Dict[str, float]:
    """Stem-level term frequency of the source, max-normalized to [0,1]."""
    counts: Dict[str, int] = {}
    for w in content_words(text):
        s = porter_stem(w)
        counts[s] = counts.get(s, 0) + 1
    if not counts:
        return {}
    mx = max(counts.values())
    return {s: c / mx for s, c in counts.items()}


def salience(
    concept: str,
    source: str,
    idf: Optional[Dict[str, float]] = None,
    tf: Optional[Dict[str, float]] = None,
) -> float:
    """
    void_freq: how strongly the SOURCE points at the concept.

    For multiword concepts, salience is the mean stem-level TF-IDF of the
    concept's content stems. `idf` is optional and injected — pass your
    corpus-level IDF table (stem -> idf, expected roughly in [0,1] after
    normalization) to weight rarity; omit it and salience is pure
    max-normalized TF, which is the within-document degenerate case.
    Stopwords contribute zero by construction.
    """
    if tf is None:
        tf = term_frequencies(source)
    stems = [porter_stem(w) for w in content_words(concept)]
    if not stems:
        return 0.0
    vals = []
    for s in stems:
        v = tf.get(s, 0.0)
        if idf is not None:
            v *= idf.get(s, 1.0)
        vals.append(v)
    return sum(vals) / len(vals)


# =====================================================================
# 3. FIDELITY — two channels, OR'd
# =====================================================================

EmbedFn = Callable[[Sequence[str]], "np.ndarray"]
# embed_fn(list_of_texts) -> (n, d) array. Inject your frozen BGE wrapper.
# The module never imports a model; determinism is the caller's contract.


def cosine_fidelity(
    concept: str,
    summary_sentences: Sequence[str],
    embed_fn: EmbedFn,
) -> float:
    """
    Channel A (geometric): max cosine between the concept embedding and any
    summary sentence embedding. Clamped to [0,1] (BGE-family similarities
    are non-negative in practice; the clamp makes the contract explicit).
    """
    if np is None:
        raise RuntimeError("numpy required for the cosine channel")
    if not summary_sentences:
        return 0.0
    vecs = embed_fn([concept] + list(summary_sentences))
    c = vecs[0]
    S = vecs[1:]
    c = c / (np.linalg.norm(c) + 1e-12)
    S = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-12)
    best = float(np.max(S @ c))
    return max(0.0, min(1.0, best))


def lexical_fidelity(concept: str, summary_text: str,
                     summary_stems: Optional[frozenset] = None) -> float:
    """
    Channel B (lexical): fraction of the concept's content stems literally
    present in the summary's stemmed vocabulary. 1.0 = every stem present.

    This is the false-void guard: word-to-sentence cosine can miss a concept
    that the summary carries inside a long paraphrased clause. If the stems
    are literally there, the concept was preserved, whatever geometry says.
    """
    if summary_stems is None:
        summary_stems = stem_set(summary_text)
    stems = [porter_stem(w) for w in content_words(concept)]
    if not stems:
        return 0.0
    hits = sum(1 for s in stems if s in summary_stems)
    return hits / len(stems)


def fidelity(
    concept: str,
    summary_text: str,
    embed_fn: Optional[EmbedFn] = None,
    summary_sents: Optional[Sequence[str]] = None,
    summary_stems: Optional[frozenset] = None,
) -> Tuple[float, float, float]:
    """
    Combined preservation score for one concept against one summary.

    Returns (fidelity, cosine_channel, lexical_channel) where
        fidelity = max(cosine_channel, lexical_channel)

    max() IS the OR: a concept is preserved if either channel preserved it.
    This is monotone-conservative for void detection — adding the lexical
    channel can only lower inv_fidelity (remove false voids), never raise it.
    If embed_fn is None the cosine channel is skipped (score 0.0) and the
    lexical channel stands alone.
    """
    cos = 0.0
    if embed_fn is not None:
        if summary_sents is None:
            summary_sents = sentences(summary_text)
        cos = cosine_fidelity(concept, summary_sents, embed_fn)
    lex = lexical_fidelity(concept, summary_text, summary_stems)
    return max(cos, lex), cos, lex


# =====================================================================
# 4. VF-IDF — with per-concept audit trail
# =====================================================================

@dataclass
class ConceptResult:
    concept: str
    vf_idf: float
    void_freq: float          # salience of the concept in the source
    inv_fidelity: float       # 1 - max(cosine, lexical), min across summaries
    cosine_channel: float     # best cosine fidelity across all summaries
    lexical_channel: float    # best lexical fidelity across all summaries
    preserved_by: str         # "cosine" | "lexical" | "both" | "neither"
    per_summary: List[Tuple[float, float]] = field(default_factory=list)
    # per_summary[i] = (cosine, lexical) fidelity against summary i

    @property
    def is_void(self) -> bool:
        return self.preserved_by == "neither"


def _preserved_label(cos: float, lex: float, threshold: float) -> str:
    c, l = cos >= threshold, lex >= threshold
    if c and l:
        return "both"
    if c:
        return "cosine"
    if l:
        return "lexical"
    return "neither"


def vf_idf(
    concepts: Iterable[str],
    source: str,
    summaries: Sequence[str],
    embed_fn: Optional[EmbedFn] = None,
    idf: Optional[Dict[str, float]] = None,
    preserved_threshold: float = 0.5,
) -> List[ConceptResult]:
    """
    VF-IDF(concept) = void_freq(concept) x inv_fidelity(concept)

        void_freq    = TF(-IDF) salience of the concept in the SOURCE
        inv_fidelity = 1 - fidelity, where fidelity for the concept is its
                       BEST preservation across the summary set, and each
                       summary's fidelity is max(cosine, lexical).

    "Best across summaries" is deliberate: for consensus-void work a concept
    only counts as dropped if EVERY summary dropped it on BOTH channels. To
    score a single model instead, pass a one-element summary list.

    preserved_threshold only affects the audit label (`preserved_by`), not
    the continuous scores. Results sorted by VF-IDF descending.
    """
    tf = term_frequencies(source)
    sum_sents = [sentences(s) for s in summaries]
    sum_stems = [stem_set(s) for s in summaries]

    out: List[ConceptResult] = []
    for concept in concepts:
        vf = salience(concept, source, idf=idf, tf=tf)
        per: List[Tuple[float, float]] = []
        best_cos = best_lex = best_fid = 0.0
        for i, summ in enumerate(summaries):
            _, cos, lex = fidelity(
                concept, summ, embed_fn,
                summary_sents=sum_sents[i], summary_stems=sum_stems[i],
            )
            per.append((cos, lex))
            best_cos = max(best_cos, cos)
            best_lex = max(best_lex, lex)
            best_fid = max(best_fid, max(cos, lex))
        inv = 1.0 - best_fid
        out.append(ConceptResult(
            concept=concept,
            vf_idf=vf * inv,
            void_freq=vf,
            inv_fidelity=inv,
            cosine_channel=best_cos,
            lexical_channel=best_lex,
            preserved_by=_preserved_label(best_cos, best_lex,
                                          preserved_threshold),
            per_summary=per,
        ))
    out.sort(key=lambda r: r.vf_idf, reverse=True)
    return out


# =====================================================================
# Source-anchored void (the literal-absence layer, now channel-aware)
# =====================================================================

def source_anchored_void(source: str, summaries: Sequence[str]) -> float:
    """
    Fraction of source content stems appearing in ZERO summaries.
    Literal lexical absence — no embeddings involved. Unchanged math from
    the original layer, now sharing one frozen stemmer with everything else.
    """
    src = stem_set(source)
    if not src:
        return 0.0
    union = frozenset().union(*(stem_set(s) for s in summaries)) \
        if summaries else frozenset()
    missing = sum(1 for s in src if s not in union)
    return missing / len(src)
