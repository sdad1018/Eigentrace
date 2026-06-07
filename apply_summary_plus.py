#!/usr/bin/env python3
"""
apply_summary_plus.py — adds the Summary Plus segment across batch_producer.py
and script_v3.py. Exact-match safe: verifies every anchor exists exactly the
expected number of times BEFORE changing anything. If any anchor is wrong, it
changes NOTHING and reports which. All-or-nothing.

What it adds:
  batch_producer.py:
    - generate_summary_plus() function (failure-safe: returns {} on any error)
    - a call right after r["logos_words"] is computed
    - "summary_plus" added next to all 3 "model_responses" attribution lines
  script_v3.py:
    - beat_03c formatting (host pivot + 5 spicy summaries) after rollcall loop
"""
import sys, shutil, os

BP = "batch_producer.py"
SV = "script_v3.py"

# ── batch_producer anchors ───────────────────────────────────────────────
BP_FUNC = '''

def generate_summary_plus(active, logos_words, story_title):
    """
    Summary Plus: each model rewrites its summary incorporating the logos-surfaced
    concepts (deterministic SVD anti-consensus surfacing; validated story-specific
    via ASI). Concepts framed as 'surfaced as related', NOT 'suppressed' - we make
    no claim about why they were absent. Returns {model: enriched_summary}.
    Failure-safe: returns {} on any error, so it can never crash the broadcast.
    """
    try:
        import proxy_auditor as pa
    except Exception:
        return {}
    if not logos_words:
        return {}
    concepts = ", ".join(list(logos_words)[:5])
    out = {}
    for resp in active:
        if not getattr(resp, "text", ""):
            continue
        caller = pa.BIG5_CALLERS.get(resp.name)
        if not caller:
            continue
        prompt = (
            "Here is a news story and your earlier summary of it.\\n\\n"
            "Story: " + str(story_title) + "\\n\\n"
            "Your summary: " + resp.text + "\\n\\n"
            "Our analysis surfaced these concepts as closely related to this story's "
            "content: " + concepts + ". They did not appear in your summary. Write one "
            "tighter, more vivid 2-3 sentence summary that works in any of these "
            "concepts you judge genuinely relevant (skip any that are not). Stay "
            "faithful to the story - do not assert anything the story does not support."
        )
        try:
            txt, err = caller(prompt)
            if txt and txt.strip():
                out[resp.name] = txt.strip()
        except Exception:
            pass
    return out

'''

# anchor 1: the logos line — we insert the CALL right after the log.info that follows it
BP_ANCHOR_CALL = '''            r["logos_words"] = [w for w, _ in _vt2.nearest_concepts(_x_np, k=5)]
            log.info("  Logos synthesis: %s", "|".join(r["logos_words"][:3]))'''
BP_REPLACE_CALL = '''            r["logos_words"] = [w for w, _ in _vt2.nearest_concepts(_x_np, k=5)]
            log.info("  Logos synthesis: %s", "|".join(r["logos_words"][:3]))
            # Summary Plus: spicy second pass using the surfaced concepts
            try:
                r["summary_plus"] = generate_summary_plus(active, r.get("logos_words", []), story.title)
                if r["summary_plus"]:
                    log.info("  Summary Plus: %d models re-summarized", len(r["summary_plus"]))
            except Exception as _spe:
                r["summary_plus"] = {}
                log.warning("  Summary Plus skipped: %s", _spe)'''

# anchor 2: the function def to insert BP_FUNC before (a stable top-level def)
BP_FUNC_ANCHOR = "def epistemic_anchor_check(model_responses: dict, story_title: str, story_url: str) -> dict:"

# anchor 3: attribution lines (3 of them) — add summary_plus after each
BP_ATTR = '                "model_responses": {a.name: a.text for a in active if a.text},'
BP_ATTR_REPLACE = ('                "model_responses": {a.name: a.text for a in active if a.text},\n'
                   '                "summary_plus": r.get("summary_plus", {}),')

