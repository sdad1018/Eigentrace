#!/usr/bin/env python3
"""
find_interesting_stories.py — surface the most INTERESTING RECENT real stories for the
confront10_v2 keeper run, ranked by the instrument's own signals (not by guessing actors).

"Interesting" = recent + real news + high model divergence/VIX + contains a named actor
whose generic role would lose connotation. We let the EigenChing signals pick the stories
where the models actually had something to disagree about — the best test bed for Summary Plus.

Ranks clean real stories by:
  - recency (most recent first)
  - mean_vix / model divergence if present in attribution
  - presence of a named actor (capitalized multi-mention proper noun in source)
Dumps title + source_body + the void_words already on the segment, paste-ready for v2.
"""
import json, glob, os, re
from datetime import datetime
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
NONSTORY={"idle","wild_weasel","governance","foraging","silence","consolidation",
          "weekly_compression","self_audit","conversation","epistemic_battery","roundtable"}
ALLMODELS=["ChatGPT","Claude","Gemini","DeepSeek","Grok"]

def ts(f):
    m=re.match(r'(\d{8})_(\d{6})',os.path.basename(f)); return m.group(1)+m.group(2) if m else "00000000000000"
def is_real(seg,a):
    st=str(seg.get("type") or seg.get("segment_type") or a.get("type") or "").lower()
    if st in NONSTORY: return False
    return bool(a.get("story_title") or a.get("title")) and len(a.get("source_body","") or "")>=600

# crude named-actor detector: capitalized surname-like tokens appearing >=2x in source
def find_actors(src):
    caps=re.findall(r'\b([A-Z][a-z]{3,})\b', src)
    from collections import Counter
    c=Counter(caps)
    # filter common non-name capitalized words
    stop={"The","This","That","They","Their","These","Those","There","When","While","After",
          "Iran","Iranian","United","States","President","Trump","Israel","Israeli","American",
          "Reuters","Associated","Monday","Tuesday","Wednesday","Thursday","Friday","Sunday","Saturday"}
    return [(w,n) for w,n in c.most_common(8) if n>=2 and w not in stop]

def main():
    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"), key=ts, reverse=True)
    scored=[]
    for f in files:
        try: seg=json.load(open(f))
        except: continue
        a=seg.get("attribution") or {}
        if not is_real(seg,a): continue
        title=a.get("story_title") or a.get("title") or ""
        src=(a.get("source_body","") or "")
        d=ts(f)
        # signals
        vix=a.get("mean_vix") or a.get("model_vix") or 0
        if isinstance(vix,dict): vix=sum(vix.values())/max(1,len(vix))
        voids=a.get("void_words",[]) or []
        actors=find_actors(src)
        if not actors: continue   # need a named actor to test the role+original fix
        # interest score: recency rank handled by sort; add vix + actor centrality + void richness
        score=float(vix or 0)+len(actors)*2+min(len(voids),10)
        scored.append({"date":d,"score":score,"vix":vix,"title":title,
                       "actors":actors,"voids":voids[:12],"src":src.replace(chr(10)," ").strip()})
    # already sorted by recency; take recent window, re-rank top by score
    recent=scored[:200]                       # most recent 200 real stories with actors
    recent.sort(key=lambda x:-x["score"])      # best signal first
    print("="*74); print("MOST INTERESTING RECENT STORIES (recent + high-divergence + named actor)"); print("="*74)
    for s in recent[:10]:
        dt=s["date"]; pretty=f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
        print(f"\n[{pretty}] vix={s['vix']} score={s['score']:.0f}")
        print(f"  TITLE: {s['title']}")
        print(f"  ACTORS (role+original candidates): {s['actors']}")
        print(f"  VOIDS already surfaced: {s['voids']}")
        print(f"  --- paste-ready source ({len(s['src'][:1700])} chars) ---")
        print(f'  "{s["src"][:1700]}"')
    print(f"\n\nPick 3 with the richest ACTORS (named people whose role loses connotation).")
    print("These become confront10_v2 STORIES — real, recent, high-divergence test cases.")
