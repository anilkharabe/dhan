#!/usr/bin/env python3
"""
Launcher for the Flask API server. Adds backend/ and api/ to sys.path and runs the app.
Run from project root: python run_api.py

For local dev only. In production, run under a real WSGI server instead
(see wsgi.py) - Flask's built-in server isn't built for real traffic, and
its debug-mode auto-reloader forks a child process, which is unsafe here
since server.py holds in-process WebSocket/tick-queue state that must never
exist in more than one process at a time.
"""
import os
import socket
import sys

_root = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.join(_root, "backend")
_api = os.path.join(_root, "api")
for _p in (_backend, _api):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from server import app


def _port_already_in_use(port: int) -> bool:
    """
    Plain bind attempt with no SO_REUSEADDR, unlike the server's own socket
    (Werkzeug sets allow_reuse_address=True). On Windows, SO_REUSEADDR lets a
    second process silently bind an already-listening port instead of
    erroring - which previously let two run_api.py instances run at once,
    with requests randomly landing on whichever (possibly stale/broken) one
    the OS picked. A clean bind() here still fails correctly against that
    existing listener, so we catch it before app.run() ever gets there.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


if __name__ == "__main__":
    PORT = 5000
    if _port_already_in_use(PORT):
        print(f"Port {PORT} is already in use - another run_api.py instance is likely running.")
        print(f"Find it with: netstat -ano | findstr :{PORT}   (Windows)   or   lsof -i :{PORT}   (Unix)")
        sys.exit(1)

    print("Starting Flask API Server...")
    print("API will be available at http://localhost:5000")
    print("\nEndpoints:")
    print("  GET /api/profile")
    print("  GET /api/current-positions")
    print("  GET /api/metrics/oi-pcr")
    print("  GET /api/summary/today")
    print("  GET /api/health")
    print("\nPress Ctrl+C to stop")
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=PORT, debug=debug_mode)
