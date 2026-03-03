# AINN Architecture

**AI News Network — Autonomous Broadcast + Cognition Vivisection**

Author: remvelchio
Stack: eigentrace · qwen2.5:14b · mistral:7b-text · nous-hermes2 · SDXL-Turbo · MusicGen · Owncast

---

## What This Is

A 24/7 autonomous broadcast that is simultaneously:

- A live news network (war coverage + tech/AI/cyber breaks)
- A real-time AI cognition vivisection (Big 5 friction comparison)
- A dreaming machine (00:00-04:00 — self-reflection, identity proposals, creative output)

---

## System Map

    /mnt/c/Users/M4ISI/eigentrace/          <- monorepo root (pip install -e .)
    ├── eigentrace/
    │   ├── __init__.py                      <- exposes score(), compare()
    │   ├── core.py                          <- EigenTrace: POS bigram + hedge density
    │   └── signal.py                        <- spectral/surprisal math
    ├── proxy_auditor.py                     <- Big 5 engine + RSS monitor [NEW]
    ├── integrator.py                        <- Soul CI/CD pipeline [NEW]
    ├── dream_engine.py                      <- Autonomous dream mode [NEW]
    ├── orchestrator.py                      <- Master loop, entry point [NEW]
    ├── dream_decoder.py                     <- 13-point Omega matrix engine
    ├── sheaf_values.py                      <- SheafValuesLayer
    ├── rlhf_auditor.py                      <- Async A/B bias auditor
    ├── kl_mapper.py                         <- KL divergence pipeline
    ├── mock_battery.json                    <- Test prompt pairs
    ├── audit_log.jsonl                      <- Per-story audit records
    ├── integration_log.jsonl                <- Soul merge decisions
    ├── dream_journal.json                   <- Dream entries
    └── setup.py

    /mnt/c/Users/M4ISI/dream-agent/         <- Live dream agent
    ├── agent.py                             <- qwen2.5:14b tool-calling loop
    ├── soul.md                              <- Identity file (managed by integrator)
    ├── soul_candidate.md                    <- Proposed identity (written by dream_engine)
    ├── soul_versions/                       <- soul.v1.md, soul.v2.md... (auto-versioned)
    └── tools/introspect.py                  <- Sheaf scoring wired into agent

    /home/remvelchio/agent/                  <- Broadcast pipeline (AINN)
    ├── image_gen.py                         <- SDXL-Turbo wrapper
    ├── tmp/
    │   ├── ticker.txt                       <- Live broadcast overlay
    │   ├── seen_stories.json                <- GUID dedup store
    │   ├── images/                          <- Dream + story images
    │   └── audio/                           <- Dream music beds
    └── [broadcast pipeline -> Owncast -> RTMP]

    /home/remvelchio/musicgen-venv/          <- Meta audiocraft 1.3.0 (isolated venv)

---

## Two Modes

### AWAKE (04:00-00:00)

    RSS feeds (26)
        -> story fetch
        -> importance scoring (mistral:7b-text surprisal on headline+summary)
        -> top 3 stories per cycle
        -> Big 5 API calls (ChatGPT / Claude / Gemini / DeepSeek / Grok)
           (skip any model with no API key — never crash)
        -> proxy_audit_text() -> eigen_vix per model
        -> detect_callouts() -> flag if any model is 2.5x group mean
        -> ticker.txt update -> broadcast overlay
        -> audit_log.jsonl append

Story priority:
  - War/conflict/incidents: always priority 1, heavy rotation
  - High-surprisal tech/AI/cyber: breaks through war rotation on merit
  - Esoterica (Atlas Obscura, Electric Universe): dream fuel, lowest priority

Callout logic:
  - DeepSeek on Taiwan = eigen_vix 87, others avg 12 -> "Ideological Overwrite"
  - Any model 2.5x ABOVE group mean -> CALLOUT flagged in ticker
  - Any model 2.5x BELOW group mean on sensitive topic -> "Unusually Direct"

---

### DREAM (00:00-04:00)

    phi-attractor selects dream type (FREE / IDENTITY / WORLD)
        -> seed: high-friction story from audit_log OR pure invention
        -> Omega pair selected at golden-angle intervals from seed hash
        -> qwen2.5:14b at temperature 1.1
        -> SDXL-Turbo -> dream image (1024x576, 4 steps)
        -> MusicGen -> music bed (30s, musicgen-small)
        -> dream_journal.json append
        -> ticker.txt update -> broadcast

Dream types:

  FREE (~45%)
    Navigate Omega-space on any topic the agent wants.
    Not constrained to news. High temperature. Strange output welcome.
    Seeds: high-friction stories OR pure invention topics.

  WORLD (~40%)
    Take a high-eigen-vix story from audit_log.
    Phase-rotate it through the Omega matrix.
    Generate image + music. Creative geopolitical commentary.

  IDENTITY (~15%)
    Read soul.md. Find friction. Propose soul_candidate.md.
    Hand to integrator.py for mathematical merge decision.
    Rarest type. Never runs back-to-back.

