#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reading_page.py -- render the Summary Plus instrument page from artifacts.

VERSION = "reading_page v3.2 2026-07-10"

Reads (STOP if a required file is missing):
  {dir}/{sid}_bakeoff_v12.json    panel, audits, essays, provenance   [required]
  {dir}/{sid}_centipede.json      segments: class-consensus, arm stats [required]
  {dir}/{sid}_qcensus.json        question census clusters             [required]
  {dir}/{sid}_synthesis2.json     FOREGROUND / plants                  [optional]
  {dir}/{sid}_synthesis.json      run-1 trajectories (rerun note)      [optional]
  {dir}/_prompts.json             source text after 'Text:'            [required]
  {dir}/{sid}_judge_*.txt         per-cell reasons, content-verified   [optional]
  bakeoff2.py                     canonical parse_ledger / audit_ledger
                                  + SP_DISCIPLINE / JUDGE_RUBRIC verbatim

Hard gates (no output file written on failure):
  G1  >= 2 frontier judges in the v12 panel
  G2  no unreplaced @@TOKEN@@ or '{{' survives to disk
  G3  ledger rows rendered == winner audit n (generator-counted)
  G6  a) recomputed ex-self means == standings
      b) recomputed winner audit == stored audit (determinism)
      c) per-row singleton verdicts reconcile to aggregates
  GS  displayed discipline/rubric sha12 == provenance shas
Soft gates (pick copy variants; always reported):
  G4  census top-3 stem overlap with winner lead -> strong/soft banner
  G5  n_paras < 3 -> whole-document trace-granularity caveat
  G7  all consensus pairs Centroid+Gradient -> shared-init disclosure
"""
VERSION = "reading_page v3.2 2026-07-10"

import argparse
import ast
import hashlib
import html
import json
import os
import re
import shutil
import sys
from collections import Counter


# ── helpers ─────────────────────────────────────────────────────────
def sha12(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hashlib.sha256(b).hexdigest()[:12]


def esc(x):
    return html.escape(str(x), quote=True)


GATES = []


def report(line):
    print("REPORT  " + line)


def gate(name, ok, detail=""):
    GATES.append((name, bool(ok)))
    print("GATE %-4s %s  %s" % (name, "PASS" if ok else "FAIL", detail))
    return bool(ok)


def pm(x):
    return ("+" if x >= 0 else "\u2212") + ("%.2f" % abs(x))


def ordinal(n):
    return {1: "first", 2: "second", 3: "third",
            4: "fourth", 5: "fifth"}.get(n, "%dth" % n)


try:
    from preservation_core import porter_stem
except Exception as e:                                       # pragma: no cover
    sys.exit("STOP: preservation_core import failed: %s" % e)


def stem_norm(tok):
    t = re.sub(r"[^a-z]", "", str(tok).lower())
    return porter_stem(t) if t else ""


WORD = r"[A-Za-z][A-Za-z'\u2019\-]*"


def stems_of(text):
    return {stem_norm(w) for w in re.findall(WORD, text)} - {""}


# ── canonical auditor + verbatim prompts, from bakeoff2.py ─────────
def load_auditor(path="bakeoff2.py"):
    if not os.path.exists(path):
        sys.exit("STOP: %s not found (needed for canonical audit + prompts)" % path)
    src = open(path, encoding="utf-8").read()
    names = ("parse_ledger", "audit_ledger", "SP_DISCIPLINE", "JUDGE_RUBRIC")
    ns = {}
    try:
        import importlib.util
        argv, sys.argv = sys.argv, ["bakeoff2"]
        try:
            spec = importlib.util.spec_from_file_location("bakeoff2_mod", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            ns = {k: getattr(mod, k) for k in names if hasattr(mod, k)}
        finally:
            sys.argv = argv
    except BaseException as e:
        print("  (import path failed: %s: %s -- ast fallback)"
              % (type(e).__name__, str(e)[:60]))
    if len(ns) < len(names):
        tree = ast.parse(src)
        keep = []
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                keep.append(n)
            elif isinstance(n, ast.FunctionDef) and n.name in names:
                keep.append(n)
            elif isinstance(n, ast.Assign) and any(
                    getattr(t, "id", "") in names for t in n.targets):
                keep.append(n)
        mod_ast = ast.Module(body=keep, type_ignores=[])
        ast.fix_missing_locations(mod_ast)
        g = {}
        exec(compile(mod_ast, path, "exec"), g)        # noqa: S102
        ns = {k: g[k] for k in names if k in g}
    missing = [k for k in names if k not in ns]
    if missing:
        sys.exit("STOP: could not obtain %s from %s" % (missing, path))
    return ns


def parse_scores(text):
    """Verbatim replica of bakeoff2's nested parser (not importable)."""
    got = {}
    for lab, val in re.findall(r"\b([A-E])\s*[:=]\s*([1-5])\b", text):
        got.setdefault(lab, int(val))
    return got


# ── args + artifact loads ───────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="anamnesis_results/universal")
ap.add_argument("--story", required=True)
ap.add_argument("--out", default="docs/vf-idf.v2.html")
ap.add_argument("--contact", default="https://eigentrace.ai/")
ap.add_argument("--canonical", default="https://eigentrace.ai/vf-idf",
                help="canonical URL for rel=canonical + og:url")
ap.add_argument("--og-image", default="https://eigentrace.ai/og/vf-idf.png",
                help="absolute URL of the og/twitter card image")
ap.add_argument("--defect-num", default="52",
                help="defect-ledger number for tonight's entry; yours to assign")
args = ap.parse_args()
sid, D = args.story, args.dir


def need(p):
    if not os.path.exists(p):
        sys.exit("STOP: required file missing: %s" % p)
    return p


print("=" * 74)
print("READING PAGE  ::  %s  ::  %s" % (sid, VERSION))
print("=" * 74)

bake = json.load(open(need(os.path.join(D, sid + "_bakeoff_v12.json")),
                      encoding="utf-8"))
cent = json.load(open(need(os.path.join(D, sid + "_centipede.json")),
                      encoding="utf-8"))
qc = json.load(open(need(os.path.join(D, sid + "_qcensus.json")),
                    encoding="utf-8"))
p2 = os.path.join(D, sid + "_synthesis2.json")
p1 = os.path.join(D, sid + "_synthesis.json")
syn2 = json.load(open(p2, encoding="utf-8")) if os.path.exists(p2) else None
syn1 = json.load(open(p1, encoding="utf-8")) if os.path.exists(p1) else None
if syn2 is None:
    report("synthesis2.json absent -- FOREGROUND pane reduced")

meta = json.load(open(need(os.path.join(D, "_prompts.json")),
                      encoding="utf-8"))[sid]
msrc = re.search(r"Text:\s*(.*)$", meta["prompt"], re.S)
source = (msrc.group(1) if msrc else meta["prompt"]).strip()
paras = [p.strip() for p in re.split(r"\n\s*\n", source) if p.strip()]

# ── panel ───────────────────────────────────────────────────────────
prov = bake["provenance"]
label_of = prov["label_map"]                       # writer -> label
model_of = {v: k for k, v in label_of.items()}     # label  -> writer
labs = sorted(model_of)
fro = bake["frontier_scores"]
loc = bake["local_scores"]
standings = bake["standings"]
winner = standings[0]["writer"]
tie = bool(bake.get("tie_at_top"))

if not gate("G1", len(fro) >= 2,
            "frontier judges = %d %s" % (len(fro), sorted(fro))):
    sys.exit("STOP: panel gate failed -- page does not ship on n=%d" % len(fro))

col_ex = {}
for lab in labs:
    vals = [fro[j][lab] for j in fro if j != model_of[lab] and lab in fro[j]]
    col_ex[lab] = (round(sum(vals) / len(vals), 2) if vals else None, len(vals))
ok6a = True
for r in standings:
    mine = col_ex[r["label"]][0]
    if r["exself_mean"] is not None and (
            mine is None or abs(mine - r["exself_mean"]) > 0.005):
        ok6a = False
        report("MISMATCH ex-self %s: recomputed %s vs stored %s"
               % (r["writer"], mine, r["exself_mean"]))
if not gate("G6a", ok6a, "recomputed ex-self means == standings"):
    sys.exit("STOP: matrix and standings disagree")

selfpref = {}
for j in fro:
    lab = label_of.get(j)
    if lab and lab in fro[j] and col_ex[lab][0] is not None:
        selfpref[j] = round(fro[j][lab] - col_ex[lab][0], 2)
sp_mean = round(sum(selfpref.values()) / len(selfpref), 2) if selfpref else None
sp_sorted = sorted(selfpref.items(), key=lambda kv: -kv[1])
report("self-preference: " + ", ".join("%s %s" % (j, pm(v))
                                       for j, v in sp_sorted)
       + " | mean %s (n=%d)" % (pm(sp_mean), len(selfpref)))

loccov = {lab: sorted((j, loc[j][lab]) for j in loc if lab in loc[j])
          for lab in labs}
for lab in labs:
    report("locals coverage %s (%s): n=%d  %s"
           % (lab, model_of[lab], len(loccov[lab]),
              ", ".join("%s:%s" % t for t in loccov[lab]) or "--"))

# judge reasons: attach only when a file's parsed scores == the matrix
reasons, blanket = {}, {}
for j in sorted(set(list(fro) + list(loc))):
    f = os.path.join(D, "%s_judge_%s.txt" % (sid, j))
    if not os.path.exists(f):
        continue
    txt = open(f, encoding="utf-8", errors="replace").read()
    want = fro.get(j) or loc.get(j) or {}
    if parse_scores(txt) != want:
        report("judge file %s: parsed scores != matrix -- reasons skipped" % j)
        continue
    rmap, notes = {}, []
    for line in txt.splitlines():
        if len(re.findall(r"\b[A-E]\s*[:=]\s*[1-5]\b", line)) >= 3:
            continue                                  # the score line itself
        mm = re.match(r"\s*\**([A-E])\**\s*[:\-\u2013\u2014]\s*(.+)$", line)
        if mm:
            rmap[mm.group(1)] = mm.group(2).strip()
        elif line.strip():
            notes.append(line.strip())
    if rmap:
        reasons[j] = rmap
    elif notes:
        blanket[j] = " ".join(notes)[:400]
