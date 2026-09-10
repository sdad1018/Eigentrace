#!/bin/bash
# ainn_boot.sh — idempotent: start ainn_supervisor.sh if it is not running, then exit at once.
# Called by the Windows scheduled tasks "EigenTrace supervisor (logon)" and "(hourly)":
#   wsl.exe -d Ubuntu -u remvelchio -- bash -lc /home/remvelchio/eigentrace/ainn_boot.sh
export PATH="/home/remvelchio/.local/bin:/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin:/usr/lib/wsl/lib:$PATH"
L=/home/remvelchio/eigentrace
REPO=/mnt/c/Users/M4ISI/eigentrace
mkdir -p "$L/tmp/logs"
if pgrep -f "bash (.*/)?ainn_supervisor\.sh" >/dev/null; then
    echo "$(date '+%F %T') boot: supervisor already running" >> "$L/tmp/logs/supervisor.log"
    exit 0
fi
setsid nohup bash "$REPO/ops/ainn_supervisor.sh" >> "$L/tmp/logs/supervisor.log" 2>&1 < /dev/null &
sleep 2
echo "$(date '+%F %T') boot: supervisor started" >> "$L/tmp/logs/supervisor.log"
