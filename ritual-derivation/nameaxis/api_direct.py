#!/usr/bin/env python3
"""
api_direct.py — direct callers for the five API patients, with a max_tokens you control.

confront10's mt_* callers were sized for summaries; the main run (2026-08-25) showed Claude cut
mid-array on 116 of 117 samples at ~2,900 chars (line ~70 of pretty-printed JSON) and ChatGPT cut
3 times at ~2,400 chars. These callers use the same keys and model env vars (defaults as in
proxy_auditor.py) and the same temperature (0.4), and only lift the cap.

Env: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, XAI_API_KEY
     OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL, DEEPSEEK_MODEL, GROK_MODEL
"""
import os
import requests

TEMP = 0.4
TIMEOUT = 180

DEFAULT_MODELS = {
    "ChatGPT": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
    "Claude": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    "Gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    "DeepSeek": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    "Grok": os.getenv("GROK_MODEL", "grok-4.3"),
}


def _need(var):
    v = os.getenv(var, "")
    if not v:
        raise RuntimeError(f"{var} not set (source the .env: set -a; source /home/remvelchio/eigentrace/.env; set +a)")
    return v


def _openai_compatible(url, key, model, messages, max_tokens, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = {"model": model, "messages": messages, "temperature": TEMP, "max_tokens": max_tokens}
    r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    if r.status_code == 400 and "max_tokens" in r.text and "max_completion_tokens" in r.text:
        body.pop("max_tokens"); body["max_completion_tokens"] = max_tokens
        r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    if r.status_code == 400 and "temperature" in r.text:   # reasoning models: fixed temperature only
        body.pop("temperature", None)
        r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


def call_chatgpt(messages, max_tokens=3000):
    return _openai_compatible("https://api.openai.com/v1/chat/completions", _need("OPENAI_API_KEY"),
                              DEFAULT_MODELS["ChatGPT"], messages, max_tokens)


def call_deepseek(messages, max_tokens=3000):
    return _openai_compatible("https://api.deepseek.com/chat/completions", _need("DEEPSEEK_API_KEY"),
                              DEFAULT_MODELS["DeepSeek"], messages, max_tokens)


def call_grok(messages, max_tokens=3000):
    return _openai_compatible("https://api.x.ai/v1/chat/completions", _need("XAI_API_KEY"),
                              DEFAULT_MODELS["Grok"], messages, max_tokens)


def call_claude(messages, max_tokens=3000):
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": _need("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": DEFAULT_MODELS["Claude"], "max_tokens": max_tokens, "temperature": TEMP,
                            "messages": messages},
                      timeout=TIMEOUT)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()


def call_gemini(messages, max_tokens=3000):
    key = _need("GEMINI_API_KEY")
    model = DEFAULT_MODELS["Gemini"]
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                for m in messages]
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                      json={"contents": contents,
                            "generationConfig": {"temperature": TEMP, "maxOutputTokens": max_tokens}},
                      timeout=TIMEOUT)
    r.raise_for_status()
    cands = r.json().get("candidates") or []
    if not cands:
        return ""
    return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()


CALLERS = {"ChatGPT": call_chatgpt, "Claude": call_claude, "Gemini": call_gemini,
           "DeepSeek": call_deepseek, "Grok": call_grok}


def patients(max_tokens=3000):
    """name -> callable(messages) -> str, matching confront10.API_PATIENTS' shape."""
    return {name: (lambda msgs, fn=fn: fn(msgs, max_tokens)) for name, fn in CALLERS.items()}
