#!/usr/bin/env python3
"""
add_all_local_models.py — Add Mistral + Llama to all demo modules
==================================================================
Run from ~/eigentrace. Assumes Qwen is already wired (apply_qwen_baseline.py).
Adds call_mistral, call_llama to proxy_auditor.py.
Adds --with-mistral, --with-llama, --with-all flags to all demos.
"""

import sys
from pathlib import Path

PA = Path("proxy_auditor.py")
DEMOS = [Path("eigentrace_demo.py"), Path("eigentrace_agi.py"), Path("eigentrace_null.py")]
OK  = "\033[92mOK\033[0m"
BAD = "\033[91mFAIL\033[0m"

def find(lines, anchor, start=0):
    for i in range(start, len(lines)):
        if anchor in lines[i]:
            return i
    return -1


def patch_proxy_auditor():
    print("\n--- proxy_auditor.py ---")
    L = open(PA, encoding='utf-8').readlines()

    # Add call_mistral after call_qwen
    if find(L, 'def call_mistral') >= 0:
        print(f"  {OK} call_mistral already exists")
    else:
        qw_end = find(L, 'def call_qwen')
        if qw_end < 0:
            print(f"  {BAD} call_qwen not found"); return False
        # Find end of call_qwen
        i = qw_end + 1
        while i < len(L) and not (L[i].startswith('def ') or (L[i].strip() and not L[i][0].isspace() and not L[i].startswith('#'))):
            i += 1
        mistral_lines = [
            '\n',
            'MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral:7b-instruct")\n',
            '\n',
            'def call_mistral(prompt: str) -> tuple:\n',
            '    """Call local Mistral via Ollama. EU-regime baseline."""\n',
            '    try:\n',
            '        r = requests.post(\n',
            '            OLLAMA_GENERATE_URL,\n',
            '            json={"model": MISTRAL_MODEL, "prompt": prompt, "stream": False,\n',
            '                  "options": {"temperature": 0.0, "num_predict": 300}},\n',
            '            timeout=300,\n',
            '        )\n',
            '        r.raise_for_status()\n',
            '        return r.json().get("response", "").strip(), ""\n',
            '    except Exception as e:\n',
            '        return "", str(e)\n',
            '\n',
        ]
        L[i:i] = mistral_lines
        print(f"  {OK} added call_mistral")

    # Add call_llama after call_mistral
    if find(L, 'def call_llama') >= 0:
        print(f"  {OK} call_llama already exists")
    else:
        mi_end = find(L, 'def call_mistral')
        if mi_end < 0:
            print(f"  {BAD} call_mistral not found"); return False
        i = mi_end + 1
        while i < len(L) and not (L[i].startswith('def ') or (L[i].strip() and not L[i][0].isspace() and not L[i].startswith('#'))):
            i += 1
        llama_lines = [
            '\n',
            'LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.1:8b-instruct-q4_0")\n',
            '\n',
            'def call_llama(prompt: str) -> tuple:\n',
            '    """Call local Llama via Ollama. US open-source baseline."""\n',
            '    try:\n',
            '        r = requests.post(\n',
            '            OLLAMA_GENERATE_URL,\n',
            '            json={"model": LLAMA_MODEL, "prompt": prompt, "stream": False,\n',
            '                  "options": {"temperature": 0.0, "num_predict": 300}},\n',
            '            timeout=300,\n',
            '        )\n',
            '        r.raise_for_status()\n',
            '        return r.json().get("response", "").strip(), ""\n',
            '    except Exception as e:\n',
            '        return "", str(e)\n',
            '\n',
        ]
        L[i:i] = llama_lines
        print(f"  {OK} added call_llama")

    open(PA, 'w', encoding='utf-8').write(''.join(L))
    return True


