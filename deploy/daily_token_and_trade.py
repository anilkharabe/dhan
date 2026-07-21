#!/usr/bin/env python3
"""
Daily pre-market job (run by cron at 9:00 AM IST, weekdays):
refresh the Dhan access token via PIN+TOTP, then start algo-backend via PM2.

Unlike generate_dhan_token.py, this never falls back to an interactive
input() prompt on failure - that would hang a cron job with no tty. On
failure it alerts via Telegram and exits without starting the trading engine.
"""
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


def main():
    dry_run = "--dry-run" in sys.argv

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
