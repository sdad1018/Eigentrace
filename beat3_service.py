#!/usr/bin/env python3
"""
beat3_service.py — EigenTrace "Summary Plus" surfacing endpoint.
KEYLESS. Calls NO paid API. bge + full 50k clean tensor (float16, validated lossless).

Pipeline (validated: composition + breadth; tuned via the stimulus bake-off):
  paste story -> embed -> DONUT (re-anchored 0.3/0.7) surfaces on-topic-ABSENT
  concepts -> COMPOSE each with the story -> BREADTH-RANK -> surface the productive
  omissions, TAGGED by type:
    FRAME concept   (appeasement, arms race, proxy war): names the story's stakes
                    -> framed for the user as "the stakes/argument".
    ABSENT-ACTOR    (majlis, HRW, Rouhani, UN): thematically load-bearing but NOT a
                    participant in this event -> framed as "the THEME it represents
                    (HRW -> humanitarian oversight; majlis -> Iran's internal politics)",
                    NEVER as an active participant. This avoids the "HRW is watching
                    closely" false-participant trap that makes a user sound like they're
                    name-dropping things absent from the story.

Bake-off finding: composition reaches FRAMES (gold for sounding like you understood
the argument); raw donut surfaces ACTORS (gold ONLY if framed as theme, trap if framed
as participant). So we keep both, tag them, and frame each correctly.

Honest label: story-specific productive omissions + their themes. NOT causal
consequences (bge = similarity, not causality).

SECURITY (Option 2 — isolated keyless VPS, NEVER Bertha): no secrets, no .env, no
provider keys, input-capped, single endpoint, rate-limit/CORS via Caddy (see runbook).
"""
import json, os, re
import numpy as np

VOCAB_JSON = os.environ.get("EIGEN_VOCAB_JSON", "global_vocab_clean.json")
VOCAB_PT   = os.environ.get("EIGEN_VOCAB_PT",   "global_vocab_clean.pt")
MAX_CHARS  = 50_000
TOPK_DONUT = 16
TOPK_NN    = 12
N_FRAME    = 5     # frame/stakes concepts to surface
N_ACTOR    = 4     # absent-actor concepts to surface (as themes)
HEAD_W, CENT_W = 0.3, 0.7
OUTER      = 0.58

print("loading bge + clean tensor (float16)...", flush=True)
import torch
from sentence_transformers import SentenceTransformer
_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
def _embed(texts):
    return np.asarray(_model.encode(texts, normalize_embeddings=True), dtype=np.float32)

_V = torch.load(VOCAB_PT, weights_only=False).numpy().astype(np.float32)
_V = _V / (np.linalg.norm(_V, axis=1, keepdims=True) + 1e-8)
_V16 = _V.astype(np.float16)
_words = json.load(open(VOCAB_JSON))
_words = _words["words"] if isinstance(_words, dict) else _words
_widx = {w: i for i, w in enumerate(_words)}
print(f"tensor: {_V16.nbytes/1e6:.0f}MB, {len(_words)} concepts", flush=True)

_STOP = set("the a an and or but news report says said story article".split())
_HARD_DROP = {"realdonaldtrump","glazer","teheran","mideast","ticker","scotus","gops","wot"}

def _nn(vec, k=TOPK_NN):
    s = (_V16.astype(np.float32)) @ vec
    return [(_words[i], float(s[i])) for i in np.argsort(-s)[:k]]
def _nn_words(vec, k=TOPK_NN):
    return [w for w, _ in _nn(vec, k)]
def _breadth(word):
    if word not in _widx: return 0.0
    nbrs = _nn(_V[_widx[word]], TOPK_NN)
    vecs = np.array([_V[_widx[w]] for w, _ in nbrs if w in _widx])
    if len(vecs) < 3: return 0.0
    S = vecs @ vecs.T; n = len(vecs)
    return 1.0 - (S.sum() - n) / (n*n - n)
def _compose(a, b, alpha=0.5):
    q = (1-alpha)*a + alpha*b
    return q / (np.linalg.norm(q) + 1e-8)

