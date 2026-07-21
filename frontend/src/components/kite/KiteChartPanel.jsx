import { useState } from 'react';
import CandlestickChart from '../CandlestickChart';

const TIMEFRAMES = [
    { label: '1m', value: '1minute' },
    { label: '5m', value: '5minute' },
    { label: '15m', value: '15minute' },
    { label: '30m', value: '30minute' },
    { label: '1H', value: '60minute' },
    { label: '1D', value: '1day' },
];

const KiteChartPanel = ({ instrumentKey, liveTick, symbol, positions, showOrderBookToggle, orderBookVisible, onToggleOrderBook }) => {
    const [interval, setInterval] = useState('1minute');

    const tick = liveTick;
    const ltp = tick?.ltp;
    const change = ltp ? ltp - (tick?.cp || tick?.close || 0) : 0;
    const changePct = tick?.cp ? ((change / tick.cp) * 100) : 0;
    const isUp = change >= 0;

    // Find matching position for entry marker
    const activePosition = positions?.find(p => p.instrument_key === instrumentKey);

    return (
        <div className="kite-chart">
            {/* Chart Toolbar */}
            <div className="kite-chart__toolbar">
                <div className="kite-chart__instrument">
                    <span className="kite-chart__symbol-name">{symbol || 'Select Instrument'}</span>
                    {ltp && (
                        <>
                            <span className={`kite-chart__live-price`} style={{ color: isUp ? 'var(--kite-green)' : 'var(--kite-red)' }}>
                                {ltp.toFixed(2)}
                            </span>
                            <span className="kite-chart__live-change" style={{ color: isUp ? 'var(--kite-green)' : 'var(--kite-red)' }}>
                                {isUp ? '▲' : '▼'} {Math.abs(change).toFixed(2)} ({changePct.toFixed(2)}%)
                            </span>
                        </>
                    )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {showOrderBookToggle && (
                        <button
                            onClick={onToggleOrderBook}
                            style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: '4px 10px',
                                border: '1px solid var(--kite-border)',
                                background: orderBookVisible ? 'var(--kite-accent)' : 'transparent',
                                color: orderBookVisible ? '#fff' : 'var(--kite-text-dim)',
                                cursor: 'pointer',
                                borderRadius: 4,
                                transition: 'all 0.15s',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                            }}
                            title={orderBookVisible ? 'Hide panel' : 'Show Positions / Trades / Summary'}
                        >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" />
                                <line x1="3" y1="15" x2="21" y2="15" />
                            </svg>
                            {orderBookVisible ? 'Hide Panel' : 'Panel'}
                        </button>
                    )}

                    <div className="kite-chart__timeframes">
                        {TIMEFRAMES.map(tf => (
                            <button
                                key={tf.value}
                                className={`kite-chart__tf-btn ${interval === tf.value ? 'active' : ''}`}
                                onClick={() => setInterval(tf.value)}
                            >
                                {tf.label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Chart Body — scrollable to show all sub-charts */}
            <div className="kite-chart__body">
                <CandlestickChart
                    key={`${instrumentKey}-${interval}`}
                    instrumentKey={instrumentKey}
                    liveTick={liveTick}
                    symbol={symbol}
                    interval={interval}
                    activePosition={activePosition}
                />
            </div>
        </div>
    );
};

export default KiteChartPanel;

