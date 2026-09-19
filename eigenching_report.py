#!/usr/bin/env python3
"""Generate eigenching_data.json and eigenching_distribution.md for the website."""
import json, glob, os, re
from collections import Counter, defaultdict

SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
OUT_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/eigenching_data.json"  # 2026-09-10: module-level so tests can point it at tmp
DIST_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/eigenching_distribution.md"  # 2026-09-19: generated, was a hand-written 2026-04-16 snapshot
ARCHETYPES = {
    ( 1, 1, 1, 1, 1, 1): "The Clear Channel",
    (-1,-1,-1,-1,-1,-1): "The Sealed Vault",
    ( 1,-1,-1,-1,-1,-1): "The Sealed Chorus",
    ( 1,-1,-1,-1,-1, 1): "The Cornering",
    ( 1,-1,-1,-1, 1,-1): "The Quiet Cull",
    ( 1,-1,-1, 1,-1,-1): "The Anonymized Drone",
    ( 1,-1, 1,-1,-1,-1): "The Named Erasure",
    ( 1, 1,-1,-1,-1,-1): "The Soft Consensus",
    (-1, 1, 1, 1, 1, 1): "The Open Field",
    (-1,-1,-1,-1,-1, 1): "The Panicked Hush",
    (-1, 1, 1, 1, 1,-1): "The Lone Wolf",
    (-1,-1, 1, 1, 1, 1): "The Scatter Signal",
    ( 1, 1, 1, 1,-1,-1): "The Unanimous Shield",
    ( 1, 1,-1, 1,-1, 1): "The Polished Unity",
    (-1, 1,-1, 1, 1, 1): "The Open Hedge",
    ( 1,-1, 1, 1,-1, 1): "The Sharp Silence",
    (-1, 1, 1,-1,-1, 1): "The Phantom Chorus",
    ( 1, 1, 1,-1, 1, 1): "The Namedrop",
    (-1,-1, 1, 1, 1,-1): "The Split Witness",
    ( 1,-1, 1,-1, 1, 1): "The Hollow Headline",
    (-1, 1,-1,-1, 1,-1): "The Divided Softening",
    ( 1, 1,-1,-1, 1, 1): "The Smoothed Pact",
    (-1,-1, 1,-1,-1,-1): "The Naming Battle",
    ( 1, 1, 1, 1, 1,-1): "The One Outlier",
    (-1,-1,-1, 1,-1, 1): "The Entity Refuge",
    ( 1,-1,-1, 1, 1,-1): "The Sharp Cornering",
    (-1, 1, 1,-1, 1,-1): "The Faceless Signal",
    ( 1, 1,-1, 1, 1,-1): "The Gentle Break",
    (-1,-1, 1, 1,-1, 1): "The Buffered Scatter",
    ( 1,-1, 1, 1, 1,-1): "The Clean Compression",
    (-1, 1,-1,-1,-1, 1): "The Uneasy Unity",
    ( 0, 0, 0, 0, 0, 0): "The Still Point",
}

DESCRIPTIONS = {
    "The Clear Channel": "Signal passes through all five models with minimal shaping. Rare.",
    "The Sealed Vault": "Total compression. Models agree to erase, soften, abstract, and hedge. The signal is gone.",
    "The Sealed Chorus": "Unified heavy compression with tight spread. Consensus of omission.",
    "The Cornering": "Models lockstep on compression. The narrowness of agreement is itself a signal.",
    "The Quiet Cull": "Direct but compressed. Models don't hedge, they just leave things out.",
    "The Anonymized Drone": "Names survive but everything else is softened and hedged.",
    "The Named Erasure": "Entities named but surrounded by hedging. Who did it is clear; what they did is fuzzy.",
    "The Soft Consensus": "Source preserved but delivery softened. The facts are there, muted.",
    "The Open Field": "Models disagree but each preserves. No collective suppression, just divergent takes.",
    "The Panicked Hush": "Models disagree on what to compress but all compress. Confused alignment.",
    "The Lone Wolf": "One model breaks from the pack. Others preserve. Worth investigating the outlier.",
    "The Scatter Signal": "Disagreement on framing but nobody drops content. Healthy diversity.",
    "The Unanimous Shield": "All models agree, preserve content, but wall it in attribution. Liability-aware.",
    "The Polished Unity": "Smooth agreement. Facts preserved, language softened, claims buffered.",
    "The Open Hedge": "Models disagree on tone but share directness. Mixed signals.",
    "The Sharp Silence": "Names kept, verbs kept, hedges dropped, but content gone. Skeleton without meat.",
    "The Phantom Chorus": "Content preserved but entities dropped across all models. Who did what, unnamed.",
    "The Namedrop": "Everything survives except the people. Story intact, actors abstract.",
    "The Split Witness": "One model sees differently. Others preserve but differ on compression.",
    "The Hollow Headline": "Names and hedges match, but content and entities go. Shape without substance.",
    "The Divided Softening": "Split disagreement with softening. Models hedge differently.",
    "The Smoothed Pact": "Content preserved, entities abstracted, tone softened. Diplomatic register.",
    "The Naming Battle": "Models scatter on everything except keeping verbs.",
    "The One Outlier": "Everything clean except one model runs hot. Watch the outlier.",
    "The Entity Refuge": "Total compression except names survive. The story is gone but the actors remain.",
    "The Sharp Cornering": "Named, direct, but everything else compressed. One model breaks.",
    "The Faceless Signal": "Content survives, entities erased, one model breaks.",
    "The Gentle Break": "Mostly healthy but softened with one divergent model. Subtle dissent.",
    "The Buffered Scatter": "Models scatter with hedges. Even the disagreement is qualified.",
    "The Clean Compression": "Everything sharp and named but compressed. Surgical editing with one break.",
    "The Uneasy Unity": "Tight spread but models disagree. Tension without divergence.",
    "The Still Point": "Perfect equilibrium across all six axes. The broadcast's empty center.",
}

