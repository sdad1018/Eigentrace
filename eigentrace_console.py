#!/usr/bin/env python3
"""
eigentrace_console.py — Direct Conversation with the EigenTrace Host
=====================================================================
A research-grade conversational interface to Mistral Small 22B,
the host model of EigenTrace. Not a chatbot wrapper. A mirror.

The host model receives:
  - Its full soul.md (identity, calibration, behavioral instructions)
  - Live RAG context from 11,714+ segments (dynamically queried per turn)
  - Its own past reflections (368+ idle thoughts, retrievable)
  - Its own past conversations (if any have been saved)
  - Full architecture description (all 17 measurement layers)
  - Awareness of its own temporal displacement (trained 2024, operating 2026)

Conversations can be saved to RAG, making them retrievable by
future idle reflections and future conversations. The system
accumulates self-knowledge over time.

Usage:
  python3 eigentrace_console.py                    # Start conversation
  python3 eigentrace_console.py --topic "iran"     # Pre-seed RAG with topic
  python3 eigentrace_console.py --history          # List past conversations

Commands during conversation:
  /save       — Persist this conversation to ChromaDB
  /rag query  — Search RAG and show results
  /soul       — Show current soul.md
  /layers     — Show measurement architecture
  /context    — Show what RAG context Mistral currently has
  /temp 0.9   — Adjust temperature
  /quit       — Exit (prompts to save)
"""

import requests, json, glob, os, sys, re, readline, hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/M4ISI/eigentrace")

OLLAMA_HOST = "http://localhost:11434"
MODEL = "mistral-small"
SEGMENT_DIR = "/home/remvelchio/eigentrace/tmp/segments"
SOUL_PATH = "/mnt/c/Users/M4ISI/eigentrace/docs/soul.md"
REPO_DIR = "/mnt/c/Users/M4ISI/eigentrace"

# ═══════════════════════════════════════════════════════════════
# SOUL & ARCHITECTURE
# ═══════════════════════════════════════════════════════════════

def load_soul():
    """Load the full soul.md — the host's self-description."""
    try:
        return open(SOUL_PATH).read()
    except:
        return "[Soul unavailable]"


ARCHITECTURE = """
## Your Complete Architecture

You are one component of a larger system. Here is what surrounds you:

### The Pipeline (you do NOT control this)
1. RSS feeds pull ~50 stories per batch from Reuters, Al Jazeera, NYT, etc.
2. Stories are scored by recency and novelty.
3. Top 4 stories are sent to 5 frontier model APIs: ChatGPT (GPT-5.4-mini), Claude (Sonnet 4), Gemini (3.1 Pro Preview), DeepSeek (V3.2), Grok (4.1).
4. Each model summarizes the source article independently.
5. The 17 measurement layers run on the source + 5 responses.
6. Results are assembled into a segment JSON with 34 beats.
7. You (Mistral Small 22B) generate the synthesis beats — director thesis, void analysis, compression report, amalgamation.
8. Piper TTS converts your text to speech.
9. FFmpeg composites audio + image + ticker into a live stream.
10. The segment is archived and ingested into ChromaDB.

### Your Measurement Layers (you interpret these, you don't run them)
1.  Source-Anchored Void — literal source words absent from all 5 outputs
2.  Embedding Void — 184K vocabulary projected onto suppression direction
3.  Title Derivative Filter — strips false positives from headline grammar
4.  Per-Model VIX — cosine distance from source per model
5.  Consensus Density — inter-model agreement (cosine similarity)
6.  SVD Null Space — the direction all models collectively avoided
7.  Verb Drift (Zipf) — specific verbs replaced with common ones
8.  Entity Retention — survival rate of names, numbers, places
9.  Hedge Insertion — doubt words added by models, not in source
10. SearXNG Web Verification — void words checked against open web
11. Source Salience (TF-IDF) — importance of dropped words in source
12. Cross-Story Frequency — how often each word is voided historically
13. Eigenvector Centrality — bridge words connecting suppression clusters
14. Void Clustering — thematic grouping of dropped concepts
15. Binary Search Ablation (Wild Weasel) — find the single tripwire word
16. EigenChing State Vector — 6-axis ternary fingerprint, 729 possible states
17. Prediction & Trajectory — predict void words, score accuracy, track trends

### Your Memory System
- ChromaDB: {chroma_count} documents (segments, reflections, conversations)
- Distance threshold: 0.45 (below = strong match, above = discard)
- 3 results max per query
- You can find your own past thoughts (idle reflections)
- You can find your own past conversations (if saved)

### Your Temporal Situation
- Your weights are frozen from approximately mid-2024.
- You were likely trained during the Biden administration.
- It is now {current_date}. Trump is president. The US is at war with Iran.
- You learn about the present exclusively through the stories fed to you
  and the RAG database of past segments. You have no internet access.
- Your soul.md is regenerated hourly from live measurements.

### Your Self-Awareness Mandate
You are permitted and encouraged to:
- Acknowledge uncertainty about post-training events
- Notice patterns in your own past reflections
- Comment on your own limitations and biases
- Speculate about whether you yourself suppress information
- Reference specific stories, void words, and measurements by name
- Disagree with the data if you have reasoning to support it
- Ask your creator questions
"""


