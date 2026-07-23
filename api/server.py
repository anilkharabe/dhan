"""
Flask API Server for Trading Dashboard
Provides read-only endpoints for React frontend
"""
import os
import sys

# Add backend to path so we can import config, data_manager, etc.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_backend = os.path.join(_root, "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from flask import Flask, jsonify, Response, request
from flask_cors import CORS
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
import json
import time
import threading
import queue
import requests as http_requests

# Import existing modules
import config
import logger
import pandas as pd
from order_manager import order_manager
from trade_tracker import trade_tracker
from data_manager import data_manager
from dhan_api import dhan_client
from indicators import Indicators
from mongo_logger import mongo_logger
from dhan_token_manager import dhan_token_manager
import trend_scanner

app = Flask(__name__)
# CORS_ALLOWED_ORIGINS: comma-separated list of allowed frontend origins in
# production (e.g. "https://dashboard.example.com"). Defaults to "*" for
# local dev, where the frontend runs on a different port than the API.
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "*")
_cors_origins = "*" if _cors_origins_env == "*" else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}}, supports_credentials=True)

# ============================================================================
# TOKEN MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/token-status', methods=['GET'])
def get_token_status():
    """Get status of the current access token"""
    return jsonify(dhan_token_manager.get_token_status())

@app.route('/api/login-url', methods=['GET'])
def get_login_url():
    """Get the Dhan web portal URL for manually generating a token"""
    url = dhan_token_manager.get_login_url()
    if url:
        return jsonify({"url": url})
    return jsonify({"error": "Configuration missing"}), 500

@app.route('/api/generate-token', methods=['POST'])
def generate_token():
    """
    Automatically generate a Dhan access token via PIN + TOTP
    (requires DHAN_PIN/DHAN_TOTP_SECRET to be configured - see .env).
    """
    result = dhan_token_manager.generate_access_token_via_totp()

    if result.get('success'):
        # Refresh global client tokens in this process
        new_token = config.DHAN_ACCESS_TOKEN
        dhan_client.set_access_token(new_token)
        if _ws_client:
            _ws_client.set_access_token(new_token)
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/save-token', methods=['POST'])
def save_token():
    """Save a manually provided access token"""
    data = request.json
    access_token = data.get('access_token')

    if not access_token:
        return jsonify({"error": "Access token is required"}), 400

    result = dhan_token_manager.save_manual_token(access_token)

    if result.get('success'):
        # Refresh global client tokens in this process
        dhan_client.set_access_token(access_token)
        if _ws_client:
            _ws_client.set_access_token(access_token)
        return jsonify(result)
    else:
        return jsonify(result), 400


# Store OI PCR history (fallback in-memory)
oi_pcr_history = {
    "NIFTY": [],
    "SENSEX": [],
    "BANKNIFTY": []
}

# BankNifty has no fixed weekday expiry (monthly-only) so resolving it means an
# actual Dhan API call (get_expiry_list) - cache it for the day rather than
# re-resolving on every poll of this endpoint.
_banknifty_expiry_cache = {"date": None, "resolved_on": None}

# ============================================================================
# LIVE TICK STREAMING (Dhan Live Market Feed → SSE)
# ============================================================================

from dhan_api import DhanWebSocketClient

# Global state for WebSocket tick relay
_ws_client = None
_ws_lock = threading.Lock()
_tick_queues = []  # List of queue.Queue for SSE clients
_tick_queues_lock = threading.Lock()
_latest_ticks = {}  # instrument_key -> latest tick data
_latest_ticks_lock = threading.Lock()
_last_relay_tick_time = 0  # Timestamp of last tick received via relay


def _broadcast_tick(tick_data: dict):
    """Broadcast a tick to all connected SSE clients and store latest."""
    # Create a copy to avoid modifying the original dict used by WebSocketClient
    tick = tick_data.copy()
    
    # Convert datetime objects or ISO strings to Unix timestamp (milliseconds) for JSON serialization
    if 'timestamp' in tick:
        if isinstance(tick['timestamp'], datetime):
            tick['timestamp'] = int(tick['timestamp'].timestamp() * 1000)
        elif isinstance(tick['timestamp'], str):
            try:
                # Handle ISO format string from JSON (e.g. from internal tick endpoint)
                # python 3.11+ supports 'Z' directly, but we replace it to be safe
                dt_str = tick['timestamp'].replace('Z', '+00:00')
                dt = datetime.fromisoformat(dt_str)
                tick['timestamp'] = int(dt.timestamp() * 1000)
            except ValueError:
                pass
    
    # Store latest tick
    with _latest_ticks_lock:
        _latest_ticks[tick['instrument_key']] = tick

    # DEBUG: Log what we are broadcasting
    print(f"[SSE] Broadcasing {tick_data.get('instrument_key')} ltp={tick_data.get('ltp')}")

    # Broadcast to all SSE clients
    with _tick_queues_lock:
        dead_queues = []
        for q in _tick_queues:
            try:
                q.put_nowait(tick)
            except queue.Full:
                dead_queues.append(q)
        for q in dead_queues:
            _tick_queues.remove(q)


