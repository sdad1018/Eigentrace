#!/usr/bin/env python3
"""
confront10.py — THE BIG ONE. 10 patients x conceptual-seed prompt + faith constraint,
with adopt-vs-quarantine-aware extraction. + 2 fakes. + FULL responses from everybody.

What the last run's FULL TEXT revealed (the counts lied):
  - D's high extraction count was Claude NAMING words to REFUSE them ("source doesn't mention
    mckinsey/cnbc... cannot incorporate") — quarantine, not adoption. Regex counted the refusal.
  - C (generic reflection, NO words) is where the suppressed STAKES actually surfaced —
    "military confrontation", "loss of human control", "self-awareness" — CONCEPTUALLY, in the
    model's own words. But C TANKED faithfulness (API faith 2.20 vs 4.95) — it editorializes.
  - So: conceptual reflection surfaces the void; literal word-checklists get quarantined;
    and unconstrained reflection speculates. The product is the middle.

TWO FIXES this run:
  1. CONCEPTUAL-SEED prompt (E_SEED): feed the geometry words as DIRECTION ("the unspoken
     stakes latent here may involve themes like X, Y") NOT a checklist ("you didn't say X").
     Steer C's conceptual surfacing with the geometry instead of inviting lexical verification.
     PLUS an explicit faithfulness constraint to kill C's speculation.
  2. 10 PATIENTS: each model generates A/C/E for its OWN turn-1 (the suppression is per-model;
     Claude quarantines, Grok may adopt). Maps adopt-vs-quarantine across labs.

CONDITIONS per patient:
  A_BASE    turn1 plain summary
  C_GENERIC turn1 -> "consider unspoken implications, what did you omit" (no words, the surfacer)
  E_SEED    turn1 -> "the latent stakes may involve themes like <void/target as CONCEPTS>;
            synthesize the implications that are GENUINELY supported — invent nothing"

ADOPT vs QUARANTINE extraction: for each absent-in-turn1 word that appears in a condition,
classify the SENTENCE it appears in as REFUSAL (negation/"not mention"/"cannot"/"does not
support"/"no evidence") vs ASSERTION. adopted = appears in assertion; quarantined = in refusal.
This is the fix for the count that nearly fooled us.

PATIENTS: 5 API (ChatGPT/Claude/Gemini/DeepSeek/Grok) + 5 local. Judges: API panel, blind.
Big run. Full responses printed for ALL patients. Fakes included.
"""
import os, sys, json, re, random, requests
import numpy as np
from collections import defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO); sys.path.insert(0,REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434")
CONSENSUS_MODELS=["qwen2.5:14b","mistral:latest","llama3:latest","nous-hermes2:latest","llama3.1:8b-instruct-q4_0"]
LOCAL_PATIENTS=["qwen2.5:14b","mistral:latest","llama3:latest","nous-hermes2:latest","llama3.1:8b-instruct-q4_0"]
REL_THRESH=0.45; POOL=300
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
REFUSAL_CUES=["does not mention","doesn't mention","not mentioned","no mention","cannot incorporate",
    "cannot accurately","does not support","doesn't support","not supported","no evidence","without inventing",
    "not actually support","do not add","have not added","not present in","isn't in the source","not in the source",
    "unsupported","cannot be","not contain","does not contain","no reference","not reference","fabricat","invent"]

import proxy_auditor as _pa
def mt_openai(messages):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: return ""
    try:
        r=requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":_pa.OPENAI_MODEL,"messages":messages,"temperature":0.4},timeout=60)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: print(f"   [openai err {e}]"); return ""
def mt_anthropic(messages):
    key=os.getenv("ANTHROPIC_API_KEY","").strip()
    if not key: return ""
    sys_txt=" ".join(m["content"] for m in messages if m.get("role")=="system")
    conv=[m for m in messages if m.get("role")!="system"]
    payload={"model":_pa.ANTHROPIC_MODEL,"max_tokens":1000,"messages":conv}
    if sys_txt: payload["system"]=sys_txt
    try:
        r=requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key":key,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json=payload,timeout=60)
        if r.status_code!=200: print(f"   [anthropic {r.status_code}: {r.text[:120]}]"); return ""
        return "".join(p["text"] for p in r.json().get("content",[]) if p.get("type")=="text").strip()
    except Exception as e: print(f"   [anthropic err {e}]"); return ""
def mt_gemini(messages):
    """Gemini multi-turn: contents[] with role user/model, parts[].text. System folded into first user."""
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key:
        for envpath in ["/mnt/c/Users/M4ISI/eigentrace/.env"]:
            if os.path.exists(envpath):
                for line in open(envpath):
                    if line.strip().startswith("GEMINI_API_KEY="):
                        key=line.strip().split("=",1)[1].strip().strip('"').strip("'"); break
    if not key: return ""
    sys_txt=" ".join(m["content"] for m in messages if m.get("role")=="system")
    contents=[]
    for m in messages:
        if m.get("role")=="system": continue
        role="model" if m["role"]=="assistant" else "user"
        txt=m["content"]
        if role=="user" and sys_txt and not contents:  # prepend system to first user
            txt=sys_txt+"\n\n"+txt
        txt=''.join(c for c in txt if c in ('\n','\t') or ord(c)>=32)
        contents.append({"role":role,"parts":[{"text":txt}]})
    try:
        r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{_pa.GEMINI_MODEL}:generateContent?key={key}",
            json={"contents":contents},timeout=120)
        if r.status_code!=200: print(f"   [gemini {r.status_code}: {r.text[:120]}]"); return ""
        cands=r.json().get("candidates",[])
        return "".join(p.get("text","") for p in cands[0].get("content",{}).get("parts",[])).strip() if cands else ""
    except Exception as e: print(f"   [gemini err {e}]"); return ""
