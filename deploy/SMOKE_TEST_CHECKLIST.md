# Deployment-day smoke test checklist

Run through this in order on the actual AWS instance, after provisioning (items D/E)
but before considering the deployment "done." Everything here was informed by
real bugs found this session - each check exists because something like it
actually broke once.

## 1. Environment sanity (before starting anything)

- [ ] `timedatectl` shows `Asia/Kolkata` (or run `python3 -c "import config; config.validate_config()"` from `backend/` -
      it will now raise a clear error if the timezone is wrong, instead of silently trading at the wrong hours)
- [ ] `.env` present with real Dhan credentials (Client ID, access token, PIN, TOTP secret) and Telegram tokens -
      sourced from Secrets Manager/SSM, not committed anywhere
- [ ] `PAPER_TRADING = True` in `backend/config.py` - confirm explicitly, don't assume
- [ ] `NIFTY_TRADING_DAYS`/`SENSEX_TRADING_DAYS` in `config.py` are correct for today's actual weekday
      (this is the exact bug we caught and fixed earlier - both were accidentally set to all 5 weekdays)
- [ ] `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-prod.txt` completed without errors

## 2. Pre-flight process check (before first start, and before every restart after)

- [ ] `ps aux | grep -E "run_backend|run_api|gunicorn"` shows nothing running yet
- [ ] `ss -tlnp | grep :5000` shows nothing listening yet
- [ ] From here on, always start/restart via `pm2` or `deploy/restart.sh` - never a manual
      `python run_backend.py &` in a spare terminal "just to check something"

## 3. First start

- [ ] `pm2 start ecosystem.config.js`
- [ ] `pm2 list` shows exactly one instance each of `algo-backend` and `algo-api`, status `online`
- [ ] `pm2 logs algo-backend --lines 50` shows clean initialization: config validated, token validated,
      trading day/hours check passed, no `Traceback`
- [ ] `pm2 logs algo-api --lines 50` shows gunicorn started with `--workers 1` (confirm only **one** worker
      PID in `ps aux | grep gunicorn`, not several - multiple workers would each open a competing Dhan
      WebSocket, see `wsgi.py`'s docstring for why)

## 4. API health

- [ ] `curl http://127.0.0.1:5000/api/health` → `{"status": "ok", ...}`
- [ ] `curl http://127.0.0.1:5000/api/current-positions` → `{"count": 0, "positions": []}` (fresh deploy, no positions yet)
- [ ] `curl http://127.0.0.1:5000/api/summary/today` → responds without error

## 5. Frontend

- [ ] `cd frontend && cp .env.production.example .env.production` and fill in the real `VITE_API_URL`
      (EC2 public IP for now, since domain/HTTPS is deferred)
- [ ] `npm run build` completes cleanly
- [ ] Serve `frontend/dist` (nginx or `npx serve`) and load it in a browser from another machine
- [ ] Confirm no CORS errors in the browser console - if there are, set `CORS_ALLOWED_ORIGINS` in the
      API's environment to the frontend's real origin and restart `algo-api`
- [ ] Dashboard loads, chart renders, positions table shows "No open positions" cleanly (not stuck loading)

## 6. Restart discipline dry-run

- [ ] Run `deploy/restart.sh` once, on purpose, just to confirm it works end-to-end (pre-flight check,
      PM2 restart, health check, position sanity check all pass)

## 7. Token refresh (test during off-market hours, not mid-session)

- [ ] Manually trigger: `python3 -c "from dhan_token_manager import dhan_token_manager; print(dhan_token_manager.generate_access_token_via_totp())"`
      from `backend/`, confirm `{"success": True, ...}`
- [ ] Confirm `.env`'s `DHAN_ACCESS_TOKEN` actually changed
- [ ] Confirm the running backend picks it up within 5 minutes without a restart (watch for
      "🔄 Access token update detected" in `pm2 logs algo-backend`) - or wait for the 09:00 daily
      scheduled job and confirm "🔄 Dhan access token proactively refreshed via TOTP" appears
- [ ] Don't test this for the first time during live market hours - do it once, calmly, before go-live

## 8. Alerting

- [ ] Confirm a deliberate error reaches Telegram (e.g. temporarily rename `DHAN_ACCESS_TOKEN` in `.env`,
      restart, confirm the "Token Error" alert arrives, then restore it)

## 9. One full trading day, watched

- [ ] Leave it running through a complete session, actually watch the dashboard at least once
- [ ] Confirm signals fire, spreads open in the correct entry sequence (hedge BUY then near SELL),
      trailing SL ratchets as expected, and `end_of_day_routine` force-closes everything at `TRADING_END_TIME`
- [ ] Only after this is genuinely boring/uneventful should PAPER_TRADING ever be considered for turning off
