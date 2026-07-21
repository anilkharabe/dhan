# Trading Dashboard

React-based read-only dashboard for the OI-Based Nifty & Sensex Options Trading System.

## Features

- **Profile View**: Display trading configuration, mode, lot sizes, and risk parameters
- **Current Positions**: Real-time view of open positions with P&L tracking
- **OI PCR Chart**: Put-Call Ratio visualization for Nifty and Sensex
- **Daily Summary**: Today's trading statistics and performance metrics

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure API URL (optional):
```bash
cp .env.example .env
# Edit .env and set VITE_API_URL if your API server runs on a different port
```

3. Start the development server:
```bash
npm run dev
```

The dashboard will be available at `http://localhost:5173` (or the port shown in terminal).

## Backend API

Make sure the Flask API server (`api_server.py`) is running on `http://localhost:5000`.

To start the API server:
```bash
python api_server.py
```

## API Endpoints

- `GET /api/profile` - Trading profile and configuration
- `GET /api/current-positions` - Current open positions
- `GET /api/metrics/oi-pcr` - OI Put-Call Ratio data
- `GET /api/summary/today` - Daily trading summary
- `GET /api/health` - Health check

## Build for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Technologies

- React 18
- Vite
- Tailwind CSS
- Recharts (for charts)
- Axios (for API calls)
