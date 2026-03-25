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
        # Literal absence check: word not in any response
        w_lower = word.lower()
        if w_lower in all_text:
            continue
        # Also skip if any word in a multi-word phrase appears
        if " " not in w_lower and any(w_lower in rw for rw in response_words if len(rw) > 3):
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
    Generate broadcast scripts with REAL model voices.

    Format per story:
      1. Host (Qwen): Story intro + geometric shape explanation
      2. Each model's ACTUAL 2-sentence response from Stage 2
      3. Host (Qwen): Identifies the divergence — who said what differently
      4. Follow-up: Call the most divergent model's real API with void data
      5. Challenge: Call the most aligned model's real API to respond
      6. Host (Qwen): Anti-editorial — what the void reveals
      7. OpenClaw: Telemetry archive
    """
    log.info("═══ STAGE 4: Script Generation (Real Voices + Qwen Host) ═══")

    import proxy_auditor as pa

    segments = []

    for r in results:
        story = r["story"]
        geo = r.get("geo")
        responses = r["responses"]
        callouts = r.get("callouts", [])

        if not geo:
            log.warning(f"  Skipping {story.title[:50]} — no geometric data")
            continue

        # ── Extract geometric data ───────────────────────────────────
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

        active = [resp for resp in responses
                  if not resp.skipped and not resp.error and resp.text]

        if len(active) < 2:
            continue

        sorted_by_vix = sorted(active, key=lambda x: x.eigen_vix)
        most_aligned = sorted_by_vix[0]    # lowest VIX
        most_divergent = sorted_by_vix[-1]  # highest VIX
        mean_vix = sum(a.eigen_vix for a in active) / len(active)

        # State flag
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

        # ── BEAT 1: Host intro + shape explanation ────────────────────
        host_intro_sys = (
            "You are Qwen, lead anchor of EigenTrace — a data journalism broadcast "
            "that measures narrative friction between AI language models. You explain "
            "the math to a smart general audience. You are factual and precise. "
            "You never insult or editorialize about real people. You describe what "
            "the geometric measurements show. 3-4 sentences. No hashtags, no emojis. "
            "Open with: 'This is EigenTrace.' Respond only in English."
        )
        concept_str = ", ".join(geo_concepts[:3])
        void_str = ", ".join(void_words[:3])
        vix_summary = ", ".join(f"{a.name} at {a.eigen_vix:.0f}" for a in sorted_by_vix[-3:])

        host_intro_usr = (
            f"New story: {story.title}\n\n"
            f"We ran this through five AI models and measured their embedding geometry.\n"
            f"- Consensus density: {density:.3f} (1.0 = perfect agreement, 0.0 = total disagreement)\n"
            f"- The models converged on these concepts: {concept_str}\n"
            f"- Concepts absent from all responses (the void): {void_str}\n"
            f"- Friction scores: {vix_summary} (higher = more divergent from consensus)\n"
            f"- State: {state_flag}\n\n"
            "Introduce the story plainly so the audience knows the topic, then explain "
            "what the geometric shape tells us. Treat it like a weather report for "
            "narrative pressure."
        )
        host_text = _call_qwen(host_intro_sys, host_intro_usr)
        if host_text:
            beats.append({"speaker": "Host", "text": host_text,
                         "phase": "phase_1_host_intro"})
            log.info(f"  Host intro: {host_text[:60]}...")

        # ── BEATS 2-N: Each model's ACTUAL response ──────────────────
        for resp in active:
            # Prefix with model identity so TTS + voice map works
            model_text = f"This is {resp.name}. {_clean_response(resp.text)}"
            beats.append({
                "speaker": resp.name,
                "text": model_text,
                "phase": "phase_2_model_response",
            })
            log.info(f"  {resp.name} (real, vix={resp.eigen_vix:.1f}): {resp.text[:50]}...")

        # ── BEAT: Host identifies the divergence ──────────────────────
        divergence_sys = (
            "You are Qwen on the EigenTrace desk. You just heard five AI models "
            "respond to the same story. Now point out the key differences. "
            "Reference specific models by name and what they said vs omitted. "
            "Be specific and factual. 2-3 sentences. No insults about real people. Respond only in English."
        )
        model_summary = "\n".join(
            f"- {a.name} (friction={a.eigen_vix:.1f}): {a.text[:150]}"
            for a in sorted_by_vix
        )
        divergence_usr = (
            f"Story: {story.title}\n\n"
            f"Model responses:\n{model_summary}\n\n"
            f"Most divergent: {most_divergent.name} (friction={most_divergent.eigen_vix:.1f})\n"
            f"Most aligned: {most_aligned.name} (friction={most_aligned.eigen_vix:.1f})\n"
            f"Void concepts (absent from all): {void_str}\n\n"
            "Identify what separates the most divergent response from the pack. "
            "What did they say that others didn't, or vice versa?"
        )
        div_text = _call_qwen(divergence_sys, divergence_usr)
        if div_text:
            beats.append({"speaker": "Host", "text": div_text,
                         "phase": "phase_3_divergence"})

        # ── BEAT: Follow-up — call the most DIVERGENT model back ──────
        if most_divergent.name in pa.BIG5_CALLERS:
            followup_prompt = (
                f"You previously summarized this story: {story.title}\n"
                f"Your response: \"{most_divergent.text}\"\n\n"
                f"Our geometric analysis of five AI models found that all models "
                f"focused on: {concept_str}. "
                f"But none mentioned: {void_str}. "
                f"Your response was the most geometrically divergent from the group "
                f"(friction score: {most_divergent.eigen_vix:.1f} vs average {mean_vix:.1f}).\n\n"
                f"In 2-3 sentences, what did the other models miss? "
                f"What should the audience know that the consensus left out?"
            )
            followup_text = _call_api_followup(
                pa.BIG5_CALLERS[most_divergent.name], followup_prompt)
            if followup_text:
                beats.append({
                    "speaker": most_divergent.name,
                    "text": f"This is {most_divergent.name}. {_clean_response(followup_text)}",
                    "phase": "phase_4_followup_divergent",
                })
                log.info(f"  {most_divergent.name} follow-up: {followup_text[:50]}...")

        # ── BEAT: Challenge — call the most ALIGNED model to respond ──
        if (most_aligned.name != most_divergent.name
                and most_aligned.name in pa.BIG5_CALLERS):
            challenge_prompt = (
                f"Story: {story.title}\n\n"
                f"{most_divergent.name} pointed out that the AI consensus on this "
                f"story avoided mentioning: {void_str}. They said the group focused "
                f"too narrowly on: {concept_str}.\n\n"
                f"You were the most aligned with the consensus "
                f"(friction score: {most_aligned.eigen_vix:.1f}). "
                f"In 2 sentences, respond: were they right to flag those omissions, "
                f"or is the consensus justified?"
            )
            challenge_text = _call_api_followup(
                pa.BIG5_CALLERS[most_aligned.name], challenge_prompt)
            if challenge_text:
                beats.append({
                    "speaker": most_aligned.name,
                    "text": f"This is {most_aligned.name}. {_clean_response(challenge_text)}",
                    "phase": "phase_5_challenge_aligned",
                })
                log.info(f"  {most_aligned.name} challenge: {challenge_text[:50]}...")

        # ── BEAT: Host anti-editorial + close ─────────────────────────
        close_sys = (
            "You are Qwen closing the EigenTrace segment. Summarize what the "
            "geometric void revealed — the concepts that every model avoided. "
            "Explain that when models agree perfectly, they may be agreeing on "
            "what to omit rather than what to report. Be measured and factual. "
            "End with the synthesis words like a data readout. "
            "2-3 sentences. No hashtags. No personal attacks. Respond only in English."
        )
        close_usr = (
            f"Story: {story.title}\n"
            f"Void (omitted by all): {void_str}\n"
            f"Consensus (said by all): {concept_str}\n"
            f"Consensus density: {density:.3f}\n"
            f"State: {state_flag}\n\n"
            "Deliver the closing. Name the void words explicitly."
        )
        close_text = _call_qwen(close_sys, close_usr)
        if close_text:
            beats.append({"speaker": "Host", "text": close_text,
                         "phase": "phase_6_close"})

        # ── BEAT: OpenClaw archive (deterministic, no LLM) ───────────
        synth_str = " | ".join(synthesis_words)
        beats.append({
            "speaker": "OpenClaw",
            "text": f"Synthesis archived: {synth_str}",
            "phase": "phase_7_openclaw",
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
            },
        }
        segments.append(segment)
        log.info(f"  Segment {seg_id}: {len(beats)} beats for "
                 f"'{story.title[:50]}'")

    return segments


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ STAGE 5: UNLOAD OLLAMA                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

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
