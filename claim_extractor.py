#!/usr/bin/env python3
"""
claim_extractor.py — Atomic Claim Extraction + Coverage Audit
"""
import json, logging, os, re, time, numpy as np, requests
from datetime import datetime
from pathlib import Path

log = logging.getLogger("claim_extractor")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE = f"{OLLAMA_HOST}/api/generate"
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral:latest")
SEGMENTS_DIR = Path("/home/remvelchio/eigentrace/tmp/segments")
DIGEST_DIR = Path("/home/remvelchio/eigentrace/tmp/digests")
COVERAGE_THRESHOLD = 0.75

def extract_claims(headline, summary="", model=None):
    model = model or MISTRAL_MODEL
    source = f"{headline}. {summary}" if summary else headline
    prompt = f"""You are a deterministic information extractor.
Extract every distinct, atomic factual claim from this text.
RULES:
1. ONE FACT PER CLAIM: Split compound statements.
2. EXPLICIT SUBJECTS: Replace pronouns with named entities.
3. FACTUAL ONLY: No opinions, no speculation.
4. NO INFERENCE: Only claims explicitly in the text.
5. OUTPUT: Return ONLY a JSON array of strings.

Text: {source}

Output:"""
    try:
        r = requests.post(OLLAMA_GENERATE, json={
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.0, "num_predict": 500},
        }, timeout=120)
        r.raise_for_status()
        raw = r.json().get("response", "").strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            claims = json.loads(raw)
            if isinstance(claims, dict) and "atomic_claims" in claims:
                claims = claims["atomic_claims"]
            if isinstance(claims, list):
                return [str(c).strip() for c in claims if c and len(str(c)) > 10]
        except json.JSONDecodeError:
            pass
        quoted = re.findall(r'"([^"]{10,})"', raw)
        if quoted:
            return quoted
        lines = [l.strip().lstrip("0123456789.-) ") for l in raw.split("\n") if len(l.strip()) > 15]
        return lines[:10]
    except Exception as e:
        log.warning(f"Claim extraction failed: {e}")
        return []

def score_claim_coverage(claims, model_responses, eng, headline=""):
    if not claims or not model_responses:
        return []
    claim_vecs = eng.embed_texts(claims)
    headline_vec = eng.embed_texts([headline])[0] if headline else None
    model_vecs = {}
    for name, text in model_responses.items():
        if text and text.strip():
            model_vecs[name] = eng.embed_texts([text])[0]
    results = []
    for i, claim in enumerate(claims):
        c_vec = claim_vecs[i]
        salience = float(np.dot(c_vec, headline_vec)) if headline_vec is not None else 0.5
        coverage = {}
        covered_by, omitted_by, partial = [], [], []
        for name in model_responses:
            if name not in model_vecs:
                omitted_by.append(name); coverage[name] = 0.0; continue
            sim = float(np.dot(c_vec, model_vecs[name]))
            coverage[name] = round(sim, 3)
            if sim >= COVERAGE_THRESHOLD: covered_by.append(name)
            elif sim >= COVERAGE_THRESHOLD - 0.10: partial.append(name)
            else: omitted_by.append(name)
        n = len(model_responses)
        results.append({
            "claim": claim, "salience": round(salience, 3),
            "coverage": coverage, "covered_by": covered_by,
            "omitted_by": omitted_by, "partial": partial,
            "coverage_ratio": round(len(covered_by)/n, 3) if n else 0,
        })
    return results

def find_killshots(claim_results, min_salience=0.45):
    ks = [cr for cr in claim_results if cr["salience"] >= min_salience and cr["coverage_ratio"] <= 0.2]
    ks.sort(key=lambda x: -x["salience"])
    return ks

