import { useState, useMemo } from 'react';

const KiteOrderBook = ({ positions, trades, summary, liveTicks, liveStrategyPnl }) => {
    const [activeTab, setActiveTab] = useState('positions');

    const posCount = positions?.length || 0;
    const tradeCount = trades?.length || 0;

    return (
        <div className="kite-orderbook">
            {/* Tabs */}
            <div className="kite-orderbook__tabs">
                <button
                    className={`kite-orderbook__tab ${activeTab === 'positions' ? 'active' : ''}`}
                    onClick={() => setActiveTab('positions')}
                >
                    Positions
                    {posCount > 0 && <span className="kite-orderbook__tab-count">{posCount}</span>}
                </button>
                <button
                    className={`kite-orderbook__tab ${activeTab === 'trades' ? 'active' : ''}`}
                    onClick={() => setActiveTab('trades')}
                >
                    Trades
                    {tradeCount > 0 && <span className="kite-orderbook__tab-count">{tradeCount}</span>}
                </button>
                <button
                    className={`kite-orderbook__tab ${activeTab === 'summary' ? 'active' : ''}`}
                    onClick={() => setActiveTab('summary')}
                >
                    Summary
                </button>
            </div>

            {/* Tab Content */}
            <div className="kite-orderbook__content">
                {activeTab === 'positions' && (
                    <PositionsTab positions={positions} liveTicks={liveTicks} />
                )}
                {activeTab === 'trades' && (
                    <TradesTab trades={trades} />
                )}
                {activeTab === 'summary' && (
                    <SummaryTab summary={summary} liveStrategyPnl={liveStrategyPnl} />
                )}
            </div>
        </div>
    );
};

