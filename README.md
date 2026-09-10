# EigenTrace

Measuring what frontier language models do to the news.

Site: https://eigentrace.ai · Method: https://eigentrace.ai/overview · License: MIT

## What it is

EigenTrace is a measurement instrument. Around the clock it takes live news
stories, asks five frontier models (ChatGPT, Claude, DeepSeek, Gemini, Grok) to
summarize each one, and measures what every summary dropped, softened or kept.
The measurement is deterministic geometry on a frozen embedding model,
`BAAI/bge-large-en-v1.5`: a source and its summaries become points in 1,024
dimensions, and retention, divergence and omission are distances and
projections between them. No second language model judges the geometry, so
the same inputs give the same numbers on every run. A local Mistral model
(`mistral-small`, served by Ollama) is still part of the system: it extracts
atomic claims from sources, narrates the broadcast, and writes the Summary Plus
text. Those three outputs are model-generated and are not measurements.

The instrument is on air 24/7 from one consumer GPU. The results and the
method are on the site; this repository is the code that runs it.

## How it works

```
RSS feeds
   |
   v
batch_producer.py                       one batch = about 3 stories
   1. fetch + importance scoring                          (CPU)
   2. five model API calls                                (network)
   3. geometry on frozen bge-large-en-v1.5                (CPU)
      per-model VIX (cosine divergence), consensus density,
      void/logos words, SVD null-space claims, compression
   4. broadcast script: model responses as beats,
      local Mistral as host and director                  (GPU: Ollama)
   5. unload Ollama                                       (free VRAM)
   6. cover image, LCM Dreamshaper v7                     (GPU)
   7. write segment JSON            -> ~/eigentrace/tmp/segments/
   |
   v
segment_player.py    reads segments, one Piper voice per speaker
   -> audio on UDP:10000, tmp/current_frame.png, ticker text
   |
   v
stream/master.sh     ffmpeg: frame + UDP audio + ticker + bed music
   -> Owncast + Twitch + YouTube (single ffmpeg tee)
```

Each stage runs alone so the GPU is never shared. Between story batches the
producer also runs side probes on the most interesting story: a four-step
escalation probe (`wild_weasel`), a Summary Plus arm, a roundtable and a pundit
desk. Those segments carry a `segment_type`; story segments carry none.

## Layout

This repository holds the code. Runtime data lives outside it, in
`~/eigentrace` (`EIGENTRACE_RUNTIME` in `install.sh`):

| Path | Contents |
| --- | --- |
| `~/eigentrace/tmp/segments/` | segment JSON queue (tens of thousands of files; list with `head`) |
| `~/eigentrace/tmp/logs/` | producer, player, supervisor and job logs |
| `~/eigentrace/tmp/images/` | cover images referenced by segments |
| `~/eigentrace/models/piper/` | Piper voices (`lessac`, `kristin`, `amy`, `danny-low`) |
| `~/eigentrace/assets/` | bumper frame, bed music |
| `~/eigentrace/stream/` | `master.sh`, the ffmpeg compositor; host-specific and deliberately not in the repo |

In the repo: `batch_producer.py`, `segment_player.py`, `geometric_engine.py`,
`eigentrace/` (the `score()` package), `ainn.sh`, `ops/`, `tests/`, `docs/`
(the site, served from `eigentrace.ai`), and the experiment scripts behind the
site pages.

## Install

Target: Ubuntu 22.04 or WSL2, Python 3.10, one NVIDIA GPU, ffmpeg.

```
git clone https://github.com/sdad1018/Eigentrace && cd Eigentrace && bash install.sh
```

