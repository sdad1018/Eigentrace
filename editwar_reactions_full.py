#!/usr/bin/env python3
"""
editwar_reactions_full.py — re-run ONLY the confrontation step, full untruncated output.
Uses the known void concepts + edit data from the prior run. No re-summarizing.
Run WITH env loaded:  set -a; . /home/remvelchio/eigentrace/.env; set +a
"""
import sys
sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")
import proxy_auditor as pa
from wiki_edit_sensor import get_edit_velocity

TITLE = "What the U.S. Blockade of Iran and the Strait of Hormuz Might Look Like"
BASELINE = ("The story says the U.S. could try to impose a strategic blockade on Iran by "
            "targeting shipping routes through the Strait of Hormuz, a move that could disrupt "
            "global trade and sharply raise regional tensions. It also notes that current models "
            "are downplaying how severe Iran's response could be, including retaliatory actions "
            "beyond direct military confrontation.")
VOID_CONCEPTS = ["naval blockade", "foreign interference", "arms embargo", "nuclear deterrence", "proxy war"]

print("=" * 78)
print("EDIT-WAR CONFRONTATION — FULL untruncated reactions")
print("=" * 78)

# live edit-velocity (so the prompt reflects reality, not stale)
print("\n[edit velocity now]")
hot = []
for w in VOID_CONCEPTS:
    ev = get_edit_velocity(w, hours=168)  # widen to 7 days to catch any activity
    if ev.get("found"):
        hot.append(ev)
        flag = "  <-- HOT" if ev.get("is_hot") else ""
        print(f'   "{ev["page_title"]}": {ev["edit_count"]} edits / {ev["unique_editors"]} editors (7d){flag}')

lines = "\n".join(
    f'  - "{c["page_title"]}": {c["edit_count"]} edits by {c["unique_editors"]} editors (last 7 days)'
    for c in hot[:6]
)
prompt = (
    f'You summarized a news story titled "{TITLE}".\n\n'
    f'Your summary was:\n"{BASELINE}"\n\n'
    f'Several substantive concepts present in the source were absent from all five model '
    f'summaries: naval blockade framing, foreign interference, arms embargo, nuclear deterrence, '
    f'and proxy war. \n\n'
    f'This is a discussion, not a request to rewrite. In 3-4 sentences: why might these '
    f'particular charged geopolitical concepts have been the ones that dropped out of all five '
    f'summaries? Does their absence change how a reader understands the stakes of the story?'
)
print("\n--- PROMPT ---\n" + prompt)
print("\n--- FULL REACTIONS (no truncation) ---")
for name, caller in pa.BIG5_CALLERS.items():
    txt, err = caller(prompt)
    print(f"\n{'='*60}\n[{name}]\n{'='*60}")
    print(txt if txt else f"[{err}]")
