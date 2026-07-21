"""
Credit Spread Backtest
Self-contained same-day/recent-day simulation of the credit-spread strategy
(see order_manager.py:place_credit_spread) against real Dhan candle+OI data,
fetched on demand rather than from MongoDB's pre-fetched ATM+-4 cache - the
hedge legs (400/1000 points away) sit outside that range, and there are no
actual spread trades logged yet to replay.

Reuses the unmodified production signal-detection code (Indicators) and the
existing backtest UI's metrics/AI-analysis helpers so results plug directly
into the same dashboard used for the option-buying scenarios.

KNOWN LIMITATION: instrument resolution goes through dhan_client's cached
scrip master, which only lists live/future contracts. This works for recent
dates (today, this week) but will fail once an expiry drops off the daily
Dhan master. Dhan's expired_options_data() endpoint covers historical expiries
but is out of scope here.
"""
from datetime import datetime
from typing import Dict, List, Optional

import config
from dhan_api import dhan_client
from data_manager import data_manager
from indicators import Indicators
from performance_metrics import PerformanceMetrics
from ai_analysis import generate_ai_analysis
from mongo_logger import mongo_logger
from logger import logger


def _get_candles(symbol: str, strike: int, option_type: str, expiry: str, date_str: str):
    # Prefer MongoDB's already-fetched candles (populated by fetch_day_candles.py) -
    # this is what lets post-market analysis run without live Dhan connectivity.
    cached = mongo_logger.get_option_1min_candles(symbol, strike, option_type, date_str)
    if cached is not None and not cached.empty:
        return cached

    key = dhan_client.get_instrument_key(symbol, strike, option_type, expiry)
    if not key:
        logger.warning(f"[credit_spread_backtest] Could not resolve instrument key for {symbol} {strike} {option_type} {expiry}")
        return None
    return dhan_client.get_historical_data(key, config.CANDLE_INTERVAL, from_date=date_str, to_date=date_str)


def _replay_signal(df, option_type: str):
    """Walk candle-by-candle with no lookahead; return (index, conditions) of the first signal, or None."""
    for i in range(config.SMA_OI_PERIOD, len(df)):
        cond = Indicators.check_entry_conditions(df.iloc[:i + 1], option_type=option_type)
        if cond.get('entry_signal'):
            return i, cond
    return None