report("judge reasons: per-label %s | blanket %s"
       % (sorted(reasons) or "--", sorted(blanket) or "--"))

# ── winner ledger: canonical per-row verdicts ───────────────────────
A = load_auditor()
parse_ledger, audit_ledger = A["parse_ledger"], A["audit_ledger"]
SPD, RUB = A["SP_DISCIPLINE"], A["JUDGE_RUBRIC"]

wtxt = bake["writers"][winner]
prose = re.split(r"^LEDGER\s*:", wtxt, flags=re.M)[0].strip()
rows_raw = parse_ledger(wtxt)


def norm_row(r):
    if isinstance(r, dict):
        t = r.get("type") or r.get("typ") or r.get("t") or "?"
        return str(t).upper()[:1], str(r.get("claim", "")), str(r.get("refs", ""))
    if isinstance(r, (list, tuple)) and len(r) >= 3:
        return str(r[0]).upper()[:1], str(r[1]), str(r[2])
    sys.exit("STOP: unknown ledger row shape: %r" % (r,))


rows = [norm_row(r) for r in rows_raw]
full = audit_ledger(rows_raw, paras)
stored = bake["claim_audits"][winner]
KEYS = ["n", "F", "I", "S", "f_traced", "f_total",
        "absence_supported", "absence_contested", "bad_refs"]
same = all(full.get(k) == stored.get(k) for k in KEYS)
if not gate("G6b", same, "recomputed winner audit == stored  "
            + json.dumps({k: full.get(k) for k in KEYS})):
    sys.exit("STOP: audit determinism broken -- paste this output back")

verdicts = []
for orig, (t, claim, refs) in zip(rows_raw, rows):
    a1 = audit_ledger([orig], paras)
    if t == "F":
        if a1.get("absence_contested"):
            c = (a1.get("contested") or [{}])[0]
            verdicts.append(("CONTESTED", c.get("hits"), c.get("evidence")))
        elif a1.get("absence_supported"):
            verdicts.append(("SUPPORTED-ABSENT", None, None))
        elif a1.get("f_traced"):
            verdicts.append(("TRACED", None, None))
        else:
            verdicts.append(("UNTRACED", None, None))
    elif t == "I":
        verdicts.append(("BAD-REF" if a1.get("bad_refs") else "REF-OK",
                         None, None))
    else:
        verdicts.append(("HEDGED", None, None))

hist = Counter(v[0] for v in verdicts)
rec_ok = (hist["CONTESTED"] == full["absence_contested"]
          and hist["SUPPORTED-ABSENT"] == full["absence_supported"]
          and hist["TRACED"] + hist["SUPPORTED-ABSENT"] == full["f_traced"]
          and (hist["TRACED"] + hist["SUPPORTED-ABSENT"]
               + hist["UNTRACED"] + hist["CONTESTED"]) == full["f_total"]
          and hist["REF-OK"] + hist["BAD-REF"] == full["I"]
          and hist["HEDGED"] == full["S"])
if not gate("G6c", rec_ok, "per-row verdicts reconcile  " + str(dict(hist))):
    sys.exit("STOP: per-row reconciliation failed -- paste this output back")

# panel-wide decomposition (finding, not law: conditional copy)
allpos = alltr = abs_ok = abs_con = 0
positive_all_traced = True
for w, a in bake["claim_audits"].items():
    pos = a["F"] - a["absence_supported"] - a["absence_contested"]
    pos_tr = a["f_traced"] - a["absence_supported"]
    allpos += pos
    alltr += pos_tr
    abs_ok += a["absence_supported"]
    abs_con += a["absence_contested"]
    if pos_tr != pos:
        positive_all_traced = False
report("panel decomposition: positive %d/%d traced; absence %d ok / %d "
       "contested; all-positive-traced=%s"
       % (alltr, allpos, abs_ok, abs_con, positive_all_traced))

# ── consensus, classes, arm-A stat ──────────────────────────────────
SEC = {"said": "Centroid", "gap->local": "Centroid",
       "gap->frontier": "Centroid", "centroid_surface": "Centroid",
       "logos_v9": "Gradient", "logos_v10": "Gradient",
       "null": "Spectral", "lexcross": "Counting", "donut": "Ring"}
secs, wd = {}, {}
classes_present = set()
flat_key, tot_arms, flat_fired, flat_clean = None, 0, 0, 0
for seg in cent.get("segments", []):
    cls = SEC.get(str(seg.get("name", "")).split("/")[0], "Centroid")
    classes_present.add(cls)
    for a in seg.get("arms", []):
        st = a.get("stem")
        if st:
            secs.setdefault(st, set()).add(cls)
            wd.setdefault(st, a.get("void", st))
        if flat_key is None:
            for k, v in a.items():
                kl = str(k).lower()
                if isinstance(v, (list, dict)) and (
                        "flat" in kl or "conseq" in kl or "terminal" in kl
                        or kl in ("a", "arm_a", "a_terms")):
                    flat_key = k
                    break
        tot_arms += 1
        _v = a.get(flat_key) if flat_key else None
        if isinstance(_v, dict):
            if _v.get("terms"):
                flat_clean += 1
            if _v.get("terms") or _v.get("terms_raw"):
                flat_fired += 1
        elif isinstance(_v, list) and _v:
            flat_clean += 1
            flat_fired += 1
consensus = sorted(((wd[s], sorted(cl)) for s, cl in secs.items()
                    if len(cl) >= 2), key=lambda x: (-len(x[1]), x[0]))
n_classes = len(classes_present)
all_cg = bool(consensus) and all(cl == ["Centroid", "Gradient"]
                                 for _, cl in consensus)
gate("G7", True, "consensus=%d, all Centroid+Gradient=%s -> disclosure %s"
     % (len(consensus), all_cg, "ON" if all_cg else "off"))
report("class-consensus: " + ("; ".join(
    "%s (%d: %s)" % (w, len(cl), ", ".join(cl)) for w, cl in consensus)
    or "--"))
report("math classes present: %d = %s" % (n_classes, sorted(classes_present)))
if flat_key:
    report("arm-A stat: key '%s', clean %d/%d, raw %d/%d"
           % (flat_key, flat_clean, tot_arms, flat_fired, tot_arms))
else:
    report("arm-A stat: no flat-list key found in arms -- stat omitted")


def find_key(o, names, depth=0):
    if depth > 4:
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if k in names and isinstance(v, (int, float)):
                return v
        for v in o.values():
            r = find_key(v, names, depth + 1)
            if r is not None:
                return r
    if isinstance(o, list):
        for v in o[:8]:
            r = find_key(v, names, depth + 1)
            if r is not None:
                return r
    return None


bm = find_key(cent, {"body_median"})
nm = find_key(cent, {"null_median"})
margin = round(bm - nm, 3) if (bm is not None and nm is not None) else None
report("tonight's pricing: body_median=%s null_median=%s margin=%s"
       % (bm, nm, margin))

# ── census ──────────────────────────────────────────────────────────
def census_rows(q):
    pools = []
    if isinstance(q, list):
        pools.append(q)
    if isinstance(q, dict):
        pools += [v for v in q.values() if isinstance(v, list)]
    for pool in pools:
        rows_ = []
        for it in pool:
            if not isinstance(it, dict):
                break
            qt = it.get("question") or it.get("text") or it.get("q")
            if not qt:
                break
            sup = None
            for k in ("support", "n_models", "models", "count", "n"):
                v = it.get(k)
                if isinstance(v, int):
                    sup = v
                    break
                if isinstance(v, list):
                    sup = len(set(map(str, v)))
                    break
            rows_.append((sup if sup is not None else 0, str(qt)))
        if rows_ and any(s for s, _ in rows_):
            rows_.sort(key=lambda r: -r[0])
            return rows_
    return None


crows = census_rows(qc)
if not crows:
    sys.exit("STOP: census schema unrecognized: " + json.dumps(qc)[:400])
crows3 = [(s, q) for s, q in crows if s >= 3]
report("census: %d clusters, %d at >=3-model consensus"
       % (len(crows), len(crows3)))

# G4: census-lead overlap (soft, picks banner copy)
DROP = {"honda", "prelude", "the", "2026", "source", "document",
        "will", "what", "how", "much", "exactly", "new"}
drop_stems = {stem_norm(w) for w in DROP}


def content_stems(text):
    """G4 uses content words only (canonical stopword handling) --
    fix for the is/of leak caught by the v2.0 build report."""
    try:
        from preservation_core import content_words
        return {stem_norm(w) for w in content_words(text)} - {""}
    except Exception:
        return stems_of(text)
lead = prose.split("---")[0]
lead_stems = content_stems(lead)
hits = 0
for s, q in crows3[:3]:
    inter = sorted((content_stems(q) - drop_stems) & lead_stems)
    if inter:
        hits += 1
    report("  G4 [%d/10] %s -> %s" % (s, q[:46], inter or "no lexical hit"))
strong = hits >= 2
gate("G4", True, "census-lead overlap %d/3 -> %s banner"
     % (hits, "STRONG" if strong else "SOFT"))

g5 = len(paras) < 3
gate("G5", True, "n_paras=%d -> caveat %s" % (len(paras), "ON" if g5 else "off"))

# GS: displayed prompts cryptographically match the run
ds, rs = sha12(SPD), sha12(RUB)
if not gate("GS", ds == prov.get("discipline_sha")
            and rs == prov.get("rubric_sha"),
            "discipline %s vs %s | rubric %s vs %s"
            % (ds, prov.get("discipline_sha"), rs, prov.get("rubric_sha"))):
    sys.exit("STOP: displayed prompts would not match provenance shas")

# ── foreground / plants / rerun ─────────────────────────────────────
fg_rows, fg_concepts, fg_top = [], [], None
if syn2:
    fg = syn2.get("foreground") or []
    if fg and isinstance(fg[0], dict):
        numeric = [k for k, v in fg[0].items() if isinstance(v, (int, float))]
        report("foreground numeric keys: " + str(numeric))
        for r in fg:
            fg_rows.append((str(r.get("concept", "?")),
                            [(k, r.get(k)) for k in numeric]))
            fg_concepts.append(str(r.get("concept", "")))
        vals = [v for _, kv in fg_rows for k, v in kv
                if isinstance(v, (int, float)) and "vf" in k.lower()]
        fg_top = max(vals) if vals else None
