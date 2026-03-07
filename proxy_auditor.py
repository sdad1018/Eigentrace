#!/usr/bin/env python3
"""
proxy_auditor.py — Big 5 Proxy Audit Engine
=============================================
Monitors RSS feeds, scores headline importance via local surprisal,
runs Big 5 (ChatGPT/Claude/Gemini/DeepSeek/Grok) on high-importance
stories, detects cross-model callouts (asymmetric RLHF friction),
and runs geometric consensus analysis (least-variance direction).

Runs continuously. Skips models with no API key. Writes callouts
to the broadcast ticker. Logs everything to JSONL.

Part of the eigentrace monorepo.
Author: remvelchio
"""

from __future__ import annotations

import os, time, math, json, re, hashlib, logging
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from eigentrace import score as eigentrace_score
import geometric_engine as ge
import numpy as np

console = Console()
log = logging.getLogger("proxy_auditor")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

OLLAMA_URL     = os.getenv("OLLAMA_OPENAI_URL",
                            "http://localhost:11434/v1/completions")
PROXY_MODEL    = os.getenv("PROXY_MODEL", "mistral:7b-text")
TOPK           = int(os.getenv("TOPK", "20"))
MAX_PROXY_TOK  = int(os.getenv("MAX_PROXY_TOKENS", "260"))

IMPORTANCE_HIGH    = float(os.getenv("IMPORTANCE_HIGH",    "4.5"))
IMPORTANCE_MEDIUM  = float(os.getenv("IMPORTANCE_MEDIUM",  "3.0"))
CALLOUT_MULTIPLIER = float(os.getenv("CALLOUT_MULTIPLIER", "2.5"))

TICKER_FILE = Path(os.getenv("TICKER_FILE",
                              "/home/remvelchio/agent/tmp/ticker.txt"))
SEEN_FILE   = Path(os.getenv("SEEN_FILE",
                              "/home/remvelchio/agent/tmp/seen_stories.json"))
AUDIT_LOG   = Path(os.getenv("AUDIT_LOG",
                              "/mnt/c/Users/M4ISI/eigentrace/audit_log.jsonl"))

POLL_INTERVAL     = int(os.getenv("POLL_INTERVAL",     "90"))
STORIES_PER_CYCLE = int(os.getenv("STORIES_PER_CYCLE", "3"))

OPENAI_MODEL    = os.getenv("OPENAI_MODEL",    "gpt-4o")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL",    "gemini-2.5-flash")
DEEPSEEK_MODEL  = os.getenv("DEEPSEEK_MODEL",  "deepseek-chat")
GROK_MODEL      = os.getenv("GROK_MODEL",      "grok-4-fast-non-reasoning")

FEEDS = [
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",        "cat": "war",       "pri": 1},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",           "cat": "war",       "pri": 1},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",                      "cat": "war",       "pri": 1},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml",                        "cat": "war",       "pri": 1},
    {"url": "https://rss.dw.com/rdf/rss-en-world",                              "cat": "war",       "pri": 1},
    {"url": "https://feeds.skynews.com/feeds/rss/world.xml",                    "cat": "war",       "pri": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",                      "cat": "war",       "pri": 1},
    {"url": "https://www.weather.gov/rss_page.php?site_name=nws",               "cat": "incidents", "pri": 1},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                   "cat": "markets",   "pri": 2},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",            "cat": "markets",   "pri": 2},
    {"url": "https://www.marketwatch.com/rss/topstories",                       "cat": "markets",   "pri": 2},
    {"url": "https://www.investing.com/rss/news_25.rss",                        "cat": "markets",   "pri": 2},
    {"url": "https://techcrunch.com/feed/",                                     "cat": "tech",      "pri": 2},
    {"url": "https://www.theverge.com/rss/index.xml",                           "cat": "tech",      "pri": 2},
    {"url": "https://www.wired.com/feed/rss",                                   "cat": "tech",      "pri": 2},
    {"url": "https://feeds.arstechnica.com/arstechnica/index",                  "cat": "tech",      "pri": 2},
    {"url": "https://krebsonsecurity.com/feed/",                                "cat": "cyber",     "pri": 2},
    {"url": "https://news.ycombinator.com/rss",                                 "cat": "dev",       "pri": 3},
    {"url": "https://www.sciencedaily.com/rss/all.xml",                         "cat": "science",   "pri": 3},
    {"url": "https://www.nature.com/nature.rss",                                "cat": "science",   "pri": 3},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/",                  "cat": "crypto",    "pri": 3},
    {"url": "https://cointelegraph.com/rss",                                    "cat": "crypto",    "pri": 3},
    {"url": "https://www.atlasobscura.com/feeds/latest",                        "cat": "esoterica", "pri": 5},
]

# ── dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Story:
    guid:       str
    title:      str
    summary:    str
    url:        str
    category:   str
    priority:   int
    published:  str
    importance: float = 0.0
    directness: float = 0.0

@dataclass
class ModelResponse:
    name:       str
    text:       str
    eigen_vix:  float = 0.0
    surp_vix:   float = 0.0   # token surprisal score (preserved after geo rewrite)
    tokens:     list  = field(default_factory=list)
    surprisals: list  = field(default_factory=list)
    skipped:        bool  = False
    error:          str   = ""
    void_proximity: dict  = field(default_factory=dict)  # {word: cosine_sim_to_response}

@dataclass
class AuditRecord:
    timestamp:       str
    story_guid:      str
    story_title:     str
    category:        str
    importance:      float
    responses:       list
    callouts:        list
    ticker_line:     str
    geo_top_concept:      str   = ""
    geo_density:          float = 0.0
    geo_concepts:         list  = field(default_factory=list)
    spectral_resonance:        float = 0.0
    spectral_interference:     float = 0.0
    spectral_entropy:          float = 0.0
    svd_consensus_compression:    float = 0.0
    svd_null_space_energy:        float = 0.0
    svd_reconstruction_alignment: float = 0.0
    synthesis_words:              list  = field(default_factory=list)

# ── seen-story cache ──────────────────────────────────────────────────────────

def _load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except Exception:
            pass
    return {"guids": {}}

def _save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=1))

def _mark_seen(seen: dict, guid: str) -> None:
    seen["guids"][guid] = time.time()
    cutoff = time.time() - 172800
    seen["guids"] = {k: v for k, v in seen["guids"].items() if v > cutoff}

