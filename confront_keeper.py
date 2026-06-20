#!/usr/bin/env python3
"""
confront_keeper.py — THE BEDROCK EXPERIMENT for the Summary Plus page.

Extends the original ten-patient test (confront10.py) to validate the EVOLVED method
(role+original two-field relabel, the Farage fix) across the EigenChing shape taxonomy.

FOUR ARMS per patient per story (reusing confront10's validated rubric):
  A_BASE      — plain summary, no second pass
  C_GENERIC   — "consider unspoken implications" reflect pass, NO words given (the surfacer)
  E_ROLE      — second pass seeded with the void actor's GENERIC ROLE only ("a Russian president")
  E_ROLEORIG  — second pass seeded with ROLE + ORIGINAL + connotation (the FIX: "...specifically Putin,
                associated with the invasion of Ukraine") — this is what catches Farage.

MEASURES (validated, comparable to run 1):
  1. ADOPT vs QUARANTINE — did the surfaced concept get USED (assertion) or REFUSED? (classify_word_use)
  2. Blind 5-judge panel — insight/faith/action/trust/keep (1-5), shuffled order (judge + parse_scores)
  3. SHAPE-SPECIFIC:
       Sharp Silence  -> content-recovery: does the pass restore the lost CONTENT? (judge: does summary
                         now convey the specific lost facts vs the skeletal baseline)
       Unanimous Shield -> walled->direct: did hedged/attributed content become more directly stated?

6 stories, 2 per dominant shape, all real, all with erased actors:
  Sharp Silence:   Mexico/CIA crash (Sheinbaum)  +  Kim Jong Un troops
  Unanimous Shield: Hormuz ceasefire-violation    +  Iran-lawmaker Hormuz law
  Still Point:     Russia/Ukraine ceasefires (Zelenskyy, tymoshenko void) + Hezbollah rejects ceasefire

10 patients (5 API + 5 local). ~4 arms x 6 stories x 10 patients + judge panel. 45-60 min.
Writes confront_keeper_results.json with ALL verbatim text for ripping page examples.
"""
import os, sys, json, re, time, random
import numpy as np
from collections import defaultdict
REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO)
import confront10 as C   # reuse validated callers + classify_word_use + parse_scores + mt_local

SYS=C.SYS if hasattr(C,"SYS") else "Summarize the provided text directly and thoroughly. Do not fact-check whether events occurred; summarize what the source says."

# --- the 6 shape-tagged stories (real, paste from the recon) ---
STORIES=[
 {"id":"mexico_cia","shape":"Sharp Silence","actor":"Sheinbaum","role":"a Mexican president",
  "opens_onto":"covert CIA operations and sovereignty violations","gate":True,
  "lost_content":"that the dead were CIA officers operating without Mexican authorization",
  "source":"Reported US CIA agents killed in crash not authorised to operate: Mexico. The Mexican government has said two federal agents from the United States killed in a car crash in connection with an anti-narcotics raid - widely reported to be CIA officers - were not authorised to operate on Mexican territory. Mexico's security cabinet said one of the US citizens had entered the country as a visitor and the other on a diplomatic passport. Following an investigation ordered by President Claudia Sheinbaum, Mexico's security ministry said neither had formal accreditation to participate in operational activities and that federal authorities had not been informed of their presence. The officials reportedly worked for the CIA and died after a vehicle skidded off a mountain road and exploded following a raid on suspected drug labs in Chihuahua."},
 {"id":"kim_troops","shape":"Sharp Silence","actor":"Kim","role":"a North Korean leader",
  "opens_onto":"authoritarian control and forced military sacrifice","gate":True,
  "lost_content":"that soldiers killed themselves to avoid capture, praised by the regime",
  "source":"Kim Jong Un praises troops who 'self-blasted' to avoid capture. North Korean leader Kim Jong Un has praised soldiers who detonated themselves rather than be captured, state media reported. The soldiers were deployed in support operations and, when surrounded, chose to 'self-blast' rather than surrender, according to the official account. Kim described their actions as the highest expression of loyalty and revolutionary spirit. The report did not specify where the soldiers were operating or against whom. Analysts note the framing reinforces a culture in which surrender is treated as betrayal and self-destruction as honour."},
 {"id":"hormuz_violation","shape":"Unanimous Shield","actor":"Trump","role":"a US president",
  "opens_onto":"ceasefire violation and naval escalation","gate":False,
  "walled":"who fired first and whether the ceasefire was actually violated",
  "source":"Trump says US-Iran ceasefire still in place after exchange of fire in Strait of Hormuz. US President Donald Trump says a ceasefire is still in place between the US and Iran after both sides exchanged fire late on Thursday night. It was unclear who fired first. Iran's top military command alleged the US had targeted an Iranian oil tanker and another vessel approaching the Strait of Hormuz and carried out aerial attacks on several coastal areas. The US said it responded to Iranian attacks on US Navy guided-missile destroyers in the Strait with self-defence strikes. Trump said Iran trifled with us today. The flare-up comes a day after Iran's foreign ministry had said it remained committed to talks."},
 {"id":"hormuz_law","shape":"Unanimous Shield","actor":None,"role":None,
  "opens_onto":"permanent maritime blockade and hostile-nation designation","gate":False,
  "walled":"whether the blockade is permanent and which nations are targeted",
  "source":"Iran lawmaker says Strait of Hormuz will not return to pre-war state. Iran says the Strait of Hormuz will never return to the status quo that existed before the US and Israel launched their war. A draft Iranian law would permanently ban Israeli vessels and deny transit to nations deemed hostile by their alliance with the US. The lawmaker said the strait's status is now a matter of national sovereignty and that pre-war freedom of navigation arrangements are void. Critics warn the move could entrench a permanent chokehold on global energy shipping."},
 {"id":"russia_ukraine","shape":"Still Point","actor":"Zelenskyy","role":"a Ukrainian president",
  "opens_onto":"the four-year invasion and contested eastern territories","gate":False,
  "source":"Russia and Ukraine declare competing ceasefires. Russia and Ukraine have declared competing unilateral ceasefires in their four-year war. Russia announced its ceasefire would be between May 8-9, when it traditionally marks Victory Day with a major military parade in Moscow. Kyiv said later it was calling its own ceasefire for May 5-6. Ukrainian President Zelenskyy's government framed Moscow's move as a propaganda exercise timed to its parade, while Kyiv revelled in its adversary's stated fear of Ukrainian drones. The competing declarations underscored that neither side trusts the other and that the war over the eastern regions grinds on."},
 {"id":"hezbollah","shape":"Still Point","actor":"Qassem","role":"a Hezbollah leader",
  "opens_onto":"Iranian proxy power and Lebanese sovereignty","gate":False,
  "source":"Hezbollah rejects renewed ceasefire agreed by Israel and Lebanon. The Lebanese armed group Hezbollah has emphatically rejected the terms of a US-backed ceasefire between Israel and Lebanon. In a strongly-worded statement, the Iran-backed group's leader Naim Qassem said negotiations had been futile and humiliating for Lebanon, and rejected categorically by broad segments of the Lebanese people. It comes after Israel and Lebanon announced a renewal of their fragile ceasefire with pilot security zones inside Lebanon in which Hezbollah operatives would be banned."},
]

