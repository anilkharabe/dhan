const KiteStatusBar = ({ connected, tickCount, lastUpdate, tradingMode }) => {
    const now = lastUpdate ? lastUpdate.toLocaleTimeString() : '—';

    return (
        <div className="kite-status">
            <div className="kite-status__left">
                <div className="kite-status__item">
                    <span className={`kite-status__dot ${connected ? 'green' : 'red'}`}></span>
                    <span>{connected ? 'WebSocket Connected' : 'Disconnected'}</span>
                </div>
                <div className="kite-status__item">
                    <span>Ticks: {tickCount || 0}</span>
                </div>
                <div className="kite-status__item">
                    <span>Updated: {now}</span>
                </div>
            </div>

            <div className="kite-status__right">
                <div className="kite-status__item">
                    <span className={`kite-status__dot ${tradingMode === 'LIVE' ? 'green' : 'yellow'}`}></span>
                    <span style={{ fontWeight: 700 }}>
                        {tradingMode === 'LIVE' ? 'LIVE TRADING' : 'PAPER TRADING'}
                    </span>
                </div>
            </div>
        </div>
    );
};

export default KiteStatusBar;
