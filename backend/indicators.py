"""
Technical Indicators Module
Calculates VWAP, RSI, and SMA for the trading strategy
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import logger

class Indicators:
    """Calculate technical indicators for options trading"""
    
    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """
        Calculate VWAP (Volume Weighted Average Price)
        Resets at the start of each trading day to match broker session VWAP.
        
        Args:
            df: DataFrame with columns ['high', 'low', 'close', 'volume']
            Index should be DatetimeIndex
        
        Returns:
            Series with VWAP values
        """
        try:
            # Typical price = (High + Low + Close) / 3
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            tp_vol = typical_price * df['volume']
            
            # Calculate VWAP per day using groupby on the index date
            # This ensures VWAP resets at the start of each session (e.g., 9:15 AM)
            # as is standard on trading platforms like Zerodha Kite.
            dates = df.index.date
            
            cumulative_tp_volume = tp_vol.groupby(dates).cumsum()
            cumulative_volume = df['volume'].groupby(dates).cumsum()
            
            vwap = cumulative_tp_volume / cumulative_volume
            
            return vwap
        
        except Exception as e:
            logger.error(f"Error calculating VWAP: {str(e)}")
            return pd.Series([np.nan] * len(df), index=df.index)
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            df: DataFrame with 'close' column
            period: RSI period (default 14)
        
        Returns:
            Series with RSI values
        """
        try:
            close = df['close']
            
            # Calculate price changes
            delta = close.diff()
            
            # Separate gains and losses
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Calculate average gain and loss using EMA
            avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
            avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
            
            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
        
        except Exception as e:
            logger.error(f"Error calculating RSI: {str(e)}")
            return pd.Series([np.nan] * len(df))
    
    @staticmethod
    def calculate_sma(series: pd.Series, period: int = 20) -> pd.Series:
        """
        Calculate SMA (Simple Moving Average)
        
        Args:
            series: Series of values (e.g., OI data)
            period: SMA period (default 20)
        
        Returns:
            Series with SMA values
        """
        try:
            sma = series.rolling(window=period, min_periods=period).mean()
            return sma
        
        except Exception as e:
            logger.error(f"Error calculating SMA: {str(e)}")
            return pd.Series([np.nan] * len(series))
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate ADX (Average Directional Index)

        Args:
            df: DataFrame with 'high', 'low', 'close' columns
            period: ADX period (default 14)

        Returns:
            Series with ADX values
        """
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            # Calculate True Range (TR)
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Calculate Directional Movement (DM)
            up_move = high - high.shift(1)
            down_move = low.shift(1) - low
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            
            plus_dm = pd.Series(plus_dm, index=df.index)
            minus_dm = pd.Series(minus_dm, index=df.index)
            
            # Smooth TR and DM (using Wilder's smoothing)
            # Wilder's Smoothing: 
            # 1. First value is SMA of first 'period' values
            # 2. Subsequent values: (Previous * (period-1) + Current) / period
            
            def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
                data = series.values
                n = len(data)
                smoothed = np.full(n, np.nan)
                
                # Need at least 'period' valid values
                # Find first valid index if any NaNs at start
                first_valid_idx = series.first_valid_index()
                if first_valid_idx is None:
                    return pd.Series(smoothed, index=series.index)
                    
                start_idx = series.index.get_loc(first_valid_idx)
                
                if n < start_idx + period:
                    return pd.Series(smoothed, index=series.index)
                
                # Initialize with SMA
                # The first smoothed value is at index (start_idx + period - 1)
                first_sma = np.mean(data[start_idx:start_idx+period])
                smoothed[start_idx + period - 1] = first_sma
                
                # Iterate for subsequent values
                alpha = 1.0 / period
                for i in range(start_idx + period, n):
                    # y[i] = y[i-1] * (1-alpha) + x[i] * alpha
                    # equivalent to (y[i-1] * (period-1) + x[i]) / period
                    smoothed[i] = smoothed[i-1] * (1.0 - alpha) + data[i] * alpha
                    
                return pd.Series(smoothed, index=series.index)

            tr_smooth = wilder_smooth(tr, period)
            plus_dm_smooth = wilder_smooth(plus_dm, period)
            minus_dm_smooth = wilder_smooth(minus_dm, period)
            
            # Calculate DI
            # Handle division by zero/NaN
            tr_smooth = tr_smooth.replace(0, np.nan)
            
            plus_di = 100 * (plus_dm_smooth / tr_smooth)
            minus_di = 100 * (minus_dm_smooth / tr_smooth)
            
            # Calculate DX
            sum_di = plus_di + minus_di
            diff_di = abs(plus_di - minus_di)
            dx = 100 * (diff_di / sum_di)
            
            # ADX is smoothed DX
            adx = wilder_smooth(dx, period)

            return adx

        except Exception as e:
            logger.error(f"Error calculating ADX: {str(e)}")
            return pd.Series([np.nan] * len(df))
    
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame, rsi_period: int = 14, sma_period: int = 20) -> pd.DataFrame:
        """
        Calculate all indicators at once and add to DataFrame
        
        Args:
            df: DataFrame with OHLCV data and OI
            rsi_period: RSI period
            sma_period: SMA period for OI and Volume
        
        Returns:
            DataFrame with added indicator columns
        """
        try:
            import config
            
            # Make a copy to avoid modifying original
            df_copy = df.copy()
            
            # Calculate VWAP
            df_copy['vwap'] = Indicators.calculate_vwap(df_copy)
            
            # Calculate RSI
            df_copy['rsi'] = Indicators.calculate_rsi(df_copy, period=rsi_period)
            
            # Calculate ADX
            adx_period = getattr(config, 'ADX_PERIOD', 14)
            df_copy['adx'] = Indicators.calculate_adx(df_copy, period=adx_period)
            
            # Calculate SMA on OI
            if 'oi' in df_copy.columns:
                df_copy['oi_sma'] = Indicators.calculate_sma(df_copy['oi'], period=sma_period)
            
            # Calculate SMA on Volume (for volume confirmation)
            if 'volume' in df_copy.columns:
                df_copy['volume_sma'] = Indicators.calculate_sma(df_copy['volume'], period=sma_period)
            
            return df_copy
        
        except Exception as e:
            logger.error(f"Error calculating all indicators: {str(e)}")
            return df
    
    @staticmethod
    def get_exit_reasoning(df: pd.DataFrame) -> str:
        """Get reasoning string based on latest indicator values for exits"""
        try:
            latest = Indicators.get_latest_values(df)
            adx = latest.get('adx', np.nan)
            oi = latest.get('oi', np.nan)
            vwap = latest.get('vwap', np.nan)
            rsi = latest.get('rsi', np.nan)
            
            reasons = []
            if not np.isnan(adx): reasons.append(f"ADX: {adx:.1f}")
            if not np.isnan(vwap): reasons.append(f"VWAP: {vwap:.2f}")
            if not np.isnan(rsi): reasons.append(f"RSI: {rsi:.1f}")
            if not np.isnan(oi): reasons.append(f"OI: {oi/1000000:.2f}M")
            
            return " | ".join(reasons) if reasons else "No indicator data"
        except Exception:
            return "No indicator data"

    @staticmethod
    def get_latest_values(df: pd.DataFrame) -> Dict[str, float]:
        """
        Get the latest values of all indicators
        
        Args:
            df: DataFrame with calculated indicators
        
        Returns:
            Dictionary with latest values
        """
        try:
            latest = df.iloc[-1]
            
            return {
                'close': latest.get('close', np.nan),
                'vwap': latest.get('vwap', np.nan),
                'rsi': latest.get('rsi', np.nan),
                'adx': latest.get('adx', np.nan),
                'oi': latest.get('oi', np.nan),
                'oi_sma': latest.get('oi_sma', np.nan),
                'high': latest.get('high', np.nan),
                'low': latest.get('low', np.nan),
                'volume': latest.get('volume', np.nan),
                'volume_sma': latest.get('volume_sma', np.nan),
            }
        
        except Exception as e:
            logger.error(f"Error getting latest values: {str(e)}")
            return {}
    
    @staticmethod
    def check_entry_conditions(df: pd.DataFrame, option_type: str = "CALL") -> Dict[str, bool]:
        """
        Check if entry conditions are met for a given option type
        
        Args:
            df: DataFrame with calculated indicators
            option_type: "CALL" or "PUT"
        
        Returns:
            Dictionary with condition checks and values
        """
        try:
            import config
            
            latest = Indicators.get_latest_values(df)
            
            # Extract values
            close = latest['close']
            vwap = latest['vwap']
            rsi = latest['rsi']
            adx = latest.get('adx', 0)
            oi = latest['oi']
            oi_sma = latest['oi_sma']
            volume = latest.get('volume', 0)
            volume_sma = latest.get('volume_sma', 0)
            
            # Check conditions
            price_below_vwap = close < vwap if not np.isnan(close) and not np.isnan(vwap) else False
            rsi_below_40 = rsi < config.RSI_THRESHOLD if not np.isnan(rsi) else False
            oi_above_sma = oi > oi_sma if not np.isnan(oi) and not np.isnan(oi_sma) else False
            
            # ADX Momentum Check
            adx_threshold = getattr(config, 'ADX_THRESHOLD', 25)
            adx_confirmed = adx > adx_threshold if not np.isnan(adx) else False
            
            # ADX Trend Check (Rising/Falling)
            adx_rising = False
            adx_must_be_rising = getattr(config, 'ADX_MUST_BE_RISING', True)
            adx_slope_period = getattr(config, 'ADX_SLOPE_PERIOD', 1)
            
            # Get previous ADX value
            prev_adx = np.nan
            if 'adx' in df.columns and len(df) > adx_slope_period:
                prev_adx = df['adx'].iloc[-(adx_slope_period + 1)]
                
            if not np.isnan(adx) and not np.isnan(prev_adx):
                adx_rising = adx > prev_adx
            
            # If enabled, entry requires ADX to be rising
            if adx_confirmed and adx_must_be_rising:
                adx_confirmed = adx_confirmed and adx_rising
            
            # Volume confirmation check
            volume_confirmed = True  # Default to True if disabled
            if config.VOLUME_CONFIRMATION_ENABLED:
                if not np.isnan(volume) and not np.isnan(volume_sma) and volume_sma > 0:
                    # Current volume must be >= 120% of average (or configured threshold)
                    volume_threshold = volume_sma * (config.VOLUME_THRESHOLD_PERCENT / 100.0)
                    volume_confirmed = volume >= volume_threshold
                else:
                    volume_confirmed = False
            
            # All conditions must be True for entry
            entry_signal = price_below_vwap and rsi_below_40 and oi_above_sma and adx_confirmed and volume_confirmed

            # Generate reasoning string
            reasons = []
            if price_below_vwap:
                reasons.append(f"Price ({close:.2f}) < VWAP ({vwap:.2f})")
            if rsi_below_40:
                reasons.append(f"RSI ({rsi:.1f}) < {config.RSI_THRESHOLD}")
            if oi_above_sma:
                reasons.append("OI > SMA")
            if adx_confirmed:
                reasons.append(f"ADX ({adx:.1f}) Trend Strong")
            if volume_confirmed:
                reasons.append("Vol confirmed")

            reasoning = " | ".join(reasons) if entry_signal else "Conditions not met"

            return {
                'entry_signal': entry_signal,
                'reasoning': reasoning,
                'price_below_vwap': price_below_vwap,
                'rsi_below_40': rsi_below_40,
                'oi_above_sma': oi_above_sma,
                'adx_confirmed': adx_confirmed,
                'adx_rising': adx_rising,
                'volume_confirmed': volume_confirmed,
                'close': close,
                'vwap': vwap,
                'rsi': rsi,
                'adx': adx,
                'prev_adx': prev_adx,
                'oi': oi,
                'oi_sma': oi_sma,
                'volume': volume,
                'volume_sma': volume_sma,
            }
        
        except Exception as e:
            logger.error(f"Error checking entry conditions: {str(e)}")
            return {'entry_signal': False}
    
    @staticmethod
    def get_stop_loss_level(df: pd.DataFrame, offset: int = 2) -> float:
        """
        Get stop loss level based on the low of t-offset candle
        
        Args:
            df: DataFrame with candle data
            offset: Number of candles back (default 2 for t-2)
        
        Returns:
            Stop loss level (low of t-offset candle)
        """
        try:
            if len(df) < offset + 1:
                logger.warning(f"Not enough candles for SL calculation. Need at least {offset + 1}, have {len(df)}")
                return np.nan
            
            # Get the low of t-offset candle
            stop_loss = df.iloc[-(offset + 1)]['low']
            
            return stop_loss
        
        except Exception as e:
            logger.error(f"Error getting stop loss level: {str(e)}")
            return np.nan


class IndicatorValidator:
    """Validate indicator calculations and data quality"""
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> bool:
        """
        Validate that DataFrame has required columns and sufficient data
        
        Args:
            df: DataFrame to validate
        
        Returns:
            True if valid, False otherwise
        """
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        
        # Check required columns
        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return False
        
        # Check minimum rows
        if len(df) < 20:  # Need at least 20 for SMA calculation
            logger.warning(f"Insufficient data: {len(df)} rows (minimum 20 required)")
            return False
        
        # Check for NaN values in critical columns
        for col in required_columns:
            if df[col].isna().any():
                logger.warning(f"NaN values found in {col}")
        
        return True
    
    @staticmethod
    def validate_indicators(df: pd.DataFrame) -> Dict[str, bool]:
        """
        Validate that all indicators are calculated correctly
        
        Args:
            df: DataFrame with indicators
        
        Returns:
            Dictionary with validation results
        """
        results = {
            'vwap_valid': False,
            'rsi_valid': False,
            'adx_valid': False,
            'oi_sma_valid': False,
        }
        
        # Check VWAP
        if 'vwap' in df.columns and not df['vwap'].iloc[-1] == np.nan:
            results['vwap_valid'] = True
        
        # Check RSI
        if 'rsi' in df.columns and not df['rsi'].iloc[-1] == np.nan:
            if 0 <= df['rsi'].iloc[-1] <= 100:
                results['rsi_valid'] = True
        
        # Check ADX
        if 'adx' in df.columns and not df['adx'].iloc[-1] == np.nan:
            if 0 <= df['adx'].iloc[-1] <= 100:
                results['adx_valid'] = True
        
        # Check OI SMA
        if 'oi_sma' in df.columns and not df['oi_sma'].iloc[-1] == np.nan:
            results['oi_sma_valid'] = True
        
        return results


if __name__ == "__main__":
    # Test indicators with sample data
    print("Testing Indicators Module...")
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range('2025-02-07 09:15:00', periods=30, freq='3min')
    
    sample_data = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.uniform(100, 110, 30),
        'high': np.random.uniform(110, 120, 30),
        'low': np.random.uniform(90, 100, 30),
        'close': np.random.uniform(100, 110, 30),
        'volume': np.random.randint(1000, 10000, 30),
        'oi': np.random.randint(50000, 100000, 30),
    })
    
    print("\nSample Data:")
    print(sample_data.head())
    
    # Calculate indicators
    print("\nCalculating indicators...")
    df_with_indicators = Indicators.calculate_all_indicators(sample_data)
    
    print("\nLatest values:")
    latest = Indicators.get_latest_values(df_with_indicators)
    for key, value in latest.items():
        print(f"  {key}: {value:.2f}")
    
    # Check entry conditions
    print("\nEntry conditions:")
    conditions = Indicators.check_entry_conditions(df_with_indicators)
    for key, value in conditions.items():
        print(f"  {key}: {value}")
    
    # Get stop loss
    print("\nStop Loss:")
    sl = Indicators.get_stop_loss_level(df_with_indicators, offset=2)
    print(f"  SL Level: {sl:.2f}")
    
    print("\nIndicators module test completed!")