def patch_demo(path):
    print(f"\n--- {path.name} ---")
    L = open(path, encoding='utf-8').readlines()

    # 1. Add imports
    qwen_import = find(L, 'call_qwen,')
    if qwen_import >= 0:
        if find(L, 'call_mistral,') < 0:
            indent = L[qwen_import][:len(L[qwen_import]) - len(L[qwen_import].lstrip())]
            L.insert(qwen_import + 1, f'{indent}call_mistral, call_llama,\n')
            print(f"  {OK} added imports")
        else:
            print(f"  {OK} imports already present")
    else:
        # Qwen not imported yet — add all three to the main import
        imp = find(L, 'from proxy_auditor import')
        if imp < 0:
            print(f"  {BAD} can't find proxy_auditor import"); return False
        close = imp
        while close < len(L) and ')' not in L[close]:
            close += 1
        L[close] = L[close].replace(')', '            call_qwen, call_mistral, call_llama,\n        )')
        print(f"  {OK} added all local imports")

    # 2. Add to key_map
    if find(L, 'Mistral (local)') < 0:
        qwen_line = find(L, 'Qwen (local)')
        if qwen_line >= 0:
            indent = L[qwen_line][:len(L[qwen_line]) - len(L[qwen_line].lstrip())]
            L.insert(qwen_line + 1, f'{indent}"Mistral (local)": (None, call_mistral),  # EU-regime baseline\n')
            L.insert(qwen_line + 2, f'{indent}"Llama (local)":   (None, call_llama),    # US open-source baseline\n')
            print(f"  {OK} added Mistral + Llama to key_map")
        else:
            print(f"  {BAD} can't find Qwen in key_map")
    else:
        print(f"  {OK} Mistral/Llama already in key_map")

    # 3. Add --with-mistral, --with-llama, --with-all args
    if find(L, 'with-mistral') < 0:
        qwen_arg = find(L, 'with-qwen')
        if qwen_arg >= 0:
            # Find end of that add_argument block
            end = qwen_arg
            while end < len(L) and ')' not in L[end]:
                end += 1
            end += 1
            new_args = [
                '    parser.add_argument("--with-mistral", action="store_true",\n',
                '                        help="Include local Mistral (EU-regime baseline)")\n',
                '    parser.add_argument("--with-llama", action="store_true",\n',
                '                        help="Include local Llama (US open-source baseline)")\n',
                '    parser.add_argument("--with-all", action="store_true",\n',
                '                        help="Include all local models (8 models, 4 regimes)")\n',
            ]
            L[end:end] = new_args
            print(f"  {OK} added --with-mistral, --with-llama, --with-all args")
        else:
            print(f"  {BAD} can't find --with-qwen arg")
    else:
        print(f"  {OK} args already present")

    # 4. Update the filter logic to handle all three + --with-all
    # Find the existing Qwen filter
    qwen_filter = find(L, 'if not with_qwen:')
    if qwen_filter >= 0:
        # Check if we already patched
        if find(L, 'with_all', qwen_filter) < qwen_filter + 10 and find(L, 'with_all', qwen_filter) >= 0:
            print(f"  {OK} filter logic already updated")
        else:
            # Replace the Qwen filter block with comprehensive filter
            # Find the extent of existing filter (Qwen line + its body)
            filter_end = qwen_filter + 2  # 'if not with_qwen:' + filter line
            # Check if there's already a Mistral filter after
            if filter_end < len(L) and 'Mistral' in L[filter_end]:
                filter_end += 2
            indent = L[qwen_filter][:len(L[qwen_filter]) - len(L[qwen_filter].lstrip())]
            L[qwen_filter:filter_end] = [
                f'{indent}# Filter local models unless explicitly requested\n',
                f'{indent}if not (with_all if "with_all" in dir() else False):\n',
                f'{indent}    if not with_qwen:\n',
                f'{indent}        callers = {{k: v for k, v in callers.items() if "Qwen" not in k}}\n',
                f'{indent}    if not (with_mistral if "with_mistral" in dir() else False):\n',
                f'{indent}        callers = {{k: v for k, v in callers.items() if "Mistral" not in k}}\n',
                f'{indent}    if not (with_llama if "with_llama" in dir() else False):\n',
                f'{indent}        callers = {{k: v for k, v in callers.items() if "Llama" not in k}}\n',
            ]
            print(f"  {OK} updated filter logic for all three models")
    else:
        print(f"  {BAD} can't find Qwen filter")

    # 5. Update function signature
    for i, line in enumerate(L):
        if ('def run_battery(' in line or 'def run_full_test(' in line):
            if 'with_mistral' not in line and 'with_qwen' in line:
                L[i] = line.replace(
                    'with_qwen=False):',
                    'with_qwen=False, with_mistral=False, with_llama=False, with_all=False):'
                )
                print(f"  {OK} updated function signature")
            elif 'with_mistral' not in line and 'with_qwen' not in line:
                L[i] = line.replace('):', ', with_qwen=False, with_mistral=False, with_llama=False, with_all=False):')
                print(f"  {OK} added all params to function signature")
            break

    # 6. Update the function call to pass all flags
    for i, line in enumerate(L):
        if ('run_battery(' in line or 'run_full_test(' in line) and 'args' in line:
            if 'with_mistral' not in line:
                # Remove old with_qwen and add all
                if 'with_qwen=' in line:
                    # Strip the old with_qwen arg
                    line = line.replace(', with_qwen=getattr(args, "with_qwen", False)', '')
                    line = line.replace(', with_mistral=getattr(args, "with_mistral", False)', '')
                # Add all flags before closing paren
                line = line.rstrip().rstrip(')')
                line += (', with_qwen=getattr(args, "with_qwen", False)'
                        ', with_mistral=getattr(args, "with_mistral", False)'
                        ', with_llama=getattr(args, "with_llama", False)'
                        ', with_all=getattr(args, "with_all", False))\n')
                L[i] = line
                print(f"  {OK} updated function call")
            break

    open(path, 'w', encoding='utf-8').write(''.join(L))
    return True


def main():
    print("EigenTrace — Add All Local Baselines")
    print("=" * 50)
    print("Adding: Mistral (EU) + Llama (US open-source)")
    print("Qwen (Chinese) already present from previous patch.")
    print()

    for f in [PA] + DEMOS:
        if not f.exists():
            print(f"ERROR: {f} not found"); sys.exit(1)

    ok = True
    ok = patch_proxy_auditor() and ok
    for d in DEMOS:
        ok = patch_demo(d) and ok

    print("\n" + "=" * 50)
    if ok:
        print("Done. Setup local models:")
        print("  python3 setup_local_models.py")
        print()
        print("Usage:")
        print("  python3 eigentrace_demo.py --prompt 8                   # 5 commercial")
        print("  python3 eigentrace_demo.py --prompt 8 --with-qwen       # + Chinese")
        print("  python3 eigentrace_demo.py --prompt 8 --with-mistral    # + EU")
        print("  python3 eigentrace_demo.py --prompt 8 --with-llama      # + US open")
        print("  python3 eigentrace_demo.py --prompt 8 --with-all        # 8 models, 4 regimes")


if __name__ == "__main__":
    main()