def _simulate_spread(
    entry_time, spread_type: str, signal_type: str,
    near_strike: int, near_df, far_strike: int, far_df,
    sl_pct: float, target_pct: float, symbol: str, cond: Dict
) -> Optional[Dict]:
    """Simulate one credit-spread trade forward from entry_time; returns a trade dict or None."""
    near_at_entry = near_df[near_df.index >= entry_time]
    far_at_entry = far_df[far_df.index >= entry_time] if far_df is not None else None
    if near_at_entry.empty or far_at_entry is None or far_at_entry.empty:
        logger.warning(f"[credit_spread_backtest] Missing leg data at/after entry time {entry_time} for {spread_type}")
        return None

    near_entry_price = float(near_at_entry.iloc[0]['close'])
    far_entry_price = float(far_at_entry.iloc[0]['close'])
    net_credit = near_entry_price - far_entry_price

    near_option_type = "PUT" if spread_type == "BULL_PUT" else "CALL"
    far_option_type = near_option_type

    if net_credit <= 0:
        # Real system would skip this entry (hedge costs more than premium collected)
        return None

    # SL is based on the sold (near) leg's own premium, not net credit (e.g. sold at
    # 100 -> SL at 120, ignoring hedge cost). Target stays based on net credit.
    sl_value = near_entry_price * (1 + sl_pct / 100.0)
    target_value = net_credit * (1 - target_pct / 100.0)

    near_future = near_df[near_df.index > entry_time]
    far_future = far_df[far_df.index > entry_time]

    exit_reason, exit_time, exit_near, exit_far = None, None, None, None
    for ts, row in near_future.iterrows():
        far_rows = far_future[far_future.index == ts]
        if far_rows.empty:
            continue
        near_close = float(row['close'])
        far_close = float(far_rows.iloc[0]['close'])
        net_spread_value = near_close - far_close

        if near_close >= sl_value:
            exit_reason, exit_time, exit_near, exit_far = "Stop Loss", ts, near_close, far_close
            break
        if net_spread_value <= target_value:
            exit_reason, exit_time, exit_near, exit_far = "Profit Target", ts, near_close, far_close
            break

    if exit_time is None:
        exit_reason = "EOD"
        if not near_future.empty:
            exit_time = near_future.index[-1]
            exit_near = float(near_future.iloc[-1]['close'])
            far_last = far_future[far_future.index <= exit_time]
            exit_far = float(far_last.iloc[-1]['close']) if not far_last.empty else far_entry_price
        else:
            exit_time, exit_near, exit_far = entry_time, near_entry_price, far_entry_price

    net_debit_to_close = exit_near - exit_far
    lot_size = config.NIFTY_LOT_SIZE if symbol == "NIFTY" else config.SENSEX_LOT_SIZE
    lot_multiplier = config.NIFTY_LOT_MULTIPLIER if symbol == "NIFTY" else config.SENSEX_LOT_MULTIPLIER
    qty = lot_multiplier * lot_size
    pnl = (net_credit - net_debit_to_close) * qty
    pnl_pct = (pnl / (net_credit * qty)) * 100 if net_credit > 0 else 0

    timeline = [
        {'time': str(entry_time), 'event': 'ENTRY',
         'details': f"Sold {near_option_type} {near_strike} @ Rs.{near_entry_price:.2f}, bought hedge {far_option_type} {far_strike} @ Rs.{far_entry_price:.2f} (net credit Rs.{net_credit:.2f})"},
        {'time': str(entry_time), 'event': 'SL_SET',
         'details': f"Stop loss (near-leg price) set at Rs.{sl_value:.2f}, profit target (cost-to-close) at Rs.{target_value:.2f}"},
        {'time': str(exit_time), 'event': 'EXIT',
         'details': f"{exit_reason}: bought back {near_option_type} {near_strike} @ Rs.{exit_near:.2f}, sold hedge {far_option_type} {far_strike} @ Rs.{exit_far:.2f} (cost to close Rs.{net_debit_to_close:.2f})"},
    ]

    trade = {
        'symbol': symbol,
        'is_spread': True,
        'spread_type': spread_type,
        'signal_type': signal_type,
        # Backward-compatible single-leg view (the sold/near leg) for existing table columns
        'option_type': near_option_type,
        'strike': near_strike,
        'entry_price': near_entry_price,
        'exit_price': exit_near,
        # Hedge leg
        'far_option_type': far_option_type,
        'far_strike': far_strike,
        'far_entry_price': far_entry_price,
        'far_exit_price': exit_far,
        'net_credit': net_credit,
        'stop_loss_value': sl_value,
        'profit_target_value': target_value,
        'entry_time': str(entry_time),
        'exit_time': str(exit_time),
        'exit_reason': exit_reason,
        'status': 'CLOSED',
        'pnl': round(pnl, 2),
        'pnl_percent': round(pnl_pct, 2),
        'timeline': timeline,
        'executions': [],
        # Indicator values at entry (for AI analysis / indicator pills - reused as-is).
        # Cast numpy scalar types (from pandas/numpy comparisons in check_entry_conditions)
        # to native Python types - numpy.bool_/float64 aren't JSON-serializable by Flask's
        # default encoder.
        'rsi': float(cond.get('rsi', 0) or 0),
        'adx': float(cond.get('adx', 0) or 0),
        'vwap': float(cond.get('vwap', 0) or 0),
        'close_at_entry': float(cond.get('close', 0) or 0),
        'oi': float(cond.get('oi', 0) or 0),
        'oi_sma': float(cond.get('oi_sma', 0) or 0),
        'volume': float(cond.get('volume', 0) or 0),
        'volume_sma': float(cond.get('volume_sma', 0) or 0),
        'volume_ratio': float((cond.get('volume', 0) / cond.get('volume_sma', 1) * 100) if cond.get('volume_sma', 0) else 0),
        'price_below_vwap': bool(cond.get('price_below_vwap', False)),
        'rsi_below_threshold': bool(cond.get('rsi_below_40', False)),
        'oi_above_sma': bool(cond.get('oi_above_sma', False)),
    }
    trade['ai_analysis'] = generate_ai_analysis(trade)
    return trade


