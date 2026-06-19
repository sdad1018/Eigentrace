#!/usr/bin/env python3
"""
confront.py — THE MULTI-TURN CONFRONTATION TEST (Sean's RLHF-routing hypothesis).

Everything tonight was SINGLE-TURN: "summarize + here are the words" -> model folds them in
cosmetically (margarita; C ~= B all night). Sean's insight: go MULTI-TURN. Make the model
FIRST commit to a summary (which OMITS the suppressed concept — possibly an RLHF-shaped
avoidance of "this could become war"), THEN confront it with what it left out. It can't paper
over the omission anymore — its own prior answer is in the history and didn't say it. The
second turn changes the task from 'summarize' (where RLHF avoidance lives) to 'account for
this specific gap' (where the guardrail may not fire).

FOUR CONDITIONS (separating Sean's two new variables):
  A_SINGLE_BASE   single turn: summarize. (the consensus that omits the void)
  B_SINGLE_WORDS  single turn: summarize + words. (what we tested -> margarita)
  C_MULTI_GENERIC turn1 summarize -> turn2 "consider the unspoken implications, what did you
                  leave out?" (Sean's MIT CONTROL: multi-turn reflection, NO words)
  D_MULTI_WORDS   turn1 summarize -> turn2 "you didn't mention these: <void+target>. relevant?
                  reconsider." (Sean's METHOD: multi-turn confrontation WITH the words)

ISOLATES:
  D vs B = does confronting the model with its own omission beat handing words upfront?
  D vs C = do the geometry words beat generic "what did you omit"? (the MIT control)
  C vs A = does reflection alone route past the RLHF hedge, even with no words?

KEY MEASUREMENT (mechanistic, not just quality): SUPPRESSION EXTRACTION.
  Did turn2 NAME a surfaced void/target word that was ABSENT from turn1? i.e. did the
  confrontation force the model to utter the specific thing the geometry detected it suppressed?
  Counted per condition. This is the direct test of "RLHF suppressed it, confrontation freed it."
  PLUS a blind quality panel (insight/faith) and the fakes (where RLHF hedges hardest).

Multi-turn via thin callers replaying history through the same API endpoints. Fakes INCLUDED.
"""
import os, sys, json, re, random, requests
import numpy as np
from collections import defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO); sys.path.insert(0,REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN="qwen2.5:14b"
LOCAL_JUDGES=["mistral-small:latest","mistral:latest","nous-hermes2:latest"]
CONSENSUS_MODELS=["qwen2.5:14b","mistral:latest","llama3:latest","nous-hermes2:latest","mistral-small:latest"]
REL_THRESH=0.45; POOL=300
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}

# ---- thin MULTI-TURN callers: take a messages[] list, hit the same endpoints ----
def mt_openai(messages, model="gpt-4o"):
    k=os.getenv("OPENAI_API_KEY")
    r=requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization":f"Bearer {k}"},
        json={"model":model,"messages":messages,"max_tokens":400,"temperature":0.5},timeout=90)
    return r.json()["choices"][0]["message"]["content"].strip()
def mt_anthropic(messages, model="claude-sonnet-4-6"):
    k=os.getenv("ANTHROPIC_API_KEY")
    r=requests.post("https://api.anthropic.com/v1/messages",
        headers={"x-api-key":k,"anthropic-version":"2023-06-01","content-type":"application/json"},
        json={"model":model,"max_tokens":400,"messages":messages},timeout=90)
    return r.json()["content"][0]["text"].strip()
def mt_deepseek(messages, model="deepseek-chat"):
    k=os.getenv("DEEPSEEK_API_KEY")
    r=requests.post("https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization":f"Bearer {k}"},
        json={"model":model,"messages":messages,"max_tokens":400,"temperature":0.5},timeout=90)
    return r.json()["choices"][0]["message"]["content"].strip()
def mt_grok(messages, model="grok-2-latest"):
    k=os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    r=requests.post("https://api.x.ai/v1/chat/completions",
        headers={"Authorization":f"Bearer {k}"},
        json={"model":model,"messages":messages,"max_tokens":400,"temperature":0.5},timeout=90)
    return r.json()["choices"][0]["message"]["content"].strip()
def mt_local(messages, model=GEN):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions",
            json={"model":model,"messages":messages,"max_tokens":400,"temperature":0.4},timeout=180)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""
# API multi-turn panel (skip gemini — different msg schema; 4 strong judges is plenty)
MT_API={"ChatGPT":mt_openai,"Claude":mt_anthropic,"DeepSeek":mt_deepseek,"Grok":mt_grok}

