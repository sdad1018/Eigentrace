# omniteardown — evidence-firewalled prospect enrichment

An autonomous agent that discovers e-commerce brands, probes their multi-channel
footprint and operational tech, drafts a personalized "Operational Flaw Teardown"
for OmniOrders, and **audits its own draft for hallucinations before publishing** —
then compiles a 4am briefing for the sales team.

**Core principle: code writes facts; models cite them.** Every observation enters
an append-only evidence ledger via deterministic probes. Claude composes probes
and interprets records — it cannot author evidence. A mechanical claim audit
(lexical trace + whole-ledger absence search + confidence-overreach detection)
plus an independent adversarial Claude check every draft. Overclaims are caught,
downgraded, and the diagnosis is rewritten under corrected confidence. Every
artifact ships with its audit stamp.

## Run it
```
pip install -e .                      # optional: gives you the `teardown` command
export ANTHROPIC_API_KEY=...          # or keep it in a .env the tool auto-loads

teardown --company "Liquid Death"     # any brand: Wikipedia-resolved, identity-gated
teardown --company "X" --domain x.com # force a domain
teardown --n 10                       # autonomous: Mistral (Ollama) proposes CPG/DTC
                                      # brands, Wikipedia/Wikidata verifies, engine
                                      # runs each, 4am briefing compiled
teardown --n 2 --dry-run              # full wiring test, zero API spend
```
(Flat-script invocation works identically: `python3 forager.py --n 10`.)
Outputs land in `runs/<brand>/<date>/`: ledger.jsonl, teardown.md, audit_report.md,
plus `runs/briefing-<date>-<time>.md` and the forage ledger. Cron line for the
literal 4am ritual is in forager.py's docstring. Cost: ~4 Claude calls/brand.

## Why trust it
Every gate in this system was earned by a documented failure. Seven defects and
one named limitation are logged in the module docstrings where they were caught:
false absence from an unverified page, query-echo false positives, a self-
contradicting ledger, a social profile masquerading as a commerce channel, a
rejection reason wearing a domain's clothes, and — the deep one — a skincare
brand resolving to a restaurant chain, proving that evidence-coherence is
necessary but not sufficient: identity is a separate axiom, with its own gate.
The reflection loop is not theoretical: on its first live run it caught the
drafter asserting three search-sourced channels as confirmed fact, downgraded
them, and rewrote the diagnosis. The audit stamp on every teardown is the receipt.

Built on the claim-audit discipline running in production at https://eigentrace.ai
(measured/argued split, pre-registration, public withdrawals ledger).
