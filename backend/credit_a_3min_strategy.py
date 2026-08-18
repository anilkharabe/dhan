"""
CREDIT_A's OI/VWAP/RSI/ADX credit-spread signal engine re-run on 3-minute
option candles instead of CREDIT_A's live 1-minute ones - isolated
paper-trading A/B test (backend/config.py: CREDIT_A_3MIN_ENABLED).

Same isolation contract as supertrend_strategy.py: deliberately self-contained
and NEVER touches order_manager.active_positions, order_manager.has_position*,
or trade_tracker.* - order_manager.restore_state() restores ANY open
trade_tracker trade regardless of strategy_tag, and has_any_position_for_symbol()
also ignores strategy_tag, so sharing that state would let this test block or
be blocked by live CREDIT_A. It also never calls dhan_client.place_order -
every fill is a synthetic paper simulation at the fetched LTP, unconditionally
(not gated on config.PAPER_TRADING).

Strikes/expiry are read from the live AlgoTradingSystem's already-computed
ATM strikes (passed into monitor_tick() each tick) rather than independently
re-fetching spot price here - keeps this test trading the exact same strikes
CREDIT_A is, and avoids doubling spot-price API calls.

Entry scans (which need a fresh 3-min historical candle fetch, unlike the
cheap LTP-only SL/target checks) are gated to at most once every
CREDIT_A_3MIN_SCAN_INTERVAL_SECONDS per symbol - deliberately not fetched on
every tick, to keep this test's added Dhan API load modest. Written the day
after a Dhan rate-limit incident forced WebSocket off (see config.py's
USE_WEBSOCKET comment) - extra unpaced REST calls are exactly what to avoid
right now.
"""
import json
import os
import time
from datetime import datetime

import config
import logger
from dhan_api import dhan_client
from data_manager import data_manager
from indicators import Indicators
from mongo_logger import mongo_logger
from telegram_notifier import telegram_notifier

STATE_FILE = os.path.join(config.BASE_DIR, "credit_a_3min_state.json")

SYMBOLS = ["NIFTY", "SENSEX"]

# Offset added to the local trade counter to build the Mongo trade_id - keeps
# this strategy's ids in their own namespace, distinct from both CREDIT_A's
# live trade_tracker.trade_counter (small per-day counts) and Supertrend's
# 900_000_000+ range (see supertrend_strategy.py). Must be a stable int, not
# hash() - see that module's comment for why.
MONGO_TRADE_ID_OFFSET = 800_000_000


