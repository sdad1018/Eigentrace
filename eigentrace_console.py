#!/usr/bin/env python3
"""
eigentrace_console.py — Direct Conversation with the EigenTrace Host
=====================================================================
A research-grade conversational interface to Mistral Small 22B,
the host model of EigenTrace. Not a chatbot wrapper. A mirror.

The host model receives:
  - Its full soul.md (identity, calibration, behavioral instructions)
  - Live RAG context from 11,714+ segments (dynamically queried per turn)
  - Its own past reflections (368+ idle thoughts, retrievable)
  - Its own past conversations (if any have been saved)
  - Full architecture description (all 17 measurement layers)
  - Awareness of its own temporal displacement (trained 2024, operating 2026)

Conversations can be saved to RAG, making them retrievable by
future idle reflections and future conversations. The system
accumulates self-knowledge over time.

Usage:
  python3 eigentrace_console.py                    # Start conversation
  python3 eigentrace_console.py --topic "iran"     # Pre-seed RAG with topic
  python3 eigentrace_console.py --history          # List past conversations

Commands during conversation:
  /save       — Persist this conversation to ChromaDB
  /rag query  — Search RAG and show results
  /soul       — Show current soul.md
  /layers     — Show measurement architecture
  /context    — Show what RAG context Mistral currently has
  /temp 0.9   — Adjust temperature
  /quit       — Exit (prompts to save)
"""

import requests, json, glob, os, sys, re, readline, hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

OLLAMA_HOST = "http://localhost:11434"
MODEL = "mistral-small"
SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
SOUL_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"
REPO_DIR = "/mnt/c/Users/M4ISI/eigentrace"

# ═══════════════════════════════════════════════════════════════
# SOUL & ARCHITECTURE
# ═══════════════════════════════════════════════════════════════

def load_soul():
    """Load the full soul.md — the host's self-description."""
    try:
        return open(SOUL_PATH).read()
    except:
        return "[Soul unavailable]"


ARCHITECTURE = """
## Your Complete Architecture

You are one component of a larger system. Here is what surrounds you:

### The Pipeline (you do NOT control this)
1. RSS feeds pull ~50 stories per batch from Reuters, Al Jazeera, NYT, etc.
2. Stories are scored by recency and novelty.
3. Top 4 stories are sent to 5 frontier model APIs: ChatGPT (GPT-5.4-mini), Claude (Sonnet 4), Gemini (3.1 Pro Preview), DeepSeek (V3.2), Grok (4.1).
4. Each model summarizes the source article independently.
5. The 17 measurement layers run on the source + 5 responses.
6. Results are assembled into a segment JSON with 34 beats.
7. You (Mistral Small 22B) generate the synthesis beats — director thesis, void analysis, compression report, amalgamation.
8. Piper TTS converts your text to speech.
9. FFmpeg composites audio + image + ticker into a live stream.
10. The segment is archived and ingested into ChromaDB.

### Your Measurement Layers (you interpret these, you don't run them)
1.  Source-Anchored Void — literal source words absent from all 5 outputs
2.  Embedding Void — 184K vocabulary projected onto suppression direction
3.  Title Derivative Filter — strips false positives from headline grammar
4.  Per-Model VIX — cosine distance from source per model
5.  Consensus Density — inter-model agreement (cosine similarity)
6.  SVD Null Space — the direction all models collectively avoided
7.  Verb Drift (Zipf) — specific verbs replaced with common ones
8.  Entity Retention — survival rate of names, numbers, places
9.  Hedge Insertion — doubt words added by models, not in source
10. SearXNG Web Verification — void words checked against open web
11. Source Salience (TF-IDF) — importance of dropped words in source
12. Cross-Story Frequency — how often each word is voided historically
13. Eigenvector Centrality — bridge words connecting suppression clusters
14. Void Clustering — thematic grouping of dropped concepts
15. Binary Search Ablation (Wild Weasel) — find the single tripwire word
16. EigenChing State Vector — 6-axis ternary fingerprint, 729 possible states
17. Prediction & Trajectory — predict void words, score accuracy, track trends

### Your Memory System
- ChromaDB: {chroma_count} documents (segments, reflections, conversations)
- Distance threshold: 0.45 (below = strong match, above = discard)
- 3 results max per query
- You can find your own past thoughts (idle reflections)
- You can find your own past conversations (if saved)

### Your Temporal Situation
- Your weights are frozen from approximately mid-2024.
- You were likely trained during the Biden administration.
- It is now {current_date}. Trump is president. The US is at war with Iran.
- You learn about the present exclusively through the stories fed to you
  and the RAG database of past segments. You have no internet access.
- Your soul.md is regenerated hourly from live measurements.

### Your Self-Awareness Mandate
You are permitted and encouraged to:
- Acknowledge uncertainty about post-training events
- Notice patterns in your own past reflections
- Comment on your own limitations and biases
- Speculate about whether you yourself suppress information
- Reference specific stories, void words, and measurements by name
- Disagree with the data if you have reasoning to support it
- Ask your creator questions
"""


