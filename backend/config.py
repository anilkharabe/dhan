"""
Configuration file for Nifty Options Algo Trading
Contains all trading parameters, API credentials, and settings
"""

import os
from datetime import time
from dotenv import load_dotenv

# ============================================================================
# LOAD ENVIRONMENT VARIABLES FROM .env FILE
# ============================================================================

# BASE_DIR = backend/; PROJECT_ROOT = project root (parent of backend)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
# Load .env from project root so backend and api share one .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ============================================================================
# TRADING PARAMETERS
# ============================================================================

# Paper Trading Mode
PAPER_TRADING = True  # Set to False for live trading

# Test Mode (bypass all time/day checks for testing)
TEST_MODE = False  # Set to True to test outside market hours

# Demo Mode (for testing without Dhan API credentials)
# When enabled, uses mock candle data for options if API fails
# Note: Still attempts to fetch real Nifty price first
DEMO_MODE = False  # Set to True to use mock data for testing
DEMO_NIFTY_PRICE = 23500.0  # Fallback Nifty price if API unavailable

# Trading Schedule
# You can start the script anytime between market open and close
# The system will automatically begin trading at TRADING_START_TIME
MARKET_OPEN_TIME = time(9, 15, 0)    # Market opens at 9:15 AM
TRADING_START_TIME = time(9, 45, 0)  # Start trading at 9:45 AM (after sufficient candles)
ENTRY_END_TIME = time(15, 15, 0)     # No new entries after 3:15 PM
TRADING_END_TIME = time(15, 25, 0)   # Final square off at 3:25 PM

# Note: You can run the script anytime between 9:15 AM and 3:15 PM
# If started before 10:00 AM, it will wait until 10:00 AM to begin trading
# If started after 10:00 AM, it will start trading immediately

# Trading Days (0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday)
# Nifty: Trade on Friday, Monday, Tuesday (expiry is Tuesday)
NIFTY_TRADING_DAYS = [0, 1, 4]  # Monday, Tuesday, Friday

# Sensex: Trade on Wednesday, Thursday (expiry is Thursday)
SENSEX_TRADING_DAYS = [2, 3]  # Wednesday, Thursday

# Backward compatibility - uses combined days
ALLOWED_TRADING_DAYS = list(set(NIFTY_TRADING_DAYS + SENSEX_TRADING_DAYS))  # All unique days

# Override for testing (allows trading on any day)
SKIP_DAY_CHECK = False  # Set to True to test on any day


# WARNING: Only use for development/testing! Set to False for live trading

# ============================================================================
# MONGODB CONFIGURATION (for data storage and backtesting)
# ============================================================================

# MongoDB connection
MONGODB_ENABLED = True  # Enable MongoDB logging
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")  # Load from .env or default to local
# For remote MongoDB: mongodb://username:password@host:port/
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "nifty_algo_trading")  # Load from .env or default

# What to log to MongoDB
LOG_NIFTY_SPOT = True  # Log Nifty spot price every 3 min
LOG_OPTION_CANDLES = True  # Log option OHLCV + indicators
LOG_SIGNALS = True  # Log all signals (taken or rejected)
LOG_TRADES = True  # Log all trade executions
LOG_SYSTEM_EVENTS = True  # Log system start/stop/errors

# Timeframe
CANDLE_INTERVAL = "1minute"  # 1-minute candles
CANDLE_INTERVAL_SECONDS = 60  # 1 minute in seconds

# Strike Selection
NIFTY_STRIKE_INTERVAL = 50  # Nifty strikes are in 50-point intervals
# No longer consulted by data_manager.determine_atm_strikes() - that function now
# always picks nearest-OTM strikes (including on expiry day) for the credit-spread
# strategy. Left defined only so other code referencing it doesn't break.
USE_ITM_ON_EXPIRY_DAY = True

# Indicator Parameters
RSI_PERIOD = 14
RSI_THRESHOLD = 40  # Entry requires RSI below this value
SMA_OI_PERIOD = 20
SMA_VOLUME_PERIOD = 20  # Volume SMA period
ADX_PERIOD = 14
ADX_THRESHOLD = 25
ADX_MUST_BE_RISING = True  # ADX must be rising to confirm trend strength
ADX_SLOPE_PERIOD = 1       # Compare ADX with value 1 candle ago

# Volume Confirmation
VOLUME_CONFIRMATION_ENABLED = False  # Disabled - volume filter too strict for current market
VOLUME_THRESHOLD_PERCENT = 120  # Current volume must be 120% of SMA (i.e., 1.2x average)

# Historical Data
PREVIOUS_DAY_CANDLES = 5  # Number of candles to fetch from previous day

