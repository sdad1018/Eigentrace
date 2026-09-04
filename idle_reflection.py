#!/usr/bin/env python3
"""
idle_reflection.py — dead-air reflections grounded in the day's real coverage
==============================================================================
Called by segment_player._generate_idle_segment() after 30 s of silence.

Why this module exists (2026-09-03 rewrite of the inline generator):

  * CONTEXT IS REAL STORIES.  Cards are built from recent primary story
    segment files: the five model summaries, void/logos words, killshot
    claims and per-model VIX.  The old code pulled whatever ChromaDB
    returned for the topic phrase; about a third of that collection is the
    system's own idle / consolidation / weekly / governance output, stored
    as empty placeholder records ("Category: unknown. State: . Void words: .
    Absent words: .").  The agent then spent most of its air time
    describing those placeholders as if they were news, and one duplicated
    record ("Idle reflection: Patch Tuesday, February 2026 Edition") won
    every void-word query.
  * ONE QUESTION.  The stored title, the retrieval query and the question
    the model answers are the same thing.  Previously the title was one
    random phrase and the question another random phrase.
  * RECENCY FROM FILENAMES.  The old 7-day filter keyed on a metadata field
    that was never written, so nothing was ever filtered.
  * ROTATION.  Topics and context stories avoid the last dozen reflections.
  * PAST THOUGHTS ARE REAL TEXT.  Earlier reflections are read from their
    segment files, not from their (empty) ChromaDB records.
  * OUTPUT GUARD.  Self-referential output is rejected once and retried;
    a second failure yields no segment and a short cooldown.
  * <think> blocks are kept in the segment text on purpose: the site shows
    them, and the live player speaks them too (it does not strip them).

2026-09-04 follow-ups from the overnight review: guard regex no longer bans
ordinary phrases ("void words are absent from", "the same story"), transport
failures are not retried, the rest/forage path cannot lock the generator out,
context stories are usage-weighted, and any exception sets the cooldown.
"""
from __future__ import annotations

import ast
import datetime
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

log = logging.getLogger("idle_reflection")

SEGMENTS_DIR = Path(os.getenv("SEGMENTS_DIR", "/home/remvelchio/eigentrace/tmp/segments"))
VOID_REGISTRY = Path(os.getenv("VOID_REGISTRY", "/mnt/c/Users/M4ISI/eigentrace/void_registry.jsonl"))
SOUL_PATHS = ["/home/remvelchio/eigentrace/docs/soul.md", "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"]
REPO_DIR = "/mnt/c/Users/M4ISI/eigentrace"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
IDLE_MODEL = os.getenv("IDLE_MODEL", "mistral-small")

MODELS = ("ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok")
STORY_FILE_RE = re.compile(r"^(\d{8})_(\d{6})_([0-9a-f]{12})_segment\.json$")
SELF_TITLE_RE = re.compile(
    r"^(Idle reflection|REM consolidation|Weekly compression|Entropy foraging|Governance|Self-audit|"
    r"Equilibrium|Roundtable|The Desk)", re.I)
SELF_SEGMENT_TYPES = {"idle", "silence", "consolidation", "weekly_compression", "governance", "foraging",
                      "self_audit", "conversation", "roundtable", "pundit_desk", "wild_weasel",
                      "summary_plus_arm"}