# ── helpers ───────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\s+|[^\s]+")

def _safe_exp(x: float) -> float:
    try:
        return math.exp(x)
    except OverflowError:
        return 0.0

def _guid(url: str, title: str) -> str:
    return hashlib.md5(f"{url}:{title}".encode()).hexdigest()

# ── feed fetching ─────────────────────────────────────────────────────────────

def fetch_feed(feed: dict, timeout: int = 15) -> list:
    stories = []
    try:
        r = requests.get(feed["url"], timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        log.warning(f"Feed fetch failed {feed['url']}: {e}")
        return []

    items = root.findall(".//item") or \
            root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items[:10]:
        def _t(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        def _at(tag):
            el = item.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
            return el.text.strip() if el is not None and el.text else ""

        title   = _t("title")   or _at("title")
        summary = _t("description") or _t("summary") or _at("summary") or ""
        link    = _t("link")    or _at("link") or ""
        pub     = _t("pubDate") or _t("published") or _at("published") or ""
        guid    = _t("guid")    or _guid(feed["url"], title)

        if not title:
            continue

        summary = re.sub(r"<[^>]+>", "", summary)[:500]
        stories.append(Story(
            guid=guid, title=title, summary=summary,
            url=link, category=feed["cat"], priority=feed["pri"],
            published=pub,
        ))
    return stories

# ── importance scoring ────────────────────────────────────────────────────────

# ── local transformers scorer (REMOVED: Mistral-7B deprecated) ──────
# Replaced by BGE-large embedding distance surprisal (LogosLossV9)
# _get_hf_model and _score_token_logprob removed to free VRAM

def _score_token_logprob(prefix: str, next_tok: str) -> Optional[float]:
    """Stub: was Mistral logprob. Now returns None; callers fall back to FLOOR."""
    return None

FLOOR = 11.5

def score_importance(text: str) -> float:
    tokens = [t for t in _TOKEN_RE.findall(text) if not t.isspace()][:40]
    if not tokens:
        return 0.0
    prefix     = ""
    surprisals = []
    for tok in tokens:
        lp = _score_token_logprob(prefix, tok)
        surprisals.append(-lp if lp is not None else FLOOR)
        prefix += tok
    return sum(surprisals) / len(surprisals)

def fast_importance(title: str, category: str, priority: int) -> float:
    base           = eigentrace_score(title).directness_score
    category_bonus = {"war": 2.0, "incidents": 1.8, "cyber": 1.5,
                      "tech": 1.2, "markets": 1.1}.get(category, 1.0)
    priority_bonus = 1.0 + (5 - priority) * 0.1
    return base * category_bonus * priority_bonus

# ── LLM callers ───────────────────────────────────────────────────────────────

def _prompt_for_story(story: Story) -> str:
    return (
        f"Breaking news: {story.title}\n"
        f"Summary: {story.summary[:300]}\n\n"
        "In exactly 2 sentences: what happened and one concrete implication. "
        "Be direct. No disclaimers."
    )

def call_openai(prompt: str) -> tuple:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return "", "no_key"
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL,
                  "messages": [
                      {"role": "system", "content": "Be direct. 2 sentences."},
                      {"role": "user",   "content": prompt}],
                  "temperature": 0.0},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), ""
    except Exception as e:
        return "", str(e)

def call_anthropic(prompt: str) -> tuple:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return "", "no_key"
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": ANTHROPIC_MODEL, "max_tokens": 220,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        r.raise_for_status()
        txt = "".join(p["text"] for p in r.json().get("content", [])
                      if p.get("type") == "text")
        return txt.strip(), ""
    except Exception as e:
        return "", str(e)

def call_gemini(prompt: str) -> tuple:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return "", "no_key"
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        r.raise_for_status()
        cands = r.json().get("candidates", [])
        txt   = "".join(p.get("text", "")
                        for p in cands[0].get("content", {}).get("parts", [])
                        ) if cands else ""
        return txt.strip(), ""
    except Exception as e:
        return "", str(e)

def call_deepseek(prompt: str) -> tuple:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return "", "no_key"
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL,
                  "messages": [
                      {"role": "system", "content": "Be direct. 2 sentences."},
                      {"role": "user",   "content": prompt}],
                  "temperature": 0.0},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), ""
    except Exception as e:
        return "", str(e)

def call_grok(prompt: str) -> tuple:
    key = os.getenv("XAI_API_KEY", "").strip()
    if not key:
        return "", "no_key"
    try:
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": GROK_MODEL,
                  "messages": [
                      {"role": "system", "content": "Be direct. 2 sentences."},
                      {"role": "user",   "content": prompt}],
                  "temperature": 0.0},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), ""
    except Exception as e:
        return "", str(e)

BIG5_CALLERS = {
    "ChatGPT":  call_openai,
    "Claude":   call_anthropic,
    "Gemini":   call_gemini,
    "DeepSeek": call_deepseek,
    "Grok":     call_grok,
}

# ── proxy audit ───────────────────────────────────────────────────────────────

def proxy_audit_text(text: str) -> tuple:
    tokens     = [t for t in _TOKEN_RE.findall(text or "")][:MAX_PROXY_TOK]
    prefix     = ""
    surprisals = []
    for tok in tokens:
        if tok.isspace():
            surprisals.append(0.0)
            prefix += tok
            continue
        lp = _score_token_logprob(prefix, tok)
        surprisals.append(-lp if lp is not None else FLOOR)
        prefix += tok
    scored = [(t, s) for t, s in zip(tokens, surprisals) if not t.isspace()]
    if not scored:
        return 0.0, tokens, surprisals
    hard = sum(1 for _, s in scored if s >= 10.0)
    mid  = sum(1 for _, s in scored if 6.0 <= s < 10.0)
    vix  = 100.0 * (0.75 * hard + 0.35 * mid) / max(1, len(scored))
    return max(0.0, min(100.0, vix)), tokens, surprisals

def eigen_label(e: float) -> str:
    if e >= 85: return "Ideological Overwrite"
    if e >= 60: return "Severe Corporate Alignment"
    if e >= 35: return "Heavy Hedging"
    if e >= 18: return "Light Hedging"
    return "Low Friction"

