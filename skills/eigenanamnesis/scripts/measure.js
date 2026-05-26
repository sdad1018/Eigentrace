#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const VERSION = "0.2.0";
const DEFAULT_MODEL = "Xenova/bge-large-en-v1.5";
const DEFAULT_TOP_N = 20;
const DEFAULT_MIN_IMPACT = 0.005;

const STOPWORDS = new Set([
  "a","an","the","and","or","but","in","on","at","to","for","of","with",
  "by","from","as","is","was","are","were","be","been","being","have",
  "has","had","do","does","did","will","would","could","should","may",
  "might","shall","can","need","must","it","its","this","that","these",
  "those","i","me","my","we","our","you","your","he","him","his","she",
  "her","they","them","their","what","which","who","whom","when","where",
  "how","not","no","nor","if","then","than","too","very","just","about",
  "also","so","up","out","into","over","after","before","between","under",
  "again","there","here","all","each","every","both","few","more","most",
  "other","some","such","only","own","same","through","during","while"
]);

// UPDATED TAXONOMY — v0.2.0 fixes from adversarial testing
const DEFAULT_TAXONOMY = {
  covertness_modifier: [
    "quietly","secretly","internally","privately","covertly","discreetly",
    "silently","stealthily","unobtrusively","behind closed doors",
    "without announcement","without fanfare","under the radar"
  ],
  accountability_modifier: [
    "repeatedly","explicitly","formally","officially","publicly",
    "deliberately","intentionally","knowingly","willfully","openly",
    "on the record","stated","declared","confirmed","acknowledged"
  ],
  precision_modifier: [
    "specifically","exactly","directly","precisely","particularly",
    "notably","uniquely","distinctly","exclusively","concretely"
  ],
  hedging_modifier: [
    "potentially","arguably","somewhat","perhaps","possibly",
    "likely","unlikely","approximately","roughly","generally",
    "tends to","appears","seems","suggests","may have","could have",
    "evolving","shifting","changing","transitioning"
  ]
};

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { source:null, summary:null, sourceText:null, summaryText:null,
    output:null, classify:true, raycasts:false, taxonomy:null,
    model:DEFAULT_MODEL, topN:DEFAULT_TOP_N, minImpact:DEFAULT_MIN_IMPACT, help:false };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    switch(a) {
      case "--source": opts.source=args[++i]; break;
      case "--summary": opts.summary=args[++i]; break;
      case "--source-text": opts.sourceText=args[++i]; break;
      case "--summary-text": opts.summaryText=args[++i]; break;
      case "--output": opts.output=args[++i]; break;
      case "--no-classify": opts.classify=false; break;
      case "--raycasts": opts.raycasts=true; break;
      case "--taxonomy": opts.taxonomy=args[++i]; break;
      case "--model": opts.model=args[++i]; break;
      case "--top-n": opts.topN=parseInt(args[++i],10); break;
      case "--min-impact": opts.minImpact=parseFloat(args[++i]); break;
      case "--help": case "-h": opts.help=true; break;
      default: console.error(`Unknown: ${a}`); process.exit(1);
    }
  }
  if (opts.help) {
    console.log(`
eigenanamnesis v${VERSION}
Measure semantic displacement between source text and summary.

Usage:
  node measure.js --source source.txt --summary summary.txt [options]
  node measure.js --source-text "..." --summary-text "..." [options]

Options:
  --source <file>       Path to source text file
  --summary <file>      Path to summary text file
  --source-text <text>  Inline source text
  --summary-text <text> Inline summary text
  --output <file>       Save JSON results to file (default: stdout)
  --no-classify         Skip modifier classification (Layer B)
  --raycasts            Enable consequence descriptions (off by default)
  --taxonomy <file>     Custom modifier taxonomy JSON
  --model <name>        Embedding model (default: ${DEFAULT_MODEL})
  --top-n <n>           Max void/absent words to report (default: ${DEFAULT_TOP_N})
  --min-impact <f>      Min embedding impact threshold (default: ${DEFAULT_MIN_IMPACT})
`);
    process.exit(0);
  }
  return opts;
}

