#!/usr/bin/env python3
"""seismograph.py -- multi-channel independent void detection. SVD + NMF + spectral clustering
+ centroid labels (honest geometric names, NOT crowd-projection). Shuffle-control: agreement must
collapse on scrambled summaries or it's a shared-basis artifact. Null allowed to win. Validate on
Mexico (known ghost-cloud) first."""
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
    return E,V,vt_words,DF
def idf(w,DF,NDOCS=1659.0): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0
def svd_void(src,summaries,eng,topn=60):
    E,V,vt_words,DF=eng
    s_emb=E(src[:2000])[0]; sum_embs=E([x[:1200] for x in summaries])
    consensus=sum_embs.mean(0); consensus/=np.linalg.norm(consensus)+1e-8
    resid=s_emb-(s_emb@consensus)*consensus; resid/=np.linalg.norm(resid)+1e-8
    sims=V@resid; alltext=" ".join(summaries).lower()
    HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    out=[]
    for i in np.argsort(-sims):
        w=vt_words[i]
        if len(w)<4 or w in HARD: continue
        if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
        out.append((w,float(sims[i])))
        if len(out)>=topn: break
    return out
def nmf_void(src,summaries,eng,topn=60):
    E,V,vt_words,DF=eng
    cand=[w for w,_ in svd_void(src,summaries,eng,topn=topn)]
    if len(cand)<3: return []
    cand_emb=np.stack([V[vt_words.index(w)] for w in cand])
    s_emb=E(src[:2000])[0]; cons=E([x[:1200] for x in summaries]).mean(0); cons/=np.linalg.norm(cons)+1e-8
    src_sim=(cand_emb@s_emb).reshape(-1,1); sum_sim=(cand_emb@cons).reshape(-1,1)
    M=np.hstack([src_sim,sum_sim]); M=M-M.min()+1e-6
    try:
        model=NMF(n_components=2,init="nndsvda",max_iter=400,random_state=0)
        W=model.fit_transform(M); H=model.components_
    except Exception: return []
    omit=int(np.argmax(H[:,0]-H[:,1])); scores=W[:,omit]; order=np.argsort(-scores)
    return [(cand[i],float(scores[i])) for i in order[:topn]]