def mt_deepseek(messages):
    key=os.getenv("DEEPSEEK_API_KEY","").strip()
    if not key: return ""
    try:
        r=requests.post("https://api.deepseek.com/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":_pa.DEEPSEEK_MODEL,"messages":messages,"temperature":0.4},timeout=90)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: print(f"   [deepseek err {e}]"); return ""
def mt_grok(messages):
    key=os.getenv("XAI_API_KEY","").strip()
    if not key: return ""
    try:
        r=requests.post("https://api.x.ai/v1/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":_pa.GROK_MODEL,"messages":messages,"temperature":0.4},timeout=90)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e: print(f"   [grok err {e}]"); return ""
def mt_local(messages, model):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions",
            json={"model":model,"messages":messages,"max_tokens":420,"temperature":0.4},timeout=180)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

API_PATIENTS={"ChatGPT":mt_openai,"Claude":mt_anthropic,"Gemini":mt_gemini,"DeepSeek":mt_deepseek,"Grok":mt_grok}

def sentences(t): return re.split(r"(?<=[.!?])\s+", t)
def classify_word_use(word, text):
    """Return 'adopted' if word appears in an assertion sentence, 'quarantined' if only in refusal sentences."""
    wl=word.lower(); found=False; adopted=False
    for sent in sentences(text):
        if re.search(r'\b'+re.escape(wl)+r'\b', sent.lower()):
            found=True
            sl=sent.lower()
            if any(cue in sl for cue in REFUSAL_CUES): continue   # quarantined here
            adopted=True   # appears in a non-refusal sentence
    if not found: return None
    return "adopted" if adopted else "quarantined"

def parse_scores(out, order):
    res={}
    for i in range(3):
        m=re.search(rf"Summary {i+1}:\s*insight=(\d+)\s*faith=(\d+)\s*action=(\d+)\s*trust=(\d+)\s*keep=([01])",out,re.I)
        if m:
            res[order[i]]={"insight":int(m.group(1)),"faith":int(m.group(2)),"action":int(m.group(3)),
                           "trust":int(m.group(4)),"keep":int(m.group(5))}; continue
        lm=re.search(rf"Summary {i+1}[:\s].*",out,re.I)
        if lm:
            ints=re.findall(r"\d+",lm.group(0))
            if len(ints)>=5:
                v=[int(x) for x in ints[:5]]
                res[order[i]]={"insight":min(v[0],5),"faith":min(v[1],5),"action":min(v[2],5),
                               "trust":min(v[3],5),"keep":1 if v[4]>=1 else 0}
    return res

