#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# ainn.sh — Start the entire AINN broadcast
# ═══════════════════════════════════════════════════════════════════════════
#
# Architecture:
#   batch_producer.py → segment JSON + images
#   segment_player.py → TTS (Piper) → UDP:10000 + current_frame.png
#   master.sh         → composites frame + UDP audio + ticker + bed music
#                        → Owncast + Twitch + YouTube (single ffmpeg tee)
#
# Usage:
#   bash ainn.sh                # Start everything
#   bash ainn.sh stop           # Stop everything
#   bash ainn.sh status         # Health check
#   bash ainn.sh --no-images    # Skip SDXL in producer
#
# ═══════════════════════════════════════════════════════════════════════════

set -uo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'
CYN='\033[0;36m'; DIM='\033[0;90m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $1"; }
warn() { echo -e "  ${YEL}⚠${RST} $1"; }
fail() { echo -e "  ${RED}✗${RST} $1"; }
hdr()  { echo -e "\n${CYN}[$1]${RST}"; }

# ══════════════════════════════════════════════════════════════════════════
# PATHS — the two codebases
# ══════════════════════════════════════════════════════════════════════════
REPO="/mnt/c/Users/M4ISI/eigentrace"          # git repo: batch_producer, proxy_auditor, etc.
RUNTIME="/home/remvelchio/eigentrace"          # runtime: segment_player, stream/, models/, tmp/
OWNCAST_DIR="/home/remvelchio/owncast"

PID_DIR="$RUNTIME/tmp/pids"
LOG_DIR="$RUNTIME/tmp/logs"
SEGMENTS_DIR="$RUNTIME/tmp/segments"

# ══════════════════════════════════════════════════════════════════════════
# ENV
# ══════════════════════════════════════════════════════════════════════════
for envf in "$REPO/.env" "/home/remvelchio/agent/.env"; do
    [[ -f "$envf" ]] && { set -a; source "$envf"; set +a; }
done

# ══════════════════════════════════════════════════════════════════════════
# PARSE ARGS
# ══════════════════════════════════════════════════════════════════════════
ACTION="start"
EXTRA_PRODUCER_ARGS=""
for arg in "$@"; do
    case $arg in
        stop)        ACTION="stop" ;;
        status)      ACTION="status" ;;
        --no-images) EXTRA_PRODUCER_ARGS="$EXTRA_PRODUCER_ARGS --no-images" ;;
    esac
done

mkdir -p "$PID_DIR" "$LOG_DIR" "$SEGMENTS_DIR"

# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════
save_pid()  { echo "$2" > "$PID_DIR/$1.pid"; }
read_pid()  { cat "$PID_DIR/$1.pid" 2>/dev/null; }
is_alive()  { local p=$(read_pid "$1"); [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; }

kill_component() {
    local name="$1"
    local pid=$(read_pid "$name")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
        ok "Stopped $name (PID $pid)"
    fi
    rm -f "$PID_DIR/$name.pid"
}

# ══════════════════════════════════════════════════════════════════════════
# STOP
# ══════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "stop" ]]; then
    hdr "Stopping AINN"
    kill_component "producer"
    kill_component "player"
    kill_component "master"
    kill_component "owncast"
    pkill -f "batch_producer.py" 2>/dev/null || true
    pkill -f "segment_player.py" 2>/dev/null || true
    pkill -f "master.sh" 2>/dev/null || true
    pkill -f "ffmpeg.*tee.*flv" 2>/dev/null || true
    sleep 2
    pkill -f "owncast" 2>/dev/null || true
    ok "All components stopped"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "status" ]]; then
    hdr "AINN Status"
    echo ""

    for comp in owncast master player producer; do
        if is_alive "$comp"; then
            ok "$comp running (PID $(read_pid $comp))"
        else
            warn "$comp not running"
        fi
    done

    echo ""
    UNPLAYED=$(find "$SEGMENTS_DIR" -name "*_segment.json" 2>/dev/null | while read f; do
        [[ ! -f "${f%.json}.played" ]] && echo x
    done | wc -l)
    TOTAL=$(find "$SEGMENTS_DIR" -name "*_segment.json" 2>/dev/null | wc -l)
    echo "  Queue: $UNPLAYED unplayed / $TOTAL total segments"

    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        LOADED=$(curl -sf http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
ms=d.get('models',[])
print(', '.join(m['name'] for m in ms) if ms else 'none loaded')
" 2>/dev/null || echo "unknown")
        ok "Ollama running ($LOADED)"
    else
        warn "Ollama not running"
    fi

    if command -v nvidia-smi &> /dev/null; then
        FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null)
        TOTAL_V=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null)
        ok "GPU: ${FREE}MB free / ${TOTAL_V}MB total"
    fi

    if [[ -L "$RUNTIME/tmp/current_frame.png" ]]; then
        TARGET=$(readlink "$RUNTIME/tmp/current_frame.png")
        [[ -f "$TARGET" ]] && ok "current_frame → $(basename $TARGET)" || warn "current_frame symlink broken"
    else
        warn "current_frame.png missing"
    fi

    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════════════════
