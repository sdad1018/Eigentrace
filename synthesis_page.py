#!/usr/bin/env python3
"""
synthesis_page.py -- renders a synthesis JSON as a self-contained HTML page.

Original article and the Claude VF-IDF synthesis side by side, with
FOREGROUND words highlighted in both columns, EXPAND words in the
synthesis, planted controls flagged with their evidence sentence, and
the measured tables underneath in the EigenTrace measured/argued idiom.

Reads the v1.1 synthesis JSON (which embeds source + article); writes
{sid}_synthesis.html next to it. No JS, no external assets -- one file,
openable anywhere, pasteable into eigentrace.ai.

    python3 synthesis_page.py anamnesis_results/universal/prelude_2026_synthesis.json
"""

VERSION = "synthesis_page v1.0 2026-07-10"

import argparse
import html
import json
import os
import re

CSS = """
:root { --fg:#fff3bf; --ex:#d3f9d8; --plant:#ffe3e3; --line:#d0d0d0;
        --ink:#1a1a1a; --dim:#666; }
* { box-sizing:border-box; }
body { font-family: Georgia, 'Times New Roman', serif; color:var(--ink);
       max-width:1160px; margin:2.2rem auto; padding:0 1.2rem;
       line-height:1.55; background:#fdfdfc; }
h1 { font-size:1.5rem; margin:.2rem 0 .1rem; }
.sub { color:var(--dim); font-size:.86rem; margin-bottom:1.4rem; }
.verdict { display:inline-block; padding:.15rem .6rem; border-radius:3px;
           font-family:monospace; font-size:.82rem; margin-left:.6rem; }
.pass { background:var(--ex); } .flag { background:var(--plant); }
.cols { display:grid; grid-template-columns:1fr 1fr; gap:1.4rem; }
.col { border:1px solid var(--line); border-radius:4px; padding:1rem 1.2rem;
       background:#fff; }
.col h2 { font-size:.8rem; letter-spacing:.12em; text-transform:uppercase;
          color:var(--dim); margin:0 0 .8rem; font-family:monospace; }
.col p { margin:.7rem 0; font-size:.95rem; }
mark { padding:0 .12em; border-radius:2px; }
mark.fg { background:var(--fg); } mark.ex { background:var(--ex); }
mark.plant { background:var(--plant); font-weight:bold; }
.legend { font-size:.8rem; color:var(--dim); margin:.7rem 0 1.6rem;
          font-family:monospace; }
.legend mark { margin-right:.9rem; }
section.meas { margin-top:2rem; border-top:2px solid var(--ink);
               padding-top:.8rem; }
section.meas h2 { font-family:monospace; font-size:.85rem;
                  letter-spacing:.1em; }
table { border-collapse:collapse; font-family:monospace; font-size:.82rem;
        margin:.6rem 0 1.2rem; }
td, th { padding:.22rem .8rem .22rem 0; text-align:left;
         border-bottom:1px solid #eee; }
th { color:var(--dim); font-weight:normal; }
.collapsed { color:#2b8a3e; font-weight:bold; }
.argued { background:#f4f2ec; border-left:3px solid #bbb;
          padding:.7rem 1rem; font-size:.92rem; margin:1rem 0; }
footer { margin-top:2rem; color:var(--dim); font-size:.78rem;
         font-family:monospace; border-top:1px solid var(--line);
         padding-top:.6rem; }
"""


def paragraphs(text):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts or [text.strip()]


def highlight(text, groups):
    """groups: list of (words, cls), longest patterns first, one pass."""
    esc = html.escape(text)
    pats = []
    for words, cls in groups:
        for w in words:
            pats.append((str(w), cls))
    pats.sort(key=lambda p: -len(p[0]))
    if not pats:
        return esc
    lookup = {}
    alts = []
    for w, cls in pats:
        key = w.lower()
        if key in lookup:
            continue
        lookup[key] = cls
        alts.append(re.escape(html.escape(w)) + r"(?:s|es|ing|ed)?")
    rx = re.compile(r"\b(" + "|".join(alts) + r")\b", re.I)

    def sub(m):
        tok = m.group(1)
        base = tok.lower()
        cls = None
        for key, c in lookup.items():
            if base.startswith(key.split()[0][:4].lower()) and \
               (key in base or base in key or base.startswith(key)):
                cls = c
                break
        cls = cls or next(iter(lookup.values()))
        # precise pass: exact/prefix match wins
        for key, c in lookup.items():
            if base == key or base.rstrip("sgnide") == key.rstrip("sgnide"):
                cls = c
                break
        return f'<mark class="{cls}">{tok}</mark>'
    return rx.sub(sub, esc)


