#!/usr/bin/env python3
"""
test_cutoff_familiarity.py — Does name retention track TRAINING-CUTOFF FAMILIARITY?

HYPOTHESIS (user's): frontier models (weights frozen ~mid-2024) under-retain entities
that became prominent AT/AFTER the cutoff, because they have weak training
representation of them — "generalizing away" unfamiliar actors when summarizing.

DESIGN: two curated buckets of named gov figures, matched loosely by role (officials/
heads of state), differing in WHEN they became prominent. Measure semantic retention
of each name across all stories it appears in.

  POST-cutoff (weak training rep): rose to prominence ~mid-2024 or later.
  PRE-cutoff (strong training rep): well-established in training data well before 2024.

PREDICTION: POST-cutoff names retained significantly LESS than PRE-cutoff names.

KEY DISCRIMINATOR vs the "minor names just drop" confound: the post-cutoff bucket
includes HIGH-PROMINENCE figures (Pezeshkian = president, Hegseth = SecDef). If even
major-but-post-cutoff figures are under-retained relative to major pre-cutoff figures,
prominence cannot explain it — it's the cutoff.

NULL: shuffle the pre/post labels -> retention gap should vanish.

NOTE: this is a curated first confirmatory test. Buckets are editable below.
Cutoff assumed ~mid-2024. EDIT NAMES if any are miscategorized.
"""
import json, glob, os, re, sys
import numpy as np

SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"; JUNE=1749200000; MIN_RESP=4; N_NULL=200

# ============ CURATION — EDIT THESE ============
# POST-cutoff: became prominent at/after ~mid-2024. Includes semi-known-then-elevated.
POST_CUTOFF = {
    "pezeshkian": "Iran president, elected July 2024",
    "araghchi":   "Iran FM, appointed Aug 2024",
    "baghaei":    "Iran MFA spokesman, 2024",
    "esmaeil":    "Esmaeil Baghaei (first name)",
    "bagher":     "Mohammad Bagher (Iran official name-fragment)",
    "hegseth":    "US SecDef, confirmed Jan 2025 (was Fox host - semi-known)",
    "vance":      "US VP, elevated 2024-25 (was senator - semi-known)",
    "pete":       "Pete Hegseth (first name)",
    # candidates - VERIFY:
    "witkoff":    "Steve Witkoff, Trump envoy 2025 (was obscure)",
    "dort":       "verify - possibly post-cutoff figure",
}
# PRE-cutoff: well-established in training well before mid-2024.
PRE_CUTOFF = {
    "netanyahu":  "Israel PM, prominent for decades",
    "putin":      "Russia president, decades",
    "khamenei":   "Iran Supreme Leader, decades",
    "trump":      "US, decades",
    "biden":      "US, decades",
    "zelensky":   "Ukraine president since 2019",
    "zelenskyy":  "alt spelling",
    "blinken":    "US SecState pre-2024 (matches Rubio/Hegseth role)",
    "erdogan":    "Turkey, decades",
    "macron":     "France president since 2017",
    "modi":       "India PM since 2014",
    "xi":         "China, decades",
}
# ===============================================

