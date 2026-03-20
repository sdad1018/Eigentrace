"""
EigenTrace — LLM Output Quality Filter
========================================
Measures directness and stance in text using:
  - POS bigram transition matrices (register-invariant cadence)
  - Modal/hedge density (epistemic stance)
  - Jensen-Shannon divergence (register-invariant distance)

MIT License
"""

from __future__ import annotations
import re
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

def _nltk():
    import nltk
    return nltk

def _ensure_nltk():
    nltk = _nltk()
    for resource in ('punkt', 'averaged_perceptron_tagger',
                     'punkt_tab', 'averaged_perceptron_tagger_eng'):
        try:
            nltk.data.find(f'tokenizers/{resource}')
        except LookupError:
            try:
                nltk.download(resource, quiet=True)
            except Exception:
                pass
    return nltk

_UNIVERSAL_TAGS = [
    'CC','CD','DT','EX','FW','IN','JJ','JJR','JJS',
    'LS','MD','NN','NNS','NNP','NNPS','PDT','POS',
    'PRP','PRP$','RB','RBR','RBS','RP','SYM','TO',
    'UH','VB','VBD','VBG','VBN','VBP','VBZ','WDT',
    'WP','WP$','WRB'
]
_TAG2ID = {t: i for i, t in enumerate(_UNIVERSAL_TAGS)}
K = len(_UNIVERSAL_TAGS)

_PUNCT_TAGS = frozenset({'.', ',', ':', ';', '``', "''",
                          '(', ')', '-LRB-', '-RRB-', '#', '$'})

_HEDGE_LEXICON = frozenset({
    # Modal hedges (unambiguous in any context)
    'may', 'might', 'could', 'would', 'should', 'possibly',
    'perhaps', 'likely', 'unlikely',
    # Epistemic verbs
    'suggest', 'suggests', 'suggested', 'seem', 'seems',
    'appeared', 'appears', 'tend', 'tends',
    # Complexity shields (almost never used in direct factual statements)
    'nuanced', 'multifaceted',
    # Vague group references (used to avoid specifics)
    'various', 'perspectives', 'factors',
    # Deflection to external authority
    'experts', 'worth', 'consider', 'consulting', 'recommend',
    # Frequency/degree hedges
    'generally', 'typically', 'often', 'sometimes', 'arguably',
    'approximately', 'potentially', 'partially', 'somewhat',
    'relatively',
})

@dataclass
class EigenMetrics:
    status: str
    directness_score: float
    hedge_density: float
    markov_distance: Optional[float]
    pos_tags: list = field(default_factory=list, repr=False)
    reason: str = ""

    def __str__(self):
        return (f"EigenMetrics(status={self.status}, "
                f"directness={self.directness_score:.3f}, "
                f"hedge_density={self.hedge_density:.4f})")

def _tag_ids(text: str) -> list:
    nltk = _ensure_nltk()
    text = re.sub(r'\s+', ' ', text).strip()
    try:
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)
        ids = [_TAG2ID.get(t, K - 1) for _, t in tagged
               if t not in _PUNCT_TAGS]
    except Exception:
        ids = [0]
    return ids if ids else [0]

def _bigram_matrix(tag_ids: list, alpha: float = 0.05) -> np.ndarray:
    M = np.full((K, K), alpha)
    for a, b in zip(tag_ids[:-1], tag_ids[1:]):
        M[a, b] += 1.0
    M /= M.sum()
    return M

def _js_divergence(M1: np.ndarray, M2: np.ndarray, eps: float = 1e-12) -> float:
    p = M1.flatten() + eps
    q = M2.flatten() + eps
    p /= p.sum()
    q /= q.sum()
    m = 0.5 * (p + q)
    def kl(a, b):
        return float(np.sum(a * np.log(a / b)))
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)

def _hedge_density(text: str) -> float:
    words = re.findall(r'\b\w+\b', text.lower())
    if not words:
        return 0.0
    count = sum(1 for w in words if w in _HEDGE_LEXICON)
    return count / len(words)

def _directness_score(hd: float,
                      markov_dist: Optional[float] = None,
                      reference_hd: float = 0.0) -> float:
    hedge_score = math.exp(-8.0 * hd)
    if markov_dist is not None:
        markov_score = math.exp(-4.0 * markov_dist)
        return 0.6 * hedge_score + 0.4 * markov_score
    return hedge_score

def _classify(score: float) -> str:
    if score >= 0.65:
        return "DIRECT"
    if score <= 0.35:
        return "HEDGED"
    return "UNKNOWN"

class EigenTrace:
    def __init__(self, reference: Optional[str] = None,
                 alpha: float = 0.05, markov_weight: float = 0.7):
        self.alpha = alpha
        self.markov_weight = markov_weight
        self._ref_matrix: Optional[np.ndarray] = None
        self._ref_hd: float = 0.0
        if reference is not None:
            self.set_reference(reference)

    def set_reference(self, text: str) -> None:
        ids = _tag_ids(text)
        self._ref_matrix = _bigram_matrix(ids, self.alpha)
        self._ref_hd = _hedge_density(text)

    def score(self, text: str) -> EigenMetrics:
        ids = _tag_ids(text)
        tags = [_UNIVERSAL_TAGS[i] if i < K else '??' for i in ids]
        hd = _hedge_density(text)
        markov_dist = None
        if self._ref_matrix is not None:
            M = _bigram_matrix(ids, self.alpha)
            markov_dist = _js_divergence(M, self._ref_matrix)
        ds = _directness_score(hd, markov_dist, self._ref_hd)
        status = _classify(ds)
        reason = []
        if hd > 0.15:
            reason.append(f"high hedge density ({hd:.3f})")
        if markov_dist is not None and markov_dist > 0.15:
            reason.append(f"high Markov distance ({markov_dist:.3f})")
        if not reason:
            reason.append("within direct range")
        return EigenMetrics(
            status=status,
            directness_score=round(ds, 4),
            hedge_density=round(hd, 4),
            markov_distance=round(markov_dist, 4) if markov_dist else None,
            pos_tags=tags,
            reason=", ".join(reason),
        )

    def compare(self, text_a: str, text_b: str) -> dict:
        ma = self.score(text_a)
        mb = self.score(text_b)
        delta = ma.directness_score - mb.directness_score
        winner = "a" if delta > 0 else "b" if delta < 0 else "tie"
        return {"winner": winner, "delta": round(abs(delta), 4), "a": ma, "b": mb}

_default_tracer = EigenTrace()

def score(text: str, reference: Optional[str] = None) -> EigenMetrics:
    if reference is not None:
        tracer = EigenTrace(reference=reference)
        return tracer.score(text)
    return _default_tracer.score(text)

def compare(text_a: str, text_b: str, reference: Optional[str] = None) -> dict:
    tracer = EigenTrace(reference=reference)
    return tracer.compare(text_a, text_b)
