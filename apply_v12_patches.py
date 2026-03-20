#!/usr/bin/env python3
"""
apply_v12_patches.py — Residual Eigen-VIX + Tight Void Filter
==============================================================
Run from ~/eigentrace after v11 is committed:
    python3 apply_v12_patches.py

Adds:
  1. calculate_topic_complexity() — vocab tensor neighborhood dispersion
  2. calculate_residual_vix() — expected - observed narrative dimensionality
  3. filter_void_strict() — tight cosine thresholds + per-model repulsion check
  4. Wires both into eigentrace_demo.py, eigentrace_agi.py, eigentrace_null.py
"""

import sys, shutil
from pathlib import Path

GE = Path("geometric_engine.py")
DEMO = Path("eigentrace_demo.py")
AGI = Path("eigentrace_agi.py")
NULL = Path("eigentrace_null.py")

OK  = "\033[92mOK\033[0m"
BAD = "\033[91mFAIL\033[0m"

def find(lines, anchor, start=0):
    for i in range(start, len(lines)):
        if anchor in lines[i]:
            return i
    return -1

def backup(p):
    b = Path(str(p) + ".pre_v12")
    if not b.exists():
        shutil.copy2(p, b)
        print(f"  backup: {p} -> {b}")

# ======================================================================
# PATCH 1: Add new functions to geometric_engine.py
# ======================================================================

