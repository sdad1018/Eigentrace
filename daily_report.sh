#!/bin/bash
# daily_report.sh — Run all daily analysis jobs
# Add to cron: 0 0 * * * bash /mnt/c/Users/M4ISI/eigentrace/daily_report.sh
set -e
cd /mnt/c/Users/M4ISI/eigentrace

DATE=$(date +%Y%m%d)
LOG="/home/remvelchio/eigentrace/tmp/logs/daily_${DATE}.log"

echo "=== DAILY REPORT ${DATE} ===" >> "$LOG"

# 1. Generate Omission Ledger
echo "[1/3] Omission Ledger..." >> "$LOG"
python3 claim_extractor.py --digest --date "$DATE" >> "$LOG" 2>&1

# 2. Run temporal stability sample
echo "[2/3] Temporal stability..." >> "$LOG"
python3 eigentrace_temporal.py --run >> "$LOG" 2>&1

# 3. Run PCA on accumulated void registry
echo "[3/3] PCA void analysis..." >> "$LOG"
python3 pca_void_registry.py >> "$LOG" 2>&1

echo "=== DAILY REPORT COMPLETE ===" >> "$LOG"

# 4. Publish to GitHub Pages
echo "[4/4] Publishing to eigentrace.ai..." >> "$LOG"
DATESTR=$(date +%Y-%m-%d)
DATENUM=$(date +%Y%m%d)
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
    git commit -m "ledger: ${DATESTR}" --quiet
    git push origin master --quiet 2>&1
    echo "Published: ${DATESTR}" >> "$LOG"
fi
