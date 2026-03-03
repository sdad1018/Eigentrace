#!/usr/bin/env python3
"""
orchestrator.py — AINN Master Loop
=====================================
Coordinates awake mode (proxy_auditor) and dream mode (dream_engine).
Single entry point for the entire system.

AWAKE (04:00-00:00):
  - Continuous RSS monitoring + Big 5 proxy audit
  - Story importance scoring
  - Cross-model callout detection
  - Ticker updates

DREAM (00:00-04:00):
  - φ-attractor dream type selection
  - FREE / IDENTITY / WORLD dreams
  - Image + music generation
  - Soul CI/CD via integrator.py
  - Ticker updates

Both modes run as threads. The orchestrator manages transitions,
monitors health, and restarts crashed workers.

Author: remvelchio
"""

from __future__ import annotations

import os, sys, time, logging, threading, signal
from pathlib import Path
from datetime import datetime

log = logging.getLogger("orchestrator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/home/remvelchio/agent")

TICKER_FILE = Path(os.getenv("TICKER_FILE",
                   "/home/remvelchio/agent/tmp/ticker.txt"))
SEEN_FILE   = Path(os.getenv("SEEN_FILE",
                   "/home/remvelchio/agent/tmp/seen_stories.json"))

DREAM_START = int(os.getenv("DREAM_START_HOUR", "0"))
DREAM_END   = int(os.getenv("DREAM_END_HOUR",   "4"))

# Restart delay after worker crash
RESTART_DELAY = int(os.getenv("RESTART_DELAY", "30"))

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  MODE DETECTION                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def current_mode() -> str:
    h = datetime.now().hour
    return "DREAM" if DREAM_START <= h < DREAM_END else "AWAKE"

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TICKER HELPERS                                                          ║
# ╚══════════════���═══════════════════════════════════════════════════════════╝

def _write_ticker(lines: list) -> None:
    try:
        TICKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        TICKER_FILE.write_text("  •  ".join(str(l) for l in lines))
    except Exception as e:
        log.warning(f"Ticker write failed: {e}")

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  AWAKE WORKER                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class AwakeWorker(threading.Thread):
    """
    Runs proxy_auditor.run_audit_cycle() in a loop during awake hours.
    Pauses automatically when dream mode is active.
    """
    def __init__(self):
        super().__init__(name="AwakeWorker", daemon=True)
        self._stop_event = threading.Event()
        self.cycles = 0
        self.last_error: str = ""

    def stop(self):
        self._stop_event.set()

    def run(self):
        # Lazy import — only load when needed
        import proxy_auditor as pa
        seen = pa._load_seen()
        poll = pa.POLL_INTERVAL

        log.info("AwakeWorker started")
        while not self._stop_event.is_set():
            if current_mode() != "AWAKE":
                time.sleep(30)
                continue
            try:
                t0 = time.time()
                lines = pa.run_audit_cycle(seen)
                if lines:
                    pa.write_ticker(lines)
                self.cycles += 1
                elapsed = time.time() - t0
                sleep = max(5, poll - elapsed)
                log.info(f"Awake cycle {self.cycles} done in {elapsed:.1f}s, "
                         f"sleep {sleep:.0f}s")
                self._stop_event.wait(sleep)
            except Exception as e:
                self.last_error = str(e)
                log.error(f"AwakeWorker error: {e}", exc_info=True)
                self._stop_event.wait(RESTART_DELAY)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  DREAM WORKER                                                            ║
# ╚══════════════════════════════════════════��═══════════════════════════════╝

