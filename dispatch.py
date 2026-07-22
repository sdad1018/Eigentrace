#!/usr/bin/env python3
"""
dispatch.py — T-30 pre-call dispatcher (the brief's second trigger).
The 4am cron covers the daily forage; this covers "30 minutes before a
scheduled call." n8n owns the schedule tick, execution visibility, and
hand-off-ability; this module owns the logic. Packet leads with the AUDITED
corrected diagnosis — the rep reads the honest layer first (P2-falsification
lesson, 2026-07-22: the draft never sees the matrix; the audit is its honest
layer, so the packet promotes the audit's verdict above the script).

calls.json: [{"id":"c1","brand":"Casper","domain":"casper.com",
              "time":"2026-07-22T14:00:00"}]        # local time
Usage:
  python3 dispatch.py --scan                        # n8n entrypoint
  python3 dispatch.py --seed "Brand" domain.com 30  # test call at now+30min
Window: fires for any unfired call with 0 < minutes-until <= 35; .fired-<id>
markers guarantee exactly-once; timing recorded on_time (>=25) vs late (<25).

Defect ledger (dispatch):
  #1 (2026-07-22, first live seed): c1 was seeded in-window before the n8n
     workflow could be activated; GUI setup outlasted the 10-minute window
     and the call died unfired — no late path existed. Production reading:
     any outage spanning a window silently costs the rep their packet.
     Fix: late-fire beats no-fire — window widened to 0 < mins <= 35,
     timing logged, markers still make refire impossible.
"""
import json, re, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CALLS = ROOT / "calls.json"
DISPATCH = ROOT / "runs" / "dispatch"

def slug(b): return re.sub(r"[^a-z0-9]+", "-", b.lower()).strip("-")

def ensure_teardown(brand, domain):
    s = slug(brand)
    today = datetime.now().strftime("%Y-%m-%d")
    d = ROOT / "runs" / s / today
    if (d / "teardown.md").exists():
        return d, "reused"
    cmd = ["python3", "forager.py", "--company", brand] + (["--domain", domain] if domain else [])
    subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    dirs = sorted((ROOT / "runs" / s).glob("*/")) if (ROOT / "runs" / s).exists() else []
    d2 = dirs[-1] if dirs else None
    return (d2, "fresh") if d2 and (d2 / "teardown.md").exists() else (None, "engine_failed")

def assemble(call, rundir, mode):
    try: a = json.loads((rundir / "audit.json").read_text())
    except Exception: a = {}
    md = ["# T-30 PRE-CALL PACKET — " + call["brand"],
          f"call at {call['time']} · generated {datetime.now().isoformat(timespec='minutes')} · teardown {rundir.name} ({mode})",
          "", "## Audited diagnosis (assert this)",
          str(a.get("corrected_diagnosis", "(no audit found)")),
          "", "STAMP: " + str(a.get("stamp", "")),
          "", "## Full teardown script", (rundir / "teardown.md").read_text()]
    DISPATCH.mkdir(parents=True, exist_ok=True)
    out = DISPATCH / f"{call['id']}-{slug(call['brand'])}-T30.md"
    out.write_text("\n".join(md))
    return str(out)

def scan():
    calls = json.loads(CALLS.read_text()) if CALLS.exists() else []
    now = datetime.now(); fired, due, already = [], [], []
    for c in calls:
        marker = DISPATCH / f".fired-{c['id']}"
        mins = (datetime.fromisoformat(c["time"]) - now).total_seconds() / 60
        if marker.exists():
            already.append(c["id"]); continue
        if 0 < mins <= 35:  # defect #1: late-fire beats no-fire
            timing = "on_time" if mins >= 25 else "late"
            due.append(c["id"])
            rundir, mode = ensure_teardown(c["brand"], c.get("domain"))
            if rundir:
                path = assemble(c, rundir, mode)
                DISPATCH.mkdir(parents=True, exist_ok=True)
                marker.write_text(datetime.now().isoformat())
                fired.append({"id": c["id"], "packet": path, "mode": mode,
                              "timing": timing, "mins": round(mins, 1)})
    print(json.dumps({"ts": now.isoformat(timespec="seconds"), "checked": len(calls),
                      "due": due, "fired_count": len(fired), "packets": fired,
                      "already_fired": already}))

def seed(brand, domain, mins):
    calls = json.loads(CALLS.read_text()) if CALLS.exists() else []
    cid = f"c{len(calls)+1}"
    calls.append({"id": cid, "brand": brand, "domain": domain,
                  "time": (datetime.now() + timedelta(minutes=int(mins))).isoformat(timespec="seconds")})
    CALLS.write_text(json.dumps(calls, indent=2))
    print(f"seeded {cid}: {brand} ({domain}) at +{mins}min")

if __name__ == "__main__":
    if "--scan" in sys.argv: scan()
    elif "--seed" in sys.argv:
        i = sys.argv.index("--seed"); seed(sys.argv[i+1], sys.argv[i+2], sys.argv[i+3])
    else: print("usage: dispatch.py --scan | --seed BRAND DOMAIN MINUTES")
