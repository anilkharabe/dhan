"""
QUICK START GUIDE
=================

Follow these steps to get started with the Nifty Options Algo Trading System.

STEP 1: INSTALL DEPENDENCIES
----------------------------
pip install -r requirements.txt


STEP 2: CONFIGURE DHAN API
----------------------------
1. Log in to web.dhan.co -> My Profile -> DhanHQ Trading APIs
2. Note your Client ID and generate an access token (~24h validity)
3. Update .env (project root):

   DHAN_CLIENT_ID = "your_client_id"
   DHAN_ACCESS_TOKEN = "your_access_token"

4. (Optional, for unattended daily token refresh) also set DHAN_PIN and
   DHAN_TOTP_SECRET, then run: python generate_dhan_token.py


STEP 3: (OPTIONAL) CONFIGURE TELEGRAM
------------------------------------
1. Create bot via @BotFather on Telegram
2. Get chat ID from @userinfobot
3. Update config.py:
   
   TELEGRAM_BOT_TOKEN = "your_bot_token"
   TELEGRAM_CHAT_ID = "your_chat_id"
   TELEGRAM_ENABLED = True


STEP 4: TEST IN PAPER TRADING MODE
---------------------------------
1. Ensure PAPER_TRADING = True in config.py
2. Run: python main.py
3. Monitor logs and charts
4. Review trade logs in trade_logs/


STEP 5: GO LIVE (AFTER THOROUGH TESTING)
---------------------------------------
⚠️  WARNING: Only proceed after successful paper trading!

1. Set PAPER_TRADING = False in config.py
2. Start with minimum lot size (LOT_SIZE = 1)
3. Monitor closely for first few days
4. Keep manual intervention ready


DAILY USAGE
-----------
1. Start script at 9:50 AM: python main.py
2. System initializes and determines strikes
3. Trading starts at 10:00 AM
4. Auto-closes at 3:15 PM
5. Review daily summary and charts


MONITORING
----------
- Watch console output for real-time status
- Check Telegram for trade notifications
- Review charts in charts/YYYY-MM-DD/
- Check logs in logs/ for detailed info


WHAT TO EXPECT
--------------
✅ System starts at 9:50 AM
✅ Fetches historical data (prev day + current)
✅ Determines ATM strikes
✅ Scans every 3 minutes for signals
✅ Generates chart for each signal
✅ Executes trades (paper or live)
✅ Monitors stop losses
✅ Closes positions at 3:15 PM
✅ Generates daily report


FILE OUTPUTS
------------
1. Charts: charts/YYYY-MM-DD/*.png
2. Trade Logs: trade_logs/trades_YYYY-MM-DD.xlsx
3. System Logs: logs/trading_YYYY-MM-DD.log


TESTING CHECKLIST
----------------
Before going live, verify:

[ ] Paper trading works without errors
[ ] Charts are generated correctly
[ ] Trade logs are accurate
[ ] Telegram notifications work
[ ] Dhan API credentials valid
[ ] Sufficient margin in account
[ ] Understanding of strategy logic
[ ] Stop loss mechanism tested
[ ] EOD square-off works correctly


COMMON FIRST-RUN ISSUES
-----------------------
1. "Insufficient data" → Wait until 10:00 AM
2. "API error" → Check Dhan credentials
3. "No charts" → Set GENERATE_CHARTS = True
4. "Telegram failed" → Verify bot token/chat ID


GETTING HELP
------------
1. Check README.md for detailed documentation
2. Review logs/ for error details
3. Test modules individually (python <module>.py)
4. Verify config.py settings


SAFETY REMINDERS
---------------
⚠️  Start with paper trading
⚠️  Use minimum lot sizes initially
⚠️  Never risk more than you can afford to lose
⚠️  Keep emergency manual override ready
⚠️  Monitor system closely in early days
⚠️  Understand that algo trading has risks


SUPPORT
-------
If you encounter issues:
1. Check logs in logs/ directory
2. Verify all settings in config.py
3. Test individual modules
4. Review Telegram error messages


Good luck with your trading!
"""

if __name__ == "__main__":
    print(__doc__)
