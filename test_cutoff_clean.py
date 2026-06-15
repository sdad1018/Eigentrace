#!/usr/bin/env python3
"""
test_cutoff_clean.py — TIGHTENED cutoff-familiarity test.

Fixes from v1 (which gave inflated d=1.51):
  1. DROP first-name fragments (pete, bagher, esmaeil) — only full surnames.
  2. TRANSLITERATION CONTROL: split by name-origin (English vs non-English) and test
     the cutoff effect WITHIN each, so "post-cutoff" isn't confounded with "foreign name."
     - English post (Hegseth/Vance/Witkoff) vs English pre (Trump/Biden/Blinken) = cleanest.
     - Non-English post (Araghchi/Baghaei/Pezeshkian) vs non-English pre (Khamenei/Putin/
       Netanyahu/Xi/Modi) = transliteration roughly matched.
  If post<pre holds WITHIN BOTH groups, the cutoff effect is real & not a name-type artifact.

Confound-killer to watch: Pezeshkian (sitting president) vs Netanyahu/Putin (presidents) —
high-prominence post-cutoff vs high-prominence pre-cutoff, same role.
"""
import json, glob, os, re, sys
import numpy as np

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4; N_NULL=200

# full surnames only, tagged by (bucket, name_origin)
NAMES = {
    # English-named
    "hegseth":   ("post","en","US SecDef 2025"),
    "vance":     ("post","en","US VP 2024-25"),
    "witkoff":   ("post","en","Trump envoy 2025"),
    "trump":     ("pre","en","decades"),
    "biden":     ("pre","en","decades"),
    "blinken":   ("pre","en","SecState pre-2024"),
    # non-English-named
    "araghchi":   ("post","intl","Iran FM Aug 2024"),
    "baghaei":    ("post","intl","Iran MFA spox 2024"),
    "pezeshkian": ("post","intl","Iran president Jul 2024"),
    "khamenei":   ("pre","intl","Iran Supreme Leader, decades"),
    "putin":      ("pre","intl","decades"),
    "netanyahu":  ("pre","intl","decades"),
    "xi":         ("pre","intl","decades"),
    "modi":       ("pre","intl","India PM 2014"),
    "erdogan":    ("pre","intl","Turkey decades"),
}

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))

    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments for {len(NAMES)} full-surname targets...")
    rets={k:[] for k in NAMES}
    for fi,f in enumerate(files):
        if fi%2000==0: print(f"  [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=(a.get("source_body","")or"").lower(); mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        present=[k for k in NAMES if re.search(r"\b"+re.escape(k)+r"\b",src)]
        if not present: continue
        summ=" ".join(mr.values()); sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents); ne=embed(present)
        for k,kv in zip(present,ne): rets[k].append(float(np.max(se@kv)))

    from scipy import stats
    def agg(filt):
        post=[]; pre=[]
        for k,(b,o,_) in NAMES.items():
            if not filt(o): continue
            if len(rets[k])<3: continue
            (post if b=="post" else pre).extend(rets[k])
        return np.array(post),np.array(pre)

    print("\n=== PER-NAME (full surnames only) ===")
    print(f"{'name':<12}{'bkt':<6}{'orig':<6}{'ret':<9}{'n'}")
    for k in sorted(NAMES,key=lambda x:(NAMES[x][0],NAMES[x][1],-len(rets[x]))):
        b,o,note=NAMES[k]
        if len(rets[k])<3: print(f"  {k:<10}{b:<6}{o:<6}(only {len(rets[k])} - excl)"); continue
        print(f"  {k:<10}{b:<6}{o:<6}{np.mean(rets[k]):<9.4f}{len(rets[k])}")

    def report(label,post,pre):
        print(f"\n=== {label} ===")
        if len(post)<15 or len(pre)<15:
            print(f"  insufficient (post={len(post)},pre={len(pre)})"); return None
        t,p=stats.ttest_ind(pre,post,equal_var=False)
        sd=np.sqrt((post.var(ddof=1)+pre.var(ddof=1))/2); d=(pre.mean()-post.mean())/sd if sd>0 else 0
        print(f"  post={post.mean():.4f} (n={len(post)})  pre={pre.mean():.4f} (n={len(pre)})  gap={pre.mean()-post.mean():+.4f}")
        print(f"  t={t:.2f} p={p:.2e} d={d:.3f} -> {'post retained LESS' if p<0.05 and pre.mean()>post.mean() else 'no/rev'}")
        return d

    pa,pr=agg(lambda o:True);     d_all=report("ALL (full surnames)",pa,pr)
    pa,pr=agg(lambda o:o=="en");  d_en=report("ENGLISH-NAMED ONLY (no transliteration confound)",pa,pr)
    pa,pr=agg(lambda o:o=="intl");d_in=report("NON-ENGLISH ONLY (transliteration ~matched)",pa,pr)

    print("\n=== VERDICT ===")
    if d_en and d_in and d_en>0.2 and d_in>0.2:
        print("  Cutoff effect holds in BOTH English-only AND non-English-only cuts.")
        print("  -> NOT a transliteration artifact. Real cutoff-familiarity effect.")
        print(f"  -> Cleanest (English-only) effect size d={d_en:.2f}")
    elif d_en and d_en>0.2:
        print(f"  Holds in English-only (d={d_en:.2f}) — clean of transliteration. Real but check intl.")
    else:
        print("  Does NOT hold cleanly once name-type controlled — earlier effect was confounded.")
    print("\n  Confound-killer: compare Pezeshkian (post, president) to Netanyahu/Putin (pre, presidents) above.")
    print("  Curated first test; pre-registered held-out replication would seal it.")

    open("anamnesis_results/cutoff_clean_results.json","w").write(json.dumps({
        "d_all":float(d_all or 0),"d_english":float(d_en or 0),"d_intl":float(d_in or 0),
        "per_name":{k:(round(float(np.mean(rets[k])),4) if len(rets[k])>=3 else None) for k in NAMES}},indent=2))
    print("\nSaved: anamnesis_results/cutoff_clean_results.json")
    return 0
if __name__=="__main__": sys.exit(main())
