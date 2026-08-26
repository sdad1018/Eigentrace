#!/usr/bin/env python3
"""
synth.py — mechanical concordance over the ten-model readings, plus optional prose synthesis.

Mechanical layer (the spine; no model involved):
  1. pool every parsed reading for a word across models and samples;
  2. normalize (lowercase, strip punctuation, crude lemmatize, drop stopwords);
  3. cluster: same operation AND (Jaccard >= 0.5 on reading tokens
                                   OR, for phonetic_split, the same hyphenated split in `chain`);
  4. per cluster: representative (highest confidence), models (distinct), samples, sources,
     model_concordance = distinct models / models that returned >= 1 parsed reading for the word;
  5. partition: attested (>= 1 checkable source) / generative / singleton (one model, one sample).

Prose layer (--prose): sends prompts/synth_v1.txt with the table to every patient; stores all ten.
The app later shows the table in full and ONE prose synthesis; choosing which is a product decision
recorded in the ledger, not a test parameter.

Usage:
  python3 nameaxis/synth.py --word Mandalay
  python3 nameaxis/synth.py --all
  python3 nameaxis/synth.py --all --prose [--mock] [--only Claude,nous-hermes2:latest]
  --in out/readings   --out out/synth
"""
import argparse, json, pathlib, re, sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
SYNTH_PROMPT = HERE / "prompts" / "synth_v1.txt"

STOP = set("""the a an of to in on at for from by with and or as is are was were be been being it its this
that these those which who whom whose what where when how not no into over under one two three also then
than so such very can may might would could should has have had do does did i you he she they we me him her
them us their our your his my""".split())


def lemma(w):
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def toks(s):
    s = re.sub(r"[^a-z0-9\s\-']", " ", (s or "").lower())
    out = []
    for w in s.split():
        w = w.strip("-'")
        if not w or w in STOP or len(w) < 2:
            continue
        out.append(lemma(w))
    return out


def split_key(chain):
    """For phonetic_split: the hyphen/plus-joined split, normalized. e.g. 'pad + dock' -> 'pad-dock'."""
    found = re.findall(r"[a-z]+(?:\s*[-+·/]\s*[a-z]+)+", (chain or "").lower())
    keys = set()
    for f in found:
        keys.add(re.sub(r"\s*[-+·/]\s*", "-", f))
    return keys


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else 0.0


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


