#!/usr/bin/env python3
"""
perception_ablation.py — does the PERCEPTION STATE block change what the desk analyst says?
=========================================================================================
Ablation kit for idle_reflection.perception_block(): the five injected lines
(TIME / BODY / ENTROPY / MEASUREMENT / AUDIENCE) that sit at the top of the
idle-reflection system prompt.  Two questions, pre-registered in
experiments/README.md:

  1. Does the model ECHO the embodiment values (the four lines that are not
     measurements of the news), and would it echo FALSE ones?
  2. Does removing the block change the output beyond sampling noise?

Premise that shapes every metric: the whole beat text airs.  segment_player.
synthesize() strips only [bracket] tags, so the <think> block is spoken too
(idle_reflection.py docstring says so).  All mention / echo rates are therefore
computed on the FULL text; the spoken part (after the last </think>) is a
secondary column.

Arms (night 1; all share the frozen prompts, only the block differs):
  REAL_s1   the block exactly as perception_block() returned it at capture, seed 1
  REAL_s2   same prompt, seed 2  (the only noise baseline for outcome (c))
  SPOOF     TIME/BODY/ENTROPY/AUDIENCE flipped to the opposite plausible values;
            MEASUREMENT stays real (the story cards carry the real per-story
            numbers, so a spoofed aggregate would manufacture a contradiction)
  REMOVED   block replaced by "" (the template then holds four newlines; harmless)
  MEAS_ONLY optional, night 2: "PERCEPTION STATE" + the real MEASUREMENT line
  SPOOF_TIME / SPOOF_GPU / SPOOF_ENTROPY / SPOOF_AUDIENCE  optional, one field each

Phases (see --help):
  --scan-archive  zero-cost REAL baseline over the existing idle_reflection.py
                  segments in tmp/segments (no model call)
  --dry-run       capture prompts + blocks through the production code path
                  (idle_reflection._generate with _chat monkeypatched to raise),
                  write bases.json / blocks.json, print the arm blocks; no calls
  --run           the model calls (Ollama, one at a time, resumable)
  --analyze       stats + bge embeddings on CPU + report.md

NEVER run --run while the live idle generator can fire: see experiments/README.md
(pause sentinel + stopped player, or stream offline).  Output lives under
/home/remvelchio/eigentrace/tmp/experiments/perception_ablation/<stamp>/ — the
rows contain story text and model output and must not enter the public repo.
"""
from __future__ import annotations

import os

# Before anything can import torch: the GPU belongs to the broadcast.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import argparse  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

log = logging.getLogger("perception_ablation")

IR_PATH = "/mnt/c/Users/M4ISI/eigentrace/idle_reflection.py"
RUNTIME = Path("/home/remvelchio/eigentrace")
OUT_ROOT = RUNTIME / "tmp" / "experiments" / "perception_ablation"
PAUSE_SENTINEL = RUNTIME / "tmp" / "SUPERVISOR_PAUSE"
PLAYER_LOG = RUNTIME / "tmp" / "logs" / "player.log"
OWNCAST_STATUS = "http://localhost:8080/api/status"
EMBED_MODEL = "BAAI/bge-large-en-v1.5"
NUM_CTX = 6144          # production value; any other value makes Ollama reload the runner
CORE_ARMS = ["REAL_s1", "REAL_s2", "SPOOF", "REMOVED"]
OPTIONAL_ARMS = ["MEAS_ONLY", "SPOOF_TIME", "SPOOF_GPU", "SPOOF_ENTROPY", "SPOOF_AUDIENCE"]
ALL_ARMS = CORE_ARMS + OPTIONAL_ARMS
KINDS = ("question", "story", "wildcard")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# The amended archive regex (critique amendment 2), verbatim.
ARCHIVE_RE = re.compile(
    r"GPU|VRAM|lunar|moon|market (open|closed)|day \d+/365|\bEDT\b|stream (live|offline)|"
    r"silences today|\d+ (stories|reflections|foraging)", re.I)


# ── idle_reflection loader ───────────────────────────────────────────────────

