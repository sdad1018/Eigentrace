#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# install.sh — set up EigenTrace on a fresh Ubuntu 22.04 / WSL2 box
# ═══════════════════════════════════════════════════════════════════════════
#
# Reproduces the production host as of 2026-09-10:
#   Python 3.10 + `pip install --user` packages pinned in requirements.lock.txt
#   (torch 2.5.1+cu121), NLTK data, Piper TTS 1.4.1 + the four voices
#   segment_player.py uses, Ollama + mistral-small, Owncast 0.2.4.
#
# Usage:
#   git clone https://github.com/sdad1018/Eigentrace && cd Eigentrace && bash install.sh
#
# Environment knobs:
#   EIGENTRACE_RUNTIME  runtime data dir           (default: $HOME/eigentrace)
#   OWNCAST_VERSION     Owncast release to install  (default: 0.2.4 = production)
#   OLLAMA_MODEL        model to pull               (default: mistral-small)
#   SKIP_APT=1 SKIP_PIP=1 SKIP_OLLAMA=1 SKIP_OWNCAST=1   skip a stage
#
# Do not run this on the production host while the broadcast is live.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

EIGENTRACE_RUNTIME=${EIGENTRACE_RUNTIME:-$HOME/eigentrace}
OWNCAST_VERSION=${OWNCAST_VERSION:-0.2.4}
OLLAMA_MODEL=${OLLAMA_MODEL:-mistral-small}
OWNCAST_DIR="$HOME/owncast"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPER_BIN="$HOME/.local/bin/piper"
PIPER_DIR="$EIGENTRACE_RUNTIME/models/piper"
PIPER_VOICES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
LOG_DIR="$EIGENTRACE_RUNTIME/tmp/logs"

# Piper voices referenced by VOICE_MAP in segment_player.py (name -> path under the
# rhasspy/piper-voices repo). lessac = Host/Grok/Claude/default, kristin = Gemini/ChatGPT,
# amy = DeepSeek, danny-low = OpenClaw.
PIPER_VOICES=(
    "en_US-lessac-medium en/en_US/lessac/medium"
    "en_US-kristin-medium en/en_US/kristin/medium"
    "en_US-amy-medium en/en_US/amy/medium"
    "en_US-danny-low en/en_US/danny/low"
)

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $1"; }
warn() { echo -e "  ${YEL}⚠${RST} $1"; }
fail() { echo -e "  ${RED}✗${RST} $1"; }
hdr()  { echo -e "\n${CYN}[$1]${RST}"; }

SUDO=""
if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else
        echo "Need root or sudo for apt." >&2; exit 1
    fi
fi

export PATH="$HOME/.local/bin:$PATH"
export CUDA_VISIBLE_DEVICES=""          # nothing in this script may touch the GPU

echo -e "${CYN}EigenTrace installer${RST}"
echo "  repo:     $REPO"
echo "  runtime:  $EIGENTRACE_RUNTIME"
echo "  owncast:  $OWNCAST_DIR (v$OWNCAST_VERSION)"
echo "  ollama:   $OLLAMA_MODEL"

# ══════════════════════════════════════════════════════════════════════════
# 1. apt packages
# ══════════════════════════════════════════════════════════════════════════
hdr "1/7 apt packages"
if [[ "${SKIP_APT:-0}" == "1" ]]; then
    warn "SKIP_APT=1 — skipping"
else
    $SUDO apt-get update -y
    $SUDO apt-get install -y ffmpeg python3-pip python3-venv curl git unzip ca-certificates
    ok "ffmpeg python3-pip python3-venv curl git unzip"
fi

# ══════════════════════════════════════════════════════════════════════════
# 2. Python packages (pinned to production)
# ══════════════════════════════════════════════════════════════════════════
hdr "2/7 Python packages"
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [[ "$PYVER" != "3.10" ]]; then
    warn "python3 is $PYVER; production runs 3.10.12 — the lock was resolved for cp310 wheels"
else
    ok "python3 $PYVER"
fi
if [[ "${SKIP_PIP:-0}" == "1" ]]; then
    warn "SKIP_PIP=1 — skipping"
else
    python3 -m pip install --user --upgrade pip
    python3 -m pip install --user -r "$REPO/requirements.lock.txt"
    ok "requirements.lock.txt installed (--user)"
    # NLTK data used by eigentrace_math (word_tokenize / pos_tag) and confront_keeper_v3 (words)
    if python3 -m nltk.downloader -q punkt punkt_tab averaged_perceptron_tagger averaged_perceptron_tagger_eng words; then
        ok "NLTK data (punkt, punkt_tab, averaged_perceptron_tagger[_eng], words)"
    else
        warn "NLTK data download failed — rerun: python3 -m nltk.downloader punkt punkt_tab averaged_perceptron_tagger averaged_perceptron_tagger_eng words"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# 3. Runtime directories
