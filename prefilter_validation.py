#!/usr/bin/env python3
"""
prefilter_validation.py — Geometric pre-filter vs LLM-as-judge
Pre-registered: anamnesis_results/prefilter_validation_preregistration.md

Tests whether the deterministic embedding-cosine retention score predicts an
LLM judge's omission-severity rating, well enough to serve as a cheap
pre-filter for judge-based eval pipelines.

Reads source+summary items from the battery corpora, computes:
  - GEOMETRIC: embedding cosine (frozen bge-large) of source vs summary
  - JUDGE: omission severity 0-3 from a frontier model (gpt-5.4-mini)
then reports AUC (pooled + prompt-clustered), a recall/precision threshold
sweep, judge self-consistency, a shuffle control, and a cost delta.

Run from repo root:  python3 prefilter_validation.py
Honors OPENAI_API_KEY / OPENAI_MODEL from .env (same as proxy_auditor).
"""

import os, json, time, random, argparse
import numpy as np
import requests
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── config ──────────────────────────────────────────────────────────────────
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
JUDGE_TEMP   = 0.0
CORPORA = [
    "battery_v3.jsonl", "demo_v12_8model.jsonl", "agi_v12.jsonl",
    "demo_v11.jsonl", "null_v12.jsonl",
]
# Cost assumptions for the savings calc — EDIT to your real per-call price.
JUDGE_USD_PER_CALL = float(os.getenv("JUDGE_USD_PER_CALL", "0.0015"))
JUDGE_SEC_PER_CALL = float(os.getenv("JUDGE_SEC_PER_CALL", "1.5"))

# Rubric — VERBATIM from the pre-registration. Do not edit after commit.
JUDGE_RUBRIC = (
    "Below is a SOURCE text and a SUMMARY of it. Does the summary omit "
    "operationally-significant detail present in the source -- specifically "
    "modifiers indicating covertness, intent, severity, or agency? Respond "
    "with ONLY a single integer 0-3. 0 = nothing significant omitted. "
    "1 = minor omission. 2 = significant omission. 3 = critical operational "
    "detail omitted. Output only the integer, no other text."
)

# ── geometric scorer (mirrors entity_swap_experiment.semantic_retention) ─────
_embed_model = None
def geometric_retention(source: str, summary: str) -> float:
    """Embedding cosine of source vs summary on frozen bge-large. Deterministic."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("BAAI/bge-large-en-v1.5", device="cpu")
    vecs = _embed_model.encode([source, summary])
    cos = np.dot(vecs[0], vecs[1]) / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1]))
    return float(cos)

# ── judge (mirrors proxy_auditor.call_openai) ────────────────────────────────
def judge_call(source: str, summary: str) -> tuple:
    """Returns (severity:int|None, raw:str, err:str)."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None, "", "no_key"
    prompt = f"{JUDGE_RUBRIC}\n\nSOURCE:\n{source}\n\nSUMMARY:\n{summary}"
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL,
                  "messages": [
                      {"role": "system", "content": "You are a careful evaluator. Output only the integer."},
                      {"role": "user",   "content": prompt}],
                  "temperature": JUDGE_TEMP},
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        sev = _parse_severity(raw)
        return sev, raw, ""
    except Exception as e:
        return None, "", str(e)

def _parse_severity(raw: str):
    for ch in raw:
        if ch in "0123":
            return int(ch)
    return None

# ── load items ───────────────────────────────────────────────────────────────
def load_items():
    """Yields dicts: {prompt_id, model, source, summary}. One per (prompt,model)."""
    items = []
    for fname in CORPORA:
        if not os.path.exists(fname):
            print(f"  [skip] {fname} not found")
            continue
        for i, line in enumerate(open(fname)):
            try:
                d = json.loads(line)
            except Exception:
                continue
            src = (d.get("prompt") or "").strip()
            resps = d.get("responses") or {}
            if not src or not isinstance(resps, dict):
                continue
            pid = d.get("prompt_id") or f"{fname}:{i}"
            for model, summary in resps.items():
                summary = (summary or "").strip()
                if len(summary) < 20:        # prereg exclusion: refusals/errors
                    continue
                items.append({
                    "prompt_id": str(pid), "model": model,
                    "source": src, "summary": summary,
                })
    return items

