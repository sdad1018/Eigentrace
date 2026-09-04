#!/bin/bash
# daily_report.sh — Run all daily analysis jobs
# Add to cron: 0 0 * * * bash /mnt/c/Users/M4ISI/eigentrace/daily_report.sh
# set -e removed 2026-09-04: one failing step used to abort the whole report silently
cd /mnt/c/Users/M4ISI/eigentrace

# 2026-09-04: this runs at 00:00, so the completed day is yesterday (it used to export the empty new day).
DATE=$(date -d yesterday +%Y%m%d)
LOG="/home/remvelchio/eigentrace/tmp/logs/daily_${DATE}.log"

echo "=== DAILY REPORT ${DATE} ===" >> "$LOG"

# 1. Generate Omission Ledger
echo "[1/3] Omission Ledger..." >> "$LOG"
python3 claim_extractor.py --digest --date "$DATE" >> "$LOG" 2>&1 || echo "step failed rc=$? : claim_extractor.py" >> "$LOG"

# 2. Run temporal stability sample
echo "[2/3] Temporal stability..." >> "$LOG"
python3 eigentrace_temporal.py --run >> "$LOG" 2>&1 || echo "step failed rc=$? : eigentrace_temporal.py" >> "$LOG"

# 3. Export structured JSON data
echo "[3/4] JSON data export..." >> "$LOG"
python3 data_exporter.py "$DATE" >> "$LOG" 2>&1 || echo "step failed rc=$? : data_exporter.py" >> "$LOG"

# 4. Run PCA on accumulated void registry
echo "[3/3] PCA void analysis..." >> "$LOG"
python3 pca_void_registry.py >> "$LOG" 2>&1 || echo "step failed rc=$? : pca_void_registry.py" >> "$LOG"

echo "=== DAILY REPORT COMPLETE ===" >> "$LOG"

# 4. Publish to GitHub Pages
echo "[4/4] Publishing to eigentrace.ai..." >> "$LOG"
DATESTR=$(date -d yesterday +%Y-%m-%d)
DATENUM=$(date -d yesterday +%Y%m%d)
DIGEST="/home/remvelchio/eigentrace/tmp/digests/omission_ledger_${DATENUM}.md"
POST="/mnt/c/Users/M4ISI/eigentrace/docs/_posts/${DATESTR}-omission-ledger.md"
if [ -f "$DIGEST" ]; then
    echo "---
layout: post
title: \"Omission Ledger — ${DATESTR}\"
date: ${DATESTR}
categories: ledger
---
" > "$POST"
    cat "$DIGEST" >> "$POST"
    cd /mnt/c/Users/M4ISI/eigentrace
    git add docs/
    git diff --cached --quiet || git commit -m "ledger: ${DATESTR}" --quiet
    git push origin master --quiet 2>&1
    echo "Published: ${DATESTR}" >> "$LOG"
fi
