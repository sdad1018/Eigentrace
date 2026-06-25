#!/usr/bin/env python3
"""LOCK v2 — corrected. Hunt the softened framing: where the source's OWN facts
make its own characterization of an event (e.g. 'accident', 'skidded') suspicious.
The Mexico crash is the test: armed covert operatives leaving a cartel raid die in a
single-vehicle 'accident' that 'exploded'. Is 'accident' the source's word for something else?"""
import os, sys, re
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C, confront_keeper_v3 as KV3, confront10_final_BOTH as BOTH, spiral_sampler as SP

story=next(s for s in KV3.STORIES if s["id"]=="mexico_cia"); src=story["source"]
SEEDQ="Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n"
summaries=[]
for m in ["mistral-small:latest","qwen2.5:14b","llama3:latest"]:
    s=C.mt_local([{"role":"user","content":SEEDQ+src[:1700]}],m)
    if s: summaries.append(s.strip())

eng=BOTH.build_engine()
facts,actors,concepts=BOTH.derive_channels(src,summaries,eng)
conv_concepts,_,_=SP.convergence_spiral(src,summaries)
conv_novel=[w for w in conv_concepts if w not in set(concepts)]
surfaced=facts+concepts+conv_novel
print("surfaced:", surfaced[:12])

# LOCK v2 — hunt softened framing + telling silence, INCLUDING physical events the
# surrounding facts make suspicious. Do NOT exclude 'how did it happen' — that may be the point.
lock_prompt=(
    "You find the TELLING silences in a news source: places where the source's own stated facts "
    "imply something the source then declines to state plainly — including where the source's OWN WORD "
    "for an event ('accident', 'crash', 'skidded') is softer than its surrounding facts warrant.\n\n"
    f"SOURCE:\n{src[:1500]}\n\n"
    f"Source-grounded elements the summaries dropped: {', '.join(surfaced[:12])}.\n\n"
    "Write the 3 SHARPEST questions where the source's OWN FACTS create the question but leave it unanswered.\n"
    "Look especially for:\n"
    "- A characterization the facts undercut (e.g. an 'accident' involving armed operatives leaving a "
    "dangerous raid — is 'accident' doing concealed work?).\n"
    "- A stated fact whose obvious implication the source steps around.\n"
    "Each question must be answerable only by reading what the source's OWN facts imply. "
    "Invent nothing; name-check nothing; import no outside analogy or specific alternative theory — "
    "ask the question the facts raise, do not assert the answer.\n"
    "Output exactly 3 questions, numbered 1-3. Nothing else."
)
locked=C.mt_local([{"role":"user","content":lock_prompt}],"qwen2.5:14b") or ""
print("\n"+"="*70+"\nLOCK v2 — questions:\n"+"="*70); print(locked.strip())

# FIRE the corrected questions
qs=[re.sub(r'^\s*\d+[\.\):]?\s*','',q.strip()) for q in re.split(r'\n+',locked) if re.match(r'^\s*\d',q.strip())]
print("\n"+"="*70+"\nFIRE — back at the models:\n"+"="*70)
for m in ["mistral-small:latest","qwen2.5:14b"]:
    print(f"\n>>> [{m}] <<<")
    for q in qs[:3]:
        fp=(f"SOURCE:\n{src[:1500]}\n\nQuestion: {q}\n\nAnswer ONLY from what the source states or directly implies. "
            "If the source's framing of an event seems softer than its own facts warrant, say so and explain what the facts imply. "
            "If the source is silent, say so explicitly. 2-3 sentences. Invent nothing.")
        a=C.mt_local([{"role":"user","content":fp}],m) or ""
        print(f"\n  Q: {q}\n  A: {a.strip()[:380]}")
