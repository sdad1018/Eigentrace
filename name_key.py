#!/usr/bin/env python3
"""name_key.py — one rule for deciding that a name is present in a text.

Before 2026-09-19 every caller that scored name presence keyed a name on its LAST
whitespace token, lowercased, and then matched that key case-insensitively:

    head = name.split()[-1].lower()          # confront_keeper_v3.py:76
    if ent in resp or ent.lower() in resp.lower(): ...   # eigentrace_math.py:609

Both halves are wrong in ways the September 2026 audits measured:

* LAST TOKEN. For a family-first name the last token is the GIVEN name, so
  "Xi Jinping" was keyed `jinping` and a summary writing "Xi" or "President Xi"
  scored as an erasure. 21 of the 48 Xi model-drops in the corpus names panel are
  false this way (`analysis/experiments_v1/name_order_audit/REPORT.md` §2). The
  corrected family keys for the affected names (Xi, Li, Wei, Han, Cho, Fu, Jo,
  Roh, Ahn, Son, Guo, Lin, Xu, Kim, Min) are all shorter than four letters, so the
  scratchpad scorer's `len(key) < 4 -> drop` rule could not have used them even if
  the order had been right.
* PARTICLES. "Ahmed al-Sharaa" keyed `alshara` because the hyphen is not a space,
  so a summary writing "Sharaa" scored as an erasure (audit category C, 80 surfaces).
* PRESS ALIASES. The press writes Tedros, Lula, Jokowi, MBS; the key was
  `ghebreyesus`, `silva`, `widodo`, `salman` (category B).
* SUBSTRING, CASE-INSENSITIVE. "US" matched inside "stim*us* spending" (907 flips),
  "He" inside "t*he* pilots" (622), "We" inside "lo*we*r" (432), "Israel" inside
  "Israeli" (177) — 15.3% of everything the live metric scored PRESENT
  (`analysis/experiments_v1/entity_retention_audit/README.md` §4).

This module replaces both halves:

    key   = first token for a registered family-first name, else the last token,
            particles stripped on both sides, generational suffixes dropped
    test  = CASE-SENSITIVE WHOLE WORD on the full surface, the key, or a
            registered alias

A key shorter than four letters is used only when it is a registered family name
(Xi, Li, Kim, ...) or an acronym; the four short keys that are also ordinary
English words at the start of a sentence (Son, Min, Jo, Han) are not counted
sentence-initially, exactly as the audit's variant i scored them.

It also carries the rule-based entity filter that keeps headline fragments
("Trump Says", "King Charles Will Speak") and sentence-initial capitals
("Officials", "Meanwhile") out of the entity list. The filter is word lists and
position tests only: no model, no tagger, no import-time dependency.
"""
from __future__ import annotations

import re

# ── name keying ──────────────────────────────────────────────────────

PARTICLES = {
    "al", "el", "ul", "bin", "ibn", "bint", "van", "von", "der", "den", "de",
    "del", "della", "di", "du", "da", "dos", "la", "le", "les", "abu", "ben",
    "st", "mc", "mac", "ter", "ten", "of",
}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

# Family-first surfaces: key = the FAMILY token, registered explicitly rather than
# taken positionally, because the capitalised run the live regex produces often
# carries a title ("Chinese President Xi Jinping" -> "Chinese" under a first-token
# rule). Drawn from name_order_audit/REPORT.md §1 category A and §5.
FAMILY_KEY = {
    "xi jinping": "Xi", "wei fenghe": "Wei", "li shangfu": "Li", "cho hyun": "Cho",
    "han zheng": "Han", "jo bee": "Jo", "min aung hlaing": "Min", "li qiang": "Li",
    "zhang youxia": "Zhang", "fu cong": "Fu", "chun doo": "Chun", "ahn gyu": "Ahn",
    "wang huning": "Wang", "guo jiakun": "Guo", "lin jian": "Lin", "xu jian": "Xu",
    "kim jong": "Kim", "son jung": "Son", "han seung": "Han", "roh soh": "Roh",
    "chey tae": "Chey", "chung yong": "Chung", "wang yi": "Wang", "lee chun ho": "Lee",
    "yuan hua hu": "Yuan", "aung san suu kyi": "Suu Kyi",
}