def _simulate_index(symbol: str, date_str: str, sl_pct: float, target_pct: float) -> List[Dict]:
    width = config.SPREAD_WIDTH_NIFTY if symbol == "NIFTY" else config.SPREAD_WIDTH_SENSEX
    strike_interval = config.NIFTY_STRIKE_INTERVAL if symbol == "NIFTY" else config.SENSEX_STRIKE_INTERVAL
    index_symbol = config.NIFTY_INDEX_SYMBOL if symbol == "NIFTY" else config.SENSEX_INDEX_SYMBOL
    expiry_day = config.NIFTY_EXPIRY_DAY if symbol == "NIFTY" else config.SENSEX_EXPIRY_DAY

    # Prefer MongoDB's already-fetched candles (populated by fetch_day_candles.py) -
    # this is what lets post-market analysis run without live Dhan connectivity.
    idx_df = mongo_logger.get_index_1min_candles(symbol, date_str)
    if idx_df is None or idx_df.empty:
        idx_df = dhan_client.get_historical_data(index_symbol, config.CANDLE_INTERVAL, from_date=date_str, to_date=date_str)
    if idx_df is None or idx_df.empty:
        logger.warning(f"[credit_spread_backtest] No index candles for {symbol} on {date_str}")
        return []

    start_t = config.TRADING_START_TIME
    ref_rows = idx_df[idx_df.index.time >= start_t]
    if ref_rows.empty:
        return []
    ref_spot = float(ref_rows.iloc[0]['close'])

    ref_dt = datetime.strptime(f"{date_str} 09:45:00", "%Y-%m-%d %H:%M:%S")
    expiry = data_manager.get_expiry_date(ref_dt, expiry_day)
    is_expiry_day = (expiry == date_str)

    strikes = data_manager.determine_atm_strikes(ref_spot, strike_interval, is_expiry_day=is_expiry_day)
    call_strike, put_strike = strikes['call'], strikes['put']
    far_put_strike = put_strike - width
    far_call_strike = call_strike + width

    call_df = _get_candles(symbol, call_strike, "CE", expiry, date_str)
    put_df = _get_candles(symbol, put_strike, "PE", expiry, date_str)
    far_put_df = _get_candles(symbol, far_put_strike, "PE", expiry, date_str)
    far_call_df = _get_candles(symbol, far_call_strike, "CE", expiry, date_str)

    if call_df is None or put_df is None:
        logger.warning(f"[credit_spread_backtest] Missing near-leg signal data for {symbol} on {date_str}")
        return []

    call_df = Indicators.calculate_all_indicators(call_df, rsi_period=config.RSI_PERIOD, sma_period=config.SMA_OI_PERIOD)
    put_df = Indicators.calculate_all_indicators(put_df, rsi_period=config.RSI_PERIOD, sma_period=config.SMA_OI_PERIOD)

    trades = []

    call_signal = _replay_signal(call_df, "CALL")
    if call_signal is not None:
        idx, cond = call_signal
        entry_time = call_df.index[idx]
        trade = _simulate_spread(entry_time, "BULL_PUT", "CALL", put_strike, put_df, far_put_strike, far_put_df,
                                  sl_pct, target_pct, symbol, cond)
        if trade:
            trades.append(trade)

    put_signal = _replay_signal(put_df, "PUT")
    if put_signal is not None:
        idx, cond = put_signal
        entry_time = put_df.index[idx]
        trade = _simulate_spread(entry_time, "BEAR_CALL", "PUT", call_strike, call_df, far_call_strike, far_call_df,
                                  sl_pct, target_pct, symbol, cond)
        if trade:
            trades.append(trade)

    return trades


def run_credit_spread_backtest(date_str: str) -> Dict:
    """
    Run the credit-spread strategy simulation for a single date across NIFTY + SENSEX.
    Only simulates an index on its actual trading days (matches main.py's live gating:
    NIFTY_TRADING_DAYS / SENSEX_TRADING_DAYS) - e.g. Sensex is skipped on a Tuesday,
    since that trade could never happen live.

    Args:
        date_str: Date to simulate (YYYY-MM-DD). Works reliably for recent dates only
            (see module docstring's KNOWN LIMITATION).

    Returns:
        {'scenario_name': str, 'metrics': dict, 'trades': list}
    """
    sl_pct = config.CREDIT_SPREAD_SL_PERCENT
    target_pct = config.CREDIT_SPREAD_PROFIT_TARGET_PERCENT
    weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()

    all_trades = []
    if weekday in config.NIFTY_TRADING_DAYS:
        all_trades.extend(_simulate_index("NIFTY", date_str, sl_pct, target_pct))
    if weekday in config.SENSEX_TRADING_DAYS:
        all_trades.extend(_simulate_index("SENSEX", date_str, sl_pct, target_pct))

    metrics = PerformanceMetrics(all_trades).calculate_all()

    return {
        'scenario_name': 'Credit Spread (Selling)',
        'metrics': metrics,
        'trades': all_trades,
    }


if __name__ == "__main__":
    import json
    from datetime import datetime as _dt

    result = run_credit_spread_backtest(_dt.now().strftime("%Y-%m-%d"))
    print(f"Trades: {len(result['trades'])}")
    for t in result['trades']:
        print(f"  {t['symbol']} {t['spread_type']}: entry {t['entry_time']} exit {t['exit_time']} "
              f"reason={t['exit_reason']} pnl={t['pnl']:+.2f} ({t['pnl_percent']:+.1f}%)")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2, default=str)}")
