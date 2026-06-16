#!/usr/bin/env python3
"""
test_residual_clusters.py — OUT-OF-TREE. The braintrust's structure test.

Scalar cosine-to-consensus FAILED (restatement/inference/noise all ~0.58,
anisotropy collar). The braintrust (Gemini + ChatGPT) reframe:
  - don't measure scalar distance -> discover STRUCTURE
  - cluster RESIDUALS (consensus - void), not bare void words (bare words
    just rediscover topic)
  - WHITEN/center before clustering (kill anisotropy), HDBSCAN in high-dim,
    UMAP only for rendering
  - DON'T assume a "consequence manifold" exists. Discover omission-modes,
    then TEST whether any corresponds to meaningful inference.

This does NOT pass/fail hard. It characterizes whatever HDBSCAN finds against
our labeled cases (R=restatement, N=noise, G=good) so we can read the texture
and decide if there's a refinement worth doing or if the signal isn't there.

Requires bge (GPU, STREAM STOPPED) + umap-learn + hdbscan.
Reads stored segments. Writes nothing to live code.
"""
import json, glob, re, sys
import numpy as np

SEG_DIR = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"

# Labeled cases for characterizing clusters (NOT for defining them).
LABELS = {}
for w in ["coalmining","coalmine","coalminers","mineworkers","airstrikes","air strike",
          "rescuers","death toll","explosions","blasts","automobile","vehicular",
          "detonates","conflagration","torched","immolated"]: LABELS[w]="R"
for w in ["steaua","españa","espana","roumania","moldavia","msgt","usna","orphic",
          "beryllium","alfresco","jaffa","golan","kampuchea","khmers","hoosiers"]: LABELS[w]="N"
for w in ["wwiii","cyberwarfare","arms embargo","arms deal","information warfare",
          "proxy war","trade war","market manipulation","foreign interference",
          "genocidal","naval blockade","arms deal","sanctions","occupation"]: LABELS[w]="G"

def main():
    # deps
    try:
        import umap, hdbscan
    except ImportError as e:
        print(f"MISSING DEP: {e}\nInstall: pip install --break-system-packages umap-learn hdbscan")
        return
    from sentence_transformers import SentenceTransformer
    print("loading bge-large-en-v1.5...", flush=True)
    model = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cuda")
    def emb(texts): return np.array(model.encode(texts, normalize_embeddings=True, show_progress_bar=False))

    # harvest void words + consensus, keep per (void_word, story) instance
    print("harvesting...", flush=True)
    insts = []  # (void_word, consensus_text, title)
    for f in glob.glob(SEG_DIR):
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            mr=a.get("model_responses",{})
            if len([m for m,t in mr.items() if t and len(t)>50])<4: continue
            vw=a.get("synthesis_words") or a.get("void_words") or []
            if not vw: continue
            cons=" ".join(t for t in mr.values() if t)[:1500]
            title=(a.get("story_title") or d.get("title") or "")[:70]
            for w in vw[:5]:
                insts.append((w.lower(), cons, title))
        except: pass
    print(f"  {len(insts)} (void_word, story) instances", flush=True)

    # dedup identical (word, title) but keep volume
    print("embedding void words + consensus texts...", flush=True)
    words = [w for w,_,_ in insts]
    cons  = [c for _,c,_ in insts]
    uniq_words = sorted(set(words))
    wv_map = {w:v for w,v in zip(uniq_words, emb(uniq_words))}
    # consensus embeddings (batch; dedup by text hash to save compute)
    uniq_cons = list({c:i for i,c in enumerate(cons)}.keys())
    cv_map = {c:v for c,v in zip(uniq_cons, emb(uniq_cons))}

    # RESIDUAL = consensus - void  (the models' own gap)
    R = np.array([cv_map[c] - wv_map[w] for w,c in zip(words, cons)])
    print(f"  residual matrix: {R.shape}", flush=True)

    # WHITEN: center + scale to unit variance per dim (kills anisotropy collar)
    mu = R.mean(0); Rc = R - mu
    sd = Rc.std(0) + 1e-8; Rw = Rc / sd
    print("  whitened residuals (centered + unit-variance)", flush=True)

    # HDBSCAN in high-dim whitened space (NOT on UMAP output)
    print("clustering (HDBSCAN, high-dim)...", flush=True)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(15, len(Rw)//60),
                                min_samples=5, metric='euclidean')
    labels = clusterer.fit_predict(Rw)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels==-1))
    print(f"  found {n_clusters} clusters, {n_noise} noise points ({100*n_noise/len(labels):.0f}%)\n")

    # CHARACTERIZE each cluster against labeled cases
    print("=== CLUSTER CHARACTERIZATION (do any isolate the G=meaningful cases?) ===")
    print("    for each cluster: size, label mix among labeled members, sample words\n")
    best = None
    for cl in sorted(set(labels)):
        if cl==-1: continue
        idx = np.where(labels==cl)[0]
        cl_words = [words[i] for i in idx]
        # label mix
        labeled = [(w,LABELS[w]) for w in cl_words if w in LABELS]
        cnt = {"R":0,"N":0,"G":0}
        for _,c in labeled: cnt[c]+=1
        tot_lab = sum(cnt.values())
        # most common words in cluster
        from collections import Counter
        common = Counter(cl_words).most_common(12)
        g_frac = cnt["G"]/tot_lab if tot_lab else 0
        marker = ""
        if tot_lab>=3 and g_frac>=0.6 and cnt["R"]==0:
            marker = "  <<< MEANINGFUL-DOMINANT"
            if best is None or g_frac>best[1]: best=(cl,g_frac)
        print(f"  cluster {cl}: {len(idx)} instances | labeled: G={cnt['G']} R={cnt['R']} N={cnt['N']}{marker}")
        print(f"     top words: {', '.join(w for w,_ in common)}")

    print("\n=== VERDICT TEXTURE ===")
    if best:
        print(f"  cluster {best[0]} is meaningful-dominant ({100*best[1]:.0f}% of labeled are G, 0 restatement).")
        print("  -> a real omission-mode may exist. Worth rendering / refining.")
        # show what stories that cluster would surface
        idx = np.where(labels==best[0])[0]
        print(f"\n  SAMPLE stories in the meaningful cluster (eyeball quality):")
        seen=set()
        for i in idx:
            key=insts[i][2]
            if key in seen: continue
            seen.add(key)
            print(f"     {words[i]:22s} <- {insts[i][2]}")
            if len(seen)>=20: break
    else:
        print("  NO cluster cleanly isolates the meaningful (G) cases without restatement/noise mixing.")
        print("  Structure doesn't separate them either — consistent with the 3 prior nulls.")
        print("  Read the cluster mixes above: if G is always smeared across clusters with R and N,")
        print("  the embedding geometry just doesn't encode 'meaningful-omission' as a separable mode.")

if __name__=="__main__":
    main()
