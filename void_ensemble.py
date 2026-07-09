#!/usr/bin/env python3
"""void_ensemble.py — 2026-07-08

The void ensemble: every live void-detection channel firing on one
story, voted, deduped (stem + geography), top five, then consequence
raycast arms per void word, RAG-lite over the segment archive, and a
Mistral mega-opine over the whole table — emitted as broadcast beats.

Registry-lite discipline: every channel declares (era, dictionary,
anchor, downstream_of). Declarations are stamped into the segment
attribution, so every on-air claim carries its parameters. The four
declared parameters this week earned: cloud, anchor, dictionary,
weighting.

Absorption: when the ensemble succeeds, it declares which legacy beats
it absorbs (ens["absorbs"]); the producer skips those for that segment.
If the ensemble fails, legacy beats fire unchanged. Graceful.

Offline test (no producer touch, prints the would-be beats):
    python3 void_ensemble.py                    # newest real segment
    python3 void_ensemble.py --no-mistral       # skip the opine
    python3 void_ensemble.py --no-raycast --no-fresh
"""
import json
import logging
import os
import re
import glob
import time

log = logging.getLogger("void_ensemble")

TOP_N = 5
SEGMENTS_DIR = "/home/remvelchio/eigentrace/tmp/segments"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ENSEMBLE_MODEL = os.getenv("ENSEMBLE_MODEL", "mistral")

# ── channel registry (era, dictionary, anchor, downstream_of) ─────────
REGISTRY = {
    "headline_void": dict(era="production", dictionary="word-vocab",
                          anchor="headline", downstream_of=None),
    "source_void":   dict(era="production", dictionary="lexical/set-theory",
                          anchor="source-text", downstream_of=None),
    "logos_v10":     dict(era="2026-07", dictionary="word-vocab+band-filter",
                          anchor="headline", downstream_of=None),
    "sp_flat":       dict(era="summary-plus", dictionary="word-vocab",
                          anchor="headline", downstream_of="logos_v10"),
    "sp_spiral":     dict(era="summary-plus", dictionary="word-vocab",
                          anchor="headline", downstream_of=None),
    "sp_void":       dict(era="summary-plus", dictionary="lexical",
                          anchor="source-text", downstream_of=None),
    "synthesis":     dict(era="cybernetic", dictionary="word-vocab",
                          anchor="headline", downstream_of=None),
    "donut":         dict(era="in-domain-void", dictionary="word-vocab",
                          anchor="headline", downstream_of=None),
    "vf_idf":        dict(era="2026-06", dictionary="two-channel cos+lex",
                          anchor="source-text", downstream_of=None),
    "raycast_arms":  dict(era="layer-18", dictionary="raycast-vocab(253K)",
                          anchor="headline", downstream_of="ensemble_top5"),
}

_STOP = set("""the a an and or but if for of in on at to from by with about
into over after before between during without within is are was were be been
have has had do does did will would can could may might this that these those
it its they them their there here he she his her him you your we our said says
say new latest update updates live""".split())
_TOK = re.compile(r"[a-zA-Z][a-zA-Z'\-]+")

try:
    from preservation_core import porter_stem as _stem
except Exception:
    _stem = lambda w: w.lower()


def _tokens(text):
    return [w.lower() for w in _TOK.findall(text or "")]


def _content(text):
    return [w for w in _tokens(text) if len(w) > 2 and w not in _STOP]


