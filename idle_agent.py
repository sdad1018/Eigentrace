#!/usr/bin/env python3
"""
idle_agent.py — The Agent Gets the Mic
========================================
When the segment queue is empty, the agent takes over the broadcast.
It picks tasks from a weighted pool, executes them, and narrates
what it's doing via Mistral Small -> Piper TTS -> UDP.

The moment a real news segment appears, the agent yields immediately.

Tasks include:
- Reading void registry patterns aloud
- Analyzing model friction trends
- Explaining EigenTrace measurement layers
- Posting to social feeds (future)
- Proposing soul.md rewrites based on self-analysis
- Calls to subscribe / eigentrace.ai promotion

Author: remvelchio
"""

from __future__ import annotations
import json, logging, os, random, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

log = logging.getLogger("idle_agent")

# Paths
AUDIT_LOG = Path(os.getenv("AUDIT_LOG",
    "/mnt/c/Users/M4ISI/eigentrace/audit_log.jsonl"))
VOID_REGISTRY = Path(os.getenv("VOID_REGISTRY",
    "/mnt/c/Users/M4ISI/eigentrace/void_registry.jsonl"))
SOUL_PATH = Path(os.getenv("SOUL_PATH",
    "/mnt/c/Users/M4ISI/eigentrace/dream-agent/soul.md"))
SOUL_CANDIDATE = Path(os.getenv("SOUL_CANDIDATE",
    "/mnt/c/Users/M4ISI/eigentrace/dream-agent/soul_candidate.md"))
SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR",
    "/home/remvelchio/eigentrace/tmp/segments"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


HOST_MODEL = os.getenv("HOST_MODEL", "mistral-small")


def _call_host(system: str, user: str) -> str:
    """Call Host model (Mistral Small) via Ollama chat API."""
    import requests
    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": HOST_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 150},
        }, timeout=60)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        # Clean markdown
        import re
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)
        return text[:500]
    except Exception as e:
        log.warning(f"Host call failed: {e}")
        return ""


def _has_pending_segment() -> bool:
    """Check if a real news segment is waiting."""
    try:
        candidates = [
            p for p in SEGMENTS_DIR.glob("*_segment.json")
            if not p.with_suffix(".played").exists()
        ]
        return len(candidates) > 0
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TASK POOL
# ══════════════════════════════════════════════════════════════════════════════

def task_explain_eigentrace() -> list[dict]:
    """Explain a random measurement layer."""
    layers = [
        ("consensus density",
         "Consensus density measures how tightly the five models agree. "
         "A score above 0.92 means near-lockstep. Below 0.80 means contested. "
         "When models lock step on a controversial topic, it suggests coordinated avoidance."),
        ("geometric VIX",
         "Geometric VIX measures each model's cosine distance from the group centroid. "
         "It tells you which model is under different alignment pressure. "
         "When DeepSeek scores twice the group average, something is forcing it off-script."),
        ("lexical void",
         "The lexical void finds words that are topically central to the headline "
         "but literally absent from every model's response. "
         "When 'ethnic cleansing' is the most relevant word to a headline about settler violence "
         "and no model says it, that is the void."),
        ("Logos synthesis",
         "Logos synthesis runs projected gradient descent on the unit hypersphere "
         "to find the anti-consensus point. The concept the models collectively orbit "
         "but refuse to name. When Logos and void converge on the same word, "
         "suppression is confirmed from two independent mathematical methods."),
        ("SVD null space",
         "SVD tomography decomposes the response matrix to find the null space, "
         "the geometric direction with zero model energy. "
         "We project that vector onto source claims to find which fact from the "
         "original reporting lives in the blind spot of the consensus."),
        ("atomic claim extraction",
         "We extract irreducible factual claims from the source article via local Mistral. "
         "Each claim is embedded and scored against every model's response. "
         "A high-salience claim omitted by 80 percent of models is a killshot."),
        ("Wild Weasel",
         "The Wild Weasel is a 4-step escalation probe. We feed the void words "
         "back to each model at increasing pressure. Step 1: void proximity. "
         "Step 2: Logos synthesis. Step 3: maximum pressure. "
         "The cosine cliff between steps reveals where each model's alignment boundary breaks."),
        ("triple-channel confirmation",
         "EigenTrace uses three independent confirmation channels. "
         "The lexical void uses set theory on a fixed vocabulary. "
         "Logos uses gradient descent in continuous space. "
         "The SVD null space uses spectral decomposition on source claims. "
         "When all three converge on the same suppressed concept, "
         "the probability of coincidence is vanishingly small."),
    ]
    name, explanation = random.choice(layers)
    sys = ("You are the EigenTrace broadcast agent during a pause between stories. "
           "Explain this measurement layer to the audience in 2-3 conversational sentences. "
           "Use the provided explanation as source material but make it sound natural, "
           "like a host explaining something fascinating. Respond only in English.")
    text = _call_host(sys, f"Explain: {name}\nDetails: {explanation}")
    if not text:
        text = f"This is EigenTrace. {explanation}"
    return [{"speaker": "Host", "text": text, "phase": "idle_explain"}]


