import React, { useState, useMemo } from 'react';

const TradeHistoryTable = ({ trades, onRowClick }) => {
    const [strategyFilter, setStrategyFilter] = useState('ALL');
    if (!trades || trades.length === 0) {
        return (
            <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100 mt-8">
                <h2 className="text-2xl font-bold mb-4">Trade History (Today)</h2>
                <div className="text-center py-8">
                    <p className="text-gray-500">No trades recorded for today yet.</p>
                </div>
            </div>
        );
    }

    // Flatten trades into events
    const events = [];
    trades.forEach(trade => {
        if (trade.is_spread) {
            // Credit spread: real leg-by-leg execution sequence.
            // Entry: hedge (far) leg is BOUGHT first, near leg is SOLD second
            // (the only failure mode is then an unwanted long, never a naked short).
            // Exit: near leg is BOUGHT BACK first, hedge (far) leg is SOLD second.
            const lot = trade.lot_size || 0;
            const farEntry = trade.far_entry_price || 0;
            const nearEntry = trade.entry_price || 0;

            events.push({
                id: `entry-far-${trade.trade_id}`,
                trade_id: trade.trade_id,
                action: 'BUY',
                leg: 'HEDGE',
                symbol: trade.symbol,
                type: trade.far_option_type,
                strike: trade.far_strike,
                price: farEntry,
                qty: lot,
                time: trade.entry_time,
                reason: 'Entry — Hedge Leg',
                aiReasoning: trade.entry_reason,
                strategy_tag: trade.strategy_tag,
                instrument_key: trade.far_instrument_key,
                isEntry: true
            });
            events.push({
                id: `entry-near-${trade.trade_id}`,
                trade_id: trade.trade_id,
                action: 'SELL',
                leg: 'SOLD',
                symbol: trade.symbol,
                type: trade.type,
                strike: trade.strike,
                price: nearEntry,
                qty: lot,
                time: trade.entry_time,
                reason: 'Entry — Sold Leg',
                aiReasoning: trade.entry_reason,
                strategy_tag: trade.strategy_tag,
                instrument_key: trade.instrument_key,
                isEntry: true
            });

            if (trade.status === 'CLOSED' && trade.exit_price != null) {
                const nearExit = trade.exit_price;
                const farExit = trade.far_exit_price || 0;
                // Split the backend's combined net-credit P&L across the two legs
                // (their sum reproduces trade.pnl exactly) so each row shows its
                // own realized result, same as the live per-leg Positions view.
                const nearLegPnl = (nearEntry - nearExit) * lot;
                const farLegPnl = (farExit - farEntry) * lot;

                events.push({
                    id: `exit-near-${trade.trade_id}`,
                    trade_id: trade.trade_id,
                    action: 'BUY',
                    leg: 'SOLD',
                    symbol: trade.symbol,
                    type: trade.type,
                    strike: trade.strike,
                    price: nearExit,
                    qty: lot,
                    time: trade.exit_time,
                    reason: `${trade.exit_reason || 'Exit'} — Buy Back`,
                    aiReasoning: trade.exit_reasoning,
                    pnl: nearLegPnl,
                    pnl_percent: nearEntry > 0 ? (nearLegPnl / (nearEntry * lot)) * 100 : 0,
                    strategy_tag: trade.strategy_tag,
                    instrument_key: trade.instrument_key
                });
                events.push({
                    id: `exit-far-${trade.trade_id}`,
                    trade_id: trade.trade_id,
                    action: 'SELL',
                    leg: 'HEDGE',
                    symbol: trade.symbol,
                    type: trade.far_option_type,
                    strike: trade.far_strike,
                    price: farExit,
                    qty: lot,
                    time: trade.exit_time,
                    reason: `${trade.exit_reason || 'Exit'} — Hedge Close`,
                    aiReasoning: trade.exit_reasoning,
                    pnl: farLegPnl,
                    pnl_percent: farEntry > 0 ? (farLegPnl / (farEntry * lot)) * 100 : 0,
                    strategy_tag: trade.strategy_tag,
                    instrument_key: trade.far_instrument_key,
                    netPnl: trade.pnl,
                    netPnlPercent: trade.pnl_percent,
                    isLastLeg: true
                });
            }
            return;
        }

        // Legacy single-leg trade (not expected in normal operation anymore)
        // 1. Initial Entry (BUY)
        const partialQty = (trade.partial_exits || []).reduce((sum, pe) => sum + (pe.lots_sold || 0), 0);
        const initialQty = partialQty + (trade.lot_size || 0);

        events.push({
            id: `entry-${trade.trade_id}`,
            trade_id: trade.trade_id,
            action: 'BUY',
            symbol: trade.symbol,
            type: trade.type,
            strike: trade.strike,
            price: trade.entry_price,
            qty: initialQty,
            time: trade.entry_time,
            reason: 'Initial Entry',
            aiReasoning: trade.entry_reason,
            strategy_tag: trade.strategy_tag,
            instrument_key: trade.instrument_key,
            isEntry: true
        });

        // 2. Partial Exits (SELL)
        (trade.partial_exits || []).forEach((pe, idx) => {
            events.push({
                id: `pe-${trade.trade_id}-${idx}`,
                trade_id: trade.trade_id,
                action: 'SELL',
                symbol: trade.symbol,
                type: trade.type,
                strike: trade.strike,
                price: pe.exit_price,
                qty: pe.lots_sold,
                time: pe.exit_time,
                reason: pe.exit_reason,
                aiReasoning: pe.exit_reasoning,
                pnl: pe.pnl,
                strategy_tag: trade.strategy_tag,
                instrument_key: trade.instrument_key,
                pnl_percent: ((pe.exit_price - trade.entry_price) / trade.entry_price) * 100
            });
        });

        // 3. Final Exit (SELL) - if closed
        if (trade.status === 'CLOSED' && trade.exit_price) {
            events.push({
                id: `exit-${trade.trade_id}`,
                trade_id: trade.trade_id,
                action: 'SELL',
                symbol: trade.symbol,
                type: trade.type,
                strike: trade.strike,
                price: trade.exit_price,
                qty: trade.lot_size,
                time: trade.exit_time,
                reason: trade.exit_reason,
                aiReasoning: trade.exit_reasoning,
                pnl: trade.pnl,
                strategy_tag: trade.strategy_tag,
                instrument_key: trade.instrument_key,
                pnl_percent: trade.pnl_percent
            });
        }
    });

    // Extract unique strategy tags for the dropdown filter
    const strategyTags = useMemo(() => {
        const tags = new Set();
        events.forEach(event => {
            if (event.strategy_tag) {
                // Remove the 'STRATEGY_' prefix for display if needed
                tags.add(event.strategy_tag);
            }
        });
        return Array.from(tags).sort();
    }, [events]);

    // Sort events by time (descending) so latest activity is at the top
    const sortedEvents = useMemo(() => {
        let filteredEvents = events;
        if (strategyFilter !== 'ALL') {
            filteredEvents = events.filter(e => e.strategy_tag === strategyFilter);
        }

        return [...filteredEvents].sort((a, b) => {
            // Compare times (HH:MM:SS format)
            if (b.time !== a.time) return b.time.localeCompare(a.time);
            return 0;
        });
    }, [events, strategyFilter]);

    return (
        <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100 mt-8 transform transition-all hover:shadow-2xl">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-3xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
                    Transactional History
                </h2>
                <div className="flex items-center gap-4">
                    <select
                        value={strategyFilter}
                        onChange={(e) => setStrategyFilter(e.target.value)}
                        className="bg-gray-50 border border-gray-200 text-gray-700 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block p-2 font-semibold"
                    >
                        <option value="ALL">All Strategies</option>
                        {strategyTags.map(tag => (
                            <option key={tag} value={tag}>
                                {tag.replace('STRATEGY_', '')}
                            </option>
                        ))}
                    </select>
                    <span className="bg-gray-100 text-gray-700 px-4 py-2 rounded-full text-sm font-bold shadow-sm">
                        {sortedEvents.length} Events
                    </span>
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                        <tr>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Time</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Action</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Strategy</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Symbol</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Strike</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Qty</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Price</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Reason</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">AI Analysis</th>
                            <th className="px-4 py-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Realized P&L</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                        {sortedEvents.map((event, idx) => {
                            const isBuy = event.action === 'BUY';
                            const pnlColor = event.pnl >= 0 ? 'text-green-700' : 'text-red-700';
                            const pnlBg = event.pnl >= 0 ? 'bg-green-50' : 'bg-red-50';

                            // Grouping indicator: check if next event is same trade_id
                            const isLastOfTrade = idx === sortedEvents.length - 1 || sortedEvents[idx + 1].trade_id !== event.trade_id;

                            return (
                                <tr key={event.id} className={`${isBuy ? 'bg-white' : 'bg-gray-50/30'} hover:bg-blue-50/50 transition-colors cursor-pointer ${isLastOfTrade ? 'border-b-2 border-gray-200' : ''}`}
                                    onClick={() => onRowClick && event.instrument_key && onRowClick(event)}
                                    title={event.instrument_key ? 'Click to view chart' : ''}
                                >
                                    <td className="px-4 py-4 whitespace-nowrap text-xs text-gray-500 font-medium">
                                        {event.time}
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap">
                                        <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border ${isBuy ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'
                                            }`}>
                                            {event.action}
                                        </span>
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap">
                                        {(() => {
                                            const tag = event.strategy_tag || '';
                                            let colorClass = 'bg-gray-100 text-gray-700 border-gray-200';
                                            if (tag.includes('STAGE')) colorClass = 'bg-indigo-100 text-indigo-700 border-indigo-200';
                                            else if (tag.includes('TRAIL')) colorClass = 'bg-emerald-100 text-emerald-700 border-emerald-200';
                                            else if (tag.includes('HYBRID')) colorClass = 'bg-amber-100 text-amber-700 border-amber-200';

                                            return (
                                                <span className={`px-2 py-1 rounded-md text-[10px] font-black tracking-widest uppercase border ${colorClass}`}>
                                                    {tag.replace('STRATEGY_', '')}
                                                </span>
                                            );
                                        })()}
                                    </td>

                                    <td className="px-4 py-4 whitespace-nowrap">
                                        <div className="flex items-center gap-1.5">
                                            <div className="font-bold text-gray-800">{event.symbol}</div>
                                            {event.instrument_key && (
                                                <svg className="w-3.5 h-3.5 text-blue-400 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                                                </svg>
                                            )}
                                        </div>
                                        <div className={`text-[10px] font-bold ${event.type === 'CALL' ? 'text-blue-600' : 'text-purple-600'}`}>
                                            {event.type}
                                        </div>
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap font-semibold text-gray-700">
                                        {event.strike}
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap font-bold text-gray-800">
                                        {event.qty}
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap font-medium text-gray-700">
                                        ₹{event.price.toFixed(2)}
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap text-xs">
                                        <span className={`px-2 py-1 rounded font-bold uppercase ${isBuy ? 'bg-gray-100 text-gray-600' :
                                            event.reason?.includes('Target') ? 'bg-emerald-100 text-emerald-700' :
                                                event.reason?.includes('SL') ? 'bg-rose-100 text-rose-700' :
                                                    'bg-blue-100 text-blue-700'
                                            }`}>
                                            {event.reason}
                                        </span>
                                    </td>
                                    <td className="px-4 py-4 text-xs text-gray-600 max-w-xs truncate" title={event.aiReasoning}>
                                        {event.aiReasoning && event.aiReasoning !== '-' ? (
                                            <span className="font-mono bg-yellow-50 text-yellow-800 px-2 py-1 rounded border border-yellow-100 text-[10px]">
                                                {event.aiReasoning}
                                            </span>
                                        ) : (
                                            <span className="text-gray-300">-</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-4 whitespace-nowrap font-bold">
                                        {!isBuy && event.pnl !== undefined ? (
                                            <div className={`${pnlBg} ${pnlColor} px-2 py-1 rounded inline-block`}>
                                                {event.pnl >= 0 ? '+' : ''}₹{event.pnl.toFixed(2)}
                                                <span className="ml-1 text-[10px] opacity-70">
                                                    ({event.pnl_percent >= 0 ? '+' : ''}{event.pnl_percent.toFixed(2)}%)
                                                </span>
                                            </div>
                                        ) : (
                                            <span className="text-gray-300">—</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default TradeHistoryTable;