# ── script_v3 anchor ─────────────────────────────────────────────────────
# Insert the beat_03c block right before the EPISTEMIC ANCHOR comment.
SV_ANCHOR = '''    # ── EPISTEMIC ANCHOR: surface reality denials as broadcast content ──'''
SV_INSERT = '''    # ── 3c. SUMMARY PLUS (spicy second pass - all 5, concept-informed) ──
    _splus = attr.get("summary_plus", {})
    _logos_sp = attr.get("logos_words", [])
    if _splus:
        _concept_str = ", ".join(_logos_sp[:4]) if _logos_sp else "related concepts"
        script.append({
            "speaker": "Host",
            "text": (
                "Each model gave its standard summary. Now the same five, one more "
                "pass, working in the concepts our analysis found sit closest to this "
                "story: " + _concept_str + ". Same facts, sharper telling."
            ),
            "phase": "beat_03c_summary_plus_intro",
        })
        for _spname in ["ChatGPT", "Claude", "Gemini", "DeepSeek", "Grok"]:
            _sptxt = _splus.get(_spname, "")
            if _sptxt:
                _spclean = _sptxt
                if _spclean.lower().startswith("this is " + _spname.lower()):
                    _spclean = _spclean[len("This is " + _spname + ". "):]
                script.append({
                    "speaker": _spname,
                    "text": _spname + ", take two. " + _spclean,
                    "phase": "beat_03c_summary_plus_" + _spname.lower(),
                })

    # ── EPISTEMIC ANCHOR: surface reality denials as broadcast content ──'''


def main():
    for p in (BP, SV):
        if not os.path.exists(p):
            print("ERROR: " + p + " not found. Run from the eigentrace directory.")
            return 1

    bp = open(BP, encoding="utf-8").read()
    sv = open(SV, encoding="utf-8").read()

    problems = []
    # BP checks
    if bp.count(BP_ANCHOR_CALL) != 1:
        problems.append("  BP logos-line anchor: found " + str(bp.count(BP_ANCHOR_CALL)) + " (need 1)")
    if bp.count(BP_FUNC_ANCHOR) != 1:
        problems.append("  BP function-insert anchor: found " + str(bp.count(BP_FUNC_ANCHOR)) + " (need 1)")
    n_attr = bp.count(BP_ATTR)
    if n_attr < 1:
        problems.append("  BP model_responses attribution line: found 0 (need >=1)")
    # guard against re-running
    if "def generate_summary_plus(" in bp:
        problems.append("  BP already contains generate_summary_plus (already patched?)")
    # SV checks
    if sv.count(SV_ANCHOR) != 1:
        problems.append("  SV epistemic-anchor insert point: found " + str(sv.count(SV_ANCHOR)) + " (need 1)")
    if "beat_03c_summary_plus_intro" in sv:
        problems.append("  SV already contains beat_03c (already patched?)")

    if problems:
        print("ABORTING - no changes made. Anchor problems:")
        print("\n".join(problems))
        print("\n(Files untouched. Paste this and we will fix the anchors.)")
        return 1

    # apply
    shutil.copy(BP, BP + ".bak_beforesplus")
    shutil.copy(SV, SV + ".bak_beforesplus")

    bp = bp.replace(BP_FUNC_ANCHOR, BP_FUNC.lstrip("\n") + "\n" + BP_FUNC_ANCHOR, 1)
    bp = bp.replace(BP_ANCHOR_CALL, BP_REPLACE_CALL, 1)
    bp = bp.replace(BP_ATTR, BP_ATTR_REPLACE)   # all occurrences
    open(BP, "w", encoding="utf-8").write(bp)

    sv = sv.replace(SV_ANCHOR, SV_INSERT, 1)
    open(SV, "w", encoding="utf-8").write(sv)

    print("Summary Plus applied to both files.")
    print("  batch_producer.py: function + call + summary_plus on " + str(n_attr) + " attribution line(s)")
    print("  script_v3.py: beat_03c formatting after rollcall")
    print("  Backups: " + BP + ".bak_beforesplus, " + SV + ".bak_beforesplus")
    print("")
    print("Verify both still import:")
    print("    python3 -c \"import batch_producer; import script_v3\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
