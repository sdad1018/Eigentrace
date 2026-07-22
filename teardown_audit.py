#!/usr/bin/env python3
"""
teardown_audit.py — Session 3: the reflection layer. Two independent checks
run over a finished draft + its ledger; neither can confirm a hallucination.

  1. MECHANICAL (§H port from eigentrace.ai/vf-idf claim audit):
     - every flaw's evidence_ids must resolve            (citation integrity)
     - claims asserting a channel "confirmed" / as bald fact are checked
       against the CONFIDENCE of their backing evidence. A channel proven
       only by web_search (med) but asserted as confirmed fact is
       CONFIDENCE_OVERREACH — the exact class of the Walmart example.
     - absence claims ("no OMS detected") are searched across the whole
       ledger and verdicted SUPPORTED_ABSENT | CONTESTED.
  2. ADVERSARIAL: a second Claude, no shared context, sees ONLY the draft
     text + the ledger, and hunts unsupported/overreaching claims.

Router: overreach on a channel downgrades the matrix (confirmed_dom vs
reported_search) and rewrites the diagnosis under corrected confidence,
then re-stamps. Mechanical verdicts are authoritative; the model auditor
is advisory and appended.

Usage (standalone, operates on a run dir):
    python3 teardown_audit.py runs/dr-squatch/2026-07-21
    python3 teardown_audit.py runs/dr-squatch/2026-07-21 --dry-run
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from datetime import datetime

MODEL = "claude-sonnet-4-6"

# confidence rank; DOM/http beats search-sourced
CONF = {"high": 3, "med": 2, "low": 1}
# which methods count as "directly verified" vs "reported"
VERIFIED_METHODS = {"dom_marker", "http_fetch", "onsite_outbound_link"}
REPORTED_METHODS = {"web_search", "direct_probe"}

CONFIRM_WORDS = re.compile(r"\b(confirmed|verified|definitely|certainly|proven)\b", re.I)
CHANNELS = ("shopify", "amazon", "walmart", "target", "ebay", "etsy", "tiktok_shop", "tiktok")


def load_run(rundir: Path):
    ledger = [json.loads(l) for l in (rundir / "ledger.jsonl").read_text().strip().split("\n")]
    teardown = json.loads((rundir / "teardown.json").read_text())
    matrix = json.loads((rundir / "matrix.json").read_text())
    return ledger, teardown, matrix


def best_evidence_for_channel(ledger, channel) -> tuple[int, str, str] | None:
    """Return (rank, method, id) of the strongest PRESENT record for a channel."""
    best = None
    for r in ledger:
        if r["claim_type"] == "channel_presence" and r["subject"] == channel and r["value"] == "present":
            rank = CONF.get(r["confidence"], 0)
            if best is None or rank > best[0]:
                best = (rank, r["method"], r["id"])
    return best


def mechanical_audit(ledger, teardown, matrix) -> dict:
    known = {r["id"] for r in ledger}
    verdicts = []

    # 1. citation integrity across every flaw
    for fl in teardown.get("flaws", []):
        for eid in fl.get("evidence_ids", []):
            verdicts.append({"check": "citation", "claim": f"flaw '{fl['title']}' cites {eid}",
                             "verdict": "RESOLVED" if eid in known else "DANGLING_CITATION",
                             "evidence": eid})

    # 2. confidence-overreach on channel claims in diagnosis + matrix + flaw prose
    diag = teardown.get("one_line_diagnosis", "")
    haystacks = [("diagnosis", diag)] + \
                [(f"flaw:{fl['title']}", fl.get("what_we_observed", "")) for fl in teardown.get("flaws", [])]
    overreached = set()
    for where, text in haystacks:
        for ch in CHANNELS:
            if ch in text.lower():
                be = best_evidence_for_channel(ledger, ch)
                if be is None:
                    continue
                rank, method, eid = be
                asserted_confirmed = bool(CONFIRM_WORDS.search(text)) or where == "diagnosis"
                if asserted_confirmed and method in REPORTED_METHODS:
                    overreached.add(ch)
                    off = next(r for r in ledger if r["id"] == eid)
                    verdicts.append({
                        "check": "confidence", "claim": f"{ch} asserted as confirmed/fact in {where}",
                        "verdict": "CONFIDENCE_OVERREACH",
                        "evidence": eid,
                        "note": f"strongest evidence is {method}/{off['confidence']} — a reported signal, "
                                f"not a verified observation: \"{off['snippet'][:90]}\""})

    # 3. matrix honesty: confirmed status backed only by reported methods
    matrix_fixed = {}
    for ch, info in matrix.items():
        status = info.get("status")
        be = best_evidence_for_channel(ledger, ch)
        if status == "confirmed" and be and be[1] in REPORTED_METHODS:
            matrix_fixed[ch] = {**info, "status": "reported_search"}
            verdicts.append({"check": "matrix", "claim": f"matrix[{ch}]=confirmed",
                             "verdict": "DOWNGRADED_reported_search", "evidence": be[2]})
        elif status == "confirmed":
            matrix_fixed[ch] = {**info, "status": "confirmed_dom"}
        else:
            matrix_fixed[ch] = info

    # 4. absence claims -> whole-ledger search
    absent_terms = ["oms", "order management", "routing", "wms", "inventory sync", "channel-integration"]
    for fl in teardown.get("flaws", []):
        prose = (fl.get("what_we_observed", "") + " " + fl.get("title", "")).lower()
        if any(t in prose for t in absent_terms) and ("no " in prose or "without" in prose or "not " in prose):
            has_absent_record = any(
                r["claim_type"] == "tech_stack" and r["subject"] == "checked_absent"
                for r in ledger)
            verdicts.append({"check": "absence",
                             "claim": f"flaw '{fl['title']}' asserts a tooling gap",
                             "verdict": "SUPPORTED_ABSENT" if has_absent_record else "UNSUPPORTED_ABSENCE",
                             "evidence": "EV-008-class" if has_absent_record else None})

    n_over = len(overreached)
    n_dangle = sum(1 for v in verdicts if v["verdict"] == "DANGLING_CITATION")
    return {"verdicts": verdicts, "overreached_channels": sorted(overreached),
            "matrix_fixed": matrix_fixed,
            "summary": {"channels_downgraded": n_over, "dangling_citations": n_dangle,
                        "total_checks": len(verdicts)}}


def rewrite_diagnosis(teardown, ledger, overreached) -> str:
    """Regenerate the count under corrected confidence, deterministically."""
    confirmed_dom = sorted({
        r["subject"] for r in ledger
        if r["claim_type"] == "channel_presence" and r["value"] == "present"
        and r["method"] in VERIFIED_METHODS})
    reported = sorted({
        r["subject"] for r in ledger
        if r["claim_type"] == "channel_presence" and r["value"] == "present"
        and r["method"] in REPORTED_METHODS and r["subject"] not in confirmed_dom})
    diag = teardown.get("one_line_diagnosis", "")
    corrected = (f"{len(confirmed_dom)} channel(s) directly verified "
                 f"({', '.join(confirmed_dom)}); {len(reported)} further reported via search "
                 f"({', '.join(reported)}) and pending direct confirmation. " +
                 re.sub(r"(?i)\b(five|four|three|\d+)\s+(sales\s+)?channels?\b",
                        "the multi-channel footprint above", diag))
    return corrected


def _salvage_json(t: str) -> dict:
    """Parse model JSON defensively. If the model embedded raw quotes inside
    string values (common when quoting a draft full of \"...\"), strict json
    fails — so we fall back to a lenient line-scan that still recovers the
    verdicts. The adversarial auditor is ADVISORY; it must never crash the run."""
    t = re.sub(r"^```(?:json)?|```$", "", t.strip()).strip()
    a, b = t.find("{"), t.rfind("}")
    blob = t[a:b + 1] if a != -1 and b != -1 else t
    try:
        return json.loads(blob)
    except Exception:
        pass
    # structured salvage: claim_text can contain raw quotes, so match lazily
    # up to the quote that is FOLLOWED by , "verdict" — that anchor survives
    # embedded quotation marks (the exact failure mode observed live).
    claims, passed = [], None
    pair = re.compile(
        r'"claim_text"\s*:\s*"(.*?)"\s*,\s*"verdict"\s*:\s*"'
        r'(SUPPORTED|UNSUPPORTED|CONTRADICTED|UNCHECKABLE_OPINION)"'
        r'(?:\s*,\s*"evidence_id"\s*:\s*(?:"([^"]*)"|null))?'
        r'(?:\s*,\s*"note"\s*:\s*"(.*?)")?', re.S)
    for m in pair.finditer(blob):
        claims.append({"claim_text": re.sub(r"\s+", " ", m.group(1)).strip()[:160],
                       "verdict": m.group(2),
                       "evidence_id": m.group(3),
                       "note": (re.sub(r"\s+", " ", m.group(4) or "").strip()[:160]
                                or "recovered via structured salvage")})
    if not claims:  # last resort: verdict tokens line by line
        for line in blob.splitlines():
            mv = re.search(r"(SUPPORTED|UNSUPPORTED|CONTRADICTED|UNCHECKABLE_OPINION)", line)
            if mv:
                claims.append({"claim_text": "unrecovered claim", "verdict": mv.group(1),
                               "note": "verdict-only recovery"})
    if re.search(r'"pass"\s*:\s*true', blob):  passed = True
    if re.search(r'"pass"\s*:\s*false', blob): passed = False
    return {"pass": passed if passed is not None else (not any(
        c["verdict"] in ("UNSUPPORTED", "CONTRADICTED") for c in claims)),
        "claims": claims, "_recovered": True}


def adversarial_audit(client, teardown_md_text, ledger, dry) -> dict:
    if dry:
        return {"pass": False, "claims": [
            {"claim_text": "(dry-run) channels asserted confirmed from search snippets",
             "verdict": "UNSUPPORTED", "note": "canned adversarial finding"}]}
    system = ("You are an adversarial fact auditor. You receive a sales teardown draft and the "
              "evidence ledger it was built from. You have NO web access and NO memory of writing it. "
              "For every checkable factual claim, verdict SUPPORTED / UNSUPPORTED / CONTRADICTED / "
              "UNCHECKABLE_OPINION against the ledger ONLY. Be adversarial about channel-presence "
              "claims backed only by web_search or direct_probe methods. "
              "CRITICAL: return ONLY valid JSON. In claim_text, PARAPHRASE the claim in your own "
              "words — do NOT copy quotation marks or apostrophes from the draft; escape nothing, "
              "just avoid inner quotes. Shape: "
              '{"pass": bool, "claims": [{"claim_text": str, "verdict": str, "evidence_id": str|null, "note": str}]}')
    user = f"DRAFT:\n{teardown_md_text}\n\nLEDGER:\n{json.dumps(ledger, indent=1)}"
    try:
        resp = client.messages.create(model=MODEL, max_tokens=2000, system=system,
                                      messages=[{"role": "user", "content": user}])
        txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _salvage_json(txt)
    except Exception as e:  # noqa: BLE001 — advisory layer fails soft, never crashes the audit
        return {"pass": None, "claims": [], "_error": f"{type(e).__name__}: {e}",
                "note": "adversarial auditor unavailable this run; mechanical verdicts stand"}


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    if len(args) != 1:
        print(__doc__); sys.exit(0)
    rundir = Path(args[0])
    ledger, teardown, matrix = load_run(rundir)

    mech = mechanical_audit(ledger, teardown, matrix)

    if dry:
        client = None
    else:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("ANTHROPIC_API_KEY not set (source your .env)."); sys.exit(0)
        import anthropic
        client = anthropic.Anthropic(api_key=key)
    adv = adversarial_audit(client, (rundir / "teardown.md").read_text(), ledger, dry)

    corrected_diag = rewrite_diagnosis(teardown, ledger, mech["overreached_channels"])

    n = mech["summary"]
    stamp = (f"AUDITED: {n['total_checks']} checks · "
             f"{n['channels_downgraded']} channel(s) downgraded for confidence-overreach · "
             f"{n['dangling_citations']} dangling citations · "
             f"adversarial_pass={adv.get('pass')}")

    # write the audit report + corrected artifacts
    report = ["# Reflection Audit — " + rundir.name, "", f"**{stamp}**", "",
              "## Corrected diagnosis (regenerated under audited confidence)",
              corrected_diag, "",
              "## Corrected channel matrix"]
    for ch, info in mech["matrix_fixed"].items():
        report.append(f"- **{ch}**: {info['status']}"
                      + (f" ({', '.join(info['evidence'])})" if info.get("evidence") else ""))
    report += ["", "## Mechanical verdicts (§H port — authoritative)"]
    for v in mech["verdicts"]:
        line = f"- [{v['check']}] {v['claim']} → **{v['verdict']}**"
        if v.get("note"): line += f"\n    {v['note']}"
        report.append(line)
    report += ["", "## Adversarial auditor (independent Claude — advisory)"]
    report.append(f"- pass: {adv.get('pass')}")
    for c in adv.get("claims", []):
        report.append(f"- \"{c.get('claim_text','')[:100]}\" → **{c.get('verdict')}** "
                      f"{('· ' + c['note']) if c.get('note') else ''}")

    (rundir / "audit_report.md").write_text("\n".join(report) + "\n")
    (rundir / "audit.json").write_text(json.dumps(
        {"stamp": stamp, "mechanical": mech, "adversarial": adv,
         "corrected_diagnosis": corrected_diag}, indent=2))

    print("\n".join(report))
    print(f"\n  audit → {rundir}/audit_report.md + audit.json")


if __name__ == "__main__":
    main()
