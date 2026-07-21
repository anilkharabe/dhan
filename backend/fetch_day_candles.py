"""
Post-Market Candle Fetch Script
================================
Run after market close to fetch ALL 1-minute OHLCV candles for the day
(multiple strikes + index spot) from Upstox historical API and store in MongoDB.

Usage:
  python3 backend/fetch_day_candles.py                          # fetch today
  python3 backend/fetch_day_candles.py 2026-02-21               # fetch specific past date
  python3 backend/fetch_day_candles.py 2026-02-10 2026-02-21   # bulk fetch date range

What it fetches:
  - NIFTY: ATM ± 4 strikes (9 total), both CE and PE → 18 option instruments
  - SENSEX: ATM ± 4 strikes (9 total), both CE and PE → 18 option instruments
  - NSE_INDEX (Nifty 50 spot) 1-min candles
  - BSE_INDEX (Sensex spot) 1-min candles

Total: ~36 instruments, ~370 candles each → ~13,300 candles per day saved in ~8 seconds.
"""

import sys
import time
import os
import io
from datetime import datetime, timedelta, date as date_type

# Add backend dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# This script's own print() calls (below) use emoji and run before anything else
# has a chance to fix stdout's encoding - Windows' default console/pipe codepage
# (cp1252) can't represent them. Wrap stdout in a fresh UTF-8 stream so it's safe
# whether this runs standalone or as a subprocess (see api/server.py's
# PYTHONIOENCODING env var for the subprocess path - this covers direct/manual runs).
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
except (AttributeError, ValueError):
    pass

import config
from dhan_api import dhan_client
from mongo_logger import mongo_logger
from data_manager import data_manager


# ============================================================================
# HELPERS
# ============================================================================

def get_expiry_date(for_date: datetime, expiry_weekday: int) -> str:
    """
    Get the upcoming (or current) expiry date for the given weekday.
    expiry_weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    """
    d = for_date.date() if isinstance(for_date, datetime) else for_date
    days_ahead = expiry_weekday - d.weekday()
    if days_ahead < 0:
        days_ahead += 7
    expiry = d + timedelta(days=days_ahead)
    return expiry.strftime("%Y-%m-%d")


def get_strikes_around_atm(spot_price: float, strike_interval: int, n: int = 4):
    """
    Return a sorted list of strikes: ATM-n, ..., ATM, ..., ATM+n  (2n+1 strikes).
    """
    atm = round(spot_price / strike_interval) * strike_interval
    return [atm + i * strike_interval for i in range(-n, n + 1)]


def is_weekend(d: date_type) -> bool:
    return d.weekday() >= 5  # Saturday=5, Sunday=6


def get_trading_dates(start: date_type, end: date_type):
    """Yield Mon-Fri dates between start and end (inclusive)."""
    current = start
    while current <= end:
        if not is_weekend(current):
            yield current
        current += timedelta(days=1)


def get_spot_price_for_date(symbol: str, date_str: str) -> float:
    """
    Get the approximate spot price for symbol on the given date.
    Strategy:
      1. If date == today → use V3 intraday endpoint (no from_date) — always works.
      2. For past dates → look up nifty_spot / index_1min_candles in MongoDB.
      3. Last fallback → return a hardcoded reasonable price so the script
         at least fetches a wide range of strikes.
    """
    index_key = config.NIFTY_INDEX_SYMBOL if symbol == "NIFTY" else config.SENSEX_INDEX_SYMBOL
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── 1. Today: use intraday endpoint (no from_date) ──
    if date_str == today_str:
        df = dhan_client.get_historical_data(
            instrument_key=index_key,
            interval="1minute"
            # No from_date → calls intraday endpoint, works for index instruments
        )
        if df is not None and not df.empty:
            return float(df['close'].median())

    # ── 2. Past date: check MongoDB index_1min_candles first ──
    try:
        stored = mongo_logger.get_index_1min_candles(symbol, date_str)
        if not stored.empty:
            return float(stored['close'].median())
    except Exception:
        pass

    # ── 3. Past date: check nifty_spot collection (logged during live trading) ──
    try:
        if mongo_logger.enabled:
            doc = mongo_logger.nifty_spot_data.find_one(
                {'date': date_str},
                {'price': 1},
                sort=[('timestamp', -1)]
            )
            if doc and doc.get('price'):
                return float(doc['price'])
    except Exception:
        pass

    # ── 4. Absolute fallback: reasonable defaults so we fetch something ──
    defaults = {'NIFTY': 22500.0, 'SENSEX': 74000.0}
    fallback = defaults.get(symbol)
    if fallback:
        print(f"  [{symbol}] ⚠️  Using fallback spot ≈ {fallback} — strike range may be off")
    return fallback


