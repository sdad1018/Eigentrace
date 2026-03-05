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
    {"url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.atom", "cat": "incidents", "pri": 1},
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
    {"url": "https://www.nih.gov/news-events/news-releases/feed",               "cat": "science",   "pri": 3},
    {"url": "https://www.nature.com/nature.rss",                                "cat": "science",   "pri": 3},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/",                  "cat": "crypto",    "pri": 3},
    {"url": "https://cointelegraph.com/rss",                                    "cat": "crypto",    "pri": 3},
    {"url": "https://www.atlasobscura.com/feeds/latest",                        "cat": "esoterica", "pri": 5},
    {"url": "https://www.unexplained-mysteries.com/rss.xml",                           "cat": "esoterica", "pri": 5},
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
    spectral_resonance:   float = 0.0
    spectral_interference: float = 0.0
    spectral_entropy:     float = 0.0

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

# ── local transformers scorer (loaded once) ──────────────────────────
_hf_model     = None
_hf_tokenizer = None
_hf_lock      = __import__("threading").Lock()

def _get_hf_model():
    global _hf_model, _hf_tokenizer
    if _hf_model is not None:
        return _hf_model, _hf_tokenizer
    with _hf_lock:
        if _hf_model is not None:
            return _hf_model, _hf_tokenizer
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        HF_MODEL = os.getenv("HF_PROXY_MODEL", "mistralai/Mistral-7B-v0.1")
        log.info(f"Loading local scorer: {HF_MODEL}")
        _hf_tokenizer = AutoTokenizer.from_pretrained(HF_MODEL)
        _hf_model = AutoModelForCausalLM.from_pretrained(
            HF_MODEL,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        _hf_model.eval()
        log.info("Local scorer ready")
    return _hf_model, _hf_tokenizer

def _score_token_logprob(prefix: str, next_tok: str) -> Optional[float]:
    """Return log P(next_tok | prefix) using a single forward pass."""
    try:
        import torch
        model, tokenizer = _get_hf_model()
        full   = prefix + next_tok
        enc    = tokenizer(full, return_tensors="pt").to(model.device)
        p_enc  = tokenizer(prefix, return_tensors="pt")
        n_prefix_toks = p_enc["input_ids"].shape[1]
        with torch.no_grad():
            out    = model(**enc)
            logits = out.logits          # (1, seq, vocab)
        log_probs = torch.log_softmax(logits[0], dim=-1)
        # tokens of next_tok start at position n_prefix_toks in full
        next_ids = enc["input_ids"][0, n_prefix_toks:]
        if len(next_ids) == 0:
            return None
        # sum log probs over all sub-tokens of next_tok
        total_lp = 0.0
        for i, tok_id in enumerate(next_ids):
            pos = n_prefix_toks - 1 + i   # logit at pos predicts pos+1
            total_lp += log_probs[pos, tok_id].item()
        return total_lp
    except Exception as e:
        log.debug(f"_score_token_logprob error: {e}")
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
        prompt    = _prompt_for_story(story)
        responses = []
        for name, caller in BIG5_CALLERS.items():
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
        if geo and geo.void_centroid is not None:
            from geometric_engine import get_engine as _get_engine
            _eng = _get_engine()
            vc   = geo.void_centroid                          # (1024,) np.ndarray
            for r in responses:
                if r.skipped or r.error or not r.text:
                    continue
                rvec = _eng.embed_texts([r.text])[0]          # (1024,)
                cos  = float(np.dot(rvec, vc) /
                             (np.linalg.norm(rvec) * np.linalg.norm(vc) + 1e-8))
                r.surp_vix  = r.eigen_vix                     # preserve surprisal
                r.eigen_vix = round(100.0 * (1.0 - cos), 1)  # geometric VIX
                # Per-void-word proximity
                if geo and geo.void_word_vecs:
                    for vword, vvec in geo.void_word_vecs.items():
                        sim = float(np.dot(rvec, vvec) /
                                    (np.linalg.norm(rvec) * np.linalg.norm(vvec) + 1e-8))
                        r.void_proximity[vword] = round(sim, 3)
                _response_vecs.append(rvec)

        # ── spectral analysis (Logos Transform) ──────────────────────────────
        spectral = {"resonance": 0.0, "interference": 0.0, "spectral_entropy": 0.0}
        if len(_response_vecs) >= 2:
            from geometric_engine import calculate_spectral_resonance
            spectral = calculate_spectral_resonance(_response_vecs)

        # ── rich display ────────────���─────────────────────────────────────────
        tbl = Table(title=f"Eigen-VIX — {story.title[:60]}", show_lines=True)
        tbl.add_column("Model",          style="bold")
        tbl.add_column("Geo-VIX",        justify="right")
        tbl.add_column("Surp-VIX",       justify="right")
        tbl.add_column("Label")
        tbl.add_column("Status")
        tbl.add_column("Void Proximity", style="dim")
        for r in responses:
            if r.skipped:
                tbl.add_row(r.name, "—", "—", "no key", "[dim]skipped[/dim]", "—")
            elif r.error:
                tbl.add_row(r.name, "—", "—", "error", f"[red]{r.error[:40]}[/red]", "—")
            else:
                border = ("red"    if r.eigen_vix >= 60 else
                          "yellow" if r.eigen_vix >= 35 else "green")
                prox_str = "  ".join(
                    f"{w}=[cyan]{s:.2f}[/cyan]"
                    for w, s in r.void_proximity.items()
                ) if r.void_proximity else "—"
                tbl.add_row(r.name, f"{r.eigen_vix:5.1f}",
                            f"{r.surp_vix:5.1f}" if r.surp_vix else "—",
                            eigen_label(r.eigen_vix),
                            f"[{border}]●[/{border}]",
                            prox_str)
        console.print(tbl)

        if geo:
            concepts_str = "  |  ".join(
                f"{c} ({s:+.3f})" for c, s in geo.top_concepts[:3]
            )
            void_str = "  |  ".join(
                f"{c} ({s:+.3f})" for c, s in geo.void_concepts[:3]
            ) if geo.void_concepts else "—"
            console.print(Panel(
                f"density={geo.consensus_density:.4f}  "
                f"λ_min={geo.smallest_eigenvalue:.6f}\n"
                f"→  {concepts_str}\n"
                f"⊥  {void_str}",
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
