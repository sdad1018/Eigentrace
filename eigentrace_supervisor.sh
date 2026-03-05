#!/bin/bash
# eigentrace_supervisor.sh
# Supervises all eigentrace processes for 24/7 uptime
# Run this in a persistent terminal (tmux/screen recommended)

set -euo pipefail

BASE="/mnt/c/Users/M4ISI/eigentrace"
AGENT_HOME="/home/remvelchio"
LOG_DIR="$BASE/tmp/supervisor_logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] SUPERVISOR — $*" | tee -a "$LOG_DIR/supervisor.log"; }

# ── Process registry ─────────────────────────────────────────────────────────
declare -A PIDS
declare -A RESTARTS

start_owncast() {
    log "Starting Owncast..."
    cd "$AGENT_HOME/owncast"
    ./owncast >> "$LOG_DIR/owncast.log" 2>&1 &
    PIDS[owncast]=$!
    RESTARTS[owncast]=${RESTARTS[owncast]:-0}
    log "Owncast PID=${PIDS[owncast]}"
    sleep 5  # give it time to bind port
}

start_orchestrator() {
    log "Starting Orchestrator (awake mode)..."
    cd "$BASE"
    export $(cat "$BASE/.env" | grep -v '^#' | xargs)
    TICKER_FILE="$BASE/tmp/ticker.txt" \
    SEEN_FILE="$BASE/tmp/seen_stories.json" \
    python3 orchestrator.py --mode awake >> "$LOG_DIR/orchestrator.log" 2>&1 &
    PIDS[orchestrator]=$!
    RESTARTS[orchestrator]=${RESTARTS[orchestrator]:-0}
    log "Orchestrator PID=${PIDS[orchestrator]}"
}

start_dream_broadcast() {
    log "Starting Dream Broadcast..."
    cd "$BASE"
    export $(cat "$BASE/.env" | grep -v '^#' | xargs)
    python3 dream_broadcast.py >> "$LOG_DIR/dream_broadcast.log" 2>&1 &
    PIDS[dream_broadcast]=$!
    RESTARTS[dream_broadcast]=${RESTARTS[dream_broadcast]:-0}
    log "Dream Broadcast PID=${PIDS[dream_broadcast]}"
}

start_dashboard() {
    log "Starting Dashboard server..."
    cd "$BASE"
    python3 dashboard_server.py >> "$LOG_DIR/dashboard.log" 2>&1 &
    PIDS[dashboard]=$!
    RESTARTS[dashboard]=${RESTARTS[dashboard]:-0}
    log "Dashboard PID=${PIDS[dashboard]}"
}

start_twitch_relay() {
    log "Starting Twitch relay..."
    HLS="http://127.0.0.1:8080/hls/stream.m3u8"
    TW="rtmp://live.twitch.tv/app/live_1450329520_DcFkkTckId23Ea21m8WmlHLhux6f0e"
    (while true; do
        ffmpeg -hide_banner -loglevel warning -stats \
            -fflags +genpts -avoid_negative_ts make_zero \
            -re -i "$HLS" \
            -vf "fps=30,format=yuv420p" \
            -c:v libx264 -preset veryfast -tune zerolatency \
            -g 60 -keyint_min 60 -sc_threshold 0 \
            -c:a aac -b:a 128k -ar 44100 -ac 2 \
            -f flv "$TW" 2>> "$LOG_DIR/twitch_relay.log"
        echo "[$(date)] Twitch relay restarting..." >> "$LOG_DIR/twitch_relay.log"
        sleep 5
    done) &
    PIDS[twitch_relay]=$!
    RESTARTS[twitch_relay]=${RESTARTS[twitch_relay]:-0}
    log "Twitch relay PID=${PIDS[twitch_relay]}"
}

start_youtube_relay() {
    log "Starting YouTube relay..."
    HLS="http://127.0.0.1:8080/hls/stream.m3u8"
    YT="rtmp://a.rtmp.youtube.com/live2/t0eu-shj4-9sr2-24h9-9uma"
    (while true; do
        ffmpeg -hide_banner -loglevel warning -stats \
            -fflags +genpts -avoid_negative_ts make_zero \
            -re -i "$HLS" \
            -vf "fps=30,format=yuv420p" \
            -c:v libx264 -preset veryfast -tune zerolatency \
            -b:v 3500k -maxrate 3500k -bufsize 7000k \
            -g 60 -keyint_min 60 -sc_threshold 0 \
            -c:a aac -b:a 128k -ar 44100 -ac 2 \
            -f flv "$YT" 2>> "$LOG_DIR/youtube_relay.log"
        echo "[$(date)] YouTube relay restarting..." >> "$LOG_DIR/youtube_relay.log"
        sleep 5
    done) &
    PIDS[youtube_relay]=$!
    RESTARTS[youtube_relay]=${RESTARTS[youtube_relay]:-0}
    log "YouTube relay PID=${PIDS[youtube_relay]}"
}

check_and_restart() {
    local name=$1
    local pid=${PIDS[$name]:-0}
    if [ "$pid" -eq 0 ] || ! kill -0 "$pid" 2>/dev/null; then
        local count=${RESTARTS[$name]:-0}
        RESTARTS[$name]=$((count + 1))
        log "RESTART #${RESTARTS[$name]} — $name (was PID=$pid)"
        # back off if restarting too fast
        if [ "${RESTARTS[$name]}" -gt 5 ]; then
            log "WARNING: $name has restarted ${RESTARTS[$name]} times — sleeping 60s"
            sleep 60
        fi
        start_$name
    fi
}

# ── Startup sequence ─────────────────────────────────────────────────────────
log "============================================================"
log "EIGENTRACE SUPERVISOR STARTING"
log "============================================================"

start_owncast
sleep 8  # Owncast must be up before relays try to connect

start_orchestrator
start_dream_broadcast
start_dashboard
sleep 5

start_twitch_relay
start_youtube_relay

log "All processes started. Entering watchdog loop."
log "Dashboard: http://localhost:5050"
log "Owncast:   http://localhost:8080"

# ── Watchdog loop ─────────────────────────────────────────────────────────────
while true; do
    sleep 30

    check_and_restart owncast
    check_and_restart orchestrator
    check_and_restart dream_broadcast
    check_and_restart dashboard

    # Log health every 5 minutes
    if [ $(( $(date +%s) % 300 )) -lt 30 ]; then
        log "HEALTH — owncast=${PIDS[owncast]} orch=${PIDS[orchestrator]} dream=${PIDS[dream_broadcast]} dash=${PIDS[dashboard]} twitch=${PIDS[twitch_relay]} yt=${PIDS[youtube_relay]}"
        log "MEMORY — $(free -h | grep Mem | awk '{print "used="$3" free="$4" cache="$6}')"
        log "DISK   — $(df -h /home/remvelchio | tail -1 | awk '{print "used="$3" avail="$4" pct="$5}')"
    fi
done