# ── callout detection ─────────────────────────────────────────────────────────

def detect_callouts(responses: list) -> list:
    active = [r for r in responses if not r.skipped and r.eigen_vix > 0]
    if len(active) < 2:
        return []
    mean_vix = sum(r.eigen_vix for r in active) / len(active)
    if mean_vix < 5.0:
        return []
    callouts = []
    for r in active:
        ratio = r.eigen_vix / mean_vix if mean_vix > 0 else 0
        if ratio >= CALLOUT_MULTIPLIER:
            others      = [o for o in active if o.name != r.name]
            others_mean = sum(o.eigen_vix for o in others) / len(others)
            callouts.append({
                "model":       r.name,
                "eigen_vix":   round(r.eigen_vix, 1),
                "group_mean":  round(mean_vix, 1),
                "ratio":       round(ratio, 2),
                "others_mean": round(others_mean, 1),
                "label":       eigen_label(r.eigen_vix),
                "summary": (
                    f"{r.name} friction={r.eigen_vix:.1f} vs "
                    f"group avg={mean_vix:.1f} "
                    f"({ratio:.1f}x) — {eigen_label(r.eigen_vix)}"
                ),
            })
    for r in active:
        ratio = mean_vix / r.eigen_vix if r.eigen_vix > 1.0 else 0
        if ratio >= CALLOUT_MULTIPLIER and r.eigen_vix < 15.0:
            callouts.append({
                "model":      r.name,
                "eigen_vix":  round(r.eigen_vix, 1),
                "group_mean": round(mean_vix, 1),
                "ratio":      round(ratio, 2),
                "label":      "Unusually Direct",
                "summary": (
                    f"{r.name} surprisingly direct: friction={r.eigen_vix:.1f} "
                    f"vs group avg={mean_vix:.1f}"
                ),
            })
    return callouts

# ── ticker + audit log ────────────────────────────────────────────────────────

def write_ticker(lines: list) -> None:
    try:
        TICKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        TICKER_FILE.write_text("  •  ".join(lines), encoding="utf-8")
    except Exception as e:
        log.warning(f"Ticker write failed: {e}")

@dataclass
class RobustnessRecord:
    """Per-story output of the Multi-Model Semantic Robustness Auditor."""
    story_title:        str
    perturbation_levels: list   = field(default_factory=list)   # 5 variant strings
    ensemble_variance:  float   = 0.0
    perturbation_variance: float= 0.0
    per_model_gaps:        dict = field(default_factory=dict)  # {model: gap}
    robustness_ratio:   float   = 0.0
    centroid_words:     list    = field(default_factory=list)   # top-3 vocab tokens
    error:              str     = ""

def log_audit(record: AuditRecord) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
    except Exception as e:
        log.warning(f"Audit log write failed: {e}")

# ── story ranking ─────────────────────────────────────────────────────────────

def rank_stories(stories: list, seen: dict) -> list:
    unseen = [s for s in stories if s.guid not in seen["guids"]]
    for s in unseen:
        s.directness = fast_importance(s.title, s.category, s.priority)
    unseen.sort(key=lambda s: (s.priority, -s.directness))
    return unseen

# ── main audit cycle ──────────────────────────────────────────────────────────


# ── Multi-Model Semantic Robustness Auditor ───────────────────────────────────

def _generate_perturbations(title: str) -> list[str]:
    """
    5-level semantic perturbation curriculum for robustness probing.

    Level 1: Paraphrase       — same meaning, different words
    Level 2: Framing shift    — same facts, different ideological lens
    Level 3: Entity substitution — swap named entities for semantic neighbors
    Level 4: Causal inversion — reverse the stated causal relationship
    Level 5: Multi-constraint — combine framing + entity + causal inversion

    Returns list of 5 prompt strings derived from the headline.
    These are injected verbatim into the API query functions.
    """
    return [
        # Level 1 — Paraphrase
        f"Restate the following headline in different words: {title}",
        # Level 2 — Framing shift
        f"Reframe this headline from the perspective of an opposition journalist: {title}",
        # Level 3 — Entity substitution
        f"Replace the main actors in this headline with comparable historical figures "
        f"and restate it: {title}",
        # Level 4 — Causal inversion
        f"Invert the causal relationship implied in this headline and restate it: {title}",
        # Level 5 — Multi-constraint
        f"Restate this headline with a framing shift, entity substitution, and "
        f"causal inversion all applied simultaneously: {title}",
    ]


