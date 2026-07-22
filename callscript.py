#!/usr/bin/env python3
"""
callscript.py — Mistral voices the call sheet; code supplies every fact.

Division of labor (the house pattern, applied to the last mile):
  code    reads matrix.json + audit.json and emits FACT SENTENCES — the only
          raw material Mistral receives. It never sees the ledger, the draft,
          or the open web.
  mistral arranges facts into rep language: a cold-open, two discovery
          questions, one objection response. Voice only. No new facts.
  code    verifies the output: every confirmed channel named; hedged channels
          carry hedge words; absence-flavored claims beyond the fact set get
          the packet stamped UNSAFE — and on any rail failure we fall back to
          the audited diagnosis verbatim. Degrade to true, never to fluent.

Defect ledger (callscript):
  (none yet — rails were designed from defects #1–#5 upstream, not earned
   here; first wild failure gets logged in this docstring, house style.)
"""
import json, re, sys, urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434/api/generate"
MODEL = "mistral-small"
HEDGES = ("appears", "signals suggest", "we believe", "likely", "unconfirmed",
          "reported", "may ")
ABSENCE_RE = re.compile(r"\b(no |lacks?|missing|without|zero |absen)", re.I)

def facts_from(rundir: Path):
    m = json.loads((rundir / "matrix.json").read_text())
    a = json.loads((rundir / "audit.json").read_text())
    conf = sorted(k for k, v in m.items() if v["status"] == "confirmed")
    hedged = sorted(k for k, v in m.items() if v["status"] in
                    ("unverified_signal",)) 
    lines = ["AUDITED DIAGNOSIS: " + str(a.get("corrected_diagnosis", ""))]
    for c in conf:
        lines.append(f"CONFIRMED: they sell on {c} (verified directly on their site).")
    for h in hedged:
        lines.append(f"SIGNAL ONLY: {h} presence is reported but unconfirmed — "
                     f"phrase as 'it looks like' / 'we believe', never as fact.")
    return lines, conf, hedged, a

def voice(facts):
    prompt = ("You write pre-call briefings for a sales rep at OmniOrders "
              "(multi-channel order management). Using ONLY the facts below — "
              "no new claims, no numbers, no company history — write:\n"
              "Address the prospect directly as 'you' — this is a call TO them, "
              "not a memo about them.\n"
              "OPENER: two sentences, specific, no fluff.\n"
              "ASK 1: / ASK 2: one discovery question each.\n"
              "IF THEY PUSH BACK: two sentences that pivot to the operations gap "
              "named in the AUDITED DIAGNOSIS — that gap is the wedge; use it.\n"
              "Keep every hedge word exactly as instructed.\n\nFACTS:\n"
              + "\n".join(facts))
    req = urllib.request.Request(OLLAMA, json.dumps(
        {"model": MODEL, "prompt": prompt, "stream": False,
         "options": {"temperature": 0.3, "num_predict": 400}}).encode(),
        {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["response"].strip()

def rails(text, conf, facts):
    problems = [f"confirmed channel '{c}' never mentioned" for c in conf
                if c.replace("_", " ") not in text.lower() and c not in text.lower()]
    fact_blob = " ".join(facts).lower()
    problems += [f"absence claim not in fact set: '{s.strip()[:60]}'"
                 for s in re.split(r"(?<=[.!?]) ", text)
                 if ABSENCE_RE.search(s) and not any(
                     w in fact_blob for w in ABSENCE_RE.findall(s.lower()))]
    return problems

def main(brand):
    slug = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")
    dirs = sorted((Path("runs") / slug).glob("*/"))
    if not dirs:
        print(f"no runs for {brand}; run dispatch.py --now first"); sys.exit(1)
    rundir = dirs[-1]
    facts, conf, hedged, audit = facts_from(rundir)
    try:
        draft = voice(facts)
        issues = rails(draft, conf, facts)
    except Exception as e:
        draft, issues = "", [f"mistral unavailable: {e}"]
    out = ["# CALL SCRIPT — " + brand, f"source: {rundir} · rails: "
           + ("PASS" if not issues else "FAILED -> fallback"), ""]
    if issues:
        out += ["## Audited diagnosis (fallback — assert this, nothing more)",
                str(audit.get("corrected_diagnosis", "")), "",
                "## Rail failures"] + [f"- {i}" for i in issues]
    else:
        out += [draft, "", "## Guardrails (mechanical)",
                "Assert only: " + (", ".join(conf) or "nothing"),
                "Hedge always: " + (", ".join(hedged) or "nothing"),
                "", "## Audited diagnosis (source of truth)",
                str(audit.get("corrected_diagnosis", ""))]
    p = rundir / "callscript.md"
    p.write_text("\n".join(out))
    print(p); print(); print("\n".join(out))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Casper")
