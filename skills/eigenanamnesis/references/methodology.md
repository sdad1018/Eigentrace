# EigenAnamnesis Methodology

See eigentrace.ai/anamnesis for the full information geometry framing.

## Algorithm
1. Tokenize source and summary into content words (excluding stopwords)
2. Identify void words (in source, absent from summary)
3. Identify absent words (in summary, absent from source)
4. For each: embed sentence with/without word, impact = cosine distance
5. Rank by impact, optionally classify via modifier taxonomy (Layer B)

## Taxonomy (v0.2.0)
- Covertness: quietly, secretly, internally, privately, covertly...
- Accountability: repeatedly, explicitly, formally, deliberately, knowingly...
- Precision: specifically, exactly, directly, precisely...
- Hedging: potentially, arguably, somewhat, appears, seems, suggests, evolving, shifting...

Taxonomy is configurable via --taxonomy flag. Categories are contestable defaults.

## Limitations
- Embedding impact ≠ meaning importance (proxy, not ground truth)
- Single embedding model may have biases
- Word-level: misses syntactic displacement
- English stopwords only
- Short texts (<50 words) produce unstable scores

Source: github.com/sdad1018/Eigentrace