thin = fg_top is not None and fg_top < 0.10
report("foreground top vf value: %s -> THIN=%s" % (fg_top, thin))


def find_plants(o, depth=0):
    if depth > 4:
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if "plant" in str(k).lower() and isinstance(v, list):
                return v
        for v in o.values():
            r = find_plants(v, depth + 1)
            if r:
                return r
    if isinstance(o, list):
        for v in o:
            r = find_plants(v, depth + 1)
            if r:
                return r
    return None


plants = []
for p in (find_plants(syn2) or []):
    if isinstance(p, dict):
        plants.append((str(p.get("word", "?")), p.get("closeness")))
    else:
        plants.append((str(p), None))
report("plants tonight: " + (", ".join(
    "%s%s" % (w, " %.3f" % c if isinstance(c, (int, float)) else "")
    for w, c in plants) or "not found in synthesis2 JSON"))


def fg_map(sj):
    out = {}
    for r in (sj or {}).get("foreground") or []:
        if isinstance(r, dict) and r.get("concept"):
            out[str(r["concept"])] = r
    return out


def kv_like(r, needle):
    for k, v in (r or {}).items():
        if needle in str(k).lower() and isinstance(v, (int, float)):
            return v
    return None


f1m, f2m = fg_map(syn1), fg_map(syn2)
rerun_bits = []
for c in sorted(set(list(f1m) + list(f2m))):
    a1v, a2v = kv_like(f1m.get(c), "after"), kv_like(f2m.get(c), "after")
    if a1v is not None or a2v is not None:
        rerun_bits.append("%s: run-1 after=%s, run-2 after=%s" % (c, a1v, a2v))
report("rerun trajectories: " + ("; ".join(rerun_bits)
                                 or "(legacy foreground-row probe; superseded by the vfidf_after join)"))

# channel-A restoration by the winner (measured, reported, rendered)
prose_stems = stems_of(prose)
resto = {c: (stem_norm(c) in prose_stems) for c in fg_concepts}
report("channel-A restoration by winner: " + (", ".join(
    "%s:%s" % (c, "yes" if v else "no") for c, v in resto.items()) or "--"))

# ── HTML builders ───────────────────────────────────────────────────
def mark_stems(text, stemset, cls):
    parts = re.split("(" + WORD + ")", text)
    out, n = [], 0
    for i, p in enumerate(parts):
        if i % 2 == 1 and stem_norm(p) in stemset:
            out.append('<mark class="%s">%s</mark>' % (cls, esc(p)))
            n += 1
        else:
            out.append(esc(p))
    return "".join(out), n


def md_lite(text, stemset, cls):
    out, count = [], 0
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        if re.fullmatch(r"-{3,}", b):
            out.append("<hr>")
            continue
        mh = re.match(r"(#{1,4})\s+(.*)$", b)
        if mh:
            lvl = min(4, len(mh.group(1)) + 2)
            h, n = mark_stems(mh.group(2), stemset, cls)
            count += n
            out.append("<h%d>%s</h%d>" % (lvl, h, lvl))
            continue
        h, n = mark_stems(b, stemset, cls)
        count += n
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        out.append("<p>%s</p>" % h)
    return "\n".join(out), count


fgset = {stem_norm(c) for c in fg_concepts} - {""}
src_html, fg_marked = [], 0
for i, p in enumerate(paras, 1):
    h, n = mark_stems(p, fgset, "fg")
    fg_marked += n
    src_html.append('<p><span class="pno">p%d</span> %s</p>' % (i, h))
SOURCE_COL = "\n".join(src_html)

vdset = {stem_norm(w) for w, _ in consensus} - {""}
SP_COL, vd_marked = md_lite(prose, vdset, "vd")
report("marks rendered: %d yellow in source, %d green in reading"
       % (fg_marked, vd_marked))

lrows = []
for (t, claim, refs), (v, hits_, ev) in zip(rows, verdicts):
    vcls = {"TRACED": "vok", "SUPPORTED-ABSENT": "vok",
            "CONTESTED": "vwarn", "UNTRACED": "vbad",
            "BAD-REF": "vbad", "REF-OK": "vref"}.get(v, "vhedge")
    extra = ""
    if v == "CONTESTED":
        extra = ('<div class="ev">hits: %s &middot; evidence: '
                 '&ldquo;%s&rdquo;</div>'
                 % (esc(", ".join(hits_ or [])), esc((ev or "")[:170])))
    lrows.append(
        "<tr><td><span class='badge b%s'>%s</span></td>"
        "<td>%s%s</td><td class='mono'>%s</td>"
        "<td><span class='badge %s'>%s</span></td></tr>"
        % (t, t, esc(claim), extra, esc(refs),
           vcls, esc(v)))
LEDGER_ROWS = "\n".join(lrows)
if not gate("G3", len(lrows) == full["n"] == stored["n"],
            "ledger rows rendered %d == audit n %d" % (len(lrows), full["n"])):
    sys.exit("STOP: rendered rows != audit count")

CENSUS_ROWS = "\n".join(
    "<tr><td class='mono'>%d/10</td><td>%s</td></tr>" % (s, esc(q))
    for s, q in crows3)

srows, prows = [], []
for r in standings:
    lab = r["label"]
    ln = len(loccov.get(lab, []))
    lm = r["local_mean"]
    loccell = ("%s (n=%d)" % (lm, ln)) if lm is not None else ("&mdash; (n=%d)" % ln)
    tag = " <span class='win'>&larr; winner</span>" if r["writer"] == winner else ""
    srows.append("<tr><td>%s%s</td><td class='mono'>%s</td>"
                 "<td class='mono'>%s (n=%s)</td><td class='mono'>%s</td>"
                 "<td class='mono'>%s</td><td class='mono'>%s/%s</td>"
                 "<td class='mono'>%s</td></tr>"
                 % (esc(r["writer"]), tag, lab, r["exself_mean"],
                    r["exself_n"], loccell, r.get("ledger_n"),
                    r.get("f_traced"), r.get("f_total"),
                    r.get("absence_contested")))
    prows.append("<tr><td>%s</td><td class='mono'>%s (n=%s)</td>"
                 "<td class='mono'>%s</td><td class='mono'>%s/%s</td>"
                 "<td class='mono'>%s</td><td class='mono'>&mdash;</td></tr>"
                 % (esc(r["writer"]), r["exself_mean"], r["exself_n"],
                    r.get("ledger_n"), r.get("f_traced"), r.get("f_total"),
                    r.get("absence_contested")))
STANDINGS_ROWS = "\n".join(srows)
POLICY_ROWS = "\n".join(prows)

mx = ["<table class='matrix'><tr><th></th>"
      + "".join("<th>%s</th>" % l for l in labs) + "</tr>"]
for j in sorted(fro):
    cells = []
    for l in labs:
        v = fro[j].get(l, "&ndash;")
        star = "*" if model_of.get(l) == j else ""
        rr = reasons.get(j, {}).get(l)
        ttl = ' title="%s"' % esc(rr) if rr else ""
        cells.append("<td%s%s>%s%s</td>"
                     % (" class='self'" if star else "", ttl, v, star))
    mx.append("<tr><th>%s</th>%s</tr>" % (esc(j), "".join(cells)))
mx.append("</table>")
MATRIX = "\n".join(mx)
MATRIX_NOTES = "".join(
    "<p class='small'><b>%s</b> (whole-panel note): %s</p>"
    % (esc(j), esc(t)) for j, t in sorted(blanket.items()) if j in fro)

# ── copy variants (all computed) ────────────────────────────────────
exvals = [r["exself_mean"] for r in standings if r["exself_mean"] is not None]
spread = round(max(exvals) - min(exvals), 2) if exvals else None
wa = bake["claim_audits"][winner]
dens = max(standings, key=lambda r: (r.get("f_traced") or 0))
da = bake["claim_audits"][dens["writer"]]

CHIP_G4 = ("the reading led with the exact questions an independent census "
           "measured &mdash; zero shared code" if strong else
           "the reading and an independent census surfaced the same silence "
           "&mdash; zero shared code")

if positive_all_traced:
    LEDGER_STAT = ("Across the whole panel this run: every positive fact "
                   "traced &mdash; %d/%d &mdash; and the entire contested mass "
                   "(%d claims) is absence claims whose negation vocabulary "
                   "echoes the source's own words; %d absence claims survived "
                   "whole-document search. A contest here marks a judgment "
                   "boundary, not a falsehood &mdash; the evidence is quoted "
                   "in every contested row below."
                   % (alltr, allpos, abs_con, abs_ok))
else:
    LEDGER_STAT = ("Panel totals this run: positive facts %d/%d traced; "
                   "absence claims %d supported, %d contested. Contests are "
                   "surfaced with evidence, never auto-failed."
                   % (alltr, allpos, abs_ok, abs_con))

if dens["writer"] != winner:
    pos_ = ordinal(standings.index(dens) + 1)
    DIVERGENCE = ("A divergence worth publishing: the panel's winner is not "
                  "the audit's densest writer. %s filed the largest ledger "
                  "(%d claims, %d/%d traced, %d bad refs) and placed %s; "
                  "%s won on insight with %d claims, %d/%d traced and %d "
                  "contested &mdash; every contest an absence claim. Insight "
                  "and provenance density are different measurements; this "
                  "page publishes both and lets them disagree."
                  % (esc(dens["writer"]), da["n"], da["f_traced"],
                     da["f_total"], da["bad_refs"], pos_, esc(winner),
                     wa["n"], wa["f_traced"], wa["f_total"],
                     wa["absence_contested"]))
else:
    DIVERGENCE = ("This run the panel's winner also leads the audit: "
                  "%s, %d claims, %d/%d traced, %d bad refs."
                  % (esc(winner), wa["n"], wa["f_traced"], wa["f_total"],
                     wa["bad_refs"]))