/* ---- Positions Tab ---- */
const PositionsTab = ({ positions, liveTicks }) => {
    if (!positions || positions.length === 0) {
        return (
            <div className="kite-empty">
                <div className="kite-empty__icon">📭</div>
                <span>No open positions</span>
            </div>
        );
    }

    return (
        <table className="kite-table">
            <thead>
                <tr>
                    <th>Instrument</th>
                    <th>Strategy</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>LTP</th>
                    <th>SL</th>
                    <th>P&L</th>
                    <th>Change%</th>
                </tr>
            </thead>
            <tbody>
                {positions.map((pos, idx) => {
                    const tick = liveTicks?.[pos.instrument_key];
                    const ltp = tick?.ltp || pos.current_price || pos.entry_price;
                    const pnl = (ltp - pos.entry_price) * (pos.lot_size || 1);
                    const pnlPct = pos.entry_price ? ((ltp - pos.entry_price) / pos.entry_price * 100) : 0;
                    const isProfit = pnl >= 0;

                    return (
                        <tr key={idx}>
                            <td style={{ fontWeight: 700 }}>
                                {pos.symbol || pos.trading_symbol}
                                {pos.option_type && (
                                    <span style={{
                                        marginLeft: 6,
                                        fontSize: 9,
                                        fontWeight: 800,
                                        padding: '1px 4px',
                                        borderRadius: 3,
                                        background: pos.option_type === 'CE' ? 'var(--kite-green-bg)' : 'var(--kite-red-bg)',
                                        color: pos.option_type === 'CE' ? 'var(--kite-green)' : 'var(--kite-red)',
                                    }}>
                                        {pos.option_type}
                                    </span>
                                )}
                            </td>
                            <td>
                                <span style={{
                                    fontSize: 9,
                                    fontWeight: 700,
                                    padding: '2px 6px',
                                    borderRadius: 4,
                                    background: 'rgba(56, 126, 255, 0.1)',
                                    color: 'var(--kite-accent)',
                                }}>
                                    {pos.strategy_tag || 'N/A'}
                                </span>
                            </td>
                            <td>{pos.lot_size || 1}</td>
                            <td>{pos.entry_price?.toFixed(2)}</td>
                            <td style={{ fontWeight: 700, color: isProfit ? 'var(--kite-green)' : 'var(--kite-red)' }}>
                                {ltp?.toFixed(2)}
                            </td>
                            <td style={{ color: 'var(--kite-yellow)' }}>
                                {pos.stop_loss?.toFixed(2) || '—'}
                            </td>
                            <td className={isProfit ? 'pnl-positive' : 'pnl-negative'}>
                                ₹{pnl.toFixed(0)}
                            </td>
                            <td className={isProfit ? 'pnl-positive' : 'pnl-negative'}>
                                {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                            </td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
};

/* ---- Trades Tab ---- */
const TradesTab = ({ trades }) => {
    if (!trades || trades.length === 0) {
        return (
            <div className="kite-empty">
                <div className="kite-empty__icon">📋</div>
                <span>No trades today</span>
            </div>
        );
    }

    return (
        <table className="kite-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Instrument</th>
                    <th>Strategy</th>
                    <th>Type</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>P&L</th>
                    <th>Exit Reason</th>
                </tr>
            </thead>
            <tbody>
                {trades.map((trade, idx) => {
                    const pnl = trade.pnl || 0;
                    const isProfit = pnl >= 0;

                    return (
                        <tr key={idx}>
                            <td style={{ color: 'var(--kite-text-dim)', fontSize: 10 }}>
                                {trade.entry_time || '—'}
                            </td>
                            <td style={{ fontWeight: 700 }}>
                                {trade.symbol || trade.trading_symbol}
                                {trade.option_type && (
                                    <span style={{
                                        marginLeft: 6,
                                        fontSize: 9,
                                        fontWeight: 800,
                                        padding: '1px 4px',
                                        borderRadius: 3,
                                        background: trade.option_type === 'CE' ? 'var(--kite-green-bg)' : 'var(--kite-red-bg)',
                                        color: trade.option_type === 'CE' ? 'var(--kite-green)' : 'var(--kite-red)',
                                    }}>
                                        {trade.option_type}
                                    </span>
                                )}
                            </td>
                            <td>
                                <span style={{
                                    fontSize: 9,
                                    fontWeight: 700,
                                    padding: '2px 6px',
                                    borderRadius: 4,
                                    background: 'rgba(56, 126, 255, 0.1)',
                                    color: 'var(--kite-accent)',
                                }}>
                                    {trade.strategy_tag || 'N/A'}
                                </span>
                            </td>
                            <td>{trade.option_type || '—'}</td>
                            <td>{trade.entry_price?.toFixed(2) || '—'}</td>
                            <td>{trade.exit_price?.toFixed(2) || '—'}</td>
                            <td className={isProfit ? 'pnl-positive' : 'pnl-negative'}>
                                ₹{pnl.toFixed(0)}
                            </td>
                            <td style={{ fontSize: 10, color: 'var(--kite-text-dim)' }}>
                                {trade.exit_reason || '—'}
                            </td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
};

/* ---- Summary Tab ---- */
const SummaryTab = ({ summary, liveStrategyPnl }) => {
    const totalPnl = liveStrategyPnl?.TOTAL || summary?.total_pnl || 0;
    const isProfit = totalPnl >= 0;

    return (
        <div className="kite-summary">
            {/* Total P&L */}
            <div className="kite-summary__card">
                <div className="kite-summary__label">Total P&L</div>
                <div className="kite-summary__value" style={{ color: isProfit ? 'var(--kite-green)' : 'var(--kite-red)' }}>
                    ₹{totalPnl.toFixed(0)}
                </div>
                <div className="kite-summary__sub">
                    {summary?.total_trades || 0} trades today
                </div>
            </div>

            {/* Wins */}
            <div className="kite-summary__card">
                <div className="kite-summary__label">Winning</div>
                <div className="kite-summary__value" style={{ color: 'var(--kite-green)' }}>
                    {summary?.winning_trades || 0}
                </div>
                <div className="kite-summary__sub">
                    Win rate: {summary?.win_rate?.toFixed(0) || 0}%
                </div>
            </div>

            {/* Losses */}
            <div className="kite-summary__card">
                <div className="kite-summary__label">Losing</div>
                <div className="kite-summary__value" style={{ color: 'var(--kite-red)' }}>
                    {summary?.losing_trades || 0}
                </div>
                <div className="kite-summary__sub">
                    Open: {summary?.open_positions || 0} positions
                </div>
            </div>

            {/* Strategy Breakdown */}
            {liveStrategyPnl && Object.entries(liveStrategyPnl)
                .filter(([key]) => key !== 'TOTAL')
                .map(([strategy, pnl]) => (
                    <div className="kite-summary__card" key={strategy}>
                        <div className="kite-summary__label">{strategy}</div>
                        <div className="kite-summary__value" style={{ color: pnl >= 0 ? 'var(--kite-green)' : 'var(--kite-red)' }}>
                            ₹{pnl.toFixed(0)}
                        </div>
                    </div>
                ))
            }
        </div>
    );
};

export default KiteOrderBook;
