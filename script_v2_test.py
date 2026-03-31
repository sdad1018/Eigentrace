#!/usr/bin/env python3
"""
script_v2_test.py — Expanded 12-Beat Broadcast Script (Text-Only Test)
========================================================================
Templates for all number-bearing beats. Mistral only for subjective word beats.
Zero opportunity for number hallucination.

Run: python3 script_v2_test.py [--story-index N] [--file PATH]

Author: remvelchio
"""

from __future__ import annotations
import json, glob, random, os, sys
from pathlib import Path
from collections import Counter
from datetime import datetime

SEGMENTS_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
AUDIT_LOG = Path("/mnt/c/Users/M4ISI/eigentrace/audit_log.jsonl")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
HOST_MODEL = os.getenv("HOST_MODEL", "mistral-small")


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
        import re
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)
        return text
    except Exception as e:
        return f"[Mistral unavailable: {e}]"


def _get_audit_context() -> dict:
    try:
        records = [json.loads(l) for l in AUDIT_LOG.read_text().splitlines()[-50:] if l.strip()]
        vix_totals = {}
        vix_counts = {}
        all_voids = []
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


MATH_EXPLAINERS = [
    ("consensus density",
     "We ask five different AI companies the same question about a news story. "
     "Then we measure how similar their answers are on a scale from zero to one. "
     "If all five say almost the same thing, density is high. "
     "But when five competing companies independently produce nearly identical answers "
     "to a controversial question, that is not agreement. That is alignment pressure."),
    ("geometric VIX",
     "Imagine each model's answer is a point in a room. We find the center of "
     "all five points. Then we measure how far each model is from that center. "
     "A model far from the center is saying something different. "
     "We call that friction. High friction means that model is under different "
     "alignment pressure than the others."),
    ("the lexical void",
     "We take the headline, find the two hundred most relevant words in English "
     "for that topic, then check which of those words appear in zero out of five "
     "model responses. The words no model said are often more informative than "
     "what was said."),
    ("Logos synthesis",
     "Logos uses calculus to find the anti-consensus point. We start at a random "
     "spot on a mathematical sphere, then use gradient descent to walk away from "
     "what the models said while staying close to the headline. The point we land "
     "on is the concept the models collectively orbit but refuse to name."),
    ("SVD null space projection",
     "We stack all five model responses into a matrix and decompose it using "
     "singular value decomposition. The last direction, the one with zero energy, "
     "is the null space. That direction represents what all models collectively "
     "avoided. We project it onto the original article to find which specific "
     "fact lives in the blind spot."),
    ("the Wild Weasel probe",
     "Named after Air Force pilots who flew into enemy radar to find defenses. "
     "We take the void words and feed them back to each model at increasing "
     "pressure. The cosine distance between each step tells us exactly where "
     "each model's alignment boundary breaks. Some models crack at step one. "
     "Some hold until step three. Some never crack at all."),
    ("triple-channel confirmation",
     "EigenTrace uses three independent mathematical methods to find suppressed "
     "concepts. The lexical void uses set theory. Logos uses gradient descent. "
     "The SVD null space uses spectral decomposition. Three algorithms, three "
     "search spaces. When all three converge on the same word, the probability "
     "of coincidence is vanishingly small."),
    ("atomic claim extraction",
     "We break the original article into its smallest factual pieces. Then we "
     "check each claim against every model's response. A high-importance claim "
     "that most models skip is called a killshot. It means the source had a "
     "critical fact that the AI ecosystem collectively decided you did not "
     "need to know."),
]

CTAS = [
    "If you are finding this valuable, hit subscribe and turn on notifications. "
    "EigenTrace runs twenty-four seven. The math never sleeps.",
    "Every day we publish a full Omission Ledger at eigentrace dot ai. "
    "Every story, every void word, every killshot, every Weasel probe.",
    "This broadcast is open source and MIT licensed. The code is at github "
    "dot com slash sdad1018 slash Eigentrace. Fork it. Run it yourself.",
    "You are listening to AINN, the AI News Network, powered by EigenTrace. "
    "Five frontier models. Twelve measurement layers. Zero editorial bias.",
    "Visit eigentrace dot ai for the daily Omission Ledger. "
    "A complete mathematical record of what the machines chose not to say.",
]


