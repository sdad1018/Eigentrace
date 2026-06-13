#!/usr/bin/env python3
"""
insert_baby_block.py — inserts the homepage baby-block into docs/index.md right
after the live broadcast iframe's caption line. Guarded; all-or-nothing.
Run from repo root. Reads the block from homepage_baby_block.html (same dir or cwd).
"""
import sys, shutil, os

IDX = "docs/index.md"
BLOCK_FILE = "homepage_baby_block.html"

# Anchor: the italic caption line right under the iframe. Insert AFTER it.
ANCHOR = "*24/7 autonomous AI news broadcast. Mistral Small 22B narrates consensus geometry across 5 frontier LLMs on breaking news.*"


def main():
    if not os.path.exists(IDX):
        print("ERROR: " + IDX + " not found (run from repo root)."); return 1
    if not os.path.exists(BLOCK_FILE):
        print("ERROR: " + BLOCK_FILE + " not found in cwd. Copy it here first."); return 1

    src = open(IDX, encoding="utf-8").read()
    block = open(BLOCK_FILE, encoding="utf-8").read().strip()

    problems = []
    if src.count(ANCHOR) != 1:
        problems.append(f"  iframe-caption anchor: found {src.count(ANCHOR)} (need 1)")
    if "A self-measuring instrument" in src:
        problems.append("  already inserted (baby block present)")
    if problems:
        print("ABORTING - no changes made:")
        print("\n".join(problems))
        print("(File untouched. The caption text may differ slightly — paste index.md head and we'll re-anchor.)")
        return 1

    shutil.copy(IDX, IDX + ".bak_babyblock")
    src = src.replace(ANCHOR, ANCHOR + "\n\n" + block, 1)
    open(IDX, "w", encoding="utf-8").write(src)
    print("Baby block inserted into index.md, right after the broadcast iframe caption.")
    print("  Backup: " + IDX + ".bak_babyblock")
    print("  (Raw HTML block — Jekyll/kramdown passes it through as-is.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
