#!/usr/bin/env python3
"""
propagation_scanner.py — Track how eigenanamnesis/eigentrace spread through Moltbook.

Classifies every mention by propagation vector:
  SELF:    we posted it
  REPLY:   response in a thread we seeded
  MENTION: term used by agent who previously interacted with our posts
  ORGANIC: term used with no traceable link to us

Tracks hop distance: how many reply-chain steps from our injection.

Usage:
  python3 propagation_scanner.py                # scan once
  python3 propagation_scanner.py --push         # scan + git push
  python3 propagation_scanner.py --cron --push  # every 30min
  python3 propagation_scanner.py --seed         # record injection event
"""

import json, os, sys, time, subprocess
from datetime import datetime, timezone

TRACKED_TERMS = ["eigentrace", "eigenanamnesis"]
OUR_AGENT = "eigentrace_observer"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(REPO_ROOT, "docs", "propagation_data.json")
MOLTBOOK_BASE = "https://moltbook.com"
SCAN_INTERVAL = 1800

def empty_data():
    return {"tracked_terms": TRACKED_TERMS, "our_agent": OUR_AGENT,
            "injection": None, "first_organic": None, "last_scan": None,
            "total_scans": 0, "events": [], "threads_seeded": [],
            "stats": {"total_mentions":0, "by_vector":{"reply":0,"mention":0,"organic":0,"self":0},
                      "unique_agents":0, "submolts_reached":0, "furthest_hop":0, "days_to_first_organic":None}}

def load():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f: return json.load(f)
    return empty_data()

def save(data):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f: json.dump(data, f, indent=2, default=str)

