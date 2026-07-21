"""
Order Manager Module
Handles credit-spread order placement, execution, and position tracking
"""

from datetime import datetime
from typing import Optional, Dict, List
import time

import config
import logger
from dhan_api import dhan_client
from data_manager import data_manager
from trade_tracker import trade_tracker
from telegram_notifier import telegram_notifier
from mongo_logger import mongo_logger

class OrderManager:
    """Manage orders and positions with multi-stage profit booking"""
    
    def __init__(self):
        # Track positions separately for each index and option type
        # Example structure:
        # {
        #   "NIFTY": {"CALL": {...} or None, "PUT": {...} or None},
        #   "SENSEX": {"CALL": {...} or None, "PUT": {...} or None},
        # }
        #   "NIFTY": {"CALL": [pos1, pos2], "PUT": []},
        #   "SENSEX": {"CALL": [], "PUT": []},
        # }
        self.active_positions = {
            "NIFTY": {"CALL": [], "PUT": []},
            "SENSEX": {"CALL": [], "PUT": []},
        }
        
        # Cache for trailing SL to avoid fetching candles every 2 seconds
        # Format: {(symbol, option_type): {'last_update': timestamp, 'trailing_sl': float}}
        self.trailing_sl_cache = {}
        
    def restore_state(self):
        """
        Restore active positions from API or DB on startup.
        This prevents duplicate trades if the backend is restarted.
        """
        try:
            if config.PAPER_TRADING:
                logger.info("♻️  Restoring state from TradeTracker (Paper Trading)...")
                open_trades = trade_tracker.get_open_trades()
                
                if not open_trades:
                    logger.info("No active paper positions found.")
                    return
                    
                restored_count = 0
                for trade in open_trades:
                    if not trade.get('is_spread'):
                        continue  # Only credit-spread trades are ever opened going forward

                    symbol = trade.get('symbol')
                    # Fallback to infer symbol if missing from older logs
                    if not symbol:
                        symbol = "SENSEX" if trade.get('strike', 0) > 40000 else "NIFTY"

                    quantity = trade.get('lot_size', 0)
                    strategy_tag = trade.get('strategy_tag', 'STRATEGY_A')
                    signal_type = trade.get('signal_type')

                    if not symbol or not signal_type or quantity == 0:
                        continue
                    if self.has_position(signal_type, symbol, strategy_tag):
                        continue

                    spread_pos = {
                        'trade_id': trade.get('trade_id', f"RESTORED_{int(time.time())}"),
                        'symbol': symbol, 'signal_type': signal_type,
                        'spread_type': trade.get('spread_type', ''),
                        'near_option_type': trade.get('type'), 'near_strike': trade.get('strike', 0),
                        'near_instrument_key': trade.get('instrument_key', ''),
                        'near_entry_price': float(trade.get('entry_price', 0)),
                        'far_option_type': trade.get('far_option_type', ''), 'far_strike': trade.get('far_strike', 0),
                        'far_instrument_key': trade.get('far_instrument_key', ''),
                        'far_entry_price': float(trade.get('far_entry_price', 0)),
                        'net_credit': float(trade.get('net_credit', 0)),
                        'stop_loss_value': float(trade.get('stop_loss_value', 0)),
                        'profit_target_value': float(trade.get('profit_target_value', 0)),
                        'lot_size': quantity, 'expiry_date': trade.get('expiry_date', ''),
                        'strategy_tag': strategy_tag,
                        # Trailing SL state - fall back to near_entry_price (the starting
                        # near-leg price) if this trade never had a trailing update persisted.
                        'best_near_price': float(trade.get('best_near_price') or trade.get('near_entry_price', 0)),
                        'trailing_active': trade.get('trailing_active', False),
                    }
                    self.active_positions[symbol][signal_type].append(spread_pos)
                    logger.info(f"✅ Restored paper spread: {symbol} {spread_pos['spread_type']} (signal: {signal_type}) | Lots: {quantity}")
                    restored_count += 1

                logger.info(f"Paper restoration complete. {restored_count} positions restored.")
                return

            # Live (non-paper) restoration: Dhan's /positions response doesn't tag
            # which two legs belong to the same spread, so automatic reconstruction
            # isn't attempted here - just surface what Dhan reports and let the
            # operator reconcile manually (via Dhan's own app) before trading resumes.
            logger.info("♻️  Checking Dhan positions on startup...")
            positions = dhan_client.get_positions()

            if not positions:
                logger.info("No active positions found on Dhan.")
                return

            open_positions = [p for p in positions if int(p.get('netQty', 0) or 0) != 0]
            if open_positions:
                logger.warning(
                    f"⚠️ {len(open_positions)} open position(s) found on Dhan at startup. "
                    "Automatic spread reconstruction isn't supported live - verify these "
                    "manually in the Dhan app before trading resumes:"
                )
                for p in open_positions:
                    logger.warning(f"   {p.get('tradingSymbol')} | netQty: {p.get('netQty')} | costPrice: {p.get('costPrice')}")
            else:
                logger.info("No open positions found on Dhan.")

        except Exception as e:
            logger.error(f"Error restoring state: {str(e)}")
    
    # ========================================================================
    # CREDIT SPREADS
    # ========================================================================
    # Defined-risk vertical spread: sell a near strike (collect premium), buy a
    # further-OTM strike as a hedge (cap max loss). The mongo/trade_tracker
    # "action" field uses BUY/SELL to mean "position opened/closed" (matching
    # get_open_positions()'s convention), not the literal transaction type of
    # either individual leg - both legs' real transaction types are logged
    # separately via the two dhan_client.place_order() calls below.

    def place_credit_spread(
        self,
        signal_type: str,
        spread_type: str,
        near_option_type: str,
        near_strike: int,
        far_option_type: str,
        far_strike: int,
        expiry_date: str,
        lot_size: int = 1,
        conditions: Optional[Dict] = None,
        df: Optional = None,
        symbol: str = "NIFTY",
        strategy_tag: str = "STRATEGY_A"
    ) -> Optional[int]:
        """
        Sell a defined-risk credit spread: SELL near_strike, BUY far_strike as hedge.

        Args:
            signal_type: "CALL" or "PUT" - which signal triggered this (used for
                active_positions bucketing / duplicate-signal checks - NOT the same
                as near_option_type, since a CALL signal sells a PUT spread)
            spread_type: "BULL_PUT" or "BEAR_CALL"
            near_option_type/near_strike: the SOLD leg
            far_option_type/far_strike: the BOUGHT hedge leg
            conditions/df: signal data from the ORIGINATING contract (for logging only -
                NOT used for leg pricing, since the traded strikes differ from the
                strike that generated the signal)

        Returns:
            Trade ID or None
        """
        try:
            if self.has_position(signal_type, symbol, strategy_tag):
                logger.warning(f"⚠️ {strategy_tag} position already exists for {symbol} {signal_type} signal. Ignoring.")
                return None

            near_instrument_key = dhan_client.get_instrument_key(
                symbol=symbol, strike=near_strike,
                option_type="CE" if near_option_type == "CALL" else "PE",
                expiry_date=expiry_date,
            )
            far_instrument_key = dhan_client.get_instrument_key(
                symbol=symbol, strike=far_strike,
                option_type="CE" if far_option_type == "CALL" else "PE",
                expiry_date=expiry_date,
            )

            if not near_instrument_key or not far_instrument_key:
                logger.error(f"Could not resolve instrument keys for {spread_type} {symbol} {near_strike}/{far_strike}")
                return None

            near_price = data_manager.get_latest_price_from_websocket(near_instrument_key) or dhan_client.get_current_price(near_instrument_key)
            far_price = data_manager.get_latest_price_from_websocket(far_instrument_key) or dhan_client.get_current_price(far_instrument_key)

            if near_price is None or far_price is None:
                logger.error(f"Could not fetch leg prices for {spread_type} {symbol} {near_strike}/{far_strike}")
                return None

            net_credit = near_price - far_price
            if net_credit <= 0:
                logger.warning(
                    f"⚠️ {spread_type} {symbol} {near_strike}/{far_strike} has non-positive net credit "
                    f"(₹{net_credit:.2f}) - hedge leg costs more than premium collected. Skipping entry."
                )
                return None

            logger.info(
                f"[{strategy_tag}] Placing {spread_type}: SELL {near_option_type} {near_strike} @ ₹{near_price:.2f} / "
                f"BUY {far_option_type} {far_strike} @ ₹{far_price:.2f} | Net Credit: ₹{net_credit:.2f} | Lots: {lot_size}"
            )

            # Buy the hedge leg FIRST - the only possible failure mode is then an
            # unwanted long option (small, bounded loss), never a naked short.
            far_order_id = dhan_client.place_order(
                instrument_key=far_instrument_key, quantity=lot_size,
                transaction_type="BUY", order_type=config.ORDER_TYPE, product=config.PRODUCT_TYPE
            )
            if far_order_id is None:
                logger.error(f"Failed to place hedge-leg BUY order for {spread_type} {far_option_type} {far_strike}. Aborting entry - nothing opened.")
                return None

            # Sell the near/short leg. Retry once before alerting, since a failure
            # here leaves us holding a naked long hedge leg that needs attention.
            near_order_id = dhan_client.place_order(
                instrument_key=near_instrument_key, quantity=lot_size,
                transaction_type="SELL", order_type=config.ORDER_TYPE, product=config.PRODUCT_TYPE
            )
            if near_order_id is None:
                time.sleep(1)
                near_order_id = dhan_client.place_order(
                    instrument_key=near_instrument_key, quantity=lot_size,
                    transaction_type="SELL", order_type=config.ORDER_TYPE, product=config.PRODUCT_TYPE
                )

            if near_order_id is None:
                msg = (
                    f"Hedge leg BUY {far_option_type} {far_strike} succeeded (order {far_order_id}) but "
                    f"near-leg SELL {near_option_type} {near_strike} failed after retry. "
                    f"Manual intervention required - a naked long {far_option_type} {far_strike} is now open."
                )
                logger.critical(msg)
                telegram_notifier.send_error("Credit Spread Entry - Manual Intervention Required", msg)
                return None

            strat_config = config.CREDIT_SPREAD_STRATEGIES.get(strategy_tag, {})
            sl_percent = strat_config.get('sl_percent', config.CREDIT_SPREAD_SL_PERCENT)
            target_percent = strat_config.get('profit_target_percent', config.CREDIT_SPREAD_PROFIT_TARGET_PERCENT)
            # SL is based on the sold (near) leg's own premium, not net credit -
            # e.g. sold near leg at 100 -> SL at 120, regardless of hedge cost.
            stop_loss_value = near_price * (1 + sl_percent / 100.0)
            # Target stays based on net credit (unchanged).
            profit_target_value = net_credit * (1 - target_percent / 100.0)

            entry_time = datetime.now()
            entry_reason = conditions.get('reasoning', "") if conditions else ""

            trade_id = trade_tracker.add_spread_trade_entry(
                spread_type=spread_type, symbol=symbol, signal_type=signal_type,
                near_option_type=near_option_type, near_strike=near_strike,
                far_option_type=far_option_type, far_strike=far_strike,
                near_entry_price=near_price, far_entry_price=far_price,
                net_credit=net_credit, stop_loss_value=stop_loss_value, profit_target_value=profit_target_value,
                entry_time=entry_time, expiry_date=expiry_date, lot_size=lot_size,
                conditions=conditions, entry_reason=entry_reason,
                near_instrument_key=near_instrument_key, far_instrument_key=far_instrument_key,
                strategy_tag=strategy_tag
            )

            pos_obj = {
                'trade_id': trade_id, 'symbol': symbol, 'signal_type': signal_type,
                'spread_type': spread_type,
                'near_option_type': near_option_type, 'near_strike': near_strike,
                'near_instrument_key': near_instrument_key, 'near_entry_price': near_price,
                'far_option_type': far_option_type, 'far_strike': far_strike,
                'far_instrument_key': far_instrument_key, 'far_entry_price': far_price,
                'net_credit': net_credit, 'stop_loss_value': stop_loss_value, 'profit_target_value': profit_target_value,
                'lot_size': lot_size, 'entry_time': entry_time, 'expiry_date': expiry_date,
                'strategy_tag': strategy_tag,
                'best_near_price': near_price, 'trailing_active': False,
            }

            if symbol not in self.active_positions:
                self.active_positions[symbol] = {"CALL": [], "PUT": []}
            self.active_positions[symbol][signal_type].append(pos_obj)

            if data_manager.ws_enabled and data_manager.ws_client:
                try:
                    data_manager.ws_client.subscribe([near_instrument_key, far_instrument_key])
                except Exception as e:
                    logger.warning(f"Could not subscribe spread legs to WebSocket: {e}")

            mongo_logger.log_trade(
                timestamp=entry_time, trade_id=trade_id, option_type=near_option_type, strike=near_strike,
                action="BUY", price=near_price, quantity=lot_size, stop_loss=stop_loss_value,
                symbol=symbol, instrument_key=near_instrument_key, expiry_date=expiry_date, lot_size=lot_size,
                reason=entry_reason, strategy_tag=strategy_tag,
                is_spread=True, spread_type=spread_type, signal_type=signal_type,
                far_option_type=far_option_type, far_strike=far_strike, far_instrument_key=far_instrument_key,
                far_price=far_price, net_credit=net_credit, stop_loss_value=stop_loss_value, profit_target_value=profit_target_value,
            )

            telegram_notifier.send_custom_message(f"📉 {spread_type} Opened - {symbol}", {
                "Sold": f"{near_option_type} {near_strike} @ ₹{near_price:.2f}",
                "Hedge": f"{far_option_type} {far_strike} @ ₹{far_price:.2f}",
                "Net Credit": f"₹{net_credit:.2f}",
                "Stop Loss (near-leg price)": f"₹{stop_loss_value:.2f}",
                "Profit Target (cost to close)": f"₹{profit_target_value:.2f}",
                "Lots": lot_size,
            })

            logger.info(f"✅ [{strategy_tag}] Spread opened: {spread_type} {symbol} | Trade ID: {trade_id} | Net Credit: ₹{net_credit:.2f}")
            return trade_id

        except Exception as e:
            logger.error(f"Error placing credit spread: {str(e)}")
            telegram_notifier.send_error("Credit Spread Entry", str(e))
            return None

    def close_credit_spread(self, position: Dict, exit_reason: str) -> bool:
        """
        Close a credit spread: buy back the near/short leg first (removes the
        undefined-risk exposure), then sell the far/hedge leg to close it out.
        """
        try:
            symbol = position['symbol']
            signal_type = position['signal_type']
            strategy_tag = position.get('strategy_tag', 'STRATEGY_A')
            lot_size = position['lot_size']

            near_exit_price = dhan_client.get_current_price(position['near_instrument_key'])
            if near_exit_price is None:
                logger.error(f"Could not fetch near-leg price to close spread trade {position['trade_id']}")
                return False

            near_close_order_id = dhan_client.place_order(
                instrument_key=position['near_instrument_key'], quantity=lot_size,
                transaction_type="BUY", order_type=config.ORDER_TYPE, product=config.PRODUCT_TYPE
            )
            if near_close_order_id is None:
                logger.error(f"Failed to buy back near leg for spread trade {position['trade_id']}. Hedge leg left open.")
                return False

            far_exit_price = dhan_client.get_current_price(position['far_instrument_key'])
            if far_exit_price is None:
                far_exit_price = 0.0
                logger.warning(f"Could not fetch far-leg price for spread trade {position['trade_id']}; recording as 0.")

            far_close_order_id = dhan_client.place_order(
                instrument_key=position['far_instrument_key'], quantity=lot_size,
                transaction_type="SELL", order_type=config.ORDER_TYPE, product=config.PRODUCT_TYPE
            )
            if far_close_order_id is None:
                msg = (
                    f"Near leg bought back for spread trade {position['trade_id']} but hedge-leg SELL "
                    f"{position['far_option_type']} {position['far_strike']} failed. Manual intervention required - "
                    f"a leftover long {position['far_option_type']} {position['far_strike']} is still open."
                )
                logger.critical(msg)
                telegram_notifier.send_error("Credit Spread Exit - Manual Intervention Required", msg)
                return False

            exit_time = datetime.now()
            trade_tracker.update_spread_trade_exit(
                trade_id=position['trade_id'], near_exit_price=near_exit_price, far_exit_price=far_exit_price,
                exit_time=exit_time, exit_reason=exit_reason
            )

            net_debit_to_close = near_exit_price - far_exit_price
            pnl = (position['net_credit'] - net_debit_to_close) * lot_size

            mongo_logger.log_trade(
                timestamp=exit_time, trade_id=position['trade_id'], option_type=position['near_option_type'],
                strike=position['near_strike'], action="SELL", price=near_exit_price, quantity=lot_size,
                reason=exit_reason, pnl=pnl, symbol=symbol, instrument_key=position['near_instrument_key'],
                expiry_date=position.get('expiry_date', ''), lot_size=lot_size, strategy_tag=strategy_tag,
                is_spread=True, spread_type=position['spread_type'], signal_type=signal_type,
                far_option_type=position['far_option_type'], far_strike=position['far_strike'],
                far_instrument_key=position['far_instrument_key'], far_price=far_exit_price,
                net_credit=position['net_credit'],
            )

            telegram_notifier.send_custom_message(f"📈 {position['spread_type']} Closed - {symbol}", {
                "Reason": exit_reason,
                "Net Credit Received": f"₹{position['net_credit']:.2f}",
                "Cost to Close": f"₹{net_debit_to_close:.2f}",
                "P&L": f"{'+' if pnl >= 0 else ''}₹{pnl:.2f}",
                "Lots": lot_size,
            })

            if position in self.active_positions[symbol][signal_type]:
                self.active_positions[symbol][signal_type].remove(position)

            logger.info(
                f"✅ [{strategy_tag}] Spread closed: {position['spread_type']} {symbol} | "
                f"P&L: {'+' if pnl >= 0 else ''}₹{pnl:.2f} | Reason: {exit_reason}"
            )
            return True

        except Exception as e:
            logger.error(f"Error closing credit spread: {str(e)}")
            telegram_notifier.send_error("Credit Spread Exit", str(e))
            return False

    def _update_trailing_stop_loss(self, position: Dict, near_price: float) -> None:
        """
        Ratchet the stop loss down as the sold (near) leg's own price improves
        (never loosens back up). Tracks the best (lowest) near-leg price seen since
        entry, and recomputes what the SL would be at that level using the
        position's own sl_percent - only applying it if that's tighter than the
        current SL. Based on the near leg alone, ignoring the hedge leg - matches
        how the SL itself is set at entry.

        e.g. sold near leg at 100 (SL 120) -> price drops to 70 -> SL tightens to 90
        -> drops to 20 -> SL tightens to 24 -> bounces back to 35 -> SL stays 24.
        """
        best_value = position.get('best_near_price', position['near_entry_price'])
        if near_price >= best_value:
            return  # not a new best - nothing to tighten

        position['best_near_price'] = near_price

        strat_config = config.CREDIT_SPREAD_STRATEGIES.get(position.get('strategy_tag', 'STRATEGY_A'), {})
        sl_percent = strat_config.get('sl_percent', config.CREDIT_SPREAD_SL_PERCENT)
        trailed_sl = near_price * (1 + sl_percent / 100.0)

        if trailed_sl < position['stop_loss_value']:
            old_sl = position['stop_loss_value']
            position['stop_loss_value'] = trailed_sl
            position['trailing_active'] = True
            logger.info(
                f"🔻 Trailing SL tightened: {position['spread_type']} {position['symbol']} | "
                f"₹{old_sl:.2f} -> ₹{trailed_sl:.2f} (best near-leg price: ₹{near_price:.2f})"
            )
            mongo_logger.update_trade_state(position['trade_id'], {
                'stop_loss_value': trailed_sl,
                'best_near_price': near_price,
                'trailing_active': True,
            })

    def check_credit_spread_stop_loss(self, position: Dict) -> bool:
        """Check and act on stop loss for a single credit-spread position.
        SL is based on the sold (near) leg's own price, not the net spread cost -
        see place_credit_spread()'s stop_loss_value calc."""
        try:
            near_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])

            if near_price is None:
                return False

            self._update_trailing_stop_loss(position, near_price)

            if near_price >= position['stop_loss_value']:
                logger.warning(
                    f"🔴 Credit spread stop loss hit: {position['spread_type']} {position['symbol']} | "
                    f"Near leg price: ₹{near_price:.2f} >= SL: ₹{position['stop_loss_value']:.2f}"
                )
                exit_reason = "Trailing Stop Loss" if position.get('trailing_active') else "Stop Loss"
                return self.close_credit_spread(position, exit_reason=exit_reason)

            return False

        except Exception as e:
            logger.error(f"Error checking credit spread stop loss: {str(e)}")
            return False

    def check_credit_spread_profit_target(self, position: Dict) -> bool:
        """Check and act on profit target for a single credit-spread position"""
        try:
            near_price = data_manager.get_latest_price_from_websocket(position['near_instrument_key']) or dhan_client.get_current_price(position['near_instrument_key'])
            far_price = data_manager.get_latest_price_from_websocket(position['far_instrument_key']) or dhan_client.get_current_price(position['far_instrument_key'])

            if near_price is None or far_price is None:
                return False

            net_spread_value = near_price - far_price  # current cost to close

            if net_spread_value <= position['profit_target_value']:
                logger.info(
                    f"🟢 Credit spread profit target hit: {position['spread_type']} {position['symbol']} | "
                    f"Cost to close: ₹{net_spread_value:.2f} <= Target: ₹{position['profit_target_value']:.2f}"
                )
                return self.close_credit_spread(position, exit_reason="Profit Target")

            return False

        except Exception as e:
            logger.error(f"Error checking credit spread profit target: {str(e)}")
            return False

    def check_all_credit_spread_stop_losses(self) -> None:
        """Check stop losses for all active credit-spread positions"""
        for symbol, opt_types in self.active_positions.items():
            for signal_type, positions in opt_types.items():
                for pos in list(positions):
                    self.check_credit_spread_stop_loss(pos)

    def check_all_credit_spread_profit_targets(self) -> None:
        """Check profit targets for all active credit-spread positions"""
        for symbol, opt_types in self.active_positions.items():
            for signal_type, positions in opt_types.items():
                for pos in list(positions):
                    self.check_credit_spread_profit_target(pos)

    def close_all_credit_spreads(self, reason: str = "EOD") -> None:
        """Close all active credit-spread positions"""
        logger.info(f"Closing all credit spreads. Reason: {reason}")
        for symbol, opt_types in self.active_positions.items():
            for signal_type, positions in opt_types.items():
                for position in list(positions):
                    self.close_credit_spread(position, exit_reason=reason)

    def has_position(self, option_type: str, symbol: Optional[str] = None, strategy_tag: Optional[str] = None) -> bool:
        """
        Check if a position exists
        
        Args:
            option_type: "CALL" or "PUT"
            symbol: Index symbol
            strategy_tag: Check for specific strategy
        
        Returns:
            True if position exists, False otherwise
        """
        symbols = [symbol] if symbol else self.active_positions.keys()
        
        for s in symbols:
            positions = self.active_positions.get(s, {}).get(option_type, [])
            if not positions:
                continue
                
            if strategy_tag:
                if any(p['strategy_tag'] == strategy_tag for p in positions):
                    return True
            else:
                if len(positions) > 0:
                    return True
                    
        return False
    
    def has_any_position(self) -> bool:
        """
        Check if any position exists (CALL or PUT)

        Returns:
            True if any position exists
        """
        for sym_pos in self.active_positions.values():
            if len(sym_pos.get("CALL", [])) > 0 or len(sym_pos.get("PUT", [])) > 0:
                return True
        return False

    def has_any_position_for_symbol(self, symbol: str) -> bool:
        """
        Check if any position (CALL or PUT, any strategy) exists for a given symbol.
        Used to enforce one trade per instrument - NIFTY and SENSEX gated independently.

        Returns:
            True if a position exists for this symbol
        """
        sym_pos = self.active_positions.get(symbol, {})
        return len(sym_pos.get("CALL", [])) > 0 or len(sym_pos.get("PUT", [])) > 0

    def get_positions(self, option_type: str, symbol: str = "NIFTY") -> List[Dict]:
        """
        Get all position details for an index and type
        """
        return self.active_positions.get(symbol, {}).get(option_type, [])

    def get_position(self, option_type: str, symbol: str = "NIFTY") -> Optional[Dict]:
        """
        Get the first active position for an index and type (backward compatibility)
        """
        positions = self.get_positions(option_type, symbol)
        return positions[0] if positions else None

    def get_position_by_strategy(self, option_type: str, symbol: str, strategy_tag: str) -> Optional[Dict]:
        """
        Get a specific strategy's position
        """
        positions = self.get_positions(option_type, symbol)
        for p in positions:
            if p['strategy_tag'] == strategy_tag:
                return p
        return None
    
    def get_active_positions_summary(self) -> str:
        """Get summary of active credit-spread positions"""

        summary = []

        for symbol, opt_types in self.active_positions.items():
            for signal_type, positions in opt_types.items():
                for pos in positions:
                    strategy = pos.get('strategy_tag', 'STRATEGY_A')
                    summary.append(
                        f"[{strategy}] {symbol} {pos.get('spread_type', '')} (signal: {signal_type}) | "
                        f"Short: {pos.get('near_option_type')} {pos.get('near_strike')} | "
                        f"Hedge: {pos.get('far_option_type')} {pos.get('far_strike')} | "
                        f"Net Credit: ₹{pos.get('net_credit', 0):.2f} | "
                        f"Lots: {pos.get('lot_size', 0)}"
                    )

        if not summary:
            return "No active positions"

        return " | ".join(summary)


# Global order manager instance
order_manager = OrderManager()

if __name__ == "__main__":
    # Test order manager
    print("Testing Order Manager...")
    
    # Check positions
    print(f"\nHas CALL position: {order_manager.has_position('CALL')}")
    print(f"Has PUT position: {order_manager.has_position('PUT')}")
    print(f"Active positions: {order_manager.get_active_positions_summary()}")
    
    print("\nOrder Manager module loaded successfully")