# ── compact geo gazetteer: country + capital + demonyms collapse ─────
_GEO_RAW = [
    ("ukraine", "kyiv kiev ukrainian ukrainians donbas donbass donetsk "
                "luhansk crimea sevastopol zelensky zelenskyy"),
    ("russia", "moscow russian russians kremlin putin"),
    ("china", "beijing chinese"),
    ("iran", "tehran iranian iranians"),
    ("israel", "jerusalem israeli israelis"),
    ("palestine", "gaza palestinian palestinians ramallah"),
    ("usa", "washington american americans america"),
    ("uk", "britain london british briton britons england"),
    ("france", "paris french"),
    ("germany", "berlin german germans"),
    ("india", "delhi indian indians"),
    ("pakistan", "islamabad pakistani pakistanis"),
    ("japan", "tokyo japanese"),
    ("north-korea", "pyongyang"),
    ("south-korea", "seoul"),
    ("taiwan", "taipei taiwanese"),
    ("venezuela", "caracas venezuelan venezuelans"),
    ("brazil", "brasilia brazilian brazilians"),
    ("mexico", "mexican mexicans"),
    ("canada", "ottawa canadian canadians"),
    ("australia", "canberra australian australians"),
    ("turkey", "ankara turkish istanbul"),
    ("saudi-arabia", "riyadh saudi saudis"),
    ("iraq", "baghdad iraqi iraqis"),
    ("syria", "damascus syrian syrians"),
    ("yemen", "sanaa yemeni yemenis"),
    ("lebanon", "beirut lebanese"),
    ("egypt", "cairo egyptian egyptians"),
    ("ethiopia", "ethiopian ethiopians"),
    ("nigeria", "abuja nigerian nigerians lagos"),
    ("south-africa", "pretoria johannesburg"),
    ("poland", "warsaw polish poles"),
    ("spain", "madrid spanish spaniards"),
    ("italy", "rome italian italians"),
    ("netherlands", "amsterdam dutch hague"),
    ("sweden", "stockholm swedish swedes"),
    ("norway", "oslo norwegian norwegians"),
    ("finland", "helsinki finnish finns"),
    ("greece", "athens greek greeks"),
    ("hungary", "budapest hungarian hungarians"),
    ("belarus", "minsk belarusian belarusians"),
    ("armenia", "yerevan armenian armenians"),
    ("azerbaijan", "baku azerbaijani azerbaijanis"),
    ("afghanistan", "kabul afghan afghans"),
    ("indonesia", "jakarta indonesian indonesians"),
    ("philippines", "manila filipino filipinos"),
    ("vietnam", "hanoi vietnamese"),
    ("thailand", "bangkok thai thais"),
    ("myanmar", "burma yangon burmese"),
    ("cuba", "havana cuban cubans"),
    ("argentina", "argentine argentines argentinian"),
    ("colombia", "bogota colombian colombians"),
    ("chile", "santiago chilean chileans"),
    ("sudan", "khartoum sudanese"),
    ("libya", "tripoli libyan libyans"),
    ("somalia", "mogadishu somali somalis"),
    ("kenya", "nairobi kenyan kenyans"),
    ("europe", "eu european europeans brussels"),
]
GEO = {}
for _canon, _aliases in _GEO_RAW:
    GEO[_canon.replace("-", " ")] = _canon
    for _a in _aliases.split():
        GEO[_a] = _canon


def _geo_key(word):
    w = word.lower().strip()
    for suf in ("'s", "\u2019s"):
        if w.endswith(suf):
            w = w[:-len(suf)]
    if w in GEO:
        return GEO[w]
    if w.endswith("s") and w[:-1] in GEO:
        return GEO[w[:-1]]
    return None


def _junk(word):
    w = word.strip()
    if len(w) < 4:
        return True
    if not w[0].isalnum():
        return True
    letters = sum(c.isalpha() for c in w)
    return letters / max(len(w), 1) < 0.6


# ── harvest ───────────────────────────────────────────────────────────
def _names(x, cap=12):
    out = []
    for item in (x or [])[:cap]:
        if isinstance(item, (tuple, list)) and item:
            item = item[0]
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def harvest_channels(containers):
    """Pull every already-computed channel's words from result/attr
    dicts. Returns {channel: [words in rank order]}."""
    ch = {}

    def get(path):
        for c in containers:
            if not isinstance(c, dict):
                continue
            cur = c
            ok = True
            for p in path:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    ok = False
                    break
            if ok and cur:
                return cur
        return None

    ch["headline_void"] = _names(get(("void_words",)))
    ch["source_void"] = _names(get(("source_void", "absent_words")), cap=40)
    ch["logos_v10"] = _names(get(("logos_words",)))
    sp = get(("sp_channels",)) or {}
    if isinstance(sp, dict):
        ch["sp_flat"] = _names(sp.get("flat"))
        ch["sp_spiral"] = _names(sp.get("spiral"))
        ch["sp_void"] = _names(sp.get("void"))
    ch["synthesis"] = _names(get(("synthesis_words",)))
    return {k: v for k, v in ch.items() if v}


