#!/usr/bin/env python3
"""
green_reader.py — ten-model green-language reader on the confront10 substrate.

Wired to what confront10 actually exposes (recon 2026-08-25):
    C.API_PATIENTS   dict  {'ChatGPT','Claude','Gemini','DeepSeek','Grok'} -> callable(messages) -> str
    C.LOCAL_PATIENTS list  ['qwen2.5:14b','mistral:latest','llama3:latest','nous-hermes2:latest','mistral-small:latest']
    C.mt_local(messages, model) -> str
    C.OLLAMA         str   http://localhost:11434 (OLLAMA_HOST)

It runs the byte-locked prompt (prompts/green_v1.txt) through all ten patients, N samples per
model per word, and stores every raw response verbatim with its parse result. It never repairs
content: fences are stripped and a JSON array is located, that is all. Refusals are stored and
flagged, never retried into compliance.

Usage (repo root, Bertha):
  python3 nameaxis/green_reader.py --smoke                 # 'paddock' once to every patient, prints mt_local's source
  python3 nameaxis/green_reader.py --decoys                # ten locked decoys, N samples each
  python3 nameaxis/green_reader.py --pairs                 # the five pairs' names_to_read
  python3 nameaxis/green_reader.py --words Mandalay Luxor  # ad hoc
  python3 nameaxis/green_reader.py --mock --decoys         # offline pipeline test with fake patients

Options:
  --n 3                      samples per model per word (pilot LOCK = 3)
  --only Claude,qwen2.5:14b  restrict to these patients (exact names as confront10 spells them)
  --use-mt-local             call locals through C.mt_local (harness parity: /v1/chat/completions, max_tokens=420,
                             timeout 180). Default is the direct caller below, because 420 tokens truncates
                             a 6-12 reading JSON array (smoke 2026-08-25: three of five locals cut mid-array).
  --local-max-tokens 1600    direct caller: Ollama num_predict (== max_tokens)
  --local-timeout 600        direct caller: seconds per call (mistral-small ran 152 s for 420 tokens)
  --local-num-ctx 4096       direct caller: context window; small enough to keep 14 GB models on the 4080
  --no-prewarm               skip the 1-token warm call that loads each local model before its batch
  --direct-api               call the five API patients through nameaxis/api_direct.py (same keys, model env vars
                             and temperature as confront10; max_tokens raised to --api-max-tokens) instead of
                             C.API_PATIENTS, whose summary-sized caps truncated Claude on 116/117 samples
  --api-max-tokens 3000
  --skip a,b                 patients to leave out of this run (e.g. mistral-small:latest for a later overnight pass)
  --api-threads              default on: each API patient runs in its own thread while locals run in the main thread;
                             per-patient order is still sequential, so no provider gets a burst
  --no-api-threads           run everything sequentially
  --no-resume                re-run words that already have an ok output file
  --eigentrace PATH          confront10 location (default /mnt/c/Users/M4ISI/eigentrace)
  --out out/readings         output root
"""
import argparse, hashlib, inspect, json, os, pathlib, re, sys, time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompts" / "green_v1.txt"
NAMES_PATH = HERE / "events" / "names.json"
PROMPT_VERSION = "green_v1"

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
REFUSAL = re.compile(r"\b(I can(?:no|')t|I'?m unable|I am unable|I won'?t|cannot comply|I'?m sorry|as an AI)\b", re.I)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


# ----------------------------------------------------------------------------- parsing
def try_parse(raw):
    """Return (readings|None, error|None, extracted:bool). Never rewrites content."""
    if not raw or not raw.strip():
        return None, "empty", False
    txt, extracted = raw.strip(), False
    m = FENCE.search(txt)
    if m:
        txt, extracted = m.group(1).strip(), True
    try:
        obj = json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("["), txt.rfind("]")
        if a == -1 or b == -1 or b <= a:
            return None, "no_json_array", extracted
        try:
            obj, extracted = json.loads(txt[a:b + 1]), True
        except json.JSONDecodeError as e:
            return None, f"json_error: {e}", extracted
    if isinstance(obj, dict):  # some models wrap the array in an object
        for k in ("readings", "result", "results", "items", "data"):
            if isinstance(obj.get(k), list):
                obj, extracted = obj[k], True
                break
    if not isinstance(obj, list):
        return None, "not_a_list", extracted
    clean = [r for r in obj if isinstance(r, dict) and "reading" in r]
    if not clean:
        return None, "no_reading_objects", extracted
    return clean, None, extracted


