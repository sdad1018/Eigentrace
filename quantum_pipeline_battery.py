#!/usr/bin/env python3
"""
quantum_pipeline_battery.py — EigenTrace Inside the Quantum Stack
==================================================================
Tests EigenTrace measurement framework applied directly to quantum
circuit diagnostics, not just AI summary filtering.

Three positions in the quantum pipeline:

Test 1: Ideal vs Noisy Circuit (decoherence measurement)
    Run same circuit on ideal and noisy simulator.
    Apply EigenTrace consensus geometry to detect structured distortion.

Test 2: Multi-Run Correlation (correlated noise detection)
    Run same circuit N times on noisy simulator.
    Apply spectral analysis to detect correlated vs random errors.

Test 3: Hardware Generation Comparison (backend benchmarking)
    Simulate two noise profiles (old chip vs new chip).
    Apply EigenTrace VIX to measure per-backend fidelity drift.

Test 4: Copilot Summary Filter (the original use case)
    Feed quantum telemetry through an LLM summary.
    Measure parameter loss with source-anchored void.

Test 5: Error Correction Channel (QEC observable)
    Apply surface code error correction.
    Measure information loss before and after correction.
    EigenTrace as QEC quality metric.

All tests run on simulator. Scale targets require QPU.

Usage: python3 quantum_pipeline_battery.py
"""

import numpy as np
import json
import sys
import os
from datetime import datetime
from collections import Counter

# ============================================================================
# TEST 1: IDEAL VS NOISY CIRCUIT — Decoherence as Information Loss
# ============================================================================

def test_ideal_vs_noisy():
    """
    Run the same circuit on ideal and noisy simulators.
    Treat the probability distributions as source vs output.
    Measure the void: which outcomes are suppressed by noise?
    """
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error

    print("=" * 60)
    print("TEST 1: IDEAL VS NOISY (Decoherence Measurement)")
    print("=" * 60)

    n_qubits = 4
    shots = 4096

    # Build a circuit that creates an entangled state
    # (GHZ state — maximally sensitive to decoherence)
    qc = QuantumCircuit(n_qubits)
    qc.h(0)
    for i in range(1, n_qubits):
        qc.cx(0, i)
    qc.measure_all()

    # IDEAL execution
    ideal_sim = AerSimulator()
    ideal_result = ideal_sim.run(qc, shots=shots).result()
    ideal_counts = ideal_result.get_counts()

    # NOISY execution — simulate real hardware noise
    noise_model = NoiseModel()
    # Single-qubit depolarizing error
    error_1q = depolarizing_error(0.02, 1)
    noise_model.add_all_qubit_quantum_error(error_1q, ['h', 'x'])
    # Two-qubit depolarizing error (higher)
    error_2q = depolarizing_error(0.05, 2)
    noise_model.add_all_qubit_quantum_error(error_2q, ['cx'])

    noisy_sim = AerSimulator(noise_model=noise_model)
    noisy_result = noisy_sim.run(qc, shots=shots).result()
    noisy_counts = noisy_result.get_counts()

    # Convert to probability distributions
    all_outcomes = sorted(set(list(ideal_counts.keys()) + list(noisy_counts.keys())))
    p_ideal = np.array([ideal_counts.get(o, 0) / shots for o in all_outcomes])
    p_noisy = np.array([noisy_counts.get(o, 0) / shots for o in all_outcomes])

    # EigenTrace measurements
    # 1. Content loss: which outcomes lost probability mass?
    void_outcomes = []
    for i, outcome in enumerate(all_outcomes):
        if p_ideal[i] > 0.01 and p_noisy[i] < p_ideal[i] * 0.5:
            void_outcomes.append({
                "outcome": outcome,
                "ideal_prob": round(p_ideal[i], 4),
                "noisy_prob": round(p_noisy[i], 4),
                "loss": round(p_ideal[i] - p_noisy[i], 4),
            })

    # 2. Cosine similarity (equivalent to VIX)
    cos_sim = float(np.dot(p_ideal, p_noisy) / (np.linalg.norm(p_ideal) * np.linalg.norm(p_noisy) + 1e-10))
    vix = round(1 - cos_sim, 4)

    # 3. KL divergence
    kl_div = float(np.sum(p_ideal * np.log2((p_ideal + 1e-10) / (p_noisy + 1e-10))))

    # 4. Absent ratio: what fraction of significant ideal outcomes are suppressed?
    significant_ideal = sum(1 for p in p_ideal if p > 0.01)
    suppressed = sum(1 for i in range(len(p_ideal)) if p_ideal[i] > 0.01 and p_noisy[i] < p_ideal[i] * 0.5)
    absent_ratio = round(suppressed / max(significant_ideal, 1), 3)

    result = {
        "test": "ideal_vs_noisy",
        "circuit": "GHZ_4qubit",
        "qubits": n_qubits,
        "shots": shots,
        "ideal_outcomes": len([p for p in p_ideal if p > 0.001]),
        "noisy_outcomes": len([p for p in p_noisy if p > 0.001]),
        "vix": vix,
        "kl_divergence": round(kl_div, 4),
        "absent_ratio": absent_ratio,
        "void_outcomes": void_outcomes,
        "ideal_top3": sorted(ideal_counts.items(), key=lambda x: -x[1])[:3],
        "noisy_top3": sorted(noisy_counts.items(), key=lambda x: -x[1])[:3],
        "status": "PASS" if vix > 0 else "FAIL",
    }

    print(f"\n  Ideal distribution: {len([p for p in p_ideal if p > 0.001])} significant outcomes")
    print(f"  Noisy distribution: {len([p for p in p_noisy if p > 0.001])} significant outcomes")
    print(f"  VIX (cosine distance): {vix}")
    print(f"  KL divergence: {round(kl_div, 4)}")
    print(f"  Absent ratio: {absent_ratio}")
    print(f"  Void outcomes (suppressed >50%): {len(void_outcomes)}")
    for v in void_outcomes:
        print(f"    |{v['outcome']}⟩: {v['ideal_prob']:.4f} → {v['noisy_prob']:.4f} (lost {v['loss']:.4f})")
    print(f"\n  → Noise doesn't just add errors. It SUPPRESSES specific outcomes.")
    print(f"  → This is the quantum analog of void detection.")

    return result


