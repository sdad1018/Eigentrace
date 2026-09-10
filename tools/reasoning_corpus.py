#!/usr/bin/env python3
"""Extract the producer's pre-aired reasoning from producer logs (current + archived .gz):
director theses (multi-line) and Mistral scratchpads, with timestamps and the nearest story title.
Output: ~/eigentrace/dataset/reasoning/producer_reasoning.jsonl (private).
Usage: python3 tools/reasoning_corpus.py [--out FILE]"""
import argparse, glob, gzip, json, os, re
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[(\w+)\] (\S+) — (.*)$")
SEGLINE = re.compile(r"Segment ([0-9a-f]{12}): \d+ beats for '(.+)'")
def lines():
    files = sorted(glob.glob("/mnt/c/Users/M4ISI/eigentrace_backups/logs_archive/producer.log.*.gz")) + ["/home/remvelchio/eigentrace/tmp/logs/producer.log"]
    for f in files:
        op = gzip.open if f.endswith(".gz") else open
        with op(f, "rt", encoding="utf-8", errors="replace") as fh:
            for l in fh: yield l.rstrip("\n")
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="/home/remvelchio/eigentrace/dataset/reasoning/producer_reasoning.jsonl")
    a = ap.parse_args(); os.makedirs(os.path.dirname(a.out), exist_ok=True)
    out = open(a.out, "w", encoding="utf-8"); cur = None; title = ""; n = {"director": 0, "scratchpad": 0}
    def flush():
        nonlocal cur
        if cur: out.write(json.dumps(cur, ensure_ascii=False) + "\n"); n[cur["kind"]] += 1; cur = None
    for l in lines():
        m = TS.match(l)
        if m:
            flush(); ts, lvl, mod, msg = m.groups(); msg = msg.strip()
            sm = SEGLINE.search(msg)
            if sm: title = sm.group(2)
            if msg.startswith("Director: "): cur = {"ts": ts, "kind": "director", "story_title_hint": title, "text": msg[len("Director: "):]}
            elif msg.startswith("[SCRATCHPAD]"): cur = {"ts": ts, "kind": "scratchpad", "story_title_hint": title, "text": msg[len("[SCRATCHPAD]"):].strip(), "truncated_in_log": msg.endswith("...")}
        elif cur is not None:
            cur["text"] += "\n" + l   # continuation line of a multi-line director note
    flush()
    # full-text records kept by reasoning_log.py since 2026-09-10; the log-derived rows above are
    # truncated (80 chars of director note, 200 of scratchpad) because that is all the log ever held
    full = 0
    for f in sorted(glob.glob("/home/remvelchio/eigentrace/tmp/reasoning/reasoning_*.jsonl")):
        for l in open(f, encoding="utf-8"):
            try: row = json.loads(l)
            except Exception: continue
            row["source"] = "reasoning_log"; out.write(json.dumps(row, ensure_ascii=False) + "\n"); full += 1
    out.close(); print(f"director notes {n['director']}, scratchpads {n['scratchpad']} (log-derived, truncated) + {full} full-text records -> {a.out}")
if __name__ == "__main__": main()