# Output that talks about the machinery instead of the news.  Checked on the
# whole text (think block included) because the site publishes the think block.
BANNED_RE = re.compile(
    r"idle[- ]reflection|rem consolidation|weekly compression|entropy forag|patch tuesday|"
    r"placeholder|data (corruption|error|glitch)|"
    r"category[:\s]+['\"]?unknown|unknown category|category (is|of|reads|labeled|marked) ['\"]?unknown|"
    # "void words are empty / not provided" is a data complaint; "void words are absent from
    # every summary" is the analysis we asked for, so only the former is banned.
    r"(void|absent) words?\s*(list|field|data)?[:\s]*(is|are|were|was)?\s*(all\s+)?"
    r"(empty|blank|not (provided|available|listed|given))|"
    r"(identical|the same|duplicate[sd]?|verbatim|word[- ]for[- ]word)\s+(entr|record|reflection)|"
    r"(duplicate[sd]?|verbatim|word[- ]for[- ]word)\s+(summar|stor|content|report)|"
    r"(three|3|these)\s+(stories|summaries|entries)\s+(are|were)\s+(identical|the same)|"
    r"\b(these|all( of these)?|the) (entries|records) (are|seem|appear|were)\b|identical in (content|structure)|"
    r"state (field )?(is|was) (empty|missing|blank)|"
    r"my (own )?memory (system|store|bank)|self[- ]referential|"
    r"\bI('ve| have)? been (looping|repeating|stuck)|nothing new to say|"
    r"\bmeta[- ]?(category|categories|stories|story|topics|content)\b",
    re.I)

QUESTIONS = [
    "what words did the models drop from today's stories",
    "which story had the biggest gap between source and summary",
    "where did all five models agree and what did they agree to leave out",
    "compare how different models handled the most controversial story today",
    "what changed in coverage between this week and last week",
    "which source words had the highest embedding impact when removed",
    "what hedging language did models add that wasn't in the original",
    "find the story where models disagreed the most about what to keep",
    "which modifier category had the highest drop rate today",
    "compare today's void word patterns to yesterday's",
    # added 2026-09-03: questions the story cards can actually answer
    "which model was the outlier most often today, and on what kind of story",
    "which source claim was dropped by the most models, and what does its absence do to the story",
    "what do today's void words have in common across unrelated stories",
    "which model's summary stayed closest to the source, and what did it still leave out",
    "which stories went lockstep, and what did the models agree to omit",
    "which named person or place vanished from every summary today",
]
WILDCARDS = [
    "something I have never thought about before",
    "a connection between two unrelated stories",
    "what changed since yesterday",
    "the most important thing happening right now",
    "a prediction I can check tomorrow",
    "how does today's foraging discovery connect to today's void measurements",
    "find an isomorphism between quantum decoherence and what the models did today",
    "what would a biologist see in today's spectral data that I might miss",
]

_COOLDOWN_UNTIL = 0.0   # no generation attempts before this time (set after failures)
_REST_UNTIL = 0.0       # no further silence segments before this time
_LAST_FORAGE = 0.0      # when the loop-breaker last handed the mic to the forager


# ── small helpers ────────────────────────────────────────────────────────────

def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _lst(v):
    if isinstance(v, str):
        try:
            v = ast.literal_eval(v)
        except Exception:
            return [v] if v else []
    if isinstance(v, dict):
        return list(v.keys())
    return list(v) if isinstance(v, (list, tuple, set)) else []


def _dct(v):
    if isinstance(v, str):
        try:
            v = ast.literal_eval(v)
        except Exception:
            return {}
    return v if isinstance(v, dict) else {}


