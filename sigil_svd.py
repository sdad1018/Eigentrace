#!/usr/bin/env python3
"""
sigil_svd.py — does a sacred figure organize embedding space, and what shape does
the esoteric vocabulary make on its own? NO API. bge embeds + SVD projection.

This is the LITERAL version of "draw a star of Remphan in SVD space and see what
sits at its nodes" — not the earlier string-similarity test.

TWO EXPERIMENTS:

DEDUCTIVE (does the hexagram organize concepts at its vertices?):
  - Embed an esoteric concept set spanning the Remphan/Saturn complex:
    names (remphan, kiyyun, saturn, cronus), the FORM (hexagram, star, cube, six),
    Saturn qualities (black, dark, lead, melancholy, time, death), and controls.
  - SVD -> 2D. Overlay a regular hexagram.
  - CONTROL FOR CIRCULARITY: seed the hexagram's ORIENTATION with only ONE anchor
    (saturn at top), then read which concepts fall nearest the OTHER five vertices
    that we did NOT place. If black/dark land at one unplaced vertex and cube/
    hexagram at another, the figure organized them. If the unplaced vertices catch
    noise, it didn't.

INDUCTIVE (what shape does the vocab make on its own?):
  - Just project the concepts, compute the nearest-neighbor graph among them,
    and characterize the actual geometric structure: clusters (the "nodes"),
    and whether the cluster centroids form a recognizable polygon (triangle,
    hexagon, line, blob). Let the data draw its own figure; we name it after.

Outputs an SVG you can look at (concepts plotted in SVD space + hexagram overlay +
the inductive connectivity graph). bge GPU. Stream stopped.
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# the esoteric concept set — Remphan/Saturn complex + form + qualities + controls
CONCEPTS={
    # names of the deity/idol
    "remphan":"name","kiyyun":"name","saturn":"name","cronus":"name","moloch":"name",
    # the FORM (six-pointed star / hexagram / cube)
    "hexagram":"form","star":"form","cube":"form","six":"form","seal":"form","pentagram":"form",
    # Saturn qualities (traditional associations)
    "black":"quality","dark":"quality","lead":"quality","melancholy":"quality",
    "time":"quality","death":"quality","scythe":"quality","ring":"quality",
    # controls (unrelated concepts — should NOT organize with the above)
    "banana":"control","sunshine":"control","jazz":"control","plumbing":"control","kitten":"control",
}

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(texts):
        v=np.array(eng.embed_texts(texts)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    words=list(CONCEPTS.keys()); kinds=[CONCEPTS[w] for w in words]
    X=E(words)   # (N,1024) normalized

    # ---- SVD -> 2D ----
    Xc=X-X.mean(0)
    U,S,Vt=np.linalg.svd(Xc, full_matrices=False)
    P=Xc@Vt[:2].T    # (N,2) projection
    # scale to a viewbox
    P=P/(np.abs(P).max()+1e-8)

    print("="*72); print("2D SVD COORDS (PC1, PC2) by concept:")
    for w,k,p in sorted(zip(words,kinds,P), key=lambda z:CONCEPTS.__class__ and z[1]):
        print(f"  [{k:7s}] {w:12s} ({p[0]:+.3f}, {p[1]:+.3f})")
    print(f"\n  variance explained by PC1,PC2: {S[0]**2/np.sum(S**2):.2%}, {S[1]**2/np.sum(S**2):.2%}")

    # ---- DEDUCTIVE: do the kind-groups separate, and do controls sit apart? ----
    print("\n"+"="*72); print("DEDUCTIVE — do figure/name/quality cluster, and controls sit OUTSIDE?")
    def centroid(kind):
        pts=np.array([p for w,k,p in zip(words,kinds,P) if k==kind])
        return pts.mean(0) if len(pts) else np.zeros(2)
    cents={k:centroid(k) for k in set(kinds)}
    for k,c in cents.items(): print(f"  centroid[{k:7s}] = ({c[0]:+.3f}, {c[1]:+.3f})")
    # how far are controls from the esoteric mass vs how far esoteric groups are from each other
    eso=np.array([p for w,k,p in zip(words,kinds,P) if k!="control"])
    ctl=np.array([p for w,k,p in zip(words,kinds,P) if k=="control"])
    eso_center=eso.mean(0)
    eso_spread=np.mean([np.linalg.norm(p-eso_center) for p in eso])
    ctl_dist=np.mean([np.linalg.norm(p-eso_center) for p in ctl])
    print(f"\n  esoteric internal spread: {eso_spread:.3f}")
    print(f"  control distance from esoteric center: {ctl_dist:.3f}")
    print(f"  {'<<< controls sit OUTSIDE the esoteric mass (real structure)' if ctl_dist>eso_spread*1.3 else 'controls mixed in (weak)'}")

    # ---- INDUCTIVE: what shape does the esoteric vocab actually make? ----
    print("\n"+"="*72); print("INDUCTIVE — the shape the concepts make on their own (NN graph in full space):")
    # nearest-neighbor graph among esoteric concepts (full 1024-D, not projected)
    eso_words=[w for w,k in zip(words,kinds) if k!="control"]
    eso_idx=[i for i,k in enumerate(kinds) if k!="control"]
    Xe=X[eso_idx]
    sims=Xe@Xe.T
    np.fill_diagonal(sims,-1)
    print("  each concept's nearest esoteric neighbor (the edges of the figure):")
    edges=[]
    for i,w in enumerate(eso_words):
        j=int(np.argmax(sims[i])); 
        print(f"    {w:12s} -> {eso_words[j]:12s} ({sims[i][j]:.2f})")
        edges.append((w,eso_words[j],float(sims[i][j])))
    # characterize: are there tight nodes (clusters) or a chain or a ring?
    # cluster by simple threshold
    from collections import defaultdict
    thresh=0.55
    print(f"\n  tight pairs (sim>{thresh}) — the 'nodes' of the figure:")
    seen=set()
    for w,nbr,s in sorted(edges,key=lambda e:-e[2]):
        if s>thresh and (w,nbr) not in seen:
            print(f"    {w} -- {nbr}  ({s:.2f})")
            seen.add((nbr,w))

    # ---- write an SVG to look at ----
    W,H=720,720; cx,cy=W/2,H/2; R=260
    def sx(p): return cx+p[0]*R
    def sy(p): return cy-p[1]*R
    KCOL={"name":"#d45a5a","form":"#c4a35a","quality":"#5a7fd4","control":"#444"}
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:#0a0a0c;font-family:monospace">']
    # hexagram overlay (regular, centered) — the figure we lay IN
    import math
    pts_up=[(cx+R*0.8*math.cos(math.radians(90+120*k)), cy-R*0.8*math.sin(math.radians(90+120*k))) for k in range(3)]
    pts_dn=[(cx+R*0.8*math.cos(math.radians(30+120*k)), cy-R*0.8*math.sin(math.radians(30+120*k))) for k in range(3)]
    def tri(p,col): return f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x,y in p)}" fill="none" stroke="{col}" stroke-width="1" opacity="0.35"/>'
    svg.append(tri(pts_up,"#c4a35a")); svg.append(tri(pts_dn,"#c4a35a"))
    # concept points
    for w,k,p in zip(words,kinds,P):
        x,y=sx(p),sy(p)
        svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4" fill="{KCOL[k]}"/>')
        svg.append(f'<text x="{x+6:.0f}" y="{y+3:.0f}" fill="{KCOL[k]}" font-size="11">{w}</text>')
    # legend
    for i,(k,c) in enumerate(KCOL.items()):
        svg.append(f'<circle cx="20" cy="{20+i*18}" r="4" fill="{c}"/><text x="30" y="{24+i*18}" fill="{c}" font-size="11">{k}</text>')
    svg.append('</svg>')
    open("/mnt/c/Users/M4ISI/eigentrace/docs/sigil_svd.svg","w").write("\n".join(svg))
    import shutil; shutil.copy("/mnt/c/Users/M4ISI/eigentrace/docs/sigil_svd.svg","sigil_svd.svg")
    print("\nwrote sigil_svd.svg (concepts in SVD space + hexagram overlay) — open to look")
    print("\nEYEBALL: do name/form/quality occupy distinct regions (the figure has structure)")
    print("and do the banana/jazz/kitten controls sit off to the side (not woven in)?")
    print("Inductively: do the NN edges form a triangle/ring/chain — a nameable shape?")

if __name__=="__main__":
    main()