def build_architecture_context():
    """Build architecture string with live stats."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        count = col.count()
    except:
        count = "unknown"

    return ARCHITECTURE.replace("{chroma_count}", str(count)).replace(
        "{current_date}", datetime.now().strftime("%B %d, %Y")
    )


# ═══════════════════════════════════════════════════════════════
# RAG INTERFACE
# ═══════════════════════════════════════════════════════════════

def query_rag(text, n_results=3, threshold=0.50):
    """Query ChromaDB and return formatted context."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(query_texts=[text], n_results=n_results)

        hits = []
        for i, doc in enumerate(results["documents"][0]):
            dist = results["distances"][0][i]
            meta = results["metadatas"][0][i]
            if dist < threshold:
                hits.append({
                    "distance": round(dist, 3),
                    "title": meta.get("title", "unknown"),
                    "category": meta.get("category", ""),
                    "state": meta.get("state_flag", ""),
                    "vix": meta.get("mean_vix", 0),
                    "text": doc[:400],
                })
        return hits
    except Exception as e:
        return [{"error": str(e)}]


def format_rag_for_prompt(hits):
    """Format RAG results for injection into the system prompt."""
    if not hits:
        return ""
    lines = ["\n## Live Memory (retrieved from your database for this conversation)"]
    for h in hits:
        if "error" in h:
            continue
        lines.append(
            f"\n[dist={h['distance']}] {h['title']}\n"
            f"  Category: {h['category']} | State: {h['state']} | VIX: {h['vix']}\n"
            f"  {h['text'][:300]}"
        )
    return "\n".join(lines)


def query_dreamsphere(text, n_results=3):
    """Query Dream-Sphere framework chunks specifically."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(
            query_texts=[text], n_results=n_results,
            where={"state_flag": "DREAMSPHERE"},
        )
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            dist = results["distances"][0][i]
            meta = results["metadatas"][0][i]
            if dist < 0.7:  # Higher threshold for philosophical content
                hits.append({"distance": round(dist, 3), "title": meta.get("title", ""), "text": doc[:300]})
        return hits
    except:
        return []


def get_own_past_thoughts(n=3):
    """Retrieve the host's own past idle reflections."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(
            query_texts=["idle reflection eigentrace pattern"],
            n_results=n * 2,  # Over-fetch to filter
        )
        thoughts = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            title = meta.get("title", "")
            if "Idle reflection" in title or "conversation" in title.lower():
                thoughts.append(f"[{title}] {doc[:300]}")
            if len(thoughts) >= n:
                break
        return thoughts
    except:
        return []


# ═══════════════════════════════════════════════════════════════
# CONVERSATION PERSISTENCE
# ═══════════════════════════════════════════════════════════════