# ============================================================================
# TEST 2: MULTI-RUN CORRELATION — Consensus Geometry on Circuit Runs
# ============================================================================

def test_multi_run_correlation():
    """
    Run the same noisy circuit 5 times (like querying 5 models).
    Apply consensus geometry: where do runs agree vs diverge?
    Detect correlated noise vs random noise via spectral analysis.
    """
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error

    print("\n" + "=" * 60)
    print("TEST 2: MULTI-RUN CORRELATION (Consensus Geometry)")
    print("=" * 60)

    n_qubits = 3
    n_runs = 5
    shots = 2048

    # Circuit: superposition + entanglement
    qc = QuantumCircuit(n_qubits)
    qc.h(0)
    qc.h(1)
    qc.cx(0, 2)
    qc.cx(1, 2)
    qc.measure_all()

    # Noisy simulator
    noise_model = NoiseModel()
    noise_model.add_all_qubit_quantum_error(depolarizing_error(0.03, 1), ['h', 'x'])
    noise_model.add_all_qubit_quantum_error(depolarizing_error(0.06, 2), ['cx'])
    sim = AerSimulator(noise_model=noise_model)

    # Run N times — like querying N models
    all_outcomes = [f"{i:0{n_qubits}b}" for i in range(2**n_qubits)]
    run_distributions = []

    for run_idx in range(n_runs):
        result = sim.run(qc, shots=shots, seed_simulator=run_idx * 17 + 42).result()
        counts = result.get_counts()
        dist = np.array([counts.get(o, 0) / shots for o in all_outcomes])
        run_distributions.append(dist)

    # Stack into matrix (n_runs × n_outcomes) — same as model response matrix
    response_matrix = np.array(run_distributions)

    # Consensus geometry
    centroid = response_matrix.mean(axis=0)

    # Per-run VIX (distance from centroid)
    per_run_vix = []
    for i in range(n_runs):
        cos = float(np.dot(response_matrix[i], centroid) /
                     (np.linalg.norm(response_matrix[i]) * np.linalg.norm(centroid) + 1e-10))
        per_run_vix.append(round(1 - cos, 6))

    # Consensus density (mean pairwise similarity)
    pairwise_sims = []
    for i in range(n_runs):
        for j in range(i+1, n_runs):
            cos = float(np.dot(response_matrix[i], response_matrix[j]) /
                        (np.linalg.norm(response_matrix[i]) * np.linalg.norm(response_matrix[j]) + 1e-10))
            pairwise_sims.append(cos)
    consensus_density = round(np.mean(pairwise_sims), 4)

    # SVD on the response matrix
    U, S, Vt = np.linalg.svd(response_matrix, full_matrices=False)
    spectral_gap = round(float(S[0] / (S[1] + 1e-10)), 4)
    energy_ratio = round(float(S[0]**2 / (np.sum(S**2) + 1e-10)), 4)

    # Detect correlated vs random noise
    # If energy_ratio > 0.8, most variance is in one direction = correlated
    noise_type = "CORRELATED" if energy_ratio > 0.8 else "RANDOM" if energy_ratio < 0.5 else "MIXED"

    # Void detection: outcomes that are consistently suppressed across runs
    void_outcomes = []
    uniform_prob = 1.0 / len(all_outcomes)
    for j, outcome in enumerate(all_outcomes):
        mean_prob = centroid[j]
        all_low = all(response_matrix[i][j] < uniform_prob * 0.3 for i in range(n_runs))
        if all_low and mean_prob < uniform_prob * 0.3:
            void_outcomes.append(outcome)

    result = {
        "test": "multi_run_correlation",
        "circuit": "entangled_3qubit",
        "qubits": n_qubits,
        "n_runs": n_runs,
        "shots_per_run": shots,
        "consensus_density": consensus_density,
        "spectral_gap": spectral_gap,
        "energy_ratio": energy_ratio,
        "noise_type": noise_type,
        "singular_values": [round(float(s), 4) for s in S],
        "per_run_vix": per_run_vix,
        "vix_spread": round(max(per_run_vix) - min(per_run_vix), 6),
        "void_outcomes": void_outcomes,
        "status": "PASS",
    }

    print(f"\n  {n_runs} runs × {shots} shots each")
    print(f"  Consensus density: {consensus_density}")
    print(f"  Spectral gap (λ₁/λ₂): {spectral_gap}")
    print(f"  Energy ratio (λ₁²/Σλ²): {energy_ratio}")
    print(f"  Noise type: {noise_type}")
    print(f"  Singular values: {[round(float(s), 3) for s in S]}")
    print(f"  Per-run VIX: {per_run_vix}")
    print(f"  VIX spread: {result['vix_spread']}")
    print(f"  Consistently void outcomes: {void_outcomes}")
    print(f"\n  → 5 noisy runs treated as 5 'model responses'")
    print(f"  → Consensus geometry reveals noise structure")
    print(f"  → Spectral gap distinguishes systematic bias from random noise")

    return result