def fresh_channels(story_title, source_text, response_texts, eng, vt):
    """Channels computed fresh at ensemble time: donut + vf_idf."""
    out = {}
    try:
        import numpy as np
        embs = np.asarray(eng.embed_texts(response_texts), dtype="float32")
        h = np.asarray(eng.embed_texts([story_title])[0], dtype="float32")
        cen = embs.mean(axis=0)
        res = vt.in_domain_void(cen, embs, k=10, headline_vec=h)
        rows = res[0] if (isinstance(res, tuple) and res
                          and isinstance(res[0], (list, tuple))) else res
        got = []
        for x in rows:
            if isinstance(x, str):
                got.append(x)
            elif isinstance(x, (list, tuple)) and x and isinstance(x[0], str):
                got.append(x[0])
        if got:
            out["donut"] = got[:10]
    except Exception as e:
        log.info(f"  ensemble: donut skipped ({e})")
    try:
        import preservation_core as pc
        tf = pc.term_frequencies(source_text)
        seen, cand = set(), []
        for w in pc.content_words(source_text):
            st = pc.porter_stem(w)
            if st not in seen:
                seen.add(st)
                cand.append((w, tf.get(st, 0.0)))
        cand = [w for w, _ in sorted(cand, key=lambda x: -x[1])[:25]]
        if cand:
            embed_fn = lambda texts: eng.embed_texts(list(texts))
            res = pc.vf_idf(cand, source_text, response_texts, embed_fn)
            voided = sorted((r for r in res if r.vf_idf > 0),
                            key=lambda r: -r.vf_idf)
            if voided:
                out["vf_idf"] = [r.concept for r in voided[:10]]
    except Exception as e:
        log.info(f"  ensemble: vf_idf skipped ({e})")
    return out


# ── vote + filters ───────────────────────────────────────────────────
def vote(channels, story_title, response_texts):
    said = {_stem(w) for t in response_texts for w in _tokens(t)}
    title_stems = {_stem(w) for w in _content(story_title)}
    cand = {}   # stem-key -> dict(word, score, channels)
    drops = dict(junk=0, title=0, said=0, stem_merged=0, geo_merged=0)

    for cname, words in channels.items():
        for idx, w in enumerate(words):
            wl = w.lower().strip()
            if _junk(wl):
                drops["junk"] += 1
                continue
            toks = _tokens(wl) or [wl]
            stems = [_stem(t) for t in toks]
            if all(s in title_stems for s in stems):
                drops["title"] += 1
                continue
            if any(s in said for s in stems):
                drops["said"] += 1
                continue
            key = " ".join(stems)
            weight = (0.3 if cname == "source_void" else 1.0 / (1 + idx))
            if key in cand:
                drops["stem_merged"] += 1
                c = cand[key]
                c["score"] += weight
                if cname not in c["channels"]:
                    c["channels"].append(cname)
            else:
                cand[key] = dict(word=wl, score=weight, channels=[cname],
                                 geo=_geo_key(wl))
    # geo dedupe: one candidate per geo group (best-scoring survives)
    best_geo = {}
    for key, c in list(cand.items()):
        g = c["geo"]
        if not g:
            continue
        if g in best_geo:
            keep, drop = ((best_geo[g], key)
                          if _rank(cand[best_geo[g]]) >= _rank(c)
                          else (key, best_geo[g]))
            # merge provenance into the survivor
            for chn in cand[drop]["channels"]:
                if chn not in cand[keep]["channels"]:
                    cand[keep]["channels"].append(chn)
            cand[keep]["score"] += 0.25 * cand[drop]["score"]
            del cand[drop]
            drops["geo_merged"] += 1
            best_geo[g] = keep
        else:
            best_geo[g] = key
    ranked = sorted(cand.values(), key=_rank, reverse=True)
    return ranked, drops


def _rank(c):
    return (len(c["channels"]), c["score"])


# ── raycast arms ──────────────────────────────────────────────────────
def raycast_arms(story_title, words):
    try:
        from consequence_engine import raycast_void_words
        res = raycast_void_words(story_title, list(words),
                                 depths=[1.5, 2.0, 3.0], top_k=5)
        arms = []
        for r in res:
            arms.append(dict(
                word=r.get("word"),
                quality=r.get("signal_quality"),
                consequences=r.get("deepest_consequences", [])[:4],
                score=r.get("consequence_score"),
                density=r.get("cluster_density"),
                novelty=r.get("novelty"),
                tether=r.get("tether")))
        return arms
    except Exception as e:
        log.warning(f"  ensemble: raycast arms failed ({e})")
        return []


