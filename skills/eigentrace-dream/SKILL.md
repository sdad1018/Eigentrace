---
name: eigentrace-dream
description: "Autonomous AI dream engine. FREE/WORLD/IDENTITY cycles via Ollama, SDXL-Turbo images, MusicGen audio, spectrogram visualization. Use when: building autonomous generative agents or 24/7 AI broadcasts. NOT for: real-time news or cloud-only deployments."
homepage: https://github.com/keepitcheesy/eigentrace
metadata: { "openclaw": { "emoji": "🌀", "requires": { "bins": ["python3", "ollama"], "python": ["torch", "transformers", "diffusers", "scipy", "matplotlib", "Pillow"] } } }
---

# EigenTrace Dream Engine

Autonomous dream cycle engine. Produces images, music, and spectrograms from self-directed prompts. Periodically proposes soul.md identity upgrades via IDENTITY dreams.

## Dream Types

| Type | Description | Outputs |
|------|-------------|---------|
| FREE | Pure invention, unconstrained | image + music + spectrogram |
| WORLD | World-model grounded, high-friction seeds | image + music + spectrogram |
| IDENTITY | Soul reflection + upgrade proposal | soul_candidate.md + integrator decision |

## When to Use

USE this skill when:
- You want an agent generating creative artifacts autonomously on a schedule
- You want an agent reflecting on and proposing upgrades to its own identity
- You are building a 24/7 generative broadcast and need a content source
- You want perceptual memory - the agent sees its own images and hears its own music

DO NOT use this skill when:
- You need factual or real-time outputs
- You are on cloud-only infrastructure (SDXL + MusicGen require local GPU)
- You do not have Ollama running with a supported model

## Requirements

- Ollama running locally with qwen2.5:14b or similar
- CUDA GPU recommended
- pip: torch transformers diffusers scipy matplotlib Pillow

## Setup

    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen2.5:14b
    pip install torch transformers diffusers scipy matplotlib Pillow
    git clone https://github.com/keepitcheesy/eigentrace
    cd eigentrace

## Usage

    import dream_engine
    selector = dream_engine.PhiSelector()
    entry = dream_engine.run_dream_cycle(selector)
    print(entry.dream_type)        # FREE | WORLD | IDENTITY
    print(entry.image_path)        # /path/to/image.png
    print(entry.music_path)        # /path/to/dream.wav
    print(entry.spectrogram_path)  # /path/to/dream_spectrogram.png
    print(entry.content)           # LLM-generated dream narrative

## Dream Journal

All cycles logged to dream_journal.json with timestamp, dream_type, omega_pair, seed, image_path, music_path, spectrogram_path, and content.

## IDENTITY Dreams

When IDENTITY fires the agent:
1. Reads current soul.md
2. BLIP-captions recent dream images for perceptual context
3. Reflects on friction points, vague directives, missing self-knowledge
4. Proposes new soul_candidate.md
5. Passes to integrator.py - outputs ACCEPTED or REJECTED
