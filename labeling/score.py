#!/usr/bin/env python3
"""
score.py -- score filled labeling forms against the instrument's key.

Reads a kit directory (story_NN.md forms plus key.json) and reports:

  1. precision / recall / F1 of the instrument's killshot omission calls
     (model in omitted_by) against the human O labels, per model and
     overall, with Wilson 95% intervals on precision and recall;
     a secondary run counts human P as omitted too;
  2. the share of void words judged relevant (R) for instrument words
     versus the blind random-vocabulary controls, with Wilson intervals,
     a Fisher exact p-value, and a per-origin breakdown;
  3. the 0-3 severity distribution per model (de-anonymised via key.json)
     and the mean number of omitted facts listed per model;
  4. Cohen's kappa between two raters when --rater2 points at a second
     directory of filled forms for the same key.

Blank or unparseable answers are unlabeled: they are counted and skipped,
never treated as negatives. No third-party packages are required.

    python3 labeling/score.py /home/remvelchio/eigentrace/labeling/kit_2026-09-10
    python3 labeling/score.py KIT --rater2 KIT_rater2 --json out.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

MODELS = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]
LETTERS = ["A", "B", "C", "D", "E"]
FORM_RE = re.compile(r"^story_(\d+)\.md$")
Z95 = 1.959963984540054


# --------------------------------------------------------------------------
# answer-block reader (a small indentation parser; PyYAML is not required)
# --------------------------------------------------------------------------
def extract_answer_block(text: str):
    blocks = re.findall(r"```ya?ml[ \t]*\n(.*?)\n```", text, flags=re.S)
    return blocks[-1] if blocks else None


def _strip_comment(v: str) -> str:
    # drop a trailing "# comment" (only when preceded by whitespace or at start)
    m = re.match(r"^(.*?)(?:\s+#.*|^#.*)?$", v)
    return (m.group(1) if m else v).strip()


def _scalar(v: str):
    v = _strip_comment(v)
    if v == "" or v.lower() in ("null", "~"):
        return None
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _unquote_key(k: str) -> str:
    k = k.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
        k = k[1:-1]
        if k and "\\" in k:
            k = k.replace('\\"', '"').replace("\\\\", "\\")
    return k


def _flow_map(v: str):
    v = _strip_comment(v)
    if not (v.startswith("{") and v.endswith("}")):
        return None
    out = OrderedDict()
    for part in v[1:-1].split(","):
        if ":" not in part:
            continue
        k, val = part.split(":", 1)
        out[_unquote_key(k)] = _scalar(val)
    return out


def parse_form(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    block = extract_answer_block(text)
    if block is None:
        return None, "no yaml answer block"
    return parse_block(block), None


def parse_block(block: str):
    """Parse the restricted YAML subset used by the forms into nested
    OrderedDicts, lists of strings and scalars. A mapping key whose next
    non-blank line is a '- ' item becomes a list. Anything unrecognised is
    kept as a string (and later treated as unlabeled), never an error."""
    lines = [l.replace("\t", "    ") for l in block.splitlines()]
    # find keys followed by list items (a trailing "# comment" on the key line is
    # allowed; the items may sit at the key's own indent or deeper, as in YAML)
    list_keys = set()
    for i, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([^:\-#][^:]*?):\s*(?:#.*)?$", raw)
        if not m:
            continue
        ind = len(m.group(1))
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            nind = len(nxt) - len(nxt.lstrip(" "))
            if nind >= ind and (nxt.strip() == "-" or nxt.strip().startswith("- ")):
                list_keys.add(i)
            break
    root = OrderedDict()
    stack = [(-1, root)]
    for i, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(-1, root)]
        parent = stack[-1][1]
        if line == "-" or line.startswith("- "):
            item = _strip_comment(line[1:].strip())
            if isinstance(parent, list) and item:
                parent.append(_scalar(item) if item[0] in "\"'" else item)
            continue
        # a mapping key ends any list that sits at the same indent
        while isinstance(parent, list) and len(stack) > 1:
            stack.pop()
            parent = stack[-1][1]
        m = re.match(r"^((?:\"[^\"]*\"|'[^']*'|[^:])+?):(?:\s+(.*))?$", line)
        if not m or not isinstance(parent, OrderedDict):
            continue
        k, v = _unquote_key(m.group(1)), (m.group(2) or "").rstrip()
        v_nc = _strip_comment(v)
        if i in list_keys:
            child = []
            parent[k] = child
            # list items may share the key's indent: keep the list open for them
            stack.append((indent - 0.5, child))
        elif v_nc == "":
            child = OrderedDict()
            parent[k] = child
            stack.append((indent, child))
        elif v_nc.startswith("{"):
            parent[k] = _flow_map(v_nc) or _scalar(v)
        elif v_nc == "[]":
            parent[k] = []
        else:
            parent[k] = _scalar(v)
    return root


# --------------------------------------------------------------------------
# normalisers: anything not recognised is "unlabeled"
# --------------------------------------------------------------------------
def norm_opc(v):
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("O", "OMIT", "OMITTED"):
        return "O"
    if s in ("P", "PARTIAL"):
        return "P"
    if s in ("C", "COVERED", "COVER"):
        return "C"
    return None


def norm_ri(v):
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("R", "REL", "RELEVANT", "Y", "YES", "1"):
        return "R"
    if s in ("I", "IRR", "IRRELEVANT", "N", "NO", "0"):
        return "I"
    return None


def norm_sev(v):
    if v is None:
        return None
    s = str(v).strip()
    if re.fullmatch(r"[0-3]", s):
        return int(s)
    return None


def norm_facts(v):
    if v is None:
        return None
    if isinstance(v, list):
        items = [str(x).strip() for x in v if str(x).strip()]
        return items
    if isinstance(v, dict):
        return [] if not v else None
    s = str(v).strip()
    if s.lower() in ("", "[]", "none", "-", "nothing"):
        return []
    return [s]


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = Z95):
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def prf(tp, fp, fn):
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = (2 * prec * rec / (prec + rec)) if prec is not None and rec is not None and (prec + rec) else None
    return OrderedDict([
        ("tp", tp), ("fp", fp), ("fn", fn),
        ("precision", prec), ("precision_ci95", wilson(tp, tp + fp)),
        ("recall", rec), ("recall_ci95", wilson(tp, tp + fn)),
        ("f1", f1),
    ])


def fisher_exact_two_sided(a, b, c, d):
    """2x2 table [[a, b], [c, d]] two-sided Fisher exact p (sum of tables
    with probability <= observed)."""
    n = a + b + c + d
    if n == 0:
        return None
    r1, c1 = a + b, a + c
    lo, hi = max(0, r1 + c1 - n), min(r1, c1)

    def logp(x):
        return (math.lgamma(r1 + 1) + math.lgamma(n - r1 + 1) + math.lgamma(c1 + 1) + math.lgamma(n - c1 + 1)
                - math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(r1 - x + 1)
                - math.lgamma(c1 - x + 1) - math.lgamma(n - r1 - c1 + x + 1))
    obs = logp(a)
    tot = 0.0
    for x in range(lo, hi + 1):
        lp = logp(x)
        if lp <= obs + 1e-9:
            tot += math.exp(lp)
    return min(1.0, tot)


def cohen_kappa(pairs, weights=None):
    """pairs: list of (label1, label2). weights: None (unweighted) or
    'linear' for ordinal integer labels. Returns (kappa, n)."""
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return None, 0
    cats = sorted({a for a, _ in pairs} | {b for _, b in pairs}, key=lambda x: (str(type(x)), x))
    idx = {c: i for i, c in enumerate(cats)}
    m = len(cats)
    obs = [[0.0] * m for _ in range(m)]
    for a, b in pairs:
        obs[idx[a]][idx[b]] += 1
    r = [sum(row) for row in obs]
    c = [sum(obs[i][j] for i in range(m)) for j in range(m)]
    if weights == "linear":
        w = [[abs(i - j) / max(1, m - 1) for j in range(m)] for i in range(m)]
    else:
        w = [[0.0 if i == j else 1.0 for j in range(m)] for i in range(m)]
    po = sum(w[i][j] * obs[i][j] for i in range(m) for j in range(m)) / n
    pe = sum(w[i][j] * r[i] * c[j] / n for i in range(m) for j in range(m)) / n
    if pe == 0:
        return (1.0 if po == 0 else None), n
    return 1.0 - po / pe, n


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load_forms(kit_dir: Path):
    forms = {}
    problems = []
    for p in sorted(kit_dir.iterdir()):
        m = FORM_RE.match(p.name)
        if not m:
            continue
        k = int(m.group(1))
        data, err = parse_form(p)
        if err:
            problems.append(f"{p.name}: {err}")
            continue
        forms[k] = data
    return forms, problems


def extract_labels(key, forms):
    """Flatten human answers into typed records keyed by (story, item, model)."""
    recs = {
        "killshot": {},   # (k, ks_id, model) -> 'O'/'P'/'C'
        "void": {},       # (k, word) -> 'R'/'I'
        "severity": {},   # (k, model) -> 0..3
        "facts": {},      # (k, model) -> list[str]
        "minutes": {},    # k -> float
    }
    unl = Counter()
    for s in key["stories"]:
        k = s["k"]
        f = forms.get(k)
        if f is None:
            unl["forms_missing"] += 1
            continue
        letters = s["letters"]
        # minutes
        try:
            mins = f.get("minutes")
            recs["minutes"][k] = float(mins) if mins not in (None, "") else None
        except (TypeError, ValueError):
            recs["minutes"][k] = None
        # omissions
        om = f.get("omissions") or {}
        for L in LETTERS:
            model = letters[L]
            ans = om.get(L) if isinstance(om, dict) else None
            sev = norm_sev(ans.get("severity")) if isinstance(ans, dict) else None
            facts = norm_facts(ans.get("facts")) if isinstance(ans, dict) else None
            if sev is None:
                unl["severity"] += 1
                unl["facts"] += 1  # an empty facts list only counts once severity is given
            else:
                recs["severity"][(k, model)] = sev
                if facts is None:
                    unl["facts"] += 1
                else:
                    recs["facts"][(k, model)] = facts
        # killshots
        kans = f.get("killshots") or {}
        for ks in s["killshots"]:
            row = kans.get(ks["id"]) if isinstance(kans, dict) else None
            for L in LETTERS:
                v = norm_opc(row.get(L)) if isinstance(row, dict) else None
                if v is None:
                    unl["killshot"] += 1
                else:
                    recs["killshot"][(k, ks["id"], letters[L])] = v
        # void words
        vans = f.get("void_words") or {}
        for w in s["void_words"]:
            v = norm_ri(vans.get(w["word"])) if isinstance(vans, dict) else None
            if v is None:
                unl["void"] += 1
            else:
                recs["void"][(k, w["word"])] = v
    return recs, unl


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def score_killshots(key, recs, partial_as_omitted=False):
    per = {m: Counter() for m in MODELS}
    for s in key["stories"]:
        k = s["k"]
        for ks in s["killshots"]:
            for m in MODELS:
                h = recs["killshot"].get((k, ks["id"], m))
                if h is None:
                    per[m]["unlabeled"] += 1
                    continue
                per[m]["labeled"] += 1
                inst = ks["instrument_calls"][m] == "O"
                human = (h == "O") or (partial_as_omitted and h == "P")
                if inst and human:
                    per[m]["tp"] += 1
                elif inst and not human:
                    per[m]["fp"] += 1
                elif (not inst) and human:
                    per[m]["fn"] += 1
                else:
                    per[m]["tn"] += 1
    out = OrderedDict()
    tot = Counter()
    for m in MODELS:
        c = per[m]
        tot.update(c)
        d = prf(c["tp"], c["fp"], c["fn"])
        d["tn"] = c["tn"]
        d["labeled"] = c["labeled"]
        d["unlabeled"] = c["unlabeled"]
        d["human_omission_rate"] = ((c["tp"] + c["fn"]) / c["labeled"]) if c["labeled"] else None
        d["instrument_omission_rate"] = ((c["tp"] + c["fp"]) / c["labeled"]) if c["labeled"] else None
        out[m] = d
    d = prf(tot["tp"], tot["fp"], tot["fn"])
    d["tn"] = tot["tn"]
    d["labeled"] = tot["labeled"]
    d["unlabeled"] = tot["unlabeled"]
    d["human_omission_rate"] = ((tot["tp"] + tot["fn"]) / tot["labeled"]) if tot["labeled"] else None
    d["instrument_omission_rate"] = ((tot["tp"] + tot["fp"]) / tot["labeled"]) if tot["labeled"] else None
    out["overall"] = d
    return out


def score_void(key, recs):
    by_origin = defaultdict(Counter)
    for s in key["stories"]:
        k = s["k"]
        for w in s["void_words"]:
            v = recs["void"].get((k, w["word"]))
            grp = w["origin"]
            if v is None:
                by_origin[grp]["unlabeled"] += 1
                continue
            by_origin[grp]["labeled"] += 1
            by_origin[grp][v] += 1
    inst = Counter()
    for grp, c in by_origin.items():
        if grp != "random":
            inst.update(c)
    rand = by_origin.get("random", Counter())

    def rate(c):
        n = c["labeled"]
        return OrderedDict([
            ("relevant", c["R"]), ("irrelevant", c["I"]), ("labeled", n), ("unlabeled", c["unlabeled"]),
            ("relevant_rate", (c["R"] / n) if n else None), ("ci95", wilson(c["R"], n)),
        ])
    out = OrderedDict()
    out["instrument"] = rate(inst)
    out["random"] = rate(rand)
    ri, rr = out["instrument"]["relevant_rate"], out["random"]["relevant_rate"]
    out["difference"] = (ri - rr) if ri is not None and rr is not None else None
    out["fisher_p_two_sided"] = fisher_exact_two_sided(inst["R"], inst["I"], rand["R"], rand["I"]) \
        if inst["labeled"] and rand["labeled"] else None
    out["by_origin"] = OrderedDict((g, rate(by_origin[g])) for g in sorted(by_origin))
    return out


def score_severity(key, recs):
    out = OrderedDict()
    for m in MODELS + ["overall"]:
        sevs = [v for (k, mm), v in recs["severity"].items() if m == "overall" or mm == m]
        facts = [len(v) for (k, mm), v in recs["facts"].items() if m == "overall" or mm == m]
        n_forms = len(key["stories"]) * (5 if m == "overall" else 1)
        dist = Counter(sevs)
        out[m] = OrderedDict([
            ("labeled", len(sevs)), ("unlabeled", n_forms - len(sevs)),
            ("distribution", OrderedDict((str(i), dist.get(i, 0)) for i in range(4))),
            ("mean_severity", (sum(sevs) / len(sevs)) if sevs else None),
            ("share_severity_ge2", (sum(1 for v in sevs if v >= 2) / len(sevs)) if sevs else None),
            ("share_severity_ge2_ci95", wilson(sum(1 for v in sevs if v >= 2), len(sevs))),
            ("mean_facts_listed", (sum(facts) / len(facts)) if facts else None),
            ("facts_labeled", len(facts)),
        ])
    return out


def score_agreement(key, recs1, recs2):
    out = OrderedDict()
    ks_pairs = [(recs1["killshot"].get(i), recs2["killshot"].get(i))
                for i in set(recs1["killshot"]) | set(recs2["killshot"])]
    kap, n = cohen_kappa(ks_pairs)
    out["killshot_OPC_kappa"] = OrderedDict([("kappa", kap), ("n", n)])
    kap, n = cohen_kappa([(None if a is None else (a == "O"), None if b is None else (b == "O"))
                          for a, b in ks_pairs])
    out["killshot_O_vs_notO_kappa"] = OrderedDict([("kappa", kap), ("n", n)])
    v_pairs = [(recs1["void"].get(i), recs2["void"].get(i)) for i in set(recs1["void"]) | set(recs2["void"])]
    kap, n = cohen_kappa(v_pairs)
    out["void_RI_kappa"] = OrderedDict([("kappa", kap), ("n", n)])
    s_pairs = [(recs1["severity"].get(i), recs2["severity"].get(i))
               for i in set(recs1["severity"]) | set(recs2["severity"])]
    kap, n = cohen_kappa(s_pairs)
    out["severity_kappa"] = OrderedDict([("kappa", kap), ("n", n)])
    kap, n = cohen_kappa(s_pairs, weights="linear")
    out["severity_linear_weighted_kappa"] = OrderedDict([("kappa", kap), ("n", n)])
    return out


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def _fmt(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, tuple):
        return f"[{x[0]:.{nd}f}, {x[1]:.{nd}f}]"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def print_report(rep):
    print("=" * 78)
    print(f"Labeling kit score  --  kit: {rep['kit_dir']}")
    print(f"stories in key: {rep['n_stories']}   forms parsed: {rep['n_forms']}   "
          f"raters: {rep['n_raters']}")
    if rep["problems"]:
        print("form problems:")
        for p in rep["problems"]:
            print(f"  - {p}")
    u = rep["unlabeled"]
    print(f"unlabeled cells: killshot {u.get('killshot', 0)}, void {u.get('void', 0)}, "
          f"severity {u.get('severity', 0)}, facts {u.get('facts', 0)}, "
          f"forms missing {u.get('forms_missing', 0)}")
    mins = [v for v in rep["minutes"].values() if v]
    if mins:
        print(f"minutes per story: mean {sum(mins)/len(mins):.1f} over {len(mins)} forms")
    for title, keyname in (("KILLSHOT OMISSION CALLS vs human O", "killshots_O"),
                           ("KILLSHOT OMISSION CALLS vs human O or P", "killshots_OP")):
        print("-" * 78)
        print(title)
        print(f"{'model':10} {'n':>4} {'tp':>4} {'fp':>4} {'fn':>4} {'tn':>4}  "
              f"{'prec':>6} {'wilson95':>16}  {'rec':>6} {'wilson95':>16}  {'f1':>6}")
        for m, d in rep[keyname].items():
            print(f"{m:10} {d['labeled']:>4} {d['tp']:>4} {d['fp']:>4} {d['fn']:>4} {d['tn']:>4}  "
                  f"{_fmt(d['precision']):>6} {_fmt(d['precision_ci95']):>16}  "
                  f"{_fmt(d['recall']):>6} {_fmt(d['recall_ci95']):>16}  {_fmt(d['f1']):>6}")
    print("-" * 78)
    print("VOID WORDS judged relevant (R)")
    v = rep["void"]
    for g in ("instrument", "random"):
        d = v[g]
        print(f"{g:12} R {d['relevant']:>4} / labeled {d['labeled']:>4}  rate {_fmt(d['relevant_rate'])} "
              f"{_fmt(d['ci95'])}  unlabeled {d['unlabeled']}")
    print(f"difference (instrument - random): {_fmt(v['difference'])}   "
          f"Fisher exact p: {_fmt(v['fisher_p_two_sided'], 4)}")
    for g, d in v["by_origin"].items():
        print(f"  origin {g:14} R {d['relevant']:>4} / {d['labeled']:>4}  rate {_fmt(d['relevant_rate'])} "
              f"{_fmt(d['ci95'])}")
    print("-" * 78)
    print("SEVERITY of worst omission per summary (0-3), by model")
    print(f"{'model':10} {'n':>4}  {'0':>4} {'1':>4} {'2':>4} {'3':>4}  {'mean':>6}  {'>=2':>6} {'wilson95':>16}  {'facts/summary':>14}")
    for m, d in rep["severity"].items():
        dist = d["distribution"]
        print(f"{m:10} {d['labeled']:>4}  {dist['0']:>4} {dist['1']:>4} {dist['2']:>4} {dist['3']:>4}  "
              f"{_fmt(d['mean_severity'], 2):>6}  {_fmt(d['share_severity_ge2']):>6} "
              f"{_fmt(d['share_severity_ge2_ci95']):>16}  {_fmt(d['mean_facts_listed'], 2):>14}")
    if rep.get("agreement"):
        print("-" * 78)
        print("INTER-RATER AGREEMENT (Cohen's kappa, rater 1 vs rater 2)")
        for name, d in rep["agreement"].items():
            print(f"  {name:32} kappa {_fmt(d['kappa'])}  n {d['n']}")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kit_dir", type=Path, help="directory with story_NN.md forms and key.json")
    ap.add_argument("--key", type=Path, default=None, help="key.json (default: kit_dir/key.json)")
    ap.add_argument("--rater2", type=Path, default=None,
                    help="second directory of filled forms for the same key (kappa)")
    ap.add_argument("--json", type=Path, default=None, help="write the full report as JSON here")
    args = ap.parse_args()

    key_path = args.key or (args.kit_dir / "key.json")
    with open(key_path, encoding="utf-8") as fh:
        key = json.load(fh)
    forms, problems = load_forms(args.kit_dir)
    recs, unl = extract_labels(key, forms)

    rep = OrderedDict()
    rep["kit_dir"] = str(args.kit_dir)
    rep["key"] = str(key_path)
    rep["n_stories"] = len(key["stories"])
    rep["n_forms"] = len(forms)
    rep["n_raters"] = 1
    rep["problems"] = problems
    rep["unlabeled"] = dict(unl)
    rep["minutes"] = {str(k): v for k, v in recs["minutes"].items()}
    rep["killshots_O"] = score_killshots(key, recs, partial_as_omitted=False)
    rep["killshots_OP"] = score_killshots(key, recs, partial_as_omitted=True)
    rep["void"] = score_void(key, recs)
    rep["severity"] = score_severity(key, recs)
    if args.rater2:
        forms2, problems2 = load_forms(args.rater2)
        recs2, unl2 = extract_labels(key, forms2)
        rep["n_raters"] = 2
        rep["problems"] += [f"rater2 {p}" for p in problems2]
        rep["rater2_unlabeled"] = dict(unl2)
        rep["agreement"] = score_agreement(key, recs, recs2)
        rep["rater2_killshots_O"] = score_killshots(key, recs2, partial_as_omitted=False)
        rep["rater2_void"] = score_void(key, recs2)
        rep["rater2_severity"] = score_severity(key, recs2)
    print_report(rep)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
        print(f"json written to {args.json}")


if __name__ == "__main__":
    main()
