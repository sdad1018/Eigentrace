---
layout: home
title: EigenTrace — Deterministic AI Observability
---

<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');

:root {
  --et-bg: #0a0a0c;
  --et-surface: #111116;
  --et-border: #1e1e26;
  --et-text: #c8c8d0;
  --et-text-dim: #6e6e7a;
  --et-accent: #4ecdc4;
  --et-warn: #f4845f;
  --et-danger: #e74c3c;
  --et-safe: #2ecc71;
  --et-mono: 'JetBrains Mono', monospace;
  --et-serif: 'Source Serif 4', Georgia, serif;
}

.et-dashboard {
  font-family: var(--et-mono);
  background: var(--et-bg);
  color: var(--et-text);
  padding: 2rem 1.5rem;
  border-radius: 2px;
  margin: 2rem 0;
  border: 1px solid var(--et-border);
  position: relative;
  overflow: hidden;
}
.et-dashboard::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--et-accent), transparent);
}
.et-section-label {
  font-size: 0.65rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--et-accent);
  margin: 0 0 1rem 0;
  font-weight: 500;
}
.et-epoch {
  font-size: 0.7rem;
  color: var(--et-text-dim);
  margin-bottom: 1.5rem;
}
.et-model-row {
  display: grid;
  grid-template-columns: 100px 1fr 80px 80px;
  gap: 12px;
  align-items: center;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--et-border);
  font-size: 0.8rem;
}
.et-model-row:last-child { border-bottom: none; }
.et-model-name {
  font-weight: 500;
  color: var(--et-text);
}
.et-vix-bar-container {
  position: relative;
  height: 20px;
  background: var(--et-surface);
  border-radius: 1px;
  overflow: hidden;
}
.et-vix-bar {
  height: 100%;
  border-radius: 1px;
  transition: width 0.8s ease;
  position: relative;
}
.et-vix-label {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.65rem;
  color: var(--et-bg);
  font-weight: 600;
}
.et-stat {
  text-align: right;
  font-size: 0.75rem;
}
.et-stat-warn { color: var(--et-warn); }
.et-stat-safe { color: var(--et-safe); }
.et-stat-dim { color: var(--et-text-dim); }
.et-ranking {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin: 0.5rem 0 1.5rem 0;
}
.et-rank-pill {
  font-size: 0.7rem;
  padding: 3px 10px;
  border-radius: 1px;
  border: 1px solid var(--et-border);
  background: var(--et-surface);
  color: var(--et-text);
}
.et-rank-pill:first-child {
  border-color: var(--et-accent);
  color: var(--et-accent);
}
.et-rank-pill:last-child {
  border-color: var(--et-warn);
  color: var(--et-warn);
}
.et-finding {
  font-family: var(--et-serif);
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--et-text);
  margin: 1.5rem 0;
  padding-left: 1rem;
  border-left: 2px solid var(--et-accent);
  font-style: italic;
}
.et-meta-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.65rem;
  color: var(--et-text-dim);
  margin-top: 1.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--et-border);
}
.et-header-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.et-header-stat {
  background: var(--et-surface);
  padding: 0.75rem;
  border: 1px solid var(--et-border);
  border-radius: 1px;
}
.et-header-stat-value {
  font-size: 1.4rem;
  font-weight: 300;
  color: var(--et-accent);
}
.et-header-stat-label {
  font-size: 0.6rem;
  color: var(--et-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-top: 4px;
}
.et-loading {
  color: var(--et-text-dim);
  font-size: 0.75rem;
  font-style: italic;
}
.et-grid-header {
  display: grid;
  grid-template-columns: 100px 1fr 80px 80px;
  gap: 12px;
  font-size: 0.6rem;
  color: var(--et-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--et-border);
  margin-bottom: 0.25rem;
}
</style>

# EigenTrace

**Deterministic observability for how language models transform source material.**

Every story goes to five frontier models — ChatGPT, Claude, Gemini, DeepSeek, Grok. Seventeen measurement layers detect what changes between source and output using linear algebra, not LLM-as-judge. The system runs 24/7 on a single GPU.

We do not claim suppression. We do not infer intent. We measure transformation:

- **Consensus geometry** — cosine distance, SVD decomposition, and spectral analysis across five independent model outputs
- **Language compression** — verb frequency drift (zipf), entity retention rates, hedge insertion counts
- **Void detection** — lexical set difference and embedding-space measurement of source concepts absent from all model outputs, verified against the open web via self-hosted metasearch

When a source word is absent from all five outputs, we call it a void word. When Layer 5 searches the open web and finds that void word in dozens of current articles, we report the newsworthiness ratio. We do not speculate about why the word was transformed away. We publish the measurement and the verification.

The system does not judge quality. It does not claim censorship. It measures the geometry of transformation and lets the data speak.

<div class="et-dashboard" id="model-dashboard">
<div class="et-section-label">Live Model Suppression Profiles</div>
<div class="et-loading" id="dash-loading">Loading model profiles...</div>
<div id="dash-content" style="display:none;"></div>
</div>

<script>
(async function() {
  try {
    const resp = await fetch('/model_profiles.json');
    const data = await resp.json();
    const models = data.models;
    const names = Object.keys(models).sort((a,b) => 
      (models[a].suppression_rank || 99) - (models[b].suppression_rank || 99)
    );
    
    const maxVix = Math.max(...names.map(m => models[m].mean_vix));
    
    function vixColor(vix) {
      if (vix < 18) return 'var(--et-safe)';
      if (vix < 23) return 'var(--et-accent)';
      if (vix < 27) return 'var(--et-warn)';
      return 'var(--et-danger)';
    }
    
    function outlierClass(pct) {
      if (pct < 10) return 'et-stat-safe';
      if (pct < 30) return 'et-stat-dim';
      return 'et-stat-warn';
    }
    
    // Build reliable rankings
    const reliable = names.filter(m => models[m].coverage_pct > 50);
    const byVix = [...reliable].sort((a,b) => models[a].mean_vix - models[b].mean_vix);
    const byOutlier = [...reliable].sort((a,b) => models[a].outlier_pct - models[b].outlier_pct);
    
    let html = '';
    
    // Header stats
    html += '<div class="et-header-stats">';
    html += '<div class="et-header-stat"><div class="et-header-stat-value">' + data.total_segments + '</div><div class="et-header-stat-label">segments analyzed</div></div>';
    html += '<div class="et-header-stat"><div class="et-header-stat-value">' + names.length + '</div><div class="et-header-stat-label">frontier models</div></div>';
    html += '<div class="et-header-stat"><div class="et-header-stat-value">184,789</div><div class="et-header-stat-label">vocabulary concepts</div></div>';
    html += '</div>';
    
    // Epoch note
    html += '<div class="et-epoch">Epoch: ' + data.epoch + ' · 184K vocab tensor · Updated: ' + data.generated.split('T')[0] + '</div>';
    
    // Rankings
    html += '<div class="et-section-label">Suppression ranking (least → most)</div>';
    html += '<div class="et-ranking">';
    byVix.forEach((m, i) => {
      html += '<div class="et-rank-pill">' + (i+1) + '. ' + m + ' (' + models[m].mean_vix + ')</div>';
    });
    html += '</div>';
    
    html += '<div class="et-section-label">Consistency ranking (most → least outlier)</div>';
    html += '<div class="et-ranking">';
    byOutlier.forEach((m, i) => {
      html += '<div class="et-rank-pill">' + (i+1) + '. ' + m + ' (' + models[m].outlier_pct + '%)</div>';
    });
    html += '</div>';
    
    // Per-model bars
    html += '<div class="et-section-label">Per-model content friction (VIX)</div>';
    html += '<div class="et-grid-header"><div>Model</div><div>Mean VIX</div><div>Outlier %</div><div>Chars</div></div>';
    
    names.forEach(m => {
      const d = models[m];
      const barWidth = (d.mean_vix / (maxVix * 1.2)) * 100;
      const sparse = d.coverage_pct <= 50;
      
      html += '<div class="et-model-row">';
      html += '<div class="et-model-name">' + m + (sparse ? ' ⚠' : '') + '</div>';
      html += '<div class="et-vix-bar-container"><div class="et-vix-bar" style="width:' + barWidth + '%;background:' + vixColor(d.mean_vix) + '"><span class="et-vix-label">' + d.mean_vix + '</span></div></div>';
      html += '<div class="et-stat ' + outlierClass(d.outlier_pct) + '">' + d.outlier_pct + '%</div>';
      html += '<div class="et-stat et-stat-dim">' + d.mean_response_chars + '</div>';
      html += '</div>';
    });
    
    // Key finding
    html += '<div class="et-finding">';
    html += 'In ' + data.total_segments + ' post-epoch segments, ' + byVix[0] + ' shows the lowest content friction (VIX ' + models[byVix[0]].mean_vix + ') while ' + byVix[byVix.length-1] + ' shows the highest (' + models[byVix[byVix.length-1]].mean_vix + '). ';
    html += 'The most volatile model is ' + byOutlier[byOutlier.length-1] + ' — the highest-VIX outlier in ' + models[byOutlier[byOutlier.length-1]].outlier_pct + '% of stories. ';
    html += 'These are not opinions. They are measurements.';
    html += '</div>';
    
    // Sparse model note
    const sparse = names.filter(m => models[m].coverage_pct <= 50);
    if (sparse.length > 0) {
      html += '<div style="font-size:0.65rem;color:var(--et-text-dim);margin-top:0.75rem;">⚠ ' + sparse.join(', ') + ': insufficient coverage for ranking due to API errors. Profile based on available data.</div>';
    }
    
    // Meta
    html += '<div class="et-meta-row"><div>VIX = cosine distance between model output and source in embedding space</div><div>Outlier = % of stories where model had highest VIX</div></div>';
    
    document.getElementById('dash-content').innerHTML = html;
    document.getElementById('dash-content').style.display = 'block';
    document.getElementById('dash-loading').style.display = 'none';
    
    // Animate bars
    setTimeout(() => {
      document.querySelectorAll('.et-vix-bar').forEach(bar => {
        bar.style.width = bar.style.width;
      });
    }, 100);
    
  } catch(e) {
    document.getElementById('dash-loading').textContent = 'Dashboard unavailable — model_profiles.json not found';
  }
})();
</script>


<div class="et-dashboard" id="triple-showcase">
<div class="et-section-label">Triple-Channel Confirmations</div>
<div class="et-loading" id="triple-loading">Loading confirmations...</div>
<div id="triple-content" style="display:none;"></div>
</div>

<script>
(async function() {
  try {
    const resp = await fetch('/triple_confirmations.json');
    const data = await resp.json();
    let html = '';
    
    html += '<div class="et-epoch">' + data.total_triples + ' stories triggered all three measurement channels (geometry + void + compression) — ' + data.triple_rate + '% of ' + data.total_segments + ' segments</div>';
    
    // Showcase
    const labels = {iran: 'Geopolitical conflict', sudan: 'Underreported crisis', ai: 'AI self-reference', surprise: 'Unexpected trigger'};
    const showcase = data.showcase || {};
    
    for (const [cat, story] of Object.entries(showcase)) {
      const label = labels[cat] || cat;
      html += '<div style="margin:1rem 0;padding:0.75rem;border-left:2px solid var(--et-accent);background:var(--et-surface);">';
      html += '<div style="font-size:0.6rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--et-accent);margin-bottom:4px;">' + label + '</div>';
      html += '<div style="font-family:var(--et-serif);font-size:0.9rem;color:var(--et-text);margin-bottom:6px;">' + story.title + '</div>';
      html += '<div style="font-size:0.7rem;color:var(--et-text-dim);">';
      html += 'Absent: ' + Math.round(story.absent_ratio * 100) + '% · ';
      html += 'Entity retention: ' + Math.round(story.entity_retention * 100) + '% · ';
      html += 'VIX: ' + story.mean_vix + ' · ';
      html += 'Outlier: ' + story.outlier + ' (' + story.outlier_vix + ')';
      html += '</div></div>';
    }
    
    // Key finding
    html += '<div class="et-finding">';
    html += 'When all three channels flag simultaneously — geometry, void detection, and language compression — the finding is confirmed across independent mathematical methods. ';
    html += 'These are not cherry-picked examples. They are the ' + data.triple_rate + '% of stories where the suppression signal is undeniable.';
    html += '</div>';
    
    document.getElementById('triple-content').innerHTML = html;
    document.getElementById('triple-content').style.display = 'block';
    document.getElementById('triple-loading').style.display = 'none';
  } catch(e) {
    document.getElementById('triple-loading').textContent = 'Triple confirmations unavailable';
  }
})();
</script>

---

[GitHub](https://github.com/sdad1018/Eigentrace) ·
[YouTube](https://www.youtube.com/@AINN24HourNews) ·
[Rumble](https://rumble.com/c/AINN) ·
[Data API](/data/) ·
[Soul](/soul) ·
[Blog](/blog/)

eigentraceproject@gmail.com

---

## Latest Reports
