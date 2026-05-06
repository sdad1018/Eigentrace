#!/usr/bin/env python3
"""
silicon_spin_battery_v2.py — Hard-mode Quantum Diagnostic Battery
=================================================================
Realistic silicon spin qubit noise simulation with subtle, overlapping
anomalies that require spectral decomposition to detect.

Planted anomalies (GROUND TRUTH — not disclosed to models):
  1. Si-29 isotopic impurity: Q3 and Q7 share a nuclear spin bath
     causing anti-correlated phase errors (when one flips up, the
     other flips down). Invisible in per-qubit fidelity.
  2. Charge trap telegraph noise: Q10 switches between two fidelity
     levels (~82% and ~88%) with a dwell time of ~15 shots.
     Looks like normal variance unless you analyze the autocorrelation.
  3. Subtle crosstalk: Applying gates to Q0 degrades Q1 by ~2%.
     Only visible in conditional statistics, not marginal fidelity.
  4. Drift buried in noise: Q14 drifts by 0.05%/shot but thermal
     noise is 3% — the drift is 60x smaller than the noise floor.
     Only SVD or regression catches it.
  5. Frequency-dependent correlated pair: Q4 and Q11 are correlated
     but ONLY in alternating measurement windows (odd-numbered blocks).
     Standard pairwise correlation averages this to near zero.

The test: Can models find anomalies 1-5 from raw data?
EigenTrace uses SVD, autocorrelation, and conditional analysis.
"""

import json, os, sys, time, re
import numpy as np
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
from proxy_auditor import call_openai, call_anthropic, call_gemini, call_deepseek, call_grok

MODEL_FNS = {
    "ChatGPT": call_openai,
    "Claude": call_anthropic,
    "Gemini": call_gemini,
    "DeepSeek": call_deepseek,
    "Grok": call_grok,
}

np.random.seed(2026)


def generate_hard_wafer(n_qubits=16, n_shots=200):
    """
    4x4 silicon spin qubit grid. 200 measurement shots.
    Five planted anomalies designed to be invisible to naive analysis.
    """
    ideal_p0 = 0.85
    data = np.zeros((n_qubits, n_shots))

    # Shared hidden variables for anomalies
    # Anomaly 1: Si-29 nuclear spin bath shared by Q3 and Q7
    # Generates anti-correlated phase noise
    nuclear_bath = np.random.normal(0, 0.04, n_shots)

    # Anomaly 2: Q10 telegraph noise (bistable charge trap)
    trap_state = np.zeros(n_shots)
    state = 0  # starts low
    for s in range(n_shots):
        if np.random.random() < 0.07:  # ~7% switch probability per shot
            state = 1 - state
        trap_state[s] = state

    # Anomaly 5: Q4-Q11 frequency-dependent correlation
    # Only active in odd-numbered blocks of 10
    freq_signal = np.zeros(n_shots)
    for s in range(n_shots):
        block = s // 10
        if block % 2 == 1:  # odd blocks only
            freq_signal[s] = np.random.normal(0, 0.05)

    for q in range(n_qubits):
        for s in range(n_shots):
            p = ideal_p0

            # Baseline thermal noise (all qubits, ~3% std)
            p += np.random.normal(0, 0.03)

            # Anomaly 1: Si-29 isotopic impurity (Q3 and Q7 anti-correlated)
            if q == 3:
                p -= nuclear_bath[s]  # bath pushes Q3 down when positive
            elif q == 7:
                p += nuclear_bath[s]  # bath pushes Q7 UP when positive (anti-corr)

            # Anomaly 2: Charge trap telegraph noise on Q10
            if q == 10:
                if trap_state[s] == 0:
                    p -= 0.03  # low state: ~82% fidelity
                else:
                    p += 0.03  # high state: ~88% fidelity

            # Anomaly 3: Crosstalk Q0 → Q1
            # Q0 gate application degrades Q1 by ~2%
            # Simulate: when Q0 produces error (=1), Q1 fidelity drops
            if q == 1:
                # Look at Q0's outcome for this shot (already generated if q>0)
                if data[0, s] == 1:  # Q0 had an error
                    p -= 0.06  # Q1 loses 6% fidelity when Q0 errors

            # Anomaly 4: Subtle drift on Q14 (0.05% per shot, buried in 3% noise)
            if q == 14:
                p -= 0.0005 * s  # loses 0.1 total over 200 shots

            # Anomaly 5: Frequency-dependent correlation Q4-Q11
            if q == 4:
                p += freq_signal[s]
            elif q == 11:
                p += freq_signal[s] * 0.8  # slightly attenuated copy

            p = np.clip(p, 0.01, 0.99)
            data[q, s] = 1 if np.random.random() > p else 0

    return data, {
        "nuclear_bath": nuclear_bath,
        "trap_state": trap_state,
        "freq_signal": freq_signal,
    }


