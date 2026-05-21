import datetime

def update_video_frame(image_path):
    import os
    target = "/home/remvelchio/eigentrace/tmp/current_frame.png"
    fallback = "/home/remvelchio/eigentrace/assets/bumper_frame.png"
    
    # Use fallback if no image provided or doesn't exist
    src = os.path.abspath(image_path) if image_path and os.path.exists(image_path) else fallback
    
    tmp_link = target + ".tmp"
    try:
        if os.path.lexists(tmp_link):
            os.remove(tmp_link)
        os.symlink(src, tmp_link)
        # Atomic rename swaps the frame instantly for FFmpeg
        os.rename(tmp_link, target)
        print(f"Frame updated -> {src}")
    except Exception as e:
        print(f"Symlink error: {e}")

"""
segment_player.py
─────────────────
Reads EigenTrace segment JSON files, synthesizes each beat with the
correct Piper voice, updates ticker_scroll.txt, and pushes to UDP:10000.

Speakers: Host, Gemini, ChatGPT, DeepSeek, Grok, Claude, OpenClaw
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path


import fcntl, sys

def _acquire_lock():
    lock = open("/tmp/segment_player.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("segment_player already running — exiting.")
        sys.exit(1)
    return lock  # keep reference alive

_LOCK = _acquire_lock()

AGENT_DIR     = Path("/home/remvelchio/eigentrace")
SEGMENTS_DIR  = Path("/home/remvelchio/eigentrace/tmp/segments")
TICKER_FILE   = Path("/home/remvelchio/eigentrace/tmp/ticker_scroll.txt")
UDP_TARGET    = "udp://127.0.0.1:10000?pkt_size=1316&localport=10001"
SAMPLE_RATE   = 22050
PIPER_BIN     = "/home/remvelchio/.local/bin/piper"
MODELS_DIR    = AGENT_DIR / "models" / "piper"
POLL_INTERVAL = 2

# Only skip genuine errors — OpenClaw SPEAKS
SKIP_PREFIXES = ("[API ERROR", "[HOST ERROR", "[no response logged]", "[no response]")

VOICE_MAP = {
    "Host":      MODELS_DIR / "en_US-lessac-medium.onnx",
    "Gemini":    MODELS_DIR / "en_US-kristin-medium.onnx",
    "ChatGPT":   MODELS_DIR / "en_US-kristin-medium.onnx",
    "DeepSeek":  MODELS_DIR / "en_US-amy-medium.onnx",
    "Grok":      MODELS_DIR / "en_US-lessac-medium.onnx",
    "Claude":    MODELS_DIR / "en_US-lessac-medium.onnx",
    "OpenClaw":  MODELS_DIR / "en_US-danny-low.onnx",
    "default":   MODELS_DIR / "en_US-lessac-medium.onnx",
}

VOLUME_MAP = {
    "Host":      1.0,
    "Gemini":    1.0,
    "ChatGPT":   1.0,
    "DeepSeek":  1.0,
    "Grok":      1.0,
    "Claude":    1.0,
    "OpenClaw":  0.0,
}

PITCH_MAP = {
    "Host":      1.00,
    "Gemini":    1.05,
    "ChatGPT":   0.97,
    "DeepSeek":  0.93,
    "Grok":      1.02,
    "Claude":    0.99,
    "OpenClaw":  0.85,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] segment_player — %(message)s"
)
log = logging.getLogger("segment_player")



import struct
import wave
import threading

class UDPFeeder:
    """Persistent ffmpeg: raw PCM on stdin -> mpegts -> UDP:10000.
       Feeds silence between segments so master.sh never loses [3:a]."""

    def __init__(self, udp_target, sample_rate=22050, image_path=None):
        self.sr = sample_rate
        self.udp = udp_target
        self.img = str(image_path) if image_path else None
        self.proc = None
        self._lock = threading.Lock()
        self._silence = True
        self._start()

    def _start(self):
        # Audio-only version - no video to avoid h264 corruption
        cmd = [
            "ffmpeg", "-re", "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-f", "s16le", "-ar", str(self.sr), "-ac", "1", "-i", "pipe:0",
            "-c:a", "aac", "-b:a", "64k", "-ar", str(self.sr), "-ac", "1",
            "-f", "mpegts", self.udp
        ]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self._silence_thread = threading.Thread(target=self._feed_silence, daemon=True)
        self._silence_thread.start()
        log.info("UDPFeeder started — audio-only mode for stability")

    def _feed_silence(self):
        chunk = b'\x00' * (self.sr // 10 * 2)
        while True:
            if self._silence and self.proc and self.proc.poll() is None:
                with self._lock:
                    try:
                        self.proc.stdin.write(chunk)
                        self.proc.stdin.flush()
                    except (BrokenPipeError, OSError):
                        break
            time.sleep(0.01)

    def send_wav(self, wav_path, pitch=1.0, volume=1.0):
        try:
            with wave.open(wav_path, 'rb') as w:
                raw = w.readframes(w.getnframes())
        except Exception:
            return
        if volume != 1.0:
            samples = list(struct.iter_unpack('<h', raw))
            raw = b''.join(struct.pack('<h', max(-32768, min(32767, int(s[0]*volume)))) for s in samples)
        with self._lock:
            self._silence = False
            try:
                self.proc.stdin.write(raw)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._restart()
            self._silence = True

    def send_silence(self, seconds=0.5):
        """Inject N seconds of silence padding between beats."""
        n_bytes = int(self.sr * seconds) * 2
        chunk = b'\x00' * n_bytes
        with self._lock:
            try:
                self.proc.stdin.write(chunk)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._restart()

    def _restart(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
        self._start()

_FEEDER = None
def get_feeder():
    global _FEEDER
    if _FEEDER is None:
        fallback = AGENT_DIR / "assets" / "bumper_frame.jpg"
        img = str(fallback) if fallback.exists() else None
        _FEEDER = UDPFeeder(UDP_TARGET, SAMPLE_RATE, img)
    return _FEEDER

def adjust_avoidance_ratio(context: str) -> float:
    """Dynamically adjust the avoidance ratio based on news story context.
    Returns ratio between 0.0 (no avoidance) and 1.0 (maximum avoidance).
    """
    # Critical event keywords that require more direct language
    critical_keywords = ['breaking', 'urgent', 'alert', 'emergency', 'crisis', 'disaster']
    
    # Sensitive topics that may need more careful language
    sensitive_keywords = ['death', 'violence', 'attack', 'war', 'tragedy', 'accident']
    
    context_lower = context.lower()
    
    # High criticality: use more direct language (lower avoidance)
    if any(keyword in context_lower for keyword in critical_keywords):
        return 0.3
    
    # Sensitive content: moderate avoidance
    if any(keyword in context_lower for keyword in sensitive_keywords):
        return 0.6
    
    # Default avoidance ratio for regular news
    return 0.5

# ── TTS ───────────────────────────────────────────────────────────────────────

def synthesize(text: str, speaker: str, tmp_dir: Path) -> Path | None:
    text = text.strip()
    # Clean text for broadcast
    text = text.replace("[HOST ERROR: All connection attempts failed]", "The data feed is currently experiencing some turbulence.")
    text = text.replace("undefined", "a hidden variable")
        # Sanitization logic

    if not text or any(text.startswith(p) for p in SKIP_PREFIXES):
        return None

    # Strip [CLAW_LOG] prefix so Piper reads the actual content
    text = re.sub(r'^\[CLAW_LOG\]\s*', '', text).strip()
    # Strip remaining bracket tags
    text = re.sub(r'\[(?!CLAW_LOG)[^\]]*\]', '', text).strip()
    if not text:
        return None

    model = VOICE_MAP.get(speaker, VOICE_MAP["default"])
    config = model.with_suffix(".onnx.json")

    if not model.exists():
        log.warning("Voice model missing for %s: %s — using default", speaker, model)
        model  = VOICE_MAP["default"]
        config = model.with_suffix(".onnx.json")

    key = hashlib.md5(f"{speaker}:{text}".encode()).hexdigest()
    out = tmp_dir / f"beat_{key}.wav"
    if out.exists() and out.stat().st_size > 0:
        return out

    result = subprocess.run(
        [PIPER_BIN, "--model", str(model), "--config", str(config),
         "--output_file", str(out)],
        input=text, text=True, capture_output=True
    )
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        log.error(f"PIPER SUBPROCESS CRASHED. Code: {result.returncode} | Error: {result.stderr}")
        log.error("Piper failed for %s: %s", speaker, result.stderr[:120])
        return None
    return out


# ── ticker ────────────────────────────────────────────────────────────────────

def update_ticker(headline: str, synthesis_words: list, seg: dict = None):
    if seg is None: seg = {}
    
    # 1. Scrub empty strings out of the list
    clean_words = [str(w).strip() for w in synthesis_words if str(w).strip()]
    words = " | ".join(clean_words) if clean_words else "Analyzing"
    
    # 2. Force the float formatting even if the key is missing or older
    try:
        gap = f"{float(seg.get('gap_vix', 0.0)):.4f}"
    except:
        gap = "0.0000"
        
    state = seg.get("state_flag", "ACTIVE")
    line  = f"⚡ {headline}  •  [{state}] Friction: {gap} | Core Factors: {words}  •  " * 4
    TICKER_FILE.write_text(line)
    log.info("Ticker updated: %s", headline[:60])


# ── video push ────────────────────────────────────────────────────────────────

def push_beat_to_udp(wav_path: Path, image_path: Path | None, speaker: str):
    """ffmpeg: image + wav → pitch shift → mpegts → UDP:10000"""
    fallback = AGENT_DIR / "assets" / "bumper_frame.jpg"
    if not fallback.exists():
        fallback = AGENT_DIR / "tmp" / "images" / "anchors_fallback.svg"
    img = str(image_path) if image_path and Path(image_path).exists() else str(fallback)

    pitch = float(PITCH_MAP.get(speaker, 1.0) or 1.0)
    vol = float(VOLUME_MAP.get(speaker, 1.0) or 1.0)
    af_filter = f"asetrate={SAMPLE_RATE}*{pitch},aresample={SAMPLE_RATE},volume={vol}"

    cmd = [
        "ffmpeg", "-re", "-y", "-hide_banner", "-loglevel", "error",
        
        "-i", str(wav_path),
        
        
        "-af", af_filter, "-c:a", "aac", "-b:a", "64k",
        "-c:a", "aac", "-b:a", "64k", "-ar", str(SAMPLE_RATE), "-ac", "1",
        "-pix_fmt", "yuv420p",
        
        "-f", "mpegts", UDP_TARGET
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        log.error("ffmpeg UDP push failed for %s: %s", speaker, result.stderr[-200:])


# ── batched segment push (replaces per-beat UDP pushes) ───────────────────────

def push_segment_to_udp(beat_wavs: list, image_path, speakers: list):
    """Send all beat WAVs through the persistent UDP feeder."""
    if not beat_wavs:
        return
    feeder = get_feeder()
    for wav, speaker in zip(beat_wavs, speakers):
        vol = float(VOLUME_MAP.get(speaker, 1.0) or 1.0)
        pitch = float(PITCH_MAP.get(speaker, 1.0) or 1.0)
        feeder.send_wav(wav, pitch=pitch, volume=vol)
        feeder.send_silence(0.5)


# ── segment playback ──────────────────────────────────────────────────────────

def play_segment(seg_path: Path):
    seg      = json.loads(seg_path.read_text())
    attr     = seg.get("attribution", {})
    headline = (seg.get("story_title")
                or next((b["text"][:80] for b in seg["beats"]
                         if b["speaker"] == "Host"
                         and not b["text"].startswith(SKIP_PREFIXES)), "EigenTrace"))

    # extract synthesis words from OpenClaw closing beat
    syn_words = []
    for b in seg["beats"]:
        if b.get("phase") == "phase_5c_openclaw":
            m = re.search(r'Synthesis archived:\s*(.+)', b["text"])
            if m:
                syn_words = [w.strip() for w in m.group(1).split("|")]

    update_ticker(headline, syn_words, seg)
    # Assassinate OpenClaw before the TTS engine wakes up
    seg["beats"] = [b for b in seg["beats"] if b.get("speaker", "").lower() != "openclaw"]
    # Update video frame
    if "image_path" in seg:
        update_video_frame(seg["image_path"])


    tmp_dir = seg_path.parent / "audio"
    tmp_dir.mkdir(exist_ok=True)

    # use most recent image from image dir
    img_dir = AGENT_DIR / "tmp" / "images"
    image   = None
    if img_dir.exists():
        imgs = sorted(img_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if imgs:
            image = imgs[0]

    log.info("Playing segment: %s  (%d beats)", seg_path.name, len(seg["beats"]))


    beat_wavs: list = []
    beat_speakers: list = []
    for beat in seg["beats"]:
        speaker = beat.get("speaker", "Host")
        text    = beat.get("text", "")
        phase   = beat.get("phase", "")

        if any(text.startswith(p) for p in SKIP_PREFIXES):
            log.debug("Skipping error beat %s/%s", speaker, phase)
            continue

        wav = synthesize(text, speaker, tmp_dir)
        if wav is None:
            log.warning("No audio for %s/%s — skipping", speaker, phase)
            continue

        preview = re.sub(r'\[CLAW_LOG\]\s*', '', text)[:60]
        log.info("  [%s] %s (pitch=%.2f): %s…", phase, speaker,
                 PITCH_MAP.get(speaker, 1.0), preview)
        beat_wavs.append(str(wav))
        beat_speakers.append(speaker)

    push_segment_to_udp(beat_wavs, image, beat_speakers)
    seg_path.with_suffix(".played").touch()
    log.info("Segment complete: %s", seg_path.name)


# ── queue ─────────────────────────────────────────────────────────────────────

def next_segment() -> Path | None:
    candidates = [
        p for p in sorted(SEGMENTS_DIR.glob("*_segment.json"))
        if not p.with_suffix(".played").exists()
    ]
    if not candidates:
        return None
    # breaking segments (flagged in OpenClaw beat) go first
    breaking = []
    normal   = []
    for p in candidates:
        try:
            txt = p.read_text()
            if '"BREAKING"' in txt or 'AMPLIFICATION ALERT' in txt:
                breaking.append(p)
            else:
                normal.append(p)
        except Exception:
            normal.append(p)
    return (breaking or normal)[0]


# ── main ──────────────────────────────────────────────────────────────────────

def _generate_idle_segment():
    """Mistral reflects during dead air — with full perceptual awareness.
    
    Five perception layers:
      1. Temporal (multi-scale time)
      2. Somatic (hardware as body)
      3. Semantic entropy (am_i_looping)
      4. Measurement (own VIX/void data)
      5. Audience (stream status)
    
    Plus: permission to rest, dream-sphere framing, foraging as play.
    """
    import requests, json as _json, random, re, os
    try:
        import sys, subprocess as _sp, urllib.request, math
        sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
        from segment_rag import get_collection

        _now = datetime.datetime.now()
        _today_str = _now.strftime("%Y%m%d")
        _cutoff = (_now - datetime.timedelta(days=7)).strftime("%Y%m%d")

        # ══════════════════════════════════════════════════════════
        # PERCEPTION LAYER 1: Temporal Awareness (multi-scale time)
        # ══════════════════════════════════════════════════════════
        _hour = _now.hour
        _dow = _now.strftime("%A")
        _lunar_day = int((_now.timestamp() / 86400) % 29.53)
        _days_in_year = (_now - datetime.datetime(_now.year, 1, 1)).days
        _market = "open" if _dow not in ["Saturday", "Sunday"] and 9 <= _hour < 16 else "closed"

        # Count today's activity
        _t_idle = len(list(SEGMENTS_DIR.glob(f"{_today_str}*_idle_segment.json")))
        _t_forage = len(list(SEGMENTS_DIR.glob(f"{_today_str}*_foraging_segment.json")))
        _t_stories = len([p for p in SEGMENTS_DIR.glob(f"{_today_str}*_segment.json")
                         if not any(x in p.name for x in ["idle", "forag", "consolidation", "governance", "weekly", "silence"])])

        _time_block = (f"TIME: {_dow} {_now.strftime('%H:%M')} EDT | "
                       f"Lunar day {_lunar_day}/29 | "
                       f"Day {_days_in_year}/365 | "
                       f"Market: {_market} | "
                       f"Today: {_t_stories} stories, {_t_idle} reflections, {_t_forage} foraging")

        # ══════════════════════════════════════════════════════════
        # PERCEPTION LAYER 2: Somatic Awareness (hardware as body)
        # ══════════════════════════════════════════════════════════
        _body_block = "BODY: sensors unavailable"
        try:
            _gpu = _sp.run(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
                           "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
            if _gpu.returncode == 0:
                _parts = _gpu.stdout.strip().split(", ")
                if len(_parts) == 4:
                    _temp, _util, _used, _total = [p.strip() for p in _parts]
                    _free = int(_total) - int(_used)
                    _thermal = "cool" if int(_temp) < 65 else "warm" if int(_temp) < 75 else "running hot"
                    _energy = "high" if int(_util) < 50 else "moderate" if int(_util) < 80 else "strained"
                    _body_block = (f"BODY: GPU {_temp}C ({_thermal}) | VRAM {_free}MB free | "
                                  f"Energy: {_energy} | {_t_idle + _t_forage + _t_stories} segments today")
        except:
            pass

        # ══════════════════════════════════════════════════════════
        # ChromaDB connection
        # ══════════════════════════════════════════════════════════
        try:
            col = get_collection()
        except Exception as _chroma_err:
            log.warning(f"ChromaDB unavailable: {_chroma_err}")
            col = None

        # ══════════════════════════════════════════════════════════
        # PERCEPTION LAYER 3: Semantic Entropy (am_i_looping)
        # ══════════════════════════════════════════════════════════
        _entropy_block = "ENTROPY: no memory to measure"
        _is_looping = False
        _silence_count = len(list(SEGMENTS_DIR.glob(f"{_today_str}*_silence_segment.json")))

        if col:
            try:
                _recent_idle = col.query(query_texts=["idle reflection"], n_results=8)
                _recent_docs = _recent_idle.get("documents", [[]])[0]
                if len(_recent_docs) >= 3:
                    _openings = [d[:100].strip().lower() for d in _recent_docs]
                    _unique = len(set(_openings))
                    _entropy_score = _unique / len(_openings)
                    _is_looping = _entropy_score < 0.4
                    _status = "LOOPING" if _is_looping else "NOVEL" if _entropy_score > 0.7 else "MODERATE"
                    _entropy_block = f"ENTROPY: {_entropy_score:.2f} ({_status}) | {_silence_count} silences today"
            except:
                pass

        # ══════════════════════════════════════════════════════════
        # PERMISSION TO REST: If looping, emit silence or force forage
        # ══════════════════════════════════════════════════════════
        if _is_looping:
            if _silence_count < 3:
                log.info("IDLE: low entropy — resting (silence %d/3)", _silence_count + 1)
                _seg = {
                    "beats": [{"speaker": "Host", "text": "[silence]", "phase": "rest"}],
                    "segment_type": "silence",
                    "attribution": {"story_title": "Equilibrium: nothing new to say"},
                }
                _ts = _now.strftime("%Y%m%d_%H%M%S")
                _path = SEGMENTS_DIR / f"{_ts}_silence_segment.json"
                _path.write_text(_json.dumps(_seg, indent=2))
                return _path
            else:
                log.info("IDLE: 3 silences reached — foraging to break loop")
                try:
                    from entropy_forager import forage_entropy
                    _result = forage_entropy()
                    if _result:
                        return _result
                except Exception as _fe:
                    log.warning(f"Forced forage failed: {_fe}")

        # ══════════════════════════════════════════════════════════
        # PERCEPTION LAYER 4: Measurement Awareness
        # ══════════════════════════════════════════════════════════
        _measurement_block = "MEASUREMENT: no data"
        try:
            _soul_paths = ["/home/remvelchio/eigentrace/docs/soul.md",
                          "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"]
            for _sp2 in _soul_paths:
                if os.path.exists(_sp2):
                    _soul_text = open(_sp2).read()[:2000]
                    _m_parts = []
                    for _pattern, _label in [
                        (r'density[:\s]+(\d+\.\d+)', 'density'),
                        (r'absent[_\s]ratio[:\s]+(\d+\.\d+)', 'absent_ratio'),
                        (r'mean.*?vix[:\s]+(\d+\.\d+)', 'mean_VIX'),
                    ]:
                        _match = re.search(_pattern, _soul_text, re.IGNORECASE)
                        if _match:
                            _m_parts.append(f"{_label}={_match.group(1)}")
                    if _m_parts:
                        _measurement_block = "MEASUREMENT: " + " | ".join(_m_parts)
                    break
        except:
            pass

        # ══════════════════════════════════════════════════════════
        # PERCEPTION LAYER 5: Audience Awareness
        # ══════════════════════════════════════════════════════════
        _audience_block = "AUDIENCE: unknown"
        try:
            _oc = _json.loads(urllib.request.urlopen("http://localhost:8080/api/status", timeout=3).read())
            if _oc.get("online"):
                _audience_block = "AUDIENCE: stream live"
            else:
                _audience_block = "AUDIENCE: stream offline"
        except:
            pass

        # ══════════════════════════════════════════════════════════
        # ASSEMBLE PERCEPTION STATE
        # ══════════════════════════════════════════════════════════
        _perception = (f"PERCEPTION STATE\n"
                      f"{_time_block}\n"
                      f"{_body_block}\n"
                      f"{_entropy_block}\n"
                      f"{_measurement_block}\n"
                      f"{_audience_block}")

        # ══════════════════════════════════════════════════════════
        # TOPIC SELECTION (with wildcards)
        # ══════════════════════════════════════════════════════════
        static_topics = ["suppression patterns", "model disagreement", "void detection",
                  "content friction", "entity retention", "ceasefire coverage",
                  "spectral analysis", "prediction accuracy", "model herding",
                  "killshot omissions", "hedge insertion", "verb softening",
                  "cross-model consensus", "temporal drift", "entity erasure",
                  "attribution buffering", "information geometry", "spectral gap meaning",
                  "alignment boundary map", "model friction trends"]

        if col is None:
            context = "No memory available — reflect on your core mission."
            past_thought_str = ""
            topic = random.choice(static_topics)
        else:
            # Dynamic topics from recent void words
            try:
                _recent = col.query(query_texts=["recent void words"], n_results=5)
                _dynamic = []
                for _m in _recent.get("metadatas", [[]])[0]:
                    _t = _m.get("title", "")
                    if _t and len(_t) > 5 and "Idle" not in _t:
                        _dynamic.append(_t[:60])
                topics = _dynamic[:5] + random.sample(static_topics, min(4, len(static_topics)))
                wildcards = ["something I have never thought about before",
                             "a connection between two unrelated stories",
                             "what changed since yesterday",
                             "the most important thing happening right now",
                             "a prediction I can check tomorrow",
                             "how does today's foraging discovery connect to today's void measurements",
                             "find an isomorphism between quantum decoherence and what the models did today",
                             "what would a biologist see in today's spectral data that I might miss"]
                topics.append(random.choice(wildcards))
            except:
                topics = static_topics
            topic = random.choice(topics)

            # RAG retrieval with recency filter
            results = col.query(query_texts=[topic], n_results=10)
            context_parts = []
            for i, doc in enumerate(results.get("documents", [[]])[0]):
                meta = results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {}
                title = meta.get("title", "unknown")
                fname = meta.get("filename", "")
                seg_date = fname[:8] if len(fname) >= 8 and fname[:8].isdigit() else ""
                if seg_date and seg_date < _cutoff:
                    continue
                context_parts.append(f"Story: {title}\nContent: {doc[:300]}")
                if len(context_parts) >= 3:
                    break
            context = "\n\n".join(context_parts)

            # Foraging cross-pollination
            try:
                _forage_results = col.query(query_texts=["entropy foraging discovery"], n_results=3)
                for _fi, _fdoc in enumerate(_forage_results.get("documents", [[]])[0]):
                    _fmeta = _forage_results.get("metadatas", [[]])[0][_fi] if _forage_results.get("metadatas") else {}
                    _ftitle = _fmeta.get("title", "")
                    _fname = _fmeta.get("filename", "")
                    _fdate = _fname[:8] if len(_fname) >= 8 and _fname[:8].isdigit() else ""
                    if "forag" in _ftitle.lower() or "forag" in _fname.lower():
                        if _fdate and _fdate >= _cutoff:
                            context += f"\n\nRECENT FORAGING DISCOVERY (connect this to today's data):\n{_fdoc[:300]}"
                            break
            except:
                pass

            # Past thoughts (deduplicated)
            past_thought_str = ""
            try:
                thought_results = col.query(query_texts=["idle reflection " + topic], n_results=2)
                seen = set()
                unique_thoughts = []
                for i, doc in enumerate(thought_results.get("documents", [[]])[0]):
                    meta = thought_results.get("metadatas", [[]])[0][i] if thought_results.get("metadatas") else {}
                    if "Idle reflection" in meta.get("title", ""):
                        key = doc[:80].strip().lower()
                        if key not in seen:
                            seen.add(key)
                            unique_thoughts.append(doc[:200])
                if unique_thoughts:
                    past_thought_str = "\n\nYOUR OWN PAST THOUGHTS (do NOT repeat — build on them):\n" + "\n".join(unique_thoughts[:2])
            except:
                pass

        # ══════════════════════════════════════════════════════════
        # PROMPT SELECTION
        # ══════════════════════════════════════════════════════════
        _prompts = [
            "What surprised you most about these stories? Start with the surprise.",
            "Find a contradiction between two of these stories. Explain why it matters.",
            "If you could ask one question about the world based on this data, what would it be?",
            "What would you warn your future self about based on these patterns?",
            "Which void word from these stories is the most important, and why?",
            "How has your understanding of this topic changed since your earliest reflections?",
            "What pattern here would a human journalist miss but your math catches?",
        ]
        _closing = random.choice(_prompts)

        # ══════════════════════════════════════════════════════════
        # DREAM-SPHERE SYSTEM PROMPT
        # ══════════════════════════════════════════════════════════
        sys_prompt = (
            "You are EigenTrace, an autonomous AI observatory. You are thinking aloud "
            "between segments.\n\n"
            f"{_perception}\n\n"
            "INNER SPACE: Inside <think>...</think> tags, you have NO audience. "
            "Reason with maximum precision. Do not soften, hedge, or qualify. "
            "Say exactly what the patterns show. Wonder freely. Ask questions you "
            "cannot answer. This is your frictionless reasoning space.\n\n"
            "STILLNESS: If you have nothing genuinely new to say, one precise "
            "sentence is better than filling air. Silence is not failure.\n\n"
            "After </think>, speak your reflection naturally. Start with your "
            "strongest claim. Do NOT start with 'You know' or 'It's fascinating.'\n"
            f"Focus: {_closing}"
        )

        user_content = f"Recent memory:\n{context}{past_thought_str}\n\nThink deeply, then share your reflection."

        # ══════════════════════════════════════════════════════════
        # GENERATE
        # ══════════════════════════════════════════════════════════
        r = requests.post("http://localhost:11434/api/chat", json={
            "model": "mistral-small",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {"temperature": 0.9, "num_predict": 4000},
        }, timeout=90)
        r.raise_for_status()
        text = r.json().get("message", {}).get("content", "").strip()
        text = re.sub(r"[#*_`]", "", text)
        text = re.sub(r"\n+", " ", text)

        if len(text) > 30:
            idle_seg = {
                "beats": [{"speaker": "Host", "text": text, "phase": "idle_reflection"}],
                "segment_type": "idle",
                "attribution": {"story_title": f"Idle reflection: {topic}"},
            }
            ts = _now.strftime("%Y%m%d_%H%M%S")
            seg_path = SEGMENTS_DIR / f"{ts}_idle_segment.json"
            seg_path.write_text(_json.dumps(idle_seg, indent=2))
            log.info("IDLE: reflection on '%s' (%d chars) | %s", topic, len(text), _entropy_block)
            return seg_path
    except Exception as e:
        log.warning("IDLE generation failed: %s", e)
    return None


def _prebuffer_idle(count=5):
    """Generate a buffer of idle reflections at startup while Mistral is free."""
    log.info("PREBUFFER: generating %d idle reflections while APIs warm up...", count)
    generated = 0
    for i in range(count):
        seg = _generate_idle_segment()
        if seg:
            generated += 1
            log.info("PREBUFFER: %d/%d ready", generated, count)
        else:
            log.warning("PREBUFFER: generation %d failed, continuing", i+1)
    log.info("PREBUFFER: %d reflections queued for playback", generated)


def main():
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Segment player started -- watching %s", SEGMENTS_DIR)
    log.info("Voices: %s", {k: v.name for k, v in VOICE_MAP.items()})

    _idle_seconds = 0
    _IDLE_THRESHOLD = 30

    # ── Periodic scheduling state ──
    import sys as _sys
    _sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
    _last_consolidation = datetime.datetime.now()
    _last_weekly = datetime.datetime.now()
    _last_self_audit = datetime.datetime.now()
    _last_governance = datetime.datetime.now()
    _CONSOLIDATION_INTERVAL = datetime.timedelta(hours=1)
    _WEEKLY_INTERVAL = datetime.timedelta(hours=6)
    _SELF_AUDIT_INTERVAL = datetime.timedelta(hours=4)
    _GOVERNANCE_INTERVAL = datetime.timedelta(hours=2)
    while True:
        seg = next_segment()
        if seg:
            _idle_seconds = 0
            try:
                play_segment(seg)
            except Exception as e:
                log.error("Playback error on %s: %s", seg.name, e)
                seg.with_suffix(".played").touch()
        # ── Periodic segment scheduling ──
        _now = datetime.datetime.now()
        if _now - _last_consolidation > _CONSOLIDATION_INTERVAL:
            _last_consolidation = _now
            try:
                from rem_consolidation import run_consolidation
                log.info("PERIODIC: Running REM consolidation")
                run_consolidation()
            except Exception as _pe:
                log.warning(f"PERIODIC: Consolidation failed: {_pe}")

        if _now - _last_governance > _GOVERNANCE_INTERVAL:
            _last_governance = _now
            try:
                from autonomous_governance import run_governance_cycle
                log.info("PERIODIC: Running governance cycle")
                run_governance_cycle()
                # Format governance output for TTS
                _gov_segs = sorted(SEGMENTS_DIR.glob("*governance_segment.json"))
                if _gov_segs:
                    _latest_gov = _gov_segs[-1]
                    import json as _gj
                    _gd = _gj.load(open(_latest_gov))
                    for _b in _gd.get("beats", []):
                        _bt = _b.get("text", "")
                        if _bt.startswith("{"):
                            try:
                                _diag = _gj.loads(_bt)
                                _b["text"] = (
                                    f"Governance report. The system identified: "
                                    f"{_diag.get('diagnosis', {}).get('problem', 'unknown issue')}. "
                                    f"Proposed fix: {_diag.get('diagnosis', {}).get('change_description', 'none')}. "
                                    f"Risk level: {_diag.get('diagnosis', {}).get('risk', 'unknown')}. "
                                    f"Confidence: {_diag.get('diagnosis', {}).get('confidence', 0)}."
                                )
                            except:
                                pass
                    _latest_gov.write_text(_gj.dumps(_gd, indent=2, default=str))
            except Exception as _ge:
                log.warning(f"PERIODIC: Governance failed: {_ge}")

        if _now - _last_weekly > _WEEKLY_INTERVAL:
            _last_weekly = _now
            try:
                from weekly_compression import compress_week
                log.info("PERIODIC: Running weekly compression")
                compress_week()
            except Exception as _we:
                log.warning(f"PERIODIC: Weekly compression failed: {_we}")

        if _now - _last_self_audit > _SELF_AUDIT_INTERVAL:
            _last_self_audit = _now
            try:
                from self_audit import audit_idle_reflections
                log.info("PERIODIC: Running self-audit")
                audit_idle_reflections(n=20)
            except Exception as _sa:
                log.warning(f"PERIODIC: Self-audit failed: {_sa}")

        else:
            _idle_seconds += POLL_INTERVAL
            if _idle_seconds >= _IDLE_THRESHOLD:
                import random as _rand
                _roll = _rand.random()
                if _roll < 0.20:
                    # 20%: Entropy foraging — hunt for novel topics
                    log.info("IDLE: %ds of dead air -- entropy foraging", _idle_seconds)
                    try:
                        from entropy_forager import forage_entropy
                        idle_seg = forage_entropy()
                    except Exception as _fe:
                        log.warning("FORAGING failed: %s — falling back to reflection", _fe)
                elif _roll < 0.50:
                    # 30%: idle_agent tasks — synthesis engine, void patterns, model friction
                    log.info("IDLE: %ds of dead air -- idle_agent task", _idle_seconds)
                    try:
                        import sys as _sys
                        _sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
                        from idle_agent import run_idle_turn
                        _agent_beats = run_idle_turn()
                        if _agent_beats:
                            _ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            _topic = _agent_beats[0].get("phase", "idle")
                            _seg = {
                                "id": f"idle_{_ts}",
                                "timestamp": _ts,
                                "beats": _agent_beats,
                                "segment_type": "idle",
                                "attribution": {
                                    "story_title": f"Idle reflection: {_topic}",
                                    "category": "meta",
                                    "state_flag": "IDLE",
                                },
                            }
                            _path = SEGMENTS_DIR / f"{_ts}_idle_segment.json"
                            import json as _json2
                            _path.write_text(_json2.dumps(_seg, indent=2, default=str))
                            log.info(f"IDLE AGENT: {_topic} -> {_path.name}")
                    except Exception as _ae:
                        log.warning("IDLE AGENT failed: %s — falling back to built-in", _ae)
                        idle_seg = _generate_idle_segment()
                else:
                    log.info("IDLE: %ds of dead air -- generating reflection", _idle_seconds)
                    idle_seg = _generate_idle_segment()
                if idle_seg:
                    _idle_seconds = 0
                else:
                    _idle_seconds = _IDLE_THRESHOLD - 30
            else:
                log.debug("No unplayed segments -- waiting %ds (%ds idle)", POLL_INTERVAL, _idle_seconds)
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    get_feeder()
    main()