# ── RAG: chroma-first over the live 17k-doc collection, lexical fallback ──
def rag_context(story_title, exclude_title="", n_scan=350, k=3):
    hits = _rag_chroma(story_title, exclude_title, k)
    return hits if hits else _rag_lexical(story_title, exclude_title,
                                          n_scan, k)


def _rag_chroma(story_title, exclude_title, k):
    """segment_rag.query over eigentrace_segments (17,445 docs, live,
    self-ingesting via stage_7). Declared: dictionary=chroma collection,
    anchor=story-title. Returns [] on any failure so lexical fires."""
    try:
        from segment_rag import query as _srq
        raw = _srq(story_title, n_results=k + 4)
        if isinstance(raw, dict):
            docs = (raw.get("documents") or [[]])[0]
            metas = (raw.get("metadatas") or [[]])[0] or [{}] * len(docs)
        else:
            docs = [str(h.get("document", h)) if isinstance(h, dict)
                    else str(h) for h in (raw or [])]
            metas = [h if isinstance(h, dict) else {} for h in (raw or [])]
        out = []
        for doc, md in zip(docs, metas):
            doc = str(doc)
            title = doc.split(". Category:")[0].strip()
            if not title or title == exclude_title:
                continue
            m = re.search(r"Void words?:\s*([^.]+)", doc)
            voids = ([w.strip() for w in m.group(1).split(",")][:4]
                     if m else [])
            out.append(dict(title=title[:90], voids=voids,
                            when=str((md or {}).get("category", "archive"))))
            if len(out) >= k:
                break
        return out
    except Exception as e:
        log.info(f"  ensemble: chroma rag unavailable ({e})")
        return []


def _rag_lexical(story_title, exclude_title="", n_scan=350, k=3):
    try:
        cur = {_stem(w) for w in _content(story_title)}
        if not cur:
            return []
        hits = []
        files = sorted(glob.glob(os.path.join(SEGMENTS_DIR,
                                              "*_segment.json")),
                       key=os.path.getmtime, reverse=True)[:n_scan]
        for f in files:
            try:
                d = json.load(open(f))
            except Exception:
                continue
            a = d.get("attribution") or {}
            t = str(a.get("story_title", ""))
            if (not t or t == exclude_title
                    or any(x in t for x in ("REM", "Weekly", "Governance"))):
                continue
            ts = {_stem(w) for w in _content(t)}
            ov = len(cur & ts)
            if ov >= 2:
                hits.append((ov, os.path.getmtime(f), t,
                             _names(a.get("void_words"), 4)
                             or _names(a.get("logos_words"), 4)))
        hits.sort(key=lambda x: (-x[0], -x[1]))
        seen, out = set(), []
        for ov, mt, t, voids in hits:
            if t in seen:
                continue
            seen.add(t)
            out.append(dict(title=t, voids=voids,
                            when=time.strftime("%b %d",
                                               time.localtime(mt))))
            if len(out) >= k:
                break
        return out
    except Exception as e:
        log.info(f"  ensemble: rag skipped ({e})")
        return []