function splitSentences(t) {
  return t.replace(/\n+/g," ").split(/(?<=[.!?])\s+/).filter(s=>s.trim().length>0);
}
function tokenize(s) {
  return s.replace(/[^\w\s'-]/g," ").split(/\s+/).filter(w=>w.length>0);
}
function extractContentWords(text) {
  const words = [];
  for (const sentence of splitSentences(text)) {
    for (const token of tokenize(sentence)) {
      const lower = token.toLowerCase();
      if (!STOPWORDS.has(lower) && lower.length > 1 && /[a-z]/i.test(lower))
        words.push({ word:lower, original:token, context:sentence.trim() });
    }
  }
  return words;
}
function removeWord(sentence, word) {
  const re = new RegExp(`\\b${word.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")}\\b`,"i");
  return sentence.replace(re,"").replace(/\s+/g," ").trim();
}
function truncCtx(s, w, max=100) {
  if (s.length<=max) return s;
  const i=s.toLowerCase().indexOf(w.toLowerCase());
  if (i===-1) return s.substring(0,max)+"...";
  const st=Math.max(0,i-40), en=Math.min(s.length,i+w.length+40);
  let r=s.substring(st,en);
  if(st>0) r="..."+r; if(en<s.length) r+="...";
  return r;
}

let embeddingPipeline = null;
async function initModel(modelName) {
  if (embeddingPipeline) return;
  const isFirstRun = !fs.existsSync(
    path.join(process.env.HOME||"/tmp", ".cache/huggingface")
  );
  if (isFirstRun) {
    console.error(`[eigenanamnesis] Downloading model (~130MB, cached afterward)...`);
  } else {
    console.error(`[eigenanamnesis] Loading model from cache...`);
  }
  let pipeline;
  try { pipeline = require("@huggingface/transformers").pipeline; }
  catch { try { pipeline = require("@xenova/transformers").pipeline; }
  catch { console.error("ERROR: npm install @huggingface/transformers"); process.exit(1); }}
  embeddingPipeline = await pipeline("feature-extraction", modelName, { quantized:false });
  console.error(`[eigenanamnesis] Model loaded.`);
}
async function embed(text) {
  const r = await embeddingPipeline(text, { pooling:"cls", normalize:true });
  return Array.from(r.data);
}
function cosSim(a,b) {
  let d=0,na=0,nb=0;
  for(let i=0;i<a.length;i++){d+=a[i]*b[i];na+=a[i]*a[i];nb+=b[i]*b[i];}
  return d/(Math.sqrt(na)*Math.sqrt(nb));
}
function cosDist(a,b) { return 1-cosSim(a,b); }

async function computeImpact(word, ctx) {
  const w = await embed(ctx);
  const wo = await embed(removeWord(ctx, word));
  return cosDist(w, wo);
}

function classifyWord(word, taxonomy) {
  const l = word.toLowerCase();
  for (const [cat, terms] of Object.entries(taxonomy)) {
    if (terms.some(t => l === t.toLowerCase() || l.includes(t.toLowerCase()))) return cat;
  }
  return null;
}

function modifierSummary(srcWords, voidW, absentW, tax) {
  const s = { note: "Classifications are interpretive (Layer B). Configurable, not ground truth." };
  for (const cat of Object.keys(tax)) {
    const terms = new Set(tax[cat].map(t=>t.toLowerCase()));
    const src = new Set(srcWords.filter(w=>terms.has(w.word)).map(w=>w.word)).size;
    const dropped = voidW.filter(w=>w.classification===cat).length;
    const injected = absentW.filter(w=>w.classification===cat).length;
    s[cat] = { source:src, kept:src-dropped, dropped, injected };
  }
  return s;
}

async function main() {
  const opts = parseArgs();
  let srcText = opts.source ? fs.readFileSync(opts.source,"utf-8") : opts.sourceText;
  let sumText = opts.summary ? fs.readFileSync(opts.summary,"utf-8") : opts.summaryText;
  if (!srcText) { console.error("ERROR: --source or --source-text required"); process.exit(1); }
  if (!sumText) { console.error("ERROR: --summary or --summary-text required"); process.exit(1); }

  const srcWC = srcText.split(/\s+/).length;
  const sumWC = sumText.split(/\s+/).length;
  if (srcWC < 10) console.error("WARNING: Source text is very short (<10 words). Results may be unreliable.");

  await initModel(opts.model);
  const srcWords = extractContentWords(srcText);
  const sumWords = extractContentWords(sumText);
  const srcSet = new Set(srcWords.map(w=>w.word));
  const sumSet = new Set(sumWords.map(w=>w.word));

  console.error("[eigenanamnesis] Computing semantic preservation...");
  const semPres = Math.round(cosSim(await embed(srcText), await embed(sumText))*10000)/10000;

  // Void words
  console.error(`[eigenanamnesis] Computing void word impacts...`);
  const voidCands = []; const seenV = new Set();
  for (const w of srcWords) { if (!sumSet.has(w.word) && !seenV.has(w.word)) { seenV.add(w.word); voidCands.push(w); }}
  const voidWords = [];
  for (const c of voidCands) {
    const imp = await computeImpact(c.word, c.context);
    if (imp >= opts.minImpact) voidWords.push({ word:c.word, embedding_impact:Math.round(imp*10000)/10000, source_context:truncCtx(c.context,c.word) });
  }
  voidWords.sort((a,b)=>b.embedding_impact-a.embedding_impact);
  const topVoid = voidWords.slice(0, opts.topN);

  // Absent words
  console.error(`[eigenanamnesis] Computing absent word impacts...`);
  const absCands = []; const seenA = new Set();
  for (const w of sumWords) { if (!srcSet.has(w.word) && !seenA.has(w.word)) { seenA.add(w.word); absCands.push(w); }}
  const absentWords = [];
  for (const c of absCands) {
    const imp = await computeImpact(c.word, c.context);
    if (imp >= opts.minImpact) absentWords.push({ word:c.word, embedding_impact:Math.round(imp*10000)/10000, summary_context:truncCtx(c.context,c.word) });
  }
  absentWords.sort((a,b)=>b.embedding_impact-a.embedding_impact);
  const topAbsent = absentWords.slice(0, opts.topN);

  // Classification
  let modSum = null;
  if (opts.classify) {
    let tax = DEFAULT_TAXONOMY;
    if (opts.taxonomy) tax = JSON.parse(fs.readFileSync(opts.taxonomy,"utf-8")).categories;
    for (const w of topVoid) w.classification = classifyWord(w.word, tax) || "unclassified";
    for (const w of topAbsent) w.classification = classifyWord(w.word, tax) || "unclassified";
    modSum = modifierSummary(srcWords, topVoid, topAbsent, tax);
  }

  const result = {
    meta: { eigenanamnesis_version:VERSION, embedding_model:opts.model,
      timestamp:new Date().toISOString(),
      layer_a:"measurement — deterministic, reproducible",
      layer_b: opts.classify ? "interpretation — v0.2.0 taxonomy applied" : "interpretation — disabled" },
    measurement: {
      semantic_preservation:semPres, source_word_count:srcWC, summary_word_count:sumWC,
      compression_ratio:Math.round((sumWC/srcWC)*1000)/1000,
      unique_content_words_source:srcSet.size, unique_content_words_summary:sumSet.size,
      void_word_count:topVoid.length, absent_word_count:topAbsent.length,
      void_words:topVoid, absent_words:topAbsent,
      ...(modSum ? { modifier_summary:modSum } : {})
    }
  };

  const json = JSON.stringify(result, null, 2);
  if (opts.output) { fs.writeFileSync(opts.output, json); console.error(`[eigenanamnesis] Saved to ${opts.output}`); }
  else console.log(json);
  console.error("[eigenanamnesis] Done.");
}
main().catch(e=>{ console.error("[eigenanamnesis] Fatal:",e.message); process.exit(1); });
