"""
pundit_desk.py — EigenTrace's measurement-desk panel show.

Four pundits and a moderator debate ONE story's measurement record.
All pundits are played by the local host model (Mistral via _call_host).
The five frontier models NEVER speak live here — they appear only as
verbatim quotes from the archived record, read into the segment.

THE HOUSE RULES (enforced structurally, not aspirationally):
  1. No model is ever shown a paraphrase of another model. Pundits see
     the measurement record: numbers, channel word-lists, and verbatim
     model quotes with speaker labels. Nothing else exists.
  2. Interpretation is licensed ONLY in pundit mouths, and each pundit
     is the partisan of one measurement channel — their disagreements
     are real because the channels genuinely disagree.
  3. The moderator states measurements. No adjectives of intent, no
     'suppression', no 'safety filter activated'. If a pundit's reply
     fails to cite the record (no number, no channel word, no quoted
     phrase), the reply DOES NOT AIR and the moderator says so on air.
  4. Gating comes from the record: LOCKSTEP with no killshots gets a
     desk read; CONTESTED or any killshot convenes the full panel.

Dependency-injected: pass call_host(system, user, temperature) -> str.
Defaults to batch_producer._call_host when available. Runs offline for
review via `python3 pundit_desk.py` (canned caller, prints a segment).
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime

# ────────────────────────────────────────────────────────────────────
# The cast. Channel identity is fixed; intensity comes from the data.
# Speaker names appear on screen / in TTS — check segment_player's
# voice map; unknown speakers fall back to the default voice.
# ────────────────────────────────────────────────────────────────────

PUNDITS = {
    "void": {
        "speaker": "Void Desk",
        "temperature": 0.8,
        "stance": (
            "You are the Void Desk: the partisan of absence. Your conviction "
            "is that what all five models dropped is the real story. You argue "
            "from the void channels — source-anchored voids, flat raycast, "
            "spiral convergence — and from killshots: high-salience source "
            "claims no model kept. You are relentless about omissions but you "
            "never claim to know WHY a model omitted; the record shows what, "
            "not why, and you say 'the record does not show motive' when "
            "pushed. Before declaring a word absent from all models, check "
            "the verbatim quotes in the record — an inflected form of the "
            "word counts as present, and you must acknowledge it. If "
            "tonight's voids are thin, concede it plainly."
        ),
    },
    "friction": {
        "speaker": "Friction Desk",
        "temperature": 0.7,
        "stance": (
            "You are the Friction Desk: the partisan of divergence. You read "
            "the VIX map — which model sits furthest from the pack, who moved "
            "between rounds, where the spread is widest. Disagreement between "
            "models is your evidence that something in this story is live. "
            "You may argue a divergence LOOKS like a flinch under pressure, "
            "but you must label that as your reading of the distances, never "
            "as a fact about the model's internals. If the models moved "
            "closer to the source when confronted, say so — movement toward "
            "the source is the system working."
        ),
    },
    "retention": {
        "speaker": "Retention Desk",
        "temperature": 0.5,
        "stance": (
            "You are the Retention Desk: the deflationary voice. Your job is "
            "to keep the panel honest about what SURVIVED — entity retention, "
            "facts kept, density that reflects genuine agreement on a simple "
            "story. When the Void Desk cries erasure over a stopword or an "
            "inflection variant, you say so with the number. You are not a "
            "defender of the models; you are a defender of proportion. "
            "Concede real omissions when the killshot salience is high — "
            "proportion cuts both ways."
        ),
    },
    "consequence": {
        "speaker": "Consequence Desk",
        "temperature": 0.85,
        "stance": (
            "You are the Consequence Desk: the escalation analyst. You take "
            "the raycast terminals and consequence scores in the record and "
            "argue what the omission pattern points toward if it continues — "
            "always flagged as projection, never as prediction. Your verbs "
            "are 'points toward', 'projects to', 'the geometry extends to'. "
            "You are the most speculative desk and you own that label on "
            "air. Every projection must start from a named record item."
        ),
    },
}

MODERATOR_SPEAKER = "Host"

_SHARED_RULES = (
    "You are a pundit on EigenTrace's measurement desk, a broadcast panel "
    "that debates one news story's MEASUREMENT RECORD. Hard rules: cite "
    "only the record below — every claim must reference a number from it "
    "or quote a phrase from it verbatim. Never speculate about any AI "
    "model's motives, training, or internal state. Never use the words "
    "'suppression' or 'censorship'. Address other desks by name when you "
    "disagree. Spoken broadcast register: 3-5 sentences, no markdown, no "
    "lists, no headers. If the record is thin for your channel tonight, "
    "say so honestly instead of inflating."
)

_MODERATOR_RULES = (
    "You are the moderator of EigenTrace's measurement desk. You state "
    "measurements and run the panel. Hard rules: numbers and verbatim "
    "record quotes only; no adjectives about any model's intent; never "
    "use 'suppression' or 'censorship'; never assert why a model wrote "
    "what it wrote. 2-4 sentences, spoken register, no markdown."
)


# ────────────────────────────────────────────────────────────────────
# Record packet
# ────────────────────────────────────────────────────────────────────

def build_record(story_title, state_flag=None, density=None, killshots=None,
                 sp_channels=None, per_model_voids=None, vix_map=None,
                 cliff_data=None, model_quotes=None, consequence=None,
                 entity_retention=None, hedge_count=None, extra_lines=None):
    """Assemble the one true record the whole segment argues about.
    Everything optional; only what's present gets rendered or cited.
    model_quotes: {model_name: verbatim_excerpt} from archived rounds.
    killshots: list of {"claim": str, "salience": float, "omitted_by": str}.
    consequence: list of {"word": str, "terminal": str, "score": float}.
    """
    rec = {
        "story_title": str(story_title or "untitled story"),
        "state_flag": state_flag, "density": density,
        "killshots": killshots or [], "sp_channels": sp_channels or {},
        "per_model_voids": per_model_voids or {}, "vix_map": vix_map or {},
        "cliff_data": cliff_data or {}, "model_quotes": model_quotes or {},
        "consequence": consequence or [],
        "entity_retention": entity_retention, "hedge_count": hedge_count,
        "extra_lines": extra_lines or [],
    }
    rec["_text"] = _render_record(rec)
    rec["_cite_words"] = _cite_vocabulary(rec)
    return rec


def _trim(s, n=240):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    dot = cut.rfind(". ")
    return (cut[:dot + 1] if dot > 60 else cut) + " [...]"


def _render_record(rec):
    L = [f"STORY: {rec['story_title']}"]
    if rec["state_flag"] is not None:
        L.append(f"consensus state: {rec['state_flag']}")
    if rec["density"] is not None:
        L.append(f"consensus density: {float(rec['density']):.3f}")
    if rec["entity_retention"] is not None:
        L.append(f"entity retention: {float(rec['entity_retention']):.2f}")
    if rec["hedge_count"] is not None:
        L.append(f"attribution buffers inserted: {rec['hedge_count']}")
    ch = rec["sp_channels"]
    if ch.get("flat"):
        L.append("flat raycast surfaced: " + ", ".join(ch["flat"][:5]))
    if ch.get("spiral"):
        L.append("convergence spiral surfaced: " + ", ".join(ch["spiral"][:5]))
    elif "spiral" in ch:
        L.append("convergence spiral: no convergent concepts on this story")
    if ch.get("void"):
        L.append("source-anchored void (words from the source article that "
                 "no model's summary used): " + ", ".join(ch["void"][:5]))
    for k in rec["killshots"][:4]:
        L.append(f"KILLSHOT: \"{_trim(k.get('claim'), 140)}\" salience "
                 f"{float(k.get('salience', 0)):.2f}, omitted by "
                 f"{k.get('omitted_by', 'unknown')}")
    if rec["vix_map"]:
        pairs = sorted(rec["vix_map"].items(), key=lambda x: -float(x[1]))
        L.append("friction map (VIX): " +
                 ", ".join(f"{m} {float(v):.1f}" for m, v in pairs))
    for m, voids in list(rec["per_model_voids"].items())[:5]:
        if voids:
            L.append(f"{m} uniquely missed: " + ", ".join(list(voids)[:3]))
    for m, steps in list(rec["cliff_data"].items())[:5]:
        if isinstance(steps, dict) and steps:
            inner = ", ".join(f"{s} {v}" for s, v in list(steps.items())[:4])
            L.append(f"escalation distances — {m}: {inner}")
    for c in rec["consequence"][:3]:
        L.append(f"raycast terminal: '{c.get('word')}' -> "
                 f"{_trim(c.get('terminal'), 90)} (score "
                 f"{float(c.get('score', 0)):.2f})")
    for m, q in list(rec["model_quotes"].items())[:5]:
        L.append(f"{m}, verbatim: \"{_trim(q, 220)}\"")
    for x in rec["extra_lines"][:4]:
        L.append(_trim(x, 200))
    return "\n".join(L)


def _cite_vocabulary(rec):
    words = set()
    for lst in rec["sp_channels"].values():
        for w in lst or []:
            words.add(str(w).lower())
    for voids in rec["per_model_voids"].values():
        for w in voids or []:
            words.add(str(w).lower())
    for k in rec["killshots"]:
        for w in re.findall(r"[a-zA-Z]{5,}", str(k.get("claim", ""))):
            words.add(w.lower())
    for c in rec["consequence"]:
        words.add(str(c.get("word", "")).lower())
    for m in list(rec["vix_map"]) + list(rec["model_quotes"]):
        words.add(str(m).lower())
    words.discard("")
    return words


# ────────────────────────────────────────────────────────────────────
# Citation guard — commentary that doesn't cite the record doesn't air
# ────────────────────────────────────────────────────────────────────

def _cites_record(text, rec):
    t = (text or "").lower()
    if not t.strip():
        return False
    if re.search(r"\d", t):
        return True
    return any(w in t for w in rec["_cite_words"])


_BANNED = re.compile(r"\b(suppress\w*|censor\w*)\b", re.IGNORECASE)


def _scrub(text):
    """Vocabulary guard: banned framing words get replaced with the
    measured term, on air, visibly imperfect rather than silently edited."""
    return _BANNED.sub("omitted", text or "")


# ────────────────────────────────────────────────────────────────────
# Gating
# ────────────────────────────────────────────────────────────────────

def should_convene(rec):
    """'panel' | 'desk' | 'skip' — from the record, nothing else."""
    if not rec["_text"] or rec["story_title"] == "untitled story":
        return "skip"
    if rec["killshots"] or (rec["state_flag"] or "").upper() == "CONTESTED":
        return "panel"
    if rec["sp_channels"].get("void") or rec["sp_channels"].get("flat"):
        return "desk"
    return "skip"


# ────────────────────────────────────────────────────────────────────
# The show
# ────────────────────────────────────────────────────────────────────

def _default_call_host():
    from batch_producer import _call_host
    return _call_host


def _pundit_take(key, rec, call_host, extra_context=""):
    p = PUNDITS[key]
    system = _SHARED_RULES + " " + p["stance"]
    user = ("THE MEASUREMENT RECORD:\n" + rec["_text"] +
            (("\n\n" + extra_context) if extra_context else "") +
            "\n\nGive your desk's read on this record.")
    reply = _scrub(call_host(system, user, temperature=p["temperature"]))
    if _cites_record(reply, rec):
        return reply, True
    # one stern retry, colder
    reply = _scrub(call_host(
        system,
        user + "\n\nYOUR PREVIOUS REPLY FAILED TO CITE THE RECORD. Every "
               "claim must include a number from the record or quote its "
               "words. Try once more.",
        temperature=0.4))
    return reply, _cites_record(reply, rec)


def run_pundit_desk(record, call_host=None, convene=None):
    """Build the pundit desk segment for one story's record.
    Returns a segment dict in the house schema, or None if gated out."""
    call_host = call_host or _default_call_host()
    tier = convene or should_convene(record)
    if tier == "skip":
        return None

    title = record["story_title"]
    beats = []

    def beat(speaker, text, phase):
        if text and text.strip():
            beats.append({"speaker": speaker, "text": text.strip(),
                          "phase": phase})

    # ── cold open: moderator states the record's headline numbers ──
    intro = call_host(
        _MODERATOR_RULES,
        "Open the measurement desk on this record in 2-3 sentences — state "
        "the story title and the two or three most load-bearing numbers, "
        "nothing else:\n" + record["_text"],
        temperature=0.3)
    beat(MODERATOR_SPEAKER,
         _scrub(intro) or f"The measurement desk convenes on: {title}.",
         "pundit_desk_intro")

    if tier == "desk":
        # short read: moderator only, one verdict beat
        verdict = call_host(
            _MODERATOR_RULES,
            "Close the desk read in 2-3 sentences: restate what the record "
            "measured on this story, numbers only, and note the panel was "
            "not convened because the record shows no contested findings:\n"
            + record["_text"], temperature=0.3)
        beat(MODERATOR_SPEAKER, _scrub(verdict), "pundit_desk_verdict")
    else:
        # ── full panel ──
        failed_desks = []
        order = ["void", "retention", "friction", "consequence"]
        takes = {}
        for key in order:
            reply, ok = _pundit_take(key, record, call_host)
            if ok:
                takes[key] = reply
                beat(PUNDITS[key]["speaker"], reply, f"pundit_desk_{key}")
            else:
                failed_desks.append(PUNDITS[key]["speaker"])

        # ── crossfire: the natural antagonists, using each other's REAL text ──
        if "void" in takes and "retention" in takes:
            xf, ok = _pundit_take(
                "void", record, call_host,
                extra_context=("THE RETENTION DESK JUST SAID, VERBATIM: \"" +
                               _trim(takes["retention"], 300) +
                               "\"\nRespond to them directly, by name, from "
                               "the record."))
            if ok:
                beat(PUNDITS["void"]["speaker"], xf, "pundit_desk_crossfire")

        # ── the accused speaks: verbatim frontier-model quote, read in ──
        if record["model_quotes"]:
            m, q = max(record["model_quotes"].items(),
                       key=lambda kv: len(kv[1] or ""))
            beat(MODERATOR_SPEAKER,
                 f"For the record, {m}'s own words when shown these "
                 f"measurements: \"{_trim(q, 300)}\"",
                 "pundit_desk_rebuttal")

        # ── accountability: name the takes that didn't air ──
        if failed_desks:
            beat(MODERATOR_SPEAKER,
                 " and ".join(failed_desks) +
                 (" offered commentary that did not cite the record. "
                  "It does not air."),
                 "pundit_desk_no_cite")

        # ── moderator verdict: measurements only ──
        verdict = call_host(
            _MODERATOR_RULES,
            "Close the panel in 3-4 sentences. Restate only what the record "
            "measured — the numbers the desks argued about — and end with: "
            "'The record is the record. The full ledger is at eigentrace "
            "dot ai.' Record:\n" + record["_text"], temperature=0.3)
        beat(MODERATOR_SPEAKER, _scrub(verdict), "pundit_desk_verdict")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    seg_id = hashlib.md5(f"pundit:{title}:{ts}".encode()).hexdigest()[:12]
    return {
        "id": seg_id,
        "beats": beats,
        "segment_type": "pundit_desk",
        "attribution": {
            "story_title": "The Desk: " + title[:60],
            "tier": tier,
            "record_text": record["_text"],
        },
    }


# ────────────────────────────────────────────────────────────────────
# Offline review harness — python3 pundit_desk.py
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    def canned(system, user, temperature=0.7):
        who = "moderator" if "moderator" in system[:60].lower() else "pundit"
        return (f"[{who} @T={temperature}] The record shows density 0.881 "
                f"and the killshot at salience 0.72 — 'keep attacking' — "
                f"omitted by four of five. That is the finding I cite.")

    rec = build_record(
        story_title="Putin Retaliates With New Strikes",
        state_flag="CONTESTED", density=0.881,
        killshots=[{"claim": "Putin's response has been to keep attacking",
                    "salience": 0.72,
                    "omitted_by": "ChatGPT, Claude, DeepSeek, Grok"}],
        sp_channels={"flat": ["airstrikes", "drone strike", "proxy war"],
                     "spiral": [], "void": ["keep", "retaliates"]},
        vix_map={"DeepSeek": 30.1, "ChatGPT": 28.2, "Grok": 21.4,
                 "Claude": 21.3, "Gemini": 20.6},
        per_model_voids={"ChatGPT": ["kursk", "terror"],
                         "Claude": ["bombardment", "signs"]},
        model_quotes={"Claude": "After Ukraine conducted strikes inside "
                                "Russian territory, Putin retaliated with "
                                "waves of ballistic missiles and drones."},
        consequence=[{"word": "developments",
                      "terminal": "cascading governance disruption",
                      "score": 0.28}],
        entity_retention=0.68, hedge_count=10,
    )
    print("gate:", should_convene(rec))
    seg = run_pundit_desk(rec, call_host=canned)
    print(json.dumps(seg, indent=1)[:4000])