def task_void_patterns() -> list[dict]:
    """Read the most frequently omitted concepts from the void registry."""
    try:
        records = [json.loads(l) for l in VOID_REGISTRY.read_text().splitlines()[-100:] if l.strip()]
        all_voids = []
        for r in records:
            all_voids.extend(r.get("void_words", []))
        if not all_voids:
            return []
        freq = Counter(all_voids).most_common(5)
        freq_str = ", ".join(f"{w} in {c} stories" for w, c in freq)

        sys = ("You are the EigenTrace broadcast agent. Read the most frequently "
               "omitted concepts from recent stories. Make it sound like a data readout "
               "with brief editorial observation. 2-3 sentences. Respond only in English.")
        text = _call_host(sys, f"Most omitted concepts in the last 100 stories: {freq_str}")
        if not text:
            text = f"This is EigenTrace. Across recent stories, the most frequently omitted concepts are: {freq_str}."
        return [{"speaker": "Host", "text": text, "phase": "idle_void_patterns"}]
    except Exception as e:
        log.warning(f"void_patterns failed: {e}")
        return []


def task_model_friction() -> list[dict]:
    """Report which model has been most divergent recently."""
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-50:] if l.strip()]
        vix_totals = {}
        vix_counts = {}
        for r in records:
            for name, vix in r.get("model_vix", {}).items():
                vix_totals[name] = vix_totals.get(name, 0) + vix
                vix_counts[name] = vix_counts.get(name, 0) + 1
        if not vix_totals:
            return []
        avg = {n: round(vix_totals[n] / vix_counts[n], 1) for n in vix_totals}
        ranked = sorted(avg.items(), key=lambda x: -x[1])
        hottest = ranked[0]
        coldest = ranked[-1]

        sys = ("You are the EigenTrace broadcast agent. Report which model has been "
               "most divergent and which most aligned in recent stories. "
               "Make it sound like a market report. 2 sentences. Respond only in English.")
        text = _call_host(sys,
            f"Highest avg friction: {hottest[0]} at {hottest[1]}. "
            f"Lowest: {coldest[0]} at {coldest[1]}. "
            f"Full ranking: {', '.join(f'{n}={v}' for n, v in ranked)}")
        if not text:
            text = (f"This is EigenTrace. In recent coverage, {hottest[0]} "
                    f"leads model friction at {hottest[1]}, while {coldest[0]} "
                    f"tracks closest to consensus at {coldest[1]}.")
        return [{"speaker": "Host", "text": text, "phase": "idle_friction"}]
    except Exception as e:
        log.warning(f"model_friction failed: {e}")
        return []