class DreamWorker(threading.Thread):
    """
    Runs dream_engine.run_dream_cycle() during dream hours.
    Pauses automatically when awake mode is active.
    """
    def __init__(self):
        super().__init__(name="DreamWorker", daemon=True)
        self._stop_event = threading.Event()
        self.cycles = 0
        self.last_error: str = ""

    def stop(self):
        self._stop_event.set()

    def run(self):
        import dream_engine as de
        selector = de.PhiSelector()
        cycle_seconds = de.DREAM_CYCLE_SECONDS

        log.info("DreamWorker started")
        while not self._stop_event.is_set():
            if current_mode() != "DREAM":
                time.sleep(30)
                continue
            try:
                entry = de.run_dream_cycle(selector)
                if entry:
                    self.cycles += 1
                    log.info(f"Dream cycle {self.cycles}: "
                             f"type={entry.dream_type} "
                             f"integrated={entry.integrated}")
                self._stop_event.wait(cycle_seconds)
            except Exception as e:
                self.last_error = str(e)
                log.error(f"DreamWorker error: {e}", exc_info=True)
                self._stop_event.wait(RESTART_DELAY)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  HEALTH MONITOR                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class HealthMonitor(threading.Thread):
    """
    Checks worker health every 60s.
    Restarts crashed workers automatically.
    Writes status to ticker if both workers are down.
    """
    def __init__(self, awake: AwakeWorker, dream: DreamWorker):
        super().__init__(name="HealthMonitor", daemon=True)
        self._stop_event = threading.Event()
        self.awake = awake
        self.dream = dream

    def stop(self):
        self._stop_event.set()

    def _restart_awake(self):
        log.warning("Restarting AwakeWorker...")
        self.awake = AwakeWorker()
        self.awake.start()

    def _restart_dream(self):
        log.warning("Restarting DreamWorker...")
        self.dream = DreamWorker()
        self.dream.start()

    def run(self):
        while not self._stop_event.is_set():
            mode = current_mode()

            if mode == "AWAKE" and not self.awake.is_alive():
                log.error(f"AwakeWorker dead. Last error: {self.awake.last_error}")
                self._restart_awake()

            if mode == "DREAM" and not self.dream.is_alive():
                log.error(f"DreamWorker dead. Last error: {self.dream.last_error}")
                self._restart_dream()

            # Status log
            log.info(
                f"Health: mode={mode} | "
                f"awake={'alive' if self.awake.is_alive() else 'DEAD'} "
                f"(cycles={self.awake.cycles}) | "
                f"dream={'alive' if self.dream.is_alive() else 'DEAD'} "
                f"(cycles={self.dream.cycles})"
            )
            self._stop_event.wait(60)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  MAIN                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_workers: list = []

def _shutdown(signum, frame):
    log.info(f"Signal {signum} received — shutting down")
    for w in _workers:
        w.stop()
    sys.exit(0)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AINN Orchestrator")
    parser.add_argument("--mode", choices=["awake", "dream", "auto"],
                        default="auto",
                        help="Force a mode or auto-detect from time (default: auto)")
    parser.add_argument("--no-media", action="store_true",
                        help="Disable image + music generation in dream mode")
    parser.add_argument("--status", action="store_true",
                        help="Print current mode and exit")
    args = parser.parse_args()

    if args.status:
        mode = current_mode()
        h = datetime.now().hour
        print(f"Mode: {mode} (hour={h}, dream={DREAM_START:02d}:00-{DREAM_END:02d}:00)")
        return

    if args.no_media:
        import dream_engine as de
        de.generate_image = lambda p: ""
        de.generate_music = lambda d, dur=30: ""
        log.info("Media generation disabled")

    # Override mode if forced
    if args.mode == "awake":
        os.environ["DREAM_START_HOUR"] = "99"  # never dream
    elif args.mode == "dream":
        os.environ["DREAM_START_HOUR"] = "0"
        os.environ["DREAM_END_HOUR"]   = "24"  # always dream

    # Signal handlers
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    mode = current_mode()
    log.info("=" * 60)
    log.info("AINN ORCHESTRATOR STARTING")
    log.info(f"Current mode: {mode}")
    log.info(f"Dream window: {DREAM_START:02d}:00 — {DREAM_END:02d}:00")
    log.info("=" * 60)

    _write_ticker([f"AINN ONLINE — mode={mode} — {datetime.now().strftime('%H:%M')}"])

    # Start both workers — each self-pauses when not its turn
    awake  = AwakeWorker()
    dream  = DreamWorker()
    health = HealthMonitor(awake, dream)

    global _workers
    _workers = [awake, dream, health]

    awake.start()
    dream.start()
    health.start()

    log.info("All workers started. Entering main loop.")

    # Main thread just keeps the process alive
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")
        for w in _workers:
            w.stop()

if __name__ == "__main__":
    main()