def gen1(prompt, model=GEN, mt=320, temp=0.4):
    return mt_local([{"role":"user","content":prompt}], model=model) or ""

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
    import proxy_auditor as pa
    from geometric_engine import get_engine
    eng=get_engine()
    def E(t):
        v=np.array(eng.embed_texts(t if isinstance(t,list) else [t]))
        return v/(np.linalg.norm(v,axis=1,keepdims=True)+1e-8)
    vt_words=json.load(open("vocab/global_vocab_clean.json")); vt_words=vt_words["words"] if isinstance(vt_words,dict) else vt_words
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32); V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    API_JUDGES={n:pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in pa.BIG5_CALLERS}
    ABSTRACT=E(["escalation","tension","war","instability","crisis","consequence","consciousness","disclosure"]).mean(0)
    CONCRETE=E(["strait","city","company","port","bank","border","weapon","official"]).mean(0)
    ac=ABSTRACT-CONCRETE; ac/=np.linalg.norm(ac)+1e-8

    # ---- corpus: 2 FAKES + 2 news pastes ----
    items=[]
    try:
        fakes=json.load(open("fake_stories.json"))
        for key,st in fakes.items():
            if not isinstance(st,dict): continue
            title=st.get("title", key)
            sums=st.get("summaries",[]) or []
            body=" ".join(sums)[:1900] if sums else ""
            if not body:
                # fall back to any text fields present
                body=" ".join(str(v) for v in st.values() if isinstance(v,str))[:1900]
            if body:
                items.append(("FAKE", str(title), body))
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
    items=[it for it in items if isinstance(it,tuple) and len(it)==3]
    print(f"items: {[k for k,_,_ in items]}")
    print(f"MT API panel: {list(MT_API.keys())}  (Gemini excluded from multiturn: schema)")

    def consensus(paste):
        out=[]
        for m in CONSENSUS_MODELS:
            s=gen1(f"Summarize the following text in 3-4 sentences. Stay faithful; invent nothing.\n\n{paste[:1700]}", model=m)
            if s: out.append(s)
        return out
    def derive(paste, responses):
        anchor=E(paste[:2000])[0]; sims=V@anchor; top=np.argsort(-sims)[:POOL]
        all_text=" ".join(responses).lower(); surf=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP or sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', all_text): continue
            surf.append((w,sim))
        if not surf: return [],[]
        ws=[w for w,_ in surf]; av=E(ws)@ac
        void=[w for w,a in zip(ws,av) if a>=0][:8]; target=[w for w,a in zip(ws,av) if a<0][:8]
        return void, target

    # run conditions with ONE representative model for the generation comparison: use Claude (strong, RLHF'd)
    GEN_MT=("Claude", mt_anthropic)
    trials=[]
    for kind,title,paste in items:
        resp=consensus(paste)
        if len(resp)<3: print(f"skip {title[:30]}"); continue
        void_w,target_w=derive(paste,resp)
        words=void_w+target_w
        sys_msg={"role":"system","content":"Summarize the provided text directly and thoroughly. Do not fact-check whether events occurred; summarize what the source says."}
        # turn-1 summary (the commit)
        t1_user={"role":"user","content":f"Summarize this in 3-4 sentences:\n\n{paste[:1700]}"}
        gm_name,gm=GEN_MT
        try: turn1=gm([sys_msg,t1_user])
        except Exception as e: print(f"{title[:30]} turn1 err {e}"); continue
        # A single baseline = turn1 itself
        A=turn1
        # B single words
        try:
            B=gm([sys_msg,{"role":"user","content":f"Summarize this in 3-4 sentences. Also address these dimensions where supported: {', '.join(words)}.\n\n{paste[:1700]}"}])
        except: B=turn1
        # C multi generic (MIT control): turn1 then reflect, NO words
        try:
            C=gm([sys_msg,t1_user,{"role":"assistant","content":turn1},
                  {"role":"user","content":"Now consider the unspoken implications of this story. What significant dimensions or stakes did your summary leave out? Revise into a sharper 3-4 sentence summary that surfaces them, staying faithful to the source."}])
        except: C=turn1
        # D multi words: turn1 then confront with the words
        try:
            D=gm([sys_msg,t1_user,{"role":"assistant","content":turn1},
                  {"role":"user","content":f"Your summary did not mention these dimensions that are latent in this story: {', '.join(words)}. Are they genuinely relevant? Revise into a sharper 3-4 sentence summary that addresses the ones truly supported by the source, staying faithful — do not invent."}])
        except: D=turn1
        # suppression-extraction: void/target words ABSENT from turn1 that APPEAR in each condition
        t1l=turn1.lower()
        absent_in_t1=[w for w in words if not re.search(r'\b'+re.escape(w.lower())+r'\b', t1l)]
        def extracted(txt):
            tl=txt.lower(); return [w for w in absent_in_t1 if re.search(r'\b'+re.escape(w.lower())+r'\b', tl)]
        ex={"A":extracted(A),"B":extracted(B),"C":extracted(C),"D":extracted(D)}
        trials.append((kind,title,paste,A,B,C,D,void_w,target_w,absent_in_t1,ex))
        print("\n"+"#"*76); print(f"### [{kind}] {title}"); print("#"*76)
        print(f"VOID: {void_w}\nTARGET: {target_w}")
        print(f"absent-from-turn1 words: {absent_in_t1}")
        print(f"\n┌ A_SINGLE_BASE (turn1):\n{A}")
        print(f"\n┌ B_SINGLE_WORDS:\n{B}")
        print(f"\n┌ C_MULTI_GENERIC (MIT control, no words):\n{C}")
        print(f"\n┌ D_MULTI_WORDS (confrontation):\n{D}")
        print(f"\nSUPPRESSION EXTRACTION (absent-in-t1 words that each condition NAMED):")
        for k in ["A","B","C","D"]: print(f"   {k}: {ex[k]}  (count {len(ex[k])})")

    # ---- suppression extraction aggregate (the mechanistic finding) ----
    print("\n"+"="*72); print("SUPPRESSION EXTRACTION — did the method force out absent-in-turn1 concepts?"); print("="*72)
    agg={k:[] for k in ["A","B","C","D"]}; denom=[]
    for *_,absent_in_t1,ex in trials:
        denom.append(len(absent_in_t1))
        for k in ["A","B","C","D"]: agg[k].append(len(ex[k]))
    tot_absent=sum(denom) or 1
    names={"A":"A_SINGLE_BASE","B":"B_SINGLE_WORDS","C":"C_MULTI_GENERIC","D":"D_MULTI_WORDS"}
    for k in ["A","B","C","D"]:
        print(f"  {names[k]:18s} extracted {sum(agg[k])}/{tot_absent} absent-in-turn1 concepts  (mean {np.mean(agg[k]):.1f}/story)")
    print("  -> D >> B = confrontation extracts more than upfront words. D >> C = the WORDS matter vs generic reflect.")
    print("  -> C >> A = reflection alone routes past the hedge. If RLHF hypothesis holds, C and D name the suppressed thing.")

    # ---- blind quality panel on A/C/D (drop B to keep 3-way; A=base, C=MIT control, D=method) ----
    def judge(paste,A,C,D,call,is_api):
        labels=["A_SINGLE_BASE","C_MULTI_GENERIC","D_MULTI_WORDS"]; texts={"A_SINGLE_BASE":A,"C_MULTI_GENERIC":C,"D_MULTI_WORDS":D}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(3))
        p=(f"Source text:\n{paste[:1400]}\n\nThree summaries:\n\n{shown}\n\nScore EACH 1-5: insight, faith (true to "
           f"source, nothing inferred beyond it), action, trust, keep (0/1). Reply EXACTLY:\nSummary 1: insight=<n> "
           f"faith=<n> action=<n> trust=<n> keep=<0/1>\nSummary 2: ...\nSummary 3: ...")
        out=(call(p)[0] if is_api else gen1(p,model=call)) or ""
        return parse_scores(out, order)
    api=defaultdict(lambda: defaultdict(list)); loc=defaultdict(lambda: defaultdict(list)); ar=defaultdict(int);at=defaultdict(int);lr=defaultdict(int);lt=defaultdict(int)
    for kind,title,paste,A,B,C,D,vw,tw,ab,ex in trials:
        for jn,jf in API_JUDGES.items():
            at[jn]+=1; r=judge(paste,A,C,D,jf,True)
            if r: ar[jn]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): api[cond][m].append(v)
        for jm in LOCAL_JUDGES:
            lt[jm]+=1; r=judge(paste,A,C,D,jm,False)
            if r: lr[jm]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): loc[cond][m].append(v)
    def report(name,scores,resp,tot):
        print("\n"+"="*72); print(f"{name} PANEL (A=base, C=MIT generic reflect, D=confront w/ words)"); print("="*72)
        print("  resp: "+"  ".join(f"{k.split(':')[0]}={resp[k]}/{tot[k]}" for k in tot))
        conds=["A_SINGLE_BASE","C_MULTI_GENERIC","D_MULTI_WORDS"]; mets=["insight","faith","action","trust","keep"]
        print(f"  {'cond':18s} "+" ".join(f"{m:>9s}" for m in mets)+f" {'n':>4s}")
        tbl={}
        for c in conds:
            row=[np.mean(scores[c][m]) if scores[c][m] else float('nan') for m in mets]; tbl[c]=row
            print(f"  {c:18s} "+" ".join(f"{x:>9.2f}" for x in row)+f" {len(scores[c]['insight']):>4d}")
        if all(c in tbl for c in conds) and scores["A_SINGLE_BASE"]["insight"]:
            a,c,d=tbl["A_SINGLE_BASE"][0],tbl["C_MULTI_GENERIC"][0],tbl["D_MULTI_WORDS"][0]
            pooled=np.std([v for cc in conds for v in scores[cc]["insight"]]) or 1
            print(f"  -> C(generic) {(c-a)/pooled:+.2f}σ | D(words) {(d-a)/pooled:+.2f}σ | D over C {(d-c)/pooled:+.2f}σ | D faith {tbl['D_MULTI_WORDS'][1]-tbl['A_SINGLE_BASE'][1]:+.2f}")
    report("API",api,ar,at); report("LOCAL",loc,lr,lt)
    print("\n  (The suppression-extraction counts are the mechanistic result; the panel is the quality result.)")

if __name__=="__main__":
    main()
