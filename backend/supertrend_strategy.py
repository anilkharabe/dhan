"""
Supertrend credit spread strategy - isolated paper-trading test (backend/config.py:
SUPERTREND_CS_ENABLED). See the plan this was built from for the full rationale.

Deliberately self-contained and NEVER touches order_manager.active_positions,
order_manager.has_position*, or trade_tracker.* - that isolation is what
guarantees this can never block, or be blocked by, the live CREDIT_A strategy
(order_manager.restore_state() restores ANY open trade_tracker trade regardless
of strategy_tag, and has_any_position_for_symbol() also ignores strategy_tag -
tracing those two functions is what drove this module's design). It also never
calls dhan_client.place_order - every fill is a synthetic paper simulation at
the fetched LTP, unconditionally (not gated on config.PAPER_TRADING).
"""
import json
import math
import os
from datetime import datetime

import pandas as pd

import config
import logger
from dhan_api import dhan_client
from data_manager import data_manager
from indicators import Indicators
from futures_data import fetch_futures_candles
from mongo_logger import mongo_logger
from telegram_notifier import telegram_notifier

STATE_FILE = os.path.join(config.BASE_DIR, "supertrend_state.json")

SYMBOLS = ["NIFTY", "SENSEX"]


class SupertrendStrategy:
    """Own, isolated state/lifecycle for the Supertrend paper-trading test."""

    def __init__(self):
        self.positions = {s: None for s in SYMBOLS}
        self.traded_today = {s: False for s in SYMBOLS}
        self.last_processed_candle_ts = {s: None for s in SYMBOLS}
        self.current_date = datetime.now().date()
        self._next_trade_id = 1

    # ------------------------------------------------------------------
    # Persistence (own state file - never touches trade_tracker)
    # ------------------------------------------------------------------
    def restore_state(self):
        try:
            if not os.path.exists(STATE_FILE):
                logger.info("[Supertrend] No saved state found, starting fresh.")
                return

            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)

            saved_date = saved.get('date')
            if saved_date != datetime.now().strftime('%Y-%m-%d'):
                logger.info(f"[Supertrend] Saved state is from {saved_date}, discarding (stale).")
                return

            self.positions = saved.get('positions', {s: None for s in SYMBOLS})
            self.traded_today = saved.get('traded_today', {s: False for s in SYMBOLS})
            self._next_trade_id = saved.get('next_trade_id', 1)
            logger.info(f"[Supertrend] Restored state: positions={self.positions}, traded_today={self.traded_today}")

        except Exception as e:
            logger.error(f"[Supertrend] Error restoring state: {str(e)}")

    def _persist_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump({
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'positions': self.positions,
                    'traded_today': self.traded_today,
                    'next_trade_id': self._next_trade_id,
                }, f, default=str)
        except Exception as e:
            logger.error(f"[Supertrend] Error persisting state: {str(e)}")

    def _handle_day_rollover(self):
        today = datetime.now().date()
        if today != self.current_date:
            logger.info(f"[Supertrend] Day rollover {self.current_date} -> {today}, resetting traded_today.")
            self.current_date = today
            self.traded_today = {s: False for s in SYMBOLS}
            self.last_processed_candle_ts = {s: None for s in SYMBOLS}
            self._persist_state()

    # ------------------------------------------------------------------
    # Day-of-week / config helpers
    # ------------------------------------------------------------------
    def is_trading_day(self, symbol: str) -> bool:
        weekday = datetime.now().weekday()
        return weekday in config.SUPERTREND_CS_CONFIG[symbol]["trading_days"]

    def get_sl_percent(self, symbol: str) -> float:
        weekday = datetime.now().weekday()
        return config.SUPERTREND_CS_CONFIG[symbol]["sl_percent_by_day"][weekday]

    def _lot_size(self, symbol: str) -> int:
        if symbol == "NIFTY":
            return config.NIFTY_LOT_MULTIPLIER * config.NIFTY_LOT_SIZE
        return config.SENSEX_LOT_MULTIPLIER * config.SENSEX_LOT_SIZE

    def _spread_width(self, symbol: str) -> int:
        return config.SPREAD_WIDTH_NIFTY if symbol == "NIFTY" else config.SPREAD_WIDTH_SENSEX

    def _expiry_day(self, symbol: str) -> int:
        return config.NIFTY_EXPIRY_DAY if symbol == "NIFTY" else config.SENSEX_EXPIRY_DAY

    def resolve_strikes(self, symbol: str, direction: str, supertrend_value: float):
        """
        Uptrend -> sell PE at floor(supertrend/100)*100, protective long PE further
        below. Downtrend -> sell CE at ceil(supertrend/100)*100, protective long CE
        further above. Direct mapping - NOT the same signal_type/spread_type
        inversion CREDIT_A uses.
        """
        width = self._spread_width(symbol)
        if direction == 'up':
            near_strike = int(math.floor(supertrend_value / 100.0) * 100)
            far_strike = near_strike - width
            return near_strike, far_strike, 'PE', 'PE'
        else:
            near_strike = int(math.ceil(supertrend_value / 100.0) * 100)
            far_strike = near_strike + width
            return near_strike, far_strike, 'CE', 'CE'

    # ------------------------------------------------------------------
    # Data / signal
    # ------------------------------------------------------------------
    def fetch_supertrend_df(self, symbol: str):
        df = fetch_futures_candles(symbol)
        if df is None or df.empty:
            return None
        return Indicators.calculate_supertrend(df, period=config.SUPERTREND_PERIOD, multiplier=config.SUPERTREND_MULTIPLIER)

    def poll_for_new_closed_candle(self, symbol: str, df):
        """
        Returns the most recently CLOSED 3-min candle row, or None if there
        isn't a new one since the last check. A candle is treated as closed
        once its timestamp + interval has actually elapsed (small buffer
        against Dhan not having finalized the bar yet).
        """
        if df is None or df.empty:
            return None

        valid = df.dropna(subset=['supertrend'])
        if valid.empty:
            return None

        last_row = valid.iloc[-1]
        last_ts = valid.index[-1]

        interval_minutes = int(config.SUPERTREND_CANDLE_INTERVAL.replace("minute", "") or "3")
        candle_close_time = last_ts + pd.Timedelta(minutes=interval_minutes)
        if datetime.now() < candle_close_time:
            return None  # this candle is still forming

        if self.last_processed_candle_ts[symbol] == last_ts:
            return None  # already processed

        self.last_processed_candle_ts[symbol] = last_ts
        return last_row

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------
    def _within_entry_window(self) -> bool:
        now_t = datetime.now().time()
        return config.TRADING_START_TIME <= now_t <= config.ENTRY_END_TIME

    def evaluate_entry(self, symbol: str, closed_candle):
        if not self.is_trading_day(symbol):
            return
        if self.traded_today[symbol] or self.positions[symbol] is not None:
            return
        if not self._within_entry_window():
            return

        direction = closed_candle.get('supertrend_direction')
        supertrend_value = closed_candle.get('supertrend')
        if direction not in ('up', 'down') or supertrend_value is None:
            return

        near_strike, far_strike, near_type, far_type = self.resolve_strikes(symbol, direction, supertrend_value)
        expiry_date = data_manager.get_expiry_date(datetime.now(), self._expiry_day(symbol))

        self.simulate_entry(symbol, direction, supertrend_value, near_strike, far_strike, near_type, far_type, expiry_date)

    def simulate_entry(self, symbol, direction, supertrend_value, near_strike, far_strike, near_type, far_type, expiry_date):
        try:
            near_instrument_key = dhan_client.get_instrument_key(symbol, near_strike, near_type, expiry_date)
            far_instrument_key = dhan_client.get_instrument_key(symbol, far_strike, far_type, expiry_date)
            if not near_instrument_key or not far_instrument_key:
                logger.warning(f"[Supertrend] Could not resolve instrument keys for {symbol} {near_strike}/{far_strike} {near_type}")
                return

            near_price = data_manager.get_latest_price_from_websocket(near_instrument_key) or dhan_client.get_current_price(near_instrument_key)
            far_price = data_manager.get_latest_price_from_websocket(far_instrument_key) or dhan_client.get_current_price(far_instrument_key)
            if near_price is None or far_price is None:
                logger.warning(f"[Supertrend] Could not fetch leg prices for {symbol} {near_strike}/{far_strike}")
                return

            net_credit = near_price - far_price
            if net_credit <= 0:
                logger.info(f"[Supertrend] {symbol} {near_strike}/{far_strike} non-positive net credit (₹{net_credit:.2f}), skipping.")
                return

            sl_percent = self.get_sl_percent(symbol)
            stop_loss_value = near_price * (1 + sl_percent / 100.0)
            profit_target_value = net_credit * (1 - config.SUPERTREND_PROFIT_TARGET_PERCENT / 100.0)
            lot_size = self._lot_size(symbol)
            trade_id = f"SUPERTREND_{self._next_trade_id}"
            self._next_trade_id += 1
            entry_time = datetime.now()

            position = {
                'trade_id': trade_id, 'symbol': symbol, 'direction': direction,
                'entry_supertrend': supertrend_value,
                'near_option_type': near_type, 'near_strike': near_strike,
                'near_instrument_key': near_instrument_key, 'near_entry_price': near_price,
                'far_option_type': far_type, 'far_strike': far_strike,
                'far_instrument_key': far_instrument_key, 'far_entry_price': far_price,
                'net_credit': net_credit, 'stop_loss_value': stop_loss_value,
                'profit_target_value': profit_target_value, 'sl_percent': sl_percent,
                'lot_size': lot_size, 'entry_time': entry_time.isoformat(), 'expiry_date': expiry_date,
            }
            self.positions[symbol] = position
            self.traded_today[symbol] = True
            self._persist_state()

            mongo_logger.log_trade(
                timestamp=entry_time, trade_id=hash(trade_id) & 0x7FFFFFFF, option_type=near_type, strike=near_strike,
                action="BUY", price=near_price, quantity=lot_size, stop_loss=stop_loss_value,
                symbol=symbol, instrument_key=near_instrument_key, expiry_date=expiry_date, lot_size=lot_size,
                reason=f"Supertrend {direction} @ {supertrend_value:.1f}", strategy_tag=config.SUPERTREND_CS_TAG,
                is_spread=True, spread_type=f"SUPERTREND_{direction.upper()}", signal_type=near_type,
                far_option_type=far_type, far_strike=far_strike, far_instrument_key=far_instrument_key,
                far_price=far_price, net_credit=net_credit, stop_loss_value=stop_loss_value,
                profit_target_value=profit_target_value,
            )

            telegram_notifier.send_custom_message(f"📉 [PAPER] Supertrend {near_type} Opened - {symbol}", {
                "Sold": f"{near_type} {near_strike} @ ₹{near_price:.2f}",
                "Hedge": f"{far_type} {far_strike} @ ₹{far_price:.2f}",
                "Net Credit": f"₹{net_credit:.2f}",
                "Supertrend": f"{supertrend_value:.1f} ({direction})",
                "Stop Loss": f"₹{stop_loss_value:.2f} ({sl_percent}%)",
                "Lots": lot_size,
            })
            logger.info(f"✅ [Supertrend PAPER] Opened {symbol} {near_type} {near_strike}/{far_strike} | Net Credit: ₹{net_credit:.2f}")

        except Exception as e:
            logger.error(f"[Supertrend] Error simulating entry for {symbol}: {str(e)}")

    # ------------------------------------------------------------------
    # Exit checks
    # ------------------------------------------------------------------
    def check_fixed_sl_and_target(self, symbol: str):
        position = self.positions[symbol]
        if position is None:
            return
        try:
            near_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])
            if near_price is None:
                return

            if near_price >= position['stop_loss_value']:
                self.simulate_exit(symbol, "Stop Loss")
                return

            far_price = data_manager.get_latest_price_from_websocket(position['far_instrument_key']) or dhan_client.get_current_price(position['far_instrument_key'])
            if far_price is not None:
                cost_to_close = near_price - far_price
                if cost_to_close <= position['profit_target_value']:
                    self.simulate_exit(symbol, "Profit Target")

        except Exception as e:
            logger.error(f"[Supertrend] Error checking SL/target for {symbol}: {str(e)}")

    def check_trend_flip_exit(self, symbol: str, closed_candle):
        """
        Exit only on an actual trend REVERSAL, not continuation. In an uptrend
        the Supertrend line sits below price (support); a short PE exits when
        price closes BELOW it (support breaking = trend reversing down).
        Mirrored for a downtrend/short CE (resistance breaking = reversing up).

        NOTE: this is the opposite of close_price > supertrend_value for the
        'up' case - that condition is true on almost every candle during a
        stable uptrend (price naturally sits above its own support line),
        which caused positions to exit within one candle of entry almost
        every time - caught via a local replay against real historical spot
        data before this ever ran live. Confirmed fix 2026-07-24.
        """
        position = self.positions[symbol]
        if position is None:
            return
        try:
            close_price = closed_candle.get('close')
            supertrend_value = closed_candle.get('supertrend')
            if close_price is None or supertrend_value is None:
                return

            if position['direction'] == 'up' and close_price < supertrend_value:
                self.simulate_exit(symbol, "Trend Flip (candle close below Supertrend)")
            elif position['direction'] == 'down' and close_price > supertrend_value:
                self.simulate_exit(symbol, "Trend Flip (candle close above Supertrend)")

        except Exception as e:
            logger.error(f"[Supertrend] Error checking trend-flip exit for {symbol}: {str(e)}")

    def simulate_exit(self, symbol: str, exit_reason: str):
        position = self.positions[symbol]
        if position is None:
            return
        try:
            near_exit_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])
            far_exit_price = data_manager.get_latest_price_from_websocket(position['far_instrument_key']) or dhan_client.get_current_price(position['far_instrument_key'])
            if near_exit_price is None:
                logger.warning(f"[Supertrend] Could not fetch near-leg exit price for {symbol}, skipping exit this tick.")
                return
            far_exit_price = far_exit_price or 0.0

            net_debit_to_close = near_exit_price - far_exit_price
            pnl = (position['net_credit'] - net_debit_to_close) * position['lot_size']
            exit_time = datetime.now()

            mongo_logger.log_trade(
                timestamp=exit_time, trade_id=hash(position['trade_id']) & 0x7FFFFFFF, option_type=position['near_option_type'],
                strike=position['near_strike'], action="SELL", price=near_exit_price, quantity=position['lot_size'],
                reason=exit_reason, pnl=pnl, symbol=symbol, instrument_key=position['near_instrument_key'],
                expiry_date=position.get('expiry_date', ''), lot_size=position['lot_size'], strategy_tag=config.SUPERTREND_CS_TAG,
                is_spread=True, spread_type=f"SUPERTREND_{position['direction'].upper()}", signal_type=position['near_option_type'],
                far_option_type=position['far_option_type'], far_strike=position['far_strike'],
                far_instrument_key=position['far_instrument_key'], far_price=far_exit_price,
                net_credit=position['net_credit'],
            )

            telegram_notifier.send_custom_message(f"📈 [PAPER] Supertrend {position['near_option_type']} Closed - {symbol}", {
                "Reason": exit_reason,
                "Net Credit Received": f"₹{position['net_credit']:.2f}",
                "Cost to Close": f"₹{net_debit_to_close:.2f}",
                "P&L": f"{'+' if pnl >= 0 else ''}₹{pnl:.2f}",
                "Lots": position['lot_size'],
            })
            logger.info(f"✅ [Supertrend PAPER] Closed {symbol} {position['near_option_type']} | P&L: {'+' if pnl >= 0 else ''}₹{pnl:.2f} | Reason: {exit_reason}")

            self.positions[symbol] = None
            self._persist_state()

        except Exception as e:
            logger.error(f"[Supertrend] Error simulating exit for {symbol}: {str(e)}")

    def close_all_positions_eod(self):
        for symbol in SYMBOLS:
            if self.positions[symbol] is not None:
                self.simulate_exit(symbol, "EOD Square Off")

    # ------------------------------------------------------------------
    # Top-level scheduler entry point
    # ------------------------------------------------------------------
    def monitor_tick(self):
        self._handle_day_rollover()

        for symbol in SYMBOLS:
            enabled = config.NIFTY_ENABLED if symbol == "NIFTY" else config.SENSEX_ENABLED
            if not enabled:
                continue

            # Frequent fixed SL/target check, independent of candle-close cadence
            if self.positions[symbol] is not None:
                self.check_fixed_sl_and_target(symbol)

            # Candle-close-driven entry/trend-flip check
            df = self.fetch_supertrend_df(symbol)
            closed_candle = self.poll_for_new_closed_candle(symbol, df)
            if closed_candle is None:
                continue

            if self.positions[symbol] is not None:
                self.check_trend_flip_exit(symbol, closed_candle)
            else:
                self.evaluate_entry(symbol, closed_candle)


supertrend_strategy = SupertrendStrategy()