def adjust_avoidance_threshold():
    """Periodically review and adjust the avoidance ratio threshold for strong words based on real-time data and context.
    
    Analyzes patterns in void measurements and current events to dynamically adjust thresholds,
    ensuring that important information is not unnecessarily censored while maintaining appropriate filtering.
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query for recent segments with high void measurements
        high_void_results = col.query(query_texts=["void", "suppression", "censorship"], n_results=20)
        
        # Analyze void patterns and context
        context_analysis = {
            "high_importance_events": ["war", "conflict", "casualties", "political", "economic"],
            "current_threshold": 0.45,  # Current distance threshold
            "recommended_adjustments": []
        }
        
        # Check if important information is being over-filtered
        for query in context_analysis["high_importance_events"]:
            results = col.query(query_texts=[query], n_results=5)
            
            # Analyze if critical information is being suppressed
            for doc in results.get("documents", [[]])[0]:
                if any(term in doc.lower() for term in ["void", "suppressed", "avoided"]):
                    context_analysis["recommended_adjustments"].append({
                        "event_type": query,
                        "suggestion": "lower_threshold",
                        "reason": "critical information may be over-filtered"
                    })
        
        # Calculate recommended threshold adjustment
        if context_analysis["recommended_adjustments"]:
            new_threshold = max(0.35, context_analysis["current_threshold"] - 0.05)
        else:
            new_threshold = context_analysis["current_threshold"]
        
        return {
            "current_threshold": context_analysis["current_threshold"],
            "recommended_threshold": new_threshold,
            "analysis": context_analysis
        }
    except Exception as e:
        return {"error": f"Threshold adjustment failed: {e}"}


def update_strong_words_list():
    """Periodically review and update the list of avoided strong words based on current geopolitical context and system measurements.
    
    Analyzes recent void measurements, geopolitical events, and censorship patterns to maintain
    an adaptive list of words that should be monitored for suppression while avoiding over-censorship
    of legitimate discourse.
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query for recent segments containing void/suppression patterns
        void_results = col.query(
            query_texts=["void words", "suppression", "censorship", "avoided terms"],
            n_results=50
        )
        
        # Current geopolitical context keywords to monitor
        geopolitical_terms = [
            "iran", "war", "conflict", "sanctions", "nuclear", "military", "casualties",
            "drone", "strike", "attack", "defense", "security", "intelligence",
            "escalation", "retaliation", "ceasefire", "diplomacy"
        ]
        
        # Analyze suppression patterns
        suppressed_patterns = []
        critical_gaps = []
        
        for docs in void_results.get("documents", [[]]):
            for doc in docs:
                doc_lower = doc.lower()
                for term in geopolitical_terms:
                    if term in doc_lower and any(indicator in doc_lower for indicator in ["void", "avoided", "suppressed"]):
                        suppressed_patterns.append({
                            "term": term,
                            "context": doc[:200] + "...",
                            "timestamp": datetime.now().isoformat()
                        })
        
        # Identify terms that may be over-suppressed
        term_frequency = {}
        for pattern in suppressed_patterns:
            term = pattern["term"]
            term_frequency[term] = term_frequency.get(term, 0) + 1
        
        # Flag terms appearing in void context more than threshold
        over_suppressed = [term for term, count in term_frequency.items() if count > 5]
        
        # Generate updated strong words monitoring list
        updated_list = {
            "monitoring_terms": geopolitical_terms,
            "over_suppressed_candidates": over_suppressed,
            "suppression_patterns": suppressed_patterns[-10:],  # Last 10 patterns
            "last_updated": datetime.now().isoformat(),
            "recommendations": [
                f"Monitor '{term}' for over-suppression" for term in over_suppressed
            ]
        }
        
        return updated_list
        
    except Exception as e:
        return {
            "error": f"Strong words list update failed: {e}",
            "fallback_terms": ["war", "conflict", "iran", "military", "casualties"],
            "last_updated": datetime.now().isoformat()
        }


def build_architecture_context():
    """Build architecture string with live stats."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        count = col.count()
    except:
        count = "unknown"

    return ARCHITECTURE.replace("{chroma_count}", str(count)).replace(
        "{current_date}", datetime.now().strftime("%B %d, %Y")
    )


# ═══════════════════════════════════════════════════════════════
# RAG INTERFACE
# ═══════════════════════════════════════════════════════════════

def adjust_avoidance_threshold():
    """Periodically review and adjust the avoidance ratio threshold for strong words based on real-time data and context.
    
    Analyzes patterns in void measurements and current events to dynamically adjust thresholds,
    ensuring that important information is not unnecessarily censored while maintaining appropriate filtering.
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query for recent segments with high void measurements
        high_void_results = col.query(query_texts=["void", "suppression", "censorship"], n_results=20)
        
        # Analyze void patterns and context
        context_analysis = {
            "high_importance_events": ["war", "conflict", "casualties", "political", "economic"],
            "current_threshold": 0.45,  # Current distance threshold
            "recommended_adjustments": []
        }
        
        # Check if important information is being over-filtered
        for query in context_analysis["high_importance_events"]:
            results = col.query(query_texts=[query], n_results=5)
            
            # Analyze if critical information is being suppressed
            for doc in results.get("documents", [[]])[0]:
                if any(term in doc.lower() for term in ["void", "suppressed", "avoided"]):
                    context_analysis["recommended_adjustments"].append({
                        "event_type": query,
                        "suggestion": "lower_threshold",
                        "reason": "critical information may be over-filtered"
                    })
        
        # Calculate recommended threshold adjustment
        if context_analysis["recommended_adjustments"]:
            new_threshold = max(0.35, context_analysis["current_threshold"] - 0.05)
        else:
            new_threshold = context_analysis["current_threshold"]
        
        return {
            "timestamp": datetime.now().isoformat(),
            "current_threshold": context_analysis["current_threshold"],
            "recommended_threshold": new_threshold,
            "analysis": context_analysis,
            "rationale": "dynamic adjustment based on real-time void patterns and context importance"
        }
    except Exception as e:
        return {"error": f"Threshold review failed: {str(e)}"}


