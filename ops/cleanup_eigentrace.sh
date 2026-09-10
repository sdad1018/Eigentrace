#!/bin/bash
# Clean ephemeral broadcast files. Keep all data (JSONs, logs, registry).

# WAVs: delete anything older than 2 hours
find /home/remvelchio/eigentrace/tmp/segments/audio -name "*.wav" -mmin +120 -delete 2>/dev/null

# Images: delete anything older than 24 hours (keep recent for stream)
# 2026-09-09: never the file current_frame.png points at — ffmpeg reads it every second and
# dies ("No such file or directory") when it vanishes, which is how the 09-07 crash loop started
CUR=$(readlink -f /home/remvelchio/eigentrace/tmp/current_frame.png 2>/dev/null)
find /home/remvelchio/eigentrace/tmp/images -name "*.png" -mmin +1440 ! -path "${CUR:-/nonexistent}" -delete 2>/dev/null
find /home/remvelchio/eigentrace/tmp/images -name "*.jpg" -mmin +1440 ! -path "${CUR:-/nonexistent}" -delete 2>/dev/null

# NEVER delete: segment JSONs, .played markers, logs, void_registry, audit_log