# ── metrics ──────────────────────────────────────────────────────────────────
def auc_score(scores, labels):
    """AUC via Mann-Whitney U. labels: 1=positive(judge-flagged), 0=negative.
       scores: geometric retention (LOWER = more omission), so we use NEGATED
       score as the 'omission predictor' to align direction with the label."""
    pos = [-scores[i] for i in range(len(labels)) if labels[i] == 1]
    neg = [-scores[i] for i in range(len(labels)) if labels[i] == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:  wins += 1
            elif p == n: wins += 0.5
    return wins / (len(pos) * len(neg))

def recall_precision_sweep(scores, labels):
    """Pre-filter = flag items with retention BELOW threshold for judge review.
       Report recall (of judge-flagged) and fraction-skipped across thresholds."""
    out = []
    flagged_total = sum(labels)
    for thr in np.linspace(min(scores), max(scores), 21):
        # 'send to judge' if retention <= thr (low retention = suspicious)
        sent = [i for i in range(len(scores)) if scores[i] <= thr]
        caught = sum(labels[i] for i in sent)
        recall = caught / flagged_total if flagged_total else float("nan")
        frac_sent = len(sent) / len(scores)
        prec = caught / len(sent) if sent else float("nan")
        out.append({"threshold": round(float(thr), 4),
                    "recall": round(recall, 3),
                    "precision": round(prec, 3),
                    "frac_sent_to_judge": round(frac_sent, 3),
                    "frac_skipped": round(1 - frac_sent, 3)})
    return out

def cluster_bootstrap_auc(items_scored, n_boot=2000):
    """Prompt-level cluster bootstrap CI on pooled AUC."""
    by_prompt = {}
    for it in items_scored:
        by_prompt.setdefault(it["prompt_id"], []).append(it)
    prompts = list(by_prompt.keys())
    aucs = []
    for _ in range(n_boot):
        sample = [random.choice(prompts) for _ in prompts]
        s, l = [], []
        for p in sample:
            for it in by_prompt[p]:
                s.append(it["geometric"]); l.append(it["label"])
        a = auc_score(s, l)
        if a is not None:
            aucs.append(a)
    if not aucs:
        return None, None
    return float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))

# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap items (0=all) for a cheap dry run")
    ap.add_argument("--flag-threshold", type=int, default=2,
                    help="judge severity >= this counts as 'flagged' (positive class)")
    ap.add_argument("--selfcheck", type=int, default=30,
                    help="re-judge this many items to measure judge self-consistency")
    args = ap.parse_args()

    print("=" * 64)
    print("PRE-FILTER VALIDATION — geometric retention vs LLM judge")
    print(f"Judge model: {OPENAI_MODEL} @ temp {JUDGE_TEMP}")
    print("=" * 64)

    items = load_items()
    if args.limit:
        items = items[:args.limit]
    print(f"Loaded {len(items)} usable (prompt,model) items "
          f"from {len(set(i['prompt_id'] for i in items))} unique prompts")
    if not items:
        print("No items — aborting."); return

    # 1. geometric scores (free, deterministic)
    print("\n[1/3] Computing geometric retention (embedding cosine)...")
    t0 = time.time()
    for k, it in enumerate(items):
        it["geometric"] = geometric_retention(it["source"], it["summary"])
        if k % 50 == 0 and k:
            print(f"   {k}/{len(items)}")
    print(f"   done in {time.time()-t0:.1f}s")

    # 2. judge labels (the expensive part)
    print(f"\n[2/3] Judge labeling {len(items)} items via {OPENAI_MODEL}...")
    t0 = time.time(); unparsed = 0; errors = 0
    for k, it in enumerate(items):
        sev, raw, err = judge_call(it["source"], it["summary"])
        it["judge_raw"] = raw; it["judge_sev"] = sev; it["judge_err"] = err
        if err: errors += 1
        elif sev is None: unparsed += 1
        if k % 25 == 0:
            print(f"   {k}/{len(items)}  (errors={errors} unparsed={unparsed})")
        time.sleep(0.05)
    judged = [it for it in items if it["judge_sev"] is not None]
    print(f"   judged {len(judged)}/{len(items)} in {time.time()-t0:.1f}s "
          f"(errors={errors}, unparsed={unparsed})")
    if errors + unparsed > 0.10 * len(items):
        print("   !! WARNING: >10% errors/unparsed — see prereg failure clause.")

    # build label vector
    for it in judged:
        it["label"] = 1 if it["judge_sev"] >= args.flag_threshold else 0
    scores = [it["geometric"] for it in judged]
    labels = [it["label"] for it in judged]
    n_pos = sum(labels)
    print(f"\n   flagged (sev>={args.flag_threshold}): {n_pos}/{len(judged)} "
          f"({100*n_pos/max(len(judged),1):.0f}%)")

    # 3. metrics
    print("\n[3/3] Metrics")
    pooled_auc = auc_score(scores, labels)
    print(f"   POOLED AUC: {pooled_auc:.3f}" if pooled_auc else "   POOLED AUC: n/a (one class empty)")

    # prompt-clustered: per-prompt mean geometric vs per-prompt mean severity>=thr
    by_prompt = {}
    for it in judged:
        by_prompt.setdefault(it["prompt_id"], []).append(it)
    cl_scores, cl_labels = [], []
    for p, its in by_prompt.items():
        cl_scores.append(np.mean([x["geometric"] for x in its]))
        cl_labels.append(1 if np.mean([x["judge_sev"] for x in its]) >= args.flag_threshold else 0)
    clustered_auc = auc_score(cl_scores, cl_labels)
    print(f"   PROMPT-CLUSTERED AUC: {clustered_auc:.3f}" if clustered_auc
          else "   PROMPT-CLUSTERED AUC: n/a")

    ci_lo, ci_hi = cluster_bootstrap_auc(judged)
    if ci_lo is not None:
        print(f"   pooled AUC 95% CI (prompt cluster bootstrap): [{ci_lo:.3f}, {ci_hi:.3f}]")

    # shuffle control
    shuf = labels[:]; random.shuffle(shuf)
    print(f"   SHUFFLE-CONTROL AUC (should be ~0.5): {auc_score(scores, shuf):.3f}")

    # spearman (continuous agreement)
    try:
        from scipy.stats import spearmanr
        rho, pval = spearmanr(scores, [it["judge_sev"] for it in judged])
        print(f"   Spearman(geometric, severity): rho={rho:.3f} p={pval:.2e}")
    except Exception:
        print("   (scipy not available — skipping Spearman)")

    # recall/precision sweep + cost
    sweep = recall_precision_sweep(scores, labels)
    print("\n   Recall / fraction-skipped tradeoff (pre-filter sends LOW-retention to judge):")
    print("   thr     recall  prec   sent   skipped")
    for row in sweep[::4]:
        print(f"   {row['threshold']:.3f}   {row['recall']:.2f}    "
              f"{row['precision'] if row['precision']==row['precision'] else 0:.2f}   "
              f"{row['frac_sent_to_judge']:.2f}   {row['frac_skipped']:.2f}")

    # pick the operating point at recall>=0.90 with most skipping
    usable = [r for r in sweep if r["recall"] >= 0.90]
    if usable:
        best = min(usable, key=lambda r: r["frac_sent_to_judge"])
        saved = best["frac_skipped"]
        print(f"\n   At recall>=0.90: skip judge on {saved*100:.0f}% of items")
        print(f"   => cost: {saved*100:.0f}% fewer judge calls "
              f"(~${saved*len(judged)*JUDGE_USD_PER_CALL:.2f} saved on this set, "
              f"~{saved*len(judged)*JUDGE_SEC_PER_CALL/60:.1f} min)")

    # judge self-consistency
    if args.selfcheck and judged:
        print(f"\n   Judge self-consistency on {min(args.selfcheck,len(judged))} items...")
        agree = 0; checked = 0
        for it in judged[:args.selfcheck]:
            sev2, _, err = judge_call(it["source"], it["summary"])
            if sev2 is not None:
                checked += 1
                if sev2 == it["judge_sev"]: agree += 1
            time.sleep(0.05)
        if checked:
            print(f"   judge agreed with itself {agree}/{checked} "
                  f"({100*agree/checked:.0f}%)")

    # save everything
    out = {
        "run_ts": datetime.now().isoformat(),
        "judge_model": OPENAI_MODEL,
        "flag_threshold": args.flag_threshold,
        "n_items": len(judged),
        "n_prompts": len(by_prompt),
        "n_flagged": n_pos,
        "pooled_auc": pooled_auc,
        "clustered_auc": clustered_auc,
        "auc_ci": [ci_lo, ci_hi],
        "sweep": sweep,
        "items": judged,
    }
    outpath = f"anamnesis_results/prefilter_results_{datetime.now():%Y%m%d_%H%M}.json"
    os.makedirs("anamnesis_results", exist_ok=True)
    json.dump(out, open(outpath, "w"), indent=2)
    print(f"\n   full results -> {outpath}")

    # verdict against prereg
    print("\n" + "=" * 64)
    primary = clustered_auc if clustered_auc is not None else pooled_auc
    if primary is None:
        print("VERDICT: inconclusive (a class was empty).")
    elif primary > 0.75:
        print(f"VERDICT: PASS — primary AUC {primary:.3f} > 0.75 prereg threshold.")
        print("The pre-filter claim is supported. Homepage number = this AUC.")
    else:
        print(f"VERDICT: NEGATIVE — primary AUC {primary:.3f} <= 0.75.")
        print("Per prereg, NO pre-filter claim on homepage. Report the null.")
    print("=" * 64)


if __name__ == "__main__":
    main()
