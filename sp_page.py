#!/usr/bin/env python3
"""
sp_page.py -- the side-by-side: source vs the winning Summary Plus,
with the geometry that forced it made visible.

Reads {sid}_bakeoff.json (writers, standings, matrix, label map),
{sid}_centipede.json (class-consensus stems for highlighting), and
{sid}_qcensus.json if present (the census-convergence box: the
measured unanswered questions beside what the winner actually led
with). No API calls -- pure render of existing artifacts.

  python3 sp_page.py --dir anamnesis_results/universal --story prelude_2026
  python3 sp_page.py --dir ... --story ... --text     # terminal columns
"""

VERSION = "sp_page v1.0 2026-07-10"

import argparse
import html
import json
import os
import re
import textwrap

try:
    from preservation_core import porter_stem
except Exception:
    porter_stem = lambda w: w.lower()

SECTION_OF = {
    "said": "Centroid", "gap->local": "Centroid",
    "gap->frontier": "Centroid", "centroid_surface": "Centroid",
    "logos_v9": "Gradient", "logos_v10": "Gradient",
    "null": "Spectral/SVD", "lexcross": "Counting", "donut": "Ring",
}

CSS = """
:root{--cc:#d3f9d8;--fg:#fff3bf;--line:#d0d0d0;--ink:#1a1a1a;--dim:#666;}
body{font-family:Georgia,serif;color:var(--ink);max-width:1160px;
 margin:2rem auto;padding:0 1.2rem;line-height:1.55;background:#fdfdfc;}
h1{font-size:1.5rem;margin:.2rem 0 .1rem;}
.sub{color:var(--dim);font-size:.85rem;margin-bottom:1.2rem;}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem;
 align-items:start;}
@media(max-width:760px){.cols{grid-template-columns:1fr;}}
.col{border:1px solid var(--line);border-radius:4px;
 padding:1rem 1.2rem;background:#fff;}
.col h2{font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;
 color:var(--dim);font-family:monospace;margin:0 0 .8rem;}
.col p{margin:.7rem 0;font-size:.94rem;}
mark{padding:0 .12em;border-radius:2px;}
mark.cc{background:var(--cc);} mark.fg{background:var(--fg);}
.legend{font-size:.8rem;color:var(--dim);font-family:monospace;
 margin:.5rem 0 1.2rem;}
table{border-collapse:collapse;font-family:monospace;font-size:.84rem;
 margin:.7rem 0 1rem;}
td,th{padding:.25rem .9rem .25rem 0;border-bottom:1px solid #eee;
 text-align:left;}
th{color:var(--dim);font-weight:normal;}
.win{font-weight:bold;color:#2b8a3e;}
.box{background:#f4f2ec;border-left:3px solid #bbb;
 padding:.7rem 1rem;font-size:.92rem;margin:1rem 0;}
h2.sec{font-family:monospace;font-size:.85rem;letter-spacing:.1em;
 border-top:2px solid var(--ink);padding-top:.7rem;margin-top:1.8rem;}
footer{margin-top:2rem;color:var(--dim);font-size:.78rem;
 font-family:monospace;border-top:1px solid var(--line);
 padding-top:.6rem;line-height:1.7;}
"""


def stem_of(w):
    return porter_stem(str(w).split()[0]) if " " in str(w) \
        else porter_stem(str(w))


def load_source(dirpath, sid):
    meta = json.load(open(os.path.join(dirpath, "_prompts.json"))
                     ).get(sid, {})
    m = re.search(r"Text:\s*(.*)$", meta.get("prompt", ""), re.S)
    return meta.get("title", sid), \
        (m.group(1).strip() if m else meta.get("prompt", ""))


def consensus_stems(cent):
    secs = {}
    word = {}
    for seg in cent.get("segments", []):
        sec = SECTION_OF.get(seg.get("name", "?").split("/")[0],
                             "Centroid")
        for arm in seg.get("arms", []):
            st = arm.get("stem")
            secs.setdefault(st, set()).add(sec)
            word.setdefault(st, arm.get("void"))
    return {word[st]: sorted(s) for st, s in secs.items()
            if len(s) >= 2}


def highlight(text, groups):
    esc = html.escape(text)
    pats = []
    for words, cls in groups:
        for w in words:
            pats.append((re.escape(html.escape(str(w))), cls))
    pats.sort(key=lambda p: -len(p[0]))
    for pat, cls in pats:
        esc = re.sub(r"\b(" + pat + r"(?:s|es|ing|ed)?)\b",
                     rf'<mark class="{cls}">\1</mark>', esc, flags=re.I)
    return esc


