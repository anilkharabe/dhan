import React from 'react';

const DailySummary = ({ summary, liveStrategyPnl }) => {
  if (!summary) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-2xl font-bold mb-4">Daily Summary</h2>
        <p className="text-gray-500">Loading summary...</p>
      </div>
    );
  }

  // Determine active strategies from live data or summary
  const detectedStrategies = liveStrategyPnl
    ? Object.keys(liveStrategyPnl).filter(k => k !== 'TOTAL')
    : Object.keys(summary.strategy_wise || {});

  const getStrategyColor = (tag) => {
    if (tag.includes('STAGE')) return 'indigo';
    if (tag.includes('TRAIL')) return 'emerald';
    if (tag.includes('HYBRID')) return 'amber';
    return 'gray';
  };

  const displayPnl = liveStrategyPnl ? liveStrategyPnl.TOTAL : summary.total_pnl;
  const pnlColor = displayPnl >= 0 ? 'text-green-600' : 'text-red-600';
  const pnlBg = displayPnl >= 0
    ? 'bg-gradient-to-br from-green-50 to-emerald-50 border-green-200'
    : 'bg-gradient-to-br from-red-50 to-rose-50 border-red-200';



  return (
    <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100 transform transition-all hover:shadow-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-3xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
          Daily Summary
        </h2>
        <span className="text-sm font-semibold text-gray-500 bg-gray-100 px-3 py-1 rounded-full">
          {summary.date}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total P&L */}
        <div className={`${pnlBg} rounded-xl p-5 border-2 transform transition-all hover:scale-105 hover:shadow-lg relative overflow-hidden`}>
          {/* Live Indicator */}
          <div className="absolute top-0 right-0 px-2 py-0.5 bg-emerald-500 text-white text-[10px] font-bold rounded-bl-lg animate-pulse">
            LIVE
          </div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-600">Total P&L</p>
            {displayPnl >= 0 ? (
              <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
              </svg>
            )}
          </div>
          <p className={`text-3xl font-extrabold ${pnlColor} tabular-nums`}>
            {displayPnl >= 0 ? '+' : ''}₹{displayPnl.toFixed(2)}
          </p>
          <div className="mt-1 flex justify-between items-center">
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">
              Closed: ₹{summary.total_pnl.toFixed(2)}
            </p>
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">
              Open: ₹{(displayPnl - summary.total_pnl).toFixed(2)}
            </p>
          </div>
        </div>

        {/* Total Trades */}
        <div className="bg-gradient-to-br from-blue-50 to-cyan-50 rounded-xl p-5 border-2 border-blue-200 transform transition-all hover:scale-105 hover:shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-600">Total Trades</p>
            <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <p className="text-3xl font-bold text-blue-600">{summary.total_trades}</p>
        </div>

        {/* Win Rate */}
        <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-xl p-5 border-2 border-purple-200 transform transition-all hover:scale-105 hover:shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-600">Win Rate</p>
            <svg className="w-5 h-5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-3xl font-bold text-purple-600">
            {summary.win_rate.toFixed(1)}%
          </p>
        </div>

        {/* Current Positions */}
        <div className="bg-gradient-to-br from-yellow-50 to-amber-50 rounded-xl p-5 border-2 border-yellow-200 transform transition-all hover:scale-105 hover:shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-600">Open Positions</p>
            <svg className="w-5 h-5 text-yellow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-3xl font-bold text-yellow-600">{summary.current_positions}</p>
        </div>
      </div>

      {/* Strategy-wise Live Breakdown */}
      <div className="mt-8">
        <div className="flex items-center gap-4 mb-4">
          <h3 className="text-xs font-black text-gray-400 uppercase tracking-[0.2em]">Strategy Variance (Live)</h3>
          <div className="h-[1px] bg-gray-100 flex-grow"></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {detectedStrategies.map(tag => {
            const stratPnl = liveStrategyPnl ? liveStrategyPnl[tag] : (summary.strategy_wise?.[tag]?.pnl || 0);
            const stratStats = summary.strategy_wise?.[tag] || { trades: 0, wins: 0 };
            const color = getStrategyColor(tag);

            return (
              <div key={tag} className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm flex flex-col justify-between hover:border-blue-400 transition-all">
                <div className="flex justify-between items-center mb-1">
                  <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest bg-${color}-50 text-${color}-700 border border-${color}-100`}>
                    {tag.replace('STRATEGY_', '')}
                  </span>
                  <span className={`text-sm font-black ${stratPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {stratPnl >= 0 ? '+' : ''}₹{stratPnl.toFixed(0)}
                  </span>
                </div>
                <div className="flex justify-between text-[9px] font-bold text-gray-400">
                  <span>{stratStats.trades} Trades</span>
                  <span>{stratStats.trades > 0 ? ((stratStats.wins / stratStats.trades) * 100).toFixed(0) : 0}% WR</span>
                </div>
              </div>
            );
          })}
        </div>

      </div>

      <div className="mt-6 grid grid-cols-2 gap-4">
        {/* Winners/Losers */}
        <div className="bg-gradient-to-r from-gray-50 to-gray-100 rounded-xl p-4 border border-gray-200 transform transition-all hover:scale-105">
          <h3 className="text-sm font-bold text-gray-700 mb-3">Trade Breakdown</h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 flex items-center gap-2">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                Winners
              </span>
              <span className="text-lg font-bold text-green-600">
                {summary.winning_trades}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600 flex items-center gap-2">
                <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                Losers
              </span>
              <span className="text-lg font-bold text-red-600">
                {summary.losing_trades}
              </span>
            </div>
          </div>
        </div>

        {/* Max Win/Loss */}
        <div className="bg-gradient-to-r from-gray-50 to-gray-100 rounded-xl p-4 border border-gray-200 transform transition-all hover:scale-105">
          <h3 className="text-sm font-bold text-gray-700 mb-3">Extremes</h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Max Win</span>
              <span className="text-lg font-bold text-green-600">
                +₹{summary.max_win.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Max Loss</span>
              <span className="text-lg font-bold text-red-600">
                ₹{summary.max_loss.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Index-wise P&L */}
      <div className="mt-6 bg-gradient-to-r from-indigo-50 to-blue-50 rounded-xl p-4 border border-indigo-200">
        <h3 className="text-sm font-bold text-gray-700 mb-3">Index Performance</h3>
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white rounded-lg p-3 border border-indigo-100">
            <span className="text-xs text-gray-500 font-semibold">Nifty:</span>
            <span className={`ml-2 text-lg font-bold ${summary.nifty_pnl >= 0 ? 'text-green-600' : 'text-red-600'
              }`}>
              {summary.nifty_pnl >= 0 ? '+' : ''}₹{summary.nifty_pnl.toFixed(2)}
            </span>
          </div>
          <div className="bg-white rounded-lg p-3 border border-indigo-100">
            <span className="text-xs text-gray-500 font-semibold">Sensex:</span>
            <span className={`ml-2 text-lg font-bold ${summary.sensex_pnl >= 0 ? 'text-green-600' : 'text-red-600'
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
