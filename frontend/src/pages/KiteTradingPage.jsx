import { useState, useEffect, useMemo } from 'react';
import apiService from '../api';
import useDhanTicks from '../hooks/useDhanTicks';
import KiteNavBar from '../components/kite/KiteNavBar';
import KiteWatchlist from '../components/kite/KiteWatchlist';
import KiteChartPanel from '../components/kite/KiteChartPanel';
import KiteOrderBook from '../components/kite/KiteOrderBook';
import KiteStatusBar from '../components/kite/KiteStatusBar';
import '../kite.css';

const NIFTY_INDEX_KEY = 'IDX_I|13';
const SENSEX_INDEX_KEY = 'IDX_I|51';

function KiteTradingPage() {
    // Data state
    const [positions, setPositions] = useState([]);
    const [summary, setSummary] = useState(null);
    const [trades, setTrades] = useState([]);
    const [profile, setProfile] = useState(null);
    const [selectedInstruments, setSelectedInstruments] = useState(null);
    const [instrumentKeys, setInstrumentKeys] = useState([]);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showOrderBook, setShowOrderBook] = useState(false);

    // Selected chart instrument
    const [selectedChart, setSelectedChart] = useState({
        type: 'INDEX',
        symbol: 'NIFTY 50',
        key: NIFTY_INDEX_KEY,
    });

    // Build WebSocket subscription keys
    const wsInstrumentKeys = useMemo(() => {
        const keys = instrumentKeys.length > 0 ? [...instrumentKeys] : [];

        if (selectedChart.key && !keys.includes(selectedChart.key)) {
            keys.push(selectedChart.key);
        }
        if (!keys.includes(NIFTY_INDEX_KEY)) {
            keys.push(NIFTY_INDEX_KEY);
        }
        if (!keys.includes(SENSEX_INDEX_KEY)) {
            keys.push(SENSEX_INDEX_KEY);
        }

        // Selected options
        if (selectedInstruments?.nifty) {
            const { call_instrument_key, put_instrument_key } = selectedInstruments.nifty;
            if (call_instrument_key && !keys.includes(call_instrument_key)) keys.push(call_instrument_key);
            if (put_instrument_key && !keys.includes(put_instrument_key)) keys.push(put_instrument_key);
        }
        if (selectedInstruments?.sensex) {
            const { call_instrument_key, put_instrument_key } = selectedInstruments.sensex;
            if (call_instrument_key && !keys.includes(call_instrument_key)) keys.push(call_instrument_key);
            if (put_instrument_key && !keys.includes(put_instrument_key)) keys.push(put_instrument_key);
        }

        return keys;
    }, [instrumentKeys, selectedChart.key, selectedInstruments]);

    // Fetch all data
    const fetchData = async () => {
        try {
            const [profileData, positionsData, summaryData, instrumentsData, selectedInstData, tradesData] = await Promise.all([
                apiService.getProfile().catch(() => null),
                apiService.getCurrentPositions(),
                apiService.getDailySummary(),
                apiService.getPositionsInstruments().catch(() => ({ instruments: [] })),
                apiService.getSelectedInstruments().catch(() => null),
                apiService.getTradesHistory().catch(() => ({ trades: [] })),
            ]);

            setProfile(profileData);
            setPositions(positionsData.positions || []);
            setSummary(summaryData);
            setTrades(tradesData.trades || []);
            if (selectedInstData) setSelectedInstruments(selectedInstData);
            setLastUpdate(new Date());
            setLoading(false);

            // Extract instrument keys
            const keys = (instrumentsData.instruments || [])
                .map(i => i.instrument_key)
                .filter(Boolean);
            setInstrumentKeys(keys);

            // Enrich positions with instrument_key
            const enrichedPositions = (positionsData.positions || []).map(pos => {
                const match = (instrumentsData.instruments || []).find(
                    i => i.symbol === pos.symbol && i.option_type === pos.option_type && i.strike === pos.strike
                );
                return { ...pos, instrument_key: match?.instrument_key || '' };
            });
            setPositions(enrichedPositions);
        } catch (err) {
            console.error('[Kite] Error fetching data:', err);
            setLoading(false);
        }
    };

    // SSE live ticks
    const { ticks: liveTicks, connected: wsConnected, tickCount } = useDhanTicks(wsInstrumentKeys, fetchData);

    // Live strategy P&L
    const liveStrategyPnl = useMemo(() => {
        const breakdown = { TOTAL: summary?.total_pnl || 0 };

        if (summary?.strategy_wise) {
            Object.entries(summary.strategy_wise).forEach(([tag, stats]) => {
                breakdown[tag] = stats.pnl || 0;
            });
        }

        positions.forEach(pos => {
            const tick = liveTicks[pos.instrument_key];
            const currentPrice = tick?.ltp || pos.current_price || pos.entry_price;
            const posPnl = (currentPrice - pos.entry_price) * (pos.lot_size || 1);
            const tag = pos.strategy_tag || 'N/A';
            if (breakdown[tag] === undefined) breakdown[tag] = 0;
            breakdown[tag] += posPnl;
            breakdown.TOTAL += posPnl;
        });

        return breakdown;
    }, [summary, positions, liveTicks]);

    // Initial fetch + polling
    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, []);

    // Handle instrument selection from watchlist or nav
    const handleSelectInstrument = (instrument) => {
        setSelectedChart({
            type: instrument.type || 'INDEX',
            symbol: instrument.name,
            key: instrument.key,
        });
    };

    // Handle trade row click from order book
    const handleTradeClick = (trade) => {
        if (trade.instrument_key) {
            setSelectedChart({
                type: 'OPTION',
                symbol: `${trade.symbol} ${trade.strike} ${trade.type || trade.option_type}`,
                key: trade.instrument_key,
            });
        }
    };

    const tradingMode = profile?.paper_trading === false ? 'LIVE' : 'PAPER';

    if (loading) {
        return (
            <div className="kite-shell" style={{ alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{
                        width: 40, height: 40, border: '3px solid var(--kite-border)',
                        borderTopColor: 'var(--kite-accent)', borderRadius: '50%',
                        animation: 'spin 0.8s linear infinite', margin: '0 auto 16px',
                    }} />
                    <div style={{ color: 'var(--kite-text-dim)', fontSize: 13, fontWeight: 600 }}>
                        Loading Terminal...
                    </div>
                    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
            </div>
        );
    }

    return (
        <div className="kite-shell">
            {/* Top Nav */}
            <KiteNavBar
                ticks={liveTicks}
                connected={wsConnected}
                selectedInstruments={selectedInstruments}
                onTickerClick={handleSelectInstrument}
            />

            {/* Main: Watchlist + Content */}
            <div className="kite-main">
                {/* Left: Watchlist */}
                <KiteWatchlist
                    ticks={liveTicks}
                    selectedInstruments={selectedInstruments}
                    selectedKey={selectedChart.key}
                    onSelect={handleSelectInstrument}
                />

                {/* Right: Chart + (optional) Order Book */}
                <div className="kite-content">
                    {/* Chart */}
                    <KiteChartPanel
                        instrumentKey={selectedChart.key}
                        liveTick={liveTicks[selectedChart.key]}
                        symbol={selectedChart.symbol}
                        positions={positions}
                        showOrderBookToggle={true}
                        orderBookVisible={showOrderBook}
                        onToggleOrderBook={() => setShowOrderBook(prev => !prev)}
                    />

                    {/* Collapsible Bottom Tabs */}
                    {showOrderBook && (
                        <KiteOrderBook
                            positions={positions}
                            trades={trades}
                            summary={summary}
                            liveTicks={liveTicks}
                            liveStrategyPnl={liveStrategyPnl}
                            onTradeClick={handleTradeClick}
                        />
                    )}
                </div>
            </div>

            {/* Status Bar */}
            <KiteStatusBar
                connected={wsConnected}
                tickCount={tickCount}
                lastUpdate={lastUpdate}
                tradingMode={tradingMode}
            />
        </div>
    );
}

export default KiteTradingPage;

