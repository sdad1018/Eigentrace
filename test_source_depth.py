#!/usr/bin/env python3
"""
test_source_depth.py — OUT-OF-TREE. Tests Gemini's hypothesis: does SOURCE
semantic depth (not consensus divergence) separate meaningful consensus-voids
from noise?

The divergence gate FAILED (15% vs 17% escalation words — no separation).
Gemini's claim: the real variable is whether the SOURCE had depth to omit.
Palantir-defense source = dense -> "information warfare" is a real omission.
Market-Talk roundup = thin list -> void is just noise.

CRITICAL ANTI-CIRCULARITY: depth must be measured INDEPENDENTLY of void content.
We do NOT define depth using conflict/charged words (that would just measure the
same thing twice). We use content-agnostic structural + concentration signals.

READS STORED DATA ONLY. No live code. No GPU (depth signals are lexical/structural).

Tests several independent depth proxies and asks for EACH: do meaningful voids
concentrate in high-depth sources? If one cleanly separates, the gate is real.
"""
import json, glob, re, statistics

SEG_DIR = "/home/remvelchio/eigentrace/tmp/segments/*_segment.json"

# Escalation/meaningful-void probe terms (the OUTCOME we're separating on).
# These are checked ONLY in the void words, NEVER in the depth computation.
ESC = {"war","wwiii","wwii","nuclear","arms","blockade","invasion","missile",
       "strike","genocid","jihad","militar","proxy","ceasefire","casualt",
       "escalat","sanction","occupation","warfare","insurgen","atrocity",
       "regime","coup","airstrike","bombard","offensive"}

# List/stub markers in TITLE — content-agnostic structural signal
THIN_TITLE = ["roundup","market talk","live:","recap","scores","odds","watch:",
              "live blog","as it happened","- la liga","vs ","price target",
              "raises its","lowers its","initiates coverage","gearing up"]

def void_is_meaningful(void):
    return any(any(e in w.lower() for e in ESC) for w in void)

def harvest():
    rows = []
    for f in glob.glob(SEG_DIR):
        try:
            d = json.load(open(f)); a = d.get("attribution", {})
            mr = a.get("model_responses", {})
            if len([m for m,t in mr.items() if t and len(t) > 50]) < 4: continue
            vw = a.get("synthesis_words") or a.get("void_words") or []
            if not vw: continue
            sb = a.get("source_body","") or ""
            title = a.get("story_title") or d.get("title") or ""
            # --- INDEPENDENT depth signals (none use void content or ESC terms) ---
            # 1. raw source length
            src_len = len(sb)
            # 2. sentence count (narrative vs stub)
            n_sent = len([s for s in re.split(r'[.!?]+', sb) if len(s.strip()) > 15])
            # 3. lexical diversity (unique words / total) — lists repeat tickers/numbers
            words = re.findall(r'[a-zA-Z]{3,}', sb.lower())
            lexdiv = len(set(words)) / max(1, len(words))
            # 4. digit ratio — financial/score lists are digit-heavy
            digits = len(re.findall(r'\d', sb))
            digit_ratio = digits / max(1, len(sb))
            # 5. thin-title structural flag
            thin_title = any(t in title.lower() for t in THIN_TITLE)
            rows.append({
                "title": title[:70], "void": vw[:5],
                "meaningful": void_is_meaningful(vw),
                "src_len": src_len, "n_sent": n_sent, "lexdiv": round(lexdiv,3),
                "digit_ratio": round(digit_ratio,4), "thin_title": thin_title,
                "density": a.get("consensus_density"),
            })
        except: pass
    return rows

def separation_test(rows, key, label, reverse=False):
    """Split by median of `key`; report meaningful-void rate in each half."""
    have = [r for r in rows if isinstance(r[key],(int,float))]
    if len(have) < 20: 
        print(f"  {label}: insufficient data"); return
    have.sort(key=lambda r: r[key], reverse=reverse)
    third = len(have)//3
    hi = have[:third]   # after sort: top third by key (high depth if reverse=True)
    lo = have[-third:]
    hi_rate = 100*sum(r["meaningful"] for r in hi)/len(hi)
    lo_rate = 100*sum(r["meaningful"] for r in lo)/len(lo)
    gap = hi_rate - lo_rate
    flag = "  <<< SEPARATES" if abs(gap) >= 8 else ""
    hilabel = "HIGH-depth" if reverse else "HIGH-value"
    lolabel = "LOW-depth" if reverse else "LOW-value"
    print(f"  {label}:")
    print(f"      {hilabel} third: {hi_rate:.0f}% meaningful  |  {lolabel} third: {lo_rate:.0f}% meaningful  |  gap {gap:+.0f}pp{flag}")

def main():
    rows = harvest()
    base = 100*sum(r["meaningful"] for r in rows)/len(rows)
    print(f"=== {len(rows)} stories | baseline meaningful-void rate: {base:.0f}% ===\n")
    print("Does any INDEPENDENT source-depth signal separate meaningful voids from noise?")
    print("(gap >= 8pp = the signal actually separates; divergence gave ~0pp)\n")

    separation_test(rows, "src_len",     "source length         ", reverse=True)
    separation_test(rows, "n_sent",      "sentence count        ", reverse=True)
    separation_test(rows, "lexdiv",      "lexical diversity     ", reverse=True)
    separation_test(rows, "digit_ratio", "digit ratio (lists)   ", reverse=False)  # LOW digits = high value?
    separation_test(rows, "density",     "consensus_density(ctl)", reverse=False)  # the failed gate, as control

    # thin-title flag (boolean)
    thin = [r for r in rows if r["thin_title"]]
    rich = [r for r in rows if not r["thin_title"]]
    if thin and rich:
        t_rate = 100*sum(r["meaningful"] for r in thin)/len(thin)
        r_rate = 100*sum(r["meaningful"] for r in rich)/len(rich)
        print(f"  thin-title flag       :")
        print(f"      RICH-title: {r_rate:.0f}% meaningful ({len(rich)} stories)  |  THIN/list-title: {t_rate:.0f}% ({len(thin)} stories)  |  gap {r_rate-t_rate:+.0f}pp{'  <<< SEPARATES' if abs(r_rate-t_rate)>=8 else ''}")

    # Combined best-guess filter: rich title AND substantive length
    print("\n=== COMBINED FILTER preview: rich-title AND src_len>median AND n_sent>=4 ===")
    med_len = statistics.median([r["src_len"] for r in rows])
    keep = [r for r in rows if not r["thin_title"] and r["src_len"]>med_len and r["n_sent"]>=4]
    if keep:
        k_rate = 100*sum(r["meaningful"] for r in keep)/len(keep)
        print(f"  kept {len(keep)}/{len(rows)} stories | meaningful-void rate among kept: {k_rate:.0f}% (baseline {base:.0f}%)")
        print(f"  lift: {k_rate-base:+.0f}pp\n")
        print("  SAMPLE of kept stories (eyeball: are these the real ones?):")
        import random; random.seed(3)
        for r in random.sample(keep, min(15,len(keep))):
            mk = "***" if r["meaningful"] else "   "
            print(f"   {mk} [{r['title']}]")
            print(f"        void: {r['void']}")

if __name__ == "__main__":
    main()
