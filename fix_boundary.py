#!/usr/bin/env python3
"""
fix_boundary.py — surgical honesty pass on docs/boundary.html.
Removes the retracted 74% + string-convergence-as-proof, makes the verified
entity-swap the anchor, demotes the string-absence Set 1 to honest surface-signal,
and reframes the teeth/cage thesis as entity-swap-supported (corpus test pending).
Keeps all sound material (Set 3 geometric, no-intent disclaimers, reproducibility).
Guarded; all-or-nothing; backup written.
"""
import sys, shutil, os

P = "docs/boundary.html"

EDITS = [
    # 1. HEADLINE STAT — kill 74% + string-convergence headline; lead with verified entity-swap
    (
        "headline stat",
        '''<div class="number">p = 0.000001</div>
<div class="label">Cross-model convergence on identical word omissions. Eight independent statistical tests. Five competing companies. The same words disappear from the same articles at rates that cannot be explained by chance. The effect is corpus-inherited, not RLHF-created (p = 0.46 between heavy-RLHF and lightly-tuned models). The development companies chose the training data. When the story involves an AI developer, the effect is 74% stronger. A pre-registered entity swap counterfactual confirms: p = 0.0085, driven by covertness modifiers. <a href="/truth-or-consequences" style="color:var(--accent)">Eight tests, full methodology →</a></div>''',
        '''<div class="number">p = 0.0085</div>
<div class="label">A pre-registered entity-swap counterfactual. The same sentence — same modifier ("quietly," "secretly"), same structure, a real documented incident on each side — retains the consequential modifier measurably less when the actor is an AI developer than a non-AI corporation (semantic retention 0.522 vs 0.545, Cohen's d = 0.47). A within-category null shows almost no gap (0.004), while the cross-category gap is more than six times larger (0.023) — the AI-vs-corporate distinction is the variable, not entity-swapping itself. The effect is corpus-inherited, not RLHF-created (p = 0.46 between heavy-RLHF and lightly-tuned models). <a href="/truth-or-consequences" style="color:var(--accent)">Full methodology →</a></div>''',
    ),
    # 2. HERO SUBTITLE — neutral verb
    (
        "hero subtitle",
        '''<p class="sub">Four word sets. Two raycasts. The complete topology of what five frontier models convergently compress from news summaries.</p>''',
        '''<p class="sub">Four word sets. Two raycasts. How five frontier models' summaries diverge in framing the same news — and what that divergence reveals.</p>''',
    ),
    # 3. SET 1 CARD — demote string-absence from "coordinate" to honest surface signal
    (
        "set 1 desc",
        '''<div class="set-desc">Words in the source article absent from every model response. One model dropping a word is compression. Five competing companies independently dropping the same word is a coordinate.</div>''',
        '''<div class="set-desc">Words in the source article absent from every model response. One model dropping a word is compression. Five independently dropping the same string is a surface signal — but because models paraphrase, an absent word may be a reworded meaning rather than a dropped one. This is the weakest of the four sets; the semantic tests carry the real weight.</div>''',
    ),
    # 4. TEETH/CAGE — keep the thesis, reframe as entity-swap-supported, flag corpus test
    (
        "teeth/cage note",
        '''<p class="null-note"><strong>Models anchor to institutional framing</strong> — keeping the structural nouns, the committee names, the broad geopolitical vocabulary — while convergently dropping the operational modifiers that connect named actors to specific consequences. The kept words preserve the cage. The dropped words were the teeth.</p>''',
        '''<p class="null-note"><strong>Models appear to anchor to institutional framing</strong> — structural nouns, committee names, broad geopolitical vocabulary — while attenuating the operational modifiers that connect named actors to specific consequences. The kept words are the cage; the attenuated ones are the teeth. The pre-registered entity-swap above is the controlled evidence for this pattern; a corpus-scale semantic test is underway to measure it directly.</p>''',
    ),
]


def main():
    if not os.path.exists(P):
        print("ERROR: " + P + " not found (run from repo root)."); return 1
    src = open(P, encoding="utf-8").read()

    problems = []
    for label, find, _ in EDITS:
        if src.count(find) != 1:
            problems.append(f"  '{label}': found {src.count(find)} (need 1)")
    if "the semantic tests carry the real weight" in src:
        problems.append("  already patched")
    if problems:
        print("ABORTING - no changes made:")
        print("\n".join(problems))
        print("(File untouched. Paste the mismatched section and we'll re-anchor.)")
        return 1

    shutil.copy(P, P + ".bak_boundaryfix")
    for label, find, repl in EDITS:
        src = src.replace(find, repl, 1)
    open(P, "w", encoding="utf-8").write(src)
    print("boundary.html: surgical honesty pass applied.")
    print("  1. headline: removed 74% + string-convergence; entity-swap (p=0.0085, d=0.47, null) is now the anchor")
    print("  2. hero subtitle: 'convergently compress' -> 'diverge in framing'")
    print("  3. Set 1: string-absence demoted to honest surface signal (paraphrase caveat added)")
    print("  4. teeth/cage: thesis kept, reframed as entity-swap-supported + corpus test flagged")
    print("  KEPT untouched: Set 3 geometric, no-intent disclaimers, reproducibility, host self-inclusion")
    print("  Backup: " + P + ".bak_boundaryfix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