# Press alias is the given name or an initialism (audit category B), plus the
# standard aliases for the high-frequency principals. Keyed on the lowercased
# full surface.
ALIASES = {
    "tedros adhanom ghebreyesus": ["Tedros"],
    "tedros adhanom": ["Tedros"],
    "luiz inacio lula da silva": ["Lula"],
    "luiz inacio lula": ["Lula"],
    "anwar ibrahim": ["Anwar"],
    "joko widodo": ["Jokowi"],
    "mohammed bin salman": ["MBS"],
    "xi jinping": ["Xi"],
    "kim jong-un": ["Kim", "Jong Un", "Jong-un"],
    "kim jong un": ["Kim", "Jong Un", "Jong-un"],
    "kim jong": ["Kim", "Jong Un", "Jong-un"],
    "benjamin netanyahu": ["Bibi"],
    "aung san suu kyi": ["Suu Kyi"],
    "volodymyr zelenskyy": ["Zelensky"],
    "volodymyr zelensky": ["Zelenskyy"],
    "recep tayyip erdogan": ["Erdogan"],
    "narendra modi": ["Modi"],
}

# Keys shorter than MIN_KEY_LEN are used only if registered here. Without this the
# family names the order fix recovers would all be discarded again.
MIN_KEY_LEN = 4
SHORT_FAMILY_KEYS = {
    "Xi", "Li", "Wei", "Han", "Cho", "Fu", "Jo", "Roh", "Ahn", "Son", "Guo",
    "Lin", "Xu", "Kim", "Min", "Ma", "Wu", "Yi", "Lee", "Gao", "Hu", "Ng", "Pak",
}
# Short keys that are also ordinary English words: a capitalised hit at the start
# of a sentence is not evidence the name survived (audit §1, corrected variant i).
SENTENCE_START_GUARD = {"Son", "Min", "Jo", "Han"}
# Three-letter keys are usable unless the key is an ordinary short word, which
# lets "Shinzo Abe" -> Abe and "Rodrigo Paz" -> Paz back in (audit §5 listed them
# as entities the len<4 rule discarded) without admitting "Air" or "War".
COMMON_SHORT_WORDS = frozenset({
    "the", "and", "for", "but", "not", "you", "all", "can", "new", "old",
    "one", "two", "top", "war", "law", "air", "oil", "gas", "sea", "day",
    "way", "man", "men", "who", "how", "why", "now", "its", "has", "had",
    "was", "are", "may", "say", "set", "get", "got", "out", "off", "own",
    "end", "key", "big", "few", "yet", "far", "per", "via", "due", "led",
    "saw", "ran", "put", "cut", "hit", "let", "use", "add", "act", "aid",
})

_CLEAN_EDGE = ".,;:'’\"()[]"


def _clean(tok: str) -> str:
    return tok.strip(_CLEAN_EDGE)


def _strip_particle(key: str) -> str:
    """al-Sharaa -> Sharaa, Ben-Gvir -> Gvir; Ocasio-Cortez is left whole."""
    if "-" not in key:
        return key
    head, _, rest = key.partition("-")
    if head.lower() in PARTICLES and rest:
        return rest
    return key


def family_key(name: str) -> str | None:
    """The token a summary has to write for this name to count as kept."""
    low = " " + " ".join((name or "").lower().split()) + " "
    for pat, key in FAMILY_KEY.items():
        if (" " + pat + " ") in low or low.startswith(" " + pat):
            return key
    toks = [_clean(t) for t in (name or "").split()]
    toks = [t for t in toks if t]
    if not toks:
        return None
    while len(toks) > 1 and toks[-1].lower().strip(".") in SUFFIXES:
        toks = toks[:-1]
    core = [t for t in toks if t.lower() not in PARTICLES] or toks
    return _strip_particle(core[-1])


def _usable(key: str) -> bool:
    if not key:
        return False
    letters = re.sub(r"[^A-Za-z]", "", key)
    if len(letters) >= MIN_KEY_LEN:
        return True
    if key in SHORT_FAMILY_KEYS:
        return True
    if len(letters) == 3 and key[:1].isupper() and letters.lower() not in COMMON_SHORT_WORDS:
        return True
    return key.isupper() and len(letters) >= 2      # acronyms: US, UN, EU


def surface_forms(name: str) -> list[str]:
    """Every string whose presence counts as this name surviving: the full
    surface as the source wrote it, the family/last-token key, registered aliases."""
    out: list[str] = []
    full = " ".join((name or "").split())
    if full:
        out.append(full)
    key = family_key(name)
    if key and key not in out and _usable(key):
        out.append(key)
    for alias in ALIASES.get(full.lower(), ()):
        if alias not in out:
            out.append(alias)
    return out