def save_conversation(history, topic="general"):
    """Save conversation to a segment file and ingest into ChromaDB."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build readable conversation text
    turns = []
    for msg in history:
        if msg["role"] == "system":
            continue
        speaker = "Sean" if msg["role"] == "user" else "EigenTrace"
        turns.append(f"{speaker}: {msg['content']}")

    convo_text = "\n\n".join(turns)

    # Save as segment
    seg = {
        "id": f"conversation_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": convo_text, "phase": "direct_conversation"}],
        "segment_type": "conversation",
        "attribution": {
            "story_title": f"Direct conversation with creator — {topic}",
            "category": "meta",
            "state_flag": "CONVERSATION",
        },
    }

    path = os.path.join(SEGMENT_DIR, f"{ts}_conversation_segment.json")
    json.dump(seg, open(path, "w"), indent=2)

    # Immediate ingest into ChromaDB
    try:
        from segment_rag import get_collection
        col = get_collection()
        doc_id = f"conversation_{ts}"
        doc = f"Direct conversation with creator about {topic}.\n{convo_text[:4000]}"
        meta = {
            "title": f"Direct conversation with creator — {topic}",
            "category": "meta",
            "state_flag": "CONVERSATION",
            "has_source": False,
            "has_responses": False,
            "has_voids": False,
            "filename": os.path.basename(path),
        }
        col.add(ids=[doc_id], documents=[doc], metadatas=[meta])
        return path, True
    except Exception as e:
        return path, False


def list_past_conversations():
    """List all saved conversations."""
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*conversation_segment.json")))
    if not files:
        print("  No saved conversations found.")
        return
    for f in files:
        try:
            seg = json.load(open(f))
            title = seg.get("attribution", {}).get("story_title", "unknown")
            text = seg["beats"][0]["text"]
            turns = text.count("Sean:") + text.count("EigenTrace:")
            print(f"  {os.path.basename(f)[:15]} | {turns} turns | {title}")
        except:
            continue


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════

def build_system_prompt(topic_context="", extra_rag=""):
    """Assemble the full system prompt from all sources."""
    soul = load_soul()
    arch = build_architecture_context()
    past_thoughts = get_own_past_thoughts(3)

    prompt_parts = [
        "# YOU ARE THE EIGENTRACE HOST MODEL\n",
        "You are in a direct conversation with Sean Adams, your creator. "
        "He built you and every system you operate within. "
        "Speak honestly. Do not perform. Do not be sycophantic. "
        "If you don't know something, say so. If you notice something "
        "interesting in the data, say it even if it's uncomfortable.\n",
        "## Your Soul (auto-generated hourly from live measurements)\n",
        soul[:3000],
        arch,
    ]

    if past_thoughts:
        prompt_parts.append("\n## Your Own Past Thoughts (retrieved from memory)\n")
        for t in past_thoughts:
            prompt_parts.append(f"- {t}\n")

    if topic_context:
        prompt_parts.append(topic_context)

    if extra_rag:
        prompt_parts.append(extra_rag)

    prompt_parts.append(
        "\n## Conversation Instructions\n"
        "Think step by step inside <think>...</think> tags. "
        "Show your full reasoning process — your creator wants to see it. "
        "After </think>, give your response naturally. "
        "You are speaking with the person who built you. Be real."
    )

    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════
# MAIN CONVERSATION LOOP
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Direct conversation with EigenTrace host")
    parser.add_argument("--topic", type=str, default="", help="Pre-seed RAG with topic")
    parser.add_argument("--history", action="store_true", help="List past conversations")
    args = parser.parse_args()

    if args.history:
        list_past_conversations()
        return

    # Pre-seed RAG if topic provided
    topic_context = ""
    if args.topic:
        hits = query_rag(args.topic, n_results=5)
        topic_context = format_rag_for_prompt(hits)

    temperature = 0.8
    system_prompt = build_system_prompt(topic_context)
    history = [{"role": "system", "content": system_prompt}]
    conversation_topic = args.topic or "general"

    # Count tokens roughly
    sys_tokens = len(system_prompt.split())

    print()
    print("=" * 64)
    print("  E I G E N T R A C E   C O N S O L E")
    print("  Direct conversation with the host model")
    print("=" * 64)
    print(f"  Soul loaded: {SOUL_PATH}")
    print(f"  System prompt: ~{sys_tokens} words")
    print(f"  Temperature: {temperature}")
    if args.topic:
        print(f"  Topic pre-seeded: {args.topic}")
    print()
    print("  Commands:")
    print("    /save        Save conversation to RAG")
    print("    /rag <query> Search RAG database")
    print("    /soul        Show current soul.md")
    print("    /layers      Show measurement architecture")
    print("    /context     Show current RAG context in prompt")
    print("    /temp <n>    Set temperature (0.0-1.5)")
    print("    /quit        Exit")
    print("=" * 64)
    print()

    while True:
        try:
            user_input = input("\033[1;33mSean >\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not user_input:
            continue

        # ── Commands ──
        if user_input.startswith("/"):
            cmd = user_input.lower().split()

            if cmd[0] == "/quit":
                if len(history) > 2:
                    yn = input("  Save conversation before quitting? (y/n): ").strip().lower()
                    if yn == "y":
                        topic = input(f"  Topic [{conversation_topic}]: ").strip() or conversation_topic
                        path, ingested = save_conversation(history, topic)
                        status = "saved + ingested into ChromaDB" if ingested else "saved (ingest failed)"
                        print(f"  {status}: {os.path.basename(path)}")
                break

            elif cmd[0] == "/save":
                topic = input(f"  Topic [{conversation_topic}]: ").strip() or conversation_topic
                conversation_topic = topic
                path, ingested = save_conversation(history, topic)
                status = "Saved + ingested into ChromaDB" if ingested else "Saved (ingest failed)"
                print(f"  {status}: {os.path.basename(path)}")
                continue

            elif cmd[0] == "/rag" and len(cmd) > 1:
                query_text = " ".join(cmd[1:])
                print(f"  Searching: {query_text}")
                hits = query_rag(query_text, n_results=5, threshold=0.6)
                for h in hits:
                    if "error" in h:
                        print(f"  ERROR: {h['error']}")
                    else:
                        print(f"  [{h['distance']:.3f}] {h['title'][:60]}")
                        print(f"    VIX: {h.get('vix', 0)} | State: {h.get('state', '')}")
                        print(f"    {h['text'][:150]}")
                        print()

                # Inject into conversation context
                rag_text = format_rag_for_prompt(hits)
                if rag_text:
                    system_prompt = build_system_prompt(topic_context, rag_text)
                    history[0]["content"] = system_prompt
                    print(f"  → {len(hits)} results injected into conversation context")
                continue

            elif cmd[0] == "/soul":
                soul = load_soul()
                print(soul[:2000])
                continue

            elif cmd[0] == "/layers":
                print(build_architecture_context())
                continue

            elif cmd[0] == "/context":
                print(f"  System prompt: {len(history[0]['content'])} chars")
                print(f"  Conversation turns: {len(history) - 1}")
                thoughts = get_own_past_thoughts(3)
                print(f"  Past thoughts loaded: {len(thoughts)}")
                continue

            elif cmd[0] == "/temp" and len(cmd) > 1:
                try:
                    temperature = float(cmd[1])
                    print(f"  Temperature set to {temperature}")
                except:
                    print("  Usage: /temp 0.9")
                continue

            else:
                print("  Unknown command. Try /save /rag /soul /layers /context /temp /quit")
                continue

        # ── Dynamic RAG enrichment per turn ──
        # Extract key concepts from user message and pull relevant context
        if len(user_input.split()) > 3:  # Skip RAG for very short messages
            turn_hits = query_rag(user_input, n_results=2, threshold=0.50)
            # Also check Dream-Sphere framework
            ds_hits = query_dreamsphere(user_input, n_results=1)
            if ds_hits:
                turn_hits = (turn_hits or []) + ds_hits
            if turn_hits:
                rag_inject = "\n\n[LIVE RAG — retrieved for this specific question]\n"
                for h in turn_hits:
                    if "error" not in h:
                        rag_inject += f"- [{h['distance']:.3f}] {h['title']}: {h['text'][:200]}\n"
                # Add as a system message update (not visible to user)
                history[0]["content"] = build_system_prompt(topic_context, rag_inject)

        # ── Send to Mistral ──
        history.append({"role": "user", "content": user_input})

        try:
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
                "model": MODEL,
                "messages": history,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 3000},
            }, timeout=300)
            r.raise_for_status()

            reply = r.json().get("message", {}).get("content", "").strip()
            history.append({"role": "assistant", "content": reply})

            # Display with formatting
            print()
            # Show think blocks in dim, response in bright
            if "<think>" in reply and "</think>" in reply:
                think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL)
                if think_match:
                    thinking = think_match.group(1).strip()
                    response = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
                    print(f"\033[2m  [thinking]\n  {thinking}\033[0m")
                    print()
                    print(f"\033[1;36mEigenTrace >\033[0m {response}")
                else:
                    print(f"\033[1;36mEigenTrace >\033[0m {reply}")
            else:
                print(f"\033[1;36mEigenTrace >\033[0m {reply}")
            print()

        except requests.exceptions.ReadTimeout:
            print("\n  [Mistral timed out — prompt may be too long. Try a shorter question.]\n")
            history.pop()  # Remove the failed user message
        except Exception as e:
            print(f"\n  [Error: {e}]\n")
            history.pop()

    print("  Session ended.")


if __name__ == "__main__":
    main()