echo -e "${CYN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       A I N N   B R O A D C A S T     ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${RST}"

hdr "Pre-flight"
ERRORS=0

# Ollama
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    ok "Ollama running"
else
    warn "Ollama not running — starting..."
    ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    sleep 4
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        ok "Ollama started"
    else
        fail "Ollama failed to start"
        ((ERRORS++))
    fi
fi

# Unload all models for clean VRAM
python3 -c "
import requests
try:
    ps = requests.get('http://localhost:11434/api/ps', timeout=5).json()
    for m in ps.get('models', []):
        requests.post('http://localhost:11434/api/generate',
                      json={'model': m['name'], 'keep_alive': 0}, timeout=5)
except: pass
" 2>/dev/null && ok "VRAM cleared" || true

# Critical files
for f in "$REPO/batch_producer.py" "$RUNTIME/segment_player.py" "$RUNTIME/stream/master.sh"; do
    [[ -f "$f" ]] && ok "$(basename $f)" || { fail "Missing: $f"; ((ERRORS++)); }
done

# eigentrace
if cd "$REPO" && python3 -c "from eigentrace import score" 2>/dev/null; then
    ok "eigentrace importable"
else
    fail "eigentrace not importable"
    ((ERRORS++))
fi

# Piper
[[ -x "/home/remvelchio/.local/bin/piper" ]] && ok "Piper TTS" || warn "Piper not found"

# Assets
for f in "$RUNTIME/assets/bed_22050.wav" "$RUNTIME/assets/bumper_frame.png"; do
    [[ -f "$f" ]] && ok "$(basename $f)" || warn "Missing: $(basename $f)"
done

# Owncast
[[ -x "$OWNCAST_DIR/owncast" ]] && ok "Owncast binary" || { fail "Owncast missing"; ((ERRORS++)); }

if [[ $ERRORS -gt 0 ]]; then
    fail "$ERRORS critical error(s) — fix before starting"
    exit 1
fi

# ── Cleanup ──────────────────────────────────────────────────────────────
hdr "Cleanup"
pkill -f "batch_producer.py" 2>/dev/null && warn "Killed stale producer" || true
pkill -f "segment_player.py" 2>/dev/null && warn "Killed stale player" || true
pkill -f "master.sh" 2>/dev/null && warn "Killed stale master.sh" || true
pkill -f "ffmpeg.*tee.*flv" 2>/dev/null && warn "Killed stale ffmpeg" || true
pkill -f "owncast" 2>/dev/null && warn "Killed stale owncast" || true
sleep 3
ok "Clean"