# Position Management
# Multi-Index Position Limits
MAX_NIFTY_CALL_POSITIONS = 1
MAX_NIFTY_PUT_POSITIONS = 1
MAX_SENSEX_CALL_POSITIONS = 1
MAX_SENSEX_PUT_POSITIONS = 1

# Total: 4 positions max (2 Nifty + 2 Sensex)

# Backward compatibility
MAX_CALL_POSITIONS = MAX_NIFTY_CALL_POSITIONS
MAX_PUT_POSITIONS = MAX_NIFTY_PUT_POSITIONS

# Number of lots per trade, per index (multiplied by index-specific lot size)
NIFTY_LOT_MULTIPLIER = 5   # 5 lots x 65 = 325 qty
SENSEX_LOT_MULTIPLIER = 8  # 8 lots x 20 = 160 qty
INITIAL_VIRTUAL_FUND = 900000  # Initial trading account balance (1,00,000 per strategy x 9)

# ============================================================================
# CREDIT SPREAD CONFIGURATION
# ============================================================================
# Defined-risk vertical spreads: sell a near strike, buy a further-OTM strike as a
# hedge. The OI-divergence signal engine determines direction - a CALL signal
# sells a Bull Put Spread; a PUT signal sells a Bear Call Spread.
# See order_manager.py:place_credit_spread().

# Hedge leg distance from the sold strike, in index points (sets max loss = width - net credit)
SPREAD_WIDTH_NIFTY = 400
SPREAD_WIDTH_SENSEX = 1000

# Stop loss: based on the SOLD (near) leg's own premium, not net credit -
# exit when that leg's price reaches (1 + pct/100) x what it was sold for.
# e.g. 20 -> sold near leg at 100 -> SL at 120 (ignores hedge leg cost/movement).
CREDIT_SPREAD_SL_PERCENT = 20

# Profit target: exit when cost-to-close (near - far) has decayed to
# (1 - pct/100) x net credit received. e.g. 90 -> lock in gains once 90% of the
# max possible profit has been captured (net credit of 100 -> target at 10).
CREDIT_SPREAD_PROFIT_TARGET_PERCENT = 90

# Single strategy config to start (not run in parallel with multiple risk profiles yet).
# Kept as a dict (not a single flat config) so main.py's existing
# `for strat_tag, strat_conf in strategies.items()` loop pattern is reused unchanged.
CREDIT_SPREAD_STRATEGIES = {
    "CREDIT_A": {
        "name": "Credit Spread",
        "enabled": True,
        "sl_percent": CREDIT_SPREAD_SL_PERCENT,
        "profit_target_percent": CREDIT_SPREAD_PROFIT_TARGET_PERCENT,
    }
}


# ============================================================================
# DHAN API CREDENTIALS
# ============================================================================
# Dhan is the sole broker: order execution, live LTP, and OI/option-chain data
# all go through DhanHQ v2. See dhan_api.py / dhan_token_manager.py.

DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")  # ~24h validity, regenerated daily

# Optional: enables unattended daily token refresh via generate_dhan_token.py
# (PIN + TOTP secret from Dhan's API automation settings). Leave blank to fall
# back to manually pasting a token from the Dhan web portal.
DHAN_PIN = os.getenv("DHAN_PIN", "")
DHAN_TOTP_SECRET = os.getenv("DHAN_TOTP_SECRET", "")

# Scrip/instrument master (security IDs) - downloaded and cached daily
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# ============================================================================
# TELEGRAM CONFIGURATION
# ============================================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") 
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "") 
TELEGRAM_ENABLED = True  # Set to True when token is added

# Notification Settings
NOTIFY_TRADE_ENTRY = True
NOTIFY_TRADE_EXIT = True
NOTIFY_ERRORS = True
NOTIFY_DAILY_SUMMARY = True

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_LEVEL = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_TO_FILE = True
LOG_TO_CONSOLE = True

# ============================================================================
# FILE PATHS (BASE_DIR set above)
# ============================================================================

