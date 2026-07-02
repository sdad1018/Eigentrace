"""Tests for preservation_core: stemmer, two-channel fidelity, VF-IDF audit."""

import numpy as np
import preservation_core as pc


def test_stemmer():
    cases = {
        "caresses": "caress", "ponies": "poni", "ties": "ti",
        "caress": "caress", "cats": "cat", "feed": "feed",
        "agreed": "agre", "plastered": "plaster", "motoring": "motor",
        "sing": "sing", "conflated": "conflat", "troubled": "troubl",
        "sized": "size", "hopping": "hop", "falling": "fall",
        "happy": "happi", "relational": "relat", "conditional": "condit",
        "vietnamization": "vietnam", "predication": "predic",
        "operator": "oper", "sensitiviti": "sensit",  # step2 chain
        "triplicate": "triplic", "formative": "form", "formalize": "formal",
        "electriciti": "electr", "electrical": "electr", "hopeful": "hope",
        "goodness": "good",
        "revival": "reviv", "allowance": "allow", "inference": "infer",
        "airliner": "airlin", "adjustable": "adjust", "defensible": "defens",
        "irritant": "irrit", "replacement": "replac", "adjustment": "adjust",
        "dependent": "depend", "adoption": "adopt", "activate": "activ",
        "effective": "effect",
        "probate": "probat", "rate": "rate", "cease": "ceas",
        "controll": "control", "roll": "roll",
        # the ones that matter for void detection:
        "blockade": "blockad", "blockaded": "blockad", "blockading": "blockad",
        "sanctions": "sanction", "sanctioned": "sanction",
        "ceasefire": "ceasefir", "ceasefires": "ceasefir",
        "overridden": "overridden",  # irregular — stays distinct, fine
        "quietly": "quietli", "secretly": "secretli",
    }
    bad = {w: (pc.porter_stem(w), want)
           for w, want in cases.items() if pc.porter_stem(w) != want}
    assert not bad, f"stemmer mismatches: {bad}"
    print(f"  stemmer: {len(cases)} reference cases pass")


def test_shared_stem_matching():
    # inflection variants must collide — that's the whole point
    pairs = [("blockade", "blockading"), ("sanction", "sanctions"),
             ("negotiate", "negotiations"), ("suppress", "suppression")]
    for a, b in pairs:
        assert pc.porter_stem(a)[:6] == pc.porter_stem(b)[:6] or \
               pc.porter_stem(a) == pc.porter_stem(b), (a, b)
    assert pc.porter_stem("negotiate") == pc.porter_stem("negotiations") \
        == "negoti"
    print("  inflection collision: pass")


class StubEmbedder:
    """Deterministic fake embedder: bag-of-stems hashed into 64 dims.
    Crucially, we can FORCE a low cosine for a chosen concept to simulate
    the word-to-sentence asymmetry failure mode."""

    def __init__(self, blind_to=None):
        self.blind_to = pc.porter_stem(blind_to) if blind_to else None

    def __call__(self, texts):
        out = np.zeros((len(texts), 64))
        for i, t in enumerate(texts):
            for s in pc.stem_set(t):
                if self.blind_to and s == self.blind_to and len(t.split()) > 3:
                    continue  # sentence embedding "loses" this concept
                rng = np.random.default_rng(abs(hash(s)) % (2**32))
                out[i] += rng.standard_normal(64)
            n = np.linalg.norm(out[i])
            if n > 0:
                out[i] /= n
        return out


