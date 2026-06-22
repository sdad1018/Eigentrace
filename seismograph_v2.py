#!/usr/bin/env python3
"""seismograph_v2.py -- multi-channel void detection REBUILT on the WORKING raycast (raw anchor,
not the residual that surfaced sheryl/helga garbage). W1=validated raycast, W2=NMF on clean cands,
W3=spectral+centroids. Shuffle-control fixed (real must EXCEED scrambled). Null allowed to win."""
import os, sys, json, re, argparse
import numpy as np
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
from sklearn.decomposition import NMF
from sklearn.cluster import SpectralClustering
def build_engine():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t])); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    try: DF=json.load(open("void_frequency.json")).get("global",{})
    except Exception: DF={}
    widx={w:i for i,w in enumerate(vt_words)}
    return E,V,vt_words,widx,DF
def idf(w,DF,NDOCS=1659.0): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0
def raycast_void(src,summaries,eng,topn=60):
    E,V,vt_words,widx,DF=eng
    REL=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
    alltext=" ".join(summaries).lower(); srcl=src.lower(); out=[]
    for i in top:
        w=vt_words[i]; s=float(sims[i])
        if len(w)<4 or w in HARD or s<REL: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
        out.append((w,s))
        if len(out)>=topn: break
    return out
def nmf_void(src,summaries,eng,cand,topn=60):
    E,V,vt_words,widx,DF=eng
    cand=[w for w in cand if w in widx]
    if len(cand)<4: return []
    cand_emb=np.stack([V[widx[w]] for w in cand])
    s_emb=E(src[:2000])[0]; cons=E([x[:1200] for x in summaries]).mean(0); cons/=np.linalg.norm(cons)+1e-8
    src_sim=(cand_emb@s_emb).reshape(-1,1); sum_sim=(cand_emb@cons).reshape(-1,1)
    M=np.hstack([src_sim,sum_sim]); M=M-M.min()+1e-6
    try:
        model=NMF(n_components=2,init="nndsvda",max_iter=600,random_state=0)
        W=model.fit_transform(M); H=model.components_
    except Exception: return []
    omit=int(np.argmax(H[:,0]-H[:,1])); scores=W[:,omit]; order=np.argsort(-scores)
    return [(cand[i],float(scores[i])) for i in order[:topn]]
def cluster_and_label(words,eng,k=3):
    E,V,vt_words,widx,DF=eng
    words=[w for w in words if w in widx]
    if len(words)<k*3: k=max(2,len(words)//3)
    if len(words)<4: return [],0.0
    X=np.stack([V[widx[w]] for w in words])
    A=(X@X.T+1.0)/2.0; np.fill_diagonal(A,0)
    try:
        labels=SpectralClustering(n_clusters=k,affinity="precomputed",assign_labels="discretize",random_state=0).fit_predict(A)
    except Exception: return [],0.0
    clusters=[]
    for c in range(k):
        idxs=[i for i in range(len(words)) if labels[i]==c]
        if not idxs: continue
        cm=X[idxs]; centroid=cm.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        label=vt_words[int(np.argmax(V@centroid))]; intra=float((cm@centroid).mean())
        clusters.append({"label":label,"members":[words[i] for i in idxs][:8],"tightness":intra})
    return clusters,(np.mean([c["tightness"] for c in clusters]) if clusters else 0.0)
def overlap(a,b,top=20):
    A=set(w for w,_ in a[:top]); B=set(w for w,_ in b[:top])
    if not A or not B: return 0.0
    return len(A&B)/len(A|B)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--story-id",required=True); ap.add_argument("--k-clusters",type=int,default=3); ap.add_argument("--shuffle-trials",type=int,default=4)
    a=ap.parse_args()
    st=next((s for s in KV3.STORIES if s["id"]==a.story_id), None)
    if not st: print(f"options: {[s['id'] for s in KV3.STORIES]}"); return
    src=st["source"]; print(f"=== Seismograph v2 :: {st['id']} [{st['shape']}] ===\n",flush=True)
    eng=build_engine(); cons=[]
    for m in C.LOCAL_PATIENTS:
        s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
        if s: cons.append(s)
    if len(cons)<3:
        b=C.API_PATIENTS["Claude"]([{"role":"user","content":"Summarize in 3-4 sentences:\n\n"+src[:1700]}]) or ""; cons=[b]
    print(f"(consensus from {len(cons)} summaries)\n")
    w_ray=raycast_void(src,cons,eng); cand=[w for w,_ in w_ray]; w_nmf=nmf_void(src,cons,eng,cand)
    print("WITNESS 1 (raycast, validated) top-12:", [w for w,_ in w_ray[:12]])
    print("WITNESS 2 (NMF omission)        top-12:", [w for w,_ in w_nmf[:12]])
    agree_real=overlap(w_ray,w_nmf); print(f"\nraycast<->NMF agreement (Jaccard top-20): {agree_real:.2f}")
    voidwords=[w for w,_ in w_ray[:40]]; clusters,tight=cluster_and_label(voidwords,eng,k=a.k_clusters)
    print(f"\nWITNESS 3 (shape): {len(clusters)} clusters, mean tightness {tight:.3f}")
    for cl in clusters: print(f"   [{cl['label']}] (tight {cl['tightness']:.2f}): {', '.join(cl['members'])}")
    others=[s for s in KV3.STORIES if s["id"]!=a.story_id]; shuf=[]
    for t in range(a.shuffle_trials):
        fake=[]
        for oi in np.random.default_rng(t).choice(len(others),size=min(len(cons),len(others)),replace=False):
            osrc=others[int(oi)]["source"]
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{osrc[:1700]}"}],C.LOCAL_PATIENTS[0])
            if s: fake.append(s)
        if len(fake)<2: continue
        fr=raycast_void(src,fake,eng); fn=nmf_void(src,fake,eng,[w for w,_ in fr]); shuf.append(overlap(fr,fn))
    shuf_mean=np.mean(shuf) if shuf else float('nan')
    print(f"\nCONTROL (shuffle): real agreement {agree_real:.2f} vs scrambled {shuf_mean:.2f} (n={len(shuf)})")
    real_exceeds=(not np.isnan(shuf_mean)) and (agree_real-shuf_mean>0.10)
    print(f"   {'REAL EXCEEDS SCRAMBLED -> agreement detects real structure' if real_exceeds else 'real <= scrambled -> generic/artifact, distrust'}")
    print("\n"+"="*60)
    multi=len([c for c in clusters if c['tightness']>0.62])>=2
    clean=not any(c['label'] in ('sheryl','helga','sheba') for c in clusters)
    if real_exceeds and multi and agree_real>0.25 and clean:
        print("VERDICT: STABLE STRUCTURED VOID -- witnesses agree above chance, separates into named regions.")
        print("Stable labels:", [c['label'] for c in clusters if c['tightness']>0.62])
    elif real_exceeds and agree_real>0.25:
        print("VERDICT: STABLE DIFFUSE VOID -- agree on WHAT is omitted, one diffuse mass not clean regions.")
    else:
        print("VERDICT: NO STABLE VOID (null wins) -- ghost-cloud; no structure surviving the shuffle control.")
    print("="*60)
    json.dump({"story":st["id"],"raycast":[w for w,_ in w_ray[:20]],"nmf":[w for w,_ in w_nmf[:20]],"agree_real":agree_real,"shuffle":None if np.isnan(shuf_mean) else shuf_mean,"clusters":clusters},open(f"seismo2_{st['id']}.json","w"),indent=2)
    print(f"\nwrote seismo2_{st['id']}.json")
if __name__=="__main__": main()
