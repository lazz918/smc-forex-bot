#!/usr/bin/env python3
"""
Background scanner loop for Windows.
Scans all pairs every 5 minutes and writes signals to scanner_signals.csv.
Telegram alerts fire if enabled in Config.
"""
import time
import traceback
from datetime import datetime
from pathlib import Path

from smc_forex_bot_v2 import Config, run_scanner

LOG = Path(__file__).parent / "logs" / "scanner.log"
LOG.parent.mkdir(exist_ok=True)
INTERVAL_SECONDS = 5 * 60  # 5 minutes


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    cfg = Config()
    cfg.MODE = "scanner"
    log("Background scanner started")
    while True:
        try:
            log("Scanning pairs...")
            run_scanner(cfg)
            log("Scan complete")
        except Exception:
            log("Scan error:\n" + traceback.format_exc())
        log(f"Sleeping {INTERVAL_SECONDS // 60} minutes")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
