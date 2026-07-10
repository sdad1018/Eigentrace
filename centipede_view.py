#!/usr/bin/env python3
"""
centipede_view.py -- draws a centipede JSON as a terminal page.

Reads the frozen artifact centipede_v0x writes ({story}_centipede.json)
and renders it in the EigenTrace idiom: SOURCE at the top, the centipede
body (spine = anchor, each segment a rib, void words down the middle,
arm A fanning left / arm B fanning right), then a MEASURED block and a
READING block kept rigorously apart.

The measurement instrument (centipede_v0x) is never touched; this viewer
only consumes its output. Same split the Summary Plus page makes its
thesis: frozen substrate, separate reading of it.

    python3 centipede_view.py anamnesis_results/universal/foo_centipede.json
    python3 centipede_view.py foo_centipede.json --width 92 --arms 3
    python3 centipede_view.py foo_centipede.json --legs said/F,logos_v10/ALL
"""

import argparse
import json
import textwrap

BAR = "=" * 78
RULE = "-" * 78


def wrap(s, w, indent=""):
    return textwrap.fill(s, width=w, initial_indent=indent,
                         subsequent_indent=indent)


def fmt_terms(terms, n, dash="-"):
    if not terms:
        return dash
    return ", ".join(terms[:n])


def draw(report, width, n_arms, only_legs):
    story = report.get("story", "?")
    prov = report.get("provenance", {})
    models = report.get("models", {})
    anchor = report.get("anchor", {})
    segs = report.get("segments", [])
    crawl = report.get("crawl", {})

    out = []
    out.append(BAR)
    out.append(f"  CENTIPEDE  ::  {story}  ::  {report.get('version','')}")
    out.append(BAR)

    # ---- SOURCE header ------------------------------------------------
    head = anchor.get("headline", "")
    out.append("SOURCE (anchor text):")
    for line in wrap(head, width - 2, "  ").splitlines():
        out.append(line)
    ct = anchor.get("contains_targets") or []
    out.append(f"  anchor holds targets: {', '.join(ct) if ct else '(none)'}")
    out.append(f"  {len(models.get('frontier',[]))} frontier + "
               f"{len(models.get('local',[]))} local models")
    out.append("")

    # ---- shared-void marker: which stems appear across many legs ------
    stem_leg_count = {}
    for seg in segs:
        for arm in seg.get("arms", []):
            st = arm.get("stem")
            stem_leg_count[st] = stem_leg_count.get(st, 0) + 1
    hot = {st for st, c in stem_leg_count.items() if c >= 4}

    # ---- the body -----------------------------------------------------
    out.append("BODY  (spine=anchor; each rib=one method; * = void shared "
               "by >=4 legs)")
    out.append(f"  arm A <-- [{prov.get('rulers',{}).get('arm_a','253K')}]"
               f"      [{prov.get('rulers',{}).get('arm_b','50K')}] --> arm B")
    out.append("")
    out.append("            o  (anchor / source center of mass)")
    out.append("            |")

    half = (width - 24) // 2
    shown = 0
    for seg in segs:
        name = seg.get("name", "?")
        if only_legs and name not in only_legs:
            continue
        arms = seg.get("arms", [])
        voids = seg.get("voids", [])
        if not voids:
            out.append(f"    ~~~~~~| {name:<16}|  (no voids)")
            out.append("            |")
            continue
        out.append(f"    ------| {name:<16}|" + "-" * 6 + ">")
        for arm in arms[:n_arms if n_arms else len(arms)]:
            v = arm.get("void", "")
            st = arm.get("stem", "")
            mark = "*" if st in hot else " "
            A = arm.get("A", {})
            B = arm.get("B", {})
            aq = A.get("quality", "-")
            a_terms = fmt_terms(A.get("terms", []), 3)
            b_terms = fmt_terms(B.get("terms", []), 3)
            fc = arm.get("field_cos")
            fc_s = f"{fc:.2f}" if isinstance(fc, (int, float)) else " -- "
            # left = arm A, middle = void, right = arm B
            left = a_terms[:half].rjust(half)
            out.append(f"  {left}  ·{mark}[ {v[:16]:<16} ]{mark}·  {b_terms[:half]}")
            out.append(f"  {'':<{half}}  ·  A[{aq}] cos={fc_s}")
        out.append("            |")
        shown += 1
    out.append("            v")
    out.append("")
    if only_legs and shown == 0:
        out.append("  (no legs matched --legs filter)")
        out.append("")

    # ---- MEASURED block ----------------------------------------------
    out.append(RULE)
    out.append("MEASURED  (numbers the instrument returned)")
    out.append(RULE)
    jk = crawl.get("junk", {})
    out.append(f"  arm-A junk filter : dropped {jk.get('dropped','?')} of "
               f"{jk.get('seen','?')} terms  [{prov.get('junk_rule','')}]")
    bm = crawl.get("body_median")
    sn = crawl.get("shuffle_null", {})
    nm = sn.get("null_median")
    mg = sn.get("margin")

    def f2(x):
        return f"{x:.3f}" if isinstance(x, (int, float)) else " -- "
    out.append(f"  arm agreement     : observed={f2(bm)}  null={f2(nm)}  "
               f"margin={('+' if isinstance(mg,(int,float)) and mg>=0 else '')}"
               f"{f2(mg)}  (n_obs={sn.get('n_obs','?')} "
               f"n_null={sn.get('n_null','?')})")
    lj = crawl.get("leg_jaccard", {})
    out.append(f"  leg void-overlap  : median J={f2(lj.get('median'))}  "
               f"pairs>=0.25: {len(lj.get('pairs_ge_025', []))}")
    aj = crawl.get("arm_jaccard_median")
    out.append(f"  arm lexical J     : {f2(aj)}  "
               f"(0.00 expected: rulers are disjoint vocab)")

    # target census, if any
    sightings = report.get("target_sightings", [])
    if sightings:
        out.append("  target census     :")
        for s in sightings:
            t = s.get("target", "?")
            sb = s.get("said_by", 0)
            n = report.get("models", {}).get("n", "?")
            tag = ""
            cp = s.get("concept_present_via_synonym")
            if s.get("synonyms"):
                if sb == 0 and cp:
                    tag = f"  -> concept present via synonym in {cp}/{n}"
                elif sb == 0 and cp == 0:
                    tag = "  -> GENUINELY ABSENT"
            iv = s.get("in_voids") or []
            ivtag = f"  in_voids={len(iv)}" if iv else ""
            out.append(f"      {t:<13} said {sb}/{n}{ivtag}{tag}")
    out.append(f"  determinism sha   : {report.get('result_sha','?')}")
    out.append("")

    # ---- READING block (argued, from the JSON's own structure) -------
    out.append(RULE)
    out.append("READING  (argued -- interpretation, separable from the above)")
    out.append(RULE)
    # a light auto-reading assembled from the measured facts, clearly
    # labeled as the viewer's summary, not a new measurement.
    lines = []
    if isinstance(mg, (int, float)):
        if mg >= 0.06:
            lines.append(f"Arms co-locate above the topic floor "
                         f"(margin {mg:+.3f}): the two rulers, given the "
                         f"same ray, land in the same neighborhood more than "
                         f"chance -- a real, priced signal.")
        else:
            lines.append(f"Arm agreement sits near the topic floor "
                         f"(margin {mg:+.3f}): little signal beyond what any "
                         f"two topical word-lists share. Read thin.")
    absent = [s["target"] for s in sightings
              if s.get("said_by") == 0 and s.get("synonyms")
              and s.get("concept_present_via_synonym") == 0]
    viasyn = [s["target"] for s in sightings
              if s.get("said_by") == 0
              and s.get("concept_present_via_synonym", 0) > 0]
    if viasyn:
        lines.append("Floored-but-present (concept carried by a synonym, "
                     "NOT suppression): " + ", ".join(viasyn) + ".")
    if absent:
        lines.append("Genuinely absent (floored AND no synonym reached): "
                     + ", ".join(absent) + " -- the true void field.")
    ljm = lj.get("median")
    if isinstance(ljm, (int, float)) and ljm < 0.1 \
            and len(lj.get("pairs_ge_025", [])) > 0:
        lines.append("Legs disagree on WHAT is missing (median void-overlap "
                     "~0) while a tight core agrees exactly -- two-layer "
                     "structure: disjoint peripheries, one shared spine.")
    if not lines:
        lines.append("No priced signal and no declared targets -- run with "
                     "--targets and --synonyms to read the void field.")
    for ln in lines:
        for w in wrap(ln, width - 4, "  * ").splitlines():
            out.append(w)
    out.append("")
    out.append("  (READING is the viewer's synthesis of the MEASURED block, "
               "not a new measurement.)")
    out.append(BAR)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--width", type=int, default=88)
    ap.add_argument("--arms", type=int, default=0,
                    help="max void words drawn per leg (0 = all)")
    ap.add_argument("--legs", default="",
                    help="comma list to draw only certain legs")
    args = ap.parse_args()
    report = json.load(open(args.json_path, encoding="utf-8"))
    only = [x.strip() for x in args.legs.split(",") if x.strip()]
    print(draw(report, args.width, args.arms, only))


if __name__ == "__main__":
    main()
