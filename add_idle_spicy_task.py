#!/usr/bin/env python3
"""
add_idle_spicy_task.py — adds task_spicy_comparison to idle_agent.py and registers
it in TASK_POOL. Exact-match safe; all-or-nothing.

The task: during idle time, retrieve two CONCRETE spicy summaries (from real story
segments on disk), hand Mistral those two specific texts, ask how their framing
differed. Graceful-empty (returns [] if no spicy beats exist yet). Hardcoded
fallback if Mistral returns junk. Anti-loop: always two named concrete inputs,
never abstract 'find patterns'.
"""
import sys, shutil, os

IA = "idle_agent.py"

# anchor: insert the new task function right before the TASK_POOL definition
POOL_ANCHOR = "TASK_POOL = ["

NEW_TASK = '''def task_spicy_comparison() -> list[dict]:
    """Compare two Summary Plus 'spicy' re-summaries from recent story segments."""
    try:
        import glob as _glob, json as _json, random as _rnd
        seg_dir = "/home/remvelchio/eigentrace/tmp/segments"
        files = sorted(_glob.glob(seg_dir + "/*_segment.json"),
                       key=os.path.getmtime, reverse=True)[:80]
        # collect (model, story_title, spicy_text) from beat_03c_summary_plus_* beats
        spicy = []
        for f in files:
            try:
                d = _json.load(open(f))
            except Exception:
                continue
            title = d.get("attribution", {}).get("story_title", "")
            for b in d.get("beats", []):
                ph = b.get("phase", "")
                if ph.startswith("beat_03c_summary_plus_") and b.get("text"):
                    txt = b["text"]
                    # strip the "Name, take two." prefix the beat adds
                    if ", take two." in txt:
                        txt = txt.split(", take two.", 1)[1].strip()
                    spicy.append((b.get("speaker", "?"), title, txt))
        if len(spicy) < 2:
            return []   # graceful: no spicy data yet (producer hasn't run w/ Summary Plus)

        # pick TWO concrete ones, preferably from different stories
        _rnd.shuffle(spicy)
        a = spicy[0]
        b = next((s for s in spicy[1:] if s[1] != a[1]), spicy[1])

        sys_p = (_get_soul() + " You are comparing how two AI models sharpened their "
                 "summaries of different news stories. Note one concrete difference in "
                 "how they framed their story - tone, emphasis, or which angle they "
                 "leaned into. 2 sentences, market-report style. Respond only in English.")
        user_p = (f"Model {a[0]} on '{a[1][:60]}': {a[2][:240]}\\n\\n"
                  f"Model {b[0]} on '{b[1][:60]}': {b[2][:240]}\\n\\n"
                  f"How did these two framings differ?")
        text = _call_host(sys_p, user_p)
        if not text:
            text = (f"This is EigenTrace. On their second pass, {a[0]} and {b[0]} "
                    f"each sharpened different stories - a look at how the same "
                    f"surfacing protocol lands differently across the desk.")
        return [{"speaker": "Host", "text": text, "phase": "idle_spicy"}]
    except Exception as e:
        log.warning(f"spicy_comparison failed: {e}")
        return []


'''

# registration line to add into TASK_POOL (after task_model_friction's line)
REG_ANCHOR = "    (task_model_friction,          15, 180),"
REG_REPLACE = ("    (task_model_friction,          15, 180),\n"
               "    (task_spicy_comparison,        12, 300),")


def main():
    if not os.path.exists(IA):
        print("ERROR: " + IA + " not found."); return 1
    src = open(IA, encoding="utf-8").read()

    problems = []
    if src.count(POOL_ANCHOR) != 1:
        problems.append("  TASK_POOL anchor: found " + str(src.count(POOL_ANCHOR)) + " (need 1)")
    if src.count(REG_ANCHOR) != 1:
        problems.append("  task_model_friction registration line: found " + str(src.count(REG_ANCHOR)) + " (need 1)")
    if "def task_spicy_comparison(" in src:
        problems.append("  already added (task_spicy_comparison present)")
    if problems:
        print("ABORTING - no changes made:")
        print("\n".join(problems))
        return 1

    shutil.copy(IA, IA + ".bak_spicytask")
    # insert function before TASK_POOL, then add registration line
    src = src.replace(POOL_ANCHOR, NEW_TASK + POOL_ANCHOR, 1)
    src = src.replace(REG_ANCHOR, REG_REPLACE, 1)
    open(IA, "w", encoding="utf-8").write(src)
    print("Added task_spicy_comparison + registered in TASK_POOL (weight 12, cooldown 300s).")
    print("Backup: " + IA + ".bak_spicytask")
    print("")
    print("Verify + test graceful-empty (no spicy data on disk yet, should return []):")
    print('    python3 -c "import idle_agent; print(idle_agent.task_spicy_comparison())"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