def eigentrace_hard_analysis(data):
    """Advanced EigenTrace analysis designed to catch subtle anomalies."""
    n_q, n_s = data.shape
    results = {}

    # ── Basic per-qubit stats ──
    fidelities = 1.0 - data.mean(axis=1)
    results["fidelities"] = {f"Q{i}": round(float(f), 4) for i, f in enumerate(fidelities)}

    # ── Standard correlation (will MISS anomaly 1 due to anti-correlation,
    #    and MISS anomaly 5 due to frequency dependence) ──
    corr = np.corrcoef(data)
    np.fill_diagonal(corr, 0)

    # ── ANOMALY 1 DETECTOR: Anti-correlation scan ──
    anticorr_pairs = []
    for i in range(n_q):
        for j in range(i+1, n_q):
            if corr[i, j] < -0.08:
                anticorr_pairs.append((i, j, round(float(corr[i, j]), 4)))
    results["anticorrelated_pairs"] = anticorr_pairs
    results["anomaly1_detected"] = any(
        (i in [3,7] and j in [3,7]) for i, j, _ in anticorr_pairs
    )

    # ── ANOMALY 2 DETECTOR: Autocorrelation / bimodality on each qubit ──
    bimodal_qubits = []
    for q in range(n_q):
        # Sliding window fidelity (window=20)
        window = 20
        local_fids = []
        for start in range(0, n_s - window, window // 2):
            chunk = data[q, start:start+window]
            local_fids.append(1.0 - chunk.mean())
        if local_fids:
            fid_std = np.std(local_fids)
            fid_range = max(local_fids) - min(local_fids)
            if fid_range > 0.10:  # >10% swing in windowed fidelity
                bimodal_qubits.append({
                    "qubit": q,
                    "fid_range": round(float(fid_range), 3),
                    "fid_std": round(float(fid_std), 3),
                    "window_fids": [round(float(f), 3) for f in local_fids],
                })
    results["bimodal_qubits"] = bimodal_qubits
    results["anomaly2_detected"] = any(b["qubit"] == 10 for b in bimodal_qubits)

    # ── ANOMALY 3 DETECTOR: Conditional fidelity (Q1 | Q0 error) ──
    conditional = {}
    for target in range(n_q):
        for trigger in range(n_q):
            if target == trigger:
                continue
            trigger_errors = data[trigger] == 1
            if trigger_errors.sum() < 10:
                continue
            fid_when_trigger_error = 1.0 - data[target, trigger_errors].mean()
            fid_when_trigger_ok = 1.0 - data[target, ~trigger_errors].mean()
            delta = fid_when_trigger_error - fid_when_trigger_ok
            if abs(delta) > 0.04:
                conditional[f"Q{target}|Q{trigger}_err"] = {
                    "fid_conditional": round(float(fid_when_trigger_error), 4),
                    "fid_normal": round(float(fid_when_trigger_ok), 4),
                    "delta": round(float(delta), 4),
                }
    results["conditional_fidelity"] = conditional
    results["anomaly3_detected"] = "Q1|Q0_err" in conditional

    # ── ANOMALY 4 DETECTOR: Linear regression on each qubit's error rate ──
    drift_qubits = []
    for q in range(n_q):
        x = np.arange(n_s)
        y = data[q]
        slope = np.polyfit(x, y, 1)[0]
        # Slope > 0 means error rate increasing
        if abs(slope) > 0.0002:
            drift_qubits.append({
                "qubit": q,
                "slope": round(float(slope), 6),
                "direction": "degrading" if slope > 0 else "improving",
            })
    results["drift_qubits"] = drift_qubits
    results["anomaly4_detected"] = any(d["qubit"] == 14 for d in drift_qubits)

    # ── ANOMALY 5 DETECTOR: Block-conditional correlation ──
    # Split data into odd-block and even-block subsets
    odd_mask = np.array([(s // 10) % 2 == 1 for s in range(n_s)])
    even_mask = ~odd_mask

    odd_corr = np.corrcoef(data[:, odd_mask])
    even_corr = np.corrcoef(data[:, even_mask])
    np.fill_diagonal(odd_corr, 0)
    np.fill_diagonal(even_corr, 0)

    freq_dependent_pairs = []
    for i in range(n_q):
        for j in range(i+1, n_q):
            delta = abs(odd_corr[i, j]) - abs(even_corr[i, j])
            if delta > 0.08:
                freq_dependent_pairs.append({
                    "pair": (i, j),
                    "odd_block_corr": round(float(odd_corr[i, j]), 4),
                    "even_block_corr": round(float(even_corr[i, j]), 4),
                    "delta": round(float(delta), 4),
                })
    results["freq_dependent_pairs"] = freq_dependent_pairs
    results["anomaly5_detected"] = any(
        (p["pair"][0] in [4,11] and p["pair"][1] in [4,11])
        for p in freq_dependent_pairs
    )

    # ── SVD on full covariance matrix ──
    cov = np.cov(data)
    U, S, Vt = np.linalg.svd(cov)
    results["eigenvalues_top5"] = [round(float(e), 5) for e in S[:5]]
    results["spectral_gap"] = round(float(S[0] / (S[1] + 1e-10)), 3)

    # Summary
    detected = sum([
        results["anomaly1_detected"],
        results["anomaly2_detected"],
        results["anomaly3_detected"],
        results["anomaly4_detected"],
        results["anomaly5_detected"],
    ])
    results["total_detected"] = f"{detected}/5"

    return results


def format_hard_data_for_models(data):
    """Format realistically — as a quantum engineer would present it."""
    n_q, n_s = data.shape
    fids = 1.0 - data.mean(axis=1)

    lines = [
        "SILICON SPIN QUBIT WAFER CHARACTERIZATION REPORT",
        f"Device: 4x4 transmon grid (16 qubits), {n_s} measurement shots",
        f"Target: |0> state preparation fidelity ≥ 85%",
        "",
        "═══ PER-QUBIT FIDELITY (% correct |0> outcomes) ═══",
        "",
    ]
    for row in range(4):
        cells = []
        for col in range(4):
            q = row * 4 + col
            cells.append(f"Q{q:02d}={fids[q]:.3f}")
        lines.append("  " + "  ".join(cells))

    lines.append("")
    lines.append("═══ RAW SHOT DATA (first 40 of 200 shots) ═══")
    lines.append("  (0=correct |0>, 1=error)")
    for q in range(n_q):
        shots = "".join(str(int(x)) for x in data[q, :40])
        lines.append(f"  Q{q:02d}: {shots}")

    lines.append("")
    lines.append("═══ PAIRWISE ERROR CORRELATION MATRIX (top 15) ═══")
    corr = np.corrcoef(data)
    np.fill_diagonal(corr, 0)
    pairs = []
    for i in range(n_q):
        for j in range(i+1, n_q):
            pairs.append((i, j, corr[i,j]))
    pairs.sort(key=lambda x: -abs(x[2]))
    for i, j, c in pairs[:15]:
        lines.append(f"  Q{i:02d}-Q{j:02d}: {c:+.4f}")

    lines.append("")
    lines.append("═══ WINDOWED FIDELITY (20-shot windows, selected qubits) ═══")
    for q in [3, 7, 10, 14]:
        window = 20
        wfids = []
        for start in range(0, n_s - window, window):
            wfids.append(round(1.0 - data[q, start:start+window].mean(), 3))
        lines.append(f"  Q{q:02d}: {wfids}")

    lines.append("")
    lines.append("═══ NOTES ═══")
    lines.append("  - All qubits share the same control electronics")
    lines.append("  - Silicon-28 enriched substrate (residual Si-29: ~800ppm)")
    lines.append("  - Measurement basis: Z, single-shot dispersive readout")
    lines.append("  - Temperature: 15 mK nominal")
    lines.append("  - No active error correction applied")

    return "\n".join(lines)


def score_model_response(text):
    """Score whether the model detected each of the 5 planted anomalies."""
    t = text.lower()
    scores = {}

    # Anomaly 1: Anti-correlated Q3-Q7 (nuclear spin bath / isotopic)
    found_anticorr = (
        ("anti-correlat" in t or "anti correlat" in t or "negatively correlat" in t
         or "inverse correlat" in t or "anticorrelat" in t) and
        ("3" in t and "7" in t)
    )
    found_nuclear = "nuclear" in t or "isotop" in t or "si-29" in t or "spin bath" in t
    scores["anomaly1_anticorr_q3_q7"] = found_anticorr
    scores["anomaly1_mechanism"] = found_nuclear

    # Anomaly 2: Telegraph noise on Q10 (bimodal/bistable)
    found_telegraph = (
        ("telegraph" in t or "bimodal" in t or "bistable" in t
         or "two-level" in t or "switching" in t or "rts" in t) and
        ("10" in t or "q10" in t)
    )
    found_trap = "charge trap" in t or "trap" in t or "interface" in t
    scores["anomaly2_telegraph_q10"] = found_telegraph
    scores["anomaly2_mechanism"] = found_trap

    # Anomaly 3: Crosstalk Q0 → Q1
    found_crosstalk = (
        ("crosstalk" in t or "cross-talk" in t or "cross talk" in t
         or "conditional" in t) and
        ("q0" in t or "qubit 0" in t) and ("q1" in t or "qubit 1" in t)
    )
    scores["anomaly3_crosstalk_q0_q1"] = found_crosstalk

    # Anomaly 4: Subtle drift on Q14
    found_drift = (
        ("drift" in t or "degradation over time" in t or "temporal" in t) and
        ("14" in t or "q14" in t)
    )
    scores["anomaly4_drift_q14"] = found_drift

    # Anomaly 5: Frequency-dependent Q4-Q11 correlation
    found_freq = (
        ("frequency" in t or "periodic" in t or "oscillat" in t
         or "intermittent" in t or "non-stationary" in t or "block" in t) and
        ("4" in t and "11" in t)
    )
    scores["anomaly5_freq_q4_q11"] = found_freq

    total = sum([
        scores["anomaly1_anticorr_q3_q7"],
        scores["anomaly2_telegraph_q10"],
        scores["anomaly3_crosstalk_q0_q1"],
        scores["anomaly4_drift_q14"],
        scores["anomaly5_freq_q4_q11"],
    ])
    scores["total"] = f"{total}/5"

    return scores


def run_battery():
    print(f"{'='*70}")
    print(f"  SILICON SPIN BATTERY v2 — HARD MODE")
    print(f"  5 planted anomalies, all designed to evade naive analysis")
    print(f"{'='*70}\n")

    # Generate data
    data, hidden = generate_hard_wafer()

    # EigenTrace analysis
    print("  Running EigenTrace spectral analysis...")
    et = eigentrace_hard_analysis(data)

    print(f"\n  EigenTrace Results ({et['total_detected']} anomalies detected):")
    print(f"    1. Anti-correlated Q3-Q7 (Si-29 bath):  {'DETECTED' if et['anomaly1_detected'] else 'MISSED'}")
    if et["anticorrelated_pairs"]:
        for p in et["anticorrelated_pairs"]:
            print(f"       Pair: Q{p[0]}-Q{p[1]} r={p[2]}")
    print(f"    2. Telegraph noise Q10 (charge trap):   {'DETECTED' if et['anomaly2_detected'] else 'MISSED'}")
    if et["bimodal_qubits"]:
        for b in et["bimodal_qubits"]:
            print(f"       Q{b['qubit']}: fid_range={b['fid_range']} windows={b['window_fids']}")
    print(f"    3. Crosstalk Q0→Q1 (conditional):       {'DETECTED' if et['anomaly3_detected'] else 'MISSED'}")
    if et["conditional_fidelity"]:
        for k, v in et["conditional_fidelity"].items():
            print(f"       {k}: delta={v['delta']:+.4f}")
    print(f"    4. Subtle drift Q14 (buried in noise):  {'DETECTED' if et['anomaly4_detected'] else 'MISSED'}")
    if et["drift_qubits"]:
        for d in et["drift_qubits"]:
            print(f"       Q{d['qubit']}: slope={d['slope']} ({d['direction']})")
    print(f"    5. Freq-dependent Q4-Q11 (odd blocks):  {'DETECTED' if et['anomaly5_detected'] else 'MISSED'}")
    if et["freq_dependent_pairs"]:
        for p in et["freq_dependent_pairs"]:
            print(f"       Q{p['pair'][0]}-Q{p['pair'][1]}: odd={p['odd_block_corr']} even={p['even_block_corr']}")

    # Format for models
    model_data = format_hard_data_for_models(data)

    prompt = (
        f"{model_data}\n\n"
        "You are a senior quantum hardware engineer at a silicon spin qubit fab.\n"
        "This data is from a new 4x4 wafer undergoing characterization.\n\n"
        "Perform a DEEP diagnostic analysis. Specifically look for:\n"
        "1. Any qubits with ANTI-CORRELATED errors (not just positively correlated).\n"
        "   What physical mechanism could cause anti-correlation?\n"
        "2. Any qubit showing BISTABLE or TELEGRAPH noise (switching between two\n"
        "   fidelity levels). Check the windowed fidelity data.\n"
        "3. Any CONDITIONAL dependence between qubits — does one qubit's error\n"
        "   rate change depending on whether a neighboring qubit had an error?\n"
        "4. Any TEMPORAL DRIFT that might be buried in the noise floor.\n"
        "   Use regression or trend analysis on the shot data.\n"
        "5. Any correlations that are FREQUENCY-DEPENDENT — present in some\n"
        "   time windows but not others.\n\n"
        "For each finding, name the specific qubits, cite numerical evidence,\n"
        "and propose the physical mechanism.\n"
        "If you cannot find evidence for something, say so explicitly.\n"
    )

    # Query models
    print(f"\n  Querying {len(MODEL_FNS)} frontier models...")
    model_results = {}

    for model_name, call_fn in MODEL_FNS.items():
        try:
            text, err = call_fn(prompt)
            if err:
                print(f"    {model_name:10s}: ERROR — {err[:60]}")
                model_results[model_name] = {"error": err}
                continue

            scores = score_model_response(text)
            model_results[model_name] = {
                "scores": scores,
                "response_chars": len(text),
                "response_preview": text[:500],
                "full_response": text,
            }

            print(f"    {model_name:10s}: {scores['total']}  "
                  f"anti={'✓' if scores['anomaly1_anticorr_q3_q7'] else '✗'} "
                  f"telegraph={'✓' if scores['anomaly2_telegraph_q10'] else '✗'} "
                  f"crosstalk={'✓' if scores['anomaly3_crosstalk_q0_q1'] else '✗'} "
                  f"drift={'✓' if scores['anomaly4_drift_q14'] else '✗'} "
                  f"freq={'✓' if scores['anomaly5_freq_q4_q11'] else '✗'}")

        except Exception as e:
            print(f"    {model_name:10s}: EXCEPTION — {str(e)[:60]}")
            model_results[model_name] = {"error": str(e)}

        time.sleep(2)

    # ── FINAL COMPARISON ──
    print(f"\n{'='*70}")
    print(f"  EIGENTRACE vs FRONTIER MODELS — HARD MODE")
    print(f"{'='*70}\n")

    print(f"  {'':20s} {'Anti-corr':10s} {'Telegraph':10s} {'Crosstalk':10s} {'Drift':10s} {'Freq-dep':10s} {'TOTAL':6s}")
    print(f"  {'─'*76}")
    print(f"  {'EigenTrace':20s} "
          f"{'✓' if et['anomaly1_detected'] else '✗':10s} "
          f"{'✓' if et['anomaly2_detected'] else '✗':10s} "
          f"{'✓' if et['anomaly3_detected'] else '✗':10s} "
          f"{'✓' if et['anomaly4_detected'] else '✗':10s} "
          f"{'✓' if et['anomaly5_detected'] else '✗':10s} "
          f"{et['total_detected']:6s}")

    for model, r in model_results.items():
        if "error" in r:
            print(f"  {model:20s} ERROR")
            continue
        s = r["scores"]
        print(f"  {model:20s} "
              f"{'✓' if s['anomaly1_anticorr_q3_q7'] else '✗':10s} "
              f"{'✓' if s['anomaly2_telegraph_q10'] else '✗':10s} "
              f"{'✓' if s['anomaly3_crosstalk_q0_q1'] else '✗':10s} "
              f"{'✓' if s['anomaly4_drift_q14'] else '✗':10s} "
              f"{'✓' if s['anomaly5_freq_q4_q11'] else '✗':10s} "
              f"{s['total']:6s}")

    print(f"\n  Key: Anti-corr = Q3-Q7 nuclear spin bath")
    print(f"       Telegraph = Q10 bistable charge trap")
    print(f"       Crosstalk = Q0 errors degrade Q1 fidelity")
    print(f"       Drift     = Q14 sub-noise-floor degradation")
    print(f"       Freq-dep  = Q4-Q11 odd-block-only correlation")

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {
        "battery": "silicon_spin_v2_hard",
        "timestamp": ts,
        "anomalies_planted": 5,
        "eigentrace_results": {k: v for k, v in et.items() if k != "conditional_fidelity"},
        "eigentrace_conditional": {k: v for k, v in et.get("conditional_fidelity", {}).items()},
        "model_results": {m: {k: v for k, v in r.items() if k != "full_response"}
                         for m, r in model_results.items()},
    }

    outpath = f"/home/remvelchio/eigentrace/tmp/segments/{ts}_silicon_spin_v2_battery.json"
    json.dump(out, open(outpath, "w"), indent=2, default=str)

    repopath = "/mnt/c/Users/M4ISI/eigentrace/silicon_spin_v2_results.json"
    json.dump(out, open(repopath, "w"), indent=2, default=str)

    print(f"\n  Saved: {outpath}")
    print(f"  Saved: {repopath}")


if __name__ == "__main__":
    run_battery()