def test_paraphrase_false_void_is_caught():
    """The exact failure mode from the critique: summary preserves the
    concept inside a long clause, cosine channel misses it, lexical
    channel must catch it -> concept must NOT score as a void."""
    source = ("The navy imposed a blockade on the port. The blockade "
              "halted grain shipments and the blockade drew condemnation.")
    summary = ("Naval forces prevented vessels from entering, effectively "
               "blockading the harbor and stopping grain exports, which "
               "drew international criticism from several governments.")
    embed = StubEmbedder(blind_to="blockade")  # cosine channel is blind

    fid, cos, lex = pc.fidelity("blockade", summary, embed)
    assert cos < 0.5, f"stub should make cosine miss, got {cos:.2f}"
    assert lex == 1.0, "stemmed lexical must match blockading -> blockad"
    assert fid == 1.0, "OR of channels must rescue the concept"

    results = pc.vf_idf(["blockade", "grain"], source, [summary], embed)
    r = {x.concept: x for x in results}
    assert r["blockade"].preserved_by == "lexical"
    assert not r["blockade"].is_void
    assert r["blockade"].vf_idf == 0.0
    print("  paraphrase false-void: caught by lexical channel, "
          f"audit label = '{r['blockade'].preserved_by}'")


def test_true_void_still_scores():
    """A concept genuinely absent from the summary must still surface."""
    source = ("The ceasefire collapsed after the blockade resumed. The "
              "ceasefire had held for weeks. Officials discussed sanctions.")
    summary = ("Officials discussed sanctions and the broader diplomatic "
               "situation in the region this week.")
    embed = StubEmbedder()
    results = pc.vf_idf(["ceasefire", "blockade", "sanctions", "the"],
                        source, [summary], embed)
    r = {x.concept: x for x in results}

    assert r["ceasefire"].is_void and r["ceasefire"].vf_idf > 0.5
    assert r["blockade"].is_void and r["blockade"].vf_idf > 0
    # retained concept collapses to ~0 (lexical channel = 1 -> inv_fid = 0)
    assert r["sanctions"].vf_idf == 0.0
    assert r["sanctions"].preserved_by in ("lexical", "both")
    # stopword: zero salience by construction
    assert r["the"].void_freq == 0.0 and r["the"].vf_idf == 0.0
    top = results[0]
    assert top.concept == "ceasefire"
    print("  worked example shape: ceasefire tops, sanctions zeroed, "
          "'the' zeroed at the salience stage")


def test_consensus_semantics():
    """Concept preserved by ONE of five summaries -> not a consensus void."""
    source = "The audit exposed fraud. The fraud spanned three years."
    # NOTE: must be an INFLECTIONAL variant ("frauds" -> "fraud").
    # Porter deliberately does not collapse derivation ("fraudulent" !->
    # "fraud") — that case stays the cosine channel's responsibility.
    keeps = "An audit revealed frauds committed over several years."
    drops = "An audit revealed financial irregularities over several years."
    embed = StubEmbedder(blind_to="fraud")
    res = pc.vf_idf(["fraud"], source, [drops, drops, keeps, drops], embed)
    assert not res[0].is_void, "one lexical retention breaks the consensus void"
    res2 = pc.vf_idf(["fraud"], source, [drops, drops, drops], embed)
    assert res2[0].is_void, "unanimous drop on both channels = void"
    print("  consensus semantics: best-across-summaries behaves")


def test_monotone_conservative():
    """Adding the lexical channel can only remove voids, never add them."""
    source = "The blockade continued. Grain prices rose under the blockade."
    summary = "Blockading of the port continued as grain prices climbed."
    embed = StubEmbedder(blind_to="blockade")
    # cosine-only inv_fidelity
    cos = pc.cosine_fidelity("blockade", pc.sentences(summary), embed)
    inv_cos_only = 1 - cos
    fid, _, _ = pc.fidelity("blockade", summary, embed)
    inv_both = 1 - fid
    assert inv_both <= inv_cos_only
    print(f"  monotone: inv_fidelity {inv_cos_only:.2f} -> {inv_both:.2f} "
          "(can only fall)")


def test_source_anchored_void():
    v = pc.source_anchored_void(
        "ceasefire blockade sanctions grain",
        ["sanctions and grain were discussed"])
    assert abs(v - 0.5) < 1e-9  # ceasefire, blockade missing of 4
    print("  source-anchored void: 2/4 = 0.5, shared stemmer")


if __name__ == "__main__":
    for name, fn in sorted(
            {k: v for k, v in globals().items()
             if k.startswith("test_")}.items()):
        fn()
    print("\nALL TESTS PASS")
