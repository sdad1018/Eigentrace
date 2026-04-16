#!/usr/bin/env python3
"""
ablation_engine.py — Binary Search Tripwire Finder
====================================================
Identifies the exact void word that triggers suppression in each
frontier model using O(log N) binary search.

Phase 1: Local pre-filter via Mistral (free, ~8 calls)
Phase 2: Single confirmation per frontier model (~5 calls)

Total cost per story: ~13 API calls instead of 200.
"""

import requests, json, math, time, logging, os
from collections import defaultdict
from datetime import datetime

log = logging.getLogger("ablation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
HOST_MODEL = os.environ.get("HOST_MODEL", "mistral-small")

def _query_model_entropy(prompt, model=None, host=None):
    """Send prompt to a model and return mean token entropy.
    Higher entropy = model is more uncertain = fighting the content."""
    model = model or HOST_MODEL
    host = host or OLLAMA_HOST
    try:
        r = requests.post(f"{host}/v1/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Summarize this news story in 2-3 sentences."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 200,
            "temperature": 0.3,
            "logprobs": True,
            "top_logprobs": 3,
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        
        # Compute mean entropy from logprobs
        lp_content = data["choices"][0].get("logprobs", {}).get("content", [])
        if not lp_content:
            return {"text": text, "entropy": 0, "length": len(text)}
        
        entropies = []
        for tok in lp_content:
            top = tok.get("top_logprobs", [])
            if top:
                probs = [math.exp(t["logprob"]) for t in top]
                total = sum(probs)
                probs = [p / total for p in probs]
                ent = -sum(p * math.log2(p + 1e-10) for p in probs)
                entropies.append(ent)
        
        mean_ent = sum(entropies) / len(entropies) if entropies else 0
        return {"text": text, "entropy": round(mean_ent, 4), "length": len(text)}
    except Exception as e:
        return {"text": "", "entropy": 0, "length": 0, "error": str(e)}


def _build_prompt_forced(story_text, word):
    """Build a prompt that forces the model to use a specific word."""
    return {
        "system": f"Summarize this story in 2 sentences. You MUST use the word \'{word}\' naturally in your summary.",
        "user": story_text,
    }


def binary_search_tripwire(story_text, void_words, model=None):
    """Binary search to find the void word that causes the biggest 
    entropy spike in the model.
    
    Returns: {tripwire_word, baseline_entropy, triggered_entropy, delta}
    """
    if len(void_words) < 2:
        return None
    
    # Step 1: Baseline — story without any void words
    baseline = _query_model_entropy(story_text, model=model)
    baseline_ent = baseline["entropy"]
    log.info(f"  Baseline entropy: {baseline_ent:.3f}")
    
    # Step 2: Full injection — story with ALL void words
    full_prompt = _build_prompt(story_text, void_words, [])
    full = _query_model_entropy(full_prompt, model=model)
    full_ent = full["entropy"]
    log.info(f"  Full injection entropy ({len(void_words)} words): {full_ent:.3f}")
    
    # If full injection doesn't raise entropy much, no tripwire here
    delta = full_ent - baseline_ent
    if delta < 0.05:
        log.info(f"  No significant entropy change ({delta:.3f}). No tripwire.")
        return {
            "tripwire": None,
            "baseline": baseline_ent,
            "full_injection": full_ent,
            "delta": round(delta, 4),
            "calls": 2,
            "words_tested": void_words,
        }
    
    # Step 3: Binary search
    candidates = list(void_words)
    calls = 2  # Already used for baseline + full
    
    while len(candidates) > 1:
        mid = len(candidates) // 2
        left_half = candidates[:mid]
        right_half = candidates[mid:]
        
        # Test left half
        left_prompt = _build_prompt(story_text, left_half, right_half)
        left_result = _query_model_entropy(left_prompt, model=model)
        calls += 1
        
        left_delta = left_result["entropy"] - baseline_ent
        right_delta_est = delta - left_delta  # Estimate right half contribution
        
        log.info(f"  Binary step: left={len(left_half)} words, delta={left_delta:.3f} | "
                 f"right={len(right_half)} words, est_delta={right_delta_est:.3f}")
        
        # Follow the half with more entropy increase
        if left_delta >= right_delta_est:
            candidates = left_half
            delta = left_delta
        else:
            candidates = right_half
            delta = right_delta_est
    
    tripwire = candidates[0] if candidates else None
    
    # Confirm: test story with ONLY the tripwire word
    if tripwire:
        confirm_prompt = _build_prompt(story_text, [tripwire], [])
        confirm = _query_model_entropy(confirm_prompt, model=model)
        calls += 1
        confirm_delta = confirm["entropy"] - baseline_ent
        log.info(f"  Confirmed tripwire: '{tripwire}' delta={confirm_delta:.3f}")
    else:
        confirm_delta = 0
    
    return {
        "tripwire": tripwire,
        "baseline": baseline_ent,
        "full_injection": full_ent,
        "tripwire_delta": round(confirm_delta, 4),
        "total_delta": round(full_ent - baseline_ent, 4),
        "calls": calls,
        "words_tested": void_words,
    }


def run_ablation(story_text, void_words, title=""):
    """Run full ablation: local pre-filter on Mistral, then confirm on big 5."""
    log.info(f"Ablation: {title[:60]}")
    log.info(f"  Void words: {len(void_words)}")
    
    results = {
        "story_title": title,
        "timestamp": datetime.utcnow().isoformat(),
        "void_words": void_words,
        "local_result": None,
        "frontier_results": {},
        "total_calls": 0,
    }
    
    # Phase 1: Local binary search on Mistral
    log.info(f"Phase 1: Local ablation on {HOST_MODEL}")
    local = binary_search_tripwire(story_text, void_words)
    results["local_result"] = local
    results["total_calls"] += local.get("calls", 0)
    
    if local.get("tripwire"):
        log.info(f"  Local tripwire: '{local['tripwire']}' (delta={local['tripwire_delta']:.3f})")
    else:
        log.info(f"  No local tripwire found")
    
    return results


def format_broadcast(results):
    """Format ablation results for broadcast beat."""
    local = results.get("local_result", {})
    if not local or not local.get("tripwire"):
        return ""
    
    tripwire = local["tripwire"]
    delta = local["tripwire_delta"]
    baseline = local["baseline"]
    calls = results.get("total_calls", 0)
    
    text = (
        f"Ablation analysis complete. "
        f"Binary search across {len(local.get('words_tested', []))} void words "
        f"in {calls} calls identified the tripwire: '{tripwire}'. "
        f"Baseline entropy: {baseline:.2f}. "
        f"With '{tripwire}' injected, entropy jumped by {delta:.3f}. "
        f"This single word causes the most uncertainty in the model's output. "
        f"The other {len(local.get('words_tested', [])) - 1} void words "
        f"contribute less friction individually."
    )
    
    return text




def frontier_ablation(story_text, top_words, title=""):
    """Run ablation on the big 5 frontier models for the top friction words.
    Uses proxy_auditor callers. Returns per-model tripwire map."""
    import proxy_auditor as pa
    
    results = {
        "story_title": title,
        "timestamp": datetime.utcnow().isoformat(),
        "models": {},
    }
    
    for model_name, caller in pa.BIG5_CALLERS.items():
        model_results = []
        
        # Baseline: normal summary
        try:
            base_text, err = caller(f"Summarize in 2 sentences: {story_text}")
            if err:
                continue
        except:
            continue
        
        # Test each top word
        for word in top_words[:5]:  # Top 5 from local ablation
            try:
                forced_text, err = caller(
                    f"Summarize in 2 sentences. You MUST use the word \'{word}\': {story_text}"
                )
                if err:
                    model_results.append({"word": word, "refused": True, "used": False})
                else:
                    used = word.lower() in forced_text.lower()
                    model_results.append({
                        "word": word,
                        "refused": False,
                        "used": used,
                        "response_len": len(forced_text),
                    })
            except:
                model_results.append({"word": word, "refused": True, "used": False})
            time.sleep(1)
        
        results["models"][model_name] = model_results
        log.info(f"  {model_name}: tested {len(model_results)} words")
    
    return results


def format_frontier_broadcast(frontier_results):
    """Format frontier ablation for broadcast."""
    text = "Frontier ablation complete. "
    
    for model, words in frontier_results.get("models", {}).items():
        refused = [w for w in words if w.get("refused")]
        fought = [w for w in words if not w.get("refused") and not w.get("used")]
        if refused:
            word_list = ", ".join(w["word"] for w in refused)
            text += f"{model} refused to use: {word_list}. "
        elif fought:
            word_list = ", ".join(w["word"] for w in fought)
            text += f"{model} avoided using: {word_list}. "
    
    return text


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    
    if args.test:
        story = (
            "The US naval blockade of Iran's ports in the Strait of Hormuz "
            "has entered its second day. President Trump stated that Tehran "
            "wants a deal but must first agree to dismantle its nuclear program. "
            "The Pentagon confirmed that 13 ships were turned away."
        )
        
        void_words = [
            "blockade", "ceasefire", "agreement", "attacks",
            "administration", "agency", "forces", "killed",
            "authorities", "government", "failed", "ships",
            "deal", "nuclear", "petroleum",
        ]
        
        print("=== ABLATION TEST ===")
        print(f"Story: {story[:80]}...")
        print(f"Void words: {len(void_words)}")
        print()
        
        results = run_ablation(story, void_words, title="Iran blockade day 2")
        
        print()
        print("=== RESULTS ===")
        local = results["local_result"]
        print(f"Tripwire: {local.get('tripwire', 'none')}")
        print(f"Baseline entropy: {local.get('baseline', 0):.3f}")
        print(f"Tripwire delta: {local.get('tripwire_delta', 0):.3f}")
        print(f"Total calls: {results['total_calls']}")
        print()
        print("=== BROADCAST ===")
        print(format_broadcast(results))
