"""
Futures candle data for the Supertrend test strategy (backend/supertrend_strategy.py).

Isolated from data_manager.py on purpose - this is strategy-specific plumbing
(NIFTY/SENSEX FUTIDX candles) that the live CREDIT_A strategy never touches,
kept out of the already-large shared data_manager module.
"""
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

import config
import logger
from dhan_api import dhan_client


def get_previous_n_trading_days(n: int, from_date: Optional[datetime] = None) -> datetime:
    """
    Return the date N trading days (weekdays only) before from_date (default: today).
    Same weekend-skipping simplification as data_manager.get_previous_trading_day
    - does not account for market holidays.
    """
    d = from_date or datetime.now()
    remaining = n
    while remaining > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return d


def fetch_futures_candles(symbol: str, lookback_days: int = None) -> Optional[pd.DataFrame]:
    """
    Fetch NIFTY/SENSEX futures OHLC(+OI) candles at config.SUPERTREND_CANDLE_INTERVAL,
    spanning `lookback_days` trailing trading days plus today - enough history for
    Indicators.calculate_supertrend's ATR warmup.

    Confirmed live 2026-07-24: Dhan's intraday_minute_data does not return
    prior-day data on this account/plan at all - a from_date/to_date range
    spanning multiple days silently comes back as today's data only, and an
    explicit single-day request for yesterday returns an empty (but
    status=success) response. This affects the existing INDEX pipeline too,
    not just futures (verified against config.NIFTY_INDEX_SYMBOL). So
    "warmup" in practice is same-day-only: this loops one call per requested
    trading day (matching data_manager.py's existing per-day call pattern)
    and concatenates whatever comes back, degrading gracefully to today-only
    data rather than failing outright. With SUPERTREND_PERIOD=10 on 3-min
    candles, Wilder ATR still settles ~30min into the session (9:15-9:45),
    before TRADING_START_TIME - so this doesn't block same-day trading.

    Args:
        symbol: "NIFTY" or "SENSEX"
        lookback_days: trailing trading days of warmup history (default:
            config.SUPERTREND_WARMUP_TRADING_DAYS)

    Returns:
        DataFrame indexed by timestamp (naive IST) with columns
        [open, high, low, close, volume, oi], or None on failure.
    """
    try:
        lookback_days = lookback_days if lookback_days is not None else config.SUPERTREND_WARMUP_TRADING_DAYS

        instrument_key = dhan_client.get_futures_instrument_key(symbol)
        if not instrument_key:
            logger.error(f"[Supertrend] Could not resolve futures instrument key for {symbol}")
            return None

        # Build the list of trading days to fetch: `lookback_days` trailing
        # days, oldest first, plus today.
        days = []
        d = datetime.now()
        for _ in range(lookback_days):
            d = get_previous_n_trading_days(1, from_date=d)
            days.append(d)
        days.append(datetime.now())
        days.sort()

        frames = []
        for day in days:
            day_str = day.strftime("%Y-%m-%d")
            day_df = dhan_client.get_historical_data(
                instrument_key,
                config.SUPERTREND_CANDLE_INTERVAL,
                from_date=day_str,
                to_date=day_str,
                instrument_type="FUTIDX",
            )
            if day_df is not None and not day_df.empty:
                frames.append(day_df)

        if not frames:
            logger.warning(f"[Supertrend] No futures candles returned for {symbol} over last {lookback_days} trading days")
            return None

        combined = pd.concat(frames).sort_index()
        combined = combined[~combined.index.duplicated(keep='last')]
        return combined

    except Exception as e:
        logger.error(f"[Supertrend] Error fetching futures candles for {symbol}: {str(e)}")
        return None