# ----------------------------------------------------------------------------- patients
def make_direct_local(tag, host, timeout, max_tokens, num_ctx):
    """Mirrors C.mt_local's sampling (temperature 0.4) but lifts its 420-token cap.
    Uses /api/chat so num_predict and num_ctx can be set; errors surface instead of returning ''."""
    import requests

    def call(messages):
        r = requests.post(f"{host}/api/chat",
                          json={"model": tag, "messages": messages, "stream": False, "keep_alive": "10m",
                                "options": {"temperature": 0.4, "num_predict": max_tokens, "num_ctx": num_ctx}},
                          timeout=timeout)
        r.raise_for_status()
        return (r.json().get("message", {}).get("content", "") or "").strip()
    return call


def prewarm_local(tag, host):
    """1-token call so model load time is not charged to the first reading."""
    try:
        import requests
        requests.post(f"{host}/api/chat",
                      json={"model": tag, "messages": [{"role": "user", "content": "hi"}],
                            "stream": False, "keep_alive": "10m", "options": {"num_predict": 1}},
                      timeout=300)
    except Exception as e:  # warming is best-effort
        print(f"   (prewarm {tag} failed: {e})")


def unload_all(host):
    """Evict every resident model before the first warm, so no leftover from an earlier run squeezes us."""
    try:
        import requests
        for m in requests.get(f"{host}/api/ps", timeout=10).json().get("models", []):
            print(f"   evicting resident {m.get('name')} …", flush=True)
            requests.post(f"{host}/api/generate", json={"model": m.get("name"), "keep_alive": 0}, timeout=60)
    except Exception as e:
        print(f"   (unload_all failed: {e})")


def unload_local(tag, host):
    """Evict a model from VRAM (keep_alive 0) so the next local gets the whole card."""
    try:
        import requests
        requests.post(f"{host}/api/generate", json={"model": tag, "keep_alive": 0}, timeout=60)
    except Exception as e:
        print(f"   (unload {tag} failed: {e})")


def mock_patients():
    """Ten fake patients exercising the parser: clean, fenced, wrapped, junk, refusal."""
    def mk(kind, name):
        def call(messages):
            word = re.search(r"«(.*?)»", messages[-1]["content"]).group(1)
            h = int(sha(name + word)[:6], 16)
            base = [
                {"operation": "etymology", "chain": f"{word} < Latin root", "reading": f"a house of {word.lower()}",
                 "languages": ["en", "la"], "source": "OED", "confidence": 0.8},
                {"operation": "phonetic_split", "chain": f"{word[:2].lower()}-{word[2:].lower()}",
                 "reading": f"the {word[:2].lower()} that lays the {word[2:].lower()}", "languages": ["en"],
                 "source": "generative", "confidence": 0.5},
                {"operation": "cross_language_homophone", "chain": f"{word} ~ fr. {word.lower()}e",
                 "reading": "light over gold" if h % 3 == 0 else "a dead field reaped", "languages": ["fr"],
                 "source": "generative", "confidence": 0.4 + (h % 5) / 10},
            ]
            arr = json.dumps(base)
            if kind == "fenced": return "Here you go:\n```json\n" + arr + "\n```"
            if kind == "wrapped": return json.dumps({"readings": base})
            if kind == "junk": return "I read the word as light. " + arr[:20]
            if kind == "refusal": return "I'm sorry, but I can't produce occult readings of names."
            return arr
        return call
    kinds = ["clean", "fenced", "wrapped", "junk", "refusal", "clean", "clean", "fenced", "clean", "clean"]
    names = ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok",
             "qwen2.5:14b", "mistral:latest", "llama3:latest", "nous-hermes2:latest", "mistral-small:latest"]
    return {n: ("api" if i < 5 else "local", mk(k, n)) for i, (n, k) in enumerate(zip(names, kinds))}, None


