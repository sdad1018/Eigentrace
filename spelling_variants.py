#!/usr/bin/env python3
"""spelling_variants.py — British/American spelling of the same word.

EigenTrace's two lexical channels ask whether a source word appears in a model
summary, and both asked with an exact token test. A British source spelling that
the model rewrote in American spelling was therefore recorded as a word the
models did not say:

* `eigentrace_math.source_anchored_void` -> `absent_words` / `absent_ratio`
  (EigenChing axis 2, the daily data export, the Omission Ledger posts);
* `confront10_final_BOTH.derive_channels` Channel A -> the Summary Plus audit page.

Measured, 2026-09-16 (`analysis/experiments_v1/quick_findings/F2_spelling_drops/`):
of the site's 49,941 stored `absent_words`, 459 (0.92%) have their counterpart
spelling in a summary; on the public audit page 2 of the 9 Channel A words are
pure spelling flips — `authorised` (22 of 25 baselines write `authorized`) and
`defence` (20 of 25 write `defense`). Corpus-wide the share of exact-token drops
explained this way is 0.43% (2,709 of 625,843), but per word the bias is large:
a British spelling is recorded as dropped about 90% of the time against about 57%
for an American one.

Rule families implemented here, the six the fix was scoped to:
  -ise/-ize (and -isation/-ization, -iser/-izer, -isable/-izable)
  -our/-or, -re/-er, -ll-/-l-, -ce/-se, -ogue/-og
plus an exception list of words that end in -ise in both varieties (advise,
comprise, exercise, surprise, raise, ...), which the -ise/-ize rule must not
touch, and an ambiguous list (cheque/check, practice/practise, disc/disk, ...)
where the two spellings are different words often enough that a match is not
evidence of the same word. Tables and guards are ported from the audit script
`F2_spelling_drops_main.py`; the families it also measured but this module does
not cover (-wards, ae/oe, and the miscellaneous pairs programme/program,
grey/gray, judgement/judgment) stay outside the rule.

Pure stdlib: importable from the metric path with no new dependency.
"""
from __future__ import annotations

import re
from functools import lru_cache

# ── words that end -ise in every variety: the -ise/-ize rule must skip them ──
ISE_EXCEPTIONS = frozenset({
    "advise", "advertise", "arise", "chastise", "comprise", "compromise",
    "despise", "devise", "disguise", "enterprise", "excise", "exercise",
    "franchise", "improvise", "incise", "merchandise", "premise", "promise",
    "revise", "supervise", "surmise", "surprise", "televise", "expertise",
    "precise", "concise", "paradise", "cruise", "bruise", "noise", "poise",
    "raise", "praise", "rise", "wise", "otherwise", "likewise", "clockwise",
    "anticlockwise", "demise", "reprise", "treatise", "apprise", "circumcise",
    "sunrise", "moonrise", "highrise", "mortise", "tortoise", "turquoise",
    "porpoise", "practise", "valise", "chemise", "cerise", "anise", "malaise",
    "mayonnaise", "polonaise", "denise", "louise", "elise",
})

# ── pairs where the two spellings are also different words ──
AMBIGUOUS = frozenset({
    "cheque", "cheques", "check", "checks", "disc", "discs", "disk", "disks",
    "practice", "practise", "practices", "practises", "practiced", "practicing",
    "practised", "practising", "licence", "license", "licences", "licenses",
})

OUR_STEMS = [
    "colour", "labour", "honour", "behaviour", "favour", "flavour", "harbour",
    "humour", "neighbour", "rumour", "savour", "valour", "vigour", "armour",
    "ardour", "candour", "clamour", "endeavour", "fervour", "odour", "parlour",
    "rigour", "splendour", "tumour", "vapour", "demeanour", "succour",
    "saviour", "arbour", "enamour", "misdemeanour", "rancour", "belabour",
    "glamour",
]
OUR_SUFFIXES = [
    "", "s", "ed", "ing", "er", "ers", "ite", "ites", "able", "ful", "less",
    "ist", "ists", "ism", "ings", "ies", "y", "al", "ally", "ise", "ised",
    "ising", "ize", "ized", "izing", "ish",
]

RE_STEMS = [
    "centre", "metre", "litre", "theatre", "fibre", "calibre", "sombre",
    "spectre", "lustre", "sabre", "meagre", "louvre", "kilometre",
    "millimetre", "centimetre", "nitre", "saltpetre", "ochre", "sceptre",
    "epicentre", "mitre", "goitre", "titre", "reconnoitre", "amphitheatre",
    "nanometre", "micrometre", "kilolitre", "millilitre", "decilitre",
]

LL_STEMS = [
    "travel", "cancel", "label", "model", "fuel", "signal", "channel",
    "counsel", "level", "total", "rival", "equal", "pedal", "quarrel",
    "tunnel", "funnel", "libel", "panel", "shovel", "spiral", "initial",
    "dial", "marvel", "chisel", "duel", "grovel", "medal", "metal", "parcel",
    "pencil", "pummel", "ravel", "revel", "shrivel", "snivel", "stencil",
    "swivel", "trowel", "yodel", "dishevel", "unravel", "apparel", "carol",
    "cavil", "cudgel", "devil", "drivel", "enamel", "gambol", "gravel",
    "kennel", "kernel", "tassel", "tinsel", "gruel", "refuel", "remodel",
    "relabel", "mislabel", "bevel", "barrel", "council", "towel", "trammel",
]
LL_SUFFIXES = ["ed", "ing", "er", "ers", "or", "ors", "ist", "ists", "ous", "ery"]