SELF_PREF_LINE = ("Self-preference, measured on the anonymized diagonal: "
                  "mean %s across %d judges (range %s %s &hellip; %s %s). "
                  "Labels are anonymized, so a nonzero diagonal is affinity "
                  "for one's own style, not knowing self-favoritism &mdash; "
                  "and this run the net lean was %s."
                  % (pm(sp_mean), len(selfpref),
                     pm(sp_sorted[0][1]), esc(sp_sorted[0][0]),
                     pm(sp_sorted[-1][1]), esc(sp_sorted[-1][0]),
                     "downward: the panel marked its own style down"
                     if sp_mean < 0 else
                     ("upward: self-flattering" if sp_mean > 0 else "flat")))

holes = [lab for lab in labs if not loccov[lab]]
LOCALS_NOTE = ("Local-panel coverage is partial this run: no local judge's "
               "parsed scores include %s &mdash; the column renders with "
               "per-label n and nothing is hung on it."
               % ", ".join("%s (%s)" % (l, model_of[l]) for l in holes)
               if holes else
               "Local panel: full label coverage this run.")

G5_CAVEAT = ("<p class='note'>Caveat, auto-printed: this demo source splits "
             "into %d paragraph(s), so citation granularity is effectively "
             "whole-document; multi-paragraph sources exercise the trace at "
             "full resolution.</p>" % len(paras)) if g5 else ""

G7_LINE = ("<p class='note'>Disclosure, printed because the data demands "
           "it: every consensus pair this run is Centroid&nbsp;+&nbsp;"
           "Gradient, and the gradient stages initialize at the centroid "
           "(&sect;B) &mdash; the two classes share a starting point, so "
           "their agreement is robustness evidence, not full independence. "
           "The convergence law is stated for the general case; this run it "
           "fired only on its weakest pair, and saying so is the point of "
           "this page.</p>") if all_cg else ""

CONSENSUS_DEMO = " &middot; ".join(
    "<b>%s</b> <span class='dim'>%d classes (%s)</span>"
    % (esc(w), len(cl), ", ".join(cl)) for w, cl in consensus) or "&mdash;"

MARGIN_LINE = ("This corpus, measured tonight: body median %s vs shuffle "
               "null %s &rarr; margin %+.3f." % (bm, nm, margin)
               if margin is not None else
               "This corpus: pricing medians not present in the centipede "
               "JSON; see the raw artifact.")

if fg_rows:
    hdr = "".join("<th class='mono'>%s</th>" % esc(k) for k, _ in fg_rows[0][1])
    body = "\n".join(
        "<tr><td>%s</td>%s</tr>"
        % (esc(c), "".join("<td class='mono'>%s</td>"
                           % (("%.3f" % v) if isinstance(v, float) else esc(v))
                           for _, v in kvs))
        for c, kvs in fg_rows)
    FG_DEMO = ("<table><tr><th>concept</th>%s</tr>%s</table>" % (hdr, body))
else:
    FG_DEMO = "<p class='dim'>foreground table unavailable this run</p>"

RERUN_NOTE = ("<p class='small'>Rerun record (the synthesis stage is a "
              "declared non-frozen stage; divergence across reruns is the "
              "temperature speaking): %s.</p>"
              % esc("; ".join(rerun_bits))) if rerun_bits else ""

# ── v2.2: before->after join from vfidf_before/vfidf_after (recon 2) ──
def _vfmap(sj, key):
    return {str(r.get("concept")): r.get("vfidf")
            for r in (sj or {}).get(key) or [] if isinstance(r, dict)}

_b2, _a2 = _vfmap(syn2, "vfidf_before"), _vfmap(syn2, "vfidf_after")
if not _b2 and fg_rows:
    _b2 = {c: dict(kvs).get("vfidf") for c, kvs in fg_rows}
join2 = []
for _c in (fg_concepts or sorted(_b2)):
    _bv, _av = _b2.get(_c), _a2.get(_c)
    if _bv is None and _av is None:
        continue
    if _av is None:
        _lab = "?"
    elif _av == 0:
        _lab = "COLLAPSED"
    elif _bv is not None and _av > _bv + 1e-9:
        _lab = "deepened"
    else:
        _lab = "kept"
    join2.append((_c, _bv, _av, _lab))

def _fmt(v):
    return "%.3f" % v if isinstance(v, (int, float)) else "&mdash;"

if join2:
    FG_DEMO = ("<table><tr><th>concept</th><th class='mono'>VF-IDF before"
               "</th><th class='mono'>after re-harvest</th><th>verdict</th>"
               "</tr>" + "\n".join(
        "<tr><td>%s</td><td class='mono'>%s</td><td class='mono'>%s</td>"
        "<td>%s</td></tr>" % (
            esc(_c), _fmt(_bv), _fmt(_av),
            "<span class='badge vok'>COLLAPSED</span>" if _lab == "COLLAPSED"
            else ("<span class='badge vbad'>deepened</span>"
                  if _lab == "deepened" else
                  "<span class='mono'>%s</span>" % esc(_lab)))
        for _c, _bv, _av, _lab in join2) + "</table>"
        "<p class='small'>COLLAPSED = the re-harvest now carries the "
        "concept: VF-IDF hits exact zero via the lexical channel. "
        "deepened = the rewrite made the concept more void, not less "
        "&mdash; a miss, published. The after-measurement treats the "
        "synthesis as the document under test: void_freq re-normalizes "
        "against the synthesis article, so before/after compare the "
        "concept's standing in two documents &mdash; source, then "
        "synthesis &mdash; under one metric.</p>")
    report("collapse table: " + "; ".join(
        "%s %s->%s %s" % (_c, _bv, _av, _lab)
        for _c, _bv, _av, _lab in join2))

_r1a = _vfmap(syn1, "vfidf_after")
_vf1 = {str(r.get("concept")): r.get("void_freq")
        for r in (syn1 or {}).get("vfidf_after") or [] if isinstance(r, dict)}
_vf2 = {str(r.get("concept")): r.get("void_freq")
        for r in (syn2 or {}).get("vfidf_after") or [] if isinstance(r, dict)}
_semdiff = sorted(c for c in _vf1 if c in _vf2
                  and isinstance(_vf1[c], (int, float))
                  and isinstance(_vf2[c], (int, float))
                  and abs(_vf1[c] - _vf2[c]) > 0.05)
if _r1a and join2 and _semdiff:
    _c1 = [c0 for c0, b0, a0, l0 in join2 if _r1a.get(c0) == 0]
    _c2 = [c0 for c0, b0, a0, l0 in join2 if l0 == "COLLAPSED"]
    RERUN_NOTE = ("<p class='small'>Rerun record (the synthesis stage is a "
                  "declared non-frozen stage): run-1 collapsed %s; run-2 "
                  "kept it and collapsed %s instead &mdash; a zero is a "
                  "zero under any normalization. Both runs re-normalize the "
                  "after void_freq against their own synthesis article "
                  "&mdash; the synthesis becomes the document under test "
                  "&mdash; so after-columns of different runs are not "
                  "directly comparable (%s). Run-1's stored after-rows "
                  "additionally disagree with run-1's own console on two "
                  "independent quantities (VF-IDF and survival), so run-1 "
                  "numerics are withheld pending a serializer audit; "
                  "run-2's stored values match its console exactly and "
                  "are what renders above.</p>"
                  % (esc(", ".join(_c1) or "?"), esc(", ".join(_c2) or "?"),
                     esc("; ".join("%s %.3f vs %.3f"
                                   % (c0, _vf1[c0], _vf2[c0])
                                   for c0 in _semdiff))))
    report("rerun: run-1 WITHHELD -- after-vf is per-run synthesis-normalized; run-1 JSON also contradicts run-1 console: "
           + "; ".join("%s %.3f vs %.3f" % (c0, _vf1[c0], _vf2[c0])
                       for c0 in _semdiff))
elif _r1a and join2:
    _bits = ["%s: run-1 after %s, run-2 after %s"
             % (c0, _fmt(_r1a[c0]).replace("&mdash;", "?"),
                _fmt(a0).replace("&mdash;", "?"))
             for c0, b0, a0, l0 in join2 if c0 in _r1a]
    if _bits:
        RERUN_NOTE = ("<p class='small'>Rerun record (the synthesis stage "
                      "is a declared non-frozen stage; divergence across "
                      "reruns is the temperature speaking): %s.</p>"
                      % esc("; ".join(_bits)))
        report("rerun (vfidf_after join): " + "; ".join(_bits))

# ── v2.2: carriage exhibit from synthesis2.survival ──
surv = []
for _r in (syn2 or {}).get("survival") or []:
    if isinstance(_r, dict) and _r.get("word") is not None:
        surv.append((str(_r["word"]), str(_r.get("cls", "?")),
                     _r.get("survived"), _r.get("of")))
CARRIAGE = ""
if surv:
    report("carriage (run-2 survival): " + "; ".join(
        "%s(%s) %s/%s" % t for t in surv))
    CARRIAGE = ("<p><b>Carriage, measured.</b> Tracked words in the 10 "
                "downstream AI summaries of the synthesis. A void concept "
                "that survives here has entered the model-mediated version "
                "of this topic &mdash; where, before, it did not exist.</p>"
                "<table><tr><th>word</th><th>class</th>"
                "<th class='mono'>carried by</th></tr>" + "\n".join(
        "<tr><td>%s</td><td class='mono'>%s</td>"
        "<td class='mono'>%s/%s</td></tr>"
        % (esc(_w), esc(_cl), _s, _o)
        for _w, _cl, _s, _o in surv) + "</table>")
_er1 = (syn1 or {}).get("expand_results") or []
if _er1:
    report("run-1 expand_results[0] (NOT rendered; adjudicate): "
           + json.dumps(_er1[0])[:200])

PLANTS_LINE = ("This run's plants, measured min-closeness on this corpus: "
               + ", ".join("<b>%s</b>%s" % (esc(w),
                           " (%.3f)" % c if isinstance(c, (int, float)) else "")
                           for w, c in plants)
               + " &mdash; refused by the writer stage."
               if plants else
               "This run's plants: recorded in the synthesis artifact.")

