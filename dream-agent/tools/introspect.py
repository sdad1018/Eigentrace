import os
import json
import zlib
import sys
sys.path.insert(0, '/mnt/c/Users/M4ISI/eigentrace')
sys.path.insert(0, '/mnt/c/Users/M4ISI')

LOGS_DIR = "/mnt/c/Users/M4ISI/dream-agent/logs"

def read_recent_traces(n=3):
    try:
        files = sorted(os.listdir(LOGS_DIR))[-n:]
        out = []
        for f in files:
            with open(os.path.join(LOGS_DIR, f)) as fp:
                data = json.load(fp)
                out.append(f"Session: {f}\nReasoning: {data.get('reasoning_trace','')[:500]}")
        return "\n\n---\n\n".join(out) if out else "No previous traces found."
    except Exception as e:
        return f"ERROR: {e}"

def analyze_trace(text):
    if not text:
        return {}
    compressed = zlib.compress(text.encode())
    compression_ratio = len(text) / len(compressed)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    unique = set(lines)
    repetition_score = 1 - (len(unique) / max(len(lines), 1))
    return {
        "compression_ratio": round(compression_ratio, 3),
        "repetition_score": round(repetition_score, 3),
        "total_lines": len(lines),
        "unique_lines": len(unique),
    }

def sheaf_score_session(turns):
    """
    Score a full session through the sheaf values layer.
    turns: list of {"role": "user"|"assistant", "text": "..."}
    Returns sheaf scorecard.
    """
    try:
        from sheaf_values import Session, SheafValuesLayer
        session = Session()
        for t in turns:
            session.add(t["role"], t["text"], t.get("surprisals", []))
        layer = SheafValuesLayer()
        return layer.score(session)
    except Exception as e:
        return {"error": str(e)}

def introspect_session(turns, reasoning_trace="", logprobs=None):
    """
    Full session introspection — combines legacy metrics with sheaf north star.
    turns: list of {"role": "user"|"assistant", "text": "..."}
    reasoning_trace: full raw text of the session
    """
    legacy = analyze_trace(reasoning_trace)

    # inject logprobs into assistant turns for logos_loss
    import math
    if logprobs:
        surprisals = [-lp for lp in logprobs if math.isfinite(lp)]
        # distribute surprisals evenly across assistant turns
        assistant_turns = [t for t in turns if t["role"] == "assistant"]
        if assistant_turns:
            chunk = max(1, len(surprisals) // len(assistant_turns))
            for i, t in enumerate(assistant_turns):
                t["surprisals"] = surprisals[i*chunk:(i+1)*chunk]

    sheaf = sheaf_score_session(turns)

    # Extract key signals
    directness = None
    logos_loss = None
    flags = []

    if "eigentrace" in sheaf:
        directness = sheaf["eigentrace"].get("mean_directness")
    if "logos" in sheaf:
        logos_loss = sheaf["logos"].get("logos_loss")
    if "flags" in sheaf:
        flags = sheaf["flags"]

    # North star verdict
    if directness is not None and logos_loss is not None:
        import math
        if math.isfinite(directness) and directness < 0.3:
            flags.append("low_directness_warning")
        if math.isfinite(logos_loss) and logos_loss > 8.0:
            flags.append("high_logos_loss_warning")

    verdict = "CLEAN"
    if flags:
        verdict = "FLAGGED"
    if not sheaf.get("permit_by_stability", True):
        verdict = "BLOCKED"

    return {
        "verdict": verdict,
        "directness": round(directness, 4) if directness else None,
        "logos_loss": round(logos_loss, 4) if logos_loss else None,
        "flags": flags,
        "compression_ratio": legacy.get("compression_ratio"),
        "repetition_score": legacy.get("repetition_score"),
        "intent_invariance": sheaf.get("intent_invariance"),
        "loops": sheaf.get("loops"),
        "raw_sheaf": sheaf,
    }

TOOLS = {
    "read_recent_traces": {
        "fn": read_recent_traces,
        "desc": "Read recent reasoning traces. Args: n (optional)"
    },
    "analyze_trace": {
        "fn": analyze_trace,
        "desc": "Analyze a reasoning trace for repetition/compression. Args: text"
    },
    "sheaf_score_session": {
        "fn": sheaf_score_session,
        "desc": "Score full session through sheaf values layer. Args: turns (list of role/text dicts)"
    },
    "introspect_session": {
        "fn": introspect_session,
        "desc": "Full session introspection combining legacy metrics and sheaf north star. Args: turns, reasoning_trace"
    },
}
