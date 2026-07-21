"""
Chart Generation Module
Creates detailed charts for each buy signal for visual confirmation
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict
import os

import config
import logger

class SignalChart:
    """Generate charts for trade signals"""
    
    def __init__(self):
        self.fig_size = config.CHART_FIGSIZE
        self.dpi = config.CHART_DPI
    
    def create_signal_chart(
        self,
        df: pd.DataFrame,
        option_type: str,
        strike: int,
        entry_price: float,
        stop_loss: float,
        entry_time: datetime,
        conditions: Dict,
        expiry_date: str
    ) -> str:
        """
        Create a comprehensive chart for a trade signal
        
        Args:
            df: DataFrame with OHLCV data and indicators
            option_type: "CALL" or "PUT"
            strike: Strike price
            entry_price: Entry price of the option
            stop_loss: Stop loss level
            entry_time: Time of entry
            conditions: Dictionary with entry conditions
            expiry_date: Expiry date of the option
        
        Returns:
            Path to saved chart image
        """
        try:
            # Limit to last N candles for clarity
            display_candles = min(config.CHART_CANDLES_TO_DISPLAY, len(df))
            df_display = df.tail(display_candles).copy()
            
            # NOTE ON TIMEZONES:
            # Upstox V3 intraday API already returns timestamps aligned to the
            # account's/local timezone for intraday data. Converting them again
            # (e.g. assuming UTC and adding +5:30) causes the chart x‑axis to
            # drift several hours away from the actual entry time (e.g.
            # showing ~07:30 when the real entry was ~13:04).
            #
            # To keep the chart aligned with the actual trade/entry timestamps,
            # we intentionally DO NOT apply any timezone conversion here and
            # simply use the timestamps as returned by the API.
            df_display.index = pd.to_datetime(df_display.index)
            
            # Create figure with subplots
            fig = plt.figure(figsize=self.fig_size)
            gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.3)
            
            ax1 = fig.add_subplot(gs[0])  # Price + VWAP
            ax2 = fig.add_subplot(gs[1], sharex=ax1)  # RSI
            ax3 = fig.add_subplot(gs[2], sharex=ax1)  # OI
            ax4 = fig.add_subplot(gs[3], sharex=ax1)  # Volume
            
            # ============================================================
            # Plot 1: Price Candlesticks + VWAP
            # ============================================================
            
            self._plot_candlesticks(ax1, df_display)
            
            # Plot VWAP
            if 'vwap' in df_display.columns:
                ax1.plot(df_display.index, df_display['vwap'], 
                        label='VWAP', color='orange', linewidth=2, alpha=0.8)
            
            # Mark entry point
            entry_idx = df_display.index[-1]  # Latest candle
            ax1.scatter(entry_idx, entry_price, color='green' if option_type == "CALL" else 'red',
                       s=200, marker='^', zorder=5, label=f'Entry: ₹{entry_price:.2f}')
            
            # Mark stop loss
            ax1.axhline(y=stop_loss, color='red', linestyle='--', linewidth=1.5,
                       alpha=0.7, label=f'SL: ₹{stop_loss:.2f}')
            
            # Add title and labels
            color = 'green' if option_type == "CALL" else 'red'
            ax1.set_title(
                f'{option_type} {strike} {expiry_date} - Entry Signal\n'
                f'Entry Time: {entry_time.strftime("%H:%M:%S")} | Entry Price: ₹{entry_price:.2f}',
                fontsize=14, fontweight='bold', color=color
            )
            ax1.set_ylabel('Option Price (₹)', fontsize=11, fontweight='bold')
            ax1.legend(loc='upper left', fontsize=9)
            ax1.grid(True, alpha=0.3)
            
            # ============================================================
            # Plot 2: RSI
            # ============================================================
            
            if 'rsi' in df_display.columns:
                ax2.plot(df_display.index, df_display['rsi'], 
                        label='RSI(14)', color='purple', linewidth=1.5)
                
                # RSI threshold lines
                ax2.axhline(y=60, color='green', linestyle='--', linewidth=1, alpha=0.5)
                ax2.axhline(y=40, color='red', linestyle='--', linewidth=1, alpha=0.5)
                ax2.axhline(y=50, color='gray', linestyle=':', linewidth=0.5, alpha=0.5)
                
                # Highlight overbought/oversold zones
                ax2.fill_between(df_display.index, 60, 100, alpha=0.1, color='green')
                ax2.fill_between(df_display.index, 0, 40, alpha=0.1, color='red')
                
                # Mark current RSI
                current_rsi = df_display['rsi'].iloc[-1]
                ax2.scatter(entry_idx, current_rsi, color='blue', s=100, zorder=5)
                ax2.text(entry_idx, current_rsi + 5, f'{current_rsi:.1f}', 
                        ha='center', fontsize=9, fontweight='bold')
            
            ax2.set_ylabel('RSI', fontsize=11, fontweight='bold')
            ax2.set_ylim(0, 100)
            ax2.legend(loc='upper left', fontsize=9)
            ax2.grid(True, alpha=0.3)
            
            # ============================================================
            # Plot 3: OI and OI SMA
            # ============================================================
            
            if 'oi' in df_display.columns:
                # Calculate dynamic bar width
                bar_width = self._calculate_bar_width(df_display)
                
                # Plot OI as bars
                ax3.bar(df_display.index, df_display['oi'], 
                       label='OI', color='steelblue', alpha=0.6, width=bar_width)
                
                # Plot OI SMA
                if 'oi_sma' in df_display.columns:
                    ax3.plot(df_display.index, df_display['oi_sma'], 
                            label='OI SMA(20)', color='red', linewidth=2)
                    
                    # Highlight crossover
                    current_oi = df_display['oi'].iloc[-1]
                    current_oi_sma = df_display['oi_sma'].iloc[-1]
                    
                    if current_oi < current_oi_sma:
                        ax3.scatter(entry_idx, current_oi, color='green', s=100, zorder=5)
                        ax3.text(entry_idx, current_oi, 'OI < SMA ✓', 
                                ha='center', va='bottom', fontsize=8, 
                                fontweight='bold', color='green')
            
            ax3.set_ylabel('Open Interest', fontsize=11, fontweight='bold')
            ax3.legend(loc='upper left', fontsize=9)
            ax3.grid(True, alpha=0.3)
            ax3.ticklabel_format(style='plain', axis='y')
            
            # ============================================================
            # Plot 4: Volume
            # ============================================================
            
            if 'volume' in df_display.columns:
                # Calculate dynamic bar width
                bar_width = self._calculate_bar_width(df_display)
                
                colors = ['green' if df_display['close'].iloc[i] >= df_display['open'].iloc[i] 
                         else 'red' for i in range(len(df_display))]
                ax4.bar(df_display.index, df_display['volume'], 
                       label='Volume', color=colors, alpha=0.6, width=bar_width)
            
            ax4.set_ylabel('Volume', fontsize=11, fontweight='bold')
            ax4.set_xlabel('Time', fontsize=11, fontweight='bold')
            ax4.legend(loc='upper left', fontsize=9)
            ax4.grid(True, alpha=0.3)
            
            # ============================================================
            # Format x-axis
            # ============================================================
            
            ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            plt.setp(ax1.get_xticklabels(), visible=False)
            plt.setp(ax2.get_xticklabels(), visible=False)
            plt.setp(ax3.get_xticklabels(), visible=False)
            
            # ============================================================
            # Add conditions summary box
            # ============================================================
            
            conditions_text = (
                f"Entry Conditions:\n"
                f"✓ Price < VWAP: {conditions.get('price_below_vwap', False)}\n"
                f"✓ RSI < 40: {conditions.get('rsi_below_40', False)}\n"
                f"✓ OI > SMA: {conditions.get('oi_above_sma', False)}\n\n"
                f"Values:\n"
                f"Close: ₹{conditions.get('close', 0):.2f}\n"
                f"VWAP: ₹{conditions.get('vwap', 0):.2f}\n"
                f"RSI: {conditions.get('rsi', 0):.1f}\n"
                f"OI: {conditions.get('oi', 0):,.0f}\n"
                f"OI SMA: {conditions.get('oi_sma', 0):,.0f}"
            )
            
            props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
            ax1.text(0.02, 0.98, conditions_text, transform=ax1.transAxes,
                    fontsize=9, verticalalignment='top', bbox=props, family='monospace')
            
            # ============================================================
            # Save chart
            # ============================================================
            
            # Generate filename
            timestamp_str = entry_time.strftime("%H-%M-%S")
            date_str = entry_time.strftime("%Y-%m-%d")
            filename = f"{option_type}_{strike}_{timestamp_str}.png"
            
            chart_dir = config.get_chart_directory(date_str)
            filepath = os.path.join(chart_dir, filename)
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)
            
            logger.info(f"Chart saved: {filepath}")
            return filepath
        
        except Exception as e:
            logger.error(f"Error creating signal chart: {str(e)}")
            return ""
    
    def _calculate_bar_width(self, df: pd.DataFrame) -> pd.Timedelta:
        """
        Calculate optimal bar width based on datetime index
        
        Args:
            df: DataFrame with datetime index
        
        Returns:
            Width as pandas Timedelta (80% of interval for proper spacing)
        """
        if len(df) > 1:
            # Calculate width as 80% of the time interval between consecutive points
            width = (df.index[1] - df.index[0]) * 0.8
        else:
            # Fallback for single data point (assume 3-minute candles)
            width = pd.Timedelta(minutes=2.4)
        
        return width
    
    def _plot_candlesticks(self, ax, df: pd.DataFrame):
        """Plot candlestick chart"""
        
        # Calculate candle widths using helper method
        width = self._calculate_bar_width(df)
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            timestamp = df.index[idx]
            
            open_price = row['open']
            close_price = row['close']
            high_price = row['high']
            low_price = row['low']
            
            # Determine color
            color = 'green' if close_price >= open_price else 'red'
            
            # Plot high-low line
            ax.plot([timestamp, timestamp], [low_price, high_price],
                   color=color, linewidth=1, solid_capstyle='round')
            
            # Plot open-close rectangle
            height = abs(close_price - open_price)
            bottom = min(open_price, close_price)
            
            rect = Rectangle((timestamp - width/2, bottom), width, height,
                           facecolor=color, edgecolor=color, alpha=0.8)
            ax.add_patch(rect)
    
    def create_daily_summary_chart(
        self,
        trades: list,
        date_str: str
    ) -> str:
        """
        Create end-of-day summary chart with all trades
        
        Args:
            trades: List of trade dictionaries
            date_str: Date string for the chart
        
        Returns:
            Path to saved chart
        """
        try:
            if not trades:
                logger.warning("No trades to create summary chart")
                return ""
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
            
            # ============================================================
            # Plot 1: Trade Timeline
            # ============================================================
            
            call_trades = [t for t in trades if t['type'] == 'CALL']
            put_trades = [t for t in trades if t['type'] == 'PUT']
            
            # Helper to safely convert P&L values (handles None / NaN / bad types)
            def _safe_pnl(value) -> float:
                try:
                    if value is None or (isinstance(value, float) and np.isnan(value)):
                        return 0.0
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
            
            # Plot CALL trades
            for i, trade in enumerate(call_trades):
                entry_time = pd.to_datetime(trade['entry_time'])
                exit_time = pd.to_datetime(trade['exit_time']) if trade.get('exit_time') else None
                pnl = _safe_pnl(trade.get('pnl', 0))
                
                color = 'green' if pnl >= 0 else 'red'
                ax1.scatter(entry_time, trade['entry_price'], color='blue', s=100, marker='^')
                if exit_time:
                    ax1.scatter(exit_time, trade['exit_price'], color=color, s=100, marker='v')
                    ax1.plot([entry_time, exit_time], 
                            [trade['entry_price'], trade['exit_price']], 
                            color=color, linewidth=2, alpha=0.6)
            
            # Plot PUT trades
            for i, trade in enumerate(put_trades):
                entry_time = pd.to_datetime(trade['entry_time'])
                exit_time = pd.to_datetime(trade['exit_time']) if trade.get('exit_time') else None
                pnl = _safe_pnl(trade.get('pnl', 0))
                
                color = 'green' if pnl >= 0 else 'red'
                ax1.scatter(entry_time, trade['entry_price'], color='orange', s=100, marker='^')
                if exit_time:
                    ax1.scatter(exit_time, trade['exit_price'], color=color, s=100, marker='v')
                    ax1.plot([entry_time, exit_time], 
                            [trade['entry_price'], trade['exit_price']], 
                            color=color, linewidth=2, alpha=0.6)
            
            ax1.set_title(f'Daily Trade Summary - {date_str}', fontsize=14, fontweight='bold')
            ax1.set_ylabel('Option Price (₹)', fontsize=11)
            ax1.grid(True, alpha=0.3)
            ax1.legend(['CALL Entry', 'PUT Entry', 'Winning Exit', 'Losing Exit'])
            
            # ============================================================
            # Plot 2: P&L Bar Chart
            # ============================================================
            
            trade_labels = [f"{t['type']} {t['strike']}\n{pd.to_datetime(t['entry_time']).strftime('%H:%M')}" 
                           for t in trades]
            pnls = [_safe_pnl(t.get('pnl', 0)) for t in trades]
            colors_pnl = ['green' if pnl >= 0 else 'red' for pnl in pnls]
            
            ax2.bar(range(len(trades)), pnls, color=colors_pnl, alpha=0.7)
            ax2.axhline(y=0, color='black', linewidth=1)
            ax2.set_xticks(range(len(trades)))
            ax2.set_xticklabels(trade_labels, rotation=45, ha='right')
            ax2.set_ylabel('P&L (₹)', fontsize=11)
            ax2.set_title('Trade-wise P&L', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, axis='y')
            
            # Add total P&L
            total_pnl = sum(pnls)
            pnl_text = f"Total P&L: {'+ ' if total_pnl >= 0 else ''}₹{total_pnl:.2f}"
            ax2.text(0.98, 0.98, pnl_text, transform=ax2.transAxes,
                    fontsize=12, fontweight='bold', 
                    color='green' if total_pnl >= 0 else 'red',
                    verticalalignment='top', horizontalalignment='right',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            # ============================================================
            # Save chart
            # ============================================================
            
            filename = f"daily_summary_{date_str}.png"
            chart_dir = config.get_chart_directory(date_str)
            filepath = os.path.join(chart_dir, filename)
            
            plt.tight_layout()
            plt.savefig(filepath, dpi=self.dpi, bbox_inches='tight')
            plt.close(fig)
            
            logger.info(f"Daily summary chart saved: {filepath}")
            return filepath
        
        except Exception as e:
            logger.error(f"Error creating daily summary chart: {str(e)}")
            return ""


# Global chart generator instance
chart_generator = SignalChart()

if __name__ == "__main__":
    print("Chart module loaded successfully")
    print("Test chart generation with real trading data")
