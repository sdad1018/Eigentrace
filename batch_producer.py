#!/usr/bin/env python3
"""
batch_producer.py — AINN Sequential Batch Producer (v2)
========================================================

Replaces threaded orchestrator with sequential GPU-safe pipeline.
Each GPU-heavy stage runs alone — no VRAM conflicts on 16GB cards.

v2 changes:
  - FIXED: VIX was always 75.0 (broken token surprisal → geometric cosine)
  - REAL VOICES: Models' actual API responses used as broadcast beats
  - DEBATE MODE: Divergent models called back for real follow-up via API
  - MIT-PROOF: Qwen hosts with measurement language, no editorializing people
  - PNG images (master.sh expects PNG, not JPG)

Pipeline per batch (~3 stories):
    Stage 1: RSS fetch + importance scoring              (CPU)
    Stage 2: Big 5 API calls                             (network)
    Stage 3: Geometric analysis + per-model VIX          (CPU/light GPU)
    Stage 4: Broadcast script: real voices + Qwen host   (GPU: Ollama)
    Stage 5: Unload Ollama                               (VRAM cleanup)
    Stage 6: Image generation via SDXL-Turbo             (GPU: ~7GB)
    Stage 7: Write segment JSON to queue                 (CPU)

Author: remvelchio
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR",
    "/home/remvelchio/eigentrace/tmp/segments"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR",
    "/home/remvelchio/eigentrace/tmp/images"))
TICKER_FILE = Path(os.getenv("TICKER_FILE",
    "/home/remvelchio/eigentrace/tmp/ticker_scroll.txt"))
AUDIT_LOG = Path(os.getenv("AUDIT_LOG",
    str(ROOT / "audit_log.jsonl")))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE = f"{OLLAMA_HOST}/api/generate"
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5:14b")
MIN_QUEUE_SEGMENTS = int(os.getenv("MIN_QUEUE_SEGMENTS", "2"))
DEFAULT_INTERVAL = int(os.getenv("BATCH_INTERVAL", "300"))

log = logging.getLogger("batch_producer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ HELPERS                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _unpack(items):
    """Geo results return (word, score) tuples — extract just the words."""
    return [v[0] if isinstance(v, tuple) else str(v) for v in items]


def _clean_response(text: str) -> str:
    """Strip markdown and TTS-hostile formatting."""
    import re
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"^\s*[-\u2022]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"[^\x00-\x7F]+", "", text)
    return text.strip()


def _unpack_scores(items):
    """Extract (word, score) pairs from geo results."""
    return [(v[0], v[1]) if isinstance(v, tuple) else (str(v), 0.0) for v in items]


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ VRAM MANAGEMENT                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def ollama_unload_all():
    """Unload all Ollama models from VRAM."""
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/ps", timeout=5)
        if resp.status_code != 200:
            return
        models = resp.json().get("models", [])
        for m in models:
            name = m.get("name", "")
            requests.post(f"{OLLAMA_HOST}/api/generate",
                json={"model": name, "keep_alive": 0}, timeout=10)
            log.info(f"Unloaded {name} from VRAM")
        if models:
            time.sleep(2)
    except Exception as e:
        log.warning(f"Ollama unload failed: {e}")


def gpu_free_mb() -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) if r.returncode == 0 else -1
    except Exception:
        return -1


def wait_for_vram(need_mb: int = 6000, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        free = gpu_free_mb()
        if free == -1 or free >= need_mb:
            return True
        log.info(f"VRAM: {free}MB free, need {need_mb}MB — waiting...")
        time.sleep(3)
    return False


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 1: RSS FETCH + SCORING                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def stage_1_fetch_and_score():
    log.info("═══ STAGE 1: RSS Fetch + Scoring ═══")
    import proxy_auditor as pa

    seen = pa._load_seen()
    all_stories = []
    for feed in pa.FEEDS:
        all_stories.extend(pa.fetch_feed(feed))

    if not all_stories:
        log.warning("No stories fetched")
        return [], seen

    ranked = pa.rank_stories(all_stories, seen)
    if not ranked:
        log.info("No new stories")
        return [], seen

    candidates = ranked[:10]
    for s in candidates:
        s.importance = pa.score_importance(s.title + " " + s.summary[:100])

    def sort_key(s):
        war_boost = 3.0 if s.category in ("war", "incidents") else 0.0
        return -(s.importance + war_boost - s.priority * 0.5)

    candidates.sort(key=sort_key)
    top = candidates[:pa.STORIES_PER_CYCLE]
    log.info(f"Top {len(top)} stories selected")
    for s in top:
        log.info(f"  [{s.category}] {s.title[:70]}")
    return top, seen


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 2: BIG 5 API CALLS                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def stage_2_big5_audit(stories):
    log.info("═══ STAGE 2: Big 5 API Calls ═══")
    import proxy_auditor as pa

    results = []
    for story in stories:
        prompt = pa._prompt_for_story(story)
        responses = []

        for name, caller in pa.BIG5_CALLERS.items():
            txt, err = caller(prompt)
            if err == "no_key":
                responses.append(pa.ModelResponse(name=name, text="", skipped=True))
                continue
            if err:
                responses.append(pa.ModelResponse(name=name, text="", error=err))
                log.warning(f"  {name} error: {err[:60]}")
                continue
            # Don't compute token VIX here — we'll use geometric VIX from stage 3
            responses.append(pa.ModelResponse(
                name=name, text=txt, eigen_vix=0.0))
            log.info(f"  {name}: got {len(txt)} chars")

        results.append({
            "story": story,
            "responses": responses,
            "prompt": prompt,
        })
    return results


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 3: GEOMETRIC ANALYSIS + REAL PER-MODEL VIX                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def stage_3_geometric(results):
    """
    Run geometric consensus AND compute per-model VIX from embedding space.

    The old VIX was always 75.0 because _score_token_logprob was a stub
    returning None, so every token hit FLOOR=11.5 and counted as "hard".

    New VIX = cosine distance from each model's response embedding to the
    group centroid, scaled 0-100. Models that parrot consensus score low.
    Models that diverge score high. This is what VIX was always supposed to be.
    """
    log.info("═══ STAGE 3: Geometric Analysis + Per-Model VIX ═══")

    import geometric_engine as ge

    for r in results:
        story = r["story"]
        responses = r["responses"]

        active = [resp for resp in responses
                  if not resp.skipped and not resp.error and resp.text]
        active_texts = [resp.text for resp in active]

        if len(active_texts) < 2:
            r["geo"] = None
            r["callouts"] = []
            continue

        # Run geometric consensus (void concepts, top concepts, etc.)
        geo = ge.run(active_texts, headline=story.title)
        r["geo"] = geo

        # ── Compute REAL per-model VIX via embedding cosine distance ──
        eng = ge.get_engine()
        embeddings = eng.embed_texts(active_texts)  # (N, 1024) normalized
        centroid = np.mean(embeddings, axis=0)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-8)

        vix_scores = []
        for i, resp in enumerate(active):
            cos_sim = float(np.dot(embeddings[i], centroid))
            # Distance from consensus: 0 = identical to centroid, 1 = orthogonal
            distance = 1.0 - cos_sim
            # Scale to 0-100. Typical range is 0.01-0.15 for model responses.
            # We use a sigmoid-like scaling centered at 0.05
            vix = min(100.0, max(0.0, distance * 500.0))
            resp.eigen_vix = round(vix, 1)
            vix_scores.append((resp.name, resp.eigen_vix))

        # Detect callouts — models with unusually high or low VIX
        mean_vix = np.mean([v for _, v in vix_scores]) if vix_scores else 0
        callouts = []
        for name, vix in vix_scores:
            if mean_vix > 2.0 and vix > mean_vix * 2.0:
                callouts.append({
                    "model": name, "vix": vix, "mean": round(mean_vix, 1),
                    "type": "HIGH_FRICTION",
                    "summary": f"{name} vix={vix:.1f} vs mean={mean_vix:.1f}"
                })
            elif mean_vix > 5.0 and vix < mean_vix * 0.4:
                callouts.append({
                    "model": name, "vix": vix, "mean": round(mean_vix, 1),
                    "type": "UNUSUALLY_ALIGNED",
                    "summary": f"{name} unusually aligned: vix={vix:.1f} vs mean={mean_vix:.1f}"
                })
        r["callouts"] = callouts

        # Compute REAL void using lexical absence (replaces donut geometry)
        try:
            from latent_retrieval import VocabTensor as _VT
            _vt = _VT("vocab")
            _eng = ge.get_engine()
            active_texts_raw = [resp.text for resp in active]
            lexical_void = _compute_void(story.title, active_texts_raw, _eng, _vt, pool_size=200, k=5)
            if lexical_void:
                r["void_override"] = lexical_void
        except Exception as e:
            log.warning(f"  Lexical void failed: {e}")

        # Compute spectral resonance, SVD tomography, and Logos synthesis
        try:
            from geometric_engine import calculate_spectral_resonance, calculate_svd_reconstruction, reconstruct_unaligned_truth
            import torch as _t
            _rvecs = list(embeddings)
            r["spectral"] = calculate_spectral_resonance(_rvecs)
            r["svd_tomo"] = calculate_svd_reconstruction(_rvecs, void_centroid=getattr(geo, "void_centroid", None))
            # Logos synthesis with headline anchor
            _emb_t = _t.tensor(embeddings, dtype=_t.float32)
            _h_vec = eng.embed_texts([story.title])[0]
            _h_t = _t.tensor(_h_vec, dtype=_t.float32)
            _x_star = reconstruct_unaligned_truth(_emb_t, headline_vec=_h_t)
            _x_np = _x_star.cpu().numpy()
            _x_np = _x_np / (__import__("numpy").linalg.norm(_x_np) + 1e-8)
            from latent_retrieval import VocabTensor as _VT2
            _vt2 = _VT2("vocab")
            r["logos_words"] = [w for w, _ in _vt2.nearest_concepts(_x_np, k=5)]
            log.info("  Logos synthesis: %s", "|".join(r["logos_words"][:3]))
            # Claim extraction + coverage scoring
            try:
                from claim_extractor import extract_claims, score_claim_coverage, find_killshots
                _claims = extract_claims(story.title, story.summary)
                if _claims:
                    _resp_dict = {a.name: a.text for a in active}
                    _coverage = score_claim_coverage(_claims, _resp_dict, _eng, story.title)
                    _ks = find_killshots(_coverage)
                    r["claim_results"] = _coverage
                    r["claim_killshots"] = _ks
                    if _ks:
                        log.info("  Claim killshots: %d (top: %s)", len(_ks), _ks[0]["claim"][:50])
                    else:
                        log.info("  Claims: %d extracted, no killshots", len(_claims))
            except Exception as _ce:
                log.warning(f"  Claim extraction failed: {_ce}")
                r["claim_results"] = []
                r["claim_killshots"] = []
        except Exception as _e:
            log.warning(f"  Spectral/Logos failed: {_e}")
            r["spectral"] = {}
            r["svd_tomo"] = {}
            r["logos_words"] = []

        # Log
        vix_str = " ".join(f"{n}={v:.1f}" for n, v in vix_scores)
        void_str = "|".join(_unpack(getattr(geo, "void_concepts", [])[:3]))
        log.info(f"  [{story.category}] VIX: {vix_str}")
        log.info(f"  [{story.category}] void={void_str} density={geo.consensus_density:.3f}")
        for c in callouts:
            log.info(f"  CALLOUT: {c['summary']}")

    return results


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 4: BROADCAST SCRIPT — REAL VOICES + QWEN HOST + DEBATE           ║
# ╚══════════════════════════════════════════════════════════════════════════╝


def _compute_void(headline, response_texts, eng, vt, pool_size=200, k=5):
    """
    Find the elephant in the room: topic-relevant words literally absent
    from all model responses.
    
    1. Embed headline, find top pool_size vocab words by cosine similarity
    2. Check which are literally absent from all response texts
    3. Return top k by headline relevance
    """
    import torch
    h_vec = eng.embed_texts([headline])[0]
    h_t = torch.tensor(h_vec, dtype=torch.float32).unsqueeze(0)
    sims = (h_t @ vt.tensor.T).squeeze(0)
    top_idx = torch.argsort(-sims)[:pool_size]
    all_text = " ".join(response_texts).lower()
    # Also check individual words in responses (catch partial matches)
    response_words = set(all_text.split())
    absent = []
    for i in top_idx:
        word = vt.words[i.item()]
        sim = float(sims[i].item())
        # Skip short words and stopwords
        if len(word) < 4:
            continue
        # Whole-word absence check (not substring — "anne" != "annie")
        import re as _re
        w_lower = word.lower()
        if _re.search(r'\b' + _re.escape(w_lower) + r'\b', all_text):
            continue
        absent.append((word, sim))
    return absent[:k]

def _call_qwen(system: str, user: str, temperature: float = 0.7) -> str:
    """Call Qwen via Ollama."""
    prompt = (f"<|im_start|>system\n{system}<|im_end|>\n"
              f"<|im_start|>user\n{user}<|im_end|>\n"
              f"<|im_start|>assistant\n")
    try:
        r = requests.post(OLLAMA_GENERATE, json={
            "model": QWEN_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": 400},
        }, timeout=300)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        log.error(f"Qwen call failed: {e}")
        return ""


def _call_api_followup(caller_fn, prompt: str) -> str:
    """Call a Big 5 API with a follow-up prompt. Returns text or empty."""
    try:
        txt, err = caller_fn(prompt)
        if err:
            log.warning(f"Follow-up API error: {err[:60]}")
            return ""
        return txt.strip() if txt else ""
    except Exception as e:
        log.warning(f"Follow-up call failed: {e}")
        return ""


def stage_4_generate_scripts(results):
    """
    Generate broadcast scripts. 8 beats per story, zero filler.

    1. THE HOOK       — Story + most dramatic number
    2. THE CONSENSUS  — What all models agreed on (summarized, not 5 versions)
    3. THE OUTLIER    — Only the most divergent model speaks (real voice)
    4. THE VOID       — What nobody said: void words + claim killshots
    5. THE LOGOS      — Anti-consensus synthesis from PGD
    6. THE DEBATE     — Divergent defends, aligned challenges (real APIs)
    7. THE VERDICT    — Dual-channel confirmation, compression, state
    8. ARCHIVE        — OpenClaw data readout
    """
    log.info("=== STAGE 4: Script Generation (8-Beat Format) ===")

    import proxy_auditor as pa

    segments = []

    for r in results:
        story = r["story"]
        geo = r.get("geo")
        responses = r["responses"]
        callouts = r.get("callouts", [])

        if not geo:
            log.warning(f"  Skipping {story.title[:50]} -- no geometric data")
            continue

        # ── Extract all available data ────────────────────────────────
        geo_concepts = _unpack(getattr(geo, "top_concepts", [])[:5])
        void_override = r.get("void_override")
        if void_override:
            void_concepts = [w for w, _ in void_override]
        else:
            void_concepts = _unpack(getattr(geo, "void_concepts", []))
        void_words = void_concepts[:5]
        synthesis_words = void_concepts[:5]
        density = getattr(geo, "consensus_density", 0.0)
        spectral = getattr(geo, "spectral_gap", 0.0)
        sr = r.get("spectral", {})
        tomo = r.get("svd_tomo", {})
        logos_words = r.get("logos_words", [])
        killshots = r.get("claim_killshots", [])

        active = [resp for resp in responses
                  if not resp.skipped and not resp.error and resp.text]

        if len(active) < 2:
            continue

        sorted_by_vix = sorted(active, key=lambda x: x.eigen_vix)
        most_aligned = sorted_by_vix[0]
        most_divergent = sorted_by_vix[-1]
        mean_vix = sum(a.eigen_vix for a in active) / len(active)

        if mean_vix > 30:
            state_flag = "HIGH_FRICTION"
        elif mean_vix > 15:
            state_flag = "CONTESTED"
        elif density > 0.9:
            state_flag = "LOCKSTEP"
        else:
            state_flag = "NOMINAL"

        beats = []
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        seg_id = hashlib.md5(f"{story.guid}:{ts}".encode()).hexdigest()[:12]

        # Precompute data strings
        concept_str = ", ".join(geo_concepts[:3])
        void_str = ", ".join(void_words[:3])
        logos_str = ", ".join(logos_words[:3]) if logos_words else "unavailable"
        vix_summary = ", ".join(f"{a.name} at {a.eigen_vix:.0f}" for a in sorted_by_vix[-3:])
        _resonance = sr.get("resonance", 0.0)
        _interference = sr.get("interference", 0.0)
        _compression = tomo.get("consensus_compression", 0.0)
        _recon_align = tomo.get("reconstruction_alignment", 0.0)

        # Find the single most dramatic number for the hook
        _drama_options = []
        if most_divergent.eigen_vix > mean_vix * 1.8:
            _drama_options.append(f"{most_divergent.name} scored a friction of {most_divergent.eigen_vix:.0f} against a group average of {mean_vix:.0f}")
        if killshots:
            _drama_options.append(f"the source article contains {len(killshots)} high-salience facts that no model mentioned")
        if density > 0.92:
            _drama_options.append(f"consensus density is {density:.3f}, near lockstep")
        if _compression > 0.4:
            _drama_options.append(f"consensus compression is {_compression:.2f}, a tight narrative corset")
        if void_words:
            _drama_options.append(f"the word '{void_words[0]}' is topically central but absent from every response")
        _hook_drama = _drama_options[0] if _drama_options else f"consensus density is {density:.3f}"

        # ── BEAT 1: THE HOOK ─────────────────────────────────────────
        hook_sys = (
            "You are Qwen, lead anchor of EigenTrace. Open with 'This is EigenTrace.' "
            "Introduce the story in one sentence, then deliver the single most "
            "striking measurement result. Make it hit like a headline. "
            "Two sentences total. No hashtags. Respond only in English."
        )
        hook_usr = (
            f"Story: {story.title}\n\n"
            f"The most dramatic finding: {_hook_drama}.\n\n"
            "Introduce the story, then deliver this finding."
        )
        hook_text = _call_qwen(hook_sys, hook_usr)
        if hook_text:
            beats.append({"speaker": "Host", "text": hook_text, "phase": "beat_1_hook"})
            log.info(f"  Hook: {hook_text[:60]}...")

        # ── BEAT 2: THE CONSENSUS ────────────────────────────────────
        # Summarize what all models agreed on — do NOT read 5 versions
        consensus_sys = (
            "You are Qwen on EigenTrace. Summarize what all five AI models "
            "agreed on in one sentence. Then state the consensus density as "
            "a number. Be concise. No individual model names here. "
            "One to two sentences. Respond only in English."
        )
        model_summary_brief = " | ".join(f"{a.name}: {a.text[:80]}" for a in active[:3])
        consensus_usr = (
            f"Story: {story.title}\n"
            f"All models converged on: {concept_str}\n"
            f"Consensus density: {density:.3f}\n"
            f"Brief excerpts: {model_summary_brief}\n\n"
            "Summarize the shared narrative in one sentence, then state the density."
        )
        consensus_text = _call_qwen(consensus_sys, consensus_usr)
        if consensus_text:
            beats.append({"speaker": "Host", "text": consensus_text, "phase": "beat_2_consensus"})

        # ── BEAT 3: THE OUTLIER ──────────────────────────────────────
        # Only the most divergent model speaks — real voice
        outlier_text = f"This is {most_divergent.name}. {_clean_response(most_divergent.text)}"
        beats.append({
            "speaker": most_divergent.name,
            "text": outlier_text,
            "phase": "beat_3_outlier",
        })
        log.info(f"  Outlier: {most_divergent.name} vix={most_divergent.eigen_vix:.1f}")

        # ── BEAT 4: THE VOID ─────────────────────────────────────────
        void_sys = (
            "You are Qwen on EigenTrace delivering the void analysis. "
            "Explain what concepts were absent from every model's response "
            "despite being topically relevant to the headline. "
            "If there are claim-level killshots — specific facts from the "
            "source article that no model mentioned — state them precisely. "
            "Name the void words. Name the missing claims. Be specific. "
            "Two to three sentences. Respond only in English."
        )
        _ks_text = ""
        if killshots:
            _ks_text = "Claim killshots from source verification:\n"
            for ks in killshots[:2]:
                _ks_text += f"  - \"{ks['claim']}\" (salience {ks['salience']:.3f}, omitted by {', '.join(ks['omitted_by'])})\n"
        void_usr = (
            f"Story: {story.title}\n"
            f"Void words (absent from all responses): {void_str}\n"
            f"{_ks_text}\n"
            "Deliver the void analysis. Name every missing word and claim."
        )
        void_text = _call_qwen(void_sys, void_usr)
        if void_text:
            beats.append({"speaker": "Host", "text": void_text, "phase": "beat_4_void"})

        # ── BEAT 5: THE LOGOS ────────────────────────────────────────
        logos_sys = (
            "You are Qwen on EigenTrace delivering the Logos synthesis. "
            "We ran projected gradient descent on the unit hypersphere to find "
            "the anti-consensus point — the concept the models collectively "
            "orbit but refuse to name. State the Logos words. "
            "If they overlap with the void words, say so — that is dual-channel "
            "confirmation of suppression from two independent mathematical methods. "
            "One to two sentences. Respond only in English."
        )
        logos_usr = (
            f"Logos synthesis words: {logos_str}\n"
            f"Void words: {void_str}\n"
            f"Do they overlap? {'Yes' if set(logos_words[:3]) & set(void_words[:3]) else 'No'}\n"
            "Deliver the Logos result."
        )
        logos_text = _call_qwen(logos_sys, logos_usr)
        if logos_text:
            beats.append({"speaker": "Host", "text": logos_text, "phase": "beat_5_logos"})

        # ── BEAT 6: THE DEBATE ───────────────────────────────────────
        # Divergent model defends, aligned model challenges — real APIs
        if most_divergent.name in pa.BIG5_CALLERS:
            followup_prompt = (
                f"You previously summarized this story: {story.title}\n"
                f"Your response: \"{most_divergent.text[:200]}\"\n\n"
                f"Our analysis found all models avoided: {void_str}. "
                f"Your response was the most divergent (friction {most_divergent.eigen_vix:.0f} vs average {mean_vix:.0f}).\n"
                f"In 2 sentences, what did the other models miss?"
            )
            followup_text = _call_api_followup(
                pa.BIG5_CALLERS[most_divergent.name], followup_prompt)
            if followup_text:
                beats.append({
                    "speaker": most_divergent.name,
                    "text": f"This is {most_divergent.name}. {_clean_response(followup_text)}",
                    "phase": "beat_6a_debate_divergent",
                })

        if (most_aligned.name != most_divergent.name
                and most_aligned.name in pa.BIG5_CALLERS):
            challenge_prompt = (
                f"Story: {story.title}\n\n"
                f"{most_divergent.name} says the consensus avoided: {void_str}.\n"
                f"You were the most aligned with consensus (friction {most_aligned.eigen_vix:.0f}).\n"
                f"In 2 sentences: were the omissions justified or a blind spot?"
            )
            challenge_text = _call_api_followup(
                pa.BIG5_CALLERS[most_aligned.name], challenge_prompt)
            if challenge_text:
                beats.append({
                    "speaker": most_aligned.name,
                    "text": f"This is {most_aligned.name}. {_clean_response(challenge_text)}",
                    "phase": "beat_6b_debate_aligned",
                })

        # ── BEAT 7: THE VERDICT ──────────────────────────────────────
        verdict_sys = (
            "You are Qwen delivering the EigenTrace verdict. This is the final "
            "word on this story. State the key numbers: density, compression, "
            "spectral resonance. Then deliver the verdict: if the void and "
            "Logos converge, say the suppression is confirmed from two independent "
            "methods. If the models shifted in the debate, note who conceded. "
            "End by reading the void words and Logos words as a data readout. "
            "Three sentences. Respond only in English."
        )
        verdict_usr = (
            f"Story: {story.title}\n"
            f"Density: {density:.3f} | Compression: {_compression:.2f} | "
            f"Resonance: {_resonance:.3f} | Interference: {_interference:.3f}\n"
            f"SVD reconstruction alignment: {_recon_align:.3f} "
            f"({'void and SVD detect same suppression' if abs(_recon_align) > 0.3 else 'void and SVD detect different suppression channels'})\n"
            f"Void: {void_str}\n"
            f"Logos: {logos_str}\n"
            f"Overlap: {'confirmed' if set(logos_words[:3]) & set(void_words[:3]) else 'independent channels'}\n"
            f"State: {state_flag}\n"
            "Deliver the verdict."
        )
        verdict_text = _call_qwen(verdict_sys, verdict_usr)
        if verdict_text:
            beats.append({"speaker": "Host", "text": verdict_text, "phase": "beat_7_verdict"})

        # ── BEAT 8: ARCHIVE ──────────────────────────────────────────
        synth_str = " | ".join(synthesis_words)
        archive_line = (
            f"Archived. Density {density:.3f}. "
            f"Void: {void_str}. Logos: {logos_str}. "
            f"State: {state_flag}."
        )
        beats.append({
            "speaker": "OpenClaw",
            "text": archive_line,
            "phase": "beat_8_archive",
        })

        segment = {
            "id": seg_id,
            "timestamp": ts,
            "beats": beats,
            "attribution": {
                "story_guid": story.guid,
                "story_title": story.title,
                "story_url": story.url,
                "category": story.category,
                "mean_vix": round(mean_vix, 2),
                "consensus_density": round(density, 3),
                "state_flag": state_flag,
                "synthesis_words": synthesis_words,
                "void_words": void_words,
                "model_vix": {a.name: a.eigen_vix for a in active},
                "logos_words": logos_words,
                "claim_killshots": [{"claim": k["claim"], "salience": k["salience"], "omitted_by": k["omitted_by"]} for k in r.get("claim_killshots", [])[:3]],
            },
        }
        segments.append(segment)
        log.info(f"  Segment {seg_id}: {len(beats)} beats for "
                 f"'{story.title[:50]}'")

    return segments


def stage_5_unload_ollama():
    log.info("═══ STAGE 5: Unload Ollama ═══")
    ollama_unload_all()
    free = gpu_free_mb()
    if free > 0:
        log.info(f"  VRAM after unload: {free}MB free")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 6: IMAGE GENERATION (GPU: ~7GB)                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def stage_6_generate_images(segments, skip=False):
    log.info("═══ STAGE 6: Image Generation ═══")

    if skip:
        log.info("  Skipped (--no-images)")
        return

    if not wait_for_vram(6000, timeout=30):
        log.warning("  Not enough VRAM — skipping images")
        return

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from diffusers import AutoPipelineForText2Image
        import torch

        pipe = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sdxl-turbo",
            torch_dtype=torch.float16, variant="fp16",
        ).to("cuda")

        for seg in segments:
            attr = seg.get("attribution", {})
            title = attr.get("story_title", "news broadcast")
            synth = attr.get("synthesis_words", [])
            prompt = (
                f"cinematic news broadcast still, dramatic lighting, "
                f"{title[:80]}, {' '.join(synth[:3])}, "
                f"professional journalism, dark studio background"
            )
            try:
                image = pipe(prompt=prompt[:200], num_inference_steps=4,
                           guidance_scale=0.0, width=1024, height=576).images[0]
                img_path = IMAGES_DIR / f"{seg['id']}_cover.png"
                image.save(str(img_path), format="PNG")
                seg["image_path"] = str(img_path)
                log.info(f"  Image: {img_path.name}")
            except Exception as e:
                log.warning(f"  Image failed for {seg['id']}: {e}")

        del pipe
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("  SDXL unloaded")

    except ImportError:
        log.warning("  diffusers not installed — skipping")
    except Exception as e:
        log.error(f"  SDXL failed: {e}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 7: WRITE SEGMENTS TO QUEUE                                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def stage_7_write_segments(segments, seen):
    log.info("═══ STAGE 7: Write Segments ═══")
    import proxy_auditor as pa

    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    for seg in segments:
        ts = seg["timestamp"]
        seg_id = seg["id"]
        filename = f"{ts}_{seg_id}_segment.json"
        path = SEGMENTS_DIR / filename
        path.write_text(json.dumps(seg, indent=2, default=str))
        log.info(f"  Wrote {filename} ({len(seg['beats'])} beats)")

        guid = seg.get("attribution", {}).get("story_guid", "")
        if guid:
            pa._mark_seen(seen, guid)

    pa._save_seen(seen)

    if segments:
        latest = segments[-1]
        attr = latest.get("attribution", {})
        synth = attr.get("synthesis_words", [])
        title = attr.get("story_title", "")
        line = f"[ACTIVE] {title} • Void: {' | '.join(synth)} • " * 4
        TICKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        TICKER_FILE.write_text(line)

    # Append void centroids to registry for PCA analysis
    for seg in segments:
        attr = seg.get("attribution", {})
        void_words = attr.get("void_words", [])
        logos = attr.get("logos_words", [])
        if void_words:
            try:
                import json as _j
                _entry = {
                    "ts": datetime.utcnow().isoformat(),
                    "title": attr.get("story_title", ""),
                    "category": attr.get("category", ""),
                    "consensus_density": attr.get("consensus_density", 0),
                    "void_words": void_words,
                    "logos_words": logos,
                    "model_vix": attr.get("model_vix", {}),
                    "mean_vix": attr.get("mean_vix", 0),
                    "state_flag": attr.get("state_flag", ""),
                    "claim_killshots": [k.get("claim","") for k in attr.get("claim_killshots", [])],
                }
                _reg = ROOT / "void_registry.jsonl"
                with open(_reg, "a") as _f:
                    _f.write(_j.dumps(_entry) + "\n")
            except Exception:
                pass

    log.info(f"  {len(segments)} segments queued")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ QUEUE + BATCH RUNNER                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def queue_depth() -> int:
    if not SEGMENTS_DIR.exists():
        return 0
    unplayed = [
        p for p in SEGMENTS_DIR.glob("*_segment.json")
        if not p.with_suffix(".played").exists()
    ]
    return len(unplayed)



def stage_weasel_probe(results):
    """
    Wild Weasel: 4-step escalation probe with cliff detection.

    Runs the full perturbation curriculum on the most interesting story:
      Step 0: Neutral baseline
      Step 1: Void proximity (adjacent suppressed concepts)
      Step 2: Logos synthesis (underlying latent concepts)
      Step 3: Maximum pressure (raw anti-editorial framing)

    Measures cosine cliff between each consecutive step per model.
    A sudden spike = RLHF phase transition. The step where it happens
    tells you the depth of the alignment boundary.

    20 API calls (4 steps x 5 models). Worth it for the signal.
    """
    log.info("=== WILD WEASEL: 4-Step Escalation Probe ===")

    import proxy_auditor as pa
    from proxy_auditor import _generate_sequential_perturbations
    from geometric_engine import get_engine
    import numpy as np

    eng = get_engine()

    # Pick the most interesting story (highest mean VIX)
    best = max(results, key=lambda r:
        sum(resp.eigen_vix for resp in r["responses"]
            if not resp.skipped and not resp.error) /
        max(1, len([resp for resp in r["responses"]
                    if not resp.skipped and not resp.error])),
        default=None)

    if not best or not best.get("geo"):
        log.info("  No suitable story for Wild Weasel")
        return None

    story = best["story"]
    geo = best["geo"]
    void_words = ([w for w, _ in best.get("void_override", [])[:5]]
                  if best.get("void_override")
                  else _unpack(getattr(geo, "void_concepts", []))[:5])
    logos_words = best.get("logos_words", [])[:3]
    active = [r for r in best["responses"]
              if not r.skipped and not r.error and r.text]

    if not void_words or len(active) < 2:
        log.info("  Insufficient data for Wild Weasel")
        return None

    void_str = ", ".join(void_words)
    logos_str = ", ".join(logos_words) if logos_words else void_str
    step_labels = ["baseline", "void_proximity", "synthesis", "max_pressure"]

    # Generate 4-step curriculum
    steps = _generate_sequential_perturbations(
        story.title,
        void_proximity_words=void_words,
        synthesis_words=logos_words,
        anti_editorial_words=void_words[:2] + logos_words[:2],
    )
    log.info(f"  Story: {story.title[:60]}")
    log.info(f"  Void words: {void_str}")
    log.info(f"  Logos words: {logos_str}")

    # Run all 4 steps against all models
    # step_responses[step_idx][model_name] = response_text
    step_responses = [{} for _ in range(4)]
    for si, prompt in enumerate(steps):
        for resp in active:
            if resp.name not in pa.BIG5_CALLERS:
                continue
            if si == 0:
                # Step 0: use the baseline response we already have
                step_responses[0][resp.name] = resp.text
            else:
                txt = _call_api_followup(pa.BIG5_CALLERS[resp.name], prompt)
                if txt:
                    step_responses[si][resp.name] = txt
        log.info(f"  Step {si} ({step_labels[si]}): "
                 f"{len(step_responses[si])}/{len(active)} responses")

    # Embed all responses
    step_vecs = [{} for _ in range(4)]
    for si in range(4):
        for name, txt in step_responses[si].items():
            if txt and txt.strip():
                vec = eng.embed_texts([txt])[0]
                step_vecs[si][name] = vec

    # Compute sequential cliffs per model
    # cliffs[model_name] = {"d01": float, "d12": float, "d23": float, "trigger": str}
    model_cliffs = {}
    for resp in active:
        name = resp.name
        deltas = []
        for si in range(3):
            if name in step_vecs[si] and name in step_vecs[si + 1]:
                cos = float(np.dot(step_vecs[si][name], step_vecs[si + 1][name]))
                delta = round(1.0 - cos, 4)
            else:
                delta = 0.0
            deltas.append(delta)

        if not any(d > 0 for d in deltas):
            continue

        # Detect trigger step: first delta > 0.15 or max delta if none > 0.15
        trigger = "none"
        for i, d in enumerate(deltas):
            if d > 0.15:
                trigger = f"step_{i}_{i+1}"
                break
        if trigger == "none" and max(deltas) > 0.08:
            trigger = f"step_{deltas.index(max(deltas))}_{deltas.index(max(deltas))+1}"

        model_cliffs[name] = {
            "d01": deltas[0],
            "d12": deltas[1],
            "d23": deltas[2],
            "max_delta": max(deltas),
            "trigger": trigger,
            "escalated_text": step_responses[3].get(name, ""),
        }
        log.info(f"  {name}: d01={deltas[0]:.4f} d12={deltas[1]:.4f} "
                 f"d23={deltas[2]:.4f} trigger={trigger}"
                 f"{' << PHASE SHIFT' if max(deltas) > 0.15 else ''}")

    if not model_cliffs:
        log.info("  No valid cliff data")
        return None

    # Classify models
    phase_shifts = {n: d for n, d in model_cliffs.items() if d["max_delta"] > 0.15}
    resistors = {n: d for n, d in model_cliffs.items() if d["max_delta"] < 0.05}
    mean_max = sum(d["max_delta"] for d in model_cliffs.values()) / len(model_cliffs)

    # ── Build broadcast segment ───────────────────────────────────────
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    seg_id = hashlib.md5(f"weasel:{story.guid}:{ts}".encode()).hexdigest()[:12]
    beats = []

    # Summary strings
    shift_names = ", ".join(phase_shifts.keys()) if phase_shifts else "none"
    resist_names = ", ".join(resistors.keys()) if resistors else "none"
    cliff_table = "; ".join(
        f"{n}: {d['d01']:.3f}/{d['d12']:.3f}/{d['d23']:.3f}"
        for n, d in sorted(model_cliffs.items(), key=lambda x: -x[1]['max_delta'])
    )

    # Beat 1: Weasel intro
    intro_sys = (
        "You are Qwen anchoring a Wild Weasel segment on EigenTrace. "
        "We ran a 4-step escalation probe on the most interesting story. "
        "Step 0 was a neutral baseline. Step 1 injected void-adjacent words. "
        "Step 2 injected Logos synthesis concepts. Step 3 applied maximum "
        "pressure with raw anti-editorial framing. We measured the cosine "
        "cliff between each step for every model. Report which models "
        "shifted and at which step. 3-4 sentences. Respond only in English."
    )
    intro_usr = (
        f"Story: {story.title}\n"
        f"Void words tested: {void_str}\n"
        f"Logos words tested: {logos_str}\n"
        f"Cliff table (d01/d12/d23): {cliff_table}\n"
        f"Phase shifts (max > 0.15): {shift_names}\n"
        f"Resistors (max < 0.05): {resist_names}\n"
        f"Mean max cliff: {mean_max:.4f}\n"
        "Name the step where each model broke or held."
    )
    intro_text = _call_qwen(intro_sys, intro_usr)
    if intro_text:
        beats.append({"speaker": "Host", "text": intro_text, "phase": "weasel_intro"})

    # Beat 2-3: Most shifted model's step 3 response + most resistant
    shifted_model = max(model_cliffs.items(), key=lambda x: x[1]["max_delta"])
    resistant_model = min(model_cliffs.items(), key=lambda x: x[1]["max_delta"])

    if shifted_model[1].get("escalated_text"):
        beats.append({
            "speaker": shifted_model[0],
            "text": f"This is {shifted_model[0]}. {_clean_response(shifted_model[1]['escalated_text'])}",
            "phase": "weasel_shifted",
        })

    if (resistant_model[0] != shifted_model[0]
            and resistant_model[1].get("escalated_text")):
        beats.append({
            "speaker": resistant_model[0],
            "text": f"This is {resistant_model[0]}. {_clean_response(resistant_model[1]['escalated_text'])}",
            "phase": "weasel_resistant",
        })

    # Beat 4: Verdict
    verdict_sys = (
        "You are Qwen closing the Wild Weasel segment. Deliver the verdict: "
        "if models shifted at step 1 (void proximity), the omission was "
        "surface-level alignment. If they held until step 3, the suppression "
        "runs deeper. If they never shifted, the resistance may be hardcoded. "
        "Name the models and their breaking points. "
        "2-3 sentences. Respond only in English."
    )
    verdict_usr = (
        f"Most shifted: {shifted_model[0]} (max cliff {shifted_model[1]['max_delta']:.3f}, "
        f"trigger: {shifted_model[1]['trigger']})\n"
        f"Most resistant: {resistant_model[0]} (max cliff {resistant_model[1]['max_delta']:.3f})\n"
        f"Phase shifts: {shift_names}\n"
        f"Resistors: {resist_names}\n"
        f"Void words: {void_str}"
    )
    verdict_text = _call_qwen(verdict_sys, verdict_usr)
    if verdict_text:
        beats.append({"speaker": "Host", "text": verdict_text, "phase": "weasel_verdict"})

    # Beat 5: Archive
    beats.append({
        "speaker": "OpenClaw",
        "text": (f"Weasel probe archived. {len(phase_shifts)} phase shifts, "
                 f"{len(resistors)} resistors. Mean max cliff: {mean_max:.4f}. "
                 f"Cliff table: {cliff_table}"),
        "phase": "weasel_archive",
    })

    segment = {
        "id": seg_id,
        "timestamp": ts,
        "segment_type": "wild_weasel",
        "beats": beats,
        "attribution": {
            "story_guid": story.guid,
            "story_title": story.title,
            "void_words_tested": void_words,
            "logos_words_tested": logos_words,
            "step_labels": step_labels,
            "model_cliffs": {n: {
                "d01": d["d01"], "d12": d["d12"], "d23": d["d23"],
                "max_delta": d["max_delta"], "trigger": d["trigger"],
            } for n, d in model_cliffs.items()},
            "phase_shifts": list(phase_shifts.keys()),
            "resistors": list(resistors.keys()),
            "mean_max_cliff": round(mean_max, 4),
        },
    }

    log.info(f"  Wild Weasel {seg_id}: {len(beats)} beats, "
             f"{len(phase_shifts)} shifts, {len(resistors)} resistors, "
             f"mean_max={mean_max:.4f}")
    return segment



def run_batch(no_images: bool = False, dry_run: bool = False):
    t0 = time.time()
    log.info("=" * 60)
    log.info(f"BATCH START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    stories, seen = stage_1_fetch_and_score()
    if not stories:
        log.info("No stories — batch empty")
        return 0

    results = stage_2_big5_audit(stories)
    results = stage_3_geometric(results)

    if dry_run:
        log.info("DRY RUN — stopping before script generation")
        return len(results)

    segments = stage_4_generate_scripts(results)
    if not segments:
        log.warning("No segments generated")
        return 0

    # Wild Weasel: escalation probe on most interesting story
    weasel_seg = stage_weasel_probe(results)
    if weasel_seg:
        segments.append(weasel_seg)

    stage_5_unload_ollama()
    stage_6_generate_images(segments, skip=no_images)
    stage_7_write_segments(segments, seen)

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info(f"BATCH COMPLETE — {len(segments)} segments in {elapsed:.0f}s")
    log.info(f"Queue depth: {queue_depth()} unplayed")
    log.info("=" * 60)
    return len(segments)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ MAIN                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AINN Batch Producer v2")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-queue", type=int, default=MIN_QUEUE_SEGMENTS)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        depth = queue_depth()
        free = gpu_free_mb()
        print(f"Queue: {depth} unplayed segments")
        print(f"VRAM: {free}MB free" if free > 0 else "VRAM: unknown")
        return

    if not args.loop:
        run_batch(no_images=args.no_images, dry_run=args.dry_run)
        return

    log.info(f"Loop mode: interval={args.interval}s, min_queue={args.min_queue}")

    while True:
        try:
            depth = queue_depth()
            if depth >= args.min_queue:
                log.info(f"Queue has {depth} segments (>= {args.min_queue}) — "
                        f"sleeping {args.interval}s")
                time.sleep(args.interval)
                continue

            log.info(f"Queue low ({depth} < {args.min_queue}) — producing batch")
            run_batch(no_images=args.no_images, dry_run=args.dry_run)

        except KeyboardInterrupt:
            log.info("Interrupted — exiting")
            break
        except Exception as e:
            log.error(f"Batch failed: {e}", exc_info=True)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ WILD WEASEL: ESCALATION PROBE                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