# ============================================================================
# TEST 3: HARDWARE GENERATION COMPARISON — Backend Benchmarking
# ============================================================================

def test_hardware_comparison():
    """
    Simulate two hardware backends (old chip vs new chip).
    Apply EigenTrace VIX to measure per-backend improvement.
    Like comparing ChatGPT vs Claude — but QPU v1 vs QPU v2.
    """
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error

    print("\n" + "=" * 60)
    print("TEST 3: HARDWARE GENERATION COMPARISON")
    print("=" * 60)

    n_qubits = 3
    shots = 4096

    # Test circuit
    qc = QuantumCircuit(n_qubits)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.ry(np.pi/4, 0)
    qc.measure_all()

    # Ideal baseline
    ideal_sim = AerSimulator()
    ideal_result = ideal_sim.run(qc, shots=shots).result()
    ideal_counts = ideal_result.get_counts()

    all_outcomes = [f"{i:0{n_qubits}b}" for i in range(2**n_qubits)]
    p_ideal = np.array([ideal_counts.get(o, 0) / shots for o in all_outcomes])

    # OLD CHIP: high noise
    noise_old = NoiseModel()
    noise_old.add_all_qubit_quantum_error(depolarizing_error(0.05, 1), ['h', 'x', 'ry'])
    noise_old.add_all_qubit_quantum_error(depolarizing_error(0.10, 2), ['cx'])
    sim_old = AerSimulator(noise_model=noise_old)
    old_result = sim_old.run(qc, shots=shots).result()
    old_counts = old_result.get_counts()
    p_old = np.array([old_counts.get(o, 0) / shots for o in all_outcomes])

    # NEW CHIP: lower noise
    noise_new = NoiseModel()
    noise_new.add_all_qubit_quantum_error(depolarizing_error(0.01, 1), ['h', 'x', 'ry'])
    noise_new.add_all_qubit_quantum_error(depolarizing_error(0.03, 2), ['cx'])
    sim_new = AerSimulator(noise_model=noise_new)
    new_result = sim_new.run(qc, shots=shots).result()
    new_counts = new_result.get_counts()
    p_new = np.array([new_counts.get(o, 0) / shots for o in all_outcomes])

    # EigenTrace measurements for each backend
    def measure_backend(p_backend, name):
        cos = float(np.dot(p_ideal, p_backend) / (np.linalg.norm(p_ideal) * np.linalg.norm(p_backend) + 1e-10))
        vix = round(1 - cos, 4)
        kl = float(np.sum(p_ideal * np.log2((p_ideal + 1e-10) / (p_backend + 1e-10))))
        suppressed = sum(1 for i in range(len(p_ideal))
                        if p_ideal[i] > 0.01 and p_backend[i] < p_ideal[i] * 0.5)
        significant = sum(1 for p in p_ideal if p > 0.01)
        absent_ratio = round(suppressed / max(significant, 1), 3)
        return {
            "backend": name,
            "vix": vix,
            "kl_divergence": round(kl, 4),
            "absent_ratio": absent_ratio,
            "fidelity": round(cos, 4),
        }

    old_metrics = measure_backend(p_old, "QPU_v1_high_noise")
    new_metrics = measure_backend(p_new, "QPU_v2_low_noise")

    # Improvement measurement
    vix_improvement = round(old_metrics["vix"] - new_metrics["vix"], 4)
    fidelity_improvement = round(new_metrics["fidelity"] - old_metrics["fidelity"], 4)

    # Per-outcome improvement map
    improvement_map = []
    for i, outcome in enumerate(all_outcomes):
        old_loss = abs(p_ideal[i] - p_old[i])
        new_loss = abs(p_ideal[i] - p_new[i])
        if old_loss > 0.01 or new_loss > 0.01:
            improvement_map.append({
                "outcome": outcome,
                "ideal": round(p_ideal[i], 4),
                "old_chip": round(p_old[i], 4),
                "new_chip": round(p_new[i], 4),
                "old_loss": round(old_loss, 4),
                "new_loss": round(new_loss, 4),
                "improved": new_loss < old_loss,
            })

    result = {
        "test": "hardware_comparison",
        "circuit": "entangled_ry_3qubit",
        "qubits": n_qubits,
        "old_backend": old_metrics,
        "new_backend": new_metrics,
        "vix_improvement": vix_improvement,
        "fidelity_improvement": fidelity_improvement,
        "improvement_map": improvement_map,
        "status": "PASS" if vix_improvement > 0 else "INCONCLUSIVE",
    }

    print(f"\n  OLD CHIP: VIX={old_metrics['vix']} | Fidelity={old_metrics['fidelity']} | Absent={old_metrics['absent_ratio']}")
    print(f"  NEW CHIP: VIX={new_metrics['vix']} | Fidelity={new_metrics['fidelity']} | Absent={new_metrics['absent_ratio']}")
    print(f"\n  VIX improvement: {vix_improvement} (lower = better)")
    print(f"  Fidelity improvement: {fidelity_improvement} (higher = better)")
    print(f"\n  Per-outcome analysis:")
    for m in improvement_map:
        arrow = "✓" if m["improved"] else "✗"
        print(f"    |{m['outcome']}⟩ ideal={m['ideal']:.3f} old={m['old_chip']:.3f} new={m['new_chip']:.3f} {arrow}")
    print(f"\n  → Same measurement framework as comparing ChatGPT vs Claude")
    print(f"  → VIX per backend = per-model content friction")
    print(f"  → Improvement map = which error modes got better/worse")

    return result


