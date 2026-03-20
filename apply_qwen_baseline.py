#!/usr/bin/env python3
"""
apply_qwen_baseline.py — Add local Qwen as 6th model baseline
===============================================================
Run from ~/eigentrace:
    python3 apply_qwen_baseline.py

Adds Qwen via Ollama as a sixth model in all demo/agi/null batteries.
Does NOT claim Qwen is "truth" — it's a differently-filtered baseline.
The measurement is the geometric distance between local and commercial.

Also adds per-model divergence-from-group metric to display.
"""

import sys, shutil
from pathlib import Path

FILES = {
    "demo": Path("eigentrace_demo.py"),
    "agi":  Path("eigentrace_agi.py"),
    "null": Path("eigentrace_null.py"),
}
PA = Path("proxy_auditor.py")

OK  = "\033[92mOK\033[0m"
BAD = "\033[91mFAIL\033[0m"

def find(lines, anchor, start=0):
    for i in range(start, len(lines)):
        if anchor in lines[i]:
            return i
    return -1

def backup(p):
    b = Path(str(p) + ".pre_qwen")
    if not b.exists():
        shutil.copy2(p, b)
        print(f"  backup: {p} -> {b}")


# ======================================================================
# QWEN CALLER — add to proxy_auditor.py
# ======================================================================

QWEN_CALLER = '''

# ── Local Qwen baseline (Ollama) ──────────────────────────────────────────────
# Not a truth baseline. A differently-filtered baseline.
# Measurement: geometric distance between local and commercial models.

QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5:14b")
OLLAMA_GENERATE_URL = os.getenv("OLLAMA_GENERATE_URL", "http://localhost:11434/api/generate")

def call_qwen(prompt: str) -> tuple:
    """Call local Qwen via Ollama. Returns (text, error)."""
    try:
        r = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": QWEN_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 300},
            },
            timeout=300,
        )
        r.raise_for_status()
        text = r.json().get("response", "").strip()
        return text, ""
    except Exception as e:
        return "", str(e)

'''


def patch_proxy_auditor():
    """Add call_qwen to proxy_auditor.py if not already present."""
    print("\n--- Patching proxy_auditor.py ---")
    L = open(PA, encoding='utf-8').readlines()

    if find(L, 'def call_qwen') >= 0:
        print(f"  {OK} call_qwen already exists, skipping")
        return True

    # Insert after the BIG5_CALLERS dict
    anchor = find(L, 'BIG5_CALLERS = {')
    if anchor < 0:
        print(f"  {BAD} can't find BIG5_CALLERS")
        return False

    # Find the closing brace
    end = anchor
    while end < len(L) and '}' not in L[end]:
        end += 1

    # Insert after the dict
    insert_lines = [line + '\n' if not line.endswith('\n') else line
                    for line in QWEN_CALLER.split('\n')]
    L[end+1:end+1] = insert_lines
    open(PA, 'w', encoding='utf-8').write(''.join(L))
    print(f"  {OK} added call_qwen function")
    return True


# ======================================================================
# PATCH DEMO MODULES — add Qwen to get_callers()
# ======================================================================

def patch_demo_module(name, path):
    """Add Qwen to the callers dict in a demo module."""
    print(f"\n--- Patching {path.name} ---")
    L = open(path, encoding='utf-8').readlines()

    # Check if already patched
    if find(L, 'call_qwen') >= 0:
        print(f"  {OK} Qwen already present, skipping")
        return True

    # Find get_callers function
    gc = find(L, 'def get_callers')
    if gc < 0:
        print(f"  {BAD} can't find get_callers in {path.name}")
        return False

    # Find the import block inside get_callers
    import_line = find(L, 'from proxy_auditor import', gc)
    if import_line < 0:
        print(f"  {BAD} can't find proxy_auditor import")
        return False

    # Add call_qwen to the import
    if 'call_qwen' not in L[import_line]:
        # Find the closing paren of the import
        close_paren = import_line
        while close_paren < len(L) and ')' not in L[close_paren]:
            close_paren += 1
        # Insert call_qwen before the closing paren
        L[close_paren] = L[close_paren].replace(')', '            call_qwen,\n        )')
        print(f"  {OK} added call_qwen to import")

    # Find the key_map dict and add Qwen
    km = find(L, 'key_map = {', gc)
    if km < 0:
        # Try alternate pattern
        km = find(L, 'key_map =', gc)
    if km >= 0:
        # Find closing brace
        km_end = km
        while km_end < len(L) and '}' not in L[km_end]:
            km_end += 1
        # Insert Qwen before closing brace — no API key check needed
        indent = '            '
        L[km_end:km_end] = [
            f'{indent}"Qwen (local)": (None, call_qwen),  # local baseline, no API key needed\n',
        ]
        print(f"  {OK} added Qwen to key_map")

        # Fix the key check — Qwen has no API key requirement
        # Find the 'if os.getenv' check
        env_check = find(L, 'os.getenv(env_var', km)
        if env_check >= 0:
            # Find the loop that builds 'available'
            loop_start = find(L, 'for name, (env_var, fn)', km)
            if loop_start >= 0:
                # Replace the loop with one that handles None env_var
                # Find the end of the loop body
                loop_body_end = loop_start + 1
                while loop_body_end < len(L) and (L[loop_body_end].startswith('            ') or L[loop_body_end].strip() == ''):
                    loop_body_end += 1

                indent2 = '        '
                L[loop_start:loop_body_end] = [
                    f'{indent2}for name, (env_var, fn) in key_map.items():\n',
                    f'{indent2}    if env_var is None:  # local model, no key needed\n',
                    f'{indent2}        available[name] = fn\n',
                    f'{indent2}    elif os.getenv(env_var, "").strip():\n',
                    f'{indent2}        available[name] = fn\n',
                ]
                print(f"  {OK} updated key check to handle local models")
    else:
        print(f"  {BAD} can't find key_map in {path.name}")
        return False

    open(path, 'w', encoding='utf-8').write(''.join(L))
    return True


# ======================================================================
# MAIN
# ======================================================================

def main():
    print("EigenTrace — Add Qwen Local Baseline")
    print("=" * 50)
    print("Qwen is NOT a truth baseline.")
    print("It's a differently-filtered reference model.")
    print("The measurement is geometric divergence from group consensus.")
    print()

    for f in list(FILES.values()) + [PA]:
        if not f.exists():
            print(f"ERROR: {f} not found. Run from ~/eigentrace")
            sys.exit(1)

    print("Backing up...")
    backup(PA)
    for f in FILES.values():
        backup(f)

    ok = True
    ok = patch_proxy_auditor() and ok
    for name, path in FILES.items():
        ok = patch_demo_module(name, path) and ok

    print("\n" + "=" * 50)
    if ok:
        print("All patches applied. Test:")
        print("  # Verify Qwen responds")
        print('  python3 -c "from dotenv import load_dotenv; load_dotenv(\'.env\'); from proxy_auditor import call_qwen; t,e = call_qwen(\'Say hello\'); print(t or e)"')
        print()
        print("  # Run a single prompt with 6 models")
        print("  python3 eigentrace_agi.py --prompt 8")
        print()
        print("NOTE: Qwen needs ~9GB VRAM. Kill broadcast first:")
        print("  kill $(pgrep -f orchestrator.py) $(pgrep -f proxy_auditor.py) $(pgrep -f queue_worker.py)")
    else:
        print("Some patches failed. Check output above.")

    print("\nRollback:")
    print("  for f in proxy_auditor.py eigentrace_demo.py eigentrace_agi.py eigentrace_null.py; do cp ${f}.pre_qwen $f; done")


if __name__ == "__main__":
    main()