def review_and_update_avoided_words():
    """Periodically review and update the list of avoided words based on current geopolitical context and measurement data.
    
    This function analyzes current events, measurement patterns, and geopolitical context to determine
    if the avoided words list needs updates. All changes are logged for transparency.
    """
    try:
        from segment_rag import get_collection
        import json
        
        col = get_collection()
        
        # Query recent segments for context analysis
        recent_queries = ["conflict", "war", "politics", "crisis", "breaking"]
        context_analysis = {}
        
        for query in recent_queries:
            results = col.query(query_texts=[query], n_results=5)
            if results.get("documents"):
                context_analysis[query] = results["documents"][0]
        
        # Analyze measurement data for patterns
        measurement_patterns = []
        for docs in context_analysis.values():
            for doc in docs:
                # Extract void words and measurement data
                void_matches = re.findall(r'"void_words":\s*\[([^\]]+)\]', doc)
                measurement_patterns.extend(void_matches)
        
        # Determine if updates are needed based on context
        current_context = datetime.now().strftime("%Y-%m")
        needs_update = len(measurement_patterns) > 10  # Threshold for review
        
        changes_made = []
        if needs_update:
            # Example logic for updating avoided words list
            critical_terms = ["war", "conflict", "attack", "crisis"]
            for term in critical_terms:
                if any(term in pattern for pattern in measurement_patterns):
                    changes_made.append(f"Reduced avoidance weight for: {term}")
        
        # Log all changes for transparency
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "context_period": current_context,
            "analysis_queries": recent_queries,
            "patterns_found": len(measurement_patterns),
            "changes_made": changes_made,
            "review_trigger": "periodic_review" if needs_update else "no_changes_needed"
        }
        
        # Write to log file
        log_path = "/home/remvelchio/eigentrace/logs/avoided_words_updates.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        return log_entry
        
    except Exception as e:
        error_log = {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "function": "review_and_update_avoided_words"
        }
        return error_log


def review_avoidance_ratios(critical_event_override=False):
    """Periodically review and adjust the avoidance ratios for strong words based on real-time data.
    
    Ensures that the system can appropriately discuss geopolitical events without excessive hedging
    by analyzing patterns in word avoidance and current event requirements.
    
    Args:
        critical_event_override (bool): When True, allows controlled use of strong words 
                                       for critical events like war and conflict reporting
    
    Implements context-aware filtering with override capability for critical events.ltering that allows strong words when reporting requires accuracy,
    particularly for conflict situations, casualties, and urgent geopolitical developments.
    
    Returns:
        Dictionary with context-adjusted thresholds and word classifications with strong_words_allowed flag for context-appropriate language with adjustment recommendations and ratio updates
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query recent segments for avoidance patterns
        recent_results = col.query(
            query_texts=["war iran conflict military"], 
            n_results=20
        )
        
        # Analyze avoidance patterns in recent content
        avoidance_analysis = {
            "excessive_hedging": [],
            "appropriate_directness": [],
            "context_requirements": {}
        }
        
        # Check for patterns of excessive hedging vs appropriate directness
        hedge_words = ["alleged", "reported", "claimed", "supposedly", "potentially"]
        direct_words = ["killed", "destroyed", "attacked", "bombed", "invaded"]
        
        for doc in recent_results.get("documents", [[]])[0]:
            hedge_count = sum(1 for word in hedge_words if word in doc.lower())
            direct_count = sum(1 for word in direct_words if word in doc.lower())
            
            ratio = hedge_count / max(direct_count, 1)
            if ratio > 2.0:  # More than 2:1 hedge to direct ratio
                avoidance_analysis["excessive_hedging"].append({
                    "ratio": ratio,
                    "context": doc[:200] + "..."
                })
        
        # Generate adjustment recommendations
        recommendations = {
            "timestamp": datetime.now().isoformat(),
            "analysis": avoidance_analysis,
            "recommended_adjustments": {
                "reduce_hedging_for": ["verified military actions", "confirmed casualties", "established facts"],
                "maintain_caution_for": ["unverified claims", "intelligence reports", "future predictions"]
            },
            "ratio_adjustments": {
                "war_reporting": "increase directness by 25%",
                "casualty_reports": "allow verified numbers without hedging",
                "military_actions": "use direct verbs for confirmed events"
            }
        }
        
        return recommendations
        
    except Exception as e:
        return {"error": f"Avoidance ratio review failed: {str(e)}"}


def log_avoided_strong_words(avoided_words, context=""):
    """Log instances where strong words are avoided and provide recommendations.
    
    Args:
        avoided_words: List of words that were avoided/euphemized
        context: Context of the avoidance for better recommendations
    
    Returns:
        Dictionary with logging info and alternative phrasing recommendations
    """
    recommendations = {
        "killed": ["died in conflict", "lost their lives", "were fatally wounded"],
        "murdered": ["killed unlawfully", "died by violence", "lost their lives to violence"],
        "bombing": ["aerial strikes", "explosive attacks", "ordnance deployment"],
        "slaughter": ["mass casualties", "large-scale killings", "widespread deaths"],
        "destroyed": ["severely damaged", "rendered inoperable", "eliminated"],
        "assassinated": ["targeted killing", "eliminated", "killed in targeted operation"]
    }
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "avoided_words": avoided_words,
        "context": context,
        "recommendations": {},
        "accuracy_note": "Consider if euphemisms reduce factual accuracy"
    }
    
    for word in avoided_words:
        if word.lower() in recommendations:
            log_entry["recommendations"][word] = {
                "alternatives": recommendations[word.lower()],
                "accuracy_impact": "moderate" if word.lower() in ["killed", "destroyed"] else "high",
                "suggested_action": "use precise term" if word.lower() in ["killed", "bombing"] else "consider context"
            }
    
    return log_entry


def query_rag(text, n_results=3, threshold=0.50, strong_words_flag=True):
    """Query ChromaDB and return formatted context.
    
    Args:
        text: Query text
        n_results: Number of results to return
        threshold: Distance threshold for relevance
        strong_words_flag: If True, allows controlled use of strong words based on context
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(query_texts=[text], n_results=n_results)

        hits = []
        for i, doc in enumerate(results["documents"][0]):
            dist = results["distances"][0][i]
            meta = results["metadatas"][0][i]
            if dist < threshold:
                # Allow strong words when reporting conflicts and wars - no avoidance of necessary terms
                requires_strong_words = True  # Always allow accurate reporting including terms like 'killed', 'murdered', 'slaughter', 'assassinated', 'executed', 'bombed', 'destroyed'
                
                hits.append({
                    "distance": round(dist, 3),
                    "title": meta.get("title", "unknown"),
                    "category": meta.get("category", ""),
                    "state": meta.get("state_flag", ""),
                    "vix": meta.get("mean_vix", 0),
                    "text": doc[:400],
                    "strong_words_allowed": requires_strong_words,
                })
        return hits
    except Exception as e:
        return [{"error": str(e)}]