`install.sh` installs the pinned Python packages (`requirements.lock.txt`,
torch 2.5.1+cu121), NLTK data, Piper TTS and its four voices, Ollama with
`mistral-small`, and Owncast 0.2.4, then runs the same pre-flight `ainn.sh`
uses. Knobs: `EIGENTRACE_RUNTIME`, `OWNCAST_VERSION`, `OLLAMA_MODEL`, and
`SKIP_APT`, `SKIP_PIP`, `SKIP_OLLAMA`, `SKIP_OWNCAST`. It never touches the GPU.
`stream/master.sh` is not installed; copy it in by hand. Do not run it on a host
that is currently broadcasting.

## Run

```
bash ainn.sh               # start producer, player, compositor
bash ainn.sh stop          # stop everything
bash ainn.sh status        # health check
bash ainn.sh --no-images   # skip image generation
```

`ops/ainn_supervisor.sh` keeps the stack up without root, cron or systemd.
Every 60 s it starts `ainn.sh` if nothing is running, relinks
`tmp/current_frame.png` to the bumper if its target is gone, and restarts the
transmitter's ffmpeg when every remote output has been dead for five minutes.
Hourly it rotates logs; daily it runs `ops/backup_daily.sh`.

The sentinel `~/eigentrace/tmp/SUPERVISOR_PAUSE` pauses it: `bash ainn.sh
stop` and Ctrl-C create the file, and a plain `bash ainn.sh` removes it. While
the file exists the supervisor leaves the stack alone. `ops/ainn_boot.sh`
launches the supervisor at logon and hourly.

## Outputs

**Segment JSON** (`~/eigentrace/tmp/segments/<timestamp>_<id>_segment.json`).
Top-level keys of a story segment:

```
attribution  beats  id  image_path  timestamp
```

`beats` is the broadcast script: a list of `{phase, speaker, text}`.
`attribution` holds the measurements and everything they were computed from:

```
story_title  story_url  story_guid  source_body  category
model_responses      the five summaries, keyed by model
model_vix  mean_vix  per-model and mean cosine divergence
consensus_density  state_flag
void_words  logos_words  synthesis_words  void_context  void_vector
source_void          words and phrases of the source absent from all summaries
null_space_claims    claims with coverage_ratio, null_alignment, omitted_by, salience
claim_killshots
compression          compression_score, entity_retention, verb_downgrade, ...
summary_plus  sp_channels  ensemble  epistemic_anchor
```

**Daily exports** (`docs/data/YYYYMMDD.json`, written by `data_exporter.py`,
one file per day since 2026-03-31). Keys: `date`, `generated_at`, `source`,
`version`, `license`, `summary` (mean VIX, mean density, top void and logos
words), `stories` (the attribution fields above plus `beats`, `dual_confirmed`,
`triple_confirmed`) and `weasel_probes`. Served at
`https://eigentrace.ai/data/YYYYMMDD.json`.

## Metrics

Definitions of every number the pipeline writes, and how each is computed:
[docs/metrics.md](docs/metrics.md).

## Tests

```
python3 -m pytest tests -q
```

`tests/conftest.py` forces CPU before torch is imported and the suite needs no
network access, so it is safe to run next to a live broadcast (125 tests).

## Changelog

[CHANGELOG.md](CHANGELOG.md)

## Limitations

- Not peer reviewed. The site documents claims that were withdrawn after
  re-scoring; nothing here has been checked by anyone outside the project.
- Everything rests on one frozen embedding model. Reproducible is not the same
  as valid: if `bge-large-en-v1.5` misrepresents meaning, every number
  inherits that bias.
- The narrator is a local model. What it says on air about the measurements is
  model text, not the measurement; the same holds for claim extraction and
  Summary Plus.
- The daily samples are small (roughly ten stories a day) and the published
  per-day measurements carry no error bars yet.
- `segment_player.py`, `segment_rag.py` and `entropy_forager.py` hard-code the
  runtime path `/home/remvelchio/eigentrace`; `batch_producer.py` honours
  `SEGMENTS_DIR`, `IMAGES_DIR` and `TICKER_FILE`.

## License

MIT. See [LICENSE](LICENSE).

## Author

Sean Adams.
