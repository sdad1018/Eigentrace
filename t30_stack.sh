#!/usr/bin/env bash
# t30_stack.sh — bring up the T-30 stack, idempotent. WSL restart kills
# nohup'd processes; the handover's stack outage was this exact class.
cd "$(dirname "$0")"
pgrep -f "ollama serve" >/dev/null || (nohup ollama serve > /tmp/ollama.log 2>&1 &)
pgrep -f "dispatch.py --serve" >/dev/null || (nohup python3 dispatch.py --serve > /tmp/dispatch-serve.log 2>&1 &)
pgrep -f "\.bin/n8n" >/dev/null || (nohup npx --yes n8n > /tmp/n8n.log 2>&1 &)
sleep 3
echo "ollama:$(pgrep -fc 'ollama serve') serve:$(pgrep -fc 'dispatch.py --serve') n8n:$(pgrep -fc '\.bin/n8n')"