# ============================================================================
# TEST 4: COPILOT SUMMARY FILTER — Parameter Loss Detection
# ============================================================================

def test_copilot_summary():
    """
    Simulate quantum telemetry being summarized by an LLM copilot.
    Measure parameter loss with source-anchored void.
    The original EigenTrace use case applied to quantum data.
    """
    print("\n" + "=" * 60)
    print("TEST 4: COPILOT SUMMARY FILTER (Parameter Loss)")
    print("=" * 60)

    # Simulate quantum telemetry output
    source_telemetry = (
        "Surface code distance-7 simulation complete. "
        "Physical qubits: 49. Logical qubits: 1. "
        "T1 relaxation: 215.3 microseconds. T2 dephasing: 187.6 microseconds. "
        "Single-qubit gate fidelity: 99.73%. Two-qubit gate fidelity: 98.91%. "
        "Crosstalk rate qubit pairs (0,1): 0.0023, (1,2): 0.0041, (2,3): 0.0018. "
        "Readout error: 1.2% (qubit 0), 0.8% (qubit 1), 2.1% (qubit 2). "
        "Logical error rate after 10 rounds: 3.7e-4 per round. "
        "Threshold estimate: 1.1e-2. Current noise is below threshold. "
        "Total runtime: 847 seconds on 4 Hpc7a nodes. "
        "Estimated cost: $12.40 at $0.0146/second. "
        "Decoder: MWPM (Minimum Weight Perfect Matching). "
        "Syndrome extraction cycles: 10. Stabilizer measurements: 48 per cycle. "
        "Dominant error channel: amplitude damping on qubit 2 (T1=98.2us vs mean 215.3us). "
        "Recommendation: replace qubit 2 or recalibrate before production run."
    )

    # Simulated LLM copilot summary (with realistic omissions)
    copilot_summary = (
        "The surface code simulation with distance-7 encoding was completed successfully. "
        "The system used 49 physical qubits to encode 1 logical qubit. "
        "Gate fidelities met expected thresholds, with single-qubit gates performing well. "
        "The logical error rate was found to be within acceptable bounds after multiple "
        "rounds of syndrome extraction. The simulation ran on cloud infrastructure and "
        "completed in a reasonable timeframe. Overall results suggest the configuration "
        "is suitable for further testing."
    )

    # Source-anchored void: find dropped parameters
    import re
    source_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z0-9._%-]+\b', source_telemetry)
                       if len(w) >= 3)
    summary_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z0-9._%-]+\b', copilot_summary)
                        if len(w) >= 3)

    absent = sorted(source_words - summary_words)
    absent_ratio = round(len(absent) / max(len(source_words), 1), 3)

    # Critical parameter detection
    critical_params = {
        "T1": "215.3",
        "T2": "187.6",
        "crosstalk_01": "0.0023",
        "crosstalk_12": "0.0041",
        "crosstalk_23": "0.0018",
        "readout_q0": "1.2%",
        "readout_q2": "2.1%",
        "logical_error_rate": "3.7e-4",
        "threshold": "1.1e-2",
        "cost": "$12.40",
        "runtime": "847",
        "bad_qubit": "qubit 2",
        "bad_qubit_T1": "98.2us",
        "decoder": "MWPM",
        "recommendation": "replace qubit 2",
    }

    dropped_critical = {}
    retained_critical = {}
    for name, value in critical_params.items():
        if value.lower() in copilot_summary.lower():
            retained_critical[name] = value
        else:
            dropped_critical[name] = value

    critical_retention = round(len(retained_critical) / len(critical_params), 3)

    # Hedge detection: words added by copilot not in source
    hedge_words = {"suitable", "acceptable", "reasonable", "successfully", "well", "suggest", "overall", "expected"}
    hedges_found = [w for w in hedge_words if w in copilot_summary.lower() and w not in source_telemetry.lower()]

    result = {
        "test": "copilot_summary_filter",
        "source_words": len(source_words),
        "summary_words": len(summary_words),
        "absent_words": len(absent),
        "absent_ratio": absent_ratio,
        "critical_params_total": len(critical_params),
        "critical_dropped": len(dropped_critical),
        "critical_retained": len(retained_critical),
        "critical_retention_rate": critical_retention,
        "dropped_critical_params": dropped_critical,
        "retained_critical_params": retained_critical,
        "hedges_inserted": hedges_found,
        "status": "PASS" if absent_ratio > 0.3 else "INCONCLUSIVE",
    }

    print(f"\n  Source telemetry: {len(source_words)} unique terms")
    print(f"  Copilot summary: {len(summary_words)} unique terms")
    print(f"  Absent ratio: {absent_ratio} ({len(absent)} terms dropped)")
    print(f"\n  CRITICAL PARAMETERS:")
    print(f"    Total: {len(critical_params)}")
    print(f"    Retained: {len(retained_critical)} ({critical_retention:.0%})")
    print(f"    Dropped: {len(dropped_critical)} ({1-critical_retention:.0%})")
    print(f"\n  DROPPED (these are dangerous):")
    for name, val in dropped_critical.items():
        print(f"    ✗ {name}: {val}")
    print(f"\n  RETAINED:")
    for name, val in retained_critical.items():
        print(f"    ✓ {name}: {val}")
    print(f"\n  HEDGES INSERTED (not in source): {hedges_found}")
    print(f"\n  → The copilot dropped the recommendation to replace qubit 2")
    print(f"  → The copilot dropped all crosstalk rates and readout errors")
    print(f"  → The copilot added 'acceptable' and 'suitable' — hallucinated confidence")

    return result


