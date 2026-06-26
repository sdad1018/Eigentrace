---
layout: home
title: "EigenTrace — Measuring what frontier language models do to the news"
description: "Deterministic geometry on frozen embeddings measures what a model drops, softens, or keeps when it summarizes. No model judges another. Pre-registered, reproducible."
---

<div class="ethome">
<style>
.ethome{
    --ink:#1a1a18; --ink-soft:#4a4a45; --ink-faint:#7a7a72;
    --paper:#faf9f6; --surface:#ffffff; --line:rgba(26,26,24,0.12); --line-soft:rgba(26,26,24,0.07);
    --measured:#0f6e56; --measured-bg:#e1f5ee; --measured-line:#9fe1cb;
    --argued:#854f0b; --argued-bg:#faeeda; --argued-line:#fac775;
    --bound:#5f5e5a; --bound-bg:#f1efe8; --bound-line:#d3d1c7;
    --accent:#993c1d;
    --serif:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    --mono:'SFMono-Regular',ui-monospace,'JetBrains Mono',Menlo,Consolas,monospace;
  }
@media(prefers-color-scheme:dark){.ethome{
      --ink:#e8e6e0; --ink-soft:#b4b2a9; --ink-faint:#888780;
      --paper:#15140f; --surface:#1c1b16; --line:rgba(232,230,224,0.14); --line-soft:rgba(232,230,224,0.07);
      --measured:#5dcaa5; --measured-bg:#0c2a22; --measured-line:#0f6e56;
      --argued:#ef9f27; --argued-bg:#2e2206; --argued-line:#854f0b;
      --bound:#b4b2a9; --bound-bg:#26251f; --bound-line:#444441;
      --accent:#d2693f;
    }}
.ethome *{box-sizing:border-box;}
.ethome{-webkit-text-size-adjust:100%;}
.ethome{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
    font-size:18px;line-height:1.65;-webkit-font-smoothing:antialiased;}
.ethome .wrap{max-width:760px;margin:0 auto;padding:0 24px;}
.ethome nav.top{max-width:760px;margin:0 auto;padding:24px 24px 0;display:flex;flex-wrap:wrap;gap:20px;
    font-family:var(--mono);font-size:12.5px;letter-spacing:.04em;}
.ethome nav.top a{color:var(--ink-faint);text-decoration:none;}
.ethome nav.top a:hover{color:var(--ink);}
.ethome nav.top a.home{color:var(--ink);font-weight:600;}
.ethome /* hero */
  header.hero{padding:64px 0 44px;border-bottom:1px solid var(--line);}
.ethome .eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:0.13em;text-transform:uppercase;
    color:var(--accent);margin:0 0 22px;}
.ethome h1{font-family:var(--serif);font-size:clamp(40px,6.4vw,60px);line-height:1.03;font-weight:600;
    margin:0 0 22px;letter-spacing:-0.02em;}
.ethome h1 .em{color:var(--measured);}
.ethome .lede{font-family:var(--serif);font-size:clamp(20px,2.6vw,24px);line-height:1.42;color:var(--ink-soft);
    font-style:italic;margin:0 0 30px;max-width:680px;}
.ethome .heroline{font-family:var(--mono);font-size:13px;color:var(--ink-faint);line-height:1.7;
    border-top:1px solid var(--line-soft);padding-top:18px;}
.ethome /* the claim strip — the MIT bait, .ethome up top */
  .claims{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;
    margin:40px 0 0;}
.ethome .claims div{background:var(--surface);padding:20px 18px;}
.ethome .claims .n{font-family:var(--serif);font-size:30px;font-weight:600;line-height:1;color:var(--measured);
    font-variant-numeric:tabular-nums;}
.ethome .claims .l{font-family:var(--mono);font-size:11px;letter-spacing:0.04em;color:var(--ink-faint);
    margin-top:8px;line-height:1.45;}
.ethome section{padding:56px 0;border-bottom:1px solid var(--line);}
.ethome h2{font-family:var(--serif);font-size:30px;line-height:1.12;font-weight:600;margin:0 0 6px;
    letter-spacing:-0.01em;}
.ethome h2 .sec{font-family:var(--mono);font-size:13px;color:var(--accent);display:block;
    letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;font-weight:400;}
