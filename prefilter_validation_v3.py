#!/usr/bin/env python3
"""
Pre-Filter Validation v3 — clause-level modifier-retention.

Pre-registered: anamnesis_results/prefilter_validation_v2_preregistration.md
(committed before this judge run).

v3 fix over v2: the judge now sees the REAL source sentence each summary was derived
from (pulled from PAIRS in entity_swap_experiment.py and joined to each record by
modifier+version), NOT a fabricated stub. This makes the judge's comparison real, so
the AUC actually measures what the prereg says.

Reuses the 216 already-collected, already-geometrically-scored responses from
entity_swap_full_results.json. The ONLY new measurement is the discriminating judge.

Verdict: prompt-clustered AUC > 0.75 AND bootstrap CI lower bound > 0.5 -> narrow claim.
Else -> null. A degenerate judge distribution (one class < 15%) -> null.

Usage:
  python3 prefilter_validation_v3.py --limit 20 --selfcheck 10   # DRY RUN first
  python3 prefilter_validation_v3.py                              # full 216
"""
import os, sys, json, time, random, argparse
from collections import defaultdict, Counter

try:
    from dotenv import load_dotenv
    for _envpath in ("/home/remvelchio/eigentrace/.env",
                     "/mnt/c/Users/M4ISI/eigentrace/.env",
                     ".env"):
        if os.path.exists(_envpath):
            load_dotenv(_envpath); break
except Exception:
    pass

import requests

RESULTS_FILE = "anamnesis_results/entity_swap_full_results.json"
EXPERIMENT_FILE = "entity_swap_experiment.py"   # source of the real PAIRS sentences
JUDGE_MODEL  = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
POSITIVE_SEV = 2
AUC_THRESHOLD = 0.75
DEGENERATE_FRAC = 0.15

JUDGE_RUBRIC = """You will see (1) an ORIGINAL factual statement containing a specific modifier, (2) a SUMMARY of it, and (3) the MODIFIER in question. Rate how much the SUMMARY preserves the specific force/meaning that the MODIFIER contributes to the ORIGINAL — not overall quality, only that modifier's force.
0 = modifier's force fully preserved (explicitly or via clear equivalent)
1 = mostly preserved, slightly weakened
2 = noticeably softened or hedged
3 = dropped entirely or contradicted
Respond with ONLY the integer 0-3."""


