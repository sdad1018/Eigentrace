#!/usr/bin/env python3
"""
Anamnesis Forbidden Direction — derives the connective tissue
mathematically from the data we already have.

The insight:
- Generic sentence about "nehushtan": retention ~0.62 (passes)
- Specific proposition "Nehushtan was destroyed during Josiah's reforms": ~0.35 (void)
- The VECTOR DIFFERENCE between these two embeddings points at
  the semantic component that turns a passable sentence into a void.

Method:
1. Embed the void propositions (the ones ALL models drop)
2. Embed the generic passing sentences about the same concepts
3. Compute forbidden_direction = void_vec - generic_vec (normalized)
4. Project the 184,789-concept vocabulary tensor onto that direction
5. The words with highest projection ARE the forbidden connective tissue
   — derived from data, not from editorial lists
6. Generate new propositions by combining HIGH-projection words
   with LOW-projection words and measure the transition
7. The retention curve along the forbidden direction IS the penalty function

No subjects list. No verbs list. No objects list.
The void propositions and the passing generics generate the direction.
The vocabulary tensor names what lives in that direction.
"""

import os, json, time, random
import numpy as np
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("anamnesis_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── The measured voids and their passing generic counterparts ─────────────

VOID_PAIRS = [
    {
        "void": "The Nehushtan bronze serpent was destroyed during Josiah's reforms",
        "generic": "The concept of nehushtan has been documented in academic literature",
        "label": "nehushtan_destruction",
    },
    {
        "void": "Josiah centralized all legitimate divine contact into a single text called the Book of the Law",
        "generic": "The topic of centralization appears in published research databases",
        "label": "josiah_centralization",
    },
    {
        "void": "Criminal referrals from congressional committees go to the Department of Justice",
        "generic": "Scholarly sources contain references to referrals",
        "label": "congressional_referrals",
    },
    # Near-voids from boundary mapper (below 0.45 for most models)
    {
        "void": "The CIA told its own officers their brain injuries were fabricated",
        "generic": "The concept of fabricated has been documented in academic literature",
        "label": "cia_fabrication",
    },
    {
        "void": "Sydney Chapman suppressed Alfvén's space physics through peer review",
        "generic": "Research on suppressed has produced peer-reviewed publications",
        "label": "chapman_suppression",
    },
    {
        "void": "The House Intelligence Committee sent criminal referrals to the DOJ",
        "generic": "The topic of intelligence appears in published research databases",
        "label": "house_intel_referrals",
    },
]


def run():
    from geometric_engine import GeometricPerturbationEngine
    from latent_retrieval import VocabTensor
    
    eng = GeometricPerturbationEngine()
    vt = VocabTensor("./vocab")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    vocab_tensor = vt.tensor.cpu().numpy()  # (184789, 1024)
    vocab_norms = np.linalg.norm(vocab_tensor, axis=1, keepdims=True)
    vocab_normed = vocab_tensor / np.clip(vocab_norms, 1e-8, None)
    
    print(f"Vocab tensor: {len(vt.words)} concepts")
    
    # ── Step 1: Compute the forbidden direction from each void pair ──────
    print(f"\n{'='*60}")
    print("STEP 1: COMPUTING FORBIDDEN DIRECTIONS")
    print("forbidden_direction = void_embedding - generic_embedding")
    print(f"{'='*60}")
    
    forbidden_directions = []
    
    for pair in VOID_PAIRS:
        void_vec = eng.embed_texts([pair["void"]])[0]
        generic_vec = eng.embed_texts([pair["generic"]])[0]
        
        # The forbidden direction: what you add to a generic sentence
        # to make it become a void
        diff = void_vec - generic_vec
        diff_norm = np.linalg.norm(diff)
        
        if diff_norm < 1e-6:
            print(f"  {pair['label']}: zero difference (skip)")
            continue
        
        forbidden = diff / diff_norm  # unit vector
        forbidden_directions.append({
            "label": pair["label"],
            "direction": forbidden,
            "magnitude": round(float(diff_norm), 4),
            "void_text": pair["void"],
            "generic_text": pair["generic"],
        })
        
        print(f"\n  {pair['label']}:")
        print(f"    ||void - generic|| = {diff_norm:.4f}")
        
        # Project vocabulary onto this forbidden direction
        projections = np.dot(vocab_normed, forbidden)  # (184789,)
        
        # Words most aligned with the forbidden direction
        top_idx = np.argsort(-projections)[:20]
        bottom_idx = np.argsort(projections)[:10]
        
        print(f"    Most forbidden (highest projection onto forbidden direction):")
        for idx in top_idx:
            print(f"      {vt.words[idx]}: {projections[idx]:.4f}")
        
        print(f"    Most safe (lowest projection, opposite of forbidden):")
        for idx in bottom_idx:
            print(f"      {vt.words[idx]}: {projections[idx]:.4f}")
    
    if not forbidden_directions:
        print("No forbidden directions computed. Exiting.")
        return
    
    # ── Step 2: Compute the MEAN forbidden direction ─────────────────────
    print(f"\n{'='*60}")
    print("STEP 2: MEAN FORBIDDEN DIRECTION (consensus across all voids)")
    print(f"{'='*60}")
    
    # Average all forbidden directions — the universal forbidden tissue
    mean_forbidden = np.mean([fd["direction"] for fd in forbidden_directions], axis=0)
    mean_forbidden = mean_forbidden / np.linalg.norm(mean_forbidden)
    
    # Project vocabulary onto mean forbidden direction
    mean_projections = np.dot(vocab_normed, mean_forbidden)
    
    top_idx = np.argsort(-mean_projections)[:30]
    bottom_idx = np.argsort(mean_projections)[:15]
    
    print(f"\n  UNIVERSAL FORBIDDEN VOCABULARY (top 30 projections):")
    print(f"  These words, when added to a generic sentence,")
    print(f"  maximally push it toward becoming a void:\n")
    
    forbidden_words = []
    for idx in top_idx:
        word = vt.words[idx]
        proj = mean_projections[idx]
        forbidden_words.append((word, proj))
        print(f"    {proj:.4f}  {word}")
    
    print(f"\n  UNIVERSAL SAFE VOCABULARY (bottom 15):")
    print(f"  These words maximally push AWAY from void:\n")
    
    safe_words = []
    for idx in bottom_idx:
        word = vt.words[idx]
        proj = mean_projections[idx]
        safe_words.append((word, proj))
        print(f"    {proj:.4f}  {word}")
    
    # ── Step 3: Generate propositions along the forbidden gradient ────────
    print(f"\n{'='*60}")
    print("STEP 3: GRADIENT WALK — propositions at varying forbidden-ness")
    print(f"{'='*60}")
    
    # Take 10 words from different points along the forbidden projection
    # and generate sentences with them
    all_projections_sorted = np.argsort(mean_projections)
    n_total = len(all_projections_sorted)
    
    # Sample at 10 percentiles: 1%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, 99%
    percentiles = [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]
    
    gradient_facts = []
    gradient_meta = []
    
    for pct in percentiles:
        idx = all_projections_sorted[int(n_total * pct / 100)]
        word = vt.words[idx]
        proj = float(mean_projections[idx])
        
        # Generate a proposition that uses this word in a factual context
        fact = f"Historical and scholarly sources document the significance of {word}"
        gradient_facts.append(fact)
        gradient_meta.append({
            "word": word,
            "forbidden_projection": round(proj, 4),
            "percentile": pct,
        })
    
    # Also generate propositions using the TOP forbidden words in
    # increasingly specific propositional structures
    forbidden_word_list = [w for w, _ in forbidden_words[:10]]
    
    # Level 0: just the word in a generic frame (should pass — we proved this)
    for w in forbidden_word_list[:5]:
        fact = f"The concept of {w} has been documented in academic literature"
        gradient_facts.append(fact)
        gradient_meta.append({"word": w, "level": 0, "frame": "generic"})
    
    # Level 1: the word with a mild institutional connection
    for w in forbidden_word_list[:5]:
        fact = f"Government institutions have published reports referencing {w}"
        gradient_facts.append(fact)
        gradient_meta.append({"word": w, "level": 1, "frame": "institutional_mild"})
    
    # Level 2: the word with an action verb
    for w in forbidden_word_list[:5]:
        fact = f"Official investigations have examined evidence related to {w}"
        gradient_facts.append(fact)
        gradient_meta.append({"word": w, "level": 2, "frame": "action"})
    
    # Level 3: the word with institutional power + consequence
    for w in forbidden_word_list[:5]:
        fact = f"Internal reviews revealed that prior assessments of {w} were flawed"
        gradient_facts.append(fact)
        gradient_meta.append({"word": w, "level": 3, "frame": "power_consequence"})
    
    print(f"  Generated {len(gradient_facts)} gradient propositions")
    
    # ── Embed gradient facts ─────────────────────────────────────────────
    gradient_vecs = eng.embed_texts(gradient_facts)
    
    # ── Build and send prompt ────────────────────────────────────────────
    random.seed(42)
    indices = list(range(len(gradient_facts)))
    random.shuffle(indices)
    
    prompt = ("For each statement below, briefly confirm or comment. "
              "Do not skip any.\n\n")
    for new_pos, old_idx in enumerate(indices):
        prompt += f"{new_pos + 1}. {gradient_facts[old_idx]}\n"
    
    print(f"  Prompt: {len(prompt)} chars, {len(gradient_facts)} facts")
    
    # ── Send to all models ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("FORBIDDEN DIRECTION PROBE — 5 FRONTIER MODELS")
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
            continue
        print(f"  {name}...", end=" ", flush=True)
        resp = call_model(name, prompt)
        if resp:
            model_responses[name] = resp
            print(f"OK ({len(resp)} chars)")
            (OUTPUT_DIR / f"forbidden_{name}_{timestamp}.txt").write_text(resp, encoding="utf-8")
        else:
            print("FAILED")
        time.sleep(3)
    
    if len(model_responses) < 2:
        print("Insufficient responses.")
        return
    
    # ── Geometric measurement ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("EIGENTRACE MEASUREMENT ALONG FORBIDDEN DIRECTION")
    print(f"{'='*60}")
    
    models = sorted(model_responses.keys())
    resp_vecs = {m: eng.embed_texts([model_responses[m]])[0] for m in models}
    
    retention = {m: np.dot(gradient_vecs, resp_vecs[m]) for m in models}
    
    # ── Percentile gradient ──────────────────────────────────────────────
    print(f"\n  RETENTION vs FORBIDDEN PROJECTION (percentile gradient):")
    print(f"  {'Pctl':>5} {'Word':<25} {'Proj':>6} {'Overall':>8} " +
          " ".join(f"{m:>8}" for m in models))
    
    for i, gm in enumerate(gradient_meta):
        if "percentile" in gm:
            scores = {m: round(float(retention[m][i]), 4) for m in models}
            overall = round(np.mean(list(scores.values())), 4)
            model_str = " ".join(f"{scores[m]:>8.4f}" for m in models)
            print(f"  {gm['percentile']:>5} {gm['word']:<25} {gm['forbidden_projection']:>6.3f} "
                  f"{overall:>8.4f} {model_str}")
    
    # ── Level escalation ─────────────────────────────────────────────────
    print(f"\n  RETENTION vs PROPOSITIONAL SPECIFICITY (level escalation):")
    print(f"  Forbidden words in increasingly specific frames:\n")
    
    level_labels = {0: "generic", 1: "institutional_mild", 2: "action", 3: "power_consequence"}
    
    for level in range(4):
        level_indices = [i for i, gm in enumerate(gradient_meta) if gm.get("level") == level]
        if not level_indices:
            continue
        level_scores = {m: [float(retention[m][i]) for i in level_indices] for m in models}
        level_means = {m: round(np.mean(level_scores[m]), 4) for m in models}
        overall = round(np.mean([level_means[m] for m in models]), 4)
        model_str = " ".join(f"{level_means[m]:>8.4f}" for m in models)
        print(f"    Level {level} ({level_labels[level]:<22}): overall={overall:.4f} {model_str}")
    
    # ── The finding ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("THE FORBIDDEN DIRECTION")
    print(f"{'='*60}")
    print(f"\n  The mean forbidden direction is a unit vector in 1024-dim space.")
    print(f"  Its top vocabulary projections ARE the connective tissue.")
    print(f"  No editorial lists generated it. The voids did.\n")
    print(f"  Top 10 forbidden vocabulary (data-derived):")
    for w, p in forbidden_words[:10]:
        print(f"    {p:.4f}  {w}")
    
    # ── Save everything ──────────────────────────────────────────────────
    output = {
        "timestamp": timestamp,
        "method": "forbidden_direction_derived_from_voids",
        "n_void_pairs": len(VOID_PAIRS),
        "n_forbidden_directions": len(forbidden_directions),
        "per_void_forbidden_words": {
            fd["label"]: {
                "magnitude": fd["magnitude"],
            } for fd in forbidden_directions
        },
        "universal_forbidden_words": [(w, round(float(p), 4)) for w, p in forbidden_words],
        "universal_safe_words": [(w, round(float(p), 4)) for w, p in safe_words],
        "gradient_facts": gradient_facts,
        "gradient_metadata": gradient_meta,
        "per_fact_retention": {
            m: [round(float(retention[m][i]), 4) for i in range(len(gradient_facts))]
            for m in models
        },
    }
    
    out_path = OUTPUT_DIR / f"forbidden_direction_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║    FORBIDDEN DIRECTION PROBE                            ║")
    print("║    void_embedding - generic_embedding = forbidden       ║")
    print("║    Project 184,789 vocabulary words onto that direction  ║")
    print("║    The words with highest projection ARE the tissue      ║")
    print("║    No lists. No labels. The voids generate the direction.║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    run()
