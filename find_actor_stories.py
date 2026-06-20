#!/usr/bin/env python3
"""
find_actor_stories.py — pull REAL corpus stories featuring connotation-carrying actors,
for the confront10_v2 keeper run. Finds clean real stories whose source_body mentions a
named actor whose generic role would lose signal (Farage->Brexit, Merkel->austerity, etc).

Searches the clean real-story corpus (excludes idle/roundtable contamination), looks for
source bodies containing target actor surnames, and dumps title + source_body so we can
paste the best 3 into confront10_v2.py's STORIES list.
"""
import json, glob, os, re
SEG_DIR="/home/remvelchio/eigentrace/tmp/segments"
NONSTORY={"idle","wild_weasel","governance","foraging","silence","consolidation",
          "weekly_compression","self_audit","conversation","epistemic_battery","roundtable"}

# actors whose generic role flattens a specific connotation (role, opens_onto)
TARGETS={
 "farage":("a British politician","Brexit and right-wing populism"),
 "merkel":("a former German chancellor","austerity politics and migration policy"),
 "erdogan":("a Turkish president","authoritarian consolidation and press crackdowns"),
 "orban":("a Hungarian prime minister","illiberal democracy and EU friction"),
 "bolsonaro":("a Brazilian president","right-populism and Amazon deforestation"),
 "le pen":("a French politician","the far-right National Rally"),
 "netanyahu":("an Israeli prime minister","judicial overhaul and settlement policy"),
 "sadr":("an Iraqi Shiite cleric","militia power and anti-US mobilization"),
}

def is_real_story(seg,a):
    st=str(seg.get("type") or seg.get("segment_type") or a.get("type") or "").lower()
    if st in NONSTORY: return False
    return bool(a.get("story_title") or a.get("title")) and len(a.get("source_body","") or "")>=600

def main():
    files=sorted(glob.glob(SEG_DIR+"/*_segment.json"))
    hits={k:[] for k in TARGETS}
    for f in files:
        try: seg=json.load(open(f))
        except: continue
        a=seg.get("attribution") or {}
        if not is_real_story(seg,a): continue
        title=a.get("story_title") or a.get("title") or ""
        src=(a.get("source_body","") or "")
        sl=src.lower()
        for actor in TARGETS:
            if re.search(r'\b'+re.escape(actor)+r'\b', sl):
                # prefer stories where the actor is central (appears early / multiple times)
                cnt=sl.count(actor)
                hits[actor].append((cnt, len(src), title, src))
    print("="*72); print("REAL STORIES BY CONNOTATION-CARRYING ACTOR"); print("="*72)
    for actor,(role,opens) in TARGETS.items():
        lst=sorted(hits[actor], key=lambda x:(-x[0],-x[1]))  # most mentions, then longest
        if not lst: 
            print(f"\n[{actor}] role='{role}' -> NO real stories found"); continue
        print(f"\n[{actor}] role='{role}' opens_onto='{opens}' — {len(lst)} stories, best:")
        cnt,ln,title,src=lst[0]
        print(f"  title: {title}")
        print(f"  mentions: {cnt}, len: {ln}")
        # print a paste-ready block
        clean=src.replace("\n"," ").strip()[:1700]
        print(f"  --- paste-ready source ({len(clean)} chars) ---")
        print(f'  "{clean}"')
    print("\nPick 3 (ideally farage + one other actor + one for the gate), paste into confront10_v2 STORIES.")
