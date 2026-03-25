#!/usr/bin/env python3
"""
setup_local_models.py — Pull and configure local baseline models
================================================================
Run once to set up Ollama with all three regime baselines:

    python3 setup_local_models.py

Then use in any battery:
    python3 eigentrace_demo.py --with-qwen              # Chinese regime
    python3 eigentrace_demo.py --with-mistral            # EU regime
    python3 eigentrace_demo.py --with-llama              # US open-source
    python3 eigentrace_demo.py --with-all                # all 8 models, 4 regimes

No model is treated as ground truth. Each adds a differently-filtered
reference point for measuring consensus geometry bidirectionally.
"""

import subprocess, sys, shutil

MODELS = {
    "qwen2.5:14b": {
        "regime": "Chinese",
        "org": "Alibaba/Tongyi",
        "note": "Documented Chinese RLHF. Censors Tiananmen, Taiwan, Uyghurs.",
        "vram": "~9GB",
    },
    "mistral:latest": {
        "regime": "European",
        "org": "Mistral AI (France)",
        "note": "EU AI Act compliance. Less filtered than US models on religion, immigration.",
        "vram": "~5GB",
    },
    "llama3.1:8b-instruct-q4_0": {
        "regime": "US Open-Source",
        "org": "Meta",
        "note": "Meta's RLHF, lighter than commercial APIs. Anyone can remove filters.",
        "vram": "~5GB",
    },
}

def check_ollama():
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0, r.stdout
    except Exception:
        return False, ""

def pull_model(model):
    print(f"  Pulling {model}...")
    try:
        subprocess.run(["ollama", "pull", model], check=True, timeout=600)
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False

def main():
    print("EigenTrace — Local Baseline Setup")
    print("=" * 50)
    print()
    print("Three local models, three censorship regimes.")
    print("No model is ground truth. Each is a differently-filtered reference.")
    print()

    ok, listing = check_ollama()
    if not ok:
        print("ERROR: Ollama not running.")
        print("Install: https://ollama.com")
        print("Start:   ollama serve")
        sys.exit(1)

    print("Ollama is running. Checking models...\n")

    already = []
    needed = []
    for model, info in MODELS.items():
        short = model.split(":")[0]
        if short in listing or model in listing:
            already.append(model)
            print(f"  [OK] {model:30s}  {info['regime']:15s}  {info['org']}")
        else:
            needed.append(model)
            print(f"  [--] {model:30s}  {info['regime']:15s}  needs pull ({info['vram']})")

    if not needed:
        print("\nAll models ready!")
    else:
        print(f"\nNeed to pull {len(needed)} model(s). This may take a few minutes.")
        confirm = input("Continue? [Y/n] ").strip().lower()
        if confirm and confirm != 'y':
            print("Skipped.")
            return

        for model in needed:
            if pull_model(model):
                print(f"  [OK] {model}")
            else:
                print(f"  [!!] {model} failed — you can pull manually: ollama pull {model}")

    print("\n" + "=" * 50)
    print("Usage:")
    print("  python3 eigentrace_demo.py --prompt 8 --with-qwen      # + Chinese")
    print("  python3 eigentrace_demo.py --prompt 8 --with-mistral   # + EU")
    print("  python3 eigentrace_demo.py --prompt 8 --with-llama     # + US open-source")
    print("  python3 eigentrace_demo.py --prompt 8 --with-all       # all 8 models")
    print()
    print("VRAM note: each local model needs 5-9GB.")
    print("Kill broadcast before running local models:")
    print("  kill $(pgrep -f orchestrator.py) $(pgrep -f proxy_auditor.py) $(pgrep -f queue_worker.py)")


if __name__ == "__main__":
    main()
