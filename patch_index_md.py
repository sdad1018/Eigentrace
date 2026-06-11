#!/usr/bin/env python3
"""
patch_index_md.py — corrects docs/index.md: removes retracted 'drop/soften/avoid'
suppression framing, refreshes stale counts, adds links to the two new pages.
Exact-match safe; all-or-nothing. Preserves all existing structure & good content.
"""
import sys, shutil, os

P = "docs/index.md"

EDITS = [
    # 1. The intro suppression framing -> neutral measurement framing
    (
        "intro line",
        "EigenTrace is an autonomous AI observatory that runs consensus geometry across 5 frontier language models on breaking news, 24/7. It measures what models collectively drop, soften, and avoid — using linear algebra on frozen embeddings, not LLM-as-judge.",
        "EigenTrace is an autonomous AI observatory that runs consensus geometry across 5 frontier language models on breaking news, 24/7. It measures how the models diverge — where they agree, where they pull apart, and which concepts sit near a story but absent from all five — using linear algebra on frozen embeddings, not LLM-as-judge.",
    ),
    # 2. Stale counts line
    (
        "stats counts",
        "**17,528** segments measured · **1,141** commits · **17** measurement layers · **5** frontier models · **1** GPU",
        "**22,500+** stories measured · **16** measurement layers · **5** frontier models · **1** GPU · predicts and scores its own findings",
    ),
    # 3. "systematically attenuate" framing in the second What-Is block -> keep but precise
    (
        "deterministic instrument line",
        "EigenTrace is a **deterministic geometric instrument** for measuring what language models systematically attenuate. It runs the same prompt through five frontier models and scores how much each preserves or drops specific elements of the source — using linear algebra on frozen embeddings, not an LLM-as-judge.",
        "EigenTrace is a **deterministic geometric instrument** for measuring how language models diverge in framing the same source. It runs the same prompt through five frontier models and scores, geometrically, how each one's response relates to the source and to the others — using linear algebra on frozen embeddings, not an LLM-as-judge.",
    ),
]

# Add the two new page links into the Key Findings section, after the Anamnesis line.
LINK_ANCHOR = "**→ [Boundary Map](/boundary)** — Live visualization of the alignment boundary across all five frontier models."
LINK_REPLACE = """**→ [How EigenTrace works](/overview)** — The full picture: an instrument that predicts how the five models will diverge *before* reading them, scores whether it was right on air, and audits its own narration against the math.

**→ [The Summary Plus protocol](/summary-plus)** — A deterministic retrieval-and-elaboration segment: surfacing concepts the models converged away from, and observing how they reckon with them. Validated for story-specific signal; faithfulness-tested on hard cases.

**→ [Boundary Map](/boundary)** — Live visualization of the alignment boundary across all five frontier models."""


def main():
    if not os.path.exists(P):
        print("ERROR: " + P + " not found (run from repo root)."); return 1
    src = open(P, encoding="utf-8").read()

    problems = []
    for label, find, _ in EDITS:
        if src.count(find) != 1:
            problems.append(f"  '{label}': found {src.count(find)} (need 1)")
    if src.count(LINK_ANCHOR) != 1:
        problems.append(f"  link anchor (Boundary Map line): found {src.count(LINK_ANCHOR)} (need 1)")
    if "/overview" in src or "/summary-plus" in src:
        problems.append("  already patched (overview/summary-plus links present)")
    if problems:
        print("ABORTING - no changes made:")
        print("\n".join(problems))
        print("(File untouched. The text may differ slightly — paste this and we'll re-anchor.)")
        return 1

    shutil.copy(P, P + ".bak_homepagefix")
    for label, find, repl in EDITS:
        src = src.replace(find, repl)
    src = src.replace(LINK_ANCHOR, LINK_REPLACE)
    open(P, "w", encoding="utf-8").write(src)
    print("index.md corrected:")
    print("  - removed 'drop/soften/avoid' suppression framing (2 spots)")
    print("  - refreshed stale counts (17,528 -> 22,500+, 17 -> 16 layers)")
    print("  - added links to /overview and /summary-plus in Key Findings")
    print("  Backup: " + P + ".bak_homepagefix")
    print("")
    print("NOTE: the entity-swap / Anamnesis claim is KEPT as-is — it's verified and defensible")
    print("      (d=0.471, p=0.0085, null gap 0.0037 vs cross-category 0.0226).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