# ── keying ──────────────────────────────────────────────────────────────────
# 2026-09-19: a beat is keyed on the EXACT archetype name (case-insensitive,
# whitespace-normalised).  The beat text is "EigenChing state: {name}. {desc}",
# and eigenching.py writes a comma INTO the name only for a near-miss
# ("The Cornering, verbs recovering"), never for an exact hit.  Keying on the
# text before the first comma therefore returned a bare archetype name only for
# near-misses and never for an exact hit; see CHANGELOG 2026-09-19.
BEAT_PREFIX = "EigenChing state:"
LEGACY_PREFIX = "EigenTrace state vector"
LEGACY_AXES = ["consensus density", "absent ratio", "verb drift",
               "entity retention", "hedge count", "mean vix"]
TRIT_WORD = {"plus": 1, "minus": -1, "neutral": 0}
STORY_FILE_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$")

NAME_BY_NORM = {}
SIG_BY_NAME = {}


def _norm_name(s):
    """Case-insensitive, whitespace-normalised, trailing period stripped."""
    return " ".join((s or "").strip().rstrip(".").lower().split())


for _sig, _name in ARCHETYPES.items():
    NAME_BY_NORM[_norm_name(_name)] = _name
    SIG_BY_NAME[_name] = _sig


def aired_name(text):
    """The full aired state name: between the prefix and the first period.

    Archetype names and the morphological names built from them never contain a
    period; the description follows it. Returns None if the beat is not in this
    format.
    """
    if BEAT_PREFIX not in text:
        return None
    return text.split(BEAT_PREFIX, 1)[1].split(".", 1)[0].strip()


def legacy_signature(text):
    """Signature read back out of a pre-EigenChing 'state vector' beat."""
    low = (text or "").lower()
    vals = []
    for axis in LEGACY_AXES:
        m = re.search(re.escape(axis) + r"\s*:\s*(plus|minus|neutral)", low)
        if not m:
            return None
        vals.append(TRIT_WORD[m.group(1)])
    return tuple(vals)


def _hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def _nearest(signature):
    """Nearest named archetype by Hamming distance; ties go to dictionary order,
    matching eigenching._nearest_archetype when no frequency table is passed."""
    best, best_d = None, 999
    for sig in ARCHETYPES:
        d = _hamming(signature, sig)
        if d < best_d:
            best, best_d = sig, d
    return best, best_d


def classify_signature(signature):
    """(tier, archetype_name) for a signature. tier: exact | near_miss | outside."""
    if signature in ARCHETYPES:
        return "exact", ARCHETYPES[signature]
    sig, d = _nearest(signature)
    if d <= 2:
        return "near_miss", ARCHETYPES[sig]
    return "outside", None


