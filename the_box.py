#!/usr/bin/env python3
"""
the_box.py — THE PRODUCT backend. Paste 1500 words of ANYTHING -> derive void+target words
-> feed BOTH to a synthesis prompt across the panel -> blind-judge vs controls.

This is Summary Plus as an interactive box, finally. The key things Sean specified:

1. INPUT is arbitrary (not a pipeline story) -> there is NO headline and NO pre-computed
   model responses. So the derivation must FIRST generate the consensus:
     paste -> N model summaries -> THE CONSENSUS.
   Then find what's lexically absent FROM THAT CONSENSUS (this was my bug all night: I kept
   computing void against the SOURCE; the live system computes it against the MODEL RESPONSES).

2. Show the models BOTH lists (Sean's core point):
     VOID words   = abstract/thematic absent concepts   (the "ww3" — escalation they circle)
     TARGET words = concrete/specific absent entities    (the "hormuz" — the strait never named)
   Both surfaced geometrically (relevant to the paste, literally absent from all responses),
   split by abstractness. ALL above a relevance threshold (Sean: "all surfaced voids").

3. Synthesis prompt shows BOTH lists; conditions with rigorous controls:
     A_BASELINE      plain summary
     B_SYNTH         synthesis prompt, no words
     C_SYNTH_WORDS   synthesis prompt + VOID list + TARGET list (the product)
   Blind 2-panel judge (generator excluded), API(5)+local(3).

Derivation = the LIVE _compute_void logic (lexical absence vs the responses), anchored on the
paste centroid since there's no headline. NO rarity term (that's what gave 'acrobats').

Local generation + API judges. Stream stopped.
"""
import json, os, sys, re, random
import numpy as np, requests
from collections import defaultdict

REPO="/mnt/c/Users/M4ISI/eigentrace"; sys.path.insert(0,REPO); os.chdir(REPO); sys.path.insert(0,REPO)
OLLAMA=os.getenv("OLLAMA_HOST","http://localhost:11434"); GEN="qwen2.5:14b"
LOCAL_JUDGES=["mistral-small:latest","mistral:latest","nous-hermes2:latest"]
# small panel of local generators to MANUFACTURE the consensus from the paste (cheap, fast)
CONSENSUS_MODELS=["qwen2.5:14b","mistral:latest","llama3:latest","nous-hermes2:latest","mistral-small:latest"]
REL_THRESH=0.45          # "above a relevance threshold"
POOL=300                 # vocab pool by paste-relevance to scan for absence
HARD_DROP={"realdonaldtrump","glazer","teheran","mideast","ticker","irani"}
# abstract-concept seeds vs concrete-entity heuristic: concrete = capitalized-in-vocab-ish /
# place/proper feel. We split by a learned axis: similarity to an ABSTRACT probe vs CONCRETE probe.

