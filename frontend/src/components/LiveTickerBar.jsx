import React, { useState, useEffect, useRef, useMemo } from 'react';

const LiveTickerBar = ({ ticks, connected, error, tickCount, selectedInstruments, onTickerClick }) => {

    // Helper to get formatted name and group
    const getInstrumentDetails = (key) => {
        if (!selectedInstruments) return { name: key, group: 'other' };

        // Check Nifty Index
        if (key === 'IDX_I|13') return { name: 'NIFTY 50', group: 'nifty', type: 'INDEX' };

        // Check Sensex Index
        if (key === 'IDX_I|51') return { name: 'SENSEX', group: 'sensex', type: 'INDEX' };

        // Check Nifty Options
        if (selectedInstruments.nifty) {
            if (key === selectedInstruments.nifty.call_instrument_key) {
                return { name: `${selectedInstruments.nifty.call_strike} CE`, group: 'nifty', type: 'CE' };
            }
            if (key === selectedInstruments.nifty.put_instrument_key) {
                return { name: `${selectedInstruments.nifty.put_strike} PE`, group: 'nifty', type: 'PE' };
            }
        }

        // Check Sensex Options
        if (selectedInstruments.sensex) {
            if (key === selectedInstruments.sensex.call_instrument_key) {
                return { name: `${selectedInstruments.sensex.call_strike} CE`, group: 'sensex', type: 'CE' };
            }
            if (key === selectedInstruments.sensex.put_instrument_key) {
                return { name: `${selectedInstruments.sensex.put_strike} PE`, group: 'sensex', type: 'PE' };
            }
        }

        // Default fallback
        const label = key.includes('|') ? key.split('|')[1] : key;
        return { name: label, group: 'other', type: 'OTHER' };
    };

    const groupedTicks = useMemo(() => {
        const nifty = [];
        const sensex = [];
        const other = [];

        const predefinedKeys = new Set();

        predefinedKeys.add('IDX_I|13');
        predefinedKeys.add('IDX_I|51');

        if (selectedInstruments?.nifty) {
            if (selectedInstruments.nifty.call_instrument_key) predefinedKeys.add(selectedInstruments.nifty.call_instrument_key);
            if (selectedInstruments.nifty.put_instrument_key) predefinedKeys.add(selectedInstruments.nifty.put_instrument_key);
        }

        if (selectedInstruments?.sensex) {
            if (selectedInstruments.sensex.call_instrument_key) predefinedKeys.add(selectedInstruments.sensex.call_instrument_key);
            if (selectedInstruments.sensex.put_instrument_key) predefinedKeys.add(selectedInstruments.sensex.put_instrument_key);
        }

        // Add predefined ones first
        predefinedKeys.forEach(key => {
            const tick = ticks?.[key] || { ltp: null, cp: null, close: null, oi: null, volume: null };
            const details = getInstrumentDetails(key);
            const item = { key, tick, ...details };

            if (details.group === 'nifty') nifty.push(item);
            else if (details.group === 'sensex') sensex.push(item);
            else other.push(item);
        });

        // Add any remaining ones from ticks
        Object.entries(ticks || {}).forEach(([key, tick]) => {
            if (!tick || predefinedKeys.has(key)) return;

            const details = getInstrumentDetails(key);
            const item = { key, tick, ...details };

            if (details.group === 'nifty') nifty.push(item);
            else if (details.group === 'sensex') sensex.push(item);
            else other.push(item);
        });

        // Sort: Index first, then CE, then PE (arbitrary but consistent)
        const sortFn = (a, b) => {
            if (a.type === 'INDEX') return -1;
            if (b.type === 'INDEX') return 1;
            if (a.type === 'CE' && b.type === 'PE') return -1;
            if (a.type === 'PE' && b.type === 'CE') return 1;
            return 0;
        };

        return {
            nifty: nifty.sort(sortFn),
            sensex: sensex.sort(sortFn),
            other
        };
    }, [ticks, selectedInstruments]);

    return (
        <div className="bg-gradient-to-r from-gray-900 via-slate-900 to-gray-900 rounded-xl shadow-2xl border border-gray-700/50 overflow-hidden flex flex-col w-full">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-2 border-b border-gray-700/50 bg-black/20">
                <div className="flex items-center gap-3">
                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                        Live Feed
                    </h3>
                    <span className="text-[10px] text-gray-600 font-mono">
                        {tickCount > 0 ? `${tickCount} ticks` : ''}
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    {error && (
                        <span className="text-[10px] text-amber-400 font-medium">{error}</span>
                    )}
                    <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${connected
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-red-500/10 text-red-400 border border-red-500/20'
                        }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
                            }`}></span>
                        {connected ? 'LIVE' : 'OFF'}
                    </div>
                </div>
            </div>

            <div className="flex flex-col w-full">
                {/* Row 1: Nifty */}
                {groupedTicks.nifty.length > 0 && (
                    <div className="flex items-stretch border-b border-gray-700/30 min-h-[60px] w-full">
                        <div className="w-20 bg-blue-900/20 flex items-center justify-center border-r border-gray-700/30 px-2 shrink-0">
                            <span className="text-xs font-bold text-blue-400">NIFTY</span>
                        </div>
                        <div className="flex-1 flex w-full">
                            {groupedTicks.nifty.map((item) => (
                                <TickCard
                                    key={item.key}
                                    label={item.name}
                                    tick={item.tick}
                                    type={item.type}
                                    onClick={() => onTickerClick && onTickerClick(item)}
                                />
                            ))}
                        </div>
                    </div>
                )}

                {/* Row 2: Sensex */}
                {groupedTicks.sensex.length > 0 && (
                    <div className="flex items-stretch min-h-[60px] w-full">
                        <div className="w-20 bg-purple-900/20 flex items-center justify-center border-r border-gray-700/30 px-2 shrink-0">
                            <span className="text-xs font-bold text-purple-400">SENSEX</span>
                        </div>
                        <div className="flex-1 flex w-full">
                            {groupedTicks.sensex.map((item) => (
                                <TickCard
                                    key={item.key}
                                    label={item.name}
                                    tick={item.tick}
                                    type={item.type}
                                    onClick={() => onTickerClick && onTickerClick(item)}
                                />
                            ))}
                        </div>
                    </div>
                )}

                {/* Fallback for others/loading */}
                {groupedTicks.nifty.length === 0 && groupedTicks.sensex.length === 0 && (
                    <div className="px-5 py-6 text-center text-gray-500 text-sm">
                        {connected ? 'Waiting for data...' : 'No live data available'}
                    </div>
                )}
            </div>
        </div>
    );
};


const TickCard = ({ label, tick, type, onClick }) => {
    const [flash, setFlash] = useState(null); // 'up' | 'down' | null
    const prevLtpRef = useRef(tick?.ltp);

    useEffect(() => {
        if (tick?.ltp && tick.ltp !== prevLtpRef.current) {
            setFlash(tick.ltp > prevLtpRef.current ? 'up' : 'down');
            prevLtpRef.current = tick.ltp;
            const t = setTimeout(() => setFlash(null), 600);
            return () => clearTimeout(t);
        }
    }, [tick?.ltp]);

    const ltp = tick?.ltp;
    const change = ltp ? ltp - (tick.cp || tick.close || 0) : 0;
    const changePct = (ltp && tick?.cp) ? ((change / tick.cp) * 100) : 0;
    const isPositive = change >= 0;

    const flashBg = flash === 'up'
        ? 'bg-emerald-500/10'
        : flash === 'down'
            ? 'bg-red-500/10'
            : '';

    // Type Badge Color
    const typeColor = type === 'INDEX' ? 'text-gray-400'
        : type === 'CE' ? 'text-green-400'
            : type === 'PE' ? 'text-red-400'
                : 'text-gray-400';

    return (
        <div
            onClick={onClick}
            className={`flex-1 flex flex-col justify-center px-4 py-2 border-r border-gray-700/30 min-w-[140px] transition-all duration-300 cursor-pointer hover:bg-white/5 ${flashBg}`}
        >
            <div className="flex items-baseline justify-between mb-1">
                <span className={`text-xs font-bold truncate ${typeColor}`} title={label}>
                    {label}
                </span>
                <span className={`text-[10px] font-bold ${ltp ? (isPositive ? 'text-emerald-400' : 'text-red-400') : 'text-gray-500'}`}>
                    {ltp ? `${changePct.toFixed(2)}%` : '—'}
                </span>
            </div>

            <div className="flex items-center justify-between">
                <span className={`text-base font-bold tabular-nums ${flash === 'up' ? 'text-emerald-400' : flash === 'down' ? 'text-red-400' : 'text-gray-400'
                    }`}>
                    {ltp ? ltp.toFixed(2) : '—'}
                </span>
            </div>

            <div className="flex justify-between items-center text-[9px] text-gray-500 mt-1">
                <span>OI: {tick?.oi ? (tick.oi / 1000).toFixed(0) + 'K' : '-'}</span>
                <span>IV: {tick?.iv ? tick.iv.toFixed(1) + '%' : '-'}</span>
            </div>
        </div>
    );
};

export default LiveTickerBar;
