#!/usr/bin/env python3
"""
Deletes backend/logs/trading_*.log files once their day is over, e.g. the
11 Aug log gets deleted when this runs on 12 Aug. These are DEBUG-level
per-trading-day logs that can grow to several MB/day and were piling up
unbounded (backend/logs/trade_logs itself is untouched - those are the
actual trade records, not debug logs).

Run daily via cron (AWS) / Task Scheduler (local Windows), scheduled after
midnight and well before the ~9:00-9:15 AM pre-market cron so no file being
actively written gets caught mid-write.
"""
import glob
import os
import re
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
LOGS_DIR = os.path.join(_ROOT, "backend", "logs")

_PATTERN = re.compile(r"^trading_(\d{4}-\d{2}-\d{2})\.log$")


def main():
    today = date.today()
    deleted = []
    for path in glob.glob(os.path.join(LOGS_DIR, "trading_*.log")):
        name = os.path.basename(path)
        match = _PATTERN.match(name)
        if not match:
            continue
        try:
            log_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if log_date < today:
            os.remove(path)
            deleted.append(name)

    if deleted:
        print(f"[{date.today().isoformat()}] Deleted {len(deleted)} old trade log(s): {', '.join(sorted(deleted))}")
    else:
        print(f"[{date.today().isoformat()}] No old trade logs to delete.")


if __name__ == "__main__":
    main()