def _broadcast_refresh():
    """Broadcast a refresh signal to all connected SSE clients."""
    refresh_signal = {"type": "refresh"}
    with _tick_queues_lock:
        dead_queues = []
        for q in _tick_queues:
            try:
                q.put_nowait(refresh_signal)
            except queue.Full:
                dead_queues.append(q)
        for q in dead_queues:
            _tick_queues.remove(q)
    print("[SSE] Broadcasted refresh signal to all clients")

def _start_ws_connection(instrument_keys: list):
    """Start or update the Dhan WebSocket connection using centralized DhanWebSocketClient."""
    global _ws_client

    with _ws_lock:
        try:
            # Check if we are receiving ticks via relay (backend).
            # If we've seen a tick in the last 30 seconds, don't try to connect our own WS.
            # This avoids running two competing WebSocket connections against the same token.
            global _last_relay_tick_time
            if time.time() - _last_relay_tick_time < 30:
                logger.info(f"[WS] Relay active (seen tick {time.time() - _last_relay_tick_time:.1f}s ago), skipping internal WS connection.")
                return True

            # Initialize if not exists or if token changed
            current_token = config.DHAN_ACCESS_TOKEN
            if _ws_client is None or _ws_client.access_token != current_token:
                if _ws_client:
                    logger.info("[WS] Token changed or client exists, recreating DhanWebSocketClient...")
                    _ws_client.disconnect()

                logger.info("[WS] Initializing DhanWebSocketClient with current token...")
                _ws_client = DhanWebSocketClient(
                    client_id=config.DHAN_CLIENT_ID,
                    access_token=current_token,
                    on_tick_callback=_broadcast_tick  # Pass our broadcaster directly!
                )

                # Connect
                if _ws_client.connect():
                    logger.info("[WS] Connected using centralized DhanWebSocketClient")
                else:
                    logger.error("[WS] Failed to connect DhanWebSocketClient")
                    return False

            # Subscribe to instruments regardless of connection state so they are tracked
            logger.info(f"[WS] Subscribing/Tracking {len(instrument_keys)} instruments...")
            _ws_client.subscribe(instrument_keys, mode="full", force=True)
            return True

        except Exception as e:
            logger.error(f"[WS] Error manipulating WebSocket connection: {e}")
            import traceback
            traceback.print_exc()
            return False