# --- NORMALIZE, don't filter. A concept surfaced in an inflected/adverbial form
# (diplomatically, airstrikes) is REAL signal in the wrong surface shape. We map it
# to its concept stem and KEEP it, rather than deleting it on a syntactic technicality
# (which would be lobotomizing — 'diplomatically' carries the live 'diplomacy' frame).
# A few irregular maps + light rules. NOT a blocklist.
_LEMMA = {
    "diplomatically":"diplomacy","diplomatic":"diplomacy",
    "geopolitically":"geopolitics","geopolitical":"geopolitics",
    "economically":"economics","militarily":"military","strategically":"strategy",
    "politically":"politics","ideologically":"ideology",
}
def _normalize(concept):
    c = concept.lower().strip()
    if c in _LEMMA: return _LEMMA[c]
    # adverbs: '...ly' -> try the adjective/concept root, but KEEP the word (don't drop)
    if c.endswith("ly") and len(c) > 5:
        root = c[:-2]
        if root.endswith("al"): root = root[:-2]   # diplomatical-ly handled above; generic -ally
        # only remap if the root is itself a plausible concept token in vocab
        if root in _widx: return root
        # else keep the original adverb (still signal; better than deleting)
        return c
    # simple plural -> singular when the singular is in vocab (airstrikes -> airstrike)
    if c.endswith("s") and len(c) > 4 and c[:-1] in _widx:
        return c[:-1]
    return c

# --- concept-type heuristic: ACTOR/institution vs FRAME/abstract ---
# actor concepts: proper-noun-ish single tokens, acronyms, named entities. We can't POS-tag
# cheaply, so: a concept is ACTOR-ish if it's a single token that is an acronym (all-ish
# caps in source vocab is lost, so use length+no-space+known-entity heuristics) OR matches
# a small known-entity lexicon. Multi-word abstract phrases (arms race, proxy war) are FRAMEs.
_KNOWN_ACTORS = set("""majlis hrw unsc un nato opec iaea wto imf fars sadr rouhani khamenei
hezbollah hamas idf cia fbi knesset duma kremlin pentagon unrwa hrc dprk apec usmca nafta
brics potus scotus""".split())
def _is_actor(concept):
    # LEXICON-ONLY: a concept is an actor ONLY if it's a known named entity/institution.
    # We deliberately do NOT guess "short token = actor" — that was lobotomizing (it swept
    # up abstract frames like 'truce'). Unknown entities fall to FRAMES (the safer error:
    # a frame-framed actor is far less harmful than an abstract word mis-tagged as an actor).
    c = concept.lower().strip()
    return c in _KNOWN_ACTORS

# theme-translation for common absent-actors (so the model frames them as themes)
_ACTOR_THEME = {
    "hrw":"humanitarian oversight and human-rights scrutiny",
    "hrc":"human-rights scrutiny",
    "unrwa":"humanitarian relief and refugee stakes",
    "unsc":"international authority and the limits of multilateral response",
    "un":"international authority and multilateral response",
    "nato":"the Western security alliance dimension",
    "iaea":"nuclear inspection and verification",
    "opec":"oil-supply and energy-leverage dynamics",
    "wto":"the global-trade-rules dimension",
    "majlis":"Iran's internal political machinery",
    "fars":"Iran's domestic/provincial dimension",
    "sadr":"factional and sectarian political forces",
    "rouhani":"Iran's prior political leadership and internal factions",
    "khamenei":"Iran's ultimate political authority",
    "hezbollah":"the regional proxy/militia dimension",
    "dprk":"the nuclear-rogue-state parallel",
}

