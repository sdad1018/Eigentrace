#!/usr/bin/env python3
"""
beat3_service.py — EigenTrace "Summary Plus" surfacing endpoint.
KEYLESS. Calls NO paid API. bge + the full 50k clean tensor (float16). One endpoint.

Pipeline (the validated full method):
  paste raw story -> embed -> DONUT (re-anchored 0.3/0.7) surfaces on-topic-ABSENT
  concepts -> COMPOSE each with the story (validated: reaches story-specific concepts)
  -> BREADTH-RANK (validated: productive concepts open broader neighborhoods) ->
  surface the broad, story-specific omissions + a ready-to-paste prompt for the
  user's own LLM.

Honest label: these are STORY-SPECIFIC PRODUCTIVE OMISSIONS (concepts on-topic yet
absent that open broad explanatory neighborhoods) — NOT "consequences" (bge encodes
similarity, not causality; we validated retrieval/conditioning, not causation).

SECURITY (Option 2 — isolated keyless VPS, NEVER Bertha):
  - holds NO secrets, NO .env, NO repo, NO provider keys. Compromise yields only a
    public model + public tensor.
  - input capped (MAX_CHARS), single endpoint, rate-limit + CORS via the reverse
    proxy (Caddy) in the runbook. Treats pasted text as untrusted: text->vector
    math->concepts, no eval/shell/file ops on input.

Deploy: behind Caddy (HTTPS, rate-limit, CORS to eigentrace.ai), ufw 443 only.
Run:  uvicorn beat3_service:app --host 127.0.0.1 --port 8000   (Caddy proxies 443->8000)

Files needed ON THE VPS (copy from Bertha, both public/derivable):
  global_vocab_clean.json, global_vocab_clean.pt   (the 50k clean tensor)
bge downloads from HF on first run.
"""
import json, os, re
import numpy as np

# ---------- config ----------
VOCAB_JSON = os.environ.get("EIGEN_VOCAB_JSON", "global_vocab_clean.json")
VOCAB_PT   = os.environ.get("EIGEN_VOCAB_PT",   "global_vocab_clean.pt")
MAX_CHARS  = 50_000          # cap the paste (~7-8k words) — no novels
TOPK_DONUT = 16              # void candidates from the donut
TOPK_NN    = 12              # neighborhood size for composition + breadth
N_SURFACE  = 8               # how many productive omissions to return
HEAD_W, CENT_W = 0.3, 0.7    # validated re-anchor blend
OUTER      = 0.58            # validated outer threshold

# ---------- load model + tensor ONCE at startup ----------
print("loading bge + clean tensor (float16)...", flush=True)
import torch
from sentence_transformers import SentenceTransformer
_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
def _embed(texts):
    v = _model.encode(texts, normalize_embeddings=True)
    return np.asarray(v, dtype=np.float32)

_V = torch.load(VOCAB_PT, weights_only=False).numpy().astype(np.float32)
_V = _V / (np.linalg.norm(_V, axis=1, keepdims=True) + 1e-8)
_V16 = _V.astype(np.float16)                    # float16: validated lossless, half RAM
_words = json.load(open(VOCAB_JSON))
_words = _words["words"] if isinstance(_words, dict) else _words
_widx = {w: i for i, w in enumerate(_words)}
print(f"tensor: {_V16.nbytes/1e6:.0f}MB, {len(_words)} concepts", flush=True)

# words too generic to surface as "omissions" (stop-ish / meta)
_STOP = set("the a an and or but news report says said story article".split())

def _nn(vec, k=TOPK_NN):
    s = (_V16.astype(np.float32)) @ vec       # store f16, compute f32 (validated identical)
    idx = np.argsort(-s)[:k]
    return [(_words[i], float(s[i])) for i in idx]

def _nn_words(vec, k=TOPK_NN):
    return [w for w, _ in _nn(vec, k)]

def _breadth(word):
    if word not in _widx: return 0.0
    v = _V[_widx[word]]
    nbrs = _nn(v, TOPK_NN)
    vecs = np.array([_V[_widx[w]] for w, _ in nbrs if w in _widx])
    if len(vecs) < 3: return 0.0
    S = vecs @ vecs.T; n = len(vecs)
    return 1.0 - (S.sum() - n) / (n*n - n)     # higher = broader neighborhood

def _compose(a, b, alpha=0.5):
    q = (1-alpha)*a + alpha*b
    return q / (np.linalg.norm(q) + 1e-8)

