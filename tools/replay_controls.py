#!/usr/bin/env python3
"""
tools/replay_controls.py — measured vs null-control distributions over stored segments.

Read-only on the repository and the runtime tree; CPU only (CUDA_VISIBLE_DEVICES
is emptied before torch is imported); writes only under --out (default
/tmp/controls_replay_v2). Never reads .env (dotenv is stubbed before
batch_producer is imported).

For each of the newest N story segments (regex ^\\d{8}_\\d{6}_[0-9a-f]{12}_segment\\.json$,
attribution.model_vix present, >= 2 usable model_responses, source_body present)
the five production measurements are recomputed with the production functions
and controls.compute_controls is run on a synthetic "batch" of that story plus
its four most recent distinct-guid predecessors (so the batch-mate path is
exercised, never the disk fallback). Parity of the recomputation with the stored
attribution is reported per probe.

Stored segments carry source_body = (title + ". " + summary + " " + body)[:5000]
but not the RSS summary on its own, so the source text is rebuilt as
title + ". " + "" + " " + rest[:N] (rest = source_body after the title). The
character cut therefore differs from production by the summary length, which is
why source_void parity is reported as a distribution rather than asserted exact.

Also runs the seeded random-vocabulary void null from the 2026-09-10 design as
validation only (not part of production): random.Random(sha1(story guid)).

Usage:  python3 tools/replay_controls.py --n 100 [--out DIR] [--segments-dir DIR] [--no-random]
"""
import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TOKENIZERS_PARALLELISM"] = "false"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # VocabTensor("vocab") is a relative path in production

# No-op dotenv so importing batch_producer never reads .env into this process.
if "dotenv" not in sys.modules:
    _stub = types.ModuleType("dotenv")
    _stub.load_dotenv = lambda *a, **k: False
    _stub.find_dotenv = lambda *a, **k: ""
    _stub.dotenv_values = lambda *a, **k: {}
    _stub.__stub__ = True
    sys.modules["dotenv"] = _stub

import numpy as np  # noqa: E402

