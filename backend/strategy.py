"""
Strategy Module
Contains the trading strategy logic for generating buy/sell signals
"""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Tuple

import config
from logger import logger
from indicators import Indicators
from data_manager import data_manager
from mongo_logger import mongo_logger

class OptionsStrategy:
    """Nifty Options OI-based trading strategy"""
    
    def __init__(self):
        self.name = "OI_Based_Options_Strategy"
        logger.info(f"Strategy initialized: {self.name}")
    
    def check_call_entry_signal(
        self,
        df: pd.DataFrame,
        strike: int
    ) -> Tuple[bool, Dict]:
        """
        Check if CALL option entry conditions are met
        
        Args:
            df: DataFrame with option data and indicators
            strike: Strike price
        
        Returns:
            Tuple of (signal_status, conditions_dict)
        """
        try:
            # Check entry conditions
            conditions = Indicators.check_entry_conditions(df, option_type="CALL")
            
            if conditions['entry_signal']:
                logger.info(f"✅ CALL {strike} entry signal detected!")
                logger.signal_detected("CALL", strike, conditions)
            
            return conditions['entry_signal'], conditions
        
        except Exception as e:
            logger.error(f"Error checking CALL entry signal: {str(e)}")
            return False, {}
    
    def check_put_entry_signal(
        self,
        df: pd.DataFrame,
        strike: int
    ) -> Tuple[bool, Dict]:
        """
        Check if PUT option entry conditions are met
        
        Args:
            df: DataFrame with option data and indicators
            strike: Strike price
        
        Returns:
            Tuple of (signal_status, conditions_dict)
        """
        try:
            # Check entry conditions
            conditions = Indicators.check_entry_conditions(df, option_type="PUT")
            
            if conditions['entry_signal']:
                logger.info(f"✅ PUT {strike} entry signal detected!")
                logger.signal_detected("PUT", strike, conditions)
            
            return conditions['entry_signal'], conditions
        
        except Exception as e:
            logger.error(f"Error checking PUT entry signal: {str(e)}")
            return False, {}
    
    def calculate_stop_loss(
        self,
        df: pd.DataFrame,
        entry_price: float = None
    ) -> Optional[float]:
        """
        Calculate stop loss based on fixed percentage of entry price
        
        Args:
            df: DataFrame (kept for compatibility, though not used for fixed % SL)
            entry_price: Entry price for calculation
        
        Returns:
            Stop loss level or None
        """
        try:
            if entry_price is None:
                if df is not None and not df.empty:
                    entry_price = df.iloc[-1]['close']
                else:
                    logger.error("Cannot calculate SL: No entry price or data")
                    return None
            
            # Calculate fixed % SL
            sl_percent = getattr(config, 'INITIAL_SL_PERCENT', 10)
            sl = entry_price * (1 - sl_percent / 100)
            
            logger.info(f"Stop loss calculated: ₹{sl:.2f} ({sl_percent}% risk)")
            return sl
        
        except Exception as e:
            logger.error(f"Error calculating stop loss: {str(e)}")
            return None
    
    def scan_for_signals(
        self,
        call_strike: int,
        put_strike: int,
        expiry_date: str,
        has_call_position: bool = False,
        has_put_position: bool = False,
        symbol: str = "NIFTY"
    ) -> Dict[str, any]:
        """
        Scan both CALL and PUT options for entry signals
        
        Args:
            call_strike: Call strike price
            put_strike: Put strike price
            expiry_date: Expiry date
            has_call_position: Whether CALL position already exists
            has_put_position: Whether PUT position already exists
            symbol: Index symbol ("NIFTY" or "SENSEX")
        
        Returns:
            Dictionary with signal information
        """
        signals = {
            'call_signal': False,
            'put_signal': False,
            'call_data': None,
            'put_data': None,
            'call_conditions': {},
            'put_conditions': {},
            'call_stop_loss': None,
            'put_stop_loss': None,
        }
        
        try:
            # Check CALL signal (only if no existing position)
            if not has_call_position:
                logger.debug(f"Scanning CALL {call_strike} for entry signal...")
                
                call_df = data_manager.get_option_data_with_indicators("CE", call_strike, expiry_date, symbol)
                
                if call_df is not None and len(call_df) >= config.SMA_OI_PERIOD:
                    call_signal, call_conditions = self.check_call_entry_signal(call_df, call_strike)
                    
                    # Log to MongoDB (stores OHLCV + indicators every 3 min)
                    if config.LOG_OPTION_CANDLES:
                        mongo_logger.log_option_candle(
                            timestamp=datetime.now(),
                            option_type="CALL",
                            strike=call_strike,
                            expiry=expiry_date,
                            instrument_key=call_df.iloc[-1].get('instrument_key', ''),
                            df=call_df
                        )
                    
                    # Log indicator values every scan
                    latest = call_df.iloc[-1]
                    
                    vwap_status = "✅" if call_conditions.get('price_below_vwap') else "❌"
                    rsi_status = "✅" if call_conditions.get('rsi_below_40') else "❌"
                    adx_status = "✅" if call_conditions.get('adx_confirmed') else "❌"
                    oi_status = "✅" if call_conditions.get('oi_above_sma') else "❌"
                    vol_status = "✅" if call_conditions.get('volume_confirmed') else "❌"
                    
                    # Calculate volume percentage vs SMA (percentage change)
                    vol_val = latest.get('volume', 0)
                    vol_sma_val = latest.get('volume_sma', 0)
                    vol_pct = ((vol_val - vol_sma_val) / vol_sma_val * 100) if vol_sma_val > 0 else 0
                    vol_pct_sign = "+" if vol_pct >= 0 else ""
                    
                    # Log status: ✅ if positive growth, ❌ if negative growth, ➖ if filter disabled
                    if not config.VOLUME_CONFIRMATION_ENABLED:
                        vol_status_symbol = "➖"
                    else:
                        vol_status_symbol = "✅" if vol_val >= vol_sma_val else "❌"
                    
                    logger.info(
                        f"📊 CALL {call_strike} | "
                        f"Price: ₹{latest['close']:.2f} | "
                        f"VWAP: ₹{latest.get('vwap', 0):.2f} {vwap_status} | "
                        f"RSI: {latest.get('rsi', 0):.1f} {rsi_status} | "
                        f"ADX: {latest.get('adx', 0):.1f} {adx_status} | "
                        f"OI: {int(latest['oi']):,} | "
                        f"OI_SMA: {int(latest.get('oi_sma', 0)):,} {oi_status} | "
                        f"Vol: {int(vol_val):,} | "
                        f"Vol_SMA: {int(vol_sma_val):,} ({vol_pct_sign}{vol_pct:.1f}%) {vol_status_symbol}"
                    )
                    
                    if call_signal:
                        current_price = call_df.iloc[-1]['close']
                        call_sl = self.calculate_stop_loss(call_df, entry_price=current_price)
                        
                        signals['call_signal'] = True
                        signals['call_data'] = call_df
                        signals['call_conditions'] = call_conditions
                        signals['call_stop_loss'] = call_sl
                elif call_df is not None:
                    logger.info(f"⏳ CALL {call_strike}: {len(call_df)}/{config.SMA_OI_PERIOD} candles (waiting for more data)")
                else:
                    logger.debug(f"No data available for CALL {call_strike}")
            
            # Check PUT signal (only if no existing position)
            if not has_put_position:
                logger.debug(f"Scanning PUT {put_strike} for entry signal...")
                
                put_df = data_manager.get_option_data_with_indicators("PE", put_strike, expiry_date, symbol)
                
                if put_df is not None and len(put_df) >= config.SMA_OI_PERIOD:
                    put_signal, put_conditions = self.check_put_entry_signal(put_df, put_strike)
                    
                    # Log to MongoDB (stores OHLCV + indicators every 3 min)
                    if config.LOG_OPTION_CANDLES:
                        mongo_logger.log_option_candle(
                            timestamp=datetime.now(),
                            option_type="PUT",
                            strike=put_strike,
                            expiry=expiry_date,
                            instrument_key=put_df.iloc[-1].get('instrument_key', ''),
                            df=put_df
                        )
                    
                    # Log indicator values every scan
                    latest = put_df.iloc[-1]
                    
                    vwap_status = "✅" if put_conditions.get('price_below_vwap') else "❌"
                    rsi_status = "✅" if put_conditions.get('rsi_below_40') else "❌"
                    adx_status = "✅" if put_conditions.get('adx_confirmed') else "❌"
                    oi_status = "✅" if put_conditions.get('oi_above_sma') else "❌"
                    vol_status = "✅" if put_conditions.get('volume_confirmed') else "❌"
                    
                    # Calculate volume percentage vs SMA (percentage change)
                    vol_val = latest.get('volume', 0)
                    vol_sma_val = latest.get('volume_sma', 0)
                    vol_pct = ((vol_val - vol_sma_val) / vol_sma_val * 100) if vol_sma_val > 0 else 0
                    vol_pct_sign = "+" if vol_pct >= 0 else ""
                    
                    # Log status: ✅ if positive growth, ❌ if negative growth, ➖ if filter disabled
                    if not config.VOLUME_CONFIRMATION_ENABLED:
                        vol_status_symbol = "➖"
                    else:
                        vol_status_symbol = "✅" if vol_val >= vol_sma_val else "❌"
                    
                    logger.info(
                        f"📊 PUT {put_strike} | "
                        f"Price: ₹{latest['close']:.2f} | "
                        f"VWAP: ₹{latest.get('vwap', 0):.2f} {vwap_status} | "
                        f"RSI: {latest.get('rsi', 0):.1f} {rsi_status} | "
                        f"ADX: {latest.get('adx', 0):.1f} {adx_status} | "
                        f"OI: {int(latest['oi']):,} | "
                        f"OI_SMA: {int(latest.get('oi_sma', 0)):,} {oi_status} | "
                        f"Vol: {int(vol_val):,} | "
                        f"Vol_SMA: {int(vol_sma_val):,} ({vol_pct_sign}{vol_pct:.1f}%) {vol_status_symbol}"
                    )
                    
                    if put_signal:
                        current_price = put_df.iloc[-1]['close']
                        put_sl = self.calculate_stop_loss(put_df, entry_price=current_price)
                        
                        signals['put_signal'] = True
                        signals['put_data'] = put_df
                        signals['put_conditions'] = put_conditions
                        signals['put_stop_loss'] = put_sl
                elif put_df is not None:
                    logger.info(f"⏳ PUT {put_strike}: {len(put_df)}/{config.SMA_OI_PERIOD} candles (waiting for more data)")
                else:
                    logger.debug(f"No data available for PUT {put_strike}")
            
            return signals
        
        except Exception as e:
            logger.error(f"Error scanning for signals: {str(e)}")
            return signals
    
    def should_exit_on_stop_loss(
        self,
        current_price: float,
        stop_loss: float,
        option_type: str,
        strike: int
    ) -> bool:
        """
        Check if stop loss is hit
        
        Args:
            current_price: Current option price
            stop_loss: Stop loss level
            option_type: "CALL" or "PUT"
            strike: Strike price
        
        Returns:
            True if stop loss hit, False otherwise
        """
        if current_price <= stop_loss:
            logger.warning(f"Stop loss hit for {option_type} {strike}: Current: ₹{current_price:.2f}, SL: ₹{stop_loss:.2f}")
            return True
        
        return False
    
    def validate_trading_time(self) -> bool:
        """
        Check if current time is within trading hours
        
        Returns:
            True if within trading hours, False otherwise
        """
        current_time = datetime.now().time()
        
        if config.TRADING_START_TIME <= current_time <= config.TRADING_END_TIME:
            return True
        
        logger.warning(f"Outside trading hours: {current_time}")
        return False
    
    def validate_init_time(self) -> bool:
        """
        Check if current time is valid for system initialization
        Allows initialization before trading starts (for data preparation)
        
        Returns:
            True if valid init time, False otherwise
        """
        current_time = datetime.now().time()
        
        # Allow initialization from market open to trading end
        if config.SYSTEM_INIT_START_TIME <= current_time <= config.TRADING_END_TIME:
            return True
        
        logger.warning(f"Outside initialization hours: {current_time}")
        return False
    
    def validate_trading_day(self) -> bool:
        """
        Check if today is a valid trading day (Friday, Monday, Tuesday)
        
        Returns:
            True if valid trading day, False otherwise
        """
        # Allow override for testing
        if config.SKIP_DAY_CHECK:
            logger.info("Day check skipped (SKIP_DAY_CHECK = True)")
            return True
        
        today = datetime.now().weekday()
        
        if today in config.ALLOWED_TRADING_DAYS:
            return True
        
        logger.warning(f"Not a trading day: {datetime.now().strftime('%A')}")
        return False
    
    def is_market_open(self) -> bool:
        """
        Check if market is currently open for trading
        
        Returns:
            True if market open, False otherwise
        """
        return self.validate_trading_day() and self.validate_trading_time()
    
    def is_market_open_for_init(self) -> bool:
        """
        Check if market is open for system initialization
        (allows initialization before trading hours)
        
        Returns:
            True if market open for init, False otherwise
        """
        return self.validate_trading_day() and self.validate_init_time()


# Global strategy instance
strategy = OptionsStrategy()

if __name__ == "__main__":
    # Test strategy module
    print("Testing Strategy Module...")
    
    # Test trading time validation
    print(f"\nIs market open: {strategy.is_market_open()}")
    print(f"Valid trading day: {strategy.validate_trading_day()}")
    print(f"Valid trading time: {strategy.validate_trading_time()}")
    
    # Test stop loss check
    test_sl = strategy.should_exit_on_stop_loss(
        current_price=145.0,
        stop_loss=150.0,
        option_type="CALL",
        strike=25550
    )
    print(f"\nStop loss hit: {test_sl}")
    
    print("\nStrategy module loaded successfully")