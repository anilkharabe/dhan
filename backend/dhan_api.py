"""
Dhan API Client
Wrapper for the DhanHQ v2 API (REST + WebSocket) covering market data
(OI/option-chain, historical candles, LTP) and order execution.

Instrument identification: Dhan needs a (security_id, exchange_segment) pair for
every API call, whereas the rest of this codebase (order_manager, data_manager,
main) was built around a single opaque "instrument_key" string (Upstox's
convention, e.g. "NSE_FO|42536"). To keep every call site elsewhere unchanged,
this module preserves that convention: get_instrument_key() returns a composite
string "{exchange_segment}|{security_id}" (e.g. "NSE_FNO|57430"), and every method
below that needs the pair parses it back out via _parse_key().
"""

import os
import time
import threading
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional, List, Dict, Tuple

import pandas as pd
import requests

from dhanhq import DhanContext, dhanhq
from dhanhq.marketfeed import MarketFeed

import config
import logger

# Numeric exchange-segment codes used by the MarketFeed WebSocket subscription API
# (see dhanhq.marketfeed.MarketFeed.get_exchange_segment for the reverse mapping)
_WS_SEGMENT_CODES = {
    "IDX_I": MarketFeed.IDX,
    "NSE_EQ": MarketFeed.NSE,
    "NSE_FNO": MarketFeed.NSE_FNO,
    "NSE_CURRENCY": MarketFeed.NSE_CURR,
    "BSE_EQ": MarketFeed.BSE,
    "MCX_COMM": MarketFeed.MCX,
    "BSE_CURRENCY": MarketFeed.BSE_CURR,
    "BSE_FNO": MarketFeed.BSE_FNO,
}
_WS_SEGMENT_NAMES = {v: k for k, v in _WS_SEGMENT_CODES.items()}


