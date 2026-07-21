#!/usr/bin/env python3
"""
MongoDB Volume Analysis Queries
Analyze volume confirmation impact on trading performance
"""

from pymongo import MongoClient
from datetime import datetime
import pandas as pd

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['nifty_algo_trading']

print("=" * 80)
print("VOLUME CONFIRMATION ANALYSIS")
print("=" * 80)

# Date to analyze
# NOTE: signal field names changed 2026-07-21 (entry gate flipped from RSI>60/price>VWAP/
# OI<SMA to RSI<40/price<VWAP/OI>SMA). This script's queries use the new field names below
# (price_below_vwap/rsi_below_threshold/oi_above_sma) - for dates before the cutover, swap
# in the old field names (price_above_vwap/rsi_above_threshold/oi_below_sma) instead.
date = '2026-02-10'  # Change to your trading date

# ============================================================================
# 1. SIGNALS REJECTED DUE TO LOW VOLUME
# ============================================================================

print(f"\n📊 Analysis for {date}\n")
print("-" * 80)
print("1. SIGNALS REJECTED DUE TO LOW VOLUME ONLY")
print("-" * 80)

# Find signals where all conditions met EXCEPT volume
low_volume_signals = list(db.signals.find({
    'date': date,
    'price_below_vwap': True,
    'rsi_below_threshold': True,
    'oi_above_sma': True,
    'volume_confirmed': False,  # Only volume failed
    'trade_taken': False
}))

if low_volume_signals:
    print(f"\nFound {len(low_volume_signals)} signals rejected due to low volume:\n")
    
    for signal in low_volume_signals:
        volume = signal.get('volume', 0)
        volume_sma = signal.get('volume_sma', 0)
        volume_pct = (volume / volume_sma * 100) if volume_sma > 0 else 0
        
        print(f"{signal['time']} | {signal['option_type']} {signal['strike']}")
        print(f"  Volume: {volume:,.0f} ({volume_pct:.0f}% of avg {volume_sma:,.0f})")
        print(f"  Price: ₹{signal.get('close', 0):.2f} | RSI: {signal.get('rsi', 0):.1f}")
        print()
else:
    print("✅ No signals rejected due to low volume")

# ============================================================================
# 2. SIGNALS ACCEPTED WITH STRONG VOLUME
# ============================================================================

print("-" * 80)
print("2. SIGNALS ACCEPTED WITH STRONG VOLUME")
print("-" * 80)

strong_volume_signals = list(db.signals.find({
    'date': date,
    'signal_detected': True,
    'volume_confirmed': True
}))

if strong_volume_signals:
    print(f"\nFound {len(strong_volume_signals)} signals with strong volume:\n")
    
    for signal in strong_volume_signals:
        volume = signal.get('volume', 0)
        volume_sma = signal.get('volume_sma', 0)
        volume_pct = (volume / volume_sma * 100) if volume_sma > 0 else 0
        
        print(f"{signal['time']} | {signal['option_type']} {signal['strike']}")
        print(f"  Volume: {volume:,.0f} ({volume_pct:.0f}% of avg)")
        print(f"  Trade taken: {'✅ Yes' if signal.get('trade_taken') else '❌ No'}")
        print()
else:
    print("No signals with strong volume found")

# ============================================================================
# 3. VOLUME DISTRIBUTION ANALYSIS
# ============================================================================

print("-" * 80)
print("3. VOLUME DISTRIBUTION ANALYSIS")
print("-" * 80)

all_candles = list(db.option_candles.find({'date': date}))

if all_candles:
    volumes = [c['volume'] for c in all_candles]
    volume_smas = [c.get('volume_sma', 0) for c in all_candles if c.get('volume_sma', 0) > 0]
    
    if volume_smas:
        ratios = [(c['volume'] / c.get('volume_sma', 1)) * 100 
                  for c in all_candles if c.get('volume_sma', 0) > 0]
        
        print(f"\nTotal candles: {len(all_candles)}")
        print(f"\nVolume Statistics:")
        print(f"  Average volume: {sum(volumes)/len(volumes):,.0f}")
        print(f"  Min volume: {min(volumes):,.0f}")
        print(f"  Max volume: {max(volumes):,.0f}")
        
        print(f"\nVolume vs SMA Ratios:")
        print(f"  Average ratio: {sum(ratios)/len(ratios):.0f}%")
        print(f"  Min ratio: {min(ratios):.0f}%")
        print(f"  Max ratio: {max(ratios):.0f}%")
        
        # Count candles above 120% threshold
        above_threshold = len([r for r in ratios if r >= 120])
        print(f"\nCandles above 120% threshold: {above_threshold}/{len(ratios)} ({above_threshold/len(ratios)*100:.1f}%)")

# ============================================================================
# 4. COMPARE WIN RATE: WITH vs WITHOUT VOLUME FILTER
# ============================================================================