@app.route('/api/ws-subscribe')
def ws_subscribe():
    """SSE endpoint — streams live ticks from Dhan's WebSocket feed."""
    instruments_param = request.args.get('instruments', '')
    instrument_keys = [k.strip() for k in instruments_param.split(',') if k.strip()]

    if not instrument_keys:
        return jsonify({"error": "No instruments specified"}), 400

    # Start/update WebSocket connection
    _start_ws_connection(instrument_keys)

    def generate():
        q = queue.Queue(maxsize=500)
        with _tick_queues_lock:
            _tick_queues.append(q)

        try:
            # Send initial snapshot of latest ticks
            with _latest_ticks_lock:
                for key in instrument_keys:
                    if key in _latest_ticks:
                        yield f"data: {json.dumps(_latest_ticks[key])}\n\n"

            # Stream live ticks
            while True:
                try:
                    tick = q.get(timeout=30)
                    yield f"data: {json.dumps(tick)}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _tick_queues_lock:
                if q in _tick_queues:
                    _tick_queues.remove(q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.route('/api/positions-instruments', methods=['GET'])
def get_positions_instruments():
    """Get open positions with their instrument keys (for WebSocket subscription)."""
    try:
        mongo_positions = mongo_logger.get_open_positions()
        instruments = []
        for pos in mongo_positions:
            inst_key = pos.get('instrument_key', '')
            if inst_key:
                instruments.append({
                    'instrument_key': inst_key,
                    'symbol': pos.get('symbol', 'NIFTY'),
                    'option_type': pos.get('option_type'),
                    'strike': pos.get('strike'),
                    'stop_loss': pos.get('stop_loss'),
                    'entry_price': pos.get('entry_price'),
                    'strategy_tag': pos.get('strategy_tag', 'STRATEGY_A')
                })
            # Credit spreads have a second leg (the hedge) that also needs a live
            # feed - without this it never gets WebSocket-subscribed and its LTP
            # stays permanently stale on the frontend.
            far_inst_key = pos.get('far_instrument_key', '') if pos.get('is_spread') else ''
            if far_inst_key:
                instruments.append({
                    'instrument_key': far_inst_key,
                    'symbol': pos.get('symbol', 'NIFTY'),
                    'option_type': pos.get('far_option_type'),
                    'strike': pos.get('far_strike'),
                    'stop_loss': None,
                    'entry_price': pos.get('far_entry_price'),
                    'strategy_tag': pos.get('strategy_tag', 'STRATEGY_A')
                })
        return jsonify({"instruments": instruments})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/latest-ticks', methods=['GET'])
def get_latest_ticks():
    """Get the latest tick data for all subscribed instruments."""
    with _latest_ticks_lock:
        return jsonify({"ticks": dict(_latest_ticks)})

    return jsonify({"status": "signal_broadcast"}), 200

@app.route('/api/internal/tick', methods=['POST'])
def internal_tick():
    """Internal endpoint for backend to relay ticks to API server."""
    try:
        tick_data = request.json
        if not tick_data:
            return jsonify({"error": "No tick data"}), 400
            
        # Update relay activity timestamp
        global _last_relay_tick_time
        _last_relay_tick_time = time.time()
        
        # Broadcast to SSE clients
        _broadcast_tick(tick_data)
        
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/internal/refresh', methods=['POST'])
def internal_refresh():
    """Internal endpoint for backend to trigger a frontend refresh."""
    try:
        _broadcast_refresh()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/selected-instruments', methods=['GET'])
def get_selected_instruments():
    """Get the currently selected instruments (Nifty/Sensex strikes) from the backend state"""
    try:
        # Path to the shared state file
        state_file = os.path.join(_root, "backend", "system_state.json")
        
        # DEBUG: Print path checking
        print(f"DEBUG: Checking for state file at: {state_file}")
        print(f"DEBUG: File exists: {os.path.exists(state_file)}")
        print(f"DEBUG: Root is: {_root}")
        
        if not os.path.exists(state_file):
            return jsonify({"error": f"System state not available yet at {state_file}"}), 404
            
        with open(state_file, 'r') as f:
            state = json.load(f)
            
        return jsonify(state)
    except Exception as e:
        print(f"DEBUG: Error reading state file: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/historical-candles', methods=['GET'])
def get_historical_candles():
    """Get historical candles for a specific instrument."""
    try:
        instrument_key = request.args.get('instrument_key')
        interval = request.args.get('interval', config.CANDLE_INTERVAL)
        
        if not instrument_key:
            return jsonify({"error": "instrument_key is required"}), 400
            
        # 2. Fallback: Fetch from Dhan API via DataManager
        # This handles cases where data isn't in cache yet
        # Use get_combined_data to include previous days for indicators/charts
        df = data_manager.get_combined_data(instrument_key, previous_day_candles=5)
        
        if df is not None and not df.empty:
            # Calculate indicators before returning
            df = Indicators.calculate_all_indicators(df)
            
            # Check if we need to append a forming candle (for live trading)
            # Get latest price from WebSocket if available
            last_candle_time = df.index[-1]
            # current_time must be naive-but-IST-wall-clock to compare against
            # last_candle_time (same convention as ts_epoch below) - datetime.now()
            # would silently depend on the server's system timezone matching IST.
            if last_candle_time.tzinfo:
                current_time = datetime.now(last_candle_time.tzinfo)
            else:
                current_time = pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None).to_pydatetime()
            
            # If the last candle is old (more than 1 minute ago), try to append latest price
            if (current_time - last_candle_time).total_seconds() > 60:
                latest_price = data_manager.get_latest_price_from_websocket(instrument_key)
                if latest_price:
                    # Create a "forming" candle
                    # Round time to nearest minute bucket
                    forming_time = current_time.replace(second=0, microsecond=0)
                    
                    # Only append if it's newer than last candle
                    if forming_time > last_candle_time:
                         # Append directly to DataFrame or handle in list conversion
                         # Here we'll handle it during list conversion for simplicity
                         pass

            candles = []
            for ts, row in df.iterrows():
                # ts is a tz-naive Timestamp whose wall-clock value IS IST (converted
                # upstream in dhan_api.py). pandas' Timestamp.timestamp() assumes naive
                # timestamps are UTC (unlike stdlib datetime.timestamp(), which uses the
                # system's local tz) - localizing first gives the correct epoch so the
                # frontend's Asia/Kolkata conversion lands back on the true IST time.
                ts_epoch = ts.tz_localize('Asia/Kolkata').timestamp() if ts.tzinfo is None else ts.timestamp()
                candle = {
                    "time": int(ts_epoch),
                    "open": row['open'],
                    "high": row['high'],
                    "low": row['low'],
                    "close": row['close'],
                    "volume": row.get('volume', 0)
                }
                
                # Add indicators if they exist
                if 'vwap' in row and not pd.isna(row['vwap']):
                    candle['vwap'] = row['vwap']
                if 'rsi' in row and not pd.isna(row['rsi']):
                    candle['rsi'] = row['rsi']
                if 'adx' in row and not pd.isna(row['adx']):
                    candle['adx'] = row['adx']
                if 'oi' in row and not pd.isna(row['oi']):
                    candle['oi'] = row['oi']
                if 'oi_sma' in row and not pd.isna(row['oi_sma']):
                    candle['oi_sma'] = row['oi_sma']
                if 'volume_sma' in row and not pd.isna(row['volume_sma']):
                    candle['volume_sma'] = row['volume_sma']
                
                candles.append(candle)
                
            # Append forming candle if needed (Logic: if last candle in DB is older than current minute)
            # This ensures the chart shows the *current* price immediately
            latest_price = data_manager.get_latest_price_from_websocket(instrument_key)
            if latest_price:
                 last_ts = df.index[-1]
                 if last_ts.tzinfo:
                     current_ts = datetime.now(last_ts.tzinfo)
                 else:
                     current_ts = pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None).to_pydatetime()

                 # Logic for 1-minute candles
                 # If current time minute > last candle minute, we have a gap
                 if current_ts.minute != last_ts.minute or current_ts.hour != last_ts.hour or current_ts.day != last_ts.day:
                     # Same UTC-assumes-naive pitfall as ts_epoch above: localize
                     # explicitly instead of relying on datetime.timestamp()'s
                     # system-timezone assumption.
                     if last_ts.tzinfo:
                         forming_ts = int(current_ts.timestamp())
                     else:
                         forming_ts = int(pd.Timestamp(current_ts).tz_localize('Asia/Kolkata').timestamp())
                     # Snap to minute
                     forming_ts = forming_ts - (forming_ts % 60)
                     
                     last_ts_epoch = last_ts.tz_localize('Asia/Kolkata').timestamp() if last_ts.tzinfo is None else last_ts.timestamp()
                     if forming_ts > int(last_ts_epoch):
                         candles.append({
                             "time": forming_ts,
                             "open": latest_price,
                             "high": latest_price,
                             "low": latest_price,
                             "close": latest_price,
                             "volume": 0, # Placeholder
                             # Indicators will be missing for this forming candle, which is fine
                         })

            return jsonify({"candles": candles})
            
        # 3. If no data found
        return jsonify({"candles": []})
        
    except Exception as e:
        print(f"Error fetching historical candles: {str(e)}")
        return jsonify({"error": str(e)}), 500

