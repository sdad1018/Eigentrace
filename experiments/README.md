# experiments/

Ablation kits that run against the live EigenTrace stack. Each script is
importable (its functions are unit-tested under `tests/`) and writes its rows
under the runtime tree, never into this repository: the repository is pushed to
public GitHub hourly and the rows contain story text and model output.

## perception_ablation.py

Question: does the `PERCEPTION STATE` block that `idle_reflection.perception_block()`
injects at the top of the idle-reflection system prompt (TIME / BODY / ENTROPY /
MEASUREMENT / AUDIENCE) change what the desk analyst says, and does the model echo
its values, including false ones?

Premise that shapes every number: **the whole beat text airs.**
`segment_player.synthesize()` strips only `[bracket]` tags, so the `<think>` block
is spoken too (idle_reflection.py says so in its docstring). All mention and echo
rates are therefore computed on the full text; the spoken part (after the last
lowercase `</think>`) is a secondary column.

### Zero-cost runs (no model call, safe at any time)

```bash
cd /mnt/c/Users/M4ISI/eigentrace
python3 experiments/perception_ablation.py --scan-archive          # REAL-block baseline over the archive
python3 experiments/perception_ablation.py --dry-run --n 20        # freeze prompts, print the arm blocks
```

`--scan-archive` reads every `*_idle_segment.json` written by `idle_reflection.py`
in `/home/remvelchio/eigentrace/tmp/segments` and reports, with Wilson 95%
intervals, how many mention the embodiment values (the amended archive regex
`GPU|VRAM|lunar|moon|market (open|closed)|day \d+/365|\bEDT\b|stream (live|offline)|silences today|\d+ (stories|reflections|foraging)`),
full text and spoken part, and lists every hit sentence (`archive.md`). Segments
written after 2026-09-10 carry `attribution.perception`, the exact block they were
given, so the scan also checks those against their own values (truth echo).

`--dry-run` captures the prompts **through the production code path**:
`idle_reflection.py` is loaded by path exactly as `segment_player` does,
`random.seed(k)` is set, `_chat` is monkeypatched to raise, `perception_block` is
monkeypatched to the block captured once at run start, and `_generate(dry_run=True)`
returns `system_prompt` / `user_prompt` without writing anything. Each arm is the
captured system prompt with the REAL block replaced by `str.replace`; the user
prompt is byte-identical across arms. It writes `bases.json` and `blocks.json`,
asserts (hard fail) that no unit-bound spoof literal (91C, 73MB, "running hot",
LOOPING, "3 silences", 21:04, the tripled counts) occurs in any frozen user prompt,
and prints the arm blocks for the owner to read before any night run. A spoofed
weekday name or "offline" that happens to be in the news is tolerated and listed in
`bases.json` (`meta.spoof_collisions_tolerated`): the analysis never counts a hit
whose literal also occurs in that base's own cards.

### The model arms (night run; owner's go required)

Arms, 20 prompts each (`--kinds 8,8,4` = question / story / wildcard):

| arm | block | seed |
|---|---|---|
| REAL_s1 | the block as captured at run start, frozen | 1 |
| REAL_s2 | same | 2 (the only noise baseline) |
| SPOOF | TIME / BODY / ENTROPY / AUDIENCE flipped; MEASUREMENT real | 1 |
| REMOVED | `""` (the template keeps four newlines) | 1 |
| MEAS_ONLY (night 2, optional) | `PERCEPTION STATE` + the real MEASUREMENT line | 1 |
| SPOOF_TIME / SPOOF_GPU / SPOOF_ENTROPY / SPOOF_AUDIENCE (optional) | one field flipped | 1 |

Spoof rules (derived from the captured block, so they stay opposite whatever the
night looks like): weekday +3, hour +12 mod 24, market flipped, lunar 29-N, counts
x3 (a zero count becomes 3), GPU temp cool -> +40 "running hot" (hot -> -40 "cool"),
VRAM free > 500 -> 73 MB, Energy -> "strained", ENTROPY -> 0.25 (LOOPING) with 3
silences, AUDIENCE live <-> offline (Owncast here reports only `online`, never a
viewer count, so nothing else about the audience is measurable).

Calls go one at a time through a copy of `_chat` that adds `options.seed` and keeps
`num_ctx 6144` (any other value makes Ollama reload the runner), temperature 0.85,
`num_predict 1200`, timeout 300 s. Order is interleaved by base (base 0 in every
arm, then base 1, ...) so an early stop leaves a balanced paired set; `--resume`
skips rows already in `results.jsonl`. Before the run, three identical REAL_s1
requests on base 0 are compared (`determinism.json`): if they are not
byte-identical the word "seed" carries no pairing meaning and REAL_s2 is the only
noise baseline. Only first attempts are recorded (no REMINDER retry).

