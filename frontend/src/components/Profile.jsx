import React from 'react';

const Profile = ({ profile, accountValue }) => {
  if (!profile) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-5 border border-gray-200">
        <h2 className="text-sm font-semibold text-gray-800 mb-3">Profile</h2>
        <p className="text-sm text-gray-500">Loading profile...</p>
      </div>
    );
  }

  const modeColors = {
    PAPER_TRADING: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    LIVE_TRADING: 'bg-red-50 text-red-700 border-red-200',
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-5 border border-gray-200">
      <h2 className="text-sm font-semibold text-gray-800 mb-4">
        Trading Profile
      </h2>

      <div className="space-y-3">
        {/* Account Fund */}
        <div className="bg-gray-900 rounded-lg p-4 relative overflow-hidden">
          <span className="absolute top-2.5 right-3 text-[9px] font-semibold text-gray-400 tracking-widest uppercase">
            Live Fund
          </span>
          <label className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-1 block">Current Account Value</label>
          <p className="text-2xl font-bold text-white tabular-nums">
            ₹{accountValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${accountValue >= profile.initial_balance ? 'bg-emerald-400' : 'bg-red-400'}`}
                style={{ width: `${Math.min(100, (accountValue / profile.initial_balance) * 100)}%` }}
              ></div>
            </div>
            <span className={`text-[10px] font-semibold tabular-nums ${accountValue >= profile.initial_balance ? 'text-emerald-400' : 'text-red-400'}`}>
              {((accountValue - profile.initial_balance) / profile.initial_balance * 100).toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Mode */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <label className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2 block">Trading Mode</label>
          <div className="flex flex-wrap gap-2">
            <span className={`px-2.5 py-1 rounded text-xs font-semibold border ${modeColors[profile.mode] || 'bg-gray-100 text-gray-700 border-gray-200'
              }`}>
              {profile.mode.replace('_', ' ')}
            </span>
            {profile.test_mode && (
              <span className="px-2.5 py-1 bg-amber-50 text-amber-700 rounded text-xs font-semibold border border-amber-200">
                TEST MODE
              </span>
            )}
          </div>
        </div>

        {/* Trading Hours */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <label className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2 block">Trading Hours</label>
          <p className="text-sm font-semibold text-gray-800 flex items-center gap-2 tabular-nums">
            <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {profile.trading_hours.start} - {profile.trading_hours.end}
          </p>
        </div>

        {/* Lot Sizes */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <label className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2 block">Lot Sizes</label>
          <div className="grid grid-cols-2 gap-2.5">
            <div className="bg-white rounded-md p-2.5 border border-gray-200 text-center">
              <span className="text-[11px] text-gray-400 font-medium block mb-0.5">Nifty</span>
              <p className="text-lg font-bold text-gray-900 tabular-nums">{profile.lot_sizes.nifty}</p>
            </div>
            <div className="bg-white rounded-md p-2.5 border border-gray-200 text-center">
              <span className="text-[11px] text-gray-400 font-medium block mb-0.5">Sensex</span>
              <p className="text-lg font-bold text-gray-900 tabular-nums">{profile.lot_sizes.sensex}</p>
            </div>
          </div>
        </div>

        {/* Indicators */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <label className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2 block">Indicator Settings</label>
          <div className="space-y-1.5">
            <div className="flex justify-between items-center bg-white rounded-md px-2.5 py-1.5 border border-gray-200">
              <span className="text-xs text-gray-500 font-medium">RSI Threshold</span>
              <span className="font-semibold text-gray-900 text-sm tabular-nums">{profile.indicators.rsi_threshold}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-md px-2.5 py-1.5 border border-gray-200">
              <span className="text-xs text-gray-500 font-medium">RSI Period</span>
              <span className="font-semibold text-gray-900 text-sm tabular-nums">{profile.indicators.rsi_period}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-md px-2.5 py-1.5 border border-gray-200">
              <span className="text-xs text-gray-500 font-medium">OI SMA Period</span>
              <span className="font-semibold text-gray-900 text-sm tabular-nums">{profile.indicators.oi_sma_period}</span>
            </div>
          </div>
        </div>

        {/* Risk Management */}
        <div className="bg-gray-50 rounded-lg p-3.5 border border-gray-200">
          <label className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-2 block">Risk Management</label>
          <div className="space-y-1.5">
            <div className="flex justify-between items-center bg-white rounded-md px-2.5 py-1.5 border border-gray-200">
              <span className="text-xs text-gray-500 font-medium">Stop Loss</span>
              <span className="font-semibold text-gray-900 text-xs">{profile.risk_management.stop_loss_method}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-md px-2.5 py-1.5 border border-gray-200">
              <span className="text-xs text-gray-500 font-medium">Max Positions</span>
              <span className="font-semibold text-gray-900 text-sm tabular-nums">{profile.risk_management.max_positions}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
