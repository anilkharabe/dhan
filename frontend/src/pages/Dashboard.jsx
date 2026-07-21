import { useState, useEffect, useMemo } from 'react';
import apiService from '../api';
import useDhanTicks from '../hooks/useDhanTicks';
import Profile from '../components/Profile';
import PositionsTable from '../components/PositionsTable';
import OIPcrChart from '../components/OIPcrChart';
import DailySummary from '../components/DailySummary';
import LiveTickerBar from '../components/LiveTickerBar';
import CandlestickChart from '../components/CandlestickChart';
import TradeHistoryTable from '../components/TradeHistoryTable';
import AdminControls from '../components/AdminControls';
import TokenStatus from '../components/TokenStatus';
import TokenExpiredModal from '../components/TokenExpiredModal';
import '../App.css';

const NIFTY_INDEX_KEY = 'IDX_I|13';
const SENSEX_INDEX_KEY = 'IDX_I|51';

function Dashboard() {
    const [profile, setProfile] = useState(null);
    const [positions, setPositions] = useState([]);
    const [oiPcr, setOiPcr] = useState(null);
    const [summary, setSummary] = useState(null);
    const [trades, setTrades] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdate, setLastUpdate] = useState(null);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [instrumentKeys, setInstrumentKeys] = useState([]);

    // Token state
    const [tokenStatus, setTokenStatus] = useState(null);
    const [showTokenModal, setShowTokenModal] = useState(false);

    // Chart selection state
    const [selectedInstruments, setSelectedInstruments] = useState(null);
    const [selectedChart, setSelectedChart] = useState({
        type: 'INDEX',
        symbol: 'NIFTY 50',
        key: NIFTY_INDEX_KEY
    });

    // Extract instrument keys from positions for WebSocket subscription
    const wsInstrumentKeys = useMemo(() => {
        const keys = instrumentKeys.length > 0 ? [...instrumentKeys] : [];

        // Ensure currently selected chart instrument is subscribed
        if (selectedChart.key && !keys.includes(selectedChart.key)) {
            keys.push(selectedChart.key);
        }

        // Ensure Nifty Index is always subscribed
        if (!keys.includes(NIFTY_INDEX_KEY)) {
            keys.push(NIFTY_INDEX_KEY);
        }

        // Ensure Sensex Index is always subscribed
        if (!keys.includes(SENSEX_INDEX_KEY)) {
            keys.push(SENSEX_INDEX_KEY);
        }

        // Subscribe to selected Nifty options
        if (selectedInstruments?.nifty) {
            if (selectedInstruments.nifty.call_instrument_key && !keys.includes(selectedInstruments.nifty.call_instrument_key)) {
                keys.push(selectedInstruments.nifty.call_instrument_key);
            }
            if (selectedInstruments.nifty.put_instrument_key && !keys.includes(selectedInstruments.nifty.put_instrument_key)) {
                keys.push(selectedInstruments.nifty.put_instrument_key);
            }
        }

        // Subscribe to selected Sensex options
        if (selectedInstruments?.sensex) {
            if (selectedInstruments.sensex.call_instrument_key && !keys.includes(selectedInstruments.sensex.call_instrument_key)) {
                keys.push(selectedInstruments.sensex.call_instrument_key);
            }
            if (selectedInstruments.sensex.put_instrument_key && !keys.includes(selectedInstruments.sensex.put_instrument_key)) {
                keys.push(selectedInstruments.sensex.put_instrument_key);
            }
        }

        return keys;
    }, [instrumentKeys, selectedChart.key, selectedInstruments]);

    const fetchData = async () => {
        try {
            setIsRefreshing(true);
            setError(null);

            // Check token status first
            try {
                const status = await apiService.getTokenStatus();
                setTokenStatus(status);
                if (status && !status.is_valid) {
                    setShowTokenModal(true);
                } else {
                    setShowTokenModal(false);
                }
            } catch (e) {
                console.warn("Could not check token status", e);
            }

            // Fetch all data in parallel
            const [profileData, positionsData, oiPcrData, summaryData, instrumentsData, selectedInstData, tradesData] = await Promise.all([
                apiService.getProfile(),
                apiService.getCurrentPositions(),
                apiService.getOiPcr(),
                apiService.getDailySummary(),
                apiService.getPositionsInstruments().catch(() => ({ instruments: [] })),
                apiService.getSelectedInstruments().catch(() => null),
                apiService.getTradesHistory().catch(() => ({ trades: [] })),
            ]);

            setProfile(profileData);
            setPositions(positionsData.positions || []);
            setOiPcr(oiPcrData);
            setSummary(summaryData);
            setTrades(tradesData.trades || []);
            if (selectedInstData) {
                setSelectedInstruments(selectedInstData);
            }

            setLastUpdate(new Date());
            setLoading(false);
            setIsRefreshing(false);

            // Update instrument keys for WebSocket subscription
            const keys = (instrumentsData.instruments || [])
                .map(i => i.instrument_key)
                .filter(Boolean);
            setInstrumentKeys(keys);

            // /api/current-positions already returns instrument_key (and
            // far_instrument_key for spreads) directly - no re-matching needed.
            setPositions(positionsData.positions || []);

        } catch (err) {
            console.error('Error fetching data:', err);
            setError('Failed to connect to API server. Make sure the Flask server is running on http://localhost:5000');
            setLoading(false);
            setIsRefreshing(false);
        }
    };

    // Real-time ticks from Dhan's Live Market Feed via SSE
    const { ticks: liveTicks, connected: wsConnected, error: wsError, tickCount } = useDhanTicks(wsInstrumentKeys, fetchData);

    // Calculate live Strategy-wise P&L (Closed + Unrealized)
    const liveStrategyPnl = useMemo(() => {
        const breakdown = {
            TOTAL: summary?.total_pnl || 0
        };

        // Initialize with closed stats from summary
        if (summary?.strategy_wise) {
            Object.entries(summary.strategy_wise).forEach(([tag, stats]) => {
                breakdown[tag] = stats.pnl || 0;
            });
        }

        // Add Unrealized P&L per strategy from open positions
        positions.forEach(pos => {
            let posPnl;

            if (pos.is_spread) {
                // Credit spread P&L is net-credit-based, not (current - entry) * qty -
                // that long-position formula has the wrong sign for a sold leg and
                // ignores the hedge leg entirely. Recompute live only when both legs
                // have a live tick; otherwise trust the backend's own pos.pnl (already
                // computed correctly server-side on the last REST refresh).
                const nearTick = liveTicks[pos.instrument_key];
                const farTick = liveTicks[pos.far_instrument_key];
                if (nearTick?.ltp != null && farTick?.ltp != null) {
                    const netSpreadValue = nearTick.ltp - farTick.ltp;
                    posPnl = ((pos.net_credit || 0) - netSpreadValue) * (pos.lot_size || 1);
                } else {
                    posPnl = pos.pnl ?? 0;
                }
            } else {
                const tick = liveTicks[pos.instrument_key];
                const currentPrice = tick?.ltp ?? pos.current_price ?? pos.entry_price;
                posPnl = (currentPrice - pos.entry_price) * (pos.lot_size || 1);
            }

            const tag = pos.strategy_tag || 'N/A';
            if (breakdown[tag] === undefined) breakdown[tag] = 0;

            breakdown[tag] += posPnl;
            breakdown.TOTAL += posPnl;
        });

        return breakdown;
    }, [summary, positions, liveTicks]);


    const liveTotalPnl = liveStrategyPnl.TOTAL;

    const accountValue = (profile?.initial_balance || 100000) + liveTotalPnl;

    useEffect(() => {
        fetchData();

        // Refresh every 60 seconds (WebSocket handles real-time updates)
        const interval = setInterval(fetchData, 60000);

        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center p-8">
                <div className="text-center">
                    <div className="relative">
                        <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4"></div>
                        <div className="absolute inset-0 animate-ping rounded-full h-16 w-16 border-4 border-blue-400 opacity-20"></div>
                    </div>
                    <p className="text-gray-700 font-medium text-lg">Loading dashboard...</p>
                    <p className="text-gray-500 text-sm mt-2">Connecting to trading system</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center p-8">
                <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full text-center">
                    <div className="text-red-500 mb-4">
                        <svg className="mx-auto h-16 w-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </div>
                    <h2 className="text-xl font-bold mb-2 text-gray-800">Connection Error</h2>
                    <p className="text-gray-600 mb-6">{error}</p>
                    <button
                        onClick={fetchData}
                        className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-semibold hover:bg-blue-700 transition"
                    >
                        Retry Connection
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">

            {/* Token Expired Modal */}
            <TokenExpiredModal
                isOpen={showTokenModal}
                onClose={() => setShowTokenModal(false)}
            />

            {/* Header Info */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-800">
                            Live Trading
                        </h1>
                        <p className="text-sm text-gray-500">
                            Real-time market analysis and execution
                        </p>
                    </div>
                    <div className="flex items-center gap-4">
                        {isRefreshing && (
                            <div className="flex items-center gap-2 text-blue-600">
                                <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 border-t-transparent"></div>
                                <span className="text-sm font-medium">Refreshing...</span>
                            </div>
                        )}
                        {lastUpdate && (
                            <div className="text-right">
                                <p className="text-xs text-gray-500">Last updated</p>
                                <p className="text-sm font-bold text-gray-800 flex items-center gap-2 justify-end">
                                    <span className={`w-2 h-2 ${wsConnected ? 'bg-green-500' : 'bg-amber-500'} rounded-full animate-pulse`}></span>
                                    {lastUpdate.toLocaleTimeString()}
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Token Status Section */}
            <TokenStatus />

            {/* Live Ticker Bar */}
            <LiveTickerBar
                ticks={liveTicks}
                connected={wsConnected}
                error={wsError}
                tickCount={tickCount}
                selectedInstruments={selectedInstruments}
                onTickerClick={(instrument) => {
                    setSelectedChart({
                        type: instrument.type === 'INDEX' ? 'INDEX' : 'OPTION',
                        symbol: instrument.name,
                        key: instrument.key
                    });
                }}
            />


            {/* Live Price Chart with Selection */}
            <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-4">
                <div className="flex justify-between items-center mb-4 border-b border-gray-100 pb-2">
                    <h2 className="text-lg font-bold text-gray-700">Live Chart</h2>

                    {/* Chart Selector */}
                    <div className="flex bg-gray-100 rounded-lg p-1 gap-1 overflow-x-auto">
                        {/* Nifty Index */}
                        <button
                            onClick={() => setSelectedChart({ type: 'INDEX', symbol: 'NIFTY 50', key: NIFTY_INDEX_KEY })}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap ${selectedChart.key === NIFTY_INDEX_KEY
                                ? 'bg-white text-blue-600 shadow-sm'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            Nifty 50
                        </button>

                        {/* Sensex Index */}
                        <button
                            onClick={() => setSelectedChart({ type: 'INDEX', symbol: 'SENSEX', key: SENSEX_INDEX_KEY })}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap ${selectedChart.key === SENSEX_INDEX_KEY
                                ? 'bg-white text-blue-600 shadow-sm'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            Sensex
                        </button>

                        {/* Nifty Options */}
                        {selectedInstruments?.nifty?.call_strike && (
                            <button
                                onClick={() => setSelectedChart({
                                    type: 'OPTION',
                                    symbol: `NIFTY ${selectedInstruments.nifty.call_strike} CE`,
                                    key: selectedInstruments.nifty.call_instrument_key
                                })}
                                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1 ${selectedChart.key === selectedInstruments.nifty.call_instrument_key
                                    ? 'bg-green-50 text-green-700 shadow-sm border border-green-100'
                                    : 'text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                Nifty {selectedInstruments.nifty.call_strike} CE
                            </button>
                        )}

                        {selectedInstruments?.nifty?.put_strike && (
                            <button
                                onClick={() => setSelectedChart({
                                    type: 'OPTION',
                                    symbol: `NIFTY ${selectedInstruments.nifty.put_strike} PE`,
                                    key: selectedInstruments.nifty.put_instrument_key
                                })}
                                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1 ${selectedChart.key === selectedInstruments.nifty.put_instrument_key
                                    ? 'bg-red-50 text-red-700 shadow-sm border border-red-100'
                                    : 'text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                <span className="w-2 h-2 rounded-full bg-red-500"></span>
                                Nifty {selectedInstruments.nifty.put_strike} PE
                            </button>
                        )}

                        {/* Sensex Options */}
                        {selectedInstruments?.sensex?.call_strike && (
                            <button
                                onClick={() => setSelectedChart({
                                    type: 'OPTION',
                                    symbol: `SENSEX ${selectedInstruments.sensex.call_strike} CE`,
                                    key: selectedInstruments.sensex.call_instrument_key
                                })}
                                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1 ${selectedChart.key === selectedInstruments.sensex.call_instrument_key
                                    ? 'bg-green-50 text-green-700 shadow-sm border border-green-100'
                                    : 'text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                Sensex {selectedInstruments.sensex.call_strike} CE
                            </button>
                        )}

                        {selectedInstruments?.sensex?.put_strike && (
                            <button
                                onClick={() => setSelectedChart({
                                    type: 'OPTION',
                                    symbol: `SENSEX ${selectedInstruments.sensex.put_strike} PE`,
                                    key: selectedInstruments.sensex.put_instrument_key
                                })}
                                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap flex items-center gap-1 ${selectedChart.key === selectedInstruments.sensex.put_instrument_key
                                    ? 'bg-red-50 text-red-700 shadow-sm border border-red-100'
                                    : 'text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                <span className="w-2 h-2 rounded-full bg-red-500"></span>
                                Sensex {selectedInstruments.sensex.put_strike} PE
                            </button>
                        )}

                    </div>
                </div>

                {/* Find active position for the selected chart */
                    (() => {
                        const activePosition = positions.find(p => p.instrument_key === selectedChart.key);
                        return (
                            <CandlestickChart
                                key={selectedChart.key} // Force re-mount on change
                                instrumentKey={selectedChart.key}
                                liveTick={liveTicks[selectedChart.key]}
                                symbol={selectedChart.symbol}
                                interval="1minute"
                                activePosition={activePosition}
                            />
                        );
                    })()
                }
            </div>

            {/* Daily Summary */}
            <DailySummary summary={summary} liveStrategyPnl={liveStrategyPnl} />

            {/* Admin Controls */}
            <AdminControls onRefresh={fetchData} />

            {/* Positions Table */}
            <PositionsTable
                positions={positions}
                liveTicks={liveTicks}
                onRowClick={(pos) => {
                    setSelectedChart({
                        type: 'OPTION',
                        symbol: pos.symbol,
                        key: pos.instrument_key
                    });
                }}
            />

            {/* Trade History */}
            <TradeHistoryTable
                trades={trades}
                onRowClick={(event) => {
                    if (event.instrument_key) {
                        setSelectedChart({
                            type: 'OPTION',
                            symbol: `${event.symbol} ${event.strike} ${event.type}`,
                            key: event.instrument_key
                        });
                        // Scroll to chart
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                    }
                }}
            />

            {/* OI PCR Chart */}
            <OIPcrChart oiPcrData={oiPcr} />

            {/* Profile at the bottom */}
            <Profile profile={profile} accountValue={accountValue} />
        </div>
    );
}

export default Dashboard;
