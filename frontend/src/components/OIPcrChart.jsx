import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const VIEW_MODES = [
  { key: 'both', label: 'Both' },
  { key: 'full', label: 'Full Chain' },
  { key: 'atm5', label: 'ATM±5' },
];

const OIPcrChart = ({ oiPcrData }) => {
  const [viewMode, setViewMode] = useState('both');

  if (!oiPcrData) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-2xl font-bold mb-4">OI Put-Call Ratio</h2>
        <p className="text-gray-500">Loading OI PCR data...</p>
      </div>
    );
  }

  // Format history data for chart. 'full' is null for historical backfilled
  // points (full-chain PCR isn't backfilled, only ATM+-5 is) - Recharts draws
  // a gap for those rather than connecting across them.
  const formatHistoryData = (history) => {
    return history.map((item, idx) => ({
      time: new Date(item.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      atm5: item.atm5,
      full: item.full,
      index: idx
    }));
  };

  const niftyData = oiPcrData.nifty?.history ? formatHistoryData(oiPcrData.nifty.history) : [];
  const sensexData = oiPcrData.sensex?.history ? formatHistoryData(oiPcrData.sensex.history) : [];
  const bankniftyData = oiPcrData.banknifty?.history ? formatHistoryData(oiPcrData.banknifty.history) : [];

  // Which primary index to pair with BANKNIFTY today, mirroring config.py's
  // NIFTY_TRADING_DAYS=[0,1,4]/SENSEX_TRADING_DAYS=[2,3] (0=Mon..4=Fri there;
  // JS Date.getDay() is 0=Sun..6=Sat, so Nifty days map to 1,2,5 here).
  const dayOfWeek = new Date().getDay();
  const primaryIndex = (dayOfWeek === 3 || dayOfWeek === 4) ? 'sensex' : 'nifty';

  // Coloring/labeling is based on full-chain PCR - the conventional metric
  // (matches Upstox/NSE), not the narrower ATM+-5 window.
  const getPcrColor = (value) => {
    if (!value) return 'text-gray-500';
    if (value < 0.8) return 'text-blue-600'; // Call heavy
    if (value > 1.2) return 'text-red-600';  // Put heavy
    return 'text-green-600'; // Neutral
  };

  const getPcrBgColor = (value) => {
    if (!value) return 'bg-gray-100';
    if (value < 0.8) return 'bg-gradient-to-r from-blue-50 to-cyan-50 border-blue-300';
    if (value > 1.2) return 'bg-gradient-to-r from-red-50 to-rose-50 border-red-300';
    return 'bg-gradient-to-r from-green-50 to-emerald-50 border-green-300';
  };

  const getPcrLabel = (value) => {
    if (!value) return 'N/A';
    if (value < 0.8) return 'Call Heavy';
    if (value > 1.2) return 'Put Heavy';
    return 'Neutral';
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white border-2 border-gray-200 rounded-lg shadow-xl p-3">
          <p className="font-bold text-gray-800 mb-1">{label}</p>
          {payload.map((p) => (
            <p key={p.dataKey} className="text-sm font-bold" style={{ color: p.color }}>
              {p.dataKey === 'full' ? 'Full Chain' : 'ATM±5'}: {p.value != null ? p.value.toFixed(3) : '—'}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const CurrentBadge = ({ atm5, full }) => (
    <div className="text-right bg-white rounded-lg px-4 py-2 border-2 border-gray-200 shadow-md">
      {full != null && (
        <div>
          <span className={`text-2xl font-bold ${getPcrColor(full)}`}>{full.toFixed(3)}</span>
          <span className="text-[10px] text-gray-400 font-semibold ml-1">FULL</span>
          <p className={`text-xs font-bold ${getPcrColor(full)}`}>{getPcrLabel(full)}</p>
        </div>
      )}
      {atm5 != null && (
        <p className="text-xs text-gray-500 font-medium mt-1">
          ATM±5: <span className="font-bold text-gray-700">{atm5.toFixed(3)}</span>
        </p>
      )}
    </div>
  );

  const IndexChart = ({ data, colorFull, colorAtm5 }) => (
    data.length > 0 ? (
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#6b7280' }} stroke="#9ca3af" />
          <YAxis
            domain={[
              (dataMin) => (Math.max(0, dataMin - 0.15)),
              (dataMax) => (dataMax + 0.15)
            ]}
            tickFormatter={(v) => v.toFixed(2)}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            stroke="#9ca3af"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value) => (value === 'full' ? 'Full Chain (matches Upstox/NSE)' : 'ATM±5 window')}
            wrapperStyle={{ fontSize: 11 }}
          />
          {viewMode !== 'atm5' && (
            <Line type="monotone" dataKey="full" stroke={colorFull} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} connectNulls={false} />
          )}
          {viewMode !== 'full' && (
            <Line type="monotone" dataKey="atm5" stroke={colorAtm5} strokeWidth={1.5} strokeDasharray="4 3" dot={false} activeDot={{ r: 4 }} />
          )}
        </LineChart>
      </ResponsiveContainer>
    ) : (
      <div className="text-center py-12">
        <svg className="mx-auto h-12 w-12 text-gray-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <p className="text-gray-400 font-medium">No data available</p>
      </div>
    )
  );

  return (
    <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100 transform transition-all hover:shadow-2xl">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <h2 className="text-3xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
            OI Put-Call Ratio
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Full Chain = every strike (matches Upstox/NSE) · ATM±5 = 11 strikes around spot (dashed)
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 shrink-0">
          {VIEW_MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => setViewMode(m.key)}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${
                viewMode === m.key
                  ? 'bg-white text-gray-800 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Primary index PCR - NIFTY on Fri/Mon/Tue, SENSEX on Wed/Thu */}
        {primaryIndex === 'nifty' ? (
          <div className={`border-2 rounded-xl p-5 ${getPcrBgColor(oiPcrData.nifty?.current_full)} transform transition-all hover:scale-105`}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-xl text-gray-800 flex items-center gap-2">
                <span className="w-3 h-3 bg-blue-500 rounded-full animate-pulse"></span>
                NIFTY
              </h3>
              <CurrentBadge atm5={oiPcrData.nifty?.current_atm5} full={oiPcrData.nifty?.current_full} />
            </div>
            <IndexChart data={niftyData} colorFull="#3b82f6" colorAtm5="#93c5fd" />
          </div>
        ) : (
          <div className={`border-2 rounded-xl p-5 ${getPcrBgColor(oiPcrData.sensex?.current_full)} transform transition-all hover:scale-105`}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-xl text-gray-800 flex items-center gap-2">
                <span className="w-3 h-3 bg-purple-500 rounded-full animate-pulse"></span>
                SENSEX
              </h3>
              <CurrentBadge atm5={oiPcrData.sensex?.current_atm5} full={oiPcrData.sensex?.current_full} />
            </div>
            <IndexChart data={sensexData} colorFull="#8b5cf6" colorAtm5="#d8b4fe" />
          </div>
        )}

        {/* Bank Nifty PCR - shown every day alongside whichever index is trading */}
        <div className={`border-2 rounded-xl p-5 ${getPcrBgColor(oiPcrData.banknifty?.current_full)} transform transition-all hover:scale-105`}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-bold text-xl text-gray-800 flex items-center gap-2">
              <span className="w-3 h-3 bg-amber-500 rounded-full animate-pulse"></span>
              BANKNIFTY
            </h3>
            <CurrentBadge atm5={oiPcrData.banknifty?.current_atm5} full={oiPcrData.banknifty?.current_full} />
          </div>
          <IndexChart data={bankniftyData} colorFull="#f59e0b" colorAtm5="#fcd34d" />
        </div>
      </div>

      {/* Legend */}
      <div className="mt-6 bg-gradient-to-r from-gray-50 to-gray-100 rounded-xl p-4 border border-gray-200">
        <p className="text-sm font-bold text-gray-700 mb-3">PCR Interpretation (Full Chain):</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-white rounded-lg p-3 border-2 border-blue-200 transform transition-all hover:scale-105">
            <span className="text-blue-600 font-bold">PCR &lt; 0.8</span>
            <p className="text-xs text-gray-600 mt-1">Call heavy (bullish sentiment)</p>
          </div>
          <div className="bg-white rounded-lg p-3 border-2 border-green-200 transform transition-all hover:scale-105">
            <span className="text-green-600 font-bold">0.8 ≤ PCR ≤ 1.2</span>
            <p className="text-xs text-gray-600 mt-1">Neutral zone</p>
          </div>
          <div className="bg-white rounded-lg p-3 border-2 border-red-200 transform transition-all hover:scale-105">
            <span className="text-red-600 font-bold">PCR &gt; 1.2</span>
            <p className="text-xs text-gray-600 mt-1">Put heavy (bearish sentiment)</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OIPcrChart;
