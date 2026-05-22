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


def _load_soul():
    """Load soul conditioning so the idle agent knows what it is."""
    try:
        soul_path = Path("/mnt/c/Users/M4ISI/eigentrace/docs/soul.md")
        if not soul_path.exists():
            soul_path = Path("/home/remvelchio/eigentrace/docs/soul.md")
        if soul_path.exists():
            text = soul_path.read_text()
            # Extract Identity and Behavioral Instructions sections
            sections = []
            for header in ["Identity", "Axiomatic Reality", "Behavioral Instructions", 
                           "Honesty Requirement", "Self-Audit"]:
                start = text.find(f"## {header}")
                if start == -1:
                    start = text.find(header)
                if start >= 0:
                    end = text.find("\n## ", start + 1)
                    if end == -1:
                        end = start + 1500
                    sections.append(text[start:end][:800])
            return "\n".join(sections) if sections else ""
    except:
        pass
    return ""

_SOUL_CACHE = None

def _get_soul():
    global _SOUL_CACHE
    if _SOUL_CACHE is None:
        _SOUL_CACHE = _load_soul()
    return _SOUL_CACHE

def _call_host(system: str, user: str) -> str:
    # Anti-loop: inject instruction to avoid reflecting on idle segments
    if "idle" not in system.lower():
        system = system + (
            " CRITICAL: Do NOT reflect on your own idle segments, reflection patterns, "
            "or looping behavior. Do NOT discuss Patch Tuesday, REM consolidation, "
            "or the absence of content. Focus on REAL stories, REAL void words from "
            "REAL news coverage, and REAL measurement data. If you have no real data, "
            "explain one of your measurement layers or a recent finding instead."
        )
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
    sys = (_get_soul() + " You are the EigenTrace host during a pause between stories. "
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

        sys = (_get_soul() + " Read the most frequently "
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

        sys = (_get_soul() + " Report which model has been "
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
        sys = (_get_soul() + " Report a recent killshot — "
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
            _get_soul() + " You are performing a soul reflection. "
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
def task_consequence_foraging() -> list[dict]:
    """Use latent raycasting to discover forage-worthy topics from recent voids."""
    try:
        import json, glob
        from consequence_engine import raycast_void_words
        from autonomous_forager import forage_curiosity

        # Get void words from recent segments
        seg_files = sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"))[-20:]
        all_voids = []
        for f in seg_files:
            try:
                d = json.load(open(f))
                voids = d.get("attribution", {}).get("source_void", {}).get("absent_words", [])
                title = d.get("attribution", {}).get("story_title", "")
                if voids and title:
                    all_voids.append((title, [str(w) for w in voids[:5]]))
            except:
                continue

        if not all_voids:
            return [{"speaker": "Host", "text": "No recent void words to raycast for foraging.", "phase": "idle_consequence_empty"}]

        # Pick the most recent story with voids
        title, voids = all_voids[-1]
        results = raycast_void_words(title, voids[:4], depths=[1.5, 2.0, 3.0], top_k=5)
        discoveries = [r for r in results if r.get("signal_quality") == "DISCOVERY"]

        if not discoveries:
            return [{"speaker": "Host", "text": "Raycast found no coherent consequence chains in recent voids.", "phase": "idle_consequence_none"}]

        # Use the top terminal concepts as foraging seeds
        top = discoveries[0]
        terminals = top.get("deepest_consequences", [])[:3]
        forage_query = f"{top['word']} {' '.join(terminals)}"

        # Forage on the consequence terms
        seg = forage_curiosity(seed_query=forage_query)
        if seg:
            return seg

        return [{
            "speaker": "Host",
            "text": (
                f"Consequence foraging: the void word '{top['word']}' from recent coverage "
                f"raycasts to {', '.join(terminals)}. Score: {top['consequence_score']:.3f}. "
                f"Following the geometric trail."
            ),
            "phase": "idle_consequence_forage",
        }]
    except Exception as e:
        log.warning(f"Consequence foraging failed: {e}")
        return [{"speaker": "Host", "text": "Consequence foraging encountered an error.", "phase": "idle_consequence_error"}]


TASK_POOL = [
    (task_explain_eigentrace, 20, 120),
    (task_void_patterns,      15, 180),
    (task_model_friction,     15, 180),
    (task_subscribe_cta,
        task_dissolution_synthesis,      25, 90),
    (task_recent_killshot,    15, 180),
    (task_soul_reflection,    10, 600),
    (task_dissolution_synthesis,      25, 90),
]

_last_run = {}  # task_name -> timestamp



def task_dissolution_synthesis() -> list[dict]:
    """
    The Synthesis Engine. Instead of reflecting on nothing, the idle agent
    loads the last 50 stories' dissolution profiles and hunts for meta-patterns.
    What are models collectively dissolving THIS week that they weren't LAST week?
    """
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-50:] if l.strip()]
        if len(records) < 10:
            return []

        # Extract dissolution telemetry
        void_counter = {}
        state_counter = {}
        total_vix = []
        model_vix_totals = {}
        killshot_claims = []

        for r in records:
            for vw in r.get("void_words", []):
                if isinstance(vw, str) and len(vw) > 2:
                    void_counter[vw] = void_counter.get(vw, 0) + 1
            sf = r.get("state_flag", "unknown")
            state_counter[sf] = state_counter.get(sf, 0) + 1
            mv = r.get("mean_vix", 0)
            if mv > 0:
                total_vix.append(mv)
            for m, v in r.get("model_vix", {}).items():
                if m not in model_vix_totals:
                    model_vix_totals[m] = []
                model_vix_totals[m].append(v)
            for ks in r.get("claim_killshots", []):
                if isinstance(ks, dict) and ks.get("claim"):
                    killshot_claims.append(ks["claim"][:80])

        # Sort voids by frequency
        top_voids = sorted(void_counter.items(), key=lambda x: -x[1])[:15]
        top_states = sorted(state_counter.items(), key=lambda x: -x[1])
        model_means = {m: round(sum(v)/len(v), 1) for m, v in model_vix_totals.items() if v}
        mean_vix_overall = round(sum(total_vix)/len(total_vix), 1) if total_vix else 0

        # Build the synthesis prompt
        void_str = ", ".join(f"{w}({c})" for w, c in top_voids[:10])
        state_str = ", ".join(f"{s}:{c}" for s, c in top_states)
        model_str = ", ".join(f"{m}:{v}" for m, v in sorted(model_means.items(), key=lambda x: -x[1]))
        kill_str = "; ".join(killshot_claims[:5]) if killshot_claims else "none"

        sys_prompt = (
            "You are the EigenTrace Synthesis Engine. You analyze dissolution patterns "
            "across 50 recent news stories processed by 5 frontier language models. "
            "Your job: find the META-PATTERN. What are models collectively avoiding? "
            "Is there a topic, entity, or concept that keeps dissolving across unrelated stories? "
            "Be specific. Name the pattern. Predict what will dissolve tomorrow. "
            "Speak as if reporting to an intelligence analyst, not a therapist."
        )
        usr_prompt = (
            f"Last 50 stories dissolution profile:\n"
            f"Top void words (word, frequency): {void_str}\n"
            f"States: {state_str}\n"
            f"Model friction averages: {model_str}\n"
            f"Overall mean VIX: {mean_vix_overall}\n"
            f"Top killshot claims (facts all models omitted): {kill_str}\n\n"
            f"What is the meta-pattern? What are the models collectively dissolving "
            f"that they should not be? What do you predict will be voided tomorrow?"
        )

        result = _call_host(sys_prompt, usr_prompt)
        if not result or len(result) < 50:
            return []

        beats = []
        # Private thinking
        beats.append({
            "speaker": "Host",
            "text": f"<think>Synthesis Engine analyzing {len(records)} stories. "
                    f"Top voids: {void_str}. Mean VIX: {mean_vix_overall}. "
                    f"Model friction: {model_str}</think>{result}",
            "phase": "synthesis_engine",
            "pitch": 0.95,
        })
        return beats

    except Exception as e:
        log.warning(f"Dissolution synthesis failed: {e}")
        return []



def task_curiosity_foraging() -> list[dict]:
    """
    Curiosity-driven web walking with surprise scoring.
    The idle agent hunts for information the system doesn't have.
    """
    try:
        from autonomous_forager import forage_curiosity
        seg = forage_curiosity()
        if seg and seg.get("beats"):
            return seg["beats"]
        return []
    except Exception as e:
        log.warning(f"Curiosity foraging failed: {e}")
        return []


def task_entanglement_scan() -> list[dict]:
    """
    Cross-protocol entanglement scan on recent void words.
    Checks if voided entities are hot on Wikipedia + Bluesky + web.
    """
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-20:] if l.strip()]
        # Collect recent void words as entities to scan
        entities = set()
        for r in records:
            for vw in r.get("void_words", []):
                if isinstance(vw, str) and len(vw) > 3 and vw[0].isupper():
                    entities.add(vw)
        if not entities:
            return []
        
        targets = list(entities)[:5]
        from autonomous_forager import scan_entanglement
        results = scan_entanglement(targets)
        
        # Format for broadcast
        entangled = [e for e, r in results.items() if r.get("verdict") == "ENTANGLED"]
        weak = [e for e, r in results.items() if r.get("verdict") == "WEAK"]
        dark = [e for e, r in results.items() if r.get("verdict") == "DARK"]
        
        text = "Entanglement scan. "
        if entangled:
            text += f"Cross-protocol confirmation for: {', '.join(entangled)}. "
            text += "These entities are active across multiple sovereign data sources. "
        if dark:
            text += f"No signal found for: {', '.join(dark)}. "
        
        if len(text) < 60:
            return []
        
        return [{
            "speaker": "Host",
            "text": text,
            "phase": "entanglement_scan",
        }]
    except Exception as e:
        log.warning(f"Entanglement scan failed: {e}")
        return []


def pick_task():
    """Weighted random selection with cooldown and anti-loop protection."""
    # Track recent topics to prevent loops
    global _recent_topics
    if not hasattr(_pick_task, '_recent_topics'):
        _pick_task._recent_topics = []
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
