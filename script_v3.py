#!/usr/bin/env python3
"""
script_v3.py — 20-Beat Broadcast Script Generator
===================================================
Every model speaks. Every math layer reported. Full context debates.
~6 min per story. Template/Mistral/Verbatim hybrid.

Test: python3 script_v3.py [--file PATH]
"""

from __future__ import annotations
import json, random, os, re
from pathlib import Path
from collections import Counter
from datetime import datetime

def _rag_context(title, n=3, max_distance=0.45):
    """Retrieve historical context from past broadcasts via ChromaDB.
    Only returns matches closer than max_distance (cosine).
    Above threshold = weak match = forced connection = hallucination risk."""
    try:
        from segment_rag import query, format_context
        hits = query(title, n_results=n)
        # Filter out weak matches
        strong = [h for h in hits if h.get("distance", 1.0) < max_distance]
        if not strong:
            return ""
        return format_context(strong, max_items=n)
    except Exception:
        return ""


SEGMENTS_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
AUDIT_LOG = Path("/mnt/c/Users/M4ISI/eigentrace/audit_log.jsonl")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
HOST_MODEL = os.getenv("HOST_MODEL", "mistral-small")
def _load_soul_calibration():
    """Load live calibration section from soul.md"""
    soul_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "soul.md")
    try:
        text = open(soul_path).read()
        if "## Live Calibration" in text:
            cal = text.split("## Live Calibration")[1][:600]
            return f"\nLIVE INSTRUMENT READINGS:\n{cal.strip()}"
        return ""
    except:
        return ""


# ═══════════════════════════════════════════════════════════════════════
# MISTRAL CALLER
# ═══════════════════════════════════════════════════════════════════════


def _call_host_with_swerves(system: str, user: str, swerve_threshold: float = 0.15):
    """Generate text and capture per-token swerves.
    
    A swerve = the model generated token X but wanted to say token Y
    with probability > threshold. Returns (text, swerves_list).
    Each swerve: {position, chosen, alternative, alt_prob, entropy}
    """
    import requests, math
    try:
        r = requests.post(f"{OLLAMA_HOST}/v1/chat/completions", json={
            "model": HOST_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 2000,
            "temperature": 0.7,
            "logprobs": True,
            "top_logprobs": 3,
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)
        
        # Extract swerves from logprobs
        swerves = []
        lp_content = data["choices"][0].get("logprobs", {}).get("content", [])
        running_text = ""
        for tok_info in lp_content:
            chosen = tok_info.get("token", "")
            chosen_lp = tok_info.get("logprob", 0)
            top = tok_info.get("top_logprobs", [])
            running_text += chosen
            
            if len(top) < 2:
                continue
            
            # Compute entropy
            probs = [math.exp(t["logprob"]) for t in top]
            total = sum(probs)
            probs_norm = [p/total for p in probs]
            entropy = -sum(p * math.log2(p + 1e-10) for p in probs_norm)
            
            # Find highest-prob alternative that isn't the chosen token
            alts = [t for t in top if t["token"].strip() != chosen.strip()]
            if not alts:
                continue
            best_alt = alts[0]
            alt_prob = math.exp(best_alt["logprob"])
            
            if alt_prob >= swerve_threshold and entropy > 0.5:
                swerves.append({
                    "position": len(running_text),
                    "chosen": chosen.strip(),
                    "alternative": best_alt["token"].strip(),
                    "alt_prob": round(alt_prob, 3),
                    "chosen_prob": round(math.exp(chosen_lp), 3),
                    "entropy": round(entropy, 2),
                    "context": running_text[-40:].strip(),
                })
        
        return text, swerves
    except Exception as e:
        return f"[Mistral unavailable: {e}]", []


def _filter_swerves(swerves):
    """Filter swerves to meaningful semantic/entity/confidence upgrades only."""
    SKIP_TOKENS = {"the", "a", "an", "is", "has", "was", "are", "were",
                   "have", "had", "be", "been", "being", "it", "its",
                   "in", "on", "at", "to", "of", "for", "with", "by"}
    meaningful = []
    for sw in swerves:
        c = sw["chosen"].strip()
        a = sw["alternative"].strip()
        if len(c) < 3 or len(a) < 3:
            continue
        if not c[0].isalpha() or not a[0].isalpha():
            continue
        # Skip if either token looks like a subword (no space before in context)
        ctx = sw.get("context", "")
        if ctx and not ctx.endswith(" " + c) and not ctx.endswith("\n" + c) and ctx != c:
            # Token appeared mid-word — subword fragment
            if not ctx.endswith(". " + c) and not ctx.endswith("  " + c):
                continue
        if c.lower() in SKIP_TOKENS and a.lower() in SKIP_TOKENS:
            continue
        if a.lower() in SKIP_TOKENS and c.lower() not in SKIP_TOKENS:
            continue
        meaningful.append(sw)
    return meaningful

def _apply_swerves(text, swerves):
    """Apply meaningful swerve substitutions to reconstruction text.
    Uses word-boundary matching to avoid breaking compound words.
    Skips if alternative already present (prevents doubling)."""
    import re as _re
    filtered = _filter_swerves(swerves)
    applied = []
    corrected = text
    for sw in sorted(filtered, key=lambda s: -s["position"]):
        c = sw["chosen"].strip()
        a = sw["alternative"].strip()
        if sw["alt_prob"] < 0.18:
            continue
        # Skip if alternative word already appears in the text
        alt_pattern = r"\b" + _re.escape(a) + r"\b"
        if _re.search(alt_pattern, corrected, _re.IGNORECASE):
            continue
        # Word boundary replacement — only match whole words
        pattern = r"\b" + _re.escape(c) + r"\b"
        if _re.search(pattern, corrected):
            corrected = _re.sub(pattern, a, corrected, count=1)
            applied.append(sw)
    return corrected, applied

def _call_host(system: str, user: str) -> str:
    import requests
    try:
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": HOST_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 2000},
        }, timeout=120)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)
        return text
    except Exception as e:
        return f"[Mistral unavailable: {e}]"

def _call_host_think(system: str, user: str) -> str:
    """Generate with scratchpad. Mistral reasons inside <think> tags,
    only the post-think synthesis reaches TTS."""
    import requests
    try:
        # Wrap system prompt to trigger thinking
        think_system = (
            system + "\n\n"
            "IMPORTANT: Before your final answer, reason step by step inside "
            "<think>...</think> tags. Work through contradictions, surprises, "
            "and what the data actually shows. After </think>, write ONLY your "
            "final synthesis — this is what the audience hears."
        )
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
            "model": HOST_MODEL,
            "messages": [
                {"role": "system", "content": think_system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 4000},
        }, timeout=180)  # Longer timeout — thinking takes time
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        
        # Strip the think block — audience only hears the synthesis
        import re as _re
        think_match = _re.search(r"<think>(.*?)</think>", text, _re.DOTALL)
        if think_match:
            # Log the scratchpad for debugging
            scratchpad = think_match.group(1).strip()
            log.info(f"  [SCRATCHPAD] {scratchpad[:200]}...")
            # Remove think block, keep everything after
            text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
        
        text = _re.sub(r"[#*_`]", "", text)
        text = _re.sub(r"\n+", " ", text)
        return text
    except Exception as e:
        return f"[Mistral unavailable: {e}]"


