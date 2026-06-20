#!/usr/bin/env python3
"""
find_by_shape.py — pull 2 real stories per major EigenChing signature shape, for a
v2 that validates role+original across the instrument's OWN taxonomy (not ad-hoc stories).

The EigenChing assigns each story a signature archetype (Still Point, Unanimous Shield,
Clear Channel, Sharp Silence, Sealed Vault, etc.). We group clean real-stories-with-actors
by their signature NAME, and surface the 2 best per shape (recent, high-vix, rich actor).

This tells us which shapes have enough real-actor stories to test, and gives paste-ready
sources so v2 spans the taxonomy: does the role+original fix hold for EVERY shape, or only some?
"""
import glob, os, json, re
from collections import Counter, defaultdict
print("start", flush=True)
SEG="/home/remvelchio/eigentrace/tmp/segments"
NONSTORY={"idle","wild_weasel","governance","foraging","silence","consolidation",
          "weekly_compression","self_audit","conversation","epistemic_battery","roundtable"}
def ts(f):
    m=re.match(r'(\d{8})_(\d{6})',os.path.basename(f)); return (m.group(1)+m.group(2)) if m else "0"*14
def actors(src):
    c=Counter(re.findall(r'\b([A-Z][a-z]{3,})\b', src))
    stop={"The","This","That","They","Their","These","Those","There","When","While","After","Iran",
          "Iranian","United","States","President","Trump","Israel","Israeli","American","Reuters",
          "Press","Monday","Tuesday","Wednesday","Thursday","Friday","Sunday","Saturday","China",
          "Chinese","Russia","Russian","Gaza","Ukraine","Washington","Tehran","Live","Published","June","Middle","East"}
    return [(w,n) for w,n in c.most_common(10) if n>=2 and w not in stop]

# extract the EigenChing signature NAME from the beats
def signature(seg):
    for b in (seg.get("beats") or []):
        if "state_vector" in b.get("phase",""):
            t=b.get("text","")
            m=re.search(r'EigenChing state:\s*(.+?)(?:$|\n)', t)
            if m: return m.group(1).strip()
    return None

files=glob.glob(SEG+"/*_segment.json")
print(f"globbed {len(files)}", flush=True)
by_shape=defaultdict(list); shape_counts=Counter()
for i,f in enumerate(files):
    if i%5000==0: print(f"  scan {i}", flush=True)
    try: seg=json.load(open(f))
    except: continue
    a=seg.get("attribution") or {}
    st=str(seg.get("type") or seg.get("segment_type") or a.get("type") or "").lower()
    if st in NONSTORY: continue
    title=a.get("story_title") or a.get("title") or ""
    src=a.get("source_body","") or ""
    if not title or len(src)<600: continue
    sig=signature(seg)
    if not sig: continue
    shape_counts[sig]+=1
    act=actors(src)
    if not act: continue
    vix=a.get("mean_vix") or 0
    if isinstance(vix,dict): vix=sum(vix.values())/max(1,len(vix))
    by_shape[sig].append({"d":ts(f),"vix":float(vix or 0),"title":title,"actors":act,
                          "voids":(a.get("void_words",[]) or [])[:10],"src":src.replace(chr(10)," ").strip()})

print(f"\n=== EigenChing shapes present (real stories w/ actors) ===", flush=True)
for sig,n in shape_counts.most_common(20):
    have=len(by_shape.get(sig,[]))
    print(f"  {n:>4} total | {have:>3} with-actor | {sig}")

print(f"\n=== 2 BEST STORIES PER MAJOR SHAPE (recent + high-vix + rich actor) ===")
for sig,_ in shape_counts.most_common(12):
    lst=by_shape.get(sig,[])
    if len(lst)<2: continue
    lst.sort(key=lambda x:-(x["vix"]+len(x["actors"])*2))   # best signal
    print(f"\n#### SHAPE: {sig} ({len(lst)} candidates) ####")
    for s in lst[:2]:
        d=s["d"]
        print(f"  [{d[:4]}-{d[4:6]}-{d[6:8]}] vix={s['vix']:.0f} | {s['title'][:55]}")
        print(f"     actors: {s['actors'][:5]}  voids: {s['voids'][:6]}")
        print(f'     src: "{s["src"][:900]}"')
print("\nPick 2 per shape (or the shapes that matter most) -> confront10_v2 STORIES, tagged by shape.")
