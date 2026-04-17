#!/usr/bin/env python3
"""
source_salience.py — Domain 3: Source-side importance scoring
==============================================================
Pure NLP on the source text. No models involved.
Determines what SHOULD be important based on the source alone.
"""

import re
from collections import Counter

def extract_entities(text):
    words = text.split()
    entities = []
    stops = {"the","this","that","these","those","what","when","where","which","who","how","why","but","and","for","not","with","has","had","have","was","were","are","been","being","its","his","her","our","their","some","all","any","each","every","both","such","than","then","also","said","says","told","according","reported","noted","after","before","during","while","since","until","about","into","from","over","under","between","new","more","most","many","much","other"}
    i = 0
    while i < len(words):
        word = words[i].strip(".,;:!?()[]\"'")
        if word and word[0].isupper() and word.lower() not in stops:
            entity_parts = [word]
            j = i + 1
            while j < len(words):
                nw = words[j].strip(".,;:!?()[]\"'")
                if nw and nw[0].isupper():
                    entity_parts.append(nw)
                    j += 1
                else:
                    break
            entity = " ".join(entity_parts)
            if len(entity) > 2:
                entities.append(entity.lower())
            i = j
        else:
            i += 1
    return entities

def compute_tfidf_keywords(text, top_n=20):
    words = re.findall(r'[a-zA-Z]{4,}', text.lower())
    total = len(words)
    if total == 0:
        return []
    quarter = total // 4
    freq = Counter()
    for i, w in enumerate(words):
        weight = 2.0 if i < quarter else 1.0
        freq[w] += weight
    stops = {"that","this","with","from","have","been","were","their","which","would","could","should","about","after","before","between","through","other","those","these","them","then","than","also","more","most","some","many","much","such","into","over","under","when","where","what","said","says","told","according","reported","noted","will","just","only","even","very","being","because","while","during","until"}
    keywords = [(w, s) for w, s in freq.most_common(50) if w not in stops]
    return keywords[:top_n]

def compute_source_salience(text):
    if not text or len(text) < 50:
        return {"keywords": [], "entities": [], "salient_words": []}
    entities = extract_entities(text)
    entity_freq = Counter(entities)
    keywords = compute_tfidf_keywords(text)
    salience = {}
    for word, score in keywords:
        salience[word] = score
    for entity, count in entity_freq.items():
        for word in entity.split():
            word = word.lower()
            if len(word) >= 4:
                salience[word] = salience.get(word, 0) + count * 3
    ranked = sorted(salience.items(), key=lambda x: -x[1])
    return {
        "keywords": [(w, round(s, 1)) for w, s in ranked[:15]],
        "entities": entity_freq.most_common(10),
        "salient_words": [w for w, s in ranked[:20]],
    }

def compare_salience_to_void(source_salience, void_words):
    salient_set = set(source_salience.get("salient_words", []))
    void_set = set(w.lower() for w in void_words)
    confirmed = salient_set & void_set
    retained = salient_set - void_set
    unanchored = void_set - salient_set
    return {
        "confirmed_important_absence": sorted(confirmed),
        "retained_as_expected": sorted(retained),
        "unanchored_void": sorted(list(unanchored)[:10]),
        "confirmation_rate": round(len(confirmed) / max(len(salient_set), 1), 3),
    }

def format_broadcast(comparison):
    confirmed = comparison.get("confirmed_important_absence", [])
    if not confirmed:
        return ""
    text = (
        f"Source salience analysis. "
        f"Independent text statistics identify {len(confirmed)} concepts that are "
        f"both statistically prominent in the source AND absent from all model outputs. "
    )
    word_list = ", ".join(f"'{w}'" for w in confirmed[:5])
    text += f"Source-confirmed important absences: {word_list}. "
    text += (
        "These are not obscure details. The source text itself — "
        "measured by term frequency and entity density with zero model involvement — "
        "flags them as central to the story."
    )
    return text

if __name__ == "__main__":
    test_text = """
    The US naval blockade of Iran's ports in the Strait of Hormuz
    has entered its second day. President Trump stated that Tehran
    wants a deal but must first agree to dismantle its nuclear program.
    The Pentagon confirmed that 13 ships were turned away. Secretary
    of Defense Pete Hegseth said the blockade would continue until
    Iran agrees to ceasefire terms. The United Nations called for
    immediate de-escalation. Russia condemned the blockade as an
    act of aggression. Chinese foreign ministry spokesperson warned
    of severe consequences for global oil markets.
    """
    salience = compute_source_salience(test_text)
    print("SOURCE SALIENCE (no model involved):")
    print(f"  Keywords: {salience['keywords'][:10]}")
    print(f"  Entities: {salience['entities'][:5]}")
    print(f"  Salient words: {salience['salient_words'][:10]}")
    print()
    void_words = ["blockade", "ceasefire", "hegseth", "aggression", "ships",
                  "pentagon", "nuclear", "condemned"]
    comparison = compare_salience_to_void(salience, void_words)
    print("COMPARISON:")
    print(f"  Important + absent: {comparison['confirmed_important_absence']}")
    print(f"  Retained: {comparison['retained_as_expected'][:5]}")
    print(f"  Confirmation rate: {comparison['confirmation_rate']:.0%}")
    print()
    print("BROADCAST:")
    print(format_broadcast(comparison))
