import React, { useState, useEffect, useCallback } from 'react';
import apiService from '../api';

const SYMBOLS = ['NIFTY', 'SENSEX'];

// Lets the user chart any strike directly, instead of being limited to
// whatever's currently in an open position or today's trade history. Loads
// spot/ATM/expiry defaults per symbol so the strike field starts near the
// money rather than the user guessing a raw number blind.
const StrikeSearch = ({ onLoad }) => {
    const [open, setOpen] = useState(false);
    const [symbol, setSymbol] = useState('NIFTY');
    const [optionType, setOptionType] = useState('CE');
    const [strike, setStrike] = useState('');
    const [meta, setMeta] = useState(null);
    const [metaLoading, setMetaLoading] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchMeta = useCallback(async (sym) => {
        setMetaLoading(true);
        setError(null);
        try {
            const data = await apiService.getOptionSearchMeta(sym);
            setMeta(data);
            setStrike((prev) => (prev ? prev : (data.atm != null ? String(data.atm) : '')));
        } catch (err) {
            setError('Could not load spot/ATM data');
        } finally {
            setMetaLoading(false);
        }
    }, []);

    useEffect(() => {
        if (open) fetchMeta(symbol);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, symbol]);

    const step = meta?.strike_interval || (symbol === 'SENSEX' ? 100 : 50);

    const bumpStrike = (dir) => {
        const current = Number(strike) || meta?.atm || 0;
        setStrike(String(current + dir * step));
    };

    const handleLoad = async () => {
        if (!strike) return;
        setLoading(true);
        setError(null);
        try {
            const data = await apiService.resolveOptionInstrument({
                symbol,
                strike,
                optionType,
                expiryDate: meta?.expiry_date,
            });
            onLoad({
                type: 'OPTION',
                symbol: `${data.symbol} ${data.strike} ${data.option_type}`,
                key: data.instrument_key,
                strategyTag: null,
                tradeMarkers: null,
            });
            setOpen(false);
        } catch (err) {
            setError(err.response?.data?.error || 'Strike not found');
        } finally {
            setLoading(false);
        }
    };

    if (!open) {
        return (
            <button
                type="button"
                onClick={() => setOpen(true)}
                className="px-3 py-1.5 rounded-md text-sm font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-100 whitespace-nowrap flex items-center gap-1.5"
                title="Search a strike to chart"
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
                </svg>
                Search Strike
            </button>
        );
    }

    return (
        <div className="flex flex-wrap items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg p-2">
            <div className="inline-flex rounded-md border border-gray-200 bg-white p-0.5">
                {SYMBOLS.map((s) => (
                    <button
                        key={s}
                        type="button"
                        onClick={() => { setSymbol(s); setStrike(''); }}
                        className={`px-2 py-1 text-xs font-bold rounded transition-all ${symbol === s ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-gray-700'
                            }`}
                    >
                        {s}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-1">
                <button
                    type="button"
                    onClick={() => bumpStrike(-1)}
                    className="w-6 h-6 flex items-center justify-center rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-100 text-sm font-bold"
                >
                    −
                </button>
                <input
                    type="number"
                    value={strike}
                    onChange={(e) => setStrike(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
                    placeholder={metaLoading ? '...' : 'Strike'}
                    step={step}
                    className="w-20 px-2 py-1 text-sm text-center border border-gray-200 rounded font-semibold tabular-nums"
                />
                <button
                    type="button"
                    onClick={() => bumpStrike(1)}
                    className="w-6 h-6 flex items-center justify-center rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-100 text-sm font-bold"
                >
                    +
                </button>
            </div>

            <div className="inline-flex rounded-md border border-gray-200 bg-white p-0.5">
                {['CE', 'PE'].map((ot) => (
                    <button
                        key={ot}
                        type="button"
                        onClick={() => setOptionType(ot)}
                        className={`px-2.5 py-1 text-xs font-bold rounded transition-all ${optionType === ot
                            ? ot === 'CE' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                            : 'text-gray-500 hover:text-gray-700'
                            }`}
                    >
                        {ot}
                    </button>
                ))}
            </div>

            {meta?.expiry_date && (
                <span className="text-[10px] text-gray-400 font-medium whitespace-nowrap">
                    Exp {meta.expiry_date}{meta.atm != null && ` · ATM ${meta.atm}`}
                </span>
            )}

            <button
                type="button"
                onClick={handleLoad}
                disabled={loading || !strike}
                className="px-3 py-1 text-xs font-bold rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
                {loading ? 'Loading...' : 'Load'}
            </button>

            <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-6 h-6 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 hover:bg-gray-200 text-sm"
                title="Close"
            >
                ×
            </button>

            {error && <span className="text-[11px] text-red-500 font-medium w-full">{error}</span>}
        </div>
    );
};

export default StrikeSearch;