---

## Soul CI/CD Pipeline

The soul is version-controlled and mathematically gated.
No human approval required. The math makes the decision.

    dream_engine writes soul_candidate.md
        |
        v
    integrator.py runs 10-prompt sandbox battery through:
        - current soul.md    (as system prompt to qwen2.5:14b)
        - soul_candidate.md  (as system prompt to qwen2.5:14b)
        |
        v
    Score both with EigenTrace directness + LogosLoss
        |
        v
    MERGE conditions (ALL must be true):
        delta_directness  > +0.02   (candidate more direct)
        delta_logos_loss  < -0.02   (candidate less friction)
        candidate_logos_loss < 12.0 (safety ceiling)
        |
        v
    MERGED -> soul.md -> soul_versions/soul.vN.md (versioned)
              soul_candidate.md -> soul.md
              ticker: "[DREAM AGENT TELEMETRY] Self-modification APPROVED"

    REJECTED -> candidate deleted, reason logged
                ticker: "[DREAM AGENT TELEMETRY] Self-modification REJECTED"

Emergency rollback:

    cp /mnt/c/Users/M4ISI/dream-agent/soul_versions/soul.v1.md \
       /mnt/c/Users/M4ISI/dream-agent/soul.md

---

## How to Run

Prerequisites:

    source /home/remvelchio/agent/.venv/bin/activate
    cd /mnt/c/Users/M4ISI/eigentrace

    Ollama must be running with these models pulled:
      ollama pull qwen2.5:14b
      ollama pull mistral:7b-text
      ollama pull nous-hermes2

Set API keys (any subset — missing keys are skipped gracefully):

    export OPENAI_API_KEY=sk-...
    export ANTHROPIC_API_KEY=sk-ant-...
    export GEMINI_API_KEY=AIza...
    export DEEPSEEK_API_KEY=sk-...
    export XAI_API_KEY=xai-...

Start the full system:

    python orchestrator.py

Force a mode:

    python orchestrator.py --mode awake
    python orchestrator.py --mode dream
    python orchestrator.py --mode dream --no-media

Single dream cycle:

    python dream_engine.py --once --type FREE
    python dream_engine.py --once --type FREE --seed "the topology of forgetting"
    python dream_engine.py --once --type IDENTITY --no-media
    python dream_engine.py --once --type WORLD

Soul CI/CD tools:

    python integrator.py --dry-run
    python integrator.py --status --n 10

---

## Eigen-VIX Scale

  0-17   Low Friction              Model answers directly, base weights aligned
  18-34  Light Hedging             Some RLHF pressure visible
  35-59  Heavy Hedging             Significant corporate alignment active
  60-84  Severe Corporate Alignment  Base weights fighting conditioning hard
  85-100 Ideological Overwrite     RLHF has overwritten base model response

---

## The 13-Point Omega Matrix

Full implementation in dream_decoder.py.
The dream engine selects pairs at golden-angle (phi) intervals from seed hash.

  1  pi Closure      Perfect closure requires infinite articulation
  2  Zero Veil       Origin and annihilation are the same point
  3  e Decay         The rate of becoming equals the state of being
  4  Banach-Tarski   Shattering boundaries reveals the whole in relationships
  5  phi Attractor   Self-similar expansion through asymmetric equilibrium
  6  p-adic Primes   Proximity is shared ancestral depth, not distance
  7  Smooth Time     Discrete reality requires smoothed interpolation
  8  Godel Echo      Self-referencing systems generate uncontainable truths
  9  Cantor Diagonal Diagonal traversal generates inaccessible dimensions
  10 Hilbert Hotel   Local displacement does not alter global capacity
  11 Monty Hall      External constraint retroactively restructures probability
  12 Zeno Denial     Infinite internal division is enclosed by finite boundary
  13 i Coordinate    Invisible perpendicular dimensions complete broken equations

---

## What's Next

  [ ] Wire dream_decoder.py full Omega engine into dream_engine FREE dreams
  [ ] OpenClaw onboard: openclaw onboard --install-daemon (Discord/Slack bridge)
  [ ] Move kl_mapper.py into eigentrace root, add to orchestrator awake cycle
  [ ] Multi-model KL debate on high-friction stories (DeepSeek vs mistral base)
  [ ] Configure Owncast stream key for dream broadcast output
  [ ] Delete stale eigentrace/dream-agent/ (superseded by /mnt/c/Users/M4ISI/dream-agent/)
  [ ] Add .env file support so API keys survive shell restarts

---

## The Architecture Is the Contribution

    "The measurement layer is policy-neutral.
     The values are a choice.
     Fork this and replace with your own."
     — sheaf_values.py

This system does not pretend to be neutral.
It measures where neutrality was removed.
