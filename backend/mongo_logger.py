"""
MongoDB Data Logger
Stores all market data, signals, and trades for backtesting and analysis
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import pandas as pd

import config
import logger

class MongoDataLogger:
    """Log all trading data to MongoDB for analysis and backtesting"""
    
    def __init__(self):
        """Initialize MongoDB connection"""
        try:
            # MongoDB connection string
            # Format: mongodb://localhost:27017/ (for local)
            # or mongodb://username:password@host:port/ (for remote)
            self.mongo_uri = getattr(config, 'MONGODB_URI', 'mongodb://localhost:27017/')
            self.db_name = getattr(config, 'MONGODB_DATABASE', 'nifty_algo_trading')
            
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.db_name]
            
            # Collections
            self.nifty_spot_data = self.db['nifty_spot']
            self.option_candles = self.db['option_candles']
            self.signals = self.db['signals']
            self.trades = self.db['trades']
            self.system_events = self.db['system_events']
            self.oi_pcr = self.db['oi_pcr']
            self.performance_stats = self.db['performance_stats']

            # Historical candle collections (for backtesting)
            self.option_1min_candles = self.db['option_1min_candles']
            self.index_1min_candles = self.db['index_1min_candles']
            self.candle_fetch_log = self.db['candle_fetch_log']

            # Trend Scanner's full-day OI/VWAP reconstruction (backend/trend_scanner.py)
            self.scanner_snapshots = self.db['scanner_snapshots']

            # Test connection
            self.client.server_info()

            # Ensure unique indexes for candle upserts (idempotent)
            self.option_1min_candles.create_index(
                [('symbol', 1), ('strike', 1), ('option_type', 1), ('timestamp', 1)],
                unique=True, background=True, name='option_candle_unique'
            )
            self.index_1min_candles.create_index(
                [('symbol', 1), ('timestamp', 1)],
                unique=True, background=True, name='index_candle_unique'
            )
            self.scanner_snapshots.create_index(
                [('symbol', 1), ('date', 1)],
                unique=True, background=True, name='scanner_snapshot_unique'
            )
            
            logger.info(f"✅ MongoDB connected: {self.db_name}")
            self.enabled = True
            
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {str(e)}")
            logger.warning("Continuing without MongoDB logging")
            self.enabled = False
    
    def log_nifty_spot(self, timestamp: datetime, price: float, source: str = "Yahoo"):
        """
        Log Nifty spot price
        
        Args:
            timestamp: Current timestamp
            price: Nifty spot price
            source: Data source (Yahoo/Upstox)
        """
        if not self.enabled:
            return
        
        try:
            doc = {
                'timestamp': timestamp,
                'date': timestamp.date().isoformat(),
                'time': timestamp.time().isoformat(),
                'price': price,
                'source': source
            }
            
            self.nifty_spot_data.insert_one(doc)
            logger.debug(f"Logged Nifty spot: ₹{price}")
            
        except Exception as e:
            logger.error(f"Error logging Nifty spot: {str(e)}")
    
    def log_option_candle(
        self,
        timestamp: datetime,
        option_type: str,
        strike: int,
        expiry: str,
        instrument_key: str,
        df: pd.DataFrame
    ):
        """
        Log option candle data with indicators
        
        Args:
            timestamp: Scan timestamp
            option_type: CALL or PUT
            strike: Strike price
            expiry: Expiry date
            instrument_key: Upstox instrument key
            df: DataFrame with OHLCV + indicators
        """
        if not self.enabled or df is None or len(df) == 0:
            return
        
        try:
            # Get latest candle
            latest = df.iloc[-1]
            
            doc = {
                'timestamp': timestamp,
                'date': timestamp.date().isoformat(),
                'time': timestamp.time().isoformat(),
                'option_type': option_type,
                'strike': strike,
                'expiry': expiry,
                'instrument_key': instrument_key,
                
                # OHLCV
                'open': float(latest['open']),
                'high': float(latest['high']),
                'low': float(latest['low']),
                'close': float(latest['close']),
                'volume': int(latest['volume']),
                'oi': int(latest['oi']),
                
                # Indicators (if present)
                'vwap': float(latest.get('vwap', 0)),
                'rsi': float(latest.get('rsi', 0)),
                'oi_sma': float(latest.get('oi_sma', 0)),
                'volume_sma': float(latest.get('volume_sma', 0)),  # Added volume SMA
                
                # Total candles received
                'total_candles': len(df)
            }
            
            self.option_candles.insert_one(doc)
            logger.debug(f"Logged {option_type} {strike} candle")
            
        except Exception as e:
            logger.error(f"Error logging option candle: {str(e)}")
    
    def log_signal(
        self,
        timestamp: datetime,
        option_type: str,
        strike: int,
        signal_detected: bool,
        conditions: Dict,
        candle_data: Dict,
        reason: str = ""
    ):
        """
        Log signal detection (whether trade was taken or not)
        
        Args:
            timestamp: Scan timestamp
            option_type: CALL or PUT
            strike: Strike price
            signal_detected: True if all conditions met
            conditions: Dict with condition results
            candle_data: Current candle OHLCV
            reason: Reason if signal rejected
        """
        if not self.enabled:
            return
        
        try:
            doc = {
                'timestamp': timestamp,
                'date': timestamp.date().isoformat(),
                'time': timestamp.time().isoformat(),
                'option_type': option_type,
                'strike': strike,
                'signal_detected': signal_detected,
                
                # Conditions
                # Schema changed 2026-07-21: entry gate flipped from RSI>60/price>VWAP/OI<SMA
                # to RSI<40/price<VWAP/OI>SMA. Docs before this date use the old field names
                # (price_above_vwap/rsi_above_threshold/oi_below_sma) with the old semantics.
                'price_below_vwap': conditions.get('price_below_vwap', False),
                'rsi_below_threshold': conditions.get('rsi_below_40', False),
                'oi_above_sma': conditions.get('oi_above_sma', False),
                'volume_confirmed': conditions.get('volume_confirmed', True),  # Added volume check
                
                # Values
                'close': conditions.get('close', 0),
                'vwap': conditions.get('vwap', 0),
                'rsi': conditions.get('rsi', 0),
                'oi': conditions.get('oi', 0),
                'oi_sma': conditions.get('oi_sma', 0),
                'volume': conditions.get('volume', 0),  # Added volume
                'volume_sma': conditions.get('volume_sma', 0),  # Added volume SMA
                
                # Candle data
                'candle_open': candle_data.get('open', 0),
                'candle_high': candle_data.get('high', 0),
                'candle_low': candle_data.get('low', 0),
                'candle_close': candle_data.get('close', 0),
                'candle_volume': candle_data.get('volume', 0),  # Added candle volume
                
                # Metadata
                'reason': reason,
                'trade_taken': False  # Will be updated if trade executed
            }
            
            result = self.signals.insert_one(doc)
            logger.debug(f"Logged signal: {option_type} {strike} - {signal_detected}")
            
            return result.inserted_id
            
        except Exception as e:
            logger.error(f"Error logging signal: {str(e)}")
            return None
    
    def update_signal_with_trade(self, signal_id, trade_id: int):
        """Update signal document when trade is executed"""
        if not self.enabled or signal_id is None:
            return
        
        try:
            self.signals.update_one(
                {'_id': signal_id},
                {'$set': {'trade_taken': True, 'trade_id': trade_id}}
            )
        except Exception as e:
            logger.error(f"Error updating signal: {str(e)}")
    
    def log_trade(
        self,
        timestamp: datetime,
        trade_id: int,
        option_type: str,
        strike: int,
        action: str,  # BUY or SELL
        price: float,
        quantity: int,
        stop_loss: Optional[float] = None,
        reason: str = "",
        exit_reasoning: str = "",
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None,
        symbol: str = "NIFTY",
        instrument_key: str = "",
        expiry_date: str = "",
        lot_size: int = 1,
        strategy_tag: str = "STRATEGY_A",
        is_spread: bool = False,
        spread_type: str = "",
        signal_type: str = "",
        far_option_type: str = "",
        far_strike: int = 0,
        far_instrument_key: str = "",
        far_price: Optional[float] = None,
        net_credit: Optional[float] = None,
        stop_loss_value: Optional[float] = None,
        profit_target_value: Optional[float] = None,
    ):
        """
        Log trade execution

        Args:
            timestamp: Trade timestamp
            trade_id: Trade ID
            option_type: CALL or PUT
            strike: Strike price
            action: BUY or SELL
            price: Execution price
            quantity: Lots
            stop_loss: SL price (for entries)
            reason: Entry/Exit reason
            pnl: P&L (for exits)
            pnl_percent: P&L % (for exits)
            symbol: Index symbol (NIFTY/SENSEX)
            instrument_key: Broker instrument key
            expiry_date: Option expiry date
            lot_size: Number of lots
            is_spread/spread_type/signal_type/far_*/net_credit/*_value: credit-spread
                fields (see order_manager.py:place_credit_spread) - blank/None for
                single-leg option-buying trades.
        """
        if not self.enabled:
            return

        try:
            doc = {
                'timestamp': timestamp,
                'date': timestamp.date().isoformat(),
                'time': timestamp.time().isoformat(),
                'trade_id': trade_id,
                'option_type': option_type,
                'strike': strike,
                'action': action,
                'price': price,
                'quantity': quantity,
                'stop_loss': stop_loss,
                'reason': reason,
                'exit_reasoning': exit_reasoning,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'symbol': symbol,
                'instrument_key': instrument_key,
                'expiry_date': expiry_date,
                'lot_size': lot_size,
                'strategy_tag': strategy_tag,
                'is_spread': is_spread,
                'spread_type': spread_type,
                'signal_type': signal_type,
                'far_option_type': far_option_type,
                'far_strike': far_strike,
                'far_instrument_key': far_instrument_key,
                'far_price': far_price,
                'net_credit': net_credit,
                'stop_loss_value': stop_loss_value,
                'profit_target_value': profit_target_value,
            }
            
            self.trades.insert_one(doc)
            logger.debug(f"Logged trade: {action} {option_type} {strike} @ ₹{price}")
            
            # Recalculate daily performance on any exit
            if action in ['SELL', 'PARTIAL_SELL']:
                self.log_daily_performance(doc['date'])

            # Send refresh signal to API server
            self._trigger_api_refresh()
            
        except Exception as e:
            logger.error(f"Error logging trade: {str(e)}")


    def update_trade_state(self, trade_id: int, updates: Dict):
        """
        Update fields on an open trade's BUY record (e.g. trailing stop_loss_value).
        The API server reads positions straight from this record, so live in-memory
        state (like a trailing SL ratchet in order_manager.py) must be persisted
        here or the dashboard will keep showing the stale entry-time value.

        Args:
            trade_id: Trade ID
            updates: Dictionary of fields to $set on the BUY record
        """
        if not self.enabled:
            return

        try:
            result = self.trades.update_one(
                {'trade_id': trade_id, 'action': 'BUY'},
                {'$set': updates}
            )
            if result.matched_count == 0:
                logger.warning(f"No trade found to update for ID {trade_id}")
        except Exception as e:
            logger.error(f"Error updating trade state: {str(e)}")

    def _trigger_api_refresh(self):
        """Send a trigger to the API server to broadcast a refresh to SSE clients"""
        try:
            import requests
            # Use a short timeout to avoid blocking the backend if API is busy/down
            requests.post("http://localhost:5000/api/internal/refresh", timeout=0.5)
        except Exception as e:
            # Don't let this fail the trade logging
            logger.debug(f"Refresh trigger skipped: {e}")
    
    def get_open_positions(self) -> List[Dict]:
        """
        Get all open positions for today.
        Finds BUY trades that don't have a matching SELL trade.
        
        Returns:
            List of open position dicts
        """
        if not self.enabled:
            return []
        
        try:
            today = datetime.now().date().isoformat()
            
            # Get all of today's BUY trades
            buy_trades = list(self.trades.find({'date': today, 'action': 'BUY'}))
            
            # Get all of today's SELL trades
            sell_trades = list(self.trades.find({'date': today, 'action': 'SELL'}))
            
            # Find trade_ids that have been sold
            sold_trade_ids = {t.get('trade_id') for t in sell_trades}
            
            # Open positions are BUYs without matching SELL
            open_positions = []
            for trade in buy_trades:
                if trade.get('trade_id') not in sold_trade_ids:
                    open_positions.append({
                        'trade_id': trade.get('trade_id'),
                        'symbol': trade.get('symbol', 'NIFTY'),
                        'option_type': trade.get('option_type'),
                        'strike': trade.get('strike'),
                        'entry_price': trade.get('price'),
                        'stop_loss': trade.get('stop_loss'),
                        'entry_time': trade.get('timestamp'),
                        'expiry_date': trade.get('expiry_date', ''),
                        'lot_size': trade.get('lot_size', trade.get('quantity', 1)),
                        'instrument_key': trade.get('instrument_key', ''),
                        # Added fields for UI
                        'profit_stage': trade.get('profit_stage', 0),
                        'trailing_active': trade.get('trailing_active', False),
                        'highest_price': trade.get('highest_price', trade.get('price')),
                        'original_stop_loss': trade.get('original_stop_loss', trade.get('stop_loss')),
                        'remaining_lot_size': trade.get('remaining_lot_size', trade.get('lot_size', trade.get('quantity', 1))),
                        'original_lot_size': trade.get('original_lot_size', trade.get('lot_size', trade.get('quantity', 1))),
                        'strategy_tag': trade.get('strategy_tag', 'STRATEGY_A'),
                        # Credit-spread fields (blank/None for single-leg option-buying trades)
                        'is_spread': trade.get('is_spread', False),
                        'spread_type': trade.get('spread_type', ''),
                        'signal_type': trade.get('signal_type', ''),
                        'far_option_type': trade.get('far_option_type', ''),
                        'far_strike': trade.get('far_strike'),
                        'far_instrument_key': trade.get('far_instrument_key', ''),
                        'far_entry_price': trade.get('far_price'),
                        'net_credit': trade.get('net_credit'),
                        'stop_loss_value': trade.get('stop_loss_value'),
                        'profit_target_value': trade.get('profit_target_value'),
                        # Renamed from best_spread_value 2026-07-21: SL trailing now
                        # tracks the near leg's own price, not the net spread value.
                        'best_near_price': trade.get('best_near_price'),
                    })
            
            return open_positions
            
        except Exception as e:
            logger.error(f"Error getting open positions: {str(e)}")
            return []
    
    def log_system_event(self, event_type: str, message: str, data: Optional[Dict] = None):
        """Log system events (start, stop, errors, etc.)"""
        if not self.enabled:
            return
        
        try:
            doc = {
                'timestamp': datetime.now(),
                'event_type': event_type,
                'message': message,
                'data': data or {}
            }
            
            self.system_events.insert_one(doc)
            
        except Exception as e:
            logger.error(f"Error logging system event: {str(e)}")
    
    def log_oi_pcr(self, timestamp: datetime, symbol: str, value: float, value_full: Optional[float] = None):
        """
        Log OI PCR value (Upsert to prevent duplicates)

        Args:
            timestamp: Calculation timestamp
            symbol: Index symbol (NIFTY/SENSEX)
            value: ATM+-5 windowed PCR (existing field, unchanged meaning)
            value_full: Full option-chain PCR (added 2026-07-21, matches Upstox/NSE) -
                omitted for historical backfilled points, which only reconstruct the
                windowed value (full-chain backfill would need per-minute OI history
                for every strike in the chain, far more API calls than the ATM+-5 band)
        """
        if not self.enabled:
            return

        try:
            update_fields = {
                'date': timestamp.date().isoformat(),
                'time': timestamp.time().isoformat(),
                'value': value,
            }
            if value_full is not None:
                update_fields['value_full'] = value_full

            # Upsert based on timestamp and symbol
            self.oi_pcr.update_one(
                {
                    'timestamp': timestamp,
                    'symbol': symbol
                },
                {'$set': update_fields},
                upsert=True
            )
            logger.debug(f"Logged OI PCR for {symbol}: atm5={value} full={value_full}")

        except Exception as e:
            logger.error(f"Error logging OI PCR: {str(e)}")

    def update_oi_pcr_full(self, timestamp: datetime, symbol: str, value_full: float) -> bool:
        """
        Set just the 'value_full' field on an already-existing OI PCR document
        (no upsert). Used by the full-chain backfill, which runs as a follow-up
        pass over documents already created by the ATM+-5 backfill/live job -
        those share the same candle-timestamp source, so timestamps line up.

        Returns:
            True if a matching document was found and updated
        """
        if not self.enabled:
            return False

        try:
            result = self.oi_pcr.update_one(
                {'timestamp': timestamp, 'symbol': symbol},
                {'$set': {'value_full': value_full}}
            )
            return result.matched_count > 0
        except Exception as e:
            logger.error(f"Error updating full-chain OI PCR: {str(e)}")
            return False

    def get_oi_pcr_history(self, symbol: str, limit: int = 5000) -> List[Dict]:
        """
        Get OI PCR history for today's trading session (market open 9:15 IST to now)

        Args:
            symbol: Index symbol
            limit: Safety cap on records returned, not the windowing mechanism
                (Default: 5000 - well above what a full day + after-hours
                polling can produce, so it never truncates the session)

        Returns:
            List of dicts {timestamp, value} sorted chronologically (oldest to newest)
        """
        if not self.enabled:
            return []

        try:
            # Anchor the window to today's market open (9:15 IST), not UTC midnight
            # or a record-count limit - polling continues well past market close, so
            # a flat .limit() silently drops the morning once enough samples pile up.
            ist_offset = timedelta(hours=5, minutes=30)
            now_ist = datetime.utcnow() + ist_offset
            market_open_ist = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
            market_open_utc = market_open_ist - ist_offset

            # Get today's session records (descending), then reverse to be chronological
            cursor = self.oi_pcr.find(
                {
                    'symbol': symbol,
                    'timestamp': {'$gte': market_open_utc}
                },
                {'_id': 0, 'timestamp': 1, 'value': 1, 'value_full': 1}
            ).sort('timestamp', -1).limit(limit)

            history = []
            for doc in cursor:
                # MongoDB stores datetimes in UTC; append +00:00 so the
                # frontend JS Date constructor treats them as UTC and
                # toLocaleTimeString('en-IN') correctly converts to IST.
                ts = doc['timestamp']
                ts_iso = ts.isoformat()
                if not ts_iso.endswith('Z') and '+' not in ts_iso and ts_iso.count('-') < 3:
                    ts_iso += '+00:00'
                history.append({
                    'timestamp': ts_iso,
                    'value': doc['value'],
                    # None for historical backfilled points (full-chain isn't backfilled)
                    'value_full': doc.get('value_full'),
                })
            
            # Reverse to return ascending (chronological) order
            return list(reversed(history))
            
        except Exception as e:
            logger.error(f"Error getting OI PCR history: {str(e)}")
            return []

    def save_scanner_snapshot(self, symbol: str, date_str: str, minutes: List[Dict]):
        """
        Persist a Trend Scanner full-day OI/VWAP reconstruction (backend/trend_scanner.py).
        One document per symbol+date, wholesale-overwritten on each successful
        rebuild (not an incremental append) - so a server restart can load
        today's last-known state instantly instead of redoing the full
        ~30s-4min live Dhan reconstruction from scratch.

        Args:
            symbol: "NIFTY"/"SENSEX"/"BANKNIFTY"
            date_str: "YYYY-MM-DD"
            minutes: list of {'time': <UTC datetime>, 'call_oi': float,
                'put_oi': float, 'close': float, 'vwap': float} - one per minute
        """
        if not self.enabled:
            return

        try:
            self.scanner_snapshots.update_one(
                {'symbol': symbol, 'date': date_str},
                {'$set': {'minutes': minutes, 'updated_at': datetime.utcnow()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving scanner snapshot for {symbol}: {str(e)}")

    def get_scanner_snapshot(self, symbol: str, date_str: str) -> Optional[Dict]:
        """
        Returns {'minutes': [...], 'updated_at': <naive UTC datetime>} for the
        given symbol+date, or None if nothing has been persisted yet today.
        """
        if not self.enabled:
            return None

        try:
            return self.scanner_snapshots.find_one(
                {'symbol': symbol, 'date': date_str},
                {'_id': 0, 'minutes': 1, 'updated_at': 1}
            )
        except Exception as e:
            logger.error(f"Error loading scanner snapshot for {symbol}: {str(e)}")
            return None

    def get_trades_for_day(self, date_str: str = None) -> List[Dict]:
        """
        Get all trades for a specific date, reconstructed from log entries.
        
        Args:
            date_str: Date string YYYY-MM-DD (defaults to today)
            
        Returns:
            List of trade dictionaries compatible with TradeTracker
        """
        if not self.enabled:
            return []
            
        try:
            if date_str is None:
                date_str = datetime.now().strftime("%Y-%m-%d")
                
            # Get all trade logs for this date
            cursor = self.trades.find({'date': date_str}).sort('timestamp', 1)
            
            trades_map = {}
            
            for log in cursor:
                trade_id = log.get('trade_id')
                action = log.get('action')
                
                if trade_id not in trades_map:
                    # New trade entry
                    if action == 'BUY':
                        trades_map[trade_id] = {
                            'trade_id': trade_id,
                            'symbol': log.get('symbol', 'NIFTY'),
                            'type': log.get('option_type'),
                            'strike': log.get('strike'),
                            'expiry': log.get('expiry_date'),
                            'instrument_key': log.get('instrument_key', ''),
                            'lot_size': log.get('lot_size', log.get('quantity', 1)),
                            'original_lot_size': log.get('lot_size', log.get('quantity', 1)),
                            'entry_time': log.get('timestamp'),
                            'entry_price': log.get('price'),
                            'stop_loss': log.get('stop_loss'),
                            'profit_stage': log.get('profit_stage', 0),
                            'trailing_active': log.get('trailing_active', False),
                            'highest_price': log.get('highest_price', log.get('price', 0)),
                            'status': 'OPEN',
                            'exit_time': None,
                            'exit_price': None,
                            'exit_reason': None,
                            'exit_reasoning': None,
                            'entry_reason': log.get('reason'),
                            'pnl': 0,  # Will accumulate from checking partial/full exits
                            'pnl_percent': 0,
                            'partial_exits': [],
                            'strategy_tag': log.get('strategy_tag', 'STRATEGY_A'),
                            # Credit-spread fields (blank/None for single-leg option-buying trades)
                            'is_spread': log.get('is_spread', False),
                            'spread_type': log.get('spread_type', ''),
                            'signal_type': log.get('signal_type', ''),
                            'far_option_type': log.get('far_option_type', ''),
                            'far_strike': log.get('far_strike'),
                            'far_instrument_key': log.get('far_instrument_key', ''),
                            'far_entry_price': log.get('far_price'),
                            'far_exit_price': None,
                            'net_credit': log.get('net_credit'),
                            'stop_loss_value': log.get('stop_loss_value'),
                            'profit_target_value': log.get('profit_target_value'),
                            'best_near_price': log.get('best_near_price'),
                        }
                else:
                    # Existing trade update
                    trade = trades_map[trade_id]
                    
                    if action == 'SELL' or action == 'PARTIAL_SELL':
                        # Update exit info
                        trade['exit_time'] = log.get('timestamp')
                        trade['exit_price'] = log.get('price')  # Last exit price
                        trade['exit_reason'] = log.get('reason')
                        if log.get('exit_reasoning'):
                            trade['exit_reasoning'] = log.get('exit_reasoning')
                        if trade.get('is_spread'):
                            trade['far_exit_price'] = log.get('far_price')
                        
                        # Accumulate P&L
                        pnl = log.get('pnl', 0)
                        if pnl:
                            trade['pnl'] += pnl
                            
                        # If full sell, mark as closed
                        if action == 'SELL':
                            trade['status'] = 'CLOSED'
                            
                            # Calculate total P&L percent based on entry value
                            entry_val = trade['entry_price'] * trade['lot_size']
                            if entry_val > 0:
                                trade['pnl_percent'] = (trade['pnl'] / entry_val) * 100
                            
                        elif action == 'PARTIAL_SELL':
                             # Add to partial exits
                            trade['partial_exits'].append({
                                'exit_time': log.get('timestamp'),
                                'exit_price': log.get('price'),
                                'lots_sold': log.get('quantity'),
                                'pnl': pnl,
                                'exit_reason': log.get('reason'),
                                'exit_reasoning': log.get('exit_reasoning', '')
                            })
                            
                            # Deduct sold quantity from main lot_size to match TradeTracker behavior
                            # This ensures frontend calculation (initial = remain + partials) is correct
                            if trade['lot_size'] > log.get('quantity', 0):
                                trade['lot_size'] -= log.get('quantity', 0)
            
            return list(trades_map.values())
            
        except Exception as e:
            logger.error(f"Error getting trades for day: {str(e)}")
            return []
    
    def get_max_trade_id(self) -> int:
        """
        Get the maximum trade ID used today.
        
        Returns:
            Max trade ID (0 if no trades)
        """
        if not self.enabled:
            return 0
        
        try:
            today = datetime.now().date().isoformat()
            
            # Find max trade_id for today
            # Use sort to find the highest trade_id efficiently
            result = self.trades.find_one(
                {'date': today},
                sort=[('trade_id', -1)]
            )
            
            if result:
                return result.get('trade_id', 0)
            return 0
            
        except Exception as e:
            logger.error(f"Error getting max trade ID: {str(e)}")
            return 0
    
    def get_today_summary(self) -> Dict:
        """Get today's trading summary from MongoDB"""
        if not self.enabled:
            return {}
        
        try:
            today = datetime.now().date().isoformat()
            
            # Count signals
            total_signals = self.signals.count_documents({'date': today})
            signals_taken = self.signals.count_documents({'date': today, 'trade_taken': True})
            
            # Count trades
            entries = self.trades.count_documents({'date': today, 'action': 'BUY'})
            exits = self.trades.count_documents({'date': today, 'action': 'SELL'})
            
            # Calculate P&L
            exit_trades = list(self.trades.find({'date': today, 'action': 'SELL', 'pnl': {'$exists': True}}))
            total_pnl = sum(t.get('pnl', 0) for t in exit_trades)
            
            return {
                'date': today,
                'total_signals': total_signals,
                'signals_taken': signals_taken,
                'entries': entries,
                'exits': exits,
                'total_pnl': total_pnl,
                'trades': exit_trades
            }
            
        except Exception as e:
            logger.error(f"Error getting summary: {str(e)}")
            return {}
    
    def close(self):
        """Close MongoDB connection"""
        if self.enabled:
            self.client.close()
            logger.info("MongoDB connection closed")


    def close_all_open_positions(self, reason: str = "Manual Reset"):
        """
        Manually close all open positions by inserting fake SELL records.
        This resolves the issue where positions remain open if the system crashes/stops.
        
        Args:
            reason: Reason for closing (default: Manual Reset)
        """
        if not self.enabled:
            return 0
        
        try:
            # Get current open positions
            open_positions = self.get_open_positions()
            count = 0
            
            timestamp = datetime.now()
            
            for pos in open_positions:
                # Insert a SELL record to "close" it
                doc = {
                    'timestamp': timestamp,
                    'date': timestamp.date().isoformat(),
                    'time': timestamp.time().isoformat(),
                    'trade_id': pos.get('trade_id'),
                    'option_type': pos.get('option_type'),
                    'strike': pos.get('strike'),
                    'action': 'SELL',
                    'price': pos.get('entry_price', 0), # Use entry price as exit to be neutral, or 0
                    'quantity': pos.get('remaining_lot_size', 0),
                    'lot_size': pos.get('lot_size', 1),
                    'stop_loss': 0,
                    'reason': reason,
                    'pnl': 0,
                    'pnl_percent': 0,
                    'symbol': pos.get('symbol', 'NIFTY'),
                    'instrument_key': pos.get('instrument_key', ''),
                    'expiry_date': pos.get('expiry_date', '')
                }
                
                self.trades.insert_one(doc)
                count += 1
                logger.debug(f"Manually closed trade {pos.get('trade_id')}")
            
            # Trigger refresh
            if count > 0:
                self._trigger_api_refresh()
                
            return count
            
        except Exception as e:
            logger.error(f"Error closing all positions: {str(e)}")
            return 0
            
    def get_historical_stats(self, days: int = 30) -> List[Dict]:
        """
        Get daily performance statistics for the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of daily stats sorted by date
        """
        if not self.enabled:
            return []
            
        try:
            # 1. Try to get from persisted performance_stats first
            start_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            cursor = self.performance_stats.find({'date': {'$gte': start_date}}).sort('date', 1)
            
            stats = []
            cumulative_pnl = 0
            
            for doc in cursor:
                pnl = doc.get('total_pnl', 0)
                cumulative_pnl += pnl
                
                # Format strategies list for frontend compatibility
                # performance_stats stores strategy_wise as a dict {tag: {pnl, trades, ...}}
                # get_historical_stats expects a list of {tag, pnl, ...}
                strategies_list = []
                if 'strategy_wise' in doc:
                    for tag, s_stats in doc['strategy_wise'].items():
                        strategies_list.append({
                            'tag': tag,
                            'pnl': s_stats.get('pnl', 0),
                            'trades': s_stats.get('trades', 0),
                            'wins': s_stats.get('wins', 0),
                            'losses': s_stats.get('losses', 0)
                        })

                stats.append({
                    'date': doc['date'],
                    'pnl': round(pnl, 2),
                    'cumulative_pnl': round(cumulative_pnl, 2),
                    'trades': doc.get('total_trades', 0),
                    'wins': doc.get('winning_trades', 0),
                    'losses': doc.get('losing_trades', 0),
                    'win_rate': doc.get('win_rate', 0),
                    'strategies': strategies_list
                })
            
            if stats:
                return stats
                
            # 2. Fallback to raw aggregation if no persisted stats found
            # (Keeping the old logic as a robust fallback)
            pipeline = [
                {
                    '$match': {
                        'date': {'$gte': start_date},
                        'action': {'$in': ['SELL', 'PARTIAL_SELL']},
                        'pnl': {'$exists': True}
                    }
                },
                # ... [Rest of the old pipeline logic]
                {
                    '$group': {
                        '_id': {
                            'date': '$date',
                            'trade_id': '$trade_id',
                            'strategy_tag': {'$ifNull': ['$strategy_tag', 'STRATEGY_A']}
                        },
                        'trade_pnl': {'$sum': '$pnl'}
                    }
                },
                {
                    '$group': {
                        '_id': {
                            'date': '$_id.date',
                            'strategy_tag': '$_id.strategy_tag'
                        },
                        'strat_pnl': {'$sum': '$trade_pnl'},
                        'strat_trades': {'$sum': 1},
                        'strat_wins': {
                            '$sum': {'$cond': [{'$gt': ['$trade_pnl', 0]}, 1, 0]}
                        },
                        'strat_losses': {
                            '$sum': {'$cond': [{'$lte': ['$trade_pnl', 0]}, 1, 0]}
                        }
                    }
                },
                {
                    '$group': {
                        '_id': '$_id.date',
                        'total_pnl': {'$sum': '$strat_pnl'},
                        'trade_count': {'$sum': '$strat_trades'},
                        'winning_trades': {'$sum': '$strat_wins'},
                        'losing_trades': {'$sum': '$strat_losses'},
                        'strategies': {
                            '$push': {
                                'tag': '$_id.strategy_tag',
                                'pnl': '$strat_pnl',
                                'trades': '$strat_trades',
                                'wins': '$strat_wins',
                                'losses': '$strat_losses'
                            }
                        }
                    }
                },
                {
                    '$sort': {'_id': 1}
                }
            ]
            
            # ... [Execute pipeline and format results]
            results = list(self.trades.aggregate(pipeline))
            stats = []
            cumulative_pnl = 0
            for doc in results:
                date = doc['_id']
                pnl = doc['total_pnl']
                cumulative_pnl += pnl
                total_trades = doc['trade_count']
                wins = doc['winning_trades']
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                stats.append({
                    'date': date,
                    'pnl': round(pnl, 2),
                    'cumulative_pnl': round(cumulative_pnl, 2),
                    'trades': total_trades,
                    'wins': wins,
                    'losses': doc['losing_trades'],
                    'win_rate': round(win_rate, 2),
                    'strategies': doc.get('strategies', [])
                })
            return stats
            
        except Exception as e:
            logger.error(f"Error getting historical stats: {str(e)}")
            return []

    def get_day_details(self, date_str: str) -> Dict:
        """
        Get detailed stats and trades for a specific date.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            
        Returns:
            Dict containing summary and trades list
        """
        if not self.enabled:
            return {}
            
        try:
            # Get trades using existing helper which reconstructs full trade lifecycles
            trades = self.get_trades_for_day(date_str)
            total_pnl = sum(t.get('pnl', 0) for t in trades)
            
            # Filter trades for statistics (CLOSED or have realized P&L)
            significant_trades = [t for t in trades if t.get('status') == 'CLOSED' or t.get('pnl', 0) != 0]
            winning_trades = [t for t in significant_trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in significant_trades if t.get('pnl', 0) <= 0]
            
            count_trades = len(significant_trades)
            avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            # Strategy-wise breakdown
            strategy_wise = {}
            for t in trades:
                tag = t.get('strategy_tag', 'STRATEGY_A')
                if tag not in strategy_wise:
                    strategy_wise[tag] = {'pnl': 0, 'trades': 0, 'wins': 0, 'losses': 0}
                
                pnl = t.get('pnl', 0)
                strategy_wise[tag]['pnl'] = round(strategy_wise[tag]['pnl'] + pnl, 2)
                # Count as a trade event if closed or has realized pnl
                if t.get('status') == 'CLOSED' or pnl != 0:
                    strategy_wise[tag]['trades'] += 1
                    if pnl > 0:
                        strategy_wise[tag]['wins'] += 1
                    else:
                        strategy_wise[tag]['losses'] += 1

            stats = {
                'date': date_str,
                'total_trades': count_trades,
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': round((len(winning_trades) / count_trades * 100), 2) if count_trades else 0,
                'total_pnl': round(total_pnl, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'max_win': round(max([t.get('pnl', 0) for t in winning_trades], default=0), 2),
                'max_loss': round(min([t.get('pnl', 0) for t in losing_trades], default=0), 2),
                'strategy_wise': strategy_wise
            }
            
            return {
                'stats': stats,
                'trades': trades
            }
            
        except Exception as e:
            logger.error(f"Error getting day details: {str(e)}")
            return {}

    def log_daily_performance(self, date_str: str = None):
        """
        Calculate and persist daily performance metrics to MongoDB.
        """
        if not self.enabled:
            return
            
        try:
            if date_str is None:
                date_str = datetime.now().strftime("%Y-%m-%d")
                
            details = self.get_day_details(date_str)
            if not details or 'stats' not in details:
                return
                
            stats = details['stats']
            
            # Upsert into performance_stats
            self.performance_stats.update_one(
                {'date': date_str},
                {'$set': stats},
                upsert=True
            )
            logger.info(f"Persisted performance stats for {date_str}")
        except Exception as e:
            logger.error(f"Error persisting daily performance: {str(e)}")

    def clear_todays_data(self):
        """
        Delete all data for today (trades, signals, system events).
        Useful for resetting the system during testing.
        """
        if not self.enabled:
            return False
            
        try:
            today = datetime.now().date().isoformat()
            
            # Delete from all collections
            r1 = self.trades.delete_many({'date': today})
            r2 = self.signals.delete_many({'date': today})
            r3 = self.system_events.delete_many({'date': {"$regex": f"^{today}"}}) # system_events might not have 'date' field in all docs, check log_system_event
            
            # log_system_event uses 'timestamp' but not 'date' field explicitly in the doc creation?
            # Let's check log_system_event... it uses 'timestamp'.
            # We can use timestamp filter for system_events.
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            r3 = self.system_events.delete_many({'timestamp': {'$gte': today_start}})
            
            logger.info(f"Cleared today's data: {r1.deleted_count} trades, {r2.deleted_count} signals")
            
            self._trigger_api_refresh()
            return True
            
        except Exception as e:
            logger.error(f"Error clearing today's data: {str(e)}")
            return False

    # =========================================================================
    # HISTORICAL CANDLE STORAGE (for post-market fetch & backtesting)
    # =========================================================================

    def upsert_option_1min_candles(
        self,
        symbol: str,
        option_type: str,
        strike: int,
        expiry: str,
        instrument_key: str,
        date: str,
        df: 'pd.DataFrame'
    ) -> int:
        """
        Bulk upsert 1-minute OHLCV candles for one option instrument.
        Safe to call multiple times — uses upsert so no duplicates.

        Args:
            symbol: 'NIFTY' or 'SENSEX'
            option_type: 'CE' or 'PE'
            strike: Strike price (int)
            expiry: Expiry date string YYYY-MM-DD
            instrument_key: Upstox instrument key e.g. 'NSE_FO|12345'
            date: Trading date YYYY-MM-DD
            df: DataFrame with index=timestamp, columns=[open,high,low,close,volume,oi]

        Returns:
            Number of candles upserted
        """
        if not self.enabled or df is None or df.empty:
            return 0

        try:
            from pymongo import UpdateOne
            ops = []
            for ts, row in df.iterrows():
                doc = {
                    'symbol': symbol,
                    'option_type': option_type,
                    'strike': int(strike),
                    'expiry': expiry,
                    'instrument_key': instrument_key,
                    'date': date,
                    'timestamp': ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': int(row.get('volume', 0)),
                    'oi': int(row.get('oi', 0)),
                }
                ops.append(UpdateOne(
                    {
                        'symbol': symbol,
                        'strike': int(strike),
                        'option_type': option_type,
                        'timestamp': doc['timestamp'],
                    },
                    {'$set': doc},
                    upsert=True
                ))

            if ops:
                result = self.option_1min_candles.bulk_write(ops, ordered=False)
                # matched_count (not modified_count!) is the correct "did we have
                # data" signal - re-fetching a day whose candles are already saved
                # and unchanged matches every document but modifies none of them,
                # which upserted_count + modified_count would wrongly report as 0
                # ("no data") even though the fetch succeeded and the data is there.
                return result.upserted_count + result.matched_count
            return 0

        except Exception as e:
            logger.error(f"Error upserting option candles ({symbol} {strike} {option_type}): {e}")
            return 0

    def upsert_index_1min_candles(
        self,
        symbol: str,
        date: str,
        df: 'pd.DataFrame'
    ) -> int:
        """
        Bulk upsert 1-minute OHLCV candles for an index (Nifty / Sensex spot).

        Args:
            symbol: 'NIFTY' or 'SENSEX'
            date: Trading date YYYY-MM-DD
            df: DataFrame with index=timestamp, columns=[open,high,low,close,volume,...]

        Returns:
            Number of candles upserted
        """
        if not self.enabled or df is None or df.empty:
            return 0

        try:
            from pymongo import UpdateOne
            ops = []
            for ts, row in df.iterrows():
                doc = {
                    'symbol': symbol,
                    'date': date,
                    'timestamp': ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'close': float(row.get('close', 0)),
                    'volume': int(row.get('volume', 0)),
                }
                ops.append(UpdateOne(
                    {'symbol': symbol, 'timestamp': doc['timestamp']},
                    {'$set': doc},
                    upsert=True
                ))

            if ops:
                result = self.index_1min_candles.bulk_write(ops, ordered=False)
                # See the matching comment in upsert_option_1min_candles - matched_count
                # (not modified_count) is the correct "did we have data" signal.
                return result.upserted_count + result.matched_count
            return 0

        except Exception as e:
            logger.error(f"Error upserting index candles ({symbol}): {e}")
            return 0

    def log_candle_fetch(
        self,
        date: str,
        symbol_stats: Dict,
        errors: List[str] = None
    ):
        """
        Record a post-market candle fetch run in the candle_fetch_log collection.

        Args:
            date: Trading date fetched YYYY-MM-DD
            symbol_stats: Dict like {'NIFTY': {'strikes': 9, 'candles': 3330}, ...}
            errors: List of error messages encountered (if any)
        """
        if not self.enabled:
            return

        try:
            total_candles = sum(s.get('candles', 0) for s in symbol_stats.values())
            doc = {
                'date': date,
                'fetched_at': datetime.utcnow(),
                'symbol_stats': symbol_stats,
                'total_candles_saved': total_candles,
                'errors': errors or []
            }
            self.candle_fetch_log.update_one(
                {'date': date},
                {'$set': doc},
                upsert=True
            )
            logger.info(f"Logged candle fetch run for {date}: {total_candles} candles total")
        except Exception as e:
            logger.error(f"Error logging candle fetch: {e}")

    def get_option_1min_candles(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        date: str
    ) -> 'pd.DataFrame':
        """
        Retrieve stored 1-min candles for one option instrument on a given date.
        Used by the backtest engine.

        Returns:
            DataFrame sorted by timestamp, or empty DataFrame if not found
        """
        if not self.enabled:
            return pd.DataFrame()

        try:
            docs = list(self.option_1min_candles.find(
                {'symbol': symbol, 'strike': int(strike),
                 'option_type': option_type, 'date': date},
                {'_id': 0}
            ).sort('timestamp', 1))

            if not docs:
                return pd.DataFrame()

            df = pd.DataFrame(docs)
            df.set_index('timestamp', inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error retrieving option candles: {e}")
            return pd.DataFrame()

    def get_index_1min_candles(
        self,
        symbol: str,
        date: str
    ) -> 'pd.DataFrame':
        """
        Retrieve stored 1-min candles for an index on a given date.
        Used by the backtest engine to reconstruct spot price history.

        Returns:
            DataFrame sorted by timestamp, or empty DataFrame if not found
        """
        if not self.enabled:
            return pd.DataFrame()

        try:
            docs = list(self.index_1min_candles.find(
                {'symbol': symbol, 'date': date},
                {'_id': 0}
            ).sort('timestamp', 1))

            if not docs:
                return pd.DataFrame()

            df = pd.DataFrame(docs)
            df.set_index('timestamp', inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error retrieving index candles: {e}")
            return pd.DataFrame()


# Global instance
mongo_logger = MongoDataLogger()

if __name__ == "__main__":
    # Test MongoDB connection
    print("Testing MongoDB Data Logger...")
    print(f"Enabled: {mongo_logger.enabled}")
    
    if mongo_logger.enabled:
        # Test logging
        mongo_logger.log_nifty_spot(datetime.now(), 25840.50, "Yahoo")
        print("✅ Test log successful")
        
        # Get summary
        summary = mongo_logger.get_today_summary()
        print(f"Today's summary: {summary}")
    else:
        print("❌ MongoDB not available - install with: pip install pymongo")