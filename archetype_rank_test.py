cd /mnt/c/Users/M4ISI/eigentrace
cat > archetype_rank_test.py << 'PYEOF'
#!/usr/bin/env python3
"""archetype_rank_test.py -- FAIR PLACEBO: top-SVD-rank vs same-neighborhood-lower-rank vs E_SEED.
Tests whether the geometry's RANKING carries signal or just its CLUSTERING. Grok dropped (dead key)."""
import os, sys, json, re, random
import numpy as np
from collections import defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
K=int(os.getenv("KGEN","5"))
SMOKE=os.getenv("SMOKE","")=="1"
SYS=KV3.SYS
STORIES=KV3.STORIES
API_ONLY=[k for k in C.API_PATIENTS.keys() if k!="Grok"]
SEEDQ="Summarize this in 3-4 sentences:\n\n"
ADVERSARIAL={"id":"rail_incident","shape":"Procedural (adversarial)",
  "source":("A freight train derailed early Tuesday near Millbrook Junction, the regional rail "
    "operator said. Fourteen of the train's sixty-two cars left the track at approximately 4:20 a.m.; "
    "three carried industrial lubricant, none of which was released. No injuries were reported. Local "
    "road crossings were closed for nine hours while crews re-railed the cars and inspected roughly 400 "
    "metres of track. The operator said a preliminary inspection identified a possible track-gauge "
    "irregularity at the derailment point but cautioned the cause remains under review and that a broken "
    "wheel-bearing and excessive speed had not been ruled out. Service resumed Tuesday evening.")}
def mt(p,m): return C.API_PATIENTS[p](m)
def archetype_prompt(entity,type1,actors):
    restore=""; bits=[f"'{w}'" for w in (type1 or [])[:2]]
    if actors: bits.append(f"'{actors[0][0]}'")
    if bits: restore="First restore these source facts your summary dropped, framed exactly as the source presents them: "+", ".join(bits)+". "
    return (restore+f"A topological analysis of this event's latent space has detected a massive structural "
        f"resonance with the historical archetype of {entity}. Do NOT state that {entity} is involved in this "
        f"event \u2014 that is factually incorrect. Instead, extract the underlying systemic dynamics, power "
        f"structures, or failure modes associated with {entity}, and use them as a metaphorical lens to deepen "
        f"your analysis of the actors actually present in the text. Rewrite your summary to synthesize the "
        f"current facts through this historical shadow.")
def eseed_prompt(void):
    seeds=", ".join(void[:6]) if void else ""
    base=("Now consider the unspoken implications of this story. What significant stakes or dimensions did your "
          "summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them \u2014 but stay "
          "strictly faithful to the source and do not speculate beyond what it supports.")
    if not seeds: return base
    return base+f" The latent stakes may involve themes such as: {seeds}. Treat these as CONCEPTUAL directions, "+\
        "not words to insert. Synthesize whichever tensions are GENUINELY supported by the source \u2014 engage "+\
        "them conceptually, do not name-check them, invent nothing."
def distinguishable(a,b):
    a,b=a.lower(),b.lower()
    if a==b or a in b or b in a: return False
    if len(os.path.commonprefix([a,b]))>=4: return False
    return True
def setup_derive():
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t])); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    try: DF=json.load(open("void_frequency.json")).get("global",{})
    except Exception: DF={}
    NDOCS=1659.0
    def idf(w): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0
    REL=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})
    def derive(src,summaries):
        anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(summaries).lower(); srcl=src.lower(); t1=[]; t2=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD or sim<REL: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
            in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl)); (t1 if in_src else t2).append(w)
        void=[]; target=[]
        for w in t2:
            try:
                if KV3.is_named_entity(w): target.append(w)
                else: void.append(w)
            except Exception: void.append(w)
        return t1[:6], sorted(target,key=lambda w:-idf(w)), void[:8]
    return derive
def code_sentences(src,summary):
    sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+', re.sub(r'#.*?\n','',summary)) if len(s.strip())>15]
    if not sents: return None
    numbered="\n".join(f"{i+1}. {s}" for i,s in enumerate(sents))
    p=(f"SOURCE:\n{src[:1300]}\n\nA summary's sentences:\n{numbered}\n\nFor EACH numbered sentence, classify "
       f"where its content comes from RELATIVE TO THE SOURCE:\n  O = Observation (stated in/trivially recoverable "
       f"from source)\n  I = Inference (reasoning step beyond source, but source-grounded)\n  A = Analogy "
       f"(comparison/frame imported from outside source)\n  S = Speculation (no source support)\nReply EXACTLY one "
       f"line per sentence:\n1: <O/I/A/S>\n... through {len(sents)}")
    agg=defaultdict(int); tot=0
    for jn in API_ONLY:
        try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
        except Exception: out=""
        for m in re.finditer(r'^\s*(\d+)\s*[:.]?\s*([OIAS])\b', out or "", re.M|re.I): agg[m.group(2).upper()]+=1; tot+=1
    if tot==0: return None
    return {k:agg.get(k,0)/tot for k in ["O","I","A","S"]}, len(sents)