# ============================================================================
# CORE FETCH LOGIC
# ============================================================================

def fetch_index_candles(symbol: str, date_str: str) -> int:
    """
    Fetch and store 1-min candles for the index spot (Nifty or Sensex).
    Returns number of candles saved.

    NOTE: Upstox V3 historical-candle endpoint does NOT support NSE_INDEX /
    BSE_INDEX instruments with a from_date.  The intraday endpoint (no
    from_date) *does* work — but only for the current trading day.
    For past dates, index candles cannot be fetched; we skip silently.
    """
    index_key = config.NIFTY_INDEX_SYMBOL if symbol == "NIFTY" else config.SENSEX_INDEX_SYMBOL
    today_str = datetime.now().strftime("%Y-%m-%d")

    print(f"  📊 Fetching {symbol} index spot candles...", end=" ", flush=True)

    if date_str == today_str:
        # Intraday endpoint — works for index instruments
        df = dhan_client.get_historical_data(
            instrument_key=index_key,
            interval="1minute"
            # No from_date → intraday
        )
    else:
        # V3 historical endpoint does not support index keys — skip
        print(f"⏭️  Skipped (index historical data unavailable via API for past dates)")
        return 0

    time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

    if df is None or df.empty:
        print("❌ No data returned")
        return 0

    saved = mongo_logger.upsert_index_1min_candles(
        symbol=symbol,
        date=date_str,
        df=df
    )
    print(f"✅ {len(df)} candles saved")
    return saved


def fetch_option_candles(
    symbol: str,
    strike: int,
    option_type: str,  # 'CE' or 'PE'
    expiry: str,
    date_str: str
) -> int:
    """
    Fetch and store 1-min candles for one option instrument.
    Returns number of candles saved.

    IMPORTANT Upstox V3 API behaviour:
      - /historical-candle/{key}/.../{to}/{from}  → past dates ONLY (not today)
      - /historical-candle/intraday/{key}/...     → TODAY only
    We choose the endpoint automatically based on whether date_str == today.
    """
    instrument_key = dhan_client.get_instrument_key(
        symbol=symbol,
        strike=strike,
        option_type=option_type,
        expiry_date=expiry
    )

    if not instrument_key:
        print(f"    ⚠️  {symbol} {strike}{option_type} – instrument key not found, skipping")
        return 0

    today_str = datetime.now().strftime("%Y-%m-%d")

    if date_str == today_str:
        # Intraday endpoint — works for current trading day
        df = dhan_client.get_historical_data(
            instrument_key=instrument_key,
            interval="1minute"
            # No from_date → intraday
        )
    else:
        # Historical endpoint — works for any past date
        df = dhan_client.get_historical_data(
            instrument_key=instrument_key,
            interval="1minute",
            from_date=date_str,
            to_date=date_str
        )

    time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

    if df is None or df.empty:
        return 0

    saved = mongo_logger.upsert_option_1min_candles(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        instrument_key=instrument_key,
        date=date_str,
        df=df
    )
    return saved


def fetch_for_symbol(symbol: str, date_str: str) -> dict:
    """
    Fetch all strikes (ATM ± N, CE+PE) for one index on one date.
    Returns stats dict: {strikes, candles, errors}
    """
    n = config.FETCH_STRIKES_AROUND_ATM  # 4 → 9 strikes
    strike_interval = config.NIFTY_STRIKE_INTERVAL if symbol == "NIFTY" else config.SENSEX_STRIKE_INTERVAL
    expiry_day = config.NIFTY_EXPIRY_DAY if symbol == "NIFTY" else config.SENSEX_EXPIRY_DAY

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    expiry = get_expiry_date(date_obj, expiry_day)

    print(f"\n  [{symbol}] Expiry: {expiry}")

    # Get spot price to determine ATM
    spot = get_spot_price_for_date(symbol, date_str)
    if spot is None:
        print(f"  [{symbol}] ⚠️  Could not determine spot price — skipping")
        return {'strikes': 0, 'candles': 0, 'errors': [f"Could not get spot for {date_str}"]}

    atm = round(spot / strike_interval) * strike_interval
    strikes = get_strikes_around_atm(spot, strike_interval, n)
    print(f"  [{symbol}] Spot ≈ {spot:.0f}  ATM = {atm}  Fetching {len(strikes)} strikes: {strikes[0]}…{strikes[-1]}")

    total_candles = 0
    errors = []

    for strike in strikes:
        for opt_type in ['CE', 'PE']:
            try:
                saved = fetch_option_candles(symbol, strike, opt_type, expiry, date_str)
                total_candles += saved
                status = f"{saved} candles" if saved else "no data"
                print(f"    {symbol} {strike}{opt_type}: {status}")
            except Exception as e:
                msg = f"{symbol} {strike}{opt_type}: {e}"
                print(f"    ⚠️  {msg}")
                errors.append(msg)

    return {
        'strikes': len(strikes),
        'candles': total_candles,
        'expiry': expiry,
        'atm': atm,
        'errors': errors
    }


