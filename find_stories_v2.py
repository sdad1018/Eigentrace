#!/usr/bin/env python3
"""find_stories_v2 — fixed: filter FIRST, sort only the survivors. Heavily instrumented."""
import glob, os, json, re, sys
from collections import Counter
print("start", flush=True)
SEG="/home/remvelchio/eigentrace/tmp/segments"
NONSTORY={"idle","wild_weasel","governance","foraging","silence","consolidation",
          "weekly_compression","self_audit","conversation","epistemic_battery","roundtable"}
def ts(f):
    m=re.match(r'(\d{8})_(\d{6})',os.path.basename(f))
    return (m.group(1)+m.group(2)) if m else "00000000000000"
def find_actors(src):
    caps=re.findall(r'\b([A-Z][a-z]{3,})\b', src)
    c=Counter(caps)
    stop={"The","This","That","They","Their","These","Those","There","When","While","After","Iran",
          "Iranian","United","States","President","Trump","Israel","Israeli","American","Reuters",
          "Associated","Press","Monday","Tuesday","Wednesday","Thursday","Friday","Sunday","Saturday",
          "China","Chinese","Russia","Russian","Gaza","Ukraine","Washington","Tehran"}
    return [(w,n) for w,n in c.most_common(10) if n>=2 and w not in stop]

files=glob.glob(SEG+"/*_segment.json")
print(f"globbed {len(files)}", flush=True)

# FILTER FIRST (no sort yet) — collect real stories with actors
keep=[]
for i,f in enumerate(files):
    if i % 5000==0: print(f"  scanning {i}...", flush=True)
    try: seg=json.load(open(f))
    except: continue
    a=seg.get("attribution") or {}
    st=str(seg.get("type") or seg.get("segment_type") or a.get("type") or "").lower()
    if st in NONSTORY: continue
    title=a.get("story_title") or a.get("title") or ""
    src=a.get("source_body","") or ""
    if not title or len(src)<600: continue
    actors=find_actors(src)
    if not actors: continue
    vix=a.get("mean_vix") or 0
    if isinstance(vix,dict): vix=sum(vix.values())/max(1,len(vix))
    keep.append({"d":ts(f),"vix":float(vix or 0),"title":title,"actors":actors,
                 "voids":(a.get("void_words",[]) or [])[:12],"src":src.replace(chr(10)," ").strip()})

print(f"kept {len(keep)} real stories with named actors", flush=True)
# NOW sort the small survivor set by recency
keep.sort(key=lambda x:x["d"], reverse=True)
recent=keep[:120]
# re-rank by interest: vix + actor richness + void count
recent.sort(key=lambda x:-(x["vix"]+len(x["actors"])*2+min(len(x["voids"]),10)))

print("\n"+"="*74); print("TOP INTERESTING RECENT STORIES WITH NAMED ACTORS"); print("="*74)
for s in recent[:10]:
    d=s["d"]; print(f"\n[{d[:4]}-{d[4:6]}-{d[6:8]}] vix={s['vix']:.0f}")
    print(f"  TITLE: {s['title']}")
    print(f"  ACTORS: {s['actors']}")
    print(f"  VOIDS: {s['voids']}")
    print(f'  SRC: "{s["src"][:1500]}"')
print("\nPick 3 with the richest named people (whose role loses connotation) for confront10_v2.")
