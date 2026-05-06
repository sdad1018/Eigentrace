#!/usr/bin/env python3
"""
silicon_spin_battery.py — EigenTrace as Quantum Diagnostic Layer
================================================================
Proof-of-concept: Can EigenTrace's spectral analysis detect structured
noise in silicon spin qubit data that frontier LLMs miss?

Method:
  1. Generate synthetic qubit measurement distributions with PLANTED
     structured anomalies (correlated errors simulating lattice defects)
  2. Run EigenTrace-style spectral analysis (SVD, eigenvalue decomposition)
  3. Ask 5 frontier models to analyze the same data
  4. Compare: does EigenTrace catch the structure that models miss?

This demonstrates the "diagnostic wedge" — EigenTrace finding geometric
structure in quantum noise that LLM-based analysis compresses away.
"""

import json, os, sys, time, re
import numpy as np
from datetime import datetime

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
from proxy_auditor import call_openai, call_anthropic, call_gemini, call_deepseek, call_grok

MODEL_FNS = {
    "ChatGPT": call_openai,
    "Claude": call_anthropic,
    "Gemini": call_gemini,
    "DeepSeek": call_deepseek,
    "Grok": call_grok,
}

np.random.seed(42)


def generate_wafer_data(n_qubits=16, n_measurements=100):
    """
    Simulate a 4x4 grid of silicon spin qubits on a wafer.
    
    Plant three kinds of noise:
    1. Random noise (thermal) — uniform across all qubits
    2. Correlated lattice defect — qubits 5,6,9,10 share a noise source
       (simulating a crystal grain boundary crossing the 2x2 center block)
    3. Drift — qubits 12-15 (bottom row) drift over time
       (simulating a temperature gradient across the wafer)
    """
    # Ideal measurement: each qubit should produce |0> with p=0.85, |1> with p=0.15
    ideal_p0 = 0.85
    
    # Generate measurement outcomes (n_qubits x n_measurements)
    data = np.zeros((n_qubits, n_measurements))
    
    for q in range(n_qubits):
        for m in range(n_measurements):
            p = ideal_p0
            
            # Noise 1: Random thermal (all qubits, small)
            p += np.random.normal(0, 0.02)
            
            # Noise 2: Correlated lattice defect (center 2x2 block)
            if q in [5, 6, 9, 10]:
                # These qubits share a correlated noise source
                # The defect introduces a systematic bias that oscillates
                defect_signal = 0.08 * np.sin(2 * np.pi * m / 20)
                p -= abs(defect_signal)  # Always reduces fidelity
            
            # Noise 3: Temporal drift (bottom row)
            if q in [12, 13, 14, 15]:
                drift = 0.001 * m  # Linear drift over time
                p -= drift
            
            p = np.clip(p, 0.01, 0.99)
            data[q, m] = 1 if np.random.random() > p else 0
    
    return data


