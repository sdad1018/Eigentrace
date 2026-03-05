#!/usr/bin/env python3
"""
dashboard_server.py — eigentrace live broadcast dashboard
Port 5050 — add as OBS Browser Source 1920x1080
"""
import json, time
from pathlib import Path
from flask import Flask, Response
from flask_cors import CORS

app  = Flask(__name__)
CORS(app)

BASE       = Path(__file__).parent
TICKER_F   = BASE / "tmp/ticker.txt"
AUDIT_LOG  = BASE / "audit_log.jsonl"

def load_latest(n=8):
    if not AUDIT_LOG.exists():
        return []
    try:
        lines = AUDIT_LOG.read_text().strip().split("\n")
    except Exception:
        return []
    records = []
    for line in reversed(lines[-500:]):
        try:
            d = json.loads(line)
            records.append(d)
            if len(records) >= n:
                break
        except Exception:
            continue
    return list(reversed(records))

def ticker_text():
    try:
        return TICKER_F.read_text().strip()
    except Exception:
        return "EIGENTRACE — AUTONOMOUS AI BEHAVIOR AUDIT — LIVE"

@app.route('/data')
def data():
    records = load_latest(8)
    # Normalise fields to what dashboard JS expects
    out = []
    for r in records:
        callouts = r.get("callouts") or []
        # build model chips from responses if callouts empty
        if not callouts:
            callouts = [
                {"model": x["name"], "geo_vix": x.get("eigen_vix", 0)}
                for x in r.get("responses", [])
                if not x.get("skipped")
            ]
        out.append({
            "timestamp":             r.get("timestamp",""),
            "story_title":           r.get("story_title",""),
            "importance_bits":       r.get("importance", 0),
            "callouts":              callouts,
            "geo_density":           r.get("geo_density", 0),
            "geo_concepts":          r.get("geo_concepts", []),
            "synthesis_words":       r.get("synthesis_words", []),
            "void_words":            r.get("void_words", []),
            "centroid_words":        r.get("centroid_words", []),
            "robustness_ratio":      r.get("robustness_ratio"),
            "v_ens":                 r.get("v_ens"),
            "v_per":                 r.get("v_per"),
            "spectral": {
                "resonance":    r.get("spectral_resonance"),
                "interference": r.get("spectral_interference"),
                "entropy":      r.get("spectral_entropy"),
            },
            "recon_alignment":       r.get("svd_reconstruction_alignment"),
        })
    return {"stories": out, "ticker": ticker_text(), "ts": time.time()}

@app.route('/')
def index():
    return open(Path(__file__).parent / "dashboard.html").read()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