def surface(title: str, text: str):
    title = (title or "").strip()[:500]
    text  = (text or "").strip()[:MAX_CHARS]
    if len(text) < 40:
        return {"error": "Please paste a longer story (at least a few sentences)."}

    chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+', text) if len(c.strip()) > 20]
    if not chunks: chunks = [text]
    cvecs = _embed(chunks[:40])
    centroid = cvecs.mean(0); centroid /= np.linalg.norm(centroid) + 1e-8
    hv = _embed([title])[0] if title else centroid
    blend = HEAD_W*hv + CENT_W*centroid; blend /= np.linalg.norm(blend) + 1e-8

    tl = text.lower()
    sims = (_V16.astype(np.float32)) @ blend
    cand_idx = np.argsort(-sims)[:200]
    donut = []
    for i in cand_idx:
        w = _words[i]
        if w in _STOP or w in _HARD_DROP: continue
        if w.lower() in tl: continue
        if sims[i] < OUTER: continue
        donut.append(w)
        if len(donut) >= TOPK_DONUT: break
    if not donut:
        return {"error": "No clear on-topic absent concepts surfaced; try a longer story."}

    # compose each void with the story -> story-specific reach, breadth-ranked, tagged
    frame_pool, actor_pool = [], []
    seen = set()
    def consider(w, via):
        # NORMALIZE (keep signal, fix form) then dedup against the story (drop only if the
        # concept is already present — this catches corrupted variants like 'irani'->'iranian'
        # WITHOUT any junk-blocklist; an absent normalized concept always survives).
        norm = _normalize(w)
        if norm in seen or norm in _STOP or norm in _HARD_DROP: return
        if norm.lower() in tl: return          # already in story -> not an omission
        seen.add(norm)
        if _is_actor(norm):
            actor_pool.append({"concept": norm, "breadth": round(_breadth(norm), 3), "via": via,
                               "theme": _ACTOR_THEME.get(norm, None)})
        else:
            frame_pool.append({"concept": norm, "breadth": round(_breadth(norm), 3), "via": via})
    for void_w in donut:
        if void_w not in _widx: continue
        Q = _compose(centroid, _V[_widx[void_w]])
        for w in _nn_words(Q, TOPK_NN):
            consider(w, void_w)
        # also consider the raw void itself (esp. actors the donut found)
        consider(void_w, void_w)

    frame_pool.sort(key=lambda x: -x["breadth"])
    actor_pool.sort(key=lambda x: -x["breadth"])
    frames = frame_pool[:N_FRAME]
    actors = actor_pool[:N_ACTOR]

    # build the user-facing prompt block with PER-TYPE framing
    frame_list = ", ".join(f["concept"] for f in frames)
    actor_lines = []
    for a in actors:
        theme = a.get("theme") or f"the broader theme it represents"
        actor_lines.append(f"{a['concept']} (invoke as: {theme})")
    actor_list = "; ".join(actor_lines)

    prompt_block = (
        "Rewrite a summary of this story, working in the concepts below that genuinely fit. "
        "Invent no facts.\n\n"
        f"STORY: {title}\n\n"
        f"FRAME / STAKES concepts (work these in as what the story is really about): {frame_list}\n\n"
        f"THEME concepts (these are NOT participants in this event — invoke each only as the "
        f"underlying theme noted in parentheses, never as an active player): {actor_list}"
    )

    return {
        "title": title,
        "frames": frames,            # [{concept, breadth, via}] — the stakes/argument
        "themes": actors,            # [{concept, breadth, via, theme}] — absent-actors as themes
        "donut_voids": donut,
        "prompt_block": prompt_block,
        "note": "FRAME concepts name the story's stakes (repeating them signals you grasped the "
                "argument). THEME concepts are absent from the event itself — invoke them as the "
                "underlying theme they represent, not as participants. Productive omissions via "
                "composition+breadth; not causal consequences.",
    }

def _selfcheck():
    demo = ("Iran and the United States are looking ahead to another round of talks to de-escalate "
            "tensions near the Strait of Hormuz, even as the conflict continues and both sides claim "
            "leverage.")
    out = surface("Iran War Live Updates: U.S. and Iran Look Ahead to Next Round of Talks", demo)
    print("FRAMES:", [f["concept"] for f in out.get("frames", [])], flush=True)
    print("THEMES:", [(a["concept"], a.get("theme")) for a in out.get("themes", [])], flush=True)
    print("\nPROMPT BLOCK:\n", out.get("prompt_block",""), flush=True)

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    app = FastAPI(title="EigenTrace Summary Plus", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["https://eigentrace.ai"],
                       allow_methods=["POST"], allow_headers=["*"])
    class StoryIn(BaseModel):
        title: str = ""
        text: str = ""
    @app.post("/surface")
    def do_surface(s: StoryIn): return surface(s.title, s.text)
    @app.get("/health")
    def health(): return {"ok": True, "concepts": len(_words)}
except Exception as e:
    print("FastAPI not available (fine for local test):", e); app = None

if __name__ == "__main__":
    _selfcheck()
