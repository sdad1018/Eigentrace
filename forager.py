#!/usr/bin/env python3
"""
forager.py — the conductor + discovery organ. Mission-driven prospect foraging.

  PROPOSE   local Mistral (Ollama) is given the mission — discover mid-market
            CPG / DTC consumer brands — and proposes candidates. It PROPOSES;
            it never asserts: hallucinated companies die at the next gate.
  VERIFY    Wikipedia search -> Wikidata entity -> P856 ("official website")
            resolves each name to a real domain, deterministically, no keys.
            Every candidate is logged verified/rejected in the forage ledger.
  RUN       each verified brand goes through the full engine one at a time,
            as a SUBPROCESS (teardown_agent.py then teardown_audit.py) —
            one brand's failure cannot kill the batch; every run is logged.
  BRIEF     a 4am morning briefing compiles all audit stamps, corrected
            diagnoses, and top talk-tracks into runs/briefing-<date>.md.

Usage:
  python3 forager.py --n 10                 # forage 10, run all, brief
  python3 forager.py --n 2 --dry-run        # canned proposals, no API spend
  python3 forager.py --company "Liquid Death"        # single brand, wiki-resolved
  python3 forager.py --company "X" --domain x.com    # single brand, forced domain

Cron (fires the real 4am briefing; WSL must be up):
  0 4 * * * cd /mnt/c/Users/M4ISI/eigentrace && /usr/bin/python3 forager.py --n 10 >> runs/_logs/cron.log 2>&1

Cost: ~4 Claude calls + searches per brand ≈ a few dollars per 10-brand run.

Defect ledger (forager):
  #1 (2026-07-22, first dry chain): a REJECTED candidate leaked into the engine
     with its rejection reason as its domain — wiki_resolve's failure reason
     shared a tuple slot with the success domain, and truthiness could not
     tell them apart. Fix: explicit ok flag; a reason can never wear a
     domain's clothes again.
  #2 (2026-07-21, first live forage): existence is not identity — "Summer
     Fridays" (skincare) resolved to TGI Fridays' Spanish site, because the
     Wikipedia gate verified that A company exists, not that it was THE
     company proposed. The engine then produced an internally consistent,
     fully audited teardown of the wrong entity — proof that evidence-
     coherence is necessary but not sufficient; identity is a separate
     axiom. Fix: bidirectional token-containment identity gate between the
     proposal and the resolved title, domain-echo logged as signal,
     mismatches rejected with the resolved title named.
Known limitation (recall, by design): brands lacking a Wikidata P856 claim
are rejected even when alive (observed: BarkBox). Precision over recall;
roadmap: fall back to the Wikipedia article's infobox URL, identity-gated.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent

ENV_PATH = Path("/home/remvelchio/eigentrace/.env")   # discovered home of the living keys
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
FORAGER_MODEL = os.getenv("FORAGER_MODEL", "mistral-small")
UA = "EigenTrace-Forager/0.4 (+https://eigentrace.ai; research; polite)"
WIKI = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"

FALLBACK_CANDIDATES = [  # used ONLY if Ollama is unreachable — logged as fallback
    "Liquid Death", "Olipop", "Bombas", "Magic Spoon", "Athletic Brewing",
    "Harry's razors", "Quip toothbrush", "Ritual vitamins", "Caraway cookware",
    "Brooklinen", "Chomps", "Poppi soda", "Vital Proteins", "Hydro Flask", "Stanley cup brand",
]
DRY_RESOLVE = {"dr. squatch": "drsquatch.com", "brumate": "brumate.com",
               "olipop": "drinkolipop.com"}

MISSION = ("Your mission: discover {k} consumer-packaged-goods or DTC consumer brands "
           "that are MID-MARKET and digitally native — likely selling on their own site "
           "plus marketplaces (Amazon/Walmart/TikTok Shop). NOT mega-conglomerates "
           "(no P&G, Unilever, Nestle), not tiny unknowns. Avoid these already-known "
           "names: {exclude}. Return ONLY JSON: {{\"candidates\": [\"Brand Name\", ...]}}")


def load_env():
    """Manual .env load, no deps; setdefault so an exported key is never clobbered."""
    try:
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


GENERIC_TOKENS = {"the", "company", "brand", "co", "inc", "llc", "corp", "corporation"}

def _tokens(s: str) -> set[str]:
    s = re.sub(r"\(.*?\)", " ", s.lower())          # strip wiki parentheticals
    return {t for t in re.findall(r"[a-z0-9]+", s)
            if len(t) > 1 and t not in GENERIC_TOKENS}

def identity_match(proposed: str, title: str, domain: str) -> tuple[bool, bool]:
    """(contain, echo). contain = the gate: proposal and resolved title must
    token-contain one another. echo = brand token appears in the domain
    (logged signal, not gating)."""
    p, t = _tokens(proposed), _tokens(title)
    contain = bool(p and t) and (p <= t or t <= p)
    echo = any(tok in domain.replace("-", "") for tok in p if len(tok) > 3)
    return contain, echo


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── PROPOSE ──────────────────────────────────────────────────────────────────

def propose(exclude: set[str], k: int, dry: bool, ledger) -> list[str]:
    if dry:
        ledger("propose", {"source": "dry-run canned"})
        return ["Dr. Squatch", "BruMate", "OLIPOP", "Fictional Widget Co"]
    prompt = MISSION.format(k=k, exclude=", ".join(sorted(exclude)[:40]) or "none")
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", timeout=300.0, json={
            "model": FORAGER_MODEL, "stream": False, "format": "json",
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.8}})
        txt = r.json().get("message", {}).get("content", "")
        a, b = txt.find("{"), txt.rfind("}")
        cands = json.loads(txt[a:b + 1]).get("candidates", [])
        cands = [c.strip() for c in cands if isinstance(c, str) and c.strip()]
        ledger("propose", {"source": FORAGER_MODEL, "count": len(cands)})
        if cands:
            return cands
        raise ValueError("empty proposal list")
    except Exception as e:  # noqa: BLE001 — fail soft, mission continues on fallback
        ledger("propose", {"source": "FALLBACK", "reason": f"{type(e).__name__}: {e}"})
        return [c for c in FALLBACK_CANDIDATES if slugify(c) not in exclude]


# ── VERIFY (Wikipedia -> Wikidata P856) ──────────────────────────────────────

def wiki_resolve(name: str, dry: bool):
    """Return (ok, title, qid, domain_or_reason). ok is the ONLY gate signal."""
    if dry:
        d = DRY_RESOLVE.get(name.lower())
        return (True, name, "Q-dry", d) if d else (False, None, None, "dry-run: not in canned map")
    headers = {"User-Agent": UA}
    try:
        with httpx.Client(headers=headers, timeout=20.0) as c:
            time.sleep(0.5)
            s = c.get(WIKI, params={"action": "query", "list": "search", "format": "json",
                                    "srlimit": 3, "srsearch": f"{name} company brand"}).json()
            hits = s.get("query", {}).get("search", [])
            hits = [h for h in hits if "disambiguation" not in h.get("title", "").lower()]
            if not hits:
                return False, None, None, "no wikipedia page"
            title = hits[0]["title"]
            time.sleep(0.5)
            p = c.get(WIKI, params={"action": "query", "prop": "pageprops", "format": "json",
                                    "titles": title}).json()
            pages = p.get("query", {}).get("pages", {})
            qid = next(iter(pages.values())).get("pageprops", {}).get("wikibase_item")
            if not qid:
                return False, None, None, f"page '{title}' has no wikidata entity"
            time.sleep(0.5)
            w = c.get(WIKIDATA, params={"action": "wbgetclaims", "entity": qid,
                                        "property": "P856", "format": "json"}).json()
            claims = w.get("claims", {}).get("P856", [])
            if not claims:
                return False, None, None, f"{qid} has no official-website claim (P856)"
            url = claims[0]["mainsnak"]["datavalue"]["value"]
            domain = re.sub(r"^https?://", "", url).split("/")[0].removeprefix("www.")
            return True, title, qid, domain
    except Exception as e:  # noqa: BLE001
        return False, None, None, f"{type(e).__name__}: {e}"


# ── RUN (subprocess isolation per brand) ─────────────────────────────────────

def run_engine(brand: str, domain: str, dry: bool, logdir: Path) -> dict:
    date = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(brand)
    rundir = Path("runs") / slug / date
    logdir.mkdir(parents=True, exist_ok=True)
    dr = ["--dry-run"] if dry else []
    res = {"brand": brand, "domain": domain, "rundir": str(rundir), "ok": False}

    p = subprocess.run([sys.executable, str(HERE / "teardown_agent.py"), brand, domain] + dr,
                       capture_output=True, text=True, timeout=1200)
    (logdir / f"{slug}.agent.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
    if p.returncode != 0 or not (rundir / "teardown.json").exists():
        res["error"] = (p.stderr or p.stdout).strip().splitlines()[-1:] or ["agent produced no artifact"]
        return res

    p2 = subprocess.run([sys.executable, str(HERE / "teardown_audit.py"), str(rundir)] + dr,
                        capture_output=True, text=True, timeout=600)
    (logdir / f"{slug}.audit.log").write_text(p2.stdout + "\n--- stderr ---\n" + p2.stderr)
    res["ok"] = True
    res["audited"] = p2.returncode == 0 and (rundir / "audit.json").exists()
    return res


# ── BRIEF ────────────────────────────────────────────────────────────────────

def briefing(results: list[dict], date: str) -> Path:
    L = [f"# 4AM Briefing — {date}",
         f"*autonomous forage → verify → probe → draft → audit · {len(results)} prospects*", "",
         "| brand | verified channels | audit stamp |", "|---|---|---|"]
    sections = []
    for r in results:
        rd = Path(r["rundir"])
        if not r["ok"]:
            L.append(f"| {r['brand']} | — | FAILED: {'; '.join(r.get('error', ['?']))[:80]} |")
            continue
        stamp, diag, chans, talk = "audit missing", "", "?", ""
        try:
            a = json.loads((rd / "audit.json").read_text())
            stamp = a.get("stamp", stamp)
            diag = a.get("corrected_diagnosis", "")
            mfix = a.get("mechanical", {}).get("matrix_fixed", {})
            chans = ", ".join(f"{k}:{v['status']}" for k, v in mfix.items()
                              if v["status"] not in ("unknown", "no_onsite_evidence"))
        except OSError:
            pass
        try:
            t = json.loads((rd / "teardown.json").read_text())
            fl = (t.get("flaws") or [{}])[0]
            talk = fl.get("talk_track_line", "")
        except OSError:
            pass
        L.append(f"| {r['brand']} | {chans[:70]} | {stamp[:80]} |")
        sections += [f"## {r['brand']} ({r['domain']})", f"**{stamp}**", "",
                     diag, "", f"**Lead talk track:** *\"{talk}\"*",
                     f"\nFull teardown: `{rd}/teardown.md` · audit: `{rd}/audit_report.md`", ""]
    L += [""] + sections
    out = Path("runs") / f"briefing-{date}-{datetime.now().strftime('%H%M')}.md"
    out.write_text("\n".join(L) + "\n")
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default
    n = int(opt("--n", "10"))
    company, domain = opt("--company"), opt("--domain")

    load_env()
    date = datetime.now().strftime("%Y-%m-%d")
    logdir = Path("runs") / "_logs"
    logdir.mkdir(parents=True, exist_ok=True)
    forage_path = Path("runs") / f"forage-{date}.jsonl"
    def ledger(event, data):
        with open(forage_path, "a") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                                "event": event, **data}) + "\n")

    targets: list[tuple[str, str]] = []
    if company:
        if not domain:
            ok, title, qid, val = wiki_resolve(company, dry)
            if not ok:
                print(f"could not resolve '{company}': {val}"); sys.exit(0)
            contain, echo = identity_match(company, title or "", val)
            if not contain:
                print(f"identity mismatch: '{company}' resolved to '{title}' ({val}).")
                print("If that IS your target, rerun with --domain to force it.")
                sys.exit(0)
            ledger("verify", {"name": company, "title": title, "qid": qid,
                              "domain": val, "domain_echo": echo})
            domain = val
        targets = [(company, domain)]
    else:
        seen = {p.name for p in Path("runs").glob("*") if p.is_dir()}
        rounds = 0
        while len(targets) < n and rounds < 4:
            rounds += 1
            for name in propose(seen, max(n - len(targets) + 5, 8), dry, ledger):
                if len(targets) >= n:
                    break
                slug = slugify(name)
                if slug in seen:
                    ledger("skip", {"name": name, "reason": "duplicate"}); continue
                seen.add(slug)
                ok, title, qid, val = wiki_resolve(name, dry)
                if ok:
                    contain, echo = identity_match(name, title or "", val)
                    if not contain:
                        ledger("reject", {"name": name,
                                          "reason": f"identity mismatch: resolved to '{title}' ({val})"})
                        continue
                    ledger("verify", {"name": name, "title": title, "qid": qid,
                                      "domain": val, "domain_echo": echo})
                    targets.append((name, val))
                else:
                    ledger("reject", {"name": name, "reason": val})
        print(f"forage complete: {len(targets)}/{n} verified · ledger → {forage_path}")

    results = []
    for i, (brand, dom) in enumerate(targets, 1):
        print(f"\n═══ [{i}/{len(targets)}] {brand} ({dom}) ═══")
        r = run_engine(brand, dom, dry, logdir)
        print("   ", "OK — audited" if r.get("audited") else ("OK — audit missing" if r["ok"] else f"FAILED: {r.get('error')}"))
        results.append(r)

    out = briefing(results, date)
    ok = sum(1 for r in results if r["ok"])
    print(f"\n═══ BRIEFING READY — {ok}/{len(results)} prospects audited ═══\n  → {out}\n")


if __name__ == "__main__":
    main()
