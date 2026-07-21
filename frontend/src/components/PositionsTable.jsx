import React, { useState, useEffect, useRef } from 'react';

const PositionsTable = ({ positions, liveTicks = {}, onRowClick }) => {
  if (!positions || positions.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100">
        <h2 className="text-2xl font-bold mb-4">Current Positions</h2>
        <div className="text-center py-12">
          <svg className="mx-auto h-16 w-16 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          <p className="text-gray-500 font-medium">No open positions</p>
          <p className="text-gray-400 text-sm mt-1">Positions will appear here when trades are active</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100 transform transition-all hover:shadow-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-3xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
          Current Positions
        </h2>
        <div className="flex items-center gap-3">
          {Object.keys(liveTicks).length > 0 && (
            <span className="flex items-center gap-1.5 bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-full text-xs font-bold border border-emerald-200">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
              LIVE
            </span>
          )}
          <span className="bg-gradient-to-r from-blue-500 to-indigo-500 text-white px-4 py-2 rounded-full text-sm font-bold shadow-lg">
            {positions.length} Active
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Instrument</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Txn</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Qty</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Avg Price</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">
                <span className="flex items-center gap-1">
                  LTP
                  {Object.keys(liveTicks).length > 0 && (
                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                  )}
                </span>
              </th>
              <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">P&L</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {positions.map((pos, idx) => (
              <PositionGroup key={idx} pos={pos} liveTicks={liveTicks} onClick={onRowClick} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Flash-on-change price cell
const useFlash = (price) => {
  const [flash, setFlash] = useState(null);
  const prevRef = useRef(null);
  useEffect(() => {
    if (price != null && prevRef.current !== null && price !== prevRef.current) {
      setFlash(price > prevRef.current ? 'up' : 'down');
      const t = setTimeout(() => setFlash(null), 500);
      prevRef.current = price;
      return () => clearTimeout(t);
    }
    prevRef.current = price;
  }, [price]);
  return flash;
};

const LegRow = ({ symbol, strike, optionType, txn, qty, avgPrice, ltp, isLive, pnl, onClick, instrumentKey, groupBorder }) => {
  const flash = useFlash(ltp);
  const isBuy = txn === 'BUY';
  const pnlColor = pnl >= 0 ? 'text-emerald-700' : 'text-red-700';

  return (
    <tr
      onClick={() => onClick && onClick(instrumentKey)}
      className={`hover:bg-blue-50/40 transition-colors cursor-pointer ${groupBorder}`}
    >
      <td className="px-4 py-2.5 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-800 text-sm">{symbol} {strike}</span>
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-black ${optionType === 'CE' || optionType === 'CALL' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
            {optionType}
          </span>
        </div>
      </td>
      <td className="px-4 py-2.5 whitespace-nowrap">
        <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider border ${isBuy ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
          {txn}
        </span>
      </td>
      <td className={`px-4 py-2.5 whitespace-nowrap text-sm font-bold tabular-nums ${isBuy ? 'text-emerald-700' : 'text-red-700'}`}>
        {isBuy ? '+' : '-'}{Math.abs(qty)}
      </td>
      <td className="px-4 py-2.5 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
        ₹{avgPrice.toFixed(2)}
      </td>
      <td className="px-4 py-2.5 whitespace-nowrap">
        {ltp != null ? (
          <div className="flex items-center gap-1.5">
            <span className={`text-sm font-bold tabular-nums transition-colors duration-300 ${flash === 'up' ? 'text-emerald-600' : flash === 'down' ? 'text-red-600' : 'text-gray-800'}`}>
              ₹{ltp.toFixed(2)}
            </span>
            {isLive && <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" title="Live price"></span>}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">—</span>
        )}
      </td>
      <td className={`px-4 py-2.5 whitespace-nowrap text-sm font-bold ${pnlColor}`}>
        {pnl != null ? `${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)}` : '—'}
      </td>
    </tr>
  );
};

const PositionGroup = ({ pos, liveTicks, onClick }) => {
  const isSpread = !!pos.is_spread;
  const lotSize = pos.lot_size || 1;

  if (!isSpread) {
    // Legacy single-leg fallback (not expected in normal operation anymore)
    const tick = liveTicks[pos.instrument_key];
    const livePrice = tick?.ltp ?? pos.current_price;
    const entryPrice = pos.entry_price || 0;
    const pnl = (livePrice != null ? livePrice - entryPrice : 0) * lotSize;
    return (
      <>
        <GroupHeader pos={pos} combinedPnl={pnl} slReferenceValue={livePrice} />
        <LegRow
          symbol={pos.symbol} strike={pos.strike} optionType={pos.option_type}
          txn="BUY" qty={lotSize} avgPrice={entryPrice} ltp={livePrice ?? null}
          isLive={!!tick?.ltp} pnl={pnl}
          onClick={(key) => onClick && onClick({ symbol: pos.symbol, instrument_key: key })}
          instrumentKey={pos.instrument_key}
        />
      </>
    );
  }

  // Credit spread: two legs, Kite-style.
  // Entry sequence: hedge (far) leg BOUGHT first, near leg SOLD second.
  // Exit sequence: near leg BOUGHT back first, far leg (hedge) SOLD second.
  const nearTick = liveTicks[pos.instrument_key];
  const farTick = liveTicks[pos.far_instrument_key];

  const nearLtp = nearTick?.ltp ?? pos.current_near_price ?? null;
  const farLtp = farTick?.ltp ?? pos.current_far_price ?? null;

  const nearEntry = pos.entry_price || 0;
  const farEntry = pos.far_entry_price || 0;

  const farPnl = farLtp != null ? (farLtp - farEntry) * lotSize : null;
  const nearPnl = nearLtp != null ? (nearEntry - nearLtp) * lotSize : null;

  const netSpreadValue = (nearLtp != null && farLtp != null) ? (nearLtp - farLtp) : null;
  const combinedPnl = pos.pnl ?? ((farPnl != null && nearPnl != null) ? farPnl + nearPnl : null);

  return (
    <>
      {/* SL is based on the near leg's own price (see order_manager.py stop_loss_value), not net spread value */}
      <GroupHeader pos={pos} combinedPnl={combinedPnl} slReferenceValue={nearLtp} />
      <LegRow
        symbol={pos.symbol} strike={pos.far_strike} optionType={pos.far_option_type}
        txn="BUY" qty={lotSize} avgPrice={farEntry} ltp={farLtp}
        isLive={!!farTick?.ltp} pnl={farPnl}
        onClick={(key) => onClick && onClick({ symbol: pos.symbol, instrument_key: key })}
        instrumentKey={pos.far_instrument_key} groupBorder="border-l-4 border-l-teal-200"
      />
      <LegRow
        symbol={pos.symbol} strike={pos.strike} optionType={pos.option_type}
        txn="SELL" qty={lotSize} avgPrice={nearEntry} ltp={nearLtp}
        isLive={!!nearTick?.ltp} pnl={nearPnl}
        onClick={(key) => onClick && onClick({ symbol: pos.symbol, instrument_key: key })}
        instrumentKey={pos.instrument_key} groupBorder="border-l-4 border-l-teal-200"
      />
    </>
  );
};

const GroupHeader = ({ pos, combinedPnl, slReferenceValue }) => {
  const isSpread = !!pos.is_spread;
  const stopLoss = isSpread ? (pos.stop_loss_value || 0) : (pos.stop_loss || 0);
  const target = isSpread ? (pos.profit_target_value || 0) : null;

  const slDistance = isSpread
    ? (stopLoss > 0 && slReferenceValue != null ? ((stopLoss - slReferenceValue) / stopLoss) * 100 : null)
    : (slReferenceValue != null && stopLoss > 0 ? ((slReferenceValue - stopLoss) / slReferenceValue) * 100 : null);
  const isNearSL = slDistance !== null && slDistance < 5;
  const isSLHit = slDistance !== null && slDistance <= 0;

  const pnlColor = (combinedPnl ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-700';
  const pnlBg = (combinedPnl ?? 0) >= 0 ? 'bg-emerald-50' : 'bg-red-50';

  return (
    <tr className="bg-gray-50/70">
      <td colSpan={6} className="px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-800">{pos.symbol}</span>
            {(() => {
              const tag = pos.strategy_tag || '';
              return (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-black tracking-widest uppercase border bg-gray-100 text-gray-700 border-gray-200">
                  {tag.replace('STRATEGY_', '')}
                </span>
              );
            })()}
            {isSpread && (
              <span className="px-2.5 py-1 rounded-lg text-[10px] font-bold border-2 bg-gradient-to-r from-teal-100 to-emerald-100 text-teal-800 border-teal-300">
                {pos.spread_type === 'BULL_PUT' ? 'BULL PUT SPREAD' : pos.spread_type === 'BEAR_CALL' ? 'BEAR CALL SPREAD' : pos.spread_type}
              </span>
            )}
            {isSpread && (
              <span className="text-xs text-gray-500 font-medium">
                Net Credit: <span className="font-bold text-gray-700">₹{(pos.net_credit || 0).toFixed(2)}</span>
              </span>
            )}
            {isSpread && stopLoss > 0 && (
              <span className="text-xs text-gray-500 font-medium">
                SL: <span className={`font-bold ${isSLHit ? 'text-red-600' : isNearSL ? 'text-amber-600' : 'text-gray-700'}`}>₹{stopLoss.toFixed(2)}</span>
                {isSLHit && <span className="ml-1 px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold rounded animate-pulse">HIT</span>}
                {isNearSL && !isSLHit && <span className="ml-1 px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold rounded">NEAR</span>}
                {pos.trailing_active && (
                  <span className="ml-1 px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[9px] font-bold rounded border border-blue-300 inline-flex items-center gap-0.5">
                    <svg className="w-2 h-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                    </svg>
                    TRAILING
                  </span>
                )}
              </span>
            )}
            {isSpread && target > 0 && (
              <span className="text-xs text-gray-500 font-medium">
                Target: <span className="font-bold text-gray-700">₹{target.toFixed(2)}</span>
              </span>
            )}
            <span className="text-xs text-gray-400">{pos.time_in_trade}</span>
          </div>
          <div className={`px-3 py-1 rounded-lg font-bold text-sm ${pnlBg} ${pnlColor}`}>
            {combinedPnl != null ? `${combinedPnl >= 0 ? '+' : ''}₹${combinedPnl.toFixed(2)}` : '—'}
            {pos.pnl_percent != null && (
              <span className="ml-1 text-xs font-semibold opacity-70">
                ({pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
};

export default PositionsTable;
