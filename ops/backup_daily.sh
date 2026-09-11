#!/bin/bash
# backup_daily.sh — copy what cannot be regenerated to the Windows drive (2026-09-09).
# Run by ainn_supervisor.sh at 05:30; safe to run by hand. Keeps 14 days.
set -uo pipefail
L=/home/remvelchio/eigentrace
DEST_ROOT=/mnt/c/Users/M4ISI/eigentrace_backups
D=$(date +%Y%m%d); DEST=$DEST_ROOT/$D
mkdir -p "$DEST" || exit 1
echo "$(date '+%F %T') backup -> $DEST"
quiet() { grep -v "file changed as we read it\|Removing leading" || true; }
# 1. segments and played-markers changed in the last 26 h
( cd "$L/tmp/segments" && find . -maxdepth 1 -type f \( -name "*.json" -o -name "*.played" \) -mmin -1560 -print0 \
  | tar czf "$DEST/segments_last26h.tgz" --null -T - ) 2>&1 | quiet
# 2. full segment archive on Sundays (no audio)
if [[ $(date +%u) -eq 7 ]]; then
    ( cd "$L/tmp" && tar czf "$DEST/segments_full.tgz" --exclude="segments/audio" segments ) 2>&1 | quiet
fi
# 3. ChromaDB (sqlite + hnsw index)
( cd "$L/tmp" && tar czf "$DEST/chromadb.tgz" chromadb ) 2>&1 | quiet
# 4. small state files in the runtime tree (registries, seen list, soul, profiles)
( cd "$L" && find . tmp -maxdepth 1 -type f \( -name "*.json" -o -name "*.md" -o -name "*.txt" \) -size -50M -print0 \
  | tar czf "$DEST/state_files.tgz" --null -T - ) 2>&1 | quiet
# 5. Owncast configuration and database (admin settings, stream key, chat/emoji) — excluded: transcoder tmp
( cd "$HOME" && tar czf "$DEST/owncast_data.tgz" --exclude="owncast/data/tmp" --exclude="owncast/data/hls" owncast/data ) 2>&1 | quiet
# 6. retention — date-named daily folders only (2026-09-11: the old rule also deleted logs_archive,
#    the permanent archive of rotated logs, once it went 14 days without a new file)
find "$DEST_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20[0-9][0-9][0-9][0-9][0-9][0-9]' -mtime +14 -exec rm -rf {} + 2>/dev/null
echo "$(date '+%F %T') done: $(du -sh "$DEST" | cut -f1)"