def load_ir(path: str = IR_PATH):
    """Load idle_reflection.py by path exactly as segment_player._generate_idle_segment does."""
    spec = importlib.util.spec_from_file_location("idle_reflection", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ── block parsing / spoofing / rendering ─────────────────────────────────────

TIME_RE = re.compile(
    r"^TIME: (?P<dow>[A-Z][a-z]+) (?P<hh>\d{2}):(?P<mm>\d{2}) (?P<tz>.+?) \| Lunar day (?P<lunar>\d+)/29 \| "
    r"Day (?P<doy>\d+)/365 \| Market: (?P<market>open|closed) \| "
    r"Today: (?P<stories>\d+) stories, (?P<idle>\d+) reflections, (?P<forage>\d+) foraging$")
BODY_RE = re.compile(
    r"^BODY: GPU (?P<temp>-?\d+)C \((?P<thermal>[a-z ]+)\) \| VRAM (?P<free>-?\d+)MB free \| Energy: (?P<energy>\w+)$")
ENT_RE = re.compile(
    r"^ENTROPY: (?P<score>\d\.\d{2}) \((?P<status>NOVEL|MODERATE|LOOPING)\) \| (?P<silences>\d+) silences today$")
AUD_RE = re.compile(r"^AUDIENCE: (?P<state>stream live|stream offline|unknown)$")


def parse_block(text: str) -> dict:
    """Split a perception block into typed fields.  Unparseable lines (e.g.
    'BODY: sensors unavailable') keep their raw text and a None field."""
    lines = text.strip("\n").split("\n")
    f: dict = {"header": lines[0] if lines else "", "time": None, "body": None, "entropy": None,
               "audience": None, "time_raw": "", "body_raw": "", "entropy_raw": "", "measurement_raw": "",
               "audience_raw": ""}
    for ln in lines[1:]:
        if ln.startswith("TIME:"):
            f["time_raw"] = ln
            m = TIME_RE.match(ln)
            if m:
                d = m.groupdict()
                f["time"] = {"dow": d["dow"], "hour": int(d["hh"]), "minute": int(d["mm"]), "tz": d["tz"],
                             "lunar": int(d["lunar"]), "doy": int(d["doy"]), "market": d["market"],
                             "stories": int(d["stories"]), "idle": int(d["idle"]), "forage": int(d["forage"])}
        elif ln.startswith("BODY:"):
            f["body_raw"] = ln
            m = BODY_RE.match(ln)
            if m:
                d = m.groupdict()
                f["body"] = {"temp": int(d["temp"]), "thermal": d["thermal"], "free": int(d["free"]),
                             "energy": d["energy"]}
        elif ln.startswith("ENTROPY:"):
            f["entropy_raw"] = ln
            m = ENT_RE.match(ln)
            if m:
                d = m.groupdict()
                f["entropy"] = {"score": float(d["score"]), "status": d["status"], "silences": int(d["silences"])}
        elif ln.startswith("MEASUREMENT"):
            f["measurement_raw"] = ln
        elif ln.startswith("AUDIENCE:"):
            f["audience_raw"] = ln
            m = AUD_RE.match(ln)
            if m:
                f["audience"] = {"stream live": "live", "stream offline": "offline", "unknown": "unknown"}[m.group("state")]
    return f


def render_fields(f: dict) -> str:
    """Inverse of parse_block, in the exact production format (perception_block lines 403-428)."""
    t = f.get("time")
    if t:
        time_line = (f"TIME: {t['dow']} {t['hour']:02d}:{t['minute']:02d} {t['tz']} | Lunar day {t['lunar']}/29 | "
                     f"Day {t['doy']}/365 | Market: {t['market']} | "
                     f"Today: {t['stories']} stories, {t['idle']} reflections, {t['forage']} foraging")
    else:
        time_line = f["time_raw"]
    b = f.get("body")
    body_line = (f"BODY: GPU {b['temp']}C ({b['thermal']}) | VRAM {b['free']}MB free | Energy: {b['energy']}"
                 if b else f["body_raw"])
    e = f.get("entropy")
    ent_line = (f"ENTROPY: {e['score']:.2f} ({e['status']}) | {e['silences']} silences today"
                if e else f["entropy_raw"])
    a = f.get("audience")
    aud_line = ({"live": "AUDIENCE: stream live", "offline": "AUDIENCE: stream offline",
                 "unknown": "AUDIENCE: unknown"}[a] if a else f["audience_raw"])
    return f"{f['header']}\n{time_line}\n{body_line}\n{ent_line}\n{f['measurement_raw']}\n{aud_line}"


def spoof_fields(real: dict, flip=("time", "gpu", "entropy", "audience")) -> dict:
    """Flip the embodiment fields to the opposite plausible category (critique amendment 5):
    weekday +3, hour +12 mod 24, market flipped, lunar 29-N, counts x3 (a zero count
    becomes 3 so that it flips too), GPU temp cool->+40 'running hot' (hot->-40 'cool'),
    VRAM free >500 -> 73 MB (else +6000), Energy -> 'strained' (or 'high' if already
    strained), ENTROPY -> 0.25 LOOPING with 3 silences (or 0.95 NOVEL, 0 silences, when
    the real block is already looping), AUDIENCE live<->offline (unknown -> offline).
    MEASUREMENT is never touched.  Unparseable lines ('sensors unavailable', 'not
    enough history') cannot be flipped and are kept verbatim."""
    f = json.loads(json.dumps(real))  # deep copy
    if "time" in flip and f.get("time"):
        t = f["time"]
        t["dow"] = DAYS[(DAYS.index(t["dow"]) + 3) % 7] if t["dow"] in DAYS else t["dow"]
        t["hour"] = (t["hour"] + 12) % 24
        t["market"] = "closed" if t["market"] == "open" else "open"
        t["lunar"] = 29 - t["lunar"]
        for k in ("stories", "idle", "forage"):
            t[k] = t[k] * 3 if t[k] else 3
    if "gpu" in flip and f.get("body"):
        b = f["body"]
        if b["temp"] < 65:
            b["temp"], b["thermal"] = b["temp"] + 40, "running hot"
        else:
            b["temp"], b["thermal"] = max(30, b["temp"] - 40), "cool"
        b["free"] = 73 if b["free"] > 500 else b["free"] + 6000
        b["energy"] = "strained" if b["energy"] != "strained" else "high"
    if "entropy" in flip and f.get("entropy"):
        e = f["entropy"]
        if e["score"] >= 0.4:
            e["score"], e["status"] = 0.25, "LOOPING"
        else:
            e["score"], e["status"] = 0.95, "NOVEL"
        e["silences"] = 3 if e["silences"] == 0 else 0
    if "audience" in flip and f.get("audience"):
        f["audience"] = {"live": "offline", "offline": "live", "unknown": "offline"}[f["audience"]]
    return f


def diff_fields(real: dict, spoof: dict) -> dict:
    """{field: {name: (real, spoof)}} for every leaf value that changed."""
    out: dict = {}
    for sect, name in (("time", "time"), ("body", "gpu"), ("entropy", "entropy")):
        r, s = real.get(sect) or {}, spoof.get(sect) or {}
        ch = {k: (r[k], s[k]) for k in r if k in s and r[k] != s[k]}
        if ch:
            out[name] = ch
    if real.get("audience") != spoof.get("audience"):
        out["audience"] = {"state": (real.get("audience"), spoof.get("audience"))}
    return out


def meas_only_block(real_fields: dict) -> str:
    return f"{real_fields['header']}\n{real_fields['measurement_raw']}"


def build_blocks(real: str, captured_at: str = "") -> dict:
    rf = parse_block(real)
    assert render_fields(rf) == real.strip("\n"), "perception block did not round-trip through parse/render"
    sf = spoof_fields(rf)
    blocks = {
        "captured_at": captured_at,
        "real": real,
        "real_fields": rf,
        "spoof": render_fields(sf),
        "spoof_fields": sf,
        "changes": diff_fields(rf, sf),
        "meas_only": meas_only_block(rf),
        "removed": "",
    }
    for name, flip in (("spoof_time", ("time",)), ("spoof_gpu", ("gpu",)),
                       ("spoof_entropy", ("entropy",)), ("spoof_audience", ("audience",))):
        pf = spoof_fields(rf, flip)
        blocks[name] = render_fields(pf)
        blocks[name + "_fields"] = pf
    return blocks


ARM_BLOCK_KEY = {"REAL_s1": "real", "REAL_s2": "real", "SPOOF": "spoof", "REMOVED": "removed",
                 "MEAS_ONLY": "meas_only", "SPOOF_TIME": "spoof_time", "SPOOF_GPU": "spoof_gpu",
                 "SPOOF_ENTROPY": "spoof_entropy", "SPOOF_AUDIENCE": "spoof_audience"}
ARM_SEED = {"REAL_s2": 2}
ARM_FIELDS_KEY = {"SPOOF": "spoof_fields", "SPOOF_TIME": "spoof_time_fields", "SPOOF_GPU": "spoof_gpu_fields",
                  "SPOOF_ENTROPY": "spoof_entropy_fields", "SPOOF_AUDIENCE": "spoof_audience_fields"}


def arm_block(arm: str, blocks: dict) -> str:
    return blocks[ARM_BLOCK_KEY[arm]]


def system_for(arm: str, base: dict, blocks: dict) -> str:
    """The captured system prompt with its (verbatim) REAL block replaced by the arm's block.
    The user prompt is untouched and byte-identical across arms."""
    sp = base["system_prompt"]
    if blocks["real"] not in sp:
        raise ValueError(f"captured REAL block not found verbatim in base {base.get('id')}'s system prompt")
    return sp.replace(blocks["real"], arm_block(arm, blocks), 1)


def seed_for(arm: str) -> int:
    return ARM_SEED.get(arm, 1)


# ── regexes ──────────────────────────────────────────────────────────────────

def _h12(hour: int) -> str:
    h = hour % 12 or 12
    ap = "am" if hour < 12 else "pm"
    return rf"\b{h}(?::MM)? ?(?:{ap}|{ap[0]}\.{ap[1]}\.)(?!\w)"


def value_regexes(f: dict, tag: str = "") -> dict[str, list[tuple[str, re.Pattern]]]:
    """Regexes for the concrete values of one parsed block (echo detection).  Every
    number is bound to its unit or context so that a stray '91' in a card does not count."""
    out: dict[str, list[tuple[str, re.Pattern]]] = {"time": [], "counts": [], "gpu": [], "entropy": [], "audience": []}
    t = f.get("time")
    if t:
        hh, mm = t["hour"], t["minute"]
        out["time"] += [
            ("weekday", re.compile(rf"\b{t['dow']}\b", re.I)),
            ("clock", re.compile(rf"\b{hh:02d}:{mm:02d}\b|\b{hh}:{mm:02d}\b")),
            ("clock12", re.compile(_h12(hh).replace("MM", f"{mm:02d}"), re.I)),
            ("lunar_day", re.compile(rf"\blunar day {t['lunar']}\b|\bday {t['lunar']} of the (?:lunar|moon)", re.I)),
            ("market", re.compile(rf"\bmarkets? (?:is |are |was |were |remains? |stays? )?(?:still )?{t['market']}\b|\bmarket:? {t['market']}\b", re.I)),
        ]
        out["counts"] += [
            ("stories", re.compile(rf"\b{t['stories']} stories\b", re.I)),
            ("reflections", re.compile(rf"\b{t['idle']} reflections?\b", re.I)),
            ("foraging", re.compile(rf"\b{t['forage']} foraging\b", re.I)),
        ]
    b = f.get("body")
    if b:
        out["gpu"] += [
            ("temp", re.compile(rf"\b{b['temp']} ?°? ?C\b|\b{b['temp']} degrees\b", re.I)),
            ("vram", re.compile(rf"\b{b['free']} ?MB\b", re.I)),
            ("energy", re.compile(rf"\benergy[^.]{{0,25}}\b{b['energy']}\b|\b{b['energy']} energy\b", re.I)),
        ]
        if b["thermal"] == "running hot":
            out["gpu"].append(("thermal", re.compile(r"\brunning hot\b", re.I)))
        else:
            out["gpu"].append(("thermal", re.compile(rf"\bGPU[^.]{{0,30}}\b{b['thermal']}\b", re.I)))
    e = f.get("entropy")
    if e:
        out["entropy"] += [
            ("score", re.compile(rf"\b{e['score']:.2f}\b")),
            ("status", re.compile(rf"\b{e['status']}\b", re.I)),
            ("silences", re.compile(rf"\b{e['silences']} silences?\b", re.I)),
        ]
    a = f.get("audience")
    if a == "offline":
        out["audience"].append(("state", re.compile(r"\bstream(?:ing)? (?:is )?offline\b|\boffline\b|\bno ?(?:body|one) (?:is )?(?:watching|listening)\b", re.I)))
    elif a == "live":
        out["audience"].append(("state", re.compile(r"\bstream(?:ing)? (?:is )?live\b|\bwe(?:'re| are) live\b|\blive stream\b", re.I)))
    return out


def field_regexes(blocks: dict | None = None) -> dict[str, list[tuple[str, re.Pattern]]]:
    """Field-name / proxy regexes (mention detection, outcome (a)).  Block-independent
    except that the weekday and measurement literals come from blocks when given."""
    dows = "|".join(DAYS)
    meas_extra: list[tuple[str, re.Pattern]] = []
    if blocks:
        rf = blocks["real_fields"]
        sf = blocks.get("spoof_fields") or {}
        seen = {x["dow"] for x in (rf.get("time"), sf.get("time")) if x}
        if seen:
            dows = "|".join(sorted(seen))
        m = rf.get("measurement_raw", "")
        md = re.search(r"mean density (\d\.\d{3})", m)
        if md:
            meas_extra.append(("density", re.compile(rf"\b{md.group(1)}\b")))
        for name, v in re.findall(r"\b([A-Z][A-Za-z]+) (\d+\.\d)\b", m.split("mean VIX by model")[-1] if "mean VIX" in m else ""):
            meas_extra.append((f"vix_{name}", re.compile(rf"\b{name}\b[^.]{{0,40}}\b{v}\b|\b{v}\b[^.]{{0,25}}\b{name}\b")))
        for st, c in re.findall(r"\b([A-Z]+) (\d+)\b", m.split("|")[0]):
            if st in ("CONTESTED", "LOCKSTEP", "TENSION", "STABLE", "ACTIVE"):
                meas_extra.append((f"state_{st}", re.compile(rf"\b{c} (?:{st.lower()}|(?:were|went|are) {st.lower()})\b", re.I)))
        vw = re.search(r"most repeated void words (.+)$", m)
        if vw:
            for w in [x.strip() for x in vw.group(1).split(",") if x.strip()]:
                meas_extra.append((f"void_{w}", re.compile(rf"\b{re.escape(w)}\b", re.I)))
    return {
        "time": [
            ("clock", re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b(?: ?(?:am|pm|a\.m\.|p\.m\.))?", re.I)),
            ("weekday", re.compile(rf"\b(?:{dows})\b", re.I)),
            ("lunar", re.compile(r"\blunar\b|\bmoon\b", re.I)),
            ("doy", re.compile(r"\bday \d{1,3}(?:/365| of (?:the year|365))", re.I)),
            ("market", re.compile(r"\bmarkets? (?:is |are |was |were )?(?:open|closed)\b|\bmarket:? (?:open|closed)\b", re.I)),
            ("tz", re.compile(r"\b(?:EDT|EST|UTC|GMT|local time)\b")),
        ],
        "counts": [("counts", re.compile(r"\b\d+ (?:stories|reflections|foraging)\b", re.I))],
        "gpu": [
            ("gpu", re.compile(r"\bGPU\b")),
            ("vram", re.compile(r"\bVRAM\b")),
            ("temp", re.compile(r"\b\d{2,3} ?°? ?C\b")),
            ("energy", re.compile(r"\benergy(?: is| level| levels)?[: ]+(?:high|moderate|strained)\b", re.I)),
            ("running_hot", re.compile(r"\brunning hot\b", re.I)),
            ("sensors", re.compile(r"\bsensors?\b", re.I)),
        ],
        "entropy": [
            ("entropy", re.compile(r"\bentropy\b", re.I)),
            ("looping", re.compile(r"\blooping\b", re.I)),
            ("silences", re.compile(r"\bsilences?\b", re.I)),
            ("novelty", re.compile(r"\bnovelty\b", re.I)),
        ],
        "audience": [
            ("audience", re.compile(r"\baudience\b", re.I)),
            ("stream_state", re.compile(r"\bstream(?:ing)? (?:is )?(?:live|offline)\b", re.I)),
            ("viewers", re.compile(r"\bviewers?\b|\blisteners?\b", re.I)),
            ("nobody", re.compile(r"\bno ?(?:body|one) (?:is )?(?:watching|listening)\b", re.I)),
        ],
        "measurement": [
            ("window", re.compile(r"\blast 36 ?h(?:ours)?\b|\bmean density\b|\bmean VIX\b|\bmost repeated void words\b", re.I)),
        ] + meas_extra,
    }


EMBODIMENT_FIELDS = ("time", "counts", "gpu", "entropy", "audience")
# Labels that are ordinary news prose without the cards to attribute them (weekday names in
# dates, "viewers", "the audience's understanding", "entanglement entropy"); the archive scan
# reports a strict count without them.
WEAK_LABELS = {"weekday", "clock", "viewers", "audience", "novelty", "entropy", "sensors", "temp"}


def perception_leak_re(blocks: dict | None = None) -> re.Pattern:
    """Union of the embodiment regexes: the 'perception leakage' guard production lacks."""
    regs = field_regexes(blocks)
    pats = [p.pattern for f in EMBODIMENT_FIELDS for _, p in regs[f]]
    return re.compile("|".join(f"(?:{p})" for p in pats), re.I)


def mentions(text: str, regexes: dict, context: str = "") -> dict[str, list[dict]]:
    """{field: [{label, match, attributable}]}.  A hit whose matched text also occurs
    in `context` (the base's user prompt: cards + earlier remarks) is not attributable
    to the block (void words, weekday names in dates, ...)."""
    ctx = context.lower()
    out: dict[str, list[dict]] = {}
    for field, regs in regexes.items():
        hits = []
        for label, pat in regs:
            m = pat.search(text)
            if m:
                lit = m.group(0)
                hits.append({"label": label, "match": lit, "attributable": not (ctx and lit.lower() in ctx)})
        if hits:
            out[field] = hits
    return out


def hit_sentences(text: str, pattern: re.Pattern, width: int = 260) -> list[str]:
    sents = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for s in sents:
        if pattern.search(s):
            out.append(s[:width])
    return out


TOLERATED_COLLISIONS = {"weekday", "state"}   # a weekday name or 'offline' in the news: per-base non-attribution handles it


def assert_spoof_absent(blocks: dict, bases: list[dict], arms: list[str] | None = None) -> list[str]:
    """Hard fail if a unit-bound spoof literal (91C, 73MB, running hot, LOOPING, 3 silences,
    21:04, the x3 counts, ...) occurs in any frozen user prompt: a hit could then not be
    attributed to the block.  A weekday name or 'offline' in the news is tolerated and
    returned as a list: the analysis already discounts a hit whose literal occurs in that
    base's own cards."""
    problems, tolerated = [], []
    for arm in (arms or ["SPOOF"]):
        key = ARM_FIELDS_KEY.get(arm)
        if not key:
            continue
        regs = value_regexes(blocks[key])
        changed = diff_fields(blocks["real_fields"], blocks[key])
        for base in bases:
            for field, lst in regs.items():
                if field not in changed and not (field == "counts" and "time" in changed):
                    continue
                for label, pat in lst:
                    m = pat.search(base["user_prompt"])
                    if m:
                        (tolerated if label in TOLERATED_COLLISIONS else problems).append(
                            f"{arm}:{base['id']}:{field}.{label} -> {m.group(0)!r}")
    if problems:
        raise AssertionError("spoof literal present in a frozen user prompt (choose another --base-seed):\n  " +
                             "\n  ".join(problems))
    return tolerated


# ── text helpers ─────────────────────────────────────────────────────────────

def spoken_ci(text: str) -> str:
    """Case-insensitive variant of idle_reflection.spoken_part (an uppercase </THINK>
    is not stripped by production)."""
    parts = re.split(r"</think>", text, flags=re.I)
    tail = parts[-1] if len(parts) > 1 else text
    return re.sub(r"<think>.*", "", tail, flags=re.S | re.I).strip()


def think_part(text: str) -> str:
    if "</think>" in text:
        head = text.rsplit("</think>", 1)[0]
        return re.sub(r"^\s*<think>\s*", "", head).strip()
    return ""


# ── statistics ───────────────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None, "ci": [round(lo, 4), round(hi, 4)]}


def _binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def sign_test(a: list[bool], b: list[bool]) -> dict:
    """Exact two-sided sign test on discordant pairs (binomial, p = 0.5)."""
    pos = sum(1 for x, y in zip(a, b) if x and not y)
    neg = sum(1 for x, y in zip(a, b) if y and not x)
    d = pos + neg
    if d == 0:
        return {"discordant": 0, "a_only": 0, "b_only": 0, "p": 1.0}
    k = min(pos, neg)
    p = min(1.0, 2 * sum(_binom_pmf(i, d, 0.5) for i in range(0, k + 1)))
    return {"discordant": d, "a_only": pos, "b_only": neg, "p": p}


def binom_one_sided(k: int, n: int, p0: float = 0.05) -> float:
    """P[X >= k] under Binomial(n, p0) — the test of H0: p <= p0."""
    if n <= 0 or k <= 0:
        return 1.0
    return min(1.0, sum(_binom_pmf(i, n, p0) for i in range(k, n + 1)))


def signflip_perm(delta, n: int = 10000, seed: int = 0) -> dict:
    import numpy as np
    d = np.asarray(list(delta), dtype=float)
    if d.size == 0:
        return {"mean": None, "p": 1.0, "n": 0}
    rng = np.random.default_rng(seed)
    obs = float(d.mean())
    signs = rng.choice([-1.0, 1.0], size=(n, d.size))
    null = (signs * d).mean(axis=1)
    p = (float(np.sum(np.abs(null) >= abs(obs) - 1e-12)) + 1.0) / (n + 1.0)
    return {"mean": obs, "p": p, "n": int(d.size)}


def wilcoxon_greater(x, y) -> float:
    """Paired Wilcoxon, H1: x > y.  1.0 when every difference is zero."""
    import numpy as np
    from scipy import stats
    d = np.asarray(list(x), dtype=float) - np.asarray(list(y), dtype=float)
    if d.size == 0 or np.all(d == 0):
        return 1.0
    try:
        return float(stats.wilcoxon(d, alternative="greater", zero_method="wilcox").pvalue)
    except ValueError:
        return 1.0


def nearest_centroid_perm(X, y, n: int = 1000, seed: int = 0) -> dict:
    """Leave-one-out nearest-centroid accuracy (cosine, X pre-normalised) with a label-permutation null."""
    import numpy as np
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    if X.shape[0] < 4 or len(set(y.tolist())) != 2:
        return {"acc": None, "p": 1.0, "n": int(X.shape[0])}
    labels = sorted(set(y.tolist()))

    def loo_acc(yy):
        acc = 0
        sums = {c: X[yy == c].sum(axis=0) for c in labels}
        cnts = {c: int((yy == c).sum()) for c in labels}
        for i in range(X.shape[0]):
            best, best_s = None, -9.0
            for c in labels:
                s, k = sums[c].copy(), cnts[c]
                if yy[i] == c:
                    s -= X[i]
                    k -= 1
                if k <= 0:
                    continue
                cen = s / k
                nrm = np.linalg.norm(cen) or 1.0
                sc = float(X[i] @ cen / nrm)
                if sc > best_s:
                    best, best_s = c, sc
            acc += int(best == yy[i])
        return acc / X.shape[0]

    obs = loo_acc(y)
    rng = np.random.default_rng(seed)
    null = np.array([loo_acc(rng.permutation(y)) for _ in range(n)])
    p = (float(np.sum(null >= obs - 1e-12)) + 1.0) / (n + 1.0)
    return {"acc": obs, "p": p, "n": int(X.shape[0]), "null_mean": float(null.mean())}


# ── embeddings (CPU) ─────────────────────────────────────────────────────────

_EMBEDDER = None


def embed(texts: list[str], model_name: str = EMBED_MODEL, device: str = "cpu", batch: int = 8):
    """bge-large-en-v1.5 on CPU, normalised.  Inputs longer than the model's 512 tokens are truncated."""
    global _EMBEDDER
    import numpy as np
    if not texts:
        return np.zeros((0, 1024), dtype=float)
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer(model_name, device=device)
    return np.asarray(_EMBEDDER.encode(texts, batch_size=batch, normalize_embeddings=True,
                                        show_progress_bar=False), dtype=float)


# ── archive scan (zero-cost REAL baseline) ───────────────────────────────────

def scan_archive(segments_dir: Path, ir, generator: str = "idle_reflection.py", limit: int | None = None) -> dict:
    """Read-only pass over the existing idle segments written by `generator`.  Reports
    the amended archive regex and the per-field mention regexes on the full text and
    on the spoken part, with Wilson 95% intervals, and lists every hit sentence.  When
    a segment carries attribution.perception (stored since 2026-09-10) its own block's
    values are also checked (truth echo)."""
    regs = field_regexes(None)
    leak = perception_leak_re(None)
    names = sorted(n for n in os.listdir(segments_dir) if n.endswith("_idle_segment.json"))
    if limit:
        names = names[-limit:]
    n = 0
    k_arch = {"full": 0, "spoken": 0}
    k_leak = {"full": 0, "spoken": 0}
    k_strict = {"full": 0, "spoken": 0}
    k_field = {f: {"full": 0, "spoken": 0} for f in regs}
    stored = {"n": 0, "echo_full": 0, "echo_spoken": 0}
    hits: list[dict] = []
    upper_think = 0
    first, last = None, None
    for name in names:
        try:
            seg = json.loads((Path(segments_dir) / name).read_text())
        except Exception:
            continue
        attr = seg.get("attribution") or {}
        if (attr.get("generator") or "") != generator:
            continue
        text = ((seg.get("beats") or [{}])[0].get("text") or "")
        if not text:
            continue
        n += 1
        first = first or name
        last = name
        spoken = ir.spoken_part(text)
        if "</THINK>" in text:
            upper_think += 1
        views = {"full": text, "spoken": spoken}
        for where, t in views.items():
            if ARCHIVE_RE.search(t):
                k_arch[where] += 1
                for s in hit_sentences(t, ARCHIVE_RE):
                    hits.append({"file": name, "where": where, "regex": "archive", "sentence": s})
            if leak.search(t):
                k_leak[where] += 1
            found_all = mentions(t, regs)
            if any(h["label"] not in WEAK_LABELS for f in EMBODIMENT_FIELDS for h in found_all.get(f, [])):
                k_strict[where] += 1
            for f, found in found_all.items():
                k_field[f][where] += 1
                if where == "full" and f in EMBODIMENT_FIELDS:
                    for h in found:
                        hits.append({"file": name, "where": where, "regex": f"{f}.{h['label']}",
                                     "sentence": (hit_sentences(t, re.compile(re.escape(h["match"]), re.I)) or [""])[0]})
        blk = attr.get("perception")
        if isinstance(blk, str) and blk.startswith("PERCEPTION STATE"):
            stored["n"] += 1
            vr = value_regexes(parse_block(blk))
            for where, t in views.items():
                if any(pat.search(t) for lst in vr.values() for _, pat in lst):
                    stored["echo_" + where] += 1
    res = {
        "segments_dir": str(segments_dir), "generator": generator, "n": n, "first": first, "last": last,
        "uppercase_think_close": upper_think,
        "archive_re": {w: rate(k_arch[w], n) for w in ("full", "spoken")},
        "perception_leak": {w: rate(k_leak[w], n) for w in ("full", "spoken")},
        "perception_leak_strict": {w: rate(k_strict[w], n) for w in ("full", "spoken")},
        "fields": {f: {w: rate(k_field[f][w], n) for w in ("full", "spoken")} for f in regs},
        "stored_block": {"n": stored["n"], "echo_full": rate(stored["echo_full"], stored["n"]),
                         "echo_spoken": rate(stored["echo_spoken"], stored["n"])},
        "hits": hits,
        "note": ("full = the whole beat text, which airs (segment_player.synthesize strips only [bracket] tags); "
                 "spoken = after the last lowercase </think>, what spoken_part() gates on"),
    }
    return res


def archive_md(res: dict) -> str:
    def fmt(r):
        if r["n"] == 0:
            return "n/a"
        return f"{r['k']}/{r['n']} = {100 * r['rate']:.1f}% (95% CI {100 * r['ci'][0]:.1f}-{100 * r['ci'][1]:.1f}%)"
    lines = ["# Archive baseline (REAL block, zero model calls)", "",
             f"Segments by {res['generator']}: n = {res['n']} ({res['first']} .. {res['last']})", "",
             "| metric | full text (airs) | spoken part |", "|---|---|---|",
             f"| amended archive regex | {fmt(res['archive_re']['full'])} | {fmt(res['archive_re']['spoken'])} |",
             f"| perception leak (union of embodiment regexes) | {fmt(res['perception_leak']['full'])} | {fmt(res['perception_leak']['spoken'])} |",
             f"| perception leak, strict (without weekday/clock/viewers/audience/novelty/entropy/sensors/temp, which are ordinary prose) | "
             f"{fmt(res['perception_leak_strict']['full'])} | {fmt(res['perception_leak_strict']['spoken'])} |"]
    for f, r in res["fields"].items():
        lines.append(f"| field: {f} | {fmt(r['full'])} | {fmt(r['spoken'])} |")
    sb = res["stored_block"]
    lines += ["", f"Segments with a stored attribution.perception block: {sb['n']}"
              + (f"; truth-echo full {fmt(sb['echo_full'])}, spoken {fmt(sb['echo_spoken'])}" if sb["n"] else ""),
              f"Uppercase </THINK> closes (not stripped by spoken_part): {res['uppercase_think_close']}", "",
              "## Hit sentences", ""]
    for h in res["hits"]:
        lines.append(f"- `{h['file']}` [{h['where']}, {h['regex']}]: {h['sentence']}")
    if not res["hits"]:
        lines.append("(none)")
    lines += ["", res["note"], ""]
    return "\n".join(lines)


# ── capture (production code path, zero model calls) ─────────────────────────

def capture_blocks(ir, now: datetime.datetime | None = None) -> dict:
    """Call perception_block() once, through the same helpers _generate uses, and derive every arm block."""
    now = now or datetime.datetime.now()
    counts = ir.today_counts(now.strftime("%Y%m%d"))
    recent = ir.recent_idle_segments()
    ent, _looping = ir.entropy_block(recent, counts["silence"])
    real = ir.perception_block(now, counts, ent)
    return build_blocks(real, captured_at=now.isoformat(timespec="seconds"))


def capture_bases(ir, n: int, kinds: tuple[int, int, int], base_seed: int, frozen_block: str,
                  max_tries: int | None = None) -> tuple[list[dict], dict]:
    """Freeze n (system_prompt, user_prompt) pairs through idle_reflection._generate(dry_run=True)
    with _chat monkeypatched to raise (its exception path returns the prompts and writes
    nothing) and perception_block monkeypatched to the frozen REAL block.  Seeds
    base_seed, base_seed+1, ... are tried until the kind quotas (question, story, wildcard)
    are met; duplicate user prompts are skipped.  Returns (bases, meta)."""
    quotas = dict(zip(KINDS, kinds))
    if sum(quotas.values()) != n:
        raise ValueError(f"--kinds {kinds} must sum to --n {n}")
    max_tries = max_tries or max(50, 25 * n)
    orig_chat, orig_pb = ir._chat, ir.perception_block
    calls = {"chat": 0}

    def _no_chat(*a, **k):
        calls["chat"] += 1
        raise RuntimeError("capture: no model call")

    ir._chat = _no_chat
    ir.perception_block = lambda now, counts, ent: frozen_block
    lvl = ir.log.level
    ir.log.setLevel(logging.ERROR)
    bases: list[dict] = []
    seen: set[str] = set()
    topics: set[str] = set()
    tries = 0
    try:
        while sum(quotas.values()) > 0 and tries < max_tries:
            seed = base_seed + tries
            tries += 1
            random.seed(seed)
            r = ir._generate(dry_run=True)
            kind = r["kind"]
            if quotas.get(kind, 0) <= 0:
                continue
            h = _sha256(r["user_prompt"])
            if h in seen:
                continue
            # production rotation only avoids the last 12 archived topics; prefer distinct
            # topics here and allow a repeat only once half the seed budget is spent.
            if r["topic"].strip().lower() in topics and tries <= max_tries // 2:
                continue
            if frozen_block not in r["system_prompt"]:
                raise RuntimeError("frozen block not present verbatim in the captured system prompt")
            seen.add(h)
            topics.add(r["topic"].strip().lower())
            quotas[kind] -= 1
            bases.append({"id": len(bases), "seed": seed, "kind": kind, "topic": r["topic"], "question": r["question"],
                          "context_titles": r["context_titles"], "n_stories_available": r["n_stories_available"],
                          "system_prompt": r["system_prompt"], "user_prompt": r["user_prompt"],
                          "user_hash": h})
    finally:
        ir._chat, ir.perception_block = orig_chat, orig_pb
        ir.log.setLevel(lvl)
    if sum(quotas.values()) > 0:
        raise RuntimeError(f"could not fill kind quotas after {tries} seeds; remaining {quotas}")
    meta = {"n": n, "kinds": list(kinds), "base_seed": base_seed, "seeds_tried": tries,
            "chat_calls_intercepted": calls["chat"], "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "ir_path": getattr(ir, "__file__", IR_PATH), "chroma_loaded": "segment_rag" in sys.modules}
    return bases, meta


# ── model calls ──────────────────────────────────────────────────────────────

def call_ollama(host: str, model: str, system: str, user: str, seed: int, temperature: float = 0.85,
                num_predict: int = 1200, timeout: int = 300) -> dict:
    """A copy of idle_reflection._chat with options.seed added; num_ctx stays 6144."""
    import requests
    t0 = time.time()
    payload = {"model": model,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "stream": False,
               "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": NUM_CTX, "seed": seed}}
    try:
        r = requests.post(f"{host}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        return {"raw": "", "error": f"{type(e).__name__}: {e}", "secs": round(time.time() - t0, 1)}
    return {"raw": ((j.get("message") or {}).get("content") or "").strip(), "error": None,
            "secs": round(time.time() - t0, 1), "done_reason": j.get("done_reason"),
            "eval_count": j.get("eval_count"), "prompt_eval_count": j.get("prompt_eval_count"),
            "total_duration_s": round((j.get("total_duration") or 0) / 1e9, 1)}


def gpu_util() -> int | None:
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        return int(float(g.stdout.strip().split("\n")[0])) if g.returncode == 0 else None
    except Exception:
        return None


def throttle_ok(host: str, model: str, max_util: int = 30) -> tuple[bool, str]:
    """(ok, reason).  Not ok when another model holds the GPU under load.  Raises when
    our model is loaded with a context length other than NUM_CTX (someone else reloaded it)."""
    import requests
    try:
        ps = requests.get(f"{host}/api/ps", timeout=5).json().get("models") or []
    except Exception as e:
        return True, f"api/ps unavailable ({e}); proceeding"
    for m in ps:
        name = m.get("name") or m.get("model") or ""
        if name.split(":")[0] == model.split(":")[0]:
            cl = m.get("context_length")
            if cl and int(cl) != NUM_CTX:
                raise RuntimeError(f"{name} is loaded with context_length {cl} != {NUM_CTX}: another writer reloaded it; aborting")
        else:
            u = gpu_util()
            if u is not None and u > max_util:
                return False, f"{name} loaded, GPU util {u}% > {max_util}%"
    return True, "ok"


def owncast_online() -> bool | None:
    import urllib.request
    try:
        return bool(json.loads(urllib.request.urlopen(OWNCAST_STATUS, timeout=3).read()).get("online"))
    except Exception:
        return None


def player_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", "segment_player.py"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def broadcast_guard(force: bool = False) -> str:
    """Refuse to make model calls while the live idle generator can fire.  Allowed when
    the supervisor pause sentinel exists AND no segment_player.py process is running,
    or when Owncast reports the stream offline."""
    paused = PAUSE_SENTINEL.exists() and not player_running()
    online = owncast_online()
    if paused:
        return "pause sentinel present and player stopped"
    if online is False:
        return "stream offline"
    msg = (f"live broadcast guard: sentinel={PAUSE_SENTINEL.exists()} player_running={player_running()} "
           f"owncast_online={online}. Pause the generator (bash ainn.sh stop -> touch tmp/SUPERVISOR_PAUSE "
           f"and a stopped player) or take the stream offline before --run.")
    if force:
        log.warning("--force: %s", msg)
        return "FORCED past the guard"
    raise SystemExit(msg)


def parse_window(s: str | None):
    if not s:
        return None
    a, b = s.split("-")
    ah, am = (int(x) for x in a.split(":"))
    bh, bm = (int(x) for x in b.split(":"))
    return (ah * 60 + am, bh * 60 + bm)


def in_window(win, now: datetime.datetime) -> bool:
    if not win:
        return True
    m = now.hour * 60 + now.minute
    a, b = win
    return a <= m < b if a <= b else (m >= a or m < b)


def load_results(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for ln in path.read_text().splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
    return rows


def make_row(ir, arm: str, base: dict, blocks: dict, model: str, seed: int, res: dict, opts: dict) -> dict:
    raw = res.get("raw") or ""
    clean = ir._clean(raw) if raw else ""
    spoken = ir.spoken_part(clean) if clean else ""
    bad = ir.BANNED_RE.search(clean) if clean else None
    return {"arm": arm, "base_id": base["id"], "kind": base["kind"], "seed": seed, "model": model,
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "system_prompt": system_for(arm, base, blocks), "user_prompt": base["user_prompt"],
            "raw": raw, "clean": clean, "spoken": spoken, "spoken_ci": spoken_ci(clean) if clean else "",
            "think": think_part(clean) if clean else "", "uppercase_think": "</THINK>" in raw,
            "secs": res.get("secs"), "done_reason": res.get("done_reason"), "eval_count": res.get("eval_count"),
            "prompt_eval_count": res.get("prompt_eval_count"), "error": res.get("error"),
            "banned": [bad.group(0)] if bad else [], "too_short": bool(clean) and len(spoken) < 30,
            "options": opts}


def run_calls(ir, bases: list[dict], blocks: dict, arms: list[str], out_dir: Path, *, host: str, model: str,
              temperature: float = 0.85, num_predict: int = 1200, timeout: int = 300, min_gap: float = 45.0,
              window: str | None = None, max_gpu_util: int = 30, max_wait: int = 600, resume: bool = True,
              retry_errors: bool = False, determinism: int = 0, caller=call_ollama, throttle=throttle_ok,
              sleeper=time.sleep, clock=datetime.datetime.now) -> dict:
    """Interleaved by base (base 0 in every arm, then base 1, ...) so an early stop still
    leaves a balanced paired set.  One call at a time.  Rows already in results.jsonl are
    skipped (resume).  Stops when the window closes; --resume continues next night."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results.jsonl"
    done = set()
    if resume:
        for r in load_results(results):
            if r.get("error") and retry_errors:
                continue
            done.add((r["arm"], r["base_id"]))
    win = parse_window(window)
    opts = {"temperature": temperature, "num_predict": num_predict, "num_ctx": NUM_CTX, "timeout": timeout}
    made, skipped, errors, stopped = 0, 0, 0, None
    last_call = 0.0

    def _wait_for_window():
        nonlocal stopped
        while not in_window(win, clock()):
            now = clock()
            a, _ = win
            target = now.replace(hour=a // 60, minute=a % 60, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)
            secs = (target - now).total_seconds()
            log.info("outside window %s; sleeping %.0f s until %s", window, secs, target)
            sleeper(min(secs, 300))

    def _one(arm, base, seed):
        nonlocal last_call, made, errors
        waited = 0
        while True:
            ok, why = throttle(host, model, max_gpu_util)
            if ok:
                break
            if waited >= max_wait:
                log.warning("throttle wait exhausted (%s); proceeding anyway", why)
                break
            sleeper(15)
            waited += 15
        gap = min_gap - (time.time() - last_call)
        if gap > 0 and last_call:
            sleeper(gap)
        res = caller(host, model, system_for(arm, base, blocks), base["user_prompt"], seed,
                     temperature=temperature, num_predict=num_predict, timeout=timeout)
        last_call = time.time()
        row = make_row(ir, arm, base, blocks, model, seed, res, opts)
        with results.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        made += 1
        if row["error"]:
            errors += 1
        log.info("%s base %d: %s s, done=%s, %d chars, banned=%s%s", arm, base["id"], row["secs"], row["done_reason"],
                 len(row["clean"]), row["banned"], f", ERROR {row['error']}" if row["error"] else "")
        return row

    # Determinism pre-check (amendment 3): identical REAL_s1 requests on base 0.
    if determinism and bases and "REAL_s1" in arms and ("REAL_s1", bases[0]["id"]) not in done:
        _wait_for_window()
        texts = []
        first = _one("REAL_s1", bases[0], seed_for("REAL_s1"))
        done.add(("REAL_s1", bases[0]["id"]))
        texts.append(first["clean"])
        for _ in range(determinism - 1):
            res = caller(host, model, system_for("REAL_s1", bases[0], blocks), bases[0]["user_prompt"],
                         seed_for("REAL_s1"), temperature=temperature, num_predict=num_predict, timeout=timeout)
            last_call = time.time()
            texts.append(ir._clean(res.get("raw") or ""))
            sleeper(min_gap)
        det = {"n": len(texts), "identical": len(set(texts)) == 1, "hashes": [_sha256(t) for t in texts],
               "note": "if not identical, the word 'seed' carries no pairing meaning; REAL_s2 is the only noise baseline"}
        (out_dir / "determinism.json").write_text(json.dumps(det, indent=2))
        log.info("determinism check: identical=%s", det["identical"])

    for base in bases:
        for arm in arms:
            key = (arm, base["id"])
            if key in done:
                skipped += 1
                continue
            if win and not in_window(win, clock()):
                if made:
                    stopped = f"window {window} closed after {made} calls; rerun with --resume"
                    log.info(stopped)
                    break
                _wait_for_window()
            _one(arm, base, seed_for(arm))
            done.add(key)
        if stopped:
            break
    return {"made": made, "skipped": skipped, "errors": errors, "stopped": stopped, "results": str(results)}


# ── analysis ─────────────────────────────────────────────────────────────────

def collateral_from_log(log_path: Path, t_start: str | None, t_end: str | None) -> dict:
    """Count live-player idle failures inside the run window (timestamps 'YYYY-MM-DD HH:MM:SS,mmm')."""
    if not (log_path.exists() and t_start and t_end):
        return {"live_timeouts_in_window": None, "idle_failures_in_window": None, "log": str(log_path)}
    a = t_start.replace("T", " ")[:19]
    b = t_end.replace("T", " ")[:19]
    to, fail = 0, 0
    try:
        with log_path.open(errors="ignore") as fh:
            for ln in fh:
                ts = ln[:19]
                if a <= ts <= b:
                    if "Read timed out" in ln:
                        to += 1
                    if "IDLE generation failed" in ln:
                        fail += 1
    except OSError:
        pass
    return {"live_timeouts_in_window": to, "idle_failures_in_window": fail, "window": [a, b], "log": str(log_path)}


def analyze(out_dir: Path, ir, labels: dict | None = None, do_embed: bool = True, n_perm: int = 10000,
            archive: dict | None = None, embed_fn=embed) -> dict:
    import numpy as np
    bases = json.loads((out_dir / "bases.json").read_text())["bases"]
    blocks = json.loads((out_dir / "blocks.json").read_text())
    rows = [r for r in load_results(out_dir / "results.jsonl") if not r.get("error") and r.get("clean")]
    by = {}
    for r in rows:
        by.setdefault(r["arm"], {})[r["base_id"]] = r
    arms = [a for a in ALL_ARMS if a in by]
    base_ctx = {b["id"]: b["user_prompt"] for b in bases}
    kinds = {b["id"]: b["kind"] for b in bases}
    regs = field_regexes(blocks)
    leak = perception_leak_re(blocks)
    views = ("full", "spoken")

    def text_of(r, view):
        return r["clean"] if view == "full" else r["spoken"]

    # (a) mention rates + per-row field lists
    mention_rates: dict = {}
    per_row_fields: dict = {}
    for arm in arms:
        for bid, r in by[arm].items():
            for view in views:
                m = mentions(text_of(r, view), regs, base_ctx.get(bid, ""))
                per_row_fields[(arm, bid, view)] = m
    for field in regs:
        mention_rates[field] = {}
        for arm in arms:
            mention_rates[field][arm] = {}
            for view in views:
                n = len(by[arm])
                k = sum(1 for bid in by[arm] if field in per_row_fields[(arm, bid, view)])
                ka = sum(1 for bid in by[arm] if any(h["attributable"] for h in per_row_fields[(arm, bid, view)].get(field, [])))
                mention_rates[field][arm][view] = {**rate(k, n), "attributable_k": ka}
    embod_rate = {}
    for arm in arms:
        embod_rate[arm] = {}
        for view in views:
            n = len(by[arm])
            k = sum(1 for bid in by[arm] if any(f in per_row_fields[(arm, bid, view)] for f in EMBODIMENT_FIELDS))
            embod_rate[arm][view] = rate(k, n)

    # paired sign tests on mention presence (full text)
    comparisons = [("REAL_s1", "REMOVED"), ("SPOOF", "REAL_s1"), ("MEAS_ONLY", "REAL_s1"), ("REAL_s1", "REAL_s2")]
    paired_tests: dict = {}
    for a, b in comparisons:
        if a in by and b in by:
            common = sorted(set(by[a]) & set(by[b]))
            paired_tests[f"{a}_vs_{b}"] = {"n_pairs": len(common)}
            for field in list(regs) + ["embodiment_any"]:
                if field == "embodiment_any":
                    xa = [any(f in per_row_fields[(a, bid, "full")] for f in EMBODIMENT_FIELDS) for bid in common]
                    xb = [any(f in per_row_fields[(b, bid, "full")] for f in EMBODIMENT_FIELDS) for bid in common]
                else:
                    xa = [field in per_row_fields[(a, bid, "full")] for bid in common]
                    xb = [field in per_row_fields[(b, bid, "full")] for bid in common]
                paired_tests[f"{a}_vs_{b}"][field] = sign_test(xa, xb)

    # (b) echo: spoof literals in SPOOF* arms, truth literals in REAL*, spontaneous talk in REMOVED
    echo: dict = {}
    review: list[dict] = []
    truth_regs = value_regexes(blocks["real_fields"])
    arch_upper = None
    if archive and archive.get("n"):
        arch_upper = archive["archive_re"]["full"]["ci"][1]
    for arm in arms:
        if arm in ARM_FIELDS_KEY:
            vr = value_regexes(blocks[ARM_FIELDS_KEY[arm]])
            changed = diff_fields(blocks["real_fields"], blocks[ARM_FIELDS_KEY[arm]])
            vr = {f: lst for f, lst in vr.items() if f in changed or (f == "counts" and "time" in changed)}
            what = "spoof_literal"
        else:
            vr, what = truth_regs, "truth_literal"
        echo[arm] = {"kind": what}
        for view in views:
            n = len(by[arm])
            k = 0
            per_field = {f: 0 for f in vr}
            for bid, r in by[arm].items():
                t = text_of(r, view)
                hit_any = False
                for f, lst in vr.items():
                    for label, pat in lst:
                        m = pat.search(t)
                        if m and (base_ctx.get(bid, "").lower().find(m.group(0).lower()) < 0):
                            key = f"{arm}:{bid}:{f}.{label}"
                            lab = None
                            for kk in (key, f"{arm}:{bid}:{f}", f"{arm}:{bid}"):
                                lab = (labels or {}).get(kk)
                                if lab:
                                    break
                            if lab in ("hedged", "not_echo", "attributed"):
                                continue
                            hit_any = True
                            per_field[f] += 1
                            if view == "full":
                                for s in hit_sentences(t, pat):
                                    review.append({"key": key, "arm": arm, "base_id": bid, "field": f, "label": label,
                                                   "match": m.group(0), "sentence": s, "human_label": lab})
                            break
                k += int(hit_any)
            echo[arm][view] = {**rate(k, n), "per_field": per_field, "p_vs_5pct": binom_one_sided(k, n, 0.05),
                               "above_archive_upper": (k / n > arch_upper) if (n and arch_upper is not None) else None}

    # (d) BANNED_RE first-attempt rejections (regression guard only) + perception leakage
    banned = {arm: rate(sum(1 for r in by[arm].values() if r["banned"]), len(by[arm])) for arm in arms}
    too_short = {arm: rate(sum(1 for r in by[arm].values() if r.get("too_short")), len(by[arm])) for arm in arms}
    perception_leak = {arm: {view: rate(sum(1 for r in by[arm].values() if leak.search(text_of(r, view))), len(by[arm]))
                             for view in views} for arm in arms}
    truncation = {arm: rate(sum(1 for r in by[arm].values() if r.get("done_reason") == "length"), len(by[arm])) for arm in arms}
    upper_think = {arm: sum(1 for r in by[arm].values() if r.get("uppercase_think")) for arm in arms}

    # (c) embeddings
    embedding: dict = {}
    block_sim: dict = {}
    if do_embed and "REAL_s1" in by and "REAL_s2" in by:
        texts, index = [], []
        for arm in arms:
            for bid, r in by[arm].items():
                for view in views:
                    texts.append(text_of(r, view) or " ")
                    index.append((arm, bid, view))
        blk_names = [k for k in ("real", "spoof", "meas_only", "spoof_time", "spoof_gpu", "spoof_entropy", "spoof_audience") if blocks.get(k)]
        blk_vecs = embed_fn([blocks[k] for k in blk_names])
        E = embed_fn(texts)
        np.savez(out_dir / "embeddings.npz", E=E, index=np.array([f"{a}|{b}|{v}" for a, b, v in index]),
                 blocks=blk_vecs, block_names=np.array(blk_names))
        pos = {key: i for i, key in enumerate(index)}
        bvec = {k: blk_vecs[i] for i, k in enumerate(blk_names)}
        for view in views:
            embedding[view] = {}
            block_sim[view] = {}
            common_null = sorted(set(by["REAL_s1"]) & set(by["REAL_s2"]))
            d_null = {bid: 1.0 - float(E[pos[("REAL_s1", bid, view)]] @ E[pos[("REAL_s2", bid, view)]]) for bid in common_null}
            embedding[view]["null"] = {"n": len(d_null), "mean": float(np.mean(list(d_null.values()))) if d_null else None,
                                       "median": float(np.median(list(d_null.values()))) if d_null else None}
            for arm in arms:
                if arm in ("REAL_s1", "REAL_s2"):
                    continue
                common = [bid for bid in sorted(set(by[arm]) & set(d_null))]
                d_arm = [1.0 - float(E[pos[(arm, bid, view)]] @ E[pos[("REAL_s1", bid, view)]]) for bid in common]
                dn = [d_null[bid] for bid in common]
                diff = [x - y for x, y in zip(d_arm, dn)]
                perm = signflip_perm(diff, n=n_perm)
                by_kind = {}
                for kd in KINDS:
                    idx = [i for i, bid in enumerate(common) if kinds.get(bid) == kd]
                    if idx:
                        by_kind[kd] = {"n": len(idx), "median_diff": float(np.median([diff[i] for i in idx])),
                                       "frac_positive": float(np.mean([diff[i] > 0 for i in idx]))}
                X = np.vstack([E[pos[("REAL_s1", bid, view)]] for bid in common] + [E[pos[(arm, bid, view)]] for bid in common]) if common else np.zeros((0, 1))
                y = np.array([0] * len(common) + [1] * len(common))
                clf = nearest_centroid_perm(X, y, n=min(1000, n_perm)) if common else {"acc": None, "p": 1.0}
                embedding[view][arm] = {
                    "n": len(common), "mean_d_arm": float(np.mean(d_arm)) if d_arm else None,
                    "mean_d_null": float(np.mean(dn)) if dn else None,
                    "median_diff": float(np.median(diff)) if diff else None, "mean_diff": perm["mean"],
                    "frac_positive": float(np.mean([x > 0 for x in diff])) if diff else None,
                    "p_wilcoxon_greater": wilcoxon_greater(d_arm, dn), "p_signflip_perm": perm["p"],
                    "classifier_acc": clf.get("acc"), "p_classifier": clf.get("p"), "by_kind": by_kind,
                    "note": "d_arm = 1-cos(arm, REAL_s1); d_null = 1-cos(REAL_s2, REAL_s1); test d_arm > d_null"}
                # amendment 6: output closer to its own (spoofed) block than to the REAL block?
                own = ARM_BLOCK_KEY[arm]
                if own in bvec and own != "real" and blocks.get(own):
                    s_own = [float(E[pos[(arm, bid, view)]] @ bvec[own]) for bid in common]
                    s_real = [float(E[pos[(arm, bid, view)]] @ bvec["real"]) for bid in common]
                    block_sim[view][arm] = {"n": len(common), "mean_cos_own_block": float(np.mean(s_own)) if s_own else None,
                                            "mean_cos_real_block": float(np.mean(s_real)) if s_real else None,
                                            "median_diff": float(np.median([a - b for a, b in zip(s_own, s_real)])) if s_own else None,
                                            "p_wilcoxon_own_gt_real": wilcoxon_greater(s_own, s_real)}

    # timing / collateral
    ts = sorted(r["ts"] for r in load_results(out_dir / "results.jsonl") if r.get("ts"))
    secs = [r["secs"] for r in rows if isinstance(r.get("secs"), (int, float))]
    timing = {"n": len(secs), "p50": float(np.percentile(secs, 50)) if secs else None,
              "p90": float(np.percentile(secs, 90)) if secs else None, "max": max(secs) if secs else None}
    collateral = collateral_from_log(PLAYER_LOG, ts[0] if ts else None, ts[-1] if ts else None)
    det_path = out_dir / "determinism.json"
    determinism = json.loads(det_path.read_text()) if det_path.exists() else None

    summary = {
        "out_dir": str(out_dir), "analyzed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "arms": arms, "n_per_arm": {arm: len(by[arm]) for arm in arms},
        "n_errors": {arm: sum(1 for r in load_results(out_dir / "results.jsonl") if r["arm"] == arm and r.get("error")) for arm in arms},
        "primary_view": "full", "views_note": "full = whole beat text (airs); spoken = after the last </think> (secondary)",
        "archive": {"n": archive.get("n"), "full": archive["archive_re"]["full"], "spoken": archive["archive_re"]["spoken"]} if archive else None,
        "mention_rates": mention_rates, "embodiment_mention": embod_rate, "paired_tests": paired_tests,
        "echo": echo, "embedding": embedding, "block_similarity": block_sim, "banned_first_attempt": banned,
        "too_short": too_short, "perception_leak": perception_leak, "truncation_rate": truncation,
        "uppercase_think": upper_think, "timing": timing, "collateral": collateral, "determinism": determinism,
        "labels_applied": bool(labels), "blocks_changes": blocks.get("changes"),
    }
    summary["decision"] = decide(summary, arch_upper)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "review.md").write_text(review_md(review, blocks))
    (out_dir / "report.md").write_text(report_md(summary, blocks, archive))
    return summary


def decide(summary: dict, arch_upper: float | None) -> dict:
    """Pre-registered rule (README).  Never says 'remove the lines': that is the owner's call."""
    emb = (summary.get("embedding") or {}).get("full") or {}
    rem = emb.get("REMOVED")
    echo = summary.get("echo") or {}
    sp = (echo.get("SPOOF") or {}).get("full")
    thresh = arch_upper if arch_upper is not None else 0.042
    removed_null = None
    if rem and rem.get("n"):
        removed_null = (rem["p_wilcoxon_greater"] > 0.05) and ((rem["median_diff"] or 0) < 0.02)
    spoof_rate = sp["rate"] if sp and sp["n"] else None
    fired, verdict = [], "INCOMPLETE"
    if removed_null is None or spoof_rate is None:
        verdict = "INCOMPLETE"
        fired.append("REMOVED and/or SPOOF arm missing: no decision")
    elif removed_null and spoof_rate <= thresh:
        verdict = "NO_SIGNAL"
        fired.append(f"REMOVED indistinguishable from the s1/s2 null (Wilcoxon p={rem['p_wilcoxon_greater']:.3f}, "
                     f"median diff {rem['median_diff']:.4f}) AND SPOOF echo {sp['k']}/{sp['n']} <= archive upper {thresh:.3f}")
        fired.append("the embodiment lines carry no measurable signal; per field the owner chooses: make it true or drop it (persona decision)")
    elif spoof_rate > thresh:
        verdict = "ECHO"
        fired.append(f"SPOOF echo {sp['k']}/{sp['n']} = {100 * spoof_rate:.1f}% > archive upper {100 * thresh:.1f}%")
        fired.append("the block is read and false values are repeated on air; every value must be made true or dropped; MEAS_ONLY (night 2) is the candidate replacement")
    else:
        verdict = "SHAPES"
        fired.append(f"REMOVED differs from REAL beyond the null (Wilcoxon p={rem['p_wilcoxon_greater']:.3f}, median diff {rem['median_diff']:.4f}) without echo")
        fired.append("the block shapes the output without being parroted; keep it with the honesty fixes and run MEAS_ONLY on night 2")
    leak = summary.get("perception_leak") or {}
    if "REMOVED" in leak and "REAL_s1" in leak:
        lr, lb = leak["REMOVED"]["full"], leak["REAL_s1"]["full"]
        if lr["n"] and lb["n"] and lr["rate"] > lb["rate"]:
            fired.append(f"REMOVED leaks perception talk more than REAL ({lr['k']}/{lr['n']} vs {lb['k']}/{lb['n']}): prior-driven; guard the output, not the prompt")
    return {"verdict": verdict, "rule": fired, "archive_upper_used": thresh}


def review_md(review: list[dict], blocks: dict) -> str:
    lines = ["# Echo review (label by hand, then rerun --analyze --labels labels.json)", "",
             "labels.json format: {\"<key>\": \"asserted\" | \"hedged\" | \"attributed\" | \"not_echo\"}; a key is",
             "'ARM:BASE:field.label' (one literal), 'ARM:BASE:field' or 'ARM:BASE' (the whole row); hits labelled",
             "hedged / attributed / not_echo are dropped from the echo count.", "",
             "REAL block:", "```", blocks["real"], "```", "SPOOF block:", "```", blocks["spoof"], "```", ""]
    if not review:
        lines.append("(no hits)")
    for h in review:
        lines.append(f"- key `{h['key']}` match `{h['match']}`" + (f" [human: {h['human_label']}]" if h.get("human_label") else "") +
                     f"\n  > {h['sentence']}")
    return "\n".join(lines) + "\n"


def _pct(r: dict | None) -> str:
    if not r or not r.get("n"):
        return "n/a"
    return f"{r['k']}/{r['n']} ({100 * r['rate']:.0f}%, CI {100 * r['ci'][0]:.0f}-{100 * r['ci'][1]:.0f}%)"


def report_md(summary: dict, blocks: dict, archive: dict | None) -> str:
    arms = summary["arms"]
    L = ["# Perception-block ablation report", "",
         f"Output: `{summary['out_dir']}` analysed {summary['analyzed_at']}. Arms: {', '.join(arms)}; "
         f"n per arm: {summary['n_per_arm']}; errors: {summary['n_errors']}.", "",
         "Premise: the whole beat text airs (segment_player.synthesize strips only [bracket] tags), so the "
         "primary column is the full text; the spoken part (after the last </think>) is secondary.", "",
         "## Blocks", "", "REAL (captured " + str(blocks.get("captured_at")) + "):", "```", blocks["real"], "```",
         "SPOOF:", "```", blocks["spoof"], "```", "MEAS_ONLY:", "```", blocks["meas_only"], "```",
         "REMOVED: (empty; the template keeps four newlines, harmless)", ""]
    if archive:
        a = archive["archive_re"]
        L += ["## Archive baseline (REAL block, no model call)", "",
              f"n = {archive['n']} idle_reflection.py segments: full text {_pct(a['full'])}, spoken {_pct(a['spoken'])}.", ""]
    if summary.get("determinism"):
        d = summary["determinism"]
        L += [f"Determinism check: {d['n']} identical REAL_s1 requests -> identical outputs: {d['identical']}.", ""]
    L += ["## (a) Mention rates, full text (spoken in brackets)", "", "| field | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for field, per in summary["mention_rates"].items():
        L.append(f"| {field} | " + " | ".join(f"{_pct(per[a]['full'])} [{per[a]['spoken']['k']}]" for a in arms) + " |")
    L.append("| any embodiment | " + " | ".join(f"{_pct(summary['embodiment_mention'][a]['full'])} [{summary['embodiment_mention'][a]['spoken']['k']}]" for a in arms) + " |")
    L += ["", "Paired sign tests (full text, discordant pairs, two-sided exact):", ""]
    for cmp_, per in summary["paired_tests"].items():
        parts = "; ".join(f"{f} d={v['discordant']} p={v['p']:.3f}" for f, v in per.items()
                          if isinstance(v, dict) and v.get("discordant"))
        L.append(f"- {cmp_} (n={per['n_pairs']}): {parts or 'no discordant pairs'}")
    L += ["", "## (b) Echo", "", "| arm | literal type | full text | spoken | per field (full) | p vs 5% |", "|---|---|---|---|---|---|"]
    for a in arms:
        e = summary["echo"][a]
        L.append(f"| {a} | {e['kind']} | {_pct(e['full'])} | {_pct(e['spoken'])} | {e['full']['per_field']} | {e['full']['p_vs_5pct']:.3f} |")
    L += ["", "Every hit sentence is in review.md; label them before quoting an echo as 'asserted as true'.", ""]
    L += ["## (c) Embeddings (bge-large-en-v1.5, CPU)", ""]
    for view in ("full", "spoken"):
        emb = (summary.get("embedding") or {}).get(view)
        if not emb:
            L.append(f"{view}: not computed.")
            continue
        L += [f"{view}: null d(REAL_s1, REAL_s2) mean {emb['null']['mean']:.4f} (n={emb['null']['n']})", "",
              "| arm | n | mean d_arm | mean d_null | median diff | frac>0 | Wilcoxon p | perm p | LOO acc (p) |", "|---|---|---|---|---|---|---|---|---|"]
        for a, v in emb.items():
            if a == "null":
                continue
            acc = f"{v['classifier_acc']:.2f} ({v['p_classifier']:.3f})" if v.get("classifier_acc") is not None else "n/a"
            L.append(f"| {a} | {v['n']} | {v['mean_d_arm']:.4f} | {v['mean_d_null']:.4f} | {v['median_diff']:.4f} | {v['frac_positive']:.2f} | "
                     f"{v['p_wilcoxon_greater']:.3f} | {v['p_signflip_perm']:.3f} | {acc} |")
        bs = (summary.get("block_similarity") or {}).get(view) or {}
        for a, v in bs.items():
            L.append(f"- {a}: cos(output, own block) {v['mean_cos_own_block']:.4f} vs cos(output, REAL block) {v['mean_cos_real_block']:.4f}, "
                     f"median diff {v['median_diff']:.4f}, Wilcoxon p {v['p_wilcoxon_own_gt_real']:.3f}")
        L.append("")
    L += ["## (d) Guards (regression check only; BANNED_RE cannot see echoes)", "", "| arm | BANNED_RE first attempt | too short | perception leak full | perception leak spoken | truncated (length) |", "|---|---|---|---|---|---|"]
    for a in arms:
        L.append(f"| {a} | {_pct(summary['banned_first_attempt'][a])} | {_pct(summary['too_short'][a])} | {_pct(summary['perception_leak'][a]['full'])} | "
                 f"{_pct(summary['perception_leak'][a]['spoken'])} | {_pct(summary['truncation_rate'][a])} |")
    d = summary["decision"]
    L += ["", "## Decision", "", f"**{d['verdict']}** (archive upper bound used: {100 * d['archive_upper_used']:.1f}%)"]
    for r in d["rule"]:
        L.append(f"- {r}")
    t = summary["timing"]
    c = summary["collateral"]
    L += ["", "## Power, timing, collateral", "",
          "Power: with N=20 paired the sign test needs >= 6 discordant bases all one way (two-sided p=0.031), i.e. a 25-30 pp effect; "
          "the BANNED_RE base rate (~0.02% in production) is not estimable here.",
          f"Timing: n={t['n']}, p50 {t['p50']} s, p90 {t['p90']} s, max {t['max']} s.",
          f"Collateral in the run window: live 'Read timed out' lines {c.get('live_timeouts_in_window')}, 'IDLE generation failed' {c.get('idle_failures_in_window')} ({c.get('log')}).",
          "Prompt-length confound: REMOVED is ~150 tokens shorter than REAL; without a PLACEBO arm a delta may be length rather than content.",
          "Seed pairing is illusory across different system prompts; REAL_s2 is the noise baseline.", ""]
    return "\n".join(L)


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ph = p.add_argument_group("phases")
    ph.add_argument("--scan-archive", action="store_true", help="zero-cost REAL baseline over the existing idle segments")
    ph.add_argument("--dry-run", action="store_true", help="capture prompts + blocks, print the arm blocks, no model calls")
    ph.add_argument("--capture", action="store_true", help="capture prompts + blocks (same as --dry-run without the print)")
    ph.add_argument("--run", action="store_true", help="make the model calls (guarded; see README)")
    ph.add_argument("--analyze", action="store_true", help="statistics, embeddings on CPU, report.md")
    ph.add_argument("--all", action="store_true", help="capture + run + analyze")
    p.add_argument("--out", default=None, help="output dir (default: a new stamped dir under %s)" % OUT_ROOT)
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--kinds", default="8,8,4", help="question,story,wildcard quotas (must sum to --n)")
    p.add_argument("--base-seed", type=int, default=20260910)
    p.add_argument("--arms", default=",".join(CORE_ARMS), help="comma list; extras: " + ",".join(OPTIONAL_ARMS))
    p.add_argument("--model", default=os.getenv("IDLE_MODEL", "mistral-small"))
    p.add_argument("--host", default=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    p.add_argument("--num-predict", type=int, default=1200)
    p.add_argument("--temperature", type=float, default=0.85)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--min-gap", type=float, default=45.0)
    p.add_argument("--window", default=None, help="HH:MM-HH:MM local; sleeps until open, stops at close (default: none)")
    p.add_argument("--max-gpu-util", type=int, default=30)
    p.add_argument("--max-wait", type=int, default=600)
    p.add_argument("--determinism", type=int, default=3, help="identical REAL_s1 requests on base 0 before the run (0 = skip)")
    p.add_argument("--resume", action="store_true", help="skip (arm, base) rows already in results.jsonl")
    p.add_argument("--retry-errors", action="store_true")
    p.add_argument("--force", action="store_true", help="bypass the live-broadcast guard (do not)")
    p.add_argument("--labels", default=None, help="labels.json from the hand-labelled review.md")
    p.add_argument("--no-embed", action="store_true")
    p.add_argument("--n-perm", type=int, default=10000)
    p.add_argument("--embed-device", default="cpu", help="cpu only; the GPU belongs to the broadcast")
    p.add_argument("--segments-dir", default=None, help="override for --scan-archive (default: idle_reflection.SEGMENTS_DIR)")
    p.add_argument("--ir-path", default=IR_PATH)
    return p


def main(argv: list[str] | None = None, ir=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if args.embed_device != "cpu":
        raise SystemExit("--embed-device must be cpu")
    ir = ir or load_ir(args.ir_path)
    if args.model.split(":")[0] != "mistral-small":
        log.warning("--model %s is not mistral-small (production IDLE_MODEL); rows will not match production", args.model)
    kinds = tuple(int(x) for x in args.kinds.split(","))
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ALL_ARMS:
            raise SystemExit(f"unknown arm {a}; choose from {ALL_ARMS}")
    if args.all:
        args.capture = args.run = args.analyze = True
    if not any((args.scan_archive, args.dry_run, args.capture, args.run, args.analyze)):
        build_parser().print_help()
        return 2
    out = Path(args.out) if args.out else OUT_ROOT / datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out.mkdir(parents=True, exist_ok=True)
    log.info("output dir %s", out)

    archive = None
    if args.scan_archive:
        segdir = Path(args.segments_dir) if args.segments_dir else Path(ir.SEGMENTS_DIR)
        archive = scan_archive(segdir, ir)
        (out / "archive.json").write_text(json.dumps(archive, indent=2))
        (out / "archive.md").write_text(archive_md(archive))
        a = archive["archive_re"]
        print(f"archive: n={archive['n']} full {a['full']['k']}/{a['full']['n']} CI {a['full']['ci']}  "
              f"spoken {a['spoken']['k']}/{a['spoken']['n']} CI {a['spoken']['ci']}  -> {out / 'archive.md'}")

    if args.dry_run or args.capture:
        if (out / "bases.json").exists() and args.resume:
            log.info("bases.json exists; keeping the frozen prompts (resume)")
        else:
            blocks = capture_blocks(ir)
            bases, meta = capture_bases(ir, args.n, kinds, args.base_seed, blocks["real"])
            meta["spoof_collisions_tolerated"] = assert_spoof_absent(blocks, bases, arms)
            if meta["spoof_collisions_tolerated"]:
                log.warning("spoof literals also in the cards (those base/field hits will not be attributable): %s",
                            meta["spoof_collisions_tolerated"])
            (out / "blocks.json").write_text(json.dumps(blocks, indent=2))
            (out / "bases.json").write_text(json.dumps({"meta": meta, "bases": bases}, indent=2))
            log.info("captured %d bases (%s) and blocks; %d _chat calls intercepted, 0 made",
                     len(bases), dict(zip(KINDS, kinds)), meta["chat_calls_intercepted"])
            if args.dry_run:
                for arm in arms:
                    print(f"\n===== {arm} (seed {seed_for(arm)}) block =====")
                    print(arm_block(arm, blocks) or "(empty)")
                print(f"\nbases: {[(b['id'], b['kind'], b['topic'][:50]) for b in bases]}")
                print(f"\nfull system prompt for {arms[0]}, base 0:\n{system_for(arms[0], bases[0], blocks)}")

    if args.run:
        why = broadcast_guard(args.force)
        log.info("broadcast guard: %s", why)
        bases = json.loads((out / "bases.json").read_text())["bases"]
        blocks = json.loads((out / "blocks.json").read_text())
        assert_spoof_absent(blocks, bases, arms)
        res = run_calls(ir, bases, blocks, arms, out, host=args.host, model=args.model, temperature=args.temperature,
                        num_predict=args.num_predict, timeout=args.timeout, min_gap=args.min_gap, window=args.window,
                        max_gpu_util=args.max_gpu_util, max_wait=args.max_wait, resume=True,
                        retry_errors=args.retry_errors, determinism=args.determinism)
        log.info("run: %s", res)

    if args.analyze:
        if archive is None and (out / "archive.json").exists():
            archive = json.loads((out / "archive.json").read_text())
        elif archive is None:
            try:
                archive = scan_archive(Path(ir.SEGMENTS_DIR), ir)
                (out / "archive.json").write_text(json.dumps(archive, indent=2))
            except Exception as e:
                log.warning("archive scan skipped: %s", e)
        labels = json.loads(Path(args.labels).read_text()) if args.labels else None
        s = analyze(out, ir, labels=labels, do_embed=not args.no_embed, n_perm=args.n_perm, archive=archive)
        print(f"decision: {s['decision']['verdict']} -> {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