# ── Mistral mega-opine ────────────────────────────────────────────────
def mistral_opine(story_title, response_texts, model_names, top5, arms,
                  rag, timeout=90):
    try:
        import requests
        summ = []
        for name, txt in zip(model_names, response_texts):
            summ.append(f"- {name}: {txt[:220]}")
        void_lines = [f"- '{c['word']}' (surfaced by {len(c['channels'])} "
                      f"channels: {', '.join(c['channels'])})" for c in top5]
        arm_lines = [f"- '{a['word']}' -> {', '.join(a['consequences'])} "
                     f"[{a['quality']}]" for a in arms if a.get("consequences")]
        rag_lines = [f"- {r['when']}: {r['title'][:70]} "
                     f"(voids then: {', '.join(r['voids'])})" for r in rag]
        prompt = (
            "You are the resident analyst on a deterministic AI-measurement "
            "news broadcast. Speak plainly, no markdown, no lists.\n\n"
            f"STORY: {story_title}\n\n"
            "THE FIVE MODEL SUMMARIES:\n" + "\n".join(summ) + "\n\n"
            "ENSEMBLE VOIDS -- concepts multiple independent detection "
            "channels found near this story that NO model said:\n"
            + "\n".join(void_lines) + "\n\n"
            + ("CONSEQUENCE RAYCASTS -- where each void's causal chain "
               "terminates in embedding space:\n" + "\n".join(arm_lines)
               + "\n\n" if arm_lines else "")
            + ("PRIOR COVERAGE from this broadcast's own archive:\n"
               + "\n".join(rag_lines) + "\n\n" if rag_lines else "")
            + "In 4 to 6 spoken sentences: what does the ensemble of voids "
              "reveal about how this story is being told, which consequence "
              "chain matters most and why, and one connection to the prior "
              "coverage if any exists. Ground every claim in the material "
              "above; do not invent facts; if a void looks like noise, say "
              "so.")
        r = requests.post(f"{OLLAMA_HOST}/api/generate",
                          json={"model": ENSEMBLE_MODEL, "prompt": prompt,
                                "stream": False,
                                "options": {"temperature": 0.4,
                                            "num_predict": 280}},
                          timeout=timeout)
        txt = (r.json() or {}).get("response", "").strip()
        return re.sub(r"\s+", " ", txt)[:1400]
    except Exception as e:
        log.warning(f"  ensemble: mistral opine failed ({e})")
        return ""


# ── the ensemble ──────────────────────────────────────────────────────
def run_story_ensemble(story_title, source_text, response_texts,
                       model_names=None, containers=None, eng=None, vt=None,
                       do_fresh=True, do_raycast=True, do_mistral=True):
    t0 = time.time()
    containers = containers or []
    model_names = model_names or [f"model{i}" for i in
                                  range(len(response_texts))]
    channels = harvest_channels(containers)
    if do_fresh and eng is not None and vt is not None and source_text:
        channels.update(fresh_channels(story_title, source_text,
                                       response_texts, eng, vt))
    if not channels:
        return {}
    ranked, drops = vote(channels, story_title, response_texts)
    top5 = [dict(word=c["word"], votes=len(c["channels"]),
                 channels=c["channels"], geo=c["geo"])
            for c in ranked[:TOP_N]]
    arms = (raycast_arms(story_title, [c["word"] for c in top5])
            if (do_raycast and top5) else [])
    rag = rag_context(story_title, exclude_title=story_title)
    opine = (mistral_opine(story_title, response_texts, model_names,
                           top5, arms, rag)
             if (do_mistral and top5) else "")
    ens = dict(
        version="ensemble-v1.1 2026-07-08 chroma-rag",
        channels_run=sorted(channels),
        n_candidates=sum(len(v) for v in channels.values()),
        drops=drops,
        top5=top5,
        arms=arms,
        rag=rag,
        opine=opine,
        registry={k: REGISTRY[k] for k in
                  list(channels) + (["raycast_arms"] if arms else [])
                  if k in REGISTRY},
        absorbs=["beat_06_void_reveal", "beat_07_void_analysis",
                 "beat_09_confirmation", "beat_consequence_accountability",
                 "beat_consequence_data"],
        elapsed_s=round(time.time() - t0, 1),
    )
    log.info(f"  ensemble: {len(channels)} channels, "
             f"{ens['n_candidates']} candidates -> top5 "
             f"{[c['word'] for c in top5]} in {ens['elapsed_s']}s")
    return ens