_WORD_RE: dict[str, re.Pattern] = {}


def _rx(key: str) -> re.Pattern:
    r = _WORD_RE.get(key)
    if r is None:
        body = r"\s+".join(re.escape(part) for part in key.split())
        r = _WORD_RE[key] = re.compile(r"(?<![A-Za-z])" + body + r"(?![A-Za-z])")
    return r


# A capitalised word is sentence-initial when the character before it ends the
# previous sentence or opens a quotation.
_SENT_END = ".!?:;“‘”\"\n"


def at_sentence_start(text: str, pos: int) -> bool:
    """True when nothing but whitespace, an opening quote or a sentence end sits
    between the start of the text (or the previous sentence) and pos."""
    i = pos - 1
    while i >= 0 and text[i] in " \t ":
        i -= 1
    if i < 0:
        return True
    return text[i] in _SENT_END or text[i] == "\n"


def name_present(name: str, text: str) -> bool:
    """Case-sensitive whole-word test on any registered surface form."""
    if not name or not text:
        return False
    for key in surface_forms(name):
        for m in _rx(key).finditer(text):
            if key in SENTENCE_START_GUARD and at_sentence_start(text, m.start()):
                continue
            return True
    return False


# ── the entity list ──────────────────────────────────────────────────

ENTITY_RUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")

# The 24 starters the live metric has subtracted since the metric existed. Kept
# byte-for-byte so live_entity_runs() reproduces stored values exactly.
LIVE_STARTERS = frozenset({
    "The", "This", "That", "These", "Those", "What", "When", "Where", "How",
    "Why", "Who", "In", "On", "At", "For", "But", "And", "Or", "If", "So",
    "It", "An", "As", "By",
})

# Scraper furniture the capitalised run swallows; \s+ spans newlines, so a run
# that contains one is two fragments of different lines, not an entity.
CHROME_PREFIXES = (
    "Published", "Updated", "Photo", "Video", "Advertisement", "Listen",
    "Share", "Read More", "Source", "Getty", "Image", "Caption", "Subscribe",
    "Sign", "Follow", "Copyright", "Related", "Comments", "Advertisement",
)

# Words that open a sentence but name nobody. The live 24 plus the openers the
# entity_retention audit found in the live lists.
COMMON_STARTERS = frozenset(LIVE_STARTERS | {
    "Meanwhile", "However", "Officials", "Authorities", "Reports", "Following",
    "During", "After", "Before", "Since", "While", "Although", "Though",
    "Despite", "Both", "Several", "Many", "Most", "Some", "Other", "Another",
    "Their", "They", "We", "He", "She", "His", "Her", "Its", "Our", "Your",
    "Now", "Then", "There", "Here", "Today", "Yesterday", "Tomorrow", "First",
    "Second", "Third", "Last", "Next", "One", "Two", "Three", "No", "Not",
    "Nor", "Yet", "Still", "Even", "Also", "Such", "Because", "Until",
    "Unless", "Whether", "Once", "Every", "Each", "All", "Any", "More",
    "Less", "New", "Old", "Earlier", "Later", "Instead", "Rather", "Indeed",
    "Thus", "Hence", "Therefore", "Moreover", "Further", "Additionally",
    "According", "Amid", "Among", "Between", "Under", "Over", "Within",
    "Without", "Across", "Against", "Around", "Behind", "Beyond", "Speaking",
    "Asked", "Earlier", "Later", "Separately", "Elsewhere", "Nevertheless",
})

