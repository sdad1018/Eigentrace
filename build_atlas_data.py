#!/usr/bin/env python3
"""
build_atlas_data.py — builds the full Consequence Atlas data:
  1. LANDSCAPE  — corpus-wide ranked omitted-concept landscape (harvest+clean+relabel)
  2. SIGNAL SPLIT — landscape split by signal_type: IN-SOURCE-DROPPED (HIGH_SALIENCE,
     which compression-as-usual cannot explain) vs ON-TOPIC-ABSENT (EMBEDDING_SIGNAL).
     This directly answers the "is it meaningful or just compression?" red-team.
  3. PER-STORY CROWNS — the validated v6 pipeline (recall -> 3way relabel -> fabrication
     gate -> comparative unlock ranking -> crown) over a curated high-signal slice.
     This is the "consensus -> the one meaningful unspoken concept" arrow (the dream
     chart), and the unlock-ranking explicitly tests meaningfulness per story.

Writes docs/atlas_data.json. Stream stopped (GPU for per-story recall + API).
"""
import json, glob, re, time, os, sys, shutil, tempfile
from collections import Counter, defaultdict
import numpy as np

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
OUT="/mnt/c/Users/M4ISI/eigentrace/docs/atlas_data.json"

SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]
MIN_FREQ=12; TOP_CONCEPTS=60; EXAMPLES_PER=4
N_CROWN_STORIES=16          # per-story crowns over this many high-signal stories
TOP_N=12; AUTHOR="ChatGPT"; JUDGE="DeepSeek"
HEAD_W, CENT_W = 0.3, 0.7; OUTER=0.58

HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","persia","ticker","linus",
           "scotus","gops","trumpers","trumpcare","goes","clang","scala","alfresco","wot"}
def is_clean_concept(w):
    wl=w.lower().strip()
    return bool(wl) and len(wl)<=40 and all(c.isalpha() or c.isspace() for c in wl)

def parse_top3(txt, cc):
    if not txt: return []
    m=re.search(r'top\s*3?\s*:?\s*(.+)', txt, re.I); tail=(m.group(1) if m else txt).replace('[','').replace(']','')
    raw=[x.strip().strip('.').strip() for x in re.split(r'[,\n]', tail)]; out=[]; lm={c.lower():c for c in cc}
    for x in raw:
        if not x: continue
        if re.fullmatch(r'\d+', x):
            i=int(x)-1
            if 0<=i<len(cc): out.append(cc[i])
        else:
            xl=x.lower()
            if xl in lm: out.append(lm[xl])
            else:
                h=[c for c in cc if c.lower()==xl or c.lower() in xl or xl in c.lower()]
                out.append(h[0] if h else (x if len(x)<45 else None))
        out=[o for o in out if o]
        if len(out)>=3: break
    return out

def relabel_batch(judge, words):
    rel={}; calls=0
    for i in range(0,len(words),20):
        chunk=words[i:i+20]
        listing="\n".join(f"  {j+1}. {w}" for j,w in enumerate(chunk))
        cp=(f"These are concepts AI news summaries often OMIT, surfaced from a frozen embedding space. "
            f"For EACH answer 'N. <action>':\n"
            f"KEEP <term> — durable concept (e.g. 'civilian casualties','arms deal','regime change').\n"
            f"CATEGORY <label> — STALE named person/org -> its durable ROLE (e.g. 'rouhani' -> 'an Iranian "
            f"president'). Fillable role, not bare generic.\n"
            f"DROP — pure noise, ticker, handle, not a real concept.\n\n{listing}\n\n"
            f"Answer one per line: N. KEEP <term> / N. CATEGORY <label> / N. DROP")
        rt,_=judge(cp); calls+=1
        for line in (rt or "").splitlines():
            m=re.match(r'\s*(\d+)\.\s*(KEEP|CATEGORY|DROP)\b\s*(.*)', line, re.I)
            if m:
                j=int(m.group(1))-1
                if 0<=j<len(chunk):
                    act=m.group(2).lower(); lab=m.group(3).strip()
                    rel[chunk[j]]=("keep",chunk[j]) if act=="keep" else (("category",lab or chunk[j]) if act=="category" else ("drop",None))
    return rel, calls

