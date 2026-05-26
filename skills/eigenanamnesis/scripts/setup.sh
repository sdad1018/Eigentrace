#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
echo "=== eigenanamnesis setup ==="
if ! command -v node &>/dev/null; then echo "ERROR: Node.js not found."; exit 1; fi
NODE_V=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_V" -lt 18 ]; then echo "ERROR: Node.js >= 18 required"; exit 1; fi
echo "Node.js: $(node -v)"
cd "$SKILL_DIR"
npm install 2>&1 | tail -3
echo "Setup complete. Run: node scripts/measure.js --help"
