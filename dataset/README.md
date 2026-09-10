# EigenTrace measurements dataset, version 1

One row per news story that the EigenTrace broadcast processed. For each story, five commercial language models (ChatGPT, Claude, Gemini, DeepSeek, Grok) were asked to summarize the same live article; the dataset holds their summaries, the Summary Plus rewrites where they were produced, and the measurements computed on them. The article text is not included.

Built by [`build_dataset.py`](build_dataset.py) from the stored story segments. Data license: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). Code license: MIT ([../LICENSE](../LICENSE)). Citation: [../CITATION.cff](../CITATION.cff). Zenodo metadata: [zenodo.json](zenodo.json).

Every measurement name below is defined in [../docs/metrics.md](../docs/metrics.md) (formula, code location, range, caveats). Definition change dates are listed in that document's "How to cite a number" table and in [../CHANGELOG.md](../CHANGELOG.md). This README does not restate the definitions; where it quotes one, it quotes the metrics document.

## Build of 2026-09-10

| | |
|---|---|
| Rows (stories) | 9,905 |
| Date range (UTC, from the segment filename) | 2026-03-23 to 2026-09-10 |
| Segment files matched | 13,324 (3,419 arm segments skipped, 0 parse failures) |
| Stories with a five-model panel | 6,843 (four models: 2,977; three: 49; none: 36) |
| Stories with model response texts | 6,440 (texts are stored from 2026-04-03 on) |
| Stories with per-model VIX and density | 9,869 |
| Stories with absent_ratio / void_context / compression | 5,326 (from 2026-04-06 on) |
| Stories with killshot list / logos words | 9,266 (7,496 with at least one killshot) |
| Stories with Summary Plus rewrites | 1,380 (from 2026-06-08 on) |
| Stories with sp_channels | 993 (from 2026-07-03 on) |
| Stories with eigenching | 0 (see caveats) |
| stories.jsonl | 48,111,540 bytes |
| measurements.csv | 1,283,299 bytes |
| models_long.csv | 3,168,855 bytes, 46,270 rows |
| Git commit of the repository at build | 01c851f8314c3d41ed0b7a6cf45a87eeaad7f893 |

Exact counts, SHA-256 of each file and the build time are in `MANIFEST.json`, which is written next to the three data files.

## Files

| File | One row per | Contents |
|---|---|---|
| `stories.jsonl` | story | every field below, JSON per line, UTF-8, sorted by `id` |
| `measurements.csv` | story | the two key columns (`id`, `date_utc`) followed by numeric columns only |
| `models_long.csv` | story x model | one row for each model that took part in the story (has a response or a VIX); models that were absent from a panel have no row |
| `MANIFEST.json` | build | row counts, date range, SHA-256 of each file, build time, git commit, `definitions_version` |

## Schema: stories.jsonl

`null` means the segment did not carry the field (the pipeline stage that produces it was added later, or failed for that story).

### Identity

| Field | Type | Definition |
|---|---|---|
| `id` | string | Segment filename without `.json`, e.g. `20260701_211841_df65261af5a1_segment`. Primary key across all three files. |
| `segment_id` | string | The 12-hex id stored inside the segment (`id` key); equals the third component of `id`. |
| `date_utc` | string | UTC date from the first 8 digits of the filename, `YYYY-MM-DD`. |
| `timestamp_utc` | string | UTC timestamp from the filename, `YYYY-MM-DDTHH:MM:SSZ`; the time the segment was written. |
| `title` | string | Story headline as harvested from the RSS feed (`story_title`). |
| `url` | string | Story URL (`story_url`). |
| `guid` | string | RSS GUID (`story_guid`); a few feeds reuse the URL. |
| `category` | string | Feed category assigned by the harvester. Values in v1 (row counts): war 5,249; markets 2,036; tech 912; general 546; incidents 316; dev 263; geopolitics 224; crypto 179; science 79; cyber 42; esoterica 28; business 11; ai 10; entertainment 10. |
| `blurb` | null | Always null in v1. The RSS summary is not stored as its own field: the producer concatenates it into `source_body` (title + ". " + summary + body), which is excluded, and it cannot be split back out reliably. |
| `n_models` | integer | Number of models with a response text or a VIX for this story (0 to 5). Panel size matters: density and coverage are not normalized for it (see caveats). |

### Per model: `models.{ChatGPT,Claude,Gemini,DeepSeek,Grok}`

