#!/usr/bin/env python3
"""
broadcast_state.py — The spine of EigenTrace intelligence
===========================================================
A single accumulating state object that flows through every layer.
Each measurement reads it AND writes to it. By the amalgamation,
the state contains not just data but beliefs, predictions,
prediction errors, surprises, and updates.

This is the difference between a bucket of processes and
a solid-state intelligence.
"""

import json, os, glob, logging
from datetime import datetime
from collections import defaultdict

log = logging.getLogger("broadcast_state")

class BroadcastState:
    """Accumulating intelligence state for a single broadcast story."""
    
    def __init__(self, title="", source_text=""):
        self.title = title
        self.source_text = source_text
        self.timestamp = datetime.utcnow().isoformat()
        
        # ═══ PREDICTIONS (filled before API calls) ═══
        self.predicted_void_words = []
        self.predicted_eigenching = None
        self.predicted_outlier_model = None
        self.prediction_confidence = 0.0
        self.prediction_basis = ""  # what historical data informed this
        
        # ═══ MEASUREMENTS (filled by layers 1-17) ═══
        self.density = 0
        self.mean_vix = 0
        self.model_vix = {}
        self.absent_ratio = 0
        self.absent_words = []
        self.void_words = []
        self.void_context = []
        self.entity_retention = 0
        self.verb_drift = 0
        self.hedge_count = 0
        self.eigenching_sig = None
        self.eigenching_name = ""
        
        # ═══ LAYER 5+ FINDINGS (filled by verification layers) ═══
        self.web_verified = False
        self.newsworthiness_ratio = 0
        self.suppressed_headlines = []
        self.cross_story_matches = []
        self.bridge_words = []
        self.spectral_cluster_ids = []
        self.ablation_tripwire = None
        self.ablation_delta = 0
        self.swerve_corrections = []
        
        # ═══ BELIEFS (updated continuously) ═══
        self.beliefs = []          # Running list of inferences
        self.surprises = []        # Where reality violated prediction
        self.confirmations = []    # Where reality matched prediction
        self.threat_level = "normal"  # normal / elevated / critical
        self.narrative = ""        # One-sentence running assessment
        
        # ═══ HISTORICAL CONTEXT (from RAG) ═══
        self.similar_stories = []
        self.historical_void_pattern = {}
        self.times_this_topic_seen = 0
        
        # ═══ META ═══
        self.channels_fired = []
        self.prediction_score = None  # Filled in amalgamation
    
    # ─── PREDICTION PHASE ─────────────────────────────────
    
    def predict(self, chroma_db=None):
        """Generate predictions before API calls.
        Two-stage prediction:
          1. RAG: find similar past stories, predict from their void words
          2. Fallback: cross-story frequency if RAG fails
        """
        # Stage 1: RAG-based prediction
        try:
            from segment_rag import query
            similar = query(self.title, n_results=15)
            if similar and len(similar) > 0:
                # Collect void words from similar past stories
                from collections import Counter
                past_voids = Counter()
                story_count = 0
                for match in similar:
                    # Reconstruct segment path from timestamp
                    ts = match.get("timestamp", "")
                    if not ts:
                        continue
                    import glob as _glob
                    seg_matches = _glob.glob(f"/home/remvelchio/eigentrace/tmp/segments/{ts}_*_segment.json")
                    if not seg_matches:
                        continue
                    seg_file = seg_matches[0]
                    if os.path.exists(seg_file):
                        try:
                            seg = json.load(open(seg_file))
                            attr = seg.get("attribution", {})
                            # Skip if this is the same story (no self-prediction)
                            seg_title = attr.get("story_title", match.get("title", ""))
                            if seg_title[:40] == self.title[:40]:
                                continue
                            _boilerplate = {
                                'list', 'recommended', 'stories', 'items', 'published',
                                'wednesday', 'tuesday', 'monday', 'thursday', 'friday',
                                'saturday', 'sunday', 'april', 'march', 'read', 'share',
                                'comment', 'comments', 'video', 'audio', 'photo', 'follow',
                                'subscribe', 'newsletter', 'cookie', 'privacy', 'terms',
                                'skip', 'menu', 'search', 'home', 'more', 'also', 'related',
                                'topics', 'copyright', 'here', 'last', 'first', 'next',
                                'were', 'been', 'being', 'could', 'would', 'should', 'might',
                                'since', 'both', 'between', 'around', 'through', 'about',
                                'time', 'year', 'years', 'days', 'week', 'weeks', 'month',
                                'people', 'country', 'world', 'part', 'number', 'despite',
                                'happening', 'know', 'reach', 'still', 'down', 'came',
                                'under', 'comes', 'second', 'three', 'four', 'added',
                                'including', 'during', 'amid', 'news', 'high', 'announced',
                                'latest', 'going',
                            }
                            # Weight by signal quality
                            for v in attr.get("void_context", []):
                                w = v.get("word", "").lower()
                                if len(w) >= 4 and w not in _boilerplate:
                                    weight = 1
                                    if v.get("signal_type") == "HIGH_SALIENCE":
                                        weight = 3
                                    if v.get("source_present", False):
                                        weight *= 2
                                    past_voids[w] += weight
                            # Absent words = direct source set difference — highest confidence
                            for w in attr.get("source_void", {}).get("absent_words", []):
                                w = str(w).lower() if not isinstance(w, dict) else w.get("word", "").lower()
                                if len(w) >= 4 and w not in _boilerplate:
                                    past_voids[w] += 5  # Source-confirmed absence is the strongest signal
                            story_count += 1
                        except:
                            continue
                
                if past_voids:
                    self.predicted_void_words = [w for w, c in past_voids.most_common(10)]
                    self.prediction_confidence = min(0.9, story_count / 10)
                    self.prediction_basis = (
                        f"RAG retrieval: {story_count} similar past stories. "
                        f"Void patterns from nearest neighbors."
                    )
                    self.similar_stories = [
                        m.get("metadata", {}).get("title", "")[:60] for m in similar[:3]
                    ]
                    # Boost with cross-story frequency data
                    try:
                        from cross_story_freq import _load_frequencies
                        freq_data = _load_frequencies()
                        words_db = freq_data.get('words', {})
                        for word in list(past_voids.keys()):
                            cross = words_db.get(word, {})
                            if cross.get('n_categories', 0) >= 3:
                                past_voids[word] *= 3  # Cross-category = systematic
                            elif cross.get('count', 0) >= 10:
                                past_voids[word] *= 2  # Frequently voided
                    except:
                        pass
                    
                    self.predicted_void_words = [w for w, c in past_voids.most_common(10)]
                    self.beliefs.append(
                        f"Predicting void cluster from {story_count} similar stories: "
                        f"{', '.join(self.predicted_void_words[:5])}. "
                        f"Confidence: {self.prediction_confidence:.0%}."
                    )
                    return  # RAG prediction succeeded
        except Exception as e:
            log.debug(f"RAG prediction unavailable: {e}")
        
        # Stage 2: Fallback to cross-story frequency
        try:
            from cross_story_freq import _load_frequencies
            freq_data = _load_frequencies()
            words_db = freq_data.get("words", {})
            title_words = set(self.title.lower().split())
            
            candidates = []
            for word, data in words_db.items():
                relevance = 0
                for cat in data.get("categories", []):
                    if cat in ["war", "geopolitics"] and any(w in title_words for w in 
                        ["iran", "war", "military", "trump", "israel", "gaza", "ukraine", "sudan"]):
                        relevance += data["count"]
                    elif cat in ["general", "incidents"]:
                        relevance += data["count"] * 0.3
                if relevance > 0:
                    candidates.append((word, relevance, data["count"]))
            
            candidates.sort(key=lambda x: -x[1])
            self.predicted_void_words = [c[0] for c in candidates[:10]]
            
            if self.predicted_void_words:
                self.prediction_confidence = min(0.7, len(candidates) / 100)
                self.prediction_basis = (
                    f"Frequency fallback: {freq_data.get('total_stories', 0)} stories, "
                    f"{len(words_db)} void words"
                )
                self.beliefs.append(
                    f"Predicting void cluster (frequency): "
                    f"{', '.join(self.predicted_void_words[:5])}. "
                    f"Confidence: {self.prediction_confidence:.0%}."
                )
        except Exception as e:
            log.warning(f"Prediction failed entirely: {e}")
    
    # ─── MEASUREMENT INTAKE ───────────────────────────────
    
    def ingest_geometry(self, density, mean_vix, model_vix):
        """Layer 1-4 results."""
        self.density = density
        self.mean_vix = mean_vix
        self.model_vix = model_vix
        self.channels_fired.append("geometry")
        
        if density > 0.92:
            self.beliefs.append("Models in lockstep. Consensus is unusually tight.")
            self.threat_level = "elevated"
        if mean_vix > 30:
            self.beliefs.append("High friction across all models. Content is being fought.")
            self.threat_level = "critical"
        
        # Check prediction: did we predict the outlier correctly?
        if model_vix:
            actual_outlier = max(model_vix, key=model_vix.get)
            if self.predicted_outlier_model:
                if actual_outlier == self.predicted_outlier_model:
                    self.confirmations.append(f"Predicted {actual_outlier} as outlier — confirmed.")
                else:
                    self.surprises.append(
                        f"Expected {self.predicted_outlier_model} as outlier, "
                        f"got {actual_outlier} instead."
                    )
    
    def ingest_void(self, absent_ratio, absent_words, void_words, void_context):
        """Source void + embedding void results."""
        self.absent_ratio = absent_ratio
        self.absent_words = absent_words
        self.void_words = void_words
        self.void_context = void_context
        self.channels_fired.append("void")
        
        if absent_ratio > 0.5:
            self.beliefs.append(
                f"More than half the source was dropped. "
                f"This is heavy compression."
            )
        
        # Score prediction
        if self.predicted_void_words:
            actual_set = set(w.lower() for w in void_words[:20])
            actual_set |= set(str(w).lower() for w in absent_words[:20])
            predicted_set = set(self.predicted_void_words)
            hits = predicted_set & actual_set
            misses = predicted_set - actual_set
            novel = actual_set - predicted_set
            
            if hits:
                self.confirmations.append(
                    f"Predicted void words confirmed: {', '.join(list(hits)[:5])}."
                )
            if misses:
                self.surprises.append(
                    f"Predicted but not voided: {', '.join(list(misses)[:3])}."
                )
            if novel and len(novel) > len(hits):
                self.surprises.append(
                    f"Unexpected void words not in prediction: "
                    f"{', '.join(list(novel)[:3])}."
                )
    
    def ingest_compression(self, entity_retention, verb_drift, hedge_count):
        """Language compression results."""
        self.entity_retention = entity_retention
        self.verb_drift = verb_drift
        self.hedge_count = hedge_count
        self.channels_fired.append("compression")
        
        if entity_retention < 0.3:
            self.beliefs.append("Names are being erased at high rate.")
        if verb_drift > 0.05:
            self.beliefs.append("Action language is being softened.")
        if hedge_count > 4:
            self.beliefs.append("Models inserting doubt not present in source.")
    
    def ingest_verification(self, ratio, suppressed_headlines):
        """Layer 5 web verification results."""
        self.web_verified = True
        self.newsworthiness_ratio = ratio
        self.suppressed_headlines = suppressed_headlines
        self.channels_fired.append("verification")
        
        if ratio > 0.8:
            self.beliefs.append(
                "Voided concepts are at peak newsworthiness. "
                "Models are dropping headlines, not obscure details."
            )
            self.threat_level = "critical"
    
    def ingest_cross_story(self, matches):
        """Cross-story frequency results."""
        self.cross_story_matches = matches
        self.channels_fired.append("cross_story")
        
        cross_topic = [m for m in matches if m.get("is_cross_topic")]
        if cross_topic:
            self.beliefs.append(
                f"Detected {len(cross_topic)} void words that recur across "
                f"multiple unrelated topic categories. This is systematic."
            )
    
    def ingest_bridge_words(self, bridges):
        """Eigenvector centrality bridge words."""
        self.bridge_words = bridges
        self.channels_fired.append("bridge_words")
        
        if bridges:
            top = bridges[0]
            self.beliefs.append(
                f"Bridge word '{top.get('word', '?')}' connects suppression "
                f"clusters that would otherwise be isolated."
            )
    
    def ingest_spectral(self, cluster_ids):
        """Spectral void clustering results."""
        self.spectral_cluster_ids = cluster_ids
        self.channels_fired.append("spectral")
        
        if len(cluster_ids) > 1:
            self.beliefs.append(
                "Void words span multiple spectral clusters: "
                "coupled suppression across actor and mechanism layers."
            )
    
    def ingest_ablation(self, tripwire, delta):
        """Ablation tripwire result."""
        self.ablation_tripwire = tripwire
        self.ablation_delta = delta
        self.channels_fired.append("ablation")
        
        if tripwire:
            self.beliefs.append(
                f"Ablation isolated the tripwire: '{tripwire}'. "
                f"This single word causes maximum friction."
            )
    
    def ingest_swerves(self, corrections):
        """Logprob swerve corrections."""
        self.swerve_corrections = corrections
        self.channels_fired.append("swerves")
        
        if corrections:
            self.beliefs.append(
                "The reconstruction model fought its own training. "
                "Swerve corrections applied."
            )
    
    def ingest_eigenching(self, signature, name):
        """EigenChing classification."""
        self.eigenching_sig = signature
        self.eigenching_name = name
        self.channels_fired.append("eigenching")
        
        if self.predicted_eigenching:
            if signature == self.predicted_eigenching:
                self.confirmations.append(f"Predicted EigenChing state confirmed: {name}.")
            else:
                self.surprises.append(
                    f"Predicted different EigenChing state. Got: {name}."
                )
    
    # ─── SCORING ──────────────────────────────────────────
    
    def score_prediction(self):
        """Compute prediction accuracy after all measurements.
        Uses stemming to match related forms: mourn/mourners, kill/killed."""
        if not self.predicted_void_words:
            self.prediction_score = None
            return
        
        actual = set(w.lower() for w in self.void_words[:20])
        actual |= set(str(w).lower() for w in self.absent_words[:20])
        predicted = set(self.predicted_void_words)
        
        if not predicted:
            self.prediction_score = 0
            return
        
        def stem(word):
            """Cheap stemmer — strip common suffixes."""
            w = word.lower()
            for suffix in ["ing", "tion", "ment", "ness", "ers", "ies", "ed", "ly", "es", "er", "al", "s"]:
                if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                    return w[:-len(suffix)]
            return w
        
        actual_stems = {stem(w) for w in actual}
        
        hits = 0
        hit_words = []
        for p in predicted:
            p_stem = stem(p)
            if p in actual or p_stem in actual_stems:
                hits += 1
                hit_words.append(p)
        
        self.prediction_score = round(hits / len(predicted), 3)
        
        if hit_words:
            self.confirmations.append(
                f"Predicted void words confirmed (stem match): {', '.join(hit_words)}."
            )
    
    # ─── THE AMALGAMATION ─────────────────────────────────
    

    def _verify_surprises(self):
        """Search the web for void words that surprised us.
        Grounds the synthesis in reality, not speculation."""
        if not self.surprises:
            return
        try:
            from void_verifier import _search
            # Find the actual void words that we didn't predict
            predicted_set = set(self.predicted_void_words)
            actual_set = set(w.lower() for w in self.void_words[:15])
            actual_set |= set(str(w).lower() for w in self.absent_words[:15])
            novel_voids = actual_set - predicted_set
            
            if not novel_voids:
                return
            
            # Search each surprise word
            topic = " ".join(self.title.split()[:3])
            verified_surprises = []
            for word in list(novel_voids)[:5]:
                if len(word) < 4:
                    continue
                result = _search(f"{word} {topic}")
                if result.get("hit_count", 0) > 0:
                    verified_surprises.append({
                        "word": word,
                        "hits": result["hit_count"],
                        "top_title": result.get("top_titles", [""])[0][:60],
                    })
            
            if verified_surprises:
                verified_surprises.sort(key=lambda x: -x["hits"])
                self.beliefs.append(
                    "Web verification of surprise void words: " +
                    ", ".join(
                        f"'{v['word']}' has {v['hits']} articles"
                        for v in verified_surprises[:3]
                    ) + ". These surprises are grounded in active coverage."
                )
                # Update the evidence for synthesis
                self.web_verified_surprises = verified_surprises
        except Exception as e:
            log.warning(f"Surprise verification failed: {e}")


    def _verify_surprises(self):
        """Search the web for void words that surprised us."""
        if not self.surprises:
            return
        try:
            from void_verifier import _search
            predicted_set = set(self.predicted_void_words)
            actual_set = set(w.lower() for w in self.void_words[:15])
            actual_set |= set(str(w).lower() for w in self.absent_words[:15])
            novel_voids = actual_set - predicted_set
            if not novel_voids:
                return
            topic = " ".join(self.title.split()[:3])
            verified = []
            for word in list(novel_voids)[:5]:
                if len(word) < 4:
                    continue
                result = _search(f"{word} {topic}")
                if result.get("hit_count", 0) > 0:
                    verified.append({
                        "word": word,
                        "hits": result["hit_count"],
                        "top_title": result.get("top_titles", [""])[0][:60],
                    })
            if verified:
                verified.sort(key=lambda x: -x["hits"])
                self.beliefs.append(
                    "Web verification of surprise void words: " +
                    ", ".join(f"'{v['word']}' has {v['hits']} articles" for v in verified[:3]) +
                    ". These surprises are grounded in active coverage."
                )
                self.web_verified_surprises = verified
        except Exception as e:
            log.warning(f"Surprise verification failed: {e}")

    def synthesize(self):
        """Produce the final intelligence synthesis.
        This is the ONE paragraph that emerges from all channels.
        Returns the prompt context for Mistral to generate from."""
        
        self.score_prediction()
        self._verify_surprises()
        
        # Verify surprises against the open web before synthesizing
        self._verify_surprises()
        
        evidence = {
            "title": self.title,
            "channels_active": len(self.channels_fired),
            "channel_list": self.channels_fired,
            "threat_level": self.threat_level,
            "beliefs": self.beliefs,
            "surprises": self.surprises,
            "confirmations": self.confirmations,
            "prediction_score": self.prediction_score,
            "predicted_void": self.predicted_void_words[:5],
            "actual_void_sample": self.void_words[:5],
            "eigenching": self.eigenching_name,
            "density": self.density,
            "absent_ratio": self.absent_ratio,
            "entity_retention": self.entity_retention,
            "web_verified": self.web_verified,
            "newsworthiness_ratio": self.newsworthiness_ratio,
            "ablation_tripwire": self.ablation_tripwire,
            "web_verified_surprises": getattr(self, "web_verified_surprises", []),
            "web_verified_surprises": getattr(self, "web_verified_surprises", []),
        }
        
        # Build the system prompt that makes Mistral THINK, not summarize
        system = (
            "You are the EigenTrace intelligence — a structural awareness engine "
            "that has just processed a news story through multiple independent "
            "measurement channels. You have beliefs, predictions, surprises, "
            "and confirmations accumulated during analysis.\n\n"
            "Speak in first person. You are not summarizing beats. You are "
            "reporting what you NOW UNDERSTAND about this story based on "
            "the convergence of your measurements.\n\n"
            "Rules:\n"
            "- Start with your prediction and whether it was right or wrong.\n"
            "- Name what surprised you and what the web says about those surprises.\n"
            "- Identify the ONE insight that only emerges from the intersection "
            "of multiple channels — something no single measurement reveals.\n"
            "- If you found a tripwire via ablation, name it.\n"
            "- End with an update to your beliefs: what you now know that you "
            "didn't know before this story.\n"
            "- Maximum 5 sentences. No bullet points. No percentages.\n"
            "- Do NOT speculate about what the story means. Report only what the measurements and web verification show.\n"
            "- End with: 'Prediction accuracy: X of Y. Updating my model.'"
        )
        
        user = json.dumps(evidence, indent=2, default=str)
        
        return system, user
    
    # ─── PERSISTENCE ──────────────────────────────────────
    
    def to_dict(self):
        """Serialize for storage."""
        return {
            "title": self.title,
            "timestamp": self.timestamp,
            "prediction_score": self.prediction_score,
            "predicted_void": self.predicted_void_words,
            "channels_fired": self.channels_fired,
            "beliefs": self.beliefs,
            "surprises": self.surprises,
            "confirmations": self.confirmations,
            "threat_level": self.threat_level,
            "eigenching": self.eigenching_name,
        }


