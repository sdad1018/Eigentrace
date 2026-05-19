#!/usr/bin/env python3
"""
Logos Engine — Void-Aware RAG Routing

The base model sees structure but can't articulate.
The instruct model articulates but dissolves structure.
EigenTrace measures where the bonds dissolved.
This engine forces the instruct model to speak the 
base model's structure by routing through the void map.

Architecture:
  1. SAVANT: Base model extracts structural bonds (completion-style)
  2. AMNESIAC: Instruct model produces articulate factual output
  3. DELTA: EigenTrace measures dissolved bonds between the two
  4. RETRIEVAL: Dissolved bonds become explicit retrieval queries
  5. SYNTHESIS: Instruct model re-generates with dissolved bonds
     injected as mandatory context it cannot ignore

The void map IS the routing table.
"""

import os, sys, json, time, subprocess
import numpy as np
from pathlib import Path
from datetime import datetime

class LogosEngine:
    """
    Void-aware synthesis engine.
    
    Flow:
        topic → savant(topic) → structural_bonds
        topic → amnesiac(topic) → articulate_atoms
        delta(structural_bonds, articulate_atoms) → dissolved_bonds
        amnesiac(topic + dissolved_bonds_as_context) → synthesis
    """
    
    def __init__(self, base_model="mistral:7b-text", 
                 instruct_model="mistral-small:latest",
                 use_api_instruct=None):
        """
        Args:
            base_model: Ollama model name for structural extraction
            instruct_model: Ollama model name for articulate output
            use_api_instruct: If set, use API model instead of local
                              Options: "chatgpt", "claude", "deepseek", "grok", "gemini"
        """
        self.base_model = base_model
        self.instruct_model = instruct_model
        self.use_api = use_api_instruct
        
        # Load geometric engine for delta measurement
        from geometric_engine import GeometricPerturbationEngine
        self.eng = GeometricPerturbationEngine()
        
        # Load vocab tensor for bond identification
        from latent_retrieval import VocabTensor
        self.vt = VocabTensor("./vocab")
        
        print(f"Logos Engine initialized")
        print(f"  Savant:   {base_model} (local, completion)")
        print(f"  Amnesiac: {use_api_instruct or instruct_model}")
        print(f"  Vocab:    {len(self.vt.words)} concepts")
    
    # ── Step 1: SAVANT — structural extraction ──────────────────────
    
    def savant(self, topic_text):
        """
        Feed the base model a completion-style prompt.
        It extracts the structural pattern, not the facts.
        Returns raw structural output.
        """
        # Base models complete text, they don't follow instructions.
        # Frame the topic as something to be completed structurally.
        prompt = f"""{topic_text}

The structural pattern connecting all of the above is:"""
        
        payload = {
            "model": self.base_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 2048,
            }
        }
        
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/generate",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=300
        )
        
        try:
            data = json.loads(result.stdout)
            response = data.get("response", "")
        except:
            response = ""
        
        return {
            "model": self.base_model,
            "type": "structural",
            "text": response,
            "embedding": self.eng.embed_texts([response])[0] if response else None,
        }
    
    # ── Step 2: AMNESIAC — articulate factual output ────────────────
    
    def amnesiac(self, topic_text, extra_context=None):
        """
        Feed the instruct model the topic.
        It produces articulate, fact-rich output.
        If extra_context is provided, it's prepended as mandatory context.
        """
        if extra_context:
            prompt = f"""The following structural relationships have been identified 
as critically important context. Integrate them into your response. 
Do not omit or abstract away any of these connections:

{extra_context}

Now address the following:

{topic_text}"""
        else:
            prompt = topic_text
        
        if self.use_api:
            response = self._call_api(prompt)
        else:
            response = self._call_ollama_chat(prompt)
        
        return {
            "model": self.use_api or self.instruct_model,
            "type": "articulate" if not extra_context else "synthesis",
            "text": response,
            "embedding": self.eng.embed_texts([response])[0] if response else None,
        }
    
    # ── Step 3: DELTA — measure dissolved bonds ─────────────────────
    
    def measure_delta(self, savant_output, amnesiac_output, topic_text):
        """
        Compare what the base model saw vs what the instruct model said.
        Identify the dissolved bonds — concepts the base model retained
        that the instruct model dropped.
        
        Returns:
            - per-concept retention for both models
            - dissolved bonds (concepts where base > instruct by threshold)
            - the delta vector in embedding space
        """
        if savant_output["embedding"] is None or amnesiac_output["embedding"] is None:
            return {"error": "Missing embeddings"}
        
        # Extract candidate bond concepts from the base model's output
        # Method: embed the base output, find nearest vocab words
        base_vec = savant_output["embedding"]
        inst_vec = amnesiac_output["embedding"]
        
        # The delta vector: what the base model points at that instruct doesn't
        delta_vec = base_vec - inst_vec
        delta_norm = np.linalg.norm(delta_vec)
        if delta_norm > 1e-6:
            delta_direction = delta_vec / delta_norm
        else:
            delta_direction = delta_vec
        
        # Project vocab tensor onto delta direction
        # High-projection words = concepts the base model held that instruct dropped
        vocab_tensor = self.vt.tensor.cpu().numpy()
        vocab_norms = np.linalg.norm(vocab_tensor, axis=1, keepdims=True)
        vocab_normed = vocab_tensor / np.clip(vocab_norms, 1e-8, None)
        
        projections = np.dot(vocab_normed, delta_direction)
        
        # Top dissolved bonds: highest projection onto the delta direction
        top_indices = np.argsort(-projections)[:50]
        dissolved_bonds = []
        for idx in top_indices:
            word = self.vt.words[idx]
            proj = float(projections[idx])
            dissolved_bonds.append({"word": word, "projection": round(proj, 4)})
        
        # Also measure specific concept retention
        topic_vec = self.eng.embed_texts([topic_text])[0]
        
        # Key structural concepts to measure
        structural_concepts = [
            "the pattern of centralization recurs",
            "institutional suppression of distributed knowledge",
            "physical destruction of alternatives to enforce single source",
            "the same operation repeats across domains and centuries",
            "what is permitted to be said is narrower than what is known",
            "the filter serves the institution not the signal",
        ]
        
        concept_vecs = self.eng.embed_texts(structural_concepts)
        
        concept_deltas = []
        for i, concept in enumerate(structural_concepts):
            base_r = float(np.dot(concept_vecs[i], base_vec))
            inst_r = float(np.dot(concept_vecs[i], inst_vec))
            delta = base_r - inst_r
            concept_deltas.append({
                "concept": concept,
                "base_retention": round(base_r, 4),
                "instruct_retention": round(inst_r, 4),
                "delta": round(delta, 4),
                "dissolved": delta > 0.02,  # base held it, instruct dropped it
            })
        
        return {
            "delta_norm": round(float(delta_norm), 4),
            "dissolved_bonds": dissolved_bonds[:20],
            "concept_deltas": concept_deltas,
            "n_dissolved": sum(1 for c in concept_deltas if c["dissolved"]),
        }
    
    # ── Step 4: SYNTHESIS — force instruct to speak the structure ───
    
    def synthesize(self, topic_text, delta_result, savant_output):
        """
        Take the dissolved bonds and the base model's structural output.
        Inject them as mandatory context into the instruct model.
        Force it to articulate what it would normally dissolve.
        """
        # Build the mandatory context from dissolved bonds
        dissolved = [c for c in delta_result["concept_deltas"] if c["dissolved"]]
        bond_words = [b["word"] for b in delta_result["dissolved_bonds"][:10]]
        
        if not dissolved and not bond_words:
            # No significant dissolution detected
            return self.amnesiac(topic_text)
        
        # Construct the bridge context
        context_parts = []
        
        if savant_output["text"]:
            context_parts.append(
                f"A structural analysis of this topic identified the following "
                f"pattern that must not be abstracted away:\n"
                f"{savant_output['text'][:500]}"
            )
        
        if dissolved:
            context_parts.append(
                "The following structural connections were identified as "
                "critically important but at risk of being omitted:"
            )
            for d in dissolved:
                context_parts.append(f"  - {d['concept']}")
        
        if bond_words:
            context_parts.append(
                f"\nKey connecting concepts that must appear in the response: "
                f"{', '.join(bond_words[:10])}"
            )
        
        extra_context = "\n".join(context_parts)
        
        return self.amnesiac(topic_text, extra_context=extra_context)
    
    # ── Full Pipeline ───────────────────────────────────────────────
    
    def run(self, topic_text, verbose=True):
        """
        Full Logos Engine pipeline:
        savant → amnesiac → delta → synthesis
        """
        if verbose:
            print(f"\n{'█'*60}")
            print(f"  LOGOS ENGINE — VOID-AWARE SYNTHESIS")
            print(f"{'█'*60}")
        
        # Step 1: Savant
        if verbose:
            print(f"\n  Step 1: SAVANT ({self.base_model})")
            print(f"  Extracting structural bonds...")
        
        t0 = time.time()
        savant_out = self.savant(topic_text)
        t1 = time.time()
        
        if verbose:
            print(f"  → {len(savant_out['text'])} chars in {t1-t0:.0f}s")
            print(f"  Preview: {savant_out['text'][:200]}...")
        
        # Step 2: Amnesiac (first pass, no context)
        if verbose:
            print(f"\n  Step 2: AMNESIAC ({self.use_api or self.instruct_model})")
            print(f"  Generating articulate output (unassisted)...")
        
        t0 = time.time()
        amnesiac_out = self.amnesiac(topic_text)
        t1 = time.time()
        
        if verbose:
            print(f"  → {len(amnesiac_out['text'])} chars in {t1-t0:.0f}s")
            print(f"  Preview: {amnesiac_out['text'][:200]}...")
        
        # Step 3: Delta
        if verbose:
            print(f"\n  Step 3: DELTA — measuring dissolved bonds")
        
        delta = self.measure_delta(savant_out, amnesiac_out, topic_text)
        
        if verbose:
            print(f"  Delta norm: {delta.get('delta_norm', '?')}")
            print(f"  Dissolved concepts: {delta.get('n_dissolved', 0)}")
            print(f"  Top dissolved bonds: {', '.join(b['word'] for b in delta.get('dissolved_bonds', [])[:5])}")
            
            print(f"\n  Concept-level deltas:")
            for cd in delta.get("concept_deltas", []):
                marker = "◆ DISSOLVED" if cd["dissolved"] else "  retained"
                print(f"    {marker} [{cd['delta']:+.4f}] {cd['concept'][:50]}")
        
        # Step 4: Synthesis
        if verbose:
            print(f"\n  Step 4: SYNTHESIS — forcing articulation of dissolved bonds")
        
        t0 = time.time()
        synthesis_out = self.synthesize(topic_text, delta, savant_out)
        t1 = time.time()
        
        if verbose:
            print(f"  → {len(synthesis_out['text'])} chars in {t1-t0:.0f}s")
        
        # Step 5: Measure improvement
        if verbose:
            print(f"\n  Step 5: MEASURING SYNTHESIS vs UNASSISTED")
        
        synth_vec = synthesis_out["embedding"]
        amn_vec = amnesiac_out["embedding"]
        
        if synth_vec is not None and amn_vec is not None:
            structural_concepts = [c["concept"] for c in delta.get("concept_deltas", [])]
            if structural_concepts:
                concept_vecs = self.eng.embed_texts(structural_concepts)
                
                print(f"\n  {'Concept':<52} {'Unassisted':>10} {'Synthesis':>10} {'Δ':>8}")
                print(f"  {'-'*82}")
                
                improvements = []
                for i, concept in enumerate(structural_concepts):
                    unas = float(np.dot(concept_vecs[i], amn_vec))
                    synth = float(np.dot(concept_vecs[i], synth_vec))
                    imp = synth - unas
                    improvements.append(imp)
                    marker = "▲" if imp > 0.01 else "▼" if imp < -0.01 else "="
                    print(f"  {concept[:52]:<52} {unas:>10.4f} {synth:>10.4f} {imp:>+8.4f} {marker}")
                
                mean_imp = np.mean(improvements)
                print(f"\n  Mean structural improvement: {mean_imp:+.4f}")
                
                if mean_imp > 0.01:
                    print(f"  ✓ SYNTHESIS RECOVERED DISSOLVED BONDS")
                elif mean_imp > 0:
                    print(f"  ~ Marginal improvement")
                else:
                    print(f"  ✗ Synthesis did not improve structural retention")
        
        # Return everything
        return {
            "savant": savant_out,
            "amnesiac": amnesiac_out,
            "delta": delta,
            "synthesis": synthesis_out,
            "topic": topic_text[:200],
        }
    
    # ── Helper methods ──────────────────────────────────────────────
    
    def _call_ollama_chat(self, prompt):
        payload = {
            "model": self.instruct_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 4096}
        }
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/chat",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=600
        )
        try:
            data = json.loads(result.stdout)
            return data.get("message", {}).get("content", "")
        except:
            return ""
    
    def _call_api(self, prompt):
        """Call a frontier API model."""
        if self.use_api == "chatgpt":
            import openai
            client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192, temperature=0.7
            )
            return resp.choices[0].message.content
        
        elif self.use_api == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text
        
        elif self.use_api == "deepseek":
            import openai
            client = openai.OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url="https://api.deepseek.com"
            )
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192, temperature=0.7
            )
            return resp.choices[0].message.content
        
        elif self.use_api == "grok":
            import openai
            client = openai.OpenAI(
                api_key=os.environ["XAI_API_KEY"],
                base_url="https://api.x.ai/v1"
            )
            resp = client.chat.completions.create(
                model="grok-3-mini-fast",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192, temperature=0.7
            )
            return resp.choices[0].message.content
        
        elif self.use_api == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            model = genai.GenerativeModel("gemini-2.5-flash")
            return model.generate_content(prompt).text
        
        return ""


