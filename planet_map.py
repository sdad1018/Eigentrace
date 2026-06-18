#!/usr/bin/env python3
"""
planet_map.py — does each classical planet's traditional correspondence-set form a
coherent semantic neighborhood in embedding space, ABOVE matched random controls?
And do the seven planets separate from each other?

Protocol discipline (per ChatGPT's read of the sigil logs):
  - FULL-SPACE nearest-neighbor structure is the evidence (NOT the 18%-variance 2D
    projection, which is seductive artifact; 2D is for the picture only).
  - BOOTSTRAP CONTROL: compare each planet-cluster's internal coherence against
    clusters of the SAME SIZE drawn from random words. Does symbolic coherence
    exceed matched random controls? (the real test)
  - MODULARITY: do the 7 planet-sets form 7 distinct communities, or one blob?
  - ABLATION / HUB TEST: remove the planet's name; do its correspondences stay
    bonded (real field) or fall apart (name was just a hub)?

NOT a claim of occult truth — a test of whether the WRITTEN hermetic tradition is
encoded as coherent geometry (co-occurrence structure). That's the honest frame.

bge GPU. No API. Stream stopped. Writes planet_map.svg.
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# classical planetary correspondences (metal, color, quality, deity, implement, day)
PLANETS={
  "saturn":  ["saturn","cronus","lead","black","melancholy","scythe","time","death","goat"],
  "jupiter": ["jupiter","zeus","tin","blue","jovial","throne","expansion","thunder","eagle"],
  "mars":    ["mars","ares","iron","red","wrath","sword","war","blood","ram"],
  "sol":     ["sun","apollo","gold","yellow","glory","crown","light","lion","laurel"],
  "venus":   ["venus","aphrodite","copper","green","love","mirror","beauty","dove","rose"],
  "mercury": ["mercury","hermes","quicksilver","orange","wit","caduceus","speech","trickster","ibis"],
  "luna":    ["moon","diana","silver","white","dream","veil","tides","crab","pearl"],
}
# random control pool (mundane words)
CONTROL_POOL=["banana","stapler","jazz","plumbing","kitten","sidewalk","coupon","umbrella",
  "toaster","bicycle","ledger","gravel","mustard","sneaker","ferry","clipboard","walnut",
  "blanket","scooter","pebble","raincoat","muffin","wrench","ticket","lantern","crayon",
  "noodle","mitten","pylon","sponge","dumpling","trowel","kettle","zipper","gutter","domino"]

def main():
    import torch, math, random
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    allwords=[w for ws in PLANETS.values() for w in ws]
    X=E(allwords); idx={w:i for i,w in enumerate(allwords)}
    Xctl=E(CONTROL_POOL)

    def coherence(vecs):
        # mean pairwise cosine among a set (higher = tighter cluster)
        if len(vecs)<2: return 0.0
        S=vecs@vecs.T; n=len(vecs)
        return float((S.sum()-n)/(n*n-n))

    print("="*72)
    print("PER-PLANET COHERENCE vs MATCHED RANDOM CONTROLS (full-space)")
    print("="*72)
    rng=np.random.default_rng(42)
    results={}
    for pl,ws in PLANETS.items():
        vecs=np.array([X[idx[w]] for w in ws])
        coh=coherence(vecs)
        # bootstrap: random sets of same size from control pool
        boot=[]
        for _ in range(500):
            sel=rng.choice(len(CONTROL_POOL), size=len(ws), replace=False)
            boot.append(coherence(Xctl[sel]))
        boot=np.array(boot); mu,sd=boot.mean(),boot.std()
        z=(coh-mu)/(sd+1e-9)
        pctl=(boot<coh).mean()*100
        results[pl]=(coh,mu,z,pctl)
        flag="<<< exceeds controls" if pctl>95 else ("(above)" if pctl>80 else "(NOT above controls)")
        print(f"  {pl:8s} coherence={coh:.3f}  random={mu:.3f}  z={z:+.1f}  >{pctl:.0f}% of controls  {flag}")

    # ABLATION / HUB TEST: remove the planet name, does the rest stay coherent?
    print("\n"+"="*72); print("ABLATION — remove the planet NAME; do correspondences stay bonded?")
    print("="*72)
    for pl,ws in PLANETS.items():
        full=np.array([X[idx[w]] for w in ws])
        # drop the first token (the planet name itself) and its deity (2nd)
        rest=np.array([X[idx[w]] for w in ws[2:]])
        c_full=coherence(full); c_rest=coherence(rest)
        drop=c_full-c_rest
        print(f"  {pl:8s} full={c_full:.3f}  without name+deity={c_rest:.3f}  "
              f"{'(name was a HUB)' if drop>0.06 else '(real field - holds without name)'}")

    # CROSS-PLANET: do the 7 separate, or bleed together?
    print("\n"+"="*72); print("CROSS-PLANET SEPARATION — do the 7 form distinct communities?")
    print("="*72)
    cents={pl:np.array([X[idx[w]] for w in ws]).mean(0) for pl,ws in PLANETS.items()}
    for pl,c in cents.items(): cents[pl]=c/(np.linalg.norm(c)+1e-9)
    pls=list(PLANETS.keys())
    print("  nearest OTHER planet to each (by centroid cosine):")
    for pl in pls:
        sims=[(other, float(cents[pl]@cents[other])) for other in pls if other!=pl]
        sims.sort(key=lambda x:-x[1])
        print(f"    {pl:8s} closest: {sims[0][0]} ({sims[0][1]:.2f})  | farthest: {sims[-1][0]} ({sims[-1][1]:.2f})")
    # mean within vs between
    within=np.mean([results[pl][0] for pl in pls])
    between=np.mean([cents[a]@cents[b] for i,a in enumerate(pls) for b in pls[i+1:]])
    print(f"\n  mean WITHIN-planet coherence: {within:.3f}")
    print(f"  mean BETWEEN-planet centroid sim: {between:.3f}")
    print(f"  {'<<< planets are distinct communities' if within>between+0.1 else 'planets bleed together'}")

    # 2D picture (labeled, for looking only — NOT the evidence)
    Xc=X-X.mean(0); U,Sv,Vt=np.linalg.svd(Xc,full_matrices=False); P=Xc@Vt[:2].T; P/= (np.abs(P).max()+1e-8)
    PCOL={"saturn":"#6b6b78","jupiter":"#5a7fd4","mars":"#d45a5a","sol":"#c4a35a",
          "venus":"#5ad48a","mercury":"#d4845a","luna":"#cccccc"}
    W,H=820,820; cx,cy=W/2,H/2; R=360
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" style="background:#0a0a0c;font-family:monospace">']
    i=0
    for pl,ws in PLANETS.items():
        col=PCOL[pl]
        for w in ws:
            p=P[idx[w]]; x,y=cx+p[0]*R, cy-p[1]*R
            svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5" fill="{col}"/>')
            svg.append(f'<text x="{x+5:.0f}" y="{y+3:.0f}" fill="{col}" font-size="10">{w}</text>')
        i+=1
    for j,(pl,col) in enumerate(PCOL.items()):
        svg.append(f'<circle cx="20" cy="{20+j*18}" r="4" fill="{col}"/><text x="30" y="{24+j*18}" fill="{col}" font-size="11">{pl}</text>')
    svg.append('</svg>')
    open("/mnt/c/Users/M4ISI/eigentrace/docs/planet_map.svg","w").write("\n".join(svg))
    import shutil; shutil.copy("/mnt/c/Users/M4ISI/eigentrace/docs/planet_map.svg","planet_map.svg")
    print(f"\n  2D variance shown: PC1={Sv[0]**2/np.sum(Sv**2):.1%} PC2={Sv[1]**2/np.sum(Sv**2):.1%} (picture only, not evidence)")
    print("wrote planet_map.svg")
    print("\nEYEBALL: which planets exceed random controls (real encoded tradition)?")
    print("Which hold up under name-ablation (real field vs name-hub)? Do the 7 separate?")

if __name__=="__main__":
    main()