# UK single-l base <-> US double-l base
SINGLE_L = {
    "enrol": "enroll", "fulfil": "fulfill", "instal": "install",
    "distil": "distill", "instil": "instill", "enthral": "enthrall",
    "appal": "appall", "skilful": "skillful", "wilful": "willful",
    "instalment": "installment", "fulfilment": "fulfillment",
    "enrolment": "enrollment", "enrolments": "enrollments",
    "instalments": "installments", "enrols": "enrolls", "fulfils": "fulfills",
    "instals": "installs", "distils": "distills",
}
# Additional -ll- / -l- pairs the LL_STEMS product does not generate
LL_EXTRA = {
    "woollen": "woolen", "counsellor": "counselor", "counsellors": "counselors",
    "marvellous": "marvelous", "jeweller": "jeweler", "jewellers": "jewelers",
    "jewellery": "jewelry",
}

CE_SE = {
    "defence": "defense", "defences": "defenses", "defenceless": "defenseless",
    "offence": "offense", "offences": "offenses", "pretence": "pretense",
    "pretences": "pretenses", "licence": "license", "licences": "licenses",
    "practise": "practice", "practised": "practiced", "practising": "practicing",
    "practises": "practices",
}

OGUE = {
    "catalogue": "catalog", "catalogues": "catalogs", "catalogued": "cataloged",
    "cataloguing": "cataloging", "dialogue": "dialog", "dialogues": "dialogs",
    "analogue": "analog", "analogues": "analogs", "monologue": "monolog",
    "monologues": "monologs", "epilogue": "epilog", "prologue": "prolog",
    "travelogue": "travelog",
}

PAIRS: dict[str, set[str]] = {}
FAMILY: dict[str, str] = {}


def _add(a: str, b: str, family: str) -> None:
    if a == b:
        return
    PAIRS.setdefault(a, set()).add(b)
    PAIRS.setdefault(b, set()).add(a)
    FAMILY.setdefault(a, family)
    FAMILY.setdefault(b, family)


for _a, _b in SINGLE_L.items():
    _add(_a, _b, "ll/l")
for _a, _b in LL_EXTRA.items():
    _add(_a, _b, "ll/l")
for _a, _b in CE_SE.items():
    _add(_a, _b, "ce/se")
for _a, _b in OGUE.items():
    _add(_a, _b, "ogue/og")
for _s in OUR_STEMS:
    for _suf in OUR_SUFFIXES:
        _add(_s + _suf, _s[:-3] + "or" + _suf, "our/or")
for _s in RE_STEMS:
    _base = _s[:-2]
    for _uk, _us in ((_s, _base + "er"), (_s + "s", _base + "ers"),
                     (_s + "d", _base + "ed"), (_base + "ring", _base + "ering")):
        _add(_uk, _us, "re/er")
for _s in LL_STEMS:
    for _suf in LL_SUFFIXES:
        _add(_s + "l" + _suf, _s + _suf, "ll/l")

_ISE_RE = re.compile(r"^(.+?)(is|iz)(e|ed|es|ing|er|ers|ation|ations|ational|able|ably|ability)$")


def _ise_variants(word: str) -> set[str]:
    """-ise/-ize and derivatives, both directions."""
    m = _ISE_RE.match(word)
    if not m:
        return set()
    root, mid, suf = m.groups()
    if len(root) < 3:
        return set()
    if root + "ise" in ISE_EXCEPTIONS or root + "ize" in ISE_EXCEPTIONS:
        return set()
    # a vowel before "is"/"iz" means the letters belong to the root
    # ("raise", "noise", "seize", "prize"), not to the suffix
    if root[-1] in "aeiou" and suf in ("e", "ed", "es", "ing"):
        return set()
    return {root + ("iz" if mid == "is" else "is") + suf}


@lru_cache(maxsize=None)
def variants(word: str, include_ambiguous: bool = False) -> frozenset:
    """Other spellings of the same word. Empty when the word is not a variant
    form, or when the pair is ambiguous and ambiguous pairs are not wanted."""
    w = (word or "").lower()
    if not w:
        return frozenset()
    if not include_ambiguous and w in AMBIGUOUS:
        return frozenset()
    out = set(PAIRS.get(w, ()))
    out |= _ise_variants(w)
    out.discard(w)
    if not include_ambiguous:
        out -= AMBIGUOUS
    return frozenset(out)


def family(word: str) -> str | None:
    """Which rule family relates this word to its counterpart."""
    w = (word or "").lower()
    if w in FAMILY:
        return FAMILY[w]
    return "ise/ize" if _ise_variants(w) else None


def present_as_variant(word: str, words: set, stems: set = None,
                       stem_fn=None) -> str | None:
    """The counterpart spelling of `word` that the responses actually used, or
    None. `words` is the response vocabulary; pass `stems` and `stem_fn` to allow
    an inflected counterpart (authorised -> authorization) to count too."""
    vs = variants(word)
    if not vs:
        return None
    for v in sorted(vs):
        if v in words:
            return v
    if stems and stem_fn is not None:
        for v in sorted(vs):
            if stem_fn(v) in stems:
                return v
    return None


_TOKEN_RE = re.compile(r"\b[a-z]+\b")


def present_as_variant_in_text(word: str, text: str) -> str | None:
    """Whole-word counterpart test against a raw text."""
    vs = variants(word)
    if not vs:
        return None
    low = (text or "").lower()
    for v in sorted(vs):
        if re.search(r"\b" + re.escape(v) + r"\b", low):
            return v
    return None
