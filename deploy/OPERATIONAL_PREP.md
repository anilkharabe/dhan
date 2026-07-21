# Operational prep (backups, logging, monitoring)

These depend on AWS/Atlas resources that don't exist yet (deferred to Sunday),
so this is the checklist to execute once they do - not something that can be
verified from the dev machine.

## Backups (MongoDB Atlas)

This database is the entire trade/P&L history - treat it accordingly.

- [ ] In the Atlas cluster settings, enable Cloud Backup (Atlas free/shared
      tiers have limited or no backup - if you're on M0/M2/M5, either upgrade
      to at least M10 for continuous backups, or schedule your own
      `mongodump` via cron as a fallback)
- [ ] If self-managing backups: `mongodump --uri="$MONGODB_URI" --out=/backup/$(date +%F)`
      on a daily cron, shipped to S3 (`aws s3 sync /backup s3://your-backup-bucket/`)
      with a lifecycle rule to expire old backups after e.g. 90 days
- [ ] Actually test a restore once, on a scratch cluster/database - an
      untested backup is not a backup

## Log persistence and retention

`backend/logs/trading_YYYY-MM-DD.log` already partitions by day (the app
creates a new file each day itself) - what's missing is age-based cleanup, so
files don't accumulate forever on the instance's disk.

- [ ] Add a daily cron job for retention (adjust the retention window to taste):
  ```
  0 2 * * * find /path/to/algo/backend/logs -name "trading_*.log" -mtime +30 -delete
  ```
- [ ] Decide whether logs should also ship off-instance (recommended, so you
      don't lose history if the instance is replaced):
  - Simplest: install the CloudWatch agent, point it at `backend/logs/*.log`
    and `backend/logs/*_stdout.log`, ship to a CloudWatch Log Group
  - Then the local retention window above can be shorter (e.g. 7 days)
    since CloudWatch holds the durable copy
- [ ] Confirm PM2's own logs aren't silently growing unbounded either -
      `pm2 install pm2-logrotate` if you go the PM2 route, or rely on
      whatever gunicorn/systemd logging you end up using instead

## Monitoring / alerting

Telegram already covers application-level errors (`telegram_notifier.py`
fires on token issues, order failures, scan errors, etc.) - this layer is
for instance/infrastructure-level problems Telegram can't see:

- [ ] CloudWatch alarm: disk space >80% used (a filled disk silently breaks
      MongoDB writes and log files - insidious because nothing crashes loudly)
- [ ] CloudWatch alarm: instance status check failure (catches the instance
      itself being unreachable, which no in-process alerting can ever detect)
- [ ] CloudWatch alarm: CPU/memory sustained high (early warning before
      something actually falls over)
- [ ] Consider a simple external uptime check (e.g. a scheduled Lambda or
      third-party pinger hitting `/api/health` every few minutes) - this is
      the one thing that can tell you the *API process itself* died, as
      opposed to just the instance being up
- [ ] Decide who receives CloudWatch alarms (SNS -> email/SMS) - Telegram
      alerts go wherever `telegram_notifier.py` is configured, but that's a
      separate channel from AWS-native alarms unless you also wire SNS -> Telegram