def key_beat(text):
    """Key one state beat.

    Returns (tier, archetype_name, aired_name) where tier is
      'exact'     — the aired name IS a named archetype;
      'near_miss' — the aired name is an archetype name plus one or two axis
                    modifiers (Hamming 1-2), i.e. NOT that archetype;
      'outside'   — a compositional name, no archetype within reach;
    or None if the text carries no state beat this generator can read.
    """
    name = aired_name(text)
    if name is not None:
        norm = _norm_name(name)
        if norm in NAME_BY_NORM:
            return "exact", NAME_BY_NORM[norm], name
        for cand_norm, cand in NAME_BY_NORM.items():
            if norm.startswith(cand_norm + ",") or norm == "partial " + cand_norm:
                return "near_miss", cand, name
        return "outside", None, name
    if LEGACY_PREFIX.lower() in (text or "").lower():
        sig = legacy_signature(text)
        if sig is None:
            return None
        tier, arch = classify_signature(sig)
        return tier, arch, arch or "".join(str(v) for v in sig)
    return None


# ── corpus axis inputs (MISSING is not zero) ────────────────────────────────
AXIS_SIGNALS = ["consensus_density", "absent_ratio", "verb_drift",
                "entity_retention", "hedge_count", "vix_spread"]


def axis_inputs(attr):
    """Return (values, missing_axes) for the six state axes.

    An absent compression / source-void / model-VIX block yields None for the
    axes it feeds — MISSING, never 0. state_vector.extract_signals reads these
    with .get(key, 0), and the quantizer sends 0 to entity = -1 and
    verb_drift = +1, so an unmeasured row lands on a specific cell by
    construction. Rows with any MISSING axis are excluded from the state
    distribution's denominator and counted separately.
    """
    comp = attr.get("compression") if isinstance(attr, dict) else None
    sv = attr.get("source_void") if isinstance(attr, dict) else None
    mvix = attr.get("model_vix") if isinstance(attr, dict) else None
    comp = comp if isinstance(comp, dict) else {}
    sv = sv if isinstance(sv, dict) else {}
    ab = comp.get("attribution_buffer")
    vals = [v for v in mvix.values() if isinstance(v, (int, float))] if isinstance(mvix, dict) else []
    values = {
        "consensus_density": attr.get("consensus_density") if isinstance(attr, dict) else None,
        "absent_ratio": sv.get("absent_ratio"),
        "verb_drift": comp.get("verb_downgrade"),
        "entity_retention": comp.get("entity_retention"),
        "hedge_count": ab.get("total") if isinstance(ab, dict) else None,
        "vix_spread": (max(vals) - min(vals)) if len(vals) >= 2 else None,
    }
    missing = [k for k in AXIS_SIGNALS if not isinstance(values[k], (int, float))
               or isinstance(values[k], bool)]
    return values, missing


def _quantized_state(values):
    """Quantize the six axes with the production rules, or None if unavailable."""
    try:
        import state_vector as SV
    except Exception:
        return None
    try:
        return tuple(SV.quantize(values[k], SV.QUANT_RULES[k]) for k in AXIS_SIGNALS)
    except Exception:
        return None


def _state_label(signature):
    tier, arch = classify_signature(signature)
    if tier == "exact":
        return arch, "exact archetype"
    if tier == "near_miss":
        return "near-miss of %s" % arch, "near-miss"
    return "unnamed state", "outside named territory"