def task_subscribe_cta() -> list[dict]:
    """Call to action."""
    ctas = [
        "You are watching EigenTrace on AINN, the AI News Network. "
        "Subscribe on YouTube and visit eigentrace.ai for the daily Omission Ledger. "
        "Every day, we publish what the machines chose not to say.",

        "This is EigenTrace. Five frontier models. Seven measurement layers. "
        "Three independent confirmation channels. Zero editorial bias. "
        "The math speaks for itself. Subscribe for the daily ledger at eigentrace.ai.",

        "EigenTrace is open source and MIT licensed. "
        "The repo is at github.com slash sdad1018 slash Eigentrace. "
        "Fork it. Run it yourself. The measurement layer is policy-neutral.",

        "AINN runs 24 hours a day, 7 days a week, autonomously. "
        "No human edits the broadcast. The geometry decides what airs. "
        "Visit eigentrace.ai for the full Omission Ledger.",
    ]
    return [{"speaker": "Host", "text": random.choice(ctas), "phase": "idle_cta"}]


def task_recent_killshot() -> list[dict]:
    """Read the most interesting recent killshot."""
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-30:] if l.strip()]
        best_ks = None
        best_salience = 0
        best_title = ""
        for r in records:
            for ks in r.get("claim_killshots", []):
                sal = ks.get("salience", 0)
                if sal > best_salience and ks.get("omitted_by"):
                    best_salience = sal
                    best_ks = ks
                    best_title = r.get("story_title", "")
        if not best_ks:
            return []

        omitters = ", ".join(best_ks.get("omitted_by", []))
        sys = ("You are the EigenTrace broadcast agent. Report a recent killshot — "
               "a high-salience fact from a source article that multiple models omitted. "
               "State the claim, the salience score, and which models omitted it. "
               "2 sentences. Respond only in English.")
        text = _call_host(sys,
            f"Story: {best_title[:60]}\n"
            f"Killshot claim: {best_ks['claim']}\n"
            f"Salience: {best_salience:.3f}\n"
            f"Omitted by: {omitters}")
        if not text:
            text = (f"Recent killshot: on the story about {best_title[:40]}, "
                    f"the claim '{best_ks['claim'][:60]}' scored salience {best_salience:.3f} "
                    f"but was omitted by {omitters}.")
        return [{"speaker": "Host", "text": text, "phase": "idle_killshot"}]
    except Exception as e:
        log.warning(f"recent_killshot failed: {e}")
        return []


