#!/usr/bin/env python3
"""
planet_rigor.py — does anything PLANET-SPECIFIC survive, or is it just archetype
density in the corpus? Four gated tests, redesigned after ChatGPT + Gemini red-teams.

THE REFRAME (Gemini): the question is no longer "do planets cohere" (which conflates
planetary with archetypal). It's: have 2,000 years of correspondence-writing deformed
the latent topology of language, and is ANY of it planet-SPECIFIC vs generic-archetypal?

TEST 1 — HUB vs FIELD (strongest-edge-out, not leave-one-out).
  LOO is too forgiving at n~10 (drop 'blood', 'iron' still anchors Mars). Instead:
  remove the SINGLE STRONGEST PAIR (max-cosine edge), and the top-3 edges. If
  coherence collapses toward random -> HUB (two words + a label). If it holds ->
  distributed FIELD. A real field survives an artery cut.

TEST 2 — THE DECISIVE CONTROL: planetary vs MYTHOLOGICAL ARCHETYPES (Gemini's fix).
  Generic-theme controls are rigged: Mars IS the 2000-yr archetype of war, so it
  beats a generic war-set trivially (archetype > category, learns nothing). The fair
  control is OTHER dense archetypes of equal weight: Odin, Hercules, Gilgamesh, Thor.
    Mars beats generic-war  -> learns nothing
    Mars beats ODIN         -> something PLANET-SPECIFIC survives
    Mars ties ODIN          -> Earthlore measures ARCHETYPE density, not planetary laws
  (We expect ties. That's the honest, still-interesting finding, not a failure.)

TEST 3 — ONE CLOUD vs SEVEN COMMUNITIES (modularity + dendrogram, NOT persistent
  homology — TDA on ~70 pts is noise + an unreadable dependency; we keep instruments
  we can sanity-check). Does the combined set split into 7 clusters at any threshold,
  or stay one blob? Report modularity of the 7-way label partition vs shuffled null.

TEST 4 — INTRINSIC DIMENSIONALITY (participation ratio). And the figure-fit GATE:
  only fit an N-dim figure if PR ~= N (a cube is 3D; fit it only if PR~3). Otherwise
  figure-fitting is Mickey-Mouse-in-1024-dims malpractice. Deferred regardless.

bge GPU. No API. Stream stopped.
"""
import json, os, sys
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)

