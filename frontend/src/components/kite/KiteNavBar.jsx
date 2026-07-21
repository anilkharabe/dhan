import { Link } from 'react-router-dom';

const KiteNavBar = ({ ticks, connected, selectedInstruments, onTickerClick }) => {
    const niftyTick = ticks?.['IDX_I|13'];
    const sensexTick = ticks?.['IDX_I|51'];

    const renderTicker = (name, tick, key) => {
        if (!tick) return null;
        const change = tick.ltp - (tick.cp || tick.close || 0);
        const changePct = tick.cp ? ((change / tick.cp) * 100) : 0;
        const isUp = change >= 0;

        return (
            <div
                className="kite-nav__ticker"
                onClick={() => onTickerClick?.({ name, key, type: 'INDEX' })}
            >
                <span className="kite-nav__ticker-name">{name}</span>
                <span className="kite-nav__ticker-price">{tick.ltp?.toFixed(2)}</span>
                <span className={`kite-nav__ticker-change ${isUp ? 'up' : 'down'}`}>
                    {isUp ? '▲' : '▼'} {Math.abs(change).toFixed(2)} ({changePct.toFixed(2)}%)
                </span>
            </div>
        );
    };

    return (
        <nav className="kite-nav">
            <div className="kite-nav__brand">
                <span className="kite-nav__logo">AlgoTrader</span>
                <span className="kite-nav__badge">Terminal</span>
            </div>

            <div className="kite-nav__tickers">
                {renderTicker('NIFTY', niftyTick, 'IDX_I|13')}
                {renderTicker('SENSEX', sensexTick, 'IDX_I|51')}
            </div>

            <div className="kite-nav__right">
                <Link to="/" className="kite-nav__link" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <polyline points="9 22 9 12 15 12 15 22" />
                    </svg>
                    Dashboard
                </Link>
                <div className={`kite-nav__conn ${connected ? 'live' : 'off'}`}>
                    <span className="kite-nav__conn-dot"></span>
                    {connected ? 'LIVE' : 'OFFLINE'}
                </div>
            </div>
        </nav>
    );
};

export default KiteNavBar;