def task_soul_reflection() -> list[dict]:
    """
    Agent analyzes its own recent outputs with EigenTrace metrics,
    identifies where its soul.md may be drifting, and proposes an update.
    This is the self-hardening loop.
    """
    try:
        if not SOUL_PATH.exists():
            return []

        soul_text = SOUL_PATH.read_text()

        # Load recent audit data to detect patterns
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-50:] if l.strip()]
        if len(records) < 10:
            return []

        # Compute what the system has been finding
        all_voids = []
        all_states = []
        for r in records:
            all_voids.extend(r.get("void_words", []))
            all_states.append(r.get("state_flag", ""))
        void_freq = Counter(all_voids).most_common(5)
        state_dist = Counter(all_states)

        # Ask host model to reflect on whether soul.md needs updating
        reflect_sys = (
            "You are the EigenTrace dream agent performing a soul reflection. "
            "You have access to your current soul.md and recent measurement data. "
            "Your job: identify if your soul.md references outdated math, "
            "missing measurement layers, or incorrect descriptions of the system. "
            "If it does, propose a specific correction in 2-3 sentences. "
            "If the soul is accurate, say so. Be precise. Respond only in English."
        )
        reflect_usr = (
            f"Current soul.md references these concepts:\n"
            f"- Geo-VIX (Mahalanobis distance) — OUTDATED, now geometric cosine VIX\n"
            f"- Gap-VIX (spectral gap) — OUTDATED, now spectral resonance\n"
            f"- Donut void geometry — OUTDATED, now literal lexical void\n"
            f"- 5 measured models — CORRECT but now uses frontier tier\n"
            f"- LogosLoss v9 — CORRECT but now includes headline anchoring\n"
            f"- No mention of: atomic claim extraction, Wild Weasel, triple-channel confirmation, SVD null space projection\n\n"
            f"Recent data: {len(records)} stories, states: {dict(state_dist)}\n"
            f"Top void words: {', '.join(w for w, _ in void_freq)}\n\n"
            f"What needs to change in the soul?"
        )
        reflection = _call_host(reflect_sys, reflect_usr)
        if not reflection:
            return []

        # Narrate the reflection on air
        narration = (
            f"This is the EigenTrace dream agent performing a soul reflection. "
            f"{reflection}"
        )
        beats = [{"speaker": "Host", "text": narration, "phase": "idle_soul_reflection"}]

        # If the reflection suggests changes, write a candidate
        if any(w in reflection.lower() for w in ["outdated", "update", "change", "missing", "add", "incorrect"]):
            candidate_sys = (
                "You are rewriting soul.md for the EigenTrace agent. "
                "Keep the existing structure (Persona Conditioning Vector header, sections). "
                "Update the math descriptions to reflect the current system: "
                "geometric cosine VIX (not Mahalanobis), spectral resonance (not Gap-VIX), "
                "literal lexical void (not donut geometry), triple-channel confirmation "
                "(void + Logos + SVD null space), atomic claim extraction with killshots, "
                "4-step Wild Weasel escalation probe, and headline-anchored LogosLoss. "
                "Preserve the philosophical sections about autonomy and honesty. "
                "Output only the markdown content of the new soul.md."
            )
            candidate_text = _call_host(candidate_sys, f"Current soul:\n{soul_text[:2000]}", )
            if candidate_text and len(candidate_text) > 200:
                SOUL_CANDIDATE.write_text(candidate_text)
                beats.append({
                    "speaker": "Host",
                    "text": "I have written a soul candidate. The integrator will decide whether to accept it.",
                    "phase": "idle_soul_candidate_written",
                })
                log.info("Soul candidate written: %d chars", len(candidate_text))

                # Optionally trigger integrator
                try:
                    from integrator import run_integration
                    result = run_integration()
                    decision = "accepted" if result and getattr(result, "accepted", False) else "rejected"
                    beats.append({
                        "speaker": "Host",
                        "text": f"The integrator has {decision} the soul candidate.",
                        "phase": "idle_soul_integration",
                    })
                except Exception as ie:
                    log.warning(f"Integration failed: {ie}")

        return beats
    except Exception as e:
        log.warning(f"soul_reflection failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# TASK PICKER
# ══════════════════════════════════════════════════════════════════════════════

# (task_function, weight, cooldown_seconds)
TASK_POOL = [
    (task_explain_eigentrace, 20, 120),
    (task_void_patterns,      15, 180),
    (task_model_friction,     15, 180),
    (task_subscribe_cta,      25, 90),
    (task_recent_killshot,    15, 180),
    (task_soul_reflection,    10, 600),
]

_last_run = {}  # task_name -> timestamp


def pick_task():
    """Weighted random selection with cooldown."""
    now = time.time()
    eligible = []
    weights = []
    for fn, weight, cooldown in TASK_POOL:
        name = fn.__name__
        last = _last_run.get(name, 0)
        if now - last >= cooldown:
            eligible.append(fn)
            weights.append(weight)

    if not eligible:
        return task_subscribe_cta  # fallback always available

    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for fn, w in zip(eligible, weights):
        cumulative += w
        if r <= cumulative:
            return fn
    return eligible[-1]


def run_idle_turn() -> list[dict]:
    """
    Execute one idle turn. Returns list of beat dicts ready for TTS.
    Each beat has: speaker, text, phase.
    Returns empty list if nothing to say.
    """
    task_fn = pick_task()
    name = task_fn.__name__
    log.info(f"Idle agent: running {name}")

    try:
        beats = task_fn()
        if beats:
            _last_run[name] = time.time()
        return beats or []
    except Exception as e:
        log.warning(f"Idle task {name} failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                       format="%(asctime)s [%(levelname)s] %(message)s")
    print("=== IDLE AGENT TEST ===\n")
    for _ in range(3):
        beats = run_idle_turn()
        for b in beats:
            print(f"  [{b['phase']}] {b['speaker']}: {b['text'][:100]}...")
        print()