# ----------------------------------------------------------------------------- load
def load_word(indir, word):
    d = pathlib.Path(indir) / slug(word)
    rows, models_responding = [], set()
    for p in sorted(d.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not rec.get("parsed"):
            continue
        models_responding.add(rec["model"])
        for r in rec["parsed"]:
            rows.append({
                "model": rec["model"], "sample": rec["sample"], "kind": rec.get("kind"),
                "operation": str(r.get("operation", "")).strip().lower() or "unspecified",
                "chain": str(r.get("chain", "")).strip(),
                "reading": str(r.get("reading", "")).strip(),
                "languages": r.get("languages", []),
                "source": str(r.get("source", "generative")).strip() or "generative",
                "confidence": _num(r.get("confidence")),
            })
    return rows, models_responding


def _num(x):
    try:
        v = float(x)
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return 0.5


# ----------------------------------------------------------------------------- cluster
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster(rows, jthresh=0.5):
    n = len(rows)
    T = [toks(r["reading"]) for r in rows]
    K = [split_key(r["chain"]) for r in rows]
    uf = UF(n)
    for i in range(n):
        for j in range(i + 1, n):
            if rows[i]["operation"] != rows[j]["operation"]:
                continue
            same = jaccard(T[i], T[j]) >= jthresh
            if not same and rows[i]["operation"] == "phonetic_split" and (K[i] & K[j]):
                same = True
            if same:
                uf.union(i, j)
    groups = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return [sorted(g) for g in groups.values()]


def is_checkable(src):
    s = (src or "").strip().lower()
    return bool(s) and s not in {"generative", "none", "n/a", "na", "-", "unknown"}


def build_table(word, rows, models_responding):
    n_resp = max(1, len(models_responding))
    out = []
    for g in cluster(rows):
        members = [rows[i] for i in g]
        rep = max(members, key=lambda r: r["confidence"])
        models = sorted({m["model"] for m in members})
        sources = sorted({m["source"] for m in members if is_checkable(m["source"])})
        langs = sorted({str(l) for m in members for l in (m["languages"] or []) if l})
        entry = {
            "operation": rep["operation"], "reading": rep["reading"], "chain": rep["chain"],
            "models": models, "n_models": len(models), "n_samples": len(members),
            "sources": sources, "languages": langs,
            "confidence_max": round(max(m["confidence"] for m in members), 2),
            "model_concordance": round(len(models) / n_resp, 3),
            "partition": ("attested" if sources else
                          ("singleton" if len(members) == 1 else "generative")),
        }
        out.append(entry)
    out.sort(key=lambda e: (-e["model_concordance"], -e["n_samples"], -e["confidence_max"]))
    return {"word": word, "models_responding": sorted(models_responding),
            "n_readings": len(rows), "clusters": out}


def render_md(tab):
    L = [f"## Readings of «{tab['word']}»",
         f"{tab['n_readings']} readings from {len(tab['models_responding'])} responding readers "
         f"({', '.join(tab['models_responding'])}).", "",
         "| # | operation | reading | chain | readers | samples | sources | concordance | class |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(tab["clusters"], 1):
        L.append(f"| {i} | {e['operation']} | {_esc(e['reading'])} | {_esc(e['chain'])} | "
                 f"{', '.join(e['models'])} ({e['n_models']}) | {e['n_samples']} | "
                 f"{_esc('; '.join(e['sources'])) or '—'} | {e['model_concordance']:.2f} | {e['partition']} |")
    return "\n".join(L) + "\n"


def _esc(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


# ----------------------------------------------------------------------------- prose
def prose(word, table_md, patients, outdir):
    prompt = SYNTH_PROMPT.read_text(encoding="utf-8").replace("{word}", word).replace("{table}", table_md)
    d = pathlib.Path(outdir) / slug(word)
    d.mkdir(parents=True, exist_ok=True)
    for name, (kind, call) in patients.items():
        p = d / f"prose_{slug(name)}.json"
        if p.exists():
            continue
        try:
            txt = call([{"role": "user", "content": prompt}]) or ""
            err = None
        except Exception as e:
            txt, err = "", f"{type(e).__name__}: {e}"
        p.write_text(json.dumps({"word": word, "model": name, "kind": kind, "prompt": "synth_v1",
                                 "text": txt, "error": err}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   prose {name:22s} {'ok' if txt else 'FAIL'}")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--word")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--prose", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--direct-api", action="store_true")
    ap.add_argument("--api-max-tokens", type=int, default=3000)
    ap.add_argument("--use-mt-local", action="store_true")
    ap.add_argument("--local-max-tokens", type=int, default=1600)
    ap.add_argument("--local-timeout", type=int, default=600)
    ap.add_argument("--local-num-ctx", type=int, default=4096)
    ap.add_argument("--eigentrace", default="/mnt/c/Users/M4ISI/eigentrace")
    ap.add_argument("--in", dest="indir", default="out/readings")
    ap.add_argument("--out", default="out/synth")
    args = ap.parse_args()

    indir = pathlib.Path(args.indir)
    if args.all:
        words = [json.loads(next(d.glob("*.json")).read_text(encoding="utf-8"))["word"]
                 for d in sorted(indir.iterdir()) if d.is_dir() and not d.name.startswith("_") and any(d.glob("*.json"))]
    elif args.word:
        words = [args.word]
    else:
        ap.error("--word W or --all")

    patients = None
    if args.prose:
        sys.path.insert(0, str(HERE))
        import green_reader as G
        class A: pass
        a = A(); a.mock = args.mock; a.eigentrace = args.eigentrace
        a.direct_api = args.direct_api; a.api_max_tokens = args.api_max_tokens
        a.use_mt_local = args.use_mt_local; a.local_timeout = args.local_timeout
        a.local_max_tokens = args.local_max_tokens; a.local_num_ctx = args.local_num_ctx
        patients, _ = G.load_patients(a)
        if args.only:
            keep = {s.strip() for s in args.only.split(",")}
            patients = {k: v for k, v in patients.items() if k in keep}

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for w in words:
        rows, resp = load_word(indir, w)
        if not rows:
            print(f"{w!r}: no parsed readings"); continue
        tab = build_table(w, rows, resp)
        md = render_md(tab)
        d = outdir / slug(w)
        d.mkdir(parents=True, exist_ok=True)
        (d / "table.json").write_text(json.dumps(tab, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "table.md").write_text(md, encoding="utf-8")
        att = sum(1 for e in tab["clusters"] if e["partition"] == "attested")
        gen = sum(1 for e in tab["clusters"] if e["partition"] == "generative")
        sing = sum(1 for e in tab["clusters"] if e["partition"] == "singleton")
        top = tab["clusters"][0]["model_concordance"] if tab["clusters"] else 0
        print(f"{w!r}: {tab['n_readings']} readings -> {len(tab['clusters'])} clusters "
              f"(attested {att}, generative {gen}, singleton {sing}); top concordance {top:.2f}")
        if patients:
            prose(w, md, patients, outdir)


if __name__ == "__main__":
    main()
