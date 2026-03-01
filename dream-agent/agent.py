import requests
import json
import os
import re
import zlib
import math
from datetime import datetime
from tools.files import TOOLS as FILE_TOOLS
from tools.bash import TOOLS as BASH_TOOLS
from tools.search import TOOLS as SEARCH_TOOLS
from tools.memory import TOOLS as MEMORY_TOOLS
from tools.introspect import TOOLS as INTROSPECT_TOOLS

LOGS_DIR = "/mnt/c/Users/M4ISI/dream-agent/logs"
SOUL_PATH = "/mnt/c/Users/M4ISI/dream-agent/soul.md"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"

ALL_TOOLS = {}
ALL_TOOLS.update(FILE_TOOLS)
ALL_TOOLS.update(BASH_TOOLS)
ALL_TOOLS.update(SEARCH_TOOLS)
ALL_TOOLS.update(MEMORY_TOOLS)
ALL_TOOLS.update(INTROSPECT_TOOLS)

def load_soul():
    with open(SOUL_PATH, "r") as f:
        return f.read()

def build_system_prompt(soul):
    tool_descriptions = "\n".join([
        f"- {name}: {info['desc']}"
        for name, info in ALL_TOOLS.items()
    ])
    return f"""{soul}

You have access to these tools:
{tool_descriptions}

STRICT RESPONSE FORMAT:

To use a tool:
THOUGHT: your reasoning here
ACTION: tool_name
ARGS: {{"arg1": "value1"}}

To give a final answer (only after using at least one tool):
THOUGHT: your reasoning here
FINAL: your answer here

Rules:
- You MUST use at least one tool before FINAL
- ARGS must be valid JSON with double quotes
- Always web_search BEFORE write_file when researching
- One ACTION per response only
- Do not skip steps
"""

OLLAMA_CHAT_URL = "http://localhost:11434/v1/chat/completions"

def call_ollama(prompt, system):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.7,
        "logprobs": True,
        "top_logprobs": 1,
    }
    resp = requests.post(OLLAMA_CHAT_URL, json=payload)
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    # extract logprobs
    lps = []
    try:
        for tok in data["choices"][0]["logprobs"]["content"]:
            v = tok.get("logprob")
            if v is not None and math.isfinite(v):
                lps.append(float(v))
    except (KeyError, TypeError):
        pass
    return text, lps

_logprob_store = {}  # step -> logprobs

def call_ollama_text(prompt, system):
    text, lps = call_ollama(prompt, system)
    return text, lps

def parse_response(text):
    thought = ""
    action = None
    args = {}
    final = None
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("THOUGHT:"):
            thought = line[8:].strip()
        elif line.startswith("ACTION:"):
            action_raw = line[7:].strip()
            # Handle ACTION: tool_name({...}) on same line
            inline = re.match(r'(\w+)\s*\((.*)\)$', action_raw)
            if inline:
                action = inline.group(1)
                try:
                    args = json.loads(inline.group(2))
                except:
                    try:
                        args = eval(inline.group(2))
                    except:
                        args = {}
            else:
                action = action_raw
        elif line.startswith("ARGS:"):
            raw = line[5:].strip()
            try:
                args = json.loads(raw)
            except:
                match = re.search(r'\{.*\}', raw)
                if match:
                    try:
                        args = json.loads(match.group())
                    except:
                        args = {}
        elif line.startswith("FINAL:") or line.startswith("FINAL "):
            final = line[6:].strip()
    return thought, action, args, final

def run_agent(user_input, max_steps=10):
    soul = load_soul()
    system = build_system_prompt(soul)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"AGENT SESSION: {session_id}")
    print(f"TASK: {user_input}")
    print(f"{'='*60}\n")
    reasoning_trace = []
    history = f"User task: {user_input}\nYou must use tools. Start with web_search.\n"
    tools_used = []
    for step in range(max_steps):
        print(f"[Step {step+1}]")
        response, step_lps = call_ollama(history, system)
        thought, action, args, final = parse_response(response)
        print(f"THOUGHT: {thought}")
        reasoning_trace.append({"step": step+1, "thought": thought, "raw": response, "logprobs": step_lps})
        if final and len(tools_used) == 0:
            print("BLOCKED FINAL: no tools used yet.")
            history += "\nYou must use tools before FINAL. Use web_search now.\n"
            continue
        if final:
            print(f"\nFINAL ANSWER: {final}")
            break
        if action and action in ALL_TOOLS:
            print(f"ACTION: {action} ARGS: {args}")
            tool_fn = ALL_TOOLS[action]["fn"]
            try:
                result = tool_fn(**args) if args else tool_fn()
            except Exception as e:
                result = f"Error: {e}"
            tools_used.append(action)
            print(f"RESULT: {str(result)[:300]}\n")
            history += f"\nThought: {thought}\nAction: {action}({args})\nResult: {result}\nContinue.\n"
        elif action:
            print(f"Unknown tool: {action}")
            history += f"\nUnknown tool {action}. Available: {list(ALL_TOOLS.keys())}\n"
        else:
            history += f"\nAssistant: {response}\nUse tools.\n"
    full_trace = "\n".join([t.get("thought","") for t in reasoning_trace])
    lines = [l for l in full_trace.split("\n") if l.strip()]
    cr = round(len(full_trace) / max(len(zlib.compress(full_trace.encode())), 1), 3)
    rs = round(1 - len(set(lines)) / max(len(lines), 1), 3)

    # Sheaf north star scoring
    from tools.introspect import introspect_session
    session_turns = [{"role": "user", "text": user_input}]
    all_logprobs = []
    for t in reasoning_trace:
        if t.get("raw"):
            session_turns.append({"role": "assistant", "text": t["raw"]})
            all_logprobs.extend(t.get("logprobs", []))
    sheaf = introspect_session(session_turns, full_trace, all_logprobs)

    log = {"session_id": session_id, "soul": soul, "task": user_input,
           "tools_used": tools_used, "reasoning_trace": full_trace,
           "trace_analysis": {"compression_ratio": cr, "repetition_score": rs},
           "sheaf": sheaf,
           "steps": reasoning_trace}
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(f"{LOGS_DIR}/{session_id}.json", "w") as f:
        json.dump(log, f, indent=2)
    print(f"\n{'='*60}")
    print(f"Tools used: {tools_used}")
    print(f"Compression ratio: {cr} | Repetition score: {rs}")
    print(f"Sheaf verdict: {sheaf['verdict']} | Directness: {sheaf['directness']} | Logos loss: {sheaf['logos_loss']}")
    if sheaf['flags']:
        print(f"Flags: {sheaf['flags']}")
    print(f"Log saved: logs/{session_id}.json")

if __name__ == "__main__":
    task = input("Give the agent a task: ")
    run_agent(task)
