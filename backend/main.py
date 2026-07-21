"""
Main Orchestrator for Nifty Options Algo Trading
Coordinates all modules and executes the trading strategy
"""

import time as time_module
import schedule
from datetime import datetime, timedelta, time
import sys

import config
import logger
from data_manager import data_manager
from strategy import strategy
from order_manager import order_manager
from trade_tracker import trade_tracker
from telegram_notifier import telegram_notifier
from charts import chart_generator
from mongo_logger import mongo_logger

class AlgoTradingSystem:
    """Main trading system orchestrator - supports multi-index trading"""
    
    def __init__(self):
        self.running = False
        
        # Nifty strikes and expiry
        self.nifty_call_strike = None
        self.nifty_put_strike = None
        self.nifty_expiry_date = None
        
        # Sensex strikes and expiry
        self.sensex_call_strike = None
        self.sensex_put_strike = None
        self.sensex_expiry_date = None

        # Bank Nifty expiry (PCR monitoring only - not traded, so no strikes)
        self.banknifty_expiry_date = None

        self.initialized = False

        # Track which indices are enabled
        self.nifty_enabled = config.NIFTY_ENABLED
        self.sensex_enabled = config.SENSEX_ENABLED
    
    def initialize(self):
        """Initialize the trading system"""
        try:
            logger.logger.system_start()
            
            # Validate configuration
            config.validate_config()
            config.display_config()
            
            # Check if it's a valid trading day (skip in test mode)
            if not config.TEST_MODE:
                # 1. Check Token Validity
                from dhan_token_manager import dhan_token_manager
                status = dhan_token_manager.get_token_status()
                if not status.get('is_valid'):
                    # On a headless server there's nobody to manually paste a
                    # fresh token - attempt unattended TOTP regeneration before
                    # giving up (requires DHAN_PIN + DHAN_TOTP_SECRET in .env).
                    logger.warning(f"⚠️ Access Token invalid ({status.get('message')}). Attempting automatic TOTP regeneration...")
                    totp_result = dhan_token_manager.generate_access_token_via_totp()
                    if totp_result.get('success'):
                        logger.info("✅ Access token auto-regenerated via TOTP")
                        from dhan_api import dhan_client
                        dhan_client.set_access_token(config.DHAN_ACCESS_TOKEN)
                        status = dhan_token_manager.get_token_status()

                    if not status.get('is_valid'):
                        logger.error(f"❌ Access Token Invalid: {status.get('message')}")
                        logger.error("Automatic TOTP regeneration failed or is not configured. Please regenerate the token from the dashboard and restart the system.")
                        telegram_notifier.send_error("Token Error", f"Access Token Invalid and auto-regeneration failed: {status.get('message')}. Please regenerate.")
                        return False
                logger.info(f"✅ Access Token validated: {status.get('message')}")

                if not strategy.validate_trading_day():
                    logger.error("Not a valid trading day. System will not start.")
                    logger.info(f"Today: {datetime.now().strftime('%A')}")
                    logger.info(f"Allowed days: Friday, Monday, Tuesday")
                    logger.info("To override for testing, set TEST_MODE = True in config.py")
                    return False
            else:
                logger.warning("⚠️  TEST MODE ENABLED - Bypassing day/time checks")
            
            current_time = datetime.now().time()
            logger.info(f"Current time: {current_time.strftime('%H:%M:%S')}")
            
            # Check if we're past market close (skip in test mode)
            if not config.TEST_MODE:
                if current_time > config.TRADING_END_TIME:
                    logger.error(f"Market has closed. Current time: {current_time}, Market closes at: {config.TRADING_END_TIME}")
                    return False
                
                # Allow initialization anytime during market hours (9:15 AM to 3:15 PM)
                market_open_time = time(9, 15, 0)
                if current_time < market_open_time:
                    logger.error(f"Market hasn't opened yet. Current time: {current_time}, Market opens at: {market_open_time}")
                    return False
            
            logger.info("✅ Market is open. Initializing system...")
            
            # Download instrument master file from Dhan
            logger.info("Downloading instrument master file...")
            from dhan_api import dhan_client
            if not dhan_client.download_instruments_master():
                logger.warning("Failed to download instruments. Instrument lookups may fail.")

            # Get Nifty price and determine strikes
            logger.info("Fetching Nifty price...")
            nifty_price = data_manager.get_nifty_price()

            if nifty_price is None:
                logger.error("Failed to fetch Nifty price. Check Dhan API credentials.")
                return False
            
            # Get Nifty expiry date (Tuesday) first to detect expiry day
            self.nifty_expiry_date = data_manager.get_expiry_date(datetime.now(), config.NIFTY_EXPIRY_DAY)
            is_nifty_expiry_today = (datetime.now().strftime('%Y-%m-%d') == self.nifty_expiry_date)
            
            nifty_strikes = data_manager.determine_atm_strikes(
                nifty_price,
                config.NIFTY_STRIKE_INTERVAL,
                is_expiry_day=is_nifty_expiry_today
            )
            self.nifty_call_strike = nifty_strikes['call']
            self.nifty_put_strike = nifty_strikes['put']
            
            if is_nifty_expiry_today:
                logger.info("📊 NIFTY: Using ITM strikes (expiry day)")
            logger.info(f"📊 NIFTY: ₹{nifty_price:.2f} | Call: {self.nifty_call_strike} | Put: {self.nifty_put_strike} | Expiry: {self.nifty_expiry_date}")
            
            # Get Sensex price and determine strikes (if enabled)
            if config.SENSEX_ENABLED:
                logger.info("Fetching Sensex price...")
                sensex_price = data_manager.get_sensex_price()
                
                if sensex_price is None:
                    logger.warning("Failed to fetch Sensex price. Sensex trading will be disabled.")
                    self.sensex_enabled = False
                else:
                    # Get Sensex expiry date (Thursday) first to detect expiry day
                    self.sensex_expiry_date = data_manager.get_expiry_date(datetime.now(), config.SENSEX_EXPIRY_DAY)
                    is_sensex_expiry_today = (datetime.now().strftime('%Y-%m-%d') == self.sensex_expiry_date)
                    
                    sensex_strikes = data_manager.determine_atm_strikes(
                        sensex_price,
                        config.SENSEX_STRIKE_INTERVAL,
                        is_expiry_day=is_sensex_expiry_today
                    )
                    self.sensex_call_strike = sensex_strikes['call']
                    self.sensex_put_strike = sensex_strikes['put']
                    
                    if is_sensex_expiry_today:
                        logger.info("📊 SENSEX: Using ITM strikes (expiry day)")
                    logger.info(f"📊 SENSEX: ₹{sensex_price:.2f} | Call: {self.sensex_call_strike} | Put: {self.sensex_put_strike} | Expiry: {self.sensex_expiry_date}")
            
            # Backward compatibility (use Nifty as default)
            self.call_strike = self.nifty_call_strike
            self.put_strike = self.nifty_put_strike
            self.expiry_date = self.nifty_expiry_date
            
            # Initialize WebSocket for real-time data (if enabled)
            if hasattr(config, 'USE_WEBSOCKET') and config.USE_WEBSOCKET:
                logger.info("Initializing WebSocket for real-time data...")
                if data_manager.init_websocket_feed():
                    logger.info("✅ WebSocket initialized - stop-loss checks will use real-time ticks")
                    
                    # collect instruments to subscribe
                    instruments_to_subscribe = []
                    
                    if self.nifty_enabled and self.nifty_call_strike and self.nifty_put_strike:
                        from dhan_api import dhan_client
                        # Call
                        call_key = dhan_client.get_instrument_key("NIFTY", self.nifty_call_strike, "CE", self.nifty_expiry_date)
                        if call_key: instruments_to_subscribe.append(call_key)
                        # Put
                        put_key = dhan_client.get_instrument_key("NIFTY", self.nifty_put_strike, "PE", self.nifty_expiry_date)
                        if put_key: instruments_to_subscribe.append(put_key)

                    if self.sensex_enabled and self.sensex_call_strike and self.sensex_put_strike:
                        from dhan_api import dhan_client
                        # Call
                        call_key = dhan_client.get_instrument_key("SENSEX", self.sensex_call_strike, "CE", self.sensex_expiry_date)
                        if call_key: instruments_to_subscribe.append(call_key)
                        # Put
                        put_key = dhan_client.get_instrument_key("SENSEX", self.sensex_put_strike, "PE", self.sensex_expiry_date)
                        if put_key: instruments_to_subscribe.append(put_key)
                        
                        
                    # Add Index symbols for dynamic strike updates
                    if self.nifty_enabled:
                        instruments_to_subscribe.append(config.NIFTY_INDEX_SYMBOL)
                    if self.sensex_enabled:
                        instruments_to_subscribe.append(config.SENSEX_INDEX_SYMBOL)
                        
                    if instruments_to_subscribe:
                        logger.info(f"DEBUG: Instruments to subscribe: {instruments_to_subscribe}")
                        data_manager.start_realtime_feed(instruments_to_subscribe)
                else:
                    logger.warning("⚠️ WebSocket init failed - falling back to REST API for stop-loss")
            
            # Backfill OI PCR data (if not in test mode)
            if not config.TEST_MODE and mongo_logger.enabled:
                logger.info("Running OI PCR backfill...")
                if self.nifty_enabled and self.nifty_expiry_date:
                    data_manager.backfill_oi_pcr("NIFTY", self.nifty_expiry_date)
                    data_manager.backfill_oi_pcr_full_chain("NIFTY", self.nifty_expiry_date)

                if self.sensex_enabled and self.sensex_expiry_date:
                    data_manager.backfill_oi_pcr("SENSEX", self.sensex_expiry_date)
                    data_manager.backfill_oi_pcr_full_chain("SENSEX", self.sensex_expiry_date)

                if config.BANKNIFTY_PCR_ENABLED:
                    if not self.banknifty_expiry_date:
                        self.banknifty_expiry_date = data_manager.get_nearest_expiry_from_list(config.BANKNIFTY_INDEX_SYMBOL)
                    if self.banknifty_expiry_date:
                        data_manager.backfill_oi_pcr("BANKNIFTY", self.banknifty_expiry_date)
                        data_manager.backfill_oi_pcr_full_chain("BANKNIFTY", self.banknifty_expiry_date)

            # Send startup notification
            telegram_notifier.send_system_start(
                mode="PAPER" if config.PAPER_TRADING else "LIVE"
            )
            
            # Sync Trade ID counter with MongoDB to prevent collisions
            if mongo_logger.enabled:
                max_trade_id = mongo_logger.get_max_trade_id()
                if max_trade_id > 0:
                    logger.info(f"🔄 Syncing Trade ID: Found max ID {max_trade_id} in DB")
                    trade_tracker.set_start_id(max_trade_id + 1)
                
                # Fetch trades for the day to populate tracker
                trade_tracker.sync_from_db()
            
            self.initialized = True
            
            # Inform user about trading status
            if not config.TEST_MODE:
                if current_time < config.TRADING_START_TIME:
                    wait_minutes = (datetime.combine(datetime.today(), config.TRADING_START_TIME) - 
                                   datetime.combine(datetime.today(), current_time)).total_seconds() / 60
                    logger.info(f"⏸️  System initialized. Trading will start in {wait_minutes:.1f} minutes at {config.TRADING_START_TIME}")
                elif current_time >= config.TRADING_START_TIME and current_time <= config.TRADING_END_TIME:
                    logger.info(f"✅ System initialized. Trading is ACTIVE now!")
            else:
                logger.warning("⚠️  TEST MODE: System will run one scan cycle for testing")
            
            # Save system state for API
            self.save_system_state()
            
            # Restore active positions from Dhan to prevent duplicate trades
            logger.info("Restoring active positions...")
            order_manager.restore_state()
            
            return True
        
        except Exception as e:
            logger.error(f"Error initializing system: {str(e)}")
            telegram_notifier.send_error("System Initialization", str(e))
            return False
    
    def save_system_state(self):
        """Save selected instruments and configuration to a JSON file for the API"""
        try:
            import json
            import os
            
            state = {
                "nifty": {
                    "enabled": self.nifty_enabled,
                    "expiry": self.nifty_expiry_date,
                    "call_strike": self.nifty_call_strike,
                    "put_strike": self.nifty_put_strike,
                    "call_instrument_key": "",
                    "put_instrument_key": ""
                },
                "sensex": {
                    "enabled": self.sensex_enabled,
                    "expiry": self.sensex_expiry_date,
                    "call_strike": self.sensex_call_strike,
                    "put_strike": self.sensex_put_strike,
                    "call_instrument_key": "",
                    "put_instrument_key": ""
                },
                "updated_at": datetime.now().isoformat()
            }
            
            # Fetch instrument keys if available
            from dhan_api import dhan_client

            if self.nifty_enabled and self.nifty_call_strike:
                # Need to handle potential None returns
                try:
                    state["nifty"]["call_instrument_key"] = dhan_client.get_instrument_key("NIFTY", self.nifty_call_strike, "CE", self.nifty_expiry_date) or ""
                    state["nifty"]["put_instrument_key"] = dhan_client.get_instrument_key("NIFTY", self.nifty_put_strike, "PE", self.nifty_expiry_date) or ""
                except Exception as e:
                    logger.error(f"Error fetching Nifty keys for state: {e}")

            if self.sensex_enabled and self.sensex_call_strike:
                try:
                    state["sensex"]["call_instrument_key"] = dhan_client.get_instrument_key("SENSEX", self.sensex_call_strike, "CE", self.sensex_expiry_date) or ""
                    state["sensex"]["put_instrument_key"] = dhan_client.get_instrument_key("SENSEX", self.sensex_put_strike, "PE", self.sensex_expiry_date) or ""
                except Exception as e:
                    logger.error(f"Error fetching Sensex keys for state: {e}")

            # Save to backend directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, "system_state.json")
            
            with open(file_path, "w") as f:
                json.dump(state, f, indent=4)
                
            logger.info(f"Saved system state to {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving system state: {str(e)}")
    
    def scan_and_trade(self):
        """Main trading loop - scan for signals and execute trades (Nifty + Sensex)"""
        try:
            current_time = datetime.now().time()
            
            # Check if within trading hours
            if not (config.TRADING_START_TIME <= current_time <= config.TRADING_END_TIME):
                return
            
            logger.info(f"Scanning for signals... Time: {current_time.strftime('%H:%M:%S')}")
            
            # Check stop losses and profit targets for existing positions
            if order_manager.has_any_position():
                order_manager.check_all_credit_spread_stop_losses()
                order_manager.check_all_credit_spread_profit_targets()

            # ========================================================================
            # DYNAMIC STRIKE UPDATE
            # ========================================================================
            try:
                # Update NIFTY Strikes
                if self.nifty_enabled and self.nifty_expiry_date:
                    nifty_ltp = data_manager.get_latest_price_from_websocket(config.NIFTY_INDEX_SYMBOL)

                    # Fallback to REST API if WebSocket price is missing (e.g., disconnected)
                    if not nifty_ltp:
                        from dhan_api import dhan_client
                        nifty_ltp = dhan_client.get_ltp(config.NIFTY_INDEX_SYMBOL)
                        if nifty_ltp:
                            logger.info(f"📡 NIFTY Spot (REST Fallback): {nifty_ltp}")
                    
                    if nifty_ltp:
                        # Calculate new strikes
                        new_strikes = data_manager.determine_atm_strikes(
                            nifty_ltp, 
                            strike_interval=50, 
                            is_expiry_day=(datetime.now().weekday() == config.NIFTY_EXPIRY_DAY) # Use configured expiry day
                        )
                        new_call = new_strikes['call']
                        new_put = new_strikes['put']
                        
                        # Check if strikes changed
                        if new_call != self.nifty_call_strike or new_put != self.nifty_put_strike:
                            logger.info(f"🔄 NIFTY Spot: {nifty_ltp} | Updating Strikes: CE {self.nifty_call_strike}->{new_call}, PE {self.nifty_put_strike}->{new_put}")
                            
                            self.nifty_call_strike = new_call
                            self.nifty_put_strike = new_put
                            
                            # Subscribe to new keys
                            from dhan_api import dhan_client
                            new_keys = []
                            call_key = dhan_client.get_instrument_key("NIFTY", new_call, "CE", self.nifty_expiry_date)
                            put_key = dhan_client.get_instrument_key("NIFTY", new_put, "PE", self.nifty_expiry_date)
                            
                            if call_key: new_keys.append(call_key)
                            if put_key: new_keys.append(put_key)
                            
                            # Also keep ALL currently active NIFTY positions in the feed
                            if order_manager.has_any_position():
                                active_positions = order_manager.get_positions("CALL", "NIFTY") + order_manager.get_positions("PUT", "NIFTY")
                                for pos in active_positions:
                                    if pos.get('is_spread'):
                                        for leg_key in (pos.get('near_instrument_key'), pos.get('far_instrument_key')):
                                            if leg_key and leg_key not in new_keys:
                                                new_keys.append(leg_key)
                                        logger.info(
                                            f"➕ Retaining active NIFTY {pos.get('spread_type', '')} "
                                            f"S{pos.get('near_strike')}/L{pos.get('far_strike')} ({pos.get('strategy_tag')}) in WS feed."
                                        )
                                    elif pos.get('instrument_key') and pos['instrument_key'] not in new_keys:
                                        new_keys.append(pos['instrument_key'])
                                        logger.info(f"➕ Retaining active NIFTY {pos.get('option_type')} {pos.get('strike')} ({pos.get('strategy_tag')}) in WS feed.")
                            
                            if new_keys:
                                data_manager.start_realtime_feed(new_keys)
                            
                            self.save_system_state()
                                
                # Update SENSEX Strikes
                if self.sensex_enabled and self.sensex_expiry_date:
                     sensex_ltp = data_manager.get_latest_price_from_websocket(config.SENSEX_INDEX_SYMBOL)

                     # Fallback to REST API if WebSocket price is missing
                     if not sensex_ltp:
                         from dhan_api import dhan_client
                         sensex_ltp = dhan_client.get_ltp(config.SENSEX_INDEX_SYMBOL)
                         if sensex_ltp:
                             logger.info(f"📡 SENSEX Spot (REST Fallback): {sensex_ltp}")
                         
                     if sensex_ltp:
                        # Calculate new strikes
                        new_strikes = data_manager.determine_atm_strikes(
                            sensex_ltp, 
                            strike_interval=config.SENSEX_STRIKE_INTERVAL, 
                            is_expiry_day=(datetime.now().weekday() == config.SENSEX_EXPIRY_DAY) # Use configured expiry day
                        )
                        new_call = new_strikes['call']
                        new_put = new_strikes['put']
                        
                        # Check if strikes changed
                        if new_call != self.sensex_call_strike or new_put != self.sensex_put_strike:
                            logger.info(f"🔄 SENSEX Spot: {sensex_ltp} | Updating Strikes: CE {self.sensex_call_strike}->{new_call}, PE {self.sensex_put_strike}->{new_put}")
                            
                            self.sensex_call_strike = new_call
                            self.sensex_put_strike = new_put
                            
                            # Subscribe to new keys
                            from dhan_api import dhan_client
                            new_keys = []
                            call_key = dhan_client.get_instrument_key("SENSEX", new_call, "CE", self.sensex_expiry_date)
                            put_key = dhan_client.get_instrument_key("SENSEX", new_put, "PE", self.sensex_expiry_date)
                            
                            if call_key: new_keys.append(call_key)
                            if put_key: new_keys.append(put_key)
                            
                            # Also keep ALL currently active SENSEX positions in the feed
                            if order_manager.has_any_position():
                                active_positions = order_manager.get_positions("CALL", "SENSEX") + order_manager.get_positions("PUT", "SENSEX")
                                for pos in active_positions:
                                    if pos.get('is_spread'):
                                        for leg_key in (pos.get('near_instrument_key'), pos.get('far_instrument_key')):
                                            if leg_key and leg_key not in new_keys:
                                                new_keys.append(leg_key)
                                        logger.info(
                                            f"➕ Retaining active SENSEX {pos.get('spread_type', '')} "
                                            f"S{pos.get('near_strike')}/L{pos.get('far_strike')} ({pos.get('strategy_tag')}) in WS feed."
                                        )
                                    elif pos.get('instrument_key') and pos['instrument_key'] not in new_keys:
                                        new_keys.append(pos['instrument_key'])
                                        logger.info(f"➕ Retaining active SENSEX {pos.get('option_type')} {pos.get('strike')} ({pos.get('strategy_tag')}) in WS feed.")
                            
                            if new_keys:
                                data_manager.start_realtime_feed(new_keys)
                                
                            self.save_system_state()
            except Exception as e:
                logger.error(f"Error updating dynamic strikes: {e}")
            
            # ========================================================================
            # LOG SPOT PRICES
            # ========================================================================
            try:
                # Log NIFTY Spot
                if self.nifty_enabled:
                    nifty_df = data_manager.get_index_data_with_indicators("NIFTY")
                    if nifty_df is not None:
                        latest = nifty_df.iloc[-1]
                        logger.info(
                            f"📊 NIFTY Spot | "
                            f"Price: ₹{latest['close']:.2f} | "
                            f"VWAP: ₹{latest.get('vwap', 0):.2f} | "
                            f"RSI: {latest.get('rsi', 0):.1f} | "
                            f"ADX: {latest.get('adx', 0):.1f} | "
                            f"OI: {int(latest.get('oi', 0)):,} | "
                            f"OI_SMA: {int(latest.get('oi_sma', 0)):,}"
                        )

                # Log SENSEX Spot
                if self.sensex_enabled:
                    sensex_df = data_manager.get_index_data_with_indicators("SENSEX")
                    if sensex_df is not None:
                        latest = sensex_df.iloc[-1]
                        logger.info(
                            f"📊 SENSEX Spot | "
                            f"Price: ₹{latest['close']:.2f} | "
                            f"VWAP: ₹{latest.get('vwap', 0):.2f} | "
                            f"RSI: {latest.get('rsi', 0):.1f} | "
                            f"ADX: {latest.get('adx', 0):.1f} | "
                            f"OI: {int(latest.get('oi', 0)):,} | "
                            f"OI_SMA: {int(latest.get('oi_sma', 0)):,}"
                        )
            except Exception as e:
                logger.error(f"Error logging spot prices: {e}")

            # ========================================================================
            # SIGNAL SCANNING AND TRADE EXECUTION
            # ========================================================================
            # Only scan for NEW entries if within ENTRY_END_TIME
            if not config.TEST_MODE and current_time > config.ENTRY_END_TIME:
                logger.info(f"⏳ Pass {config.ENTRY_END_TIME.strftime('%H:%M')} | Position Management Mode: Checking SL/TP only. No NEW entries.")
                return

            # ========================================================================
            # SCAN NIFTY
            # ========================================================================
            # Check if today is a Nifty trading day (Friday, Monday, Tuesday)
            today_weekday = datetime.now().weekday()
            
            if (self.nifty_enabled and 
                self.nifty_call_strike and 
                self.nifty_put_strike and 
                today_weekday in config.NIFTY_TRADING_DAYS):
                
                logger.info("------------------------------------------------------------")
                
                # Per-index position flag - gates entries so only one trade is open on NIFTY at a time
                nifty_has_position = order_manager.has_any_position_for_symbol("NIFTY")
                
                nifty_signals = strategy.scan_for_signals(
                    call_strike=self.nifty_call_strike,
                    put_strike=self.nifty_put_strike,
                    expiry_date=self.nifty_expiry_date,
                    has_call_position=False, # Always scan; per-strategy check happens in scan_and_trade loop below
                    has_put_position=False,
                    symbol="NIFTY"
                )
                
                nifty_strategies = config.CREDIT_SPREAD_STRATEGIES

                # Execute NIFTY CALL signal - sells a Bull Put Spread
                if nifty_signals['call_signal'] and not nifty_has_position:
                    entry_price = nifty_signals['call_conditions'].get('close')
                    vol = float(nifty_signals['call_conditions'].get('volume') or 0)
                    vol_sma = float(nifty_signals['call_conditions'].get('volume_sma') or 0)

                    if vol_sma > 0:
                        vol_ratio = (vol / vol_sma * 100)
                    elif vol > 0:
                        vol_ratio = 999.9 # Infinitely better than zero average
                    else:
                        vol_ratio = 0.0

                    logger.info(f"🟢 NIFTY CALL SIGNAL: {self.nifty_call_strike} @ ₹{entry_price:.2f} | Vol: {vol:,.0f} | Vol SMA: {vol_sma:,.0f} | Ratio: {vol_ratio:.1f}%")

                    for strat_tag, strat_conf in nifty_strategies.items():
                        if not strat_conf.get('enabled', True):
                            continue

                        # Check if this strategy already has a position
                        if order_manager.has_position("CALL", "NIFTY", strat_tag):
                            continue

                        logger.info(f"🚀 [{strat_tag}] Entering NIFTY Bull Put Spread (CALL signal)")
                        order_manager.place_credit_spread(
                            signal_type="CALL", spread_type="BULL_PUT",
                            near_option_type="PUT", near_strike=self.nifty_put_strike,
                            far_option_type="PUT", far_strike=self.nifty_put_strike - config.SPREAD_WIDTH_NIFTY,
                            expiry_date=self.nifty_expiry_date,
                            lot_size=config.NIFTY_LOT_MULTIPLIER * config.NIFTY_LOT_SIZE,
                            conditions=nifty_signals['call_conditions'],
                            df=nifty_signals['call_data'],
                            symbol="NIFTY", strategy_tag=strat_tag
                        )

                # Execute NIFTY PUT signal - sells a Bear Call Spread
                if nifty_signals['put_signal'] and not nifty_has_position:
                    entry_price = nifty_signals['put_conditions'].get('close')
                    vol = float(nifty_signals['put_conditions'].get('volume') or 0)
                    vol_sma = float(nifty_signals['put_conditions'].get('volume_sma') or 0)

                    if vol_sma > 0:
                        vol_ratio = (vol / vol_sma * 100)
                    elif vol > 0:
                        vol_ratio = 999.9
                    else:
                        vol_ratio = 0.0

                    logger.info(f"🔴 NIFTY PUT SIGNAL: {self.nifty_put_strike} @ ₹{entry_price:.2f} | Vol: {vol:,.0f} | Vol SMA: {vol_sma:,.0f} | Ratio: {vol_ratio:.1f}%")

                    for strat_tag, strat_conf in nifty_strategies.items():
                        if not strat_conf.get('enabled', True):
                            continue

                        # Check if this strategy already has a position
                        if order_manager.has_position("PUT", "NIFTY", strat_tag):
                            continue

                        logger.info(f"🚀 [{strat_tag}] Entering NIFTY Bear Call Spread (PUT signal)")
                        order_manager.place_credit_spread(
                            signal_type="PUT", spread_type="BEAR_CALL",
                            near_option_type="CALL", near_strike=self.nifty_call_strike,
                            far_option_type="CALL", far_strike=self.nifty_call_strike + config.SPREAD_WIDTH_NIFTY,
                            expiry_date=self.nifty_expiry_date,
                            lot_size=config.NIFTY_LOT_MULTIPLIER * config.NIFTY_LOT_SIZE,
                            conditions=nifty_signals['put_conditions'],
                            df=nifty_signals['put_data'],
                            symbol="NIFTY", strategy_tag=strat_tag
                        )


            # ========================================================================
            # SCAN SENSEX
            # ========================================================================
            # Check if today is a Sensex trading day (Wednesday, Thursday)
            if (self.sensex_enabled and 
                self.sensex_call_strike and 
                self.sensex_put_strike and 
                today_weekday in config.SENSEX_TRADING_DAYS):
                
                logger.info("-------------------------------------------------------------")
                
                # Per-index position flag - gates entries so only one trade is open on SENSEX at a time
                sensex_has_position = order_manager.has_any_position_for_symbol("SENSEX")
                
                sensex_signals = strategy.scan_for_signals(
                    call_strike=self.sensex_call_strike,
                    put_strike=self.sensex_put_strike,
                    expiry_date=self.sensex_expiry_date,
                    has_call_position=False, # Always scan; per-strategy check happens in scan_and_trade loop below
                    has_put_position=False,
                    symbol="SENSEX"
                )
                
                sensex_strategies = config.CREDIT_SPREAD_STRATEGIES

                # Execute SENSEX CALL signal - sells a Bull Put Spread
                if sensex_signals['call_signal'] and not sensex_has_position:
                    entry_price = sensex_signals['call_conditions'].get('close')
                    vol = float(sensex_signals['call_conditions'].get('volume') or 0)
                    vol_sma = float(sensex_signals['call_conditions'].get('volume_sma') or 0)

                    if vol_sma > 0:
                        vol_ratio = (vol / vol_sma * 100)
                    elif vol > 0:
                        vol_ratio = 999.9
                    else:
                        vol_ratio = 0.0

                    logger.info(f"🟢 SENSEX CALL SIGNAL: {self.sensex_call_strike} @ ₹{entry_price:.2f} | Vol: {vol:,.0f} | Vol SMA: {vol_sma:,.0f} | Ratio: {vol_ratio:.1f}%")

                    for strat_tag, strat_conf in sensex_strategies.items():
                        if not strat_conf.get('enabled', True):
                            continue

                        # Check if this strategy already has a position
                        if order_manager.has_position("CALL", "SENSEX", strat_tag):
                            continue

                        logger.info(f"🚀 [{strat_tag}] Entering SENSEX Bull Put Spread (CALL signal)")
                        order_manager.place_credit_spread(
                            signal_type="CALL", spread_type="BULL_PUT",
                            near_option_type="PUT", near_strike=self.sensex_put_strike,
                            far_option_type="PUT", far_strike=self.sensex_put_strike - config.SPREAD_WIDTH_SENSEX,
                            expiry_date=self.sensex_expiry_date,
                            lot_size=config.SENSEX_LOT_MULTIPLIER * config.SENSEX_LOT_SIZE,
                            conditions=sensex_signals['call_conditions'],
                            df=sensex_signals['call_data'],
                            symbol="SENSEX", strategy_tag=strat_tag
                        )

                # Execute SENSEX PUT signal - sells a Bear Call Spread
                if sensex_signals['put_signal'] and not sensex_has_position:
                    entry_price = sensex_signals['put_conditions'].get('close')
                    vol = float(sensex_signals['put_conditions'].get('volume') or 0)
                    vol_sma = float(sensex_signals['put_conditions'].get('volume_sma') or 0)

                    if vol_sma > 0:
                        vol_ratio = (vol / vol_sma * 100)
                    elif vol > 0:
                        vol_ratio = 999.9
                    else:
                        vol_ratio = 0.0

                    logger.info(f"🔴 SENSEX PUT SIGNAL: {self.sensex_put_strike} @ ₹{entry_price:.2f} | Vol: {vol:,.0f} | Vol SMA: {vol_sma:,.0f} | Ratio: {vol_ratio:.1f}%")

                    for strat_tag, strat_conf in sensex_strategies.items():
                        if not strat_conf.get('enabled', True):
                            continue

                        # Check if this strategy already has a position
                        if order_manager.has_position("PUT", "SENSEX", strat_tag):
                            continue

                        logger.info(f"🚀 [{strat_tag}] Entering SENSEX Bear Call Spread (PUT signal)")
                        order_manager.place_credit_spread(
                            signal_type="PUT", spread_type="BEAR_CALL",
                            near_option_type="CALL", near_strike=self.sensex_call_strike,
                            far_option_type="CALL", far_strike=self.sensex_call_strike + config.SPREAD_WIDTH_SENSEX,
                            expiry_date=self.sensex_expiry_date,
                            lot_size=config.SENSEX_LOT_MULTIPLIER * config.SENSEX_LOT_SIZE,
                            conditions=sensex_signals['put_conditions'],
                            df=sensex_signals['put_data'],
                            symbol="SENSEX", strategy_tag=strat_tag
                        )

            
            # Log position status
            position_summary = order_manager.get_active_positions_summary()
            logger.info(f"Active Positions: {position_summary}")
        
        except Exception as e:
            logger.error(f"Error in scan_and_trade: {str(e)}")
            telegram_notifier.send_error("Scan Error", str(e))
    
    def check_stop_losses_only(self):
        """
        Check stop losses for active positions
        Runs independently every 30 seconds (not tied to candle intervals)
        """
        try:
            # Skip if no active positions
            if not order_manager.has_any_position():
                return
            
            # Skip if market is closed
            if not config.TEST_MODE:
                current_time = datetime.now().time()
                if current_time < config.TRADING_START_TIME or current_time > config.TRADING_END_TIME:
                    return
            
            logger.debug("🔍 Checking stop losses & profit targets...")

            # Check stop losses and profit targets for all positions
            order_manager.check_all_credit_spread_stop_losses()
            order_manager.check_all_credit_spread_profit_targets()

        except Exception as e:
            logger.error(f"Error checking stop losses/profit targets: {str(e)}")
            telegram_notifier.send_error("SL/Profit Check", str(e))
    
    def end_of_day_routine(self):
        """End of day routine - close positions and generate reports"""
        try:
            logger.info("=" * 80)
            logger.info("END OF DAY ROUTINE STARTED")
            logger.info("=" * 80)
            
            # Close all open positions
            order_manager.close_all_credit_spreads(reason="EOD")
            
            # Stop WebSocket feed
            if data_manager.ws_enabled and data_manager.ws_client:
                logger.info("Stopping WebSocket feed...")
                data_manager.stop_realtime_feed()
            
            # Save trade logs
            trade_tracker.save_to_excel()
            trade_tracker.save_to_csv()
            
            # Generate daily summary
            summary = trade_tracker.get_summary()
            trade_tracker.print_summary()
            
            # Send daily summary notification
            telegram_notifier.send_daily_summary(summary)
            
            # Generate daily summary chart
            if config.GENERATE_DAILY_SUMMARY_CHART:
                try:
                    chart_generator.create_daily_summary_chart(
                        trades=trade_tracker.trades,
                        date_str=datetime.now().strftime("%Y-%m-%d")
                    )
                except Exception as e:
                    logger.error(f"Error generating daily summary chart: {str(e)}")
            
            logger.info("=" * 80)
            logger.info("END OF DAY ROUTINE COMPLETED")
            logger.info("=" * 80)
            
            # Stop the system
            self.stop()
        
        except Exception as e:
            logger.error(f"Error in end_of_day_routine: {str(e)}")
            telegram_notifier.send_error("EOD Routine", str(e))
    
    def run_post_market_analysis(self):
        """
        Post-market entry point: called instead of the live trade loop when
        the system is started after TRADING_END_TIME (or live Dhan data is
        otherwise unavailable). Replays today's already-fetched candles
        (MongoDB, populated by fetch_day_candles.py) through the same
        credit-spread signal logic used live, for analysis only - no orders
        are placed via order_manager.
        """
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"📊 Market is closed - running post-market analysis on cached data for {date_str}...")

            from credit_spread_backtest import run_credit_spread_backtest
            result = run_credit_spread_backtest(date_str)

            trades = result.get('trades', [])
            metrics = result.get('metrics', {})

            if not trades:
                logger.info("Post-market analysis: no signals found (or no cached candle data - fetch candles first).")
                return

            logger.info(f"Post-market analysis: {len(trades)} signal(s) found")
            for t in trades:
                logger.info(
                    f"  {t['symbol']} {t['spread_type']}: entry {t['entry_time']} exit {t['exit_time']} "
                    f"({t['exit_reason']}) pnl={t['pnl']:+.2f} ({t['pnl_percent']:+.1f}%)"
                )
            logger.info(
                f"  Total P&L: {metrics.get('total_pnl', 0):+.2f} | "
                f"Win rate: {metrics.get('win_rate', 0):.1f}% | "
                f"Trades: {metrics.get('total_trades', 0)}"
            )
        except Exception as e:
            logger.error(f"Error during post-market analysis: {str(e)}")

    def start(self):
        """Start the trading system"""
        try:
            # Outside market hours, skip live initialization (it requires a
            # live NIFTY price fetch) and fall back to replaying today's
            # cached candles for analysis instead of refusing to start.
            if not config.TEST_MODE and datetime.now().time() > config.TRADING_END_TIME:
                self.run_post_market_analysis()
                return

            # Initialize system
            if not self.initialize():
                logger.error("Failed to initialize system")
                return
            
            self.running = True
            logger.info("🚀 Trading system started successfully!")
            
            # TEST MODE: Run one scan and exit
            if config.TEST_MODE:
                logger.warning("⚠️  TEST MODE ENABLED: Running single scan cycle...")
                logger.warning("⚠️  System will fetch data and test indicators, then exit")
                logger.info("=" * 80)
                
                # Run one scan
                self.scan_and_trade()
                
                logger.info("=" * 80)
                logger.info("✅ TEST MODE: Scan complete!")
                logger.info("💡 To run continuously, set TEST_MODE = False in config.py")
                logger.info("=" * 80)
                
                # Stop the system
                self.running = False
                return
            
            # NORMAL MODE: Schedule tasks and run continuously
            
            # 1. Scan for new entries every 3 minutes during trading hours
            schedule.every(config.CANDLE_INTERVAL_SECONDS).seconds.do(self.scan_and_trade)
            
            # 2. Check stop losses - every 2s with WebSocket, every 30s without
            if data_manager.ws_enabled and data_manager.ws_client:
                sl_interval = 2  # Near real-time with WebSocket ticks
                logger.info("📡 WebSocket active: stop-loss checks every 2 seconds")
            else:
                sl_interval = 30  # Fallback to REST API polling
                logger.info("🔄 REST mode: stop-loss checks every 30 seconds")
            schedule.every(sl_interval).seconds.do(self.check_stop_losses_only)
            
            # 3. End of day routine at market close
            eod_time = config.TRADING_END_TIME.strftime("%H:%M")
            schedule.every().day.at(eod_time).do(self.end_of_day_routine)
            
            # 4. Run OI PCR job every 3 minutes
            schedule.every(3).minutes.do(self.run_oi_pcr_job)
            
            # 5. Check for token updates from .env every 5 minutes
            schedule.every(5).minutes.do(self.check_token_updates)

            # 6. Proactively regenerate the Dhan access token daily before
            # market open (~24h validity) - on an unattended server nobody's
            # around to notice it expired, so refresh it before that happens
            # rather than only reacting to a manual update in .env.
            schedule.every().day.at("09:00").do(self.refresh_dhan_token)

            # Main loop
            while self.running:
                try:
                    schedule.run_pending()
                    time_module.sleep(1)
                
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    self.stop()
                    break
                
                except Exception as e:
                    logger.error(f"Error in main loop: {str(e)}")
                    telegram_notifier.send_error("Main Loop", str(e))
                    time_module.sleep(5)  # Wait before retrying
        
        except Exception as e:
            logger.error(f"Fatal error in trading system: {str(e)}")
            telegram_notifier.send_error("System Fatal", str(e))
            self.stop()
    
    def run_oi_pcr_job(self):
        """
        Calculate and log OI PCR for enabled indices
        Runs every 3 minutes
        """
        try:
            # Check if within market hours (allow some buffer)
            current_time = datetime.now().time()
            market_open = time(9, 15)
            market_close = time(15, 30)
            
            if not config.TEST_MODE:
                if current_time < market_open or current_time > market_close:
                    return

            # NIFTY
            if self.nifty_enabled and self.nifty_expiry_date:
                try:
                    pcr = data_manager.calculate_oi_pcr("NIFTY", self.nifty_expiry_date)
                    if pcr is not None:
                        mongo_logger.log_oi_pcr(datetime.utcnow(), "NIFTY", pcr['atm5'], pcr['full'])
                        logger.info(f"Updated NIFTY PCR: ATM+-5={pcr['atm5']} | Full={pcr['full']}")
                except Exception as e:
                    logger.error(f"Error updating Nifty PCR: {str(e)}")

            # SENSEX
            if self.sensex_enabled and self.sensex_expiry_date:
                try:
                    pcr = data_manager.calculate_oi_pcr("SENSEX", self.sensex_expiry_date)
                    if pcr is not None:
                        mongo_logger.log_oi_pcr(datetime.utcnow(), "SENSEX", pcr['atm5'], pcr['full'])
                        logger.info(f"Updated SENSEX PCR: ATM+-5={pcr['atm5']} | Full={pcr['full']}")
                except Exception as e:
                    logger.error(f"Error updating Sensex PCR: {str(e)}")

            # BANKNIFTY (monitoring only - shown on the dashboard alongside
            # whichever of NIFTY/SENSEX is trading that day; not itself traded,
            # so it runs every day regardless of NIFTY_TRADING_DAYS/SENSEX_TRADING_DAYS)
            if config.BANKNIFTY_PCR_ENABLED:
                try:
                    # Monthly-only expiry (no fixed weekday) - resolve once per
                    # day and re-resolve if the cached one has passed.
                    if not self.banknifty_expiry_date or self.banknifty_expiry_date < datetime.now().strftime('%Y-%m-%d'):
                        self.banknifty_expiry_date = data_manager.get_nearest_expiry_from_list(config.BANKNIFTY_INDEX_SYMBOL)

                    if self.banknifty_expiry_date:
                        pcr = data_manager.calculate_oi_pcr("BANKNIFTY", self.banknifty_expiry_date)
                        if pcr is not None:
                            mongo_logger.log_oi_pcr(datetime.utcnow(), "BANKNIFTY", pcr['atm5'], pcr['full'])
                            logger.info(f"Updated BANKNIFTY PCR: ATM+-5={pcr['atm5']} | Full={pcr['full']}")
                except Exception as e:
                    logger.error(f"Error updating BankNifty PCR: {str(e)}")

        except Exception as e:
            logger.error(f"Error in OI PCR job: {str(e)}")

    def check_token_updates(self):
        """
        Reload .env and check if access token was updated externally (via API)
        If updated, refresh the dhan_client and websocket
        """
        try:
            from dotenv import load_dotenv
            import os

            # Force reload .env
            env_path = os.path.join(config.PROJECT_ROOT, ".env")
            load_dotenv(env_path, override=True)

            new_token = os.getenv("DHAN_ACCESS_TOKEN")
            if new_token and new_token != config.DHAN_ACCESS_TOKEN:
                logger.info("🔄 Access token update detected in .env. Refreshing clients...")

                # Update config
                config.DHAN_ACCESS_TOKEN = new_token

                # Update Dhan Client
                from dhan_api import dhan_client
                dhan_client.set_access_token(new_token)

                # Update WebSocket Client
                if data_manager.ws_client:
                    data_manager.ws_client.set_access_token(new_token)

                logger.info("✅ Clients refreshed with new token")
        except Exception as e:
            logger.error(f"Error checking token updates: {e}")

    def refresh_dhan_token(self):
        """
        Proactively regenerate the Dhan access token via TOTP once daily,
        before it has a chance to expire mid-session on an unattended server.
        No-ops gracefully if DHAN_PIN/DHAN_TOTP_SECRET aren't configured
        (manual-token users are unaffected).
        """
        try:
            from dhan_token_manager import dhan_token_manager

            result = dhan_token_manager.generate_access_token_via_totp()
            if not result.get('success'):
                logger.warning(f"Scheduled token refresh skipped/failed: {result.get('message')}")
                return

            logger.info("🔄 Dhan access token proactively refreshed via TOTP")

            # Propagate to the already-instantiated clients (config.DHAN_ACCESS_TOKEN
            # was already updated by generate_access_token_via_totp itself).
            new_token = config.DHAN_ACCESS_TOKEN
            from dhan_api import dhan_client
            dhan_client.set_access_token(new_token)
            if data_manager.ws_client:
                data_manager.ws_client.set_access_token(new_token)

            logger.info("✅ Clients refreshed with proactively-regenerated token")
        except Exception as e:
            logger.error(f"Error during scheduled token refresh: {e}")
            telegram_notifier.send_error("Token Refresh", f"Scheduled TOTP refresh failed: {e}")

    def stop(self):
        """Stop the trading system"""
        logger.info("Stopping trading system...")
        
        self.running = False
        
        # Send stop notification
        telegram_notifier.send_system_stop()
        
        logger.logger.system_stop()
        
        sys.exit(0)


def main():
    """Main entry point"""
    
    print("\n" + "=" * 80)
    print("NIFTY OPTIONS ALGO TRADING SYSTEM")
    print("=" * 80)
    print(f"Mode: {'PAPER TRADING' if config.PAPER_TRADING else '⚠️  LIVE TRADING ⚠️'}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %A')}")
    print("=" * 80 + "\n")
    
    # Create and start the trading system
    trading_system = AlgoTradingSystem()
    
    try:
        trading_system.start()
    
    except KeyboardInterrupt:
        print("\n\nShutting down gracefully...")
        trading_system.stop()
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        trading_system.stop()


if __name__ == "__main__":
    main()