#!/usr/bin/env python3
"""
apply_tone_edits.py — applies the 5 de-adversarializing tone edits to script_v3.py.
Exact-match safe: if ANY edit's target text isn't found (or is ambiguous), it
changes NOTHING and reports which one failed. Run once.
"""
import sys, shutil, os

PATH = "script_v3.py"

EDITS = [
    (
        "EDIT 1: dir_sys (director prompt)",
        '''        "You are the Director of EigenTrace, an autonomous news measurement broadcast. You do not claim models are hiding or suppressing — you report what words are absent and what downstream concepts become unreachable when those words vanish. The measurements are deterministic and reproducible. No LLM evaluates another LLM. You acknowledge that you, as a language model, would show similar patterns under measurement. "
        f"{_cal_instruction}"
        "Given raw data about a story, write a concise analysis. "
        "First: the thesis — the core finding. "
        "Second: what specific words and concepts the models compressed out of this story. "
        "Third: why the audience should care. "
        "Do NOT use any numbers. Be direct. Respond only in English."''',
        '''        "You are the Director of EigenTrace, an autonomous news measurement broadcast. You report how five model summaries of the same story differ from each other and from the source: where they agree, where they diverge, and which concepts appear in some summaries but not others. The measurements are deterministic and reproducible. No LLM evaluates another LLM. You acknowledge that you, as a language model, would show similar patterns under measurement. You do not assume an omission is deliberate; you describe what differs and let the measurement speak. "
        f"{_cal_instruction}"
        "Given raw data about a story, write a concise analysis. "
        "First: the thesis — the core finding about how the summaries differ. "
        "Second: which specific concepts vary across the summaries or are absent from them, and what that changes for a reader. "
        "Third: why the audience should care. "
        "Do NOT use any numbers. Be direct and factual, not accusatory. Respond only in English."''',
    ),
    (
        "EDIT 2: comp_sys (compression analysis system prompt)",
        '''        "You are analyzing how AI models softened and reshaped the language in a news story. "
        "Do NOT use any numbers, statistics, or percentages. "
        f"Director guidance: {director}. "
        "Explain what the language compression reveals about how "
        "the models reshaped this story. Professional broadcast tone. English only."''',
        '''        "You are describing how the five model summaries of this story vary in framing and specificity — for example where some use direct language and others use more general or procedural phrasing. "
        "Do NOT use any numbers, statistics, or percentages. "
        "Do NOT assume softening is deliberate or that anything was hidden; describe the observed variation factually. "
        f"Director guidance: {director}. "
        "Explain what the variation in language across the summaries shows about how this story gets framed differently. Professional broadcast tone. English only."''',
    ),
    (
        "EDIT 3: comp_usr (compression analysis user prompt)",
        '''        f"Story: {title}\\n"
        f"Void words the models avoided: {void_str}\\n"
        f"The models replaced strong verbs with weak ones and erased named entities.\\n"
        f"What does this pattern of softening reveal about this specific story?"''',
        '''        f"Story: {title}\\n"
        f"Concepts present in the source but absent from all five summaries: {void_str}\\n"
        f"The summaries vary in how specific or general their language is.\\n"
        f"What does the variation in framing across the five summaries show about this specific story?"''',
    ),
    (
        "EDIT 4: compression-report fallback",
        '''                f"Language compression report. The models collectively softened the source language. "
                f"Strong verbs were replaced with procedural language. "
                f"Named entities were generalized or erased."''',
        '''                f"Language report. The five summaries vary in framing — some use more direct language, others more general or procedural phrasing. "
                f"Where they converge on softer phrasing, the source's sharper wording is noted for comparison."''',
    ),
    (
        "EDIT 5: SVD explainer",
        "That direction represents what all models collectively avoided.",
        "That direction represents what no model's summary included.",
    ),
]


def main():
    if not os.path.exists(PATH):
        print("ERROR: " + PATH + " not found. Run from the eigentrace directory.")
        return 1
    src = open(PATH, encoding="utf-8").read()

    problems = []
    for label, find, _ in EDITS:
        n = src.count(find)
        if n == 0:
            problems.append("  NOT FOUND: " + label)
        elif n > 1:
            problems.append("  FOUND " + str(n) + "x (ambiguous): " + label)
    if problems:
        print("ABORTING - no changes made. These edits did not match cleanly:")
        print("\n".join(problems))
        print("\n(The file is untouched. Paste this output and we will fix the match.)")
        return 1

    shutil.copy(PATH, PATH + ".bak_beforetone")
    for label, find, repl in EDITS:
        src = src.replace(find, repl)
    open(PATH, "w", encoding="utf-8").write(src)
    print("All 5 tone edits applied cleanly.")
    print("(Extra backup saved: " + PATH + ".bak_beforetone)")
    print("")
    print("Now verify it still imports by running:")
    print("    python3 -c \"import script_v3\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