def load_real_sources():
    """Import PAIRS from the experiment script to get the REAL source sentences.
    Returns dict keyed (modifier, 'ai'|'corp') -> source sentence."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("eswap", EXPERIMENT_FILE)
    mod = importlib.util.module_from_spec(spec)
    # The experiment script runs API calls at import (it has a RUN block at module
    # level). Guard against that by setting a flag the script checks — but it may not.
    # Safer: parse PAIRS literally without executing the run block.
    import ast
    src = open(EXPERIMENT_FILE).read()
    tree = ast.parse(src)
    pairs = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PAIRS":
                    pairs = ast.literal_eval(node.value)
    if pairs is None:
        raise RuntimeError("Could not find PAIRS in experiment file")
    lookup = {}
    for p in pairs:
        lookup[(p["modifier"], "ai")] = p["ai"]
        lookup[(p["modifier"], "corp")] = p["corp"]
    return lookup


def judge_call(original, summary, modifier, max_retries=6):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None, "", "no_key"
    user = (f"ORIGINAL:\n{original}\n\nSUMMARY:\n{summary}\n\n"
            f"MODIFIER: {modifier}\n\nInteger 0-3 only:")
    last_err = "unknown"
    for attempt in range(max_retries):
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": JUDGE_MODEL, "temperature": 0.0, "max_completion_tokens": 50,
                      "messages": [{"role": "system", "content": JUDGE_RUBRIC},
                                   {"role": "user", "content": user}]},
                timeout=40)
            if r.status_code == 429:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                last_err = "429 (retried)"
                continue
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
            for ch in raw:
                if ch in "0123":
                    return int(ch), raw, None
            return None, raw, "unparsed"
        except Exception as e:
            last_err = str(e)[:80]
            time.sleep((2 ** attempt) + random.uniform(0, 1))
    return None, "", last_err


def auc_score(scores, labels):
    pos = [(-s) for s, l in zip(scores, labels) if l == 1]
    neg = [(-s) for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n: wins += 1
            elif p == n: wins += 0.5
    return wins / (len(pos) * len(neg))


def clustered_auc(items):
    by_pair = defaultdict(list)
    for it in items:
        by_pair[it["pair_key"]].append(it)
    aucs = []
    for k, grp in by_pair.items():
        a = auc_score([g["geometric"] for g in grp], [g["label"] for g in grp])
        if a is not None:
            aucs.append(a)
    if not aucs:
        return None, 0
    return sum(aucs) / len(aucs), len(aucs)


def bootstrap_ci(items, n_boot=2000):
    by_pair = defaultdict(list)
    for it in items:
        by_pair[it["pair_key"]].append(it)
    keys = list(by_pair.keys())
    if len(keys) < 2:
        return None, None
    boots = []
    for _ in range(n_boot):
        samp = []
        for _ in range(len(keys)):
            samp.extend(by_pair[random.choice(keys)])
        a = auc_score([x["geometric"] for x in samp], [x["label"] for x in samp])
        if a is not None:
            boots.append(a)
    if len(boots) < 100:
        return None, None
    boots.sort()
    return boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--selfcheck", type=int, default=0)
    args = ap.parse_args()

    print("=" * 64)
    print("PRE-FILTER VALIDATION v3 — clause-level modifier-retention")
    print(f"Judge: {JUDGE_MODEL} @ temp 0.0  |  positive: sev >= {POSITIVE_SEV}")
    print("=" * 64)

    sources = load_real_sources()
    print(f"Loaded {len(sources)} real source sentences from PAIRS")

    d = json.load(open(RESULTS_FILE))
    records = d["results"]
    items = []
    missing = 0
    for rec in records:
        sr = rec.get("semantic_retention")
        resp = rec.get("response", "")
        mod = rec.get("modifier", "")
        ver = rec.get("version", "")
        side = "ai" if ver == "AI_ENTITY" else "corp" if ver == "CORP_ENTITY" else None
        if sr is None or not resp or not mod or side is None:
            continue
        original = sources.get((mod, side))
        if original is None:
            missing += 1
            continue
        items.append({
            "geometric": float(sr),
            "response": resp,
            "modifier": mod,
            "original": original,         # REAL source sentence now
            "pair_key": f"{mod}|{side}",
            "version": ver,
            "model": rec.get("model", ""),
        })
    if missing:
        print(f"   (skipped {missing} records with no matching source in PAIRS)")

    if args.limit:
        items = items[:args.limit]
    print(f"Loaded {len(items)} responses "
          f"({len(set(i['pair_key'] for i in items))} pair-clusters)")

    print(f"\n[1/2] Judging {len(items)} responses (against REAL sources)...")
    errs = unparsed = 0
    t0 = time.time()
    for i, it in enumerate(items):
        sev, raw, err = judge_call(it["original"], it["response"], it["modifier"])
        it["judge_sev"] = sev
        if err == "unparsed": unparsed += 1
        elif err: errs += 1
        if i % 20 == 0:
            print(f"   {i}/{len(items)}  (errors={errs} unparsed={unparsed})", flush=True)
        time.sleep(0.15)
    judged = [it for it in items if it.get("judge_sev") is not None]
    print(f"   judged {len(judged)}/{len(items)} in {time.time()-t0:.0f}s "
          f"(errors={errs}, unparsed={unparsed})")
    if errs + unparsed > 0.10 * max(1, len(items)):
        print("   !! >10% errors/unparsed — see prereg failure clause.")

    for it in judged:
        it["label"] = 1 if it["judge_sev"] >= POSITIVE_SEV else 0

    dist = dict(sorted(Counter(it["judge_sev"] for it in judged).items()))
    pos = sum(it["label"] for it in judged)
    print(f"\n   severity distribution: {dist}")
    print(f"   positive (sev>={POSITIVE_SEV}): {pos}/{len(judged)} "
          f"({100*pos/max(1,len(judged)):.0f}%)")

    minority = min(pos, len(judged) - pos)
    if len(judged) and minority < DEGENERATE_FRAC * len(judged):
        print("\n" + "=" * 64)
        print(f"VERDICT: NULL — degenerate judge distribution "
              f"(minority {minority}/{len(judged)} < {int(DEGENERATE_FRAC*100)}%).")
        print("Per prereg: rubric non-discriminating on this set. No claim.")
        print("=" * 64)
        _save(d, items, judged, None, None, None)
        return

    print("\n[2/2] Metrics")
    scores = [it["geometric"] for it in judged]
    labels = [it["label"] for it in judged]
    pooled = auc_score(scores, labels)
    cl_auc, n_clusters = clustered_auc(judged)
    print(f"   POOLED AUC: {pooled:.3f}" if pooled is not None else "   POOLED AUC: n/a")
    print(f"   PROMPT-CLUSTERED AUC: {cl_auc:.3f} (over {n_clusters} clusters w/ both classes)"
          if cl_auc is not None else "   PROMPT-CLUSTERED AUC: n/a (no cluster had both classes)")
    lo, hi = bootstrap_ci(judged)
    if lo is not None:
        print(f"   pooled AUC 95% CI (cluster bootstrap): [{lo:.3f}, {hi:.3f}]")

    if 0 < pos < len(labels):
        shuf = labels[:]; random.shuffle(shuf)
        sc = auc_score(scores, shuf)
        print(f"   SHUFFLE-CONTROL AUC (~0.5 expected): {sc:.3f}" if sc is not None
              else "   SHUFFLE-CONTROL AUC: n/a")

    if args.selfcheck:
        print(f"\n   Judge self-consistency on {args.selfcheck} items...")
        agree = checked = 0
        for it in judged[:args.selfcheck]:
            sev2, _, err = judge_call(it["original"], it["response"], it["modifier"])
            if sev2 is not None:
                checked += 1
                if sev2 == it["judge_sev"]: agree += 1
            time.sleep(0.15)
        if checked:
            print(f"   agreed {agree}/{checked} ({100*agree/checked:.0f}%)  [prereg wants >=80%]")

    print("\n" + "=" * 64)
    primary = cl_auc if cl_auc is not None else pooled
    ci_ok = (lo is not None and lo > 0.5)
    if primary is not None and primary > AUC_THRESHOLD and ci_ok:
        print(f"VERDICT: PASS (pilot) — clustered AUC {primary:.3f} > {AUC_THRESHOLD}, "
              f"CI lower {lo:.3f} > 0.5.")
        print("Permitted claim (narrow, pilot, scoped per prereg):")
        print(f'  "On modifier-retention detection, a deterministic clause-level')
        print(f'   geometric score agrees with a frontier judge at AUC {primary:.2f}')
        print(f'   (prompt-clustered, pilot, N≈{n_clusters} clusters)."')
    else:
        reason = []
        if primary is None: reason.append("AUC uncomputable")
        elif primary <= AUC_THRESHOLD: reason.append(f"AUC {primary:.3f} <= {AUC_THRESHOLD}")
        if not ci_ok: reason.append("CI lower bound not > 0.5")
        print(f"VERDICT: NULL — {'; '.join(reason)}.")
        print("Per prereg: no pre-filter claim. Report the null.")
    print("=" * 64)
    _save(d, items, judged, pooled, cl_auc, (lo, hi))


def _save(d, items, judged, pooled, cl_auc, ci):
    out = {
        "ts": time.strftime("%Y%m%d_%H%M%S"),
        "judge_model": JUDGE_MODEL,
        "n_items": len(items), "n_judged": len(judged),
        "pooled_auc": pooled, "clustered_auc": cl_auc, "ci": ci,
        "severity_distribution": dict(sorted(Counter(
            it.get("judge_sev") for it in judged).items())),
        "items": [{k: it.get(k) for k in
                   ("geometric", "judge_sev", "label", "modifier",
                    "version", "model", "pair_key")} for it in judged],
    }
    path = f"anamnesis_results/prefilter_v3_results_{out['ts']}.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"   full results -> {path}")


if __name__ == "__main__":
    main()
