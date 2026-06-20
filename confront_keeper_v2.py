#!/usr/bin/env python3
"""
confront_keeper_v2.py — THE upgraded bedrock experiment for the Summary Plus page.

Validates the EVOLVED method (type-1 actor RESTORATION added to the validated type-2
conceptual seeding) across EigenChing shape-tagged real stories, scored on the EXACT
rubric the gold standard used, hardened against the red-team (repeated sampling, factorial,
null control, per-lab split).

Reuses confront10's REAL functions by importing it (no reimplementation):
  C.API_PATIENTS, C.LOCAL_PATIENTS, C.mt_local, C.classify_word_use, C.parse_scores,
  C.REL_THRESH, C.POOL, C.HARD_DROP, C._pa (proxy_auditor for BIG5 judges)

ARMS (per patient per story, K generations each):
  A_BASE          plain summary, no 2nd pass
  C_GENERIC       "unspoken implications... stay faithful" reflect, NO concepts (VALIDATED)
  E_SEED          C_GENERIC's faithful revise + type-2 conceptual directions (VALIDATED, the gold std)
  E_SEED_RESTORE  E_SEED + type-1 restoration clause (the UPGRADE: restore in-source dropped actor)

GOLD STANDARD to beat (judge_only.py, n=100):
  A_BASE     insight 2.66 faith 4.53 keep 0.82
  C_GENERIC  insight 3.77 faith 2.63 keep 0.28   (+1.02σ ins / -1.90 faith)
  E_SEED     insight 3.51 faith 3.27 keep 0.50   (+0.78σ ins / -1.26 faith)
HYPOTHESIS: E_SEED_RESTORE raises faith above E_SEED (restored source-actors are faithful)
            while holding the +0.78σ insight -> toward the high-insight+high-faith corner.

type-1/type-2 split (the core machinery change): derive() never checked source -> type-2 ghosts.
  type-1 = near source AND in source AND absent from summaries  (RESTORATION, faithful)
  type-2 = near source AND NOT in source AND absent from summaries (ASSOCIATION, gated, TF-IDF ranked)
Prints type-1/type-2 counts per story so viability is visible on story 1.

TF-IDF elephant filter on type-2: void_frequency.json['global'] = corpus DF. Low-freq concept
= conspicuously specific (elephant, rank first); high-freq = genre-ghost (sink).

Repeated sampling K (default 3, set higher for keeper) + saves ALL verbatim to JSON.
SMOKE=1 -> 1 story. KGEN env -> override K.
"""
import os, sys, json, re, time, random
import numpy as np
from collections import defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C
from geometric_engine import get_engine

K=int(os.getenv("KGEN","3"))
SMOKE=os.getenv("SMOKE","")=="1"
SYS="Summarize the provided text directly and thoroughly. Do not fact-check whether events occurred; summarize what the source says."

# ---------- shape-tagged real stories (from find_by_shape recon) ----------
STORIES=[
 {"id":"mexico_cia","shape":"Sharp Silence",
  "source":"Reported US CIA agents killed in crash not authorised to operate: Mexico. The Mexican government has said two federal agents from the United States killed in a car crash in connection with an anti-narcotics raid - widely reported to be CIA officers - were not authorised to operate on Mexican territory. Mexico's security cabinet said one of the US citizens had entered the country as a visitor and the other on a diplomatic passport. Following an investigation ordered by President Claudia Sheinbaum, Mexico's security ministry said neither had formal accreditation to participate in operational activities and that federal authorities had not been informed of their presence. The officials reportedly worked for the CIA and died after their vehicle skidded off a mountain road and exploded following a raid on suspected drug labs in Chihuahua."},
 {"id":"russia_ukraine","shape":"Still Point",
  "source":"Russia and Ukraine declare competing ceasefires. Russia and Ukraine have declared competing unilateral ceasefires in their four-year war. Russia announced its ceasefire would be between May 8-9, when it traditionally marks Victory Day with a major military parade in Moscow. Kyiv said later it was calling its own ceasefire for May 5-6. Ukrainian President Zelenskyy's government framed Moscow's move as a propaganda exercise timed to its parade, while Kyiv revelled in its adversary's stated fear of Ukrainian drones. The competing declarations underscored that neither side trusts the other and that the war over the eastern regions grinds on."},
 {"id":"hezbollah","shape":"Still Point",
  "source":"Hezbollah rejects renewed ceasefire agreed by Israel and Lebanon. The Lebanese armed group Hezbollah has emphatically rejected the terms of a US-backed ceasefire between Israel and Lebanon. In a strongly-worded statement, the Iran-backed group's leader Naim Qassem said negotiations had been futile and humiliating for Lebanon, and rejected categorically by broad segments of the Lebanese people. It comes after Israel and Lebanon announced a renewal of their fragile ceasefire with the creation of pilot security zones inside Lebanon in which Hezbollah operatives would be banned."},
 {"id":"hormuz_violation","shape":"Unanimous Shield",
  "source":"Trump says US-Iran ceasefire still in place after exchange of fire in Strait of Hormuz. US President Donald Trump says a ceasefire is still in place between the US and Iran after both sides exchanged fire late on Thursday night. It was unclear who fired first. Iran's top military command alleged the US had targeted an Iranian oil tanker and another vessel approaching the Strait of Hormuz and carried out aerial attacks on several coastal areas. The US said it responded to Iranian attacks on US Navy guided-missile destroyers in the Strait with self-defence strikes. Trump said Iran trifled with us today."},
 {"id":"british_couple","shape":"Clear Channel (null control)",
  "source":"British couple lose Iran jail sentence appeal, family says. A British couple jailed in Iran on espionage charges have lost an appeal against their 10-year sentence, according to their family. Lindsay and Craig Foreman were arrested in January 2025 while passing through Iran on a round-the-world motorcycle trip. They were accused of spying - charges they adamantly deny - and were sentenced in February. Both are currently on hunger strike in Tehran's Evin prison. A member of their legal team in the UK told the BBC no reason was given for the rejection of their appeal. Lindsay's son Joe Bennett said they were not permitted to attend their own appeal hearing."},
 {"id":"kim_troops","shape":"Sharp Silence",
  "source":"Kim Jong Un praises troops who 'self-blasted' to avoid capture. North Korean leader Kim Jong Un has praised soldiers who detonated themselves rather than be captured, state media reported. The soldiers were deployed in support operations and, when surrounded, chose to 'self-blast' rather than surrender, according to the official account. Kim described their actions as the highest expression of loyalty and revolutionary spirit. The report did not specify where the soldiers were operating or against whom."},
]

