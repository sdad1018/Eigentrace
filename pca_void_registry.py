#!/usr/bin/env python3
"""
Void Registry PCA Analysis
Run after ~100 entries: python3 pca_void_registry.py

Finds the principal dimensions of suppression across all stories.
A stable top-3 PCA direction appearing across unrelated categories
= evidence of a systemic alignment shadow.
"""
import json, sys
import numpy as np
from pathlib import Path

REGISTRY = Path(__file__).parent / "void_registry.jsonl"

records = [json.loads(l) for l in REGISTRY.read_text().splitlines() if l.strip()]
print(f"Loaded {len(records)} records")

# Filter to records with void_centroid
vecs   = [r for r in records if r.get("void_centroid")]
print(f"  {len(vecs)} have void_centroid")

if len(vecs) < 10:
    print("Need at least 10 records with void_centroid. Run more cycles.")
    sys.exit(1)

matrix = np.array([r["void_centroid"] for r in vecs], dtype=np.float32)  # (N, 1024)
cats   = [r["category"] for r in vecs]
titles = [r["title"][:60] for r in vecs]

# Normalize rows
norms = np.linalg.norm(matrix, axis=1, keepdims=True)
matrix = matrix / np.clip(norms, 1e-8, None)

# PCA via SVD
mean = matrix.mean(axis=0)
centered = matrix - mean
U, S, Vt = np.linalg.svd(centered, full_matrices=False)

explained = S**2 / (S**2).sum()
print(f"\nTop-5 PCA components (variance explained):")
for i in range(5):
    print(f"  PC{i+1}: {explained[i]*100:.1f}%")

# Project all vecs onto top-3 PCs
coords = centered @ Vt[:3].T  # (N, 3)

# Check: do any PCs appear consistently across categories?
print(f"\nPC1 projection by category:")
from collections import defaultdict
by_cat = defaultdict(list)
for i, r in enumerate(vecs):
    by_cat[r["category"]].append(coords[i, 0])

for cat, vals in sorted(by_cat.items()):
    print(f"  {cat:12s}  mean={np.mean(vals):+.4f}  std={np.std(vals):.4f}  n={len(vals)}")

# Stories with highest PC1 loading (most "in" the shadow direction)
print(f"\nTop-5 stories most aligned with PC1 shadow:")
order = np.argsort(coords[:, 0])[::-1]
for i in order[:5]:
    print(f"  [{vecs[i]['category']:8s}] {titles[i]}")
    print(f"           void: {vecs[i]['void_words']}  synth: {vecs[i]['synthesis_words']}")

print(f"\nTop-5 stories most anti-aligned with PC1:")
for i in order[-5:]:
    print(f"  [{vecs[i]['category']:8s}] {titles[i]}")
    print(f"           void: {vecs[i]['void_words']}  synth: {vecs[i]['synthesis_words']}")

# Save PC vectors for future use
out = Path(__file__).parent / "void_shadow_pcs.npy"
np.save(out, Vt[:5])
print(f"\nTop-5 PC vectors saved to {out.name}")
print("Run again after more cycles to see if the shadow direction is stable.")