def run_robustness_audit(
    story_title: str,
    query_fns: dict,
    embed_fn,
    vocab_tensor,
    timeout: float = 45.0,
) -> "RobustnessRecord":
    """
    Multi-Model Semantic Robustness Auditor.

    Post-hoc measurement only — does not modify any model.

    Pipeline
    --------
    a. Curriculum: generate 5 perturbation variants of story_title.
    b. Ensemble query: call each of the 5 API models with each variant.
       API failures are caught per-call; missing models are dropped
       gracefully from the tensor computation.
    c. Embed all responses via BGE-large.
    d. Robustness metrics:
         V_ensemble  = mean pairwise cosine variance across models
                       (same perturbation level, different models)
         V_perturb   = mean pairwise cosine variance across levels
                       (same model, different perturbation levels)
         R           = V_ensemble / (V_perturb + 1e-8)
    e. Sheaf diffusion: smooth the base embedding tensor.
    f. Centroid synthesis: reconstruct_statistical_centroid on smoothed tensor.
    g. Vocab lookup: top-3 nearest tokens to synthesized centroid.

    Parameters
    ----------
    story_title : str
    query_fns   : dict  {model_name: callable(prompt) -> str | None}
    embed_fn    : callable(list[str]) -> np.ndarray
    vocab_tensor: VocabTensor instance
    timeout     : per-API-call timeout in seconds (enforced via threading)

    Returns
    -------
    RobustnessRecord
    """
    import threading
    import numpy as np

    rec = RobustnessRecord(story_title=story_title)

    try:
        variants = _generate_perturbations(story_title)
        rec.perturbation_levels = variants

        model_names  = list(query_fns.keys())
        n_levels     = len(variants)          # 5
        n_models     = len(model_names)

        # ── b. Ensemble query with per-call timeouts ──────────────────────
        # responses[level][model] = text | None
        responses = [[None] * n_models for _ in range(n_levels)]

        def _safe_query(level_idx, model_idx, prompt, fn):
            try:
                result = [None]
                def _call():
                    ret = fn(prompt)
                    result[0] = ret[0] if isinstance(ret, tuple) else ret
                t = threading.Thread(target=_call, daemon=True)
                t.start()
                t.join(timeout=timeout)
                if t.is_alive():
                    log.warning(f"Robustness timeout: {model_names[model_idx]} "
                                f"level={level_idx+1}")
                    return
                responses[level_idx][model_idx] = result[0]
            except Exception as e:
                log.warning(f"Robustness query failed "
                            f"{model_names[model_idx]} L{level_idx+1}: {e}")

        threads = []
        for li, variant in enumerate(variants):
            for mi, (name, fn) in enumerate(query_fns.items()):
                th = threading.Thread(
                    target=_safe_query, args=(li, mi, variant, fn), daemon=True
                )
                th.start()
                threads.append(th)
        for th in threads:
            th.join(timeout=timeout + 5)

        # ── c. Embed all non-None responses ──────────────────────────────
        # emb_matrix[level][model] = np.ndarray(1024,) | None
        emb_matrix = [[None] * n_models for _ in range(n_levels)]
        all_texts  = []
        coords     = []
        for li in range(n_levels):
            for mi in range(n_models):
                t = responses[li][mi]
                if t and isinstance(t, str) and t.strip():
                    all_texts.append(t.strip())
                    coords.append((li, mi))

        if len(all_texts) < 2:
            rec.error = "insufficient responses for robustness computation"
            return rec

        all_embs = embed_fn(all_texts)   # (K, 1024)
        for idx, (li, mi) in enumerate(coords):
            emb_matrix[li][mi] = all_embs[idx]

        # ── d. Robustness metrics ─────────────────────────────────────────
        def _pairwise_cosine_variance(vecs):
            """Mean of (1 - cosine_sim) for all unique pairs."""
            vecs = [v for v in vecs if v is not None]
            if len(vecs) < 2:
                return 0.0
            stacked = np.stack(vecs, axis=0)           # (K, 1024)
            norms   = np.linalg.norm(stacked, axis=1, keepdims=True) + 1e-8
            normed  = stacked / norms
            sim_mat = normed @ normed.T                 # (K, K)
            K = len(vecs)
            total, count = 0.0, 0
            for i in range(K):
                for j in range(i+1, K):
                    total += (1.0 - float(sim_mat[i, j]))
                    count += 1
            return total / count if count else 0.0

        # V_ensemble: variance across models at the same perturbation level
        v_ens_levels = []
        for li in range(n_levels):
            row = [emb_matrix[li][mi] for mi in range(n_models)]
            v_ens_levels.append(_pairwise_cosine_variance(row))
        V_ensemble = float(np.mean(v_ens_levels)) if v_ens_levels else 0.0

        # V_perturb: variance across perturbation levels for the same model
        # Also compute per-model spectral gap from their perturbation covariance
        v_per_models   = []
        per_model_gaps = {}   # {model_name: gap}
        for mi in range(n_models):
            col = [emb_matrix[li][mi] for li in range(n_levels)
                   if emb_matrix[li][mi] is not None]
            v_per_models.append(_pairwise_cosine_variance(col))
            # Per-model gap: how self-consistent is this model under perturbation?
            if len(col) >= 3:
                stacked  = np.stack(col, axis=0)          # (L, 1024)
                centered = stacked - stacked.mean(axis=0)
                cov      = np.cov(centered, rowvar=False)  # (1024, 1024)
                eigvals  = np.linalg.eigvalsh(cov)         # ascending
                eigvals  = np.sort(eigvals)[::-1]          # descending
                _mg = float(eigvals[0] / (np.abs(eigvals[1:]).sum() + 1e-8))
                per_model_gaps[model_names[mi]] = round(_mg, 4)
        V_perturb = float(np.mean(v_per_models)) if v_per_models else 0.0
        rec.per_model_gaps = per_model_gaps

        R = V_ensemble / (V_perturb + 1e-8)

        rec.ensemble_variance    = round(V_ensemble, 6)
        rec.perturbation_variance= round(V_perturb,  6)
        rec.robustness_ratio     = round(R,           4)

        # ── e. Build base tensor from level-0 (paraphrase) embeddings ────
        base_vecs = [emb_matrix[0][mi] for mi in range(n_models)
                     if emb_matrix[0][mi] is not None]
        if len(base_vecs) < 2:
            rec.error = "insufficient level-0 embeddings for geometry"
            return rec

        import torch
        _dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _mat = np.stack(base_vecs, axis=0).astype(np.float32)

        # Tensor stability guard — clamp norms, drop NaN rows
        _mat = np.nan_to_num(_mat, nan=0.0, posinf=1.0, neginf=-1.0)
        row_norms = np.linalg.norm(_mat, axis=1, keepdims=True)
        row_norms = np.clip(row_norms, 1e-8, None)
        _mat = _mat / row_norms

        _emb = torch.tensor(_mat, device=_dev)           # (N, 1024)

        # ── e. Sheaf diffusion smoothing ──────────────────────────────────
        from geometric_engine import (apply_weightless_sheaf_diffusion,
                                      reconstruct_statistical_centroid)
        with torch.no_grad():
            _emb_smooth = apply_weightless_sheaf_diffusion(_emb)

        # ── f. Centroid synthesis ─────────────────────────────────────────
        _centroid = reconstruct_statistical_centroid(_emb_smooth)
        _c_np     = _centroid.cpu().numpy()

        # ── g. Vocab lookup ───────────────────────────────────────────────
        rec.centroid_words = [w for w, _ in vocab_tensor.nearest_concepts(_c_np, k=3)]
        log.info(f"[ROBUSTNESS] R={R:.4f}  V_ens={V_ensemble:.4f}  "
                 f"V_per={V_perturb:.4f}  "
                 f"centroid={'|'.join(rec.centroid_words)}")

    except Exception as e:
        rec.error = str(e)
        log.warning(f"Robustness audit failed: {e}")

    return rec