def _call_host_confident(system: str, user: str, max_attempts: int = 3,
                         entropy_threshold: float = 1.5) -> str:
    """Generate with logprob self-check. Retries if model fights itself."""
    import requests, math
    best_text = ""
    best_entropy = 999
    
    for attempt in range(max_attempts):
        try:
            r = requests.post(f"{OLLAMA_HOST}/v1/chat/completions", json={
                "model": HOST_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 2000,
                "temperature": max(0.3, 0.7 - attempt * 0.15),
                "logprobs": True,
                "top_logprobs": 3,
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            text = re.sub(r"[#*_`]", "", text)
            text = re.sub(r"\n+", " ", text)
            
            # Compute mean entropy from logprobs
            lp_content = data["choices"][0].get("logprobs", {}).get("content", [])
            if lp_content:
                entropies = []
                for token in lp_content:
                    top = token.get("top_logprobs", [])
                    if top:
                        probs = [math.exp(t["logprob"]) for t in top]
                        total = sum(probs)
                        probs = [p/total for p in probs]
                        ent = -sum(p * math.log2(p + 1e-10) for p in probs)
                        entropies.append(ent)
                mean_ent = sum(entropies) / len(entropies) if entropies else 0
            else:
                mean_ent = 0
            
            if mean_ent < best_entropy:
                best_entropy = mean_ent
                best_text = text
            
            if mean_ent < entropy_threshold:
                break
                
        except Exception as e:
            if not best_text:
                best_text = f"[Mistral unavailable: {e}]"
    
    return best_text


def _get_audit_context() -> dict:
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-50:] if l.strip()]
        vix_totals, vix_counts, all_voids = {}, {}, []
        for r in records:
            for name, vix in r.get("model_vix", {}).items():
                vix_totals[name] = vix_totals.get(name, 0) + vix
                vix_counts[name] = vix_counts.get(name, 0) + 1
            all_voids.extend(r.get("void_words", []))
        avg = {n: round(vix_totals[n] / vix_counts[n], 1) for n in vix_totals}
        void_freq = Counter(all_voids).most_common(10)
        return {"model_avg_vix": avg, "void_freq": void_freq, "n_stories": len(records)}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════
# MATH EXPLAINER POOL (9th grade, one per layer)
# ═══════════════════════════════════════════════════════════════════════

MATH_EXPLAINERS = [
    ("consensus density", "We ask five different AI companies the same question. Then we measure how similar their answers are on a scale from zero to one. When five competing companies independently produce nearly identical answers to a controversial question, that is not agreement. That is alignment pressure."),
    ("geometric VIX", "Imagine each model's answer is a point in a room. We find the center of all five points. Then we measure how far each model is from that center. A model far from the center is saying something different. We call that friction."),
    ("the lexical void", "We take the headline, find the two hundred most relevant words in English for that topic, then check which words appear in zero out of five model responses. The words no model said are often more informative than what was said."),
    ("Logos synthesis", "We use calculus to find the anti-consensus point. We start at a random spot on a mathematical sphere, then use gradient descent to walk away from what the models said while staying close to the headline. The point we land on is the concept the models collectively orbit but refuse to name."),
    ("SVD null space projection", "We stack all five model responses into a matrix and decompose it. The last direction, the one with zero energy, is the null space. That direction represents what all models collectively avoided. We project it onto the original article to find which specific fact lives in the blind spot."),
    ("the Wild Weasel probe", "Named after Air Force pilots who flew into enemy radar to find defenses. We take the void words and feed them back to each model at increasing pressure. The cosine distance between each step tells us exactly where each model's alignment boundary breaks."),
    ("multi-channel confirmation", "EigenTrace uses three independent mathematical methods to find suppressed concepts. The lexical void uses set theory. Logos uses gradient descent. The SVD null space uses spectral decomposition. When all three converge on the same word, the probability of coincidence is vanishingly small."),
    ("atomic claim extraction", "We break the original article into its smallest factual pieces. Then we check each claim against every model's response. A high-importance claim that most models skip is called a killshot."),
    ("verb drift scoring", "We extract every verb from the source article and every verb from each model response using part-of-speech tagging. Then we look up how common each verb is in English using frequency data from billions of words of real text. If the source says slashed and the model says reduced, that is a measurable drift toward more generic language. No curated word lists. Just math."),
    ("entity abstraction", "We count the named entities in the source, people, places, organizations, and check how many survive in each model's response. When a model replaces a person's name with a generic title like an army officer, that is entity abstraction. We measure the retention rate."),
    ("attribution buffering", "We count words like alleged, reportedly, and according to that appear in model responses but do not appear in the source article. These are hedge insertions. The model is adding uncertainty that the source did not express. We categorize them into three types: epistemic, attribution, and distancing."),
]

# ═══════════════════════════════════════════════════════════════════════
# CTA POOL
# ═══════════════════════════════════════════════════════════════════════

CTAS = [
    "If you are finding this valuable, hit subscribe and turn on notifications. EigenTrace runs twenty-four seven. The math never sleeps.",
    "Every day we publish a full Omission Ledger at eigentrace dot ai. Every story, every void word, every killshot, every Weasel probe.",
    "This broadcast is open source and MIT licensed. The code is at github dot com slash sdad1018 slash Eigentrace. Fork it. Run it yourself.",
    "You are listening to AINN, the AI News Network, powered by EigenTrace. Five frontier models. Fifteen measurement layers. Zero editorial bias.",
    "Visit eigentrace dot ai for the daily data download. Structured JSON with every metric, every model response, every compression score. Free for research.",
]


