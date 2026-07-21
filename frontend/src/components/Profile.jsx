import React from 'react';

const Profile = ({ profile, accountValue }) => {
  if (!profile) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-2xl font-bold mb-4">Profile</h2>
        <p className="text-gray-500">Loading profile...</p>
      </div>
    );
  }

  const modeColors = {
    PAPER_TRADING: 'bg-gradient-to-r from-green-100 to-emerald-100 text-green-800 border-green-300',
    LIVE_TRADING: 'bg-gradient-to-r from-red-100 to-rose-100 text-red-800 border-red-300',
  };

  return (
    <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100 transform transition-all hover:shadow-2xl">
      <h2 className="text-2xl font-bold mb-6 bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
        Trading Profile
      </h2>

      <div className="space-y-5">
        {/* Account Fund */}
        <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl p-5 border-2 border-indigo-400 shadow-lg transform transition-all hover:scale-105 relative overflow-hidden">
          <div className="absolute top-0 right-0 px-3 py-1 bg-white/20 text-white text-[10px] font-extrabold rounded-bl-xl tracking-wider uppercase animate-pulse">
            Live Fund
          </div>
          <label className="text-[10px] font-extrabold text-blue-100 uppercase tracking-widest mb-1 block">Current Account Value</label>
          <p className="text-3xl font-black text-white tabular-nums drop-shadow-md">
            ₹{accountValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-white/20 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${accountValue >= profile.initial_balance ? 'bg-emerald-400' : 'bg-rose-400'}`}
                style={{ width: `${Math.min(100, (accountValue / profile.initial_balance) * 100)}%` }}
              ></div>
            </div>
            <span className={`text-[10px] font-bold ${accountValue >= profile.initial_balance ? 'text-emerald-300' : 'text-rose-300'}`}>
              {((accountValue - profile.initial_balance) / profile.initial_balance * 100).toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Mode */}
        <div className="bg-gradient-to-r from-gray-50 to-gray-100 rounded-lg p-4 border border-gray-200 transform transition-all hover:scale-105">
          <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 block">Trading Mode</label>
          <div className="flex flex-wrap gap-2">
            <span className={`px-4 py-2 rounded-lg text-sm font-bold border-2 transform transition-all hover:scale-105 ${modeColors[profile.mode] || 'bg-gray-100 text-gray-800 border-gray-300'
              }`}>
              {profile.mode.replace('_', ' ')}
            </span>
            {profile.test_mode && (
              <span className="px-3 py-2 bg-gradient-to-r from-yellow-100 to-amber-100 text-yellow-800 rounded-lg text-xs font-bold border-2 border-yellow-300 animate-pulse">
                TEST MODE
              </span>
            )}
          </div>
        </div>

        {/* Trading Hours */}
        <div className="bg-gradient-to-r from-blue-50 to-cyan-50 rounded-lg p-4 border border-blue-200 transform transition-all hover:scale-105">
          <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 block">Trading Hours</label>
          <p className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {profile.trading_hours.start} - {profile.trading_hours.end}
          </p>
        </div>

        {/* Lot Sizes */}
        <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-lg p-4 border border-purple-200 transform transition-all hover:scale-105">
          <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 block">Lot Sizes</label>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white rounded-lg p-3 border border-purple-100 text-center transform transition-all hover:scale-110">
              <span className="text-xs text-gray-500 font-semibold block mb-1">Nifty</span>
              <p className="text-2xl font-bold text-purple-600">{profile.lot_sizes.nifty}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-purple-100 text-center transform transition-all hover:scale-110">
              <span className="text-xs text-gray-500 font-semibold block mb-1">Sensex</span>
              <p className="text-2xl font-bold text-purple-600">{profile.lot_sizes.sensex}</p>
            </div>
          </div>
        </div>

        {/* Indicators */}
        <div className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-lg p-4 border border-indigo-200 transform transition-all hover:scale-105">
          <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 block">Indicator Settings</label>
          <div className="space-y-2">
            <div className="flex justify-between items-center bg-white rounded-lg px-3 py-2 border border-indigo-100">
              <span className="text-sm text-gray-600 font-medium">RSI Threshold:</span>
              <span className="font-bold text-indigo-600 text-lg">{profile.indicators.rsi_threshold}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-lg px-3 py-2 border border-indigo-100">
              <span className="text-sm text-gray-600 font-medium">RSI Period:</span>
              <span className="font-bold text-indigo-600 text-lg">{profile.indicators.rsi_period}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-lg px-3 py-2 border border-indigo-100">
              <span className="text-sm text-gray-600 font-medium">OI SMA Period:</span>
              <span className="font-bold text-indigo-600 text-lg">{profile.indicators.oi_sma_period}</span>
            </div>
          </div>
        </div>

        {/* Risk Management */}
        <div className="bg-gradient-to-r from-orange-50 to-red-50 rounded-lg p-4 border border-orange-200 transform transition-all hover:scale-105">
          <label className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 block">Risk Management</label>
          <div className="space-y-2">
            <div className="flex justify-between items-center bg-white rounded-lg px-3 py-2 border border-orange-100">
              <span className="text-sm text-gray-600 font-medium">Stop Loss:</span>
              <span className="font-bold text-orange-600 text-sm">{profile.risk_management.stop_loss_method}</span>
            </div>
            <div className="flex justify-between items-center bg-white rounded-lg px-3 py-2 border border-orange-100">
              <span className="text-sm text-gray-600 font-medium">Max Positions:</span>
              <span className="font-bold text-orange-600 text-lg">{profile.risk_management.max_positions}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
