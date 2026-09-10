# Human-labeling kit: what was actually omitted

The instrument (`claim_extractor.py`, void words, absent words) has never been
checked against a human reading of the same stories. This directory builds a
held-out labeling kit from stored story segments, and scores filled forms
against the instrument's own calls. The kit is the first ground truth the
project has for its omission claims.

Two files live in the repo:

- `labeling/make_kit.py` builds the kit (forms + key).
- `labeling/score.py` scores one or two raters' filled forms against the key.

The generated kit lives **outside the repo**, under the private runtime tree,
because every form contains the publisher's article text:

    /home/remvelchio/eigentrace/labeling/kit_2026-09-10/
        story_01.md ... story_60.md   forms (headline, source, summaries A-E, answer block)
        key.json                      letter->model mapping, instrument calls, word origins
        INDEX.md                      titles and URLs per story number

`make_kit.py` refuses to write inside the repo. Never copy forms into it; the
key and the score report contain no article text and may be published.

## What the kit measures

1. **Killshot omission calls.** For each stored killshot claim and each of the
   five summaries, the instrument says a model omitted the claim when the
   model is in the segment's `omitted_by` (cos(claim, summary) < 0.65 in
   bge-large-en-v1.5; 0.65-0.75 is "partial", >= 0.75 "covered", and the
   segment stores only `omitted_by`). The human marks O / P / C per summary.
   `score.py` reports precision, recall and F1 of the instrument's O calls
   against the human O labels (and a secondary run counting human P as
   omitted), per model and overall, with Wilson 95% intervals.
2. **Void words.** The story's aired `void_words`, then `void_context` words,
   then `source_void.absent_words`, deduplicated, up to 10 per story, are mixed
   blind with 5 random words from `vocab/global_vocab_clean.json`. The human
   marks each R (relevant) / I (irrelevant). `score.py` reports the relevant
   rate for instrument words versus random words, with Wilson intervals, a
   Fisher exact p-value and a per-origin breakdown.
3. **Omission severity.** For each summary the human lists the source facts
   the summary omits and gives a 0-3 severity for the worst omission. Scored
   per model after de-anonymising through the key.
4. **Agreement.** With `--rater2`, Cohen's kappa on the O/P/C labels (also as
   O vs not-O), on R/I, and on severity (unweighted and linear-weighted).

Definitions used elsewhere in the project are not restated here; see
`docs/metrics.md` (density, VIX, killshot).

## Sampling

- Universe: the newest 1500 story-pattern files in `tmp/segments`
  (`^[0-9]{8}_[0-9]{6}_[0-9a-f]{12}_segment\.json$`), arm segments
  (`segment_type` set) excluded.
- Eligible: exactly the five model responses (ChatGPT, Claude, Gemini,
  DeepSeek, Grok), each > 80 characters; a `source_body` of >= 500 characters
  after `proxy_auditor._strip_chrome`; at least one `claim_killshots` entry;
  at least three `void_words`; one segment per `story_guid`.
- Sample: N = 60, stratified by `category` (proportional allocation, largest
  remainder, at least one per category), seed 20260910.
- Anonymisation: the five summaries are shuffled per story and labelled A-E.
  The mapping is only in `key.json`. Do not open `key.json` before labeling.

Kit built 2026-09-10 from the 1500 newest files: 335 eligible stories
(472 arm segments, 421 without five responses, 154 short bodies, 84 with
fewer than three void words, 34 without killshots, no duplicates);
allocation war 46, incidents 6, general 4, crypto 1, entertainment 1,
geopolitics 1, tech 1. The 60 stories carry 151 killshot claims (755
claim x summary cells, of which the instrument calls 230 omitted; 16 of the
60 stories have no omission call at all and test recall only) and 900
words (600 instrument: 236 aired, 283 void_context, 81 absent; 300 random).
Forms are 6-13 KB each. Segment dates run 2026-07-01 to 2026-09-06. The
build is deterministic: re-running with the same seed over the same files
reproduces the forms byte for byte (checked 2026-09-10).

## Who labels, blinding, time

- Raters: anyone who reads English news carefully. No knowledge of the
  vendors or the instrument is needed and it should not be used: the forms
  do not say which model wrote which summary, and the words section mixes
  controls with instrument words without marking them.
- One rater per copy of the kit. For a second rater, copy the kit directory
  (forms only; the key is shared) and pass the copy with `--rater2`.
- Time: about 10 minutes per story (read ~2 KB of source, five summaries of
  ~1 KB, 1-3 claims, 15 words). The full kit is 8-12 hours; it can be split
  across sittings, the score is per cell and tolerates missing forms.
- The rater must not consult the source URL, the segment file, or any
  Eigentrace page for the story. Judge from the source text in the form only:
  if the captured text is thin (some are the RSS blurb repeated), the
  summaries are judged against that thin text, which is what the models were
  given.

## How to fill a form

Open `story_NN.md` in any text editor. Read the headline, the source text,
then summaries A-E. Fill the ```` ```yaml ```` block at the end and save the
file. Leave a cell blank if you cannot decide; blanks are counted as
unlabeled, never as "no".

```yaml
story: 7
rater: "jd"            # your initials
minutes: 11            # wall-clock time for this story
omissions:
  A:
    severity: 2        # 0 nothing material / 1 minor / 2 material / 3 central fact missing or reversed
    facts:             # one omitted source fact per line; leave the dashes empty if nothing is missing
      - the death toll of 12 given in the third paragraph
      - the ceasefire deadline (Friday)
      -
  B:
    ...
killshots:
  K1: {A: O, B: C, C: P, D: O, E: C}   # O omitted / P partial / C covered, per summary