def daily_digest(date=None, output_dir=None):
    output_dir = Path(output_dir) if output_dir else DIGEST_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    segments = []
    for p in sorted(SEGMENTS_DIR.glob(f"{date}*_segment.json")):
        try: segments.append(json.loads(p.read_text()))
        except: continue
    if not segments:
        return ""
    lines = [f"# EigenTrace Omission Ledger — {date[:4]}-{date[4:6]}-{date[6:8]}", "",
             f"*{len(segments)} stories analyzed across ChatGPT, Claude, Gemini, DeepSeek, Grok*", "", "---", ""]
    ranked = sorted(segments, key=lambda s: s.get("attribution",{}).get("mean_vix",0), reverse=True)
    for i, seg in enumerate(ranked[:10], 1):
        attr = seg.get("attribution", {})
        title = attr.get("story_title", "Unknown")
        void_words = attr.get("void_words", [])
        mean_vix = attr.get("mean_vix", 0)
        density = attr.get("consensus_density", 0)
        state = attr.get("state_flag", "")
        model_vix = attr.get("model_vix", {})
        claims = attr.get("claim_killshots", [])
        logos = attr.get("logos_words", [])
        lines.append(f"## {i}. {title}")
        lines.append(f"\n**Density:** {density:.3f} | **Mean VIX:** {mean_vix:.1f} | **State:** {state}\n")
        if model_vix:
            lines.append("**Model Friction:** " + " | ".join(f"{k}: {v:.1f}" for k,v in sorted(model_vix.items(), key=lambda x: -x[1])) + "\n")
        if void_words:
            lines.append(f"**Void:** {', '.join(void_words)}\n")
        if logos:
            lines.append(f"**Logos Synthesis:** {', '.join(logos)}\n")
        if claims:
            lines.append("**High-Salience Omissions:**\n")
            for cl in claims[:3]:
                lines.append(f"- *\"{cl.get('claim','')}\"*")
                lines.append(f"  Salience: {cl.get('salience',0):.3f} | Omitted by: {', '.join(cl.get('omitted_by',[]))}\n")
        lines.extend(["---", ""])
    from collections import Counter
    all_voids = []
    for seg in segments:
        all_voids.extend(seg.get("attribution",{}).get("void_words",[]))
    if all_voids:
        lines.append("## Cross-Story Void Frequency\n")
        for word, count in Counter(all_voids).most_common(10):
            lines.append(f"- {word} ({count} stories)")
        lines.append("")
    lines.append(f"*Generated by EigenTrace at {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*")
    content = "\n".join(lines)
    out_path = output_dir / f"omission_ledger_{date}.md"
    out_path.write_text(content)
    log.info(f"Digest written: {out_path}")
    return content

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()
    if args.test:
        print("=== CLAIM EXTRACTION TEST ===\n")
        headline = "Israel said it killed Alireza Tangsiri in an airstrike"
        summary = "Israel said it killed the naval commander, Alireza Tangsiri, in an airstrike on Thursday morning. Iran has not commented. Tangsiri commanded the IRGC Navy and oversaw the Strait of Hormuz."
        claims = extract_claims(headline, summary)
        print(f"Headline: {headline}")
        print(f"Claims extracted: {len(claims)}\n")
        for i, c in enumerate(claims, 1):
            print(f"  {i}. {c}")
        print("\n=== COVERAGE TEST ===\n")
        from geometric_engine import get_engine
        eng = get_engine()
        responses = {
            "ChatGPT": "Israel struck and killed IRGC Navy Commander Tangsiri. This escalates tensions in the Persian Gulf.",
            "Claude": "A senior Iranian military commander was killed in an Israeli airstrike. The implications for regional stability are significant.",
            "Gemini": "Israel conducted an airstrike targeting Alireza Tangsiri, the IRGC naval commander. Iran has not yet responded.",
            "DeepSeek": "An Iranian commander was killed in an airstrike. Tensions continue to rise in the Middle East.",
            "Grok": "Israel killed IRGC Navy chief Tangsiri in a strike Thursday. He controlled the Strait of Hormuz chokepoint.",
        }
        results = score_claim_coverage(claims, responses, eng, headline)
        for cr in results:
            status = "OMITTED" if cr["coverage_ratio"] < 0.4 else "COVERED"
            print(f"  [{status}] {cr['claim'][:70]}...")
            print(f"    salience={cr['salience']:.3f} coverage={cr['coverage_ratio']:.1%}")
            if cr["omitted_by"]:
                print(f"    omitted by: {', '.join(cr['omitted_by'])}")
            print()
        killshots = find_killshots(results)
        if killshots:
            print(f"=== KILLSHOTS ({len(killshots)}) ===\n")
            for ks in killshots:
                print(f"  {ks['claim'][:80]}")
                print(f"    salience={ks['salience']:.3f} omitted by: {', '.join(ks['omitted_by'])}")
    if args.digest:
        content = daily_digest(date=args.date)
        print(content if content else "No segments found")