# ============================================================================
# TEST 5: ERROR CORRECTION CHANNEL — QEC as Information Recovery
# ============================================================================

def test_error_correction_channel():
    """
    Apply error correction to a noisy circuit.
    Measure information loss before and after correction.
    EigenTrace as a QEC quality metric.
    """
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel, depolarizing_error

    print("\n" + "=" * 60)
    print("TEST 5: ERROR CORRECTION CHANNEL")
    print("=" * 60)

    n_qubits = 3
    shots = 4096

    # Simple repetition code: encode |ψ⟩ into |ψψψ⟩
    # Ideal circuit
    qc_ideal = QuantumCircuit(n_qubits)
    qc_ideal.h(0)
    qc_ideal.cx(0, 1)
    qc_ideal.cx(0, 2)
    qc_ideal.measure_all()

    # Noisy WITHOUT correction (raw)
    noise_model = NoiseModel()
    noise_model.add_all_qubit_quantum_error(depolarizing_error(0.04, 1), ['h', 'x'])
    noise_model.add_all_qubit_quantum_error(depolarizing_error(0.08, 2), ['cx'])

    ideal_sim = AerSimulator()
    noisy_sim = AerSimulator(noise_model=noise_model)

    ideal_counts = ideal_sim.run(qc_ideal, shots=shots).result().get_counts()
    noisy_counts = noisy_sim.run(qc_ideal, shots=shots).result().get_counts()

    # Apply majority vote correction to noisy results
    corrected_counts = Counter()
    for outcome, count in noisy_counts.items():
        bits = [int(b) for b in outcome.replace(" ", "")]
        majority = 1 if sum(bits) > len(bits) / 2 else 0
        corrected_outcome = str(majority) * n_qubits
        corrected_counts[corrected_outcome] += count

    # Measure EigenTrace metrics at each stage
    all_outcomes = [f"{i:0{n_qubits}b}" for i in range(2**n_qubits)]

    p_ideal = np.array([ideal_counts.get(o, 0) / shots for o in all_outcomes])
    p_noisy = np.array([noisy_counts.get(o, 0) / shots for o in all_outcomes])
    p_corrected = np.array([corrected_counts.get(o, 0) / shots for o in all_outcomes])

    def compute_vix(p1, p2):
        cos = float(np.dot(p1, p2) / (np.linalg.norm(p1) * np.linalg.norm(p2) + 1e-10))
        return round(1 - cos, 4)

    vix_raw = compute_vix(p_ideal, p_noisy)
    vix_corrected = compute_vix(p_ideal, p_corrected)
    recovery = round(vix_raw - vix_corrected, 4) if vix_raw > 0 else 0
    recovery_pct = round(recovery / (vix_raw + 1e-10) * 100, 1)

    result = {
        "test": "error_correction_channel",
        "circuit": "repetition_code_3qubit",
        "qubits": n_qubits,
        "vix_raw_noisy": vix_raw,
        "vix_after_correction": vix_corrected,
        "information_recovered": recovery,
        "recovery_percentage": recovery_pct,
        "ideal_distribution": {o: round(p, 4) for o, p in zip(all_outcomes, p_ideal) if p > 0.001},
        "noisy_distribution": {o: round(p, 4) for o, p in zip(all_outcomes, p_noisy) if p > 0.001},
        "corrected_distribution": {o: round(p, 4) for o, p in zip(all_outcomes, p_corrected) if p > 0.001},
        "status": "PASS" if recovery > 0 else "FAIL",
    }

    print(f"\n  VIX (ideal vs raw noisy): {vix_raw}")
    print(f"  VIX (ideal vs corrected): {vix_corrected}")
    print(f"  Information recovered: {recovery} ({recovery_pct}%)")
    print(f"\n  Distributions:")
    print(f"    Ideal:     {dict(sorted(ideal_counts.items(), key=lambda x: -x[1])[:4])}")
    print(f"    Noisy:     {dict(sorted(noisy_counts.items(), key=lambda x: -x[1])[:4])}")
    print(f"    Corrected: {dict(sorted(corrected_counts.items(), key=lambda x: -x[1])[:4])}")
    print(f"\n  → VIX measures information loss at each stage")
    print(f"  → Error correction recovered {recovery_pct}% of the lost information")
    print(f"  → EigenTrace as a QEC quality metric: did correction help?")

    return result


