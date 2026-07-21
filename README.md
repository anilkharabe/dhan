# OI-Based Nifty & Sensex Options Trading

Project layout:

- **backend/** – Trading engine (strategy, data, orders, indicators, etc.). Run with `python run_backend.py`.
- **api/** – Flask API for the dashboard. Run with `python run_api.py`.
- **frontend/** – React/Vite dashboard. Run with `cd frontend && npm run dev`.
- **docs/** – Strategy documentation and setup guides.
- **.env** – Credentials and config (at project root; shared by backend and api).
- **requirements.txt** – Python dependencies (install at project root).

## Quick start

From project root:

1. **Backend (trading):** `python3 run_backend.py`
2. **API (for dashboard):** `python3 run_api.py` → http://localhost:5000
3. **Frontend:** `cd frontend && npm install && npm run dev` → http://localhost:5173

See `docs/STRATEGY_DOCUMENTATION.md` and `docs/DASHBOARD_SETUP.md` for details.
