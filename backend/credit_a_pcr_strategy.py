"""
CREDIT_A's OI/VWAP/RSI/ADX signal engine, plus a full-chain PCR confluence
gate, run as two more isolated paper-trading test strategies (1-min and
3-min candles) - backend/config.py: CREDIT_A_PCR_1MIN_ENABLED /
CREDIT_A_PCR_3MIN_ENABLED.

Same isolation contract as supertrend_strategy.py / credit_a_3min_strategy.py:
deliberately self-contained, never touches order_manager.active_positions or
trade_tracker.*, and never calls dhan_client.place_order - every fill is a
synthetic paper simulation at the fetched LTP, unconditionally (not gated on
config.PAPER_TRADING).

Why the PCR gate: a normal retracement inside a bigger trend (e.g. a brief
dip during an uptrend) can satisfy CREDIT_A's price<VWAP + RSI<40 + OI>OI_SMA
conditions on a single strike's own noisy series, firing a CALL-sell (a
bearish bet) even though the broader market is still bullish - a "fake"
trade fighting the real trend. Full-chain PCR (data_manager.calculate_oi_pcr,
already validated against Upstox/NSE's publicly displayed PCR) is far less
noisy than one strike's own OHLCV, since it's summed across the whole option
chain. Lenient gate (per user choice 2026-08-18): only vetoes a signal that
directly contradicts chain-wide sentiment - CALL-sell blocked if PCR shows a
bull market, PUT-sell blocked if PCR shows a bear market. The neutral band
and aligned trades still fire unchanged.

One class, two instances (see bottom of file) - same logic, parameterized by
candle interval, so a fix here doesn't need to be copy-pasted between a
1-min and 3-min copy. Each instance still gets its own state file and its
own Mongo trade-id namespace, so they can never see or interact with each
other's (or CREDIT_A's, or CREDIT_A_3MIN's, or Supertrend's) positions.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import config
import logger
from dhan_api import dhan_client
from data_manager import data_manager
from indicators import Indicators
from mongo_logger import mongo_logger
from telegram_notifier import telegram_notifier

SYMBOLS = ["NIFTY", "SENSEX"]


class CreditAPcrStrategy:
    """Own, isolated state/lifecycle for one CREDIT_A + PCR paper-trading test instance."""

    def __init__(self, candle_interval: str, strategy_tag: str, display_name: str,
                 state_file: str, mongo_trade_id_offset: int, scan_interval_seconds: int):
        self.candle_interval = candle_interval
        self.strategy_tag = strategy_tag
        self.display_name = display_name
        self.state_file = state_file
        self.mongo_trade_id_offset = mongo_trade_id_offset
        self.scan_interval_seconds = scan_interval_seconds

        self.positions = {s: None for s in SYMBOLS}
        self.last_scan_time = {s: None for s in SYMBOLS}
        self.current_date = datetime.now().date()
        self._next_trade_id = 1

    # ------------------------------------------------------------------
    # Persistence (own state file - never touches trade_tracker)
    # ------------------------------------------------------------------
    def restore_state(self):
        try:
            if not os.path.exists(self.state_file):
                logger.info(f"[{self.display_name}] No saved state found, starting fresh.")
                return

            with open(self.state_file, 'r') as f:
                saved = json.load(f)

            saved_date = saved.get('date')
            if saved_date != datetime.now().strftime('%Y-%m-%d'):
                logger.info(f"[{self.display_name}] Saved state is from {saved_date}, discarding (stale).")
                return

            self.positions = saved.get('positions', {s: None for s in SYMBOLS})
            self._next_trade_id = saved.get('next_trade_id', 1)

            logger.info(f"[{self.display_name}] Restored state: positions={self.positions}")

        except Exception as e:
            logger.error(f"[{self.display_name}] Error restoring state: {str(e)}")

    def _persist_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'positions': self.positions,
                    'next_trade_id': self._next_trade_id,
                }, f, default=str)
        except Exception as e:
            logger.error(f"[{self.display_name}] Error persisting state: {str(e)}")

    def _handle_day_rollover(self):
        today = datetime.now().date()
        if today != self.current_date:
            logger.info(f"[{self.display_name}] Day rollover {self.current_date} -> {today}.")
            self.current_date = today
            self.last_scan_time = {s: None for s in SYMBOLS}
            self._persist_state()

    # ------------------------------------------------------------------
    # Entry window
    # ------------------------------------------------------------------
    def _within_entry_window(self) -> bool:
        now_t = datetime.now().time()
        return config.TRADING_START_TIME <= now_t <= config.ENTRY_END_TIME

    # ------------------------------------------------------------------
    # PCR confluence gate
    # ------------------------------------------------------------------
    def _passes_pcr_filter(self, symbol: str, expiry_date: str, signal_type: str):
        """
        Lenient gate: only vetoes a signal that directly contradicts chain-wide
        sentiment. Fails OPEN (allows the trade) if PCR can't be fetched, so a
        transient option-chain fetch failure doesn't just block this test
        strategy entirely - either way the outcome is logged into the trade's
        entry reason for later analysis.

        Returns (passed: bool, note: str, full_pcr: Optional[float]) - full_pcr
        is handed to _passes_roc_filter so it doesn't need a second option-chain
        fetch for the same decision.
        """
        try:
            pcr = data_manager.calculate_oi_pcr(symbol, expiry_date)
        except Exception as e:
            logger.warning(f"[{self.display_name}] PCR fetch error for {symbol}: {e}")
            return True, "PCR unavailable (fetch error) - allowed", None

        if pcr is None:
            return True, "PCR unavailable - allowed", None

        full_pcr = pcr['full']
        if signal_type == "CALL" and full_pcr > config.CREDIT_A_PCR_BULL_ABOVE:
            return False, f"PCR(full)={full_pcr} > {config.CREDIT_A_PCR_BULL_ABOVE} (bull sentiment) - CALL-sell blocked", full_pcr
        if signal_type == "PUT" and full_pcr < config.CREDIT_A_PCR_BEAR_BELOW:
            return False, f"PCR(full)={full_pcr} < {config.CREDIT_A_PCR_BEAR_BELOW} (bear sentiment) - PUT-sell blocked", full_pcr

        return True, f"PCR(full)={full_pcr} - aligned/neutral", full_pcr

    def _pcr_n_minutes_ago(self, symbol: str, minutes: int):
        """
        Look up the logged full-chain PCR reading closest to (now - minutes)
        from Mongo's oi_pcr history (mongo_logger.get_oi_pcr_history) - a pure
        DB read, no extra Dhan API call. Today's history can be as dense as
        1-per-minute (backfill_oi_pcr replays historical 1-min candles at
        startup) or 1-per-3-min (the live run_oi_pcr_job cadence), so the
        query asks for more points than the lookback window strictly needs
        rather than assuming either cadence. Returns None if MongoDB is
        disabled/unreachable or there isn't a reading old enough yet (e.g.
        the first ~15-20 minutes after market open).
        """
        if not mongo_logger.enabled:
            return None
        try:
            limit = max(minutes + 15, 20)
            history = mongo_logger.get_oi_pcr_history(symbol, limit=limit)
            if not history:
                return None

            target_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

            past_point = None
            for point in history:  # ascending (oldest -> newest)
                ts = point.get('timestamp')
                if not ts:
                    continue
                try:
                    point_time = datetime.fromisoformat(ts)
                except ValueError:
                    continue
                if point_time <= target_time:
                    past_point = point
                else:
                    break

            if past_point is None:
                return None

            return past_point.get('value_full')

        except Exception as e:
            logger.warning(f"[{self.display_name}] Error looking up PCR history for {symbol}: {e}")
            return None

    def _passes_roc_filter(self, symbol: str, signal_type: str, current_full_pcr: float):
        """
        Extra veto layered on top of _passes_pcr_filter's level check, for the
        case discussed 2026-08-18: PCR hasn't crossed the OPPOSITE boundary
        yet, but is moving toward it fast (e.g. 0.6 -> 0.86 within an hour
        after a gap-down) - OI-based PCR lags a fast price reversal, so the
        static level alone would still let a stale, contradicted trade
        through. Only checked in the still-opposite-looking zone (CALL: PCR <
        CREDIT_A_PCR_BEAR_BELOW; PUT: PCR > CREDIT_A_PCR_BULL_ABOVE) - the
        neutral band and the already-aligned zone are left alone, per user
        direction. Fails OPEN if there isn't enough history yet.

        Returns (passed: bool, note: str).
        """
        try:
            if signal_type == "CALL" and current_full_pcr < config.CREDIT_A_PCR_BEAR_BELOW:
                past_pcr = self._pcr_n_minutes_ago(symbol, config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES)
                if past_pcr is None:
                    return True, "ROC check skipped (insufficient history)"
                delta = current_full_pcr - past_pcr
                if delta > config.CREDIT_A_PCR_ROC_THRESHOLD:
                    return False, (
                        f"PCR rose {delta:+.3f} in {config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES}min "
                        f"({past_pcr}->{current_full_pcr}) - recovering fast, CALL-sell blocked"
                    )
                return True, f"ROC {delta:+.3f}/{config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES}min - not fast enough to block"

            if signal_type == "PUT" and current_full_pcr > config.CREDIT_A_PCR_BULL_ABOVE:
                past_pcr = self._pcr_n_minutes_ago(symbol, config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES)
                if past_pcr is None:
                    return True, "ROC check skipped (insufficient history)"
                delta = current_full_pcr - past_pcr
                if delta < -config.CREDIT_A_PCR_ROC_THRESHOLD:
                    return False, (
                        f"PCR fell {delta:+.3f} in {config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES}min "
                        f"({past_pcr}->{current_full_pcr}) - reversing fast, PUT-sell blocked"
                    )
                return True, f"ROC {delta:+.3f}/{config.CREDIT_A_PCR_ROC_LOOKBACK_MINUTES}min - not fast enough to block"

            return True, "ROC check not applicable (outside opposite-zone)"

        except Exception as e:
            logger.warning(f"[{self.display_name}] ROC filter error for {symbol}: {e}")
            return True, "ROC check error - allowed"

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------
    def _maybe_scan_entry(self, symbol, call_strike, put_strike, expiry_date, spread_width, lot_size):
        last_scan = self.last_scan_time.get(symbol)
        if last_scan is not None and (datetime.now() - last_scan).total_seconds() < self.scan_interval_seconds:
            return
        self.last_scan_time[symbol] = datetime.now()

        try:
            call_df = data_manager.get_option_data_with_indicators(
                "CE", call_strike, expiry_date, symbol, interval=self.candle_interval
            )
            call_signal, call_conditions = False, {}
            if call_df is not None and len(call_df) >= config.SMA_OI_PERIOD:
                call_conditions = Indicators.check_entry_conditions(call_df, option_type="CALL")
                call_signal = call_conditions.get('entry_signal', False)

            time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

            put_df = data_manager.get_option_data_with_indicators(
                "PE", put_strike, expiry_date, symbol, interval=self.candle_interval
            )
            put_signal, put_conditions = False, {}
            if put_df is not None and len(put_df) >= config.SMA_OI_PERIOD:
                put_conditions = Indicators.check_entry_conditions(put_df, option_type="PUT")
                put_signal = put_conditions.get('entry_signal', False)

            # Whichever signal fires wins this cycle - no simultaneous CE+PE,
            # matching CREDIT_A's own direct-mapping rule (see order_manager.py).
            if call_signal:
                passed, pcr_note, full_pcr = self._passes_pcr_filter(symbol, expiry_date, "CALL")
                if passed and full_pcr is not None:
                    passed, roc_note = self._passes_roc_filter(symbol, "CALL", full_pcr)
                    pcr_note = f"{pcr_note} | {roc_note}"
                if not passed:
                    logger.info(f"🚫 [{self.display_name}] {symbol} CALL signal blocked: {pcr_note}")
                    return
                logger.info(f"🟢 [{self.display_name}] {symbol} CALL SIGNAL: {call_strike} @ ₹{call_conditions.get('close', 0):.2f} | {pcr_note}")
                entry_reason = f"{call_conditions.get('reasoning', '')} | {pcr_note}"
                self.simulate_entry(
                    symbol, "CALL", "SHORT_CALL_SPREAD", "CALL", call_strike,
                    "CALL", call_strike + spread_width, expiry_date, lot_size, entry_reason
                )
            elif put_signal:
                passed, pcr_note, full_pcr = self._passes_pcr_filter(symbol, expiry_date, "PUT")
                if passed and full_pcr is not None:
                    passed, roc_note = self._passes_roc_filter(symbol, "PUT", full_pcr)
                    pcr_note = f"{pcr_note} | {roc_note}"
                if not passed:
                    logger.info(f"🚫 [{self.display_name}] {symbol} PUT signal blocked: {pcr_note}")
                    return
                logger.info(f"🔴 [{self.display_name}] {symbol} PUT SIGNAL: {put_strike} @ ₹{put_conditions.get('close', 0):.2f} | {pcr_note}")
                entry_reason = f"{put_conditions.get('reasoning', '')} | {pcr_note}"
                self.simulate_entry(
                    symbol, "PUT", "SHORT_PUT_SPREAD", "PUT", put_strike,
                    "PUT", put_strike - spread_width, expiry_date, lot_size, entry_reason
                )

        except Exception as e:
            logger.error(f"[{self.display_name}] Error scanning entry for {symbol}: {str(e)}")

    def simulate_entry(self, symbol, signal_type, spread_type, near_option_type, near_strike,
                        far_option_type, far_strike, expiry_date, lot_size, entry_reason):
        try:
            near_instrument_key = dhan_client.get_instrument_key(
                symbol=symbol, strike=near_strike,
                option_type="CE" if near_option_type == "CALL" else "PE", expiry_date=expiry_date,
            )
            far_instrument_key = dhan_client.get_instrument_key(
                symbol=symbol, strike=far_strike,
                option_type="CE" if far_option_type == "CALL" else "PE", expiry_date=expiry_date,
            )
            if not near_instrument_key or not far_instrument_key:
                logger.warning(f"[{self.display_name}] Could not resolve instrument keys for {symbol} {near_strike}/{far_strike}")
                return

            near_price = data_manager.get_live_price(near_instrument_key)
            far_price = data_manager.get_live_price(far_instrument_key)
            if near_price is None or far_price is None:
                logger.warning(f"[{self.display_name}] Could not fetch leg prices for {symbol} {near_strike}/{far_strike}")
                return

            net_credit = near_price - far_price
            if net_credit <= 0:
                logger.info(f"[{self.display_name}] {symbol} {near_strike}/{far_strike} non-positive net credit (₹{net_credit:.2f}), skipping.")
                return

            sl_percent = config.CREDIT_SPREAD_SL_PERCENT
            target_percent = config.CREDIT_SPREAD_PROFIT_TARGET_PERCENT
            stop_loss_value = near_price * (1 + sl_percent / 100.0)
            profit_target_value = net_credit * (1 - target_percent / 100.0)

            trade_id = f"{self.strategy_tag}_{self._next_trade_id}"
            mongo_trade_id = self.mongo_trade_id_offset + self._next_trade_id
            self._next_trade_id += 1
            entry_time = datetime.now()

            position = {
                'trade_id': trade_id, 'mongo_trade_id': mongo_trade_id, 'symbol': symbol,
                'signal_type': signal_type, 'spread_type': spread_type,
                'near_option_type': near_option_type, 'near_strike': near_strike,
                'near_instrument_key': near_instrument_key, 'near_entry_price': near_price,
                'far_option_type': far_option_type, 'far_strike': far_strike,
                'far_instrument_key': far_instrument_key, 'far_entry_price': far_price,
                'net_credit': net_credit, 'stop_loss_value': stop_loss_value,
                'best_near_price': near_price, 'trailing_active': False,
                'profit_target_value': profit_target_value, 'sl_percent': sl_percent,
                'lot_size': lot_size, 'entry_time': entry_time.isoformat(), 'expiry_date': expiry_date,
            }
            self.positions[symbol] = position
            self._persist_state()

            mongo_logger.log_trade(
                timestamp=entry_time, trade_id=mongo_trade_id, option_type=near_option_type, strike=near_strike,
                action="BUY", price=near_price, quantity=lot_size, stop_loss=stop_loss_value,
                symbol=symbol, instrument_key=near_instrument_key, expiry_date=expiry_date, lot_size=lot_size,
                reason=entry_reason, strategy_tag=self.strategy_tag,
                is_spread=True, spread_type=spread_type, signal_type=signal_type,
                far_option_type=far_option_type, far_strike=far_strike, far_instrument_key=far_instrument_key,
                far_price=far_price, net_credit=net_credit, stop_loss_value=stop_loss_value,
                profit_target_value=profit_target_value,
            )

            telegram_notifier.send_custom_message(f"📉 [PAPER] {self.display_name} {spread_type} Opened - {symbol}", {
                "Sold": f"{near_option_type} {near_strike} @ ₹{near_price:.2f}",
                "Hedge": f"{far_option_type} {far_strike} @ ₹{far_price:.2f}",
                "Net Credit": f"₹{net_credit:.2f}",
                "Stop Loss (near-leg price)": f"₹{stop_loss_value:.2f}",
                "Profit Target (cost to close)": f"₹{profit_target_value:.2f}",
                "Lots": lot_size,
                "Reason": entry_reason,
            })
            logger.info(f"✅ [{self.display_name} PAPER] Opened {symbol} {spread_type} {near_strike}/{far_strike} | Net Credit: ₹{net_credit:.2f}")

        except Exception as e:
            logger.error(f"[{self.display_name}] Error simulating entry for {symbol}: {str(e)}")

    # ------------------------------------------------------------------
    # Exit checks
    # ------------------------------------------------------------------
    def _update_trailing_stop_loss(self, position, near_price: float) -> None:
        """Ratchet the SL down as the near leg's own price improves - mirrors
        order_manager._update_trailing_stop_loss exactly (same % logic)."""
        best_value = position.get('best_near_price', position['near_entry_price'])
        if near_price >= best_value:
            return

        position['best_near_price'] = near_price
        trailed_sl = near_price * (1 + position['sl_percent'] / 100.0)

        if trailed_sl < position['stop_loss_value']:
            position['stop_loss_value'] = trailed_sl
            position['trailing_active'] = True
            self._persist_state()
            mongo_logger.update_trade_state(position['mongo_trade_id'], {
                'stop_loss_value': trailed_sl,
                'best_near_price': near_price,
                'trailing_active': True,
            })

    def _check_exit(self, symbol: str):
        position = self.positions[symbol]
        if position is None:
            return
        try:
            near_price = data_manager.get_live_price(position['near_instrument_key'])
            if near_price is None:
                return

            self._update_trailing_stop_loss(position, near_price)

            if near_price >= position['stop_loss_value']:
                exit_reason = "Trailing Stop Loss" if position.get('trailing_active') else "Stop Loss"
                self.simulate_exit(symbol, exit_reason)
                return

            far_price = data_manager.get_live_price(position['far_instrument_key'])
            if far_price is not None:
                net_spread_value = near_price - far_price
                if net_spread_value <= position['profit_target_value']:
                    self.simulate_exit(symbol, "Profit Target")

        except Exception as e:
            logger.error(f"[{self.display_name}] Error checking exit for {symbol}: {str(e)}")

    def simulate_exit(self, symbol: str, exit_reason: str):
        position = self.positions[symbol]
        if position is None:
            return
        try:
            near_exit_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])
            far_exit_price = data_manager.get_latest_price_from_websocket(position['far_instrument_key']) or dhan_client.get_current_price(position['far_instrument_key'])
            if near_exit_price is None:
                logger.warning(f"[{self.display_name}] Could not fetch near-leg exit price for {symbol}, skipping exit this tick.")
                return
            far_exit_price = far_exit_price or 0.0

            net_debit_to_close = near_exit_price - far_exit_price
            pnl = (position['net_credit'] - net_debit_to_close) * position['lot_size']
            exit_time = datetime.now()

            mongo_logger.log_trade(
                timestamp=exit_time, trade_id=position['mongo_trade_id'], option_type=position['near_option_type'],
                strike=position['near_strike'], action="SELL", price=near_exit_price, quantity=position['lot_size'],
                reason=exit_reason, pnl=pnl, symbol=symbol, instrument_key=position['near_instrument_key'],
                expiry_date=position.get('expiry_date', ''), lot_size=position['lot_size'], strategy_tag=self.strategy_tag,
                is_spread=True, spread_type=position['spread_type'], signal_type=position['signal_type'],
                far_option_type=position['far_option_type'], far_strike=position['far_strike'],
                far_instrument_key=position['far_instrument_key'], far_price=far_exit_price,
                net_credit=position['net_credit'],
            )

            telegram_notifier.send_custom_message(f"📈 [PAPER] {self.display_name} {position['spread_type']} Closed - {symbol}", {
                "Reason": exit_reason,
                "Net Credit Received": f"₹{position['net_credit']:.2f}",
                "Cost to Close": f"₹{net_debit_to_close:.2f}",
                "P&L": f"{'+' if pnl >= 0 else ''}₹{pnl:.2f}",
                "Lots": position['lot_size'],
            })
            logger.info(f"✅ [{self.display_name} PAPER] Closed {symbol} {position['spread_type']} | P&L: {'+' if pnl >= 0 else ''}₹{pnl:.2f} | Reason: {exit_reason}")

            self.positions[symbol] = None
            self._persist_state()

        except Exception as e:
            logger.error(f"[{self.display_name}] Error simulating exit for {symbol}: {str(e)}")

    def close_all_positions_eod(self):
        for symbol in SYMBOLS:
            if self.positions[symbol] is not None:
                self.simulate_exit(symbol, "EOD Square Off")

    # ------------------------------------------------------------------
    # Top-level scheduler entry point
    # ------------------------------------------------------------------
    def monitor_tick(self, nifty_enabled, nifty_call_strike, nifty_put_strike, nifty_expiry_date,
                      sensex_enabled, sensex_call_strike, sensex_put_strike, sensex_expiry_date):
        self._handle_day_rollover()

        symbol_args = {
            "NIFTY": (
                nifty_enabled, nifty_call_strike, nifty_put_strike, nifty_expiry_date,
                config.NIFTY_TRADING_DAYS, config.SPREAD_WIDTH_NIFTY,
                config.NIFTY_LOT_MULTIPLIER * config.NIFTY_LOT_SIZE,
            ),
            "SENSEX": (
                sensex_enabled, sensex_call_strike, sensex_put_strike, sensex_expiry_date,
                config.SENSEX_TRADING_DAYS, config.SPREAD_WIDTH_SENSEX,
                config.SENSEX_LOT_MULTIPLIER * config.SENSEX_LOT_SIZE,
            ),
        }

        for symbol, (enabled, call_strike, put_strike, expiry_date, trading_days, spread_width, lot_size) in symbol_args.items():
            if not enabled or not call_strike or not put_strike:
                continue
            if datetime.now().weekday() not in trading_days:
                continue

            if self.positions[symbol] is not None:
                self._check_exit(symbol)
                continue

            if not self._within_entry_window():
                continue

            self._maybe_scan_entry(symbol, call_strike, put_strike, expiry_date, spread_width, lot_size)


# Two isolated instances - same logic, different candle interval. Mongo
# trade-id ranges: CREDIT_A_PCR_1MIN=600M, CREDIT_A_PCR_3MIN=700M,
# CREDIT_A_3MIN=800M (credit_a_3min_strategy.py), Supertrend=900M
# (supertrend_strategy.py) - all comfortably clear of CREDIT_A's own live
# trade_tracker.trade_counter (small per-day counts).
credit_a_pcr_1min_strategy = CreditAPcrStrategy(
    candle_interval=config.CREDIT_A_PCR_1MIN_CANDLE_INTERVAL,
    strategy_tag=config.CREDIT_A_PCR_1MIN_TAG,
    display_name="CREDIT_A PCR 1min",
    state_file=os.path.join(config.BASE_DIR, "credit_a_pcr_1min_state.json"),
    mongo_trade_id_offset=600_000_000,
    scan_interval_seconds=config.CREDIT_A_PCR_1MIN_SCAN_INTERVAL_SECONDS,
)

credit_a_pcr_3min_strategy = CreditAPcrStrategy(
    candle_interval=config.CREDIT_A_PCR_3MIN_CANDLE_INTERVAL,
    strategy_tag=config.CREDIT_A_PCR_3MIN_TAG,
    display_name="CREDIT_A PCR 3min",
    state_file=os.path.join(config.BASE_DIR, "credit_a_pcr_3min_state.json"),
    mongo_trade_id_offset=700_000_000,
    scan_interval_seconds=config.CREDIT_A_PCR_3MIN_SCAN_INTERVAL_SECONDS,
)
