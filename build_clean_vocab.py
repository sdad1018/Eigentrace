#!/usr/bin/env python3
"""
build_clean_vocab.py — Build cleaned vocabularies for the void/raycast paths.

ROOT CAUSE (confirmed by recon):
  - global_vocab (184k) = wordfreq_200k + curated_22k -> mostly real words + obscure tail
  - raycast_vocab (253k) = real words + WIKIPEDIA TITLES ('1979 NASCAR Winston West Series',
    '1932 Democratic National Convention') -> THIS is why void words were junk
  The two void paths use two different dirty vocabs. Clean both.

FILTERS (each measured/justified, NO phantom whitelist):
  1. zipf >= 2.5  -> concept/junk split (measured 95% signal / 85% junk). Multiword:
     min over content words. Accepts a few rare concepts lost (e.g. cyberwarfare 2.02)
     as an HONEST stated cost, not a hack.
  2. ASCII-only, lowercase-able, alpha (+ spaces/hyphens) -> kills transliterations
     (steaua, españa, chávez) and Wikipedia-title cruft (digits, caps phrases).
  3. drop multi-word phrases with >2 words OR any digit OR any capital -> kills
     Wikipedia titles ('1979 NASCAR...', 'Democratic National Convention').

CALIBRATES against labeled SIGNAL/JUNK/NAMES FIRST and prints survival, so we
confirm it keeps arms-deal/foreign-interference and kills meriweather/steaua
BEFORE writing anything. Writes *_clean.{json,pt} — does NOT touch live files.

No GPU (slices existing tensors). Run on Bertha.
"""
import json, re, sys
import numpy as np

try:
    from wordfreq import zipf_frequency
except ImportError:
    print("need: pip install --break-system-packages wordfreq"); sys.exit(1)

ZIPF_FLOOR = 2.5

# labeled cases for calibration (do NOT define the filter, only verify it)
SIGNAL = ["arms deal","foreign interference","proxy war","regime change","trade war",
          "market manipulation","naval blockade","regime collapse","currency collapse",
          "genocidal","sanctions","occupation","ceasefire","annexation","insurgency",
          "escalation","deterrence","embargo","proliferation","warfare","blockade",
          "propaganda","surveillance","airstrike","cyberwarfare","information warfare"]
JUNK   = ["meriweather","unlashed","robotism","detribalize","drowsily","infernally",
          "orphic","alfresco","beryllium","fogged","indenture","unrelieved","warless",
          "electrostate","robotism"]
NAMES  = ["poroshenko","steaua","narodnaya","palestina","roumania","chavez","españa",
          "hizbullah","motorcity"]
WIKI   = ["1979 NASCAR Winston West Series","1932 Democratic National Convention",
          "Princeton Tigers basketball","Xtreme Soccer League season"]

def is_clean(w):
    """Return True if word passes all filters."""
    wl = w.lower().strip()
    if not wl: return False
    # filter 2: ascii + alpha (allow internal spaces/hyphens)
    if not wl.isascii(): return False
    if not re.fullmatch(r"[a-z][a-z\- ]*[a-z]", wl) and not re.fullmatch(r"[a-z]+", wl):
        return False
    # filter 3: kill wiki-title cruft — any digit, any capital in original, >2 words
    if any(c.isdigit() for c in w): return False
    if any(c.isupper() for c in w): return False
    if len(wl.split()) > 2: return False
    # filter 1: frequency floor (multiword: min over parts)
    parts = wl.split()
    zf = min(zipf_frequency(p, 'en') for p in parts)
    if zf < ZIPF_FLOOR: return False
    return True

def calibrate():
    print(f"=== CALIBRATION (zipf floor {ZIPF_FLOOR}) — verify before building ===\n")
    for label, group in [("SIGNAL (want KEPT)",SIGNAL),("JUNK (want CUT)",JUNK),
                          ("NAMES (want CUT)",NAMES),("WIKI TITLES (want CUT)",WIKI)]:
        kept=[w for w in group if is_clean(w)]; cut=[w for w in group if not is_clean(w)]
        print(f"{label}:")
        print(f"   KEPT ({len(kept)}/{len(group)}): {kept}")
        print(f"   CUT  ({len(cut)}/{len(group)}): {cut}")
        print()
    sig_keep = sum(1 for w in SIGNAL if is_clean(w))/len(SIGNAL)
    junk_cut = sum(1 for w in JUNK+NAMES+WIKI if not is_clean(w))/len(JUNK+NAMES+WIKI)
    print(f"  >>> SIGNAL kept: {100*sig_keep:.0f}%  |  JUNK/NAMES/WIKI cut: {100*junk_cut:.0f}%")
    print(f"  (cyberwarfare at 2.02 will be cut by the 2.5 floor — honest stated cost)\n")
    return sig_keep, junk_cut

def clean_vocab(json_path, pt_path, out_prefix, is_npy=False):
    print(f"=== cleaning {json_path} ===")
    meta = json.load(open(json_path))
    words = meta["words"]
    print(f"  original: {len(words)} words")
    keep_idx = [i for i,w in enumerate(words) if is_clean(w)]
    keep_words = [words[i] for i in keep_idx]
    print(f"  cleaned:  {len(keep_words)} words ({100*len(keep_words)/len(words):.0f}% kept)")
    print(f"  sample survivors: {keep_words[:15]}")

    # slice the tensor/matrix
    if is_npy:
        M = np.load(pt_path)
        Mc = M[keep_idx]
        np.save(f"{out_prefix}.npy", Mc)
        print(f"  wrote {out_prefix}.npy {Mc.shape}")
    else:
        import torch
        T = torch.load(pt_path, map_location="cpu", weights_only=True)
        Tc = T[keep_idx].contiguous()
        torch.save(Tc, f"{out_prefix}.pt")
        print(f"  wrote {out_prefix}.pt {tuple(Tc.shape)}")

    out_meta = dict(meta); out_meta["words"]=keep_words; out_meta["count"]=len(keep_words)
    out_meta["source"]=meta.get("source","")+f" | cleaned zipf>={ZIPF_FLOOR}+ascii+nowiki"
    json.dump(out_meta, open(f"{out_prefix}.json","w"))
    print(f"  wrote {out_prefix}.json\n")
    return len(keep_words)

def main():
    sig_keep, junk_cut = calibrate()
    if sig_keep < 0.7:
        print("ABORT: signal retention too low, filter too aggressive."); return
    if junk_cut < 0.7:
        print("WARNING: junk cut rate low, filter too loose — review before using.")
    if "--build" not in sys.argv:
        print("Calibration only. Re-run with --build to write cleaned vocab files.")
        return
    print("="*60)
    clean_vocab("vocab/global_vocab.json","vocab/global_vocab.pt",
                "vocab/global_vocab_clean")
    clean_vocab("vocab/raycast_vocab.json","vocab/raycast_vocab.npy",
                "vocab/raycast_vocab_clean", is_npy=True)
    print("DONE. Cleaned vocabs written with _clean suffix. Live files untouched.")
    print("Next: recompute void words on a sample with the clean vocab and eyeball.")

if __name__=="__main__":
    main()
