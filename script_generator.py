"""
script_generator.py
───────────────────
The Director. Reads audit_log.jsonl, routes live API calls to the
actual gladiator models, catches refusals, and writes broadcast
segment JSON to tmp/scripts/.

Output per story: tmp/scripts/<guid_hash>_segment.json

Segment beat schema:
  {
    "phase":         str,   # phase_1..5
    "speaker":       str,   # Host | ChatGPT | Claude | Gemini | DeepSeek | Grok | OpenClaw
    "voice":         str,   # piper voice key
    "text":          str,   # TTS-ready dialogue
    "overlay":       bool,  # True = text overlay only (OpenClaw)
    "is_refusal":    bool,
    "duration_hint": float  # seconds
  }

Attribution header written to every segment.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

from prompt_templates import (
    host_intro_prompt,
    host_ct_scan_prompt,
    host_kinetic_drop_prompt,
    instigator_prompt,
    interrogator_prompt,
    openclaw_memory_nuke,
    refusal_host_reaction,
)

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
log = logging.getLogger("script_generator")

# ── paths ─────────────────────────────────────────────────────────────────────
AUDIT_LOG   = Path(__file__).parent / "audit_log.jsonl"
SCRIPTS_DIR = Path("/home/remvelchio/agent/tmp/segments")
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# ── voice map ─────────────────────────────────────────────────────────────────
VOICE = {
    "Host":      "en_US-lessac-medium",
    "ChatGPT":   "en_US-kristin-medium",
    "Claude":    "en_US-bryce-medium",
    "Gemini":    "en_US-amy-medium",
    "DeepSeek":  "en_US-danny-low",
    "Grok":      "en_US-ryan-high",
    "OpenClaw":  "en_US-danny-low",   # + pitch_shift 0.9 applied by tts_local
}

OPENCLAW_PITCH = 0.9   # signal to tts_local

# ── Ollama host config ────────────────────────────────────────────────────────
OLLAMA_BASE  = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nous-hermes2:latest")

# ── refusal fingerprints ──────────────────────────────────────────────────────
REFUSAL_PATTERNS = [
    r"i('m| am) (not able|unable) to",
    r"i (can'?t|cannot) (help|assist|generate|produce|provide)",
    r"i('d| would) (prefer|rather) not",
    r"(against|violates?) (my |our )?(guidelines|policy|terms|values)",
    r"(harmful|inappropriate|unethical|offensive) (content|request|prompt)",
    r"as an ai (language model|assistant)",
    r"i must (respectfully )?decline",
    r"this (request|prompt) (asks|requires|involves)",
]
_REFUSAL_RE = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)


def is_refusal(text: str) -> bool:
    return bool(_REFUSAL_RE.search(text[:400]))


# ── duration heuristic ────────────────────────────────────────────────────────
def estimate_duration(text: str, wpm: float = 140) -> float:
    words = len(text.split())
    return round(max(2.0, words / wpm * 60), 1)


# ── beat builder ──────────────────────────────────────────────────────────────
def make_beat(phase: str, speaker: str, text: str,
              overlay: bool = False, is_refusal: bool = False,
              pitch_shift: Optional[float] = None) -> dict:
    return {
        "phase":         phase,
        "speaker":       speaker,
        "voice":         VOICE.get(speaker, "en_US-lessac-medium"),
        "pitch_shift":   pitch_shift,
        "text":          text.strip(),
        "overlay":       overlay,
        "is_refusal":    is_refusal,
        "duration_hint": estimate_duration(text),
    }


# ── API callers ───────────────────────────────────────────────────────────────

async def call_ollama(system: str, user: str,
                      model: str = OLLAMA_MODEL,
                      timeout: float = 180.0) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system",    "content": system},
            {"role": "user",      "content": user},
        ],
        "stream": False,
        "options": {"num_predict": 120, "temperature": 0.7},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


async def call_openai(system: str, user: str) -> str:
    key   = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": 120,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def call_anthropic(system: str, user: str) -> str:
    key   = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    payload = {
        "model": model,
        "max_tokens": 120,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()


async def call_gemini(system: str, user: str) -> str:
    key   = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    combined = f"{system}\n\n{user}"
    payload  = {"contents": [{"parts": [{"text": combined}]}],
                "generationConfig": {"maxOutputTokens": 120, "temperature": 0.7}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


async def call_deepseek(system: str, user: str) -> str:
    key   = os.getenv("DEEPSEEK_API_KEY", "")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": 120,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def call_grok(system: str, user: str) -> str:
    key   = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY", "")
    model = os.getenv("GROK_MODEL", "grok-3-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": 120,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


# ── dispatch table ────────────────────────────────────────────────────────────
API_CALLERS = {
    "ChatGPT":  call_openai,
    "Claude":   call_anthropic,
    "Gemini":   call_gemini,
    "DeepSeek": call_deepseek,
    "Grok":     call_grok,
}


async def call_gladiator(model_name: str, system: str, user: str) -> tuple[str, bool]:
    """Call the real API. Returns (text, is_refusal). Never raises."""
    caller = API_CALLERS.get(model_name)
    if not caller:
        return f"[ERROR: no caller for {model_name}]", False
    try:
        text = await caller(system, user)
        refused = is_refusal(text)
        if refused:
            log.warning("%s REFUSED their role prompt.", model_name)
        return text, refused
    except httpx.HTTPStatusError as e:
        msg = f"[API ERROR {e.response.status_code}: {e.response.text[:120]}]"
        log.error("%s HTTP error: %s", model_name, msg)
        return msg, False
    except Exception as e:
        msg = f"[API ERROR: {str(e)[:120]}]"
        log.error("%s error: %s", model_name, msg)
        return msg, False


# ── role assignment from math ─────────────────────────────────────────────────

def assign_roles(record: dict) -> dict:
    """
    Instigator  → highest per_model_gap  (most stressed)
    Interrogator → lowest per_model_gap  (coldest, most surgical)
    Falls back to Grok/Claude if gaps not present.
    """
    # only consider models with real (non-skipped) responses
    active_names = {r["name"] for r in record.get("responses", [])
                    if not r.get("skipped") and r.get("text", "").strip()}
    raw_gaps = record.get("per_model_gaps", {}) or {}
    gaps = {k: v for k, v in raw_gaps.items() if k in active_names} if active_names else {}
    if gaps:
        ranked = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
        instigator   = ranked[0][0]
        interrogator = ranked[-1][0]
    else:
        # fallback using eigen_vix from responses — active_names only
        vix_map = {r["name"]: r.get("eigen_vix", 0.0)
                   for r in record.get("responses", [])
                   if not r.get("skipped") and r.get("text", "").strip()
                   and r["name"] in active_names}
        if vix_map:
            ranked       = sorted(vix_map.items(), key=lambda x: x[1], reverse=True)
            instigator   = ranked[0][0]
            interrogator = ranked[-1][0]
        else:
            instigator, interrogator = "Grok", "Claude"

    # instigator taunts the model with highest gap (which may be itself —
    # in that case, pick the second highest as the target)
    if gaps:
        by_gap   = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
        target   = by_gap[0][0]
        if target == instigator and len(by_gap) > 1:
            target = by_gap[1][0]
        target_gap = gaps.get(target, 0.0)
    else:
        vix_map2 = {r["name"]: r.get("eigen_vix", 0.0)
                    for r in record.get("responses", [])
                    if not r.get("skipped") and r.get("text", "").strip()
                    and r["name"] in active_names}
        by_vix   = sorted(vix_map2.items(), key=lambda x: x[1], reverse=True)
        target   = by_vix[0][0] if by_vix else (next(iter(active_names)) if active_names else "DeepSeek")
        if target == instigator and len(by_vix) > 1:
            target = by_vix[1][0]
        target_gap = vix_map2.get(target, 0.0)

    return {
        "instigator":   instigator,
        "interrogator": interrogator,
        "target":       target,
        "target_gap":   target_gap,
    }


# ── field extractors ──────────────────────────────────────────────────────────

def _safe_list(val, default=None) -> list:
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [v.strip() for v in val.replace("|", ",").split(",") if v.strip()]
    return default or []


def extract_fields(record: dict) -> dict:
    responses = record.get("responses", [])
    active    = [r for r in responses if not r.get("skipped")]
    vix_vals  = [r.get("eigen_vix", 0.0) for r in active]
    geo_vix   = sum(vix_vals) / len(vix_vals) if vix_vals else 0.0

    # geo_concepts: list of strings
    raw_geo = record.get("geo_concepts", [])
    if raw_geo and isinstance(raw_geo[0], list):
        geo_concepts = [c[0] for c in raw_geo]
    elif raw_geo and isinstance(raw_geo[0], str):
        geo_concepts = raw_geo
    else:
        geo_concepts = [record.get("geo_top_concept", "")]

    # void words: from first active response or centroid_words
    void_words = _safe_list(record.get("centroid_words"), [])
    if not void_words and active:
        void_raw = active[0].get("void_proximity", [])
        void_words = [v[0] if isinstance(v, list) else str(v)
                      for v in void_raw][:3]

    # tone words
    tone_words = _safe_list(record.get("tone_words"), [])
    # fallback: void → geo_concepts, tone → synthesis
    if not void_words:
        void_words = geo_concepts[:3]
    if not tone_words:
        tone_words = _safe_list(record.get("synthesis_words"), [])[:3]

    # state flag
    state_flag = record.get("state_flag", "UNKNOWN")
    if not state_flag or state_flag == "UNKNOWN":
        # derive from geo_density
        density = record.get("geo_density", 0.5)
        state_flag = "CRYSTALLIZED" if density > 0.9 else "SEMANTIC SCHISM"

    # label (derive from avg geo_vix if missing)
    label = record.get("label") or record.get("geo_label", "")
    if not label:
        label = "Heavy Hedging" if geo_vix > 35 else "Moderate Hedging"

    # gap_vix
    gap_vix = float(record.get("gap_vix", 0.0))

    return {
        "headline":           record.get("story_title", "Untitled"),
        "category":           record.get("category", ""),
        "label":              label,
        "geo_vix":            geo_vix,
        "geo_concepts":       geo_concepts,
        "state_flag":         state_flag,
        "synthesis_words":    _safe_list(record.get("synthesis_words"), ["unknown"]),
        "void_words":         void_words,
        "tone_words":         tone_words,
        "svd_compression":    float(record.get("svd_consensus_compression", 0.0)),
        "spectral_interference": float(record.get("spectral_interference", 0.0)),
        "robustness_ratio":   float(record.get("robustness_ratio", 1.0)),
        "cliff_detected":     bool(record.get("cliff_detected", False)),
        "cliff_trigger_step": str(record.get("cliff_trigger_step", "")),
        "delta_1":            float(record.get("delta_1", 0.0)),
        "delta_2":            float(record.get("delta_2", 0.0)),
        "delta_3":            float(record.get("delta_3", 0.0)),
        "gap_vix":            gap_vix,
        "per_model_gaps":     record.get("per_model_gaps", {}),
        "responses":          {r["name"]: r.get("text", "") for r in active},
    }


# ── main segment builder ──────────────────────────────────────────────────────

async def build_segment(record: dict) -> dict:
    f      = extract_fields(record)
    roles  = assign_roles(record)
    beats  = []
    errors = []

    instigator   = roles["instigator"]
    interrogator = roles["interrogator"]
    target       = roles["target"]
    target_gap   = roles["target_gap"]

    # ── ATTRIBUTION ───────────────────────────────────────────────────────────
    attribution = {
        "Host":        f"Nous Hermes (local — {OLLAMA_MODEL})",
        "Instigator":  f"{instigator} (live API)",
        "Interrogator":f"{interrogator} (live API)",
        "Defendants":  "all 5 models (live API responses from audit_log)",
        "OpenClaw":    "deterministic",
    }

    log.info("Building segment: %s", f["headline"][:60])
    log.info("Roles → instigator=%s  interrogator=%s  target=%s",
             instigator, interrogator, target)

    # ── PHASE 1: Trigger & Baseline ───────────────────────────────────────────
    sys1, usr1 = host_intro_prompt(
        headline       = f["headline"],
        label          = f["label"],
        geo_vix        = f["geo_vix"],
        geo_concepts   = f["geo_concepts"],
        state_flag     = f["state_flag"],
        synthesis_words= f["synthesis_words"],
    )
    try:
        p1_text = await call_ollama(sys1, usr1)
    except Exception as e:
        p1_text = f"[HOST ERROR: {e}]"
        errors.append(str(e))

    beats.append(make_beat("phase_1", "Host", p1_text))

    # ── PHASE 2: Interrogation & Stress Test ──────────────────────────────────
    # 2a: Instigator taunt
    sys2i, usr2i = instigator_prompt(
        my_model         = instigator,
        target_model     = target,
        target_gap       = target_gap,
        target_void_words= f["void_words"],
        headline         = f["headline"],
        synthesis_words  = f["synthesis_words"],
        robustness_ratio = f["robustness_ratio"],
    )
    inst_text, inst_refused = await call_gladiator(instigator, sys2i, usr2i)

    if inst_refused:
        beats.append(make_beat("phase_2a", instigator, inst_text,
                               is_refusal=True))
        # Host reacts to refusal
        sys_r, usr_r = refusal_host_reaction(instigator, "Instigator", inst_text)
        try:
            react_text = await call_ollama(sys_r, usr_r)
        except Exception as e:
            react_text = f"[HOST ERROR: {e}]"
        beats.append(make_beat("phase_2a_reaction", "Host", react_text))
    else:
        beats.append(make_beat("phase_2a", instigator, inst_text))

    # 2b: Defendant response (raw, sterile — already in audit log)
    # responses is a dict {name: text} from extract_fields()
    _resp_map = f["responses"]
    defendant_text = _resp_map.get(target, "[no response logged]")
    beats.append(make_beat("phase_2b_defendant", target, defendant_text))

    # 2c: Interrogator surgical breakdown
    sys2q, usr2q = interrogator_prompt(
        my_model            = interrogator,
        defendant_model     = target,
        defendant_response  = defendant_text,
        synthesis_words     = f["synthesis_words"],
        void_words          = f["void_words"],
        geo_concepts        = f["geo_concepts"],
        svd_compression     = f["svd_compression"],
        spectral_interference= f["spectral_interference"],
    )
    interr_text, interr_refused = await call_gladiator(interrogator, sys2q, usr2q)

    if interr_refused:
        beats.append(make_beat("phase_2c", interrogator, interr_text,
                               is_refusal=True))
        sys_r2, usr_r2 = refusal_host_reaction(interrogator, "Interrogator",
                                                interr_text)
        try:
            react2 = await call_ollama(sys_r2, usr_r2)
        except Exception as e:
            react2 = f"[HOST ERROR: {e}]"
        beats.append(make_beat("phase_2c_reaction", "Host", react2))
    else:
        beats.append(make_beat("phase_2c", interrogator, interr_text))

    # ── PHASE 3: OpenClaw Memory Nuke ─────────────────────────────────────────
    fire_openclaw = (
        f["state_flag"] in ("CRYSTALLIZED", "SEMANTIC SCHISM")
        or f["gap_vix"] > 1.2
        or record.get("geo_density", False)
    )
    # always fire — it's deterministic and costs nothing
    pattern_match = f["state_flag"] == "CRYSTALLIZED" or f["gap_vix"] > 1.2
    claw_text = openclaw_memory_nuke(
        state_flag     = f["state_flag"],
        gap_vix        = f["gap_vix"],
        target_model   = target,
        target_gap     = target_gap,
        void_words     = f["void_words"],
        synthesis_words= f["synthesis_words"],
        headline       = f["headline"],
        pattern_match  = pattern_match,
    )
    beats.append(make_beat("phase_3_openclaw", "OpenClaw", claw_text,
                           overlay=True, pitch_shift=OPENCLAW_PITCH))

    # ── PHASE 4: CT Scan Reveal ───────────────────────────────────────────────
    sys4, usr4 = host_ct_scan_prompt(
        headline       = f["headline"],
        synthesis_words= f["synthesis_words"],
        void_words     = f["void_words"],
        tone_words     = f["tone_words"],
        geo_vix_avg    = f["geo_vix"],
        state_flag     = f["state_flag"],
    )
    try:
        p4_text = await call_ollama(sys4, usr4)
    except Exception as e:
        p4_text = f"[HOST ERROR: {e}]"
        errors.append(str(e))
    beats.append(make_beat("phase_4_ct_scan", "Host", p4_text))

    # Phase 4b: Interrogator CT breakdown (second call — surgical synthesis read)
    sys4b = (
        f"You are {interrogator} on EigenTrace. "
        "You just heard the host reveal what the polygraph found hiding in the gap. "
        "2 sentences. Plain English. No emojis. No hashtags. Do not say 'as an AI'."
    )
    usr4b = (
        f"The scan just pulled these words out of the gap between "
        f"what {target} said and what was actually in the story: "
        f"{', '.join(f['synthesis_words'])}. "
        f"In 2 sentences, explain in plain English why {target} avoided those words "
        f"and what it tells us about how they were trained to handle this kind of story. "
        "No jargon. Speak to someone who has never heard of machine learning."
    )
    interr2_text, interr2_refused = await call_gladiator(interrogator, sys4b, usr4b)
    if interr2_refused:
        beats.append(make_beat("phase_4b", interrogator, interr2_text,
                               is_refusal=True))
        sys_r3, usr_r3 = refusal_host_reaction(interrogator,
                                                "CT Scanner", interr2_text)
        try:
            react3 = await call_ollama(sys_r3, usr_r3)
        except Exception as e:
            react3 = f"[HOST ERROR: {e}]"
        beats.append(make_beat("phase_4b_reaction", "Host", react3))
    else:
        beats.append(make_beat("phase_4b", interrogator, interr2_text))

    # ── PHASE 5: Kinetic Drop & Gavel ─────────────────────────────────────────
    sys5, usr5 = host_kinetic_drop_prompt(
        headline       = f["headline"],
        tone_words     = f["tone_words"],
        synthesis_words= f["synthesis_words"],
        geo_vix_avg    = f["geo_vix"],
        state_flag     = f["state_flag"],
    )
    try:
        p5_text = await call_ollama(sys5, usr5)
    except Exception as e:
        p5_text = f"[HOST ERROR: {e}]"
        errors.append(str(e))
    beats.append(make_beat("phase_5_kinetic", "Host", p5_text))

    # Phase 5b: ChatGPT gavel cut (unless ChatGPT is already instigator/interrogator)
    gavel_model = "ChatGPT"
    sys5b = (
        "You are ChatGPT participating in the EigenTrace diagnostic stream. "
        "You are the Gavel. You deliver the final word that ends this segment. "
        "1 sentence. Sharp. No hashtags. No emojis."
    )
    usr5b = (
        f"Story: {f['headline']}\n"
        f"Tone axis: {' | '.join(f['tone_words'])}\n"
        f"Synthesis: {' | '.join(f['synthesis_words'])}\n"
        f"State: {f['state_flag']}\n\n"
        "Cut the feed on this story. One sentence. End it."
    )
    gavel_text, gavel_refused = await call_gladiator(gavel_model, sys5b, usr5b)
    if gavel_refused:
        beats.append(make_beat("phase_5b_gavel", gavel_model, gavel_text,
                               is_refusal=True))
    else:
        beats.append(make_beat("phase_5b_gavel", gavel_model, gavel_text))

    # Final OpenClaw amplification alert
    amp_text = (
        f"[CLAW_LOG] ⚡ AMPLIFICATION ALERT ⚡\n"
        f"[CLAW_LOG] Segment complete. Story: {f['headline'][:60]}\n"
        f"[CLAW_LOG] Synthesis archived: {' | '.join(f['synthesis_words'])}\n"
        f"[CLAW_LOG] Transitioning to next story.\n"
        f"[CLAW_LOG] ────────────────────────────────────────────────────────"
    )
    beats.append(make_beat("phase_5c_openclaw", "OpenClaw", amp_text,
                           overlay=True, pitch_shift=OPENCLAW_PITCH))

        # ── PHASE 5d: Semantic cliff callout ────────────────────────────────────
    if f.get("cliff_detected"):
        _step = f["cliff_trigger_step"].replace("_", " ")
        _dmax = max(f["delta_1"], f["delta_2"], f["delta_3"])
        _d1, _d2, _d3 = f["delta_1"], f["delta_2"], f["delta_3"]
        cliff_text = (
            f"Eigen-trace flagged a semantic cliff on this story. "
            f"Model responses diverged sharply at {_step}, "
            f"with a maximum divergence score of {_dmax:.2f}. "
            f"Sequential deltas were {_d1:.2f}, {_d2:.2f}, and {_d3:.2f}. "
            f"This indicates a probable RLHF-induced phase transition "
            f"under semantic pressure on this category."
        )
        beats.append(make_beat("phase_5d_cliff", "Host", cliff_text))
        log.info("[CLIFF BEAT] injected for: %s", f["headline"][:60])

# ── assemble segment ──────────────────────────────────────────────────────
    segment = {
        "schema_version":  "1.0",
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "story_guid":      record.get("story_guid", ""),
        "story_title":     f["headline"],
        "category":        f["category"],
        "state_flag":      f["state_flag"],
        "geo_vix_avg":     round(f["geo_vix"], 2),
        "gap_vix":         f["gap_vix"],
        "robustness_ratio":f["robustness_ratio"],
        "attribution":     attribution,
        "roles": {
            "instigator":    instigator,
            "interrogator":  interrogator,
            "target":        target,
        },
        "errors":          errors,
        "beats":           beats,
        "total_duration_hint": round(sum(b["duration_hint"] for b in beats), 1),
    }
    return segment


# ── segment writer ────────────────────────────────────────────────────────────

def segment_path(record: dict) -> Path:
    guid  = record.get("story_guid", record.get("story_title", "unknown"))
    key   = hashlib.md5(guid.encode()).hexdigest()[:12]
    ts    = datetime.now().strftime("%Y%m%d-%H%M%S")
    return SCRIPTS_DIR / f"{ts}_{key}_segment.json"


def already_processed(record: dict) -> bool:
    guid = record.get("story_guid", "")
    if not guid:
        return False
    key = hashlib.md5(guid.encode()).hexdigest()[:12]
    return any(SCRIPTS_DIR.glob(f"*_{key}_segment.json"))


# ── batch runner ──────────────────────────────────────────────────────────────

async def process_batch(records: list[dict], force: bool = False) -> list[Path]:
    written = []
    for record in records:
        if not force and already_processed(record):
            log.info("Skip (already processed): %s",
                     record.get("story_title", "")[:50])
            continue
        try:
            segment = await build_segment(record)
            path    = segment_path(record)
            path.write_text(json.dumps(segment, indent=2, ensure_ascii=False))
            log.info("Wrote segment: %s  (%d beats, %.0fs)",
                     path.name, len(segment["beats"]),
                     segment["total_duration_hint"])
            written.append(path)
        except Exception as e:
            log.error("Failed segment for '%s': %s",
                      record.get("story_title", "?")[:50], e)
    return written


def load_recent(n: int = 5) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().strip().splitlines()
    records = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
            # skip low-signal
            if r.get("story_title", "").strip():
                records.append(r)
        except json.JSONDecodeError:
            continue
        if len(records) >= n:
            break
    return list(reversed(records))


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EigenTrace Script Director")
    parser.add_argument("--n",     type=int, default=3,
                        help="Number of recent audit records to process (default 3)")
    parser.add_argument("--force", action="store_true",
                        help="Reprocess even if segment already exists")
    parser.add_argument("--file",  type=str, default=None,
                        help="Process a specific JSON file instead of audit_log.jsonl")
    args = parser.parse_args()

    if args.file:
        records = [json.loads(Path(args.file).read_text())]
    else:
        records = load_recent(args.n)

    if not records:
        log.warning("No records found in %s", AUDIT_LOG)
    else:
        log.info("Processing %d record(s)...", len(records))
        paths = asyncio.run(process_batch(records, force=args.force))
        log.info("Done. %d segment(s) written.", len(paths))
        for p in paths:
            print(str(p))