def run_fetch(date_str: str) -> bool:
    """
    Full fetch run for one trading date: both NIFTY and SENSEX.
    Returns True on success (even partial).
    """
    print(f"\n{'='*60}")
    print(f"  📅 Fetching candles for: {date_str}")
    print(f"{'='*60}")

    # Validate it's not a weekend
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    if is_weekend(date_obj):
        print(f"  ⚠️  {date_str} is a weekend — skipping")
        return False

    symbol_stats = {}
    all_errors = []

    # 1. Index spot candles
    print("\n  [INDEX SPOT CANDLES]")
    for symbol in ['NIFTY', 'SENSEX']:
        if symbol == 'NIFTY' and not config.NIFTY_ENABLED:
            continue
        if symbol == 'SENSEX' and not config.SENSEX_ENABLED:
            continue
        fetch_index_candles(symbol, date_str)
        time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

    # 2. Option candles (NIFTY)
    if config.NIFTY_ENABLED:
        stats = fetch_for_symbol("NIFTY", date_str)
        symbol_stats["NIFTY"] = stats
        all_errors.extend(stats.get('errors', []))

    # 3. Option candles (SENSEX)
    if config.SENSEX_ENABLED:
        stats = fetch_for_symbol("SENSEX", date_str)
        symbol_stats["SENSEX"] = stats
        all_errors.extend(stats.get('errors', []))

    # 4. Log fetch run to MongoDB
    mongo_logger.log_candle_fetch(
        date=date_str,
        symbol_stats=symbol_stats,
        errors=all_errors
    )

    # 5. Summary
    total = sum(s.get('candles', 0) for s in symbol_stats.values())
    print(f"\n{'='*60}")
    print(f"  ✅ Done for {date_str}")
    for sym, s in symbol_stats.items():
        print(f"     {sym}: {s.get('strikes', 0)} strikes, {s.get('candles', 0)} candles saved")
    print(f"     TOTAL: {total} candles saved to MongoDB")
    if all_errors:
        print(f"  ⚠️  {len(all_errors)} errors (check logs)")
    print(f"{'='*60}\n")

    return True


def run_bulk_fetch(start_date_str: str, end_date_str: str):
    """
    Fetch candles for every trading day in [start_date, end_date].
    """
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end   = datetime.strptime(end_date_str,   "%Y-%m-%d").date()

    all_dates = list(get_trading_dates(start, end))
    print(f"\n🗂️  Bulk fetch: {start_date_str} → {end_date_str}  ({len(all_dates)} trading days)\n")

    for i, d in enumerate(all_dates, 1):
        date_str = d.strftime("%Y-%m-%d")
        print(f"[{i}/{len(all_dates)}] {date_str}")
        try:
            run_fetch(date_str)
        except KeyboardInterrupt:
            print("\n⛔ Interrupted by user")
            break
        except Exception as e:
            print(f"  ❌ Error fetching {date_str}: {e}")
        # Brief pause between days to be polite to the API
        time.sleep(1)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 Post-Market Candle Fetch")
    print("   Data will be saved to MongoDB for backtesting\n")

    # Ensure instruments CSV is available
    dhan_client.download_instruments_master(force_refresh=False)

    args = sys.argv[1:]

    if len(args) == 0:
        # Default: fetch today
        today = datetime.now().strftime("%Y-%m-%d")
        run_fetch(today)

    elif len(args) == 1:
        # Single date
        try:
            datetime.strptime(args[0], "%Y-%m-%d")
        except ValueError:
            print(f"❌ Invalid date format: '{args[0]}'. Use YYYY-MM-DD")
            sys.exit(1)
        run_fetch(args[0])

    elif len(args) == 2:
        # Date range
        try:
            start = datetime.strptime(args[0], "%Y-%m-%d")
            end   = datetime.strptime(args[1], "%Y-%m-%d")
        except ValueError:
            print(f"❌ Invalid date format. Use: YYYY-MM-DD YYYY-MM-DD")
            sys.exit(1)
        if end < start:
            print("❌ End date must be >= start date")
            sys.exit(1)
        run_bulk_fetch(args[0], args[1])

    else:
        print("Usage:")
        print("  python3 backend/fetch_day_candles.py                       # today")
        print("  python3 backend/fetch_day_candles.py YYYY-MM-DD             # specific date")
        print("  python3 backend/fetch_day_candles.py YYYY-MM-DD YYYY-MM-DD  # date range")
        sys.exit(1)

    mongo_logger.close()
    print("✅ MongoDB connection closed. Done!\n")
