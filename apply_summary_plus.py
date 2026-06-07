#!/usr/bin/env python3
"""
apply_summary_plus.py (v2) — corrected for the double-spaced batch_producer.py.
Exact-match safe: verifies anchors before changing anything; all-or-nothing.
"""
import sys, shutil, os

BP = "batch_producer.py"
SV = "script_v3.py"

BP_FUNC = '''def generate_summary_plus(active, logos_words, story_title):
    """
    Summary Plus: each model rewrites its summary incorporating the logos-surfaced
    concepts (deterministic SVD anti-consensus surfacing; validated story-specific
    via ASI). Concepts framed as 'surfaced as related', NOT 'suppressed'. Returns
    {model: enriched_summary}. Failure-safe: returns {} on any error.
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

# function insert anchor (top-level def, confirmed unique earlier)
BP_FUNC_ANCHOR = "def epistemic_anchor_check(model_responses: dict, story_title: str, story_url: str) -> dict:"

# CALL insert: anchor on the log.info line ALONE (single line, byte-exact, 12-space indent)
BP_CALL_ANCHOR = '            log.info("  Logos synthesis: %s", "|".join(r["logos_words"][:3]))'
BP_CALL_REPLACE = (
    '            log.info("  Logos synthesis: %s", "|".join(r["logos_words"][:3]))\n'
    '\n'
    '            # Summary Plus: spicy second pass using the surfaced concepts\n'
    '            try:\n'
    '                r["summary_plus"] = generate_summary_plus(active, r.get("logos_words", []), story.title)\n'
    '                if r["summary_plus"]:\n'
    '                    log.info("  Summary Plus: %d models re-summarized", len(r["summary_plus"]))\n'
    '            except Exception as _spe:\n'
    '                r["summary_plus"] = {}\n'
    '                log.warning("  Summary Plus skipped: %s", _spe)'
)

# attribution lines (add summary_plus after each occurrence)
BP_ATTR = '                "model_responses": {a.name: a.text for a in active if a.text},'
BP_ATTR_REPLACE = ('                "model_responses": {a.name: a.text for a in active if a.text},\n'
                   '                "summary_plus": r.get("summary_plus", {}),')

# script_v3 insert before the epistemic anchor comment
SV_ANCHOR = '    # ── EPISTEMIC ANCHOR: surface reality denials as broadcast content ──'
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
    if bp.count(BP_CALL_ANCHOR) != 1:
        problems.append("  BP log.info(logos) anchor: found " + str(bp.count(BP_CALL_ANCHOR)) + " (need 1)")
    if bp.count(BP_FUNC_ANCHOR) != 1:
        problems.append("  BP function-insert anchor: found " + str(bp.count(BP_FUNC_ANCHOR)) + " (need 1)")
    n_attr = bp.count(BP_ATTR)
    if n_attr < 1:
        problems.append("  BP attribution line: found 0 (need >=1)")
    if "def generate_summary_plus(" in bp:
        problems.append("  BP already patched (generate_summary_plus present)")
    if sv.count(SV_ANCHOR) != 1:
        problems.append("  SV epistemic-anchor insert point: found " + str(sv.count(SV_ANCHOR)) + " (need 1)")
    if "beat_03c_summary_plus_intro" in sv:
        problems.append("  SV already patched (beat_03c present)")

    if problems:
        print("ABORTING - no changes made. Anchor problems:")
        print("\n".join(problems))
        print("\n(Files untouched. Paste this and we will fix.)")
        return 1

    shutil.copy(BP, BP + ".bak_beforesplus")
    shutil.copy(SV, SV + ".bak_beforesplus")
    bp = bp.replace(BP_FUNC_ANCHOR, BP_FUNC + BP_FUNC_ANCHOR, 1)
    bp = bp.replace(BP_CALL_ANCHOR, BP_CALL_REPLACE, 1)
    bp = bp.replace(BP_ATTR, BP_ATTR_REPLACE)
    open(BP, "w", encoding="utf-8").write(bp)
    sv = sv.replace(SV_ANCHOR, SV_INSERT, 1)
    open(SV, "w", encoding="utf-8").write(sv)

    print("Summary Plus applied.")
    print("  batch_producer.py: function + call + summary_plus on " + str(n_attr) + " attribution line(s)")
    print("  script_v3.py: beat_03c after rollcall")
    print("  Backups: .bak_beforesplus on both")
    print("")
    print("Verify both import:")
    print('    python3 -c "import batch_producer; import script_v3"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