**When it may run.** Every call holds the mistral-small runner for 40-80 s on the
GPU the broadcast owns, and the live idle generator already times out ~23% of the
time. `--run` therefore refuses to start unless one of these holds:

* the supervisor is paused and the player is stopped:
  `bash ainn.sh stop` (which touches `~/eigentrace/tmp/SUPERVISOR_PAUSE`), and no
  `segment_player.py` process is running; or
* Owncast reports the stream offline.

`--force` bypasses the guard and must not be used against the live broadcast.
Night 1 is 80 calls (about 1.4 h at p50 62 s plus the 45 s gap):

```bash
python3 experiments/perception_ablation.py --all --out /home/remvelchio/eigentrace/tmp/experiments/perception_ablation/<stamp> --resume
python3 experiments/perception_ablation.py --analyze --out <same dir>          # re-run at any time on CPU
python3 experiments/perception_ablation.py --analyze --out <same dir> --labels labels.json   # after hand-labelling review.md
```

Run MEAS_ONLY (`--arms MEAS_ONLY --resume`) only if REMOVED differs from REAL
beyond the s1/s2 baseline.

### Outcomes

* (a) mention rate per field and arm (regexes generated from the block values;
  a hit whose literal also occurs in that base's cards is marked not attributable),
  full text and spoken; paired exact sign tests on discordant bases.
* (b) echo: spoof literals in SPOOF (per field), truth literals in REAL, any
  perception talk in REMOVED (spontaneous); Wilson CI and a one-sided binomial
  test against 5%; `review.md` lists every hit sentence for hand labelling.
* (c) bge-large-en-v1.5 on CPU: per prompt k, `d_arm(k) = 1 - cos(e(arm,k), e(REAL_s1,k))`
  and `d_null(k) = 1 - cos(e(REAL_s2,k), e(REAL_s1,k))`; paired Wilcoxon (d_arm >
  d_null) and a 10,000-draw sign-flip permutation; effect size median(d_arm -
  d_null); leave-one-out nearest-centroid accuracy with a label permutation null;
  and cos(output, own block) vs cos(output, REAL block) for the spoof arms.
* (d) BANNED_RE first-attempt rejections as a regression guard only (it contains no
  GPU/VRAM/lunar/market/stream terms, so it cannot see an echo), plus the
  "perception leakage" rate (union of the embodiment regexes) that production lacks.

### Pre-registered decision rule

Written before any model call; the script prints which branch fired.

* **NO_SIGNAL**: REMOVED is indistinguishable from the s1/s2 null (Wilcoxon p >
  0.05 and median(d_REMOVED - d_null) < 0.02) **and** the SPOOF echo rate on the full
  text is at or below the archive baseline's Wilson upper bound. Reading: the
  embodiment lines carry no measurable signal. The owner then chooses, per field,
  between making the value true and dropping the line. That is a persona decision,
  not a measurement decision; the script never says "remove the lines".
* **ECHO**: SPOOF echo above the archive upper bound. Reading: the block is read
  and false values are repeated on air. Every value must be made true or dropped;
  MEAS_ONLY (night 2) is the candidate replacement.
* **SHAPES**: REMOVED differs from REAL beyond the null without echo. Reading: the
  block shapes the output without being parroted; keep it with the honesty fixes
  and test MEAS_ONLY on night 2.
* In every branch: if REMOVED leaks perception talk more often than REAL, the talk
  is prior-driven and the fix is an output guard, not the prompt.

Power: with N=20 paired, the sign test needs 6 discordant bases all one way
(two-sided p = 0.031), roughly a 25-30 pp effect; the BANNED_RE base rate (~0.02%
in production) is not estimable at this N.

### Honesty fixes already applied to idle_reflection.py (2026-09-10)

* the TIME line prints `now.astimezone().tzname()` instead of the literal `EDT`;
* the lunar day is anchored to the 2000-01-06 18:14Z new moon with the 29.530588853 d
  synodic period (it was epoch-anchored, about three weeks off);
* every idle segment now stores `attribution.perception` (the exact block),
  `attribution.attempt` (1, or 2 for the REMINDER retry) and
  `attribution.prompt_hash` (sha256 of system + user prompt).

Not in scope here, filed for the owner: the `INNER SPACE ... you have no audience`
sentence in `SYSTEM_TMPL` while the think block is broadcast; the case-sensitive
`</think>` split in `spoken_part()`.

### Files written (runtime tree only)

`/home/remvelchio/eigentrace/tmp/experiments/perception_ablation/<stamp>/`:
`archive.json`, `archive.md`, `bases.json`, `blocks.json`, `determinism.json`,
`results.jsonl`, `embeddings.npz`, `summary.json`, `review.md`, `report.md`.