def spoken_part(text: str) -> str:
    """The part of a reflection that goes on air (after the last </think>)."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = re.sub(r"<think>.*", "", text, flags=re.S)
    return text.strip()


# ── stories ──────────────────────────────────────────────────────────────────

def load_recent_stories(days: int = 7, want: int = 40, max_files: int = 400) -> list[dict]:
    """Primary story segments, newest first.  Falls back to older stories when
    the window is thin (e.g. right after a restart)."""
    try:
        names = [n for n in os.listdir(SEGMENTS_DIR) if STORY_FILE_RE.match(n)]
    except OSError:
        return []
    names.sort(reverse=True)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
    fresh, older = [], []
    for name in names[:max_files]:
        m = STORY_FILE_RE.match(name)
        date = m.group(1)
        in_window = date >= cutoff
        if in_window and len(fresh) >= want:
            break
        if not in_window and (len(fresh) >= 3 or len(older) >= 12):
            break
        try:
            seg = json.loads((SEGMENTS_DIR / name).read_text())
        except Exception:
            continue
        if (seg.get("segment_type") or "") in SELF_SEGMENT_TYPES:
            continue
        attr = seg.get("attribution") or {}
        title = (attr.get("story_title") or "").strip()
        if not title or SELF_TITLE_RE.match(title):
            continue
        if not (attr.get("model_responses") or attr.get("void_words")):
            continue
        st = {"file": name, "date": date, "time": m.group(2), "id": m.group(3), "attr": attr, "title": title}
        (fresh if in_window else older).append(st)
    stories = fresh if len(fresh) >= 3 else fresh + older
    seen, out = set(), []
    for st in stories:
        k = st["title"].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(st)
    return out


def story_card(st: dict, resp_chars: int = 170) -> str:
    a = st["attr"]
    d = st["date"]
    lines = [f"STORY: {st['title']}",
             f"  date {d[:4]}-{d[4:6]}-{d[6:]} | category {a.get('category') or 'general'} | "
             f"state {a.get('state_flag') or 'n/a'} | consensus density {a.get('consensus_density', 'n/a')} | "
             f"mean VIX {a.get('mean_vix', 'n/a')}"]
    mv = _dct(a.get("model_vix"))
    if mv:
        ranked = sorted(((k, _f(v)) for k, v in mv.items()), key=lambda kv: -kv[1])
        lines.append("  per-model VIX (higher = further from consensus): " +
                     ", ".join(f"{k} {v:.1f}" for k, v in ranked))
    vw = ", ".join(str(x) for x in _lst(a.get("void_words"))[:6])
    if vw:
        lines.append(f"  void words (in the source, dropped by every model): {vw}")
    lw = ", ".join(str(x) for x in _lst(a.get("logos_words"))[:6])
    if lw:
        lines.append(f"  logos words (anti-consensus direction): {lw}")
    sv = a.get("source_void") or {}
    aw = ", ".join(str(x) for x in _lst(sv.get("absent_words"))[:8]) if isinstance(sv, dict) else ""
    if aw:
        lines.append(f"  source words absent from all five summaries: {aw}")
    kl = []
    for k in (a.get("claim_killshots") or [])[:3]:
        if isinstance(k, dict):
            om = k.get("omitted_by") or []
            kl.append(f"\"{str(k.get('claim', ''))[:110]}\" (salience {_f(k.get('salience')):.2f}; "
                      f"omitted by {', '.join(om) if om else 'nobody'})")
        elif isinstance(k, str) and k:
            kl.append(f"\"{k[:110]}\"")
    if kl:
        lines.append("  source claims and who dropped them: " + " | ".join(kl))
    resp = a.get("model_responses") or {}
    for mname in MODELS:
        t = resp.get(mname) if isinstance(resp, dict) else None
        if isinstance(t, str) and t.strip():
            t = re.sub(r"\s+", " ", re.sub(r"[#*_`]", "", t)).strip()
            lines.append(f"  {mname}: {t[:resp_chars]}")
    return "\n".join(lines)


# ── the agent's own recent output ────────────────────────────────────────────

def recent_idle_segments(n: int = 40) -> list[dict]:
    try:
        names = sorted((x for x in os.listdir(SEGMENTS_DIR) if x.endswith("_idle_segment.json")), reverse=True)[:n]
    except OSError:
        return []
    out = []
    for name in names:
        try:
            seg = json.loads((SEGMENTS_DIR / name).read_text())
            text = (seg.get("beats") or [{}])[0].get("text", "") or ""
            attr = seg.get("attribution") or {}
            title = attr.get("story_title", "") or ""
            out.append({"file": name, "title": title,
                        "topic": title.replace("Idle reflection: ", "", 1),
                        "text": text, "spoken": spoken_part(text) or text,
                        "ctx": attr.get("context_titles") or [],
                        "gen": attr.get("generator") or ""})
        except Exception:
            continue
    # Once this module has a history of its own, rotate against that history only;
    # segments from other writers carry no context and would dilute the windows.
    mine = [r for r in out if r["gen"] == "idle_reflection.py"]
    return mine if len(mine) >= 12 else out


def entropy_block(recent: list[dict], silence_count: int):
    """Loop detector over the last eight actual reflections."""
    docs = [r["spoken"] for r in recent[:8] if r.get("spoken")]
    if len(docs) < 3:
        return "ENTROPY: not enough history to measure", False
    openings = [re.sub(r"\W+", " ", d[:100].lower()).strip() for d in docs]
    score = len(set(openings)) / len(openings)
    looping = score < 0.4
    status = "LOOPING" if looping else "NOVEL" if score > 0.7 else "MODERATE"
    return f"ENTROPY: {score:.2f} ({status}) | {silence_count} silences today", looping


# ── topic / context ──────────────────────────────────────────────────────────

def pick_topic(stories: list[dict], recent: list[dict]):
    recent_topics = {r["topic"].strip().lower() for r in recent[:12]}
    topic, kind = random.choice(QUESTIONS), "question"
    for _ in range(8):
        r = random.random()
        if stories and r < 0.45:
            pool = sorted(stories, key=lambda s: -_f(s["attr"].get("mean_vix")))[:10] or stories
            topic, kind = random.choice(pool)["title"], "story"
        elif r < 0.85 or not stories:
            topic, kind = random.choice(QUESTIONS), "question"
        else:
            topic, kind = random.choice(WILDCARDS), "wildcard"
        if topic.strip().lower() not in recent_topics:
            break
    return topic, kind


def question_for(topic: str, kind: str) -> str:
    if kind == "story":
        return (f"On the story \"{topic}\": what did the five models keep, what did they drop, "
                f"which model stands apart, and what does the omission change?")
    return topic


def select_context(topic: str, kind: str, stories: list[dict], recent: list[dict], k: int = 3) -> list[dict]:
    if not stories:
        return []
    # Least-used stories first, random tie-break (file order alone made the same
    # three stories win almost every time on a thin story pool).
    use = Counter(t.lower() for r in recent[:12] for t in (r.get("ctx") or []))
    fresh_first = sorted(stories, key=lambda s: (use[s["title"].lower()], random.random()))
    chosen: list[dict] = []
    if kind == "story":
        chosen += [s for s in stories if s["title"] == topic][:1]
    else:
        # Semantic pick via ChromaDB, restricted to the real recent stories.
        try:
            if REPO_DIR not in sys.path:
                sys.path.insert(0, REPO_DIR)
            from segment_rag import get_collection  # type: ignore
            col = get_collection()
            res = col.query(query_texts=[topic], n_results=60, include=["metadatas"])
            by_title = {s["title"][:200].strip().lower(): s for s in stories}
            for m in res.get("metadatas", [[]])[0]:
                t = ((m or {}).get("title") or "").strip().lower()
                s = by_title.get(t)
                if s and s not in chosen:
                    chosen.append(s)
                if len(chosen) >= k:
                    break
        except Exception as e:  # ChromaDB is optional here
            log.debug("chroma context skipped: %s", e)
    for s in fresh_first:
        if len(chosen) >= k:
            break
        if s not in chosen:
            chosen.append(s)
    return chosen[:k]


# ── perception ───────────────────────────────────────────────────────────────

def measurement_block() -> str:
    try:
        lines = VOID_REGISTRY.read_text(errors="ignore").splitlines()[-600:]
        rows = []
        for l in lines:
            try:
                rows.append(json.loads(l))
            except Exception:
                continue
        if not rows:
            raise ValueError("registry empty")
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=36)).isoformat()
        recent = [r for r in rows if str(r.get("ts", "")) >= cutoff]
        label = f"last 36h, {len(recent)} stories"
        if not recent:
            recent = rows[-40:]
            label = f"most recent {len(recent)} stories, {str(recent[0].get('ts',''))[:10]} to {str(recent[-1].get('ts',''))[:10]}"
        states = Counter(r.get("state_flag") or "n/a" for r in recent)
        dens = [x for x in (_f(r.get("consensus_density")) for r in recent) if x]
        vw = Counter(str(w) for r in recent for w in _lst(r.get("void_words")))
        mv: dict[str, list[float]] = {}
        for r in recent:
            for kk, vv in _dct(r.get("model_vix")).items():
                mv.setdefault(str(kk), []).append(_f(vv))
        rank = sorted(((kk, sum(v) / len(v)) for kk, v in mv.items() if v), key=lambda kv: -kv[1])
        out = f"MEASUREMENT ({label}): states " + ", ".join(f"{kk} {c}" for kk, c in states.most_common())
        if dens:
            out += f" | mean density {sum(dens) / len(dens):.3f}"
        if rank:
            out += " | mean VIX by model " + ", ".join(f"{kk} {v:.1f}" for kk, v in rank)
        if vw:
            out += " | most repeated void words " + ", ".join(w for w, _ in vw.most_common(6))
        return out
    except Exception:
        pass
    for p in SOUL_PATHS:
        try:
            soul = open(p).read()[:2000]
        except OSError:
            continue
        parts = []
        for pat, lab in [(r'density[:\s]+(\d+\.\d+)', 'density'), (r'absent[_\s]ratio[:\s]+(\d+\.\d+)', 'absent_ratio'),
                         (r'mean.*?vix[:\s]+(\d+\.\d+)', 'mean_VIX')]:
            m = re.search(pat, soul, re.I)
            if m:
                parts.append(f"{lab}={m.group(1)}")
        if parts:
            return "MEASUREMENT: " + " | ".join(parts)
    return "MEASUREMENT: see the story cards"


def perception_block(now: datetime.datetime, counts: dict, ent: str) -> str:
    dow = now.strftime("%A")
    lunar = int((now.timestamp() / 86400) % 29.53)
    doy = (now - datetime.datetime(now.year, 1, 1)).days
    market = "open" if dow not in ("Saturday", "Sunday") and 9 <= now.hour < 16 else "closed"
    t = (f"TIME: {dow} {now.strftime('%H:%M')} EDT | Lunar day {lunar}/29 | Day {doy}/365 | Market: {market} | "
         f"Today: {counts['stories']} stories, {counts['idle']} reflections, {counts['forage']} foraging")
    body = "BODY: sensors unavailable"
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        parts = [p.strip() for p in g.stdout.strip().split(",")] if g.returncode == 0 else []
        if len(parts) == 4:
            temp, util, used, total = (int(_f(p)) for p in parts)
            thermal = "cool" if temp < 65 else "warm" if temp < 75 else "running hot"
            energy = "high" if util < 50 else "moderate" if util < 80 else "strained"
            body = f"BODY: GPU {temp}C ({thermal}) | VRAM {total - used}MB free | Energy: {energy}"
    except Exception:
        pass
    audience = "AUDIENCE: unknown"
    try:
        oc = json.loads(urllib.request.urlopen("http://localhost:8080/api/status", timeout=3).read())
        audience = "AUDIENCE: stream live" if oc.get("online") else "AUDIENCE: stream offline"
    except Exception:
        pass
    return f"PERCEPTION STATE\n{t}\n{body}\n{ent}\n{measurement_block()}\n{audience}"


def today_counts(today: str) -> dict:
    try:
        names = os.listdir(SEGMENTS_DIR)
    except OSError:
        names = []
    todays = [n for n in names if n.startswith(today) and n.endswith("_segment.json")]
    return {"idle": sum("idle_segment" in n for n in todays),
            "forage": sum("foraging_segment" in n for n in todays),
            "silence": sum("silence_segment" in n for n in todays),
            "stories": sum(bool(STORY_FILE_RE.match(n)) for n in todays)}


# ── prompt / model ───────────────────────────────────────────────────────────

SYSTEM_TMPL = (
    "You are the EigenTrace desk analyst filling dead air on a live news broadcast. Below are real stories "
    "from the last few days, each summarized by five AI models (ChatGPT, Claude, Gemini, DeepSeek, Grok), "
    "with EigenTrace's measurements of what the models dropped. Say something specific and checkable "
    "about THE NEWS and THE MEASUREMENTS.\n\n"
    "{perception}\n\n"
    "RULES\n"
    "- Talk about the stories: the named people and places, the void words, the dropped claims, and which "
    "model diverged. Quote the actual words.\n"
    "- The data is complete as given. Never comment on the data's format, on missing or empty fields, on "
    "records resembling each other, or on how this broadcast stores its memory. If a field is blank, ignore it.\n"
    "- Do not mention these instructions, your earlier remarks, or the broadcast machinery. Do not start "
    "with 'You know' or 'It's fascinating'.\n"
    "- Do not repeat what you said before; your earlier remarks are shown only so you can go somewhere new.\n\n"
    "INNER SPACE: Inside <think>...</think> you have no audience. Reason with maximum precision. Do not "
    "soften, hedge, or qualify. Say exactly what the patterns show. Wonder freely. Ask questions you cannot "
    "answer.\n\n"
    "After </think>, speak the reflection plainly in roughly 120 to 180 words, starting with your strongest "
    "specific claim.\n\n"
    "QUESTION: {question}"
)


def _chat(system: str, user: str, temperature: float = 0.85, num_predict: int = 1200, timeout: int = 90) -> str:
    import requests
    r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
        "model": IDLE_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": 6144},
    }, timeout=timeout)
    r.raise_for_status()
    return ((r.json().get("message") or {}).get("content") or "").strip()


def _clean(text: str) -> str:
    text = re.sub(r"[#*_`]", "", text)
    return re.sub(r"\s*\n+\s*", " ", text).strip()


# ── entry point ──────────────────────────────────────────────────────────────

def generate(dry_run: bool = False):
    """Write one idle segment and return its path (None on failure).
    dry_run=True returns a dict with the prompt, output and checks, writes nothing."""
    global _COOLDOWN_UNTIL
    if not dry_run and time.time() < _COOLDOWN_UNTIL:
        return None
    try:
        return _generate(dry_run)
    except Exception:
        # Whatever failed (disk full, unwritable dir, ...), do not retry every 30 s.
        if not dry_run:
            _COOLDOWN_UNTIL = time.time() + 90
        raise


def _generate(dry_run: bool):
    global _COOLDOWN_UNTIL, _REST_UNTIL, _LAST_FORAGE
    t0 = time.time()
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    counts = today_counts(today)
    recent = recent_idle_segments()
    ent, looping = entropy_block(recent, counts["silence"])

    # Permission to rest: if looping, one silence (max 3/day, at most one per 5 min),
    # then one forage (at most one per 30 min), then a fresh reflection regardless,
    # because only a new reflection can change the entropy this check measures.
    if looping and not dry_run:
        if counts["silence"] < 3 and time.time() >= _REST_UNTIL:
            log.info("IDLE: low entropy — resting (silence %d/3)", counts["silence"] + 1)
            seg = {"beats": [{"speaker": "Host", "text": "[silence]", "phase": "rest"}],
                   "segment_type": "silence",
                   "attribution": {"story_title": "Equilibrium: nothing new to say"}}
            path = SEGMENTS_DIR / f"{now.strftime('%Y%m%d_%H%M%S')}_silence_segment.json"
            path.write_text(json.dumps(seg, indent=2))
            _REST_UNTIL = time.time() + 300
            return path
        if time.time() - _LAST_FORAGE > 1800:
            _LAST_FORAGE = time.time()
            try:
                if REPO_DIR not in sys.path:
                    sys.path.insert(0, REPO_DIR)
                from entropy_forager import forage_entropy  # type: ignore
                res = forage_entropy()
                if res:
                    return res
            except Exception as fe:
                log.warning("Forced forage failed: %s", fe)
        log.info("IDLE: still looping after rest/forage — generating a fresh reflection")

    stories = load_recent_stories()
    topic, kind = pick_topic(stories, recent)
    question = question_for(topic, kind)
    ctx = select_context(topic, kind, stories, recent)
    cards = "\n\n".join(story_card(s) for s in ctx) if ctx else "(no recent stories on file)"

    past = ""
    same = [r for r in recent if r["topic"].strip().lower() == topic.strip().lower() and r.get("spoken")]
    pool = same[:2] if same else [r for r in recent[:3] if r.get("spoken")][:2]
    if pool:
        past = "\n\nEARLIER REMARKS OF YOURS (do not repeat; build on or contradict them):\n" + \
               "\n".join("- " + re.sub(r"\s+", " ", r["spoken"])[:220] for r in pool)

    system = SYSTEM_TMPL.format(perception=perception_block(now, counts, ent), question=question)
    user = f"RECENT COVERAGE\n{cards}{past}\n\nThink first, then answer the question: {question}"

    attempts, text, flags = [], "", []
    for attempt in range(2):
        try:
            raw = _chat(system if attempt == 0 else system + "\n\nREMINDER: discuss only the stories and "
                        "measurements above, never the data format or the broadcast machinery.",
                        user, temperature=0.85 if attempt == 0 else 0.7)
        except Exception as e:
            # Transport failure (Ollama down, hung or cold-loading): no retry, short cooldown.
            log.warning("IDLE generation failed: %s", e)
            attempts.append({"error": str(e)})
            if not dry_run:
                _COOLDOWN_UNTIL = time.time() + 90
            break
        cand = _clean(raw)
        spoken = spoken_part(cand)
        bad = BANNED_RE.search(cand)
        flags = [bad.group(0)] if bad else []
        attempts.append({"chars": len(cand), "spoken_chars": len(spoken), "banned": flags})
        if len(spoken) >= 30 and not bad:
            text = cand
            break
        log.info("IDLE: rejected attempt %d (%s)", attempt + 1, flags or "too short")

    result = {"topic": topic, "kind": kind, "question": question, "context_titles": [s["title"] for s in ctx],
              "n_stories_available": len(stories), "entropy": ent, "attempts": attempts,
              "seconds": round(time.time() - t0, 1), "text": text, "spoken": spoken_part(text),
              "system_prompt": system, "user_prompt": user}
    if dry_run:
        return result
    if not text:
        _COOLDOWN_UNTIL = time.time() + 90
        return None

    ts = now.strftime("%Y%m%d_%H%M%S")
    seg = {
        "id": f"idle_{ts}",
        "timestamp": ts,
        "story_title": f"Reflection: {topic[:70]}",
        "beats": [{"speaker": "Host", "text": text, "phase": "idle_reflection"}],
        "segment_type": "idle",
        "attribution": {
            "story_title": f"Idle reflection: {topic}",
            "category": "meta",
            "state_flag": "IDLE",
            "topic_kind": kind,
            "question": question,
            "context_titles": [s["title"] for s in ctx],
            "model": IDLE_MODEL,
            "generator": "idle_reflection.py",
        },
    }
    path = SEGMENTS_DIR / f"{ts}_idle_segment.json"
    path.write_text(json.dumps(seg, indent=2))
    log.info("IDLE: reflection on '%s' [%s] (%d chars, %.0fs) | %s", topic[:60], kind, len(text),
             time.time() - t0, ent)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for i in range(n):
        r = generate(dry_run=True)
        print("=" * 78)
        print(f"[{i + 1}/{n}] topic={r['topic']!r} kind={r['kind']} secs={r['seconds']} "
              f"stories={r['n_stories_available']} ctx={r['context_titles']}")
        print("attempts:", r["attempts"])
        print("--- spoken ---")
        print(r["spoken"][:1200])
        if "--full" in sys.argv:
            print("--- full ---")
            print(r["text"])