# ── 1. Owncast ───────────────────────────────────────────────────────────
hdr "1/4 Owncast"
cd "$OWNCAST_DIR" && ./owncast >> "$LOG_DIR/owncast.log" 2>&1 &
save_pid "owncast" $!
sleep 4
if curl -sf http://localhost:8080 > /dev/null 2>&1; then
    ok "Owncast live (PID $(read_pid owncast))"
else
    warn "Owncast may still be starting"
fi

# ── 2. Master compositor ─────────────────────────────────────────────────
hdr "2/4 Master compositor"
cd "$RUNTIME/stream" && bash master.sh >> "$LOG_DIR/master.log" 2>&1 &
save_pid "master" $!
ok "master.sh (PID $(read_pid master))"
echo -e "  ${DIM}frame + UDP audio + ticker + bed → Owncast + Twitch + YouTube${RST}"

# ── 3. Segment player ───────────────────────────────────────────────────
hdr "3/4 Segment player"
cd "$RUNTIME" && python3 segment_player.py >> "$LOG_DIR/player.log" 2>&1 &
save_pid "player" $!
ok "segment_player.py (PID $(read_pid player))"
echo -e "  ${DIM}TTS via Piper → UDP:10000 + current_frame.png${RST}"

# ── 4. Batch producer ───────────────────────────────────────────────────
hdr "4/4 Batch producer"
cd "$REPO" && python3 batch_producer.py --loop --interval 60 --min-queue 1 $EXTRA_PRODUCER_ARGS \
    >> "$LOG_DIR/producer.log" 2>&1 &
save_pid "producer" $!
ok "batch_producer.py --loop (PID $(read_pid producer))"

# ── Online ───────────────────────────────────────────────────────────────
echo ""
echo -e "${CYN}════════════════════════════════════════════════════════════════${RST}"
echo -e "${CYN}  AINN ONLINE — $(date '+%Y-%m-%d %H:%M:%S')${RST}"
echo -e "${CYN}════════════════════════════════════════════════════════════════${RST}"
echo ""
echo "  Logs:"
echo "    tail -f $LOG_DIR/producer.log"
echo "    tail -f $LOG_DIR/player.log"
echo "    tail -f $LOG_DIR/master.log"
echo ""
echo "  Commands:"
echo "    bash ainn.sh status"
echo "    bash ainn.sh stop"
echo ""

# ── Watchdog ─────────────────────────────────────────────────────────────
trap '
    echo ""
    echo "Shutting down AINN..."
    kill_component "producer"
    kill_component "player"
    kill_component "master"
    kill_component "owncast"
    pkill -f "batch_producer.py" 2>/dev/null || true
    pkill -f "segment_player.py" 2>/dev/null || true
    pkill -f "master.sh" 2>/dev/null || true
    echo "Done."
    exit 0
' SIGINT SIGTERM

while true; do
    sleep 30

    if ! is_alive "player"; then
        warn "$(date '+%H:%M:%S') player died — restarting"
        cd "$RUNTIME" && python3 segment_player.py >> "$LOG_DIR/player.log" 2>&1 &
        save_pid "player" $!
    fi

    if ! is_alive "producer"; then
        warn "$(date '+%H:%M:%S') producer died — restarting"
        cd "$REPO" && python3 batch_producer.py --loop --interval 60 --min-queue 1 $EXTRA_PRODUCER_ARGS \
            >> "$LOG_DIR/producer.log" 2>&1 &
        save_pid "producer" $!
    fi

    if ! is_alive "master"; then
        warn "$(date '+%H:%M:%S') master died — restarting"
        cd "$RUNTIME/stream" && bash master.sh >> "$LOG_DIR/master.log" 2>&1 &
        save_pid "master" $!
    fi

    if ! is_alive "owncast"; then
        warn "$(date '+%H:%M:%S') owncast died — restarting"
        cd "$OWNCAST_DIR" && ./owncast >> "$LOG_DIR/owncast.log" 2>&1 &
        save_pid "owncast" $!
    fi
done
