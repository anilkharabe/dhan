import React from 'react';

const DailySummary = ({ summary, liveStrategyPnl }) => {
  if (!summary) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-5 border border-gray-200">
        <h2 className="text-sm font-semibold text-gray-800 mb-3">Daily Summary</h2>
        <p className="text-sm text-gray-500">Loading summary...</p>
      </div>
    );
  }

  // Determine active strategies from live data or summary
  const detectedStrategies = liveStrategyPnl
    ? Object.keys(liveStrategyPnl).filter(k => k !== 'TOTAL')
    : Object.keys(summary.strategy_wise || {});

  const displayPnl = liveStrategyPnl ? liveStrategyPnl.TOTAL : summary.total_pnl;
  const pnlColor = displayPnl >= 0 ? 'text-emerald-600' : 'text-red-600';

  return (
    <div className="bg-white rounded-lg shadow-sm p-5 border border-gray-200">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-800">Daily Summary</h2>
        <span className="text-xs font-medium text-gray-400">
          {summary.date}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Total P&L */}
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 relative">
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-medium text-gray-500">Total P&L</p>
            <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
              LIVE
            </span>
          </div>
          <p className={`text-2xl font-bold ${pnlColor} tabular-nums`}>
            {displayPnl >= 0 ? '+' : ''}₹{displayPnl.toFixed(2)}
          </p>
          <div className="mt-1.5 flex justify-between items-center text-[10px] text-gray-400">
            <span>Closed ₹{summary.total_pnl.toFixed(2)}</span>
            <span>Open ₹{(displayPnl - summary.total_pnl).toFixed(2)}</span>
          </div>
        </div>

        {/* Total Trades */}
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <p className="text-xs font-medium text-gray-500 mb-1.5">Total Trades</p>
          <p className="text-2xl font-bold text-gray-900 tabular-nums">{summary.total_trades}</p>
        </div>

        {/* Win Rate */}
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <p className="text-xs font-medium text-gray-500 mb-1.5">Win Rate</p>
          <p className="text-2xl font-bold text-gray-900 tabular-nums">
            {summary.win_rate.toFixed(1)}%
          </p>
        </div>

        {/* Current Positions */}
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <p className="text-xs font-medium text-gray-500 mb-1.5">Open Positions</p>
          <p className="text-2xl font-bold text-gray-900 tabular-nums">{summary.current_positions}</p>
        </div>
      </div>

      {/* Strategy-wise Live Breakdown */}
      <div className="mt-6">
        <div className="flex items-center gap-3 mb-3">
          <h3 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Strategy Variance (Live)</h3>
          <div className="h-px bg-gray-100 flex-grow"></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2.5">
          {detectedStrategies.map(tag => {
            const stratPnl = liveStrategyPnl ? liveStrategyPnl[tag] : (summary.strategy_wise?.[tag]?.pnl || 0);
            const stratStats = summary.strategy_wise?.[tag] || { trades: 0, wins: 0 };

            return (
              <div key={tag} className="bg-white rounded-lg p-3 border border-gray-200 flex flex-col justify-between hover:border-gray-300 transition-colors">
                <div className="flex justify-between items-center mb-1">
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide bg-gray-100 text-gray-600 border border-gray-200">
                    {tag.replace('STRATEGY_', '')}
                  </span>
                  <span className={`text-sm font-bold ${stratPnl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {stratPnl >= 0 ? '+' : ''}₹{stratPnl.toFixed(0)}
                  </span>
                </div>
                <div className="flex justify-between text-[10px] font-medium text-gray-400">
                  <span>{stratStats.trades} Trades</span>
                  <span>{stratStats.trades > 0 ? ((stratStats.wins / stratStats.trades) * 100).toFixed(0) : 0}% WR</span>
                </div>
              </div>
            );
          })}
        </div>

      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        {/* Winners/Losers */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <h3 className="text-xs font-semibold text-gray-600 mb-2">Trade Breakdown</h3>
          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                Winners
              </span>
              <span className="text-sm font-bold text-emerald-600 tabular-nums">
                {summary.winning_trades}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-red-500 rounded-full"></span>
                Losers
              </span>
              <span className="text-sm font-bold text-red-600 tabular-nums">
                {summary.losing_trades}
              </span>
            </div>
          </div>
        </div>

        {/* Max Win/Loss */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <h3 className="text-xs font-semibold text-gray-600 mb-2">Extremes</h3>
          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">Max Win</span>
              <span className="text-sm font-bold text-emerald-600 tabular-nums">
                +₹{summary.max_win.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">Max Loss</span>
              <span className="text-sm font-bold text-red-600 tabular-nums">
                ₹{summary.max_loss.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Index-wise P&L */}
      <div className="mt-3 bg-gray-50 rounded-lg p-3.5 border border-gray-200">
        <h3 className="text-xs font-semibold text-gray-600 mb-2">Index Performance</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white rounded-md p-2.5 border border-gray-200 flex items-center justify-between">
            <span className="text-xs text-gray-500 font-medium">Nifty</span>
            <span className={`text-sm font-bold tabular-nums ${summary.nifty_pnl >= 0 ? 'text-emerald-600' : 'text-red-600'
              }`}>
              {summary.nifty_pnl >= 0 ? '+' : ''}₹{summary.nifty_pnl.toFixed(2)}
            </span>
          </div>
          <div className="bg-white rounded-md p-2.5 border border-gray-200 flex items-center justify-between">
            <span className="text-xs text-gray-500 font-medium">Sensex</span>
            <span className={`text-sm font-bold tabular-nums ${summary.sensex_pnl >= 0 ? 'text-emerald-600' : 'text-red-600'
              }`}>
              {summary.sensex_pnl >= 0 ? '+' : ''}₹{summary.sensex_pnl.toFixed(2)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DailySummary;
