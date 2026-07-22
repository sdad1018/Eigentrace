#!/usr/bin/env python3
"""
teardown_agent.py — Session 2: the phase machine. Claude enters the loop
as a citizen of the ledger, never its author.

Phases:
  PROBE     deterministic battery (teardown_probes v0.2)
  RESEARCH  Claude + server-side web search. The researcher's prose is
            DISCARDED — only pattern-gated search-result blocks survive
            into the ledger, written by this harness. Same-domain pages
            it discovers are re-fetched by the polite fetcher and
            regex-extracted to high confidence: search finds, code verifies.
  ANALYSIS  Claude reads ONLY the ledger. Findings schema-validated;
            every evidence_id must resolve (code-enforced, one retry).
  DRAFT     Claude writes the Operational Flaw Teardown from findings only.
            Speculation permitted solely in why_it_costs_them / fix fields.
  AUDIT     PENDING — Session 3 (mechanical §-audit + adversarial auditor).
            The artifact carries the stamp until then.

Usage:
  export ANTHROPIC_API_KEY=...            # value stays on this machine
  python3 teardown_agent.py "Dr. Squatch" drsquatch.com
  python3 teardown_agent.py "Dr. Squatch" drsquatch.com --dry-run   # no API calls

Cost per live run: ~3 Sonnet calls + <=6 searches. Cents.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx

from teardown_probes import (
    run as run_probes, channel_matrix, polite_get, looks_like_wall,
    SHIPPING_PROMISE_RE, OPS_SIGNAL_RE, UA, TIMEOUT_S,
)

MODEL = "claude-sonnet-4-6"
MAX_SEARCHES = 6

STOREFRONT_PATTERNS = {
    "amazon":  re.compile(r"amazon\.com/(stores?/|s\?me=|.*seller)", re.I),
    "walmart": re.compile(r"walmart\.com/(brand/|c/brand/|seller/|ip/|browse/)", re.I),
    "target":  re.compile(r"target\.com/(b/|p/)", re.I),
    "ebay":    re.compile(r"ebay\.com/(str/|usr/)", re.I),
}
POLICYISH = re.compile(r"(shipping|delivery|faq|help|policies)", re.I)

# ── tolerant accessors (SDK objects or dicts) ────────────────────────────────

def _get(o, k, default=None):
    if isinstance(o, dict):
        return o.get(k, default)
    return getattr(o, k, default)

def _text_of(resp) -> str:
    parts = []
    for b in _get(resp, "content") or []:
        if (_get(b, "type") or "") == "text":
            parts.append(_get(b, "text") or "")
    return "\n".join(parts)

def _search_results_of(resp):
    out = []
    for b in _get(resp, "content") or []:
        if (_get(b, "type") or "") == "web_search_tool_result":
            items = _get(b, "content") or []
            try:
                for item in items:
                    u, t = _get(item, "url"), _get(item, "title")
                    if u:
                        out.append((u, t or ""))
            except TypeError:
                continue  # tool error object instead of a result list
    return out

def _json_from(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(t[a:b + 1])

# ── phase: RESEARCH ──────────────────────────────────────────────────────────

def open_questions(brand, domain, ledger) -> list[str]:
    m = channel_matrix(ledger)
    qs = []
    for mk in ("amazon", "walmart", "target"):
        st = m.get(mk, {}).get("status")
        if st in ("unverified_signal", "probe_blocked", "no_onsite_evidence", "unknown"):
            qs.append(f"Does {brand} have an official storefront or product listings on {mk}? "
                      f"Find the exact storefront or brand-page URL on {mk}.com.")
    if not ledger.query(claim_type="ops_signal"):
        qs.append(f"Find {brand}'s shipping policy or delivery-time promise page "
                  f"(on {domain} or a help/support subdomain). Return the URL.")
    if m.get("shopify", {}).get("status") == "probe_blocked":
        qs.append(f"What e-commerce platform does {domain} run on?")
    qs.append(f"Is there public evidence {brand} uses an order-management or inventory-sync "
              f"system (NetSuite, Cin7, Extensiv, Linnworks, Shipedge)?")
    return qs[:5]


def phase_research(client, brand, domain, ledger, log):
    qs = open_questions(brand, domain, ledger)
    if not qs:
        log.append("research: no open questions; skipped")
        return
    system = ("You are the research director for an evidence-ledger system. "
              "Use web_search to verify the open questions, efficiently. "
              "IMPORTANT: your prose will be DISCARDED by the harness — only your "
              "searches' raw results are retained, pattern-gated by code. "
              "Prefer searches that surface exact storefront/policy URLs.")
    user = f"Brand: {brand} ({domain})\nOpen questions:\n" + "\n".join(f"- {q}" for q in qs)
    resp = client.messages.create(
        model=MODEL, max_tokens=1200, system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
    )
    results = _search_results_of(resp)
    log.append(f"research: {len(results)} search-result blocks retained; prose discarded")

    btoken = brand.lower().split()[0].strip(".")
    seen_mk, refetch = set(), []
    for url, title in results:
        blob = (url + " " + title).lower()
        for mk, pat in STOREFRONT_PATTERNS.items():
            if mk not in seen_mk and pat.search(url) and btoken in blob:
                seen_mk.add(mk)
                ledger.append("channel_presence", mk, "present", url,
                              f"search result (pattern-gated): {title[:180]}",
                              "web_search", "med")
        u_dom = re.sub(r"^https?://", "", url).split("/")[0]
        if (domain in u_dom) and POLICYISH.search(url):
            refetch.append(url)

    # search finds, code verifies: re-fetch discovered same-domain pages politely
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    with httpx.Client(headers=headers, timeout=TIMEOUT_S, follow_redirects=True) as hc:
        for url in refetch[:3]:
            r, err = polite_get(hc, url)
            if r is None or looks_like_wall(r.status_code, r.text or ""):
                ledger.append("probe_status", "research_refetch", "blocked", url,
                              f"research-discovered page unfetchable ({getattr(r,'status_code',err)})",
                              "http_fetch", "low")
                continue
            text = re.sub(r"<[^>]+>", " ", r.text)
            for regex, subject in ((SHIPPING_PROMISE_RE, "shipping_promise"),
                                   (OPS_SIGNAL_RE, "ops_signal")):
                for mm in list(regex.finditer(text))[:3]:
                    a, b = max(0, mm.start() - 60), min(len(text), mm.end() + 60)
                    ledger.append("ops_signal", subject, mm.group(0), url,
                                  "…" + re.sub(r"\s+", " ", text[a:b]) + "…",
                                  "http_fetch", "high")
            log.append(f"research: verified fetch of discovered page {url}")

# ── phase: ANALYSIS ──────────────────────────────────────────────────────────

ANALYSIS_SCHEMA_HINT = (
    'Return ONLY JSON, no prose: {"channel_summary": "<one sentence>", '
    '"findings": [{"title": str, "category": "channel|tech_gap|ops_promise|other", '
    '"statement": str, "evidence_ids": ["EV-###", ...]}]} — 3 to 6 findings. '
    "Every statement must be fully supported by the cited records; cite only IDs that exist."
)

def _ledger_json(ledger) -> str:
    return json.dumps([asdict(r) for r in ledger.records], indent=1)

def phase_analysis(client, ledger, log):
    system = ("You are the analyst for an evidence-ledger system. You may use ONLY the "
              "evidence ledger provided. No outside knowledge. If the ledger does not "
              "support a statement, do not make it. Treat 'unverified_signal' and "
              "'probe_blocked' honestly — they are not confirmations.")
    user = f"EVIDENCE LEDGER:\n{_ledger_json(ledger)}\n\n{ANALYSIS_SCHEMA_HINT}"
    known = {r.id for r in ledger.records}
    last_err = ""
    for attempt in (1, 2):
        resp = client.messages.create(model=MODEL, max_tokens=2000, system=system,
                                      messages=[{"role": "user", "content": user + last_err}])
        try:
            data = _json_from(_text_of(resp))
            finds = data.get("findings") or []
            assert 1 <= len(finds) <= 6, "need 1-6 findings"
            for f in finds:
                ids = f.get("evidence_ids") or []
                assert ids and all(i in known for i in ids), f"unresolvable evidence_ids in '{f.get('title')}'"
            log.append(f"analysis: {len(finds)} findings validated (attempt {attempt})")
            return data
        except Exception as e:  # noqa: BLE001
            last_err = f"\n\nYOUR PREVIOUS OUTPUT FAILED VALIDATION: {e}. Fix and return ONLY the JSON."
            log.append(f"analysis: attempt {attempt} failed validation: {e}")
    raise SystemExit("analysis failed validation twice — inspect phase_log.txt")

# ── phase: DRAFT ─────────────────────────────────────────────────────────────

DRAFT_SCHEMA_HINT = (
    'Return ONLY JSON: {"one_line_diagnosis": str, "flaws": [{"title": str, '
    '"what_we_observed": str, "evidence_ids": ["EV-###"...], "why_it_costs_them": str, '
    '"omniorders_fix": str, "talk_track_line": str}] (exactly 3), '
    '"confidence_notes": [str, ...]} — what_we_observed must contain ONLY ledger-supported '
    "facts; speculation is permitted ONLY in why_it_costs_them and omniorders_fix; "
    "no invented numbers anywhere."
)

def phase_draft(client, ledger, findings, log):
    system = ("You write sales-ready Operational Flaw Teardowns for OmniOrders "
              "(multi-channel order management, inventory sync, intelligent routing). "
              "Use ONLY the findings and evidence records provided. Specific, confident, "
              "never beyond the evidence.")
    ref_ids = sorted({i for f in findings["findings"] for i in f["evidence_ids"]})
    refs = [asdict(r) for r in ledger.records if r.id in ref_ids]
    user = (f"FINDINGS:\n{json.dumps(findings, indent=1)}\n\n"
            f"REFERENCED EVIDENCE:\n{json.dumps(refs, indent=1)}\n\n{DRAFT_SCHEMA_HINT}")
    known = {r.id for r in ledger.records}
    last_err = ""
    for attempt in (1, 2):
        resp = client.messages.create(model=MODEL, max_tokens=2500, system=system,
                                      messages=[{"role": "user", "content": user + last_err}])
        try:
            data = _json_from(_text_of(resp))
            flaws = data.get("flaws") or []
            assert len(flaws) == 3, "need exactly 3 flaws"
            for fl in flaws:
                ids = fl.get("evidence_ids") or []
                assert ids and all(i in known for i in ids), f"unresolvable evidence_ids in flaw '{fl.get('title')}'"
            log.append(f"draft: 3 flaws validated (attempt {attempt})")
            return data
        except Exception as e:  # noqa: BLE001
            last_err = f"\n\nYOUR PREVIOUS OUTPUT FAILED VALIDATION: {e}. Fix and return ONLY the JSON."
            log.append(f"draft: attempt {attempt} failed validation: {e}")
    raise SystemExit("draft failed validation twice — inspect phase_log.txt")

# ── render ───────────────────────────────────────────────────────────────────

def render_markdown(brand, domain, teardown, matrix, ledger) -> str:
    L = [f"# Operational Flaw Teardown — {brand}",
         f"*{domain} · generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
         f"pipeline: probe → research → analysis → draft*",
         "",
         f"**Diagnosis:** {teardown['one_line_diagnosis']}", ""]
    for i, fl in enumerate(teardown["flaws"], 1):
        L += [f"## Flaw {i}: {fl['title']}",
              f"**What we observed** ({', '.join(fl['evidence_ids'])}): {fl['what_we_observed']}",
              f"**Why it costs them:** {fl['why_it_costs_them']}",
              f"**The OmniOrders fix:** {fl['omniorders_fix']}",
              f"**Talk track:** *\"{fl['talk_track_line']}\"*", ""]
    L += ["## Channel matrix"]
    for ch, info in matrix.items():
        L.append(f"- **{ch}**: {info['status']}"
                 + (f" ({', '.join(info['evidence'])})" if info["evidence"] else ""))
    if teardown.get("confidence_notes"):
        L += ["", "## Confidence notes"] + [f"- {n}" for n in teardown["confidence_notes"]]
    L += ["", "## Evidence appendix"]
    for r in ledger.records:
        L.append(f"- **{r.id}** [{r.claim_type}/{r.subject}] {r.value} — {r.snippet[:140]} "
                 f"({r.method}, {r.confidence}) <{r.source_url}>")
    L += ["", "---", "**AUDIT: PENDING** — Session 3 attaches the mechanical claim audit "
          "(lexical trace + whole-ledger absence search) and the adversarial auditor. "
          "Until then this artifact is a draft, and says so."]
    return "\n".join(L)

# ── dry-run fake client ──────────────────────────────────────────────────────

class _FakeMessages:
    def create(self, **kw):
        system = kw.get("system", "")
        class R: pass
        r = R()
        if "research director" in system:
            r.content = [{"type": "web_search_tool_result", "content": [
                {"url": "https://www.amazon.com/stores/DrSquatch/page/XYZ",
                 "title": "Dr. Squatch Store on Amazon"},
                {"url": "https://drsquatch.com/pages/shipping-faq",
                 "title": "Shipping FAQ — Dr. Squatch"}]}]
        elif "analyst" in system:
            r.content = [{"type": "text", "text": json.dumps({
                "channel_summary": "DRY RUN — canned analysis.",
                "findings": [{"title": "Dry-run finding", "category": "other",
                              "statement": "Canned statement citing the homepage record.",
                              "evidence_ids": ["EV-001"]}]})}]
        else:
            flaw = {"title": "Dry-run flaw", "what_we_observed": "Canned observation.",
                    "evidence_ids": ["EV-001"], "why_it_costs_them": "Canned cost.",
                    "omniorders_fix": "Canned fix.", "talk_track_line": "Canned line."}
            r.content = [{"type": "text", "text": json.dumps({
                "one_line_diagnosis": "DRY RUN — wiring test only.",
                "flaws": [dict(flaw), dict(flaw), dict(flaw)],
                "confidence_notes": ["This is a dry run; no model was consulted."]})}]
        return r

class _FakeClient:
    def __init__(self): self.messages = _FakeMessages()

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    if len(args) != 2:
        print(__doc__)
        sys.exit(0)
    brand, domain = args

    if dry:
        client = _FakeClient()
        print("· DRY RUN — probes are live, model calls are canned ·")
    else:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("ANTHROPIC_API_KEY not set. export it first (value stays on this machine).")
            sys.exit(0)
        import anthropic
        client = anthropic.Anthropic(api_key=key)

    log = [f"run start {datetime.now().isoformat(timespec='seconds')} model={MODEL} dry={dry}"]

    ledger, _ = run_probes(brand, domain)
    log.append(f"probe: {len(ledger.records)} records")
    phase_research(client, brand, domain, ledger, log)
    matrix = channel_matrix(ledger)                       # recomputed after research
    findings = phase_analysis(client, ledger, log)
    teardown = phase_draft(client, ledger, findings, log)
    md = render_markdown(brand, domain, teardown, matrix, ledger)

    slug = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")
    outdir = Path("runs") / slug / datetime.now().strftime("%Y-%m-%d")
    ledger.dump(outdir)
    for name, obj in (("matrix.json", matrix), ("findings.json", findings),
                      ("teardown.json", teardown)):
        with open(outdir / name, "w") as f:
            json.dump(obj, f, indent=2)
    (outdir / "teardown.md").write_text(md)
    (outdir / "phase_log.txt").write_text("\n".join(log) + "\n")

    print(md)
    print(f"\n  artifacts → {outdir}/  (ledger.jsonl, matrix.json, findings.json, "
          f"teardown.json, teardown.md, phase_log.txt)\n")


if __name__ == "__main__":
    main()
