import { useState, useEffect, useRef, useMemo } from 'react';

const KiteWatchlist = ({ ticks, selectedInstruments, selectedKey, onSelect }) => {
    const getInstruments = () => {
        const instruments = [];

        // Nifty Index
        instruments.push({
            key: 'IDX_I|13',
            name: 'NIFTY 50',
            group: 'NIFTY',
            type: 'INDEX',
        });

        // Sensex Index
        instruments.push({
            key: 'IDX_I|51',
            name: 'SENSEX',
            group: 'SENSEX',
            type: 'INDEX',
        });

        // Nifty Options
        if (selectedInstruments?.nifty) {
            if (selectedInstruments.nifty.call_strike) {
                instruments.push({
                    key: selectedInstruments.nifty.call_instrument_key,
                    name: `NIFTY ${selectedInstruments.nifty.call_strike} CE`,
                    group: 'NIFTY',
                    type: 'CE',
                });
            }
            if (selectedInstruments.nifty.put_strike) {
                instruments.push({
                    key: selectedInstruments.nifty.put_instrument_key,
                    name: `NIFTY ${selectedInstruments.nifty.put_strike} PE`,
                    group: 'NIFTY',
                    type: 'PE',
                });
            }
        }

        // Sensex Options
        if (selectedInstruments?.sensex) {
            if (selectedInstruments.sensex.call_strike) {
                instruments.push({
                    key: selectedInstruments.sensex.call_instrument_key,
                    name: `SENSEX ${selectedInstruments.sensex.call_strike} CE`,
                    group: 'SENSEX',
                    type: 'CE',
                });
            }
            if (selectedInstruments.sensex.put_strike) {
                instruments.push({
                    key: selectedInstruments.sensex.put_instrument_key,
                    name: `SENSEX ${selectedInstruments.sensex.put_strike} PE`,
                    group: 'SENSEX',
                    type: 'PE',
                });
            }
        }

        return instruments;
    };

    const instruments = useMemo(getInstruments, [selectedInstruments]);

    // Group by exchange
    const niftyInstruments = instruments.filter(i => i.group === 'NIFTY');
    const sensexInstruments = instruments.filter(i => i.group === 'SENSEX');

    return (
        <div className="kite-watchlist">
            <div className="kite-watchlist__header">
                <span className="kite-watchlist__title">Market Watch</span>
                <span className="kite-watchlist__count">{instruments.length} items</span>
            </div>

            <div className="kite-watchlist__list">
                {niftyInstruments.length > 0 && (
                    <>
                        <div className="kite-watchlist__group-label">NIFTY</div>
                        {niftyInstruments.map(inst => (
                            <WatchlistRow
                                key={inst.key}
                                instrument={inst}
                                tick={ticks?.[inst.key]}
                                isActive={selectedKey === inst.key}
                                onClick={() => onSelect(inst)}
                            />
                        ))}
                    </>
                )}

                {sensexInstruments.length > 0 && (
                    <>
                        <div className="kite-watchlist__group-label">SENSEX</div>
                        {sensexInstruments.map(inst => (
                            <WatchlistRow
                                key={inst.key}
                                instrument={inst}
                                tick={ticks?.[inst.key]}
                                isActive={selectedKey === inst.key}
                                onClick={() => onSelect(inst)}
                            />
                        ))}
                    </>
                )}

                {instruments.length === 0 && (
                    <div className="kite-empty">
                        <div className="kite-empty__icon">📊</div>
                        <span>No instruments available</span>
                        <span style={{ fontSize: '10px', opacity: 0.6 }}>
                            Waiting for market data...
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
};

const WatchlistRow = ({ instrument, tick, isActive, onClick }) => {
    const [flash, setFlash] = useState(null);
    const prevLtpRef = useRef(tick?.ltp);

    useEffect(() => {
        if (tick?.ltp && tick.ltp !== prevLtpRef.current) {
            setFlash(tick.ltp > prevLtpRef.current ? 'up' : 'down');
            prevLtpRef.current = tick.ltp;
            const t = setTimeout(() => setFlash(null), 500);
            return () => clearTimeout(t);
        }
    }, [tick?.ltp]);

    const ltp = tick?.ltp;
    const change = ltp ? ltp - (tick.cp || tick.close || 0) : 0;
    const changePct = tick?.cp ? ((change / tick.cp) * 100) : 0;
    const isUp = change >= 0;

    const typeClass = instrument.type === 'CE' ? 'ce' : instrument.type === 'PE' ? 'pe' : 'index';
    const priceClass = `kite-watchlist__price ${isUp ? 'up' : 'down'} ${flash ? `flash-${flash}` : ''}`;

    return (
        <div
            className={`kite-watchlist__row ${isActive ? 'active' : ''}`}
            onClick={onClick}
        >
            <div className="kite-watchlist__row-left">
                <span className="kite-watchlist__symbol">{instrument.name}</span>
                <span className={`kite-watchlist__type-badge ${typeClass}`}>
                    {instrument.type}
                </span>
            </div>

            <div className="kite-watchlist__row-right">
                {ltp ? (
                    <>
                        <span className={priceClass}>
                            {ltp.toFixed(2)}
                        </span>
                        <span className={`kite-watchlist__change ${isUp ? 'up' : 'down'}`}>
                            {isUp ? '+' : ''}{change.toFixed(2)} ({changePct.toFixed(2)}%)
                        </span>
                    </>
                ) : (
                    <span className="kite-watchlist__price" style={{ color: 'var(--kite-text-muted)' }}>
                        —
                    </span>
                )}
            </div>

            {/* Hover action buttons */}
            <div className="kite-watchlist__actions">
                <button className="kite-watchlist__action-btn buy">B</button>
                <button className="kite-watchlist__action-btn sell">S</button>
            </div>
        </div>
    );
};

export default KiteWatchlist;