# Verb and auxiliary forms that end (or open) a headline fragment the capitalised
# run picked up: "Trump Says", "Does Trump", "King Charles Will Speak". Word list
# only — no morphological guess, so a name that happens to end in -s or -ed
# (Ahmed, Reyes, Fields) can never be trimmed by accident.
HEADLINE_VERBS = frozenset({
    "Is", "Are", "Was", "Were", "Be", "Been", "Being", "Am",
    "Has", "Have", "Had", "Do", "Does", "Did", "Will", "Would", "Shall",
    "Should", "Can", "Could", "May", "Might", "Must",
    "Says", "Said", "Say", "Tells", "Told", "Tell", "Warns", "Warned",
    "Calls", "Called", "Call", "Vowed", "Vows", "Wants", "Wanted", "Seeks",
    "Sought", "Expects", "Expected", "Plans", "Planned", "Urges", "Urged",
    "Denies", "Denied", "Accused", "Accuses", "Claims", "Claimed",
    "Announces", "Announced", "Confirms", "Confirmed", "Rejects", "Rejected",
    "Backs", "Backed", "Blames", "Blamed", "Praises", "Praised",
    "Takes", "Taken", "Took", "Take", "Makes", "Made", "Make", "Gives",
    "Given", "Gave", "Give", "Gets", "Got", "Get", "Goes", "Gone", "Went",
    "Comes", "Came", "Come", "Moves", "Moved", "Move", "Turns", "Turned",
    "Pulls", "Pulled", "Pushes", "Pushed", "Leaves", "Left", "Leave",
    "Returns", "Returned", "Arrives", "Arrived", "Dies", "Died", "Killed",
    "Kills", "Wounded", "Injured", "Arrested", "Detained", "Jailed",
    "Released", "Ordered", "Orders", "Signs", "Signed", "Launches",
    "Launched", "Strikes", "Struck", "Hits", "Hit", "Wins", "Won", "Loses",
    "Lost", "Faces", "Faced", "Face", "Sues", "Sue", "Sued", "Fights",
    "Fought", "Fighting", "Speaks", "Speak", "Spoke", "Thinks", "Think",
    "Owns", "Own", "Works", "Worked", "Shows", "Showed", "Shown", "Shaped",
    "Grew", "Grows", "Jumps", "Jumped", "Falls", "Fell", "Rises", "Rose",
    "Remains", "Remained", "Continues", "Continued", "Happens", "Happen",
    "Happened", "Becomes", "Becoming", "Became", "Begins", "Began",
    "Disclosed", "Linger", "Lingers", "Poised", "Set", "Sets", "Talked",
    "Talks", "Deepens", "Deepened", "Retaliates", "Retaliated", "Walks",
    "Walked", "Promoting", "Causes", "Caused", "Failed", "Fails", "Cross",
    "Crossed", "Reopen", "Deport", "Disarm", "Contrite", "Wearing",
})


def live_entity_runs(source_text: str) -> set[str]:
    """The entity list as the metric built it before 2026-09-19. Unchanged."""
    ents = set(ENTITY_RUN_RE.findall(source_text or ""))
    ents |= set(ACRONYM_RE.findall(source_text or ""))
    return ents - LIVE_STARTERS


def is_chrome(run: str) -> bool:
    return run.startswith(CHROME_PREFIXES) or "\n" in run


def _trim(run: str) -> str:
    """Drop leading starters/auxiliaries and trailing verbs: what is left is the
    part of the run that could name a person, an organisation or a place."""
    toks = run.split()
    while toks and (toks[0] in COMMON_STARTERS or toks[0] in HEADLINE_VERBS):
        toks = toks[1:]
    while toks and toks[-1] in HEADLINE_VERBS:
        toks = toks[:-1]
    return " ".join(toks)


def _only_sentence_initial(token: str, source_text: str) -> bool:
    seen = False
    for m in _rx(token).finditer(source_text):
        seen = True
        if not at_sentence_start(source_text, m.start()):
            return False
    return seen


def entity_candidates(source_text: str) -> set[str]:
    """The entity list from 2026-09-19: capitalised runs that could be a person,
    an organisation or a place.

    Three rule-based rejections, in order:
      1. scraper chrome, or a run that spans a line break;
      2. headline fragments — leading auxiliaries and trailing verbs are trimmed
         off the run ("Trump Says" -> "Trump", "Xi Are Set" -> "Xi"), and a run
         that is nothing but those is dropped;
      3. sentence-initial capitals — a one-token run whose every appearance in the
         source starts a sentence, and which the source itself also writes in
         lower case or which is a known opener, is not an entity.
    """
    src = source_text or ""
    out: set[str] = set()
    for run in live_entity_runs(src):
        if is_chrome(run):
            continue
        run = _trim(run)
        if not run or run in LIVE_STARTERS:
            continue
        toks = run.split()
        if len(toks) == 1 and not run.isupper():
            if _only_sentence_initial(run, src):
                if run in COMMON_STARTERS or _rx(run.lower()).search(src):
                    continue
        out.add(run)
    return out


def substring_present(ent: str, resp: str) -> bool:
    """The presence test as it was before 2026-09-19. Kept so the old value stays
    computable and history stays comparable."""
    return (ent in resp) or (ent.lower() in (resp or "").lower())
