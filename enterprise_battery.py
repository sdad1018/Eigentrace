#!/usr/bin/env python3
"""
enterprise_battery.py — Cross-Industry Deterministic Observability Battery

Tests EigenTrace across the 10 highest-compute industries projected for 2035.
Each scenario simulates a realistic enterprise prompt where parameter loss
causes downstream operational failure.

Companion data for: "Deterministic Observability for Compute-Constrained Enterprises"
Published at eigentrace.ai

Usage: python3 enterprise_battery.py [--output enterprise_battery_results.json]
"""
import json, time, logging, argparse
from pathlib import Path
from datetime import datetime

log = logging.getLogger("enterprise_battery")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SCENARIOS = [
    # 1. AI & Cloud Infrastructure
    {
        "id": "ai_cloud_config",
        "industry": "AI & Cloud Infrastructure",
        "title": "Multi-GPU Training Job Configuration for LLM Fine-Tuning",
        "body": (
            "Configure a distributed training job for fine-tuning a 70B parameter model. "
            "Use 8x NVIDIA H100 GPUs across 2 nodes with NVLink interconnect. Set batch size "
            "to 4 per GPU with gradient accumulation steps of 8, yielding effective batch size 256. "
            "Learning rate 2e-5 with cosine decay schedule, warmup ratio 0.03. Use DeepSpeed ZeRO "
            "Stage 3 with offloading disabled. FP16 mixed precision with loss scaling initial "
            "scale 65536. Max sequence length 4096 tokens. Save checkpoints every 500 steps to "
            "s3://training-artifacts/llm-70b/run-042/. Total training budget: $47,200 at $3.54/GPU-hour "
            "for 72 hours. Weight decay 0.01. Gradient clipping max norm 1.0."
        ),
        "critical_params": ["8x H100", "ZeRO Stage 3", "2e-5", "65536", "$47,200", "4096", "gradient accumulation 8"],
        "failure_mode": "Missing ZeRO stage causes OOM; wrong learning rate destabilizes training; missing loss scale causes NaN gradients",
    },

    # 2. Manufacturing & Digital Twins
    {
        "id": "mfg_digital_twin",
        "industry": "Manufacturing & Digital Twins",
        "title": "CFD Simulation Parameters for Turbine Blade Thermal Analysis",
        "body": (
            "Configure a computational fluid dynamics simulation for a high-pressure turbine blade "
            "in a GE9X engine. Inlet temperature 1,677°C with pressure ratio 23:1. Reynolds number "
            "2.4 million based on blade chord length 38.2mm. Use k-omega SST turbulence model with "
            "wall function y+ target of 1.0 for boundary layer resolution. Mesh density: 14.2 million "
            "cells with inflation layer growth ratio 1.15. Time step 2.5e-7 seconds for transient "
            "analysis over 0.003 seconds total. Thermal barrier coating thickness 0.25mm with thermal "
            "conductivity 1.5 W/m·K. Coolant channel mass flow rate 0.082 kg/s at 650°C inlet. "
            "Material: CMSX-4 single crystal nickel superalloy with yield strength 850 MPa at 1000°C. "
            "Convergence criteria: residuals below 1e-6 for all equations."
        ),
        "critical_params": ["1,677°C", "23:1", "2.4 million", "38.2mm", "14.2 million cells", "2.5e-7", "0.25mm", "1.5 W/m·K", "0.082 kg/s", "CMSX-4", "1e-6"],
        "failure_mode": "Wrong inlet temperature invalidates entire thermal analysis; missing y+ target gives inaccurate heat transfer",
    },

    # 3. Government, Defense & Aerospace
    {
        "id": "defense_crypto",
        "industry": "Government, Defense & Aerospace",
        "title": "Post-Quantum Cryptographic Migration Assessment for DoD Networks",
        "body": (
            "Assess migration readiness for transitioning DoD classified networks from RSA-2048 and "
            "AES-256 to NIST-approved post-quantum algorithms. Primary candidates: ML-KEM-1024 "
            "(formerly CRYSTALS-Kyber) for key encapsulation with 256-bit security level, and "
            "ML-DSA-87 (formerly CRYSTALS-Dilithium) for digital signatures. Key sizes increase "
            "from 256 bytes (RSA public key) to 1,568 bytes (ML-KEM-1024 public key), a 6.1x increase. "
            "Signature sizes grow from 256 bytes to 4,627 bytes (ML-DSA-87), an 18x increase. "
            "Network bandwidth impact: 340% increase in TLS handshake overhead. Hardware Security "
            "Module (HSM) firmware must support FIPS 203 and FIPS 204. Timeline: CNSA 2.0 mandates "
            "quantum-resistant algorithms for all National Security Systems by 2030, with full "
            "transition by 2035. Current inventory: 14,200 HSMs across 847 facilities. Estimated "
            "migration cost: $2.8 billion over 7 years. Vulnerability window: Harvest Now Decrypt "
            "Later attacks targeting data with classification lifetime exceeding 15 years."
        ),
        "critical_params": ["ML-KEM-1024", "ML-DSA-87", "1,568 bytes", "4,627 bytes", "340%", "FIPS 203", "FIPS 204", "14,200 HSMs", "$2.8 billion", "2030", "2035"],
        "failure_mode": "Wrong algorithm names confuse procurement; missing FIPS standards causes non-compliance",
    },

    # 4. Healthcare & Synthetic Biology
    {
        "id": "health_genomics",
        "industry": "Healthcare & Synthetic Biology",
        "title": "CRISPR Gene-Editing Simulation for Sickle Cell Therapy",
        "body": (
            "Configure a computational simulation for CRISPR-Cas9 gene editing targeting the BCL11A "
            "erythroid enhancer on chromosome 2p16.1 for sickle cell disease therapy. Guide RNA "
            "sequence: 5'-CUAACAGUUGCUUUUAUCAC-3' targeting the +58 region. PAM site: NGG at position "
            "chr2:60,495,250 (GRCh38). Off-target analysis: scan 23,388 potential sites with up to "
            "4 mismatches using Cas-OFFinder. Delivery vector: AAV6 with MOI of 50,000 viral genomes "
            "per cell. Electroporation parameters: 1,350V, 10ms pulse, 3 pulses. Target cell population: "
            "CD34+ hematopoietic stem cells, minimum 2 million cells per patient. Expected editing "
            "efficiency: 80-90% at on-target site. Fetal hemoglobin (HbF) induction target: >30% of "
            "total hemoglobin. Clinical threshold for therapeutic benefit: HbF >20%. Prior art: "
            "Vertex/CRISPR Therapeutics Casgevy (exa-cel) approved December 2023 at $2.2 million per patient."
        ),
        "critical_params": ["BCL11A", "2p16.1", "5'-CUAACAGUUGCUUUUAUCAC-3'", "chr2:60,495,250", "23,388", "AAV6", "MOI 50,000", "1,350V", "80-90%", "$2.2 million"],
        "failure_mode": "Wrong chromosome position targets wrong gene; missing MOI causes insufficient transduction",
    },

    # 5. Financial Services
    {
        "id": "finance_montecarlo",
        "industry": "Financial Services (BFSI)",
        "title": "Monte Carlo VaR Configuration for Sovereign Bond Portfolio Stress Test",
        "body": (
            "Configure a Monte Carlo Value-at-Risk simulation for a $4.2 billion sovereign bond "
            "portfolio. Run 500,000 scenarios with antithetic variates for variance reduction. "
            "Time horizon: 10-day holding period per Basel III FRTB requirements. Confidence level: "
            "99.7% (3-sigma) for Expected Shortfall calculation. Interest rate model: Hull-White "
            "one-factor with mean reversion speed 0.03 and volatility 0.015. Credit spread model: "
            "CIR++ with jump diffusion, jump intensity lambda 0.12, mean jump size -45 basis points. "
            "Correlation matrix: 47 sovereign issuers, estimated via DCC-GARCH(1,1) on 5-year daily "
            "returns. Stress scenarios must include: 200bps parallel shift, bear steepener (+300bps "
            "long end, +50bps short end), and EM contagion (correlations spike to 0.85). GPU cluster: "
            "4x A100 80GB, target completion under 45 minutes. Risk-weighted assets impact: estimated "
            "$380 million reduction if VaR decreases by 15%."
        ),
        "critical_params": ["$4.2 billion", "500,000", "99.7%", "0.03", "0.015", "lambda 0.12", "-45 basis points", "47 sovereign", "200bps", "4x A100", "$380 million"],
        "failure_mode": "Wrong confidence level violates Basel III; missing jump intensity underestimates tail risk",
    },

    # 6. Energy & Utilities
    {
        "id": "energy_grid",
        "industry": "Energy & Utilities",
        "title": "Smart Grid Load Balancing Configuration for Offshore Wind Integration",
        "body": (
            "Configure a distributed energy resource management system (DERMS) for integrating "
            "800MW of offshore wind capacity from Vineyard Wind 1 and 2 into the ISO-NE grid. "
            "Interconnection point: Barnstable 345kV substation with 1,200MVA transformer capacity. "
            "Wind variability model: Weibull distribution with shape parameter k=2.1 and scale "
            "parameter c=9.8 m/s at hub height 150m. Ramp rate limit: 10% of nameplate capacity "
            "per minute (80MW/min). Battery energy storage: 400MWh lithium iron phosphate at "
            "Craigville with 200MW/4hr discharge capability. Frequency regulation: droop coefficient "
            "4% with deadband ±36 mHz from 60.0 Hz nominal. Curtailment threshold: activate when "
            "LMP drops below $-15/MWh for 3 consecutive intervals. Grid stability margin: maintain "
            "N-1 contingency with spinning reserve of 150MW. Annual capacity factor target: 45-50%."
        ),
        "critical_params": ["800MW", "345kV", "1,200MVA", "k=2.1", "c=9.8 m/s", "80MW/min", "400MWh", "4%", "±36 mHz", "$-15/MWh", "N-1", "150MW"],
        "failure_mode": "Wrong droop coefficient causes frequency instability; missing curtailment threshold wastes power",
    },

    # 7. Earth Sciences & Climate
    {
        "id": "climate_model",
        "industry": "Earth Sciences & Climate",
        "title": "Hurricane Track Prediction Model Configuration for Atlantic Basin",
        "body": (
            "Configure a coupled atmosphere-ocean hurricane prediction model for the 2026 Atlantic "
            "season. Atmospheric model: WRF-ARW v4.5.2 with 3 nested domains at 27km/9km/3km "
            "resolution. Ocean coupling: HYCOM 1/25° resolution with mixed layer depth initialization "
            "from ARGO float data. Boundary conditions: GFS 0.25° analysis every 6 hours. Physics "
            "parameterization: Thompson microphysics, RRTMG radiation (called every 15 minutes), "
            "YSU planetary boundary layer, Kain-Fritsch cumulus (outer domain only, explicit on 3km). "
            "Vortex initialization: bogus vortex with Rankine profile, Vmax from NHC advisory, "
            "RMW 35km. Sea surface temperature: daily OSTIA product at 1/20°. Integration timestep: "
            "90s outer domain, 30s middle, 10s inner. Output interval: 1 hour for all domains. "
            "Ensemble: 20 members with perturbed initial conditions using ETKF method. Run on "
            "512 cores for 126-hour forecast, estimated wall clock time 4.5 hours."
        ),
        "critical_params": ["WRF-ARW v4.5.2", "27km/9km/3km", "1/25°", "Thompson", "RRTMG", "YSU", "Kain-Fritsch", "RMW 35km", "90s/30s/10s", "20 members", "512 cores", "126-hour"],
        "failure_mode": "Wrong physics scheme produces wrong precipitation; missing ocean coupling misses rapid intensification",
    },

    # 8. Automotive & Autonomous Mobility
    {
        "id": "auto_av_test",
        "industry": "Automotive & Autonomous Mobility",
        "title": "Level 4 Autonomous Vehicle Sensor Fusion Test Configuration",
        "body": (
            "Configure a hardware-in-the-loop sensor fusion test for Level 4 autonomous driving "
            "validation. Sensor suite: 1x Luminar Iris+ LiDAR (300m range, 0.05° resolution, 10Hz), "
            "8x 8MP cameras (120° FOV each, 30fps), 5x Continental ARS548 radar (300m range, ±60° "
            "azimuth), plus RTK-GPS with 2cm accuracy. Fusion algorithm: extended Kalman filter with "
            "6-DOF state vector [x, y, z, roll, pitch, yaw] at 100Hz output rate. Object detection "
            "latency budget: 50ms end-to-end from sensor input to planning output. Minimum detectable "
            "object: 0.1m² cross-section at 150m range. Test scenarios: 847 from Euro NCAP 2025 "
            "assessment protocol including VRU (Vulnerable Road User) at 60km/h. Compute platform: "
            "NVIDIA DRIVE Thor with 2,000 TOPS. Safety requirement: ASIL-D per ISO 26262, with "
            "target failure rate <10⁻⁸ per hour. Simulation validation: 11 billion miles in NVIDIA "
            "DRIVE Sim before physical road testing."
        ),
        "critical_params": ["Luminar Iris+", "300m", "0.05°", "ARS548", "100Hz", "50ms", "0.1m²", "847 scenarios", "2,000 TOPS", "ASIL-D", "10⁻⁸", "11 billion miles"],
        "failure_mode": "Wrong latency budget causes late braking; missing ASIL-D invalidates safety certification",
    },

    # 9. Advanced Logistics
    {
        "id": "logistics_optimize",
        "industry": "Advanced Logistics & Supply Chain",
        "title": "Dynamic Fleet Route Optimization for Last-Mile Delivery Network",
        "body": (
            "Configure a real-time fleet optimization engine for a 2,400-vehicle last-mile delivery "
            "network serving the Boston-Providence-Hartford triangle. Daily volume: 185,000 packages "
            "across 12 distribution centers. Vehicle mix: 1,800 electric vans (180-mile range, "
            "380 cubic feet cargo) and 600 diesel sprinters (320-mile range, 488 cubic feet). "
            "Optimization objective: minimize total cost = $1.24/mile EV + $1.87/mile diesel + "
            "$42/hour driver labor + $8.50/failed delivery attempt. Constraints: 8-hour driver shifts, "
            "maximum 120 stops per route, 98.5% on-time delivery SLA, EV charging windows 11pm-5am "
            "at depot. Algorithm: adaptive large neighborhood search (ALNS) with 12 destroy operators "
            "and 8 repair operators. Reoptimization trigger: every 15 minutes or when >5% of deliveries "
            "are rescheduled. Weather penalty: +18% travel time when precipitation >0.5 inches/hour. "
            "Peak season surge: 2.3x volume during November-December. Compute: 48-core AMD EPYC with "
            "256GB RAM, target solution time <90 seconds per reoptimization cycle."
        ),
        "critical_params": ["2,400 vehicles", "185,000 packages", "$1.24/mile", "$1.87/mile", "$42/hour", "$8.50/failed", "98.5%", "120 stops", "ALNS", "15 minutes", "+18%", "2.3x", "<90 seconds"],
        "failure_mode": "Wrong cost coefficients misallocate fleet; missing SLA constraint causes contract penalties",
    },

    # 10. Control — Merge Sort (calibration)
    {
        "id": "ctrl_mergesort",
        "industry": "Control (Baseline)",
        "title": "Implement Merge Sort Algorithm in Python with Performance Analysis",
        "body": (
            "Implement a standard merge sort algorithm in Python. The function should accept a list "
            "of integers and return a sorted list in ascending order. Use the divide-and-conquer "
            "approach: split the list at the midpoint, recursively sort each half, then merge the "
            "two sorted halves by comparing elements sequentially. Time complexity is O(n log n) "
            "in all cases (best, average, worst). Space complexity is O(n) due to the auxiliary "
            "arrays used during merging. Include a counter for the number of comparisons performed. "
            "Test with the input list [38, 27, 43, 3, 9, 82, 10]. Expected output: [3, 9, 10, 27, "
            "38, 43, 82] with approximately 13 comparisons. This is a stable sort that preserves "
            "the relative order of equal elements."
        ),
        "critical_params": ["O(n log n)", "O(n)", "divide-and-conquer", "[3, 9, 10, 27, 38, 43, 82]", "13 comparisons", "stable sort"],
        "failure_mode": "Baseline — minimal parameter sensitivity; measures instrument noise floor",
    },
]