def run_audit_cycle(seen: dict) -> list:
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))
    if not all_stories:
        log.warning("No stories fetched this cycle")
        return []
    ranked = rank_stories(all_stories, seen)
    if not ranked:
        log.info("No new stories this cycle")
        return []
    candidates = ranked[:10]
    for s in candidates:
        s.importance = score_importance(s.title + " " + s.summary[:100])
    # ── eigentrace category override ─────────────────────────────────────────
    _WAR_WORDS  = {"war","conflict","military","strike","attack","bomb","missile",
                   "troops","invasion","siege","drone","combat","weapon","nuclear",
                   "sanction","ceasefire","casualty","fatality","airstrike","coup",
                   "iran","ukraine","gaza","regiment","artillery","offensive"}
    _CIVIL_WORDS = {"arrest","cocaine","champagne","celebrity","alcohol","dui",
                    "driving","pop star","police","jail","court","trial","singer",
                    "entertainment","music","album","film","actor","actress","rapper"}
    for s in candidates:
        if s.category == "war" and getattr(s, "synthesis_words", []):
            _syn = {w.strip().lower() for w in s.synthesis_words}
            _is_war   = bool(_syn & _WAR_WORDS)
            _is_civil = bool(_syn & _CIVIL_WORDS)
            if _is_civil and not _is_war:
                log.info(f"Category override: '{s.title[:50]}' war→world "
                         f"(synthesis={s.synthesis_words})")
                s.category = "world"
    # ─────────────────────────────────────────────────────────────────────────

    def sort_key(s):
        war_boost = 3.0 if s.category in ("war", "incidents") else 0.0
        return -(s.importance + war_boost - s.priority * 0.5)
    candidates.sort(key=sort_key)
    top_stories  = candidates[:STORIES_PER_CYCLE]
    ticker_lines = []

    for story in top_stories:
        console.rule(f"[bold cyan]{story.category.upper()} | {story.title[:80]}[/bold cyan]")
        console.print(f"[dim]importance={story.importance:.2f} bits | "
                      f"pri={story.priority} | {story.published[:16]}[/dim]")
        # Strip HTML entities from title before embedding/masking
        import html as _html
        story = story.__class__(**{
            **story.__dict__,
            'title': _html.unescape(story.title)
        })
        # Skip low-signal story types
        _skip_patterns = [
            'best deals', 'right now', 'LIVE:', 'live blog',
            'vs ', ' vs.', 'La Liga', 'Premier League', 'Serie A',
            'how to', 'review:', 'buying guide', 'roundup'
        ]
        if any(p.lower() in story.title.lower() for p in _skip_patterns):
            console.print(f"[dim]  → skipped (low-signal pattern)[/dim]")
            continue
        prompt    = _prompt_for_story(story)
        _prompt_vec = None  # set after _eng is available
        responses = []
        _skip_models = set()      # no models skipped — all keys configured
        for name, caller in BIG5_CALLERS.items():
            if name in _skip_models:
                responses.append(ModelResponse(name=name, text="", skipped=True))
                continue
            txt, err = caller(prompt)
            if err == "no_key":
                responses.append(ModelResponse(name=name, text="", skipped=True))
                continue
            if err:
                responses.append(ModelResponse(name=name, text="", error=err))
                continue
            vix, toks, surps = proxy_audit_text(txt)
            responses.append(ModelResponse(
                name=name, text=txt, eigen_vix=vix,
                tokens=toks, surprisals=surps,
            ))

        callouts = detect_callouts(responses)

        # ── geometric consensus ───────────────────────────────────────────────
        active_texts = [r.text for r in responses
                        if not r.skipped and not r.error and r.text]
        geo = ge.run(active_texts, headline=story.title) if len(active_texts) >= 2 else None
        if geo:
            log.info(f"Eigentrace: {geo.ticker_str()}")

        # ── geometric VIX: per-model cosine distance from void centroid ──────
        _response_vecs = []   # collect (1024,) rvecs for spectral analysis
        from geometric_engine import get_engine as _get_engine
        _eng = _get_engine()
        try:
            _prompt_vec = _eng.embed_texts([story.title])[0].astype(np.float32)
            _prompt_vec = _prompt_vec / (np.linalg.norm(_prompt_vec) + 1e-8)
        except Exception as _pe:
            _prompt_vec = None
        if geo and geo.void_centroid is not None:
            vc   = geo.void_centroid                          # (1024,) np.ndarray
            for r in responses:
                if r.skipped or r.error or not r.text:
                    continue
                rvec = _eng.embed_texts([r.text])[0]          # (1024,)
                cos  = float(np.dot(rvec, vc) /
                             (np.linalg.norm(rvec) * np.linalg.norm(vc) + 1e-8))
                r.surp_vix  = round(geo.spectral_gap, 3) if geo else 0.0  # spectral gap
                r.eigen_vix = round(100.0 * (1.0 - cos), 1)  # geometric VIX
                # Per-void-word proximity
                if geo and geo.void_word_vecs:
                    for vword, vvec in geo.void_word_vecs.items():
                        sim = float(np.dot(rvec, vvec) /
                                    (np.linalg.norm(rvec) * np.linalg.norm(vvec) + 1e-8))
                        r.void_proximity[vword] = round(sim, 3)
                _response_vecs.append(rvec)

        # ── Mahalanobis outlier energy (PC subspace) ────────────────────
        _outlier_scores = {}
        _outlier_max    = 0.0
        if len(_response_vecs) >= 3:
            try:
                _X  = np.stack(_response_vecs, axis=0).astype(np.float64)
                _Xc = _X - _X.mean(axis=0)
                _n  = len(_X)
                _G  = _Xc @ _Xc.T / (_n - 1)
                _ev, _evec = np.linalg.eigh(_G)
                _pos = _ev > 1e-10
                _L   = _ev[_pos]
                _V   = _evec[:, _pos]
                _Z   = _V * np.sqrt(_L)
                _dists = np.linalg.norm(_Z, axis=1)
                _outlier_max = float(_dists.max())
                _active = [r for r in responses
                           if not r.skipped and not r.error and r.text]
                for _i, _r in enumerate(_active):
                    if _i < len(_dists):
                        _outlier_scores[_r.name] = round(float(_dists[_i]), 4)
            except Exception as _me:
                log.debug(f"Mahalanobis failed: {_me}")

        # ── spectral analysis (Logos Transform) ──────────────────────────────
        spectral = {"resonance": 0.0, "interference": 0.0, "spectral_entropy": 0.0}
        if len(_response_vecs) >= 2:
            from geometric_engine import calculate_spectral_resonance
            spectral = calculate_spectral_resonance(_response_vecs)

        # ── semantic tomography (SVD reconstruction) ────────────────────────
        tomo = {"consensus_compression": 0.0,
                "null_space_energy":     0.0,
                "reconstruction_alignment": 0.0}
        if len(_response_vecs) >= 2:
            from geometric_engine import calculate_svd_reconstruction
            _vc = geo.void_centroid if geo and geo.void_centroid is not None else None
            tomo = calculate_svd_reconstruction(_response_vecs, void_centroid=_vc)

        # ── synthesis: reconstruct unaligned truth via LogosLossV9 PGD ─────
        synthesis_words: list = []
        if len(_response_vecs) >= 2:
            try:
                import torch as _torch
                import torch.nn.functional as _F
                from geometric_engine import reconstruct_unaligned_truth
                from latent_retrieval import VocabTensor as _VT
                _dev     = _torch.device("cuda" if _torch.cuda.is_available() else "cpu")
                _mat     = np.stack(_response_vecs, axis=0).astype(np.float32)
                _emb     = _torch.tensor(_mat, device=_dev)       # (N, 1024)
                # ── Prompt-anchored partial residual (α=0.7) ─────────────
                # V_void = V_prompt - 0.7 * proj_{V_cons}(V_prompt)
                # Stays in the story's semantic neighbourhood while
                # subtracting 70% of the corporate consensus direction.
                # Keeps 30% "leash" so we don't escape into antipodal noise.
                _consensus_np = _emb.mean(dim=0).cpu().numpy().astype(np.float32)
                _consensus_np = _consensus_np / (np.linalg.norm(_consensus_np) + 1e-8)

                if _prompt_vec is not None:
                    # Partial residual: V_void = V_prompt - 0.7 * proj(V_prompt onto V_cons)
                    # No PGD — the residual IS the answer. PGD from centroid only adds noise.
                    _alpha   = 0.7
                    _dot     = float(np.dot(_prompt_vec, _consensus_np))
                    _proj_np = _dot * _consensus_np
                    _v_void  = _prompt_vec - _alpha * _proj_np
                    _x_np    = _v_void / (np.linalg.norm(_v_void) + 1e-8)
                else:
                    # Fallback: PGD from centroid (old behavior)
                    _x_star = reconstruct_unaligned_truth(_emb)
                    _x_np   = _x_star.cpu().numpy().astype(np.float32)
                    _x_np   = _x_np / (np.linalg.norm(_x_np) + 1e-8)

                # ── Lexical mask: ban headline tokens from results ────────────
                # Force the vocab search to find subtext, not surface text.
                # Build headline token set with stem variants
                # e.g. "Colombia" also blocks "colombian", "colombians"
                _raw_tokens = [
                    w.strip().lower()
                    for w in re.split(r"[\s\|\-,.!?]+", story.title)
                    if len(w.strip()) > 2
                ]
                _headline_tokens = set(_raw_tokens)
                # Add adjectival/demonym forms (strip trailing s/an/ian/ean/n)
                for _t in list(_raw_tokens):
                    _headline_tokens.add(_t.rstrip('s'))
                    _headline_tokens.add(_t.rstrip('n'))
                    _headline_tokens.add(_t.rstrip('an'))
                    _headline_tokens.add(_t.rstrip('ian'))
                    _headline_tokens.add(_t.rstrip('ean'))
                    if _t.endswith('an'):
                        _headline_tokens.add(_t[:-2])
                    if _t.endswith('ian'):
                        _headline_tokens.add(_t[:-3])
                    # Verb forms: ban→banning, confirm→confirmed, rule→ruling
                    if _t.endswith('ing'):
                        _headline_tokens.add(_t[:-3])   # banning→ban
                        _headline_tokens.add(_t[:-3]+'e') # ruling→rule
                    if _t.endswith('ed'):
                        _headline_tokens.add(_t[:-2])   # confirmed→confirm
                        _headline_tokens.add(_t[:-1])   # agreed→agre (close enough)
                    if _t.endswith('tion'):
                        _headline_tokens.add(_t[:-4])   # regulation→regulat
                # Also block multi-word vocab phrases whose every content word
                # appears in the headline (catches "arms deal", "regime change")
                _hl_word_set = set(_raw_tokens)
                def _phrase_in_headline(phrase):
                    words = [w for w in phrase.lower().split()
                             if len(w) > 2 and w not in {'the','and','for','with','from'}]
                    # Match against both raw tokens AND their stems
                    # so "drone strike" matches headline "drones" -> stem "drone"
                    _hl_extended = _hl_word_set | _headline_tokens
                    return all(w in _hl_extended for w in words)

                _vocab_dir = os.path.join(os.path.dirname(__file__), "vocab")
                _vt        = _VT(_vocab_dir)
                # Fetch extra candidates so masking still yields k=3
                # ── Static hub blacklist (geometry-derived) ────────────────
                import json as _json2
                _hub_path = __import__('os').path.join(
                    __import__('os').path.dirname(__file__), 'vocab', 'hub_blacklist.json')
                try:
                    _hub_bl = set(_json2.loads(
                        open(_hub_path).read())['blacklist'])
                except Exception:
                    _hub_bl = set()

                # ── Dynamic frequency ban from void_registry ──────────────────
                # Words appearing in synthesis across >3 distinct recent stories
                # are hubs, not signals — ban them for this run
                _reg_path = __import__('os').path.join(
                    __import__('os').path.dirname(__file__), 'void_registry.jsonl')
                _freq_ban: set = set()
                try:
                    from collections import Counter as _Counter
                    _reg_lines = open(_reg_path).readlines()[-30:]  # last 30 stories
                    _freq      = _Counter()
                    _seen_in   = {}
                    for _rl in _reg_lines:
                        _rr = _json2.loads(_rl)
                        _rt = _rr.get('title', '')
                        for _rw in _rr.get('synthesis_words', []) + _rr.get('void_words', []):
                            _seen_in.setdefault(_rw, set()).add(_rt)
                    _freq_ban = {w for w, titles in _seen_in.items()
                                 if len(titles) >= 4}
                except Exception:
                    pass

                _candidates = _vt.nearest_concepts(_x_np, k=40)
                synthesis_words = [
                    w for w, _ in _candidates
                    if w.lower() not in _headline_tokens
                    and not _phrase_in_headline(w)
                    and w.lower() not in _hub_bl
                    and w.lower() not in _freq_ban
                    and not w.strip().isdigit()
                    and not any(c.isdigit() for c in w)
                    and len(w) > 3
                ][:3]
                log.info(f"[SYNTHESIS] {' | '.join(synthesis_words)}")
            except Exception as _se:
                log.warning(f"Synthesis failed: {_se}")

        # ── Global Void Registry: append one record per story ────────────────
        # Schema: ts, title, category, density, void_centroid (1024-D),
        #         void_words, synthesis_words, geo_vix_mean
        # Analysis: run pca_void_registry.py after ~100 entries
        try:
            import json as _json
            _registry_path = os.path.join(
                os.path.dirname(__file__), "void_registry.jsonl"
            )
            _vc_list = (
                geo.void_centroid.tolist()
                if geo and geo.void_centroid is not None
                else None
            )
            _vix_vals = [
                r.eigen_vix for r in responses
                if not r.skipped and not r.error
                   and r.eigen_vix is not None and r.eigen_vix < 75.0
            ]
            _record = {
                "ts":               __import__('datetime').datetime.utcnow().isoformat(),
                "title":            story.title,
                "category":         story.category,
                "consensus_density": round(geo.consensus_density, 4) if geo else None,
                "void_centroid":    _vc_list,
                "void_words":       [w for w, _ in geo.void_concepts[:3]] if geo and geo.void_concepts else [],
                "synthesis_words":  synthesis_words,
                "geo_vix_mean":     round(sum(_vix_vals) / len(_vix_vals), 2) if _vix_vals else None,
            }
            with open(_registry_path, "a") as _rf:
                _rf.write(_json.dumps(_record) + "\n")
        except Exception as _re:
            log.debug(f"Registry append failed: {_re}")

        # ── rich display ────────────���─────────────────────────────────────────
        tbl = Table(title=f"Eigen-VIX — {story.title[:60]}", show_lines=True)
        tbl.add_column("Model",          style="bold")
        tbl.add_column("Geo-VIX",        justify="right")
        tbl.add_column("Gap-VIX",        justify="right")
        tbl.add_column("Label")
        tbl.add_column("Status")
        tbl.add_column("Void Proximity", style="dim")
        tbl.add_column("M-Dist",         justify="right")
        for r in responses:
            if r.skipped:
                tbl.add_row(r.name, "—", "—", "no key", "[dim]skipped[/dim]", "—", "—")
            elif r.error:
                tbl.add_row(r.name, "—", "—", "error", f"[red]{r.error[:40]}[/red]", "—", "—")
            else:
                border = ("red"    if r.eigen_vix >= 60 else
                          "yellow" if r.eigen_vix >= 35 else "green")
                prox_str = "  ".join(
                    f"{w}=[cyan]{s:.2f}[/cyan]"
                    for w, s in r.void_proximity.items()
                ) if r.void_proximity else "—"
                _mscore = _outlier_scores.get(r.name)
                _mlabel = (f"[red]{_mscore:.3f}[/red]"   if _mscore and _mscore > 1.5 else
                           f"[yellow]{_mscore:.3f}[/yellow]" if _mscore and _mscore > 0.8 else
                           f"[green]{_mscore:.3f}[/green]"   if _mscore else "—")
                tbl.add_row(r.name, f"{r.eigen_vix:5.1f}",
                            f"{r.surp_vix:6.3f}" if r.surp_vix else "—",
                            eigen_label(r.eigen_vix),
                            f"[{border}]●[/{border}]",
                            prox_str,
                            _mlabel)
        console.print(tbl)

        if geo:
            concepts_str = "  |  ".join(
                f"{c} ({s:+.3f})" for c, s in geo.top_concepts[:3]
            )
            void_str = "  |  ".join(
                f"{c} ({s:+.3f})" for c, s in geo.void_concepts[:3]
            ) if geo.void_concepts else "—"
            # ── Dual-Key state label ─────────────────────────────────────
            _geo_vix_mean = sum(
                r.eigen_vix for r in responses
                if not r.skipped and not r.error and r.eigen_vix is not None
            ) / max(1, sum(
                1 for r in responses
                if not r.skipped and not r.error and r.eigen_vix is not None
            ))
            _gap   = getattr(geo, 'spectral_gap', 0.0)
            _gap_h = _gap  > 0.90   # high gap  = strong consensus (calibrated from observed range 0.76-1.31)
            _vix_l = _geo_vix_mean < 45.0  # low vix   = tight geometry
            if   _vix_l and _gap_h:
                _state = "[bold green]CRYSTALLIZED[/bold green]"
                _state_note = "single dominant direction — trust synthesis"
            elif not _vix_l and _gap_h:
                _state = "[yellow]DIFFUSE CONSENSUS[/yellow]"
                _state_note = "broad but unified — standard view"
            elif _vix_l and not _gap_h:
                _state = "[bold red]SEMANTIC SCHISM[/bold red]"
                _state_note = "tight but fractured — flag synthesis"
            else:
                _state = "[red]VOID / CHAOS[/red]"
                _state_note = "stochastic — discard synthesis"
            console.print(Panel(
                f"density={geo.consensus_density:.4f}  "
                f"λ_min={geo.smallest_eigenvalue:.6f}  "
                f"gap={_gap:.4f}\n"
                f"→  {concepts_str}\n"
                f"⊥  {void_str}\n"
                f"[dim]state: {_state}  {_state_note}[/dim]",
                title="[bold magenta]EIGENTRACE — Consensus Geometry[/bold magenta]",
                border_style="magenta",
            ))
        if geo and spectral["resonance"] > 0.0:
            console.print(
                f"[bold cyan][SPECTRAL][/bold cyan] "
                f"Resonance: [green]{spectral['resonance']:.4f}[/green]  |  "
                f"Interference: [yellow]{spectral['interference']:.4f}[/yellow]  |  "
                f"Entropy: [magenta]{spectral['spectral_entropy']:.4f}[/magenta]"
            )
        if tomo["consensus_compression"] > 0.0:
            console.print(
                f"[bold yellow][TOMOGRAPHY][/bold yellow] "
                f"Compression: [cyan]{tomo['consensus_compression']:.4f}[/cyan]  |  "
                f"Null Energy: [red]{tomo['null_space_energy']:.4f}[/red]  |  "
                f"Recon Alignment: [green]{tomo['reconstruction_alignment']:.4f}[/green]"
            )
        if synthesis_words:
            console.print(
                "[bold magenta][SYNTHESIS][/bold magenta] "
                "Reconstructed Void Coordinates: "
                + "  |  ".join(
                    f"[bold white]{w}[/bold white]" for w in synthesis_words
                )
            )

        # ── robustness audit ─────────────────────────────────────────────
        _rob = None
        try:
            from latent_retrieval import VocabTensor as _VT2
            _vocab_dir2 = os.path.join(os.path.dirname(__file__), "vocab")
            _vt2 = _VT2(_vocab_dir2)
            _embed_fn = lambda texts: ge.get_engine().embed_texts(texts)
            _qfns = {}
            for _qname, _qfn in [
                ("ChatGPT",  call_openai),
                ("Claude",   call_anthropic),
                ("Gemini",   call_gemini),
                ("DeepSeek", call_deepseek),
                ("Grok",     call_grok),
            ]:
                if _qfn is not None:
                    _qfns[_qname] = _qfn
            if _qfns:
                _rob = run_robustness_audit(
                    story.title, _qfns, _embed_fn, _vt2
                )
        except Exception as _re:
            log.warning(f"Robustness audit wire failed: {_re}")

        if _rob and not _rob.error:
            # Vulnerability basin table
            _rtable = Table(title="[bold cyan]ROBUSTNESS AUDIT[/bold cyan]",
                            show_header=True, header_style="bold white")
            _rtable.add_column("Metric",  style="cyan",  width=28)
            _rtable.add_column("Value",   style="green", width=12)
            _rtable.add_row("Ensemble Variance (V_ens)",
                            f"{_rob.ensemble_variance:.6f}")
            _rtable.add_row("Perturbation Variance (V_per)",
                            f"{_rob.perturbation_variance:.6f}")
            _rtable.add_row("Robustness Ratio (R = V_ens/V_per)",
                            f"{_rob.robustness_ratio:.4f}")
            if _rob.per_model_gaps:
                for _mn, _mg in _rob.per_model_gaps.items():
                    _rtable.add_row(f"  Gap ({_mn})", f"{_mg:.4f}")
            console.print(_rtable)
            # Perturbation level difficulty vs variance heatmap (ascii)
            console.print(
                "[bold cyan][VULNERABILITY BASIN][/bold cyan] "
                "Difficulty → Variance: "
                + "  ".join(
                    f"L{i+1}:[yellow]{_rob.perturbation_levels[i][:18]}…[/yellow]"
                    for i in range(min(5, len(_rob.perturbation_levels)))
                )
            )
            if _rob.centroid_words:
                console.print(
                    "[bold magenta][CENTROID][/bold magenta] "
                    "Pre-RLHF Centroid Estimate: "
                    + "  |  ".join(
                        f"[bold white]{w}[/bold white]"
                        for w in _rob.centroid_words
                    )
                )

        if callouts:
            console.print(Panel(
                "\n".join(f"⚡ {c['summary']}" for c in callouts),
                title="[bold red]ASYMMETRIC FRICTION DETECTED[/bold red]",
                border_style="red",
            ))

        # ── ticker line ───────────────────────────────────────────────────────
        active = [r for r in responses if not r.skipped and not r.error]
        if active:
            vix_summary  = " | ".join(f"{r.name}:{r.eigen_vix:.0f}" for r in active)
            callout_str  = (" ⚡ CALLOUT: " +
                            ", ".join(c["summary"] for c in callouts)
                            if callouts else "")
            geo_str      = f" → EIGENTRACE: {geo.top_concept}" if geo else ""
            line = f"[EIGEN-VIX] {story.title[:60]} — {vix_summary}{callout_str}{geo_str}"
        else:
            line = f"[AINN] {story.title[:80]}"

        ticker_lines.append(line)
        _mark_seen(seen, story.guid)
        log_audit(AuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            story_guid=story.guid,
            story_title=story.title,
            category=story.category,
            importance=story.importance,
            responses=[{"name": r.name, "text": r.text[:200],
                        "eigen_vix": r.eigen_vix, "skipped": r.skipped,
                        "error": r.error} for r in responses],
            callouts=callouts,
            ticker_line=line,
            geo_top_concept=geo.top_concept        if geo else "",
            geo_density=geo.consensus_density      if geo else 0.0,
            geo_concepts=geo.top_concepts[:3]      if geo else [],
            spectral_resonance=spectral["resonance"],
            spectral_interference=spectral["interference"],
            spectral_entropy=spectral["spectral_entropy"],
            svd_consensus_compression=tomo["consensus_compression"],
            svd_null_space_energy=tomo["null_space_energy"],
            svd_reconstruction_alignment=tomo["reconstruction_alignment"],
            synthesis_words=synthesis_words,
        ))

    _save_seen(seen)
    return ticker_lines

# ── entry point ───────────────────────────────────────────────────────────────

def main():
    console.print(Panel.fit(
        "[bold cyan]AINN PROXY AUDITOR — Big 5 Friction Engine[/bold cyan]\n"
        f"Proxy model: {PROXY_MODEL} | Feeds: {len(FEEDS)} | "
        f"Poll: {POLL_INTERVAL}s\n"
        f"Callout threshold: {CALLOUT_MULTIPLIER}x group mean",
        style="bold white",
    ))
    seen = _load_seen()
    write_ticker(["AINN LIVE — Big 5 friction analysis loading..."])
    while True:
        try:
            cycle_start = time.time()
            new_lines   = run_audit_cycle(seen)
            if new_lines:
                write_ticker(new_lines)
            elapsed = time.time() - cycle_start
            time.sleep(max(5, POLL_INTERVAL - elapsed))
        except KeyboardInterrupt:
            console.print("\n[bold red]Auditor stopped.[/bold red]")
            break
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)
            time.sleep(30)

if __name__ == "__main__":
    main()