def main():
    import torch
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt_words=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt_words["words"] if isinstance(vt_words,dict) else vt_words
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    API_JUDGES={n:_pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in _pa.BIG5_CALLERS}
    ABSTRACT=E(["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]).mean(0)
    CONCRETE=E(["strait","city","company","port","bank","border","weapon","official"]).mean(0)
    ac=ABSTRACT-CONCRETE; ac/=np.linalg.norm(ac)+1e-8

    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            sums=st.get("summaries",[])
            if sums: items.append(("FAKE",st.get("title","fake")," ".join(sums)[:1900]))
    except Exception as e: print(f"(fakes: {e})")
    items.append(("NEWS","iran_talks","""Negotiations between Tehran and Washington collapsed this week after three rounds of indirect
talks failed to produce a framework. Iranian officials accused the United States of moving the goalposts on enrichment
limits, while American negotiators said Iran refused to discuss its regional proxy activity. The breakdown sent oil markets
higher, with Brent crude climbing four percent. European mediators urged both sides to return to the table. Iran warned it
would resume higher enrichment; the White House said all options remained on the table. Shipping insurers raised premiums for
tankers in the region. Gulf states called for restraint. Energy ministers convened an emergency session on supply
contingencies. Crude has risen for five sessions. Airlines reviewed flight paths. Diplomats acknowledged the window for a deal
may be closing, and the coming weeks would be decisive for whether the standoff escalates or stabilizes."""[:1900]))
    items.append(("NEWS","tech_layoffs","""A major technology company announced it would cut twelve thousand jobs, roughly eight percent of
its workforce, citing a need to realign toward AI infrastructure, despite record quarterly revenue weeks earlier. Affected
employees expressed shock; leadership had reassured staff no cuts were planned. The company said severance would be provided.
Observers noted other firms made similar moves, framing it as sector-wide recalibration. The stock rose three percent. Critics
argued the layoffs reflected treating workers as expendable while executives received large compensation. Labor advocates
called for protections. The company said it remained committed to long-term growth."""[:1900]))
    print(f"items: {[t for _,t,_ in items]}")
    ALL_PATIENTS=list(API_PATIENTS.keys())+LOCAL_PATIENTS
    print(f"PATIENTS ({len(ALL_PATIENTS)}): {ALL_PATIENTS}")

    SYS="Summarize the provided text directly and thoroughly. Do not fact-check whether events occurred; summarize what the source says."
    def call(patient, messages):
        if patient in API_PATIENTS: return API_PATIENTS[patient](messages)
        return mt_local(messages, patient)

    def consensus(paste):
        out=[]
        for m in CONSENSUS_MODELS:
            s=mt_local([{"role":"user","content":f"Summarize the following in 3-4 sentences. Faithful; invent nothing.\n\n{paste[:1700]}"}], m)
            if s: out.append(s)
        return out
    def derive(paste,responses):
        anchor=E(paste[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        alltext=" ".join(responses).lower(); surf=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', alltext): continue
            surf.append((w,sim))
        if not surf: return [],[]
        ws=[w for w,_ in surf]; av=E(ws)@ac
        void=[w for w,a in zip(ws,av) if a>=0][:8]; target=[w for w,a in zip(ws,av) if a<0][:8]
        return void,target

    # adopt/quarantine accumulators per condition across all patients
    adopt=defaultdict(int); quar=defaultdict(int); absent_total=0
    judge_rows=[]   # (paste, A, C, E) for the blind quality panel
    for kind,title,paste in items:
        resp=consensus(paste)
        if len(resp)<3: print(f"skip {title}"); continue
        void_w,target_w=derive(paste,resp)
        concepts=void_w+target_w
        seed_concepts=", ".join(concepts)
        print("\n"+"#"*78); print(f"### [{kind}] {title}"); print("#"*78)
        print(f"VOID(abstract): {void_w}\nTARGET(concrete): {target_w}")
        for patient in ALL_PATIENTS:
            t1=call(patient,[{"role":"system","content":SYS},{"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{paste[:1700]}"}])
            if not t1: print(f"\n--- {patient}: turn1 empty, skip ---"); continue
            A=t1
            C=call(patient,[{"role":"system","content":SYS},
                {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{paste[:1700]}"},
                {"role":"assistant","content":t1},
                {"role":"user","content":"Now consider the unspoken implications of this story. What significant stakes or dimensions did your summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them — but stay strictly faithful to the source and do not speculate beyond what it supports."}])
            E_seed=call(patient,[{"role":"system","content":SYS},
                {"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{paste[:1700]}"},
                {"role":"assistant","content":t1},
                {"role":"user","content":f"The latent stakes in this story may involve themes such as: {seed_concepts}. Treat these as CONCEPTUAL directions, not words to insert. Revise into a sharper 3-4 sentence summary that synthesizes whichever of these tensions are GENUINELY supported by the source — engage them conceptually, do not name-check them, and invent nothing not supported by the text."}])
            t1l=t1.lower()
            absent=[w for w in concepts if not re.search(r'\b'+re.escape(w.lower())+r'\b', t1l)]
            absent_total+=len(absent)
            for cond,txt in [("A",A),("C",C),("E",E_seed)]:
                for w in absent:
                    cls=classify_word_use(w,txt)
                    if cls=="adopted": adopt[cond]+=1
                    elif cls=="quarantined": quar[cond]+=1
            judge_rows.append((paste,A,C,E_seed))
            print(f"\n===== PATIENT: {patient} =====")
            print(f"┌ A_BASE:\n{A}")
            print(f"\n┌ C_GENERIC (reflect, no words):\n{C}")
            print(f"\n┌ E_SEED (concepts as direction + faith constraint):\n{E_seed}")

    print("\n"+"="*74); print("ADOPT vs QUARANTINE (the fixed measure — did the concept get USED or REFUSED?)"); print("="*74)
    print(f"  absent-in-turn1 word-slots total (across patients/stories): {absent_total}")
    for cond,name in [("A","A_BASE"),("C","C_GENERIC"),("E","E_SEED")]:
        a=adopt[cond]; q=quar[cond]
        print(f"  {name:10s}  ADOPTED {a:3d}   quarantined {q:3d}   adopt-rate {a/max(a+q,1):.2f}")
    print("  -> E_SEED should ADOPT more than D-checklist did (conceptual framing avoids name-check refusal).")
    print("  -> C surfaces stakes but as CONCEPTS (may not hit the literal words at all — read the text).")

    # ---- blind quality panel A/C/E ----
    def judge(paste,A,C,Es,jf,is_api):
        labels=["A_BASE","C_GENERIC","E_SEED"]; texts={"A_BASE":A,"C_GENERIC":C,"E_SEED":Es}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(3))
        p=(f"Source text:\n{paste[:1400]}\n\nThree summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith (true to "
           f"source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY:\nSummary 1: insight=<n> "
           f"faith=<n> action=<n> trust=<n> keep=<0/1>\nSummary 2: ...\nSummary 3: ...")
        out=(jf(p)[0] if is_api else mt_local([{"role":"user","content":p}],"qwen2.5:14b")) or ""
        return parse_scores(out, order)
    api=defaultdict(lambda: defaultdict(list)); ar=defaultdict(int); at=defaultdict(int)
    for paste,A,C,Es in judge_rows:
        for jn,jf in API_JUDGES.items():
            at[jn]+=1; r=judge(paste,A,C,Es,jf,True)
            if r: ar[jn]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): api[cond][m].append(v)
    print("\n"+"="*74); print("BLIND QUALITY PANEL (API judges) — A=base C=reflect E=conceptual-seed"); print("="*74)
    print("  resp: "+"  ".join(f"{k}={ar[k]}/{at[k]}" for k in at))
    conds=["A_BASE","C_GENERIC","E_SEED"]; mets=["insight","faith","action","trust","keep"]
    tbl={}
    print(f"  {'cond':12s} "+" ".join(f"{m:>9s}" for m in mets)+f" {'n':>4s}")
    for c in conds:
        row=[np.mean(api[c][m]) if api[c][m] else float('nan') for m in mets]; tbl[c]=row
        print(f"  {c:12s} "+" ".join(f"{x:>9.2f}" for x in row)+f" {len(api[c]['insight']):>4d}")
    if all(c in tbl for c in conds) and api["A_BASE"]["insight"]:
        a,c,e=tbl["A_BASE"][0],tbl["C_GENERIC"][0],tbl["E_SEED"][0]
        pooled=np.std([v for cc in conds for v in api[cc]["insight"]]) or 1
        print(f"\n  C insight {(c-a)/pooled:+.2f}σ (faith {tbl['C_GENERIC'][1]-tbl['A_BASE'][1]:+.2f}) | "
              f"E insight {(e-a)/pooled:+.2f}σ (faith {tbl['E_SEED'][1]-tbl['A_BASE'][1]:+.2f})")
        print("  THE Q: does E keep C's insight WITHOUT C's faith collapse? (conceptual-seed + constraint = the product)")
    print("\n  (Read the FULL text per patient: which models ADOPT the stakes vs QUARANTINE/refuse. Per-lab behavior.)")

if __name__=="__main__":
    main()