class DhanClient:
    """Dhan API client for market data (OI/option-chain/candles/LTP) and order execution"""

    def __init__(self):
        self.client_id = config.DHAN_CLIENT_ID
        self.access_token = config.DHAN_ACCESS_TOKEN

        self.dhan_context = None
        self.dhan = None
        if self.client_id and self.access_token:
            self._build_client(self.client_id, self.access_token)

        # Instrument master cache (filtered to NIFTY/SENSEX options + index rows)
        self.instruments_df = None
        self.instruments_cache_file = os.path.join(config.BASE_DIR, "dhan_instruments_cache.csv")

    def _build_client(self, client_id: str, access_token: str):
        self.dhan_context = DhanContext(client_id, access_token)
        self.dhan = dhanhq(self.dhan_context)

    def set_access_token(self, token: str):
        """Update the access token and rebuild the Dhan client context"""
        self.access_token = token
        self._build_client(self.client_id, token)
        logger.info(f"DhanClient token updated (starts with {token[:5]}...)")

    def _ready(self) -> bool:
        if not self.dhan:
            logger.error("DhanClient not initialized - DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN missing")
            return False
        return True

    # ------------------------------------------------------------------
    # Instrument master (Dhan's "compact" scrip master CSV)
    # ------------------------------------------------------------------
    def download_instruments_master(self, force_refresh: bool = False) -> bool:
        """
        Download Dhan's scrip master and cache the NIFTY/SENSEX/BANKNIFTY option
        rows (+ their index rows) needed by this system.

        Confirmed column schema (verified against a live download of
        https://images.dhan.co/api-data/api-scrip-master.csv):
          SEM_EXM_EXCH_ID ('NSE'/'BSE'), SEM_SEGMENT ('D'=F&O, 'I'=Index),
          SEM_INSTRUMENT_NAME ('OPTIDX' for index options), SEM_TRADING_SYMBOL
          (e.g. "NIFTY-Jul2026-25500-CE" / bare "NIFTY" for the index row),
          SEM_STRIKE_PRICE, SEM_OPTION_TYPE ('CE'/'PE'), SEM_EXPIRY_DATE
          ("YYYY-MM-DD HH:MM:SS"), SEM_LOT_UNITS, SEM_SMST_SECURITY_ID.
        """
        try:
            if not force_refresh and os.path.exists(self.instruments_cache_file):
                file_date = datetime.fromtimestamp(os.path.getmtime(self.instruments_cache_file)).date()
                if file_date == datetime.now().date():
                    logger.info("Loading Dhan instruments from cache...")
                    self.instruments_df = pd.read_csv(self.instruments_cache_file, low_memory=False)
                    logger.info(f"Loaded {len(self.instruments_df)} Dhan instruments from cache")
                    return True

            logger.info(f"Downloading Dhan scrip master from {config.DHAN_SCRIP_MASTER_URL}...")
            response = requests.get(config.DHAN_SCRIP_MASTER_URL, timeout=60)

            if response.status_code != 200:
                logger.error(f"Failed to download Dhan scrip master: {response.status_code}")
                return False

            df = pd.read_csv(StringIO(response.text), low_memory=False)

            options_mask = (
                (df['SEM_SEGMENT'] == 'D') &
                (df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
                (
                    ((df['SEM_EXM_EXCH_ID'] == 'NSE') & df['SEM_TRADING_SYMBOL'].astype(str).str.startswith('NIFTY-')) |
                    ((df['SEM_EXM_EXCH_ID'] == 'NSE') & df['SEM_TRADING_SYMBOL'].astype(str).str.startswith('BANKNIFTY-')) |
                    ((df['SEM_EXM_EXCH_ID'] == 'BSE') & df['SEM_TRADING_SYMBOL'].astype(str).str.startswith('SENSEX-'))
                )
            )
            index_mask = (
                (df['SEM_SEGMENT'] == 'I') &
                (df['SEM_TRADING_SYMBOL'].isin(['NIFTY', 'SENSEX', 'BANKNIFTY']))
            )

            self.instruments_df = df[options_mask | index_mask].copy()
            self.instruments_df.to_csv(self.instruments_cache_file, index=False)

            opt_count = int(options_mask.sum())
            idx_count = int(index_mask.sum())
            logger.info(f"✅ Downloaded and cached {len(self.instruments_df)} Dhan instruments")
            logger.info(f"  NIFTY/SENSEX/BANKNIFTY options: {opt_count} | Index rows: {idx_count}")

            return True

        except Exception as e:
            logger.error(f"Error downloading Dhan instruments master: {str(e)}")
            return False

    def search_instrument(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        expiry_date: str
    ) -> Optional[str]:
        """
        Search for a security_id in the cached Dhan scrip master.

        Args:
            symbol: Underlying symbol ("NIFTY" or "SENSEX")
            strike: Strike price
            option_type: "CE" or "PE"
            expiry_date: Expiry date (YYYY-MM-DD)

        Returns:
            Dhan security_id (as string) or None
        """
        try:
            if self.instruments_df is None:
                logger.info("Instruments not loaded, downloading...")
                if not self.download_instruments_master():
                    logger.error("Failed to download instruments")
                    return None

            df = self.instruments_df
            filtered = df[
                (df['SEM_TRADING_SYMBOL'].astype(str).str.startswith(f"{symbol.upper()}-")) &
                (df['SEM_STRIKE_PRICE'] == float(strike)) &
                (df['SEM_OPTION_TYPE'] == option_type) &
                (df['SEM_EXPIRY_DATE'].astype(str).str[:10] == expiry_date)
            ]

            if len(filtered) > 0:
                return str(int(filtered.iloc[0]['SEM_SMST_SECURITY_ID']))

            logger.warning(f"Dhan instrument not found: {symbol} {strike} {option_type} {expiry_date}")
            return None

        except Exception as e:
            logger.error(f"Error searching Dhan instrument: {str(e)}")
            return None

    def get_instrument_key(self, symbol: str, strike: int, option_type: str, expiry_date: str) -> str:
        """
        Resolve a composite instrument key "{exchange_segment}|{security_id}" for an
        option contract, mirroring the string-key convention the rest of this
        codebase already uses (kept so order_manager/data_manager/main need no
        structural changes beyond swapping the client).

        Args:
            symbol: Underlying symbol (e.g., "NIFTY")
            strike: Strike price
            option_type: "CE"/"PE" (also accepts "CALL"/"PUT")
            expiry_date: Expiry date (YYYY-MM-DD)

        Returns:
            Composite instrument key string, or "" if not found
        """
        try:
            if option_type.upper() == "CALL":
                option_type = "CE"
            elif option_type.upper() == "PUT":
                option_type = "PE"
            else:
                option_type = option_type.upper()

            security_id = self.search_instrument(symbol, strike, option_type, expiry_date)
            if not security_id:
                return ""

            exchange_segment = "BSE_FNO" if symbol.upper() == "SENSEX" else "NSE_FNO"
            return f"{exchange_segment}|{security_id}"

        except Exception as e:
            logger.error(f"Error generating Dhan instrument key: {str(e)}")
            return ""

    def _parse_key(self, instrument_key: str) -> Tuple[str, str]:
        """Split a composite instrument key into (exchange_segment, security_id)"""
        exchange_segment, _, security_id = instrument_key.partition("|")
        return exchange_segment, security_id

    # ------------------------------------------------------------------
    # Historical candles (with OI) - feeds indicators (VWAP/RSI/OI-SMA)
    # ------------------------------------------------------------------
    def get_historical_data(
        self,
        instrument_key: str,
        interval: str,
        from_date: str = None,
        to_date: str = None,
        _retries: int = 2
    ) -> Optional[pd.DataFrame]:
        """
        Fetch minute candles (with Open Interest) via Dhan's intraday charts API.

        Dhan's charts endpoint has been observed to intermittently rate-limit
        (DH-904) on rapid back-to-back calls for different instruments - retry
        with a brief pause before giving up, same pattern as get_ltp().

        Args:
            instrument_key: Composite key "{exchange_segment}|{security_id}"
            interval: Candle interval, e.g. "1minute", "3minute", "5minute"
            from_date: Start date (YYYY-MM-DD); defaults to today if not given
            to_date: End date (YYYY-MM-DD); defaults to today if not given

        Returns:
            DataFrame indexed by timestamp with columns [open, high, low, close, volume, oi]
        """
        if not self._ready() or not instrument_key:
            return None

        try:
            exchange_segment, security_id = self._parse_key(instrument_key)
            if not security_id:
                logger.warning(f"get_historical_data called with invalid instrument_key: {instrument_key}")
                return None

            instrument_type = "INDEX" if exchange_segment == "IDX_I" else "OPTIDX"

            if "minute" in interval:
                interval_value = int(interval.replace("minute", "") or "1")
            else:
                interval_value = 1

            today_str = datetime.now().strftime("%Y-%m-%d")
            from_date = from_date or today_str
            to_date = to_date or today_str

            response = self.dhan.intraday_minute_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                from_date=from_date,
                to_date=to_date,
                interval=interval_value,
                oi=(instrument_type != "INDEX"),
            )

            if not response or response.get('status') != 'success':
                is_rate_limit = response and response.get('remarks', {}).get('error_type') == 'Rate_Limit'
                if is_rate_limit and _retries > 0:
                    time.sleep(1.0)
                    return self.get_historical_data(instrument_key, interval, from_date, to_date, _retries=_retries - 1)
                logger.error(f"Dhan intraday_minute_data failed for {instrument_key}: {response}")
                return None

            data = response.get('data', {})
            # NOTE: Dhan's charts API returns a columnar dict of parallel arrays
            # ({"open": [...], "high": [...], ..., "timestamp": [...], "open_interest": [...]})
            # per its documented response shape. VERIFY this against a live response
            # the first time this runs with real credentials -- if the shape differs,
            # adjust the parsing below (see plan's Phase 1 exploration notes).
            if not data or 'open' not in data:
                logger.warning(f"No candle data returned for {instrument_key}")
                return None

            df = pd.DataFrame({
                'timestamp': data.get('timestamp', []),
                'open': data.get('open', []),
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', []),
                'volume': data.get('volume', []),
                'oi': data.get('open_interest', [0] * len(data.get('open', []))),
            })

            if df.empty:
                return None

            # Dhan returns epoch seconds in UTC; convert to naive IST (UTC+5:30) so
            # candle timestamps match wall-clock market hours (9:15-15:30 IST) -
            # confirmed live: raw UTC labeling put candles ~5.5h off (e.g. a 15:29 IST
            # candle showing as 09:59).
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)

            return df

        except Exception as e:
            logger.error(f"Error fetching Dhan historical data: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # Option chain (OI + greeks + volume per strike) - feeds OI-PCR
    # ------------------------------------------------------------------
    def get_option_chain(self, instrument_key: str, expiry_date: str) -> Optional[Dict]:
        """
        Fetch the option chain for an underlying index.

        Args:
            instrument_key: Composite key for the underlying INDEX, e.g. "IDX_I|13"
            expiry_date: Expiry date (YYYY-MM-DD)

        Returns:
            Dict: {'spot_price': float, 'strikes': {strike_float: {'ce': {...}, 'pe': {...}}}}
        """
        if not self._ready():
            return None

        try:
            exchange_segment, security_id = self._parse_key(instrument_key)

            response = self.dhan.option_chain(
                under_security_id=int(security_id),
                under_exchange_segment=exchange_segment,
                expiry=expiry_date
            )

            if not response or response.get('status') != 'success':
                logger.error(f"Dhan option_chain failed for {instrument_key} {expiry_date}: {response}")
                return None

            # Response is nested: {'status': 'success', 'data': {'data': {'last_price':.., 'oc': {...}}, 'status': 'success'}}
            # (confirmed against a live call - same double-wrap pattern as ticker_data)
            data = response.get('data', {}).get('data', {})
            spot_price = data.get('last_price')
            oc = data.get('oc', {})

            strikes = {}
            for strike_str, leg_data in oc.items():
                try:
                    strikes[float(strike_str)] = {
                        'ce': leg_data.get('ce', {}),
                        'pe': leg_data.get('pe', {}),
                    }
                except (TypeError, ValueError):
                    continue

            return {'spot_price': spot_price, 'strikes': strikes}

        except Exception as e:
            logger.error(f"Error fetching Dhan option chain: {str(e)}")
            return None

    def get_expiry_list(self, instrument_key: str) -> Optional[List[str]]:
        """Fetch available expiry dates for an underlying index"""
        if not self._ready():
            return None
        try:
            exchange_segment, security_id = self._parse_key(instrument_key)
            response = self.dhan.expiry_list(int(security_id), exchange_segment)
            if response and response.get('status') == 'success':
                return response.get('data', {}).get('data', [])
            return None
        except Exception as e:
            logger.error(f"Error fetching Dhan expiry list: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # LTP / current price
    # ------------------------------------------------------------------
    def get_ltp(self, instrument_key: str, _retries: int = 2) -> Optional[float]:
        """
        Get Last Traded Price for an instrument via Dhan's Market Quote (LTP mode).

        Dhan's ticker/LTP endpoint has been observed to intermittently fail on
        rapid back-to-back calls (transient, not a payload/auth problem - retrying
        after a brief pause resolves it) - retry a couple of times before giving up,
        since a silent None here would otherwise cost a signal-detection cycle.

        Args:
            instrument_key: Composite key "{exchange_segment}|{security_id}"

        Returns:
            LTP or None
        """
        if not self._ready() or not instrument_key:
            return None

        try:
            exchange_segment, security_id = self._parse_key(instrument_key)
            response = self.dhan.ticker_data({exchange_segment: [int(security_id)]})

            if not response or response.get('status') != 'success':
                if _retries > 0:
                    time.sleep(0.5)
                    return self.get_ltp(instrument_key, _retries=_retries - 1)
                logger.error(f"Dhan ticker_data failed for {instrument_key}: {response}")
                return None

            data = response.get('data', {}).get('data', {})
            leg = data.get(exchange_segment, {}).get(str(security_id))
            if leg and 'last_price' in leg:
                return float(leg['last_price'])

            logger.warning(f"No LTP in Dhan response for {instrument_key}")
            return None

        except Exception as e:
            logger.error(f"Error fetching Dhan LTP for {instrument_key}: {str(e)}")
            return None

    def get_current_price(self, instrument_key: str) -> Optional[float]:
        """
        Get current price. Prefers true LTP; falls back to the latest minute
        candle's close (mirrors upstox_api.py's get_current_price fallback shape).
        """
        ltp = self.get_ltp(instrument_key)
        if ltp is not None:
            return ltp

        try:
            df = self.get_historical_data(instrument_key, "1minute")
            if df is not None and len(df) > 0:
                return float(df.iloc[-1]['close'])
        except Exception as e:
            logger.error(f"Error getting Dhan current price fallback: {str(e)}")

        return None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def place_order(
        self,
        instrument_key: str,
        quantity: int,
        transaction_type: str = "BUY",
        order_type: str = "MARKET",
        product: str = "INTRADAY"
    ) -> Optional[str]:
        """
        Place an order.

        Args:
            instrument_key: Composite key "{exchange_segment}|{security_id}"
            quantity: Order quantity (shares, not lots)
            transaction_type: BUY or SELL
            order_type: MARKET or LIMIT
            product: INTRADAY or CNC (Dhan product-type constants)

        Returns:
            Order ID or None
        """
        if config.PAPER_TRADING:
            logger.info(f"[PAPER TRADING] Would place order: {transaction_type} {quantity} {instrument_key}")
            fake_order_id = f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return fake_order_id

        if not self._ready():
            return None

        try:
            exchange_segment, security_id = self._parse_key(instrument_key)

            response = self.dhan.place_order(
                security_id=security_id,
                exchange_segment=exchange_segment,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                product_type=product,
                price=0,
            )

            if response and response.get('status') == 'success':
                order_id = response.get('data', {}).get('orderId')
                logger.info(f"Order placed successfully: {order_id}")
                return order_id

            logger.error(f"Failed to place order: {response}")
            return None

        except Exception as e:
            logger.error(f"Error placing Dhan order: {str(e)}")
            return None

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get order status by order ID"""
        if not self._ready():
            return None
        try:
            return self.dhan.get_order_by_id(order_id)
        except Exception as e:
            logger.error(f"Error fetching Dhan order status: {str(e)}")
            return None

    def get_positions(self) -> Optional[List[Dict]]:
        """Get current open positions from Dhan"""
        if not self._ready():
            return None
        try:
            response = self.dhan.get_positions()
            if response and response.get('status') == 'success':
                return response.get('data', [])
            return None
        except Exception as e:
            logger.error(f"Error fetching Dhan positions: {str(e)}")
            return None


class DhanWebSocketClient:
    """WebSocket client for real-time LTP/OI ticks using Dhan's Live Market Feed (Full mode)"""

    def __init__(self, client_id: str, access_token: str, on_tick_callback=None):
        """
        Args:
            client_id: Dhan client ID
            access_token: Dhan access token
            on_tick_callback: Callback invoked for every tick, signature: on_tick_callback(tick_dict)
        """
        self.client_id = client_id
        self.access_token = access_token
        self.on_tick_callback = on_tick_callback

        self.connected = False
        self.feed = None
        self.thread = None

        # instrument_key ("{segment}|{security_id}") -> latest tick dict
        self.tick_buffers: Dict[str, Dict] = {}
        self.subscribed_instruments = set()

        self.lock = threading.Lock()

        logger.info("Dhan WebSocket client initialized")

    def set_access_token(self, token: str):
        """Update the access token and reconnect if needed"""
        if self.access_token == token:
            return

        logger.info("DhanWebSocketClient token updating...")
        self.access_token = token

        if self.connected:
            logger.info("Reconnecting Dhan WebSocket with new token...")
            self.disconnect()
            self.connect()

    def connect(self) -> bool:
        """Connect to Dhan's Live Market Feed (starts a background thread)"""
        try:
            dhan_context = DhanContext(self.client_id, self.access_token)

            self.feed = MarketFeed(
                dhan_context,
                instruments=[],
                version='v2',
                on_message=self._on_message,
                on_connect=self._on_connect,
                on_close=self._on_close,
                on_error=self._on_error,
            )

            self.thread = self.feed.start()

            for _ in range(50):  # wait up to 5 seconds
                if self.connected:
                    break
                time.sleep(0.1)

            if self.connected:
                logger.info("✅ Dhan WebSocket connected successfully")
                return True

            logger.error("❌ Dhan WebSocket connection timed out or failed")
            return False

        except Exception as e:
            logger.error(f"Error connecting to Dhan WebSocket: {str(e)}")
            return False

    def subscribe(self, instrument_keys: List[str], mode: str = "full", force: bool = False) -> bool:
        """
        Subscribe to instruments for live ticks.

        Args:
            instrument_keys: List of composite instrument keys ("{segment}|{security_id}")
            mode: kept for call-site parity with the old Upstox client; Dhan always
                  subscribes in Full mode here so OI/volume/LTP arrive in one tick.
            force: Re-send subscription even if already subscribed (used on reconnect)
        """
        with self.lock:
            if force:
                new_keys = instrument_keys
            else:
                new_keys = [k for k in instrument_keys if k not in self.subscribed_instruments]
            self.subscribed_instruments.update(instrument_keys)

        if not new_keys:
            return True

        if not self.feed:
            logger.warning("Dhan WebSocket not connected yet, added to pending subscriptions")
            return False

        try:
            symbols = []
            for key in new_keys:
                segment, security_id = key.split("|", 1)
                seg_code = _WS_SEGMENT_CODES.get(segment)
                if seg_code is None:
                    logger.warning(f"Unknown exchange segment for Dhan WS subscribe: {segment}")
                    continue
                symbols.append((seg_code, security_id, MarketFeed.Full))

            if symbols:
                self.feed.subscribe_symbols(symbols)

            logger.info(f"✅ Subscribed to {len(new_keys)} instrument(s) on Dhan WebSocket")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to Dhan instruments: {str(e)}")
            return False

    def unsubscribe(self, instrument_keys: List[str]) -> bool:
        """Unsubscribe from instruments"""
        if not self.feed:
            return False
        try:
            symbols = []
            for key in instrument_keys:
                segment, security_id = key.split("|", 1)
                seg_code = _WS_SEGMENT_CODES.get(segment)
                if seg_code is None:
                    continue
                symbols.append((seg_code, security_id, MarketFeed.Full))

            if symbols:
                self.feed.unsubscribe_symbols(symbols)

            with self.lock:
                self.subscribed_instruments.difference_update(instrument_keys)

            return True
        except Exception as e:
            logger.error(f"Error unsubscribing from Dhan instruments: {str(e)}")
            return False

    def _on_connect(self, instance):
        logger.info("🔌 Dhan WebSocket connection opened")
        self.connected = True

    def _on_message(self, instance, data: Dict):
        """Handle a decoded tick dict from MarketFeed (Ticker/Quote/Full packet)"""
        try:
            if not data or 'security_id' not in data:
                return

            segment_code = data.get('exchange_segment')
            segment_name = _WS_SEGMENT_NAMES.get(segment_code, str(segment_code))
            security_id = data['security_id']
            instrument_key = f"{segment_name}|{security_id}"

            tick = {
                'timestamp': datetime.now(),
                'instrument_key': instrument_key,
                'ltp': float(data.get('LTP', 0.0) or 0.0),
                'open': float(data.get('open', 0.0) or 0.0),
                'high': float(data.get('high', 0.0) or 0.0),
                'low': float(data.get('low', 0.0) or 0.0),
                'close': float(data.get('close', 0.0) or 0.0),
                'volume': int(data.get('volume', 0) or 0),
                'oi': int(data.get('OI', 0) or 0),
            }

            with self.lock:
                self.tick_buffers[instrument_key] = tick

            if self.on_tick_callback:
                self.on_tick_callback(tick)

        except Exception as e:
            logger.error(f"Error processing Dhan WebSocket message: {str(e)}")

    def _on_error(self, instance, error):
        logger.error(f"❌ Dhan WebSocket error: {error}")

    def _on_close(self, instance):
        logger.warning("🔌 Dhan WebSocket connection closed")
        self.connected = False

    def disconnect(self):
        """Disconnect the WebSocket"""
        try:
            if self.feed:
                self.feed.close_connection()
            self.connected = False
            logger.info("Dhan WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting Dhan WebSocket: {str(e)}")

    def is_connected(self) -> bool:
        return self.connected

    def get_latest_tick(self, instrument_key: str) -> Optional[Dict]:
        """Get the latest tick for an instrument"""
        with self.lock:
            return self.tick_buffers.get(instrument_key)


# Global Dhan client instance
dhan_client = DhanClient()

if __name__ == "__main__":
    print("Testing Dhan Client...")
    print(f"Client ID configured: {bool(config.DHAN_CLIENT_ID)}")
    print(f"Access token configured: {bool(config.DHAN_ACCESS_TOKEN)}")
    print("Dhan Client module loaded successfully")