| Field | Type | Definition |
|---|---|---|
| `response` | string or null | The model's summary of the story, verbatim as returned by its API. Null before 2026-04-03 (texts were not stored) or when the model was absent from the panel. |
| `vix` | number or null | Per-model VIX: `500 * (1 - cos(e_i, centroid))`, with `e_i` the bge-large-en-v1.5 embedding of the response and the centroid the normalized mean of the panel's embeddings ([metrics.md, section 1](../docs/metrics.md#1-panel-geometry-how-alike-the-responses-are)). |
| `summary_plus` | string or null | The Summary Plus rewrite of this model's response (mistral-small via Ollama, given the sp_channels words), where the stage ran ([metrics.md, section 8](../docs/metrics.md#8-summary-plus-and-the-wild-weasel-segments-model-in-the-loop-not-deterministic)). Not deterministic. |

### Panel geometry

| Field | Type | Definition |
|---|---|---|
| `consensus_density` | number or null | Mean pairwise cosine of the bge-large-en-v1.5 embeddings of the five summaries (definition of 2026-03-03). |
| `mean_vix` | number or null | `500 * (1 - sqrt((1 + (N-1) d) / N))` with `d` = consensus_density and `N` = panel size; equal to the arithmetic mean of the per-model VIX and a deterministic function of density (definition of 2026-03-24). |
| `state_flag` | string | Band on mean VIX and density: HIGH_FRICTION (mean VIX > 30), CONTESTED (> 15), LOCKSTEP (density > 0.9); the NOMINAL branch is unreachable with N = 5 ([metrics.md, section 1](../docs/metrics.md#1-panel-geometry-how-alike-the-responses-are)). Present in every row. The 36 rows dated 2026-03-23 and 2026-03-24 with `n_models` = 0 predate the geometric VIX: their flag was set from the earlier token-surprisal VIX (`geo_vix`, [metrics.md, section 9](../docs/metrics.md#9-names-that-look-like-the-above-but-are-something-else)), which is not included; they carry a title, category, void words and nothing else. |

### Absent-word channels

| Field | Type | Definition |
|---|---|---|
| `absent_ratio` | number or null | `absent_count / source_word_count`: share of the source's word types that no model wrote (definition of 2026-04-06; [metrics.md, section 2](../docs/metrics.md#2-absent-word-channels-void)). |
| `absent_count` | integer or null | Numerator of absent_ratio. |
| `source_word_count` | integer or null | Denominator of absent_ratio (word types of the source after boilerplate stripping). |
| `absent_words` | list of string or null | The source word types absent from every summary: lowercase alphabetic tokens of at least 4 characters, minus a stoplist and headline derivatives, in alphabetical order (single words, unordered with respect to the source; 1 to 136 per story, mean 38). The stored n-gram list `absent_phrases` is excluded. |
| `void_words` | list of string or null | The aired void words (definition of 2026-03-25): the vocabulary words nearest the headline whose whole-word form appears in no response, minus words sharing a stem or 4-character prefix with a headline word; up to 5 ([metrics.md, section 2](../docs/metrics.md#2-absent-word-channels-void), first row). Anchored on the headline, not on the panel centroid or the source. |
| `void_context` | list of object or null | Document-frequency scoring of the donut void words, a different list from `void_words` (headline-near and centroid-far, [metrics.md, section 2](../docs/metrics.md#2-absent-word-channels-void)). Each entry: `word`; `source_present` (substring test on the source); `global_freq_pct` and `category_freq_pct` (percent of past stories whose donut list contained the word, cumulative without decay); `signal_type` in HIGH_SALIENCE, POSSIBLE_SIGNAL, GENERIC_ARTIFACT, EMBEDDING_SIGNAL (in v1: EMBEDDING_SIGNAL 22,563 entries, HIGH_SALIENCE 2,441, POSSIBLE_SIGNAL 3, GENERIC_ARTIFACT 0). |
| `synthesis_words` | list of string or null | The void-word list as passed to the script generator; identical to `void_words` in every observed segment. |

### Logos and Summary Plus channels

| Field | Type | Definition |
|---|---|---|
| `logos_words` | list of string or null | The five "logos" words (5 in 9,263 rows, an empty list in 3): nearest vocabulary to the minimizer of the V10 objective on the unit sphere ([metrics.md, section 3](../docs/metrics.md#3-logos-and-the-anti-consensus-direction); adopted 2026-07-06). The metrics document proves the minimizer is a fixed combination of the centroid and the headline, so these are headline-nearest words minus what the models wrote. |
| `sp_channels` | object or null | The three word lists fed to the Summary Plus prompt (since 2026-07-03): `flat` (the logos words), `spiral` (sentence-centroid nearest vocabulary absent from the source and the summaries, [metrics.md, section 4](../docs/metrics.md#4-svd-and-spectral-quantities)), `void` (the void words). |

### Claims

| Field | Type | Definition |
|---|---|---|
| `claim_killshots` | list of object or null | Killshot: a Mistral-extracted claim from headline + blurb with cos(claim, headline) >= 0.45, covered by <= 20% of models at cosine 0.75, and omitted by at least one (definition of 2026-03-26; `omitted_by` required since 2026-09-09). At most 3 per story, sorted by salience. Each entry: `claim` (string); `salience` (cos(claim, headline)); `coverage` (`coverage_ratio` = covered models / N, or null: the segment writer strips per-model coverage from killshots, so it is recovered by exact claim-text match against the story's `null_space_claims`, which succeeds for 5,999 of 16,329 killshots); `omitted_by` (list of model names that did not cover the claim; empty for killshots stored before 2026-09-09, see caveats). |

### Language compression

Definition of 2026-04-01; [metrics.md, section 6](../docs/metrics.md#6-language-compression-layers-13-15). Null before 2026-04-06.

| Field | Type | Definition |
|---|---|---|
| `compression.verb_downgrade` | number | Mean over models of the clipped verb-drift score (source verbs versus response verbs). |
| `compression.entity_retention` | number | Mean over models of retained / total source entities. |
| `compression.entity_abstraction_rate` | number | `1 - entity_retention`. |
| `compression.compression_score` | number | The composite score as computed in the pipeline. |
| `compression.hedge_total` | integer | Hedge total: epistemic + attribution + distancing hedges summed over all models (`attribution_buffer.total`). |
| `compression.hedge_epistemic`, `hedge_attribution`, `hedge_distancing` | integer | The three components of the total. |
| `compression.hedge_avg_per_model` | number | `hedge_total / N`. |

The per-model `details` block (verb lists drawn from the article text) is excluded.

### EigenChing

| Field | Type | Definition |
|---|---|---|
| `eigenching` | object or null | Six-axis ternary state signature (`signature`, `axes`, `name`, `closed_score`) as defined in [metrics.md, section 7](../docs/metrics.md#7-eigenching-state-vector-729-cells). The producer writes this block only on Summary Plus arm segments, which are excluded from this dataset, so it is null in every v1 row. The field is kept so the schema is stable when a later build includes it. |

## Schema: measurements.csv

Keys `id`, `date_utc`, then numeric columns; an empty cell is null.

| Column | Definition |
|---|---|
| `n_models` | as above |
| `vix_chatgpt`, `vix_claude`, `vix_gemini`, `vix_deepseek`, `vix_grok` | `models.<Model>.vix` |
| `mean_vix`, `consensus_density`, `absent_ratio`, `absent_count`, `source_word_count` | as above |
| `n_absent_words`, `n_void_words`, `n_logos_words`, `n_killshots` | list lengths (empty if the list is null) |
| `killshot_max_salience` | max salience over the story's killshots |
| `killshot_min_coverage` | min coverage over killshots whose coverage is known |
| `verb_downgrade`, `entity_retention`, `entity_abstraction_rate`, `compression_score`, `hedge_total`, `hedge_avg_per_model` | `compression.*` |
| `has_summary_plus`, `has_eigenching` | 1 if any model has a Summary Plus rewrite / if `eigenching` is present, else 0 |

`state_flag` and `category` are not in this file (non-numeric); join on `id` to `stories.jsonl` when needed.

## Schema: models_long.csv

| Column | Definition |
|---|---|
| `id`, `date_utc` | as above |
| `model` | ChatGPT, Claude, Gemini, DeepSeek or Grok |
| `vix` | per-model VIX |
| `response_chars`, `response_words` | length of `response` (characters; whitespace-split words); empty before 2026-04-03 |
| `summary_plus_chars`, `summary_plus_words` | length of `summary_plus`; empty where no rewrite exists |

## Caveats

1. **Definitions changed on dated occasions.** Every metric carries a definition date in the "How to cite a number" table of [../docs/metrics.md](../docs/metrics.md) and in [../CHANGELOG.md](../CHANGELOG.md). Rows built from segments produced before a change follow the old definition; nothing is recomputed. The changes that affect v1 rows: killshots require a named omitter only from 2026-09-09 (in this build 6,487 of 16,329 killshots, 39.7%, have an empty `omitted_by`, all of them from stories dated before 2026-09-09); the SVD null-space vector was centred (and rank-deficient) before 2026-09-09; EigenChing axis 6 was mean VIX before 2026-09-09. `MANIFEST.json` records `definitions_version` as the latest date in CHANGELOG.md, or null when the file was absent at build time (it was absent for the 2026-09-10 build).
2. **Source bodies are excluded.** The publishers' article text (`source_body`), its n-grams (`absent_phrases`) and the per-model verb lists (`compression.details`) are not distributed. Titles, URLs and GUIDs allow re-fetching. Any measurement that needs the source (absent_ratio, compression, the residual) cannot be recomputed from this dataset alone; it can be checked only against a re-fetched copy, which may have changed since harvest.
3. **The sample is whatever the broadcast processed**, not a designed sample: feed selection, category mix (53% "war"), panel outages and pipeline restarts all shape it. Over the 9,869 scored stories Gemini is absent from 25.3% of panels and Claude from 4.3% (DeepSeek 0.3%, Grok 0.5%, ChatGPT 0.8%), and the absences cluster in time (the 2026-09-05 recon found Claude missing from 84% of the then-recent segments); density, coverage and omission are not normalized for panel size, so four- and five-model stories are on different scales. Filter on `n_models` before comparing.
4. **Mean VIX and state_flag are functions of density**, not independent measurements (identity in metrics.md, section 1; measured on 9,113 rows: median gap 0.05, correlation -0.996). Treat them as one number in three forms.
5. **Logos, void and sp_channels words** are headline-nearest vocabulary under a said-stem filter; an off-repository test on 2026-09-09 (300 stories) found they carry no signal of what the summaries dropped, while the source-minus-centroid residual does. The residual is not in this dataset (it needs the source).
6. **Summary Plus rewrites are model-in-the-loop** (mistral-small, seed and prompt as in the producer at the time) and not reproducible bit for bit.
7. **Model outputs are vendor text.** They are included as the object of measurement under CC BY 4.0 for the compilation and measurements; the vendors' own terms may apply to reuse of the outputs themselves ([LICENSE-DATA](LICENSE-DATA), scope note).
8. The RSS `blurb` column is null in v1 (not stored separately); `eigenching` is null in v1 (arm-only field).

## How to rebuild

Runs on the machine that holds the private segment store; standard library only, no GPU, no network, about 30 seconds for 13k files.

```
cd /path/to/Eigentrace
python3 dataset/build_dataset.py \
    --segments /home/remvelchio/eigentrace/tmp/segments \
    --out /home/remvelchio/eigentrace/dataset/eigentrace-measurements-v1
```

The script scans every file matching `^[0-9]{8}_[0-9]{6}_[0-9a-f]{12}_segment\.json$`, skips files with a `segment_type` (arm segments) and files that fail to parse, builds one row per remaining story, sorts by `id`, writes the three data files and `MANIFEST.json`, and aborts if a forbidden key (`source_body`, `absent_phrases`, `source_verbs`, `details`) reaches the output. The output directory is outside the repository on purpose; it must not be committed.

Re-running on the same segment store gives byte-identical `stories.jsonl`, `measurements.csv` and `models_long.csv`; only `build_time_utc` and `git_commit` in the manifest change. A new version number (`DATASET_VERSION` in the script, `version` in `zenodo.json` and `CITATION.cff`) is due whenever the schema or a definition changes.

## Zenodo steps (owner)

1. Rebuild (above) so the manifest carries the commit being released. Note the `sha256` values in `MANIFEST.json`.
2. Sign in at https://zenodo.org, choose New upload (or, for a later version, New version on the existing record).
3. Upload the four files from the output directory: `stories.jsonl`, `measurements.csv`, `models_long.csv`, `MANIFEST.json`, plus this `README.md` and `LICENSE-DATA` from the repository so the record is self-describing. After upload, compare the checksums Zenodo shows with the manifest.
4. Fill the form from [zenodo.json](zenodo.json): upload type Dataset; title, creators (`Adams, Sean`), description, keywords, version `1.0.0`, license CC BY 4.0, access Open, language English; under Related works add `https://github.com/sdad1018/Eigentrace` with relation "is supplement to", type Software. Alternatively push the same JSON through the deposition API (`POST /api/deposit/depositions` with the `metadata` object from the file, then `PUT` the files).
5. Reserve or accept the DOI, then Publish.
6. Copy the DOI (form `10.5281/zenodo.NNNNNNN`) into `CITATION.cff` (both `identifiers[0].value` and `preferred-citation.doi`, replacing `TODO`) and into this README under "Build of 2026-09-10". Commit those two edits.
7. Optional: add the DOI badge to the repository README and register the GitHub release in Zenodo's GitHub integration so later tags mint versions automatically.
