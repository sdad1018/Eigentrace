#!/usr/bin/env python3
"""
teardown_probes.py — v0.3: probe battery + evidence ledger. ZERO LLM calls.

Principle: code writes facts. Models will only ever cite them.
Corollary (v0.2): absence from a page you never saw is not evidence.

Usage:
    python3 teardown_probes.py "Brand Name" brand-domain.com

Outputs:
    runs/<brand-slug>/<date>/ledger.jsonl   — append-only evidence ledger
    runs/<brand-slug>/<date>/matrix.json    — channel matrix (honest states)

Defect ledger (probe layer):
  #1 (2026-07-21, first live run, Gymshark): DOM-derived absence claims were
     recorded from an unverified homepage response — the site's bot wall returned
     a challenge page and v0.1 read its emptiness as absence. Fix: homepage
     verification gate (status + size + challenge markers); every DOM-derived
     absence claim requires a verified page, else it is recorded probe_blocked.
  #2 (2026-07-21, same run): marketplace search pages echo the query, so
     "brand token found" was near-tautological — and the matrix promoted this
     low-confidence presence to confirmed. Fix: confidence-aware matrix;
     direct-probe positives render as unverified_signal until independently
     verified (Session 2).
  #3 (2026-07-21, Dr. Squatch dry run): self-contradictory ledger — Shopify
     recorded present (fingerprint hit) AND listed in checked_absent, because
     the absent list was built per-MARKER, not per-NAME (multi-marker techs
     with one miss landed on both sides). Danger class: a claim citing the
     absent record would be claim-traced yet false — the mechanical audit's
     one blind spot. Fix: per-name aggregation at the root, plus
     EvidenceLedger.self_check(), an append-only consistency tripwire run
     before any model reads the records.

Dependencies: httpx, beautifulsoup4. Politeness: identified UA, 1s delay,
15s timeout, ~10 fetches max. Blocks are findings, not obstacles to defeat.
NOTE: keep runs/ in .gitignore.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ── constants ────────────────────────────────────────────────────────────────

UA = "EigenTrace-TeardownProbe/0.3 (+https://eigentrace.ai; research; polite)"
DELAY_S = 1.0
TIMEOUT_S = 15.0

MARKETPLACES = {
    "amazon":      ["amazon.com/", "amzn.to/"],
    "walmart":     ["walmart.com/"],
    "target":      ["target.com/"],
    "ebay":        ["ebay.com/"],
    "etsy":        ["etsy.com/"],
    "tiktok_shop": ["tiktok.com/@", "shop.tiktok.com"],
}

DIRECT_PROBE_URLS = {
    "amazon":  "https://www.amazon.com/s?k={q}",
    "walmart": "https://www.walmart.com/search?q={q}",
}

TECH_FINGERPRINTS = {
    "cdn.shopify.com":  ("Shopify", "platform"),
    "/cdn/shop/":       ("Shopify", "platform"),
    "myshopify.com":    ("Shopify", "platform"),
    "klaviyo":          ("Klaviyo", "email/sms"),
    "rechargepayments": ("Recharge", "subscriptions"),
    "gorgias":          ("Gorgias", "support"),
    "aftership":        ("AfterShip", "post-purchase tracking"),
    "loopreturns":      ("Loop Returns", "returns"),
    "shipstation":      ("ShipStation", "shipping ops"),
    "shipbob":          ("ShipBob", "3PL"),
    "shipedge":         ("Shipedge", "WMS/OMS"),
    "stamped.io":       ("Stamped", "reviews"),
    "judge.me":         ("Judge.me", "reviews"),
    "yotpo":            ("Yotpo", "reviews/loyalty"),
    "attentivemobile":  ("Attentive", "sms"),
    "triplewhale":      ("Triple Whale", "analytics"),
}

CHALLENGE_MARKERS = [
    "just a moment", "cf-browser-verification", "cf-challenge", "cf_chl",
    "access denied", "pardon our interruption", "are you a robot",
    "enable javascript and cookies", "captcha", "request blocked",
    "verify you are a human",
]

SHIPPING_PROMISE_RE = re.compile(
    r"(ships?\s+(?:within|in)\s+\d+\s*[-–]?\s*\d*\s*(?:business\s+)?days?"
    r"|same[- ]day\s+shipping"
    r"|2[- ]day\s+(?:shipping|delivery)"
    r"|next[- ]day\s+(?:shipping|delivery)"
    r"|free\s+shipping\s+(?:on\s+orders?\s+)?over)",
    re.I,
)
OPS_SIGNAL_RE = re.compile(
    r"(back[- ]?ordered?|out\s+of\s+stock|pre[- ]?order|sold\s+out"
    r"|our\s+warehouse|fulfillment\s+(?:center|partner)|ships\s+from)",
    re.I,
)

CONTENT_PATHS = [
    "/policies/shipping-policy",
    "/pages/shipping",
    "/pages/shipping-policy",
    "/policies/refund-policy",
    "/pages/faq",
]

# ── evidence layer ───────────────────────────────────────────────────────────

@dataclass
class EvidenceRecord:
    id: str
    claim_type: str      # channel_presence | tech_stack | ops_signal | probe_status
    subject: str
    value: str           # "present" | "absent_after_probe" | "blocked" | "ok" | matched text
    source_url: str
    snippet: str
    method: str          # http_fetch | dom_marker | onsite_outbound_link | direct_probe
    observed_at: str
    confidence: str      # high | med | low


class EvidenceLedger:
    """Append-only. The only writer of facts in the whole system."""

    def __init__(self, brand: str, domain: str):
        self.brand, self.domain = brand, domain
        self.records: list[EvidenceRecord] = []

    def append(self, claim_type, subject, value, source_url, snippet, method, confidence) -> EvidenceRecord:
        rec = EvidenceRecord(
            id=f"EV-{len(self.records) + 1:03d}",
            claim_type=claim_type, subject=subject, value=value,
            source_url=source_url, snippet=(snippet or "")[:300], method=method,
            observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            confidence=confidence,
        )
        self.records.append(rec)
        return rec

    def query(self, claim_type=None, subject=None):
        out = self.records
        if claim_type: out = [r for r in out if r.claim_type == claim_type]
        if subject:    out = [r for r in out if r.subject == subject]
        return out

    def self_check(self) -> list:
        """Defect #3 guard: a ledger must never assert X present and X absent
        in the same run. Contradictions are RECORDED, never silently edited —
        presence (higher-confidence, specific) voids the absent listing for
        that subject. Runs before any model reads the ledger."""
        issues = []
        by_subj: dict = {}
        for r in self.records:
            if r.claim_type == "channel_presence":
                by_subj.setdefault(r.subject, []).append(r)
        for subj, recs in by_subj.items():
            pres = [r for r in recs if r.value == "present"]
            abst = [r for r in recs if r.value.startswith("absent")]
            if pres and abst:
                issues.append((subj, pres[0].id, abst[0].id))
        present_tech = {r.subject: r.id for r in self.records
                        if r.claim_type == "tech_stack" and r.value == "present"}
        for r in self.records:
            if r.claim_type == "tech_stack" and r.subject == "checked_absent" and "for: " in r.snippet:
                listed = {n.strip() for n in r.snippet.split("for: ", 1)[1].split(",")}
                for name in sorted(set(present_tech) & listed):
                    issues.append((name, present_tech[name], r.id))
        for subj, pid, aid in issues:
            self.append("probe_status", f"consistency:{subj}", "contradiction",
                        "ledger://self_check",
                        f"{subj} recorded both present ({pid}) and absent ({aid}); "
                        f"presence wins; the absent listing is void for this subject",
                        "self_check", "high")
        return issues

    def dump(self, outdir: Path):
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "ledger.jsonl", "w") as f:
            for r in self.records:
                f.write(json.dumps(asdict(r)) + "\n")


def looks_like_wall(status: int, text: str) -> str | None:
    """Return the reason this response should not be trusted as the real page,
    or None if it looks like a genuine 200 with a real body."""
    if status != 200:
        return f"status={status}"
    low = text[:5000].lower()
    for m in CHALLENGE_MARKERS:
        if m in low:
            return f"challenge marker: '{m}'"
    if len(text) < 2000:
        return f"suspiciously small body ({len(text)} bytes)"
    return None


def channel_matrix(ledger: EvidenceLedger) -> dict:
    """Confidence-aware, honest states:
    confirmed | unverified_signal | absent_after_probe | probe_blocked
    | no_onsite_evidence | unknown"""
    matrix = {}
    link_scan_ran = bool(ledger.query(claim_type="probe_status", subject="onsite_link_scan"))

    # shopify — absence requires BOTH a verified homepage clean of markers AND products.json 404-family
    shop = ledger.query(claim_type="channel_presence", subject="shopify")
    shop_probe = ledger.query(claim_type="probe_status", subject="shopify")
    strong_present = [r for r in shop if r.value == "present" and r.confidence in ("high", "med")]
    if strong_present:
        matrix["shopify"] = {"status": "confirmed", "evidence": [r.id for r in strong_present]}
    elif any(r.value == "absent_after_probe" for r in shop):
        matrix["shopify"] = {"status": "absent_after_probe",
                             "evidence": [r.id for r in shop if r.value == "absent_after_probe"]}
    elif shop_probe:
        matrix["shopify"] = {"status": "probe_blocked", "evidence": [r.id for r in shop_probe]}
    else:
        matrix["shopify"] = {"status": "unknown", "evidence": []}

    for mk in MARKETPLACES:
        recs = ledger.query(claim_type="channel_presence", subject=mk)
        probe = ledger.query(claim_type="probe_status", subject=mk)
        present = [r for r in recs if r.value == "present"]
        strong = [r for r in present if r.confidence in ("high", "med")]
        if strong:
            matrix[mk] = {"status": "confirmed", "evidence": [r.id for r in strong]}
        elif present:  # defect #2: low-confidence presence is a signal, not a fact
            matrix[mk] = {"status": "unverified_signal", "evidence": [r.id for r in present]}
        elif any(r.value == "blocked" for r in probe):
            matrix[mk] = {"status": "probe_blocked", "evidence": [r.id for r in probe]}
        elif link_scan_ran:
            matrix[mk] = {"status": "no_onsite_evidence",
                          "evidence": [r.id for r in probe]}
        else:
            matrix[mk] = {"status": "unknown", "evidence": []}
    return matrix

# ── fetch layer ──────────────────────────────────────────────────────────────

def polite_get(client: httpx.Client, url: str):
    time.sleep(DELAY_S)
    try:
        r = client.get(url)
        return r, None
    except Exception as e:  # noqa: BLE001 — any transport failure is a recorded fact
        return None, f"{type(e).__name__}: {e}"

# ── probes ───────────────────────────────────────────────────────────────────

def probe_shopify(client, ledger, domain, homepage_html: str, homepage_verified: bool):
    url = f"https://{domain}/products.json?limit=3"
    r, err = polite_get(client, url)
    pj_status = getattr(r, "status_code", err)
    if r is not None and r.status_code == 200:
        try:
            data = r.json()
            if isinstance(data, dict) and "products" in data:
                titles = ", ".join(p.get("title", "?") for p in data["products"][:3])
                ledger.append("channel_presence", "shopify", "present", url,
                              f"products.json responded with catalog: {titles}",
                              "http_fetch", "high")
                return
        except Exception:
            pass

    if homepage_verified:
        hits = [m for m in ("cdn.shopify.com", "/cdn/shop/", "myshopify.com") if m in homepage_html]
        if hits:
            ledger.append("channel_presence", "shopify", "present", f"https://{domain}/",
                          f"DOM markers on verified homepage: {', '.join(hits)}",
                          "dom_marker", "high")
            return
        if isinstance(pj_status, int) and pj_status in (404, 410):
            # both conditions met: verified homepage clean of markers AND products.json 404
            ledger.append("channel_presence", "shopify", "absent_after_probe", url,
                          f"products.json {pj_status} + verified homepage has no Shopify markers",
                          "http_fetch", "med")
            return

    # everything else is a limitation of the probe, never evidence of absence (defect #1)
    ledger.append("probe_status", "shopify", "blocked", url,
                  f"products.json status={pj_status}; homepage_verified={homepage_verified} — "
                  f"insufficient basis for an absence claim",
                  "http_fetch", "low")


def probe_marketplace_links(ledger, domain, soup: BeautifulSoup):
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
    found_any = []
    for mk, needles in MARKETPLACES.items():
        found = [h for h in hrefs if any(n in h for n in needles)]
        if found:
            found_any.append(mk)
            ledger.append("channel_presence", mk, "present", f"https://{domain}/",
                          f"site links out to own {mk} storefront: {found[0]}",
                          "onsite_outbound_link", "high")
    ledger.append("probe_status", "onsite_link_scan", "completed", f"https://{domain}/",
                  f"scanned {len(hrefs)} links on verified homepage; storefront links found for: "
                  f"{', '.join(found_any) or 'none'}",
                  "dom_marker", "high")


def probe_marketplace_direct(client, ledger, brand):
    q = brand.replace(" ", "+")
    for mk, tmpl in DIRECT_PROBE_URLS.items():
        if any(r.value == "present" and r.confidence == "high"
               for r in ledger.query(claim_type="channel_presence", subject=mk)):
            continue  # already confirmed via onsite link — don't burn a fetch
        url = tmpl.format(q=q)
        r, err = polite_get(client, url)
        body = r.text[:2000].lower() if r is not None else ""
        if r is None or r.status_code in (403, 429, 503) or "captcha" in body:
            ledger.append("probe_status", mk, "blocked", url,
                          f"direct probe walled (status={getattr(r, 'status_code', err)}) — "
                          f"needs search-API probe in Session 2",
                          "direct_probe", "low")
        elif r.status_code == 200 and brand.lower().split()[0] in r.text.lower():
            # defect #2: search pages echo the query — this is a SIGNAL only
            ledger.append("channel_presence", mk, "present", url,
                          "brand token on marketplace search page — query-echo risk; "
                          "unverified_signal until Session 2 confirms a storefront",
                          "direct_probe", "low")
        else:
            ledger.append("probe_status", mk, "inconclusive", url,
                          f"status={getattr(r, 'status_code', err)}, no brand token",
                          "direct_probe", "low")


def probe_tech(ledger, domain, homepage_html, soup: BeautifulSoup):
    srcs = " ".join(
        [s.get("src", "") for s in soup.find_all("script", src=True)]
        + [l.get("href", "") for l in soup.find_all("link", href=True)]
    )
    haystack = homepage_html + " " + srcs
    names_hit: dict = {}
    for marker, (name, category) in TECH_FINGERPRINTS.items():
        if marker in haystack and name not in names_hit:
            names_hit[name] = (marker, category)
    for name, (marker, category) in names_hit.items():
        ledger.append("tech_stack", name, "present", f"https://{domain}/",
                      f"fingerprint '{marker}' in verified page source ({category})",
                      "dom_marker", "high")
    all_names = {name for name, _cat in TECH_FINGERPRINTS.values()}
    absent = sorted(all_names - set(names_hit))     # per-NAME, defect #3 fix
    ledger.append("tech_stack", "checked_absent", "absent_after_probe", f"https://{domain}/",
                  "no fingerprint on verified homepage for: " + ", ".join(absent),
                  "dom_marker", "med")


def probe_content(client, ledger, domain):
    fetched = 0
    for path in CONTENT_PATHS:
        if fetched >= 2:
            break
        url = f"https://{domain}{path}"
        r, _err = polite_get(client, url)
        if r is None or looks_like_wall(r.status_code, r.text or ""):
            continue
        fetched += 1
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        for regex, subject in ((SHIPPING_PROMISE_RE, "shipping_promise"), (OPS_SIGNAL_RE, "ops_signal")):
            for m in list(regex.finditer(text))[:3]:
                a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
                ledger.append("ops_signal", subject, m.group(0), url,
                              "…" + text[a:b] + "…", "http_fetch", "high")

# ── run ──────────────────────────────────────────────────────────────────────

def run(brand: str, domain: str) -> tuple[EvidenceLedger, dict]:
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    ledger = EvidenceLedger(brand, domain)
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(headers=headers, timeout=TIMEOUT_S, follow_redirects=True) as client:
        r, err = polite_get(client, f"https://{domain}/")
        if r is None:
            ledger.append("probe_status", "homepage", "unreachable", f"https://{domain}/",
                          str(err), "http_fetch", "high")
            return ledger, channel_matrix(ledger)

        wall = looks_like_wall(r.status_code, r.text or "")
        homepage_verified = wall is None
        if homepage_verified:
            ledger.append("probe_status", "homepage", "ok", f"https://{domain}/",
                          f"verified 200, {len(r.text)} bytes — DOM-derived claims are grounded",
                          "http_fetch", "high")
            homepage_html = r.text
            soup = BeautifulSoup(homepage_html, "html.parser")
        else:
            ledger.append("probe_status", "homepage", "blocked", f"https://{domain}/",
                          f"homepage unverified ({wall}) — all DOM-derived absence claims "
                          f"suppressed this run (defect #1 guard)",
                          "http_fetch", "high")
            homepage_html, soup = "", None

        probe_shopify(client, ledger, domain, homepage_html, homepage_verified)
        if homepage_verified:
            probe_marketplace_links(ledger, domain, soup)
            probe_tech(ledger, domain, homepage_html, soup)
        probe_marketplace_direct(client, ledger, brand)
        probe_content(client, ledger, domain)

    ledger.self_check()   # defect #3 tripwire: consistency before any model reads
    return ledger, channel_matrix(ledger)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(0)  # deliberate: never a bare nonzero exit in an interactive shell
    brand, domain = sys.argv[1], sys.argv[2]
    ledger, matrix = run(brand, domain)

    print(f"\n═══ EVIDENCE LEDGER — {brand} ({ledger.domain}) · {len(ledger.records)} records ═══")
    for rec in ledger.records:
        print(f"  {rec.id}  [{rec.claim_type:>16}] {rec.subject:<18} = {rec.value:<20} ({rec.method}, {rec.confidence})")
        print(f"         {rec.snippet[:110]}")
    print("\n═══ CHANNEL MATRIX ═══")
    for ch, info in matrix.items():
        print(f"  {ch:<12} {info['status']:<20} evidence: {', '.join(info['evidence']) or '—'}")

    slug = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")
    outdir = Path("runs") / slug / datetime.now().strftime("%Y-%m-%d")
    ledger.dump(outdir)
    with open(outdir / "matrix.json", "w") as f:
        json.dump(matrix, f, indent=2)
    print(f"\n  ledger → {outdir}/ledger.jsonl")
    print(f"  matrix → {outdir}/matrix.json\n")


if __name__ == "__main__":
    main()