def surface(title: str, text: str):
    """The full pipeline. Returns surfaced productive omissions + a prompt block."""
    title = (title or "").strip()[:500]
    text  = (text or "").strip()[:MAX_CHARS]
    if len(text) < 40:
        return {"error": "Please paste a longer story (at least a few sentences)."}

    # 1) EMBED — story centroid from chunks (proxy for the 'consensus' anchor)
    chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+', text) if len(c.strip()) > 20]
    if not chunks: chunks = [text]
    cvecs = _embed(chunks[:40])
    centroid = cvecs.mean(0); centroid /= np.linalg.norm(centroid) + 1e-8
    hv = _embed([title])[0] if title else centroid
    blend = HEAD_W*hv + CENT_W*centroid; blend /= np.linalg.norm(blend) + 1e-8

    # 2) DONUT — concepts near the story but ABSENT from its own text
    present = set()
    tl = text.lower()
    # mark vocab concepts literally present in the text (so we surface only ABSENT ones)
    sims = (_V16.astype(np.float32)) @ blend
    cand_idx = np.argsort(-sims)[:200]          # 200 nearest concepts to the story
    donut = []
    for i in cand_idx:
        w = _words[i]
        if w in _STOP: continue
        if w.lower() in tl: continue            # ABSENT only: skip if literally in story
        # re-anchored band: near the blend but not a trivial top hit
        if sims[i] < OUTER: continue
        donut.append(w)
        if len(donut) >= TOPK_DONUT: break

    if not donut:
        return {"error": "No clear on-topic absent concepts surfaced; try a longer or more specific story."}

    # 3) COMPOSE each void with the story -> story-specific reachable concepts
    #    + 4) BREADTH-RANK: keep concepts that open broad neighborhoods
    scored = []
    seen = set()
    for void_w in donut:
        if void_w not in _widx: continue
        vv = _V[_widx[void_w]]
        Q = _compose(centroid, vv)
        reach = _nn_words(Q, TOPK_NN)
        # the conditioned, story-specific concepts (not in story text, not the void itself)
        for w in reach:
            if w in seen or w in _STOP: continue
            if w.lower() in tl: continue
            seen.add(w)
            b = _breadth(w)
            scored.append({"concept": w, "breadth": round(b, 3), "via": void_w})

    # rank by breadth (validated: productive omissions open broader neighborhoods)
    scored.sort(key=lambda x: -x["breadth"])
    top = scored[:N_SURFACE]

    # build the user-facing prompt block (they feed THEIR llm)
    concept_list = ", ".join(t["concept"] for t in top)
    prompt_block = (
        "Here are concepts that are on-topic for this story but were absent from a "
        "standard summary of it. Rewrite the summary to incorporate the ones that "
        "genuinely fit the source; ignore any that don't. Do not invent facts.\n\n"
        f"STORY:\n{title}\n\nSURFACED CONCEPTS: {concept_list}"
    )

    return {
        "title": title,
        "surfaced": top,                         # [{concept, breadth, via}]
        "donut_voids": donut,                    # the absent concepts the donut found
        "prompt_block": prompt_block,
        "note": "Story-specific productive omissions — concepts on-topic yet absent that "
                "open broad explanatory neighborhoods. Not causal 'consequences'.",
    }

# ---------- self-check on startup ----------
def _selfcheck():
    demo = ("Iran and the United States reached an agreement to de-escalate tensions in "
            "the Persian Gulf after weeks of confrontation near the Strait of Hormuz. "
            "Officials said shipping would resume and both sides claimed a diplomatic win.")
    out = surface("US and Iran reach deal to ease Gulf tensions", demo)
    print("SELF-CHECK surfaced:", [s["concept"] for s in out.get("surfaced", [])], flush=True)

# ---------- FastAPI app ----------
try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    app = FastAPI(title="EigenTrace Summary Plus", docs_url=None, redoc_url=None)
    # CORS — lock to your site in production (also enforced at Caddy)
    app.add_middleware(CORSMiddleware,
        allow_origins=["https://eigentrace.ai"], allow_methods=["POST"], allow_headers=["*"])

    class StoryIn(BaseModel):
        title: str = ""
        text: str = ""

    @app.post("/surface")
    def do_surface(s: StoryIn):
        return surface(s.title, s.text)

    @app.get("/health")
    def health(): return {"ok": True, "concepts": len(_words)}
except Exception as e:
    print("FastAPI not available (fine for local test):", e)
    app = None

if __name__ == "__main__":
    _selfcheck()
