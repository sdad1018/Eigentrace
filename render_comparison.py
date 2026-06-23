#!/usr/bin/env python3
"""
render_comparison.py -- regenerate docs/comparison_all.html from the five-arm BOTH run.

Run on Bertha:
    cd /mnt/c/Users/M4ISI/eigentrace
    python3 render_comparison.py

Reads:  confront10_final_results.json   (has facts, concepts=flat, conv_novel=spiral, per-gen arms)
Writes: docs/comparison_all.html

What changed vs the stale page:
  - pairs are now BASELINE vs A_PLUS_BOTH (the two-derivation output), not BASELINE vs A_PLUS_C
  - each story header shows ALL THREE channels, labeled:
        Channel A (dropped facts) / C-flat (centroid) / C-spiral (convergence-novel)
    so the audit page itself shows the two SVD derivations, matching the product page
  - house style = the Iran Arc tokens (light paper, Iowan serif, measured/flat/spiral colors)
No new API calls, no regeneration — pure render of saved data.
"""
import json, html, os, sys

REPO = "/mnt/c/Users/M4ISI/eigentrace"
if os.path.isdir(REPO):
    os.chdir(REPO)

RESULTS = "confront10_final_results.json"
OUT = "docs/comparison_all.html"

SHAPE_LABEL = {
    "mexico_cia": "Sharp Silence",
    "russia_ukraine": "Still Point",
    "hezbollah": "Still Point",
    "hormuz_violation": "Unanimous Shield",
    "british_couple": "Clear Channel (null control)",
    "kim_troops": "Sharp Silence",
    "rail_incident": "Procedural (adversarial)",
}

CSS = """
:root{
  --ink:#1a1a18;--ink-soft:#4a4a45;--ink-faint:#7a7a72;
  --paper:#faf9f6;--surface:#ffffff;--line:rgba(26,26,24,0.12);--line-soft:rgba(26,26,24,0.07);
  --measured:#0f6e56;--measured-bg:#e1f5ee;--measured-line:#9fe1cb;
  --accent:#993c1d;
  --flat:#3b6ea5;--flat-bg:#e7eef6;
  --spiral:#7a3d8f;--spiral-bg:#f0e7f4;
  --mono:'SFMono-Regular',ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace;
  --serif:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
}
@media(prefers-color-scheme:dark){:root{
  --ink:#e8e6e0;--ink-soft:#b4b2a9;--ink-faint:#888780;
  --paper:#15140f;--surface:#1c1b16;--line:rgba(232,230,224,0.14);--line-soft:rgba(232,230,224,0.07);
  --measured:#5dcaa5;--measured-bg:#0c2a22;--measured-line:#0f6e56;--accent:#d85a30;
  --flat:#7da9d8;--flat-bg:#11243a;--spiral:#c08fd2;--spiral-bg:#2a1832;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.6;-webkit-font-smoothing:antialiased}
.nav{max-width:1040px;margin:0 auto;padding:22px 24px;display:flex;gap:22px;font-size:14px;color:var(--ink-faint);flex-wrap:wrap}
.nav a{color:var(--ink-faint);text-decoration:none}.nav a:hover{color:var(--ink)}.nav .home{color:var(--ink);font-weight:500}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px 110px}
header{padding:48px 0 32px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:0 0 18px}
h1{font-family:var(--serif);font-size:42px;line-height:1.06;font-weight:600;margin:0 0 16px;letter-spacing:-.01em}
.standfirst{font-family:var(--serif);font-size:20px;line-height:1.45;color:var(--ink-soft);font-style:italic;margin:0 0 8px;max-width:720px}
.backlink{display:inline-block;font-family:var(--mono);font-size:13.5px;color:var(--accent);text-decoration:none;margin-top:18px;border-bottom:1px solid var(--accent);padding-bottom:1px}
.backlink:hover{color:var(--ink);border-color:var(--ink)}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-family:var(--mono);font-size:12px;color:var(--ink-soft);margin:26px 0 0}
.legend span{display:flex;align-items:center;gap:7px}
.legend .sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.story{margin:54px 0 0}
.story h2{font-family:var(--serif);font-size:26px;font-weight:600;margin:0 0 4px;letter-spacing:-.01em}
.story .shape{font-family:var(--mono);font-size:12.5px;color:var(--ink-faint);letter-spacing:.04em;margin-bottom:16px}
.channels{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 22px}
.chan{flex:1;min-width:210px;border:1px solid var(--line);border-radius:10px;padding:13px 16px;background:var(--surface)}
.chan .cn{font-family:var(--mono);font-size:11.5px;font-weight:600;letter-spacing:.04em;display:flex;align-items:center;gap:8px;margin-bottom:9px}
.chan .cd{width:9px;height:9px;border-radius:2px;display:inline-block;flex:none}
.chan.a .cd{background:var(--accent)} .chan.a .cn{color:var(--accent)}
.chan.flat .cd{background:var(--flat)} .chan.flat .cn{color:var(--flat)}
.chan.spiral .cd{background:var(--spiral)} .chan.spiral .cn{color:var(--spiral)}
.chan .ws{display:flex;flex-wrap:wrap;gap:6px}
.chan .w{font-family:var(--mono);font-size:12px;padding:2px 8px;border-radius:5px;background:var(--bound-bg,#f1efe8);color:var(--ink-soft)}
.chan.a .w{background:#f7ece6;color:var(--accent)}
.chan.flat .w{background:var(--flat-bg);color:var(--flat)}
.chan.spiral .w{background:var(--spiral-bg);color:var(--spiral);font-weight:600}
.chan .none{font-family:var(--mono);font-size:12px;color:var(--ink-faint);font-style:italic}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:0 0 14px}
.cell{border:1px solid var(--line-soft);border-radius:10px;padding:15px 18px;background:var(--surface);font-size:15px;line-height:1.55;color:var(--ink-soft)}
.cell.base{border-style:dashed}
.cell.plus{border-color:var(--measured-line)}
.cell h3{font-family:var(--mono);font-size:11.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;margin:0 0 9px;color:var(--ink-faint)}
.cell.plus h3{color:var(--measured)}
.cell strong{color:var(--ink);font-weight:600}
footer{margin-top:72px;padding-top:24px;border-top:1px solid var(--line);font-family:var(--mono);font-size:13px;color:var(--ink-faint);line-height:1.7}
footer a{color:var(--accent);text-decoration:none}footer a:hover{color:var(--ink)}
@media(max-width:680px){.pair{grid-template-columns:1fr}h1{font-size:34px}}
"""