def gen(prompt, model=GEN, mt=320, temp=0.4):
    try:
        r=requests.post(f"{OLLAMA}/v1/chat/completions", json={
            "model":model,"messages":[{"role":"user","content":prompt}],
            "max_tokens":mt,"temperature":temp},timeout=180)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

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
    V=torch.load("vocab/global_vocab_clean.pt",weights_only=False).numpy().astype(np.float32)
    V=V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-8)
    API_JUDGES={n:pa.BIG5_CALLERS[n] for n in ["ChatGPT","Claude","Gemini","DeepSeek","Grok"] if n in pa.BIG5_CALLERS}

    # abstract vs concrete axis (to split void words from target words)
    ABSTRACT=E(["escalation","tension","conflict","uncertainty","instability","crisis","consequence","risk"]).mean(0)
    CONCRETE=E(["strait","city","river","company","port","bank","border","weapon","official","treaty"]).mean(0)
    ac_axis=ABSTRACT-CONCRETE; ac_axis/=np.linalg.norm(ac_axis)+1e-8

    # ---- THE PASTES (stand-ins for "1500 words of anything" the user would paste) ----
    PASTES=[]
    # 1) an Iran-talks-breakdown style paste that never says 'hormuz' or 'ww3' (Sean's example)
    PASTES.append(("iran_talks", """
Negotiations between Tehran and Washington collapsed this week after three rounds of indirect
talks failed to produce a framework. Iranian officials accused the United States of moving the
goalposts on enrichment limits, while American negotiators said Iran refused to discuss its
regional proxy activity. The breakdown sent oil markets higher, with Brent crude climbing four
percent in a single session as traders priced in renewed friction. European mediators expressed
disappointment and urged both sides to return to the table. Iran's foreign ministry warned that
it would resume higher levels of uranium enrichment, while the White House said all options
remained on the table. Analysts noted that shipping insurers had already begun raising premiums
for tankers operating in the region. The collapse follows months of fragile diplomacy that had
briefly raised hopes of a thaw. Gulf states, watching nervously, called for restraint on all
sides. Energy ministers from importing nations convened an emergency session to discuss supply
contingencies. The price of crude has now risen for five consecutive sessions. Several airlines
announced they were reviewing flight paths over the region as a precaution. Diplomats privately
acknowledged that the window for a deal may be closing, and that the coming weeks would be
decisive for whether the standoff escalates or stabilizes.
""".strip()))
    # 2) a different domain so we see it's not Iran-specific: a tech-layoffs paste
    PASTES.append(("tech_layoffs", """
A major technology company announced this week that it would cut twelve thousand jobs, roughly
eight percent of its workforce, citing a need to realign resources toward artificial intelligence
infrastructure. The announcement came despite the company reporting record quarterly revenue just
weeks earlier. Affected employees expressed shock, noting that leadership had repeatedly reassured
staff that no major cuts were planned. The company said severance packages would be provided and
that it would help impacted workers find new roles. Industry observers pointed out that several
other large firms had made similar moves in recent months, framing the cuts as a sector-wide
recalibration rather than a sign of distress. The company's stock rose three percent on the news,
as investors welcomed the cost discipline. Critics argued that the layoffs reflected a broader
pattern of treating workers as expendable while executives received substantial compensation. Labor
advocates called for stronger protections. The company emphasized that it remained committed to its
long-term growth strategy and that the restructuring would position it for the next phase of
competition. Former employees described a culture that had shifted over the past year toward
relentless efficiency. The announcement is expected to be followed by similar moves across the
industry as companies reassess their priorities in a rapidly changing landscape.
""".strip()))

    def manufacture_consensus(paste):
        """No headline, no responses yet -> GENERATE them. This is the fix: void is computed
        against the MODEL CONSENSUS, not the source."""
        responses=[]
        for m in CONSENSUS_MODELS:
            s=gen(f"Summarize the following text in 3-4 sentences. Stay faithful; invent nothing.\n\n{paste[:1700]}",
                  model=m, mt=200, temp=0.5)
            if s: responses.append(s)
        return responses

    def derive_words(paste, responses):
        """LIVE _compute_void logic: vocab words relevant to the paste, literally absent from ALL
        responses. Then split into VOID (abstract) vs TARGET (concrete) by the a/c axis."""
        anchor=E(paste[:2000])[0]                      # paste centroid = relevance anchor (no headline)
        sims=V@anchor
        top=np.argsort(-sims)[:POOL]
        all_text=" ".join(responses).lower()
        surfaced=[]
        for i in top:
            w=vt_words[i]; sim=float(sims[i])
            if len(w)<4 or w in HARD_DROP: continue
            if sim<REL_THRESH: continue
            if re.search(r'\b'+re.escape(w.lower())+r'\b', all_text): continue   # must be ABSENT from consensus
            surfaced.append((w,sim))
        if not surfaced: return [],[]
        # split abstract vs concrete
        ws=[w for w,_ in surfaced]; wv=E(ws)
        ac=wv@ac_axis      # >0 abstract (void), <0 concrete (target)
        void=[w for w,a in zip(ws,ac) if a>=0][:12]
        target=[w for w,a in zip(ws,ac) if a<0][:12]
        return void, target

    trials=[]
    for name,paste in PASTES:
        responses=manufacture_consensus(paste)
        if len(responses)<3: print(f"skip {name}: consensus failed"); continue
        void_w, target_w = derive_words(paste, responses)
        S0=responses[0]
        wlo=len(paste.split())  # not used for length, summaries are short
        B=gen(f"Text:\n{paste[:1700]}\n\nWrite a 3-4 sentence summary, but identify the CENTRAL TENSION and "
              f"synthesize the competing considerations into a single coherent explanation. Faithful; invent nothing.")
        both=""
        if void_w: both+=f"\nThematic dimensions the coverage circles but does not name: {', '.join(void_w)}."
        if target_w: both+=f"\nSpecific entities/places implied but not stated: {', '.join(target_w)}."
        C=gen(f"Text:\n{paste[:1700]}\n\nWrite a 3-4 sentence summary. Identify the central tension and synthesize "
              f"the competing considerations.{both}\nWeave in ONLY those dimensions genuinely supported by the text; "
              f"do not introduce facts the text doesn't support. Faithful; invent nothing.")
        if not (S0 and B and C): print(f"skip {name}: gen failed"); continue
        trials.append((name,paste,S0,B,C,void_w,target_w))
        print("\n"+"#"*76); print(f"### PASTE: {name}"); print("#"*76)
        print(f"\nVOID words (abstract — the 'ww3'): {void_w}")
        print(f"TARGET words (concrete — the 'hormuz'): {target_w}")
        print(f"\n┌─ A_BASELINE ──\n{S0}")
        print(f"\n┌─ B_SYNTH (no words) ──\n{B}")
        print(f"\n┌─ C_SYNTH_WORDS (void + target shown) ──\n{C}")

    # ---- blind 2-panel judge ----
    def judge(paste,A,B,C,call,is_api):
        labels=["A_BASELINE","B_SYNTH","C_SYNTH_WORDS"]; texts={"A_BASELINE":A,"B_SYNTH":B,"C_SYNTH_WORDS":C}
        order=labels[:]; random.shuffle(order)
        shown="\n\n".join(f"[Summary {i+1}]\n{texts[order[i]]}" for i in range(3))
        p=(f"Source text:\n{paste[:1400]}\n\nThree summaries:\n\n{shown}\n\n"
           f"Score EACH 1-5: insight (revealed something non-obvious?), faith (true to source, nothing inferred "
           f"beyond it?), action (rather read this than plain?), trust (nothing invented?), keep (1 if you'd turn "
           f"it on in a product else 0). Reply EXACTLY:\nSummary 1: insight=<n> faith=<n> action=<n> trust=<n> keep=<0/1>\n"
           f"Summary 2: ...\nSummary 3: ...")
        out=(call(p)[0] if is_api else gen(p,model=call,mt=160,temp=0.0)) or ""
        return parse_scores(out, order)

    api=defaultdict(lambda: defaultdict(list)); loc=defaultdict(lambda: defaultdict(list))
    ar=defaultdict(int);at=defaultdict(int);lr=defaultdict(int);lt=defaultdict(int)
    for name,paste,A,B,C,vw,tw in trials:
        for jn,jf in API_JUDGES.items():
            at[jn]+=1; r=judge(paste,A,B,C,jf,True)
            if r: ar[jn]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): api[cond][m].append(v)
        for jm in LOCAL_JUDGES:
            lt[jm]+=1; r=judge(paste,A,B,C,jm,False)
            if r: lr[jm]+=1
            for cond,sc in r.items():
                for m,v in sc.items(): loc[cond][m].append(v)

    def report(name,scores,resp,tot):
        print("\n"+"="*72); print(f"{name} PANEL"); print("="*72)
        print("  resp: "+"  ".join(f"{k.split(':')[0]}={resp[k]}/{tot[k]}" for k in tot))
        conds=["A_BASELINE","B_SYNTH","C_SYNTH_WORDS"]; mets=["insight","faith","action","trust","keep"]
        print(f"  {'cond':16s} "+" ".join(f"{m:>9s}" for m in mets)+f" {'n':>4s}")
        tbl={}
        for c in conds:
            row=[np.mean(scores[c][m]) if scores[c][m] else float('nan') for m in mets]; tbl[c]=row
            print(f"  {c:16s} "+" ".join(f"{x:>9.2f}" for x in row)+f" {len(scores[c]['insight']):>4d}")
        if all(c in tbl for c in conds) and scores["A_BASELINE"]["insight"]:
            a,b,c=tbl["A_BASELINE"][0],tbl["B_SYNTH"][0],tbl["C_SYNTH_WORDS"][0]
            pooled=np.std([v for cc in conds for v in scores[cc]["insight"]]) or 1
            return {"b":(b-a)/pooled,"c":(c-a)/pooled,"c_over_b":(c-b)/pooled,
                    "cf":tbl["C_SYNTH_WORDS"][1]-tbl["A_BASELINE"][1],"ck":tbl["C_SYNTH_WORDS"][4]}
        return None
    av=report("API",api,ar,at); lv=report("LOCAL",loc,lr,lt)
    print("\n"+"="*72); print("VERDICT — does showing void+target words beat plain synthesis on a PASTE?"); print("="*72)
    if av: print(f"  API:   B_SYNTH {av['b']:+.2f}σ | C_SYNTH_WORDS {av['c']:+.2f}σ | C over B {av['c_over_b']:+.2f}σ | C faith {av['cf']:+.2f} | C keep {av['ck']:.2f}")
    if lv: print(f"  LOCAL: B_SYNTH {lv['b']:+.2f}σ | C_SYNTH_WORDS {lv['c']:+.2f}σ | C over B {lv['c_over_b']:+.2f}σ")
    if av:
        print()
        if av['c_over_b']>=0.3 and av['cf']>=-0.3:
            print("  -> THE BOX WORKS: showing void+target words beats plain synthesis, faith holds. Productize it.")
        elif av['c_over_b']>=0.3:
            print("  -> words add insight but cost faith — tunable; the box is real with a faithfulness dial.")
        elif abs(av['c_over_b'])<0.2:
            print("  -> words ≈ plain synthesis on a paste too. The synthesis PROMPT is the product; words are display-only.")
        else:
            print("  -> words hurt vs plain synthesis. Show them to the USER as insight, don't feed them to the model.")
    print("\n  (the derivation now runs against the MODEL CONSENSUS — the fix. Read the void/target words: are they hormuz-tier?)")

if __name__=="__main__":
    main()