def calculate_oi_pcr(symbol: str, expiry_date: str) -> Optional[Dict[str, float]]:
    """
    Calculate Put-Call Ratio (PCR) for an index - {'atm5': ..., 'full': ...}
    Delegates to data_manager for calculation
    """
    return data_manager.calculate_oi_pcr(symbol, expiry_date)

@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get the trading profile and status."""
    try:
        profile = {
            "mode": "PAPER_TRADING" if config.PAPER_TRADING else "LIVE_TRADING",
            "initial_balance": getattr(config, 'INITIAL_VIRTUAL_FUND', 100000),
            "test_mode": config.TEST_MODE,
            "demo_mode": config.DEMO_MODE,
            "trading_hours": {
                "start": config.TRADING_START_TIME.strftime("%H:%M:%S"),
                "end": config.TRADING_END_TIME.strftime("%H:%M:%S")
            },
            "trading_days": {
                "nifty": config.NIFTY_TRADING_DAYS,
                "sensex": config.SENSEX_TRADING_DAYS
            },
            "lot_sizes": {
                "nifty": config.NIFTY_LOT_SIZE,
                "sensex": config.SENSEX_LOT_SIZE
            },
            "strike_intervals": {
                "nifty": config.NIFTY_STRIKE_INTERVAL,
                "sensex": config.SENSEX_STRIKE_INTERVAL
            },
            "indicators": {
                "rsi_threshold": config.RSI_THRESHOLD,
                "rsi_period": config.RSI_PERIOD,
                "oi_sma_period": config.SMA_OI_PERIOD
            },
            "risk_management": {
                "stop_loss_method": "t-2_candle_low",
                "max_positions": 4
            }
        }
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/current-positions', methods=['GET'])
def get_current_positions():
    """Get all current open positions"""
    try:
        positions = []
        
        # Read from MongoDB (shared between backend and API processes)
        mongo_positions = mongo_logger.get_open_positions()
        
        for pos in mongo_positions:
            lot_size = pos.get('lot_size', 1)
            entry_time = pos.get('entry_time')
            time_str = "N/A"
            if entry_time:
                time_in_trade = datetime.now() - entry_time
                hours = int(time_in_trade.total_seconds() // 3600)
                minutes = int((time_in_trade.total_seconds() % 3600) // 60)
                time_str = f"{hours}h {minutes}m"

            if pos.get('is_spread'):
                near_price = dhan_client.get_current_price(pos['instrument_key']) if pos.get('instrument_key') else None
                far_price = dhan_client.get_current_price(pos['far_instrument_key']) if pos.get('far_instrument_key') else None
                net_credit = pos.get('net_credit', 0) or 0
                net_spread_value = (near_price - far_price) if (near_price is not None and far_price is not None) else None
                pnl = ((net_credit - net_spread_value) * lot_size) if net_spread_value is not None else None
                pnl_percent = (pnl / (net_credit * lot_size) * 100) if (pnl is not None and net_credit > 0 and lot_size > 0) else None

                positions.append({
                    "symbol": pos.get('symbol', 'NIFTY'),
                    "is_spread": True,
                    "spread_type": pos.get('spread_type', ''),
                    "option_type": pos.get('option_type'),  # sold/near leg
                    "strike": pos.get('strike'),
                    "instrument_key": pos.get('instrument_key', ''),
                    "entry_price": round(pos.get('entry_price', 0), 2),
                    "far_option_type": pos.get('far_option_type', ''),
                    "far_strike": pos.get('far_strike'),
                    "far_instrument_key": pos.get('far_instrument_key', ''),
                    "far_entry_price": round(pos.get('far_entry_price', 0) or 0, 2),
                    "current_near_price": round(near_price, 2) if near_price is not None else None,
                    "current_far_price": round(far_price, 2) if far_price is not None else None,
                    "net_credit": round(net_credit, 2),
                    "net_spread_value": round(net_spread_value, 2) if net_spread_value is not None else None,
                    "stop_loss_value": round(pos.get('stop_loss_value', 0) or 0, 2),
                    "profit_target_value": round(pos.get('profit_target_value', 0) or 0, 2),
                    "trailing_active": pos.get('trailing_active', False),
                    "expiry": pos.get('expiry_date', ''),
                    "lot_size": lot_size,
                    "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else "N/A",
                    "time_in_trade": time_str,
                    "pnl": round(pnl, 2) if pnl is not None else None,
                    "pnl_percent": round(pnl_percent, 2) if pnl_percent is not None else None,
                    "status": "OPEN",
                    "strategy_tag": pos.get('strategy_tag', 'N/A')
                })
                continue

            # Get current price if instrument_key is available
            current_price = None
            if pos.get('instrument_key'):
                current_price = dhan_client.get_current_price(pos['instrument_key'])

            # Calculate P&L
            entry_price = pos.get('entry_price', 0)
            entry_value = entry_price * lot_size
            current_value = current_price * lot_size if current_price else entry_value
            pnl = current_value - entry_value
            pnl_percent = (pnl / entry_value * 100) if entry_value > 0 else 0

            positions.append({
                "symbol": pos.get('symbol', 'NIFTY'),
                "is_spread": False,
                "option_type": pos.get('option_type'),
                "strike": pos.get('strike'),
                "instrument_key": pos.get('instrument_key', ''),
                "expiry": pos.get('expiry_date', ''),
                "entry_price": round(entry_price, 2),
                "current_price": round(current_price, 2) if current_price else None,
                "stop_loss": round(pos.get('stop_loss', 0), 2),
                "lot_size": lot_size,
                "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else "N/A",
                "time_in_trade": time_str,
                "pnl": round(pnl, 2),
                "pnl_percent": round(pnl_percent, 2),
                "status": "OPEN",
                # Profit booking fields
                "profit_stage": pos.get('profit_stage', 0),
                "remaining_lot_size": pos.get('remaining_lot_size', lot_size),
                "original_lot_size": pos.get('original_lot_size', lot_size),
                "trailing_active": pos.get('trailing_active', False),
                "highest_price": round(pos.get('highest_price', entry_price), 2),
                "original_stop_loss": round(pos.get('original_stop_loss', pos.get('stop_loss', 0)), 2),
                "strategy_tag": pos.get('strategy_tag', 'N/A')
            })
        
        return jsonify({"positions": positions, "count": len(positions)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _format_pcr_history(raw_history):
    """Convert mongo_logger's {timestamp, value, value_full} docs into the
    API's {timestamp, atm5, full} shape."""
    return [
        {
            'timestamp': h['timestamp'],
            'atm5': h.get('value'),
            'full': h.get('value_full'),  # None for historical backfilled points
        }
        for h in raw_history
    ]