print("\n" + "=" * 80)
print("4. IMPACT OF VOLUME FILTER ON WIN RATE")
print("=" * 80)

# Get all closed trades
closed_trades = list(db.trades.find({
    'date': date,
    'action': 'SELL',
    'pnl': {'$exists': True}
}))

if closed_trades:
    # Find corresponding entry signals
    winning_with_volume = 0
    total_with_volume = 0
    
    for trade in closed_trades:
        # Find the signal that triggered this trade
        signal = db.signals.find_one({
            'date': date,
            'trade_id': trade.get('trade_id'),
            'trade_taken': True
        })
        
        if signal:
            total_with_volume += 1
            if trade['pnl'] > 0:
                winning_with_volume += 1
            
            volume = signal.get('volume', 0)
            volume_sma = signal.get('volume_sma', 0)
            volume_ratio = (volume / volume_sma * 100) if volume_sma > 0 else 0
            
            pnl_symbol = "+" if trade['pnl'] >= 0 else ""
            print(f"\nTrade #{trade.get('trade_id')} | {trade['option_type']} {trade['strike']}")
            print(f"  Volume: {volume:,.0f} ({volume_ratio:.0f}% of avg)")
            print(f"  P&L: {pnl_symbol}₹{trade['pnl']:.2f} ({pnl_symbol}{trade.get('pnl_percent', 0):.1f}%)")
    
    if total_with_volume > 0:
        win_rate = (winning_with_volume / total_with_volume) * 100
        print(f"\n{'=' * 80}")
        print(f"WIN RATE WITH VOLUME FILTER: {win_rate:.1f}%")
        print(f"Winning trades: {winning_with_volume}/{total_with_volume}")
        print(f"{'=' * 80}")

# ============================================================================
# 5. BEST PERFORMING VOLUME RANGES
# ============================================================================

print("\n" + "=" * 80)
print("5. P&L BY VOLUME RANGE")
print("=" * 80)

if closed_trades:
    # Group trades by volume ratio ranges
    ranges = {
        '120-140%': {'trades': [], 'pnl': 0},
        '140-160%': {'trades': [], 'pnl': 0},
        '160-200%': {'trades': [], 'pnl': 0},
        '200%+': {'trades': [], 'pnl': 0}
    }
    
    for trade in closed_trades:
        signal = db.signals.find_one({
            'date': date,
            'trade_id': trade.get('trade_id')
        })
        
        if signal:
            volume = signal.get('volume', 0)
            volume_sma = signal.get('volume_sma', 0)
            if volume_sma > 0:
                ratio = (volume / volume_sma) * 100
                
                if 120 <= ratio < 140:
                    ranges['120-140%']['trades'].append(trade)
                    ranges['120-140%']['pnl'] += trade['pnl']
                elif 140 <= ratio < 160:
                    ranges['140-160%']['trades'].append(trade)
                    ranges['140-160%']['pnl'] += trade['pnl']
                elif 160 <= ratio < 200:
                    ranges['160-200%']['trades'].append(trade)
                    ranges['160-200%']['pnl'] += trade['pnl']
                elif ratio >= 200:
                    ranges['200%+']['trades'].append(trade)
                    ranges['200%+']['pnl'] += trade['pnl']
    
    print("\nP&L by volume ratio range:\n")
    for range_name, data in ranges.items():
        if data['trades']:
            count = len(data['trades'])
            pnl = data['pnl']
            avg_pnl = pnl / count
            winners = len([t for t in data['trades'] if t['pnl'] > 0])
            win_rate = (winners / count) * 100
            
            print(f"{range_name:12} | Trades: {count:2} | "
                  f"Total P&L: {pnl:+8.2f} | "
                  f"Avg: {avg_pnl:+6.2f} | "
                  f"Win Rate: {win_rate:5.1f}%")

# ============================================================================
# 6. EXPORT TO CSV FOR EXCEL ANALYSIS
# ============================================================================

print("\n" + "=" * 80)
print("6. EXPORTING DATA TO CSV")
print("=" * 80)

# Export signals to CSV
signals_df = pd.DataFrame(list(db.signals.find({'date': date})))
if not signals_df.empty:
    # Calculate volume ratio
    signals_df['volume_ratio'] = (signals_df['volume'] / signals_df['volume_sma']) * 100
    
    # Select relevant columns
    export_cols = [
        'time', 'option_type', 'strike', 'signal_detected', 'trade_taken',
        'price_below_vwap', 'rsi_below_threshold', 'oi_above_sma', 'volume_confirmed',
        'close', 'vwap', 'rsi', 'oi', 'oi_sma', 'volume', 'volume_sma', 'volume_ratio'
    ]
    
    export_df = signals_df[export_cols]
    filename = f'volume_analysis_{date}.csv'
    export_df.to_csv(filename, index=False)
    print(f"\n✅ Exported to {filename}")
    print("   Open in Excel for detailed analysis!")
else:
    print("\nNo data to export")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

# Close connection
client.close()