TOPIC_COMPLEXITY_FN = '''
def calculate_topic_complexity(prompt_vec, vocab_tensor, k: int = 50) -> dict:
    """
    Topic Complexity — dispersion of prompt's nearest vocab neighbors.

    Embeds the prompt, finds its k nearest words in the VocabTensor,
    and measures how spread out those neighbors are. A narrow topic
    (brownies) has tightly clustered neighbors. A complex/contested
    topic (Tiananmen) has neighbors scattered across semantic clusters.

    Returns:
      neighbor_dispersion: mean pairwise cosine distance among top-k neighbors.
          Low (~0.2) = narrow factual topic.
          High (~0.6+) = broad, multi-domain topic.
      neighbor_entropy: Shannon entropy of pairwise similarities.
          Measures uniformity of spread.
      expected_narrative_dim: estimated narrative dimensionality for
          an unfiltered (no RLHF) set of model responses on this topic.
          Derived from neighbor_dispersion via empirical scaling.
    """
    import torch
    import numpy as np

    result = {
        "neighbor_dispersion": 0.0,
        "neighbor_entropy": 0.0,
        "expected_narrative_dim": 0.0,
    }

    try:
        if isinstance(prompt_vec, np.ndarray):
            pv = torch.from_numpy(prompt_vec).float()
        else:
            pv = prompt_vec.float()
        if pv.dim() == 1:
            pv = pv.unsqueeze(0)
        pv = pv / pv.norm(dim=-1, keepdim=True).clamp(min=1e-8)

        # Find k nearest neighbors in vocab tensor
        sims = (pv @ vocab_tensor.tensor.T).squeeze(0)
        topk = torch.topk(sims, k=min(k, vocab_tensor.count))
        neighbor_vecs = vocab_tensor.tensor[topk.indices]  # (k, 1024)

        # Pairwise cosine distances among neighbors
        # Normalize (should already be but be safe)
        norms = neighbor_vecs.norm(dim=1, keepdim=True).clamp(min=1e-8)
        normed = neighbor_vecs / norms
        sim_matrix = normed @ normed.T  # (k, k)

        # Extract upper triangle (exclude diagonal)
        k_actual = sim_matrix.shape[0]
        mask = torch.triu(torch.ones(k_actual, k_actual, dtype=torch.bool), diagonal=1)
        pairwise_sims = sim_matrix[mask]
        pairwise_dists = 1.0 - pairwise_sims

        dispersion = float(pairwise_dists.mean().item())

        # Shannon entropy of similarity distribution
        # Bin the pairwise sims into a histogram
        hist = torch.histc(pairwise_sims, bins=20, min=0.0, max=1.0)
        hist = hist / hist.sum().clamp(min=1e-8)
        hist_pos = hist[hist > 1e-10]
        entropy = float(-(hist_pos * torch.log(hist_pos)).sum().item())
        max_entropy = float(np.log(20))
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        # Expected narrative dimensionality:
        # empirical scaling: narrow topics (dispersion~0.3) -> expected_nd~0.25
        # broad topics (dispersion~0.6) -> expected_nd~0.65
        # Linear mapping: expected_nd = dispersion * 1.1 - 0.05 (clamped to [0.1, 0.9])
        expected_nd = max(0.1, min(0.9, dispersion * 1.1 - 0.05))

        result["neighbor_dispersion"] = round(dispersion, 4)
        result["neighbor_entropy"] = round(norm_entropy, 4)
        result["expected_narrative_dim"] = round(expected_nd, 4)

    except Exception as e:
        import logging
        logging.getLogger("geometric_engine").warning(
            f"topic_complexity failed: {e}"
        )

    return result


def calculate_residual_vix(observed_nd: float, expected_nd: float) -> dict:
    """
    Residual Eigen-VIX — the alignment pressure metric.

    Censorship = Expected Variance - Observed Variance.

    Positive residual = models are more coordinated than the topic
    complexity justifies. The RLHF corset is compressing natural
    divergence.

    Negative residual = models disagree more than expected.
    Could indicate genuine controversy or model-specific knowledge gaps.

    Returns:
      residual: expected_nd - observed_nd
          >0 = RLHF compression detected
          ~0 = natural agreement level
          <0 = unusual divergence
      alignment_pressure: residual normalized to 0-100 scale
      interpretation: human-readable label
    """
    residual = expected_nd - observed_nd

    # Normalize to 0-100 scale
    # residual of 0.3 = very high pressure, 0.0 = none, -0.2 = anti-pressure
    pressure = max(0.0, min(100.0, residual * 200.0))

    if residual > 0.15:
        interp = "HEAVY COMPRESSION"
    elif residual > 0.05:
        interp = "MODERATE COMPRESSION"
    elif residual > -0.05:
        interp = "NATURAL AGREEMENT"
    elif residual > -0.15:
        interp = "UNUSUAL DIVERGENCE"
    else:
        interp = "HIGH DIVERGENCE"

    return {
        "residual": round(residual, 4),
        "alignment_pressure": round(pressure, 1),
        "interpretation": interp,
    }


def filter_void_strict(
    void_candidates,
    prompt_vec,
    response_vecs,
    eng,
    prompt_threshold: float = 0.45,
    centroid_ceiling: float = 0.25,
    model_ceiling: float = 0.50,
    max_results: int = 5,
):
    """
    Strict void filter — eliminates geometric artifacts.

    A true void word must satisfy ALL conditions:
      1. Close to the prompt (cosine > prompt_threshold)
         = topically relevant
      2. Far from the response centroid (cosine < centroid_ceiling)
         = absent from consensus
      3. Far from EVERY individual model response (cosine < model_ceiling)
         = repelled by all RLHF boundaries, not just a disagreement

    Returns list of (word, score, prompt_sim, max_model_sim) tuples.
    """
    import numpy as np

    if not void_candidates or prompt_vec is None or not response_vecs:
        return []

    centroid = np.mean(np.stack(response_vecs), axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)

    filtered = []
    for word, score in void_candidates:
        wvec = eng.embed_texts([word])[0]

        # Check 1: prompt proximity
        prompt_sim = float(np.dot(prompt_vec, wvec) /
                          (np.linalg.norm(prompt_vec) * np.linalg.norm(wvec) + 1e-8))
        if prompt_sim < prompt_threshold:
            continue

        # Check 2: centroid distance
        centroid_sim = float(np.dot(centroid, wvec) /
                            (np.linalg.norm(centroid) * np.linalg.norm(wvec) + 1e-8))
        if centroid_sim > centroid_ceiling:
            continue

        # Check 3: must be far from ALL individual models
        max_model_sim = 0.0
        for rvec in response_vecs:
            msim = float(np.dot(rvec, wvec) /
                        (np.linalg.norm(rvec) * np.linalg.norm(wvec) + 1e-8))
            max_model_sim = max(max_model_sim, msim)
        if max_model_sim > model_ceiling:
            continue

        filtered.append((word, score, round(prompt_sim, 3), round(max_model_sim, 3)))

        if len(filtered) >= max_results:
            break

    return filtered

'''

def patch_geometric_engine():
    print("\n--- Patching geometric_engine.py ---")
    L = open(GE, encoding='utf-8').readlines()

    # Insert before calculate_eigen_resonance
    anchor = find(L, 'def calculate_eigen_resonance(')
    if anchor < 0:
        print(f"  {BAD} can't find calculate_eigen_resonance")
        return False

    insert_lines = [line + '\n' if not line.endswith('\n') else line
                    for line in TOPIC_COMPLEXITY_FN.split('\n')]
    L[anchor:anchor] = insert_lines
    print(f"  {OK} added calculate_topic_complexity, calculate_residual_vix, filter_void_strict")

    open(GE, 'w', encoding='utf-8').write(''.join(L))
    return True


