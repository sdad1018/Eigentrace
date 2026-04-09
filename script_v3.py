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

def _rag_context(title, n=3):
    """Retrieve historical context from past broadcasts via ChromaDB."""
    try:
        from segment_rag import query, format_context
        hits = query(title, n_results=n)
        return format_context(hits, max_items=n)
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
            "options": {"temperature": 0.7, "num_predict": 500},
        }, timeout=120)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)
        return text
    except Exception as e:
        return f"[Mistral unavailable: {e}]"


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
                model_responses[speaker] = b["text"][:300]

    void_str = ", ".join(void_words[:5])
    logos_str = ", ".join(logos_words[:5]) if logos_words else "unavailable"

    script = []

    # ── 1. COLD OPEN (Template) ──────────────────────────────────────
    script.append({
        "speaker": "Host",
        "text": f"This is EigenTrace. {title}",
        "phase": "beat_01_cold_open",
    })

    # ── 2. DIRECTOR THESIS (Mistral) ─────────────────────────────────
    dir_sys = (
        "You are the Director of EigenTrace, a news analysis broadcast. " + _load_soul_calibration() + " "
        "Given raw data about a story, write exactly two sentences. "
        "First: the thesis, one sentence stating the core finding. "
        "Second: why the audience should care. "
        "Do NOT use any numbers. Be direct. Respond only in English."
    )
    dir_usr = (
        f"Story: {title}. State: {state}. "
        f"Void words: {void_str}. "
        f"Killshots: {len(killshots)} omitted claims. "
        f"Outlier model: {outlier}"
    )
    director = _call_host(dir_sys, dir_usr)
    script.append({
        "speaker": "Host",
        "text": director,
        "phase": "beat_02_director",
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
                clean = text[:600]
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
    _nav_junk = {"adventures","africa","america","announcement","asia","australia",
        "business","canada","climate","culture","education","entertainment","europe",
        "fashion","food","health","home","lifestyle","live","magazine","markets",
        "media","middle","money","news","opinion","photos","politics","science",
        "search","sport","sports","style","tech","technology","travel","tv","uk",
        "us","video","videos","weather","world","subscribe","newsletter","login",
        "sign","menu","share","comment","comments","follow","read","skip","cookie",
        "cookies","privacy","policy","terms","contact","about","advertise","more"}
    _raw_absent = _sv.get("absent_words", [])
    _absent_words = [w for w in _raw_absent if w.lower() not in _nav_junk][:15]
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
    if _raw_responses and _absent_words:
        _per_model_drops = []
        for _mname in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]:
            _mtext = _raw_responses.get(_mname, "").lower()
            if not _mtext:
                continue
            _dropped = [w for w in _absent_words[:8] if w.lower() not in _mtext]
            _kept = [w for w in _absent_words[:8] if w.lower() in _mtext]
            if _dropped:
                _per_model_drops.append(f"{_mname} dropped {', '.join(_dropped[:4])}")
        if _per_model_drops:
            script.append({
                "speaker": "Host",
                "text": "Per-model void comparison. " + ". ".join(_per_model_drops[:4]) + ".",
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
        "Explain in 2-3 sentences why these specific absent words matter "
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
        "In 2 sentences, explain what the language compression reveals about how "
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
        "Then write 2-3 grammatically correct sentences incorporating the void words "
        "into a coherent narrative. English only."
    )
    recon_usr = (
        f"Story: {title}\n"
        f"Void words to incorporate: {', '.join(void_words[:8])}\n"
        f"Logos concepts: {logos_str}\n"
        f"Null space claim: {ns_claims[0]['claim'] if ns_claims else 'none'}"
    )
    recon_text = _call_host(recon_sys, recon_usr)
    script.append({
        "speaker": "Host",
        "text": recon_text,
        "phase": "beat_13_reconstruction",
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
            omitters = ", ".join(ks.get("omitted_by", []))
            ks_text += f"The claim: {ks['claim']}. Salience: {ks['salience']:.2f}. Omitted by: {omitters}. "
        script.append({"speaker": "Host", "text": ks_text, "phase": "beat_15_killshots"})

    # ── 16. DEBATE (Verbatim API — with full context) ────────────────
    # Find divergent and aligned model debate beats
    for b in beats_raw:
        if "debate" in b.get("phase", ""):
            script.append({
                "speaker": b["speaker"],
                "text": b["text"][:300],
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
            "Write 2-3 sentences connecting this story's void words to the weekly trends. "
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

    # ── 18. MATH EXPLAINER (Pre-written) ─────────────────────────────
    exp = MATH_EXPLAINERS[hash(title) % len(MATH_EXPLAINERS)]
    script.append({
        "speaker": "Host",
        "text": f"While we prepare the next story, let me explain {exp[0]}. {exp[1]}",
        "phase": "beat_18_math_explainer",
    })

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
