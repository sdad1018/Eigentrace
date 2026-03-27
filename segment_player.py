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
UDP_TARGET    = "udp://127.0.0.1:10000?pkt_size=1316"
SAMPLE_RATE   = 22050
PIPER_BIN     = "/home/remvelchio/.local/bin/piper"
MODELS_DIR    = AGENT_DIR / "models" / "piper"
POLL_INTERVAL = 10

# Only skip genuine errors — OpenClaw SPEAKS
SKIP_PREFIXES = ("[API ERROR", "[HOST ERROR", "[no response logged]", "[no response]")

VOICE_MAP = {
    "Host":      MODELS_DIR / "en_US-lessac-medium.onnx",
    "Gemini":    MODELS_DIR / "en_US-bryce-medium.onnx",
    "ChatGPT":   MODELS_DIR / "en_US-kristin-medium.onnx",
    "DeepSeek":  MODELS_DIR / "en_US-amy-medium.onnx",
    "Grok":      MODELS_DIR / "en_US-lessac-medium.onnx",
    "Claude":    MODELS_DIR / "en_US-arctic-medium.onnx",
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
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
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
                try:
                    self.proc.stdin.write(chunk)
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
            time.sleep(0.1)

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

# ── TTS ───────────────────────────────────────────────────────────────────────

def synthesize(text: str, speaker: str, tmp_dir: Path) -> Path | None:
    text = text.strip()
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
        log.error("Piper failed for %s: %s", speaker, result.stderr[:120])
        return None
    return out


# ── ticker ────────────────────────────────────────────────────────────────────

def update_ticker(headline: str, synthesis_words: list):
    words = " | ".join(synthesis_words) if synthesis_words else ""
    line  = f"⚡ {headline}  •  {words}  •  " * 6
    TICKER_FILE.write_text(line)
    log.info("Ticker updated: %s", headline[:60])


# ── video push ────────────────────────────────────────────────────────────────

def push_beat_to_udp(wav_path: Path, image_path: Path | None, speaker: str):
    """ffmpeg: image + wav → pitch shift → mpegts → UDP:10000"""
    fallback = AGENT_DIR / "assets" / "bumper_frame.jpg"
    if not fallback.exists():
        fallback = AGENT_DIR / "tmp" / "images" / "anchors_fallback.svg"
    img = str(image_path) if image_path and Path(image_path).exists() else str(fallback)

    pitch = PITCH_MAP.get(speaker, 1.0)
    vol = VOLUME_MAP.get(speaker, 1.0)
    af_filter = f"asetrate={SAMPLE_RATE}*{pitch},aresample={SAMPLE_RATE},volume={vol}"

    cmd = [
        "ffmpeg", "-re", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", img,
        "-i", str(wav_path),
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-vf", "scale=1024:576",
        "-af", af_filter,
        "-c:a", "aac", "-b:a", "64k", "-ar", str(SAMPLE_RATE), "-ac", "1",
        "-pix_fmt", "yuv420p",
        "-shortest",
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
        vol = VOLUME_MAP.get(speaker, 1.0)
        pitch = PITCH_MAP.get(speaker, 1.0)
        feeder.send_wav(wav, pitch=pitch, volume=vol)


# ── segment playback ──────────────────────────────────────────────────────────

def play_segment(seg_path: Path):
    seg      = json.loads(seg_path.read_text())
    attr     = seg.get("attribution", {})
    headline = (attr.get("story_title")
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

    update_ticker(headline, syn_words)

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

def main():
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Segment player started — watching %s", SEGMENTS_DIR)
    log.info("Voices: %s", {k: v.name for k, v in VOICE_MAP.items()})

    while True:
        seg = next_segment()
        if seg:
            try:
                play_segment(seg)
            except Exception as e:
                log.error("Playback error on %s: %s", seg.name, e)
                seg.with_suffix(".played").touch()
        else:
            # Agent gets the mic during dead air
            try:
                from idle_agent import run_idle_turn, _has_pending_segment
                idle_beats = run_idle_turn()
                if idle_beats:
                    for beat in idle_beats:
                        # Check for incoming news before each beat
                        if _has_pending_segment():
                            log.info("News incoming — yielding mic")
                            break
                        speaker = beat.get("speaker", "Host")
                        text_content = beat.get("text", "")
                        phase = beat.get("phase", "idle")
                        if not text_content:
                            continue
                        voice = VOICE_MAP.get(speaker, VOICE_MAP["Host"])
                        pitch = PITCH_MAP.get(speaker, 1.0)
                        feeder = get_feeder()
                        wav = synthesize(text_content, speaker, Path("/home/remvelchio/eigentrace/tmp/segments/audio"))
                        if wav:
                            log.info("  [%s] %s (pitch=%.2f): %s",
                                     phase, speaker, pitch,
                                     text_content[:60] + "..." if len(text_content) > 60 else text_content)
                            feeder.send_wav(wav, pitch=pitch)
                            time.sleep(1)  # brief pause between beats
                else:
                    time.sleep(POLL_INTERVAL)
            except ImportError:
                log.debug("idle_agent not available — waiting %ds", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                log.warning("Idle agent error: %s", e)
                time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