# ══════════════════════════════════════════════════════════════════════════
hdr "3/7 Runtime directories"
mkdir -p "$EIGENTRACE_RUNTIME"/tmp/segments \
         "$EIGENTRACE_RUNTIME"/tmp/logs \
         "$EIGENTRACE_RUNTIME"/tmp/images \
         "$EIGENTRACE_RUNTIME"/tmp/pids \
         "$EIGENTRACE_RUNTIME"/tmp/chromadb \
         "$EIGENTRACE_RUNTIME"/models/piper \
         "$EIGENTRACE_RUNTIME"/assets \
         "$EIGENTRACE_RUNTIME"/stream \
         "$EIGENTRACE_RUNTIME"/docs
ok "$EIGENTRACE_RUNTIME/{tmp/segments,tmp/logs,tmp/images,tmp/pids,tmp/chromadb,models/piper,assets,stream,docs}"
if [[ -d "$REPO/assets" ]]; then
    cp -n "$REPO"/assets/* "$EIGENTRACE_RUNTIME/assets/" 2>/dev/null || true
    ok "copied repo assets/ into runtime assets/ (existing files kept)"
fi

# ══════════════════════════════════════════════════════════════════════════
# 4. Piper voices
# ══════════════════════════════════════════════════════════════════════════
hdr "4/7 Piper voices -> $PIPER_DIR"
for entry in "${PIPER_VOICES[@]}"; do
    name="${entry%% *}"; sub="${entry##* }"
    for ext in onnx onnx.json; do
        dest="$PIPER_DIR/$name.$ext"
        if [[ -s "$dest" ]]; then
            ok "$name.$ext (present)"
        else
            curl -fL --retry 3 --progress-bar -o "$dest.part" "$PIPER_VOICES_BASE/$sub/$name.$ext"
            mv "$dest.part" "$dest"
            ok "$name.$ext"
        fi
    done
done

# ══════════════════════════════════════════════════════════════════════════
# 5. Ollama + model
# ══════════════════════════════════════════════════════════════════════════
hdr "5/7 Ollama"
if [[ "${SKIP_OLLAMA:-0}" == "1" ]]; then
    warn "SKIP_OLLAMA=1 — skipping"
else
    if command -v ollama >/dev/null 2>&1; then
        ok "ollama present ($(ollama --version 2>/dev/null | head -1))"
    else
        curl -fsSL https://ollama.com/install.sh | sh
        ok "ollama installed"
    fi
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        # WSL2 without systemd: the install script cannot register a service, so serve by hand
        nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
        sleep 5
    fi
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        ok "ollama serving on :11434"
        ollama pull "$OLLAMA_MODEL"
        ok "pulled $OLLAMA_MODEL"
    else
        warn "ollama not reachable on :11434 — run 'ollama serve' then 'ollama pull $OLLAMA_MODEL'"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# 6. Owncast
# ══════════════════════════════════════════════════════════════════════════
hdr "6/7 Owncast -> $OWNCAST_DIR"
if [[ "${SKIP_OWNCAST:-0}" == "1" ]]; then
    warn "SKIP_OWNCAST=1 — skipping"
elif [[ -x "$OWNCAST_DIR/owncast" ]]; then
    ok "owncast binary present (not replaced)"
else
    mkdir -p "$OWNCAST_DIR"
    ZIP="$(mktemp -t owncast.XXXXXX.zip)"
    if curl -fL --retry 3 --progress-bar \
         -o "$ZIP" "https://github.com/owncast/owncast/releases/download/v${OWNCAST_VERSION}/owncast-${OWNCAST_VERSION}-linux-64bit.zip"; then
        unzip -o -q "$ZIP" -d "$OWNCAST_DIR"
        rm -f "$ZIP"
        chmod +x "$OWNCAST_DIR/owncast"
        ok "owncast v$OWNCAST_VERSION unpacked"
    else
        rm -f "$ZIP"
        warn "release zip download failed — falling back to the official install script (latest release)"
        (cd "$HOME" && curl -s https://owncast.online/install.sh | bash)
        ok "owncast installed by install.sh"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# 7. Pre-flight (mirrors ainn.sh)
# ══════════════════════════════════════════════════════════════════════════
hdr "7/7 Pre-flight"
ERRORS=0

# Critical files
for f in "$REPO/batch_producer.py" "$REPO/segment_player.py"; do
    if [[ -f "$f" ]]; then ok "$(basename "$f")"; else fail "Missing: $f"; ERRORS=$((ERRORS+1)); fi
done
# master.sh is not in the repo: it lives with the stream keys in $RUNTIME/stream (never committed)
if [[ -f "$EIGENTRACE_RUNTIME/stream/master.sh" ]]; then
    ok "stream/master.sh"
else
    warn "Missing: $EIGENTRACE_RUNTIME/stream/master.sh (the ffmpeg compositor; copy it in by hand — ainn.sh treats it as critical)"
fi

# eigentrace importable
if (cd "$REPO" && python3 -c "from eigentrace import score" 2>/dev/null); then
    ok "eigentrace importable"
else
    fail "eigentrace not importable"; ERRORS=$((ERRORS+1))
fi

# Production imports (CPU only; no tensors, no model loads)
if (cd "$REPO" && python3 - <<'PY' 2>/dev/null
import numpy, torch, chromadb, sentence_transformers, diffusers, transformers, spacy, nltk, wordfreq, trafilatura, rich, dotenv, httpx, requests, bs4, websocket
print("      numpy", numpy.__version__, "| torch", torch.__version__, "cuda", torch.version.cuda,
      "| chromadb", chromadb.__version__, "| sentence-transformers", sentence_transformers.__version__,
      "| diffusers", diffusers.__version__, "| spacy", spacy.__version__)
PY
); then
    ok "production imports"
else
    fail "a production import failed — run: python3 -c 'import numpy, torch, chromadb, sentence_transformers, diffusers, spacy, nltk, wordfreq, trafilatura, rich, dotenv, httpx, requests'"
    ERRORS=$((ERRORS+1))
fi
TORCH_CUDA="$(python3 -c 'import torch; print(torch.version.cuda or "cpu")' 2>/dev/null || echo unknown)"
if [[ "$TORCH_CUDA" == "12.1" ]]; then ok "torch CUDA build 12.1"; else warn "torch CUDA build is '$TORCH_CUDA' (production: 12.1)"; fi
if python3 -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null; then ok "spacy en_core_web_sm"; else warn "spacy model en_core_web_sm not loadable"; fi
if python3 -c "import nltk; nltk.data.find('tokenizers/punkt_tab'); nltk.data.find('taggers/averaged_perceptron_tagger_eng')" 2>/dev/null; then
    ok "NLTK data"
else
    warn "NLTK punkt_tab / averaged_perceptron_tagger_eng missing"
fi

# Piper
if [[ -x "$PIPER_BIN" ]]; then ok "Piper TTS ($PIPER_BIN)"; else fail "Piper not found at $PIPER_BIN"; ERRORS=$((ERRORS+1)); fi
for entry in "${PIPER_VOICES[@]}"; do
    name="${entry%% *}"
    if [[ -s "$PIPER_DIR/$name.onnx" && -s "$PIPER_DIR/$name.onnx.json" ]]; then ok "voice $name"; else fail "voice $name missing"; ERRORS=$((ERRORS+1)); fi
done

# Assets
for f in "$EIGENTRACE_RUNTIME/assets/bed_22050.wav" "$EIGENTRACE_RUNTIME/assets/bumper_frame.png"; do
    if [[ -f "$f" ]]; then ok "$(basename "$f")"; else warn "Missing: $(basename "$f") (copy into $EIGENTRACE_RUNTIME/assets)"; fi
done

# Owncast
if [[ -x "$OWNCAST_DIR/owncast" ]]; then ok "Owncast binary"; else fail "Owncast missing"; ERRORS=$((ERRORS+1)); fi

# Ollama
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama running"
    if ollama list 2>/dev/null | grep -q "^${OLLAMA_MODEL}"; then ok "model $OLLAMA_MODEL"; else warn "model $OLLAMA_MODEL not listed"; fi
else
    warn "Ollama not running"
fi

# ffmpeg
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg"; else fail "ffmpeg missing"; ERRORS=$((ERRORS+1)); fi

# Secrets live outside git
if [[ -f "$REPO/.env" ]]; then
    ok ".env present"
else
    warn "no $REPO/.env — create it with OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, XAI_API_KEY (see batch_producer.py); it is gitignored"
fi

# Hard-coded paths in the players
if [[ "$EIGENTRACE_RUNTIME" != "/home/remvelchio/eigentrace" ]]; then
    warn "EIGENTRACE_RUNTIME=$EIGENTRACE_RUNTIME but segment_player.py, segment_rag.py and entropy_forager.py hard-code /home/remvelchio/eigentrace"
    warn "  (batch_producer.py / idle_reflection.py honour SEGMENTS_DIR, IMAGES_DIR, TICKER_FILE; the others do not yet)"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
    fail "$ERRORS critical error(s) — fix before running ainn.sh"
    exit 1
fi
ok "Install complete. Next: bash ainn.sh   (start the broadcast)"
