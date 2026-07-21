# 📊 OI-Based Nifty & Sensex Options Trading Strategy

## Complete Documentation & Architecture Guide

> **Proprietary & Confidential – Not for Public Use**  
> This document and the underlying trading strategy are the exclusive property of the owner.  
> Unauthorized copying, distribution, disclosure, or use in any form is strictly prohibited.

---

# Table of Contents

1. [Strategy Overview](#strategy-overview)
2. [Trading Philosophy](#trading-philosophy)
3. [System Architecture](#system-architecture)
4. [Entry Strategy](#entry-strategy)
5. [Exit Strategy](#exit-strategy)
6. [Risk Management](#risk-management)
7. [Technical Implementation](#technical-implementation)
8. [Performance Analysis](#performance-analysis)
9. [Backtesting Framework](#backtesting-framework)
10. [Troubleshooting Guide](#troubleshooting-guide)

---

# 1. Strategy Overview

## 1.1 Core Concept

This is an **Open Interest (OI) based mean reversion strategy** for index options (Nifty & Sensex) that identifies institutional money flow through OI analysis combined with technical indicators.

### Key Principle:
**"When Open Interest is declining while price is rising, institutions are EXITING positions - we fade the move"**

### Strategy Type:
- **Style:** Contrarian / Mean Reversion
- **Timeframe:** Intraday (3-minute candles)
- **Holding Period:** Minutes to hours
- **Risk Profile:** Medium (defined stop loss)

---

## 1.2 Why This Strategy Works

### Market Inefficiency Exploited:
Retail traders chase price momentum without understanding institutional positioning. When OI decreases during price rallies, it signals:

1. **Smart money is reducing exposure** (closing winning positions)
2. **The move is losing steam** (new positions not being added)
3. **Mean reversion opportunity** (overextension likely to reverse)

### Statistical Edge:
- Options near ATM (At The Money) have highest liquidity
- 3-minute timeframe captures intraday momentum shifts
- OI divergence from price creates predictable reversals
- Stop loss at t-2 candle low protects from runaway losses

---

# 2. Trading Philosophy

## 2.1 Core Beliefs

### 1. **Follow Institutional Money**
> "Retail traders move price, institutions move markets"

We track where big money (institutions, hedge funds, FIIs) are positioning through Open Interest analysis.

### 2. **Divergence is Opportunity**
When price and OI move in opposite directions:
- Price ↑ + OI ↓ = **Short opportunity** (institutions exiting longs)
- Price ↓ + OI ↑ = **Long opportunity** (institutions building shorts to cover)

### 3. **Mean Reversion Over Momentum**
Index options near ATM tend to revert to VWAP. Extreme moves create rubber-band effects.

### 4. **Risk-First Approach**
Every trade has a predefined stop loss BEFORE entry. We protect capital first, make profits second.

---

## 2.2 Market Structure Understanding

### Open Interest Dynamics:

**What is Open Interest?**
- Total number of outstanding option contracts
- Represents institutional positioning
- Unlike volume (which resets daily), OI shows cumulative positioning

**OI Interpretation:**

| Price Movement | OI Movement | Interpretation | Action |
|----------------|-------------|----------------|--------|
| ↑ Rising | ↑ Rising | Strong bullish (new longs) | Stay out |
| ↑ Rising | ↓ Falling | Weak rally (short covering) | **BUY PUT** |
| ↓ Falling | ↑ Rising | Strong bearish (new shorts) | Stay out |
| ↓ Falling | ↓ Falling | Weak fall (long unwinding) | **BUY CALL** |

**Our Strategy Focuses On:**
- Price ↑ + OI ↓ situations for **PUT entries**
- Price ↓ + OI ↑ situations for **CALL entries** (less common)

---

# 3. System Architecture

## 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING SYSTEM CORE                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Data Layer   │  │ Strategy Layer│  │ Execution     │
│               │  │               │  │ Layer         │
├───────────────┤  ├───────────────┤  ├───────────────┤
│ - Upstox API  │  │ - Signal      │  │ - Order Mgmt  │
│ - Yahoo Fin   │  │   Detection   │  │ - Position    │
│ - MongoDB     │  │ - Indicators  │  │   Tracking    │
│ - Cache       │  │ - Risk Calc   │  │ - Stop Loss   │
└───────────────┘  └───────────────┘  └───────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Notification Layer   │
                ├───────────────────────┤
                │ - Telegram Alerts     │
                │ - Charts Generation   │
                │ - Trade Logs          │
                └───────────────────────┘
```

---

## 3.2 Component Architecture

### 3.2.1 Data Management Layer

**Purpose:** Fetch, cache, and process market data

**Components:**

```python
data_manager.py
├── get_nifty_price()          # Yahoo Finance → Nifty spot
├── get_sensex_price()         # Yahoo Finance → Sensex spot
├── determine_atm_strikes()    # Calculate ATM strikes
├── get_expiry_date()          # Find next expiry (Tue/Thu)
├── get_option_data()          # Fetch option OHLCV
├── get_combined_data()        # Current + Previous day candles
└── calculate_indicators()     # VWAP, RSI, OI SMA
```

**Data Flow:**

```
1. Market Opens (9:15 AM)
   ↓
2. Fetch Nifty Spot Price (Yahoo Finance)
   ↓
3. Calculate ATM Strikes (round to nearest 50/100)
   ↓
4. Find Instrument Keys (from Upstox master file)
   ↓
5. Fetch Historical Candles (3-min OHLCV + OI)
   ↓
6. Calculate Indicators (VWAP, RSI, OI SMA)
   ↓
7. Cache Data (reduce API calls)
   ↓
8. Return to Strategy Layer
```

**Caching Strategy:**
```python
# Reduces API calls by 50-75%
cache = {
    instrument_key: (timestamp, DataFrame),
    # Only re-fetch if >2:45 old
}
```

---

### 3.2.2 Strategy Layer

**Purpose:** Detect trading signals based on rules

**Components:**

```python
strategy.py
├── scan_for_signals()         # Main scanner
├── check_entry_conditions()   # 4 conditions check
├── calculate_stop_loss()      # t-2 candle low
└── validate_trading_day()     # Mon/Tue/Fri for Nifty

indicators.py
├── calculate_vwap()           # Volume-weighted avg price
├── calculate_rsi()            # Relative Strength Index
├── calculate_oi_sma()         # Open Interest SMA(20)
└── calculate_volume_sma()     # Volume SMA(20)
```

**Signal Detection Logic:**

```python
def check_entry_signal(df, option_type):
    """
    4 Conditions must ALL be TRUE:
    """
    latest = df.iloc[-1]
    
    # Condition 1: Price above VWAP (momentum exists)
    price_above_vwap = latest['close'] > latest['vwap']
    
    # Condition 2: RSI > 60 (overbought territory)
    rsi_bullish = latest['rsi'] > 60
    
    # Condition 3: OI < OI SMA (institutions exiting)
    oi_declining = latest['oi'] < latest['oi_sma']
    
    # Condition 4: Volume confirmation (disabled by default)
    volume_confirmed = True  # or check if volume > 120% of avg
    
    # ALL must be true
    signal = (price_above_vwap and 
              rsi_bullish and 
              oi_declining and 
              volume_confirmed)
    
    return signal
```

---

### 3.2.3 Execution Layer

**Purpose:** Execute trades and manage positions

**Components:**

```python
order_manager.py
├── place_buy_order()          # Entry execution
├── place_sell_order()         # Exit execution
├── check_stop_loss()          # Monitor SL every 30sec
├── close_all_positions()      # EOD square-off
└── get_position_summary()     # Position tracking

trade_tracker.py
├── log_trade()                # Record in Excel/CSV
├── update_exit()              # Update P&L
├── get_summary()              # Daily stats
└── generate_report()          # Performance analysis
```

**Position Management:**

```python
positions = {
    'nifty': {
        'call': {
            'strike': 25500,
            'entry_price': 148.50,
            'stop_loss': 105.20,
            'lot_size': 25,
            'entry_time': '10:15:00'
        },
        'put': None  # No position
    },
    'sensex': {
        'call': None,
        'put': {
            'strike': 82800,
            'entry_price': 420.30,
            'stop_loss': 298.50,
            'lot_size': 20,
            'entry_time': '11:24:00'
        }
    }
}

# Max Positions: 4 total (2 Nifty + 2 Sensex)
```

---

### 3.2.4 Notification Layer

**Purpose:** Alert user and maintain logs

**Components:**

```python
telegram_notifier.py
├── send_system_start()        # System online notification
├── send_trade_entry()         # Entry alert with conditions
├── send_trade_exit()          # Exit alert with P&L
├── send_stop_loss_hit()       # SL alert
├── send_daily_summary()       # EOD report
└── send_error()               # Error alerts

charts.py
├── create_signal_chart()      # Entry chart with indicators
├── create_daily_summary()     # Daily P&L chart
└── add_annotations()          # Mark entry/exit/SL
```

**Telegram Message Format:**

```
📈 TRADE ENTRY - NIFTY PUT 📈

Index: NIFTY
Strike: 25550
Entry Price: ₹96.00
Stop Loss: ₹68.50
Lot Size: 25
Time: 10:15:04

Conditions:
• Price > VWAP: ✅ (96.00 > 86.89)
• RSI > 60: ✅ (62.8)
• OI < SMA: ✅ (7.3M < 6.3M)
• Volume confirmed: ✅
```

---

## 3.3 Data Flow Diagram

### Complete Trade Lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. MARKET OPEN (9:15 AM)                                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. INITIALIZATION (9:15 - 10:00 AM)                         │
├─────────────────────────────────────────────────────────────┤
│ • Fetch Nifty/Sensex spot prices (Yahoo Finance)            │
│ • Calculate ATM strikes (round to 50/100)                   │
│ • Get expiry dates (Tue for Nifty, Thu for Sensex)         │
│ • Download instrument master (NSE + BSE)                    │
│ • Find instrument keys for options                          │
│ • Wait for 20 candles (60 minutes of data)                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. SCANNING LOOP (Every 3 minutes: 10:15 AM - 3:15 PM)     │
├─────────────────────────────────────────────────────────────┤
│ For each index (Nifty, Sensex):                            │
│   ├─ Check if trading day (Mon/Tue/Fri or Wed/Thu)        │
│   ├─ Fetch latest candles (3-min OHLCV + OI)              │
│   ├─ Calculate indicators (VWAP, RSI, OI SMA)             │
│   ├─ Check 4 entry conditions                              │
│   ├─ If signal: Calculate stop loss (t-2 low)             │
│   └─ If all pass: Execute trade                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. POSITION MONITORING (Every 30 seconds)                   │
├─────────────────────────────────────────────────────────────┤
│ For each open position:                                     │
│   ├─ Fetch current price                                   │
│   ├─ Compare with stop loss                                │
│   ├─ If price <= SL: Exit position                         │
│   └─ Log to MongoDB, Excel, Telegram                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. END OF DAY (3:15 PM)                                     │
├─────────────────────────────────────────────────────────────┤
│ • Square off all open positions                             │
│ • Calculate daily P&L                                       │
│ • Generate charts and reports                               │
│ • Send Telegram summary                                     │
│ • Save trades to Excel/CSV                                  │
│ • Store data in MongoDB                                     │
└─────────────────────────────────────────────────────────────┘
```

---

# 4. Entry Strategy

## 4.1 The 4-Condition Filter

Every trade must pass ALL 4 conditions:

### **Condition 1: Price > VWAP** (Momentum Confirmation)

**What:** Option price must be trading above its VWAP

**Why:** Ensures we're entering during an upward move (for PUT entries)

**Calculation:**
```python
VWAP = Σ(Price × Volume) / Σ(Volume)
```

**Example:**
```
Current Price: ₹96.00
VWAP: ₹86.89
✅ Pass (96.00 > 86.89)
```

**Rationale:** We want to fade strong moves, not weak ones. VWAP ensures there's actual momentum to reverse.

---

### **Condition 2: RSI > 60** (Overbought Territory)

**What:** 14-period RSI must be above 60

**Why:** Indicates overbought conditions ripe for reversal

**Calculation:**
```python
RSI = 100 - (100 / (1 + RS))
where RS = Average Gain / Average Loss over 14 periods
```

**Thresholds:**
- RSI > 70 = Extremely overbought
- RSI > 60 = Overbought (our threshold)
- RSI = 50 = Neutral
- RSI < 40 = Oversold

**Example:**
```
Current RSI: 62.8
Threshold: 60
✅ Pass (62.8 > 60)
```

**Rationale:** RSI > 60 means retail is piling in. Combined with declining OI, this is a classic fade setup.

---

### **Condition 3: OI < OI SMA** (Institutional Exit Signal)

**What:** Current Open Interest must be below its 20-period SMA

**Why:** THIS IS THE KEY SIGNAL - Institutions are reducing positions

**Calculation:**
```python
OI_SMA = Average OI over last 20 candles (60 minutes)

if OI < OI_SMA:
    # Institutions closing positions
    # Move is weak, likely to reverse
```

**Example:**
```
Current OI: 7,286,565 contracts
OI SMA: 6,346,369 contracts
❌ Fail (OI > OI_SMA - institutions adding, not exiting)
```

**What declining OI means:**
- Put OI declining + Price rising = Short covering (weak rally)
- Call OI declining + Price falling = Long unwinding (weak selloff)

**Rationale:** When OI falls during price moves, smart money is EXITING. We fade the move.

---

### **Condition 4: Volume Confirmation** (Optional)

**What:** Current volume must be ≥120% of 20-period volume SMA

**Why:** Ensures adequate liquidity and interest

**Calculation:**
```python
Volume_SMA = Average volume over 20 candles
Threshold = Volume_SMA × 1.20

if Current_Volume >= Threshold:
    volume_confirmed = True
```

**Example:**
```
Current Volume: 318,565
Volume SMA: 1,203,091
Threshold: 1,443,709 (120% of SMA)
❌ Fail (318,565 < 1,443,709)
```

**Status:** Currently **DISABLED** in config (too restrictive)

**Rationale:** High volume confirms the move has attention. However, in practice, this filter rejects too many good setups.

---

## 4.2 Strike Selection Logic

### ATM vs ITM by Day

- **Non-expiry days:** Use **ATM** (At The Money) strikes for both CE and PE.
- **Expiry day:** Use **one-interval ITM** (In The Money) to reduce theta decay and allow better price movement.
  - **Nifty expiry:** Every **Tuesday** → ITM strikes on Tuesday only.
  - **Sensex expiry:** Every **Thursday** → ITM strikes on Thursday only.

On expiry day:
- **CALL:** One interval **below** ATM (e.g. spot 24570 → ATM 24550 CE → ITM **24500 CE**).
- **PUT:** One interval **above** ATM (e.g. spot 24570 → ATM 24600 PE → ITM **24650 PE**).

Controlled by config: `USE_ITM_ON_EXPIRY_DAY = True` (set to `False` to always use ATM).

### ATM (At The Money) Strategy

**Why ATM on non-expiry?**
1. **Highest liquidity** - Tightest bid-ask spreads
2. **Fastest movement** - High delta, responds quickly to spot moves
3. **Best risk/reward** - Not too cheap (won't move), not too expensive (high risk)

### **For CALL Options:**
```python
nifty_spot = 25,534
strike_interval = 50

call_strike = (nifty_spot // strike_interval) * strike_interval
# = (25534 // 50) * 50
# = 510 * 50
# = 25,500 ✅
```

### **For PUT Options:**
```python
nifty_spot = 25,534
strike_interval = 50

put_strike = ((nifty_spot // strike_interval) + 1) * strike_interval
# = ((25534 // 50) + 1) * 50
# = (510 + 1) * 50
# = 511 * 50
# = 25,550 ✅
```

### **Sensex (100-point intervals):**
```python
sensex_spot = 82,864
strike_interval = 100

call_strike = (82864 // 100) * 100 = 82,800
put_strike = ((82864 // 100) + 1) * 100 = 82,900
```

---

## 4.3 Timing Strategy

### **Trading Window:**
- **Start:** 10:00 AM (after 20 candles = 60 min of data)
- **End:** 3:15 PM (square off all positions)

### **Why Wait Until 10:15 AM?**

**Reason 1: Data Requirement**
- Need 20 candles for indicators (RSI, OI SMA)
- Market opens: 9:15 AM
- 20 × 3-minute candles = 60 minutes
- First valid signal: 10:15 AM

**Reason 2: Market Stabilization**
- First hour (9:15-10:15) is volatile (news reactions, overnight gaps)
- Institutions position themselves
- By 10:15, market structure is clearer

### **Day Selection:**

**Nifty:**
- **Monday:** Fresh week, building toward Tuesday expiry
- **Tuesday:** Expiry day (highest activity)
- **Friday:** Last day before weekend, institutions adjust

**Sensex:**
- **Wednesday:** Building toward Thursday expiry
- **Thursday:** Expiry day (highest activity)

**Why not all days?**
- Avoid overtrading
- Focus on high-conviction setups near expiry
- Better risk/reward during expiry week

---

## 4.4 Entry Checklist

Before placing any trade, verify:

```
[ ] Correct trading day (Mon/Tue/Fri for Nifty, Wed/Thu for Sensex)
[ ] Within trading hours (10:00 AM - 3:15 PM)
[ ] At least 20 candles available
[ ] No existing position in same option type
[ ] All 4 conditions pass:
    [ ] Price > VWAP
    [ ] RSI > 60
    [ ] OI < OI_SMA
    [ ] (Volume confirmed - if enabled)
[ ] Stop loss calculated (t-2 candle low)
[ ] Position size within limits (max 4 total)
[ ] Paper trading mode active (if testing)
```

---

# 5. Exit Strategy

## 5.1 Stop Loss Mechanism

### **Fixed Stop Loss: t-2 Candle Low**

**What:** Stop loss is set at the low of the candle from 2 periods ago

**Why:**
- Gives room for normal price fluctuation
- Not too tight (avoid premature stops)
- Not too wide (limits max loss)
- Based on actual price action, not arbitrary %

### **Calculation:**

```python
def calculate_stop_loss(df):
    """
    Use low of t-2 candle (2 candles back)
    """
    if len(df) < 3:
        return None
    
    # t-2 candle = 3rd from last (index -3)
    stop_loss = df.iloc[-3]['low']
    
    return stop_loss
```

### **Example:**

```
Latest candles:
Index  Time      Open    High    Low     Close
-3     10:09     94.50   96.20   93.80   95.50  ← t-2 candle
-2     10:12     95.60   97.10   95.00   96.80
-1     10:15     96.90   98.50   96.30   98.10  ← Current (entry)

Entry Price: ₹98.10
Stop Loss: ₹93.80 (low of t-2 candle)
Risk: ₹4.30 per contract
```

### **Why t-2 and not t-1?**

**t-1 (previous candle):**
- ❌ Too tight - normal volatility will hit SL
- ❌ High probability of premature exit

**t-2 (two candles back):**
- ✅ Reasonable room - accommodates intraday noise
- ✅ Still protects capital - limits loss to recent range
- ✅ Based on actual support - price that held before

**t-3 or older:**
- ❌ Too wide - excessive risk per trade
- ❌ May be outdated support level

---

## 5.2 Stop Loss Monitoring

### **Frequency: Every 30 Seconds**

Unlike entry scanning (every 3 minutes), stop loss is checked every 30 seconds.

**Why?**
- Options can move fast
- 3-minute intervals too slow for risk management
- Need near real-time protection

### **Monitoring Logic:**

```python
def check_stop_loss():
    """
    Runs every 30 seconds
    """
    for position in active_positions:
        # Fetch current price
        current_price = get_current_price(position.instrument_key)
        
        # Check if stop loss hit
        if current_price <= position.stop_loss:
            # Exit immediately
            exit_position(
                position=position,
                exit_price=current_price,
                reason="STOP_LOSS"
            )
            
            # Send notification
            telegram_notifier.send_stop_loss_hit(position)
```

### **Stop Loss Hit Example:**

```
Entry: ₹98.10
Stop Loss: ₹93.80

10:15:00 - Entry at ₹98.10
10:15:30 - Price: ₹97.50 (✅ above SL)
10:16:00 - Price: ₹96.20 (✅ above SL)
10:16:30 - Price: ₹95.10 (✅ above SL)
10:17:00 - Price: ₹93.50 (❌ BELOW SL!)
          → Exit at ₹93.50
          → Loss: ₹4.60 per contract
          → Total loss: ₹4.60 × 25 = ₹115.00
```

---

## 5.3 End of Day Square-Off

### **Time: 3:15 PM Sharp**

All positions are closed at market close regardless of P&L.

**Why?**
- **No overnight risk** - Avoid gap risk
- **Capital preservation** - Sleep peacefully
- **Clean slate** - Fresh start next day
- **Avoid expiry risk** - Don't hold into expiry chaos

### **Square-Off Process:**

```python
def end_of_day_routine():
    """
    Runs at 3:15 PM
    """
    # 1. Close all positions
    for position in active_positions:
        current_price = get_current_price(position.instrument_key)
        
        exit_position(
            position=position,
            exit_price=current_price,
            reason="EOD_SQUARE_OFF"
        )
    
    # 2. Calculate daily P&L
    daily_pnl = sum(trade.pnl for trade in today_trades)
    
    # 3. Generate reports
    save_trades_to_excel()
    create_daily_summary_chart()
    
    # 4. Send Telegram summary
    send_daily_summary(daily_pnl, trades)
    
    # 5. Stop system
    system.stop()
```

### **EOD Summary Example:**

```
═══════════════════════════════════════
DAILY SUMMARY - 2026-02-13
═══════════════════════════════════════

NIFTY TRADES: 3
  Winners: 2
  Losers: 1
  P&L: +₹1,850.00

SENSEX TRADES: 2
  Winners: 1
  Losers: 1
  P&L: -₹450.00

TOTAL:
  Trades: 5
  Win Rate: 60.0%
  Net P&L: +₹1,400.00

═══════════════════════════════════════
```

---

## 5.4 Exit Scenarios Summary

| Exit Type | Trigger | Frequency | Action |
|-----------|---------|-----------|--------|
| **Stop Loss** | Price ≤ SL | Every 30 sec | Exit at market price |
| **Target** | N/A | N/A | We don't use targets |
| **EOD Square-Off** | 3:15 PM | Once daily | Exit all positions |
| **Manual Exit** | User command | On demand | Exit specified position |

**Note:** We do NOT use profit targets. Positions run until SL hit or EOD.

---

# 6. Risk Management

## 6.1 Position Sizing

### **Lot Size: 1 lot per trade**

**Nifty:** 1 lot = 25 contracts
**Sensex:** 1 lot = 20 contracts

### **Capital Requirements (Example):**

```
NIFTY PUT Entry:
Entry Price: ₹96.00
Lot Size: 25
Capital Required: ₹96 × 25 = ₹2,400

Stop Loss: ₹68.50
Max Loss: (₹96 - ₹68.50) × 25 = ₹687.50

SENSEX CALL Entry:
Entry Price: ₹420.00
Lot Size: 20
Capital Required: ₹420 × 20 = ₹8,400

Stop Loss: ₹298.50
Max Loss: (₹420 - ₹298.50) × 20 = ₹2,430.00
```

### **Maximum Exposure:**

```
Max Positions: 4 total
- 1 Nifty CALL
- 1 Nifty PUT
- 1 Sensex CALL
- 1 Sensex PUT

Typical Capital: ₹10,000 - ₹20,000
Max Risk per Position: ₹500 - ₹2,500
Max Daily Risk: ₹5,000 - ₹10,000 (all 4 SL hit)
```

---

## 6.2 Risk Per Trade

### **Formula:**

```
Risk per Trade = (Entry Price - Stop Loss) × Lot Size

Risk % = (Risk per Trade / Account Capital) × 100
```

### **Example:**

```
Account Capital: ₹100,000
Entry: ₹98.10
Stop Loss: ₹93.80
Lot Size: 25 (Nifty)

Risk = (₹98.10 - ₹93.80) × 25
     = ₹4.30 × 25
     = ₹107.50

Risk % = (₹107.50 / ₹100,000) × 100
       = 0.11%  ← Very conservative!
```

### **Maximum Risk Guidelines:**

**Conservative:** 0.5% - 1% per trade
**Moderate:** 1% - 2% per trade
**Aggressive:** 2% - 3% per trade
**Reckless:** >3% per trade (NOT recommended)

**Our Strategy:** Typically 0.1% - 1% per trade (CONSERVATIVE)

---

## 6.3 Daily Loss Limits

### **Recommended:**

```
Max Trades per Day: 8-10
Max Losses in a Row: 3

If 3 losses in a row:
→ STOP trading for the day
→ Review what went wrong
→ Fresh start tomorrow
```

### **Circuit Breaker:**

```python
def check_circuit_breaker():
    """
    Stop trading if daily loss > threshold
    """
    daily_pnl = get_daily_pnl()
    
    # Stop if down more than 5% of capital
    if daily_pnl < (account_capital * -0.05):
        logger.critical("Circuit breaker hit! Daily loss limit exceeded.")
        send_alert("Trading stopped - Daily loss limit hit")
        system.stop()
```

---

## 6.4 Position Limits

```
Maximum Positions: 4 total

Breakdown:
├── Nifty CALL: 1
├── Nifty PUT: 1
├── Sensex CALL: 1
└── Sensex PUT: 1

Rules:
✓ Can hold both CALL and PUT on same index
✓ Cannot hold 2 CALLs on same index
✓ Cannot hold 2 PUTs on same index
✓ Max exposure across all: ₹50,000 (approx)
```

---

# 7. Technical Implementation

## 7.1 Technology Stack

```
Programming Language: Python 3.12
Data Sources: Upstox API v2, Yahoo Finance
Database: MongoDB
Notifications: Telegram Bot API
Visualization: Matplotlib, Pandas
Scheduling: Schedule library
Configuration: .env (python-dotenv)
Logging: Custom logger module
```

---

## 7.2 Key Libraries

```python
# Data Processing
pandas>=2.0.0
numpy>=1.24.0

# API Integration
requests>=2.31.0
python-dotenv>=1.0.0

# Visualization
matplotlib>=3.7.0

# Excel Export
openpyxl>=3.1.0

# Database
pymongo>=4.6.0

# Scheduling
schedule>=1.2.0

# Utilities
python-dateutil>=2.8.2
```

---

## 7.3 File Structure

```
algo_trading/
├── main.py                    # Entry point, orchestration
├── config.py                  # All configuration
├── .env                       # Credentials (gitignored)
│
├── Data Layer
│   ├── upstox_client.py      # Upstox API wrapper
│   ├── data_manager.py       # Data fetching & processing
│   └── mongo_logger.py       # MongoDB persistence
│
├── Strategy Layer
│   ├── strategy.py           # Signal detection logic
│   └── indicators.py         # Technical indicators (VWAP, RSI, etc)
│
├── Execution Layer
│   ├── order_manager.py      # Position & order management
│   └── trade_tracker.py      # Trade logging & analytics
│
├── Notification Layer
│   ├── telegram_notifier.py  # Telegram alerts
│   ├── charts.py             # Chart generation
│   └── logger.py             # Console/file logging
│
├── Utilities
│   ├── generate_token.py     # Upstox token generator
│   ├── refresh_token.py      # Auto token refresh
│   └── diagnose_signals.py   # Debug tool
│
└── Data Files
    ├── trades/               # Excel/CSV trade logs
    ├── charts/               # Generated charts
    └── instruments_cache.csv # Cached instrument master
```

---

## 7.4 Execution Flow

### **Startup Sequence:**

```
1. Load .env configuration
2. Validate credentials (Upstox, Telegram)
3. Check trading day (Mon/Tue/Fri or Wed/Thu)
4. Check market hours (9:15 AM - 3:15 PM)
5. Download instrument master (NSE + BSE)
6. Fetch Nifty & Sensex spot prices
7. Calculate ATM strikes
8. Find option instrument keys
9. Wait until 10:00 AM (if early)
10. Start scanning loop
```

### **Main Loop:**

```
Every 3 minutes (10:15 AM - 3:15 PM):
├── Check current time
├── Scan Nifty (if Mon/Tue/Fri)
│   ├── Fetch CALL option data
│   ├── Calculate indicators
│   ├── Check 4 entry conditions
│   ├── If signal: Calculate SL & enter trade
│   ├── Fetch PUT option data
│   └── Repeat process
├── Scan Sensex (if Wed/Thu)
│   └── Same process
└── Log data to MongoDB

Every 30 seconds:
└── Check stop losses for all positions

At 3:15 PM:
└── Square off all positions & generate reports
```

---

## 7.5 MongoDB Schema

### **Collections:**

**1. nifty_spot**
```javascript
{
  _id: ObjectId("..."),
  timestamp: ISODate("2026-02-13T10:15:00Z"),
  price: 25534.00,
  source: "Yahoo Finance"
}
```

**2. sensex_spot**
```javascript
{
  _id: ObjectId("..."),
  timestamp: ISODate("2026-02-13T10:15:00Z"),
  price: 82864.82,
  source: "Yahoo Finance"
}
```

**3. option_candles** (Most Important for Backtesting)
```javascript
{
  _id: ObjectId("..."),
  timestamp: ISODate("2026-02-13T10:15:00Z"),
  date: "2026-02-13",
  time: "10:15:00",
  
  // Identification
  index: "NIFTY",  // or "SENSEX"
  option_type: "PUT",  // or "CALL"
  strike: 25550,
  expiry: "2026-02-17",
  instrument_key: "NSE_FO|48219",
  
  // OHLCV (Raw Data)
  open: 95.50,
  high: 97.20,
  low: 95.00,
  close: 96.00,
  volume: 318565,  // ← Essential for backtesting
  oi: 7286565,     // ← Essential for backtesting
  
  // Calculated Indicators
  vwap: 86.89,
  rsi: 62.8,
  oi_sma: 6346369,      // ← Essential for backtesting
  volume_sma: 1203091,  // ← Essential for backtesting
  
  total_candles: 20
}
```

**4. signals**
```javascript
{
  _id: ObjectId("..."),
  timestamp: ISODate("2026-02-13T10:15:00Z"),
  
  // Signal Details
  index: "NIFTY",
  option_type: "PUT",
  strike: 25550,
  signal_detected: true,
  
  // Conditions (All 4)
  price_above_vwap: true,
  rsi_above_threshold: true,
  oi_below_sma: true,
  volume_confirmed: true,
  
  // Candle Data
  close: 96.00,
  vwap: 86.89,
  rsi: 62.8,
  oi: 7286565,
  oi_sma: 6346369,
  volume: 318565,
  volume_sma: 1203091,
  
  // Trade Info
  trade_taken: true,
  trade_id: 5,
  reason: ""  // If rejected, reason here
}
```

**5. trades**
```javascript
{
  _id: ObjectId("..."),
  trade_id: 5,
  
  // Entry
  entry_time: ISODate("2026-02-13T10:15:00Z"),
  index: "NIFTY",
  option_type: "PUT",
  strike: 25550,
  entry_price: 96.00,
  quantity: 1,  // Lots
  lot_size: 25,
  
  // Risk
  stop_loss: 68.50,
  
  // Exit
  exit_time: ISODate("2026-02-13T14:30:00Z"),
  exit_price: 104.50,
  exit_reason: "EOD_SQUARE_OFF",
  
  // P&L
  pnl: 212.50,  // (104.50 - 96.00) × 25
  pnl_percent: 8.85,  // 8.85% gain
  
  status: "CLOSED"
}
```

**6. system_events**
```javascript
{
  _id: ObjectId("..."),
  timestamp: ISODate("2026-02-13T09:56:48Z"),
  event_type: "SYSTEM_START",
  message: "Trading system initialized",
  mode: "PAPER_TRADING"
}
```

---

# 8. Performance Analysis

## 8.1 Expected Win Rate

Based on strategy characteristics:

**Conservative Estimate:** 55-60% win rate
**Realistic Target:** 60-65% win rate
**Optimistic:** 65-70% win rate

### **Why This Win Rate?**

**Factors Supporting Higher Win Rate:**
✅ Mean reversion strategies typically 55-65% win rate
✅ OI divergence is a strong signal
✅ ATM options have fastest movement
✅ Tight stop losses prevent large losses
✅ No overnight risk

**Factors Limiting Win Rate:**
❌ Market can remain irrational longer than expected
❌ Stop losses can be hit on whipsaws
❌ RSI can stay overbought in strong trends
❌ Not every OI decline signals reversal

---

## 8.2 Risk/Reward Profile

### **Typical Trade:**

```
Entry: ₹96.00
Stop Loss: ₹68.50
Risk: ₹27.50 (28.6% of entry)

Target: Not fixed, but expect:
- Small Win: ₹100-104 (+4-8%)
- Medium Win: ₹104-110 (+8-15%)
- Large Win: ₹110-120 (+15-25%)

Average Win: ~10-12% (₹105-108)
Average Loss: ~15-20% (hits SL)

Risk/Reward: 1:0.5 to 1:1
(Compensated by >60% win rate)
```

### **100 Trades Simulation:**

```
Assumptions:
- 60% win rate (60 wins, 40 losses)
- Avg win: +10% = +₹960 per trade
- Avg loss: -20% = -₹480 per trade

Results:
Winning trades: 60 × ₹960 = ₹57,600
Losing trades: 40 × ₹480 = -₹19,200
Net P&L: ₹38,400

Average per trade: ₹384
Return on Risk: 38,400 / (100 × 2,400) = 16%
```

---

## 8.3 Key Metrics to Track

```python
# Daily Metrics
├── Total Trades
├── Winning Trades
├── Losing Trades
├── Win Rate %
├── Total P&L
├── Average P&L per Trade
├── Max Win
├── Max Loss
├── Largest Drawdown
└── Sharpe Ratio (if enough data)

# Per-Index Breakdown
├── Nifty Win Rate
├── Sensex Win Rate
├── CALL vs PUT Performance
└── Time-of-Day Performance

# Risk Metrics
├── Max Consecutive Losses
├── Average Risk per Trade
├── Risk-Adjusted Return
└── Recovery Factor
```

---

# 9. Backtesting Framework

## 9.1 Using MongoDB Data

### **Data Collection Period:**

Run system for **60-90 days** to collect:
- 60 days × 120 scans/day = 7,200 data points
- 4 options × 7,200 = 28,800 option candles
- Enough for robust backtesting

### **Backtest Script Template:**

```python
#!/usr/bin/env python3
"""
Backtest OI Strategy on Historical MongoDB Data
"""

from pymongo import MongoClient
import pandas as pd
from datetime import datetime, timedelta

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client['nifty_algo_trading']

# Fetch historical data
start_date = datetime(2026, 1, 1)
end_date = datetime(2026, 2, 13)

candles = list(db.option_candles.find({
    'date': {
        '$gte': start_date.strftime('%Y-%m-%d'),
        '$lte': end_date.strftime('%Y-%m-%d')
    },
    'index': 'NIFTY',
    'option_type': 'PUT'
}))

# Convert to DataFrame
df = pd.DataFrame(candles)

# Backtest logic
signals = []
for i in range(20, len(df)):
    # Check conditions
    price_above_vwap = df.iloc[i]['close'] > df.iloc[i]['vwap']
    rsi_above_60 = df.iloc[i]['rsi'] > 60
    oi_below_sma = df.iloc[i]['oi'] < df.iloc[i]['oi_sma']
    
    if price_above_vwap and rsi_above_60 and oi_below_sma:
        # Calculate SL from t-2 candle
        stop_loss = df.iloc[i-2]['low']
        
        signals.append({
            'timestamp': df.iloc[i]['timestamp'],
            'entry': df.iloc[i]['close'],
            'stop_loss': stop_loss,
            'strike': df.iloc[i]['strike']
        })

# Simulate trades
trades = []
for signal in signals:
    # Find exit (SL hit or EOD)
    # Calculate P&L
    # Add to trades list
    pass

# Calculate metrics
win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades)
total_pnl = sum(t['pnl'] for t in trades)

print(f"Win Rate: {win_rate:.1%}")
print(f"Total P&L: ₹{total_pnl:,.2f}")
print(f"Avg P&L: ₹{total_pnl/len(trades):,.2f}")
```

---

## 9.2 Parameter Optimization

### **Variables to Test:**

```python
# RSI Threshold
RSI_VALUES = [55, 57.5, 60, 62.5, 65]

# OI Comparison
OI_PERIODS = [15, 20, 25, 30]

# Stop Loss
SL_CANDLES = [2, 3, 4]  # t-2, t-3, t-4

# Volume Filter
VOLUME_ENABLED = [True, False]
VOLUME_THRESHOLDS = [100, 120, 150]

# Time Filters
START_TIMES = ['10:00', '10:15', '10:30']
END_TIMES = ['14:30', '15:00', '15:15']
```

### **Optimization Loop:**

```python
best_sharpe = 0
best_params = {}

for rsi in RSI_VALUES:
    for oi_period in OI_PERIODS:
        for sl_candle in SL_CANDLES:
            # Run backtest with these params
            results = backtest(
                rsi_threshold=rsi,
                oi_sma_period=oi_period,
                sl_candle=sl_candle
            )
            
            # Calculate Sharpe ratio
            sharpe = results['sharpe_ratio']
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = {
                    'rsi': rsi,
                    'oi_period': oi_period,
                    'sl_candle': sl_candle
                }

print(f"Best Params: {best_params}")
print(f"Best Sharpe: {best_sharpe:.2f}")
```

---

# 10. Troubleshooting Guide

## 10.1 Common Issues

### **Issue 1: "Instrument not found"**

**Error:**
```
WARNING | Instrument not found: NIFTY 82800 CE 2026-02-19
```

**Cause:** Searching with wrong symbol (NIFTY instead of SENSEX)

**Solution:** Ensure `symbol` parameter is passed correctly in `scan_for_signals()`

---

### **Issue 2: "Token expired"**

**Error:**
```
ERROR | 401 - Invalid or expired token
```

**Cause:** Access token older than 18 hours

**Solution:**
```bash
python3 generate_token.py
```

---

### **Issue 3: "No signals detected all day"**

**Possible Causes:**
1. All 4 conditions too strict
2. Wrong trading day
3. Volume filter blocking trades
4. Market ranging (no strong moves)

**Solutions:**
1. Disable volume filter: `VOLUME_CONFIRMATION_ENABLED = False`
2. Lower RSI threshold to 55
3. Check logs for which condition is failing
4. Run diagnostic: `python3 diagnose_signals.py`

---

### **Issue 4: "MongoDB connection failed"**

**Error:**
```
ERROR | MongoDB connection failed
```

**Solutions:**
```bash
# Start MongoDB
sudo systemctl start mongod

# Check status
sudo systemctl status mongod

# Install if missing
sudo apt install mongodb-server
```

---

### **Issue 5: "Stop loss monitoring not working"**

**Symptoms:** Position hit SL but didn't exit

**Cause:** 30-second check job not running

**Solution:** Check schedule is running:
```python
# In main.py, verify this exists:
schedule.every(30).seconds.do(check_stop_losses_only)
```

---

## 10.2 Debug Checklist

When things aren't working:

```
[ ] Check .env file has correct credentials
[ ] Verify token is not expired (< 18 hours old)
[ ] Confirm correct trading day (Mon/Tue/Fri or Wed/Thu)
[ ] Check market hours (10:00 AM - 3:15 PM)
[ ] Verify internet connection
[ ] Check MongoDB is running
[ ] Review logs for errors
[ ] Run diagnostic script: diagnose_signals.py
[ ] Check instruments_cache.csv exists and is recent
[ ] Verify Telegram bot token and chat ID
[ ] Test with DEMO_MODE = True first
```

---

## 10.3 Performance Optimization

### **If system is slow:**

```python
# 1. Enable caching (reduce API calls)
# In data_manager.py
cache_duration = timedelta(minutes=2, seconds=45)

# 2. Reduce logging verbosity
# In config.py
LOG_OPTION_CANDLES = False  # Only on production

# 3. Use local MongoDB (not remote)
MONGODB_URI = "mongodb://localhost:27017/"

# 4. Limit chart generation
GENERATE_CHARTS = False  # Only generate on trades
```

---

# Conclusion

This strategy combines:
- **Open Interest analysis** (institutional positioning)
- **Technical indicators** (VWAP, RSI)
- **Risk management** (fixed stop loss)
- **Systematic execution** (remove emotions)

**Expected Results:**
- Win Rate: 60-65%
- Risk/Reward: 1:0.5 to 1:1
- Monthly Return: 5-15% (depends on frequency)

**Remember:**
- No strategy is perfect
- Always backtest before going live
- Start with paper trading
- Risk only what you can afford to lose
- Keep detailed logs for improvement

**Happy Trading!** 🚀
