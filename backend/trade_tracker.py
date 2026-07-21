"""
Trade Tracker Module
Logs all trades to Excel/CSV for analysis
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import os

import config
import logger
from mongo_logger import mongo_logger

class TradeTracker:
    """Track and log trades to Excel/CSV"""
    
    def __init__(self):
        self.trades = []
        self.trade_counter = 0  # Counter for generating IDs
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.trade_log_path = config.get_trade_log_path(self.current_date)
        
    def set_start_id(self, start_id: int):
        """Set the starting trade ID counter"""
        self.trade_counter = start_id - 1
        logger.info(f"Trade counter initialized to start at: {start_id}")
    
    def add_spread_trade_entry(
        self,
        spread_type: str,
        symbol: str,
        signal_type: str,
        near_option_type: str,
        near_strike: int,
        far_option_type: str,
        far_strike: int,
        near_entry_price: float,
        far_entry_price: float,
        net_credit: float,
        stop_loss_value: float,
        profit_target_value: float,
        entry_time: datetime,
        expiry_date: str,
        lot_size: int = 1,
        conditions: Optional[Dict] = None,
        entry_reason: str = "",
        near_instrument_key: str = "",
        far_instrument_key: str = "",
        strategy_tag: str = "STRATEGY_A"
    ) -> int:
        """
        Log a new credit-spread trade entry (two legs: sold near leg + bought hedge leg).

        Args:
            spread_type: "BULL_PUT" or "BEAR_CALL"
            signal_type: "CALL" or "PUT" - which signal triggered this (NOT the same as
                near_option_type: a CALL signal sells a PUT spread, so signal_type="CALL"
                but near_option_type="PUT". Used for active_positions bucketing / duplicate
                signal checks, which key off the signal that was acted on, not the leg traded.
            near_option_type/near_strike: the SOLD leg (collects premium)
            far_option_type/far_strike: the BOUGHT hedge leg (caps max loss)
            near_entry_price/far_entry_price: each leg's fill price
            net_credit: near_entry_price - far_entry_price
            stop_loss_value/profit_target_value: net cost-to-close thresholds

        Returns:
            Trade ID
        """
        self.trade_counter += 1
        trade_id = self.trade_counter

        trade = {
            'trade_id': trade_id,
            'symbol': symbol,
            'is_spread': True,
            'spread_type': spread_type,
            'signal_type': signal_type,
            # Backward-compatible single-leg view (the sold/near leg)
            'type': near_option_type,
            'strike': near_strike,
            'instrument_key': near_instrument_key,
            'entry_price': near_entry_price,
            # Hedge leg
            'far_option_type': far_option_type,
            'far_strike': far_strike,
            'far_instrument_key': far_instrument_key,
            'far_entry_price': far_entry_price,
            'net_credit': net_credit,
            'stop_loss_value': stop_loss_value,
            'profit_target_value': profit_target_value,
            'expiry': expiry_date,
            'lot_size': lot_size,
            'entry_time': entry_time,
            'exit_time': None,
            'exit_price': None,
            'far_exit_price': None,
            'exit_reason': None,
            'exit_reasoning': None,
            'entry_reason': entry_reason,
            'pnl': None,
            'pnl_percent': None,
            'status': 'OPEN',
            'strategy_tag': strategy_tag,
            'entry_vwap': conditions.get('vwap') if conditions else None,
            'entry_rsi': conditions.get('rsi') if conditions else None,
            'entry_oi': conditions.get('oi') if conditions else None,
            'entry_oi_sma': conditions.get('oi_sma') if conditions else None,
        }

        self.trades.append(trade)
        logger.info(
            f"Spread Trade #{trade_id} logged: {spread_type} | "
            f"SELL {near_option_type} {near_strike} @ ₹{near_entry_price:.2f} / "
            f"BUY {far_option_type} {far_strike} @ ₹{far_entry_price:.2f} | "
            f"Net Credit: ₹{net_credit:.2f} | Reason: {entry_reason}"
        )

        return trade_id

    def update_spread_trade_exit(
        self,
        trade_id: int,
        near_exit_price: float,
        far_exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        exit_reasoning: str = ""
    ):
        """
        Close a credit-spread trade: buy back the near/short leg, sell the far/hedge leg.

        Args:
            near_exit_price: cost to buy back the short leg
            far_exit_price: proceeds from selling the hedge leg
        """
        for trade in self.trades:
            if trade['trade_id'] == trade_id:
                trade['exit_time'] = exit_time
                trade['exit_price'] = near_exit_price
                trade['far_exit_price'] = far_exit_price
                trade['exit_reason'] = exit_reason
                trade['exit_reasoning'] = exit_reasoning
                trade['status'] = 'CLOSED'

                net_credit = trade.get('net_credit', 0)
                lot_size = trade.get('lot_size', 1)
                net_debit_to_close = near_exit_price - far_exit_price
                pnl = (net_credit - net_debit_to_close) * lot_size
                pnl_percent = (pnl / (net_credit * lot_size)) * 100 if net_credit > 0 and lot_size > 0 else 0

                trade['pnl'] = pnl
                trade['pnl_percent'] = pnl_percent

                logger.info(
                    f"Spread Trade #{trade_id} closed: {trade.get('spread_type', '')} | "
                    f"Net Credit: ₹{net_credit:.2f} | Cost to Close: ₹{net_debit_to_close:.2f} | "
                    f"P&L: {'+ ' if pnl >= 0 else ''}₹{pnl:.2f} ({pnl_percent:+.2f}%)"
                )

                break

    def get_open_trades(self, option_type: Optional[str] = None) -> List[Dict]:
        """
        Get all open trades, optionally filtered by type
        
        Args:
            option_type: "CALL" or "PUT" or None for all
        
        Returns:
            List of open trade dictionaries
        """
        open_trades = [t for t in self.trades if t['status'] == 'OPEN']
        
        if option_type:
            open_trades = [t for t in open_trades if t['type'] == option_type]
        
        return open_trades
    
    def get_trade_by_id(self, trade_id: int) -> Optional[Dict]:
        """Get trade by ID"""
        for trade in self.trades:
            if trade['trade_id'] == trade_id:
                return trade
        return None
    
    def save_to_excel(self, filepath: Optional[str] = None):
        """
        Save all trades to Excel file
        
        Args:
            filepath: Custom filepath or None for default
        """
        if not self.trades:
            logger.warning("No trades to save")
            return
        
        if filepath is None:
            filepath = self.trade_log_path
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(self.trades)
            
            # Format datetime columns
            df['entry_time'] = pd.to_datetime(df['entry_time'])
            df['exit_time'] = pd.to_datetime(df['exit_time'])
            
            # Create Excel writer with formatting
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Write main trades sheet
                df.to_excel(writer, sheet_name='Trades', index=False)
                
                # Create summary sheet
                summary = self._create_summary()
                summary_df = pd.DataFrame([summary])
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Format columns
                workbook = writer.book
                trades_sheet = writer.sheets['Trades']
                
                # Auto-adjust column widths
                for column in trades_sheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    trades_sheet.column_dimensions[column_letter].width = adjusted_width
            
            logger.info(f"Trades saved to Excel: {filepath}")
        
        except Exception as e:
            logger.error(f"Error saving to Excel: {str(e)}")
    
    def save_to_csv(self, filepath: Optional[str] = None):
        """
        Save all trades to CSV file
        
        Args:
            filepath: Custom filepath or None for default
        """
        if not self.trades:
            logger.warning("No trades to save")
            return
        
        if filepath is None:
            filepath = self.trade_log_path.replace('.xlsx', '.csv')
        
        try:
            df = pd.DataFrame(self.trades)
            df.to_csv(filepath, index=False)
            logger.info(f"Trades saved to CSV: {filepath}")
        
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}")

    def sync_from_db(self):
        """
        Sync trades from MongoDB to local memory.
        Crucial for API server which runs in a separate process.
        """
        if not mongo_logger.enabled:
            return
            
        try:
            db_trades = mongo_logger.get_trades_for_day(self.current_date)
            if db_trades:
                self.trades = db_trades
                logger.info(f"Synced {len(self.trades)} trades from MongoDB")
        except Exception as e:
            logger.error(f"Error syncing from DB: {str(e)}")
    
    def _create_summary(self) -> Dict:
        """Create trading summary statistics"""
        
        closed_trades = [t for t in self.trades if t['status'] == 'CLOSED']
        winning_trades = [t for t in closed_trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in closed_trades if t.get('pnl', 0) <= 0]
        
        # Calculate Total Realized P&L
        total_pnl = 0
        nifty_pnl = 0
        sensex_pnl = 0
        
        # Iterate through ALL trades to get realized P&L (closed + partials)
        for trade in self.trades:
            trade_pnl = 0
            
            # 1. Add P&L from final exit (if closed)
            if trade['status'] == 'CLOSED' and trade.get('pnl') is not None:
                trade_pnl += trade['pnl']
            
            # 2. Add P&L from partial exits (for both OPEN and CLOSED trades)
            if 'partial_exits' in trade:
                for pe in trade['partial_exits']:
                    if pe.get('pnl') is not None:
                        trade_pnl += pe['pnl']
            
            # Add to totals
            total_pnl += trade_pnl
            
            if trade.get('symbol') == 'NIFTY':
                nifty_pnl += trade_pnl
            elif trade.get('symbol') == 'SENSEX':
                sensex_pnl += trade_pnl

        # Calculate averages and max/min
        avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
        
        # Note: Max Win/Loss logic might need adjustment if a single trade has mixed results
        # For now, keeping it based on final closed P&L to avoid confusion
        max_win = max([t.get('pnl', 0) for t in winning_trades]) if winning_trades else 0
        max_loss = min([t.get('pnl', 0) for t in losing_trades]) if losing_trades else 0
        
        win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0
        
        # Calculate strategy-wise breakdown
        strategy_wise = {}
        for trade in self.trades:
            tag = trade.get('strategy_tag', 'STRATEGY_A')
            if tag not in strategy_wise:
                strategy_wise[tag] = {'pnl': 0, 'trades': 0, 'wins': 0, 'losses': 0}
            
            trade_pnl = 0
            if trade['status'] == 'CLOSED' and trade.get('pnl') is not None:
                trade_pnl += trade['pnl']
            
            if 'partial_exits' in trade:
                for pe in trade['partial_exits']:
                    if pe.get('pnl') is not None:
                        trade_pnl += pe['pnl']
            
            strategy_wise[tag]['pnl'] = round(strategy_wise[tag]['pnl'] + trade_pnl, 2)
            
            if trade['status'] == 'CLOSED' or 'partial_exits' in trade:
                strategy_wise[tag]['trades'] += 1
                if trade_pnl > 0:
                    strategy_wise[tag]['wins'] += 1
                else:
                    strategy_wise[tag]['losses'] += 1

        return {
            'date': self.current_date,
            'total_trades': len(closed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'nifty_pnl': round(nifty_pnl, 2),
            'sensex_pnl': round(sensex_pnl, 2),
            'avg_pnl': round(avg_pnl, 2),
            'max_win': round(max_win, 2),
            'max_loss': round(max_loss, 2),
            'avg_win': round(sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades), 2) if winning_trades else 0,
            'avg_loss': round(sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades), 2) if losing_trades else 0,
            'strategy_wise': strategy_wise
        }
    
    def get_summary(self) -> Dict:
        """Get current trading summary"""
        return self._create_summary()
    
    def print_summary(self):
        """Print trading summary to console"""
        summary = self.get_summary()
        
        print("\n" + "=" * 80)
        print("DAILY TRADING SUMMARY")
        print("=" * 80)
        print(f"Date: {summary['date']}")
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Winning Trades: {summary['winning_trades']}")
        print(f"Losing Trades: {summary['losing_trades']}")
        print(f"Win Rate: {summary['win_rate']:.2f}%")
        print(f"Total P&L: {'+ ' if summary['total_pnl'] >= 0 else ''}₹{summary['total_pnl']:.2f}")
        print(f"Average P&L: {'+ ' if summary['avg_pnl'] >= 0 else ''}₹{summary['avg_pnl']:.2f}")
        print(f"Max Win: + ₹{summary['max_win']:.2f}")
        print(f"Max Loss: ₹{summary['max_loss']:.2f}")
        print("=" * 80 + "\n")
    

# Global trade tracker instance
trade_tracker = TradeTracker()

if __name__ == "__main__":
    # Test trade tracker
    print("Testing Trade Tracker...")
    
    from datetime import datetime, timedelta
    
    # Add sample trades
    now = datetime.now()
    
    # Trade 1: Bull Put Spread (CALL signal)
    trade_id_1 = trade_tracker.add_spread_trade_entry(
        spread_type="BULL_PUT", symbol="NIFTY", signal_type="CALL",
        near_option_type="PUT", near_strike=25550,
        far_option_type="PUT", far_strike=25150,
        near_entry_price=150.50, far_entry_price=90.0,
        net_credit=60.50, stop_loss_value=121.0, profit_target_value=30.25,
        entry_time=now, expiry_date="2025-02-11", lot_size=1,
        conditions={'vwap': 148.0, 'rsi': 65.5, 'oi': 50000, 'oi_sma': 55000}
    )

    # Trade 2: Bear Call Spread (PUT signal)
    trade_id_2 = trade_tracker.add_spread_trade_entry(
        spread_type="BEAR_CALL", symbol="NIFTY", signal_type="PUT",
        near_option_type="CALL", near_strike=25600,
        far_option_type="CALL", far_strike=26000,
        near_entry_price=135.75, far_entry_price=80.0,
        net_credit=55.75, stop_loss_value=111.5, profit_target_value=27.88,
        entry_time=now + timedelta(minutes=30), expiry_date="2025-02-11", lot_size=1,
        conditions={'vwap': 133.0, 'rsi': 62.0, 'oi': 48000, 'oi_sma': 52000}
    )

    # Close trades
    trade_tracker.update_spread_trade_exit(trade_id_1, near_exit_price=100.0, far_exit_price=70.0, exit_time=now + timedelta(hours=1), exit_reason="Profit Target")
    trade_tracker.update_spread_trade_exit(trade_id_2, near_exit_price=170.0, far_exit_price=95.0, exit_time=now + timedelta(hours=1, minutes=30), exit_reason="Stop Loss")

    # Print summary
    trade_tracker.print_summary()
    
    # Save to files
    trade_tracker.save_to_excel()
    trade_tracker.save_to_csv()
    
    print("\nTrade Tracker test completed!")
