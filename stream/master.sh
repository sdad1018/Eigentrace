#!/usr/bin/env bash
# THE MASTER TRANSMITTER
set -uo pipefail

LOCKFILE="/tmp/agente_master.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "$(date): MASTER already running. Exiting duplicate."
    exit 1
fi
echo $$ > "$LOCKFILE"

# The Global Distribution Keys
STREAM_KEY='hCet25N^wsaXpSH8X$^jW3P9Y7EaZk'
OWNCAST="rtmp://127.0.0.1:1935/live/$STREAM_KEY"
TWITCH="rtmp://iad05.contribute.live-video.net/app/live_1450329520_DcFkkTckId23Ea21m8WmlHLhux6f0e"
YOUTUBE="rtmp://a.rtmp.youtube.com/live2/t0eu-shj4-9sr2-24h9-9uma"

BED_MUSIC="/home/remvelchio/eigentrace/assets/bed_22050.wav"
UDP_IN="udp://127.0.0.1:10000?fifo_size=1000000&overrun_nonfatal=1&timeout=0"
TICKER_FILE="/home/remvelchio/eigentrace/tmp/ticker_scroll.txt"
TICKER_FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

echo "$(date): MASTER TRANSMITTER STARTING (PID=$$)"

[[ -f "$TICKER_FILE" ]] || echo "EIGENTRACE LIVE: Analyzing Narrative Entropy..." > "$TICKER_FILE"

while true; do
    ffmpeg -hide_banner -loglevel warning -stats \
        -err_detect ignore_err \
        -fflags +genpts \
        -re -f image2 -loop 1 -framerate 30 -i "/home/remvelchio/eigentrace/tmp/current_frame.png" \
        -stream_loop -1 -i "$BED_MUSIC" \
        -f lavfi -i "anullsrc=cl=mono:r=44100" \
        -thread_queue_size 4096 -probesize 10000000 -analyzeduration 10000000 -f mpegts -i "$UDP_IN" \
        -filter_complex \
            "[0:v]fps=30,scale=1024:576,drawbox=x=0:y=h-60:w=iw:h=60:color=black@0.55:t=fill,drawtext=fontfile=${TICKER_FONT}:textfile=${TICKER_FILE}:reload=1:expansion=none:fontcolor=white:fontsize=28:x=w-mod(t*120\,(w+tw)):y=h-60+14:shadowcolor=black@0.6:shadowx=2:shadowy=2[v]; \
             [1:a]volume=0.08[bed]; \
             [2:a]volume=0.0[null]; \
             [3:a]aresample=async=1:min_hard_comp=0.100000:first_pts=0,volume=3.0[story]; \
             [null][story]amix=inputs=2:duration=longest:dropout_transition=2[voice]; \
             [voice][bed]amix=inputs=2:duration=longest:dropout_transition=2[a]" \
        -map "[v]" -map "[a]" \
        -c:v libx264 -preset fast -b:v 2500k -maxrate 2500k -bufsize 5000k \
        -pix_fmt yuv420p -g 60 -keyint_min 60 -sc_threshold 0 \
        -c:a aac -b:a 128k -ar 44100 -ac 2 \
        -f tee "[f=flv:onfail=ignore]$OWNCAST|[f=flv:onfail=ignore]$TWITCH|[f=flv:onfail=ignore]$YOUTUBE" \
        2>>/home/remvelchio/eigentrace/tmp/master.log || true

    echo "$(date): MASTER DIED — restarting in 2 seconds..."
    sleep 2
done
