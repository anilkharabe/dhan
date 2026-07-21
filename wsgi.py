"""
Production WSGI entry point for the Flask API server.

Run with gunicorn (Linux only - gunicorn relies on os.fork, doesn't work on
Windows; use run_api.py for local Windows dev instead):

    gunicorn wsgi:app --bind 0.0.0.0:5000 --workers 1 --threads 4 --worker-class gthread

IMPORTANT: --workers must stay at 1. api/server.py holds in-process state
(the Dhan WebSocket relay client, SSE tick queues, latest-tick cache) that
must exist exactly once - multiple worker *processes* would each open their
own competing WebSocket connection to Dhan and maintain separate tick state,
silently splitting data between whichever client happens to hit which worker.
Use --threads to handle concurrent requests instead of --workers.
"""
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.join(_root, "backend")
_api = os.path.join(_root, "api")
for _p in (_backend, _api):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from server import app  # noqa: E402

if __name__ == "__main__":
    # Allows `python wsgi.py` as a sanity check, but prefer gunicorn per the
    # module docstring above for actual production use.
    app.run(host="0.0.0.0", port=5000)