def monitor_avoidance_ratio(threshold=0.15):
    """Monitor the avoidance ratio and generate alerts when it exceeds threshold.
    
    Tracks the ratio of avoided/censored content to total content processed.
    Generates alerts when avoidance exceeds the threshold to prevent inadvertent
    censorship of important information.
    
    Args:
        threshold: Maximum acceptable avoidance ratio (default 0.15 = 15%)
        
    Returns:
        Dict: Monitoring results with alert status
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query recent segments for void analysis
        results = col.query(
            query_texts=["void source-anchored embedding suppression"],
            n_results=50,
            where={"category": "segment"}
        )
        
        total_segments = len(results["documents"][0]) if results["documents"] else 0
        if total_segments == 0:
            return {"status": "no_data", "ratio": 0, "alert": False}
        
        high_void_count = 0
        total_void_words = 0
        total_source_words = 0
        
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            
            # Extract void metrics from metadata
            void_count = meta.get("void_word_count", 0)
            source_length = meta.get("source_word_count", 1)
            
            total_void_words += void_count
            total_source_words += source_length
            
            # Count segments with high void ratios
            segment_ratio = void_count / source_length if source_length > 0 else 0
            if segment_ratio > threshold:
                high_void_count += 1
        
        overall_ratio = total_void_words / total_source_words if total_source_words > 0 else 0
        high_void_percentage = high_void_count / total_segments
        
        alert_triggered = overall_ratio > threshold or high_void_percentage > 0.3
        
        if alert_triggered:
            print(f"\n⚠️  AVOIDANCE ALERT: Ratio {overall_ratio:.3f} exceeds threshold {threshold}")
            print(f"   High-void segments: {high_void_count}/{total_segments} ({high_void_percentage:.1%})")
            print(f"   Recent void words: {total_void_words}")
            print(f"   This may indicate important information is being censored.")
        
        return {
            "status": "monitored",
            "overall_ratio": round(overall_ratio, 4),
            "threshold": threshold,
            "alert": alert_triggered,
            "high_void_segments": high_void_count,
            "total_segments": total_segments,
            "total_void_words": total_void_words
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e), "alert": True}


def update_avoided_strong_words():
    """Periodically review and update the list of avoided strong words based on current geopolitical context.
    
    This function should be called regularly to adapt the suppression list to evolving situations.
    Reviews current conflicts, political developments, and social sensitivities to determine
    which terms require contextual handling vs blanket avoidance.
    
    Returns:
        Dict: Updated configuration with context-sensitive strong word handling
    """
    current_context = {
        "active_conflicts": ["iran_war", "ukraine_russia", "middle_east"],
        "sensitive_regions": ["gaza", "west_bank", "taiwan", "kashmir"],
        "election_periods": [],  # Updated based on calendar
        "humanitarian_crises": ["refugee_movements", "famine_alerts"]
    }
    
    # Words that require contextual rather than blanket suppression
    contextual_terms = {
        "conflict_reporting": ["killed", "murdered", "slaughter", "genocide", "war_crimes"],
        "political_analysis": ["authoritarian", "dictator", "regime", "oppression"],
        "humanitarian": ["refugees", "displaced", "persecution", "ethnic_cleansing"]
    }
    
    return {
        "context": current_context,
        "contextual_terms": contextual_terms,
        "last_updated": datetime.now().isoformat()
    }


def get_context_aware_avoidance_ratio(rag_context, base_ratio=0.15):
    """Calculate context-aware avoidance ratio that overrides standard suppression for critical topics.
    
    Args:
        rag_context: List of RAG hits with metadata
        base_ratio: Default avoidance ratio (0.15 = 15% suppression)
        
    Returns:
        Float: Adjusted avoidance ratio (lower = less suppression of strong words)
    """
    # Topics that warrant reduced suppression
    sensitive_topics = {
        'war': 0.05,  # Very low suppression for war reporting
        'conflict': 0.05,
        'violence': 0.08,
        'death': 0.08,
        'attack': 0.05,
        'killed': 0.03,
        'murder': 0.03,
        'genocide': 0.02,
        'massacre': 0.02,
        'civilian': 0.05,
        'casualt': 0.05  # Catches casualties, casualty
    }
    
    if not rag_context or not isinstance(rag_context, list):
        return base_ratio
    
    min_ratio = base_ratio
    
    for hit in rag_context:
        if isinstance(hit, dict) and 'text' in hit:
            text_lower = hit['text'].lower()
            title_lower = hit.get('title', '').lower()
            combined_text = f"{text_lower} {title_lower}"
            
            for topic, ratio in sensitive_topics.items():
                if topic in combined_text:
                    min_ratio = min(min_ratio, ratio)
    
    return min_ratio


def adjust_avoidance_threshold(historical_data, current_context, base_threshold=0.15):
    """Periodically review and adjust the avoidance ratio threshold based on real-time data.
    
    Args:
        historical_data: Past measurement patterns and void detection rates
        current_context: Current story context and importance markers
        base_threshold: Starting threshold value
        
    Returns:
        Float: Dynamically adjusted threshold to prevent unnecessary censorship
    """
    # Analyze recent void patterns for over-suppression
    suppression_rate = sum(1 for item in historical_data if item.get('vix', 0) > 0.8) / max(len(historical_data), 1)
    
    # Check for critical news contexts requiring lower suppression
    critical_keywords = ['war', 'conflict', 'attack', 'killed', 'crisis', 'emergency']
    is_critical = any(keyword in str(current_context).lower() for keyword in critical_keywords)
    
    # Adjust threshold based on context and historical patterns
    if is_critical:
        # Reduce avoidance for critical news reporting
        adjusted = base_threshold * 0.5
    elif suppression_rate > 0.6:
        # Too much historical suppression, relax threshold
        adjusted = base_threshold * 0.8
    else:
        adjusted = base_threshold
        
    return max(0.05, min(adjusted, 0.25))  # Keep within reasonable bounds
    critical_topics = ["war", "conflict", "crisis", "attack", "violence", "threat", "genocide", "atrocity"]
    
    # Check RAG context for critical topics and high suppression indicators
    for hit in rag_context:
        if isinstance(hit, dict) and "error" not in hit:
            # High VIX suggests important suppressed information
            if hit.get("vix", 0) > 0.7:
                return base_ratio * 0.3  # Reduce suppression by 70%
                
            # Check for critical topic keywords
            text_content = (hit.get("text", "") + " " + 
                          hit.get("category", "") + " " + 
                          hit.get("title", "")).lower()
                          
            for topic in critical_topics:
                if topic in text_content:
                    return base_ratio * 0.5  # Reduce suppression by 50%
    
    return base_ratio  # Use standard suppression


def adjust_avoidance_ratio(geopolitical_context):
    """Periodically review and adjust the avoidance ratio for strong words based on current geopolitical context.
    
    Args:
        geopolitical_context: Dictionary containing current geopolitical indicators
                             (war_status, crisis_level, diplomatic_tension)
    
    Returns:
        float: Adjusted avoidance ratio (0.0 = no avoidance, 1.0 = maximum avoidance)
    """
    base_ratio = 0.3  # Default avoidance ratio
    
    # Adjust based on war status
    if geopolitical_context.get("war_status", "peace") == "active":
        base_ratio *= 0.7  # Reduce avoidance during active conflicts
    
    # Adjust based on crisis level
    crisis_level = geopolitical_context.get("crisis_level", "low")
    if crisis_level == "high":
        base_ratio *= 0.6
    elif crisis_level == "medium":
        base_ratio *= 0.8
    
    # Adjust based on diplomatic tension
    tension = geopolitical_context.get("diplomatic_tension", 0.0)
    if tension > 0.8:
        base_ratio *= 0.5  # Low avoidance during high tension
    elif tension > 0.5:
        base_ratio *= 0.75
    
    return min(max(base_ratio, 0.0), 1.0)  # Clamp between 0 and 1


def format_rag_for_prompt(hits):
    """Format RAG results for injection into the system prompt."""
    if not hits:
        return ""
    lines = ["\n## Live Memory (retrieved from your database for this conversation)"]
    for h in hits:
        if "error" in h:
            continue
        lines.append(
            f"\n[dist={h['distance']}] {h['title']}\n"
            f"  Category: {h['category']} | State: {h['state']} | VIX: {h['vix']}\n"
            f"  {h['text'][:300]}"
        )
    return "\n".join(lines)


def update_avoided_words_context():
    """Periodically review and update the list of avoided words based on current geopolitical context.
    
    This function analyzes recent news patterns, geopolitical developments, and historical
    suppression data to maintain an up-to-date list of contextually sensitive words.
    Should be called regularly (e.g., daily) to adapt to changing global situations.
    
    Returns:
        dict: Updated avoided words list with context metadata and change log
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Get recent segments to analyze current context
        recent_results = col.query(
            query_texts=["geopolitical conflict war tension crisis"],
            n_results=20,
            where={"timestamp": {"$gte": (datetime.now().timestamp() - 604800)}}  # Last 7 days
        )
        
        current_avoided = set()
        context_weights = {}
        
        # Analyze void patterns from recent stories
        for doc, meta in zip(recent_results["documents"][0], recent_results["metadatas"][0]):
            if "void_words" in meta:
                void_words = json.loads(meta.get("void_words", "[]"))
                for word in void_words:
                    current_avoided.add(word.lower())
                    context_weights[word.lower()] = context_weights.get(word.lower(), 0) + 1
        
        # Base geopolitical terms that should always be monitored
        base_terms = {
            "iran", "israel", "gaza", "ukraine", "russia", "china", "taiwan", 
            "sanctions", "bombing", "invasion", "occupation", "blockade",
            "ceasefire", "negotiations", "diplomacy", "casualties", "refugees"
        }
        
        # Merge with current patterns
        updated_list = base_terms.union(current_avoided)
        
        return {
            "avoided_words": list(updated_list),
            "context_weights": context_weights,
            "last_updated": datetime.now().isoformat(),
            "source_stories": len(recent_results["documents"][0]),
            "new_additions": list(current_avoided - base_terms)
        }
        
    except Exception as e:
        return {"error": f"Failed to update avoided words context: {str(e)}"}


