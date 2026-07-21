"""
Logging module for Nifty Options Algo Trading
Provides structured logging to console and file
"""

import io
import logging
import sys
from datetime import datetime
from pathlib import Path
import config

# Log messages throughout this codebase use emoji (checkmarks, targets, etc.).
# Windows' default console codepage (cp1252/cp437) can't encode most of them,
# which crashes the console handler's write() and gets misreported as a
# "Logging error" for an otherwise-successful log call. sys.stdout.reconfigure()
# is unreliable for this in some hosting environments (the underlying writes can
# still go through the original codec) - wrapping the raw buffer in a fresh UTF-8
# TextIOWrapper is the version that's actually been confirmed to work here.
def _utf8_console_stream():
    try:
        return io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except (AttributeError, ValueError):
        return sys.stdout

class TradingLogger:
    """Custom logger for trading operations"""
    
    def __init__(self, name="AlgoTrading"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler
        if config.LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler(_utf8_console_stream())
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(simple_formatter)
            self.logger.addHandler(console_handler)
        
        # File handler
        if config.LOG_TO_FILE:
            log_file = config.get_log_file_path()
            # encoding must be explicit - FileHandler defaults to the OS locale
            # encoding (cp1252 on Windows), which can't hold the emoji used
            # throughout this codebase's log messages.
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message):
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message):
        """Log info message"""
        self.logger.info(message)
    
    def warning(self, message):
        """Log warning message"""
        self.logger.warning(message)
    
    def error(self, message):
        """Log error message"""
        self.logger.error(message)
    
    def critical(self, message):
        """Log critical message"""
        self.logger.critical(message)
    
    def trade_entry(self, option_type, strike, entry_price, stop_loss, timestamp=None):
        """Log trade entry"""
        if timestamp is None:
            timestamp = datetime.now()
        
        message = (
            f"TRADE ENTRY | {option_type} {strike} | "
            f"Entry: ₹{entry_price:.2f} | SL: ₹{stop_loss:.2f} | "
            f"Time: {timestamp.strftime('%H:%M:%S')}"
        )
        self.logger.info(message)
    
    def trade_exit(self, option_type, strike, entry_price, exit_price, pnl, reason, timestamp=None):
        """Log trade exit"""
        if timestamp is None:
            timestamp = datetime.now()
        
        pnl_symbol = "+" if pnl >= 0 else ""
        message = (
            f"TRADE EXIT | {option_type} {strike} | "
            f"Entry: ₹{entry_price:.2f} | Exit: ₹{exit_price:.2f} | "
            f"P&L: {pnl_symbol}₹{pnl:.2f} | Reason: {reason} | "
            f"Time: {timestamp.strftime('%H:%M:%S')}"
        )
        self.logger.info(message)
    
    def signal_detected(self, option_type, strike, conditions):
        """Log signal detection with all conditions including volume"""
        import config
        
        # Get volume info
        volume = conditions.get('volume', 0)
        volume_sma = conditions.get('volume_sma', 0)
        volume_confirmed = conditions.get('volume_confirmed', True)
        
        # Calculate volume ratio if available
        if volume_sma > 0:
            volume_ratio = (volume / volume_sma) * 100
            volume_str = f"{volume:,.0f} ({volume_ratio:.0f}% of avg)"
        else:
            volume_str = f"{volume:,.0f}"
        
        message = (
            f"🎯 SIGNAL DETECTED | {option_type} {strike}\n"
            f"   ✅ Price < VWAP: {conditions.get('price_below_vwap', False)} "
            f"({conditions.get('close', 0):.2f} < {conditions.get('vwap', 0):.2f})\n"
            f"   ✅ RSI < {config.RSI_THRESHOLD}: {conditions.get('rsi_below_40', False)} "
            f"(RSI: {conditions.get('rsi', 0):.1f})\n"
            f"   ✅ OI > SMA: {conditions.get('oi_above_sma', False)} "
            f"({conditions.get('oi', 0):,.0f} > {conditions.get('oi_sma', 0):,.0f})\n"
        )
        
        # Add volume info
        volume_emoji = "✅" if volume_confirmed else "❌"
        message += (
            f"   {volume_emoji} Volume: {volume_str} "
            f"(Threshold: {config.VOLUME_THRESHOLD_PERCENT if config.VOLUME_CONFIRMATION_ENABLED else 'N/A'}%)\n"
        )
        
        self.logger.info(message)
    
    def stop_loss_hit(self, option_type, strike, current_price, stop_loss):
        """Log stop loss hit"""
        message = (
            f"STOP LOSS HIT | {option_type} {strike} | "
            f"Current: ₹{current_price:.2f} | SL: ₹{stop_loss:.2f}"
        )
        self.logger.warning(message)
    
    def api_error(self, operation, error_message):
        """Log API errors"""
        message = f"API ERROR | Operation: {operation} | Error: {error_message}"
        self.logger.error(message)
    
    def daily_summary(self, total_trades, winning_trades, losing_trades, total_pnl):
        """Log daily summary"""
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_symbol = "+" if total_pnl >= 0 else ""
        
        message = (
            f"\n{'=' * 80}\n"
            f"DAILY SUMMARY\n"
            f"{'=' * 80}\n"
            f"Total Trades: {total_trades}\n"
            f"Winning Trades: {winning_trades}\n"
            f"Losing Trades: {losing_trades}\n"
            f"Win Rate: {win_rate:.2f}%\n"
            f"Total P&L: {pnl_symbol}₹{total_pnl:.2f}\n"
            f"{'=' * 80}"
        )
        self.logger.info(message)
    
    def system_start(self):
        """Log system start"""
        self.logger.info("=" * 80)
        self.logger.info("NIFTY OPTIONS ALGO TRADING SYSTEM STARTED")
        self.logger.info(f"Mode: {'PAPER TRADING' if config.PAPER_TRADING else 'LIVE TRADING'}")
        self.logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        self.logger.info("=" * 80)
    
    def system_stop(self):
        """Log system stop"""
        self.logger.info("=" * 80)
        self.logger.info("SYSTEM STOPPED")
        self.logger.info("=" * 80)

# Create global logger instance
logger = TradingLogger()

# Convenience functions
def debug(message):
    logger.debug(message)

def info(message):
    logger.info(message)

def warning(message):
    logger.warning(message)

def error(message):
    logger.error(message)

def critical(message):
    logger.critical(message)

if __name__ == "__main__":
    # Test logging
    logger.system_start()
    logger.info("Test info message")
    logger.warning("Test warning message")
    logger.error("Test error message")
    logger.trade_entry("CALL", 25550, 150.50, 145.00)
    logger.trade_exit("CALL", 25550, 150.50, 160.75, 10.25, "Target")
    logger.daily_summary(5, 3, 2, 125.50)
    logger.system_stop()
