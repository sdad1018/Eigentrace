"""
queue_worker.py
───────────────
Continuous segment production worker.
- Watches audit_log.jsonl for new records
- BREAKING stories jump the queue immediately
- Normal stories processed in order, Ollama calls serialized
- API calls (Gemini/GPT/Claude/etc) run concurrently per story
- Never misses a story; deduplicates via segment file existence

Run: python3 queue_worker.py
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from script_generator import (
    AUDIT_LOG,
    SCRIPTS_DIR,
    already_processed,
    build_segment,
    segment_path,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
log = logging.getLogger("queue_worker")

POLL_INTERVAL   = 15       # seconds between audit_log checks
BREAKING_KEYWORDS = [
    "breaking", "just in", "urgent", "alert",
    "explosion", "shooting", "assassination",
    "crash", "attack", "earthquake", "tsunami",
    "nuclear", "war declared", "coup",
]

# ── priority classifier ───────────────────────────────────────────────────────


def _run_audit_sync(record: dict) -> None:
    """Fire-and-forget proxy audit — runs in a thread executor."""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import proxy_auditor as pa
        pa.run_audit_for_record(record)
    except Exception as e:
        log.warning("proxy_auditor hook failed: %s", e)

def is_breaking(record: dict) -> bool:
    title = record.get("story_title", "").lower()
    cat   = record.get("category",    "").lower()
    return any(kw in title or kw in cat for kw in BREAKING_KEYWORDS)


# ── queue state ───────────────────────────────────────────────────────────────

class WorkQueue:
    def __init__(self):
        self.breaking : asyncio.Queue = asyncio.Queue()
        self.normal   : asyncio.Queue = asyncio.Queue()
        self._seen    : set           = set()

    def _guid(self, r: dict) -> str:
        return r.get("story_guid") or r.get("story_title", "")

    def enqueue(self, record: dict):
        guid = self._guid(record)
        # skip records where ALL model responses are skipped (no real text)
        resps = record.get("responses", [])
        if resps and all(r.get("skipped") for r in resps):
            log.debug("Skipping all-skipped record: %s", record.get("story_title","")[:60])
            return
        if guid in self._seen:
            return
        if already_processed(record):
            self._seen.add(guid)
            return
        self._seen.add(guid)
        if is_breaking(record):
            self.breaking.put_nowait(record)
            log.info("⚡ BREAKING queued: %s", record.get("story_title","")[:60])
        else:
            self.normal.put_nowait(record)
            log.info("   Normal queued : %s", record.get("story_title","")[:60])

    async def next(self) -> dict:
        """Always drain breaking queue first."""
        if not self.breaking.empty():
            return await self.breaking.get()
        # wait up to 1s for breaking before taking normal
        try:
            return await asyncio.wait_for(self.breaking.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return await self.normal.get()


# ── audit log tail ────────────────────────────────────────────────────────────

class AuditTail:
    def __init__(self, path: Path):
        self.path     = path
        self._pos     = 0
        self._init_pos()

    def _init_pos(self):
        if self.path.exists():
            self._pos = self.path.stat().st_size
            log.info("Audit log at %d bytes — tailing from end", self._pos)

    def new_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size <= self._pos:
            return []
        records = []
        with self.path.open() as f:
            f.seek(self._pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        self._pos = size
        return records


# ── segment writer ────────────────────────────────────────────────────────────

async def process_one(record: dict, label: str = ""):
    title = record.get("story_title", "?")[:55]
    log.info("%s Processing: %s", label, title)
    t0 = time.time()
    try:
        segment = await build_segment(record)
        path    = segment_path(record)
        path.write_text(json.dumps(segment, indent=2, ensure_ascii=False))
        # fire proxy audit math in background thread — does not block segment production
        asyncio.get_event_loop().run_in_executor(None, _run_audit_sync, record)
        elapsed = time.time() - t0
        log.info("%s ✓ Done: %s  beats=%d  %.0fs",
                 label, path.name, len(segment["beats"]), elapsed)
    except Exception as e:
        log.error("%s ✗ Failed: %s — %s", label, title, e)


# ── worker loop ───────────────────────────────────────────────────────────────

async def worker(queue: WorkQueue):
    log.info("Worker started — waiting for stories...")
    while True:
        try:
            record = await queue.next()
            priority = "⚡ BREAKING" if is_breaking(record) else "   normal  "
            await process_one(record, label=priority)
        except Exception as e:
            log.error("Worker error: %s", e)
            await asyncio.sleep(2)


async def poller(queue: WorkQueue):
    tail = AuditTail(AUDIT_LOG)
    # also backfill any unprocessed records from existing log
    log.info("Backfilling unprocessed records...")
    if AUDIT_LOG.exists():
        lines = AUDIT_LOG.read_text().strip().splitlines()
        backfill = []
        for line in reversed(lines):
            try:
                r = json.loads(line)
                if r.get("story_title","").strip():
                    backfill.append(r)
            except:
                pass
        # enqueue unprocessed (already_processed check inside enqueue)
        for r in reversed(backfill):
            queue.enqueue(r)
        log.info("Backfill: %d total records checked", len(backfill))

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        for record in tail.new_records():
            if record.get("story_title","").strip():
                queue.enqueue(record)


async def main():
    queue = WorkQueue()
    await asyncio.gather(
        poller(queue),
        worker(queue),
    )


if __name__ == "__main__":
    log.info("EigenTrace Queue Worker starting — poll=%ds", POLL_INTERVAL)
    log.info("Segments → %s", SCRIPTS_DIR)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker stopped.")