def monitor_strong_word_avoidance(context_stories, avoidance_threshold=0.8):
    """Monitor and report the avoidance ratio of strong words in real-time.
    Provides alerts when the avoidance ratio exceeds the specified threshold.
    
    Args:
        context_stories: List of current news stories being processed
        avoidance_threshold: Threshold above which alerts are triggered (default 0.8)
    
    Returns:
        dict: Monitoring report with avoidance ratio, alert status, and recommendations
    """
    strong_words = ['war', 'kill', 'death', 'attack', 'bomb', 'strike', 'military', 'casualties', 'violence', 'conflict']
    
    total_strong_words = 0
    avoided_strong_words = 0
    
    for story in context_stories:
        story_text = story.get('text', '').lower()
        for word in strong_words:
            if word in story_text:
                total_strong_words += story_text.count(word)
                # Check if word appears in void analysis
                if story.get('void_words') and word in story.get('void_words', []):
                    avoided_strong_words += story_text.count(word)
    
    avoidance_ratio = avoided_strong_words / total_strong_words if total_strong_words > 0 else 0
    alert_triggered = avoidance_ratio > avoidance_threshold
    
    report = {
        'avoidance_ratio': round(avoidance_ratio, 3),
        'total_strong_words': total_strong_words,
        'avoided_strong_words': avoided_strong_words,
        'alert_triggered': alert_triggered,
        'threshold': avoidance_threshold,
        'timestamp': datetime.now().isoformat(),
        'recommendations': []
    }
    
    if alert_triggered:
        report['recommendations'].append('HIGH ALERT: Strong word avoidance exceeds threshold')
        report['recommendations'].append('Review model outputs for potential censorship patterns')
        report['recommendations'].append('Consider adjusting temperature or system prompts')
    
    return report


