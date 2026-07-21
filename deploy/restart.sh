#!/usr/bin/env bash
# Safe restart procedure for the Linux/AWS deployment.
#
# ALWAYS restart through this script (or `pm2 restart ecosystem.config.js`
# directly) - never launch run_backend.py/run_api.py manually in a separate
# shell "just to test something". This session found real duplicate-trade
# bugs (two independent trading engines racing against the same account,
# each blind to the other's in-memory positions) caused by exactly that kind
# of stray, un-tracked process. The pre-flight check below exists because of
# that incident, not as a hypothetical precaution.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Pre-flight check: looking for backend/API processes NOT managed by PM2 ==="
STRAY=$(ps aux | grep -E "run_backend\.py|run_api\.py|gunicorn.*wsgi:app" | grep -v grep || true)
if [ -n "$STRAY" ]; then
    echo "Processes matching the trading engine/API found on this host:"
    echo "$STRAY"
    echo ""
    echo "Cross-check against 'pm2 list' below - anything NOT listed there is"
    echo "an orphan and must be killed before restarting, or you will end up"
    echo "with two engines running against the same Dhan account/MongoDB."
fi

echo ""
echo "=== Port 5000 owner(s) ==="
ss -tlnp 2>/dev/null | grep ":5000 " || echo "(nothing listening on 5000)"

echo ""
echo "=== PM2 status before restart ==="
pm2 list

echo ""
read -p "Proceed with restart? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted - resolve the above first."
    exit 1
fi

echo ""
echo "=== Restarting via PM2 ==="
pm2 restart ecosystem.config.js

echo ""
echo "=== PM2 status after restart ==="
pm2 list

echo ""
echo "=== Health check (waiting 5s for API to come up) ==="
sleep 5
if curl -sf http://127.0.0.1:5000/api/health; then
    echo ""
    echo "API OK"
else
    echo "API health check FAILED - check: pm2 logs algo-api"
    exit 1
fi

echo ""
echo "=== Open positions sanity check (should match what you expect - no surprise duplicates) ==="
curl -sf http://127.0.0.1:5000/api/current-positions | python3 -m json.tool || echo "Could not fetch positions"
