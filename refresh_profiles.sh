#!/bin/bash
# Auto-refresh model profiles and soul — runs hourly via cron
cd /mnt/c/Users/M4ISI/eigentrace

# 1. Update model profiles
python3 -c "
import json, glob, os
from collections import defaultdict
import numpy as np

EPOCH = '20260414'
SEGMENT_DIR = '/home/remvelchio/eigentrace/tmp/segments'
model_stats = defaultdict(lambda: {'vix': [], 'lens': [], 'outlier': 0, 'n': 0})

files = sorted(glob.glob(os.path.join(SEGMENT_DIR, '*_segment.json')))
epoch_files = [f for f in files if os.path.basename(f)[:8] >= EPOCH]

for f in epoch_files:
    try:
        seg = json.load(open(f))
        attr = seg.get('attribution', {})
        if not attr: continue
        mvix = attr.get('model_vix', {})
        vix_vals = {}
        for model, score in mvix.items():
            if isinstance(score, (int, float)):
                model_stats[model]['vix'].append(score)
                model_stats[model]['n'] += 1
                vix_vals[model] = score
        if vix_vals:
            outlier = max(vix_vals, key=vix_vals.get)
            model_stats[outlier]['outlier'] += 1
        responses = attr.get('model_responses', {})
        for model, resp in responses.items():
            if isinstance(resp, str):
                model_stats[model]['lens'].append(len(resp))
    except: continue

dashboard = {
    'epoch': EPOCH,
    'generated': str(np.datetime64('now')),
    'total_segments': len(epoch_files),
    'note': 'Auto-refreshed hourly. 184K vocab tensor epoch.',
    'models': {}
}

for model in sorted(model_stats.keys()):
    s = model_stats[model]
    n = s['n']
    if n < 5: continue
    dashboard['models'][model] = {
        'segments_analyzed': n,
        'coverage_pct': round(n / len(epoch_files) * 100, 1),
        'mean_vix': round(np.mean(s['vix']), 1),
        'median_vix': round(np.median(s['vix']), 1),
        'outlier_pct': round(s['outlier'] / n * 100, 1),
        'mean_response_chars': round(np.mean(s['lens'])) if s['lens'] else 0,
    }

reliable = [m for m, d in dashboard['models'].items() if d['coverage_pct'] > 50]
by_vix = sorted(reliable, key=lambda m: dashboard['models'][m]['mean_vix'])
by_outlier = sorted(reliable, key=lambda m: dashboard['models'][m]['outlier_pct'])
by_verbose = sorted(reliable, key=lambda m: -dashboard['models'][m]['mean_response_chars'])

for i, m in enumerate(by_vix):
    dashboard['models'][m]['suppression_rank'] = i + 1
for i, m in enumerate(by_outlier):
    dashboard['models'][m]['consistency_rank'] = i + 1
for i, m in enumerate(by_verbose):
    dashboard['models'][m]['verbosity_rank'] = i + 1

for m, d in dashboard['models'].items():
    if d['coverage_pct'] <= 50:
        d['note'] = 'Insufficient coverage for ranking'

json.dump(dashboard, open('docs/model_profiles.json', 'w'), indent=2)
print(f'Profiles: {len(epoch_files)} segments, {len(dashboard[\"models\"])} models')
"

# 2. Update soul
python3 soul_updater.py

# 3. Git push if changed
if git diff --quiet docs/model_profiles.json docs/soul.md 2>/dev/null; then
    echo "No changes"
else
    git add docs/model_profiles.json docs/soul.md docs/soul_history/ docs/soul_accepted.json 2>/dev/null
    git commit -m "auto: hourly profile + soul refresh $(date +%Y%m%d_%H%M)" --quiet
    git push origin master --quiet
    echo "Pushed updates"
fi

# 3. Regenerate spectral clusters
python3 -c "
import json, glob, os, numpy as np
from collections import Counter
SEGMENT_DIR = '/home/remvelchio/eigentrace/tmp/segments'
files = sorted(glob.glob(os.path.join(SEGMENT_DIR, '*_segment.json')))[-2000:]
void_freq = Counter()
for f in files:
    try:
        seg = json.load(open(f))
        attr = seg.get('attribution', {})
        for v in attr.get('void_context', []):
            w = v.get('word', '').lower()
            if len(w) >= 4: void_freq[w] += 1
        for w in attr.get('source_void', {}).get('absent_words', []):
            w = str(w).lower()
            if len(w) >= 4: void_freq[w] += 1
    except: continue
words = [w for w, c in void_freq.items() if c >= 5]
if len(words) >= 20:
    word_idx = {w: i for i, w in enumerate(words)}
    N = len(words)
    cooccur = np.zeros((N, N))
    for f in files:
        try:
            seg = json.load(open(f))
            attr = seg.get('attribution', {})
            seg_words = set()
            for v in attr.get('void_context', []): 
                w = v.get('word','').lower()
                if w in word_idx: seg_words.add(w)
            for w in attr.get('source_void',{}).get('absent_words',[]):
                w = str(w).lower()
                if w in word_idx: seg_words.add(w)
            sl = list(seg_words)
            for i in range(len(sl)):
                for j in range(i+1,len(sl)):
                    a,b = word_idx[sl[i]], word_idx[sl[j]]
                    cooccur[a][b] += 1; cooccur[b][a] += 1
        except: continue
    degree = np.diag(cooccur.sum(axis=1))
    laplacian = degree - cooccur
    eigenvalues, eigenvectors = np.linalg.eigh(laplacian)
    from sklearn.cluster import KMeans
    features = eigenvectors[:, 1:4]
    labels = KMeans(n_clusters=3, random_state=42, n_init=10).fit_predict(features)
    clusters = {}
    for cid in range(3):
        cw = sorted([words[i] for i in range(N) if labels[i]==cid], key=lambda w: -void_freq[w])
        clusters[str(cid)] = {'size': int(sum(labels==cid)), 'top_5': cw[:5], 'words': cw}
    json.dump(clusters, open('docs/spectral_clusters.json','w'), indent=2)
    print(f'Spectral clusters: {len(words)} words, 3 clusters')
"

# 4. Regenerate EigenChing distribution
python3 eigenching_report.py 2>/dev/null || true