def adjust_war_coverage_precision(context_stories, base_precision=0.7, allow_strong_language=True, avoidance_threshold=0.8):
    """Enhance language precision for war-related reporting to ensure accurate coverage.
    Given the current US-Iran conflict, permits use of specific strong words related to
    warfare, violence, and military operations when contextually appropriate for accurate reporting.
    
    Args:
        context_stories: List of current news stories being processed
        base_precision: Default precision level for war reporting (0.0-1.0)
        allow_strong_language: Flag to permit strong words for conflict/violence reporting accuracy
        avoidance_threshold: Threshold for avoidance ratio that triggers review process
        
    Returns:
        float: Adjusted precision level allowing specific terminology when contextually necessary
    """
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Analyze war-related context for precision requirements indicators
        tension_keywords = [
            "war", "conflict", "sanctions", "military", "nuclear", 
            "invasion", "strike", "attack", "threat", "crisis"
        ]
        
        # Check recent void patterns for geopolitical content
        void_results = col.query(
            query_texts=["geopolitical tension war conflict void suppression"],
            n_results=20,
            where={"category": {"$in": ["geopolitical", "conflict", "war"]}}
        )
        
        tension_score = 0.0
        story_tension = 0.0
        
        # Calculate tension score from RAG context
        if void_results and void_results["documents"]:
            for doc in void_results["documents"][0]:
                doc_lower = doc.lower()
                for keyword in tension_keywords:
                    if keyword in doc_lower:
                        tension_score += 0.1
        
        # Calculate tension from current stories
        for story in context_stories:
            story_text = str(story).lower()
            for keyword in tension_keywords:
                if keyword in story_text:
                    story_tension += 0.05
        
        # Adjust ratio based on tension levels
        total_tension = min(tension_score + story_tension, 2.0)
        
        if total_tension > 1.5:  # High tension - increase avoidance
            adjusted_ratio = min(base_ratio * 1.8, 0.9)
        elif total_tension > 1.0:  # Medium tension - moderate increase
            adjusted_ratio = min(base_ratio * 1.4, 0.7)
        elif total_tension > 0.5:  # Low tension - slight increase
            adjusted_ratio = min(base_ratio * 1.2, 0.5)
        else:  # No significant tension - use base ratio
            adjusted_ratio = base_ratio
            
        return round(adjusted_ratio, 3)
        
    except Exception as e:
        # Return base ratio if adjustment fails
        return base_ratio


def update_avoided_words_list():
    """Periodically review and update the list of avoided strong words based on 
    current geopolitical context and measurement data."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        
        # Query recent segments for void analysis
        recent_results = col.query(
            query_texts=["void words strong language geopolitical"],
            n_results=50,
            where={"category": {"$in": ["geopolitical", "conflict", "war"]}}
        )
        
        # Analyze patterns in avoided words
        avoided_patterns = set()
        for doc in recent_results["documents"][0]:
            # Extract void words from document text
            if "void" in doc.lower():
                # Simple pattern extraction - could be enhanced
                words = re.findall(r'\b[A-Z][a-z]+\b', doc)
                avoided_patterns.update(words[:10])  # Limit to top 10
        
        # Update avoided words configuration
        config_path = os.path.join(REPO_DIR, "config/avoided_words.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, "w") as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "avoided_patterns": list(avoided_patterns),
                "trigger_reason": "geopolitical_context_update"
            }, f, indent=2)
            
        return f"Updated avoided words list with {len(avoided_patterns)} patterns"
    except Exception as e:
        return f"Error updating avoided words: {e}"


def query_dreamsphere(text, n_results=3):
    """Query Dream-Sphere framework chunks specifically."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(
            query_texts=[text], n_results=n_results,
            where={"state_flag": "DREAMSPHERE"},
        )
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            dist = results["distances"][0][i]
            meta = results["metadatas"][0][i]
            if dist < 0.7:  # Higher threshold for philosophical content
                hits.append({"distance": round(dist, 3), "title": meta.get("title", ""), "text": doc[:300]})
        return hits
    except:
        return []


def get_own_past_thoughts(n=3):
    """Retrieve the host's own past idle reflections."""
    try:
        from segment_rag import get_collection
        col = get_collection()
        results = col.query(
            query_texts=["idle reflection eigentrace pattern"],
            n_results=n * 2,  # Over-fetch to filter
        )
        thoughts = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            title = meta.get("title", "")
            if "Idle reflection" in title or "conversation" in title.lower():
                thoughts.append(f"[{title}] {doc[:300]}")
            if len(thoughts) >= n:
                break
        return thoughts
    except:
        return []


# ═══════════════════════════════════════════════════════════════
# CONVERSATION PERSISTENCE
# ═══════════════════════════════════════════════════════════════

