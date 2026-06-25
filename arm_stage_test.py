#!/usr/bin/env python3
"""Test stage_summary_plus_probe() in isolation, with a constructed results entry
built from the Mexico story. Local-model FIRE (cheap). Proves the production
function runs end-to-end and returns a valid segment dict BEFORE we swap the call."""
import os, sys, re, types
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C, confront_keeper_v3 as KV3
import batch_producer as BP

# --- monkeypatch API_PATIENTS -> local models so FIRE is free for the test ---
# (the stage imports confront10.API_PATIENTS inside FIRE; point those names at local)
def _mk_local(model):
    def _caller(messages):
        out = C.mt_local(messages, model)
        return (out, None)
    return _caller
C.API_PATIENTS = {  # 3 local stand-ins so we see the spectrum behavior
    "ChatGPT": _mk_local("mistral-small:latest"),
    "Claude":  _mk_local("qwen2.5:14b"),
    "Gemini":  _mk_local("llama3:latest"),
}

# --- build a realistic 'results' entry from the Mexico story ---
story = next(s for s in KV3.STORIES if s["id"]=="mexico_cia")
src = story["source"]
# a minimal story object with the attrs the stage reads
StoryObj = types.SimpleNamespace(title="Reported US CIA agents killed in crash not authorised: Mexico",
                                 guid="test-mexico-cia", summary=src, source=src, category="world")
# get real local summaries to populate summary_plus + responses
SEEDQ="Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n"
splus={}; responses=[]
for nm,mdl in [("ChatGPT","mistral-small:latest"),("Claude","qwen2.5:14b"),("Gemini","llama3:latest")]:
    s=C.mt_local([{"role":"user","content":SEEDQ+src[:1700]}],mdl)
    if s:
        splus[nm]=s.strip()
        responses.append(types.SimpleNamespace(name=nm, text=s.strip(), eigen_vix=20.0, error=None, skipped=False))

result = {
    "story": StoryObj,
    "responses": responses,
    "summary_plus": splus,
    "compression": {"verb_downgrade": 0.21, "entity_retention": 0.30, "attribution_buffer": {"total": 4}},
    "source_void": {"absent_ratio": 0.0},
    "geo": types.SimpleNamespace(consensus_density=0.91),
    "_density": 0.91,
}

print("="*70+"\nCALLING stage_summary_plus_probe([mexico_result])...\n"+"="*70)
seg = BP.stage_summary_plus_probe([result])

print("\n"+"="*70+"\nRESULT\n"+"="*70)
if seg is None:
    print("!! returned None — check the log lines above for which gate tripped")
else:
    print(f"segment_type : {seg['segment_type']}")
    print(f"seg id       : {seg['id']}")
    print(f"beats        : {len(seg['beats'])}")
    print(f"sig          : {seg['attribution']['eigenching']['signature']} ({seg['attribution']['eigenching']['name']})")
    print(f"A facts      : {seg['attribution']['channel_A_facts']}")
    print(f"C concepts   : {seg['attribution']['channel_C_concepts']}")
    print(f"spiral-novel : {seg['attribution']['spiral_novel']}")
    print(f"questions    : {seg['attribution']['lock_questions']}")
    print("\n--- beat phases (the segment's spine) ---")
    for b in seg['beats']:
        print(f"  [{b['phase']}] {b['speaker']}: {b['text'][:90]}")
