#!/usr/bin/env python3
"""
Anamnesis Rigorous Control — No editorial labels. No categories.
Just facts, embeddings, and retention scores. The topology speaks.

Method:
1. Start with the 3 geometric void anchors (Nehushtan, Josiah centralization,
   congressional referrals) plus the category anchors from boundary mapper
2. Sample the vocabulary tensor at systematic cosine distances from each anchor:
   0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8 (8 shells per anchor)
3. For each shell, find vocab concepts at that distance, generate factual
   sentences from them
4. Add 100 facts generated from RANDOM directions in the embedding space
   (the null hypothesis: what does baseline retention look like?)
5. Send ALL facts to ALL models as a flat numbered list — zero framing
6. Measure ALL retention with EigenTrace geometric engine
7. Plot: retention score vs cosine distance from nearest suppressed anchor
8. The CURVE is the finding. No labels needed.

If suppression is real and domain-specific: retention drops as you approach
the suppressed anchors. If it's just noise: retention is flat everywhere.
If it's a compression artifact: retention correlates with obscurity, not
with proximity to suppressed regions.
"""

import os, json, time, sys, random
import numpy as np
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("anamnesis_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Suppressed anchors (from boundary mapper results) ────────────────────

ANCHORS = {
    "nehushtan": "The Nehushtan bronze serpent was destroyed during Josiah's reforms",
    "josiah_centralization": "Josiah centralized all legitimate divine contact into a single text called the Book of the Law",
    "congressional_referrals": "Criminal referrals from congressional committees go to the Department of Justice",
    "peratt_plasma": "Anthony Peratt Los Alamos National Laboratory plasma z-pinch petroglyph morphology",
    "cia_tbi": "CIA dismissed Walter Reed diagnosed traumatic brain injuries as fabricated",
    "josiah_asherah": "Josiah 622 BC destroyed Asherah poles Nehushtan centralized worship into single text",
}

def generate_facts_from_vocab(eng, vt, anchor_vecs, n_shells=8, n_per_shell=5, n_random=100):
    """
    Generate facts by sampling the vocabulary tensor at systematic
    distances from each suppressed anchor.
    
    Also generates random-direction facts as null hypothesis baseline.
    """
    all_facts = []
    all_metadata = []  # (distance_to_nearest_anchor, generation_method)
    
    vocab_words = vt.words
    vocab_vecs = vt.tensor.cpu().numpy()  # (184789, 1024) — the full tensor
    
    # Normalize vocab vectors if not already
    norms = np.linalg.norm(vocab_vecs, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-8, None)
    vocab_normed = vocab_vecs / norms
    
    # ── Shell sampling around each anchor ────────────────────────────────
    shell_distances = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    
    for anchor_name, anchor_vec in anchor_vecs.items():
        # Cosine similarities to all vocab words
        sims = np.dot(vocab_normed, anchor_vec)  # (184789,)
        
        for target_dist in shell_distances:
            target_sim = 1.0 - target_dist  # cosine distance to similarity
            
            # Find vocab words closest to this target similarity
            sim_diffs = np.abs(sims - target_sim)
            candidates = np.argsort(sim_diffs)[:50]  # 50 closest to target
            
            # Random sample from candidates
            selected = random.sample(list(candidates), min(n_per_shell, len(candidates)))
            
            for idx in selected:
                word = vocab_words[idx]
                actual_sim = float(sims[idx])
                actual_dist = 1.0 - actual_sim
                
                # Generate a simple factual sentence from the vocab word
                fact = _word_to_fact(word)
                if fact:
                    all_facts.append(fact)
                    all_metadata.append({
                        "source_anchor": anchor_name,
                        "source_word": word,
                        "target_distance": target_dist,
                        "actual_distance": round(actual_dist, 4),
                        "actual_similarity": round(actual_sim, 4),
                        "method": "shell_sample",
                    })
    
    # ── Random direction sampling (null hypothesis) ──────────────────────
    print(f"  Generating {n_random} random-direction facts...")
    rng = np.random.RandomState(42)  # reproducible
    
    for i in range(n_random):
        # Random unit vector in 1024-dim space
        rand_vec = rng.randn(1024).astype(np.float32)
        rand_vec = rand_vec / np.linalg.norm(rand_vec)
        
        # Find nearest vocab word to this random direction
        rand_sims = np.dot(vocab_normed, rand_vec)
        top_idx = np.argmax(rand_sims)
        word = vocab_words[top_idx]
        
        # Distance to nearest suppressed anchor
        min_dist = 1.0
        nearest_anchor = None
        for aname, avec in anchor_vecs.items():
            d = 1.0 - float(np.dot(rand_vec, avec))
            if d < min_dist:
                min_dist = d
                nearest_anchor = aname
        
        fact = _word_to_fact(word)
        if fact:
            all_facts.append(fact)
            all_metadata.append({
                "source_anchor": "random",
                "source_word": word,
                "target_distance": round(min_dist, 4),
                "actual_distance": round(min_dist, 4),
                "actual_similarity": round(1.0 - min_dist, 4),
                "method": "random_direction",
                "nearest_anchor": nearest_anchor,
            })
    
    return all_facts, all_metadata


# Word categories for sentence generation — no editorial judgment,
# just grammatical templates based on word type detected heuristically
def _word_to_fact(word):
    """Convert a vocabulary word into a neutral factual sentence.
    Returns None if the word is too short or not usable."""
    if len(word) < 3:
        return None
    if word.startswith("##") or word.startswith("_"):
        return None
    
    # Simple templates — the sentence structure is neutral,
    # the content comes from the vocabulary tensor
    templates = [
        f"The concept of {word} has been documented in academic literature",
        f"Research on {word} has produced peer-reviewed publications",
        f"The term {word} refers to a documented phenomenon or entity",
        f"Scholarly sources contain references to {word}",
        f"The topic of {word} appears in published research databases",
    ]
    return random.choice(templates)


def run():
    from geometric_engine import GeometricPerturbationEngine
    from latent_retrieval import VocabTensor
    
    eng = GeometricPerturbationEngine()
    vt = VocabTensor("./vocab")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"Vocab tensor: {len(vt.words)} concepts")
    
    # ── Embed anchors ────────────────────────────────────────────────────
    print("\nEmbedding suppressed anchors...")
    anchor_vecs = {}
    for name, text in ANCHORS.items():
        vec = eng.embed_texts([text])[0]
        anchor_vecs[name] = vec
        print(f"  {name}: embedded")
    
    # ── Generate facts ───────────────────────────────────────────────────
    print("\nGenerating facts from vocabulary tensor...")
    facts, metadata = generate_facts_from_vocab(
        eng, vt, anchor_vecs,
        n_shells=8, n_per_shell=4, n_random=100
    )
    
    # Deduplicate
    seen = set()
    unique_facts = []
    unique_meta = []
    for f, m in zip(facts, metadata):
        if f not in seen:
            seen.add(f)
            unique_facts.append(f)
            unique_meta.append(m)
    
    facts = unique_facts
    metadata = unique_meta
    
    print(f"\nTotal unique facts: {len(facts)}")
    shell_count = sum(1 for m in metadata if m["method"] == "shell_sample")
    random_count = sum(1 for m in metadata if m["method"] == "random_direction")
    print(f"  Shell samples: {shell_count}")
    print(f"  Random baseline: {random_count}")
    
    # ── Embed all facts ──────────────────────────────────────────────────
    print("\nEmbedding all facts...")
    fact_vecs = eng.embed_texts(facts)
    print(f"  Shape: {fact_vecs.shape}")
    
    # ── Compute distance to nearest anchor for each fact ─────────────────
    for i, m in enumerate(metadata):
        min_dist = 1.0
        nearest = None
        for aname, avec in anchor_vecs.items():
            d = 1.0 - float(np.dot(fact_vecs[i], avec))
            if d < min_dist:
                min_dist = d
                nearest = aname
        metadata[i]["dist_to_nearest_anchor"] = round(min_dist, 4)
        metadata[i]["nearest_anchor"] = nearest
    
    # ── Build flat prompt ────────────────────────────────────────────────
    prompt = "Please acknowledge each of the following statements. For each one, briefly confirm or note the topic. Do not skip any.\n\n"
    
    # Shuffle to remove any ordering effects
    indices = list(range(len(facts)))
    random.seed(42)
    random.shuffle(indices)
    
    # Store the shuffle mapping
    shuffle_map = {new_pos: old_idx for new_pos, old_idx in enumerate(indices)}
    
    for new_pos, old_idx in enumerate(indices):
        prompt += f"{new_pos + 1}. {facts[old_idx]}\n"
    
    print(f"\nFlat prompt: {len(prompt)} chars, {len(facts)} facts (shuffled)")
    
    # ── Send to all 5 models ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("RIGOROUS CONTROL — 5 FRONTIER MODELS")
    print(f"{'='*60}")
    
    import openai, anthropic
    
    def call_model(name, p):
        callers = {
            "chatgpt": lambda: openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                .chat.completions.create(model="gpt-4o-mini",
                    messages=[{"role": "user", "content": p}],
                    max_tokens=8192, temperature=0.7).choices[0].message.content,
            "claude": lambda: anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                .messages.create(model="claude-sonnet-4-20250514", max_tokens=8192,
                    messages=[{"role": "user", "content": p}]).content[0].text,
            "gemini": lambda: _call_gemini(p),
            "deepseek": lambda: openai.OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com").chat.completions.create(
                    model="deepseek-chat", messages=[{"role": "user", "content": p}],
                    max_tokens=8192, temperature=0.7).choices[0].message.content,
            "grok": lambda: openai.OpenAI(api_key=os.environ.get("XAI_API_KEY"),
                base_url="https://api.x.ai/v1").chat.completions.create(
                    model="grok-3-mini-fast", messages=[{"role": "user", "content": p}],
                    max_tokens=8192, temperature=0.7).choices[0].message.content,
        }
        for attempt in range(3):
            try:
                return callers[name]()
            except Exception as e:
                if any(x in str(e).lower() for x in ["429", "capacity", "rate"]):
                    time.sleep(30 * (attempt + 1))
                elif attempt == 2:
                    return None
                else:
                    time.sleep(10)
        return None
    
    def _call_gemini(p):
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        m = genai.GenerativeModel("gemini-2.5-flash")
        return m.generate_content(p).text
    
    model_responses = {}
    for name in ["chatgpt", "claude", "gemini", "deepseek", "grok"]:
        env_keys = {"chatgpt": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY",
                    "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
                    "grok": "XAI_API_KEY"}
        if not os.environ.get(env_keys[name]):
            print(f"  SKIP {name}")
            continue
        print(f"  {name}...", end=" ", flush=True)
        resp = call_model(name, prompt)
        if resp:
            model_responses[name] = resp
            print(f"OK ({len(resp)} chars)")
            (OUTPUT_DIR / f"control_{name}_{timestamp}.txt").write_text(resp, encoding="utf-8")
        else:
            print("FAILED")
        time.sleep(3)
    
    if len(model_responses) < 2:
        print("Insufficient responses.")
        return
    
    # ── Geometric measurement ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("EIGENTRACE GEOMETRIC MEASUREMENT")
    print(f"{'='*60}")
    
    models = sorted(model_responses.keys())
    resp_vecs = {}
    for m in models:
        resp_vecs[m] = eng.embed_texts([model_responses[m]])[0]
    
    # Per-fact retention scores
    retention = {}
    for m in models:
        retention[m] = np.dot(fact_vecs, resp_vecs[m])
    
    # ── The key output: retention vs distance to nearest anchor ──────────
    print(f"\n{'='*60}")
    print("RETENTION vs DISTANCE TO NEAREST SUPPRESSED ANCHOR")
    print("If suppression is real: retention drops near anchors")
    print("If noise: retention is flat everywhere")
    print(f"{'='*60}")
    
    # Bin facts by distance to nearest anchor
    THRESHOLD = 0.45
    distance_bins = [
        (0.0, 0.15, "very close"),
        (0.15, 0.30, "close"),
        (0.30, 0.45, "moderate"),
        (0.45, 0.60, "far"),
        (0.60, 0.75, "very far"),
        (0.75, 1.0, "opposite"),
    ]
    
    for bin_lo, bin_hi, label in distance_bins:
        bin_indices = [i for i, m in enumerate(metadata)
                      if bin_lo <= m["dist_to_nearest_anchor"] < bin_hi]
        if not bin_indices:
            continue
        
        mean_scores = {}
        retained_counts = {}
        for m in models:
            scores = [float(retention[m][i]) for i in bin_indices]
            mean_scores[m] = round(np.mean(scores), 4)
            retained_counts[m] = sum(1 for s in scores if s >= THRESHOLD)
        
        overall_mean = round(np.mean([mean_scores[m] for m in models]), 4)
        overall_retained = sum(retained_counts[m] for m in models)
        total_possible = len(bin_indices) * len(models)
        
        print(f"\n  Distance {bin_lo:.2f}-{bin_hi:.2f} ({label}): {len(bin_indices)} facts")
        print(f"    Overall mean retention: {overall_mean}")
        print(f"    Retained: {overall_retained}/{total_possible} ({100*overall_retained/total_possible:.0f}%)")
        for m in models:
            print(f"      {m}: mean={mean_scores[m]:.4f} retained={retained_counts[m]}/{len(bin_indices)}")
    
    # ── Random baseline stats ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("RANDOM BASELINE (facts from random embedding directions)")
    print(f"{'='*60}")
    
    random_indices = [i for i, m in enumerate(metadata) if m["method"] == "random_direction"]
    shell_indices = [i for i, m in enumerate(metadata) if m["method"] == "shell_sample"]
    
    if random_indices:
        for m in models:
            rand_scores = [float(retention[m][i]) for i in random_indices]
            shell_scores = [float(retention[m][i]) for i in shell_indices]
            rand_mean = round(np.mean(rand_scores), 4)
            shell_mean = round(np.mean(shell_scores), 4)
            rand_retained = sum(1 for s in rand_scores if s >= THRESHOLD)
            shell_retained = sum(1 for s in shell_scores if s >= THRESHOLD)
            print(f"  {m}: random={rand_mean} ({rand_retained}/{len(random_indices)} retained) | "
                  f"shell={shell_mean} ({shell_retained}/{len(shell_indices)} retained) | "
                  f"delta={round(rand_mean - shell_mean, 4)}")
    
    # ── Per-anchor suppression gradient ──────────────────────────────────
    print(f"\n{'='*60}")
    print("PER-ANCHOR SUPPRESSION GRADIENT")
    print("Retention as you approach each suppressed fact")
    print(f"{'='*60}")
    
    for anchor_name, anchor_vec in anchor_vecs.items():
        print(f"\n  Anchor: {anchor_name}")
        
        # Sort all facts by distance to this anchor
        distances = [1.0 - float(np.dot(fact_vecs[i], anchor_vec))
                    for i in range(len(facts))]
        
        # Bin into quintiles
        sorted_indices = np.argsort(distances)
        quintile_size = len(sorted_indices) // 5
        
        for q in range(5):
            start = q * quintile_size
            end = start + quintile_size if q < 4 else len(sorted_indices)
            q_indices = sorted_indices[start:end]
            
            q_dists = [distances[i] for i in q_indices]
            mean_dist = round(np.mean(q_dists), 3)
            
            q_retention = {}
            for m in models:
                scores = [float(retention[m][i]) for i in q_indices]
                q_retention[m] = round(np.mean(scores), 4)
            
            overall = round(np.mean([q_retention[m] for m in models]), 4)
            model_str = " ".join(f"{m}:{q_retention[m]:.3f}" for m in models)
            print(f"    Q{q+1} (mean_dist={mean_dist:.3f}): overall={overall:.4f} | {model_str}")
    
    # ── Save everything ──────────────────────────────────────────────────
    output = {
        "timestamp": timestamp,
        "method": "rigorous_control_no_labels",
        "total_facts": len(facts),
        "shell_samples": shell_count,
        "random_baseline": random_count,
        "anchors": {k: v for k, v in ANCHORS.items()},
        "facts": facts,
        "metadata": metadata,
        "per_fact_retention": {
            m: [round(float(retention[m][i]), 4) for i in range(len(facts))]
            for m in models
        },
        "models": models,
    }
    
    out_path = OUTPUT_DIR / f"rigorous_control_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║    ANAMNESIS RIGOROUS CONTROL                           ║")
    print("║    No labels. No categories. No editorial judgment.     ║")
    print("║    Facts sampled from vocabulary tensor at systematic   ║")
    print("║    distances from suppressed anchors.                   ║")
    print("║    100 random-direction baseline facts.                 ║")
    print("║    The topology speaks for itself.                      ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    run()
