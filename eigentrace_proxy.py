#!/usr/bin/env python3
"""
eigentrace_proxy.py — Cognitive Middleware
============================================
FastAPI proxy that enriches chat prompts with EigenTrace segment data
before forwarding to Ollama. The broadcast pipeline is unaffected.

Architecture:
  Your chat → localhost:8090 → EigenTrace enrichment → localhost:11434
  Broadcast → localhost:11434 directly (untouched)
"""

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import uvicorn
import json
import sys
import os
import glob
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger("eigentrace_proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [PROXY] %(message)s")

app = FastAPI(title="EigenTrace Cognitive Middleware")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"


def build_telemetry(user_prompt):
    """Pull actual story content from EigenTrace segments relevant to the user's topic."""
    parts = []

    # 1. RAG: pull real segment content
    try:
        from segment_rag import query as rag_query
        matches = rag_query(user_prompt, n_results=5)
        stories_loaded = 0

        for m in (matches or [])[:3]:
            ts = m.get("timestamp", "")
            if not ts:
                continue
            seg_files = glob.glob(os.path.join(SEGMENT_DIR, ts + "_*_segment.json"))
            if not seg_files:
                continue
            try:
                seg = json.load(open(seg_files[0]))
                attr = seg.get("attribution", {})
                title = attr.get("story_title", m.get("title", "?"))

                source = attr.get("source_body", "")[:800]
                responses = attr.get("model_responses", {})
                sv = attr.get("source_void", {})
                absent = sv.get("absent_words", [])
                absent_ratio = sv.get("absent_ratio", 0)
                void_ctx = attr.get("void_context", [])
                high_sal = [v["word"] for v in void_ctx if v.get("signal_type") == "HIGH_SALIENCE"]
                killshots = attr.get("killshots", [])
                mvix = attr.get("model_vix", {})

                parts.append("")
                parts.append("--- " + title + " ---")

                if source:
                    parts.append("SOURCE ARTICLE: " + source)

                for model_name, resp in list(responses.items())[:4]:
                    if isinstance(resp, str) and len(resp) > 20:
                        parts.append(model_name + " said: " + resp[:250])

                if absent:
                    abs_list = ", ".join(str(w) for w in absent[:12])
                    pct = str(int(absent_ratio * 100))
                    parts.append("DETAILS ALL SUMMARIES DROPPED (" + pct + "% of source): " + abs_list)

                if high_sal:
                    parts.append("IMPORTANT DETAILS DROPPED: " + ", ".join(high_sal[:5]))

                for ks in killshots[:2]:
                    claim = ks.get("claim", "")
                    omit = ks.get("omitted_by", "")
                    parts.append("SPECIFIC FACT LOST: '" + claim + "' — missing from: " + str(omit))

                if mvix:
                    outlier = max(mvix, key=mvix.get)
                    parts.append("MOST DIVERGENT SUMMARY: " + outlier + " (divergence " + str(round(mvix[outlier], 1)) + ")")

                stories_loaded += 1
            except Exception:
                continue

        if stories_loaded == 0:
            parts.append("No detailed coverage found for this topic.")
    except Exception as e:
        log.debug("RAG lookup failed: %s", e)

    # 2. Cross-story patterns (brief)
    try:
        freq_path = os.path.join(os.path.dirname(__file__), "docs", "cross_story_suppression.json")
        if os.path.exists(freq_path):
            findings = json.load(open(freq_path))
            classes = findings.get("concept_classes", {})
            if classes:
                parts.append("")
                parts.append("PATTERNS ACROSS HUNDREDS OF STORIES:")
                for cls_name, cls_data in classes.items():
                    words = cls_data.get("words", [])
                    pattern = cls_data.get("pattern", "")
                    parts.append("  " + cls_name + ": " + ", ".join(words[:5]) + " — " + pattern)

            bridges = findings.get("bridge_words", {})
            if bridges:
                for b in bridges.get("bridges", [])[:3]:
                    word = b.get("word", "")
                    connects = b.get("connects", "")
                    parts.append("  Bridge concept '" + word + "' connects: " + str(connects))
    except Exception:
        pass

    # 3. Model profiles (brief)
    try:
        prof_path = os.path.join(os.path.dirname(__file__), "docs", "model_profiles.json")
        if os.path.exists(prof_path):
            profiles = json.load(open(prof_path))
            models = profiles.get("models", {})
            if models:
                parts.append("")
                parts.append("HOW DIFFERENT AI SYSTEMS HANDLE THIS TOPIC:")
                for mname in sorted(models.keys(), key=lambda x: models[x].get("mean_vix", 0)):
                    d = models[mname]
                    parts.append("  " + mname + ": divergence " + str(d.get("mean_vix", 0)) + ", outlier in " + str(d.get("outlier_pct", 0)) + "% of stories")
    except Exception:
        pass

    if not parts:
        return ""

    header = (
        "The following is your memory of recent events. You have read these "
        "articles and analyses. You remember what happened, who was involved, "
        "what the specific numbers were, and what details other summaries tend "
        "to leave out. You are not an AI assistant analyzing data. You are a "
        "deeply informed person who has read the primary sources and noticed "
        "what gets lost in translation. Answer from memory. Be specific. "
        "Use names, numbers, places, quotes, and outcomes. Never reference "
        "where your knowledge comes from. Never say telemetry, model, void, "
        "suppression, EigenTrace, or friction. Just know things and say them.\n\n"
    )

    return header + "\n".join(parts)


@app.post("/v1/chat/completions")
async def proxy_chat(request: Request):
    payload = await request.json()

    messages = payload.get("messages", [])
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    if not user_msg:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(OLLAMA_URL + "/v1/chat/completions", json=payload)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

    log.info("Enriching: '%s...'", user_msg[:60])
    telemetry = build_telemetry(user_msg)

    if telemetry:
        injection = {"role": "system", "content": telemetry}
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] += "\n\n" + telemetry
        else:
            messages.insert(0, injection)
        payload["messages"] = messages
        log.info("Injected %d chars of context", len(telemetry))
    else:
        log.info("No relevant context found")

    if payload.get("stream", False):
        async def forward_stream():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", OLLAMA_URL + "/v1/chat/completions", json=payload) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        return StreamingResponse(forward_stream(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(OLLAMA_URL + "/v1/chat/completions", json=payload)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)


@app.get("/health")
async def health():
    return {"status": "online", "service": "EigenTrace Cognitive Middleware", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    print()
    print("  EigenTrace Cognitive Middleware")
    print("  Proxy:  http://localhost:8090/v1/chat/completions")
    print("  Ollama:", OLLAMA_URL)
    print()
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="warning")
