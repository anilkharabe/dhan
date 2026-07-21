"""
Telegram Notification Module
Sends trading alerts and notifications via Telegram
"""

import requests
from datetime import datetime
from typing import Optional, Dict
import config
import logger

class TelegramNotifier:
    """Send notifications via Telegram bot"""
    
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = config.TELEGRAM_ENABLED and bool(self.bot_token) and bool(self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifications disabled (token or chat_id not configured)")
    
    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters for Telegram HTML parse mode
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text safe for Telegram HTML parsing
        """
        if not isinstance(text, str):
            text = str(text)
        
        # Replace HTML special characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        return text
    
    def _send_message(self, message: str, parse_mode: str = "HTML"):
        """
        Send a message to Telegram
        
        Args:
            message: Message text (with HTML tags if parse_mode is HTML)
            parse_mode: Parse mode (HTML or Markdown)
        """
        if not self.enabled:
            logger.debug(f"Telegram disabled. Would have sent: {message}")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.debug("Telegram notification sent successfully")
                return True
            else:
                logger.error(f"Failed to send Telegram notification: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {str(e)}")
            return False
    
    def send_trade_entry(
        self,
        option_type: str,
        strike: int,
        entry_price: float,
        stop_loss: float,
        entry_time: datetime,
        conditions: Optional[Dict] = None
    ):
        """Send trade entry notification"""
        
        if not config.NOTIFY_TRADE_ENTRY:
            return
        
        emoji = "📈" if option_type == "CALL" else "📉"
        
        message = (
            f"{emoji} <b>TRADE ENTRY</b> {emoji}\n\n"
            f"<b>Type:</b> {option_type}\n"
            f"<b>Strike:</b> {strike}\n"
            f"<b>Entry Price:</b> ₹{entry_price:.2f}\n"
            f"<b>Stop Loss:</b> ₹{stop_loss:.2f}\n"
            f"<b>Time:</b> {entry_time.strftime('%H:%M:%S')}\n"
        )
        
        if conditions:
            message += (
                f"\n<b>Conditions:</b>\n"
                f"• Price &gt; VWAP: ✅\n"
                f"• RSI &gt; 60: ✅ ({conditions.get('rsi', 0):.1f})\n"
                f"• ADX &gt; 25: ✅ ({conditions.get('adx', 0):.1f} { '📈' if conditions.get('adx_rising', False) else '📉'})\n"
                f"• OI &lt; SMA: ✅\n"
            )
        
        self._send_message(message)
    
    def send_trade_exit(
        self,
        option_type: str,
        strike: int,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_percent: float,
        exit_reason: str,
        exit_time: datetime
    ):
        """Send trade exit notification"""
        
        if not config.NOTIFY_TRADE_EXIT:
            return
        
        if pnl >= 0:
            emoji = "✅"
            status = "PROFIT"
        else:
            emoji = "❌"
            status = "LOSS"
        
        pnl_symbol = "+" if pnl >= 0 else ""
        
        message = (
            f"{emoji} <b>TRADE EXIT - {status}</b> {emoji}\n\n"
            f"<b>Type:</b> {option_type}\n"
            f"<b>Strike:</b> {strike}\n"
            f"<b>Entry:</b> ₹{entry_price:.2f}\n"
            f"<b>Exit:</b> ₹{exit_price:.2f}\n"
            f"<b>P&L:</b> {pnl_symbol}₹{pnl:.2f} ({pnl_percent:+.2f}%)\n"
            f"<b>Reason:</b> {self._escape_html(exit_reason)}\n"
            f"<b>Time:</b> {exit_time.strftime('%H:%M:%S')}\n"
        )
        
        self._send_message(message)
    
    def send_partial_exit(
        self,
        option_type: str,
        strike: int,
        entry_price: float,
        exit_price: float,
        lots_sold: int,
        remaining_lots: int,
        original_lots: int,
        pnl: float,
        exit_reason: str,
        stage: int
    ):
        """Send partial profit booking notification"""
        
        if not config.NOTIFY_TRADE_EXIT:
            return
        
        pnl_symbol = "+" if pnl >= 0 else ""
        pnl_percent = (pnl / (entry_price * lots_sold)) * 100 if entry_price > 0 else 0
        
        stage_emoji = {1: "🎯", 2: "📈", 3: "🎯🎯"}.get(stage, "📤")
        
        message = (
            f"{stage_emoji} <b>PARTIAL PROFIT BOOKED</b> {stage_emoji}\n\n"
            f"<b>Stage:</b> {stage}\n"
            f"<b>Type:</b> {option_type}\n"
            f"<b>Strike:</b> {strike}\n"
            f"<b>Entry:</b> ₹{entry_price:.2f}\n"
            f"<b>Exit:</b> ₹{exit_price:.2f}\n"
            f"<b>P&amp;L:</b> {pnl_symbol}₹{pnl:.2f} ({pnl_percent:+.2f}%)\n"
            f"<b>Lots Sold:</b> {lots_sold}\n"
            f"<b>Remaining:</b> {remaining_lots}/{original_lots} lots\n"
            f"<b>Reason:</b> {self._escape_html(exit_reason)}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        )
        
        self._send_message(message)
    
    def send_error(self, error_type: str, error_message: str, timestamp: Optional[datetime] = None):
        """Send error notification"""
        
        if not config.NOTIFY_ERRORS:
            return
        
        if timestamp is None:
            timestamp = datetime.now()
        
        message = (
            f"⚠️ <b>ERROR ALERT</b> ⚠️\n\n"
            f"<b>Type:</b> {self._escape_html(error_type)}\n"
            f"<b>Message:</b> {self._escape_html(error_message)}\n"
            f"<b>Time:</b> {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        
        self._send_message(message)
    
    def send_daily_summary(self, summary: Dict):
        """Send daily trading summary"""
        
        if not config.NOTIFY_DAILY_SUMMARY:
            return
        
        total_pnl = summary.get('total_pnl', 0)
        
        if total_pnl >= 0:
            emoji = "🎉"
            status = "PROFITABLE"
        else:
            emoji = "😔"
            status = "LOSS"
        
        pnl_symbol = "+" if total_pnl >= 0 else ""
        
        message = (
            f"{emoji} <b>DAILY SUMMARY - {status}</b> {emoji}\n\n"
            f"<b>Date:</b> {summary.get('date', 'N/A')}\n"
            f"<b>Total Trades:</b> {summary.get('total_trades', 0)}\n"
            f"<b>Winning Trades:</b> {summary.get('winning_trades', 0)}\n"
            f"<b>Losing Trades:</b> {summary.get('losing_trades', 0)}\n"
            f"<b>Win Rate:</b> {summary.get('win_rate', 0):.2f}%\n\n"
            f"<b>Total P&L:</b> {pnl_symbol}₹{total_pnl:.2f}\n"
            f"<b>Avg P&L:</b> {pnl_symbol}₹{summary.get('avg_pnl', 0):.2f}\n"
            f"<b>Max Win:</b> +₹{summary.get('max_win', 0):.2f}\n"
            f"<b>Max Loss:</b> ₹{summary.get('max_loss', 0):.2f}\n"
        )
        
        self._send_message(message)
    
    def send_system_start(self, mode: str = "PAPER"):
        """Send system start notification"""
        
        message = (
            f"🚀 <b>SYSTEM STARTED</b> 🚀\n\n"
            f"<b>Mode:</b> {mode} TRADING\n"
            f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        )
        
        self._send_message(message)
    
    def send_system_stop(self):
        """Send system stop notification"""
        
        message = (
            f"🛑 <b>SYSTEM STOPPED</b> 🛑\n\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n"
        )
        
        self._send_message(message)
    
    def send_custom_message(self, title: str, details: Dict):
        """Send custom notification"""
        
        message = f"<b>{self._escape_html(title)}</b>\n\n"
        
        for key, value in details.items():
            message += f"<b>{self._escape_html(str(key))}:</b> {self._escape_html(str(value))}\n"
        
        self._send_message(message)
    
    def test_connection(self) -> bool:
        """Test Telegram connection"""
        
        if not self.enabled:
            print("Telegram is not enabled. Configure bot token and chat ID.")
            return False
        
        message = "🧪 <b>Test Message</b>\n\nTelegram notification is working correctly!"
        result = self._send_message(message)
        
        if result:
            print("✅ Telegram test successful!")
        else:
            print("❌ Telegram test failed. Check logs for details.")
        
        return result


# Global notifier instance
telegram_notifier = TelegramNotifier()

# Convenience functions
def notify_trade_entry(option_type, strike, entry_price, stop_loss, entry_time, conditions=None):
    telegram_notifier.send_trade_entry(option_type, strike, entry_price, stop_loss, entry_time, conditions)

def notify_trade_exit(option_type, strike, entry_price, exit_price, pnl, pnl_percent, exit_reason, exit_time):
    telegram_notifier.send_trade_exit(option_type, strike, entry_price, exit_price, pnl, pnl_percent, exit_reason, exit_time)

def notify_error(error_type, error_message, timestamp=None):
    telegram_notifier.send_error(error_type, error_message, timestamp)

def notify_daily_summary(summary):
    telegram_notifier.send_daily_summary(summary)

if __name__ == "__main__":
    # Test Telegram notifier
    print("Testing Telegram Notifier...")
    print(f"Enabled: {telegram_notifier.enabled}")
    
    if telegram_notifier.enabled:
        telegram_notifier.test_connection()
    else:
        print("\nTo enable Telegram notifications:")
        print("1. Create a bot via @BotFather on Telegram")
        print("2. Get your chat ID from @userinfobot")
        print("3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.py")
        print("4. Set TELEGRAM_ENABLED = True in config.py")