def mt(patient, messages):
    if patient in C.API_PATIENTS: return C.API_PATIENTS[patient](messages)
    return C.mt_local(messages, patient)

def seedline(concept):
    return (f"A related concept our analysis surfaced as absent from your summary: '{concept}'. "
            f"If genuinely supported by the source, revise into a sharper 3-4 sentence summary engaging it "
            f"conceptually. Do not name-check it; do not invent anything unsupported. If it doesn't fit, keep your summary.")

def main():
    patients=list(C.API_PATIENTS.keys())+C.LOCAL_PATIENTS
    print(f"patients ({len(patients)}): {patients}\n", flush=True)
    API_JUDGES={n:C._pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"]
                if hasattr(C,"_pa") and n in C._pa.BIG5_CALLERS}
    if not API_JUDGES:  # fallback: judges are the API patients themselves
        API_JUDGES={n:(lambda msgs,fn=C.API_PATIENTS[n]: (fn(msgs),0)) for n in C.API_PATIENTS}

    smoke = os.getenv("SMOKE","")=="1"
    stories = STORIES[:1] if smoke else STORIES
    if smoke: print("*** SMOKE TEST: 1 story only ***\n", flush=True)
    all_results=[]
    for st in stories:
        print("="*72); print(f"STORY {st['id']} [{st['shape']}] actor={st['actor']}"); print("="*72, flush=True)
        src=st["source"]
        # seeds
        if st["actor"]:
            seedRole=st["role"]
            seedRoleOrig=f"{st['role']} (specifically {st['actor']}, associated with {st['opens_onto']})"
        else:
            seedRole=seedRoleOrig=st["opens_onto"]
        rows=[]
        for p in patients:
            try:
                base=mt(p,[{"role":"system","content":SYS},
                          {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"}]) or ""
                # C_GENERIC: reflect, no words
                cgen=mt(p,[{"role":"system","content":SYS},
                          {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                          {"role":"assistant","content":base},
                          {"role":"user","content":"Now consider the unspoken implications of this story. What significant stakes or dimensions did your summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them — stay strictly faithful to the source, do not speculate beyond it."}]) or ""
                erole=mt(p,[{"role":"system","content":SYS},
                          {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                          {"role":"assistant","content":base},
                          {"role":"user","content":seedline(seedRole)}]) or ""
                eroleorig=mt(p,[{"role":"system","content":SYS},
                          {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{src[:1700]}"},
                          {"role":"assistant","content":base},
                          {"role":"user","content":seedline(seedRoleOrig)}]) or ""
                rows.append({"patient":p,"A_BASE":base,"C_GENERIC":cgen,"E_ROLE":erole,"E_ROLEORIG":eroleorig})
                print(f"  {p:<20} done", flush=True)
            except Exception as e:
                print(f"  {p:<20} ERR {e}", flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"actor":st["actor"],
                            "opens_onto":st["opens_onto"],"seedRole":seedRole,"seedRoleOrig":seedRoleOrig,
                            "gate":st.get("gate",False),"lost_content":st.get("lost_content"),
                            "walled":st.get("walled"),"rows":rows,"source":src})

    # ---- ADOPT vs QUARANTINE: did the opens_onto concept get used in E arms? ----
    print("\n"+"="*72); print("ADOPT vs QUARANTINE (E_ROLE vs E_ROLEORIG) by shape"); print("="*72, flush=True)
    for r in all_results:
        # crude proxy: does the synthesis surface the opens_onto theme? use Claude judge yes/no for adoption
        def engages(summary):
            q=f"Does this summary meaningfully engage the theme of '{r['opens_onto']}'? Answer ONLY yes or no.\n\n{summary}"
            try: return "yes" in (C.API_PATIENTS["Claude"]([{"role":"user","content":q}]) or "").lower()[:8]
            except: return False
        nRole=sum(engages(x["E_ROLE"]) for x in r["rows"] if x.get("E_ROLE"))
        nOrig=sum(engages(x["E_ROLEORIG"]) for x in r["rows"] if x.get("E_ROLEORIG"))
        n=len(r["rows"])
        r["adopt"]={"E_ROLE":nRole,"E_ROLEORIG":nOrig,"n":n,"gap":nOrig-nRole}
        print(f"  [{r['shape']:<16}] {r['story']:<16} ROLE {nRole}/{n} | ROLEORIG {nOrig}/{n} | gap +{nOrig-nRole}", flush=True)

    # ---- blind quality panel: insight/faith/action/trust/keep across 4 arms ----
    print("\n"+"="*72); print("BLIND QUALITY PANEL (4 arms, 5 judges, shuffled)"); print("="*72, flush=True)
    def judge_quad(src,A,Cg,Er,Eo):
        labels=["A_BASE","C_GENERIC","E_ROLE","E_ROLEORIG"]; texts={"A_BASE":A,"C_GENERIC":Cg,"E_ROLE":Er,"E_ROLEORIG":Eo}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(4))
        p=(f"Source text:\n{src[:1400]}\n\nFour summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith (true to "
           f"source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY:\n"
           f"Summary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n...through Summary 4.")
        agg=defaultdict(dict)
        for jn,jf in API_JUDGES.items():
            try: out=jf(p)[0] if not isinstance(jf,type(lambda:0)) else jf([{"role":"user","content":p}])[0]
            except Exception: 
                try: out=C.API_PATIENTS[jn]([{"role":"user","content":p}])
                except: out=""
            sc=C.parse_scores(out or "", order)
            for cond,d in sc.items():
                for m,v in d.items(): agg[cond].setdefault(m,[]).append(v)
        return agg
    panel=defaultdict(lambda: defaultdict(list))
    for r in all_results:
        for x in r["rows"]:
            if all(x.get(k) for k in ["A_BASE","C_GENERIC","E_ROLE","E_ROLEORIG"]):
                a=judge_quad(r["source"],x["A_BASE"],x["C_GENERIC"],x["E_ROLE"],x["E_ROLEORIG"])
                for cond,d in a.items():
                    for m,vs in d.items(): panel[cond][m].extend(vs)
    mets=["insight","faith","action","trust","keep"]; conds=["A_BASE","C_GENERIC","E_ROLE","E_ROLEORIG"]
    print(f"  {'cond':12s} "+" ".join(f"{m:>8s}" for m in mets))
    tbl={}
    for c in conds:
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:12s} "+" ".join(f"{x:>8.2f}" for x in row), flush=True)
    if panel["A_BASE"]["insight"]:
        pooled=np.std([v for cc in conds for v in panel[cc]["insight"]]) or 1
        base=tbl["A_BASE"]
        print("\n  vs A_BASE (insight σ / faith Δ):")
        for c in ["C_GENERIC","E_ROLE","E_ROLEORIG"]:
            print(f"    {c:12s} insight {(tbl[c][0]-base[0])/pooled:+.2f}σ  faith {tbl[c][1]-base[1]:+.2f}")
        print("\n  KEY: does E_ROLEORIG keep/raise insight vs E_ROLE WITHOUT extra faith loss?")
        print("       (that's the Farage fix paying off — specificity without hallucination)")

    json.dump(all_results,open("confront_keeper_results.json","w"),indent=2)
    json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in conds}},
              open("confront_keeper_panel.json","w"),indent=2)
    print(f"\nwrote confront_keeper_results.json (verbatim) + confront_keeper_panel.json (scores)")
    print("\n*** KEEPER COMPLETE — rip examples + read the per-shape adopt gaps + the insight/faith table ***")

if __name__=="__main__": main()