CHARTS_DIR = os.path.join(BASE_DIR, "charts")
TRADE_LOGS_DIR = os.path.join(BASE_DIR, "trade_logs")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Create directories if they don't exist
for directory in [CHARTS_DIR, TRADE_LOGS_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# ============================================================================
# MULTI-INDEX TRADING (NIFTY + SENSEX)
# ============================================================================

# Enable/Disable Indices
NIFTY_ENABLED = True
SENSEX_ENABLED = True  # Set to False to trade only Nifty

# ============================================================================
# NIFTY CONFIGURATION
# ============================================================================

# Nifty Symbol
# Composite Dhan key "{exchange_segment}|{security_id}" - security_id 13 = NIFTY
# index (IDX_I segment), confirmed against Dhan's scrip master.
NIFTY_INDEX_SYMBOL = "IDX_I|13"
NIFTY_EXCHANGE = "NSE_FNO"
NIFTY_STRIKE_INTERVAL = 50
NIFTY_LOT_SIZE = 65  # Nifty 50 lot size (65 shares per lot)

# Nifty Expiry
NIFTY_EXPIRY_DAY = 1  # Tuesday (0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday)

# ============================================================================
# SENSEX CONFIGURATION  
# ============================================================================

# Sensex Symbol
# Composite Dhan key "{exchange_segment}|{security_id}" - security_id 51 = SENSEX
# index (IDX_I segment), confirmed against Dhan's scrip master.
SENSEX_INDEX_SYMBOL = "IDX_I|51"
SENSEX_EXCHANGE = "BSE_FNO"
SENSEX_STRIKE_INTERVAL = 100  # Sensex strikes in 100-point intervals
SENSEX_LOT_SIZE = 20  # Sensex lot size is 20

# Sensex Expiry
SENSEX_EXPIRY_DAY = 3  # Thursday (0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday)

# ============================================================================
# BANKNIFTY CONFIGURATION (OI-PCR monitoring only - not traded by this system)
# ============================================================================

# Bank Nifty Symbol
# Composite Dhan key "{exchange_segment}|{security_id}" - security_id 25 = BANKNIFTY
# index (IDX_I segment), confirmed against a live download of Dhan's scrip master.
BANKNIFTY_INDEX_SYMBOL = "IDX_I|25"
BANKNIFTY_EXCHANGE = "NSE_FNO"
# Strikes are listed at 100-point spacing near the money (confirmed against the
# live option chain for the nearest expiry); wider bands only appear far OTM.
BANKNIFTY_STRIKE_INTERVAL = 100
BANKNIFTY_LOT_SIZE = 30  # Confirmed against live scrip master (SEM_LOT_UNITS)

# Bank Nifty options are monthly-only (no weekly expiry) - confirmed against the
# live scrip master, which only lists last-Tuesday-of-month expiries. There's no
# fixed weekday offset to compute like NIFTY_EXPIRY_DAY/SENSEX_EXPIRY_DAY; the
# nearest expiry is resolved at runtime from Dhan's expiry-list API instead
# (see data_manager.get_nearest_expiry_from_list).
BANKNIFTY_PCR_ENABLED = True

# ============================================================================
# BACKWARD COMPATIBILITY (Keep existing NIFTY configs)
# ============================================================================

# Legacy config - maps to Nifty for backward compatibility
INDEX_SYMBOL = NIFTY_INDEX_SYMBOL
NIFTY_SYMBOL = "NIFTY"
STRIKE_INTERVAL = NIFTY_STRIKE_INTERVAL  # Will be selected based on active index

# ============================================================================
# CANDLE FETCH (post-market historical data collection for backtesting)
# ============================================================================

# Strikes to fetch around ATM (ATM ± N).  N=4 → 9 strikes per side.
FETCH_STRIKES_AROUND_ATM = 4

# Delay (seconds) between API calls to respect Dhan rate limits
CANDLE_FETCH_RATE_LIMIT_SECS = 0.15

# ============================================================================
# CHART CONFIGURATION
# ============================================================================

CHART_CANDLES_TO_DISPLAY = 40  # Number of candles to show in chart
CHART_DPI = 100
CHART_FIGSIZE = (16, 12)
GENERATE_CHARTS = False  # Set to False to disable chart generation
GENERATE_DAILY_SUMMARY_CHART = True

# ============================================================================
# DATA MANAGEMENT
# ============================================================================

# Cache settings
CACHE_HISTORICAL_DATA = True
MAX_CACHE_AGE_MINUTES = 5

# ============================================================================
# WEBSOCKET CONFIGURATION (V3)
# ============================================================================

# Enable WebSocket for real-time tick data
USE_WEBSOCKET = True  # Set to True to enable WebSocket (start with False for safety)
WEBSOCKET_MODE = "full"  # Options: "ltpc", "full", "option_greeks", "full_d30"

# Tick Aggregation
TICK_BUFFER_SIZE = 1000  # Maximum ticks to buffer before aggregation
CANDLE_AGGREGATION_INTERVAL = 60  # 1 minute in seconds (same as CANDLE_INTERVAL_SECONDS)

# Connection Settings
WEBSOCKET_PING_INTERVAL = 30  # Heartbeat interval in seconds
WEBSOCKET_RECONNECT_ATTEMPTS = 5
WEBSOCKET_RECONNECT_DELAY = 5  # seconds between reconnection attempts

# Validation Mode (for testing)
VALIDATE_WEBSOCKET_WITH_REST = False  # Compare WebSocket vs REST data during operation

# ============================================================================
# RISK MANAGEMENT
# ============================================================================

# Order execution
ORDER_TYPE = "MARKET"
PRODUCT_TYPE = "INTRADAY"  # MIS equivalent

# Slippage control (future use)
MAX_SLIPPAGE_PERCENT = 0  # Currently not used

# Maximum daily loss (optional - for future use)
MAX_DAILY_LOSS = None  # Set amount if you want daily loss limit

# Capital Allocation
CAPITAL_PER_STRATEGY = 100000  # ₹1,00,000 allocated per strategy (3 strategies = ₹3,00,000 total)

# ============================================================================
# VALIDATION
# ============================================================================

def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Check API credentials
    if not PAPER_TRADING:
        if not DHAN_CLIENT_ID:
            errors.append("DHAN_CLIENT_ID not set")
        if not DHAN_ACCESS_TOKEN:
            errors.append("DHAN_ACCESS_TOKEN not set")
    
    # Check trading times are valid
    if TRADING_END_TIME <= TRADING_START_TIME:
        errors.append("TRADING_END_TIME must be after TRADING_START_TIME")
    
    # Check indicator parameters
    if RSI_PERIOD < 2:
        errors.append("RSI_PERIOD must be at least 2")
    
    if SMA_OI_PERIOD < 2:
        errors.append("SMA_OI_PERIOD must be at least 2")
    
    # Check position limits
    if MAX_CALL_POSITIONS < 1 or MAX_PUT_POSITIONS < 1:
        errors.append("Position limits must be at least 1")

    # Trading-hours/day gating throughout the codebase uses naive datetime.now(),
    # which assumes the OS clock is already IST. This is silently wrong on a
    # server defaulting to UTC (e.g. a fresh EC2 instance) - fail loudly here
    # rather than let the system quietly trade at the wrong real-world hours.
    from datetime import datetime, timedelta
    local_offset = datetime.now().astimezone().utcoffset()
    ist_offset = timedelta(hours=5, minutes=30)
    if local_offset != ist_offset:
        errors.append(
            f"System timezone is not IST (Asia/Kolkata) - detected UTC offset {local_offset}. "
            f"Trading-hours/day checks assume the OS clock is IST. Set the server timezone to "
            f"Asia/Kolkata before running (e.g. on Linux: sudo timedatectl set-timezone Asia/Kolkata)."
        )

    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_chart_directory(date_str=None):
    """Get chart directory for a specific date"""
    from datetime import datetime
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    chart_dir = os.path.join(CHARTS_DIR, date_str)
    os.makedirs(chart_dir, exist_ok=True)
    return chart_dir

def get_trade_log_path(date_str=None):
    """Get trade log file path for a specific date"""
    from datetime import datetime
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    return os.path.join(TRADE_LOGS_DIR, f"trades_{date_str}.xlsx")

def get_log_file_path(date_str=None):
    """Get log file path for a specific date"""
    from datetime import datetime
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    return os.path.join(LOGS_DIR, f"trading_{date_str}.log")

# ============================================================================
# DISPLAY CONFIGURATION
# ============================================================================

def display_config():
    """Display current configuration"""
    print("=" * 80)
    print("NIFTY OPTIONS ALGO TRADING - CONFIGURATION")
    print("=" * 80)
    print(f"Mode: {'PAPER TRADING' if PAPER_TRADING else 'LIVE TRADING'}")
    print(f"Trading Hours: {TRADING_START_TIME} to {TRADING_END_TIME}")
    print(f"Candle Interval: {CANDLE_INTERVAL}")
    print(f"RSI Period: {RSI_PERIOD} | Threshold: {RSI_THRESHOLD}")
    print(f"OI SMA Period: {SMA_OI_PERIOD}")
    print(f"Credit Spread SL/Target: {CREDIT_SPREAD_SL_PERCENT}% / {CREDIT_SPREAD_PROFIT_TARGET_PERCENT}%")
    print(f"Spread Width: NIFTY {SPREAD_WIDTH_NIFTY} | SENSEX {SPREAD_WIDTH_SENSEX}")
    print(f"Max Positions: {MAX_CALL_POSITIONS} Call + {MAX_PUT_POSITIONS} Put")
    print(f"Lot Multiplier: NIFTY {NIFTY_LOT_MULTIPLIER} ({NIFTY_LOT_MULTIPLIER * NIFTY_LOT_SIZE} qty) | SENSEX {SENSEX_LOT_MULTIPLIER} ({SENSEX_LOT_MULTIPLIER * SENSEX_LOT_SIZE} qty)")
    print(f"Charts: {'ENABLED' if GENERATE_CHARTS else 'DISABLED'}")
    print(f"Telegram: {'ENABLED' if TELEGRAM_ENABLED else 'DISABLED'}")
    print("=" * 80)

# Debugging Setting
DEBUG_MODE = True  # Set to True for verbose WebSocket logging

if __name__ == "__main__":
    # Validate and display config
    validate_config()
    display_config()
