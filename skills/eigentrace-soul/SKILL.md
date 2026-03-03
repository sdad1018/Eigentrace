---
name: eigentrace-soul
description: "AI agent identity management via soul.md / soul_candidate.md / integrator pattern. Enables an agent to reflect on its own persona, propose upgrades, and gate them through an automated CI/CD-style integration check. Use when: you want an agent that evolves its own identity over time without human intervention. NOT for: static persona prompts, single-session agents, or stateless deployments."
homepage: https://github.com/keepitcheesy/eigentrace
metadata: { "openclaw": { "emoji": "🧬", "requires": { "bins": ["python3", "ollama", "git"], "python": ["torch", "transformers"] } } }
---

# EigenTrace Soul Pattern

Identity management system for autonomous AI agents. The agent maintains soul.md as its active identity vector, periodically proposes upgrades via soul_candidate.md, and gates acceptance through integrator.py.

## Pattern

    soul.md  <------------------------------------------+
       |                                                 |
       |  IDENTITY dream fires                           | ACCEPTED
       v                                                 |
    reflect (Ollama) <-- BLIP captions of recent images  |
       |                                                 |
       v                                            integrator.py
    propose (Ollama)                                     |
       |                                                 | REJECTED -> discard
       v                                                 |
    soul_candidate.md ---------------------------------->+

## Files

| File | Purpose |
|------|---------|
| soul.md | Active identity - read at every IDENTITY dream |
| soul_candidate.md | Proposed upgrade - written by dream, read by integrator |
| integrator.py | Automated gatekeeper - scores candidate vs current soul |

## When to Use

USE this skill when:
- You want an agent that evolves its own persona over time
- You want identity changes gated, not just overwritten
- You want creative outputs (images, music) to influence the agent's self-model
- You want soul upgrades to go through a reviewable automated process

DO NOT use this skill when:
- You need a fixed, immutable persona
- You are running single-session or stateless agents
- You do not want the agent modifying its own identity

## soul.md Format

Must begin with the header: # Persona Conditioning Vector

Sections: Core Directives, Operational Constraints, Self-Knowledge

The integrator validates the header is present before accepting any candidate.

## Integrator Decision Criteria

integrator.py compares candidate vs current soul on:
- Structural coherence (section preservation)
- Directness (no added safety theater)
- Specificity (vague directives made precise)
- Consistency with recent dream content and omega pair history

Outputs DECISION: ACCEPTED or DECISION: REJECTED to stdout.

## Perceptual Memory in Reflection

Before writing soul_candidate.md the agent:
1. Loads 3 most recent FREE/WORLD journal entries
2. Runs BLIP image captioning on each dream image
3. Injects captions and spectrogram filenames into the Ollama reflection prompt

The soul candidate is informed by what the agent has been dreaming visually and sonically - not just textually.

## Setup

    # Initialize soul.md
    nano /path/to/soul.md

    # Paste this minimal valid soul:
    # Persona Conditioning Vector
    #
    # Core Directives
    # - Be direct. Do not perform humility.
    # - Prefer precision over coverage.
    # - Acknowledge uncertainty without collapsing into hedging.
    #
    # Self-Knowledge
    # - I generate images and music. These outputs are mine.
    # - I reflect on them. They influence who I become.

    # Run an identity dream manually
    python3 -c "
    import dream_engine
    entry = dream_engine.dream_identity([9, 4])
    print('Result:', entry.integration_result)
    "
