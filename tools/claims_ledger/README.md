# Claim ledger and gate

Installed 2026-09-17. **Advisory**: it reports, it does not block. The rule that turns it
into a blocking gate, and who turns it, are at the bottom of this file.

## The rule it enforces

> No public prose may assert a stronger status than the ledger records for that claim.

`claims_ledger.json` records, for every claim the site makes, what is actually known about
it: a status, the cheapest boring explanation that has not been ruled out, the evidence, the
wording that is allowed in public, and the wording that is not. `ledger_check.py` reads the
pages in `docs/`, finds each claim's registered sentence, classifies what the prose around
it asserts, and reports every place where the page claims more than the ledger allows.

It is a reporter, not an editor. It never changes a page.

## Status hierarchy

Strongest assertion first. A page may assert its claim's status or anything weaker;
asserting anything stronger is a violation.

| | status | means |
|---|---|---|
| 1 | `MEASURED` | a run exists, the number reproduces from disk |
| 2 | `DERIVED` | follows from a measured result without a new run |
| 3 | `ARGUED` | a reading of the evidence, not a measurement |
| 4 | `THEOLOGICAL` | asserted within a stated frame, not from data |
| 5 | `SYMBOLIC` | held as an image or a benchmark, not as a claim about the world |
| 6 | `SPECULATIVE` | proposed, untested, and labelled as such |
| 7 | `CONTRADICTED` | tested and the test went against it |
| 8 | `WITHDRAWN` | retracted; lives on `/withdrawals` only |
| 9 | `UNTESTED` | no run exists |

Two ranks are not statuses a claim can hold:

- `UNFENCED` is what the checker calls prose that asserts a claim with no measured, argued
  or withdrawn marker at all. It ranks with `ARGUED`, so a `CONTRADICTED` or `WITHDRAWN`
  claim still standing unmarked on a page is a violation.
- `ISOMORPHISM` is reserved for a proven bijection and is used by no claim in this ledger.

Corrections policy, unchanged by this gate: corrections and withdrawals live only on
`/withdrawals`. A page either states something true or the claim comes off it; correction
text never goes inline on the page that failed.

## Running it

From anywhere:

    python3 tools/claims_ledger/ledger_check.py --advisory

Defaults are derived from the script's own location: the ledger beside it, `docs/` at the
repository root. Useful flags:

| flag | effect |
|---|---|
| `--advisory` | report only, always exit 0 (what the hourly refresh uses) |
| `--blocking` | exit 2 if any violation is found |
| `--docs PATH` | scan a different tree, e.g. a staged copy before publishing |
| `--root PATH` | root that repo-relative `site_pages` resolve against (default: parent of `--docs`) |
| `--md-out FILE` / `--json-out FILE` | where the reports go |
| `--skip-regression` | skip `cktest/`; not for automated use |

With no output flag it writes nothing and prints the summary. **An output path inside this
repository is refused**: this repository is public and commits itself hourly, and a
violations report quotes every failing sentence.

`cktest/ck_regress.py` is the checker's own regression suite: five synthetic pages plus the
withdrawal-cue lexicon. It runs automatically before every scan and a failure aborts the
scan, because a checker that has stopped working would otherwise report zero violations
and look like success.

Exit codes: `0` clean or advisory, `1` the regression suite failed or the arguments were
bad, `2` violations found under `--blocking`.

## Where it runs

`refresh_profiles.sh` calls it once an hour, before the commit step, between the marker
comments `CLAIMS_LEDGER_GATE_V1`. That call is non-blocking by construction: it is wrapped
in a 60 s `timeout`, its exit code is ignored, and the refresh continues whatever happens.
The report is written outside this repository, to the private runtime tree at
`tmp/logs/claims_ledger_violations.md`, and the counts go to the refresh log.

## About this copy

The ledger of record lives in the private runtime tree, where the experiments run. This is
a generated copy, and two things were changed on the way in so that it is safe to publish:

1. **Paths.** No absolute path and no machine account name appears here. Paths into this
   repository are repo-relative (`docs/index.md`); evidence that exists only in the private
   runtime tree is recorded as the placeholder `runtime tree: <relative path>`, which names
   the file without pointing at a machine. 246 paths became repo-relative, 370 became
   placeholders, and four prose strings that quoted a path were reworded.
2. **Two charter claims are held back.** `CHI_001` and `CHI_002` are recorded in the runtime
   ledger only. Both are `UNTESTED`, both carry no `site_pages`, so neither is in this
   gate's scope and neither can change any count; they are held back because their text
   quotes charter vocabulary that no public page uses. Restoring them is an owner decision.
   This copy therefore carries 101 of the runtime ledger's 103 claims.

Two strings in this file use a word that site copy does not: one is a `must_not_say` rule
whose whole purpose is to keep that word off the site, and one is the name of a sealed
experiment (`PREREG_OVERTON_WORD`), which has to match the runtime ledger's identifier.
Neither is page copy, and neither can be reworded without breaking what it is for.

Everything else is byte-for-byte the ledger's own text, including each claim's
`allowed_public_wording` and `must_not_say`. When the runtime ledger changes, this copy is
regenerated from it; editing this copy by hand puts the two out of step.

## State at install, and the flip rule

First run against the live `docs/` tree, 2026-09-17: 151 files scanned, 118 anchors, **115
distinct sentences (162 claim-place pairs)** asserting more than the ledger records.

Two counts are reported and they are not the same thing. *Places* are distinct
`(page, line)` sentences — the number of edits the site needs. *Pairs* are
`(claim, place)` attributions, and one sentence can carry several claims. A gate whose
purpose is to stop status inflation must not inflate its own count, so the pair count is
never published as a count of places.

**The gate is advisory until a run reports zero violations.** While the count is above zero
it reports and nothing else; a gate that blocks on a backlog it cannot clear only teaches
people to pass `--skip-regression`.

**The flip:** after the first run that reports zero violations, the gate becomes blocking —
`--advisory` becomes `--blocking` in the `CLAIMS_LEDGER_GATE_V1` block of
`refresh_profiles.sh`, and from then on a violation fails the caller. **The owner flips it,
and only the owner.** Nothing in this directory flips itself, and no automated run may flip
it. Until then, the report is the whole product.