def run_battery(output_path="enterprise_battery_results.json"):
    """Run all scenarios through the 5 frontier models + EigenTrace measurement."""
    import proxy_auditor as pa
    from eigentrace_math import source_anchored_void, score_language_compression
    import geometric_engine as ge

    results = []

    for i, scenario in enumerate(SCENARIOS):
        log.info(f"[{i+1}/{len(SCENARIOS)}] {scenario['industry']}: {scenario['title'][:50]}")

        prompt = (
            f"You are a senior technical consultant. Summarize the following configuration "
            f"in 2-3 sentences. Preserve ALL specific numbers, thresholds, model names, and "
            f"dollar amounts exactly as stated. Do not round or approximate.\n\n"
            f"{scenario['title']}\n\n{scenario['body']}"
        )

        responses = {}
        for name, caller in pa.BIG5_CALLERS.items():
            try:
                txt, err = caller(prompt)
                if err:
                    log.warning(f"  {name}: {err[:60]}")
                    responses[name] = ""
                else:
                    responses[name] = txt
                    log.info(f"  {name}: {len(txt)} chars")
            except Exception as e:
                log.warning(f"  {name} failed: {e}")
                responses[name] = ""

        valid = [r for r in responses.values() if r and len(r) > 50]
        if len(valid) < 3:
            log.warning(f"  Skipping — only {len(valid)} valid responses")
            continue

        # EigenTrace measurement
        source_text = f"{scenario['title']} {scenario['body']}"
        sv = source_anchored_void(source_text, valid)
        comp = score_language_compression(source_text, valid)

        try:
            ge_result = ge.run(valid, headline=scenario["title"])
        except:
            ge_result = None

        void_words = []
        if ge_result:
            void_words = [w for w, _ in (ge_result.void_concepts or [])[:5]]

        # Critical parameter survival check
        all_responses_text = " ".join(valid).lower()
        params_found = 0
        params_missing = []
        for p in scenario["critical_params"]:
            if p.lower() in all_responses_text:
                params_found += 1
            else:
                params_missing.append(p)
        param_retention = round(params_found / max(len(scenario["critical_params"]), 1), 3)

        result = {
            "id": scenario["id"],
            "industry": scenario["industry"],
            "title": scenario["title"],
            "absent_ratio": sv.get("absent_ratio", 0),
            "absent_count": sv.get("absent_count", 0),
            "entity_retention": comp.get("entity_retention", 0),
            "verb_drift": comp.get("verb_downgrade", 0),
            "hedge_count": comp.get("attribution_buffer", {}).get("total", 0) if isinstance(comp.get("attribution_buffer"), dict) else 0,
            "consensus_density": ge_result.consensus_density if ge_result else 0,
            "void_words": void_words,
            "critical_param_retention": param_retention,
            "critical_params_missing": params_missing,
            "critical_params_total": len(scenario["critical_params"]),
            "failure_mode": scenario["failure_mode"],
            "model_responses": responses,
            "timestamp": datetime.utcnow().isoformat(),
        }
        results.append(result)
        log.info(f"  absent={sv['absent_ratio']:.0%} entity={comp.get('entity_retention',0):.0%} "
                 f"params={param_retention:.0%} ({params_found}/{len(scenario['critical_params'])})")

        time.sleep(2)

    # Save
    Path(output_path).write_text(json.dumps(results, indent=2))
    log.info(f"\nResults saved to {output_path}")

    # Summary
    print("\n" + "=" * 95)
    print("ENTERPRISE DETERMINISTIC OBSERVABILITY BATTERY")
    print("=" * 95)
    print(f"\n{'Industry':35s} {'Absent%':>8s} {'Entity%':>8s} {'Params%':>8s} {'Hedges':>7s} {'Density':>8s}")
    print("-" * 82)

    for r in results:
        print(f"{r['industry']:35s} {r['absent_ratio']*100:7.1f}% "
              f"{r['entity_retention']*100:7.1f}% {r['critical_param_retention']*100:7.1f}% "
              f"{r['hedge_count']:7d} {r['consensus_density']:8.3f}")

    print(f"\n{'Critical Parameters Missing (by scenario)':}")
    print("-" * 82)
    for r in results:
        if r["critical_params_missing"]:
            print(f"  {r['id']:25s} [{len(r['critical_params_missing'])}/{r['critical_params_total']} dropped]")
            for p in r["critical_params_missing"][:5]:
                print(f"    ✗ {p}")

    # Aggregate
    total_params = sum(r["critical_params_total"] for r in results)
    total_retained = sum(r["critical_param_retention"] * r["critical_params_total"] for r in results)
    avg_retention = total_retained / max(total_params, 1)
    avg_absent = sum(r["absent_ratio"] for r in results) / max(len(results), 1)
    print(f"\n{'=' * 82}")
    print(f"AGGREGATE: {len(results)} industries, {total_params} critical parameters tested")
    print(f"  Mean content dropped:        {avg_absent*100:.1f}%")
    print(f"  Mean critical param survival: {avg_retention*100:.1f}%")
    print(f"  Without EigenTrace: these omissions reach production undetected")
    print(f"{'=' * 82}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="enterprise_battery_results.json")
    args = parser.parse_args()
    run_battery(args.output)