PAT = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{12}_segment\.json$")
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def q(xs):
    xs = [float(x) for x in xs if x is not None]
    if not xs:
        return None
    xs.sort()
    k = len(xs)
    return dict(n=k, mean=round(statistics.mean(xs), 4), median=round(xs[k // 2], 4),
                p10=round(xs[int(0.1 * k)], 4), p90=round(xs[min(k - 1, int(0.9 * k))], 4))


def frac(pairs, pred):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    return round(sum(1 for a, b in pairs if pred(a, b)) / len(pairs), 3) if pairs else None


def stage4_void_filter(title, void_concepts):
    """The stage_4_generate_scripts headline filter, copied verbatim (batch_producer.py)."""
    _hw = set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', title.lower()))
    void_words = [w for w in void_concepts
                  if w.lower() not in _hw
                  and not any(w.lower().startswith(h[:4]) or h.startswith(w.lower()[:4])
                              for h in _hw if len(h) >= 4)][:15]
    if not void_words:
        void_words = void_concepts[:15]
    return void_words


def load_segments(seg_dir, n):
    files = sorted(f for f in os.listdir(seg_dir) if PAT.match(f))
    segs = []
    for f in reversed(files):
        try:
            s = json.load(open(os.path.join(seg_dir, f)))
        except Exception:
            continue
        a = s.get("attribution", {})
        mr = a.get("model_responses") or {}
        mr = {k: v for k, v in mr.items() if isinstance(v, str) and v.strip() and not v.lstrip().startswith("[")}
        if not a.get("model_vix") or len(mr) < 2 or not a.get("source_body"):
            continue
        segs.append(dict(file=f, title=a.get("story_title", ""), guid=a.get("story_guid", f),
                         cat=a.get("category", ""), src=a.get("source_body", ""), resp=mr,
                         model_vix=a.get("model_vix") or {},
                         density=a.get("consensus_density"), mean_vix=a.get("mean_vix"),
                         void_words=a.get("void_words", []), source_void=a.get("source_void", {}),
                         comp=a.get("compression", {}), ks=a.get("claim_killshots", [])))
        if len(segs) >= n:
            break
    segs.reverse()  # chronological
    return segs


def make_story(s):
    t = s["title"]
    sb = s["src"]
    rest = sb[len(t) + 2:] if sb.startswith(t + ". ") else sb
    return SimpleNamespace(guid=s["guid"], title=t, summary="", body=rest, category=s["cat"], url=s["guid"])


def make_result(s):
    story = make_story(s)
    resps = [SimpleNamespace(name=n, text=t, skipped=False, error=None,
                             eigen_vix=float(s["model_vix"].get(n, 0.0)))
             for n, t in s["resp"].items()]
    return {"story": story, "responses": resps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--segments-dir", default="/home/remvelchio/eigentrace/tmp/segments")
    ap.add_argument("--out", default="/tmp/controls_replay_v2")
    ap.add_argument("--no-random", action="store_true", help="skip the seeded random-vocab void null")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    import batch_producer as bp
    import controls
    import claim_extractor as ce
    from eigentrace_math import source_anchored_void, score_language_compression
    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor

    segs = load_segments(args.segments_dir, args.n)
    n = len(segs)
    if not n:
        print("no segments")
        return 1
    log(f"{n} segments, {segs[0]['file']} .. {segs[-1]['file']}")

    eng = get_engine()
    log("bge-large loaded on", eng.model.device)
    cache = {}

    class CacheEngine:
        """Production engine with a text->vector cache (same vectors, fewer forward passes)."""
        def embed_texts(self, texts):
            todo = [t for t in dict.fromkeys(texts) if t not in cache]
            for k in range(0, len(todo), 16):
                chunk = todo[k:k + 16]
                for t, v in zip(chunk, eng.embed_texts(chunk)):
                    cache[t] = np.asarray(v, dtype=np.float32)
            return np.stack([cache[t] for t in texts])

        def compute_consensus_density(self, E):
            return eng.compute_consensus_density(E)
    ceng = CacheEngine()
    ceng.embed_texts([s["title"] for s in segs])
    log("titles embedded")
    ceng.embed_texts([t for s in segs for t in s["resp"].values()])
    log("responses embedded")

    vt = VocabTensor("vocab")
    long_idx = [k for k, w in enumerate(vt.words) if len(w) >= 4]
    log("vocab loaded")

    results = [make_result(s) for s in segs]
    empty_dir = Path(args.out) / "no_segments_here"   # disk fallback never used in the replay

    def window(i):
        """This story + its 4 most recent distinct-guid predecessors (cyclic)."""
        out = [results[i]]
        used = {segs[i]["guid"]}
        k = 1
        while len(out) < 5 and k < n:
            j = (i - k) % n
            k += 1
            if segs[j]["guid"] in used:
                continue
            used.add(segs[j]["guid"])
            out.append(results[j])
        return out

    rows = []
    for i, s in enumerate(segs):
        r = results[i]
        story = r["story"]
        texts = [x.text for x in r["responses"]]
        E = ceng.embed_texts(texts)
        d_meas = float(ceng.compute_consensus_density(E))
        vix = [round(v, 1) for v in bp._panel_vix(E)]
        r["geo"] = SimpleNamespace(consensus_density=d_meas)
        st = {}
        void_pool = bp._compute_void(story.title, texts, ceng, vt, pool_size=200, k=5, stats=st)
        r["void_stats"] = st
        r["source_void"] = source_anchored_void(controls.source_text_void(story), texts, title=story.title)
        r["compression"] = score_language_compression(controls.source_text_compression(story), texts)
        claims = []
        for kx in s["ks"]:
            c = kx.get("claim") if isinstance(kx, dict) else str(kx)
            if c and c not in claims:
                claims.append(c)
        claims = claims[:3]
        if claims:
            own_cov = ce.score_claim_coverage(claims, s["resp"], ceng, headline=story.title)
            r["claim_killshots"] = own_cov
        else:
            r["claim_killshots"] = []

        ctl = controls.compute_controls(r, window(i), 0, ceng, vt, texts, story, embeddings=E,
                                        void_fn=bp._compute_void, panel_vix=bp._panel_vix,
                                        segments_dir=empty_dir)

        row = dict(file=s["file"], title=s["title"][:80], cat=s["cat"], n_resp=len(texts),
                   control_story=(ctl.get("control_story") or {}).get("guid"),
                   errors={k: v.get("error") for k, v in ctl.items() if isinstance(v, dict) and v.get("error")})
        # parity with the stored attribution
        row["density_stored"] = s["density"]
        row["density_measured"] = round(d_meas, 4)
        row["density_gap"] = round(abs(d_meas - float(s["density"])), 4) if s["density"] is not None else None
        row["vix_stored"] = s["mean_vix"]
        row["vix_measured"] = round(sum(vix) / len(vix), 2)
        row["vix_gap"] = round(abs(row["vix_measured"] - float(s["mean_vix"])), 3) if s["mean_vix"] is not None else None
        filtered = stage4_void_filter(story.title, [w for w, _ in void_pool])
        row["void_top5_recomputed"] = filtered[:5]
        row["void_top5_stored"] = list(s["void_words"])[:5]
        row["void_top5_match"] = filtered[:5] == list(s["void_words"])[:5]
        row["sv_stored"] = (s["source_void"] or {}).get("absent_ratio")
        row["sv_measured"] = r["source_void"]["absent_ratio"]
        row["sv_gap"] = (round(abs(row["sv_measured"] - float(row["sv_stored"])), 4)
                         if row["sv_stored"] is not None else None)
        row["hedges_stored"] = ((s["comp"] or {}).get("attribution_buffer") or {}).get("total")
        row["hedges_measured"] = r["compression"]["attribution_buffer"]["total"]
        row["er_stored"] = (s["comp"] or {}).get("entity_retention")
        row["er_measured"] = r["compression"]["entity_retention"]
        # the controls themselves
        row["controls"] = ctl
        # seeded random-vocab void null (validation only; not in production)
        if not args.no_random and st.get("pool_n"):
            seed = int(hashlib.sha1(str(story.guid).encode()).hexdigest(), 16) % (2 ** 32)
            rng = random.Random(seed)
            all_text = " ".join(texts).lower()
            fr = []
            for _ in range(5):
                ws = [vt.words[k] for k in rng.sample(long_idx, st["pool_n"])]
                ab = sum(1 for w in ws if not re.search(r"\b" + re.escape(w.lower()) + r"\b", all_text))
                fr.append(ab / len(ws))
            row["void_random_null"] = dict(seed=seed, n_draws=5, absent_frac=round(statistics.mean(fr), 4),
                                           method="random_vocab_same_size_seeded_sha1_guid")
        rows.append(row)
        if (i + 1) % 10 == 0:
            log(f"{i + 1}/{n}")

    json.dump(rows, open(os.path.join(args.out, "rows.json"), "w"), indent=1, default=str)

    def g(row, probe, key):
        p = (row["controls"] or {}).get(probe) or {}
        return None if p.get("error") else p.get(key)

    S = dict(n=n, first=segs[0]["file"], last=segs[-1]["file"], date="2026-09-10",
             elapsed_s=round(time.time() - T0, 1))
    S["parity"] = dict(
        density_gap=q([r["density_gap"] for r in rows]),
        density_within_0_001=frac([(r["density_gap"], 0) for r in rows], lambda a, b: a <= 0.001),
        vix_gap=q([r["vix_gap"] for r in rows]),
        vix_within_0_05=frac([(r["vix_gap"], 0) for r in rows], lambda a, b: a <= 0.05),
        void_top5_match_frac=round(sum(1 for r in rows if r["void_top5_match"]) / n, 3),
        source_void_gap=q([r["sv_gap"] for r in rows]),
        source_void_within_0_001=frac([(r["sv_gap"], 0) for r in rows], lambda a, b: a <= 0.001),
        source_void_within_0_01=frac([(r["sv_gap"], 0) for r in rows], lambda a, b: a <= 0.01),
        hedges_exact=frac([(r["hedges_measured"], r["hedges_stored"]) for r in rows], lambda a, b: a == b),
        entity_retention_within_0_01=frac([(r["er_measured"], r["er_stored"]) for r in rows],
                                          lambda a, b: abs(a - b) <= 0.01),
        note=("source text rebuilt from stored source_body without the RSS summary, so the character cut "
              "differs from production by the summary length; void top-5 compared after the stage-4 headline filter"),
    )
    S["void"] = dict(
        measured=q([g(r, "void", "absent_frac") for r in rows]),
        control_unrelated_headline=q([g(r, "void", "control_absent_frac") for r in rows]),
        random_vocab_seeded=q([(r.get("void_random_null") or {}).get("absent_frac") for r in rows]),
        pool_n=q([g(r, "void", "pool_n") for r in rows]),
        frac_measured_below_control=frac([(g(r, "void", "absent_frac"), g(r, "void", "control_absent_frac"))
                                          for r in rows], lambda a, b: a < b),
    )
    S["source_void"] = dict(
        measured=q([g(r, "source_void", "absent_ratio") for r in rows]),
        control_other_article=q([g(r, "source_void", "control_absent_ratio") for r in rows]),
        frac_measured_below_control=frac([(g(r, "source_void", "absent_ratio"),
                                           g(r, "source_void", "control_absent_ratio")) for r in rows],
                                         lambda a, b: a < b),
    )
    ks_rows = [r for r in rows if (g(r, "killshots", "n_claims") or 0) > 0]
    S["killshots"] = dict(
        n_stories_with_killshots=len(ks_rows),
        n_claims=sum(g(r, "killshots", "n_claims") for r in ks_rows),
        max_sim_own=q([g(r, "killshots", "mean_max_sim_own") for r in ks_rows]),
        max_sim_control=q([g(r, "killshots", "mean_max_sim_control") for r in ks_rows]),
        frac_control_below_own=frac([(g(r, "killshots", "mean_max_sim_control"),
                                      g(r, "killshots", "mean_max_sim_own")) for r in ks_rows], lambda a, b: a < b),
        control_omitted_all=frac([(sum(1 for p in (g(r, "killshots", "per_claim") or [])
                                       if p.get("n_omitted_control") == r["controls"]["killshots"].get("control_n_responses")),
                                   g(r, "killshots", "n_claims")) for r in ks_rows], lambda a, b: a == b),
    )
    S["density"] = dict(
        measured=q([g(r, "density", "measured") for r in rows]),
        control_mixed=q([g(r, "density", "control_mixed") for r in rows]),
        vix_measured=q([g(r, "density", "measured_mean_vix") for r in rows]),
        vix_control_mixed=q([g(r, "density", "control_mean_vix") for r in rows]),
        n_panel=q([g(r, "density", "n_panel") for r in rows]),
        frac_measured_above_control=frac([(g(r, "density", "measured"), g(r, "density", "control_mixed"))
                                          for r in rows], lambda a, b: a > b),
    )
    S["compression"] = dict(
        hedges_measured=q([g(r, "compression", "hedges_total") for r in rows]),
        hedges_control=q([g(r, "compression", "hedges_total_control") for r in rows]),
        entity_retention_measured=q([g(r, "compression", "entity_retention") for r in rows]),
        entity_retention_control=q([g(r, "compression", "entity_retention_control") for r in rows]),
        verb_downgrade_measured=q([g(r, "compression", "verb_downgrade") for r in rows]),
        verb_downgrade_control=q([g(r, "compression", "verb_downgrade_control") for r in rows]),
        frac_entity_retention_above_control=frac([(g(r, "compression", "entity_retention"),
                                                   g(r, "compression", "entity_retention_control"))
                                                  for r in rows], lambda a, b: a > b),
        frac_hedges_below_control=frac([(g(r, "compression", "hedges_total"),
                                         g(r, "compression", "hedges_total_control")) for r in rows],
                                       lambda a, b: a < b),
        n_blurb_controls=sum(1 for r in rows if (g(r, "compression", "blurb") or None)),
    )
    S["errors"] = {}
    for r in rows:
        for k in r["errors"]:
            S["errors"][k] = S["errors"].get(k, 0) + 1
    json.dump(S, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