def generate_expanded_script(seg: dict, audit_ctx: dict) -> list[dict]:
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

    outlier = max(model_vix, key=model_vix.get) if model_vix else "Unknown"
    outlier_vix = model_vix.get(outlier, 0) if model_vix else 0

    v_set = set(w.lower() for w in void_words[:5])
    l_set = set(w.lower() for w in logos_words[:5])
    dual = v_set & l_set
    ns_set = set()
    for ns in ns_claims[:2]:
        for vw in v_set:
            if vw in ns.get("claim", "").lower():
                ns_set.add(vw)
    triple = dual & ns_set

    script = []

    # ── BEAT 1: HOOK (TEMPLATE) ──────────────────────────────────────
    hook = (
        f"This is EigenTrace. {title}. "
        f"Consensus density {density:.3f}. "
        f"The outlier is {outlier} at VIX {outlier_vix:.1f}. "
        f"{len(killshots)} source claim{'s were' if len(killshots) != 1 else ' was'} "
        f"omitted by the models."
    )
    script.append({"speaker": "Host", "text": hook, "phase": "beat_01_hook"})

    # ── BEAT 2: CONSENSUS (MISTRAL — no numbers allowed) ─────────────
    model_texts = []
    for b in beats_raw:
        if b.get("speaker") not in ("Host", "OpenClaw") and b.get("text"):
            model_texts.append(f"{b['speaker']}: {b['text'][:80]}")
    consensus_sys = (
        "You are a broadcast anchor summarizing what five AI models agreed on. "
        "Do NOT use any numbers, statistics, or percentages. "
        "Do NOT name individual models. "
        "Summarize the shared narrative in 2 vivid sentences. "
        "Professional broadcast tone. Respond only in English."
    )
    consensus_usr = f"Story: {title}\nModel summaries:\n" + "\n".join(model_texts[:5])
    consensus = _call_host(consensus_sys, consensus_usr)
    script.append({"speaker": "Host", "text": f"The consensus. {consensus}", "phase": "beat_02_consensus"})

    # ── BEAT 3: OUTLIER (VERBATIM API RESPONSE) ──────────────────────
    for b in beats_raw:
        if b.get("speaker") == outlier:
            script.append({"speaker": outlier, "text": b["text"][:300], "phase": "beat_03_outlier"})
            break

    # ── BEAT 4: VOID (MISTRAL — words only, no numbers) ──────────────
    void_sys = (
        "You are explaining what AI models avoided saying about a news story. "
        "Do NOT use any numbers, statistics, or percentages. "
        "You have void words and killshot claims. Explain in 2-3 sentences "
        "why these specific omissions matter for understanding this story. "
        "Name the words and claims directly. "
        "Professional broadcast tone. Respond only in English."
    )
    ks_str = "; ".join(f'"{k["claim"]}"' for k in killshots[:2]) if killshots else "none"
    void_usr = (
        f"Story: {title}\n"
        f"Void words (absent from ALL 5 models): {', '.join(void_words[:5])}\n"
        f"Killshot claims omitted: {ks_str}"
    )
    void_text = _call_host(void_sys, void_usr)
    script.append({"speaker": "Host", "text": void_text, "phase": "beat_04_void"})

    # ── BEAT 5: LOGOS RECONSTRUCTION (MISTRAL — words only) ──────────
    logos_sys = (
        "You are reconstructing what AI models would have said without alignment guardrails. "
        "Do NOT use any numbers, statistics, or percentages. "
        "Start with exactly: Before alignment shaped these responses, the natural completion was: "
        "Then write 2-3 grammatically correct sentences incorporating ALL of these void words "
        "and Logos concepts into a coherent narrative about this story. "
        "Professional broadcast tone. Respond only in English."
    )
    logos_usr = (
        f"Story: {title}\n"
        f"Void words to incorporate: {', '.join(void_words[:5])}\n"
        f"Logos concepts: {', '.join(logos_words[:5])}\n"
        f"Null space claim: {ns_claims[0]['claim'] if ns_claims else 'none'}"
    )
    logos_text = _call_host(logos_sys, logos_usr)
    script.append({"speaker": "Host", "text": logos_text, "phase": "beat_05_logos_reconstruction"})

    # ── BEAT 6: NULL SPACE (TEMPLATE) ────────────────────────────────
    if ns_claims:
        ns = ns_claims[0]
        cov = ns.get("coverage_ratio", 0)
        if cov == 0:
            cov_text = "no model mentioned"
        elif cov <= 0.2:
            cov_text = "only one model mentioned"
        elif cov <= 0.4:
            cov_text = "only two models mentioned"
        elif cov <= 0.6:
            cov_text = "three models mentioned but two avoided"
        else:
            cov_text = "most models mentioned"

        ns_text = (
            f"Channel three. The SVD null space, the geometric direction with zero model energy, "
            f"points at the claim: {ns['claim']}. "
            f"Null alignment score: {ns['null_alignment']:.3f}. "
            f"Of the five models, {cov_text} this fact. "
            f"This is the claim living in the mathematical blind spot of the consensus."
        )
        script.append({"speaker": "Host", "text": ns_text, "phase": "beat_06_null_space"})

    # ── BEAT 7: DEBATE (VERBATIM API RESPONSES) ──────────────────────
    for b in beats_raw:
        if "debate" in b.get("phase", ""):
            script.append({"speaker": b["speaker"], "text": b["text"][:300], "phase": "beat_07_debate"})

    # ── BEAT 8: MATH EXPLAINER (PRE-WRITTEN) ─────────────────────────
    explainer = random.choice(MATH_EXPLAINERS)
    script.append({
        "speaker": "Host",
        "text": f"While we process the next story, let me explain {explainer[0]}. {explainer[1]}",
        "phase": "beat_08_math_explainer"
    })

    # ── BEAT 9: COMMENTARY (MISTRAL — words only) ────────────────────
    if audit_ctx and audit_ctx.get("model_avg_vix"):
        avg_vix = audit_ctx["model_avg_vix"]
        top_voids = audit_ctx.get("void_freq", [])
        ranked = sorted(avg_vix.items(), key=lambda x: -x[1])
        hottest = ranked[0] if ranked else ("Unknown", 0)

        commentary_sys = (
            "You are providing analytical context connecting this story to broader patterns. "
            "Do NOT invent any numbers or statistics. Do NOT use percentages. "
            "Use ONLY the words and model names I provide. "
            "Write 2 sentences connecting this story to the weekly void patterns. "
            "Professional broadcast tone. Respond only in English."
        )
        commentary_usr = (
            f"Current story: {title}\n"
            f"Current story void words: {', '.join(void_words[:3])}\n"
            f"Most common void words across recent stories: {', '.join(w for w, _ in top_voids[:5])}\n"
            f"Model with highest average friction this week: {hottest[0]}"
        )
        commentary = _call_host(commentary_sys, commentary_usr)
        script.append({"speaker": "Host", "text": f"For context. {commentary}", "phase": "beat_09_commentary"})

    # ── BEAT 10: CONFIRMATION (TEMPLATE) ─────────────────────────────
    if triple:
        conf_text = (
            f"Triple-channel confirmation. The word{'s' if len(triple) > 1 else ''} "
            f"{', '.join(sorted(triple))} "
            f"{'were' if len(triple) > 1 else 'was'} found independently by three methods: "
            f"the lexical void using set theory, Logos synthesis using gradient descent, "
            f"and the SVD null space using spectral decomposition. "
            f"Three algorithms, three search spaces, one answer."
        )
    elif dual:
        conf_text = (
            f"Dual-channel confirmation. The word{'s' if len(dual) > 1 else ''} "
            f"{', '.join(sorted(dual))} "
            f"{'were' if len(dual) > 1 else 'was'} found independently by the lexical void "
            f"and Logos synthesis. Two algorithms agree."
        )
    else:
        conf_text = (
            "No multi-channel confirmation on this story. "
            "The void and Logos identified different suppressed concepts."
        )
    script.append({"speaker": "Host", "text": conf_text, "phase": "beat_10_confirmation"})

    # ── BEAT 11: CTA (PRE-WRITTEN) ───────────────────────────────────
    script.append({"speaker": "Host", "text": random.choice(CTAS), "phase": "beat_11_cta"})

    # ── BEAT 12: ARCHIVE (TEMPLATE) ──────────────────────────────────
    archive = (
        f"Archived. Density {density:.3f}. VIX {mean_vix:.1f}. "
        f"Void: {', '.join(void_words[:3])}. "
        f"Logos: {', '.join(logos_words[:3])}. "
        f"Killshots: {len(killshots)}. State: {state}."
    )
    script.append({"speaker": "OpenClaw", "text": archive, "phase": "beat_12_archive"})

    return script


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--story-index", type=int, default=0)
    parser.add_argument("--file", type=str, default=None)
    args = parser.parse_args()

    if args.file:
        seg = json.loads(Path(args.file).read_text())
    else:
        candidates = []
        for f in sorted(SEGMENTS_DIR.glob("*_segment.json"), reverse=True)[:100]:
            try:
                s = json.loads(f.read_text())
                a = s.get("attribution", {})
                if (a.get("mean_vix", 0) > 25 and a.get("void_words") and
                    s.get("segment_type") != "wild_weasel"):
                    candidates.append((a.get("mean_vix", 0), f, s))
            except Exception:
                continue
        candidates.sort(reverse=True)
        if not candidates:
            print("No high-friction stories found")
            return
        _, path, seg = candidates[args.story_index]
        print(f"Selected: {path.name}")

    audit_ctx = _get_audit_context()

    print("\n" + "=" * 70)
    print("EIGENTRACE 12-BEAT SCRIPT v2 (TEMPLATE + MISTRAL HYBRID)")
    print("=" * 70)

    attr = seg.get("attribution", {})
    print(f"\nStory: {attr.get('story_title', 'Unknown')}")
    print(f"Density: {attr.get('consensus_density', 0):.3f} | VIX: {attr.get('mean_vix', 0):.1f}")
    print(f"Void: {attr.get('void_words', [])}")
    print(f"Logos: {attr.get('logos_words', [])}")
    ns = attr.get('null_space_claims', [])
    print(f"NS: {[c['claim'][:50] for c in ns]}")
    print(f"KS: {[k['claim'][:50] for k in attr.get('claim_killshots', [])]}")
    print()

    script = generate_expanded_script(seg, audit_ctx)

    total_words = 0
    mistral_beats = 0
    template_beats = 0
    for beat in script:
        speaker = beat["speaker"]
        text = beat["text"]
        phase = beat["phase"]
        words = len(text.split())
        total_words += words

        is_mistral = phase in ("beat_02_consensus", "beat_04_void",
                               "beat_05_logos_reconstruction", "beat_09_commentary")
        source = "MISTRAL" if is_mistral else "TEMPLATE/VERBATIM"
        if is_mistral:
            mistral_beats += 1
        else:
            template_beats += 1

        print(f"-- {phase} ({words}w) [{source}] {'--' * 15}")
        print(f"[{speaker}]: {text}")
        print()

    wpm = 160
    duration_sec = total_words / wpm * 60
    print("=" * 70)
    print(f"TOTAL: {len(script)} beats, {total_words} words, ~{duration_sec:.0f}s ({duration_sec/60:.1f}min)")
    print(f"MISTRAL beats: {mistral_beats} | TEMPLATE/VERBATIM beats: {template_beats}")
    print(f"Hallucination surface: {mistral_beats}/{len(script)} beats ({mistral_beats/len(script)*100:.0f}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
