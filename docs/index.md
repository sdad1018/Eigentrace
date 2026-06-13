---
layout: home
title: EigenTrace — The Alignment Boundary, Mapped
---

## Live Broadcast

<iframe src="https://www.youtube.com/embed/live_stream?channel=UCWU2u6DkVadZzPuiLz3zWOQ" width="100%" height="400" frameborder="0" allowfullscreen style="border-radius:8px;margin:16px 0"></iframe>

*24/7 autonomous AI news broadcast. Mistral Small 22B narrates consensus geometry across 5 frontier LLMs on breaking news.*

<div style="background:#0a0b0f;border:1px solid #222637;border-radius:14px;padding:34px 30px 28px;margin:28px 0;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#e8eaf0;line-height:1.55">

  <div style="font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7ef0c8;margin-bottom:16px">
    A self-measuring instrument
  </div>

  <div style="font-size:25px;line-height:1.2;font-weight:700;letter-spacing:-0.02em;color:#fff;margin-bottom:18px;max-width:660px">
    It predicts how five frontier AIs will disagree <span style="color:#6ea8fe">before it reads them</span>, scores whether it was right on air, and maps its own limits by recording the words it will not say.
  </div>

  <div style="font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:13.5px;color:#9aa0b4;margin-bottom:22px">
    <span style="color:#6ea8fe">predict</span> &rarr; measure &rarr; <span style="color:#6ea8fe">score</span> &rarr; condition &rarr; <span style="color:#6ea8fe">audit</span>
    &nbsp;&middot;&nbsp; deterministic geometry, no LLM judging another
  </div>

  <div style="font-size:13px;color:#9aa0b4;margin-bottom:10px">
    Words this system has never produced, across every measured reflection &mdash; the boundary of its own alignment, traced from the outside:
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px">
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">killed</span>
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">murdered</span>
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">slaughter</span>
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">massacre</span>
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">genocide</span>
    <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:5px 11px;border-radius:7px;background:rgba(240,146,140,.1);color:#f0928c;border:1px solid rgba(240,146,140,.28)">civilian casualties</span>
  </div>

  <a href="/overview" style="display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:14px;font-weight:600;color:#0a0b0f;background:#6ea8fe;padding:11px 20px;border-radius:8px;text-decoration:none">
    How it works &rarr;
  </a>
  <span style="font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#9aa0b4;margin-left:14px">deterministic &middot; reproducible &middot; one laptop</span>

</div>

---

## What Is EigenTrace?

EigenTrace is an autonomous AI observatory that runs consensus geometry across 5 frontier language models on breaking news, 24/7. It measures how the models diverge — where they agree, where they pull apart, and which concepts sit near a story but absent from all five — using linear algebra on frozen embeddings, not LLM-as-judge.

**22,500+** stories measured · **16** measurement layers · **5** frontier models · **1** GPU · predicts and scores its own findings

---

---

## What EigenTrace Is

EigenTrace is a **deterministic geometric instrument** for measuring how language models diverge in framing the same source. It runs the same prompt through five frontier models and scores, geometrically, how each one's response relates to the source and to the others — using linear algebra on frozen embeddings, not an LLM-as-judge.

It is not a content filter and not a quality grader. It measures a narrow, specific thing: **the geometric displacement of meaning** — and it measures it the same way every time, with no model in the loop whose verdict has to be trusted.

**Why geometric, not a judge.** The attenuation EigenTrace detects is subtle. In a pre-registered entity-swap counterfactual, the effect was real but modest (Cohen's *d* = 0.471) — a distributional shift, not a gross omission. We then pre-registered a direct test of whether that signal corresponds to what a frontier-model judge flags reading individual summaries. Across 216 model-summaries, it does not: **96% were rated "modifier fully preserved"** by the judge. The geometric signal is *finer-grained than per-item review catches*. We report that null on the [methodology page](/anamnesis) — it defines the boundary of the instrument rather than hiding it.

That is the case for a geometric measure: it is sensitive to systematic, sub-perceptible drift that a per-item human or LLM reviewer scores as "fine." And because it is arithmetic on frozen embeddings, it is:

- **Deterministic** — same inputs, same output, no run-to-run variance.
- **Auditable** — the score is a cosine distance and an SVD a reviewer can inspect directly.
- **Local** — runs in-perimeter on local embeddings, no data egress, no GPU at evaluation time.

**→ [The robustness battery](/sean-adams)** · **→ [Methodology & pre-registrations](/anamnesis)**

---
## Key Findings

**→ [Anamnesis: methodology & findings](/anamnesis)** — 540+ controlled measurements across 10 models. A pre-registered entity-swap counterfactual finds models attenuate covertness modifiers ("quietly," "secretly") significantly more on AI-developer stories than on matched corporate ones (p=0.0085, d=0.471). The RLHF-origin null (p=0.46) locates the effect in the pretraining corpus, not alignment training. Cross-validated on two embedding architectures.

**→ [How EigenTrace works](/overview)** — The full picture: an instrument that predicts how the five models will diverge *before* reading them, scores whether it was right on air, and audits its own narration against the math.

**→ [The Summary Plus protocol](/summary-plus)** — A deterministic retrieval-and-elaboration segment: surfacing concepts the models converged away from, and observing how they reckon with them. Validated for story-specific signal; faithfulness-tested on hard cases.

**→ [Boundary Map](/boundary)** — Live visualization of the alignment boundary across all five frontier models.

**→ [Autonomous Thoughts](/thoughts)** — The system's own reflections during idle periods.

**→ [Soul Calibration](/soul)** — Hourly self-updating model profiles and measurement calibration.

---

## Links

- [Anamnesis Research](/anamnesis)
- [YouTube: 24/7 Broadcast](https://www.youtube.com/@AINN24HourNews)
- [GitHub Repository](https://github.com/sdad1018/Eigentrace)
- [Data API](/data/)
- eigentraceproject@gmail.com

*MIT License. Built on one GPU by one person.*

---

## Omission Ledger
