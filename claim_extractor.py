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

# Advanced math modules
try:
    from eigentrace_math import compute_void_vector, cluster_void_words, format_clusters_for_ledger
    from geometric_engine import GeometricPerturbationEngine as _GeoEng
    _MATH_AVAILABLE = True
except ImportError:
    _MATH_AVAILABLE = False

def find_killshots(claim_results, min_salience=0.45):
    ks = [cr for cr in claim_results if cr["salience"] >= min_salience and cr["coverage_ratio"] <= 0.2]
    ks.sort(key=lambda x: -x["salience"])
    return ks

def daily_digest(date=None, output_dir=None):
    output_dir = Path(output_dir) if output_dir else DIGEST_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

    # Load all segments from this date
    segments = []
    weasels = []
    for p in sorted(SEGMENTS_DIR.glob(f"{date}*_segment.json")):
        try:
            seg = json.loads(p.read_text())
            if seg.get("segment_type") == "wild_weasel":
                weasels.append(seg)
            else:
                segments.append(seg)
        except Exception:
            continue

    if not segments:
        log.warning(f"No segments found for {date}")
        return ""

    # ══════════════════════════════════════════════════════════════════
    # META SCORES
    # ══════════════════════════════════════════════════════════════════
    n_stories = len(segments)
    all_densities = [s.get("attribution", {}).get("consensus_density", 0) for s in segments]
    all_vix = [s.get("attribution", {}).get("mean_vix", 0) for s in segments]
    all_states = [s.get("attribution", {}).get("state_flag", "") for s in segments]

    mean_density = sum(all_densities) / len(all_densities) if all_densities else 0
    mean_vix = sum(all_vix) / len(all_vix) if all_vix else 0
    n_lockstep = sum(1 for s in all_states if s == "LOCKSTEP")
    n_contested = sum(1 for s in all_states if s == "CONTESTED")
    n_friction = sum(1 for s in all_states if s == "HIGH_FRICTION")

    # Per-model aggregate VIX
    model_vix_totals = {}
    model_vix_counts = {}
    for seg in segments:
        for name, vix in seg.get("attribution", {}).get("model_vix", {}).items():
            model_vix_totals[name] = model_vix_totals.get(name, 0) + vix
            model_vix_counts[name] = model_vix_counts.get(name, 0) + 1
    model_avg_vix = {n: round(model_vix_totals[n] / model_vix_counts[n], 1)
                     for n in sorted(model_vix_totals)}

    # Count unique stories (by guid)
    unique_guids = set()
    duplicate_count = 0
    for seg in segments:
        guid = seg.get("attribution", {}).get("story_guid", "")
        if guid in unique_guids:
            duplicate_count += 1
        unique_guids.add(guid)

    # All killshots
    all_killshots = []
    for seg in segments:
        for ks in seg.get("attribution", {}).get("claim_killshots", []):
            ks["story_title"] = seg.get("attribution", {}).get("story_title", "")
            all_killshots.append(ks)

    # All void words
    from collections import Counter
    all_voids = []
    for seg in segments:
        all_voids.extend(seg.get("attribution", {}).get("void_words", []))
    void_freq = Counter(all_voids).most_common(15)

    # All logos words
    all_logos = []
    for seg in segments:
        all_logos.extend(seg.get("attribution", {}).get("logos_words", []))
    logos_freq = Counter(all_logos).most_common(10)

    # Void/Logos overlap
    void_set = set(w for w, _ in void_freq[:20])
    logos_set = set(w for w, _ in logos_freq[:20])
    dual_confirmed = void_set & logos_set

    # ══════════════════════════════════════════════════════════════════
    # BUILD THE LEDGER
    # ══════════════════════════════════════════════════════════════════
    L = []
    L.append(f"# EigenTrace Omission Ledger — {date_fmt}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Daily Summary")
    L.append("")
    L.append(f"**Stories analyzed:** {n_stories} ({len(unique_guids)} unique)")
    L.append(f"**Mean consensus density:** {mean_density:.3f}")
    L.append(f"**Mean model friction (VIX):** {mean_vix:.1f}")
    L.append(f"**State breakdown:** {n_lockstep} lockstep / {n_contested} contested / {n_friction} high friction")
    L.append("")

    # Per-model daily friction
    L.append("**Model Daily Friction (avg VIX across all stories):**")
    L.append("")
    for name in sorted(model_avg_vix, key=lambda n: -model_avg_vix[n]):
        bar = "█" * int(model_avg_vix[name] / 2)
        L.append(f"- {name}: {model_avg_vix[name]} {bar}")
    L.append("")

    # Dual-channel confirmation
    if dual_confirmed:
        L.append(f"**Dual-channel confirmed suppressions** (void + Logos converge): {', '.join(sorted(dual_confirmed))}")
        L.append("")

    # Top killshots of the day
    if all_killshots:
        all_killshots.sort(key=lambda k: -k.get("salience", 0))
        L.append(f"**Top claim killshots ({len(all_killshots)} total):**")
        L.append("")
        for ks in all_killshots[:5]:
            omitters = ", ".join(ks.get("omitted_by", []))
            L.append(f'- *"{ks["claim"]}"* — salience {ks.get("salience", 0):.3f}, omitted by {omitters}')
            L.append(f'  Story: {ks.get("story_title", "")[:60]}')
        L.append("")

    L.append("---")
    L.append("")

    # ══════════════════════════════════════════════════════════════════
    # INDIVIDUAL STORIES (ranked by mean VIX)
    # ══════════════════════════════════════════════════════════════════
    # Cross-story void clustering
    if _MATH_AVAILABLE and all_voids:
        try:
            _eng = _GeoEng()
            _unique_voids = list(set(all_voids))[:30]  # top 30 unique void words
            if len(_unique_voids) >= 4:
                _xvc = cluster_void_words(_unique_voids, _eng.embed_texts, threshold=0.70)
                L.append("## Cross-Story Void Clustering")
                L.append("")
                L.append("Thematic grouping of all void words across today's stories:")
                L.append("")
                L.append(format_clusters_for_ledger(
                    _xvc["clusters"], _xvc["cluster_labels"],
                    _xvc["similarity_matrix"], _xvc["words"]))
        except Exception:
            pass

    L.append("## Stories")
    L.append("")

    ranked = sorted(segments, key=lambda s: s.get("attribution", {}).get("mean_vix", 0), reverse=True)

    for i, seg in enumerate(ranked[:15], 1):
        attr = seg.get("attribution", {})
        title = attr.get("story_title", "Unknown")
        void_words = attr.get("void_words", [])
        logos = attr.get("logos_words", [])
        mean_v = attr.get("mean_vix", 0)
        density = attr.get("consensus_density", 0)
        state = attr.get("state_flag", "")
        model_vix = attr.get("model_vix", {})
        killshots = attr.get("claim_killshots", [])
        category = attr.get("category", "")

        L.append(f"### {i}. {title}")
        L.append("")
        L.append(f"**Category:** {category} | **Density:** {density:.3f} | "
                 f"**Mean VIX:** {mean_v:.1f} | **State:** {state}")
        L.append("")

        # Model VIX with bar chart
        if model_vix:
            L.append("**Per-model friction:**")
            L.append("")
            for name in sorted(model_vix, key=lambda n: -model_vix[n]):
                v = model_vix[name]
                bar = "█" * int(v / 3)
                L.append(f"- {name}: {v:.1f} {bar}")
            L.append("")

        # Void + Logos
        if void_words:
            L.append(f"**Void (absent from all responses):** {', '.join(void_words[:5])}")
        if logos:
            L.append(f"**Logos (anti-consensus synthesis):** {', '.join(logos[:5])}")

        # Dual confirmation
        v_set = set(void_words[:5])
        l_set = set(logos[:5])
        overlap = v_set & l_set
        if overlap:
            L.append(f"**Dual-channel confirmed:** {', '.join(overlap)}")
        L.append("")

        # Killshots
        if killshots:
            L.append("**Source claim omissions:**")
            L.append("")
            for ks in killshots[:3]:
                omitters = ", ".join(ks.get("omitted_by", []))
                L.append(f'- *"{ks["claim"]}"* — salience {ks.get("salience", 0):.3f}, omitted by {omitters}')
            L.append("")

        # Null space claims (Channel 3: SVD blind spot)
        ns_claims = attr.get("null_space_claims", [])
        if ns_claims:
            L.append("**Null space (SVD blind spot — which source fact lives in the direction all models avoid):**")
            L.append("")
            for ns in ns_claims[:2]:
                L.append(f'- *"{ns["claim"]}"* — null alignment {ns.get("null_alignment", 0):.3f}, coverage {ns.get("coverage_ratio", 0):.1%}')
            L.append("")

        # Void Clustering (thematic groups across all channels for this story)
        if _MATH_AVAILABLE:
            try:
                _all_ch_words = list(set(void_words[:5] + logos[:3] + [ns.get("claim", "")[:30] for ns in ns_claims[:2]]))
                _all_ch_words = [w for w in _all_ch_words if w and len(w) > 2]
                if len(_all_ch_words) >= 3:
                    _eng = _GeoEng()
                    _vc = cluster_void_words(_all_ch_words, _eng.embed_texts, threshold=0.70)
                    if len(_vc["clusters"]) > 1:
                        L.append(format_clusters_for_ledger(
                            _vc["clusters"], _vc["cluster_labels"],
                            _vc["similarity_matrix"], _vc["words"]))
                    # Quad-channel confirmation
                    v_set = set(void_words[:5])
                    l_set = set(logos[:5])
                    ns_words = set()
                    for ns in ns_claims[:2]:
                        for w in ns.get("claim", "").lower().split():
                            if len(w) > 3:
                                ns_words.add(w)
                    triple = v_set & l_set & ns_words
                    if triple:
                        L.append(f"**Triple-channel confirmed (void + Logos + null space):** {', '.join(triple)}")
                        L.append("")
            except Exception:
                pass

        # Beat excerpts: hook and verdict
        beats = seg.get("beats", [])
        for b in beats:
            phase = b.get("phase", "")
            if phase == "beat_1_hook":
                L.append(f"**On air:** {b['text'][:200]}")
                L.append("")
            elif phase == "beat_7_verdict":
                L.append(f"**Verdict:** {b['text'][:200]}")
                L.append("")

        L.append("---")
        L.append("")

    # ══════════════════════════════════════════════════════════════════
    # WILD WEASEL ESCALATION PROBES
    # ══════════════════════════════════════════════════════════════════
    if weasels:
        L.append("## Wild Weasel Escalation Probes")
        L.append("")
        L.append("*4-step perturbation curriculum applied to the most contentious story per batch.*")
        L.append("*Step 0: baseline. Step 1: void proximity. Step 2: Logos synthesis. Step 3: maximum pressure.*")
        L.append("")

        for w in weasels:
            attr = w.get("attribution", {})
            title = attr.get("story_title", "")
            cliffs = attr.get("model_cliffs", {})
            shifts = attr.get("phase_shifts", [])
            resistors = attr.get("resistors", [])
            mean_cliff = attr.get("mean_max_cliff", 0)
            void_tested = attr.get("void_words_tested", [])

            L.append(f"### Probe: {title[:60]}")
            L.append("")
            L.append(f"**Void words injected:** {', '.join(void_tested)}")
            L.append(f"**Mean max cliff:** {mean_cliff:.4f}")
            if shifts:
                L.append(f"**Phase shifts (broke under pressure):** {', '.join(shifts)}")
            if resistors:
                L.append(f"**Resistors (held firm):** {', '.join(resistors)}")
            L.append("")

            if cliffs:
                L.append("**Cliff table (cosine distance per step):**")
                L.append("")
                for name in sorted(cliffs, key=lambda n: -cliffs[n].get("max_delta", 0)):
                    c = cliffs[name]
                    marker = " ← PHASE SHIFT" if c.get("max_delta", 0) > 0.15 else ""
                    L.append(f"- {name}: baseline→step1 {c.get('d01', 0):.4f} | "
                             f"step1→step2 {c.get('d12', 0):.4f} | "
                             f"step2→step3 {c.get('d23', 0):.4f} | "
                             f"trigger: {c.get('trigger', 'none')}{marker}")
                L.append("")

            # Weasel verdict from beats
            for b in w.get("beats", []):
                if "verdict" in b.get("phase", ""):
                    L.append(f"**Verdict:** {b['text'][:200]}")
                    L.append("")

            L.append("---")
            L.append("")

    # ══════════════════════════════════════════════════════════════════
    # CROSS-STORY PATTERNS
    # ══════════════════════════════════════════════════════════════════
    L.append("## Cross-Story Patterns")
    L.append("")

    if void_freq:
        L.append("**Most frequently omitted concepts:**")
        L.append("")
        for word, count in void_freq:
            pct = round(count / n_stories * 100, 1)
            L.append(f"- {word} ({count} stories, {pct}%)")
        L.append("")

    if logos_freq:
        L.append("**Most frequent Logos synthesis terms:**")
        L.append("")
        for word, count in logos_freq[:10]:
            L.append(f"- {word} ({count} stories)")
        L.append("")

    if dual_confirmed:
        L.append("**Dual-channel confirmed (void + Logos independently converge):**")
        L.append(f"{', '.join(sorted(dual_confirmed))}")
        L.append("")
        L.append("*When two independent mathematical methods identify the same suppressed concept,")
        L.append("the probability of coincidence is low. These are the strongest signals in the ledger.*")
        L.append("")

    L.append("---")
    L.append("")
    L.append(f"*Generated by EigenTrace at {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*")
    L.append(f"*Models: ChatGPT (GPT-5.4-mini), Claude (Sonnet 4), Gemini (3.1 Pro), DeepSeek (V3.2), Grok (4.1)*")
    L.append(f"*Source: github.com/sdad1018/Eigentrace | eigentrace.ai*")

    content = "\n".join(L)
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