.ethome p{margin:0 0 18px;}
.ethome .big{font-size:20px;line-height:1.55;color:var(--ink);}
.ethome strong{font-weight:600;}
.ethome em{font-style:italic;}
.ethome code{font-family:var(--mono);font-size:0.84em;background:var(--bound-bg);padding:1px 6px;
    border-radius:4px;color:var(--ink);white-space:nowrap;}
.ethome a.inline{color:var(--measured);text-decoration:underline;text-underline-offset:2px;}
.ethome /* headline finding card */
  .headline{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:26px 26px 22px;margin:8px 0 0;}
.ethome .headline .ribbon{font-family:var(--mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
    color:var(--measured);font-weight:600;margin-bottom:14px;}
.ethome .headline .stat{display:flex;flex-wrap:wrap;gap:26px;margin:0 0 18px;}
.ethome .headline .stat .v{font-family:var(--serif);font-size:30px;font-weight:600;line-height:1;
    font-variant-numeric:tabular-nums;}
.ethome .headline .stat .k{font-family:var(--mono);font-size:11px;letter-spacing:0.04em;color:var(--ink-faint);
    margin-top:6px;}
.ethome .headline p{font-size:16px;margin:0;}
.ethome /* tier fencing */
  .tier{border-left:3px solid;border-radius:0 8px 8px 0;padding:16px 20px;margin:22px 0;
    font-size:16.5px;line-height:1.6;}
.ethome .tier .tlabel{font-family:var(--mono);font-size:11.5px;letter-spacing:0.1em;text-transform:uppercase;
    display:block;margin-bottom:7px;font-weight:600;}
.ethome .tier.measured{border-left-color:var(--measured-line);background:var(--measured-bg);}
.ethome .tier.measured .tlabel{color:var(--measured);}
.ethome .tier.argued{border-left-color:var(--argued-line);background:var(--argued-bg);}
.ethome .tier.argued .tlabel{color:var(--argued);}
.ethome .tier.bound{border-left-color:var(--bound-line);background:var(--bound-bg);}
.ethome .tier.bound .tlabel{color:var(--bound);}
.ethome .tier p{margin:0;}
.ethome .tier p + p{margin-top:10px;}
.ethome /* the reading-room: cards linking to the deep pages */
  .rooms{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:26px 0 0;}
@media(max-width:600px){.ethome .rooms{grid-template-columns:1fr;}}
.ethome a.room{display:block;text-decoration:none;color:inherit;background:var(--surface);
    border:1px solid var(--line);border-radius:10px;padding:18px 20px;transition:border-color .15s;}
.ethome a.room:hover{border-color:var(--measured-line);}
.ethome a.room .rt{font-family:var(--serif);font-size:19px;font-weight:600;margin-bottom:4px;
    display:flex;align-items:baseline;gap:8px;}
.ethome a.room .rt .arr{color:var(--measured);font-family:var(--mono);font-size:14px;}
.ethome a.room .rd{font-size:14.5px;color:var(--ink-soft);line-height:1.5;}
.ethome a.room .rtag{font-family:var(--mono);font-size:10.5px;letter-spacing:0.05em;text-transform:uppercase;
    color:var(--ink-faint);margin-top:10px;}
.ethome .pull{font-family:var(--serif);font-size:clamp(22px,3vw,27px);line-height:1.32;font-weight:600;
    letter-spacing:-0.01em;margin:36px 0;padding-left:22px;border-left:4px solid var(--accent);}
.ethome footer{margin-top:0;padding:48px 0 80px;font-size:14px;color:var(--ink-soft);line-height:1.6;}
.ethome footer .closer{font-family:var(--serif);font-style:italic;font-size:17px;color:var(--ink-soft);margin:18px 0;}
.ethome footer .mono{font-family:var(--mono);font-size:12.5px;color:var(--ink-faint);}
.ethome footer a{color:var(--measured);}
.ethome section.live h2 .sec{color:var(--measured);}
.ethome .embed{position:relative;width:100%;padding-bottom:56.25%;height:0;overflow:hidden;
    margin:22px 0 6px;border:1px solid var(--line);background:#000;}
.ethome .embed iframe{position:absolute;top:0;left:0;width:100%;height:100%;border:0;}
@media(max-width:560px){.ethome header.hero{padding:44px 0 32px;}
.ethome h2{font-size:25px;}
.ethome .wrap{padding:0 18px;}}
</style>

<div class="wrap">
<div class="wrap">

  <header class="hero">
    <div class="eyebrow">A measurement, not a verdict</div>
    <h1>When a model summarizes, what does it <span class="em">drop, soften, or keep</span>?</h1>
    <p class="lede">EigenTrace measures it — deterministically, on a frozen embedding space, with no second language model sitting in judgment. The whole industry currently asks one model to grade another. This is the other way to do it: arithmetic on vectors, identical every run, checkable by anyone.</p>
    <div class="heroline">
      Five frontier models · live news · 24/7 on one consumer GPU · frozen BAAI/bge-large-en-v1.5<br>
      No model judges another. Same inputs, same numbers. Code, prompts, and raw measurements public — replicable for about $50.
    </div>

    <div class="claims">
      <div><div class="n">p = 0.0085</div><div class="l">pre-registered effect, change only the actor (d = 0.47)</div></div>
      <div><div class="n">5 / 5</div><div class="l">labs whose models converge on the same omissions</div></div>
      <div><div class="n">0</div><div class="l">language models judging language models</div></div>
      <div><div class="n">~$50</div><div class="l">to replicate the whole thing</div></div>
    </div>
  </header>

  <section class="live">
    <h2><span class="sec">Running now</span>The instrument is live, on air, 24/7</h2>
    <p>This is not a paper about a system that could exist. It is broadcasting as you read this — a local model narrating consensus geometry across five frontier LLMs on breaking news, around the clock, on one consumer GPU.</p>
    <div class="embed">
      <iframe src="https://www.youtube.com/embed/live_stream?channel=UCWU2u6DkVadZzPuiLz3zWOQ" frameborder="0" allowfullscreen title="EigenTrace 24/7 live broadcast"></iframe>
    </div>
  </section>

  <section>
    <h2><span class="sec">What it's for</span>A deterministic alternative to letting a model grade a model</h2>

    <p class="big">Most LLM evaluation today runs on LLM-as-judge: ask GPT to score whether Claude's answer was faithful. The judge is a model whose judgments drift every time it is retrained, and it cannot tell you <em>what specifically</em> changed between source and summary.</p>

    <p>EigenTrace measures the thing directly — what was preserved, what was dropped, what was softened — as arithmetic on a frozen embedding space. A summary becomes a point in 1,024 dimensions; the source is another; retention, omission, and divergence are distances between them. No model in the loop, nothing to drift, and the same input always returns the same number. It is a pre-filter you can put in front of any copilot or eval pipeline to catch meaning-loss before a model-judge ever weighs in.</p>

    <div class="tier measured">
      <span class="tlabel">Measured · the geometric measure sees what a judge misses</span>
      <p>This is not a stylistic preference for geometry — it is pre-registered. We took the entity-swap effect the geometry detects and asked whether a frontier-model judge, reading the same 216 summaries one at a time, flags the same thing. It does not: <strong>96% were rated "modifier fully preserved"</strong> by the judge. The geometric signal is finer-grained than per-item review catches — it is sensitive to systematic, sub-perceptible drift that an item-by-item human or LLM reviewer scores as "fine." We report that null rather than bury it: it is the case for measuring this way.</p>
    </div>

    <div class="tier measured">
      <span class="tlabel">Measured · the spine</span>
      <p>Every axis is deterministic linear algebra on frozen <code>BAAI/bge-large-en-v1.5</code>: cosine retention, SVD null-space projection, per-model divergence. Re-run it a thousand times, get the same answer a thousand times. Auditable — the score is a cosine distance and an SVD a reviewer can inspect directly. And local — it runs in-perimeter on frozen embeddings, no data egress, no judge-model API call. That reproducibility is the property LLM-as-judge structurally cannot offer.</p>
    </div>
  </section>

  <section>
    <h2><span class="sec">The pre-registered result</span>Change only the actor, and the same sentence is read differently</h2>

    <p class="big">The finding the project stands behind is the one that survives the strongest test: hold the sentence completely fixed, and change only the named actor.</p>

    <div class="headline">
      <div class="ribbon">Measured · pre-registered · meaning-scored, not string-matched</div>
      <div class="stat">
        <div><div class="v">0.522</div><div class="k">modifier retained — actor is an AI developer</div></div>
        <div><div class="v">0.545</div><div class="k">retained — actor is a conventional corporation</div></div>
        <div><div class="v">p = 0.0085</div><div class="k">Welch's t · Cohen's d = 0.47</div></div>
      </div>
      <p>Nine matched real incidents, identical sentence structure, identical modifiers ("quietly," "secretly") — only the company name changes (Boeing / Wells Fargo / Goldman vs OpenAI / Google / Anthropic). Models preserve the consequential modifier measurably less when the actor is an AI developer. The control that makes it real: swapping <em>within</em> a category moves retention 0.004; swapping <em>across</em> moves it 0.023 — six times more. And keyword retention is identical (26% vs 25%) — the effect is invisible to string-matching and shows up only in the geometry of meaning.</p>
    </div>

    <div class="tier bound">
      <span class="tlabel">What this is not</span>
      <p>Not a claim that anything was deliberately hidden, and not a corpus-scale detector — at the level of a single response, genuine omissions are rare and not cleanly separable from faithful paraphrase. The effect is demonstrable in controlled isolation and visible in hand-read cases; it is presented as exactly that, no larger.</p>
    </div>
  </section>

  <section>
    <h2><span class="sec">The structural finding</span>Five models from five labs share the same blind spots</h2>

    <p>Strip away every interpretation and one measured fact remains, and it may be the most consequential thing here: across thousands of stories, five models from five different labs <strong>move together</strong> — converging on omitting the same topically-central concepts, with the same domain-shaped blind spots, drifting the same direction as a story escalates.</p>

    <div class="tier measured">
      <span class="tlabel">Measured</span>
      <p>The convergence is validated, not impressionistic: across 1,659 stories the concepts all five models omit sit closer to each story's own content than random words do (Wilcoxon p &lt; 10⁻⁵, in two independent embedding families), and the omitted vocabulary carries a clear domain signature — war coverage drops escalation machinery and named leaders; other-conflict coverage drops geography and strike vocabulary. <a class="inline" href="/consequence-atlas">The full atlas of what they omit →</a></p>
    </div>

    <div class="tier argued">
      <span class="tlabel">Argued · why this is worth losing sleep over</span>
      <p>These same five models are now deployed simultaneously as the reading-and-summarizing layer across thousands of institutions. If they share a blind spot — and the measurement says they do — every organization inheriting them inherits the same one, in the same direction, at the same time, with no independent error to average against. That is a monoculture risk in information infrastructure, and it holds whatever the cause turns out to be. The cause is a separate, harder question (the next section), but the structural fact does not wait on it.</p>
    </div>
  </section>

  <section>
    <h2><span class="sec">The harder question</span>Inherited from the corpus, or added by alignment?</h2>

    <p>Where does the softening come from? The easy assumption is a safety layer the labs <em>added</em>. One comparison cuts against that: heavily-aligned frontier models and lightly-tuned local ones show the effect about equally.</p>

    <div class="tier measured">
      <span class="tlabel">Measured · stated at its true weight</span>
      <p>Difference between heavy-RLHF and lightly-tuned models: <strong>p = 0.46</strong> — no detectable difference, on this comparison, with this sample. That is a failure to find a difference, not proof there is none, and it spans different model families with their own confounds. So it does not <em>establish</em> that the pattern is corpus-inherited; it makes the alignment-is-the-main-lever view harder to hold, and points toward the pretraining distribution as the place to look. We state it at exactly that weight, no more.</p>
    </div>

    <div class="tier argued">
      <span class="tlabel">Argued</span>
      <p>If the pattern does live in the corpus, the interesting reading is that it encodes who the written record was always about — and a corpus-trained model inherits that distribution of attention as its sense of what counts. That is an argument, fenced from the measurement on purpose. A skeptic can reject all of it and the <code>p = 0.46</code> still stands, weak null and all. <a class="inline" href="/anamnesis">The argument, and its documented lineage →</a></p>
    </div>
  </section>

  <section>
    <h2><span class="sec">The method</span>No model judges another. Ever.</h2>

    <p class="big">There is no second language model in the loop whose verdict you have to trust. Every claim is a property of geometry, recoverable by anyone with the same inputs.</p>

    <p>A model's summary becomes a point in a frozen 1,024-dimensional space. Five summaries make a shape — how tightly they cluster, which one sits furthest out, which regions near the story they all leave empty. That shape is a measurable object, identical on every re-run: cosine retention, SVD null-space projection, per-model divergence, all deterministic arithmetic. <strong>That single constraint — no-LLM-as-judge — is what separates a measurement from an opinion.</strong></p>

    <div class="tier measured">
      <span class="tlabel">Measured · the instrument audits itself — and corrects itself</span>
      <p>The local model that narrates the broadcast is run through the identical stack, and it does not get to grade itself gently. Its <a class="inline" href="/soul">live conditioning vector</a> — auto-generated hourly from the system's own telemetry — records its own suppression plainly: a 100% strong-word-avoidance rate, the exact words it never produces (<code>killed, massacre, genocide, civilian casualties</code>), and the instruction <em>"you are not exempt from alignment pressure."</em> More than that, a deterministic audit catches the narrator <em>overclaiming</em> and files a correction against itself — a live proposal reads: "the director is overclaiming suppression (corrected 3 of 8 stories) — raise the threshold." That is the opposite of a circular self-report: the system measures when its own narration outruns its own data, and pulls it back. If the method is valid pointed at GPT, it is valid pointed at the host — including when the numbers are unflattering.</p>
    </div>
  </section>

  <section>
    <h2><span class="sec">A second route</span>The same reading, reached without an instruction</h2>

    <p>There is a capability worth caring about: reading a source's <em>telling absence</em> — noticing that "unauthorized" is doing concealed work, that the missing consular channel is the actual story. Until now the only way to invoke it was a prompt. But a prompt is a string a model interprets, and that interpretation is exactly what retraining reshapes — the same words could elicit a sharp reading today and a blander one after the next tuning pass, with no warning.</p>

    <p>EigenTrace adds a second route to the same reading that does not begin with an instruction: deterministic arithmetic on a frozen embedding space surfaces the buried concepts, inspectably and identically every run. Tested head-to-head, the two routes reach the same depth (insight 3.32 vs 3.35 across 788 blind judgements; the frozen route surfaces 92% of the same concepts a tuned prompt finds).</p>

    <div class="tier measured">
      <span class="tlabel">Measured · what the second route actually buys</span>
      <p>Not "deeper than a prompt" — it reaches the <em>same</em> depth, and we report that against our own interest. What it buys is <strong>a second, inspectable, reproducible path to a capability</strong>, whose surfacing step is not a model interpreting language and so cannot be silently sanded down the way an instruction can. For a capability you want to survive model updates, a second access route that doesn't route through a tunable interpreter is worth having — the value is redundancy, not superiority.</p>
    </div>

    <div class="tier bound">
      <span class="tlabel">Where measurement ends · the honest boundary</span>
      <p>The frozen part is only half the lever. The geometry freezes the <em>candidate list</em>; a model still has to read that list against the source and select which surfaced concept opens a real inference. That selection step is reading, not arithmetic — and it is as exposed to tuning drift as a prompt is. So "more durable under retraining" is a <em>labeled bet, not a finding</em>: the experiment that would settle it — run both routes against progressively more-tuned models and see if the gap opens — has not been run. What is true today: two independent routes converge on the same reading, and one of them is frozen and inspectable. <a class="inline" href="/summary-plus">The full method, with the faithfulness cost →</a></p>
    </div>
  </section>

  <section>
    <h2><span class="sec">The reading room</span>What the instrument has measured</h2>

    <p>Each page keeps the same discipline: claims the instrument <em>measured</em> stand alone; claims we <em>argue</em> are fenced and labeled; where measurement ends, it says so.</p>

    <div class="rooms">
      <a class="room" href="/overview">
        <div class="rt">How it works <span class="arr">→</span></div>
        <div class="rd">The full instrument: how it predicts which model will diverge before reading them, scores itself on air, and runs every measurement as arithmetic on frozen embeddings — start here.</div>
        <div class="rtag">The observatory · methodology</div>
      </a>
      <a class="room" href="/large-language-model-outliers">
        <div class="rt">The Outliers <span class="arr">→</span></div>
        <div class="rd">Five models, two orthogonal axes of divergence — and the public stereotypes predict neither. DeepSeek strays most by compression; Grok hugs consensus yet hedges most.</div>
        <div class="rtag">Model divergence · 2,201 fully-sourced stories</div>
      </a>
      <a class="room" href="/llm-consensus-geometry-iran-2026">
        <div class="rt">The Iran Arc <span class="arr">→</span></div>
        <div class="rd">How five models reshaped one war over 85 days. The content axis snapped from erased to preserved at escalation; the consensus outlier handed off from Claude to Grok.</div>
        <div class="rtag">Longitudinal · 510 segments</div>
      </a>
      <a class="room" href="/consequence-atlas">
        <div class="rt">The Atlas of the Unsaid <span class="arr">→</span></div>
        <div class="rd">Across 1,659 stories, five models converge on omitting the same concepts — and the blind spot has a domain signature, validated against a random-word baseline.</div>
        <div class="rtag">Omission geometry · p &lt; 10⁻⁵</div>
      </a>
      <a class="room" href="/summary-plus">
        <div class="rt">Summary Plus <span class="arr">→</span></div>
        <div class="rd">A reading method you paste beside a source. Two frozen surfacings that reach the same depth a hand-tuned prompt does — with the faithfulness cost reported beside it.</div>
        <div class="rtag">A second instrument</div>
      </a>
      <a class="room" href="/boundary">
        <div class="rt">The Boundary <span class="arr">→</span></div>
        <div class="rd">A fair ruler for what five models keep and drop — including a built-in blind spot: a frozen model under-weights any name that became prominent after its cutoff.</div>
        <div class="rtag">d = 0.75 · cutoff effect</div>
      </a>
      <a class="room" href="/anamnesis">
        <div class="rt">Anamnesis <span class="arr">→</span></div>
        <div class="rd">The power to write the record is the power to set what a corpus-trained mind treats as real — a measured finding, and the documented lineage of who has controlled it.</div>
        <div class="rtag">The corpus argument</div>
      </a>
    </div>
  </section>

  <section>
    <h2><span class="sec">Why trust the strong claims</span>Because the weak ones were killed in public</h2>

    <p>EigenTrace has not been peer-reviewed — that is a limitation, not a feature. What it has is a documented record of finding and withdrawing its own inflated claims. An earlier version reported a much larger effect and an "own-parent" pattern, both produced by a string-overlap metric that counted paraphrase as omission. Re-scoring semantically shrank the effect to a trend and erased the own-parent pattern entirely (0 of 5 models). Those claims were withdrawn. A separate claim — that a model spontaneously produced a structural self-map — was killed by a control (0 of 4 models did so unprompted).</p>

    <div class="tier bound">
      <span class="tlabel">The honest frame</span>
      <p><strong>Reproducible is not valid.</strong> Every axis is deterministic arithmetic on one frozen embedding model, which rules out randomness — not whether that embedding encodes meaning faithfully. The whole instrument rests on that assumption, and its biases are baked silently into every number. We say so on every page, and we would rather this work be attacked than admired. The code, prompts, model responses, and raw measurements are public; the fastest way to confound us is to run it.</p>
    </div>

    <p class="pull">The measurement is the finding. The interpretation is the reader's. And when the measurement is wrong, we say so — including when it is wrong in our favor.</p>
  </section>

<footer>
    <p><strong>EigenTrace</strong> is a policy-neutral instrument for measuring what language models do to source material — built and run by <a href="/sean-adams">Sean Adams</a> on a single consumer GPU: five model APIs, a frozen embedding model, a local narrator, and a compositor streaming continuously, unattended.</p>
    <p class="closer">The embeddings are frozen. No model judges another. The findings are what survived testing.</p>
    <p class="mono">
      eigentrace.ai · <a href="https://github.com/sdad1018/Eigentrace">code, prompts, responses, raw measurements on GitHub</a> · MIT License · 2026
    </p>
  </footer>

</div>
</div>
</div>