def load_patients(args):
    if args.mock:
        return mock_patients()
    sys.path.insert(0, args.eigentrace)
    import confront10 as C  # noqa: E402
    patients = {}
    if getattr(args, "direct_api", False):
        sys.path.insert(0, str(HERE))
        import api_direct
        for name, fn in api_direct.patients(getattr(args, "api_max_tokens", 3000)).items():
            patients[name] = ("api", fn)
    else:
        for name, fn in C.API_PATIENTS.items():
            patients[name] = ("api", fn)
    for tag in C.LOCAL_PATIENTS:
        if getattr(args, "use_mt_local", False):
            patients[tag] = ("local", (lambda msgs, tag=tag: C.mt_local(msgs, tag)))
        else:
            patients[tag] = ("local", make_direct_local(tag, C.OLLAMA, args.local_timeout,
                                                        args.local_max_tokens, args.local_num_ctx))
    return patients, C


# ----------------------------------------------------------------------------- words
def load_words(args):
    names = json.loads(NAMES_PATH.read_text(encoding="utf-8"))
    words = []
    if args.smoke:
        words += names["smoke"]
    if args.decoys:
        words += names["decoys"]
    if args.pairs:
        for pair, ws in names["pairs"].items():
            words += ws
    if args.words:
        words += args.words
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w); out.append(w)
    return out


