#!/usr/bin/env python3
"""Dump every aired beat, verbatim, as plain text: one file per broadcast day plus an index.

The player speaks segment JSON `beats` verbatim (think blocks included), so this IS the aired
narration. Output is private (article-derived text): ~/eigentrace/dataset/narration/.
Usage: python3 tools/narration_corpus.py [--since YYYYMMDD] [--out DIR]
"""
import argparse, json, os, re, sys, time
SEG = "/home/remvelchio/eigentrace/tmp/segments"
STORY = re.compile(r"^(\d{8})_(\d{6})_([0-9a-f]{12})_segment\.json$")
OTHER = re.compile(r"^(\d{8})_(\d{6})_([a-z_]+)_segment\.json$")
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--since", default="00000000"); ap.add_argument("--out", default="/home/remvelchio/eigentrace/dataset/narration")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    names = sorted(n for n in os.listdir(SEG) if n.endswith("_segment.json") and n[:8] >= a.since)
    files = {}; index = open(os.path.join(a.out, "index.tsv"), "w", encoding="utf-8")
    index.write("date\ttime\ttype\tsegment\tbeats\tchars\ttitle\n"); n_seg = n_beat = 0
    for n in names:
        m = STORY.match(n) or OTHER.match(n)
        if not m: continue
        day, tm, kind = m.group(1), m.group(2), ("story" if STORY.match(n) else m.group(3))
        try: s = json.load(open(os.path.join(SEG, n), encoding="utf-8"))
        except Exception: continue
        kind = s.get("segment_type") or kind; beats = s.get("beats") or []
        title = (s.get("story_title") or (s.get("attribution") or {}).get("story_title") or "")[:120]
        fh = files.get(day)
        if fh is None: fh = files[day] = open(os.path.join(a.out, f"narration_{day}.txt"), "w", encoding="utf-8")
        fh.write(f"\n=== {n} | {kind} | {title} | aired-order-by-name\n")
        chars = 0
        for b in beats:
            t = (b.get("text") or "").strip()
            if not t: continue
            fh.write(f"[{b.get('speaker','Host')} / {b.get('phase','')}] {t}\n"); chars += len(t); n_beat += 1
        index.write(f"{day}\t{tm}\t{kind}\t{n}\t{len(beats)}\t{chars}\t{title}\n"); n_seg += 1
    for fh in files.values(): fh.close()
    index.close(); print(f"segments {n_seg}, beats {n_beat}, days {len(files)} -> {a.out}")
if __name__ == "__main__": main()