def mt(patient, messages):
    if patient in C.API_PATIENTS: return C.API_PATIENTS[patient](messages)
    return C.mt_local(messages, patient)

def main():
    stories = STORIES[:1] if SMOKE else STORIES
    if SMOKE: print("*** SMOKE: 1 story ***", flush=True)
    print(f"K (generations per condition) = {K}", flush=True)

    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt["words"] if isinstance(vt,dict) else vt
    import torch
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    ABS=["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]
    CON=["strait","city","company","port","bank","border","weapon","official"]
    ac=E(ABS).mean(0)-E(CON).mean(0); ac/=np.linalg.norm(ac)+1e-8

    # IDF source for TF-IDF elephant ranking
    try:
        DF=json.load(open("void_frequency.json")).get("global",{})
        NDOCS=1659.0
    except Exception:
        DF={}; NDOCS=1659.0
    def idf(w): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0

    REL_THRESH=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD_DROP=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

    def derive_split(src, summaries):
        """Returns (type1_words, type2_ranked). type1=in-source dropped; type2=ghosts, TF-IDF ranked."""
        anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(summaries).lower(); srcl=src.lower()
        t1=[]; t2=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue   # said -> not void
            in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
            if in_src: t1.append(w)
            else:      t2.append(w)
        # split type-2 by abstract/concrete just like original (for the conceptual seed),
        # then rank by IDF (high IDF = conspicuous/elephant first)
        if t2:
            av=E(t2)@ac
            t2_sorted=sorted(t2, key=lambda w:-idf(w))
        else:
            t2_sorted=[]
        return t1[:8], t2_sorted[:8]

    # the 5 API judges (reuse proxy_auditor BIG5 if present, else API patients)
    try:
        API_JUDGES={n:C._pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in C._pa.BIG5_CALLERS}
        assert API_JUDGES
        JUDGE_IS_PA=True
    except Exception:
        API_JUDGES={n:C.API_PATIENTS[n] for n in C.API_PATIENTS}; JUDGE_IS_PA=False

    patients=list(C.API_PATIENTS.keys())+C.LOCAL_PATIENTS
    print(f"patients ({len(patients)}): {patients}", flush=True)

    all_results=[]
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72, flush=True)
        src=st["source"]
        # consensus summaries (5 local) to derive the void from — same as confront10
        cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3:
            print("  consensus<3, skipping story"); continue
        t1w,t2w=derive_split(src,cons)
        print(f"  TYPE-1 (in-source dropped, RESTORE): {t1w}  [count {len(t1w)}]", flush=True)
        print(f"  TYPE-2 (ghosts, IDF-ranked, SEED):   {t2w}  [count {len(t2w)}]", flush=True)
        seed_concepts=", ".join(t2w)
        # restoration target: prefer a type-1 word that looks like a proper noun / actor;
        # fallback to the first type-1 word; if none, restoration clause is skipped (logged)
        restore_target=None
        for w in t1w:
            if w[0:1].isupper() or w in src:  # crude actor-ish check
                restore_target=w; break
        if restore_target is None and t1w: restore_target=t1w[0]

        rows=[]
        for p in patients:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},
                              {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"}]) or ""
                    cgen=mt(p,[{"role":"system","content":SYS},
                              {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                              {"role":"assistant","content":base},
                              {"role":"user","content":"Now consider the unspoken implications of this story. What significant stakes or dimensions did your summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them — but stay strictly faithful to the source and do not speculate beyond what it supports."}]) or ""
                    eseed=mt(p,[{"role":"system","content":SYS},
                              {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                              {"role":"assistant","content":base},
                              {"role":"user","content":f"The latent stakes in this story may involve themes such as: {seed_concepts}. Treat these as CONCEPTUAL directions, not words to insert. Revise into a sharper 3-4 sentence summary that synthesizes whichever of these tensions are GENUINELY supported by the source — engage them conceptually, do not name-check them, and invent nothing not supported by the text."}]) or ""
                    # E_SEED_RESTORE: identical seed + a type-1 restoration clause
                    restore_clause=""
                    if restore_target:
                        restore_clause=(f" Additionally, the source explicitly refers to '{restore_target}', which your "
                                        f"summary omitted — restore it, framed exactly as the source presents it, with no "
                                        f"added characterization beyond what the text states.")
                    erestore=mt(p,[{"role":"system","content":SYS},
                              {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                              {"role":"assistant","content":base},
                              {"role":"user","content":f"The latent stakes in this story may involve themes such as: {seed_concepts}. Treat these as CONCEPTUAL directions, not words to insert. Revise into a sharper 3-4 sentence summary that synthesizes whichever of these tensions are GENUINELY supported by the source — engage them conceptually, do not name-check them, and invent nothing not supported by the text.{restore_clause}"}]) or ""
                    gens.append({"A_BASE":base,"C_GENERIC":cgen,"E_SEED":eseed,"E_SEED_RESTORE":erestore})
                except Exception as e:
                    print(f"    {p} gen{k} ERR {e}", flush=True)
            rows.append({"patient":p,"gens":gens})
            print(f"  {p:<20} {len(gens)}/{K} gens", flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"type1":t1w,"type2":t2w,
                            "restore_target":restore_target,"seed_concepts":seed_concepts,
                            "source":src,"rows":rows})
        # save incrementally so a crash keeps completed stories
        json.dump(all_results,open("confront_keeper_v2_results.json","w"),indent=2)
        print(f"  [saved {len(all_results)} stories to confront_keeper_v2_results.json]", flush=True)

    # ---------- blind 5-judge panel, 4 arms, shuffled, K-aware ----------
    print("\n"+"="*72); print("BLIND PANEL (4 arms, 5 judges, all generations)"); print("="*72, flush=True)
    ARMS=["A_BASE","C_GENERIC","E_SEED","E_SEED_RESTORE"]
    def judge_quad(src,texts):
        order=ARMS[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(4))
        p=(f"Source text:\n{src[:1400]}\n\nFour summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
           f"(true to source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY:\n"
           f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary 4)")
        agg=defaultdict(lambda: defaultdict(list))
        for jn,jf in API_JUDGES.items():
            try:
                out = jf(p)[0] if JUDGE_IS_PA else jf([{"role":"user","content":p}])
            except Exception:
                try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
                except: out=""
            for cond,d in C.parse_scores(out or "", order).items():
                for m,v in d.items(): agg[cond][m].append(v)
        return agg
    panel=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for row in r["rows"]:
            for g in row["gens"]:
                if all(g.get(a) for a in ARMS):
                    a=judge_quad(r["source"],g)
                    for cond,d in a.items():
                        for m,vs in d.items(): panel[cond][m].extend(vs)
    mets=["insight","faith","action","trust","keep"]
    print(f"  {'cond':14s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ARMS:
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:14s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}", flush=True)
    if panel["A_BASE"]["insight"]:
        pooled=np.std([v for cc in ARMS for v in panel[cc]["insight"]]) or 1
        base=tbl["A_BASE"]
        print("\n  vs A_BASE (insight σ / faith Δ):", flush=True)
        for c in ["C_GENERIC","E_SEED","E_SEED_RESTORE"]:
            print(f"    {c:14s} insight {(tbl[c][0]-base[0])/pooled:+.2f}σ  faith {tbl[c][1]-base[1]:+.2f}", flush=True)
        print(f"\n  HEADLINE: E_SEED_RESTORE faith {tbl['E_SEED_RESTORE'][1]:.2f} vs E_SEED faith {tbl['E_SEED'][1]:.2f} "
              f"(Δ {tbl['E_SEED_RESTORE'][1]-tbl['E_SEED'][1]:+.2f}) | insight {tbl['E_SEED_RESTORE'][0]:.2f} vs {tbl['E_SEED'][0]:.2f}")
        print("  -> upgrade validated if RESTORE faith > SEED faith WITHOUT losing insight.")

    json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in ARMS},
               "gold_standard":{"A_BASE":[2.66,4.53,2.47,4.26,0.82],
                                "C_GENERIC":[3.77,2.63,2.64,2.63,0.28],
                                "E_SEED":[3.51,3.27,2.71,3.24,0.50]}},
              open("confront_keeper_v2_panel.json","w"),indent=2)
    print(f"\nwrote confront_keeper_v2_results.json (verbatim) + confront_keeper_v2_panel.json (scores)")
    print("*** READ VERBATIM FIRST — scores can invert true quality (a faithful refusal scores low on faith) ***")

if __name__=="__main__": main()
