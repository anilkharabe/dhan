#!/usr/bin/env python3
"""
Diagnostic: Check why signals aren't being generated
Run this to see what conditions are failing
"""

import sys
import os

# Ensure backend is on path when run as python backend/diagnose_signals.py from project root
_backend = os.path.dirname(os.path.abspath(__file__))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from datetime import datetime
from data_manager import data_manager
from strategy import strategy
from indicators import Indicators
import config

print("=" * 80)
print("SIGNAL DIAGNOSTIC - Checking Current Conditions")
print("=" * 80)

# Get Nifty price and strikes
nifty_price = data_manager.get_nifty_price()
print(f"\nNifty Price: ₹{nifty_price:.2f}")

expiry = data_manager.get_expiry_date(datetime.now(), config.NIFTY_EXPIRY_DAY)
print(f"Expiry: {expiry}")

is_expiry_today = (datetime.now().strftime('%Y-%m-%d') == expiry)
strikes = data_manager.determine_atm_strikes(
    nifty_price,
    config.NIFTY_STRIKE_INTERVAL,
    is_expiry_day=is_expiry_today
)
call_strike = strikes['call']
put_strike = strikes['put']
print(f"Call Strike: {call_strike}")
print(f"Put Strike: {put_strike}")
if is_expiry_today:
    print("(Using ITM strikes - expiry day)")

# Test CALL option
print("\n" + "=" * 80)
print(f"TESTING CALL {call_strike}")
print("=" * 80)

call_df = data_manager.get_option_data_with_indicators("CE", call_strike, expiry)

if call_df is not None and len(call_df) >= 20:
    print(f"✅ Got {len(call_df)} candles")
    
    # Check latest values
    latest = call_df.iloc[-1]
    print(f"\nLatest Candle Data:")
    print(f"  Close: ₹{latest['close']:.2f}")
    print(f"  VWAP: ₹{latest.get('vwap', 0):.2f}")
    print(f"  RSI: {latest.get('rsi', 0):.1f}")
    print(f"  Volume: {int(latest['volume']):,}")
    print(f"  Volume SMA: {int(latest.get('volume_sma', 0)):,}")
    print(f"  OI: {int(latest['oi']):,}")
    print(f"  OI SMA: {int(latest.get('oi_sma', 0)):,}")
    
    # Check conditions
    conditions = Indicators.check_entry_conditions(call_df, "CALL")
    
    print(f"\nEntry Conditions:")
    print(f"  ✅ Price < VWAP: {conditions.get('price_below_vwap', False)} ({latest['close']:.2f} < {latest.get('vwap', 0):.2f})")
    print(f"  ✅ RSI < {config.RSI_THRESHOLD}: {conditions.get('rsi_below_40', False)} (RSI: {latest.get('rsi', 0):.1f})")
    print(f"  ✅ OI > SMA: {conditions.get('oi_above_sma', False)} ({int(latest['oi']):,} > {int(latest.get('oi_sma', 0)):,})")
    
    if config.VOLUME_CONFIRMATION_ENABLED:
        volume = latest['volume']
        volume_sma = latest.get('volume_sma', 0)
        volume_ratio = (volume / volume_sma * 100) if volume_sma > 0 else 0
        print(f"  ✅ Volume ≥ {config.VOLUME_THRESHOLD_PERCENT}%: {conditions.get('volume_confirmed', False)} ({int(volume):,} = {volume_ratio:.0f}% of avg)")
    
    print(f"\n{'🎯 SIGNAL DETECTED!' if conditions.get('entry_signal') else '❌ NO SIGNAL'}")
    
    if not conditions.get('entry_signal'):
        print("\nFailed conditions:")
        if not conditions.get('price_below_vwap'):
            print("  • Price NOT below VWAP")
        if not conditions.get('rsi_below_40'):
            print(f"  • RSI above {config.RSI_THRESHOLD}")
        if not conditions.get('oi_above_sma'):
            print("  • OI NOT above SMA")
        if config.VOLUME_CONFIRMATION_ENABLED and not conditions.get('volume_confirmed'):
            print(f"  • Volume below {config.VOLUME_THRESHOLD_PERCENT}% threshold")
else:
    print(f"❌ Insufficient data: {len(call_df) if call_df is not None else 0} candles (need 20)")

# Test PUT option
print("\n" + "=" * 80)
print(f"TESTING PUT {put_strike}")
print("=" * 80)

put_df = data_manager.get_option_data_with_indicators("PE", put_strike, expiry)

if put_df is not None and len(put_df) >= 20:
    print(f"✅ Got {len(put_df)} candles")
    
    latest = put_df.iloc[-1]
    print(f"\nLatest Candle Data:")
    print(f"  Close: ₹{latest['close']:.2f}")
    print(f"  VWAP: ₹{latest.get('vwap', 0):.2f}")
    print(f"  RSI: {latest.get('rsi', 0):.1f}")
    print(f"  Volume: {int(latest['volume']):,}")
    print(f"  Volume SMA: {int(latest.get('volume_sma', 0)):,}")
    print(f"  OI: {int(latest['oi']):,}")
    print(f"  OI SMA: {int(latest.get('oi_sma', 0)):,}")
    
    conditions = Indicators.check_entry_conditions(put_df, "PUT")
    
    print(f"\nEntry Conditions:")
    print(f"  ✅ Price < VWAP: {conditions.get('price_below_vwap', False)}")
    print(f"  ✅ RSI < {config.RSI_THRESHOLD}: {conditions.get('rsi_below_40', False)}")
    print(f"  ✅ OI > SMA: {conditions.get('oi_above_sma', False)}")
    if config.VOLUME_CONFIRMATION_ENABLED:
        volume_ratio = (latest['volume'] / latest.get('volume_sma', 1) * 100)
        print(f"  ✅ Volume ≥ {config.VOLUME_THRESHOLD_PERCENT}%: {conditions.get('volume_confirmed', False)} ({volume_ratio:.0f}%)")
    
    print(f"\n{'🎯 SIGNAL DETECTED!' if conditions.get('entry_signal') else '❌ NO SIGNAL'}")
else:
    print(f"❌ Insufficient data")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)