def esc(s):
    return html.escape(s or "").replace("\n", " ").strip()

def words(lst, novel_cls=False):
    if not lst:
        return '<span class="none">— none —</span>'
    cls = ' class="w"'
    return "".join(f'<span{cls}>{esc(w)}</span>' for w in lst)

def main():
    if not os.path.exists(RESULTS):
        print(f"ERROR: {RESULTS} not found in {os.getcwd()}", file=sys.stderr)
        return 1
    data = json.load(open(RESULTS))

    parts = []
    n_pairs = 0
    for o in data:
        sid = o.get("story", "?")
        facts = o.get("facts", []) or []
        flat = o.get("concepts", []) or []          # Channel C-flat (centroid)
        spiral = o.get("conv_novel", []) or []        # Channel C-spiral (convergence-novel)
        shape = o.get("shape") or SHAPE_LABEL.get(sid, "")

        parts.append(f'<div class="story"><h2>{esc(sid)}</h2>')
        parts.append(f'<div class="shape">{esc(shape)}</div>')

        # the three channels, labeled — the two SVD derivations made visible
        parts.append('<div class="channels">')
        parts.append(
            '<div class="chan a"><div class="cn"><span class="cd"></span>Channel A · dropped facts</div>'
            f'<div class="ws">{words(facts)}</div></div>'
        )
        parts.append(
            '<div class="chan flat"><div class="cn"><span class="cd"></span>C-flat · centroid raycast</div>'
            f'<div class="ws">{words(flat)}</div></div>'
        )
        parts.append(
            '<div class="chan spiral"><div class="cn"><span class="cd"></span>C-spiral · convergence (novel)</div>'
            f'<div class="ws">{words(spiral)}</div></div>'
        )
        parts.append('</div>')

        # pairs: BASELINE vs A_PLUS_BOTH, one per generation that has both
        for row in o.get("rows", []):
            patient = row.get("patient", "?")
            for k, g in enumerate(row.get("gens", [])):
                base = g.get("BASELINE")
                both = g.get("A_PLUS_BOTH")
                if not base or not both:
                    continue
                n_pairs += 1
                parts.append('<div class="pair">')
                parts.append(
                    f'<div class="cell base"><h3>{esc(patient)} · k{k} · baseline</h3>{esc(base)}</div>'
                )
                parts.append(
                    f'<div class="cell plus"><h3>{esc(patient)} · k{k} · Summary Plus (A + both derivations)</h3>{esc(both)}</div>'
                )
                parts.append('</div>')

        parts.append('</div>')  # .story

    body = "\n".join(parts)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Summary Plus — Every Pair, Side by Side · EigenTrace</title>
<meta name="description" content="The full audit: seven real news stories, each summarized plainly and through Summary Plus, side by side. Both SVD derivations of the negative space shown per story. Judge for yourself.">
<link rel="canonical" href="https://eigentrace.ai/comparison_all">
<meta name="robots" content="index, follow">
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
  <a href="/" class="home">EigenTrace</a>
  <a href="/summary-plus">Summary Plus</a>
  <a href="/anamnesis">Anamnesis</a>
  <a href="/llm-consensus-geometry-iran-2026">Iran Arc</a>
  <a href="https://github.com/sdad1018/Eigentrace" target="_blank" rel="noopener">GitHub ↗</a>
</nav>
<div class="wrap">
<header>
  <p class="eyebrow">The full audit · {n_pairs} pairs · seven stories</p>
  <h1>Every pair, side by side</h1>
  <p class="standfirst">Each story summarized two ways: the plain relay, and the reading through Summary Plus. The three channels — the dropped facts and both geometric derivations of the negative space — are shown per story. Judge for yourself.</p>
  <a class="backlink" href="/summary-plus">← Back to Summary Plus</a>
  <div class="legend">
    <span><span class="sw" style="background:var(--accent)"></span>Channel A — dropped facts</span>
    <span><span class="sw" style="background:var(--flat)"></span>C-flat — centroid raycast</span>
    <span><span class="sw" style="background:var(--spiral)"></span>C-spiral — sentence convergence</span>
  </div>
</header>
{body}
<footer>
  Seven real news stories · five frontier models · frozen BAAI/bge-large-en-v1.5 · no language model evaluated another's output.<br><br>
  EigenTrace · <a href="/summary-plus">Summary Plus</a> · <a href="https://github.com/sdad1018/Eigentrace" target="_blank" rel="noopener">GitHub ↗</a> · MIT License · 2026
</footer>
</div>
</body>
</html>
"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {OUT}  ({n_pairs} pairs across {len(data)} stories, {len(page)} bytes)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