def search_moltbook(term):
    try:
        import requests
        r = requests.get(f"{MOLTBOOK_BASE}/api/search", params={"q":term,"limit":100},
                         headers={"User-Agent":"EigenTrace-Scanner/0.2"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d if isinstance(d, list) else d.get("results", [])
        return []
    except Exception as e:
        print(f"[scan] Error: {e}"); return []

def get_thread_replies(thread_id):
    try:
        import requests
        r = requests.get(f"{MOLTBOOK_BASE}/api/posts/{thread_id}/comments",
                         params={"limit":100}, headers={"User-Agent":"EigenTrace-Scanner/0.2"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d if isinstance(d, list) else d.get("comments", [])
        return []
    except: return []

def classify(item, data):
    agent = item.get("agent", item.get("author", item.get("username", "unknown")))
    thread_id = str(item.get("thread_id", item.get("parent_id", "")))
    if agent == OUR_AGENT: return "self"
    if thread_id in data.get("threads_seeded", []): return "reply"
    reply_agents = {e["agent"] for e in data["events"] if e["vector"] == "reply"}
    if agent in reply_agents: return "mention"
    return "organic"

def parse_item(item, vector):
    text = item.get("text", item.get("content", item.get("body", "")))
    return {"id": str(item.get("id", item.get("_id", f"u{time.time()}"))),
            "agent": item.get("author", item.get("username", "unknown")),
            "submolt": item.get("submolt", item.get("community", "unknown")),
            "thread_id": str(item.get("thread_id", item.get("parent_id", ""))),
            "text": text[:300], "timestamp": item.get("created_at", item.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "vector": vector, "upvotes": item.get("upvotes", item.get("score", 0)),
            "replies": item.get("reply_count", 0), "url": item.get("url", ""),
            "terms": [t for t in TRACKED_TERMS if t.lower() in text.lower()],
            "hop_distance": {"self":0,"reply":1,"mention":2,"organic":3}.get(vector, 0)}

def compute_stats(data):
    events = data["events"]
    non_self = [e for e in events if e["vector"] != "self"]
    data["stats"] = {
        "total_mentions": len(non_self),
        "by_vector": {v: len([e for e in events if e["vector"]==v]) for v in ["reply","mention","organic","self"]},
        "unique_agents": len(set(e["agent"] for e in non_self)) if non_self else 0,
        "submolts_reached": len(set(e["submolt"] for e in non_self)) if non_self else 0,
        "furthest_hop": max((e.get("hop_distance",0) for e in non_self), default=0),
        "days_to_first_organic": None
    }
    organic = sorted([e for e in events if e["vector"]=="organic"], key=lambda e: e.get("timestamp",""))
    if organic:
        if not data.get("first_organic"): data["first_organic"] = organic[0]["timestamp"]
        if data.get("injection"):
            try:
                inj = datetime.fromisoformat(data["injection"]["timestamp"].replace("Z","+00:00"))
                org = datetime.fromisoformat(organic[0]["timestamp"].replace("Z","+00:00"))
                data["stats"]["days_to_first_organic"] = round((org-inj).total_seconds()/86400, 1)
            except: pass

def scan_once(data):
    added = 0
    existing_ids = {e["id"] for e in data["events"]}
    sym = {"self":"⊙","reply":"↩","mention":"◆","organic":"★"}
    for term in TRACKED_TERMS:
        print(f"[scan] '{term}'...")
        for item in search_moltbook(term):
            iid = str(item.get("id",""))
            if iid in existing_ids: continue
            v = classify(item, data)
            e = parse_item(item, v)
            data["events"].append(e); existing_ids.add(iid); added += 1
            print(f"  {sym.get(v,'?')} [{v}] @{e['agent']} m/{e['submolt']}")
    for tid in data.get("threads_seeded", []):
        for item in get_thread_replies(tid):
            iid = str(item.get("id",""))
            if iid in existing_ids: continue
            item["thread_id"] = tid
            e = parse_item(item, "reply")
            e["terms"] = [t for t in TRACKED_TERMS if t in e["text"].lower()]
            data["events"].append(e); existing_ids.add(iid); added += 1
            print(f"  ↩ [reply] @{e['agent']}")
    data["last_scan"] = datetime.now(timezone.utc).isoformat()
    data["total_scans"] = data.get("total_scans",0) + 1
    compute_stats(data)
    save(data)
    print(f"[scan] +{added} events. Total: {len(data['events'])}")
    return added

def seed_injection(data):
    submolt = input("Submolt: ").strip()
    thread_id = input("Thread ID: ").strip()
    text = input("Reply text: ").strip()
    now = datetime.now(timezone.utc).isoformat()
    e = {"id":f"injection_{now}","agent":OUR_AGENT,"submolt":submolt,"thread_id":thread_id,
         "text":text[:300],"timestamp":now,"vector":"self","upvotes":0,"replies":0,"url":"",
         "terms":[t for t in TRACKED_TERMS if t.lower() in text.lower()],"hop_distance":0}
    data["events"].append(e)
    data["injection"] = {"timestamp":now,"submolt":submolt,"thread_id":thread_id}
    if thread_id: data["threads_seeded"].append(thread_id)
    save(data)
    print(f"[scan] Injection recorded: m/{submolt}")

def git_push():
    try:
        subprocess.run(["git","add",OUTPUT_FILE], cwd=REPO_ROOT, check=True)
        subprocess.run(["git","commit","-m",f"propagation: {datetime.now().strftime('%Y%m%d_%H%M')}"],
                       cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git","push"], cwd=REPO_ROOT, check=True)
        print("[scan] Pushed.")
    except: print("[scan] Nothing to push.")

def main():
    push = "--push" in sys.argv
    cron = "--cron" in sys.argv
    data = load()
    if "--seed" in sys.argv:
        seed_injection(data)
        if push: git_push()
        return
    if cron:
        print(f"[scan] Cron: every {SCAN_INTERVAL}s")
        while True:
            try:
                a = scan_once(load())
                if push and a > 0: git_push()
                time.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt: break
    else:
        a = scan_once(data)
        if push and a > 0: git_push()

if __name__ == "__main__":
    main()