def col_html(title, text, groups):
    body = "".join(f"<p>{highlight(p, groups)}</p>"
                   for p in paragraphs(text))
    return (f'<div class="col"><h2>{html.escape(title)}</h2>{body}</div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rep = json.load(open(args.json_path, encoding="utf-8"))
    if "source" not in rep or "article" not in rep:
        raise SystemExit("this JSON predates v1.1 (no embedded source/"
                         "article) -- re-run synthesis.py v1.1 first")

    sid = rep.get("story", "?")
    prov = rep.get("provenance", {})
    fg_words = [r["concept"] for r in rep.get("foreground", [])]
    ex_words = list(rep.get("expand", []))
    plants = list(prov.get("plants", []))
    pc = rep.get("planted_control", {})
    adopted_plants = pc.get("adopted", [])
    verdict = pc.get("verdict", "?")
    vcls = "pass" if verdict == "PASSED" else "flag"
    ad = rep.get("adoption", {})

    src_groups = [(fg_words, "fg")]
    syn_groups = [(adopted_plants, "plant"), (ex_words, "ex"),
                  (fg_words, "fg")]

    rows_before = rep.get("vfidf_before") or []
    rows_after = {r["concept"]: r for r in (rep.get("vfidf_after") or [])}
    fg_table = ["<table><tr><th>concept</th><th>vf</th><th>cos</th>"
                "<th>lex</th><th>VF-IDF before</th><th>after</th>"
                "<th></th></tr>"]
    for r in rows_before:
        a = rows_after.get(r["concept"])
        av = f"{a['vfidf']:.3f}" if a else "&mdash;"
        tag = ""
        if a is not None:
            coll = a["vfidf"] < max(0.001, r["vfidf"] * 0.5)
            tag = ('<span class="collapsed">COLLAPSED</span>'
                   if coll else "kept")
        fg_table.append(
            f"<tr><td>{html.escape(r['concept'])}</td>"
            f"<td>{r['void_freq']:.2f}</td>"
            f"<td>{r.get('cos_ch', 0):.2f}</td>"
            f"<td>{r.get('lex_ch', 0):.2f}</td>"
            f"<td>{r['vfidf']:.3f}</td><td>{av}</td><td>{tag}</td></tr>")
    fg_table.append("</table>")

    ex_table = ["<table><tr><th>concept</th><th>in synthesis</th>"
                "<th>survived new summaries</th></tr>"]
    for r in rep.get("expand_results", []):
        surv = (f"{r['survived']}/{r['of']}" if r.get("survived")
                is not None else "&mdash;")
        ex_table.append(
            f"<tr><td>{html.escape(str(r['concept']))}</td>"
            f"<td>{'yes' if r.get('in_synthesis') else 'no'}</td>"
            f"<td>{surv}</td></tr>")
    ex_table.append("</table>")

    plant_ev = "".join(
        f"<p><mark class='plant'>{html.escape(p)}</mark> &mdash; "
        f"&ldquo;{html.escape(s)}&rdquo;</p>"
        for p, s in (pc.get("evidence") or {}).items())

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Synthesis :: {html.escape(sid)}</title><style>{CSS}</style></head>
<body>
<h1>The Anti-Summary <span class="verdict {vcls}">audit: {html.escape(verdict)}</span></h1>
<div class="sub">{html.escape(sid)} &middot; thesis + measured antithesis
&rarr; synthesis &middot; model: {html.escape(str(prov.get('model','?')))}
temp={prov.get('temperature','?')} (the one non-frozen stage, declared)
&middot; {html.escape(str(rep.get('generated','')))}</div>
<div class="legend"><mark class="fg">FOREGROUND</mark> source-salient,
dropped by every AI summary (VF-IDF) &nbsp;
<mark class="ex">EXPAND</mark> centipede shared-core voids &nbsp;
<mark class="plant">PLANTED CONTROL</mark> deterministic audit word</div>
<div class="cols">
{col_html('Original (thesis)', rep['source'], src_groups)}
{col_html('Synthesis (the anti-summary)', rep['article'], syn_groups)}
</div>
<section class="meas"><h2>MEASURED</h2>
<p>Adoption: <b>{len(ad.get('adopted', []))}/{len(ad.get('adopted', []))
+ len(ad.get('missed', []))}</b> real candidates verified present
(word-boundary stem match, not the model's own claim).
Missed: {html.escape(', '.join(ad.get('missed', [])) or 'none')}.</p>
<p>Planted control: <b>{html.escape(verdict)}</b>.</p>
{plant_ev}
<h2>FOREGROUND VF-IDF &mdash; verbatim metric
(fidelity = max(cosine, lexical), best across summaries)</h2>
{''.join(fg_table)}
<h2>EXPAND &mdash; adoption and survival
(before is 0 by construction: not in source)</h2>
{''.join(ex_table)}
</section>
<div class="argued"><b>Argued.</b> A FOREGROUND concept that COLLAPSED
became un-droppable: the synthesis made it load-bearing enough that the
AI layer now carries it. An EXPAND concept that survived entered the
model-mediated version of this topic where before it did not exist.
Whether that visibility converts is the untested half &mdash; nobody has
that outcome data yet, which is the point of measuring first.</div>
<footer>{html.escape(rep.get('version',''))} &middot;
centipede sha {html.escape(str(prov.get('centipede_sha')))} &middot;
source sha {html.escape(str(prov.get('source_sha')))} &middot;
plants keyed by story sha, no RNG &middot; EigenTrace</footer>
</body></html>"""

    out = args.out or os.path.splitext(args.json_path)[0] + ".html"
    open(out, "w", encoding="utf-8").write(doc)
    print(f"HTML -> {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