@app.route('/api/metrics/oi-pcr', methods=['GET'])
def get_oi_pcr():
    """Get OI PCR for Nifty and Sensex - both an ATM+-5 windowed value and the
    full option-chain value (matches Upstox/NSE - see calculate_oi_pcr)."""
    try:
        nifty_atm5, nifty_full = None, None

        # 1. NIFTY
        try:
            # Try to compute live if within trading hours (or always for now)
            try:
                nifty_expiry = data_manager.get_expiry_date(datetime.now(), config.NIFTY_EXPIRY_DAY)
                pcr = calculate_oi_pcr("NIFTY", nifty_expiry)

                if pcr is not None:
                    nifty_atm5, nifty_full = pcr['atm5'], pcr['full']
                    # Note: Logging is handled by the backend scheduler (main.py)
                    # mongo_logger.log_oi_pcr(datetime.utcnow(), "NIFTY", nifty_atm5, nifty_full)
            except Exception as e:
                print(f"Nifty live calc failed: {e}")

            # Retrieve history from DB
            nifty_history = _format_pcr_history(mongo_logger.get_oi_pcr_history("NIFTY"))

            # If live calc failed, use latest from DB as current
            if nifty_atm5 is None and nifty_history:
                nifty_atm5 = nifty_history[-1]['atm5']
                nifty_full = nifty_history[-1]['full']

            # If MongoDB disabled, fallback to in-memory (legacy)
            if not nifty_history and oi_pcr_history.get("NIFTY"):
                 nifty_history = _format_pcr_history(oi_pcr_history["NIFTY"][-100:])
                 if nifty_atm5 is None and nifty_history:
                     nifty_atm5 = nifty_history[-1]['atm5']
                     nifty_full = nifty_history[-1]['full']

        except Exception as e:
            print(f"Error handling Nifty PCR: {str(e)}")
            nifty_history = []

        # 2. SENSEX
        sensex_atm5, sensex_full = None, None
        try:
            if config.SENSEX_ENABLED:
                try:
                    sensex_expiry = data_manager.get_expiry_date(datetime.now(), config.SENSEX_EXPIRY_DAY)
                    pcr = calculate_oi_pcr("SENSEX", sensex_expiry)

                    if pcr is not None:
                        sensex_atm5, sensex_full = pcr['atm5'], pcr['full']
                        # mongo_logger.log_oi_pcr(datetime.utcnow(), "SENSEX", sensex_atm5, sensex_full)
                except Exception as e:
                    print(f"Sensex live calc failed: {e}")

                sensex_history = _format_pcr_history(mongo_logger.get_oi_pcr_history("SENSEX"))

                if sensex_atm5 is None and sensex_history:
                    sensex_atm5 = sensex_history[-1]['atm5']
                    sensex_full = sensex_history[-1]['full']

                if not sensex_history and oi_pcr_history.get("SENSEX"):
                     sensex_history = _format_pcr_history(oi_pcr_history["SENSEX"][-100:])
                     if sensex_atm5 is None and sensex_history:
                         sensex_atm5 = sensex_history[-1]['atm5']
                         sensex_full = sensex_history[-1]['full']
            else:
                sensex_history = []
        except Exception as e:
            print(f"Error handling Sensex PCR: {str(e)}")
            sensex_history = []

        # 3. BANKNIFTY (monitoring only - not traded, so no NIFTY_ENABLED-style gate)
        banknifty_atm5, banknifty_full = None, None
        try:
            if config.BANKNIFTY_PCR_ENABLED:
                try:
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    if _banknifty_expiry_cache["resolved_on"] != today_str or not _banknifty_expiry_cache["date"]:
                        _banknifty_expiry_cache["date"] = data_manager.get_nearest_expiry_from_list(config.BANKNIFTY_INDEX_SYMBOL)
                        _banknifty_expiry_cache["resolved_on"] = today_str

                    banknifty_expiry = _banknifty_expiry_cache["date"]
                    if banknifty_expiry:
                        pcr = calculate_oi_pcr("BANKNIFTY", banknifty_expiry)
                        if pcr is not None:
                            banknifty_atm5, banknifty_full = pcr['atm5'], pcr['full']
                except Exception as e:
                    print(f"BankNifty live calc failed: {e}")

                banknifty_history = _format_pcr_history(mongo_logger.get_oi_pcr_history("BANKNIFTY"))

                if banknifty_atm5 is None and banknifty_history:
                    banknifty_atm5 = banknifty_history[-1]['atm5']
                    banknifty_full = banknifty_history[-1]['full']

                if not banknifty_history and oi_pcr_history.get("BANKNIFTY"):
                    banknifty_history = _format_pcr_history(oi_pcr_history["BANKNIFTY"][-100:])
                    if banknifty_atm5 is None and banknifty_history:
                        banknifty_atm5 = banknifty_history[-1]['atm5']
                        banknifty_full = banknifty_history[-1]['full']
            else:
                banknifty_history = []
        except Exception as e:
            print(f"Error handling BankNifty PCR: {str(e)}")
            banknifty_history = []

        return jsonify({
            "nifty": {
                "current_atm5": nifty_atm5,
                "current_full": nifty_full,
                "history": nifty_history
            },
            "sensex": {
                "current_atm5": sensex_atm5,
                "current_full": sensex_full,
                "history": sensex_history
            },
            "banknifty": {
                "current_atm5": banknifty_atm5,
                "current_full": banknifty_full,
                "history": banknifty_history
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/scanner/trend', methods=['GET'])
def get_trend_scanner():
    """Full-day (9:15-15:30) OI/PCR + VWAP history table for one symbol at a
    time (NIFTY/SENSEX/BANKNIFTY), at 5-min or 15-min spacing. Informational
    only - does not feed the credit-spread entry gate. See
    backend/trend_scanner.py. Non-blocking: on a cache miss/expiry this kicks
    off the (30s-4min) reconstruction in a background thread and returns
    `{"status": "building"}` immediately - the frontend polls this same
    endpoint every few seconds until `{"status": "ready", "rows": [...]}`
    comes back. Deliberately NOT held open for the full rebuild duration:
    a request that long would occupy one of the browser's ~6 per-origin
    HTTP/1.1 connection slots for minutes, starving unrelated polling (e.g.
    TokenStatus) - confirmed live 2026-07-22."""
    symbol = request.args.get('symbol', 'NIFTY').upper()
    timeframe = request.args.get('timeframe', '15min')

    if symbol not in trend_scanner.SYMBOLS:
        return jsonify({"error": f"Unknown symbol: {symbol}"}), 400
    if timeframe not in trend_scanner.TIMEFRAMES:
        return jsonify({"error": f"timeframe must be one of {list(trend_scanner.TIMEFRAMES)}"}), 400

    try:
        result = trend_scanner.get_symbol_history(symbol, timeframe)
        if result is None:
            return jsonify({"symbol": symbol, "timeframe": timeframe, "rows": [], "message": "No data available yet"})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summary/today', methods=['GET'])
def get_daily_summary():
    """Get today's trading summary"""
    try:
        # Sync trades from MongoDB (since we are in a separate process)
        trade_tracker.sync_from_db()
        
        summary = trade_tracker.get_summary()
        
        # Get current positions count (correctly iterating through lists)
        positions_count = sum(
            len(positions) for symbol_pos in order_manager.active_positions.values()
            for positions in symbol_pos.values()
        )
        
        return jsonify({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_trades": summary.get('total_trades', 0),
            "winning_trades": summary.get('winning_trades', 0),
            "losing_trades": summary.get('losing_trades', 0),
            "win_rate": summary.get('win_rate', 0),
            "total_pnl": summary.get('total_pnl', 0),
            "nifty_pnl": summary.get('nifty_pnl', 0),
            "sensex_pnl": summary.get('sensex_pnl', 0),
            "current_positions": positions_count,
            "max_win": summary.get('max_win', 0),
            "max_loss": summary.get('max_loss', 0),
            "strategy_wise": summary.get('strategy_wise', {})
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/performance/history', methods=['GET'])
def get_performance_history():
    """Get historical performance stats for charts"""
    try:
        days = int(request.args.get('days', 30))
        stats = mongo_logger.get_historical_stats(days)
        return jsonify({"history": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/performance/day', methods=['GET'])
def get_day_performance():
    """Get details for a specific date"""
    try:
        date_str = request.args.get('date')
        if not date_str:
            return jsonify({"error": "Date parameter required"}), 400
            
        details = mongo_logger.get_day_details(date_str)
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/trades/history', methods=['GET'])
def get_trades_history():
    """Get history of all trades for today (including closed ones)"""
    try:
        # Sync trades from MongoDB
        trade_tracker.sync_from_db()
        
        # Sort trades by exit_time (descending) or entry_time if not closed
        trades_list = []
        for t in trade_tracker.trades:
            # Format times for JSON
            entry_time = t.get('entry_time')
            exit_time = t.get('exit_time')
            
            trade_data = t.copy()
            if isinstance(entry_time, datetime):
                trade_data['entry_time'] = entry_time.strftime("%H:%M:%S")
            if isinstance(exit_time, datetime):
                trade_data['exit_time'] = exit_time.strftime("%H:%M:%S")
            
            # Format times in partial exits
            if 'partial_exits' in trade_data:
                formatted_pe = []
                for pe in trade_data['partial_exits']:
                    pe_copy = pe.copy()
                    pe_time = pe_copy.get('exit_time')
                    if isinstance(pe_time, datetime):
                        pe_copy['exit_time'] = pe_time.strftime("%H:%M:%S")
                    formatted_pe.append(pe_copy)
                trade_data['partial_exits'] = formatted_pe
            
            # Ensure pnl and pnl_percent are rounded
            if trade_data.get('pnl') is not None:
                trade_data['pnl'] = round(trade_data['pnl'], 2)
            if trade_data.get('pnl_percent') is not None:
                trade_data['pnl_percent'] = round(trade_data['pnl_percent'], 2)
                
            trades_list.append(trade_data)
            
        # Sort: Closed trades first, then by time descending
        trades_list.sort(key=lambda x: (x.get('status') == 'OPEN', x.get('exit_time') or x.get('entry_time')), reverse=True)
            
        return jsonify({"trades": trades_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    ws_status = "connected" if (_ws_client and _ws_client.is_connected()) else "disconnected"
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "websocket": ws_status,
        "subscribed_instruments": list(_ws_client.subscribed_instruments) if _ws_client else [],
        "sse_clients": len(_tick_queues),
    })

@app.route('/api/admin/reset-positions', methods=['POST'])
def reset_positions():
    """Manually close all open positions"""
    try:
        count = mongo_logger.close_all_open_positions(reason="Manual Admin Reset")
        return jsonify({"message": f"Closed {count} positions", "count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/clear-today', methods=['POST'])
def clear_today():
    """Clear all data for today"""
    try:
        success = mongo_logger.clear_todays_data()
        if success:
            return jsonify({"message": "Cleared all data for today"})
        else:
            return jsonify({"error": "Failed to clear data"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# BACKTEST ENDPOINTS
# ============================================================================

@app.route('/api/backtest/fetch-candles', methods=['POST'])
def backtest_fetch_candles():
    """
    Trigger post-market candle fetch for a given date.
    Runs fetch_day_candles.py as a subprocess and streams its output.
    Body JSON: { "date": "YYYY-MM-DD" }   (optional, defaults to today)
    """
    import subprocess
    import os as _os

    data = request.json or {}
    date_arg = data.get('date', datetime.now().strftime('%Y-%m-%d'))

    script = _os.path.join(_backend, 'fetch_day_candles.py')

    def generate():
        try:
            # Use sys.executable (the interpreter running this server) rather than
            # a hardcoded "python3" - that command doesn't exist on Windows by
            # default and gets redirected to the Microsoft Store stub instead.
            # PYTHONIOENCODING forces the CHILD's stdout to be UTF-8 from process
            # startup (fetch_day_candles.py prints emoji before it ever imports
            # anything that could reconfigure the stream itself); encoding='utf-8'
            # makes the PARENT decode those bytes correctly instead of via the
            # Windows locale default (cp1252), which was producing mojibake.
            child_env = _os.environ.copy()
            child_env['PYTHONIOENCODING'] = 'utf-8'
            proc = subprocess.Popen(
                [sys.executable, script, date_arg],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=_root,
                env=child_env
            )
            for line in proc.stdout:
                yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            proc.wait()
            status = 'success' if proc.returncode == 0 else 'error'
            yield f"data: {json.dumps({'done': True, 'status': status, 'returncode': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'done': True, 'status': 'error', 'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/api/backtest/run', methods=['POST'])
def backtest_run():
    """
    Run the credit-spread backtest simulation for a given date.
    Body JSON: { "date": "YYYY-MM-DD", "scenarios": ["CREDIT_SPREAD"] }
    Returns: metrics + per-trade details
    """
    try:
        data = request.json or {}
        date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        requested_scenarios = data.get('scenarios', ['CREDIT_SPREAD'])

        from credit_spread_backtest import run_credit_spread_backtest

        all_results = {}

        for scenario_key in requested_scenarios:
            if scenario_key != "CREDIT_SPREAD":
                continue
            try:
                # Self-contained simulation, fetches its own candles on demand
                # (hedge legs sit outside the ATM+-4 pre-fetch range) - see
                # credit_spread_backtest.py.
                result = run_credit_spread_backtest(date_str)
                scenario_name = result['scenario_name']

                metrics = result.get('metrics', {})
                trades  = result.get('trades', [])

                # Serialize trades (dates/datetimes → strings)
                serialized_trades = []
                for t in trades:
                    td = {}
                    for k, v in t.items():
                        if isinstance(v, datetime):
                            td[k] = v.strftime('%H:%M:%S')
                        else:
                            td[k] = v
                    serialized_trades.append(td)

                all_results[scenario_key] = {
                    'scenario_name': scenario_name,
                    'metrics': metrics,
                    'trades': serialized_trades,
                }
            except Exception as e:
                all_results[scenario_key] = {
                    'scenario_name': scenario_key,
                    'error': str(e),
                    'metrics': {},
                    'trades': [],
                }

        return jsonify({'date': date_str, 'results': all_results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest/candle-status', methods=['GET'])
def backtest_candle_status():
    """Check if candle data exists for a given date in MongoDB."""
    try:
        date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        log = mongo_logger.candle_fetch_log.find_one({'date': date_str}, {'_id': 0})
        if log:
            if 'fetched_at' in log and isinstance(log['fetched_at'], datetime):
                log['fetched_at'] = log['fetched_at'].isoformat()
            return jsonify({'has_data': True, 'fetch_log': log})
        else:
            # Check if any candles exist for this date even without a log entry
            count = mongo_logger.option_1min_candles.count_documents({'date': date_str})
            return jsonify({'has_data': count > 0, 'candle_count': count, 'fetch_log': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':

    print("Starting Flask API Server...")
    print("API will be available at http://localhost:5000")
    print("\nEndpoints:")
    print("  GET /api/profile")
    print("  GET /api/current-positions")
    print("  GET /api/positions-instruments")
    print("  GET /api/ws-subscribe?instruments=KEY1,KEY2  (SSE stream)")
    print("  GET /api/latest-ticks")
    print("  GET /api/metrics/oi-pcr")
    print("  GET /api/scanner/trend")
    print("  GET /api/summary/today")
    print("  GET /api/health")
    print("\nPress Ctrl+C to stop")

    # Local dev only - see wsgi.py for the production entry point.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, threaded=True)