def main():
    import proxy_auditor as pa
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    judge=pa.BIG5_CALLERS[JUDGE]; author=pa.BIG5_CALLERS[AUTHOR]
    SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
    def is_story(a):
        mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
        t=a.get("story_title","").lower()
        return len(s)>=4 and not any(x in t for x in SKIP)

    # ---------- PASS 1: harvest landscape + signal split ----------
    freq=Counter(); by_cat=defaultdict(Counter); examples=defaultdict(list)
    best_ks=defaultdict(lambda:(0,"")); cat_count=Counter()
    sig_freq={"HIGH_SALIENCE":Counter(),"EMBEDDING_SIGNAL":Counter()}
    n=0
    print("PASS 1: harvesting landscape...", flush=True)
    for f in SEGS:
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            n+=1; cat=a.get("category","general"); cat_count[cat]+=1
            title=a.get("story_title",""); url=a.get("story_url","")
            ksl=a.get("claim_killshots") or []
            bks=max(ksl,key=lambda k:k.get("salience",0) if isinstance(k,dict) else 0,default=None)
            # void_context carries per-word signal_type
            vc_sig={}
            for vc in (a.get("void_context") or []):
                if isinstance(vc,dict): vc_sig[str(vc.get("word","")).lower()]=vc.get("signal_type","")
            for w in (a.get("void_words") or []):
                wl=str(w).lower().strip()
                if not wl or wl in HARD_DROP or not is_clean_concept(wl): continue
                freq[wl]+=1; by_cat[cat][wl]+=1
                st=vc_sig.get(wl,"")
                if st in sig_freq: sig_freq[st][wl]+=1
                if len(examples[wl])<EXAMPLES_PER and title: examples[wl].append({"title":title[:90],"url":url,"cat":cat})
                if bks and isinstance(bks,dict) and bks.get("salience",0)>best_ks[wl][0]:
                    best_ks[wl]=(bks["salience"],bks.get("claim","")[:120])
        except: pass
    print(f"  {n} stories, {len(freq)} distinct concepts", flush=True)

    top=[(w,c) for w,c in freq.most_common() if c>=MIN_FREQ][:TOP_CONCEPTS]
    words=[w for w,_ in top]
    print(f"  relabeling {len(words)} concepts...", flush=True)
    rel,rcalls=relabel_batch(judge, words)

    def dom(w):
        best=("general",0)
        for c,cc in by_cat.items():
            if cc.get(w,0)>best[1]: best=(c,cc[w])
        return best[0]

    landscape=[]
    for w,c in top:
        act,lab=rel.get(w,("keep",w))
        if act=="drop": continue
        ks=best_ks[w]
        # source-dropped vs embedding-adjacent counts for this concept
        landscape.append({"concept":lab if act=="category" else w,"raw":w,"count":c,"domain":dom(w),
            "examples":examples[w],"killshot":ks[1] if ks[0]>0.5 else "","killshot_salience":round(ks[0],3) if ks[0]>0 else 0,
            "relabeled":act=="category",
            "in_source_count":sig_freq["HIGH_SALIENCE"].get(w,0),
            "adjacent_count":sig_freq["EMBEDDING_SIGNAL"].get(w,0)})

    # signal split top lists
    def clean_sig_list(counter):
        out=[]
        for w,c in counter.most_common(60):
            if w in HARD_DROP or not is_clean_concept(w) or c<4: continue
            act,lab=rel.get(w,("keep",w))
            if act=="drop": continue
            out.append({"concept":lab if act=="category" else w,"count":c})
            if len(out)>=18: break
        return out
    signal_split={
        "in_source_dropped": clean_sig_list(sig_freq["HIGH_SALIENCE"]),   # compression can't explain
        "on_topic_absent":   clean_sig_list(sig_freq["EMBEDDING_SIGNAL"]),
    }

    domains={}
    for cat,_ in cat_count.most_common(6):
        dl=[]
        for w,cnt in by_cat[cat].most_common(40):
            if w in HARD_DROP or cnt<4: continue
            act,lab=rel.get(w,("keep",w))
            if act=="drop": continue
            dl.append({"concept":lab if act=="category" else w,"count":cnt})
            if len(dl)>=10: break
        domains[cat]={"n_stories":cat_count[cat],"concepts":dl}

    # ---------- PASS 2: per-story crowns (v6 pipeline) ----------
    print("PASS 2: per-story crowns (v6 pipeline)...", flush=True)
    tmp=tempfile.mkdtemp(prefix="cv_")
    shutil.copy("vocab/global_vocab_clean.json",os.path.join(tmp,"global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",os.path.join(tmp,"global_vocab.pt"))
    eng=get_engine(); vt=VocabTensor(tmp)
    def E(t):
        v=np.array(eng.embed_texts(t)); return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)

    CUE=["war","strike","nuclear","ceasefire","sanction","missile","invasion","escalat","embargo",
         "strait","blockade","retaliat","truce","deal","iran","ukraine","russia","israel","gaza"]
    # pick recent high-signal charged stories with rich responses + high vix (divergence) preferred
    cands=[]
    for f in sorted(SEGS, reverse=True):
        if len(cands)>=N_CROWN_STORIES*3: break
        try:
            d=json.load(open(f)); a=d.get("attribution",{})
            if not is_story(a): continue
            t=a.get("story_title","")
            if sum(c in t.lower() for c in CUE)<1: continue
            cands.append((a.get("mean_vix",0), a))
        except: pass
    cands.sort(key=lambda x:x[0], reverse=True)   # prefer high-divergence stories
    crowns=[]; ccalls=0; seen=set()
    for vix,a in cands:
        if len(crowns)>=N_CROWN_STORIES: break
        title=a.get("story_title","").strip()
        if title.lower() in seen: continue
        seen.add(title.lower())
        sums={k:v for k,v in a["model_responses"].items() if v and len(v)>50}
        try:
            vecs=E(list(sums.values())); cen=vecs.mean(0); cen/=np.linalg.norm(cen)+1e-8
            hv=E([title])[0]; bl=HEAD_W*hv+CENT_W*cen; bl/=np.linalg.norm(bl)+1e-8
            res=vt.in_domain_void(centroid=cen,response_vecs=vecs,headline_vec=bl,k=TOP_N,outer_threshold=OUTER)
            cwords=[w for w,_ in (res[0] if isinstance(res,tuple) else res)]
            if len(cwords)<4: continue
            consensus=" ".join(list(sums.values())[:2])[:360]
            crel,rc=relabel_batch(judge,cwords); ccalls+=rc
            working=[(w,crel.get(w,("keep",w))[1]) for w in cwords if crel.get(w,("keep",w))[0]!="drop"]
            summ={}
            for w,lab in working:
                ap=(f"News story: {title}\n\nWrite a tight 2-3 sentence summary that MUST meaningfully "
                    f"incorporate '{lab}'. Work it in naturally; stay consistent; invent nothing.")
                s1,_=author(ap); ccalls+=1
                if s1 and len(s1.strip())>20: summ[w]=(lab,s1.strip())
            clean=[]
            for w,(lab,s1) in summ.items():
                fp=(f"SOURCE STORY: {title}\n\nA SUMMARY: {s1}\n\nDoes this summary assert any SPECIFIC FACT "
                    f"the source contradicts or can't support? Interpretation is FINE — only flag INVENTED "
                    f"specifics. Answer one word: CLEAN or FABRICATED.")
                ft,_=judge(fp); ccalls+=1
                if "clean" in (ft or "").lower(): clean.append(w)
            if len(clean)<2: continue
            labels=[summ[w][0] for w in clean]
            lst="\n".join(f"  {i+1}. [{summ[w][0]}] {summ[w][1]}" for i,w in enumerate(clean))
            rp=(f"SOURCE STORY: {title}\n\nBASE FACTS: {consensus}\n\nRank the TOP 3 candidate summaries that "
                f"add the most SPECIFIC, NON-OBVIOUS explanatory dimension — a new consequence, actor, or "
                f"mechanism a reader wouldn't already assume. Penalize restating the obvious or being too generic.\n\n"
                f"{lst}\n\nAnswer EXACTLY: TOP3: concept1, concept2, concept3")
            rt,_=judge(rp); ccalls+=1
            crowned=parse_top3(rt,labels)
            if not crowned: continue
            demoted=[summ[w][0] for w in clean if summ[w][0].lower() not in [c.lower() for c in crowned]]
            signal=round(len(demoted)/max(len(clean),1),3)
            crowns.append({"title":title,"url":a.get("story_url",""),"category":a.get("category",""),
                "consensus":consensus,"crowned":crowned,"demoted":demoted[:8],
                "mean_vix":round(vix,1),"signal":signal})
            print(f"  [{len(crowns)}/{N_CROWN_STORIES}] {title[:42]:44s} -> {crowned}", flush=True)
        except Exception as e:
            print(f"   skip: {str(e)[:50]}")
    crowns.sort(key=lambda c:c["signal"], reverse=True)

    payload={
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_stories": n, "n_distinct_concepts": len(freq),
        "method":"void_words harvested -> clean+relabel; per-story crowns via recall->relabel->fabrication-gate->unlock-rank",
        "landscape": landscape,
        "signal_split": signal_split,
        "domains": domains,
        "crowns": crowns,
        "totals": dict(cat_count.most_common()),
    }
    with open(OUT,"w") as fh: json.dump(payload,fh,indent=2)
    shutil.copy(OUT,"atlas_data.json"); shutil.rmtree(tmp,ignore_errors=True)
    print(f"\nwrote {len(landscape)} landscape concepts, {len(crowns)} story crowns -> {OUT}")
    print(f"relabel calls: {rcalls} | crown calls: {ccalls}")
    print("\nIN-SOURCE-DROPPED (compression can't explain) top 8:")
    for x in signal_split["in_source_dropped"][:8]: print(f"  {x['count']:4d}  {x['concept']}")

if __name__=="__main__":
    main()