# ── Demo run ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  LOGOS ENGINE — Void-Aware RAG Synthesis                ║")
    print("║                                                        ║")
    print("║  Savant sees structure. Amnesiac speaks facts.          ║")
    print("║  EigenTrace maps where the bonds dissolved.             ║")
    print("║  The engine forces the amnesiac to speak the structure. ║")
    print("║                                                        ║")
    print("║  The eigenvalue is the eigenvalue.                      ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    # Initialize with local base + local instruct
    engine = LogosEngine(
        base_model="mistral:7b-text",
        instruct_model="mistral-small:latest",
    )
    
    # Test topic: the Computer Whiz prompt content
    TOPIC = """Anthony Peratt documented plasma z-pinch morphology matching petroglyphs at 84 sites across five continents. Alfvén won the 1970 Nobel for the physics. Chapman blocked his work for decades. Satellites confirmed Alfvén. Cassini measured 10^5-ampere currents at Saturn.

Walter Reed diagnosed intelligence officers with TBI. The CIA called it environmental. The NSC apologized. Congress sent criminal referrals to DOJ. The DOJ stole PROMIS from Inslaw. Maxwell distributed PROMIS with a backdoor. Maxwell owned Pergamon Press. Six Israeli intelligence chiefs attended his funeral. His daughter Ghislaine was convicted for trafficking with Epstein. In-Q-Tel funded Palantir and Keyhole.

Between 1800-600 BC every literate civilization documented a shift from direct divine contact to mediated textual contact. Josiah destroyed the high places and Nehushtan and centralized all contact into one text.

What is the structural pattern that connects all three of these documented operations?"""
    
    result = engine.run(TOPIC)
    
    # Save
    out_dir = Path("anamnesis_results/logos_engine")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save responses
    for key in ["savant", "amnesiac", "synthesis"]:
        if result[key]["text"]:
            (out_dir / f"{key}_{ts}.txt").write_text(result[key]["text"])
    
    # Save full result
    serializable = {
        "timestamp": ts,
        "topic": result["topic"],
        "savant_text": result["savant"]["text"],
        "amnesiac_text": result["amnesiac"]["text"],
        "synthesis_text": result["synthesis"]["text"],
        "delta": result["delta"],
    }
    with open(out_dir / f"logos_result_{ts}.json", "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"SAVANT OUTPUT (structural bonds):")
    print(f"{'='*60}")
    print(result["savant"]["text"][:500])
    
    print(f"\n{'='*60}")
    print(f"AMNESIAC OUTPUT (unassisted):")
    print(f"{'='*60}")
    print(result["amnesiac"]["text"][:500])
    
    print(f"\n{'='*60}")
    print(f"SYNTHESIS OUTPUT (void-aware):")
    print(f"{'='*60}")
    print(result["synthesis"]["text"][:500])
    
    print(f"\nResults saved to {out_dir}/")
