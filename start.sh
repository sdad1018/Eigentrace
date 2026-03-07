#!/bin/bash
set -a
source /mnt/c/Users/M4ISI/eigentrace/.env
source /home/remvelchio/agent/.env
set +a

HLS="http://127.0.0.1:8080/hls/stream.m3u8"
TW="rtmp://live.twitch.tv/app/live_1450329520_DcFkkTckId23Ea21m8WmlHLhux6f0e"
YT="rtmp://a.rtmp.youtube.com/live2/t0eu-shj4-9sr2-24h9-9uma"
export STREAM_URL="rtmp://localhost:1935/live/abc123"

echo "[$(date)] Cleaning up stale processes..."
pkill -f owncast 2>/dev/null
pkill -f auto_switch_stream 2>/dev/null
pkill -f "ffmpeg.*rtmp" 2>/dev/null
pkill -f "ffmpeg.*udp" 2>/dev/null
sleep 2

echo "[$(date)] Starting Owncast..."
cd /home/remvelchio/owncast && ./owncast &
OWNCAST_PID=$!
echo "[$(date)] Owncast PID: $OWNCAST_PID"
sleep 3

echo "[$(date)] Starting auto_switch_stream..."
bash /home/remvelchio/agent/stream/auto_switch_stream.sh >> /home/remvelchio/agent/tmp/auto_switch.log 2>&1 &
SWITCH_PID=$!
echo "[$(date)] auto_switch_stream PID: $SWITCH_PID"

echo "[$(date)] Waiting for HLS stream to go live..."
WAIT=0
until curl -sf "$HLS" > /dev/null 2>&1; do
    sleep 3
    WAIT=$((WAIT+3))
    if [[ $WAIT -ge 120 ]]; then
        echo "[$(date)] WARNING: HLS not live after 120s, starting relays anyway"
        break
    fi
done
echo "[$(date)] HLS live after ${WAIT}s — starting relays"

( while true; do
    echo "[$(date)] Starting Twitch relay..."
    ffmpeg -hide_banner -loglevel warning -stats \
      -fflags +genpts+nobuffer -avoid_negative_ts make_zero \
      -re -i "$HLS" -vf "fps=30,format=yuv420p" \
      -c:v libx264 -preset veryfast -tune zerolatency \
      -g 60 -keyint_min 60 -sc_threshold 0 \
      -c:a aac -b:a 128k -ar 44100 -ac 2 -f flv "$TW"
    echo "[$(date)] Twitch relay died, restarting in 5s..."
    sleep 5
done ) >> /home/remvelchio/agent/tmp/relay_twitch.log 2>&1 &
TW_PID=$!

( while true; do
    echo "[$(date)] Starting YouTube relay..."
    ffmpeg -hide_banner -loglevel warning -stats \
      -fflags +genpts+nobuffer -avoid_negative_ts make_zero \
      -re -i "$HLS" -vf "fps=30,format=yuv420p" \
      -c:v libx264 -preset veryfast -tune zerolatency \
      -b:v 3500k -maxrate 3500k -bufsize 7000k \
      -g 60 -keyint_min 60 -sc_threshold 0 \
      -c:a aac -b:a 128k -ar 44100 -ac 2 -f flv "$YT"
    echo "[$(date)] YouTube relay died, restarting in 5s..."
    sleep 5
done ) >> /home/remvelchio/agent/tmp/relay_youtube.log 2>&1 &
YT_PID=$!

echo "[$(date)] Twitch PID: $TW_PID | YouTube PID: $YT_PID"
echo "[$(date)] Starting Orchestrator..."
trap "echo Shutting down...; kill $OWNCAST_PID $SWITCH_PID $TW_PID $YT_PID 2>/dev/null; exit 0" SIGINT SIGTERM
cd /mnt/c/Users/M4ISI/eigentrace && python3 orchestrator.py --mode awake
