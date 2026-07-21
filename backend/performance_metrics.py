"""
Performance Metrics Calculator
Calculate trading performance metrics for scenario comparison
"""

from typing import List, Dict, Any
import numpy as np
from datetime import datetime


class PerformanceMetrics:
    """Calculate comprehensive trading performance metrics"""
    
    def __init__(self, trades: List[Dict]):
        """
        Initialize with trade data
        
        Args:
            trades: List of trade dictionaries with entry/exit data
        """
        self.trades = trades
        self.closed_trades = [t for t in trades if t.get('status') == 'CLOSED']
        self.open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    def calculate_all(self) -> Dict[str, Any]:
        """Calculate all performance metrics"""
        
        if len(self.closed_trades) == 0:
            return self._empty_metrics()
        
        # Extract P&L data (filter out None values)
        pnl_list = [t['pnl'] for t in self.closed_trades if t.get('pnl') is not None]
        pnl_percent_list = [t.get('pnl_percent') for t in self.closed_trades if t.get('pnl_percent') is not None]
        
        # Default to 0 if list is empty
        if not pnl_list:
            pnl_list = [0.0]
        if not pnl_percent_list:
            pnl_percent_list = [0.0]

        
        # Calculate metrics
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t['pnl'] > 0]
        losing_trades = [t for t in self.closed_trades if t['pnl'] < 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        total_pnl = sum(pnl_list)
        avg_pnl = np.mean(pnl_list)
        
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        # Profit/Loss statistics
        gross_profit = sum(t['pnl'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        
        # Best/Worst trades
        best_trade = max(pnl_list) if pnl_list else 0
        worst_trade = min(pnl_list) if pnl_list else 0
        
        # Drawdown calculation
        cumulative_pnl = np.cumsum(pnl_list)
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = cumulative_pnl - running_max
        max_drawdown = abs(min(drawdown)) if len(drawdown) > 0 else 0
        
        # Risk-adjusted return (simplified Sharpe-like ratio)
        if len(pnl_list) > 1:
            pnl_std = np.std(pnl_list)
            risk_adjusted_return = (avg_pnl / pnl_std) if pnl_std > 0 else 0
        else:
            risk_adjusted_return = 0
        
        return {
            # Trade counts
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'open_trades': len(self.open_trades),
            
            # Win rate
            'win_rate': win_rate,
            'loss_rate': 100 - win_rate,
            
            # P&L
            'total_pnl': total_pnl,
            'avg_pnl_per_trade': avg_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            
            # Win/Loss stats
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': best_trade,
            'largest_loss': worst_trade,
            
            # Ratios
            'profit_factor': profit_factor,
            'risk_reward_ratio': (avg_win / avg_loss) if avg_loss > 0 else 0,
            'risk_adjusted_return': risk_adjusted_return,
            
            # Risk metrics
            'max_drawdown': max_drawdown,
            
            # Per trade percentage
            'avg_pnl_percent': np.mean(pnl_percent_list) if pnl_percent_list else 0,
        }
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics when no trades"""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'open_trades': len(self.open_trades),
            'win_rate': 0,
            'loss_rate': 0,
            'total_pnl': 0,
            'avg_pnl_per_trade': 0,
            'gross_profit': 0,
            'gross_loss': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'largest_win': 0,
            'largest_loss': 0,
            'profit_factor': 0,
            'risk_reward_ratio': 0,
            'risk_adjusted_return': 0,
            'max_drawdown': 0,
            'avg_pnl_percent': 0,
        }
    
    def get_pnl_curve(self) -> List[float]:
        """Get cumulative P&L curve"""
        if len(self.closed_trades) == 0:
            return []
        
        pnl_list = [t['pnl'] for t in self.closed_trades]
        cumulative_pnl = np.cumsum(pnl_list)
        return cumulative_pnl.tolist()
    
    def get_trade_distribution(self) -> Dict[str, Any]:
        """Get P&L distribution statistics"""
        if len(self.closed_trades) == 0:
            return {}
        
        pnl_list = [t['pnl'] for t in self.closed_trades]
        
        return {
            'mean': np.mean(pnl_list),
            'median': np.median(pnl_list),
            'std': np.std(pnl_list),
            'min': min(pnl_list),
            'max': max(pnl_list),
            'percentile_25': np.percentile(pnl_list, 25),
            'percentile_75': np.percentile(pnl_list, 75),
        }


def compare_scenarios(scenario_results: Dict[str, Dict]) -> str:
    """
    Compare performance across scenarios and generate report
    
    Args:
        scenario_results: Dict mapping scenario names to their metrics
        
    Returns:
        Formatted comparison report
    """
    report = []
    report.append("=" * 80)
    report.append("SCENARIO COMPARISON REPORT")
    report.append("=" * 80)
    
    # Get baseline (Scenario 1)
    baseline_key = list(scenario_results.keys())[0]
    baseline = scenario_results[baseline_key]
    
    for scenario_name, metrics in scenario_results.items():
        report.append(f"\n{scenario_name}")
        report.append("-" * 80)
        
        # Basic stats
        report.append(f"  Total Trades: {metrics['total_trades']}")
        report.append(f"  Win Rate: {metrics['win_rate']:.1f}%")
        report.append(f"  Total P&L: ₹{metrics['total_pnl']:,.2f}")
        report.append(f"  Avg P&L/Trade: ₹{metrics['avg_pnl_per_trade']:,.2f}")
        report.append(f"  Avg P&L %: {metrics['avg_pnl_percent']:.2f}%")
        report.append(f"  Max Drawdown: ₹{metrics['max_drawdown']:,.2f}")
        report.append(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        
        # Comparison to baseline
        if scenario_name != baseline_key:
            trade_diff = metrics['total_trades'] - baseline['total_trades']
            trade_diff_pct = (trade_diff / baseline['total_trades'] * 100) if baseline['total_trades'] > 0 else 0
            
            winrate_diff = metrics['win_rate'] - baseline['win_rate']
            
            pnl_diff = metrics['total_pnl'] - baseline['total_pnl']
            pnl_diff_pct = (pnl_diff / baseline['total_pnl'] * 100) if baseline['total_pnl'] != 0 else 0
            
            avg_pnl_diff = metrics['avg_pnl_per_trade'] - baseline['avg_pnl_per_trade']
            avg_pnl_diff_pct = (avg_pnl_diff / baseline['avg_pnl_per_trade'] * 100) if baseline['avg_pnl_per_trade'] != 0 else 0
            
            report.append(f"\n  📊 Comparison to Baseline:")
            report.append(f"     Trades: {trade_diff:+d} ({trade_diff_pct:+.1f}%)")
            report.append(f"     Win Rate: {winrate_diff:+.1f}%")
            report.append(f"     Total P&L: ₹{pnl_diff:+,.2f} ({pnl_diff_pct:+.1f}%)")
            report.append(f"     Avg P&L/Trade: ₹{avg_pnl_diff:+,.2f} ({avg_pnl_diff_pct:+.1f}%)")
    
    # Recommendation
    report.append("\n" + "=" * 80)
    report.append("RECOMMENDATION")
    report.append("=" * 80)
    
    # Find best scenario by risk-adjusted return
    best_scenario = max(scenario_results.items(), 
                       key=lambda x: x[1]['total_pnl'] if x[1]['total_trades'] > 0 else 0)
    
    report.append(f"\nBest Overall Performance: {best_scenario[0]}")
    report.append(f"  Total P&L: ₹{best_scenario[1]['total_pnl']:,.2f}")
    report.append(f"  Win Rate: {best_scenario[1]['win_rate']:.1f}%")
    report.append(f"  Risk-Adjusted Return: {best_scenario[1]['risk_adjusted_return']:.2f}")
    
    return "\n".join(report)


if __name__ == "__main__":
    # Test with sample data
    sample_trades = [
        {'status': 'CLOSED', 'pnl': 500, 'pnl_percent': 10},
        {'status': 'CLOSED', 'pnl': -200, 'pnl_percent': -5},
        {'status': 'CLOSED', 'pnl': 800, 'pnl_percent': 15},
        {'status': 'CLOSED', 'pnl': 300, 'pnl_percent': 8},
        {'status': 'CLOSED', 'pnl': -150, 'pnl_percent': -3},
        {'status': 'OPEN', 'pnl': 0, 'pnl_percent': 0},
    ]
    
    metrics_calc = PerformanceMetrics(sample_trades)
    metrics = metrics_calc.calculate_all()
    
    print("Performance Metrics Test:")
    print("=" * 50)
    for key, value in metrics.items():
        print(f"{key}: {value}")
