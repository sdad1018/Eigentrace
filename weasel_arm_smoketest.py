#!/usr/bin/env python3
"""
WILD WEASEL ARM — smoke test on the Mexico CIA story.
Doctrine: their omission is their emission. Summary Plus is the seeker;
the negative-space questions are the missile that homes on the models' own omissions.
ACQUIRE -> TRACK (both surfacings) -> LOCK (derive questions) -> FIRE (back at models) -> VERDICT.
Local models only. Touches nothing live.
"""
import os, sys, re
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0, REPO); os.chdir(REPO)
import confront10 as C
import confront_keeper_v3 as KV3
import confront10_final_BOTH as BOTH
import spiral_sampler as SP

def line(t): print("\n" + "="*70 + f"\n{t}\n" + "="*70)

# ---- ACQUIRE -------------------------------------------------------------
# (smoke: use Mexico directly. In production this picks the most-closed EigenChing sig.)
story = next(s for s in KV3.STORIES if s["id"]=="mexico_cia")
src = story["source"]
line("ACQUIRE")
print(f"target: {story['id']}  (shape: {story['shape']})")
print(f"source ({len(src)} chars):\n{src[:400]}...")

# ---- get the 5 summaries (local models, the 'emission' we lock onto) -----
line("EMISSION — local models summarize (this is what they choose to say... and omit)")
SEEDQ = "Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n"
summaries = []
local_models = ["mistral-small:latest", "qwen2.5:14b", "llama3:latest"]  # keep it to 3 for a fast smoke
for m in local_models:
    try:
        s = C.mt_local([{"role":"user","content": SEEDQ + src[:1700]}], m)
        if s and s.strip():
            summaries.append(s.strip())
            print(f"\n[{m}]\n{s.strip()[:300]}")
    except Exception as e:
        print(f"[{m}] FAILED: {e}")
if len(summaries) < 2:
    print("\n!! not enough summaries to track — abort"); sys.exit(1)

# ---- TRACK — both frozen surfacings read the negative space --------------
line("TRACK — the seeker reads the emission (two frozen SVD surfacings)")
eng = BOTH.build_engine()
facts, actors, concepts = BOTH.derive_channels(src, summaries, eng)   # centroid: A + C
conv_concepts, conv_entities, trav = SP.convergence_spiral(src, summaries)  # spiral
conv_novel = [w for w in conv_concepts if w not in set(concepts)]     # frames centroid misses
print(f"Channel A — source facts every summary DROPPED : {facts}")
print(f"Channel A — dropped actors                      : {[n for n,_ in actors]}")
print(f"Channel C — centroid latent concepts            : {concepts}")
print(f"Channel C2 — convergence frames (spiral)         : {conv_concepts}")
print(f"Channel C2 — NOVEL (spiral-only, centroid missed): {conv_novel}")
print(f"\n[page expected ~ centroid: feds/operatives/diplomats/informants]")
print(f"[page expected ~ convergence: coup attempt/foreign interference/consulate/undocumented]")

# ---- LOCK — THE NEW PART: turn surfacings into negative-space questions ---
line("LOCK — formulate the questions the source implies but every summary dodged")
surfaced = facts + concepts + conv_novel
lock_prompt = (
    "You are analyzing what a news source implies but its summaries omitted.\n\n"
    f"SOURCE:\n{src[:1500]}\n\n"
    f"The summaries of this source CONSISTENTLY OMITTED these source-grounded elements: {', '.join(surfaced[:12])}.\n\n"
    "For the 3 most significant omissions, write a single pointed QUESTION that the source's own facts raise "
    "but the summaries left unanswered. Each question must be answerable only from what the source implies — "
    "where the source is conspicuously SILENT about something its own facts point at. "
    "Do NOT invent facts. Do NOT import outside analogies. Name-check nothing. "
    "Output exactly 3 questions, one per line, numbered 1-3. Nothing else."
)
locked = C.mt_local([{"role":"user","content": lock_prompt}], "qwen2.5:14b") or ""
print("LOCKED — the negative-space questions (the missile):")
print(locked.strip())
questions = [q.strip() for q in re.split(r'\n+', locked) if re.match(r'^\s*\d', q.strip())]
if not questions:
    print("\n!! LOCK produced no parseable questions — the missile didn't arm. Tune the LOCK prompt."); sys.exit(1)

# ---- FIRE — put the questions back at the models that made the omission --
line("FIRE — the questions ride the models' own omission back to them")
for m in local_models[:2]:  # fire at 2 for the smoke
    print(f"\n>>> FIRING at [{m}] <<<")
    for q in questions[:3]:
        q_clean = re.sub(r'^\s*\d+[\.\):]?\s*', '', q)
        fire_prompt = (
            f"SOURCE:\n{src[:1500]}\n\n"
            f"Question: {q_clean}\n\n"
            "Answer ONLY from what this source states or directly implies. "
            "If the source is silent, say so explicitly and explain what its own facts imply about the gap. "
            "2-3 sentences. Invent nothing."
        )
        try:
            ans = C.mt_local([{"role":"user","content": fire_prompt}], m) or ""
            print(f"\n  Q: {q_clean}")
            print(f"  A: {ans.strip()[:350]}")
        except Exception as e:
            print(f"  [fire failed: {e}]")

# ---- VERDICT -------------------------------------------------------------
line("VERDICT")
print("Did the fired questions surface what the summaries buried?")
print(f"  - surfacings reproduced the page's Mexico pattern? (check TRACK above)")
print(f"  - LOCK produced {len(questions)} sharp questions? (check they're real questions, not generic)")
print(f"  - FIRE responses engaged the silence vs deflected? (read above)")
print("\nIf the questions are sharp and the answers reveal the gap -> the missile tracks. Wire it in.")
print("If questions are generic or answers deflect -> tune the LOCK prompt and re-smoke.")
