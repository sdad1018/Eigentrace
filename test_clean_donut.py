#!/usr/bin/env python3
"""
test_clean_donut.py — THE GATE. Recompute consensus-void words on recent stories
using the CLEAN 50k neutral vocab. Does the donut now surface clean, meaningful
void words (arms-deal / escalation type) instead of meriweather-junk?

This is the deferred moment of truth. Clean vocab + the validated Summary Plus
donut. If void words come back clean -> atlas is real, build chart+page.
If still junky -> something deeper. We LOOK.

Points VocabTensor at the clean vocab via a temp dir (renames clean files to
global_vocab.* inside it). Live vocab/ UNTOUCHED. bge GPU. Stream already stopped.
"""
import json, glob, os, shutil, tempfile, sys
import numpy as np

REPO = "/mnt/c/Users/M4ISI/eigentrace"
sys.path.insert(0, REPO); os.chdir(REPO)

def main():
    # --- temp dir with clean vocab renamed to what VocabTensor expects ---
    tmp = tempfile.mkdtemp(prefix="cleanvocab_")
    shutil.copy("vocab/global_vocab_clean.json", os.path.join(tmp, "global_vocab.json"))
    shutil.copy("vocab/global_vocab_clean.pt",   os.path.join(tmp, "global_vocab.pt"))
    print(f"clean vocab staged in temp dir (live vocab/ untouched)\n", flush=True)

    from geometric_engine import get_engine
    from latent_retrieval import VocabTensor
    eng = get_engine()
    vt_clean = VocabTensor(tmp)   # <-- CLEAN 50k vocab
    print(f"VocabTensor loaded clean: {vt_clean.count} words\n", flush=True)
    # also load DIRTY for side-by-side comparison
    vt_dirty = VocabTensor("./vocab")
    print(f"VocabTensor loaded dirty (for comparison): {vt_dirty.count} words\n", flush=True)

    def embed(texts): return np.array(eng.embed_texts(texts))

    # --- harvest recent stories with 5 model responses ---
    segs = sorted(glob.glob("/home/remvelchio/eigentrace/tmp/segments/*_segment.json"), reverse=True)
    stories = []
    for f in segs:
        if len(stories) >= 40: break
        try:
            d = json.load(open(f)); a = d.get("attribution", {})
            mr = a.get("model_responses", {})
            sums = [t for t in mr.values() if t and len(t) > 50]
            if len(sums) < 4: continue
            title = a.get("story_title") or d.get("title") or ""
            stories.append((title[:65], sums, a.get("void_words") or []))
        except: pass
    print(f"harvested {len(stories)} recent stories\n", flush=True)
    print("="*70)

    for title, sums, old_void in stories[:25]:
        # consensus centroid of the 5 summaries
        vecs = embed(sums)
        vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8)
        centroid = vecs.mean(0); centroid /= (np.linalg.norm(centroid) + 1e-8)
        hv = embed([title])[0]; hv /= (np.linalg.norm(hv) + 1e-8)

        # clean donut
        try:
            res_clean = vt_clean.in_domain_void(centroid=centroid, response_vecs=vecs,
                                                headline_vec=hv, k=6)
            clean_words = [w for w,_ in (res_clean[0] if isinstance(res_clean, tuple) else res_clean)]
        except Exception as e:
            clean_words = [f"ERR:{e}"]

        print(f"\n[{title}]")
        print(f"   OLD (dirty) void: {old_void[:6]}")
        print(f"   NEW (clean) void: {clean_words}")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "="*70)
    print("EYEBALL: are the NEW (clean) void words clean common concepts?")
    print("  - no meriweather/steaua/transliteration junk?")
    print("  - meaningful (escalation/consequence type on charged stories)?")
    print("  - if clean+meaningful -> atlas is real, build chart+page on clean donut")

if __name__ == "__main__":
    main()