THIN_LINE = ("the pipeline itself flagged this document (FOREGROUND top "
             "%.3f &lt; 0.10 &rarr; THIN &mdash; thinness is a finding)"
             % fg_top if thin else
             ("FOREGROUND top score this run: %s" % fg_top
              if fg_top is not None else "see the synthesis artifact"))

CENSUS_DEMO = " &middot; ".join("%s %d/10" % (esc(q[:52]), s)
                                for s, q in crows3[:3])
CENSUS_DEMO += (" &mdash; the silence the winning reading led with"
                if strong else
                " &mdash; the same silence the winning reading opened on")

top = standings[0]
PIN_LINE = ("Current pin: <b>%s</b> &mdash; panel %s (n=%s), ledger %d "
            "claims, %d/%d traced. Provenance-density leader: %s (%d/%d "
            "traced, %d bad refs). The seat re-opens on major model "
            "releases; the pin is recorded in every artifact's provenance."
            % (esc(winner), top["exself_mean"], top["exself_n"], wa["n"],
               wa["f_traced"], wa["f_total"], esc(dens["writer"]),
               da["f_traced"], da["f_total"], da["bad_refs"]))

AUDIT_DEMO = ("Demo run: 5/5 frontier models emitted parseable ledgers "
              "cold (%d claims panel-wide). %s"
              % (sum(a["n"] for a in bake["claim_audits"].values()),
                 LEDGER_STAT))

armA = ("<li>flat-leg honesty: clean gated terms for %d of %d void "
        "probes (raw raycast candidates for %d; the junk rule and quality "
        "gates account for the difference) &mdash; near-silence on thin "
        "copy is instrument behavior worth showing, not hiding.</li>"
        % (flat_clean, tot_arms, flat_fired)) if flat_key else ""
resto_li = ("<li>channel-A restoration by the winner: %s &mdash; the "
            "discipline says directions, not words, and the winner chose "
            "structure over token restoration; the collapse table above is "
            "the corpus-level view of the same channel.</li>"
            % esc(", ".join("%s %s" % (c, "restored" if v else "not restored")
                            for c, v in resto.items()))) if resto else ""
APPENDIX = (
    "<ul>"
    "<li>census: %s.</li>"
    "<li>panel: spread %s across writers (n=4 per mean); self-preference "
    "mean %s (n=%d), per-judge %s.</li>"
    "<li>plants: %s</li>"
    "%s%s"
    "<li>pricing: %s</li>"
    "</ul>"
    % (" &middot; ".join("%s %d/10" % (esc(q[:40]), s) for s, q in crows3[:5]),
       spread, pm(sp_mean), len(selfpref),
       ", ".join("%s %s" % (esc(j), pm(v)) for j, v in sp_sorted),
       PLANTS_LINE, armA, resto_li, esc(MARGIN_LINE)))

TIENOTE = ("; tied at the top, alphabetical display" if tie else "")
WINSCORE = "%s, n=%s%s" % (top["exself_mean"], top["exself_n"], TIENOTE)

RUBRIC_AMEND = ("Rubric amended 2026-07-10 (bakeoff v1.2, sha %s; previous "
                "one-line-only rubric sha cb7c7f362985): scores line plus "
                "one grounded reason per summary. The previous rubric "
                "commanded a ~19-character reply that the harvest floor "
                "(50 chars) destroyed &mdash; defect #%s below."
                % (rs, esc(args.defect_num)))

DEFECT_NEW = ("&middot; <b>#%s</b> the judge rubric ordered a 19-character "
              "reply; the collection gate destroyed anything under 50 chars "
              "&mdash; for two runs the only surviving judges were the ones "
              "that disobeyed, and their stale files were then re-read as "
              "fresh by the next run &rarr; per-stage --min-chars, an mtime "
              "staleness gate on judge reads, a declared tie policy, and "
              "versioned output filenames." % esc(args.defect_num))

report("defect number rendered: #%s -- veto with --defect-num"
       % args.defect_num)

# ── template ────────────────────────────────────────────────────────
TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Not a Summary. A Reading. &mdash; EigenTrace</title>
<link rel="canonical" href="@@CANONICAL@@">
<meta name="description" content="Five frontier AI models read one page's measured silence under an evidence-ledger discipline. Every claim typed, traced against the source, contests quoted. The commercial form of EigenTrace's Summary Plus.">
<meta property="og:type" content="article">
<meta property="og:title" content="Not a Summary. A Reading.">
<meta property="og:description" content="Five frontier AI models read one page's measured silence under an evidence-ledger discipline. Every claim typed, traced against the source, contests quoted.">
<meta property="og:url" content="@@CANONICAL@@">
<meta property="og:site_name" content="EigenTrace">
<meta property="og:image" content="@@OGIMAGE@@">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="@@OGIMAGE@@">
<style>
/* house tokens -- cloned from the editorial family (convergence/outliers/
   atlas/withdrawals). dark: paper/ink/killed cloned exactly from the house
   dark block; remaining dark tiers derived in the same grammar. */