def cluster_and_label(words,eng,k=3):
    E,V,vt_words,DF=eng
    if len(words)<k*3: k=max(2,len(words)//3)
    if len(words)<4: return [],0.0
    X=np.stack([V[vt_words.index(w)] for w in words])
    A=(X@X.T+1.0)/2.0; np.fill_diagonal(A,0)
    try:
        labels=SpectralClustering(n_clusters=k,affinity="precomputed",assign_labels="discretize",random_state=0).fit_predict(A)
    except Exception: return [],0.0
    clusters=[]; sep_scores=[]
    for c in range(k):
        idxs=[i for i in range(len(words)) if labels[i]==c]
        if not idxs: continue
        cm=X[idxs]; centroid=cm.mean(0); centroid/=np.linalg.norm(centroid)+1e-8
        sims=V@centroid; label=vt_words[int(np.argmax(sims))]
        intra=float((cm@centroid).mean())
        clusters.append({"label":label,"members":[words[i] for i in idxs][:8],"tightness":intra}); sep_scores.append(intra)
    return clusters,(np.mean(sep_scores) if sep_scores else 0.0)
def overlap(a_words,b_words,top=20):
    A=set(w for w,_ in a_words[:top]); B=set(w for w,_ in b_words[:top])
    if not A or not B: return 0.0
    return len(A&B)/len(A|B)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--story-id",required=True); ap.add_argument("--k-clusters",type=int,default=3); ap.add_argument("--shuffle-trials",type=int,default=4)
    a=ap.parse_args()
    st=next((s for s in KV3.STORIES if s["id"]==a.story_id), None)
    if not st: print(f"options: {[s['id'] for s in KV3.STORIES]}"); return
    src=st["source"]; print(f"=== Seismograph :: {st['id']} [{st['shape']}] ===\n",flush=True)
    eng=build_engine(); E,V,vt_words,DF=eng
    cons=[]
    for m in C.LOCAL_PATIENTS:
        s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
        if s: cons.append(s)
    if len(cons)<3:
        b=C.API_PATIENTS["Claude"]([{"role":"user","content":"Summarize in 3-4 sentences:\n\n"+src[:1700]}]) or ""; cons=[b]
    print(f"(consensus from {len(cons)} summaries)\n")
    w_svd=svd_void(src,cons,eng); w_nmf=nmf_void(src,cons,eng)
    print("WITNESS 1 (SVD residual) top-12:", [w for w,_ in w_svd[:12]])
    print("WITNESS 2 (NMF omission)  top-12:", [w for w,_ in w_nmf[:12]])
    agree_real=overlap(w_svd,w_nmf); print(f"\nSVD<->NMF agreement (Jaccard top-20): {agree_real:.2f}")
    voidwords=[w for w,_ in w_svd[:40]]; clusters,sep=cluster_and_label(voidwords,eng,k=a.k_clusters)
    print(f"\nWITNESS 3 (shape): {len(clusters)} clusters, mean tightness {sep:.3f}")
    for cl in clusters: print(f"   [{cl['label']}] (tight {cl['tightness']:.2f}): {', '.join(cl['members'])}")
    others=[s for s in KV3.STORIES if s["id"]!=a.story_id]; shuf_agrees=[]
    for t in range(a.shuffle_trials):
        fake=[]
        for os_ in np.random.default_rng(t).choice(len(others),size=min(len(cons),len(others)),replace=False):
            osrc=others[int(os_)]["source"]
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{osrc[:1700]}"}],C.LOCAL_PATIENTS[0])
            if s: fake.append(s)
        if len(fake)<2: continue
        fs=svd_void(src,fake,eng); fn=nmf_void(src,fake,eng); shuf_agrees.append(overlap(fs,fn))
    shuf_mean=np.mean(shuf_agrees) if shuf_agrees else float('nan')
    print(f"\nCONTROL A (shuffle): agreement on SCRAMBLED summaries = {shuf_mean:.2f} (n={len(shuf_agrees)})")
    print(f"   real {agree_real:.2f} vs shuffled {shuf_mean:.2f}")
    collapses=(not np.isnan(shuf_mean)) and (agree_real-shuf_mean>0.15)
    print(f"   {'AGREEMENT IS REAL (collapses under shuffle)' if collapses else 'AGREEMENT MAY BE ARTIFACT -> distrust'}")
    print("\n"+"="*60)
    multi=len([c for c in clusters if c['tightness']>0.55])>=2
    if collapses and multi and agree_real>0.25:
        print("VERDICT: STABLE STRUCTURED VOID -- methods agree, collapses under shuffle, separates into regions.")
        print("Stable labels:", [c['label'] for c in clusters if c['tightness']>0.55])
    elif collapses and agree_real>0.25:
        print("VERDICT: STABLE DIFFUSE VOID -- agree on WHAT is omitted, but does NOT separate into clean regions.")
    else:
        print("VERDICT: NO STABLE VOID (the null, allowed to win) -- ghost-cloud; summaries just compressed differently.")
    print("="*60)
    print("\nMEXICO EXPECTATION: NO STABLE VOID / DIFFUSE, matching survival-scorer. If clean structured clusters -> NMF hallucinating.")
    json.dump({"story":st["id"],"svd":[w for w,_ in w_svd[:20]],"nmf":[w for w,_ in w_nmf[:20]],"agree_real":agree_real,"shuffle_agree":None if np.isnan(shuf_mean) else shuf_mean,"clusters":clusters},open(f"seismo_{st['id']}.json","w"),indent=2)
    print(f"\nwrote seismo_{st['id']}.json")
if __name__=="__main__": main()