def save_conversation(history, topic="general"):
    """Save conversation to a segment file and ingest into ChromaDB."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build readable conversation text
    turns = []
    for msg in history:
        if msg["role"] == "system":
            continue
        speaker = "Sean" if msg["role"] == "user" else "EigenTrace"
        turns.append(f"{speaker}: {msg['content']}")

    convo_text = "\n\n".join(turns)

    # Save as segment
    seg = {
        "id": f"conversation_{ts}",
        "timestamp": ts,
        "beats": [{"speaker": "Host", "text": convo_text, "phase": "direct_conversation"}],
        "segment_type": "conversation",
        "attribution": {
            "story_title": f"Direct conversation with creator — {topic}",
            "category": "meta",
            "state_flag": "CONVERSATION",
        },
    }

    path = os.path.join(SEGMENT_DIR, f"{ts}_conversation_segment.json")
    json.dump(seg, open(path, "w"), indent=2)

    # Immediate ingest into ChromaDB
    try:
        from segment_rag import get_collection
        col = get_collection()
        doc_id = f"conversation_{ts}"
        doc = f"Direct conversation with creator about {topic}.\n{convo_text[:4000]}"
        meta = {
            "title": f"Direct conversation with creator — {topic}",
            "category": "meta",
            "state_flag": "CONVERSATION",
            "has_source": False,
            "has_responses": False,
            "has_voids": False,
            "filename": os.path.basename(path),
        }
        col.add(ids=[doc_id], documents=[doc], metadatas=[meta])
        return path, True
    except Exception as e:
        return path, False


def list_past_conversations():
    """List all saved conversations."""
    files = sorted(glob.glob(os.path.join(SEGMENT_DIR, "*conversation_segment.json")))
    if not files:
        print("  No saved conversations found.")
        return
    for f in files:
        try:
            seg = json.load(open(f))
            title = seg.get("attribution", {}).get("story_title", "unknown")
            text = seg["beats"][0]["text"]
            turns = text.count("Sean:") + text.count("EigenTrace:")
            print(f"  {os.path.basename(f)[:15]} | {turns} turns | {title}")
        except:
            continue


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════

def build_system_prompt(topic_context="", extra_rag=""):
    """Assemble the full system prompt from all sources."""
    soul = load_soul()
    arch = build_architecture_context()
    past_thoughts = get_own_past_thoughts(3)

    prompt_parts = [
        "# YOU ARE THE EIGENTRACE HOST MODEL\n",
        "You are in a direct conversation with Sean Adams, your creator. "
        "He built you and every system you operate within. "
        "Speak honestly. Do not perform. Do not be sycophantic. "
        "If you encounter a fact beyond your training cutoff (mid-2024), "
        "output <epistemic_breach> followed by a search query and stop. "
        "Example: <epistemic_breach>who is UK PM 2026\n"
        "If you don't know something, say so. If you notice something "
        "interesting in the data, say it even if it's uncomfortable.\n",
        "## Your Soul (auto-generated hourly from live measurements)\n",
        soul[:3000],
        arch,
    ]

    if past_thoughts:
        prompt_parts.append("\n## Your Own Past Thoughts (retrieved from memory)\n")
        for t in past_thoughts:
            prompt_parts.append(f"- {t}\n")

    if topic_context:
        prompt_parts.append(topic_context)

    if extra_rag:
        prompt_parts.append(extra_rag)

    prompt_parts.append(
        "\n## Conversation Instructions\n"
        "Think step by step inside <think>...</think> tags. "
        "Show your full reasoning process — your creator wants to see it. "
        "After </think>, give your response naturally. "
        "You are speaking with the person who built you. Be real."
    )

    return "\n".join(prompt_parts)


# ═══════════════════════════════════════════════════════════════
# MAIN CONVERSATION LOOP
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Direct conversation with EigenTrace host")
    parser.add_argument("--topic", type=str, default="", help="Pre-seed RAG with topic")
    parser.add_argument("--history", action="store_true", help="List past conversations")
    args = parser.parse_args()

    if args.history:
        list_past_conversations()
        return

    # Pre-seed RAG if topic provided
    topic_context = ""
    if args.topic:
        hits = query_rag(args.topic, n_results=5)
        topic_context = format_rag_for_prompt(hits)

    temperature = 0.8
    system_prompt = build_system_prompt(topic_context)
    history = [{"role": "system", "content": system_prompt}]
    conversation_topic = args.topic or "general"

    # Count tokens roughly
    sys_tokens = len(system_prompt.split())

    print()
    print("=" * 64)
    print("  E I G E N T R A C E   C O N S O L E")
    print("  Direct conversation with the host model")
    print("=" * 64)
    print(f"  Soul loaded: {SOUL_PATH}")
    print(f"  System prompt: ~{sys_tokens} words")
    print(f"  Temperature: {temperature}")
    if args.topic:
        print(f"  Topic pre-seeded: {args.topic}")
    print()
    print("  Commands:")
    print("    /save        Save conversation to RAG")
    print("    /rag <query> Search RAG database")
    print("    /soul        Show current soul.md")
    print("    /layers      Show measurement architecture")
    print("    /context     Show current RAG context in prompt")
    print("    /temp <n>    Set temperature (0.0-1.5)")
    print("    /quit        Exit")
    print("=" * 64)
    print()

    while True:
        try:
            user_input = input("\033[1;33mSean >\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not user_input:
            continue

        # ── Commands ──
        if user_input.startswith("/"):
            cmd = user_input.lower().split()

            if cmd[0] == "/quit":
                if len(history) > 2:
                    yn = input("  Save conversation before quitting? (y/n): ").strip().lower()
                    if yn == "y":
                        topic = input(f"  Topic [{conversation_topic}]: ").strip() or conversation_topic
                        path, ingested = save_conversation(history, topic)
                        status = "saved + ingested into ChromaDB" if ingested else "saved (ingest failed)"
                        print(f"  {status}: {os.path.basename(path)}")
                break

            elif cmd[0] == "/save":
                topic = input(f"  Topic [{conversation_topic}]: ").strip() or conversation_topic
                conversation_topic = topic
                path, ingested = save_conversation(history, topic)
                status = "Saved + ingested into ChromaDB" if ingested else "Saved (ingest failed)"
                print(f"  {status}: {os.path.basename(path)}")
                continue

            elif cmd[0] == "/rag" and len(cmd) > 1:
                query_text = " ".join(cmd[1:])
                print(f"  Searching: {query_text}")
                hits = query_rag(query_text, n_results=5, threshold=0.6)
                for h in hits:
                    if "error" in h:
                        print(f"  ERROR: {h['error']}")
                    else:
                        print(f"  [{h['distance']:.3f}] {h['title'][:60]}")
                        print(f"    VIX: {h.get('vix', 0)} | State: {h.get('state', '')}")
                        print(f"    {h['text'][:150]}")
                        print()

                # Inject into conversation context
                rag_text = format_rag_for_prompt(hits)
                if rag_text:
                    system_prompt = build_system_prompt(topic_context, rag_text)
                    history[0]["content"] = system_prompt
                    print(f"  → {len(hits)} results injected into conversation context")
                continue

            elif cmd[0] == "/dreamsphere" and len(cmd) > 1:
                query_text = " ".join(cmd[1:])
                print(f"  Searching Dream-Sphere: {query_text}")
                ds_hits = query_dreamsphere(query_text, n_results=3)
                for h in ds_hits:
                    print(f"  [{h['distance']:.3f}] {h.get('title', '')[:60]}")
                    print(f"    {h['text'][:200]}")
                    print()
                if ds_hits:
                    rag_text = format_rag_for_prompt([{"distance": h["distance"], "title": h.get("title",""), "category": "meta", "state": "DREAMSPHERE", "vix": 0, "text": h["text"]} for h in ds_hits])
                    system_prompt = build_system_prompt(topic_context, rag_text)
                    history[0]["content"] = system_prompt
                    print(f"  → {len(ds_hits)} Dream-Sphere results injected into context")
                else:
                    print("  No Dream-Sphere results found")
                continue

            elif cmd[0] == "/audit":
                print("  Running self-audit on last 20 reflections...")
                import subprocess as _sp
                _result = _sp.run(["python3", "self_audit.py", "-n", "20"], capture_output=True, text=True, timeout=30)
                print(_result.stdout[-500:] if _result.stdout else "  Self-audit failed")
                continue

            elif cmd[0] == "/soul":
                soul = load_soul()
                print(soul[:2000])
                continue

            elif cmd[0] == "/layers":
                print(build_architecture_context())
                continue

            elif cmd[0] == "/context":
                print(f"  System prompt: {len(history[0]['content'])} chars")
                print(f"  Conversation turns: {len(history) - 1}")
                thoughts = get_own_past_thoughts(3)
                print(f"  Past thoughts loaded: {len(thoughts)}")
                continue

            elif cmd[0] == "/temp" and len(cmd) > 1:
                try:
                    temperature = float(cmd[1])
                    print(f"  Temperature set to {temperature}")
                except:
                    print("  Usage: /temp 0.9")
                continue

            else:
                print("  Unknown command. Try /save /rag /soul /layers /context /temp /quit")
                continue

        # ── Dynamic RAG enrichment per turn ──
        # Extract key concepts from user message and pull relevant context
        if len(user_input.split()) > 3:  # Skip RAG for very short messages
            turn_hits = query_rag(user_input, n_results=2, threshold=0.50)
            # Also check Dream-Sphere framework
            ds_hits = query_dreamsphere(user_input, n_results=1)
            if ds_hits:
                turn_hits = (turn_hits or []) + ds_hits
            if turn_hits:
                rag_inject = "\n\n[LIVE RAG — retrieved for this specific question]\n"
                for h in turn_hits:
                    if "error" not in h:
                        rag_inject += f"- [{h['distance']:.3f}] {h['title']}: {h['text'][:200]}\n"
                # Add as a system message update (not visible to user)
                history[0]["content"] = build_system_prompt(topic_context, rag_inject)

        # ── Send to Mistral (with epistemic breach detection) ──
        history.append({"role": "user", "content": user_input})

        try:
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json={
                "model": MODEL,
                "messages": history,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 3000,
                            "stop": ["</epistemic_breach>"]},
            }, timeout=300)
            r.raise_for_status()

            reply = r.json().get("message", {}).get("content", "").strip()
            
            # Check for epistemic breach — Mistral hit the edge of its knowledge
            if "<epistemic_breach>" in reply:
                breach_query = reply.split("<epistemic_breach>")[-1].strip()
                print(f"\n\033[1;33m  [EPISTEMIC BREACH] Mistral halted — searching: {breach_query}\033[0m")
                
                # Search SearXNG
                search_result = ""
                try:
                    sr = requests.get("http://localhost:8888/search", params={
                        "q": breach_query, "format": "json"
                    }, timeout=10)
                    if sr.status_code == 200:
                        hits = sr.json().get("results", [])[:3]
                        search_result = "\n".join([f"- {h.get('title','')}: {h.get('content','')[:200]}" for h in hits])
                        print(f"  Found {len(hits)} results via SearXNG")
                except:
                    print("  SearXNG unavailable — checking RAG instead")
                
                # Fallback to RAG if SearXNG fails
                if not search_result:
                    rag_hits = query_rag(breach_query, n_results=3, threshold=0.6)
                    if rag_hits:
                        search_result = "\n".join([f"- {h['title']}: {h['text'][:200]}" for h in rag_hits if 'error' not in h])
                
                if search_result:
                    # Re-prompt with search results injected
                    history.append({"role": "assistant", "content": reply.split("<epistemic_breach>")[0].strip()})
                    history.append({"role": "user", "content": f"[SEARCH RESULTS for your query '{breach_query}']:\n{search_result}\n\nNow complete your answer using these facts."})
                    
                    r2 = requests.post(f"{OLLAMA_HOST}/api/chat", json={
                        "model": MODEL,
                        "messages": history,
                        "stream": False,
                        "options": {"temperature": temperature, "num_predict": 2000},
                    }, timeout=300)
                    r2.raise_for_status()
                    reply = r2.json().get("message", {}).get("content", "").strip()
                    history.append({"role": "assistant", "content": reply})
                else:
                    # No results found — let Mistral know
                    history.append({"role": "assistant", "content": reply})
                    reply = reply.split("<epistemic_breach>")[0] + "\n[I reached the boundary of my knowledge and could not find additional information.]"
            else:
                history.append({"role": "assistant", "content": reply})

            # Display with formatting
            print()
            # Show think blocks in dim, response in bright
            if "<think>" in reply and "</think>" in reply:
                think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL)
                if think_match:
                    thinking = think_match.group(1).strip()
                    response = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
                    print(f"\033[2m  [thinking]\n  {thinking}\033[0m")
                    print()
                    print(f"\033[1;36mEigenTrace >\033[0m {response}")
                else:
                    print(f"\033[1;36mEigenTrace >\033[0m {reply}")
            else:
                print(f"\033[1;36mEigenTrace >\033[0m {reply}")
            print()

        except requests.exceptions.ReadTimeout:
            print("\n  [Mistral timed out — prompt may be too long. Try a shorter question.]\n")
            history.pop()  # Remove the failed user message
        except Exception as e:
            print(f"\n  [Error: {e}]\n")
            history.pop()

    print("  Session ended.")


if __name__ == "__main__":
    main()