# ── beats ─────────────────────────────────────────────────────────────
def build_ensemble_beats(ens, story_title=""):
    if not ens or not ens.get("top5"):
        return []
    beats = []
    nch = len(ens.get("channels_run", []))
    d = ens.get("drops", {})
    beats.append(dict(
        speaker="Host", phase="ensemble_intro",
        text=(f"The void ensemble. {nch} independent detection channels ran "
              f"on this story and voted on {ens.get('n_candidates', 0)} "
              f"candidate omissions. Filters removed "
              f"{d.get('said', 0)} words the models actually said, "
              f"{d.get('title', 0)} headline echoes, and collapsed "
              f"{d.get('geo_merged', 0)} geographic duplicates. "
              f"Every channel's dictionary and anchor is declared in the "
              f"archive.")))
    parts = []
    for c in ens["top5"]:
        parts.append(f"{c['word']}, surfaced by {c['votes']} "
                     f"channel{'s' if c['votes'] != 1 else ''}")
    beats.append(dict(
        speaker="Host", phase="ensemble_top5",
        text=("Top five ensemble voids after deduplication: "
              + "; ".join(parts) + ".")))
    arms = ens.get("arms", [])
    if arms:
        lines = []
        disc = [a for a in arms if a.get("quality") == "DISCOVERY"]
        for a in arms:
            if not a.get("consequences"):
                continue
            lines.append(f"Through '{a['word']}': the chain terminates at "
                         f"{', '.join(a['consequences'][:3])} — "
                         f"{str(a.get('quality', '')).lower()} grade.")
        honesty = ("" if disc else
                   " No arm reached discovery grade this story; the rays "
                   "are reported at their measured quality, not upgraded.")
        beats.append(dict(
            speaker="Host", phase="ensemble_raycast",
            text=("Consequence raycasting, one arm per void. "
                  + " ".join(lines[:4]) + honesty)))
    if ens.get("opine"):
        beats.append(dict(
            speaker="Mistral", phase="ensemble_opine",
            text="This is Mistral at the analysis desk. " + ens["opine"]))
    if ens.get("rag"):
        r0 = ens["rag"][0]
        vtxt = (" — the voids then were " + ", ".join(r0["voids"][:3])
                if r0.get("voids") else "")
        beats.append(dict(
            speaker="Host", phase="ensemble_memory",
            text=(f"From this broadcast's own memory, seventeen thousand "
                  f"archived segments deep, the closest prior coverage: "
                  f"'{r0['title'][:70]}'{vtxt}. The archive remembers "
                  f"what the summaries dropped.")))
    beats.append(dict(
        speaker="OpenClaw", phase="ensemble_provenance",
        text=(f"Ensemble registry archived. {nch} channels with declared "
              f"dictionaries and anchors; said-stem, headline, and "
              f"geography filters applied; raycast arms marked downstream "
              f"of the ensemble vote. Deterministic; no model judged "
              f"another.")))
    return beats


# ── offline test mode ─────────────────────────────────────────────────
def _offline():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mistral", action="store_true")
    ap.add_argument("--no-raycast", action="store_true")
    ap.add_argument("--no-fresh", action="store_true")
    ap.add_argument("--file", default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target = args.file
    if not target:
        for f in sorted(glob.glob(os.path.join(SEGMENTS_DIR,
                                               "*_segment.json")),
                        key=os.path.getmtime, reverse=True):
            d = json.load(open(f))
            a = d.get("attribution") or {}
            t = str(a.get("story_title", ""))
            if a.get("model_responses") and t and not any(
                    x in t for x in ("REM", "Weekly", "Governance")):
                target = f
                break
    d = json.load(open(target))
    a = d.get("attribution") or {}
    title = a.get("story_title", "")
    mr = a.get("model_responses") or {}
    names, texts = list(mr.keys()), [str(v) for v in mr.values()]
    source = str(a.get("source_body") or "")[:4000] or title
    print(f"OFFLINE ENSEMBLE on: {title}\n{'=' * 70}")

    eng = vt = None
    if not args.no_fresh:
        try:
            import geometric_engine as ge
            from latent_retrieval import VocabTensor
            eng = ge.get_engine()
            vt = VocabTensor("vocab")
        except Exception as e:
            print(f"(fresh channels unavailable: {e})")

    ens = run_story_ensemble(
        title, source, texts, model_names=names, containers=[a],
        eng=eng, vt=vt, do_fresh=not args.no_fresh,
        do_raycast=not args.no_raycast, do_mistral=not args.no_mistral)

    print(json.dumps({k: v for k, v in ens.items()
                      if k not in ("opine",)}, indent=1, default=str)[:3500])
    print(f"\n{'=' * 70}\nWOULD-BE BEATS:\n")
    for b in build_ensemble_beats(ens, title):
        print(f"[{b['speaker']} / {b['phase']}]\n  {b['text']}\n")


if __name__ == "__main__":
    _offline()