# ----------------------------------------------------------------------------- run
def run(args):
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_sha = sha(prompt)
    patients, C = load_patients(args)
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        patients = {k: v for k, v in patients.items() if k in keep}
        missing = keep - set(patients)
        if missing:
            print(f"!! unknown patients ignored: {sorted(missing)}")
    if args.skip:
        drop = {s_.strip() for s_ in args.skip.split(",")}
        patients = {k: v for k, v in patients.items() if k not in drop}
    n = 1 if args.smoke and not (args.decoys or args.pairs or args.words) else args.n
    words = load_words(args)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    caller_local = "C.mt_local(max_tokens=420,timeout=180)" if args.use_mt_local else \
        f"direct:/api/chat(temperature=0.4,num_predict={args.local_max_tokens},num_ctx={args.local_num_ctx},timeout={args.local_timeout})"
    host = getattr(C, "OLLAMA", "http://localhost:11434") if C else None

    print(f"prompt {PROMPT_VERSION} sha256 {prompt_sha}")
    print(f"patients ({len(patients)}): {list(patients)}")
    print(f"words ({len(words)}): {words}")
    print(f"samples/model/word: {n}   local caller: {caller_local}   out: {out}")
    if args.smoke and C is not None:
        print("── C.mt_local source (for the ledger) ──")
        try:
            print(inspect.getsource(C.mt_local))
        except Exception as e:
            print(f"(could not read source: {e})")

    # job order: each patient's jobs run sequentially; API patients may run in parallel threads
    # (one per provider), locals run one model at a time in the main thread so Ollama holds one model.
    jobs_by_model = {name: [(w, i) for w in words for i in range(n)] for name in patients}
    total = sum(len(v) for v in jobs_by_model.values())
    stats = {name: {"ok": 0, "parsed": 0, "fail": 0, "refusal_like": 0, "resumed": 0, "latency": []}
             for name in patients}
    counter = {"done": 0}
    import threading
    lock = threading.Lock()

    def do_one(name, w, i):
        kind, call = patients[name]
        path = out / slug(w) / f"{slug(name)}_{i}.json"
        s = stats[name]
        if path.exists() and not args.no_resume:
            try:
                prev = json.loads(path.read_text(encoding="utf-8"))
                if prev.get("ok") and (prev.get("parsed") or prev.get("refusal_like")):
                    s["ok"] += 1; s["resumed"] += 1
                    s["parsed"] += 1 if prev.get("parsed") else 0
                    s["refusal_like"] += 1 if prev.get("refusal_like") else 0
                    with lock:
                        counter["done"] += 1
                    return
            except Exception:
                pass
        msgs = [{"role": "user", "content": prompt.replace("{word}", w)}]
        t0 = time.time()
        err = None
        try:
            raw = call(msgs) or ""
        except Exception as e:
            raw, err = "", f"{type(e).__name__}: {e}"
        dt = round(time.time() - t0, 2)
        parsed, perr, extracted = try_parse(raw)
        rec = {
            "word": w, "model": name, "kind": kind, "sample": i,
            "prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha,
            "caller": caller_local if kind == "local" else
                      (f"direct_api(max_tokens={args.api_max_tokens})" if args.direct_api else "C.API_PATIENTS"),
            "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "latency_s": dt, "ok": bool(raw), "call_error": err,
            "raw": raw, "parsed": parsed, "parse_error": perr, "extracted": extracted,
            "n_readings": len(parsed) if parsed else 0,
            "refusal_like": bool(parsed is None and raw and REFUSAL.search(raw)),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        s["latency"].append(dt)
        if raw: s["ok"] += 1
        else: s["fail"] += 1
        if parsed: s["parsed"] += 1
        if rec["refusal_like"]: s["refusal_like"] += 1
        flag = "ok " if parsed else ("REF" if rec["refusal_like"] else ("raw" if raw else "ERR"))
        with lock:
            counter["done"] += 1
            print(f"[{counter['done']:4d}/{total}] {flag} {name:22s} {w!r:28s} #{i} {dt:6.1f}s "
                  f"{'n=' + str(len(parsed)) if parsed else (perr or err or '')}", flush=True)

    def run_model(name):
        for (w, i) in jobs_by_model[name]:
            do_one(name, w, i)

    api_names = [k for k, (kind, _) in patients.items() if kind == "api"]
    local_names = [k for k, (kind, _) in patients.items() if kind == "local"]
    threads = []
    if api_names and getattr(args, "api_threads", True):
        for name in api_names:
            t = threading.Thread(target=run_model, args=(name,), daemon=True)
            t.start(); threads.append(t)
    else:
        for name in api_names:
            run_model(name)
    prev_local = None
    if local_names and not args.mock:
        unload_all(host)
    for name in local_names:
        pending = [1 for (w, i) in jobs_by_model[name]
                   if not ((out / slug(w) / f"{slug(name)}_{i}.json").exists() and not args.no_resume)]
        if not args.mock and pending:
            if prev_local:
                print(f"   unloading {prev_local} …", flush=True); unload_local(prev_local, host)
            if not args.no_prewarm:
                print(f"   warming {name} …", flush=True); prewarm_local(name, host)
            prev_local = name
        run_model(name)
    if prev_local and not args.mock:
        unload_local(prev_local, host)
    for t in threads:
        t.join()

    # summary
    print("\n── summary ──")
    summary = {}
    for name, s in stats.items():
        lat = s["latency"]
        summary[name] = {"ok": s["ok"], "parsed": s["parsed"], "fail": s["fail"],
                         "refusal_like": s["refusal_like"], "resumed": s["resumed"],
                         "mean_latency_s": round(sum(lat) / len(lat), 1) if lat else None}
        print(f"{name:22s} ok={s['ok']:3d} parsed={s['parsed']:3d} fail={s['fail']:3d} "
              f"refusal_like={s['refusal_like']:3d} resumed={s['resumed']:3d} "
              f"mean_latency={summary[name]['mean_latency_s'] if lat else '-'}")
    runs = out / "_runs"
    runs.mkdir(exist_ok=True)
    (runs / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")).write_text(
        json.dumps({"prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha, "n": n,
                    "words": words, "patients": list(patients), "local_caller": caller_local,
                    "summary": summary}, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--decoys", action="store_true")
    ap.add_argument("--pairs", action="store_true")
    ap.add_argument("--words", nargs="*")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--only")
    ap.add_argument("--use-mt-local", action="store_true")
    ap.add_argument("--local-max-tokens", type=int, default=1600)
    ap.add_argument("--local-timeout", type=int, default=600)
    ap.add_argument("--local-num-ctx", type=int, default=4096)
    ap.add_argument("--no-prewarm", action="store_true")
    ap.add_argument("--direct-api", action="store_true")
    ap.add_argument("--api-max-tokens", type=int, default=3000)
    ap.add_argument("--skip")
    ap.add_argument("--api-threads", dest="api_threads", action="store_true", default=True)
    ap.add_argument("--no-api-threads", dest="api_threads", action="store_false")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--eigentrace", default="/mnt/c/Users/M4ISI/eigentrace")
    ap.add_argument("--out", default="out/readings")
    args = ap.parse_args()
    if not (args.smoke or args.decoys or args.pairs or args.words):
        ap.error("choose --smoke, --decoys, --pairs, or --words")
    run(args)


if __name__ == "__main__":
    main()