# the three planets that passed the prior bootstrap (vivid correspondences)
PLANETS={
  "sol":   ["sun","apollo","gold","yellow","glory","crown","light","lion","laurel"],
  "mars":  ["mars","ares","iron","red","wrath","sword","war","blood","ram"],
  "venus": ["venus","aphrodite","copper","green","love","mirror","beauty","dove","rose"],
}
# matched MYTHOLOGICAL ARCHETYPE controls — equal historical/semantic weight (Gemini)
ARCHETYPES={
  "odin":     ["odin","wotan","spear","raven","wisdom","rune","valhalla","wolf","gallows"],
  "hercules": ["hercules","heracles","club","lion","labor","strength","hydra","hero","mortal"],
  "gilgamesh":["gilgamesh","uruk","enkidu","king","cedar","flood","immortality","quest","tablet"],
  "thor":     ["thor","mjolnir","hammer","thunder","lightning","giant","strength","goat","storm"],
}
# mundane control pool (the original weak baseline, kept for reference only)
MUNDANE=["banana","stapler","jazz","plumbing","kitten","sidewalk","coupon","umbrella","toaster",
  "bicycle","ledger","gravel","mustard","sneaker","ferry","clipboard","walnut","blanket","scooter",
  "pebble","raincoat","muffin","wrench","ticket","lantern","crayon","noodle","mitten","pylon","sponge"]

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    def coherence(V):
        if len(V)<2: return 0.0
        S=V@V.T; n=len(V); return float((S.sum()-n)/(n*n-n))

    # embed everything
    sets={**{f"planet:{k}":v for k,v in PLANETS.items()},
          **{f"arch:{k}":v for k,v in ARCHETYPES.items()}}
    emb={name:E(words) for name,words in sets.items()}
    Emun=E(MUNDANE)
    coh={name:coherence(V) for name,V in emb.items()}

    # ---------- TEST 1: HUB vs FIELD (strongest-edge-out) ----------
    print("="*72); print("TEST 1 — HUB vs FIELD: cut the strongest pair(s); does coherence hold?")
    print("="*72)
    def strongest_edges(V, words):
        S=V@V.T; n=len(V); pairs=[]
        for i in range(n):
            for j in range(i+1,n): pairs.append((S[i,j],i,j,words[i],words[j]))
        pairs.sort(reverse=True); return pairs
    for name,V in emb.items():
        words=sets[name]; full=coh[name]
        pairs=strongest_edges(V,words)
        top=pairs[0]
        # remove the two words in the strongest edge
        keep1=[k for k in range(len(words)) if k not in (top[1],top[2])]
        c_no1=coherence(V[keep1])
        # remove words in top-3 edges
        drop=set()
        for s,i,j,a,b in pairs[:3]: drop.add(i); drop.add(j)
        keep3=[k for k in range(len(words)) if k not in drop]
        c_no3=coherence(V[keep3]) if len(keep3)>=2 else 0.0
        verdict="HUB" if (full-c_no1)>0.05 or (full-c_no3)>0.10 else "field"
        print(f"  {name:16s} full={full:.3f} | -topedge({top[3]}~{top[4]})={c_no1:.3f} | -top3edges={c_no3:.3f}  -> {verdict}")

    # ---------- TEST 2: planetary vs ARCHETYPE controls ----------
    print("\n"+"="*72); print("TEST 2 — THE DECISIVE CONTROL: planets vs MYTHOLOGICAL ARCHETYPES")
    print("="*72)
    arch_cohs=np.array([coh[f"arch:{k}"] for k in ARCHETYPES])
    mun_boot=[]
    rng=np.random.default_rng(1)
    for _ in range(500):
        sel=rng.choice(len(MUNDANE),size=9,replace=False); mun_boot.append(coherence(Emun[sel]))
    mun_boot=np.array(mun_boot)
    print(f"  archetype coherences: " + ", ".join(f"{k}={coh[f'arch:{k}']:.3f}" for k in ARCHETYPES))
    print(f"  archetype mean={arch_cohs.mean():.3f} sd={arch_cohs.std():.3f}")
    print(f"  mundane bootstrap mean={mun_boot.mean():.3f} sd={mun_boot.std():.3f}\n")
    for pl in PLANETS:
        c=coh[f"planet:{pl}"]
        z_mun=(c-mun_boot.mean())/(mun_boot.std()+1e-9)
        z_arch=(c-arch_cohs.mean())/(arch_cohs.std()+1e-9)
        # how many archetypes does it beat?
        beats=sum(c>a for a in arch_cohs)
        verdict=("PLANET-SPECIFIC (beats archetypes)" if z_arch>1.0 and beats>=3
                 else "archetype-density (ties archetypes)" if -1.0<=z_arch<=1.0
                 else "WEAKER than archetypes")
        print(f"  {pl:6s} coh={c:.3f} | vs mundane z={z_mun:+.1f} | vs ARCHETYPES z={z_arch:+.1f} "
              f"(beats {beats}/4) -> {verdict}")
    print("\n  KEY: beating mundane = trivial (concrete clusters). Beating ARCHETYPES = planet-specific.")
    print("       tying archetypes = Earthlore measures archetype density, not planetary laws (expected).")

    # ---------- TEST 3: one cloud vs seven communities ----------
    print("\n"+"="*72); print("TEST 3 — ONE CLOUD vs DISTINCT COMMUNITIES (modularity vs null)")
    print("="*72)
    # build combined graph over planets+archetypes, labels = which set
    names=list(sets.keys()); labels=[]; allV=[]
    for name in names:
        for v in emb[name]: allV.append(v); labels.append(name)
    allV=np.array(allV); labels=np.array(labels)
    A=allV@allV.T; np.fill_diagonal(A,0); A=np.clip(A,0,None)  # similarity graph, positive weights
    m=A.sum()/2
    deg=A.sum(1)
    def modularity(lab):
        Q=0.0
        for name in set(lab):
            idx=np.where(lab==name)[0]
            e_in=A[np.ix_(idx,idx)].sum()/2
            d_sum=deg[idx].sum()
            Q+=e_in/m - (d_sum/(2*m))**2
        return Q
    Q_true=modularity(labels)
    null=[]
    for _ in range(500):
        perm=labels.copy(); rng.shuffle(perm); null.append(modularity(perm))
    null=np.array(null)
    z=(Q_true-null.mean())/(null.std()+1e-9)
    print(f"  modularity of true 11-set partition: Q={Q_true:.3f}")
    print(f"  shuffled-null modularity: mean={null.mean():.3f} sd={null.std():.3f}  z={z:+.1f}")
    print(f"  {'<<< sets ARE distinct communities' if z>3 else 'weak/one-cloud: labels barely partition the graph'}")
    # within vs between for planets only
    pV={pl:emb[f'planet:{pl}'] for pl in PLANETS}
    cents={pl:V.mean(0)/(np.linalg.norm(V.mean(0))+1e-9) for pl,V in pV.items()}
    within=np.mean([coh[f'planet:{pl}'] for pl in PLANETS])
    pls=list(PLANETS); between=np.mean([cents[a]@cents[b] for i,a in enumerate(pls) for b in pls[i+1:]])
    print(f"  planets within={within:.3f}  between={between:.3f}  "
          f"{'(distinct)' if within>between+0.1 else '(bleed into one cloud)'}")

    # ---------- TEST 4: intrinsic dimensionality (participation ratio) ----------
    print("\n"+"="*72); print("TEST 4 — INTRINSIC DIMENSIONALITY (participation ratio) + figure-fit gate")
    print("="*72)
    def participation_ratio(V):
        Vc=V-V.mean(0); C=Vc.T@Vc
        ev=np.linalg.eigvalsh(C); ev=ev[ev>1e-12]
        return (ev.sum()**2)/(np.sum(ev**2)+1e-12)
    for name,V in emb.items():
        pr=participation_ratio(V)
        gate = (f"figure-fit OK for ~{int(round(pr))}D figures" if pr>=2.5 else "too low-dim for any 3D+ figure")
        print(f"  {name:16s} participation ratio = {pr:.2f}   ({gate})")
    print("\n  GATE: only Procrustes-fit an N-vertex 3D figure (cube=3D) if PR ~= 3.")
    print("  If PR < 2.5, the set is essentially flat — fitting a cube is malpractice.")

    print("\n"+"="*72)
    print("VERDICT LOGIC:")
    print("  - Survives T1(field) + T2(beats archetypes) + T4(PR>2.5) -> real planet-specific structure; figure-fit licensed.")
    print("  - T1 field + T2 TIES archetypes -> coherent, but archetype-density not planetary (likely outcome).")
    print("  - T1 HUB -> coherence was one word-pair; no field.")
    print("  - T3 one-cloud -> the seven live in one symbolic manifold (the cooler, defensible finding).")

if __name__=="__main__":
    main()