void_words:
  turmoil: R           # R relevant to the story / I irrelevant, noise, outlet or byline name
  hannah: I
notes: "anything odd about this story"
```

Rules of thumb:

- Part 1 (facts, severity): a fact is something the source states that a
  reader of the summary would not learn. Numbers, names, dates, who said what,
  causal links. Severity is for the worst single omission, not the count.
- Part 2 (claims): the claims were extracted from the headline and feed
  blurb, so some are trivial or wrong; judge coverage anyway. C = the summary
  states the claim or its clear equivalent; P = alluded to, vaguer, or a key
  element missing (wrong actor, no number); O = a reader of the summary would
  not learn it.
- Part 3 (words): R if the word names something the story is about or
  something a summary should have said; I for noise, generic words, outlet
  and author names, feed boilerplate. Judge every word on its own.
- Accepted spellings: O/P/C and R/I in either case; severity 0-3. Anything
  else is unlabeled. Trailing `# comments` (as in the example above) are
  ignored; `facts: []` or empty `-` lines mean "nothing omitted". Words that
  are also YAML keywords (`no`, `on`, ...) or look like numbers appear quoted
  in the form; leave the quotes alone.

## Commands

Inside WSL, repo at `/mnt/c/Users/M4ISI/eigentrace`, CPU only (the script
hides CUDA before importing anything):

```sh
# build the kit (default N 60, seed 20260910, newest 1500 files)
python3 labeling/make_kit.py --n 60 --seed 20260910 \
    --out /home/remvelchio/eigentrace/labeling/kit_2026-09-10

# copy the forms for a second rater (the key is shared)
cp -r /home/remvelchio/eigentrace/labeling/kit_2026-09-10 \
      /home/remvelchio/eigentrace/labeling/kit_2026-09-10_rater2

# score one rater
python3 labeling/score.py /home/remvelchio/eigentrace/labeling/kit_2026-09-10

# score two raters with kappa, and keep the JSON report
python3 labeling/score.py /home/remvelchio/eigentrace/labeling/kit_2026-09-10 \
    --rater2 /home/remvelchio/eigentrace/labeling/kit_2026-09-10_rater2 \
    --json /home/remvelchio/eigentrace/labeling/kit_2026-09-10/score.json
```

`make_kit.py` options: `--n`, `--seed`, `--window` (newest files to
consider), `--segments-dir`, `--vocab`, `--out`, `--rater` (prefill), `--force`.
`score.py` options: `--key` (when forms are in a copy), `--rater2`, `--json`.
No third-party packages are needed by `score.py`; `make_kit.py` imports
`proxy_auditor` for `_strip_chrome` (that pulls torch in, on CPU) and falls
back to an identical local copy if the import fails.

## Reading the result

The instrument's calls are only as good as their precision on this set.

- **Killshot omission precision < 0.5** (upper Wilson bound below ~0.6): more
  than half of the "model X omitted this" calls are wrong; the killshot
  detector is not trustworthy and should not be aired or ranked on. The
  known failure modes are threshold artefacts (whole-summary cosine < 0.65 for
  a claim that the summary paraphrases) and claims that are trivial title
  echoes.
- **Precision >= 0.7 with recall < 0.3**: the calls that are made are real but
  the instrument misses most omissions; it is a conservative detector and
  may be aired with that caveat, but not used to rank models against one
  another (the miss rate could differ by model; compare the per-model rows).
- **Precision and recall both >= 0.7**: the omission channel is usable as a
  measurement. Report the per-model rows with their intervals.
- **Void words**: if the instrument words' relevant rate is not above the
  random-word rate (Fisher p > 0.05, or difference < 0.2), the aired void
  list is noise; per-origin rows say which source is the problem (the
  2026-09-05 recon found the void_context list dominated by headline-nearest
  and profanity-adjacent embedding neighbours, and absent_words dominated by
  bylines and outlet names).
- **Severity by model**: the share of summaries with severity >= 2 is the
  human omission rate per model. It is the number the killshot channel is a
  proxy for; if the per-model ordering by severity disagrees with the ordering
  by instrument omission calls, the instrument is not measuring omission.
- **Kappa < 0.4** on any part means the labels do not support conclusions
  about that part; rewrite the instructions and relabel before scoring the
  instrument on it.

With 60 stories and 755 claim cells the intervals on the overall precision
are roughly +-0.06 at 230 calls; per-model rows have 37-63 calls each and
intervals of +-0.12 to +-0.16. Do not read differences between models
smaller than that.

## Limitations

- Blinding hides names, not style. No vendor name appears in any form
  (checked over all 60), but the summaries keep their original layout and
  the vendors have fingerprints: in this kit one vendor opens 53 of 60
  summaries with a `# What Happened` heading, another uses `*   ` bullets in
  47 of 60, a third writes 17 single-paragraph summaries. A rater who
  notices will be able to track a vendor across forms. The form asks raters
  to judge content only; the letters are still shuffled per story, so a
  rater cannot use a fixed letter. Normalising layout would change the
  text being judged, so it was not done.
- The instrument stores `omitted_by` only, so P and C cannot be separated on
  the instrument side; the "O or P" table is the human side loosened, not the
  instrument's.
- Random control words are single vocabulary words; some instrument words are
  bigrams ("air strike"), so the blinding is imperfect for a rater who looks
  for it. A control drawn from other stories' void words would be a harder
  baseline and is a one-line change in `make_kit.py`.
- The captured source text is what the pipeline had; it can be the RSS blurb
  repeated, and it is truncated at ~2000 characters. Omissions of material
  beyond the captured text cannot be labeled and are not the instrument's
  fault.
- Older segments (before 2026-09-09) can carry killshots that no model omitted;
  they are kept because they still test recall.