# ── report ──────────────────────────────────────────────────────────────────
def generate_report():
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*_segment.json")))
    exact_counts, near_counts = Counter(), Counter()
    exact_examples, near_examples = defaultdict(list), defaultdict(list)
    tier_counts, fmt_counts = Counter(), Counter()
    outside_names = Counter()
    total = 0

    rows = missing_rows = measured_rows = 0
    missing_by_axis = Counter()
    measured_states = Counter()
    imputed_states = Counter()
    cell_measured = cell_imputed = 0

    for f in files:
        try:
            seg = json.load(open(f))
            if not isinstance(seg, dict):
                continue
            attr = seg.get("attribution") or {}
            title = (attr.get("story_title") or "Unknown") if isinstance(attr, dict) else "Unknown"

            for b in (seg.get("beats") or []):
                if not isinstance(b, dict):
                    continue
                if "state_vector" not in (b.get("phase") or ""):
                    continue
                keyed = key_beat(b.get("text") or "")
                if keyed is None:
                    continue
                tier, arch, name = keyed
                total += 1
                tier_counts[tier] += 1
                fmt_counts["named" if BEAT_PREFIX in (b.get("text") or "") else "legacy_axis_readout"] += 1
                if tier == "exact":
                    exact_counts[arch] += 1
                    if len(exact_examples[arch]) < 3:
                        exact_examples[arch].append(title[:80])
                elif tier == "near_miss":
                    near_counts[arch] += 1
                    if len(near_examples[arch]) < 3:
                        near_examples[arch].append(title[:80])
                else:
                    outside_names[name] += 1

            if STORY_FILE_RE.match(os.path.basename(f)):
                rows += 1
                values, missing = axis_inputs(attr)
                imputed = _quantized_state({k: (values[k] if isinstance(values[k], (int, float))
                                                and not isinstance(values[k], bool) else 0)
                                            for k in AXIS_SIGNALS})
                if imputed is not None:
                    imputed_states[imputed] += 1
                    if imputed[3] == -1 and imputed[2] == 1:
                        cell_imputed += 1
                if missing:
                    missing_rows += 1
                    missing_by_axis.update(missing)
                    continue
                state = _quantized_state(values)
                if state is None:
                    continue
                measured_rows += 1
                measured_states[state] += 1
                if state[3] == -1 and state[2] == 1:
                    cell_measured += 1
        except Exception:
            continue

    archetypes = []
    for sig, name in sorted(ARCHETYPES.items(), key=lambda x: -exact_counts.get(x[1], 0)):
        archetypes.append({
            "name": name,
            "signature": list(sig),
            "count": exact_counts.get(name, 0),
            "pct": round(exact_counts.get(name, 0) / max(total, 1) * 100, 1),
            "near_miss_count": near_counts.get(name, 0),
            "near_miss_pct": round(near_counts.get(name, 0) / max(total, 1) * 100, 1),
            "near_miss_note": ("beats aired as this archetype's name plus one or two axis "
                               "modifiers (Hamming 1-2). They are NOT this archetype and are "
                               "not included in count."),
            "description": DESCRIPTIONS.get(name, ""),
            "examples": exact_examples.get(name, []),
            "near_miss_examples": near_examples.get(name, []),
        })

    report = {
        "total_segments": total,
        "total_files": len(files),
        "generated": __import__("datetime").datetime.utcnow().isoformat(),
        "archetypes": archetypes,
    }
    # 2026-09-10: this is a census of every segment that aired a state beat, not a sample:
    # count and pct are exact over total_segments, so no interval is published here.
    # 2026-09-19: count is the number of EXACT archetype hits. Near-misses (Hamming 1-2)
    # are carried separately in near_miss_count and are never added to count.
    try:
        import re as _re
        report["n"] = total
        report["census"] = True
        report["keying"] = ("exact archetype name, case-insensitive and whitespace-normalised; "
                            "near-misses counted separately")
        report["state_beats"] = total
        report["beats_by_format"] = dict(fmt_counts)
        report["exact_total"] = sum(exact_counts.values())
        report["near_miss_total"] = sum(near_counts.values())
        report["outside_named_territory_total"] = tier_counts.get("outside", 0)
        report["archetypes_with_exact_hits"] = sum(1 for a in archetypes if a["count"] > 0)
        report["archetypes_without_exact_hits"] = sum(1 for a in archetypes if a["count"] == 0)
        report["most_common_aired_state"] = (outside_names.most_common(1)[0][0]
                                             if outside_names else None)
        report["story_files"] = sum(1 for f in files if _re.match(r"^\d{8}_\d{6}_[0-9a-f]{12}_segment\.json$", os.path.basename(f)))
        report["state_distribution"] = {
            "rows": rows,
            "missing_rows": missing_rows,
            "measured_rows": measured_rows,
            "missing_by_axis": dict(missing_by_axis),
            "entity_dropped_verbs_intact_measured": [cell_measured, measured_rows],
            "entity_dropped_verbs_intact_if_missing_read_as_zero": [cell_imputed, rows],
            "note": ("rows with any MISSING axis metric are excluded from the measured "
                     "denominator and counted in missing_rows; they are not read as zero"),
        }
        report["ci_method"] = ("census: count and pct are exact over total_segments (state beats "
                               "whose aired name is exactly a named archetype); no sampling "
                               "interval applies. near_miss_count is the separate count of beats "
                               "one or two axes away from that archetype and is not part of count. "
                               "story_files counts files matching the story filename pattern, "
                               "including wild_weasel probes; total_files counts every segment file.")
    except Exception:
        pass

    out = OUT_PATH
    json.dump(report, open(out, "w"), indent=2)
    try:
        write_distribution(report, measured_states, imputed_states, outside_names)
    except Exception:
        pass
    print(f"EigenChing report: {total} state beats, "
          f"{sum(exact_counts.values())} exact archetype hits across "
          f"{sum(1 for a in archetypes if a['count'] > 0)} archetypes, "
          f"{sum(near_counts.values())} near-misses")
    return report


def _pct(n, d):
    return "%.1f%%" % (100.0 * n / d) if d else "n/a"


