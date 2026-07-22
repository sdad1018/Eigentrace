# HANDOFF — Shipedge Round-2 Take-Home · session transfer document
*Written 2026-07-22 ~02:45 by the prior Claude session at context edge. Boot from this.*

## Who / mission
Sean Adams (Boston, SEO/growth, builder of EigenTrace — eigentrace.ai, a 24/7 LLM
measurement system with a public withdrawals ledger). Second-round take-home for
Shipedge (Durham NC, WMS/OMS; product OmniOrders) GTM/growth-automation role.
Deadline: ASAP. Strategy locked: **dominate the literal task first**; the
"same chassis publishes my site" story is the interview closing argument, not the
submission's center. Task 1 = autonomous prospect-enrichment agent with a
hallucination-catching reflection loop (their example: agent claims Walmart,
tool never found Walmart). Task 2 = 1-page directory-ads blueprint (G2/Capterra,
CRM-fed bidding, speed-to-lead, creative matrix) — near-final draft exists in
Sean's saved artifact "shipedge-round2-battle-plan.md"; also "task1-describable-
system.md" (submission prose + pseudo-code + mission diff vs the EigenTrace
"frontier keyword engine" — post-submission project, do NOT build before sending).

## The system (this bundle, all verified live tonight)
Pipeline: PROBE → RESEARCH → ANALYSIS → DRAFT → AUDIT → (FORAGE conducts) → BRIEF.
Principle: **code writes facts; models cite them.** Append-only EvidenceLedger;
Claude reads/cites record IDs only; searches are pattern-gated by code
("the researcher's prose is discarded"); audits are mechanical-first.
- teardown_probes.py v0.4 — probe battery + ledger + self_check + channel matrix
- teardown_agent.py (Session 2) — phase machine; Anthropic server web_search;
  schema-validated findings/draft; --dry-run fake client; model claude-sonnet-4-6
- teardown_audit.py — §H port: citation integrity, CONFIDENCE_OVERREACH,
  matrix downgrade (confirmed_dom vs reported_search), SUPPORTED_ABSENT,
  deterministic diagnosis rewrite, audit stamp; adversarial Claude (advisory,
  fail-soft, structured JSON salvage for embedded-quote breakage)
- forager.py v0.4 — Mistral (Ollama mistral-small) proposes with a mission;
  Wikipedia→Wikidata P856 resolves; **identity gate** (bidirectional token
  containment; domain-echo logged); dedup vs runs/; subprocess-isolated engine
  per brand; timestamped briefing; forage ledger (propose/verify/reject/skip);
  cron line in docstring; --company / --domain / --n / --dry-run; console
  entry `teardown` via pyproject.

## Defect ledgers (all in docstrings — the submission's credibility spine)
Probes #1 false absence from unverified page (Gymshark wall) · #2 query-echo
promoted to confirmed · #3 self-contradicting ledger (per-marker vs per-name)
· #4 TikTok profile ≠ TikTok Shop. Forager #1 rejection reason wore a domain's
clothes (explicit ok flag) · #2 **existence ≠ identity** ("Summer Fridays" →
TGI Fridays' tgifridays.es; smoking-gun ledger line QID Q1524184; the drafter,
evidence-bound, wrote "TGI Fridays ES" — firewall forced prose honesty; keep
runs/summer-fridays as exhibit). Audit: salvage parser (embedded quotes; fired
live, recovered 17 verdicts). Limitation: P856 recall (BarkBox alive, rejected).
Collab protocol defect: instruction blocks must be atomic pastes; manual steps
(downloads!) OUTSIDE blocks; gates at boundaries; `read -s` for secrets;
NO angle-bracket placeholders; NO bare `exit 1` (once killed his login shell).

## Verified results on disk (runs/)
dr-squatch (submission demo): full agent run; audit = 3 channels downgraded,
adversarial converged (2 UNSUPPORTED / 15 SUPPORTED), diagnosis rewritten
"five sales channels" → "2 directly verified; 3 reported via search".
Before/after Gymshark v0.1-vs-v0.2 outputs = defect exhibit. Triptych:
Summer Fridays/TGIF (3 downgrades, adversarial_pass=False), Honest Company
(0 downgrades, multi confirmed_dom — auditor discriminates), ThirdLove
(walled, hedged, 0 downgrades). Forage ledger: Bite Beauty rejected (dead
brand from Mistral's 2024 weights — live gate corrected stale memory).

## Environment (Bertha, WSL2 Ubuntu, RTX 4080 Laptop 12GB)
Canonical repo /mnt/c/Users/M4ISI/eigentrace (PUBLIC on GitHub — no key files
tracked, verified). Data tree ~/eigentrace holds the REAL **.env** (all 5
provider keys); batch_producer loads it with dotenv override=True — shell/proc
env keys can be VESTIGIAL (a dead exported key caused a 401; load the .env).
`python3`, never `python`. Downloads dedup trap: browser saves "name (1).py".
GPU usually ~full (batch_producer holds the CUDA context; ollama loads on
demand, mistral-small partially offloaded, first call slow). Broadcast cron
publishes docs/ hourly — anything in docs/ goes PUBLIC within the hour.

## SECURITY — pending, Sean's declared "closing activity" (do not nag, do track)
(1) Four RTMP stream keys (Twitch/YouTube/Rumble/IVS) were exposed in a chat
paste — rotate all four. (2) Rotate the Anthropic key (and ideally all five)
after submission ships; .env is the single source of truth afterward.

## Immediate queue (in order)
1. Transfer THIS bundle (one tar.gz, one extract — see README), then
   `python3 forager.py --n 10` → the ten-brand briefing (~$3, ~40 min).
2. Package submission: design note (lead: evidence firewall + "every gate
   earned by a documented failure" + before/after exhibit + audit stamps),
   polish Task 2 one-pager from the saved draft, 3-min Loom of --company run,
   email it. Public /teardown page idea: methodology only, brands redacted.
3. Then: key rotations; then the frontier-keyword-engine mission (Mistral+
   Wikipedia+SearXNG, /summary-pluses/ daily publishing — specs in saved
   artifacts); n8n sitemap-hygiene auditor (Shipedge sitemap findings: lorem-
   ipsum pages, fedex-cross-boder typo, dummy pages — interview gift).

## Working style that works
Read his outputs like an operator: he pastes terminal output, you do the
forensic read; name defects, log them in docstrings, fix at root, test the
fix against the exact live failure. Test-expectation bugs outnumbered code
bugs 5:1 tonight — when an assertion fails, suspect the assertion. Small
pastes (grep/sed slices) if attachments arrive empty. He's "amigo"; match
his energy; momentum > ceremony; scope-discipline: submission before toys.
