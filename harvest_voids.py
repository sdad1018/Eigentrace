#!/usr/bin/env python3
"""
harvest_voids.py — PURE RECON, no LLM, no GPU. Reads all rich story segments and
characterizes the AGGREGATE void landscape across the whole corpus, so we can see
the real structure before designing the atlas hero chart.

Reads precomputed fields the live system already wrote:
  void_words, void_context (freq%, signal_type), claim_killshots (salience+omitted_by),
  source_void (absent ratio), consensus_density, mean_vix, category, state_flag.

Prints six views:
  A. most frequent crowned-void WORDS across corpus (the recurring-void landscape)
  B. void-type distribution by CATEGORY (what kind of silence per domain)
  C. highest-salience MOST-OMITTED killshot claims (most direct "what they won't say")
  D. void signal_type breakdown (embedding vs other)
  E. divergence/density distributions (the cheap scalar signals)
  F. state_flag distribution (CONTESTED etc.)

Reads from tmp/segments (richest). No writes. Stream can stay up.
"""
import json, glob, re
from collections import Counter, defaultdict
import numpy as np

SEGS=glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json")
SKIP=["compression","governance","weekly","audit","daily ","self-audit","system "]

def is_story(a):
    mr=a.get("model_responses",{}); s={k:v for k,v in mr.items() if v and len(v)>50}
    t=a.get("story_title","").lower()
    return len(s)>=4 and not any(x in t for x in SKIP)

# accumulators
void_word_freq=Counter()
void_by_cat=defaultdict(Counter)
killshots=[]   # (salience, n_omitted, claim, category)
signal_types=Counter()
cat_count=Counter()
state_flags=Counter()
densities=[]; vixes=[]; absent_ratios=[]
void_word_cat_examples=defaultdict(list)  # word -> [titles]
n=0

for f in SEGS:
    try:
        d=json.load(open(f)); a=d.get("attribution",{})
        if not is_story(a): continue
        n+=1
        cat=a.get("category","(none)"); cat_count[cat]+=1
        state_flags[a.get("state_flag","(none)")]+=1
        if a.get("consensus_density") is not None: densities.append(a["consensus_density"])
        if a.get("mean_vix") is not None: vixes.append(a["mean_vix"])
        sv=a.get("source_void",{})
        if isinstance(sv,dict) and sv.get("absent_ratio") is not None: absent_ratios.append(sv["absent_ratio"])
        title=a.get("story_title","")[:50]
        # void words
        for w in (a.get("void_words") or []):
            wl=str(w).lower().strip()
            if wl:
                void_word_freq[wl]+=1; void_by_cat[cat][wl]+=1
                if len(void_word_cat_examples[wl])<3: void_word_cat_examples[wl].append(title)
        # void_context signal types
        for vc in (a.get("void_context") or []):
            if isinstance(vc,dict): signal_types[vc.get("signal_type","?")]+=1
        # killshots (salient claims omitted by models)
        for ks in (a.get("claim_killshots") or []):
            if isinstance(ks,dict):
                sal=ks.get("salience",0); om=ks.get("omitted_by") or []
                killshots.append((sal, len(om), ks.get("claim","")[:90], cat))
    except: pass

print(f"{'='*72}\nHARVESTED {n} rich story segments\n{'='*72}\n")

print("=== A. MOST FREQUENT VOID WORDS ACROSS CORPUS (the recurring-void landscape) ===")
for w,c in void_word_freq.most_common(45):
    ex=void_word_cat_examples[w][0] if void_word_cat_examples[w] else ""
    print(f"  {c:5d}  {w:24s} e.g. {ex}")
print(f"\n  (total distinct void words: {len(void_word_freq)})\n")

print("=== B. TOP VOID WORDS BY CATEGORY (kind of silence per domain) ===")
for cat,_ in cat_count.most_common(8):
    top=void_by_cat[cat].most_common(10)
    print(f"  [{cat}] (n={cat_count[cat]}): " + ", ".join(f"{w}({c})" for w,c in top))
print()

print("=== C. HIGHEST-SALIENCE MOST-OMITTED KILLSHOT CLAIMS ===")
# rank by salience * n_omitted (high-salience claims many models dropped)
killshots.sort(key=lambda x:(x[1], x[0]), reverse=True)
print("  [most models omitted, then by salience]")
for sal,nom,claim,cat in killshots[:25]:
    print(f"  omit={nom} sal={sal:.3f} [{cat:10s}] {claim}")
print()

print("=== D. VOID SIGNAL_TYPE BREAKDOWN ===")
for st,c in signal_types.most_common(): print(f"  {c:6d}  {st}")
print()

print("=== E. SCALAR SIGNAL DISTRIBUTIONS (cheap, precomputed) ===")
def stats(name,arr):
    if not arr: print(f"  {name}: none"); return
    a=np.array(arr); print(f"  {name}: n={len(a)} min={a.min():.3f} med={np.median(a):.3f} max={a.max():.3f} mean={a.mean():.3f}")
stats("consensus_density", densities)
stats("mean_vix", vixes)
stats("source_void.absent_ratio", absent_ratios)
print()

print("=== F. STATE_FLAG DISTRIBUTION ===")
for s,c in state_flags.most_common(): print(f"  {c:6d}  {s}")
print()

print("=== CATEGORY TOTALS ===")
for c,n2 in cat_count.most_common(): print(f"  {n2:5d}  {c}")
