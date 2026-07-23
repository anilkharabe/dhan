"""
Trend Scanner Module
Full trading-day (9:15-15:30) history of Call/Put OI, PCR, and VWAP for
NIFTY / BANKNIFTY / SENSEX, at 5-min or 15-min row spacing - modeled on a
commercial reference tool's "Intraday Trend" table (SMC Autotrender).

Two independent signals per row (not blended into a single score, since both
are point-in-time comparisons rather than timeframe-dependent indicators):
- VWAP Signal: price vs VWAP (reverse-engineered from the reference tool with
  100% confidence: strict `close > vwap -> BUY, else SELL`, confirmed via a
  tie-break row and a flip row in the reference sample data)
- Option Signal: full-chain PCR threshold (direction confirmed from the
  reference tool - low PCR/call-heavy read as bearish there - exact
  crossover unconfirmed, using the same 0.8/1.2 bands as OIPcrChart.jsx as a
  placeholder)

Reconstructs the whole day on-demand from Dhan's historical option-candle API
(same technique as data_manager.backfill_oi_pcr_full_chain, but keeping the
raw call/put OI sums, not just the ratio). This does NOT depend on main.py's
trading engine (or its 3-min OI/PCR sampler) being alive, since Dhan retains
the day's per-minute OI history regardless of whether anything was
live-polling it.

Every successful reconstruction is also persisted to Mongo
(mongo_logger.scanner_snapshots), write-through, so a server restart doesn't
force the next request to redo the full ~30s-4min rebuild from scratch: a
cache miss first tries today's last-persisted Mongo snapshot (serving it
immediately, possibly slightly stale) before falling back to a live Dhan
rebuild, and kicks off a background refresh if what it served was stale.

Informational only - does not feed strategy.py's credit-spread entry gate.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, time as dtime, timezone
from typing import Dict, List, Optional

import pandas as pd

import config
import logger
from dhan_api import dhan_client
from data_manager import data_manager
from indicators import Indicators
from mongo_logger import mongo_logger

SYMBOLS = {
    "NIFTY": {"instrument_key": config.NIFTY_INDEX_SYMBOL, "expiry_day": config.NIFTY_EXPIRY_DAY},
    "SENSEX": {"instrument_key": config.SENSEX_INDEX_SYMBOL, "expiry_day": config.SENSEX_EXPIRY_DAY},
    "BANKNIFTY": {"instrument_key": config.BANKNIFTY_INDEX_SYMBOL, "expiry_day": None},
}

TIMEFRAMES = {"5min": "5min", "15min": "15min"}

CACHE_TTL_SECONDS = 180
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

# Bounded concurrency for per-strike/leg OI history fetches - stays within
# dhanhq's default connection pool size (pool_maxsize=10, dhan_http.py:48-51)
# and lets DH-904 rate-limit retries (already handled per-call in dhan_api.py)
# absorb any contention rather than failing outright.
MAX_CONCURRENT_LEG_FETCHES = 6

# Same 0.8/1.2 bands as OIPcrChart.jsx, but read in the OPPOSITE direction: a
# live comparison against the reference tool's Intraday Trend table
# (2026-07-22) showed SELL held all session while full-chain PCR stayed
# 0.31-0.58 (call-heavy) - i.e. heavy call OI reads bearish/resistance there,
# not bullish. Exact crossover is unconfirmed since PCR never left the <0.8
# band in that sample; these thresholds are a best-effort placeholder.
PCR_SELL_BELOW = 0.8
PCR_BUY_ABOVE = 1.2

_cache: Dict[str, Dict] = {}
_locks: Dict[str, threading.Lock] = {symbol: threading.Lock() for symbol in SYMBOLS}
_building: Dict[str, bool] = {symbol: False for symbol in SYMBOLS}


def get_symbol_history(symbol: str, timeframe: str) -> Optional[Dict]:
    """Full-day OI/PCR/VWAP history table for one symbol, resampled to the
    requested timeframe.

    Non-blocking: a full reconstruction takes 30s-4min (rate-limited,
    sequential per-strike Dhan calls), and a request held open that long
    occupies one of the browser's ~6 per-origin HTTP/1.1 connection slots for
    its entire duration - with a browser tab or two open, that's enough to
    starve unrelated polling (e.g. TokenStatus) of a connection until it hits
    its own client-side timeout, even though the server itself handles the
    request fine. So a cache miss kicks off the rebuild in a background
    thread and returns `{"status": "building"}` immediately; the caller
    (frontend) polls every few seconds - each poll is a fast round trip -
    until `{"status": "ready", "rows": [...]}` comes back."""
    if symbol not in SYMBOLS or timeframe not in TIMEFRAMES:
        return None

    cached = _cache.get(symbol)
    if _is_fresh(cached):
        return _ready_response(symbol, timeframe, cached["df"])

    # In-memory cache missing/stale (typically right after a server restart,
    # since this is per-process state) - try today's last-persisted Mongo
    # snapshot before falling back to a full live Dhan reconstruction, so a
    # restart doesn't force the next viewer to wait minutes for data that was
    # already built earlier today.
    mongo_cached = _load_from_mongo(symbol)
    if mongo_cached is not None:
        _cache[symbol] = mongo_cached
        if not _is_fresh(mongo_cached):
            _ensure_rebuild_started(symbol)  # serve stale Mongo data now, refresh in background
        return _ready_response(symbol, timeframe, mongo_cached["df"])

    _ensure_rebuild_started(symbol)
    return {"symbol": symbol, "timeframe": timeframe, "status": "building", "rows": []}


def _ready_response(symbol: str, timeframe: str, df: pd.DataFrame) -> Dict:
    return {"symbol": symbol, "timeframe": timeframe, "status": "ready", "rows": _build_rows(df, timeframe)}


def _ensure_rebuild_started(symbol: str) -> None:
    with _locks[symbol]:
        if _building.get(symbol):
            return  # already in progress - don't start a duplicate

        cached = _cache.get(symbol)
        if _is_fresh(cached):
            return  # another request already finished rebuilding it

        _building[symbol] = True

    def _worker():
        try:
            df = _reconstruct_minute_data(symbol)
            if df is not None and not df.empty:
                _cache[symbol] = {"df": df, "date": date.today(), "computed_at": time.time()}
                _save_to_mongo(symbol, df)
        except Exception as e:
            logger.error(f"TrendScanner: background rebuild failed for {symbol}: {str(e)}")
        finally:
            _building[symbol] = False

    threading.Thread(target=_worker, daemon=True, name=f"trend-scanner-{symbol}").start()


def _save_to_mongo(symbol: str, df: pd.DataFrame) -> None:
    try:
        minutes = [
            {
                "time": data_manager._ist_naive_to_utc(ts),
                "call_oi": float(row["call_oi"]),
                "put_oi": float(row["put_oi"]),
                "close": float(row["close"]),
                "vwap": float(row["vwap"]),
            }
            for ts, row in df.iterrows()
        ]
        mongo_logger.save_scanner_snapshot(symbol, date.today().isoformat(), minutes)
    except Exception as e:
        logger.error(f"TrendScanner: failed to persist snapshot for {symbol}: {str(e)}")


def _load_from_mongo(symbol: str) -> Optional[Dict]:
    try:
        doc = mongo_logger.get_scanner_snapshot(symbol, date.today().isoformat())
        if not doc or not doc.get("minutes"):
            return None

        records = []
        for m in doc["minutes"]:
            # Mongo stores naive UTC instants; convert back to the naive-IST
            # wall-clock convention the rest of this module's DataFrames use.
            ist_ts = pd.Timestamp(m["time"], tz="UTC").tz_convert("Asia/Kolkata").tz_localize(None)
            records.append({
                "time": ist_ts,
                "call_oi": m["call_oi"],
                "put_oi": m["put_oi"],
                "close": m["close"],
                "vwap": m["vwap"],
            })

        df = pd.DataFrame(records).set_index("time").sort_index()

        updated_at = doc.get("updated_at")
        computed_at = updated_at.replace(tzinfo=timezone.utc).timestamp() if updated_at else 0
        return {"df": df, "date": date.today(), "computed_at": computed_at}
    except Exception as e:
        logger.error(f"TrendScanner: failed to load Mongo snapshot for {symbol}: {str(e)}")
        return None


def _is_fresh(cached: Optional[Dict]) -> bool:
    return bool(
        cached
        and cached["date"] == date.today()
        and (time.time() - cached["computed_at"]) < CACHE_TTL_SECONDS
    )


def _reconstruct_minute_data(symbol: str) -> Optional[pd.DataFrame]:
    meta = SYMBOLS[symbol]
    instrument_key = meta["instrument_key"]

    spot_df = dhan_client.get_historical_data(instrument_key, config.CANDLE_INTERVAL)
    if spot_df is None or spot_df.empty:
        logger.warning(f"TrendScanner: no spot candle data for {symbol}")
        return None

    vwap_series = Indicators.calculate_vwap(spot_df)

    expiry = _get_expiry(symbol, meta["expiry_day"])
    if not expiry:
        logger.warning(f"TrendScanner: could not resolve expiry for {symbol}")
        return None

    oi_df = _fetch_full_chain_oi_minutes(symbol, instrument_key, expiry, spot_df.index)
    if oi_df is None or oi_df.empty:
        logger.warning(f"TrendScanner: no option-chain OI data for {symbol}")
        return None

    combined = spot_df[["close"]].join(vwap_series.rename("vwap")).join(oi_df, how="inner")
    # Defensive upper/lower bound on market hours - live testing surfaced a
    # stray duplicate-valued candle at 19:30 IST in Dhan's raw response, well
    # past the 15:30 close, so don't just trust the response's own timestamps.
    times = combined.index.map(lambda ts: ts.time())
    combined = combined[(times >= MARKET_OPEN) & (times <= MARKET_CLOSE)]
    return combined.dropna(subset=["close", "vwap", "call_oi", "put_oi"])


def _fetch_full_chain_oi_minutes(
    symbol: str, instrument_key: str, expiry: str, minute_index: pd.DatetimeIndex
) -> Optional[pd.DataFrame]:
    chain_data = dhan_client.get_option_chain(instrument_key, expiry)
    if not chain_data:
        return None

    all_strikes = list(chain_data.get("strikes", {}).keys())
    if not all_strikes:
        return None

    # BANKNIFTY's monthly chain lists ~380 strikes (~760 legs) vs NIFTY's
    # weekly ~240 (~480 legs) - fetched one leg at a time with a 0.15s pace,
    # that's minutes of difference. dhanhq's client shares one requests.Session
    # (dhan_http.py:48) over a default urllib3 pool (pool_maxsize=10, no custom
    # pool= passed), which is safe for concurrent independent GETs, and each
    # call's own DH-904 rate-limit retry (dhan_api.py) is independent per
    # thread - so a bounded worker pool is a safe way to cut wall-clock time
    # roughly proportionally without changing what gets fetched.
    #
    # dhan_client.get_instrument_key() -> search_instrument() re-filters the
    # ENTIRE ~9400-row instruments dataframe on every single call (CPU-bound
    # pandas string ops, not I/O) - done 700+ times that's GIL-serialized
    # across threads regardless of pool size, which is why parallelizing
    # alone only bought a ~25% speedup live-tested on BANKNIFTY. Building this
    # symbol+expiry's lookup ONCE up front turns each leg's resolution into an
    # O(1) dict lookup, so the thread pool's concurrency actually lands on the
    # real bottleneck (network I/O) instead.
    instrument_index = _build_instrument_index(symbol, expiry)

    legs = [(strike, option_type) for strike in all_strikes for option_type in ("CE", "PE")]

    def _fetch_leg(strike, option_type):
        inst_key = instrument_index.get(float(strike), {}).get(option_type)
        if not inst_key:
            # Fall back to the slow per-call path for the rare strike the
            # fast index didn't resolve - keeps correctness even if the
            # index ever misses an entry.
            inst_key = dhan_client.get_instrument_key(symbol, strike, option_type, expiry)
        if not inst_key:
            return option_type, None
        df = dhan_client.get_historical_data(inst_key, config.CANDLE_INTERVAL)
        if df is None or df.empty or "oi" not in df.columns:
            return option_type, None
        # OI is a persistent state, not a flow - a strike with no candle in a
        # given minute still HAS its last known OI, so reindex onto the full
        # session's minute index and forward-fill before summing.
        # data_manager's existing backfill_oi_pcr_full_chain skips this and
        # treats a missing minute as contributing 0, which saw-tooths the
        # total whenever a quiet far-OTM strike has a gap.
        return option_type, df["oi"].reindex(minute_index).ffill()

    call_legs: List[pd.Series] = []
    put_legs: List[pd.Series] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_LEG_FETCHES) as pool:
        futures = [pool.submit(_fetch_leg, strike, option_type) for strike, option_type in legs]
        for future in as_completed(futures):
            try:
                option_type, leg_series = future.result()
            except Exception as e:
                logger.error(f"TrendScanner: leg fetch failed for {symbol}: {str(e)}")
                continue
            if leg_series is not None:
                (call_legs if option_type == "CE" else put_legs).append(leg_series)

    if not call_legs or not put_legs:
        return None

    call_oi = pd.concat(call_legs, axis=1).sum(axis=1)
    put_oi = pd.concat(put_legs, axis=1).sum(axis=1)
    return pd.DataFrame({"call_oi": call_oi, "put_oi": put_oi})


def _build_instrument_index(symbol: str, expiry: str) -> Dict[float, Dict[str, str]]:
    """
    One-time O(n) filter over the (already-cached) instruments dataframe,
    building a {strike: {option_type: instrument_key}} lookup for this
    symbol+expiry - replaces 700+ repeated full-dataframe scans (one per
    strike/leg via dhan_client.search_instrument) with a single pass.

    Mirrors dhan_api.DhanClient.search_instrument's matching conditions
    manually (kept in sync by hand) rather than modifying that shared method,
    since it's also used by live order-placement/data_manager code paths this
    scanner shouldn't risk touching.
    """
    if dhan_client.instruments_df is None:
        if not dhan_client.download_instruments_master():
            return {}

    df = dhan_client.instruments_df
    filtered = df[
        (df["SEM_TRADING_SYMBOL"].astype(str).str.startswith(f"{symbol.upper()}-"))
        & (df["SEM_EXPIRY_DATE"].astype(str).str[:10] == expiry)
    ]

    exchange_segment = "BSE_FNO" if symbol.upper() == "SENSEX" else "NSE_FNO"
    index: Dict[float, Dict[str, str]] = {}
    for _, row in filtered.iterrows():
        strike = float(row["SEM_STRIKE_PRICE"])
        option_type = row["SEM_OPTION_TYPE"]
        security_id = str(int(row["SEM_SMST_SECURITY_ID"]))
        index.setdefault(strike, {})[option_type] = f"{exchange_segment}|{security_id}"
    return index


def _get_expiry(symbol: str, expiry_day: Optional[int]) -> Optional[str]:
    try:
        if symbol == "BANKNIFTY":
            return data_manager.get_nearest_expiry_from_list(config.BANKNIFTY_INDEX_SYMBOL)
        return data_manager.get_expiry_date(datetime.now(), expiry_day)
    except Exception as e:
        logger.error(f"TrendScanner: expiry resolution failed for {symbol}: {str(e)}")
        return None


def _build_rows(minute_df: pd.DataFrame, timeframe: str) -> List[Dict]:
    rule = TIMEFRAMES[timeframe]
    resampled = minute_df.resample(rule, label="left", closed="left").last().dropna(how="any")

    rows = []
    for ts, row in resampled.iterrows():
        call_oi = float(row["call_oi"])
        put_oi = float(row["put_oi"])
        close = float(row["close"])
        vwap = float(row["vwap"])
        pcr = round(put_oi / call_oi, 3) if call_oi > 0 else None

        rows.append({
            "time": data_manager._ist_naive_to_utc(ts).isoformat() + "Z",
            "call_oi": call_oi,
            "put_oi": put_oi,
            "diff": put_oi - call_oi,
            "pcr": pcr,
            "option_signal": _option_signal(pcr),
            "price": close,
            "vwap": round(vwap, 2),
            "vwap_signal": "BUY" if close > vwap else "SELL",
        })
    return rows


def _option_signal(pcr: Optional[float]) -> Optional[str]:
    if pcr is None:
        return None
    if pcr < PCR_SELL_BELOW:
        return "SELL"
    if pcr > PCR_BUY_ABOVE:
        return "BUY"
    return "NEUTRAL"