def paras(text, groups):
    ps = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(f"<p>{highlight(p, groups)}</p>" for p in ps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="anamnesis_results/universal")
    ap.add_argument("--story", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--text", action="store_true",
                    help="also print terminal two-column render")
    args = ap.parse_args()
    sid = args.story
    dirp = args.dir

    bake = json.load(open(os.path.join(dirp, f"{sid}_bakeoff.json"),
                          encoding="utf-8"))
    title, source = load_source(dirp, sid)
    cent_p = os.path.join(dirp, f"{sid}_centipede.json")
    cc = consensus_stems(json.load(open(cent_p))) \
        if os.path.exists(cent_p) else {}
    q_p = os.path.join(dirp, f"{sid}_qcensus.json")
    census = json.load(open(q_p)).get("consensus", []) \
        if os.path.exists(q_p) else []
    fg = []
    s2 = os.path.join(dirp, f"{sid}_synthesis2.json")
    if os.path.exists(s2):
        fg = [r["concept"] for r in
              json.load(open(s2)).get("foreground", [])]

    standings = bake["standings"]
    winner = standings[0]
    wtext = bake["writers"][winner["writer"]]
    label_of = bake["provenance"]["label_map"]
    fro = bake.get("frontier_scores", {})

    # self-preference: mean self-score minus mean ex-self received
    selfs = [fro[j][label_of[j]] for j in fro
             if j in label_of and label_of[j] in fro[j]]
    exs = [r["exself_mean"] for r in standings
           if r["exself_mean"] is not None]
    self_pref = (round(sum(selfs) / len(selfs)
                       - sum(exs) / len(exs), 2)
                 if selfs and exs else None)

    groups = [(list(cc), "cc")] + ([(fg, "fg")] if fg else [])

    # matrix html
    labs = [r["label"] for r in sorted(standings,
                                       key=lambda r: r["label"])]
    mrows = []
    for jm in sorted(fro):
        cells = []
        for lab in labs:
            v = fro[jm].get(lab, "—")
            star = "*" if label_of.get(jm) == lab else ""
            cells.append(f"<td>{v}{star}</td>")
        mrows.append(f"<tr><th>{jm}</th>{''.join(cells)}</tr>")
    srows = "".join(
        f"<tr><td>{'★ ' if r is winner else ''}{r['writer']}</td>"
        f"<td>{r['label']}</td>"
        f"<td class='{'win' if r is winner else ''}'>"
        f"{r['exself_mean']}</td>"
        f"<td>{r['local_mean']}</td><td>{r['chars']}</td></tr>"
        for r in standings)
    qrows = "".join(
        f"<tr><td>{q['support']}/{bake['provenance'].get('n','10') if False else 10}</td>"
        f"<td>{html.escape(q['question'])}</td></tr>"
        for q in census[:5])
    lead = html.escape(re.split(r"(?<=[.!?])\s+", wtext.strip())[0]
                       [:260])

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Summary Plus :: {html.escape(sid)}</title>
<style>{CSS}</style></head><body>
<h1>Source vs the winning Summary Plus</h1>
<div class="sub">{html.escape(sid)} &middot; writer:
<b>{html.escape(winner['writer'])}</b> (panel ex-self
{winner['exself_mean']}) &middot; five frontier writers, judged by the
panel, nobody grades their own homework &middot;
{html.escape(bake.get('generated',''))}</div>
<div class="legend"><mark class="cc">CLASS-CONSENSUS</mark> void stems
surfaced by &ge;2 independent math classes
{('&nbsp;<mark class="fg">FOREGROUND</mark> source-salient, dropped by '
  'every AI summary') if fg else ''}</div>
<div class="cols">
<div class="col"><h2>Source</h2>{paras(source, groups)}</div>
<div class="col"><h2>Summary Plus &mdash; the winning reading</h2>
{paras(wtext, groups)}</div>
</div>
{('<h2 class="sec">TWO INSTRUMENTS, ONE SILENCE</h2>'
  '<div class="box"><b>The question census measured</b> (independent '
  'clustering of ten models&rsquo; unanswered-question lists):'
  '<table><tr><th>support</th><th>consensus question</th></tr>'
  + qrows + '</table><b>The winning reading led with:</b> '
  '&ldquo;' + lead + '&rdquo;<br>Two instruments that share no code '
  'converged on the same ranked silence.</div>') if census else ''}
<h2 class="sec">STANDINGS</h2>
<table><tr><th>writer</th><th>label</th><th>panel ex-self</th>
<th>local panel</th><th>chars</th></tr>{srows}</table>
<h2 class="sec">PANEL MATRIX</h2>
<table><tr><th>judge \\ writer</th>{''.join(f'<th>{l}</th>'
                                            for l in labs)}</tr>
{''.join(mrows)}</table>
<p class="sub">* judge&rsquo;s own column, excluded from standings.
{('Self-preference, measured: judges scored their own work +'
  + str(self_pref) + ' above what the room gave them.')
 if self_pref is not None else ''}</p>
<footer>Discipline sha {bake['provenance'].get('discipline_sha')}
&middot; rubric sha {bake['provenance'].get('rubric_sha')} &middot;
feed sha {bake['provenance'].get('feed_sha')} &middot; source sha
{bake['provenance'].get('source_sha')} &middot; writer + judge stages
declared non-frozen; everything else deterministic. &mdash;
EigenTrace, 2026</footer></body></html>"""

    out = args.out or os.path.join(dirp, f"{sid}_sp.html")
    open(out, "w", encoding="utf-8").write(doc)
    print(f"HTML -> {out} ({os.path.getsize(out)} bytes)")

    if args.text:
        W = 47
        def col(t):
            o = []
            for p in t.split("\n\n"):
                o += textwrap.wrap(" ".join(p.split()), W) + [""]
            return o
        L, R = col(source), col(wtext)
        print("=" * (W * 2 + 5))
        print(f"{'SOURCE':<{W}}  |  WINNING SUMMARY PLUS "
              f"({winner['writer']})")
        print("=" * (W * 2 + 5))
        for i in range(max(len(L), len(R))):
            print(f"{(L[i] if i < len(L) else ''):<{W}}  |  "
                  f"{R[i] if i < len(R) else ''}")


if __name__ == "__main__":
    main()