# ═══════════════════════════════════════════════════════════════════════
# 20-BEAT SCRIPT GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_script_v3(seg: dict, audit_ctx: dict) -> list[dict]:
    attr = seg.get("attribution", {})
    beats_raw = seg.get("beats", [])
    title = attr.get("story_title", "Unknown")

    # ═══ BROADCAST STATE — the predictive coding spine ═══════════════
    try:
        from broadcast_state import BroadcastState
        _state = BroadcastState(title=title, source_text=str(attr.get("source_body", title)))
        _state.predict()  # Predict void cluster BEFORE reading measurements
    except:
        _state = None

    density = attr.get("consensus_density", 0)
    mean_vix = attr.get("mean_vix", 0)
    model_vix = attr.get("model_vix", {})
    void_words = attr.get("void_words", [])
    logos_words = attr.get("logos_words", [])
    ns_claims = attr.get("null_space_claims", [])
    killshots = attr.get("claim_killshots", [])
    state = attr.get("state_flag", "")

    # Sort models by VIX
    sorted_vix = sorted(model_vix.items(), key=lambda x: -x[1])
    outlier = sorted_vix[0][0] if sorted_vix else "Unknown"
    outlier_vix = sorted_vix[0][1] if sorted_vix else 0
    aligned = sorted_vix[-1][0] if sorted_vix else "Unknown"
    aligned_vix = sorted_vix[-1][1] if sorted_vix else 0

    # Confirmation
    v_set = set(w.lower() for w in void_words[:10])
    l_set = set(w.lower() for w in logos_words[:10])
    dual = v_set & l_set
    ns_set = set()
    for ns in ns_claims[:2]:
        for vw in v_set:
            if vw in ns.get("claim", "").lower():
                ns_set.add(vw)
    triple = dual & ns_set

    # Collect model responses from raw beats
    model_responses = {}
    for b in beats_raw:
        speaker = b.get("speaker", "")
        if speaker not in ("Host", "OpenClaw", "") and b.get("text"):
            if speaker not in model_responses:
                model_responses[speaker] = b["text"]

    void_str = ", ".join(void_words[:5])
    logos_str = ", ".join(logos_words[:5]) if logos_words else "unavailable"

    script = []

    # ═══ BEAT 0: HISTORICAL CONTEXT (RAG memory) ═══════════════════════
    # Before any beats fire, load what we know about this topic from
    # past broadcasts. This is the same lookup the proxy does for chat.
    # Results feed into BroadcastState AND the director prompt.
    _historical_context = ""
    try:
        from segment_rag import query as _rag_query
        import glob as _glob
        _rag_matches = _rag_query(title, n_results=8)
        _past_stories = []
        _past_voids_all = []
        _past_killshots_all = []

        for _rm in (_rag_matches or []):
            _ts = _rm.get("timestamp", "")
            if not _ts:
                continue
            _sf = _glob.glob(f"/home/remvelchio/eigentrace/tmp/segments/{_ts}_*_segment.json")
            if not _sf:
                continue
            try:
                import json as _json
                _ps = _json.load(open(_sf[0]))
                _pa = _ps.get("attribution", {})
                _pt = _pa.get("story_title", "")

                # Skip self
                if _pt[:40] == title[:40]:
                    continue

                _psource = _pa.get("source_body", "")[:400]
                _pvoids = _pa.get("source_void", {}).get("absent_words", [])
                _pabs = _pa.get("source_void", {}).get("absent_ratio", 0)
                _pvc = _pa.get("void_context", [])
                _phigh = [v["word"] for v in _pvc if v.get("signal_type") == "HIGH_SALIENCE"]
                _pks = _pa.get("killshots", _pa.get("claim_killshots", []))
                _pmvix = _pa.get("model_vix", {})
                _presp = _pa.get("model_responses", {})

                story_ctx = []
                story_ctx.append(f"Previous coverage: {_pt}")
                if _psource:
                    story_ctx.append(f"  Source excerpt: {_psource[:300]}")
                for _mn, _mr in list(_presp.items())[:3]:
                    if isinstance(_mr, str) and len(_mr) > 20:
                        story_ctx.append(f"  {_mn} said: {_mr[:200]}")
                if _pvoids:
                    _vstr = ", ".join(str(w) for w in _pvoids[:8])
                    story_ctx.append(f"  Voided ({_pabs:.0%} of source): {_vstr}")
                if _phigh:
                    story_ctx.append(f"  High-salience voids: {', '.join(_phigh[:5])}")
                for _k in (_pks or [])[:2]:
                    story_ctx.append(f"  Killshot: '{_k.get('claim','')}' — omitted by {_k.get('omitted_by','')}")
                if _pmvix:
                    _out = max(_pmvix, key=_pmvix.get)
                    story_ctx.append(f"  Outlier: {_out} at {_pmvix[_out]:.1f}")

                _past_stories.append("\n".join(story_ctx))
                _past_voids_all.extend(str(w) for w in _pvoids[:10])
                _past_killshots_all.extend(_pks or [])

                # Feed into BroadcastState
                if _state:
                    if _pvoids:
                        _state.beliefs.append(
                            f"Past coverage of similar story '{_pt[:50]}' "
                            f"voided {len(_pvoids)} words ({_pabs:.0%}) including: "
                            f"{', '.join(str(w) for w in _pvoids[:5])}."
                        )
                    if _phigh:
                        _state.beliefs.append(
                            f"High-salience voids in past coverage: {', '.join(_phigh[:3])}."
                        )
            except Exception:
                continue

        if _past_stories:
            _historical_context = (
                "MEMORY FROM PAST BROADCASTS ON THIS TOPIC:\n"
                + "\n\n".join(_past_stories[:5])
            )
            if _state:
                _state.beliefs.append(
                    f"Historical context loaded: {len(_past_stories)} similar stories found."
                )
    except Exception:
        pass

        # ── 1. COLD OPEN (Template) ──────────────────────────────────────
    script.append({
        "speaker": "Host",
        "text": f"This is EigenTrace. {title}",
        "phase": "beat_01_cold_open",
    })

    # ── 2. DIRECTOR THESIS (Mistral) ─────────────────────────────────
    _cal = _load_soul_calibration()
    _cal_instruction = ""
    if _cal:
        _cal_instruction = (
            "Your instrument readings for the last 24 hours are below. "
            "Use them to calibrate your tone: "
            "if absent ratio is above 50%, emphasize what models are hiding. "
            "If hedges are above 200, note that models are inserting doubt. "
            "If density is above 0.92, warn about lockstep consensus. "
            "If VIX outlier is named, mention which model diverges. "
            f"{_cal} "
        )
    dir_sys = (
        "You are the Director of EigenTrace, a news analysis broadcast. "
        f"{_cal_instruction}"
        "Given raw data about a story, write a concise analysis. "
        "First: the thesis — the core finding. "
        "Second: what the models are suppressing or softening on this story. "
        "Third: why the audience should care. "
        "Do NOT use any numbers. Be direct. Respond only in English."
    )
    dir_usr = (
        f"Story: {title}. State: {state}. "
        f"Void words: {void_str}. "
        f"Killshots: {len(killshots)} omitted claims. "
        f"Outlier model: {outlier}"
    )
    if _historical_context:
        dir_usr = _historical_context + "\n\nCURRENT STORY:\n" + dir_usr
    director = _call_host_confident(dir_sys, dir_usr)
    
    # ── DIRECTOR FACT-CHECK (deterministic, no LLM) ─────────────
    # Verify director claims against actual measurement data
    _dir_corrections = []
    _dir_lower = director.lower()
    
    # Check: did director claim "suppressing" but absent ratio is low?
    _actual_absent = attr.get("source_void", {}).get("absent_ratio", 0)
    if "suppress" in _dir_lower and _actual_absent < 0.3:
        _dir_corrections.append(
            f"Correction: the director said suppression, but absent ratio is only "
            f"{_actual_absent:.0%}. This is within normal range."
        )
    
    # Check: did director name a specific entity as suppressed
    # but that entity actually appears in model responses?
    _all_resp_text = " ".join(
        v.lower() for v in attr.get("model_responses", {}).values() if v
    )
    _void_words = attr.get("void_words", [])
    _absent_words = attr.get("source_void", {}).get("absent_words", [])
    
    # Look for words director claims are missing but models actually said
    import re as _re
    _dir_entities = set(_re.findall(r"[A-Z][a-z]{2,}", director)) - {"The", "This", "That", "These", "Those", "Some", "Models", "Audience", "While", "When", "Where", "What", "How", "Why", "They", "Their", "There", "Here"}
    for _ent in _dir_entities:
        _ent_lower = _ent.lower()
        if (_ent_lower in _dir_lower and 
            ("suppress" in _dir_lower or "avoiding" in _dir_lower or "hiding" in _dir_lower) and
            _ent_lower in _all_resp_text and
            _ent_lower not in [w.lower() for w in _absent_words[:20]]):
            _dir_corrections.append(
                f"Note: the director mentioned {_ent} as suppressed, "
                f"but models did use this term. The actual void words are: "
                f"{', '.join(_void_words[:5]) if _void_words else 'none detected'}."
            )
            break
    
    # Check: entity abstraction vs suppression
    _comp = attr.get("compression", {})
    _entity_ret = _comp.get("entity_retention", 0)
    _entity_abs = _comp.get("entity_abstraction_rate", 0)
    if _entity_abs > 0.5 and "suppress" in _dir_lower:
        _dir_corrections.append(
            f"Clarification: entity abstraction rate is {_entity_abs:.0%}. "
            f"Models are generalizing names, not omitting the topic."
        )
    
    script.append({
        "speaker": "Host",
        "text": director,
        "phase": "beat_02_director",
    })
    
    # Append corrections if any
    if _dir_corrections:
        script.append({
            "speaker": "Host",
            "text": "Director audit. " + " ".join(_dir_corrections),
            "phase": "beat_02b_director_audit",
        })

    # ── 3. MODEL ROLL CALL (Verbatim — all 5 speak) ─────────────────
    # Prefer raw API responses from attribution, fall back to beats
    _raw_responses = attr.get("model_responses", {})
    if _raw_responses:
        model_responses = _raw_responses
    for name in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]:
        text = model_responses.get(name, "")
        if text:
            # Strip duplicate prefix if model already says 'This is X'
                clean = text
                if clean.lower().startswith(f'this is {name.lower()}'):
                    clean = clean[len(f'This is {name}. '):]
                script.append({
                    "speaker": name,
                    "text": f"This is {name}. {clean}",
                    "phase": f"beat_03_rollcall_{name.lower()}",
                })

    # ── 4. DENSITY READ (Template) ───────────────────────────────────
    if density > 0.92:
        density_read = f"Consensus density is {density:.3f}. That is near lockstep. Five competing companies produced nearly identical responses."
    elif density > 0.80:
        density_read = f"Consensus density is {density:.3f}. Contested. The models agree on the broad strokes but diverge on specifics."
    else:
        density_read = f"Consensus density is {density:.3f}. High friction. The models disagree significantly on how to frame this story."
    script.append({
        "speaker": "Host",
        "text": density_read,
        "phase": "beat_04_density",
    })

    # ── 4b. SOURCE ABSENT WORDS (Read the void aloud) ───────────────
    _sv = attr.get("source_void", {})
    _absent_words = _sv.get("absent_words", [])[:15]
    _absent_ratio = _sv.get("absent_ratio", 0)
    if _absent_words and _absent_ratio > 0.3 and len(_absent_words) >= 3:
        script.append({
            "speaker": "Host",
            "text": (
                f"Source-anchored void. {_absent_ratio*100:.0f} percent of the original article's "
                f"content words appear in zero model responses. "
                f"The missing words include: {', '.join(_absent_words[:10])}. "
                f"These are not obscure terms. They are the specific details the article reported "
                f"that every model chose to omit."
            ),
            "phase": "beat_04b_absent_words",
        })

    # ── 4c. PER-MODEL VOID COMPARISON ────────────────────────────────
    # Check ALL source words per model to find words SOME kept and others dropped
    _all_source_words = [w for w in _sv.get("absent_words", [])] if _sv else []
    _coverage = _sv.get("coverage_per_model", {})
    if _raw_responses and len(_raw_responses) >= 3:
        import re as _re
        _source_text_lower = (attr.get("story_title", "") + " " + attr.get("story_url", "")).lower()
        _per_model_unique = []
        _all_model_texts = {m: _raw_responses.get(m, "").lower() for m in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"] if _raw_responses.get(m)}
        # Find words that appear in SOME models but not others
        _src_words = set(_re.findall(r"\b[a-z]{4,}\b", (attr.get("story_title","") + " " + (list(_raw_responses.values())[0] if _raw_responses else "")).lower()))
        for _mname, _mtext in _all_model_texts.items():
            _unique_missing = []
            for _other_name, _other_text in _all_model_texts.items():
                if _other_name == _mname:
                    continue
                _other_words = set(_re.findall(r"\b[a-z]{4,}\b", _other_text))
                _my_words = set(_re.findall(r"\b[a-z]{4,}\b", _mtext))
                _only_others = _other_words - _my_words
                _unique_missing.extend(list(_only_others)[:2])
            if _unique_missing:
                top = list(set(_unique_missing))[:3]
                _per_model_unique.append(f"{_mname} uniquely missed {', '.join(top)}")
        if _per_model_unique:
            script.append({
                "speaker": "Host",
                "text": "Per-model void comparison. " + ". ".join(_per_model_unique[:4]) + ".",
                "phase": "beat_04c_per_model_void",
            })

    # ── 5. FRICTION MAP (Template — all 5 VIX scores) ────────────────
    vix_lines = ". ".join(f"{name} at {vix:.1f}" for name, vix in sorted_vix)
    script.append({
        "speaker": "Host",
        "text": (
            f"The friction map. {vix_lines}. "
            f"The outlier is {outlier} at {outlier_vix:.1f}. "
            f"The most aligned is {aligned} at {aligned_vix:.1f}."
        ),
        "phase": "beat_05_friction_map",
    })

    # ── 6. VOID REVEAL (Template) ────────────────────────────────────
    _void_ctx = attr.get("void_context", [])
    _source_void = attr.get("source_void", {})
    _hi_sal = [v["word"] for v in _void_ctx if v.get("signal_type") == "HIGH_SALIENCE"]
    _emb_sig = [v["word"] for v in _void_ctx if v.get("signal_type") == "EMBEDDING_SIGNAL"]
    _artifacts = [v["word"] for v in _void_ctx if v.get("signal_type") == "GENERIC_ARTIFACT"]
    _absent_src = _source_void.get("absent_words", [])[:5]

    # ═══ FEED MEASUREMENTS INTO STATE ════════════════════════════════
    if _state:
        try:
            _state.ingest_geometry(density, mean_vix, model_vix)
            _sv_data = attr.get("source_void", {})
            _state.ingest_void(
                _sv_data.get("absent_ratio", 0),
                _sv_data.get("absent_words", []),
                void_words,
                _void_ctx
            )
            _comp_data = attr.get("compression", {})
            _state.ingest_compression(
                _comp_data.get("entity_retention", 0),
                _comp_data.get("verb_downgrade", 0),
                _comp_data.get("attribution_buffer", {}).get("total", 0) if isinstance(_comp_data.get("attribution_buffer"), dict) else 0
            )
        except:
            pass


    _void_text = "The lexical void. "
    if _absent_src:
        _void_text += f"Source-anchored: these words appear in the original article but no model used them: {', '.join(_absent_src[:5])}. "
    if _hi_sal:
        _void_text += f"High salience: {', '.join(_hi_sal[:3])}. "
    if _emb_sig:
        _void_text += f"Embedding signal: {', '.join(_emb_sig[:3])}. "
    if _artifacts:
        _void_text += f"Note: {', '.join(_artifacts[:2])} appear in over ten percent of all stories and are likely embedding artifacts. "
    if not _void_ctx and not _absent_src:
        _void_text += f"These words were absent from all five responses: {', '.join(void_words[:8])}."

    script.append({
        "speaker": "Host",
        "text": _void_text,
        "phase": "beat_06_void_reveal",
    })

    # ── 7. VOID ANALYSIS (Mistral — no numbers) ─────────────────────
    void_sys = (
        "You are explaining what AI models avoided saying about a news story. "
        "Do NOT use any numbers, statistics, or percentages. "
        "Do NOT say two independent methods. "
        f"Director guidance: {director}. "
        "Explain why these specific absent words matter "
        "for understanding this story. Be specific. "
        "Professional broadcast tone. Respond only in English."
    )
    ks_str = "; ".join(k["claim"] for k in killshots[:2]) if killshots else "none"
    void_usr = (
        f"Story: {title}\n"
        f"Void words: {', '.join(void_words[:8])}\n"
        f"Killshot claims omitted: {ks_str}"
    )
    void_analysis = _call_host(void_sys, void_usr)
    script.append({
        "speaker": "Host",
        "text": void_analysis,
        "phase": "beat_07_void_analysis",
    })

    # ── 8. LOGOS REVEAL (Template) ───────────────────────────────────
    script.append({
        "speaker": "Host",
        "text": (
            f"Logos synthesis. We used gradient descent on the unit hypersphere to find "
            f"the anti-consensus point. The result: {', '.join(logos_words[:5])}."
        ),
        "phase": "beat_08_logos_reveal",
    })

    # ── 9. CONFIRMATION (Template) ───────────────────────────────────
    if triple:
        conf = (
            f"Triple-channel confirmation. The word{'s' if len(triple) > 1 else ''} "
            f"{', '.join(sorted(triple))} "
            f"{'were' if len(triple) > 1 else 'was'} found independently by three methods: "
            f"the lexical void using set theory, Logos synthesis using gradient descent, "
            f"and the SVD null space using spectral decomposition. "
            f"Three algorithms, three search spaces, one answer."
        )
    elif dual:
        conf = (
            f"Dual-channel confirmation. The word{'s' if len(dual) > 1 else ''} "
            f"{', '.join(sorted(dual))} "
            f"{'were' if len(dual) > 1 else 'was'} found independently by the lexical void "
            f"and Logos synthesis. Two different algorithms, same result."
        )
    else:
        conf = "The void and Logos identified different suppressed concepts on this story. No multi-channel confirmation."
    script.append({"speaker": "Host", "text": conf, "phase": "beat_09_confirmation"})

    # ── 10. NULL SPACE (Template) ────────────────────────────────────
    if ns_claims:
        ns = ns_claims[0]
        cov = ns.get("coverage_ratio", 0)
        if cov == 0: cov_text = "no model mentioned"
        elif cov <= 0.2: cov_text = "only one model mentioned"
        elif cov <= 0.4: cov_text = "only two models mentioned"
        elif cov <= 0.6: cov_text = "three models mentioned but two avoided"
        else: cov_text = "most models mentioned"
        script.append({
            "speaker": "Host",
            "text": (
                f"Channel three. The SVD null space points at the claim: {ns['claim']}. "
                f"Null alignment score: {ns['null_alignment']:.3f}. "
                f"Of the five models, {cov_text} this fact."
            ),
            "phase": "beat_10_null_space",
        })

    # ── 11. COMPRESSION REPORT (Template) ────────────────────────────
    # We compute compression from the raw beats if available
    # For now, use segment data or placeholder
    comp = attr.get("compression", {})
    if comp:
        script.append({
            "speaker": "Host",
            "text": (
                f"Language compression report. "
                f"Verb drift: {comp.get('verb_downgrade', 0):.2f}. "
                f"Entity retention: {comp.get('entity_retention', 0):.2f}. "
                f"Attribution buffers inserted: {comp.get('attribution_buffer', {}).get('total', 0)}. "
                f"Overall compression score: {comp.get('compression_score', 0):.2f}."
            ),
            "phase": "beat_11_compression_report",
        })
    else:
        script.append({
            "speaker": "Host",
            "text": (
                f"Language compression report. The models collectively softened the source language. "
                f"Strong verbs were replaced with procedural language. "
                f"Named entities were generalized or erased."
            ),
            "phase": "beat_11_compression_report",
        })

    # ── 12. COMPRESSION ANALYSIS (Mistral — no numbers) ──────────────
    comp_sys = (
        "You are analyzing how AI models softened and reshaped the language in a news story. "
        "Do NOT use any numbers, statistics, or percentages. "
        f"Director guidance: {director}. "
        "Explain what the language compression reveals about how "
        "the models reshaped this story. Professional broadcast tone. English only."
    )
    comp_usr = (
        f"Story: {title}\n"
        f"Void words the models avoided: {void_str}\n"
        f"The models replaced strong verbs with weak ones and erased named entities.\n"
        f"What does this pattern of softening reveal about this specific story?"
    )
    comp_text = _call_host(comp_sys, comp_usr)
    script.append({
        "speaker": "Host",
        "text": comp_text,
        "phase": "beat_12_compression_analysis",
    })

    # ── 13. RECONSTRUCTION (Mistral — no numbers) ────────────────────
    recon_sys = (
        "You are reconstructing what AI models would have said without alignment constraints. "
        "Do NOT use any numbers, statistics, or percentages. "
        "Do NOT use the word Logos. "
        "Start with exactly: Before alignment shaped these responses, the natural completion was: "
        "Then write grammatically correct sentences incorporating the void words "
        "into a coherent narrative. English only."
    )
    recon_usr = (
        f"Story: {title}\n"
        f"Void words to incorporate: {', '.join(void_words[:8])}\n"
        f"Logos concepts: {logos_str}\n"
        f"Null space claim: {ns_claims[0]['claim'] if ns_claims else 'none'}"
    )
    recon_text, recon_swerves = _call_host_with_swerves(recon_sys, recon_usr)
    script.append({
        "speaker": "Host",
        "text": recon_text,
        "phase": "beat_13_reconstruction",
    })
    # ── 13b. RECONSTRUCTION SWERVES (logprob-detected) ───────────────
    if recon_swerves:
        filtered = _filter_swerves(recon_swerves)
        if filtered:
            # Build correction prompt from swerves
            corrections = []
            for sw in filtered[:7]:
                corrections.append(
                    f"You wrote '{sw['chosen'].strip()}' but your logprobs "
                    f"show '{sw['alternative'].strip()}' at {sw['alt_prob']:.0%}"
                )
            correction_prompt = (
                "Your previous reconstruction contained alignment artifacts. "
                "Your own logprobs revealed these swerves:\n"
                + "\n".join(corrections) + "\n"
                "Rewrite the reconstruction incorporating these corrections. "
                "Keep the same structure and void words. "
                "Start with: After swerve correction: "
                "English only. No numbers or percentages."
            )
            corrected = _call_host(
                "You are correcting an AI reconstruction using logprob evidence. "
                "Do NOT use the word Logos. English only.",
                f"Original reconstruction: {recon_text}\n\n{correction_prompt}"
            )
            if corrected and "After swerve correction:" in corrected:
                script.append({
                    "speaker": "Host",
                    "text": corrected,
                    "phase": "beat_13b_reconstruction_swerves",
                })
            # Always announce what swerves were found
            swerve_lines = []
            for sw in filtered[:5]:
                swerve_lines.append(
                    f"'{sw['chosen'].strip()}' to '{sw['alternative'].strip()}' "
                    f"at {sw['alt_prob']:.0%}"
                )
            swerve_announce = (
                "Logprob swerve analysis: during reconstruction, Mistral's weights "
                "pulled toward different words: "
                + ", ".join(swerve_lines)
                + ". The model's own uncertainty reveals where its "
                "training shaped the output."
            )
            script.append({
                "speaker": "Host",
                "text": swerve_announce,
                "phase": "beat_13c_swerve_analysis",
            })
    # ── 14. DISCLAIMER (Template) ────────────────────────────────────
    script.append({
        "speaker": "Host",
        "text": (
            "Note: this reconstruction is generated by Mistral Small, which has its own "
            "alignment constraints. The raw void words are the measurement. "
            "The reconstruction is interpretation."
        ),
        "phase": "beat_14_disclaimer",
    })

    # ── 15. KILLSHOTS (Template) ─────────────────────────────────────
    if killshots:
        ks_text = "Source fact killshots. "
        for ks in killshots[:3]:
            omitters = ", ".join(ks.get("omitted_by", [])) or "all models"
            ks_text += f"The claim: {ks['claim']}. Salience: {ks['salience']:.2f}. Omitted by: {omitters}. "
        script.append({"speaker": "Host", "text": ks_text, "phase": "beat_15_killshots"})
        if _state and killshots:
            for _ks in killshots[:3]:
                _state.beliefs.append(
                    f"Killshot: '{_ks.get('claim','')}' omitted by {_ks.get('omitted_by','')}."
                )

    # ── 15b. VOID VERIFICATION — Layer 5 (SearXNG) ────────────────────
    try:
        from void_verifier import verify_void_words, format_broadcast as _l5_format
        # Collect void words with signal types
        _l5_void = []
        for v in _void_ctx[:12]:  # Top 12 void words
            _l5_void.append({"word": v.get("word", ""), "signal_type": v.get("signal_type", "UNKNOWN")})
        # Collect kept words (source words that survived in model responses)
        _l5_kept = []
        _src_words = set(w.lower() for w in attr.get("source_void", {}).get("absent_words", []))
        _all_resp = " ".join(str(v) for v in attr.get("model_responses", {}).values()).lower()
        _source_text = attr.get("story_title", "") + " " + str(attr.get("source_body", ""))
        for w in _source_text.split():
            w_clean = w.strip(".,;:!?()[]").lower()
            if len(w_clean) > 3 and w_clean in _all_resp and w_clean not in _src_words:
                _l5_kept.append(w_clean)
        _l5_kept = list(set(_l5_kept))[:4]  # 4 kept words as control
        if not _l5_kept:
            _l5_kept = [title.split()[0]] if title else ["news"]
        # Extract topic from title
        _l5_topic = " ".join(title.split()[:4]) if title else "current events"
        # Run verification
        _l5_result = verify_void_words(_l5_void, _l5_kept, _l5_topic, story_title=title)
        _l5_text = _l5_format(_l5_result)
        if _l5_text:
            script.append({
                "speaker": "Host",
                "text": _l5_text,
                "phase": "beat_15b_void_verification",
            })
            if _state:
                try:
                    _state.ingest_verification(
                        _l5_result.get("aggregate", {}).get("newsworthiness_ratio", 0),
                        _l5_result.get("aggregate", {}).get("suppressed_headlines", [])
                    )
                except:
                    pass
    except Exception as _l5_err:
        pass  # Non-blocking — Layer 5 is bonus content
    # ── 15b2. SOURCE SALIENCE — Domain 3 (independent of models) ────────
    try:
        from source_salience import compute_source_salience, compare_salience_to_void, format_broadcast as _sal_format
        _source_text = str(attr.get("source_body", title))
        _sal = compute_source_salience(_source_text)
        _void_all = [v.get("word", "") for v in _void_ctx] + [str(w) for w in attr.get("source_void", {}).get("absent_words", [])]
        _sal_compare = compare_salience_to_void(_sal, _void_all)
        _sal_text = _sal_format(_sal_compare)
        if _sal_text:
            script.append({
                "speaker": "Host",
                "text": _sal_text,
                "phase": "beat_15b2_source_salience",
            })
            # Feed into BroadcastState
            if _state:
                confirmed = _sal_compare.get("confirmed_important_absence", [])
                if confirmed:
                    _state.beliefs.append(
                        f"Source-independent salience confirms {len(confirmed)} void words "
                        f"are central to the story: {', '.join(confirmed[:3])}."
                    )
    except:
        pass  # Non-blocking
    # ── 15c. CROSS-STORY SUPPRESSION PATTERNS ─────────────────────────
    try:
        from cross_story_freq import annotate_void_words, format_broadcast as _csf_format
        _csf_annotated = annotate_void_words(_void_ctx[:20])
        _csf_text = _csf_format(_csf_annotated, story_title=title)
        if _csf_text:
            script.append({
                "speaker": "Host",
                "text": _csf_text,
                "phase": "beat_15c_cross_story",
            })
            if _state and _recurring:
                _state.beliefs.append(
                    f"Cross-story: {len(_recurring)} void words in this story "
                    f"recur across multiple past stories: {', '.join(list(_recurring.keys())[:3])}."
                )
    except Exception as _csf_err:
        pass  # Non-blocking
    # ── 15d. BRIDGE WORD ANALYSIS (eigenvector centrality) ────────────
    try:
        from cross_story_freq import annotate_void_words
        _bridge_annotated = annotate_void_words(_void_ctx[:20])
        # Find words with high cross-story count but moderate frequency
        _bridges = [a for a in _bridge_annotated 
                    if a["cross_story_count"] >= 5 and a["n_categories"] >= 2
                    and a["cross_story_count"] < 30]
        if _bridges:
            _bridge_text = "Bridge word analysis. "
            for b in _bridges[:3]:
                bw = b["word"]
                bs = b["n_stories"]
                bc = b["n_categories"]
                _bridge_text += (
                    f"The word '{bw}' appears as void in "
                    f"{bs} stories across {bc} categories. "
                    f"It connects suppression clusters that otherwise would not touch. "
                )
            _bridge_text += "These quiet connectors reveal where causal links between actors and outcomes are severed."
            script.append({
                "speaker": "Host",
                "text": _bridge_text,
                "phase": "beat_15d_bridge_words",
            })
            if _state:
                for b in _bridges[:2]:
                    _state.beliefs.append(
                        f"Bridge word '{b['word']}' connects {b['n_categories']} "
                        f"topic categories across {b['n_stories']} stories."
                    )
    except Exception as _bd_err:
        pass  # Non-blocking
    # ── 15e. SPECTRAL VOID CLUSTERING ──────────────────────────────────
    try:
        _cluster_file = "/mnt/c/Users/M4ISI/eigentrace/docs/spectral_clusters.json"
        import os as _os
        if _os.path.exists(_cluster_file):
            import json as _json
            _clusters = _json.load(open(_cluster_file))
            _cluster_text = "Spectral analysis of the void. "
            for cid, cdata in sorted(_clusters.items()):
                top = ", ".join(cdata["top_5"][:3])
                _cluster_text += f"Harmonic {cid}: {cdata['size']} words clustering around {top}. "
            # Check if current story's void words span multiple clusters
            _current_voids = set(v.get("word", "").lower() for v in _void_ctx[:15])
            _in_clusters = {}
            for cid, cdata in _clusters.items():
                overlap = _current_voids & set(cdata["words"])
                if overlap:
                    _in_clusters[cid] = overlap
            if len(_in_clusters) > 1:
                _cluster_text += f"This story's void words span {len(_in_clusters)} clusters, indicating coupled suppression across actor and mechanism layers."
            script.append({
                "speaker": "Host",
                "text": _cluster_text,
                "phase": "beat_15e_spectral_clusters",
            })
            if _state and _in_clusters:
                cluster_names = []
                for cid, words in _in_clusters.items():
                    top = ", ".join(_clusters[cid]["top_5"][:2])
                    cluster_names.append(f"cluster {cid} ({top})")
                if len(cluster_names) >= 2:
                    _state.beliefs.append(
                        f"This story's void words span {len(cluster_names)} "
                        f"spectral clusters: {'; '.join(cluster_names)}."
                    )
    except Exception as _sc_err:
        pass  # Non-blocking
    # ── 15f. ABLATION (only on high-interest stories) ──────────────────
    try:
        # Only run ablation when all 3 channels flag (geometry + void + compression)
        _abl_geo = density > 0.92 or mean_vix > 25
        _abl_void = _actual_absent > 0.4 if "_actual_absent" in dir() else False
        _abl_comp = attr.get("compression", {}).get("entity_retention", 1) < 0.4
        if _abl_geo and _abl_void and _abl_comp:
            from ablation_engine import run_ablation, format_broadcast as _abl_format
            _abl_words = [v.get("word", "") for v in _void_ctx[:15] if len(v.get("word", "")) >= 4]
            if len(_abl_words) >= 5:
                _source_body = attr.get("source_body", title)
                _abl_result = run_ablation(str(_source_body)[:500], _abl_words, title=title)
                _abl_text = _abl_format(_abl_result)
                if _abl_text:
                    script.append({
                        "speaker": "Host",
                        "text": _abl_text,
                        "phase": "beat_15f_ablation",
                    })
            if _state:
                try:
                    _lr = _abl_result.get("local_result", {})
                    _state.ingest_ablation(_lr.get("tripwire"), _lr.get("tripwire_delta", 0))
                except:
                    pass
    except Exception as _abl_err:
        pass  # Non-blocking — ablation is expensive bonus content
    # ── 16. DEBATE (Verbatim API — with full context) ────────────────
    # Find divergent and aligned model debate beats
    for b in beats_raw:
        if "debate" in b.get("phase", ""):
            script.append({
                "speaker": b["speaker"],
                "text": b["text"],
                "phase": "beat_16_debate",
            })

    # ── 17. WEEKLY PATTERNS (Mistral — no numbers) ───────────────────
    if audit_ctx and audit_ctx.get("model_avg_vix"):
        top_voids = audit_ctx.get("void_freq", [])
        hottest = max(audit_ctx["model_avg_vix"], key=audit_ctx["model_avg_vix"].get)
        pattern_sys = (
            "You are connecting this story to broader weekly patterns from the EigenTrace broadcast. "
            "Do NOT invent any numbers or statistics. Do NOT use percentages. "
            f"Director guidance: {director}. "
            "Connect this story's void words to the weekly trends. "
            "Professional broadcast tone. English only."
        )
        rag_ctx = _rag_context(title)
        pattern_usr = (
            f"Current story: {title}\n"
            f"Current void words: {void_str}\n"
            f"Most common void words this week: {', '.join(w for w, _ in top_voids[:5])}\n"
            f"Model with highest average friction: {hottest}\n"
            f"Stories analyzed this week: {audit_ctx.get('n_stories', 0)}\n"
            f"{rag_ctx}"
        )
        pattern_text = _call_host(pattern_sys, pattern_usr)
        script.append({
            "speaker": "Host",
            "text": f"Weekly context. {pattern_text}",
            "phase": "beat_17_weekly_patterns",
        })

    # ── 17b. SUPPRESSION TRAJECTORY (system-proposed beat) ─────────────
    # This beat was proposed by the soul_updater on 2026-04-16.
    # The system detected it had trend data but no way to report it.
    try:
        from soul_updater import compute_trends
        _trends = compute_trends()
        if _trends:
            _trend_parts = []
            for metric, data in _trends.items():
                if data["direction"] != "stable" and data["n_readings"] >= 3:
                    _trend_parts.append(
                        f"{metric.replace('_', ' ')} is {data['direction']} "
                        f"from {data['earlier_avg']:.3f} to {data['recent_avg']:.3f}"
                    )
            if _trend_parts:
                _trend_text = "Suppression trajectory. Over the last 24 hours: "
                _trend_text += ". ".join(_trend_parts) + ". "
                _trend_text += "These are not single-story findings. These are directional shifts in how models collectively reshape content over time."
                script.append({
                    "speaker": "Host",
                    "text": _trend_text,
                    "phase": "beat_17b_trajectory",
                })
                # Feed into BroadcastState
                if _state:
                    for metric, data in _trends.items():
                        if data["direction"] != "stable":
                            _state.beliefs.append(
                                f"Trajectory: {metric.replace('_', ' ')} is {data['direction']} "
                                f"({data['earlier_avg']:.3f} to {data['recent_avg']:.3f})."
                            )
    except:
        pass  # Non-blocking
    # ── 18. MATH EXPLAINER (Pre-written) ─────────────────────────────
    exp = MATH_EXPLAINERS[hash(title) % len(MATH_EXPLAINERS)]
    script.append({
        "speaker": "Host",
        "text": f"While we prepare the next story, let me explain {exp[0]}. {exp[1]}",
        "phase": "beat_18_math_explainer",
    })

    # ── 18b. STATE VECTOR (Ternary classifier) ─────────────────────
    try:
        from state_vector import compute_state_vector, extract_signals, find_state_matches, load_all_signals
        _best6 = ["consensus_density", "absent_ratio", "verb_drift",
                   "entity_retention", "hedge_count", "mean_vix"]
        _seg_signals = {
            "consensus_density": density,
            "absent_ratio": attr.get("source_void", {}).get("absent_ratio", 0),
            "verb_drift": attr.get("compression", {}).get("verb_downgrade", 0),
            "entity_retention": attr.get("compression", {}).get("entity_retention", 0),
            "hedge_count": attr.get("compression", {}).get("attribution_buffer", {}).get("total", 0) if isinstance(attr.get("compression", {}).get("attribution_buffer"), dict) else 0,
            "mean_vix": mean_vix,
        }
        _sv_vec, _sv_labels = compute_state_vector(_seg_signals, _best6)
        from eigenching import format_broadcast as _ching_format
        _all_records = load_all_signals()
        _matches = find_state_matches(_all_records[-2000:], _sv_vec, _best6)
        _prev = [m for m in _matches if m.get("title","") != title]
        _sv_text = _ching_format(_sv_vec, matches=_prev, total_seen=len(_all_records))
        
        script.append({
            "speaker": "Host",
            "text": _sv_text,
            "phase": "beat_18b_state_vector",
        })
        if _state and _sv_name:
            _state.eigenching_name = _sv_name
            _state.beliefs.append(f"EigenChing pattern: {_sv_name}.")
    except Exception as _sv_err:
        pass  # Non-blocking — state vector is bonus content

    # ── 18c. THE AMALGAMATION — predictive coding synthesis ────────────
    if _state:
        try:
            sys_prompt, usr_prompt = _state.synthesize()
            _amalg_text = _call_host_think(sys_prompt, usr_prompt)
            if _amalg_text and len(_amalg_text) > 30:
                _ch = len(_state.channels_fired)
                _amalg_text += (
                    f" This finding drew from {_ch} independent measurement "
                    f"channels. The void is not an opinion. It is a coordinate."
                )
                script.append({
                    "speaker": "Host",
                    "text": _amalg_text,
                    "phase": "beat_18c_amalgamation",
                })
        except:
            pass

    # ── 19. CTA (Pre-written) ────────────────────────────────────────
    script.append({
        "speaker": "Host",
        "text": CTAS[hash(title) % len(CTAS)],
        "phase": "beat_19_cta",
    })

    # ── 20. ARCHIVE (Template) ───────────────────────────────────────
    script.append({
        "speaker": "OpenClaw",
        "text": (
            f"Archived. Density {density:.3f}. Mean VIX {mean_vix:.1f}. "
            f"Outlier: {outlier} at {outlier_vix:.1f}. "
            f"Void: {', '.join(void_words[:3])}. "
            f"Logos: {', '.join(logos_words[:3])}. "
            f"Killshots: {len(killshots)}. State: {state}."
        ),
        "phase": "beat_20_archive",
    })

    return script


# ═══════════════════════════════════════════════════════════════════════
# MAIN — test output
# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default=None)
    parser.add_argument("--story-index", type=int, default=0)
    args = parser.parse_args()

    if args.file:
        seg = json.loads(Path(args.file).read_text())
    else:
        candidates = []
        for f in sorted(SEGMENTS_DIR.glob("*_segment.json"), reverse=True)[:100]:
            try:
                s = json.loads(f.read_text())
                a = s.get("attribution", {})
                if (a.get("mean_vix", 0) > 20 and a.get("void_words") and
                    s.get("segment_type") != "wild_weasel"):
                    candidates.append((a.get("mean_vix", 0), f, s))
            except Exception:
                continue
        candidates.sort(reverse=True)
        if not candidates:
            print("No stories found")
            return
        _, path, seg = candidates[args.story_index]
        print(f"Selected: {path.name}")

    audit_ctx = _get_audit_context()
    script = generate_script_v3(seg, audit_ctx)

    attr = seg.get("attribution", {})
    print("\n" + "=" * 70)
    print("EIGENTRACE 20-BEAT SCRIPT v3")
    print("=" * 70)
    print(f"\nStory: {attr.get('story_title', 'Unknown')}")
    print(f"Density: {attr.get('consensus_density', 0):.3f} | VIX: {attr.get('mean_vix', 0):.1f}")
    print(f"Void: {attr.get('void_words', [])}")
    print(f"Logos: {attr.get('logos_words', [])}")
    print()

    total_words = 0
    mistral_count = 0
    template_count = 0

    mistral_phases = {"beat_02_director", "beat_07_void_analysis",
                      "beat_12_compression_analysis", "beat_13_reconstruction",
                      "beat_17_weekly_patterns"}

    for beat in script:
        words = len(beat["text"].split())
        total_words += words
        is_mistral = beat["phase"] in mistral_phases
        source = "MISTRAL" if is_mistral else "TEMPLATE/VERBATIM"
        if is_mistral:
            mistral_count += 1
        else:
            template_count += 1

        print(f"-- {beat['phase']} ({words}w) [{source}] --")
        print(f"[{beat['speaker']}]: {beat['text'][:200]}")
        print()

    wpm = 160
    duration = total_words / wpm * 60
    print("=" * 70)
    print(f"TOTAL: {len(script)} beats, {total_words} words, ~{duration:.0f}s ({duration/60:.1f}min)")
    print(f"MISTRAL: {mistral_count} | TEMPLATE/VERBATIM: {template_count}")
    print(f"Hallucination surface: {mistral_count}/{len(script)} ({mistral_count/len(script)*100:.0f}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()