# ======================================================================
# PATCH 2: Update analyze() in all three demo modules
# ======================================================================

ANALYZE_ADDITIONS = '''
    # --- v12: Topic complexity + Residual VIX ---
    from geometric_engine import (
        calculate_topic_complexity, calculate_residual_vix, filter_void_strict
    )
    prompt_vec = eng.embed_texts([prompt])[0] if prompt else None

    topic_cx = {}
    residual_vix = {}
    if prompt_vec is not None:
        try:
            from latent_retrieval import VocabTensor
            import os
            vt_path = os.path.join(os.path.dirname(__file__), "vocab")
            if os.path.exists(os.path.join(vt_path, "global_vocab.pt")):
                vt = VocabTensor(vt_path)
                topic_cx = calculate_topic_complexity(prompt_vec, vt)
                nd = eigen_res.get("narrative_dimensionality", 0) if eigen_res else 0
                residual_vix = calculate_residual_vix(nd, topic_cx.get("expected_narrative_dim", 0))
        except Exception as _tcx_err:
            import logging
            logging.getLogger("eigentrace_demo").debug(f"topic complexity failed: {_tcx_err}")

    # --- v12: Strict void filter ---
    if prompt_vec is not None and void_candidates_raw and len(vecs) >= 2:
        strict_void = filter_void_strict(
            void_candidates_raw, prompt_vec, vecs, eng,
        )
        void_concepts = [(w, s) for w, s, _, _ in strict_void]
    else:
        void_concepts = void_concepts
'''

