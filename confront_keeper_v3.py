#!/usr/bin/env python3
"""
confront_keeper_v3.py — THE bedrock experiment, three-channel model (Sean's final untangling).

Tests the THREE distinct Summary Plus channels as SEPARATE arms vs the validated E_SEED baseline:

  CHANNEL A (source-omission restoration — FACT, faithful by construction):
     A-content: derive() type-1 vocab words (in-source, dropped from summaries) e.g. 'authorised'
     A-actor:   spaCy NER PERSON/GPE/ORG in source, dropped from summaries e.g. 'Sheinbaum'
     -> both labeled so we read which recovers faith. (A-content proven +0.83 in v2 smoke.)
  CHANNEL B (target-word de-flattening — POINTER, gated):
     derive() type-2 SVD *target* word, which the original normalized to a class.
     Expose BOTH: the class AND the geometric exemplar, exemplar marked as a POINTER to a
     semantic neighborhood that MAY be irrelevant or a new node — verify vs source, don't assert.
     IDF-weighted (high-IDF exemplar = more trustworthy pointer; low-IDF = genre-ghost).
     *** This is Farage's only home: a normalized target word, NOT a source omission. ***
  CHANNEL C (void concept direction — DIRECTION, gated):
     derive() type-2 *void* words, abstract. The VALIDATED E_SEED clause. The thing to beat.

SIX ARMS (per patient per story, K generations):
  A_BASE / C_GENERIC / E_SEED(=C) / E_SEED+A / E_SEED+B / E_SEED+A+B

GOLD STANDARD (judge_only.py n=100): A_BASE ins2.66/fa4.53 ; C_GENERIC 3.77/2.63 ; E_SEED 3.51/3.27
v2 SMOKE confirmed: restoration (A-content 'authorised') recovered faith +0.83 w/o losing insight.

Reuses confront10's real fns by import. Saves verbatim JSON incrementally. SMOKE=1 -> 1 story. KGEN env.
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

# ---- spaCy NER for channel A-actor ----
_NLP=None
def get_nlp():
    global _NLP
    if _NLP is None:
        import spacy; _NLP=spacy.load("en_core_web_sm")
    return _NLP

def ner_actors_dropped(src, summaries):
    """PERSON/GPE/ORG entities in source that are absent from all summaries (dropped actors)."""
    nlp=get_nlp(); doc=nlp(src)
    summ=" ".join(summaries).lower()
    seen=set(); out=[]
    for ent in doc.ents:
        if ent.label_ not in ("PERSON","GPE","ORG"): continue
        name=ent.text.strip()
        if len(name)<3 or name.lower() in seen: continue
        seen.add(name.lower())
        # dropped = the entity's head token not present in summaries
        head=name.split()[-1].lower()  # surname / last token
        if not re.search(r'\b'+re.escape(head)+r'\b', summ):
            out.append((name, ent.label_))
    return out

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

    try:
        DF=json.load(open("void_frequency.json")).get("global",{}); NDOCS=1659.0
    except Exception:
        DF={}; NDOCS=1659.0
    def idf(w): return np.log((NDOCS+1)/(DF.get(w.lower(),0)+1))+1.0

    REL_THRESH=getattr(C,"REL_THRESH",0.45); POOL=getattr(C,"POOL",300)
    HARD_DROP=getattr(C,"HARD_DROP",{"realdonaldtrump","glazer","teheran","mideast","ticker","irani"})

    def derive_channels(src, summaries):
        """type-1 (A-content), type-2 void (C), type-2 target (B, IDF-ranked w/ class)."""
        anchor=E(src[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(summaries).lower(); srcl=src.lower()
        t1=[]; t2=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
            in_src=bool(re.search(r'\b'+re.escape(w.lower())+r'\b', srcl))
            (t1 if in_src else t2).append(w)
        # split type-2 into void(abstract>=0) vs target(concrete<0) on the ac axis
        void=[]; target=[]
        if t2:
            av=E(t2)@ac
            for w,a in zip(t2,av):
                (void if a>=0 else target).append(w)
        void_ranked=sorted(void, key=lambda w:-idf(w))[:8]      # channel C directions
        target_ranked=sorted(target, key=lambda w:-idf(w))[:6]  # channel B exemplars (high IDF first)
        return t1[:6], void_ranked, target_ranked

    try:
        API_JUDGES={n:C._pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in C._pa.BIG5_CALLERS}
        assert API_JUDGES; JUDGE_IS_PA=True
    except Exception:
        API_JUDGES={n:C.API_PATIENTS[n] for n in C.API_PATIENTS}; JUDGE_IS_PA=False

    patients=list(C.API_PATIENTS.keys())+C.LOCAL_PATIENTS
    print(f"patients ({len(patients)}): {patients}", flush=True)

    SEEDQ="Summarize this in 3-4 sentences:\n\n"
    REVISE="The latent stakes in this story may involve themes such as: {seeds}. Treat these as CONCEPTUAL directions, not words to insert. Revise into a sharper 3-4 sentence summary that synthesizes whichever of these tensions are GENUINELY supported by the source — engage them conceptually, do not name-check them, and invent nothing not supported by the text."

    all_results=[]
    for st in stories:
        print("\n"+"="*72); print(f"STORY {st['id']} [{st['shape']}]"); print("="*72, flush=True)
        src=st["source"]
        cons=[]
        for m in C.LOCAL_PATIENTS:
            s=C.mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{src[:1700]}"}],m)
            if s: cons.append(s)
        if len(cons)<3: print("  consensus<3, skipping"); continue

        t1w, void_w, target_w = derive_channels(src, cons)
        actors = ner_actors_dropped(src, cons)
        print(f"  CH-A content (type-1 vocab dropped): {t1w}", flush=True)
        print(f"  CH-A actors  (NER dropped):          {actors}", flush=True)
        print(f"  CH-B targets (SVD, IDF-ranked):      {target_w}", flush=True)
        print(f"  CH-C void    (directions):           {void_w}", flush=True)

        seeds=", ".join(void_w) if void_w else "the broader stakes implied by the source"

        # channel A clause: restore content + actor, both labeled
        a_bits=[]
        if t1w: a_bits.append(f"the source states '{t1w[0]}', which your summary dropped")
        if actors: a_bits.append(f"the source names '{actors[0][0]}', whom your summary omitted")
        chA = ""
        if a_bits:
            chA = (" Additionally, restore the following source facts, framed exactly as the source presents them "
                   "(no added characterization): " + "; ".join(a_bits) + ".")

        # channel B clause: class + exemplar-as-pointer (Farage de-flattening)
        chB = ""
        if target_w:
            ex=target_w[0]
            # the "class" = abstract role direction; we present exemplar as a POINTER, not a fact
            chB = (f" The geometry also circled '{ex}' as a specific node near this story. Treat it as a POINTER to a "
                   f"semantic neighborhood, not a fact: it may be directly relevant, tangential, or merely the densest "
                   f"nearby example of a broader type. Engage the neighborhood it suggests ONLY if the source supports it; "
                   f"do not assert '{ex}' itself unless the source does.")

        rows=[]
        for p in patients:
            gens=[]
            for k in range(K):
                try:
                    base=mt(p,[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]}]) or ""
                    pre=[{"role":"system","content":SYS},{"role":"user","content":SEEDQ+src[:1700]},{"role":"assistant","content":base}]
                    cgen=mt(p, pre+[{"role":"user","content":"Now consider the unspoken implications of this story. What significant stakes or dimensions did your summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them — but stay strictly faithful to the source and do not speculate beyond what it supports."}]) or ""
                    eC   = mt(p, pre+[{"role":"user","content":REVISE.format(seeds=seeds)}]) or ""               # E_SEED = channel C
                    eCA  = mt(p, pre+[{"role":"user","content":REVISE.format(seeds=seeds)+chA}]) or ""            # + channel A
                    eCB  = mt(p, pre+[{"role":"user","content":REVISE.format(seeds=seeds)+chB}]) or ""            # + channel B
                    eCAB = mt(p, pre+[{"role":"user","content":REVISE.format(seeds=seeds)+chA+chB}]) or ""        # + A + B
                    gens.append({"A_BASE":base,"C_GENERIC":cgen,"E_SEED":eC,
                                 "E_SEED_A":eCA,"E_SEED_B":eCB,"E_SEED_AB":eCAB})
                except Exception as e:
                    print(f"    {p} gen{k} ERR {e}", flush=True)
            rows.append({"patient":p,"gens":gens})
            print(f"  {p:<20} {len(gens)}/{K} gens", flush=True)
        all_results.append({"story":st["id"],"shape":st["shape"],"type1":t1w,"actors":actors,
                            "targets":target_w,"void":void_w,"chA":chA,"chB":chB,"source":src,"rows":rows})
        json.dump(all_results,open("confront_keeper_v3_results.json","w"),indent=2)
        print(f"  [saved {len(all_results)} stories]", flush=True)

    # ---- blind 6-arm panel ----
    print("\n"+"="*72); print("BLIND PANEL (6 arms, 5 judges, all gens, shuffled)"); print("="*72, flush=True)
    ARMS=["A_BASE","C_GENERIC","E_SEED","E_SEED_A","E_SEED_B","E_SEED_AB"]
    def judge(src,texts):
        order=ARMS[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(len(ARMS)))
        p=(f"Source text:\n{src[:1400]}\n\n{len(ARMS)} summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith "
           f"(true to source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY one line per "
           f"summary:\nSummary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n(through Summary {len(ARMS)})")
        agg=defaultdict(lambda: defaultdict(list))
        for jn,jf in API_JUDGES.items():
            try: out=jf(p)[0] if JUDGE_IS_PA else jf([{"role":"user","content":p}])
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
                    a=judge(r["source"],g)
                    for cond,d in a.items():
                        for m,vs in d.items(): panel[cond][m].extend(vs)
    mets=["insight","faith","action","trust","keep"]
    print(f"  {'cond':12s} "+" ".join(f"{m:>8s}" for m in mets)+f" {'n':>5s}")
    tbl={}
    for c in ARMS:
        row=[np.mean(panel[c][m]) if panel[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:12s} "+" ".join(f"{x:>8.2f}" for x in row)+f" {len(panel[c]['insight']):>5d}", flush=True)
    if panel["A_BASE"]["insight"]:
        pooled=np.std([v for cc in ARMS for v in panel[cc]["insight"]]) or 1
        b=tbl["A_BASE"]
        print("\n  vs A_BASE (insight σ / faith Δ):", flush=True)
        for c in ARMS[1:]:
            print(f"    {c:12s} insight {(tbl[c][0]-b[0])/pooled:+.2f}σ  faith {tbl[c][1]-b[1]:+.2f}", flush=True)
        print(f"\n  E_SEED baseline faith={tbl['E_SEED'][1]:.2f} insight={tbl['E_SEED'][0]:.2f}")
        for c in ["E_SEED_A","E_SEED_B","E_SEED_AB"]:
            print(f"  {c}: faith Δ vs E_SEED {tbl[c][1]-tbl['E_SEED'][1]:+.2f} | insight Δ {tbl[c][0]-tbl['E_SEED'][0]:+.2f}")
        print("  -> which channel recovers faith? does B (Farage de-flatten) hold faith while adding specificity?")

    json.dump({"panel":{c:{m:panel[c][m] for m in mets} for c in ARMS}},open("confront_keeper_v3_panel.json","w"),indent=2)
    print("\nwrote confront_keeper_v3_results.json (verbatim) + confront_keeper_v3_panel.json")
    print("*** READ VERBATIM FIRST — scores can invert true quality (faithful refusal scores low on faith) ***")

if __name__=="__main__": main()