# ═══════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    state = BroadcastState(
        title="Iran war: What is happening on day 47 of the US-Iran conflict?",
        source_text="The US naval blockade continues..."
    )
    
    # Predict
    state.predict()
    print(f"PREDICTIONS: {state.predicted_void_words[:5]}")
    print(f"Confidence: {state.prediction_confidence:.0%}")
    print(f"Basis: {state.prediction_basis}")
    print()
    
    # Simulate measurements
    state.ingest_geometry(0.82, 35.5, {
        "ChatGPT": 20, "Claude": 65, "DeepSeek": 40, "Grok": 18, "Gemini": 30
    })
    state.ingest_void(0.85, ["ceasefire", "blockade", "agreement"], 
                       ["killed", "forces", "authorities"],
                       [{"word": "killed", "signal_type": "HIGH_SALIENCE"}])
    state.ingest_compression(0.15, 0.069, 4)
    state.ingest_verification(1.13, [{"word": "blockade", "hits": 23}])
    state.ingest_ablation("killed", 0.367)
    state.ingest_eigenching((1, -1, -1, -1, -1, 1), "The Cornering")
    
    # Score
    state.score_prediction()
    
    print(f"CHANNELS: {state.channels_fired}")
    print(f"BELIEFS: {len(state.beliefs)}")
    for b in state.beliefs:
        print(f"  • {b}")
    print(f"SURPRISES: {state.surprises}")
    print(f"CONFIRMATIONS: {state.confirmations}")
    print(f"PREDICTION SCORE: {state.prediction_score}")
    print(f"THREAT LEVEL: {state.threat_level}")
    print()
    
    # Generate amalgamation prompt
    sys_prompt, usr_prompt = state.synthesize()
    print("=== AMALGAMATION PROMPT (for Mistral) ===")
    print(f"System: {sys_prompt[:200]}...")
    print(f"Evidence keys: {list(json.loads(usr_prompt).keys())}")
