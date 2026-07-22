#!/usr/bin/env python3
"""
Daily pre-market job (run by cron every 5 min from 9:00-9:15 AM IST, weekdays):
refresh the Dhan access token via PIN+TOTP, then start algo-backend via PM2.

Unlike generate_dhan_token.py, this never falls back to an interactive
input() prompt on failure - that would hang a cron job with no tty. On
failure it alerts via Telegram and exits without starting the trading engine.

Runs on a 5-minute retry window rather than a single exact minute: a cron
entry pinned to one exact minute can be silently skipped if the system clock
steps across it (e.g. an NTP correction shortly after boot) - regular cron
has no catch-up/missed-job mechanism, unlike anacron. The idempotency check
below means repeated firings within the window are harmless no-ops once
algo-backend is confirmed running.
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT, ".env"))

from dhan_token_manager import dhan_token_manager  # noqa: E402
from telegram_notifier import notify_error  # noqa: E402


def _algo_backend_already_running():
    try:
        check = subprocess.run(
            ["pm2", "jlist"], cwd=_ROOT, capture_output=True, text=True, check=True
        )
        procs = json.loads(check.stdout)
        return any(
            p.get("name") == "algo-backend" and p.get("pm2_env", {}).get("status") == "online"
            for p in procs
        )
    except Exception:
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    if not dry_run and _algo_backend_already_running():
        print("algo-backend already online - skipping (idempotent retry-window firing)")
        return

    result = dhan_token_manager.generate_access_token_via_totp()
    if not result.get("success"):
        message = (
            f"Daily cron could not refresh the Dhan access token: "
            f"{result.get('message')}. algo-backend was NOT started - "
            f"fix manually (check DHAN_PIN/DHAN_TOTP_SECRET) and start trading yourself."
        )
        print(f"FAILED: {message}")
        if not dry_run:
            notify_error("Dhan token refresh failed", message)
        sys.exit(1)

    print(f"Token refreshed OK: {result.get('message')}")

    if dry_run:
        print("--dry-run: skipping pm2 startOrRestart algo-backend")
        return

    subprocess.run(
        ["pm2", "startOrRestart", "ecosystem.config.js", "--only", "algo-backend"],
        cwd=_ROOT,
        check=True,
    )
    subprocess.run(["pm2", "save"], check=True)
    print("algo-backend started via PM2")


if __name__ == "__main__":
    main()