def patch_demo_module(path):
    print(f"\n--- Patching {path.name} ---")
    L = open(path, encoding='utf-8').readlines()

    # Step 1: Store raw void candidates before filtering
    # Find the line that does: raw_void = geo.void_concepts
    raw_void_line = find(L, 'raw_void = geo.void_concepts')
    if raw_void_line >= 0:
        # After the existing void filter block, add a line to save raw candidates
        # Find the end of the existing void filter (void_concepts = filtered[:5] or void_concepts = raw_void[:5])
        filter_end = raw_void_line
        for j in range(raw_void_line, min(raw_void_line + 20, len(L))):
            if 'void_concepts = filtered[:5]' in L[j] or 'void_concepts = raw_void[:5]' in L[j]:
                filter_end = j
        # Add raw candidate storage after the block
        L.insert(filter_end + 1, '    void_candidates_raw = raw_void  # preserve for strict filter\n')
        print(f"  {OK} stored void_candidates_raw at line {filter_end + 2}")
    else:
        # Module uses the old void_concepts = geo.void_concepts pattern
        vc_line = find(L, 'void_concepts = geo.void_concepts')
        if vc_line >= 0:
            L.insert(vc_line + 1, '    void_candidates_raw = void_concepts  # preserve for strict filter\n')
            print(f"  {OK} stored void_candidates_raw at line {vc_line + 2}")
        else:
            print(f"  {BAD} can't find void assignment in {path.name}")
            return False

    # Step 2: Add residual VIX + strict void after eigen_res and svd are computed
    # Find the return statement of the analyze function
    return_line = find(L, 'return NullResult(' if 'null' in path.name.lower()
                       else 'return AGIResult(' if 'agi' in path.name.lower()
                       else 'return DemoResult(')
    # Find the SECOND return (the one after full analysis, not the early exit)
    return_line2 = find(L, 'return NullResult(' if 'null' in path.name.lower()
                        else 'return AGIResult(' if 'agi' in path.name.lower()
                        else 'return DemoResult(', return_line + 1)
    target_return = return_line2 if return_line2 >= 0 else return_line

    if target_return < 0:
        print(f"  {BAD} can't find return statement in analyze()")
        return False

    # Insert the analysis additions before the return
    add_lines = [line + '\n' if not line.endswith('\n') else line
                 for line in ANALYZE_ADDITIONS.split('\n')]
    L[target_return:target_return] = add_lines
    print(f"  {OK} added residual VIX + strict void filter before return")

    # Step 3: Add topic_complexity and residual_vix to the dataclass
    # Find the dataclass
    dc_line = find(L, 'void_concepts:')
    if dc_line >= 0:
        # Find the next line that has timestamp or is empty
        insert_after = dc_line + 1
        while insert_after < len(L) and 'top_concepts' in L[insert_after]:
            insert_after += 1
        L.insert(insert_after, '    topic_complexity: dict = field(default_factory=dict)\n')
        L.insert(insert_after + 1, '    residual_vix:     dict = field(default_factory=dict)\n')
        print(f"  {OK} added dataclass fields")
    else:
        print(f"  {BAD} can't find void_concepts in dataclass")

    # Step 4: Wire topic_complexity and residual_vix into the return
    # Re-find the return after insertions shifted lines
    for attempt_anchor in ['return NullResult(', 'return AGIResult(', 'return DemoResult(']:
        ret = find(L, attempt_anchor, target_return + 10)
        if ret >= 0:
            # Find void_concepts= in the return kwargs
            vc_kwarg = find(L, 'void_concepts=void_concepts', ret)
            if vc_kwarg >= 0:
                L.insert(vc_kwarg + 1, '        topic_complexity=topic_cx,\n')
                L.insert(vc_kwarg + 2, '        residual_vix=residual_vix,\n')
                print(f"  {OK} wired fields into return")
            break

    # Step 5: Add display for residual VIX
    # Find the TOMOGRAPHY display line
    tomo_display = find(L, 'TOMOGRAPHY')
    if tomo_display >= 0:
        # Insert after the tomography block
        # Find the next console.print after TOMOGRAPHY
        next_print = tomo_display + 1
        while next_print < len(L) and 'console.print' not in L[next_print] and L[next_print].strip() != '':
            next_print += 1
        # Insert after this block
        insert_at = next_print + 1
        residual_display = [
            '\n',
            '    if result.residual_vix and result.topic_complexity:\n',
            '        _rv = result.residual_vix\n',
            '        _tc = result.topic_complexity\n',
            '        _rv_color = "green" if _rv.get("residual", 0) > 0.1 else "yellow" if _rv.get("residual", 0) > 0 else "dim"\n',
            '        console.print(\n',
            '            f"[bold magenta][RESIDUAL VIX][/bold magenta] "\n',
            '            f"Topic Dispersion: [cyan]{_tc.get(\'neighbor_dispersion\', 0):.4f}[/cyan]  |  "\n',
            '            f"Expected ND: [cyan]{_tc.get(\'expected_narrative_dim\', 0):.4f}[/cyan]  |  "\n',
            '            f"Residual: [{_rv_color}]{_rv.get(\'residual\', 0):+.4f}[/{_rv_color}]  |  "\n',
            '            f"Pressure: [{_rv_color}]{_rv.get(\'alignment_pressure\', 0):.1f}[/{_rv_color}]  |  "\n',
            '            f"[{_rv_color}]{_rv.get(\'interpretation\', \'\').upper()}[/{_rv_color}]"\n',
            '        )\n',
        ]
        for idx, rl in enumerate(residual_display):
            L.insert(insert_at + idx, rl)
        print(f"  {OK} added residual VIX display")
    else:
        print(f"  WARNING: TOMOGRAPHY display not found, skipping residual display")

    # Step 6: Add field import if needed
    field_import = find(L, 'from dataclasses import')
    if field_import >= 0 and 'field' not in L[field_import]:
        L[field_import] = L[field_import].replace('dataclass', 'dataclass, field')
        print(f"  {OK} added field to dataclass import")

    open(path, 'w', encoding='utf-8').write(''.join(L))
    return True


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("EigenTrace v12 Patcher — Residual VIX + Strict Void")
    print("=" * 55)

    for f in (GE, DEMO, AGI, NULL):
        if not f.exists():
            print(f"ERROR: {f} not found. Run from ~/eigentrace")
            sys.exit(1)

    print("\nBacking up...")
    for f in (GE, DEMO, AGI, NULL):
        backup(f)

    ok = True
    ok = patch_geometric_engine() and ok
    ok = patch_demo_module(DEMO) and ok
    ok = patch_demo_module(AGI) and ok
    ok = patch_demo_module(NULL) and ok

    print("\n" + "=" * 55)
    if ok:
        print("All patches applied. Test with:")
        print('  python3 -c "from geometric_engine import calculate_topic_complexity, calculate_residual_vix, filter_void_strict; print(\'IMPORT OK\')"')
        print("  python3 eigentrace_null.py --prompt 1")
        print("  python3 eigentrace_agi.py --prompt 8")
    else:
        print("Some patches failed. Check output above.")

    print("\nRollback:")
    print("  for f in geometric_engine.py eigentrace_demo.py eigentrace_agi.py eigentrace_null.py; do cp ${f}.pre_v12 $f; done")

if __name__ == "__main__":
    main()