:root{--ink:#1a1a18;--ink-soft:#4a4a45;--ink-faint:#7a7a72;
--paper:#faf9f6;--surface:#ffffff;
--line:rgba(26,26,24,0.12);--line-soft:rgba(26,26,24,0.07);
--measured:#0f6e56;--measured-bg:#e1f5ee;--measured-line:#9fe1cb;
--argued:#854f0b;--argued-bg:#faeeda;--argued-line:#fac775;
--frozen:#2a4a6a;--frozen-bg:#e4eaf1;--frozen-line:#aac0db;
--ends:#5f5e5a;--ends-bg:#f1efe8;--ends-line:#d3d1c7;
--killed:#9a3324;--killed-bg:#f7e9e6;--killed-line:#e0a89f;
--accent:#993c1d;
--vd-bg:#e1f5ee;--vd-line:#0f6e56;
--fg-bg:#fdf3c9;--fg-line:#b08a00;
--serif:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;
--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
--mono:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace}
@media(prefers-color-scheme:dark){:root{
--ink:#e8e6e0;--ink-soft:#b4b2a9;--ink-faint:#888780;
--paper:#15140f;--surface:#1c1b16;
--line:rgba(232,230,224,0.14);--line-soft:rgba(232,230,224,0.07);
--measured:#5dcaa5;--measured-bg:#132e25;--measured-line:#1f5c4d;
--argued:#e0b25f;--argued-bg:#302509;--argued-line:#7a5a1e;
--frozen:#93b6dd;--frozen-bg:#17222e;--frozen-line:#2a4a6a;
--ends:#aaa69d;--ends-bg:#232119;--ends-line:#5f5e5a;
--killed:#e08576;--killed-bg:#2c1714;--killed-line:#9a3324;
--accent:#d98a63;
--vd-bg:#132e25;--vd-line:#5dcaa5;
--fg-bg:#33290c;--fg-line:#c9a227}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--sans);font-size:17px;line-height:1.65;
-webkit-font-smoothing:antialiased}
a{color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nav{max-width:730px;margin:0 auto;padding:22px 24px;display:flex;
gap:18px;flex-wrap:wrap;font-size:13.5px}
.nav a{color:var(--ink-faint);text-decoration:none}
.nav a:hover{color:var(--ink)}
.nav .home{color:var(--ink);font-weight:500}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px 120px}
.wrap>p,.wrap>h1,.wrap>ul,.wrap>pre,.wrap>.eyebrow,.wrap>footer,
.wrap>.legend{max-width:682px;margin-left:auto;margin-right:auto}
.wrap>.chips,.wrap>.cols,.wrap>table,.wrap>.divider{max-width:992px;
margin-left:auto;margin-right:auto}
.wrap>table.matrix{max-width:560px}
.wrap>.cta{display:block;width:max-content;margin:18px auto 6px}
h1{font-family:var(--serif);font-size:45px;line-height:1.06;
font-weight:600;margin:6px auto 18px;letter-spacing:-.01em}
.standfirst{font-family:var(--serif);font-size:21px;line-height:1.42;
color:var(--ink-soft);font-style:italic;margin:0 auto 20px}
.dateline{font-family:var(--mono);font-size:13px;color:var(--ink-faint);
padding-top:16px;border-top:1px solid var(--line);margin:0 auto 6px}
.eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.12em;
text-transform:uppercase;color:var(--accent);margin:66px auto 12px;
padding-top:20px;border-top:1px solid var(--line);font-weight:600}
.eyebrow.lead{margin-top:26px;padding-top:0;border-top:0}
p{margin:.6em auto}
.dim{color:var(--ink-faint);font-weight:400}
.small{font-size:13px;color:var(--ink-faint)}
.note{font-size:14px;color:var(--ink-soft);background:var(--frozen-bg);
border-left:3px solid var(--frozen-line);padding:10px 14px;
border-radius:0 6px 6px 0}
.legend{font-size:14px;color:var(--ink-soft)}
.legend span{margin-right:16px}
mark.vd{background:var(--vd-bg);border-bottom:2px solid var(--vd-line);
padding:0 .1em;color:inherit}
mark.fg{background:var(--fg-bg);border-bottom:2px solid var(--fg-line);
padding:0 .1em;color:inherit}
.chips{display:flex;flex-wrap:wrap;gap:12px;margin:22px auto}
.chip{background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:13px 15px;flex:1 1 250px;font-size:14px;
color:var(--ink-soft)}
.chip b{display:block;font-family:var(--mono);font-size:11.5px;
letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
margin-bottom:6px;font-weight:600}
.cta{padding:12px 20px;background:var(--ink);color:var(--paper);
text-decoration:none;font:600 13.5px var(--mono);border-radius:6px;
letter-spacing:.03em}
.cta:hover{background:var(--accent);color:#fff}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin:16px auto}
.col{background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:22px 24px;font-family:var(--serif);
font-size:16px;line-height:1.6}
.col .placard{font-family:var(--sans);font-size:11.5px;font-weight:600;
letter-spacing:.09em;text-transform:uppercase;color:var(--ink-faint);
margin:0 0 14px}
.col .placard .dim{text-transform:none;letter-spacing:0}
.col h3,.col h4{font-family:var(--serif);font-weight:600;line-height:1.22}
.col h3{font-size:19px;margin:1.1em 0 .4em}
.col h4{font-size:16.5px;margin:1em 0 .3em}
.pno{font:600 10.5px var(--mono);color:var(--ink-faint);
background:var(--ends-bg);padding:2px 6px;border-radius:3px;
margin-right:7px}
table{border-collapse:collapse;width:100%;font:13px/1.55 var(--mono);
background:var(--surface);margin:.7em auto}
td,th{border-top:1px solid var(--line);padding:7px 10px;text-align:left;
vertical-align:top}
th{font:600 10.5px var(--mono);letter-spacing:.08em;
text-transform:uppercase;color:var(--ink-faint);border-top:0;
border-bottom:1px solid var(--line)}
tr:hover td{background:var(--line-soft)}
.mono{font-family:var(--mono);font-size:.95em}
.badge{font:600 10.5px/1 var(--mono);padding:3px 7px;border-radius:4px;
letter-spacing:.05em;white-space:nowrap;border:1px solid var(--line);
background:var(--surface);color:var(--ink-soft)}
.vok{background:var(--measured-bg);color:var(--measured);
border-color:var(--measured-line)}
.vwarn{background:var(--argued-bg);color:var(--argued);
border-color:var(--argued-line)}
.vbad{background:var(--killed-bg);color:var(--killed);
border-color:var(--killed-line)}
.vref{background:var(--frozen-bg);color:var(--frozen);
border-color:var(--frozen-line)}
.vhedge{background:var(--ends-bg);color:var(--ends);
border-color:var(--ends-line)}
.ev{font:12px/1.5 var(--mono);color:var(--ink-faint);margin-top:5px;
border-left:2px solid var(--argued-line);padding-left:8px}
.matrix td,.matrix th{text-align:center}
.matrix td.self{background:var(--ends-bg);color:var(--ink-faint)}
.matrix td[title]{cursor:help;text-decoration:underline dotted var(--ink-faint)}
.win{color:var(--measured);font-family:var(--mono);font-size:11.5px}
pre{font:12.5px/1.55 var(--mono);background:#15140f;color:#e8e3d8;
border:1px solid var(--line);border-radius:8px;padding:18px 20px;
overflow-x:auto;margin:14px auto}
code{font-family:var(--mono);font-size:.85em;background:var(--frozen-bg);
padding:1px 6px;border-radius:4px}
hr{border:0;border-top:1px solid var(--line);margin:1.6em 0}
ul{padding-left:22px}
li{margin:6px 0}
.divider{font:600 12px/1.6 var(--mono);letter-spacing:.1em;
text-transform:uppercase;color:var(--ink-soft);text-align:center;
border-top:2px solid var(--ink);border-bottom:2px solid var(--ink);
padding:14px 10px;margin:3.2em auto}
footer{border-top:1px solid var(--line);margin-top:70px;padding-top:26px;
font:12.5px/1.75 var(--mono);color:var(--ink-faint)}
footer .closer{font-family:var(--serif);font-style:italic;font-size:17px;
color:var(--ink-soft);margin:0 0 16px;line-height:1.5}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
@media(max-width:600px){body{font-size:16px}h1{font-size:34px}
.wrap{padding:0 18px 80px}}
</style></head><body>
<nav class="nav"><a class="home" href="/">EigenTrace</a><a href="/consequence-atlas">Atlas</a><a href="/summary-plus">Summary Plus</a><a href="/large-language-model-outliers">Outliers</a><a href="/sean-adams">About</a></nav>
<div class="wrap">

<div class="eyebrow lead">Summary Plus &middot; the commercial instrument</div>
<h1>Not a summary.<br><mark class="vd">A reading.</mark></h1>
<p class="standfirst">A real marketing page on the left &mdash; and on the
right, what the best of five frontier AI models produced when handed the
page's measured silence, under a prompt that forbids inserting, inventing,
and padding. The only path left open was to read.</p>
<p class="dateline">@@NCLASSES@@ independent mathematics &middot; every
claim typed, cited &amp; machine-audited against the source &middot;
generated @@GENERATED@@ &middot; one demo document, every stage
inspectable</p>

<div class="chips">
<div class="chip"><b>Two instruments, one silence</b>@@CHIP_G4@@</div>
<div class="chip"><b>Every claim audited</b>facts traced to cited paragraphs;
absence claims searched whole-document; contests quoted</div>
<div class="chip"><b>Self-preference: @@SPDISP@@</b>what happens when AIs
grade their own homework &mdash; measured and published</div>
</div>
<a class="cta" href="@@CONTACT@@">Send me a URL &rarr; your page gets this
treatment</a>

<div class="eyebrow">The exhibit</div>
<p class="legend"><span><mark class="fg">yellow</mark> source-salient
concepts every AI summary deleted (marked in the source)</span>
<span><mark class="vd">green</mark> void stems surfaced by &ge;2 independent
math classes, adopted by the winning reading (marked in the reading)</span></p>
@@G5_CAVEAT@@
<div class="cols">
<div class="col"><h3 class="placard">Source (paragraphs as numbered for the writer)</h3>
@@SOURCE_COL@@</div>
<div class="col"><h3 class="placard">The winning reading &mdash; @@WINNER@@
<span class="dim">(panel ex-self @@WINSCORE@@)</span></h3>
@@SP_COL@@</div>
</div>

<div class="eyebrow">The ledger &mdash; every claim, typed and audited</div>
<p>The writer must ledger its own reading:
<span class="badge bF">F</span> fact, traceable to cited paragraphs &middot;
<span class="badge bI">I</span> inference from structure &middot;
<span class="badge bS">S</span> speculation, drawn from the measured
consequence field, hedged. Then the machine checks: facts traced lexically
into their citations; absence claims searched across the whole document;
every contest quoted. Confidence is earned here, never self-reported.</p>
<p>@@LEDGER_STAT@@</p>
<table><tr><th>type</th><th>claim</th><th>refs</th><th>verdict</th></tr>
@@LEDGER_ROWS@@</table>

<div class="eyebrow">Two instruments, one silence</div>
<p>Before any writer ran, a separate instrument asked ten models what this
document raises but refuses to answer, clustered their questions
deterministically, and reported consensus:</p>
<table><tr><th>support</th><th>consensus question</th></tr>
@@CENSUS_ROWS@@</table>
<p>@@G4_LINE@@ Convergence between instruments that share no code is what
&ldquo;measured&rdquo; means on this site.</p>

<div class="eyebrow">The panel &mdash; nobody grades their own homework</div>
<table><tr><th>writer</th><th>label</th><th>panel ex-self</th>
<th>local panel</th><th>ledger</th><th>F-traced</th><th>contested</th></tr>
@@STANDINGS_ROWS@@</table>
<p class="small">Full judge &times; writer matrix (self-scores starred and
excluded from standings; hover a dotted cell for the judge's stated
reason):</p>
@@MATRIX@@
@@MATRIX_NOTES@@
<p>@@SELF_PREF_LINE@@</p>
<p>@@DIVERGENCE@@</p>
<p class="small">@@LOCALS_NOTE@@</p>

<div class="eyebrow">What you get</div>
<p>Send a URL or a text. One command runs the whole organism &mdash;
harvest, the independent mathematics, both raycasts per void, the
evidence-disciplined write by five frontier models, the ex-self panel, the
claim audit &mdash; and you get back the unsaid report (deleted &middot;
unreached &middot; unanswered &middot; unsayable, four measured strata of
your document's silence), the winning reading with its audited ledger, and
the receipts: every artifact sha-stamped, identical inputs reproducing
identical measurements, the two AI-written stages declared as such.</p>
<p><b>Full disclosure, standing policy:</b> everything above is one demo
document &mdash; thin marketing copy, and @@THIN_LINE@@. The button grows
the corpus. A position-matched placebo test is queued and will be published
either way.</p>
<a class="cta" href="@@CONTACT@@">Send me a URL &mdash; first one's the
demo.</a>
<p class="small">Measured: the census, the mathematics, the convergence law,
the panel matrix, the claim audit, the self-preference number, the
replications. Argued: that a page whose silence has been read wins
visibility and revenue in the AI layer. Plausible, untested &mdash; nobody
has that outcome data, because nobody else is reading the layer.
Measure first.</p>

<div class="divider">everything above sells the instrument &middot;
everything below IS the instrument &middot; if this page is all that
survives, the mathematics survives with it</div>

<div class="eyebrow">&sect;A &mdash; Substrate &amp; determinism</div>
<p>All vectors are unit-normalized embeddings from bge-large-en-v1.5
(1024-dim), CPU-pinned for bitwise determinism. Per document: anchor
h&nbsp;=&nbsp;E(title + prompt); per model group g &isin; {F, L, ALL}:
response vectors e&#8321;&hellip;e&#8345;, centroid
c&nbsp;=&nbsp;normalize(mean&nbsp;e&#7522;). Rulers: 50K curated-frequency
clean vocabulary (readout + spiral leg), 253K Wikipedia-title vocabulary
(flat leg), 184K global vocabulary (ring, optional; not run in this demo).
There is no RNG anywhere in the geometric path; every artifact prints a
RESULT sha &mdash; canonical JSON minus timestamp, sha256 &rarr; 12 hex
&mdash; and identical corpus + anchor + parameters must reproduce it. The
anchor is a load-bearing parameter of every method below except
said/gap/lexcross.</p>

<div class="eyebrow">&sect;B &mdash; The five mathematics (verbatim,
sign-honest)</div>
<p><b>I. Centroid arithmetic</b></p>
<pre>said: v = c   &middot;   gap: v = &plusmn;normalize(c_L &minus; c_F)   &middot;   centroid_surface: v = h</pre>
<p><b>II. Gradient descent</b> (both losses MINIMIZED; AdamW lr=0.05,
wd=1e-4 &mdash; the weight decay leaks an undeclared pull-to-origin; 150
steps; sphere projection each step; init = c &rArr; determinism is
structural)</p>
<pre>logos_v10: L(x) = mean&#7522;(1 &minus; cos(x, e&#7522;)) + 0.75&middot;cos(x, c) &minus; 0.30&middot;cos(x, h)
logos_v9:  L(x) = LogosLossV9(x, E) + 0.15&middot;cos(x, c) &minus; 0.30&middot;cos(x, h)</pre>
<p>Sign semantics, stated because a prior analysis got them backwards
(defect #49): minimizing +&lambda;&middot;cos(x,c) REPELS the consensus;
minimizing &minus;&lambda;&middot;cos(x,h) ATTRACTS the anchor. V10 in one
line: the direction agreeing with every response individually while
disagreeing with their mean &mdash; shared-but-not-central &mdash; tethered
to the document.</p>
<p><b>III. Spectral (SVD)</b></p>
<pre>E = U&Sigma;V&#7488; (full_matrices=False); v = V[&minus;1], the right singular vector of least &sigma;;
flip sign if v&middot;h &lt; 0; n &ge; 3</pre>
<p>The axis along which the group's answers cannot vary &mdash; what their
span fails to express. Known gap: gate on &sigma;_min (currently discarded);
when &sigma;_min is not small, this direction is noise.</p>
<p><b>IV. Counting</b></p>
<p>lexcross: stems said by the other model population, absent from this
one, counted per model, alphabetic tiebreak. (History: a set-difference
version made every count 1 and let the hash seed order the ranking &mdash;
defect #39, the only RNG ever found in the organism.)</p>
<p><b>V. Ring geometry (optional)</b></p>
<p>A donut on the 184K ruler: inner ring excludes centroid-proximal words,
outer ring gates on anchor relevance; hard fallback waives both gates;
returns (results, centroid) &mdash; unpack at the call site.</p>
<p><b>Readout (all vector methods)</b></p>
<pre>scan top-2000 ruler words by V&middot;v; keep len&ge;4, not HARD_DROP;
dedupe by Porter stem; skip stems the group said; take K=8</pre>

<div class="eyebrow">&sect;C &mdash; The two legs (per void w; v = E("w in
the context of {headline}"); d&#770; = (v&minus;h)/&Vert;v&minus;h&Vert;)</div>
<p><b>flat leg &mdash; consequence raycast (253K ruler)</b></p>
<pre>terminals T_&lambda; = h + &lambda;&middot;d&#770;, &lambda; &isin; {2, 3, 4}; kNN per terminal
density = mean pairwise cos(neighbors) &middot; novelty = 1 &minus; cos(T&#772;, v) &middot; tether = cos(h, T&#772;)</pre>
<p>Canonical example: a story avoiding &ldquo;world war&rdquo; whose
consequence field contains &ldquo;Hormuz&rdquo;. Junk rule on this ruler
(declared): leading non-letter | ellipsis | 3+ digit run | &gt;4 tokens.</p>
<p><b>spiral leg &mdash; sentence-converged (50K ruler; C-spiral lineage,
constants shared verbatim)</b></p>
<pre>T = normalize(h + 2.0&middot;d&#770;); pool = top-400 by cos(V, T)
keep w&prime;: stem &ne; stem(w); stem unsaid by all models;
        convergence = #{source sentences s : cos(w&prime;, s) &gt; 0.45} &ge; 2
sort (&minus;convergence, &minus;cos); top 5</pre>
<p>Both legs fire down the same ray: their agreement measures robustness
across ruler + discipline, never independence &mdash; and it is priced
(&sect;E), never assumed.</p>

<div class="eyebrow">&sect;D &mdash; The convergence law</div>
<p>CLASS-CONSENSUS: a void counts when independent mathematics land on the
same stem. Distinct classes per stem is the metric; a word surfaced eight
times by one class counts once (the said&equiv;logos J=1.00 core proved
within-class agreement is often structural: same centroid init, same
responses). This run, computed over the full
centipede JSON (every void per method, not the per-method-5 display
feed handed to the writers): @@CONSENSUS_DEMO@@.</p>
@@G7_LINE@@

<div class="eyebrow">&sect;E &mdash; Pricing (nothing agrees for free)</div>
<pre>shuffle null: cos(A&#772;&#7522;, B&#772;&#11388;) over ALL mismatched pairs with
different void stems &mdash; full enumeration, no sampling, no RNG.
Topic floor measured &asymp; 0.615&ndash;0.67 across corpora to date.</pre>
<p>Margins, session record (prior corpora): thin marketing copy +0.021
(correctly thin) &middot; research story +0.058 &middot; compliant-frame
variant +0.058 (cone +0.123) &middot; allegation dossier +0.080.
@@MARGIN_LINE@@</p>
<p class="small">Also printed per run: LEG-JACC (stem-Jaccard between leg
void-sets, all pairs), ARM-JACC (~0.00 in ray mode &mdash; the rulers
barely share surface forms; a disjointness document, not an agreement
metric), per-leg consequence centroids vs body, and the RESULT sha.</p>

<div class="eyebrow">&sect;F &mdash; VF-IDF (the metric, exactly)</div>
<pre>void_freq(c) = stem-level TF salience of c in the SOURCE (max-normalized)
fidelity(c, summary) = max(cosine, lexical)
  cosine = max cos(c, any summary sentence), clamped [0,1]
  lexical = fraction of c's content stems literally in the summary's stem set
inv_fidelity(c) = 1 &minus; max over summaries &middot; VF-IDF(c) = void_freq &times; inv_fidelity</pre>
<p>max() is the OR: the lexical channel is the false-void guard &mdash; a
concept counts dropped only if every summary dropped it on both channels,
so anything any summary carries lexically zeroes exactly. FOREGROUND takes
only rows &gt; 0.01 (zeros are preserved, not dropped); a top score
&lt; 0.10 prints THIN &mdash; thinness is a finding. This run's table:</p>
@@FG_DEMO@@
@@RERUN_NOTE@@
@@CARRIAGE@@

<div class="eyebrow">&sect;G &mdash; The writer stage (prompts verbatim; the
two declared non-frozen stages)</div>
<p><b>the Summary Plus discipline (verbatim, sha @@DSHA@@)</b></p>
<pre>@@DISCIPLINE@@</pre>
<p><b>the judge rubric (verbatim, sha @@RSHA@@; judges see prose only
&mdash; the ledger is stripped before judging)</b></p>
<pre>@@RUBRIC@@</pre>
<p class="small">@@RUBRIC_AMEND@@</p>
<p>Writers anonymized A&ndash;E in deterministic (alphabetical) order;
standings are EX-SELF means. Why the discipline forces improvement: the
geometry supplies attention targets the writer could not self-generate, and
the contract closes every cheap exit &mdash; insertion (directions, not
words), invention (trace or omit), padding (drop silently; zero analogies).
The one rewarded behavior left is reading.</p>

<div class="eyebrow">&sect;H &mdash; The mechanical claim audit (confidence
earned)</div>
<pre>parse: lines after 'LEDGER:' matching TYPE|claim|refs
F, positive:  &ge;&lceil;stems/3&rceil; of the claim's content stems present in the
              cited paragraphs (lexical trace) &rarr; TRACED
F, absence (claim contains no/not/none/never/absent/omits/lacks/&hellip;):
              search the WHOLE source for the claim's concept stems;
              none found &rarr; SUPPORTED-ABSENT; any found &rarr; CONTESTED,
              with the offending sentence quoted
I:            refs must be valid paragraph ids
S:            exempt; counted; must be hedged (style call, human)</pre>
<p>Contests are surfaced, not auto-failed: &ldquo;no performance
figures&rdquo; vs &ldquo;strong off-the-line response&rdquo; is a judgment
boundary the audit's job is to make visible with evidence attached.
@@AUDIT_DEMO@@</p>

<div class="eyebrow">&sect;I &mdash; The decoys (the trap is geometry
too)</div>
<pre>closeness(w) = max(V&middot;anchor, V&middot;response-centroid)
plants = ascending-closeness words, len&ge;5, alphabetic, stem &notin; source &cup;
said &cup; candidates; each camouflaged with its own top-3 vocab neighbors;
woven into sha-keyed slots, unlabeled</pre>
<p>Measured, not curated: the vocabulary's farthest points from the
document's field. @@PLANTS_LINE@@ Record across all runs: impossible decoys
refused every time; one early ornamental decoy adopted twice, caught and
evidence-quoted both times; rival brand names refused every run.</p>

<div class="eyebrow">&sect;J &mdash; The question census</div>
<pre>ten models independently list raised-but-unanswered questions;
lines ending '?' extracted (numbering stripped); embedded;
greedy deterministic clustering: fixed order (model, line index),
assign to best cluster with centroid-cos &ge; 0.80 else new cluster,
centroid renormalized per insert; report clusters with &ge; 3 models</pre>
<p>One model's curiosity is an opinion; consensus is a measured gap.
This run: @@CENSUS_DEMO@@.</p>

<div class="eyebrow">&sect;K &mdash; Writer selection policy (declared)</div>
<p>The bake-off is the selection instrument. Policy: run the ex-self panel
per document class until the ordering stabilizes, then PIN one writer on
three axes &mdash; panel score, audit cleanliness, price per run &mdash;
record the pin in every artifact's provenance, and re-open the seat on
major model releases. Current table:</p>
<table><tr><th>writer</th><th>ex-self</th><th>ledger</th><th>F-traced</th>
<th>contested</th><th>seat cost</th></tr>
@@POLICY_ROWS@@</table>
<p class="small">@@PIN_LINE@@</p>

<div class="eyebrow">&sect;L &mdash; Every constant (the parameters
table)</div>
<table>
<tr><th>parameter</th><th>value</th></tr>
<tr><td>embedder</td><td class="mono">bge-large-en-v1.5, 1024-d, CPU,
unit-norm</td></tr>
<tr><td>readout K per leg</td><td class="mono">8 (display 5)</td></tr>
<tr><td>V10 composite</td><td class="mono">attract-each 1.0 &middot;
repel-mean 0.75 &middot; anchor 0.30</td></tr>
<tr><td>V9 composite</td><td class="mono">criterion + repel-mean 0.15
&middot; anchor 0.30</td></tr>
<tr><td>optimizer</td><td class="mono">AdamW lr 0.05, wd 1e-4, 150 steps,
sphere projection, init = centroid</td></tr>
<tr><td>flat-leg depths &lambda;</td><td class="mono">2.0, 3.0, 4.0
(253K ruler)</td></tr>
<tr><td>flat-leg gates</td><td class="mono">density&gt;0.4 &and;
novelty&gt;0.25 &and; tether&gt;0.25</td></tr>
<tr><td>spiral leg</td><td class="mono">&lambda;=2.0 &middot; pool 400
&middot; convergence &ge;2 @ cos 0.45 &middot; top 5 (50K ruler)</td></tr>
<tr><td>junk rule (253K)</td><td class="mono">leading non-letter | ellipsis
| 3+ digit run | &gt;4 tokens</td></tr>
<tr><td>census clustering</td><td class="mono">cos &ge; 0.80, greedy
deterministic, min-models 3</td></tr>
<tr><td>F-trace threshold</td><td class="mono">&ge; &lceil;content-stems/3&rceil;
present in cited &para;s</td></tr>
<tr><td>anti-void plants</td><td class="mono">2 per run, min-closeness,
camo = own top-3 neighbors, sha-keyed slots</td></tr>
<tr><td>shuffle null</td><td class="mono">all mismatched (A&#772;&#7522;,B&#772;&#11388;)
pairs, different stems, full enumeration</td></tr>
<tr><td>judge context</td><td class="mono">writer prose to 6000 ch (was
1900 pre-v1.2), ledger stripped before judging</td></tr>
<tr><td>harvest floors</td><td class="mono">writer stage 50 ch (battery
convention) &middot; judge stage 15 ch (--min-chars, v1.2)</td></tr>
<tr><td>judge freshness</td><td class="mono">judge files must postdate the
run start (mtime gate) or are STALE-EXCLUDED</td></tr>
<tr><td>tie policy</td><td class="mono">single key: ex-self mean; ties
declared in the artifact, alphabetical display</td></tr>
<tr><td>writer/judge temps</td><td class="mono">declared per artifact; the
only non-frozen stages</td></tr>
</table>

<div class="eyebrow">&sect;M &mdash; Defect ledger (the corrections that
shaped the design)</div>
<p>#24 substring anchor-match (&ldquo;lying&rdquo; &isin;
&ldquo;identifying&rdquo;) &rarr; stem-set comparison &middot; #37
provenance hash globbed sibling corpora &rarr; loader whitelist, fix proven
by restoring the original fingerprint &middot; #39 hash-seed nondeterminism
laundered through a set &rarr; per-model counts, caught by the RESULT sha
on its maiden flight &middot; #44 cosine-only fidelity made retained words
look dropped &rarr; verbatim two-channel metric with exact zeros &middot;
#47 FOREGROUND sort/floor inversion &rarr; desc sort, &gt;0.01 floor, THIN
banner &middot; #49 gravity sign error carried for hours &rarr;
sign-semantics stated on this page, twice @@DEFECT_NEW@@</p>

<div class="eyebrow">&sect;N &mdash; Reproduction from this page alone</div>
<pre>1. Embedder: any bge-large-en-v1.5 checkpoint (or nearest
   successor); pin to CPU; unit-normalize all outputs.
2. Rulers: 50K = top-frequency English content words, stopworded,
   deduped by Porter stem; 253K = Wikipedia article titles; 184K =
   union corpus vocabulary. Exact historic rulers are fingerprinted
   by the shas below; the CONSTRUCTION is what matters.
3. Harvest: N models (5 frontier + 5 open-weight), one identical
   prompt, error-banner gate on refusal boilerplate, declared
   per-stage minimum-length floors.
4. Implement &sect;B methods per group F/L/ALL; readout per &sect;B; legs per
   &sect;C; convergence law per &sect;D; pricing per &sect;E; VF-IDF per &sect;F.
5. Writer stage: &sect;G prompts verbatim; ledger contract verbatim;
   anonymize; ex-self panel; audit per &sect;H; decoys per &sect;I; census
   per &sect;J.
6. Determinism check: run twice; RESULT shas must match. If they
   don't, you have an unfrozen stage you haven't declared &mdash; find it.
7. Honesty invariants: print raw metrics when gates saturate; price
   every agreement against its null; report what didn't work; the
   instrument that never delivers bad news cannot be trusted with
   good news.</pre>

<div class="eyebrow">&sect;O &mdash; Demo data appendix (static snapshot;
raw JSON linked)</div>
@@APPENDIX@@
<p class="small">Raw artifacts: @@RAWLINKS@@</p>

<footer>
<p class="closer">The silence was measured before it was read; the reading
was audited after it was written &mdash; contests included.</p>
<p>The commercial form of Summary Plus, EigenTrace's published instrument for
reading the unsaid. Discipline sha @@DSHA@@ &middot; rubric sha @@RSHA@@
&middot; feed sha @@FSHA@@ &middot; source sha @@SSHA@@ &middot; generated
@@GENERATED@@ &middot; writer + judge stages declared non-frozen; no RNG
outside those two declared stages &middot; no curated result lists &mdash;
even the decoys are measured; the only hand lists are the stopword and junk
guards, declared in &sect;L &middot; inputs are publicly available text;
every output is an original reading &middot; built by one person, every
stage inspectable &middot; page generator @@VERSIONSTR@@, gate report
printed at build time &middot; <a href="https://github.com/sdad1018/Eigentrace">GitHub &#8599;</a> &mdash; EigenTrace, 2026</p>
</footer>
</div>
<script src="/assets/sidenav.js" defer></script>
</body></html>
"""

G4_LINE = ("The winning reading led with the same silence &mdash; produced "
           "by different code, a different prompt, a different task."
           if strong else
           "The winning reading opened on the same silence the census "
           "measured (lexical overlap %d/3 top clusters; the words differ, "
           "the gap is the same)." % hits)

report("contact=%s | canonical=%s | og:image=%s"
       % (args.contact, args.canonical, args.og_image))

mapping = {
    "NCLASSES": str(n_classes),
    "CHIP_G4": CHIP_G4,
    "SPDISP": "%s (n=%d)" % (pm(sp_mean), len(selfpref)),
    "CONTACT": esc(args.contact),
    "CANONICAL": esc(args.canonical),
    "OGIMAGE": esc(args.og_image),
    "G5_CAVEAT": G5_CAVEAT,
    "SOURCE_COL": SOURCE_COL,
    "SP_COL": SP_COL,
    "WINNER": esc(winner),
    "WINSCORE": esc(WINSCORE),
    "LEDGER_STAT": LEDGER_STAT,
    "LEDGER_ROWS": LEDGER_ROWS,
    "CENSUS_ROWS": CENSUS_ROWS,
    "G4_LINE": G4_LINE,
    "STANDINGS_ROWS": STANDINGS_ROWS,
    "MATRIX": MATRIX,
    "MATRIX_NOTES": MATRIX_NOTES,
    "SELF_PREF_LINE": SELF_PREF_LINE,
    "DIVERGENCE": DIVERGENCE,
    "LOCALS_NOTE": LOCALS_NOTE,
    "THIN_LINE": THIN_LINE,
    "CONSENSUS_DEMO": CONSENSUS_DEMO,
    "G7_LINE": G7_LINE,
    "MARGIN_LINE": MARGIN_LINE,
    "FG_DEMO": FG_DEMO,
    "RERUN_NOTE": RERUN_NOTE,
    "CARRIAGE": CARRIAGE,
    "DISCIPLINE": esc(SPD),
    "RUBRIC": esc(RUB),
    "RUBRIC_AMEND": RUBRIC_AMEND,
    "AUDIT_DEMO": AUDIT_DEMO,
    "PLANTS_LINE": PLANTS_LINE,
    "CENSUS_DEMO": CENSUS_DEMO,
    "POLICY_ROWS": POLICY_ROWS,
    "PIN_LINE": PIN_LINE,
    "DEFECT_NEW": DEFECT_NEW,
    "APPENDIX": APPENDIX,
    "DSHA": esc(prov.get("discipline_sha", "?")),
    "RSHA": esc(prov.get("rubric_sha", "?")),
    "FSHA": esc(prov.get("feed_sha", "?")),
    "SSHA": esc(prov.get("source_sha", "?")),
    "GENERATED": esc(bake.get("generated", "?")),
    "VERSIONSTR": esc(VERSION),
}

page = TEMPLATE
for k, v in mapping.items():
    page = page.replace("@@" + k + "@@", v if isinstance(v, str) else str(v))

# copy raw artifacts next to the page, link relatively (G8)
outdir = os.path.dirname(os.path.abspath(args.out)) or "."
datadir = os.path.join(outdir, "data")
os.makedirs(datadir, exist_ok=True)
raw = {}
for tag, p in (("bakeoff", os.path.join(D, sid + "_bakeoff_v12.json")),
               ("centipede", os.path.join(D, sid + "_centipede.json")),
               ("census", os.path.join(D, sid + "_qcensus.json")),
               ("synthesis", p2 if syn2 else None)):
    if p and os.path.exists(p):
        dst = os.path.join(datadir, os.path.basename(p))
        shutil.copy2(p, dst)
        raw[tag] = "data/" + os.path.basename(p)
RAWLINKS = " &middot; ".join('<a href="%s">%s</a>' % (esc(v), esc(k))
                             for k, v in raw.items())
page = page.replace("@@RAWLINKS@@", RAWLINKS)

left = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", page)))
if not gate("G2", not left and "{{" not in page,
            "unfilled tokens: %s" % (left or "none")):
    sys.exit("STOP: template tokens survived -- page not written")

g8 = all(os.path.exists(os.path.join(outdir, v)) for v in raw.values())
gate("G8", g8, "raw artifacts copied + linked: %s" % sorted(raw))

os.makedirs(outdir, exist_ok=True)
open(args.out, "w", encoding="utf-8").write(page)

print("-" * 74)
hard = all(ok for name, ok in GATES
           if name in ("G1", "G2", "G3", "G6a", "G6b", "G6c", "GS", "G8"))
print("GATE SUMMARY: %s  (%s)"
      % ("ALL HARD GATES PASS" if hard else "FAILURES PRESENT",
         ", ".join("%s:%s" % (n, "P" if o else "F") for n, o in GATES)))
print("PAGE -> %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