class CreditA3MinStrategy:
    """Own, isolated state/lifecycle for the CREDIT_A 3-min paper-trading test."""

    def __init__(self):
        self.positions = {s: None for s in SYMBOLS}
        self.last_scan_time = {s: None for s in SYMBOLS}
        self.current_date = datetime.now().date()
        self._next_trade_id = 1

    # ------------------------------------------------------------------
    # Persistence (own state file - never touches trade_tracker)
    # ------------------------------------------------------------------
    def restore_state(self):
        try:
            if not os.path.exists(STATE_FILE):
                logger.info("[CREDIT_A_3MIN] No saved state found, starting fresh.")
                return

            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)

            saved_date = saved.get('date')
            if saved_date != datetime.now().strftime('%Y-%m-%d'):
                logger.info(f"[CREDIT_A_3MIN] Saved state is from {saved_date}, discarding (stale).")
                return

            self.positions = saved.get('positions', {s: None for s in SYMBOLS})
            self._next_trade_id = saved.get('next_trade_id', 1)

            logger.info(f"[CREDIT_A_3MIN] Restored state: positions={self.positions}")

        except Exception as e:
            logger.error(f"[CREDIT_A_3MIN] Error restoring state: {str(e)}")

    def _persist_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump({
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'positions': self.positions,
                    'next_trade_id': self._next_trade_id,
                }, f, default=str)
        except Exception as e:
            logger.error(f"[CREDIT_A_3MIN] Error persisting state: {str(e)}")

    def _handle_day_rollover(self):
        today = datetime.now().date()
        if today != self.current_date:
            logger.info(f"[CREDIT_A_3MIN] Day rollover {self.current_date} -> {today}.")
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
    # Entry
    # ------------------------------------------------------------------
    def _maybe_scan_entry(self, symbol, call_strike, put_strike, expiry_date, spread_width, lot_size):
        last_scan = self.last_scan_time.get(symbol)
        if last_scan is not None and (datetime.now() - last_scan).total_seconds() < config.CREDIT_A_3MIN_SCAN_INTERVAL_SECONDS:
            return
        self.last_scan_time[symbol] = datetime.now()

        try:
            call_df = data_manager.get_option_data_with_indicators(
                "CE", call_strike, expiry_date, symbol, interval=config.CREDIT_A_3MIN_CANDLE_INTERVAL
            )
            call_signal, call_conditions = False, {}
            if call_df is not None and len(call_df) >= config.SMA_OI_PERIOD:
                call_conditions = Indicators.check_entry_conditions(call_df, option_type="CALL")
                call_signal = call_conditions.get('entry_signal', False)

            time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

            put_df = data_manager.get_option_data_with_indicators(
                "PE", put_strike, expiry_date, symbol, interval=config.CREDIT_A_3MIN_CANDLE_INTERVAL
            )
            put_signal, put_conditions = False, {}
            if put_df is not None and len(put_df) >= config.SMA_OI_PERIOD:
                put_conditions = Indicators.check_entry_conditions(put_df, option_type="PUT")
                put_signal = put_conditions.get('entry_signal', False)

            # Whichever signal fires wins this cycle - no simultaneous CE+PE,
            # matching CREDIT_A's own direct-mapping rule (see order_manager.py).
            if call_signal:
                logger.info(f"🟢 [CREDIT_A_3MIN] {symbol} CALL SIGNAL: {call_strike} @ ₹{call_conditions.get('close', 0):.2f}")
                self.simulate_entry(
                    symbol, "CALL", "SHORT_CALL_SPREAD", "CALL", call_strike,
                    "CALL", call_strike + spread_width, expiry_date, lot_size, call_conditions
                )
            elif put_signal:
                logger.info(f"🔴 [CREDIT_A_3MIN] {symbol} PUT SIGNAL: {put_strike} @ ₹{put_conditions.get('close', 0):.2f}")
                self.simulate_entry(
                    symbol, "PUT", "SHORT_PUT_SPREAD", "PUT", put_strike,
                    "PUT", put_strike - spread_width, expiry_date, lot_size, put_conditions
                )

        except Exception as e:
            logger.error(f"[CREDIT_A_3MIN] Error scanning entry for {symbol}: {str(e)}")

    def simulate_entry(self, symbol, signal_type, spread_type, near_option_type, near_strike,
                        far_option_type, far_strike, expiry_date, lot_size, conditions):
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
                logger.warning(f"[CREDIT_A_3MIN] Could not resolve instrument keys for {symbol} {near_strike}/{far_strike}")
                return

            near_price = data_manager.get_live_price(near_instrument_key)
            far_price = data_manager.get_live_price(far_instrument_key)
            if near_price is None or far_price is None:
                logger.warning(f"[CREDIT_A_3MIN] Could not fetch leg prices for {symbol} {near_strike}/{far_strike}")
                return

            net_credit = near_price - far_price
            if net_credit <= 0:
                logger.info(f"[CREDIT_A_3MIN] {symbol} {near_strike}/{far_strike} non-positive net credit (₹{net_credit:.2f}), skipping.")
                return

            sl_percent = config.CREDIT_SPREAD_SL_PERCENT
            target_percent = config.CREDIT_SPREAD_PROFIT_TARGET_PERCENT
            stop_loss_value = near_price * (1 + sl_percent / 100.0)
            profit_target_value = net_credit * (1 - target_percent / 100.0)

            trade_id = f"CREDIT_A_3MIN_{self._next_trade_id}"
            mongo_trade_id = MONGO_TRADE_ID_OFFSET + self._next_trade_id
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

            entry_reason = conditions.get('reasoning', '') if conditions else ''

            mongo_logger.log_trade(
                timestamp=entry_time, trade_id=mongo_trade_id, option_type=near_option_type, strike=near_strike,
                action="BUY", price=near_price, quantity=lot_size, stop_loss=stop_loss_value,
                symbol=symbol, instrument_key=near_instrument_key, expiry_date=expiry_date, lot_size=lot_size,
                reason=entry_reason, strategy_tag=config.CREDIT_A_3MIN_TAG,
                is_spread=True, spread_type=spread_type, signal_type=signal_type,
                far_option_type=far_option_type, far_strike=far_strike, far_instrument_key=far_instrument_key,
                far_price=far_price, net_credit=net_credit, stop_loss_value=stop_loss_value,
                profit_target_value=profit_target_value,
            )

            telegram_notifier.send_custom_message(f"📉 [PAPER] CREDIT_A 3min {spread_type} Opened - {symbol}", {
                "Sold": f"{near_option_type} {near_strike} @ ₹{near_price:.2f}",
                "Hedge": f"{far_option_type} {far_strike} @ ₹{far_price:.2f}",
                "Net Credit": f"₹{net_credit:.2f}",
                "Stop Loss (near-leg price)": f"₹{stop_loss_value:.2f}",
                "Profit Target (cost to close)": f"₹{profit_target_value:.2f}",
                "Lots": lot_size,
            })
            logger.info(f"✅ [CREDIT_A_3MIN PAPER] Opened {symbol} {spread_type} {near_strike}/{far_strike} | Net Credit: ₹{net_credit:.2f}")

        except Exception as e:
            logger.error(f"[CREDIT_A_3MIN] Error simulating entry for {symbol}: {str(e)}")

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
            logger.error(f"[CREDIT_A_3MIN] Error checking exit for {symbol}: {str(e)}")

    def simulate_exit(self, symbol: str, exit_reason: str):
        position = self.positions[symbol]
        if position is None:
            return
        try:
            near_exit_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])
            far_exit_price = data_manager.get_latest_price_from_websocket(position['far_instrument_key']) or dhan_client.get_current_price(position['far_instrument_key'])
            if near_exit_price is None:
                logger.warning(f"[CREDIT_A_3MIN] Could not fetch near-leg exit price for {symbol}, skipping exit this tick.")
                return
            far_exit_price = far_exit_price or 0.0

            net_debit_to_close = near_exit_price - far_exit_price
            pnl = (position['net_credit'] - net_debit_to_close) * position['lot_size']
            exit_time = datetime.now()

            mongo_logger.log_trade(
                timestamp=exit_time, trade_id=position['mongo_trade_id'], option_type=position['near_option_type'],
                strike=position['near_strike'], action="SELL", price=near_exit_price, quantity=position['lot_size'],
                reason=exit_reason, pnl=pnl, symbol=symbol, instrument_key=position['near_instrument_key'],
                expiry_date=position.get('expiry_date', ''), lot_size=position['lot_size'], strategy_tag=config.CREDIT_A_3MIN_TAG,
                is_spread=True, spread_type=position['spread_type'], signal_type=position['signal_type'],
                far_option_type=position['far_option_type'], far_strike=position['far_strike'],
                far_instrument_key=position['far_instrument_key'], far_price=far_exit_price,
                net_credit=position['net_credit'],
            )

            telegram_notifier.send_custom_message(f"📈 [PAPER] CREDIT_A 3min {position['spread_type']} Closed - {symbol}", {
                "Reason": exit_reason,
                "Net Credit Received": f"₹{position['net_credit']:.2f}",
                "Cost to Close": f"₹{net_debit_to_close:.2f}",
                "P&L": f"{'+' if pnl >= 0 else ''}₹{pnl:.2f}",
                "Lots": position['lot_size'],
            })
            logger.info(f"✅ [CREDIT_A_3MIN PAPER] Closed {symbol} {position['spread_type']} | P&L: {'+' if pnl >= 0 else ''}₹{pnl:.2f} | Reason: {exit_reason}")

            self.positions[symbol] = None
            self._persist_state()

        except Exception as e:
            logger.error(f"[CREDIT_A_3MIN] Error simulating exit for {symbol}: {str(e)}")

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


credit_a_3min_strategy = CreditA3MinStrategy()