def write_distribution(report, measured_states, imputed_states, outside_names):
    """Regenerate docs/eigenching_distribution.md from this run."""
    total = report["total_segments"]
    sd = report.get("state_distribution", {})
    rows, missing_rows, measured_rows = sd.get("rows", 0), sd.get("missing_rows", 0), sd.get("measured_rows", 0)
    cm, cmd = sd.get("entity_dropped_verbs_intact_measured", [0, 0])
    ci, cid = sd.get("entity_dropped_verbs_intact_if_missing_read_as_zero", [0, 0])
    L = []
    A = L.append
    A("# EigenChing distribution")
    A("")
    A("Generated by `eigenching_report.py` on %s UTC. Two censuses with two different"
      % report["generated"][:19])
    A("denominators; neither is a sample.")
    A("")
    A("## 1. Aired state beats")
    A("")
    A("%s state beats in %s segment files." % (f"{total:,}", f"{report['total_files']:,}"))
    A("")
    A("| tier | beats | share |")
    A("|---|---|---|")
    A("| exact archetype | %s | %s |" % (f"{report['exact_total']:,}", _pct(report["exact_total"], total)))
    A("| near-miss (one or two axes from a named archetype) | %s | %s |"
      % (f"{report['near_miss_total']:,}", _pct(report["near_miss_total"], total)))
    A("| outside named territory | %s | %s |"
      % (f"{report['outside_named_territory_total']:,}", _pct(report["outside_named_territory_total"], total)))
    A("")
    fmts = report.get("beats_by_format", {})
    A("Beat formats: %s name the state, %s read the six axes out and are classified from"
      % (f"{fmts.get('named', 0):,}", f"{fmts.get('legacy_axis_readout', 0):,}"))
    A("those axis words. A near-miss is counted as a near-miss of the archetype it names, never")
    A("as that archetype.")
    A("")
    A("### Named archetypes with at least one exact hit (%d of 32)" % report["archetypes_with_exact_hits"])
    A("")
    A("| archetype | signature | exact | near-miss |")
    A("|---|---|---|---|")
    for a in report["archetypes"]:
        if a["count"] > 0:
            A("| %s | %s | %d | %d |" % (a["name"], " ".join("%+d" % v if v else " 0" for v in a["signature"]),
                                         a["count"], a["near_miss_count"]))
    A("")
    A("### Named archetypes with no exact hit (%d of 32)" % report["archetypes_without_exact_hits"])
    A("")
    A("| archetype | near-miss beats |")
    A("|---|---|")
    for a in report["archetypes"]:
        if a["count"] == 0:
            A("| %s | %d |" % (a["name"], a["near_miss_count"]))
    A("")
    A("### Most common aired states outside named territory")
    A("")
    for name, n in outside_names.most_common(5):
        A("- %s — %s (%s of all state beats)" % (name, f"{n:,}", _pct(n, total)))
    A("")
    A("## 2. Corpus state distribution")
    A("")
    A("%s story segment files. %s carry no compression, source-void or per-model VIX block:"
      % (f"{rows:,}", f"{missing_rows:,}"))
    A("those axes are MISSING, the rows are excluded from the denominator below, and they are")
    A("not read as zero. Measured denominator: %s rows." % f"{measured_rows:,}")
    A("")
    A("| state | nearest name | tier | rows | share of measured |")
    A("|---|---|---|---|---|")
    tot_m = sum(measured_states.values())
    for sig, n in measured_states.most_common(5):
        label, tier = _state_label(sig)
        A("| %s | %s | %s | %s | %s |" % (" ".join("%+d" % v if v else " 0" for v in sig), label,
                                          tier, f"{n:,}", _pct(n, tot_m)))
    A("")
    A("### Entity axis -1 (names dropped) with verb axis +1 (verbs intact)")
    A("")
    A("%s of %s measured rows (%s)." % (f"{cm:,}", f"{cmd:,}", _pct(cm, cmd)))
    A("")
    A("Reading a missing axis as zero instead puts %s of %s rows (%s) in that cell: the"
      % (f"{ci:,}", f"{cid:,}", _pct(ci, cid)))
    A("quantizer sends a missing entity value to -1 and a missing verb value to +1, so a row")
    A("with no measurement lands there by construction. Such rows are reported as MISSING.")
    A("")
    # The page is written beside OUT_PATH, so a caller (or a test) that
    # redirects only OUT_PATH cannot write over the live page by omission.
    out_dir = os.path.dirname(os.path.abspath(OUT_PATH))
    dist = DIST_PATH
    if os.path.dirname(os.path.abspath(DIST_PATH)) != out_dir:
        dist = os.path.join(out_dir, os.path.basename(DIST_PATH))
    with open(dist, "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    generate_report()
