// PM2 process config for the Linux/AWS deployment. Not used for local Windows
// dev (where backend/API/frontend are run manually in separate terminals per
// the project's usual workflow) - paths below assume a Linux venv at .venv/.
//
// Usage on the deployment server:
//   python3 -m venv .venv
//   .venv/bin/pip install -r requirements.txt -r requirements-prod.txt
//   pm2 start ecosystem.config.js
module.exports = {
    apps: [
        {
            name: "algo-backend",
            script: "run_backend.py",
            interpreter: "./.venv/bin/python3",
            // MUST stay 1: the trading engine keeps positions in memory
            // (order_manager.active_positions) - a second instance racing
            // against this one WILL place duplicate trades. Confirmed the
            // hard way this session.
            instances: 1,
            exec_mode: "fork",
            autorestart: true,
            // main.py exits cleanly (code 0, not an error) once it finishes
            // its after-hours post-market-analysis pass, or after the EOD
            // routine on a normal trading day - both are expected exits,
            // not crashes. stop_exit_codes tells PM2 to treat exit code 0
            // as an intentional stop (no restart) instead of a crash -
            // the daily 9am cron's `startOrRestart` brings it back up for
            // real the next trading morning. A genuine crash (unhandled
            // exception -> nonzero exit code) still hits autorestart below.
            // Confirmed live 2026-08-19: without this, exp_backoff_restart_delay
            // does NOT actually cap restarts at max_restarts - PM2 kept
            // retrying indefinitely (3500+ restarts) with growing backoff
            // instead of stopping, every single evening after EOD.
            stop_exit_codes: [0],
            min_uptime: "30s",
            max_restarts: 15,
            exp_backoff_restart_delay: 3000,
            watch: [".env"], // restart on .env changes (e.g. Dhan token refresh)
            ignore_watch: ["logs/*", "data/*", "*.log"],
            env: {
                PYTHONUNBUFFERED: "1",
            },
        },
        {
            name: "algo-api",
            script: "./.venv/bin/gunicorn",
            // interpreter: "none" - without this, PM2 defaults to running
            // unrecognized script types through Node's module loader, which
            // feeds this Python venv shebang script to Node as if it were
            // JS ("SyntaxError: Unexpected identifier 'gunicorn'") and
            // crash-loops forever. "none" makes PM2 exec the script
            // directly so its own shebang (#!.venv/bin/python3) is used.
            // Confirmed live during the 2026-07-23 server rebuild.
            interpreter: "none",
            // --workers must stay 1 - see wsgi.py docstring: server.py holds
            // in-process WebSocket/tick-queue state that can only safely
            // exist in one process. --threads handles concurrency instead.
            args: "wsgi:app --bind 0.0.0.0:5000 --workers 1 --threads 4 --worker-class gthread",
            instances: 1,
            exec_mode: "fork",
            autorestart: true,
            watch: false,
        },
        // Frontend: for local dev only (npm run dev). In production, serve
        // frontend/dist as static files via nginx or S3+CloudFront instead
        // of running a node process for it - that's a deployment-day (AWS
        // provisioning) decision, not something to hardcode here.
        {
            name: "algo-frontend-dev",
            script: "npm",
            args: "run dev",
            cwd: "./frontend",
        }
    ],
};