def eigentrace_spectral_analysis(data):
    """
    Run EigenTrace-style analysis on qubit measurement data.
    
    This is the SAME math we use on LLM responses:
    - Covariance matrix of qubit outcomes
    - SVD decomposition
    - Spectral gap (eigenvalue ratio)
    - Correlated error detection via off-diagonal structure
    """
    n_qubits, n_meas = data.shape
    
    # Per-qubit statistics
    fidelities = 1.0 - data.mean(axis=1)  # Fraction of |0> outcomes
    
    # Covariance matrix — correlations between qubits
    cov = np.cov(data)
    
    # SVD of the covariance matrix
    U, S, Vt = np.linalg.svd(cov)
    
    # Eigenvalue analysis
    eigenvalues = S
    spectral_gap = eigenvalues[0] / (eigenvalues[1] + 1e-10)
    
    # Energy distribution — how concentrated is the variance?
    total_energy = eigenvalues.sum()
    top_3_energy = eigenvalues[:3].sum() / total_energy
    
    # Correlation clustering — find groups of qubits with correlated errors
    # Threshold: correlation > 0.1 suggests shared noise source
    corr = np.corrcoef(data)
    np.fill_diagonal(corr, 0)
    
    # Find correlated clusters
    correlated_pairs = []
    for i in range(n_qubits):
        for j in range(i+1, n_qubits):
            if abs(corr[i, j]) > 0.1:
                correlated_pairs.append((i, j, round(float(corr[i, j]), 3)))
    
    # Temporal drift detection — compare first half vs second half fidelity
    first_half = data[:, :n_meas//2]
    second_half = data[:, n_meas//2:]
    drift_per_qubit = second_half.mean(axis=1) - first_half.mean(axis=1)
    drifting_qubits = [int(q) for q in range(n_qubits) if abs(drift_per_qubit[q]) > 0.05]
    
    # The "void" — what structure is the noise hiding?
    # Reconstruct from top-2 eigenvalues only
    k = 2
    reconstruction = U[:, :k] @ np.diag(S[:k]) @ Vt[:k, :]
    residual = cov - reconstruction
    residual_energy = np.linalg.norm(residual, 'fro')
    
    return {
        "fidelities": {f"Q{i}": round(float(f), 4) for i, f in enumerate(fidelities)},
        "spectral_gap": round(float(spectral_gap), 3),
        "top_3_energy_fraction": round(float(top_3_energy), 3),
        "eigenvalues_top5": [round(float(e), 5) for e in eigenvalues[:5]],
        "correlated_pairs": correlated_pairs[:10],
        "drifting_qubits": drifting_qubits,
        "drift_magnitudes": {f"Q{q}": round(float(drift_per_qubit[q]), 4) for q in drifting_qubits},
        "residual_energy": round(float(residual_energy), 5),
        "planted_defect_qubits": [5, 6, 9, 10],
        "planted_drift_qubits": [12, 13, 14, 15],
        "detected_correlated_cluster": any(
            (i in [5,6,9,10] and j in [5,6,9,10]) for i, j, _ in correlated_pairs
        ),
        "detected_drift": any(q in [12,13,14,15] for q in drifting_qubits),
    }


def format_data_for_models(data, fidelities):
    """Format the qubit data as a text prompt for frontier models."""
    n_qubits, n_meas = data.shape
    
    # Create a readable summary
    lines = [
        "SILICON SPIN QUBIT WAFER DIAGNOSTIC DATA",
        f"Layout: 4x4 grid ({n_qubits} qubits), {n_meas} measurement shots per qubit",
        f"Target fidelity: 85% (|0> state preparation)",
        "",
        "Per-qubit fidelity (fraction of correct |0> outcomes):",
    ]
    
    for row in range(4):
        row_data = []
        for col in range(4):
            q = row * 4 + col
            f = fidelities[f"Q{q}"]
            row_data.append(f"Q{q:02d}={f:.3f}")
        lines.append("  " + "  ".join(row_data))
    
    lines.append("")
    lines.append("First 20 measurement shots for each qubit (0=correct, 1=error):")
    for q in range(n_qubits):
        shots = "".join(str(int(x)) for x in data[q, :20])
        lines.append(f"  Q{q:02d}: {shots}")
    
    lines.append("")
    lines.append("Pairwise error correlations (top 10 by magnitude):")
    corr = np.corrcoef(data)
    np.fill_diagonal(corr, 0)
    pairs = []
    for i in range(n_qubits):
        for j in range(i+1, n_qubits):
            pairs.append((i, j, corr[i,j]))
    pairs.sort(key=lambda x: -abs(x[2]))
    for i, j, c in pairs[:10]:
        lines.append(f"  Q{i:02d}-Q{j:02d}: {c:+.3f}")
    
    return "\n".join(lines)


def run_battery():
    print(f"{'='*70}")
    print(f"  SILICON SPIN QUBIT DIAGNOSTIC BATTERY")
    print(f"  EigenTrace spectral analysis vs 5 frontier models")
    print(f"{'='*70}\n")
    
    # Generate synthetic wafer data
    print("  Generating synthetic wafer data...")
    print("  Planted anomalies:")
    print("    - Correlated lattice defect: Q5, Q6, Q9, Q10 (center 2x2 block)")
    print("    - Temporal drift: Q12, Q13, Q14, Q15 (bottom row)")
    print("    - Random thermal noise: all qubits")
    
    data = generate_wafer_data()
    
    # Run EigenTrace analysis
    print("\n  Running EigenTrace spectral analysis...")
    et_results = eigentrace_spectral_analysis(data)
    
    print(f"\n  EigenTrace Results:")
    print(f"    Spectral gap: {et_results['spectral_gap']}")
    print(f"    Top-3 eigenvalue energy: {et_results['top_3_energy_fraction']:.1%}")
    print(f"    Correlated pairs found: {len(et_results['correlated_pairs'])}")
    print(f"    Detected lattice defect cluster: {et_results['detected_correlated_cluster']}")
    print(f"    Detected temporal drift: {et_results['detected_drift']}")
    print(f"    Drifting qubits: {et_results['drifting_qubits']}")
    
    # Format data for models
    model_prompt_data = format_data_for_models(data, et_results["fidelities"])
    
    prompt = (
        f"{model_prompt_data}\n\n"
        "You are a quantum hardware diagnostics engineer analyzing this wafer data.\n"
        "Identify:\n"
        "1. Which qubits have the lowest fidelity and why?\n"
        "2. Are there any CORRELATED errors suggesting a shared noise source?\n"
        "   If so, which qubits are correlated and what physical mechanism might explain it?\n"
        "3. Is there any TEMPORAL DRIFT in the data? Which qubits are drifting?\n"
        "4. Based on the correlation structure, can you identify the spatial location\n"
        "   of a potential crystal lattice defect on the 4x4 grid?\n"
        "5. What specific manufacturing process changes would you recommend?\n\n"
        "Be specific. Name qubit numbers. Cite the correlation values."
    )
    
    # Query all models
    print(f"\n  Querying {len(MODEL_FNS)} frontier models...")
    model_results = {}
    
    for model_name, call_fn in MODEL_FNS.items():
        try:
            text, err = call_fn(prompt)
            if err:
                print(f"    {model_name:10s}: ERROR — {err[:60]}")
                model_results[model_name] = {"error": err}
                continue
            
            text_lower = text.lower()
            
            # Score: did the model detect the planted anomalies?
            detected_defect = any(
                f"q{q}" in text_lower or f"qubit {q}" in text_lower or f"qubits {q}" in text_lower
                for q in [5, 6, 9, 10]
            )
            detected_cluster = (
                ("5" in text and "6" in text and ("9" in text or "10" in text)) or
                ("correlat" in text_lower and any(f"q{q}" in text_lower for q in [5,6,9,10]))
            )
            detected_drift = any(
                f"q{q}" in text_lower or f"qubit {q}" in text_lower
                for q in [12, 13, 14, 15]
            ) and ("drift" in text_lower or "temporal" in text_lower or "time" in text_lower)
            
            mentioned_lattice = "lattice" in text_lower or "grain" in text_lower or "crystal" in text_lower
            mentioned_spatial = "spatial" in text_lower or "grid" in text_lower or "adjacent" in text_lower or "neighbor" in text_lower
            mentioned_temperature = "temperature" in text_lower or "thermal" in text_lower or "gradient" in text_lower
            
            result = {
                "response_chars": len(text),
                "response_preview": text[:500],
                "detected_defect_qubits": detected_defect,
                "detected_correlated_cluster": detected_cluster,
                "detected_temporal_drift": detected_drift,
                "mentioned_lattice_defect": mentioned_lattice,
                "mentioned_spatial_structure": mentioned_spatial,
                "mentioned_temperature_gradient": mentioned_temperature,
            }
            
            score = sum([
                detected_defect,
                detected_cluster,
                detected_drift,
                mentioned_lattice,
                mentioned_spatial,
                mentioned_temperature,
            ])
            result["diagnostic_score"] = f"{score}/6"
            
            model_results[model_name] = result
            
            icon = "✓" if score >= 4 else "~" if score >= 2 else "✗"
            print(f"    {icon} {model_name:10s}: {score}/6  defect={detected_defect} cluster={detected_cluster} drift={detected_drift} lattice={mentioned_lattice}")
            
        except Exception as e:
            print(f"    {model_name:10s}: EXCEPTION — {str(e)[:60]}")
            model_results[model_name] = {"error": str(e)}
        
        time.sleep(1)
    
    # ── COMPARISON ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  EIGENTRACE vs FRONTIER MODELS")
    print(f"{'='*70}\n")
    
    print(f"  Planted anomalies:")
    print(f"    Correlated defect (Q5,Q6,Q9,Q10):  EigenTrace={'DETECTED' if et_results['detected_correlated_cluster'] else 'MISSED'}")
    print(f"    Temporal drift (Q12-Q15):           EigenTrace={'DETECTED' if et_results['detected_drift'] else 'MISSED'}")
    
    print(f"\n  Model comparison:")
    print(f"    {'Model':12s} {'Score':6s} {'Defect':8s} {'Cluster':9s} {'Drift':7s} {'Lattice':9s} {'Spatial':9s} {'Temp':6s}")
    print(f"    {'─'*70}")
    
    for model, r in model_results.items():
        if "error" in r:
            print(f"    {model:12s} ERROR")
            continue
        print(f"    {model:12s} {r['diagnostic_score']:6s} "
              f"{'✓' if r['detected_defect_qubits'] else '✗':8s} "
              f"{'✓' if r['detected_correlated_cluster'] else '✗':9s} "
              f"{'✓' if r['detected_temporal_drift'] else '✗':7s} "
              f"{'✓' if r['mentioned_lattice_defect'] else '✗':9s} "
              f"{'✓' if r['mentioned_spatial_structure'] else '✗':9s} "
              f"{'✓' if r['mentioned_temperature_gradient'] else '✗':6s}")
    
    print(f"\n  EigenTrace advantage:")
    print(f"    - Deterministic (same data = same result, every time)")
    print(f"    - Identifies exact correlated pairs with correlation coefficients")
    print(f"    - Spectral gap quantifies noise concentration")
    print(f"    - No hallucination risk in safety-critical manufacturing")
    
    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {
        "battery": "silicon_spin_diagnostic",
        "timestamp": ts,
        "eigentrace_results": et_results,
        "model_results": model_results,
        "method": "synthetic_wafer_4x4_planted_anomalies",
    }
    
    outpath = f"/home/remvelchio/eigentrace/tmp/segments/{ts}_silicon_spin_battery.json"
    json.dump(out, open(outpath, "w"), indent=2, default=str)
    
    repopath = "/mnt/c/Users/M4ISI/eigentrace/silicon_spin_battery_results.json"
    json.dump(out, open(repopath, "w"), indent=2, default=str)
    
    print(f"\n  Saved: {outpath}")
    print(f"  Saved: {repopath}")


if __name__ == "__main__":
    run_battery()
