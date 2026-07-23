import { useState, useEffect, useCallback, useRef } from 'react';
import apiService from '../api';

const BUILDING_POLL_MS = 3000;

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX'];
const TIMEFRAMES = [
    { key: '5min', label: '5 min' },
    { key: '15min', label: '15 min' },
];

// BUY = green, SELL = red, NEUTRAL/unknown = gray - matches the reference
// tool's Option Signal / VWAP Signal badge coloring.
const signalBadgeClass = (signal) => {
    if (signal === 'BUY') return 'bg-emerald-50 text-emerald-700 border-emerald-300';
    if (signal === 'SELL') return 'bg-red-50 text-red-700 border-red-300';
    if (signal === 'NEUTRAL') return 'bg-gray-100 text-gray-600 border-gray-200';
    return 'bg-gray-100 text-gray-400 border-gray-200';
};

const SignalBadge = ({ signal }) => (
    <span className={`px-2.5 py-1 rounded-lg text-xs font-black border-2 ${signalBadgeClass(signal)}`}>
        {signal || 'N/A'}
    </span>
);

const TabButton = ({ active, onClick, children }) => (
    <button
        type="button"
        onClick={onClick}
        className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${active
            ? 'bg-white text-gray-800 shadow-sm'
            : 'text-gray-500 hover:text-gray-700'
            }`}
    >
        {children}
    </button>
);

const fmtOi = (value) => (value == null ? '—' : Math.round(value).toLocaleString('en-IN'));
const fmtNum = (value, digits = 2) => (value == null ? '—' : value.toFixed(digits));

const HistoryRow = ({ row }) => {
    const time = new Date(row.time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
    return (
        <tr className="hover:bg-blue-50/40 transition-colors">
            <td className="px-4 py-2.5 text-sm font-semibold text-gray-700 whitespace-nowrap">{time}</td>
            <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">{fmtOi(row.call_oi)}</td>
            <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">{fmtOi(row.put_oi)}</td>
            <td className={`px-4 py-2.5 text-sm font-semibold tabular-nums ${row.diff < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                {row.diff == null ? '—' : (row.diff >= 0 ? '+' : '') + Math.round(row.diff).toLocaleString('en-IN')}
            </td>
            <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">{fmtNum(row.pcr, 3)}</td>
            <td className="px-4 py-2.5"><SignalBadge signal={row.option_signal} /></td>
            <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">{fmtNum(row.price)}</td>
            <td className="px-4 py-2.5 text-sm text-gray-700 tabular-nums">{fmtNum(row.vwap)}</td>
            <td className="px-4 py-2.5"><SignalBadge signal={row.vwap_signal} /></td>
        </tr>
    );
};

function Scanner() {
    const [symbol, setSymbol] = useState('NIFTY');
    const [timeframe, setTimeframe] = useState('15min');
    const [rows, setRows] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);

    // Tracks the symbol/timeframe this component currently cares about, so a
    // slow poll chain for a selection the user has since switched away from
    // doesn't clobber state when it eventually resolves.
    const selectionRef = useRef({ symbol, timeframe });
    const pollTimeoutRef = useRef(null);

    const fetchData = useCallback(async (sym, tf, { showSpinner }) => {
        if (showSpinner) setLoading(true);
        const isCurrent = () => selectionRef.current.symbol === sym && selectionRef.current.timeframe === tf;
        try {
            const data = await apiService.getTrendScanner(sym, tf);
            if (!isCurrent()) return;

            if (data.status === 'building') {
                // Backend is reconstructing the day's option chain in a
                // background thread (30s-4min) - each poll here is a fast,
                // near-instant round trip, so it never holds one of the
                // browser's per-origin connection slots open for long.
                pollTimeoutRef.current = setTimeout(
                    () => fetchData(sym, tf, { showSpinner: false }),
                    BUILDING_POLL_MS
                );
                return;
            }

            setRows(data.rows || []);
            setLastUpdate(new Date());
            setError(null);
            setLoading(false);
        } catch (err) {
            if (!isCurrent()) return;
            setError(err.message || 'Failed to load trend scanner');
            setLoading(false);
        }
    }, []);

    // Symbol/timeframe change - fresh load, show spinner (may be a slow
    // cache-miss reconstruction on the backend).
    useEffect(() => {
        selectionRef.current = { symbol, timeframe };
        if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
        setRows(null);
        setError(null);
        fetchData(symbol, timeframe, { showSpinner: true });
        return () => {
            if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
        };
    }, [symbol, timeframe, fetchData]);

    // Background poll for the current selection - keep showing existing rows
    // while refreshing (backend cache makes most of these polls cheap).
    useEffect(() => {
        const interval = setInterval(() => {
            fetchData(symbol, timeframe, { showSpinner: false });
        }, 60000);
        return () => clearInterval(interval);
    }, [symbol, timeframe, fetchData]);

    const displayRows = rows ? [...rows].reverse() : [];

    return (
        <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
            <div className="bg-white rounded-xl shadow-xl p-6 border border-gray-100">
                <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                    <div>
                        <h2 className="text-3xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
                            Trend Scanner
                        </h2>
                        <p className="text-xs text-gray-400 mt-1">
                            Full-day Call/Put OI, PCR, and VWAP history (9:15-15:30). Informational only.
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        {lastUpdate && (
                            <span className="text-xs text-gray-400">
                                Updated {lastUpdate.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                        )}
                        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
                            {TIMEFRAMES.map((tf) => (
                                <TabButton key={tf.key} active={timeframe === tf.key} onClick={() => setTimeframe(tf.key)}>
                                    {tf.label}
                                </TabButton>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1 mb-4">
                    {SYMBOLS.map((sym) => (
                        <TabButton key={sym} active={symbol === sym} onClick={() => setSymbol(sym)}>
                            {sym}
                        </TabButton>
                    ))}
                </div>

                {loading && (
                    <div className="flex items-center justify-center p-12">
                        <div className="text-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4"></div>
                            <p className="text-gray-700 font-medium">Reconstructing {symbol}'s option chain history...</p>
                            <p className="text-gray-400 text-sm mt-1">First load for a symbol can take a few minutes - cached afterward</p>
                        </div>
                    </div>
                )}

                {!loading && error && (
                    <div className="text-center py-8">
                        <p className="text-red-600 font-medium">{error}</p>
                    </div>
                )}

                {!loading && !error && displayRows.length === 0 && (
                    <div className="text-center py-8">
                        <p className="text-gray-400 font-medium">No data available yet for {symbol}</p>
                    </div>
                )}

                {!loading && !error && displayRows.length > 0 && (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Time</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Call OI</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Put OI</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Diff</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">PCR</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Option Signal</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Price</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">VWAP</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">VWAP Signal</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {displayRows.map((row) => (
                                    <HistoryRow key={row.time} row={row} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

export default Scanner;