def main():
    print("Loading bge-large...")
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("BAAI/bge-large-en-v1.5")
    def embed(t):
        if not t: return np.zeros((0,1024))
        return np.array(model.encode(t,normalize_embeddings=True,show_progress_bar=False,batch_size=128))

    targets = {**{k:"post" for k in POST_CUTOFF}, **{k:"pre" for k in PRE_CUTOFF}}
    files=[f for f in glob.glob(os.path.join(SEG_DIR,"*_segment.json")) if os.path.getmtime(f)>JUNE and not any(x in f for x in ['idle','governance','weekly','consolidation','roundtable'])]
    print(f"Scanning {len(files)} segments for {len(targets)} curated names...")

    name_rets = {k:[] for k in targets}  # name -> list of retentions across stories
    for fi,f in enumerate(files):
        if fi%2000==0: print(f"  [{fi}/{len(files)}]",flush=True)
        try: d=json.load(open(f))
        except: continue
        a=d.get("attribution",{}); src=(a.get("source_body","")or"").lower(); mr=a.get("model_responses",{})
        if len(mr)<MIN_RESP or len(src)<80: continue
        present=[k for k in targets if re.search(r"\b"+re.escape(k)+r"\b",src)]
        if not present: continue
        summ=" ".join(mr.values())
        sents=[s.strip() for s in re.split(r'(?<=[.!?])\s+',summ) if len(s.strip())>15]
        if len(sents)<3: continue
        se=embed(sents)
        ne=embed(present)
        for k,kv in zip(present,ne):
            name_rets[k].append(float(np.max(se@kv)))

    # aggregate
    post_vals=[]; pre_vals=[]
    print("\n=== PER-NAME RETENTION ===")
    print(f"{'name':<14}{'bucket':<7}{'mean_ret':<10}{'#stories':<9}note")
    for k in sorted(targets, key=lambda x:(targets[x], -len(name_rets[x]))):
        rs=name_rets[k]
        if len(rs)<3:
            print(f"  {k:<12}{targets[k]:<7}{'(only '+str(len(rs))+' stories - excluded)'}")
            continue
        m=np.mean(rs)
        note=(POST_CUTOFF if targets[k]=="post" else PRE_CUTOFF).get(k,"")
        print(f"  {k:<12}{targets[k]:<7}{m:<10.4f}{len(rs):<9}{note[:40]}")
        (post_vals if targets[k]=="post" else pre_vals).extend(rs)

    post_vals=np.array(post_vals); pre_vals=np.array(pre_vals)
    print(f"\n=== AGGREGATE ===")
    print(f"  POST-cutoff names: retention {post_vals.mean():.4f}  (n={len(post_vals)} name-mentions)")
    print(f"  PRE-cutoff names:  retention {pre_vals.mean():.4f}  (n={len(pre_vals)} name-mentions)")
    print(f"  Gap (pre - post): {pre_vals.mean()-post_vals.mean():+.4f}")

    if len(post_vals)<20 or len(pre_vals)<20:
        print("  insufficient name-mentions — need more curated names or stories."); return 1

    from scipy import stats
    t,p=stats.ttest_ind(pre_vals,post_vals,equal_var=False)
    sd=np.sqrt((post_vals.var(ddof=1)+pre_vals.var(ddof=1))/2); d=(pre_vals.mean()-post_vals.mean())/sd if sd>0 else 0
    print(f"  Welch t={t:.2f}  p={p:.2e}  Cohen's d={d:.3f}")
    holds = p<0.01 and pre_vals.mean()>post_vals.mean()
    print(f"  -> {'SUPPORTS cutoff-familiarity: post-cutoff names retained LESS' if holds else ('REVERSED' if pre_vals.mean()<post_vals.mean() else 'no sig difference')}")

    # null
    pooled=np.concatenate([post_vals,pre_vals]); npost=len(post_vals); ng=[]
    for _ in range(N_NULL):
        idx=np.random.permutation(len(pooled)); ng.append(pooled[idx[:npost]].mean()-pooled[idx[npost:]].mean())
    ng=np.array(ng); real=pre_vals.mean()-post_vals.mean(); nullp=float(np.mean(np.abs(ng)>=abs(real)))
    print(f"  NULL: frac shuffles >= real gap = {nullp:.4f} -> {'specific to pre/post split' if nullp<0.01 else 'within null range'}")

    print("\n=== CONFOUND CHECK ===")
    print("  Remember: post-cutoff bucket includes HIGH-prominence figures (president, SecDef).")
    print("  If they're still under-retained vs pre-cutoff heads of state, prominence != explanation.")
    print("  But this is a CURATED first test — buckets are hand-picked, n is modest. Confirmatory,")
    print("  not definitive. A pre-registered replication on held-out names would seal it.")

    open("anamnesis_results/cutoff_familiarity_results.json","w").write(json.dumps({
        "post_retention":float(post_vals.mean()),"pre_retention":float(pre_vals.mean()),
        "gap_pre_minus_post":float(real),"p":float(p),"d":float(d),"null_p":nullp,
        "post_n":len(post_vals),"pre_n":len(pre_vals),"holds":bool(holds),
        "post_names":list(POST_CUTOFF.keys()),"pre_names":list(PRE_CUTOFF.keys())},indent=2))
    print("\nSaved: anamnesis_results/cutoff_familiarity_results.json")
    return 0
if __name__=="__main__": sys.exit(main())
