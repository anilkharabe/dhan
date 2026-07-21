# Dashboard Setup Guide

## Quick Start

### 1. Backend API Server

The Flask API server provides read-only endpoints for the React dashboard.

**Install dependencies:**
```bash
pip install flask flask-cors
```

**Start the API server (from project root):**
```bash
python run_api.py
```

The API will be available at `http://localhost:5000`

**Note:** Run from project root. The API imports the backend trading modules automatically.

### 2. React Frontend

**Navigate to frontend directory:**
```bash
cd frontend
```

**Install dependencies:**
```bash
npm install
```

**Start development server:**
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173` (or the port shown in terminal)

### 3. Access Dashboard

Open your browser and navigate to `http://localhost:5173`

The frontend will automatically refresh every 30 seconds to show the latest data.

## Features

### Profile View
- Trading mode (Paper/Live)
- Trading hours
- Lot sizes (Nifty/Sensex)
- Indicator settings (RSI threshold, periods)
- Risk management parameters

### Current Positions
- Real-time position tracking
- Entry price, current price, stop loss
- P&L calculation (absolute and percentage)
- Time in trade

### OI PCR Chart
- Put-Call Ratio for Nifty and Sensex
- Historical trend visualization
- Color-coded interpretation (Call Heavy / Neutral / Put Heavy)

### Daily Summary
- Total P&L
- Win rate
- Total trades
- Max win/loss
- Index-wise breakdown

## API Endpoints

All endpoints are read-only (GET requests only):

- `GET /api/profile` - Trading profile
- `GET /api/current-positions` - Current positions
- `GET /api/metrics/oi-pcr` - OI PCR data
- `GET /api/summary/today` - Daily summary
- `GET /api/health` - Health check

## Troubleshooting

### API Server Not Starting
- Make sure Flask and Flask-CORS are installed: `pip install flask flask-cors`
- Check that you're running from the correct directory (where `api_server.py` is located)
- Verify that your trading system modules are accessible

### Dashboard Can't Connect to API
- Ensure the API server is running on `http://localhost:5000`
- Check browser console for CORS errors
- Verify API URL in `.env` file matches your API server URL

### OI PCR Not Showing
- OI PCR calculation requires market data
- Make sure your trading system can fetch option data
- Check that expiry dates are correctly configured

## Production Deployment

### Build React App
```bash
cd frontend
npm run build
```

### Serve Static Files
The `dist` directory contains the built files. You can serve them using:
- Nginx
- Apache
- Any static file server

### API Server
For production, use a WSGI server like Gunicorn (from project root):
```bash
pip install gunicorn
PYTHONPATH=backend:api gunicorn -w 4 -b 0.0.0.0:5000 server:app
```

## Security Notes

- The frontend is **read-only** - no trading actions can be performed
- API endpoints don't expose sensitive credentials
- Consider adding authentication for production use
- Use HTTPS in production environments