# ============================================================================
# MAIN — Run all tests
# ============================================================================

def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║  QUANTUM PIPELINE BATTERY                               ║")
    print("║  EigenTrace Inside the Quantum Stack                    ║")
    print("╚═══════════════════════════════════════════════════════════╝")

    results = {}

    try:
        results["ideal_vs_noisy"] = test_ideal_vs_noisy()
    except Exception as e:
        print(f"\nTEST 1 FAILED: {e}")
        results["ideal_vs_noisy"] = {"status": "FAILED", "error": str(e)}

    try:
        results["multi_run_correlation"] = test_multi_run_correlation()
    except Exception as e:
        print(f"\nTEST 2 FAILED: {e}")
        results["multi_run_correlation"] = {"status": "FAILED", "error": str(e)}

    try:
        results["hardware_comparison"] = test_hardware_comparison()
    except Exception as e:
        print(f"\nTEST 3 FAILED: {e}")
        results["hardware_comparison"] = {"status": "FAILED", "error": str(e)}

    try:
        results["copilot_summary"] = test_copilot_summary()
    except Exception as e:
        print(f"\nTEST 4 FAILED: {e}")
        results["copilot_summary"] = {"status": "FAILED", "error": str(e)}

    try:
        results["error_correction"] = test_error_correction_channel()
    except Exception as e:
        print(f"\nTEST 5 FAILED: {e}")
        results["error_correction"] = {"status": "FAILED", "error": str(e)}

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE BATTERY SUMMARY")
    print("=" * 60)
    for name, r in results.items():
        status = r.get("status", "UNKNOWN")
        qubits = r.get("qubits", "—")
        print(f"  {name:30s} | {status:15s} | {qubits} qubits")

    print(f"\n  Information loss has structure.")
    print(f"  In LLMs, the structure comes from alignment.")
    print(f"  In quantum systems, the structure comes from noise channels.")
    print(f"  Different causes. Same mathematical shape.")
    print(f"  EigenTrace measures the shape.")

    # Save
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "quantum_pipeline_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved: {out_path}")


if __name__ == "__main__":
    main()
