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
            watch: [".env"], // restart on .env changes (e.g. Dhan token refresh)
            ignore_watch: ["logs/*", "data/*", "*.log"],
            env: {
                PYTHONUNBUFFERED: "1",
            },
        },
        {
            name: "algo-api",
            script: "./.venv/bin/gunicorn",
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
