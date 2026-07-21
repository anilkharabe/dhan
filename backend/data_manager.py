"""
Data Manager Module
Manages historical and live candle data for options
"""

import math
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import time

import config
import logger
from dhan_api import dhan_client
from indicators import Indicators
from mongo_logger import mongo_logger

class DataManager:
    """Manage option data and candles"""
    
    def __init__(self):
        self.data_cache = {}  # Cache for storing candle data
        self.last_update = {}  # Track last update time
        
        # WebSocket support (LTP/OI ticks only - candles always come via REST)
        self.ws_client = None
        self.ws_enabled = config.USE_WEBSOCKET if hasattr(config, 'USE_WEBSOCKET') else False
    
    def init_websocket_feed(self):
        """
        Initialize WebSocket client for real-time LTP/OI ticks (Dhan Live Market Feed).
        Only called if USE_WEBSOCKET is True in config.
        Note: candles for indicators always come from periodic REST fetches
        (get_option_data_with_indicators), never from WebSocket aggregation -
        the WS feed here is only used for fast LTP reads during SL/target checks.
        """
        if not self.ws_enabled:
            logger.info("WebSocket disabled in config")
            return False

        try:
            from dhan_api import DhanWebSocketClient

            self.ws_client = DhanWebSocketClient(
                client_id=config.DHAN_CLIENT_ID,
                access_token=config.DHAN_ACCESS_TOKEN,
                on_tick_callback=self._on_tick_relay
            )

            if not self.ws_client.connect():
                logger.error("Failed to connect WebSocket client")
                return False

            logger.info("✅ WebSocket client initialized and connected")
            return True

        except Exception as e:
            logger.error(f"Error initializing WebSocket: {str(e)}")
            return False

    def start_realtime_feed(self, instrument_keys: List[str]):
        """
        Subscribe to real-time LTP/OI ticks for the given instruments

        Args:
            instrument_keys: List of composite instrument keys ("{segment}|{security_id}")
        """
        if not self.ws_client or not self.ws_client.is_connected():
            logger.warning("WebSocket not initialized or connected")
            return False

        try:
            success = self.ws_client.subscribe(instrument_keys, mode=config.WEBSOCKET_MODE)

            if success:
                logger.info(f"Started real-time feed for {len(instrument_keys)} instruments")

            return success

        except Exception as e:
            logger.error(f"Error starting realtime feed: {str(e)}")
            return False
    
    def stop_realtime_feed(self):
        """
        Stop WebSocket feed and disconnect
        """
        if self.ws_client:
            try:
                self.ws_client.disconnect()
                logger.info("WebSocket feed stopped")
            except Exception as e:
                logger.error(f"Error stopping WebSocket: {str(e)}")
    
    def _on_tick_relay(self, tick_data: Dict):
        """
        Relay WebSocket ticks to the Flask API server
        This allows the dashboard to receive live ticks even when the API
        server's own WebSocket connection to Dhan is unavailable.
        """
        try:
            import requests
            # Skip noise or non-significant updates if needed,
            # but for now relay everything to keep the dashboard snappy
            api_url = "http://localhost:5000/api/internal/tick"
            # Convert datetime to string for JSON serialization
            payload = tick_data.copy()
            if 'timestamp' in payload and isinstance(payload['timestamp'], datetime):
                payload['timestamp'] = payload['timestamp'].isoformat()

            # Using fire-and-forget or short timeout to not block the WS thread
            try:
                requests.post(api_url, json=payload, timeout=0.1)
            except requests.exceptions.Timeout:
                pass # Expected for high-frequency ticks
            except Exception as e:
                # Log once in a while to not spam
                if time.time() % 60 < 2:
                    logger.debug(f"Tick relay failed (API might be restarting): {e}")
        except Exception as e:
            pass

    def get_latest_price_from_websocket(self, instrument_key: str) -> Optional[float]:
        """
        Get latest price from WebSocket tick buffer
        Much faster than REST API for stop-loss checks

        Args:
            instrument_key: Instrument identifier

        Returns:
            Latest traded price or None
        """
        if not self.ws_client:
            return None

        latest_tick = self.ws_client.get_latest_tick(instrument_key)
        if latest_tick:
            return latest_tick.get('ltp')

        return None
    
    def get_previous_trading_day(self, current_date: datetime) -> datetime:
        """
        Get the previous trading day (skipping weekends)
        
        Args:
            current_date: Current date
        
        Returns:
            Previous trading day
        """
        prev_day = current_date - timedelta(days=1)
        
        # Skip weekends
        while prev_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
            prev_day -= timedelta(days=1)
        
        return prev_day

    @staticmethod
    def _ist_naive_to_utc(timestamp) -> datetime:
        """
        Convert a tz-naive timestamp whose wall-clock VALUE is IST (as produced
        by dhan_client.get_historical_data's index) into a true UTC datetime.

        Needed before handing a timestamp to mongo_logger: pymongo stores naive
        datetimes as-is (BSON datetimes are UTC instants), so logging the raw
        IST-valued naive timestamp directly would silently store "09:15" as if
        it were 09:15 UTC (really 14:45 IST) instead of 09:15 IST (03:45 UTC) -
        the same class of bug fixed in api/server.py's candle timestamps, just
        hitting Mongo insertion instead of epoch-seconds conversion.

        Args:
            timestamp: tz-naive datetime/Timestamp with an IST wall-clock value

        Returns:
            Naive datetime representing the equivalent true UTC instant
        """
        return (
            pd.Timestamp(timestamp)
            .tz_localize('Asia/Kolkata')
            .tz_convert('UTC')
            .tz_localize(None)
            .to_pydatetime()
        )

    def calculate_oi_pcr(self, symbol: str, expiry_date: str) -> Optional[Dict[str, float]]:
        """
        Calculate Put-Call Ratio (PCR) for an index two ways from a single
        option-chain fetch (no extra API cost): a narrow ATM+-5 strike window
        (11 strikes - what this system trades around) and the full option
        chain (matches the PCR shown on Upstox/NSE/most public trackers -
        confirmed via live comparison 2026-07-21: full-chain matched Upstox's
        displayed value exactly, ATM+-5 did not, since it deliberately excludes
        far-OTM OI).

        Args:
            symbol: "NIFTY" or "SENSEX"
            expiry_date: Expiry date string

        Returns:
            {'atm5': float, 'full': float} or None if unavailable
        """
        try:
            # Get instrument details
            if symbol == "NIFTY":
                instrument_key = config.NIFTY_INDEX_SYMBOL
                strike_interval = config.NIFTY_STRIKE_INTERVAL
            elif symbol == "SENSEX":
                instrument_key = config.SENSEX_INDEX_SYMBOL
                strike_interval = config.SENSEX_STRIKE_INTERVAL
            elif symbol == "BANKNIFTY":
                instrument_key = config.BANKNIFTY_INDEX_SYMBOL
                strike_interval = config.BANKNIFTY_STRIKE_INTERVAL
            else:
                return None

            # 1. Fetch Option Chain
            chain_data = dhan_client.get_option_chain(instrument_key, expiry_date)

            if not chain_data:
                return None

            # 2. Get underlying spot price
            spot_price = chain_data.get('spot_price')

            if not spot_price or spot_price == 0:
                if symbol == "NIFTY":
                    spot_price = self.get_nifty_price()
                elif symbol == "SENSEX":
                    spot_price = self.get_sensex_price()
                elif symbol == "BANKNIFTY":
                    spot_price = self.get_banknifty_price()

            if not spot_price:
                return None

            # 3. Get 11 strikes (ATM +/- 5)
            pcr_strikes = self.get_pcr_strikes(spot_price, strike_interval)

            # 4. Sum OI both ways: windowed (ATM+-5 only) and full chain (every strike)
            window_call_oi = 0
            window_put_oi = 0
            full_call_oi = 0
            full_put_oi = 0

            for strike, legs in chain_data.get('strikes', {}).items():
                call_oi = legs.get('ce', {}).get('oi', 0) or 0
                put_oi = legs.get('pe', {}).get('oi', 0) or 0
                full_call_oi += call_oi
                full_put_oi += put_oi
                if strike in pcr_strikes:
                    window_call_oi += call_oi
                    window_put_oi += put_oi

            # 5. Calculate both PCRs
            if window_call_oi <= 0 or full_call_oi <= 0:
                return None

            return {
                'atm5': round(window_put_oi / window_call_oi, 3),
                'full': round(full_put_oi / full_call_oi, 3),
            }

        except Exception as e:
            logger.error(f"Error calculating OI PCR: {str(e)}")
            return None

    def backfill_oi_pcr(self, symbol: str, expiry_date: str):
        """
        Backfill OI PCR for the current day using historical 1-minute candles.
        Recomputes the ATM+-5 strike band separately for EACH historical minute,
        using that minute's own spot price - NOT a single band derived from the
        current spot price. A fixed "now" band applied retroactively to earlier
        minutes (when the index was elsewhere) understates/overstates one side's
        OI and produces a skewed PCR that visibly decays back to normal as the
        reconstructed timestamps approach "now" - this was a real, confirmed bug.

        Args:
            symbol: "NIFTY" or "SENSEX"
            expiry_date: Expiry date string
        """
        try:
            logger.info(f"⏳ Starting OI PCR backfill for {symbol}...")

            if symbol == "NIFTY":
                index_symbol = config.NIFTY_INDEX_SYMBOL
                strike_interval = config.NIFTY_STRIKE_INTERVAL
            elif symbol == "SENSEX":
                index_symbol = config.SENSEX_INDEX_SYMBOL
                strike_interval = config.SENSEX_STRIKE_INTERVAL
            elif symbol == "BANKNIFTY":
                index_symbol = config.BANKNIFTY_INDEX_SYMBOL
                strike_interval = config.BANKNIFTY_STRIKE_INTERVAL
            else:
                return

            # 1. Fetch today's spot candles - gives a per-minute spot price so
            # each historical minute can get its OWN ATM+-5 band.
            spot_df = dhan_client.get_historical_data(index_symbol, config.CANDLE_INTERVAL)
            if spot_df is None or spot_df.empty:
                logger.error(f"Cannot backfill {symbol}: spot candle history unavailable")
                return

            # 2. Work out each minute's own strike band, and the union of
            # strikes needed across the whole day to cover all of them.
            minute_strikes = {}  # timestamp -> set of that minute's 11 strikes
            all_strikes = set()
            for timestamp, row in spot_df.iterrows():
                spot_price = float(row['close'])
                strikes = set(self.get_pcr_strikes(spot_price, strike_interval))
                minute_strikes[timestamp] = strikes
                all_strikes.update(strikes)

            # 3. Fetch historical OI candles for the union of strikes across the day
            oi_by_leg = {}  # (strike, option_type) -> {timestamp: oi}
            for strike in all_strikes:
                for option_type in ["CE", "PE"]:
                    inst_key = dhan_client.get_instrument_key(symbol, strike, option_type, expiry_date)
                    if not inst_key:
                        continue

                    df = dhan_client.get_historical_data(inst_key, config.CANDLE_INTERVAL)
                    if df is not None and not df.empty:
                        oi_by_leg[(strike, option_type)] = df['oi'].to_dict()

                    # Respect Dhan API rate limits
                    time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

            # 4. For each minute, sum OI only over THAT minute's own ATM+-5 band
            count = 0
            for timestamp, strikes in minute_strikes.items():
                call_oi = 0
                put_oi = 0
                for strike in strikes:
                    call_series = oi_by_leg.get((strike, "CE"))
                    if call_series and timestamp in call_series:
                        call_oi += call_series[timestamp] or 0
                    put_series = oi_by_leg.get((strike, "PE"))
                    if put_series and timestamp in put_series:
                        put_oi += put_series[timestamp] or 0

                if call_oi > 0:
                    pcr = round(put_oi / call_oi, 3)
                    mongo_logger.log_oi_pcr(self._ist_naive_to_utc(timestamp), symbol, pcr)
                    count += 1

            logger.info(f"✅ Backfilled {count} OI PCR data points for {symbol} ({len(all_strikes)} strikes fetched)")

        except Exception as e:
            logger.error(f"Error backfilling OI PCR: {str(e)}")

    def backfill_oi_pcr_full_chain(self, symbol: str, expiry_date: str):
        """
        Backfill the FULL-CHAIN OI PCR ('value_full') for today, as a follow-up
        pass over documents already created by backfill_oi_pcr()/the live job.
        Unlike the ATM+-5 window, the full strike set is the same set of
        strikes all day (every strike listed for this expiry), so - unlike
        backfill_oi_pcr() - there's no need to recompute a per-minute band;
        just fetch OI history for every strike once and sum across all of them
        per timestamp. This is a MUCH heavier call (all strikes in the chain,
        not just ~11-15) - only run when the full-chain history is actually
        needed, not on every startup.

        Args:
            symbol: "NIFTY" or "SENSEX"
            expiry_date: Expiry date string
        """
        try:
            logger.info(f"⏳ Starting FULL-CHAIN OI PCR backfill for {symbol} (all strikes - this can take a few minutes)...")

            if symbol == "NIFTY":
                index_symbol = config.NIFTY_INDEX_SYMBOL
            elif symbol == "SENSEX":
                index_symbol = config.SENSEX_INDEX_SYMBOL
            elif symbol == "BANKNIFTY":
                index_symbol = config.BANKNIFTY_INDEX_SYMBOL
            else:
                return

            # 1. Get the full strike list for this expiry from the live chain
            chain_data = dhan_client.get_option_chain(index_symbol, expiry_date)
            if not chain_data:
                logger.error(f"Cannot full-chain-backfill {symbol}: option chain unavailable")
                return

            all_strikes = list(chain_data.get('strikes', {}).keys())
            logger.info(f"Full chain has {len(all_strikes)} strikes for {symbol} {expiry_date}")

            # 2. Fetch historical OI candles for every strike, summing totals per minute
            call_oi_by_ts: Dict = {}
            put_oi_by_ts: Dict = {}
            for strike in all_strikes:
                for option_type in ["CE", "PE"]:
                    inst_key = dhan_client.get_instrument_key(symbol, strike, option_type, expiry_date)
                    if not inst_key:
                        continue

                    df = dhan_client.get_historical_data(inst_key, config.CANDLE_INTERVAL)
                    if df is not None and not df.empty:
                        target = call_oi_by_ts if option_type == "CE" else put_oi_by_ts
                        for timestamp, row in df.iterrows():
                            target[timestamp] = target.get(timestamp, 0) + (row.get('oi', 0) or 0)

                    # Respect Dhan API rate limits
                    time.sleep(config.CANDLE_FETCH_RATE_LIMIT_SECS)

            # 3. Compute full-chain PCR per minute and update existing docs in place
            count = 0
            for timestamp, call_oi in call_oi_by_ts.items():
                put_oi = put_oi_by_ts.get(timestamp, 0)
                if call_oi > 0:
                    pcr_full = round(put_oi / call_oi, 3)
                    if mongo_logger.update_oi_pcr_full(self._ist_naive_to_utc(timestamp), symbol, pcr_full):
                        count += 1

            logger.info(f"✅ Full-chain OI PCR backfill complete for {symbol}: {count} points updated ({len(all_strikes)} strikes fetched)")

        except Exception as e:
            logger.error(f"Error backfilling full-chain OI PCR: {str(e)}")

    def get_expiry_date(self, current_date: datetime, expiry_day: int = None) -> str:
        """
        Get the next expiry date for the given weekday
        
        Args:
            current_date: Current date
            expiry_day: Weekday of expiry (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri)
                       Default: Tuesday (1) for Nifty
        
        Returns:
            Expiry date string (YYYY-MM-DD)
        """
        if expiry_day is None:
            expiry_day = config.NIFTY_EXPIRY_DAY  # Default to Tuesday
        
        # Find next expiry day
        days_until_expiry = (expiry_day - current_date.weekday()) % 7
        
        # If today is expiry day and market hasn't closed, use today
        if days_until_expiry == 0 and current_date.time() < config.TRADING_END_TIME:
            expiry = current_date
        else:
            # Otherwise use next expiry day
            if days_until_expiry == 0:
                days_until_expiry = 7
            expiry = current_date + timedelta(days=days_until_expiry)
        
        return expiry.strftime('%Y-%m-%d')
    
    def determine_atm_strikes(
        self,
        current_price: float,
        strike_interval: int = None,
        is_expiry_day: bool = False
    ) -> Dict[str, int]:
        """
        Determine the nearest strictly-OTM strikes for Call and Put, always
        (including on expiry day - the old ITM shift was carried over from the
        retired option-buying strategy and no longer applies here).

        Args:
            current_price: Current index price
            strike_interval: Strike interval (50 for Nifty, 100 for Sensex)
            is_expiry_day: Unused - kept for call-site signature compatibility

        Returns:
            Dict with 'call' and 'put' strikes, each strictly outside current_price
        """
        if strike_interval is None:
            strike_interval = config.NIFTY_STRIKE_INTERVAL

        # Call: nearest strike strictly ABOVE spot
        call_strike = (int(current_price // strike_interval) + 1) * strike_interval

        # Put: nearest strike strictly BELOW spot
        put_strike = (math.ceil(current_price / strike_interval) - 1) * strike_interval

        return {
            'call': call_strike,
            'put': put_strike
        }
    
    def get_pcr_strikes(self, spot_price: float, strike_interval: int) -> List[int]:
        """
        Get 11 strikes for PCR calculation (ATM +/- 5 strikes)
        
        Args:
            spot_price: Current spot price
            strike_interval: Strike interval
            
        Returns:
            List of 11 strike prices centered around ATM
        """
        # Calculate ATM strike (round down to nearest interval)
        atm = int(spot_price // strike_interval) * strike_interval
        
        # Generate 11 strikes: [ATM - 5*interval, ..., ATM, ..., ATM + 5*interval]
        strikes = [atm + (i * strike_interval) for i in range(-5, 6)]
        
        return strikes
    
    def fetch_previous_day_candles(
        self,
        instrument_key: str,
        num_candles: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        Fetch last N candles from previous trading day
        
        Args:
            instrument_key: Instrument identifier
            num_candles: Number of candles to fetch
        
        Returns:
            DataFrame with previous day's candles
        """
        try:
            today = datetime.now()
            prev_day = self.get_previous_trading_day(today)
            
            # Get candles from previous day's last hour
            # Assuming 3-min candles, we need at least 15 minutes for 5 candles
            from_date = prev_day.strftime('%Y-%m-%d')
            to_date = prev_day.strftime('%Y-%m-%d')
            
            df = dhan_client.get_historical_data(
                instrument_key=instrument_key,
                interval=config.CANDLE_INTERVAL,
                from_date=from_date,
                to_date=to_date
            )

            if df is not None and len(df) > 0:
                # Get last N candles
                df_last = df.tail(num_candles)
                # logger.info(f"Fetched {len(df_last)} candles from previous day")
                return df_last
            else:
                logger.warning(f"No previous day data found for {instrument_key}")
                return None
        
        except Exception as e:
            logger.error(f"Error fetching previous day candles: {str(e)}")
            return None
    
    def fetch_current_day_candles(
        self,
        instrument_key: str,
        from_time: str = "09:15",
        to_time: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Fetch current day's candles using V3 API
        V3 automatically returns all intraday candles for current trading day
        
        Args:
            instrument_key: Instrument identifier
            from_time: Start time (HH:MM) - used for filtering
            to_time: End time (HH:MM) or None for current time - used for filtering
        
        Returns:
            DataFrame with current day's candles
        """
        try:
            # Fetches all of today's candles automatically (from_date/to_date default to today)
            df = dhan_client.get_historical_data(
                instrument_key=instrument_key,
                interval=config.CANDLE_INTERVAL
            )
            
            if df is not None and len(df) > 0:
                # Filter by time if needed
                if to_time:
                    end_time = datetime.strptime(to_time, '%H:%M').time()
                    df = df[df.index.time <= end_time]
                
                # logger.info(f"Fetched {len(df)} candles from current day")
                return df
            else:
                logger.warning(f"No current day data found for {instrument_key}")
                return None
        
        except Exception as e:
            logger.error(f"Error fetching current day candles: {str(e)}")
            return None
    
    def get_combined_data(
        self,
        instrument_key: str,
        previous_day_candles: int = 5
    ) -> Optional[pd.DataFrame]:
        """
        Get intraday data for analysis
        
        NOTE: V3 API only provides current day data. 
        Previous day data not available.
        
        Args:
            instrument_key: Instrument identifier
            previous_day_candles: Not used with V3 (kept for compatibility)
        
        Returns:
            DataFrame with current day candles
        """
        try:
            # Demo mode - generate mock data
            if config.DEMO_MODE:
                logger.info(f"DEMO MODE: Generating mock candle data for {instrument_key}")
                return self._generate_mock_data(num_candles=30)
            
            # 1. Fetch current day candles (Intraday)
            curr_df = self.fetch_current_day_candles(instrument_key)
            
            # 2. Fetch previous days' data (Historical)
            # Calculate start date for history (e.g., 5 days ago)
            from_date = (datetime.now() - timedelta(days=previous_day_candles + 2)).strftime('%Y-%m-%d')
            to_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            hist_df = dhan_client.get_historical_data(
                instrument_key=instrument_key,
                interval=config.CANDLE_INTERVAL,
                from_date=from_date,
                to_date=to_date
            )

            # 3. Combine Data
            if hist_df is not None and not hist_df.empty:
                if curr_df is not None and not curr_df.empty:
                    # Combine and remove duplicates
                    combined_df = pd.concat([hist_df, curr_df])
                    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                    combined_df.sort_index(inplace=True)
                    return combined_df
                else:
                    return hist_df
            
            # Fallback if no history
            if curr_df is None or len(curr_df) == 0:
                logger.warning(f"No data available for {instrument_key}")
                return None
            
            return curr_df
        
        except Exception as e:
            logger.error(f"Error getting data: {str(e)}")
            return None
    
    def _generate_mock_data(self, num_candles: int = 30) -> pd.DataFrame:
        """
        Generate mock OHLCV data for demo mode
        
        Args:
            num_candles: Number of candles to generate
        
        Returns:
            DataFrame with mock data
        """
        import numpy as np
        
        # Generate timestamps (3-minute intervals)
        end_time = datetime.now()
        timestamps = [end_time - timedelta(minutes=3*i) for i in range(num_candles)]
        timestamps.reverse()
        
        # Generate realistic option price data
        base_price = 150.0
        
        data = []
        for i, ts in enumerate(timestamps):
            # Add some randomness
            trend = i * 0.5  # Slight upward trend
            noise = np.random.uniform(-5, 5)
            
            close = base_price + trend + noise
            open_price = close + np.random.uniform(-2, 2)
            high = max(open_price, close) + np.random.uniform(0, 3)
            low = min(open_price, close) - np.random.uniform(0, 3)
            volume = np.random.randint(5000, 50000)
            oi = np.random.randint(40000, 100000)
            
            data.append({
                'timestamp': ts,
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume,
                'oi': oi
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def get_option_data_with_indicators(
        self,
        option_type: str,
        strike: int,
        expiry_date: str,
        symbol: str = "NIFTY"
    ) -> Optional[pd.DataFrame]:
        """
        Get option data with all indicators calculated
        
        Args:
            option_type: "CE" or "PE"
            strike: Strike price
            expiry_date: Expiry date
            symbol: Index symbol ("NIFTY" or "SENSEX")
        
        Returns:
            DataFrame with OHLCV data and indicators
        """
        try:
            # Generate instrument key
            instrument_key = dhan_client.get_instrument_key(
                symbol=symbol,
                strike=strike,
                option_type=option_type,
                expiry_date=expiry_date
            )

            # Get combined historical data
            # ALWAYS fetch fresh data from API for signal scanning
            # WebSocket cache is ONLY used for real-time stop-loss price checks, not for entry signals
            # This prevents serving stale prices when instruments aren't subscribed to WebSocket yet
            df = self.get_combined_data(instrument_key, config.PREVIOUS_DAY_CANDLES)
            
            if df is None or len(df) < config.SMA_OI_PERIOD:
                candles_needed = config.SMA_OI_PERIOD
                candles_have = len(df) if df is not None else 0
                minutes_needed = (candles_needed - candles_have) * 3
                
                logger.info(
                    f"⏳ Waiting for more data: {candles_have}/{candles_needed} candles "
                    f"(need {minutes_needed} more minutes)"
                )
                return None
            
            # Calculate indicators
            df_with_indicators = Indicators.calculate_all_indicators(
                df,
                rsi_period=config.RSI_PERIOD,
                sma_period=config.SMA_OI_PERIOD
            )
            
            # Cache the data
            cache_key = f"{option_type}_{strike}"
            self.data_cache[cache_key] = df_with_indicators
            self.last_update[cache_key] = datetime.now()
            
            return df_with_indicators
        
        except Exception as e:
            logger.error(f"Error getting option data with indicators: {str(e)}")
            return None
    
    def get_index_data_with_indicators(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get index data with all indicators calculated
        for logging spot price details
        
        Args:
            symbol: "NIFTY" or "SENSEX"
        
        Returns:
            DataFrame with OHLCV data and indicators
        """
        try:
            # Determine instrument key
            if symbol == "NIFTY":
                instrument_key = config.NIFTY_INDEX_SYMBOL
            elif symbol == "SENSEX":
                instrument_key = config.SENSEX_INDEX_SYMBOL
            else:
                return None
            
            # Fetch data (same logic as options: use get_combined_data)
            df = self.get_combined_data(instrument_key, config.PREVIOUS_DAY_CANDLES)
            
            if df is None or len(df) < config.SMA_OI_PERIOD:
                 return None
            
            # Calculate indicators
            # Note: Index data might not have 'oi' column, so some indicators might be skipped/NaN
            # but calculate_all_indicators handles missing columns gracefully
            df_with_indicators = Indicators.calculate_all_indicators(
                df,
                rsi_period=config.RSI_PERIOD,
                sma_period=config.SMA_OI_PERIOD
            )
            
            return df_with_indicators
        
        except Exception as e:
            logger.error(f"Error getting index data for {symbol}: {str(e)}")
            return None

    def update_live_candle(
        self,
        option_type: str,
        strike: int,
        expiry_date: str,
        new_candle: Optional[Dict] = None
    ) -> Optional[pd.DataFrame]:
        """
        Update data with new candle (for live trading)
        
        Args:
            option_type: "CE" or "PE"
            strike: Strike price
            expiry_date: Expiry date
            new_candle: New candle data dict (or None to fetch)
        
        Returns:
            Updated DataFrame with indicators
        """
        try:
            cache_key = f"{option_type}_{strike}"
            
            # Get current cached data
            if cache_key not in self.data_cache:
                logger.warning(f"No cached data for {cache_key}, fetching fresh data")
                return self.get_option_data_with_indicators(option_type, strike, expiry_date)
            
            df = self.data_cache[cache_key].copy()
            
            # Fetch latest candle if not provided
            if new_candle is None:
                instrument_key = dhan_client.get_instrument_key(
                    symbol="NIFTY",
                    strike=strike,
                    option_type=option_type,
                    expiry_date=expiry_date
                )

                latest_df = dhan_client.get_historical_data(
                    instrument_key=instrument_key,
                    interval=config.CANDLE_INTERVAL,
                    from_date=datetime.now().strftime('%Y-%m-%d'),
                    to_date=datetime.now().strftime('%Y-%m-%d')
                )
                
                if latest_df is None or len(latest_df) == 0:
                    logger.warning("Failed to fetch latest candle")
                    return df
                
                new_candle = latest_df.iloc[-1].to_dict()
                new_candle['timestamp'] = latest_df.index[-1]
            
            # Append new candle
            new_row = pd.DataFrame([new_candle])
            new_row.set_index('timestamp', inplace=True)
            
            df = pd.concat([df, new_row])
            df = df[~df.index.duplicated(keep='last')]
            df.sort_index(inplace=True)
            
            # Recalculate indicators
            df_with_indicators = Indicators.calculate_all_indicators(
                df,
                rsi_period=config.RSI_PERIOD,
                sma_period=config.SMA_OI_PERIOD
            )
            
            # Update cache
            self.data_cache[cache_key] = df_with_indicators
            self.last_update[cache_key] = datetime.now()
            
            return df_with_indicators
        
        except Exception as e:
            logger.error(f"Error updating live candle: {str(e)}")
            return None
    
    def get_nifty_price(self) -> Optional[float]:
        """
        Get current Nifty spot price
        Tries multiple sources in order:
        1. Dhan API (if configured)
        2. Yahoo Finance (free, no API key needed)
        3. Demo fallback price (if enabled)

        Returns:
            Nifty price or None
        """
        try:
            # Method 1: Try Dhan API first (most reliable if configured)
            if config.DHAN_ACCESS_TOKEN:
                logger.info("Trying Dhan API for Nifty price...")
                ltp = dhan_client.get_ltp(config.INDEX_SYMBOL)
                if ltp:
                    logger.info(f"✅ Nifty LTP from Dhan API: {ltp}")
                    return ltp
                else:
                    logger.warning(f"Dhan API call failed or returned None for {config.INDEX_SYMBOL}")
            else:
                logger.info("Dhan ACCESS_TOKEN not configured")

            # Method 2: Try Yahoo Finance (free alternative)
            logger.info("Trying Yahoo Finance for Nifty price...")
            nifty_price = self._get_nifty_from_yahoo()
            if nifty_price:
                logger.info(f"✅ Nifty price from Yahoo Finance: {nifty_price}")
                return nifty_price
            
            # Method 3: Demo fallback
            if config.DEMO_MODE:
                logger.warning(f"All sources failed. Using DEMO MODE fallback price: {config.DEMO_NIFTY_PRICE}")
                return config.DEMO_NIFTY_PRICE
            else:
                logger.error("Failed to fetch Nifty price from all sources")
                return None
        
        except Exception as e:
            logger.error(f"Error getting Nifty price: {str(e)}")
            
            if config.DEMO_MODE:
                logger.warning(f"Exception occurred. Using DEMO MODE fallback price: {config.DEMO_NIFTY_PRICE}")
                return config.DEMO_NIFTY_PRICE
            
            return None
    
    def _get_nifty_from_yahoo(self) -> Optional[float]:
        """
        Fetch Nifty 50 price from Yahoo Finance (free, no API key needed)
        
        Returns:
            Nifty price or None
        """
        try:
            import requests
            
            # Yahoo Finance symbol for Nifty 50
            symbol = "^NSEI"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract current price
                if 'chart' in data and 'result' in data['chart']:
                    result = data['chart']['result'][0]
                    if 'meta' in result and 'regularMarketPrice' in result['meta']:
                        price = result['meta']['regularMarketPrice']
                        return float(price)
            
            return None
        
        except Exception as e:
            logger.debug(f"Yahoo Finance fetch failed: {str(e)}")
            return None
    
    def get_sensex_price(self) -> Optional[float]:
        """
        Get current Sensex spot price from Yahoo Finance
        
        Returns:
            Sensex price or None
        """
        try:
            logger.info("Fetching Sensex from Yahoo Finance...")
            sensex_price = self._get_sensex_from_yahoo()
            if sensex_price:
                logger.info(f"✅ Sensex price from Yahoo Finance: {sensex_price}")
                return sensex_price
            
            logger.error("Failed to fetch Sensex price")
            return None
        
        except Exception as e:
            logger.error(f"Error getting Sensex price: {str(e)}")
            return None
    
    def _get_sensex_from_yahoo(self) -> Optional[float]:
        """
        Fetch Sensex price from Yahoo Finance
        
        Returns:
            Sensex price or None
        """
        try:
            import requests
            
            # Yahoo Finance symbol for Sensex
            symbol = "^BSESN"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'chart' in data and 'result' in data['chart']:
                    result = data['chart']['result'][0]
                    if 'meta' in result and 'regularMarketPrice' in result['meta']:
                        price = result['meta']['regularMarketPrice']
                        return float(price)
            
            return None
        
        except Exception as e:
            logger.debug(f"Sensex Yahoo Finance fetch failed: {str(e)}")
            return None

    def get_banknifty_price(self) -> Optional[float]:
        """
        Get current Bank Nifty spot price from Yahoo Finance (fallback only -
        calculate_oi_pcr's primary source is the Dhan option chain's own
        spot_price field; this only gets used if that's missing/zero).

        Returns:
            Bank Nifty price or None
        """
        try:
            logger.info("Fetching Bank Nifty from Yahoo Finance...")
            price = self._get_banknifty_from_yahoo()
            if price:
                logger.info(f"✅ Bank Nifty price from Yahoo Finance: {price}")
                return price

            logger.error("Failed to fetch Bank Nifty price")
            return None

        except Exception as e:
            logger.error(f"Error getting Bank Nifty price: {str(e)}")
            return None

    def _get_banknifty_from_yahoo(self) -> Optional[float]:
        """
        Fetch Bank Nifty price from Yahoo Finance

        Returns:
            Bank Nifty price or None
        """
        try:
            import requests

            # Yahoo Finance symbol for Bank Nifty
            symbol = "^NSEBANK"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if 'chart' in data and 'result' in data['chart']:
                    result = data['chart']['result'][0]
                    if 'meta' in result and 'regularMarketPrice' in result['meta']:
                        price = result['meta']['regularMarketPrice']
                        return float(price)

            return None

        except Exception as e:
            logger.debug(f"Bank Nifty Yahoo Finance fetch failed: {str(e)}")
            return None

    def get_nearest_expiry_from_list(self, instrument_key: str) -> Optional[str]:
        """
        Resolve the nearest upcoming expiry for an underlying by querying Dhan's
        expiry-list API directly, rather than assuming a fixed weekday offset
        like get_expiry_date() does for NIFTY/SENSEX. Needed for BANKNIFTY, whose
        options are monthly-only (confirmed against a live scrip master download -
        no weekly expiries exist), so there's no simple "+N days" rule to apply.

        Args:
            instrument_key: Composite key for the underlying INDEX, e.g. "IDX_I|25"

        Returns:
            Nearest expiry date string (YYYY-MM-DD), or None if unavailable
        """
        try:
            expiries = dhan_client.get_expiry_list(instrument_key)
            if not expiries:
                return None

            today_str = datetime.now().strftime('%Y-%m-%d')
            upcoming = sorted(e[:10] for e in expiries if e[:10] >= today_str)
            return upcoming[0] if upcoming else None

        except Exception as e:
            logger.error(f"Error resolving nearest expiry for {instrument_key}: {str(e)}")
            return None


# Global data manager instance
data_manager = DataManager()

if __name__ == "__main__":
    # Test data manager
    print("Testing Data Manager...")
    
    # Test expiry calculation
    today = datetime.now()
    expiry = data_manager.get_expiry_date(today)
    print(f"Current date: {today.strftime('%Y-%m-%d')}")
    print(f"Next expiry: {expiry}")
    
    # Test ATM strike calculation
    test_price = 25570
    strikes = data_manager.determine_atm_strikes(test_price)
    print(f"\nNifty @ {test_price}")
    print(f"Call Strike: {strikes['call']}")
    print(f"Put Strike: {strikes['put']}")
    
    print("\nData Manager module loaded successfully")