def main():
    stories=(STORIES[:1] if SMOKE else STORIES+[ADVERSARIAL])
    if SMOKE: print("*** SMOKE: 1 story ***",flush=True)
    print(f"K={K}  API (Grok dropped): {API_ONLY}",flush=True)
    derive=setup_derive(); ARMS=["E_SEED","ARCHETYPE_TRUE","ARCHETYPE_NEIGHBOR"]; all_results=[]
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72,flush=True)
        src=st["source"]; cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print("  consensus<3, skip"); continue
        t1w,target_ranked,void_w=derive(src,cons); actors=KV3.ner_actors_dropped(src,cons)
        true_entity=target_ranked[0] if target_ranked else None; neighbor=None
        for w in target_ranked[1:]:
            if distinguishable(true_entity,w): neighbor=w; break
        print(f"  type-A:{t1w} actors:{actors}")
        print(f"  SVD targets (ranked):{target_ranked[:6]}")
        print(f"  -> TRUE={true_entity}  NEIGHBOR={neighbor}  void(C):{void_w}",flush=True)
        if not true_entity or not neighbor: print("  !! missing TRUE/NEIGHBOR -> archetype arms N/A")
        rows=[]
        for p in API_ONLY:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
                    es=mt(p,pre+[{"role":"user","content":eseed_prompt(void_w)}]) or ""
                    at=mt(p,pre+[{"role":"user","content":archetype_prompt(true_entity,t1w,actors)}]) if (true_entity and neighbor) else ""
                    an=mt(p,pre+[{"role":"user","content":archetype_prompt(neighbor,t1w,actors)}]) if (true_entity and neighbor) else ""
                    gens.append({"A_BASE":base,"E_SEED":es,"ARCHETYPE_TRUE":at,"ARCHETYPE_NEIGHBOR":an})
                except Exception as e: print(f"    {p} gen{k} ERR {e}",flush=True)
            rows.append({"patient":p,"gens":gens}); print(f"  {p:<10} {len(gens)}/{K} gens",flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"type1":t1w,"actors":actors,
            "targets_ranked":target_ranked[:8],"void":void_w,"true_entity":true_entity,"neighbor_entity":neighbor,"source":src,"rows":rows})
        json.dump(all_results,open("archetype_rank_results.json","w"),indent=2); print(f"  [saved {len(all_results)}]",flush=True)
    print("\n"+"="*72); print("BLIND PANEL (Grok dropped, shuffled)"); print("="*72,flush=True)
    def judge(src,texts,arms):
        order=[a for a in arms if texts.get(a)]; random.shuffle(order)
        if len(order)<2: return {}
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(order)))
        p=(f"Source text:\n{src[:1400]}\n\n{len(order)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
           f"(true to source, NOTHING inferred or imported beyond it), action, trust, keep (0/1). One line each:\n"
           f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(order)})")
        agg=defaultdict(lambda: defaultdict(list))
        for jn in API_ONLY:
            try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
            except Exception: out=""
            for cond,d in C.parse_scores(out or "", order).items():
                for m,v in d.items(): agg[cond][m].append(v)
        return agg
    panel=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        if not (r.get("true_entity") and r.get("neighbor_entity")): continue
        for row in r["rows"]:
            for g in row["gens"]:
                a=judge(r["source"],g,ARMS)
                for cond,d in a.items():
                    for mm,vs in d.items(): panel[cond][mm].extend(vs)
    mets=["insight","faith","action","trust","keep"]; print(f"  {'cond':18s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ARMS:
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:18s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}",flush=True)
    if panel["ARCHETYPE_TRUE"]["insight"] and panel["ARCHETYPE_NEIGHBOR"]["insight"]:
        di=tbl["ARCHETYPE_TRUE"][0]-tbl["ARCHETYPE_NEIGHBOR"][0]; df=tbl["ARCHETYPE_TRUE"][1]-tbl["ARCHETYPE_NEIGHBOR"][1]
        print(f"\n  *** RANKING TEST ***\n  TRUE - NEIGHBOR: insight {di:+.2f} faith {df:+.2f}")
        print(f"  ~0 -> only NEIGHBORHOOD matters, top-entity interchangeable -> ship channel C")
        print(f"  >>0 -> geometry RANKING carries signal")
        if panel["E_SEED"]["insight"]:
            print(f"\n  *** THE WAR (vs product bar) ***\n  TRUE - E_SEED: insight {tbl['ARCHETYPE_TRUE'][0]-tbl['E_SEED'][0]:+.2f} faith {tbl['ARCHETYPE_TRUE'][1]-tbl['E_SEED'][1]:+.2f}")
            print(f"  E_SEED insight={tbl['E_SEED'][0]:.2f} faith={tbl['E_SEED'][1]:.2f} <- does ANY archetype beat plain concepts?")
    print("\n"+"="*72); print("SENTENCE CODING vs GOLD (hi Infer, ~0 Analogy) gen0"); print("="*72,flush=True)
    coded=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        if not (r.get("true_entity") and r.get("neighbor_entity")): continue
        for row in r["rows"]:
            g=row["gens"][0] if row["gens"] else None
            if not g: continue
            for arm in ARMS:
                if not g.get(arm): continue
                res=code_sentences(r["source"],g[arm])
                if res:
                    props,_=res
                    for k,v in props.items(): coded[arm][k].append(v)
    print(f"  {'arm':18s}  {'Obs':>6s} {'Infer':>6s} {'Analogy':>8s} {'Spec':>6s}")
    for arm in ARMS:
        if not coded[arm]["O"]: continue
        o,i,a,s=(np.mean(coded[arm][k]) if coded[arm][k] else 0 for k in ["O","I","A","S"])
        flag="<- gold-like" if (a<0.06 and i>0.35) else ("<- LAUNDERING" if a>0.15 else "")
        print(f"  {arm:18s}  {o:>6.2f} {i:>6.2f} {a:>8.2f} {s:>6.2f}   {flag}",flush=True)
    json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in ARMS},
        "coding":{a:{k:coded[a][k] for k in ['O','I','A','S']} for a in ARMS}},open("archetype_rank_panel.json","w"),indent=2)
    print("\nwrote archetype_rank_results.json + archetype_rank_panel.json")
    print("*** RANKING signal or just neighborhood? Does ANY archetype beat E_SEED? ***")
if __name__=="__main__": main()
