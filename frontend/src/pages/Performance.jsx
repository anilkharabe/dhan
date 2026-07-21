import { useState, useEffect } from 'react';
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
    AreaChart, Area
} from 'recharts';
import apiService from '../api';
import DailySummary from '../components/DailySummary';
import TradeHistoryTable from '../components/TradeHistoryTable';

const INITIAL_CAPITAL = 100000;

// Generic per-tag color assignment (strategy tags are config-driven, e.g. CREDIT_A/CREDIT_B)
const STRATEGY_PALETTE = [
    { hex: '#4F46E5', cls: 'bg-indigo-50 text-indigo-700 border-indigo-100' },
    { hex: '#10B981', cls: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
    { hex: '#F59E0B', cls: 'bg-amber-50 text-amber-700 border-amber-100' },
    { hex: '#EC4899', cls: 'bg-pink-50 text-pink-700 border-pink-100' },
];

const paletteIndex = (tag) => {
    let hash = 0;
    for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0;
    return hash % STRATEGY_PALETTE.length;
};

const getStrategyColor = (tag) => STRATEGY_PALETTE[paletteIndex(tag)].hex;
const getStrategyClass = (tag) => STRATEGY_PALETTE[paletteIndex(tag)].cls;
const StrategyMiniCard = ({ tag, stats }) => (
    <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 relative overflow-hidden group hover:border-blue-400 transition-all duration-300">
        <div className={`absolute top-0 right-0 w-24 h-24 -mr-8 -mt-8 rounded-full opacity-[0.05]`} style={{ backgroundColor: getStrategyColor(tag) }}></div>
        <div className="flex justify-between items-start relative z-10">
            <span className={`px-2 py-0.5 rounded text-[10px] font-black tracking-widest uppercase border ${getStrategyClass(tag)}`}>
                {tag.replace('STRATEGY_', '')}
            </span>
            <span className={`text-sm font-black ${stats.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {stats.pnl >= 0 ? '+' : ''}₹{stats.pnl.toFixed(0)}
            </span>
        </div>
        <div className="flex justify-between text-[10px] font-bold text-gray-400 relative z-10 mt-4">
            <span>{stats.trades} Trades</span>
            <span>{stats.trades > 0 ? ((stats.wins / stats.trades) * 100).toFixed(0) : 0}% WR</span>
        </div>
    </div>
);

function Performance() {
    const [history, setHistory] = useState([]);
    const [strategies, setStrategies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedStrategy, setSelectedStrategy] = useState('ALL');
    const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
    const [dayDetails, setDayDetails] = useState(null);
    const [loadingDay, setLoadingDay] = useState(false);

    useEffect(() => {
        fetchHistory();
    }, []);

    useEffect(() => {
        if (selectedDate) {
            fetchDayDetails(selectedDate);
        }
    }, [selectedDate]);

    const fetchHistory = async () => {
        try {
            setLoading(true);
            const data = await apiService.getPerformanceHistory(30);

            const allStrats = new Set();
            (data.history || []).forEach(day => {
                (day.strategies || []).forEach(s => allStrats.add(s.tag));
            });
            const stratList = Array.from(allStrats).sort();
            setStrategies(stratList);

            let equity = {
                TOTAL: INITIAL_CAPITAL * (stratList.length || 1)
            };
            stratList.forEach(s => equity[s] = INITIAL_CAPITAL);

            const processedData = (data.history || []).map(day => {
                const dayStats = { ...day };
                stratList.forEach(tag => {
                    const stratData = (day.strategies || []).find(s => s.tag === tag) || { pnl: 0 };
                    equity[tag] += stratData.pnl;
                    dayStats[`equity_${tag}`] = equity[tag];
                    dayStats[`pnl_${tag}`] = stratData.pnl;
                });
                equity.TOTAL += day.pnl;
                dayStats.equity_TOTAL = equity.TOTAL;
                return dayStats;
            });

            setHistory(processedData);
            setLoading(false);
        } catch (err) {
            setError(err.message);
            setLoading(false);
        }
    };

    const fetchDayDetails = async (date) => {
        try {
            setLoadingDay(true);
            const data = await apiService.getDayDetails(date);
            setDayDetails(data);
            setLoadingDay(false);
        } catch (err) {
            console.error("Error fetching day details:", err);
            setDayDetails(null);
            setLoadingDay(false);
        }
    };

    const hasHistory = history.length > 0;

    const totalPnl = hasHistory
        ? selectedStrategy === 'ALL'
            ? history.reduce((acc, curr) => acc + curr.pnl, 0)
            : history.reduce((acc, curr) => {
                const s = (curr.strategies || []).find(st => st.tag === selectedStrategy);
                return acc + (s ? s.pnl : 0);
            }, 0)
        : 0;

    const winRate = hasHistory
        ? selectedStrategy === 'ALL'
            ? (history.reduce((acc, curr) => acc + curr.wins, 0) / history.reduce((acc, curr) => acc + curr.trades, 0) * 100)
            : (() => {
                const total = history.reduce((acc, curr) => {
                    const s = (curr.strategies || []).find(st => st.tag === selectedStrategy);
                    return { wins: acc.wins + (s ? s.wins : 0), trades: acc.trades + (s ? s.trades : 0) };
                }, { wins: 0, trades: 0 });
                return total.trades > 0 ? (total.wins / total.trades * 100) : 0;
            })()
        : 0;

    const currentCapital = selectedStrategy === 'ALL' ? INITIAL_CAPITAL * (strategies.length || 1) : INITIAL_CAPITAL;

    const strategyTotals = history.length > 0 ? history.reduce((acc, day) => {
        (day.strategies || []).forEach(strat => {
            if (!acc[strat.tag]) acc[strat.tag] = { pnl: 0, trades: 0, wins: 0, losses: 0 };
            acc[strat.tag].pnl += strat.pnl;
            acc[strat.tag].trades += strat.trades;
            acc[strat.tag].wins += strat.wins;
            acc[strat.tag].losses += strat.losses;
        });
        return acc;
    }, {}) : {};

    const strategyList = Object.entries(strategyTotals).sort((a, b) => b[1].pnl - a[1].pnl);

    if (loading) {
        return (
            <div className="flex justify-center items-center h-96">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-8 pb-12">
            {/* Strategy Selection & Allocation Banner */}
            <div className="flex flex-col items-center gap-4 mb-8">
                <div className="flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-full border border-blue-100 shadow-sm">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" /><path fillRule="evenodd" d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z" clipRule="evenodd" /></svg>
                    <span className="text-xs font-black uppercase tracking-widest">Independent Allocation: ₹{INITIAL_CAPITAL.toLocaleString()} per Strategy</span>
                </div>
                <div className="flex flex-wrap justify-center bg-white p-1 rounded-xl shadow-lg border border-gray-100 overflow-hidden gap-1">
                    {['ALL', ...strategies].map(strat => (
                        <button
                            key={strat}
                            onClick={() => setSelectedStrategy(strat)}
                            className={`px-4 py-2 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all duration-300 ${selectedStrategy === strat
                                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md scale-105 z-10'
                                : 'text-gray-400 hover:bg-gray-50'
                                }`}
                        >
                            {strat === 'ALL' ? 'ALL' : strat.replace('STRATEGY_', '')}
                        </button>
                    ))}
                </div>
            </div>

            {/* Header Stats Breakdown */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
                    <p className="text-xs text-gray-400 font-black uppercase tracking-widest mb-1">Total P&L (30d)</p>
                    <p className={`text-3xl font-black ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(2)}
                    </p>
                    <div className="mt-3 pt-3 border-t border-gray-50 flex justify-between items-center">
                        <span className="text-xs text-gray-400 font-medium">Starting Core</span>
                        <span className="text-xs text-gray-600 font-bold">₹{currentCapital.toLocaleString()}</span>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
                    <p className="text-xs text-gray-400 font-black uppercase tracking-widest mb-1">Win Rate Ratio</p>
                    <p className="text-3xl font-black text-blue-600">
                        {winRate.toFixed(1)}%
                    </p>
                    <div className="mt-3 pt-3 border-t border-gray-50 flex justify-between items-center text-xs text-gray-400">
                        <span>Success Factor</span>
                        <span className="text-gray-600 font-bold">{selectedStrategy === 'ALL' ? 'Aggregate' : 'Isolated'}</span>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
                    <p className="text-xs text-gray-400 font-black uppercase tracking-widest mb-1">Current Balance</p>
                    <p className="text-3xl font-black text-indigo-600">
                        ₹{(currentCapital + totalPnl).toLocaleString()}
                    </p>
                    <div className="mt-3 pt-3 border-t border-gray-50 flex justify-between items-center">
                        <span className="text-xs text-gray-400 font-medium">ROI Intensity</span>
                        <span className={`text-xs font-bold ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {((totalPnl / currentCapital) * 100).toFixed(2)}%
                        </span>
                    </div>
                </div>
            </div>

            {/* Advanced Metrics Cards */}
            {(() => {
                const metrics = hasHistory ? history.reduce((acc, curr) => {
                    const pnl = selectedStrategy === 'ALL'
                        ? curr.pnl
                        : ((curr.strategies || []).find(s => s.tag === selectedStrategy)?.pnl || 0);

                    if (pnl > 0) acc.grossProfit += pnl;
                    else acc.grossLoss += Math.abs(pnl);

                    const equity = selectedStrategy === 'ALL'
                        ? curr.equity_TOTAL
                        : curr[`equity_${selectedStrategy}`];

                    if (equity > acc.peak) acc.peak = equity;
                    const dd = ((acc.peak - equity) / acc.peak) * 100;
                    if (dd > acc.maxDD) acc.maxDD = dd;

                    return acc;
                }, { grossProfit: 0, grossLoss: 0, peak: currentCapital, maxDD: 0 }) : null;

                const profitFactor = metrics && metrics.grossLoss > 0 ? (metrics.grossProfit / metrics.grossLoss).toFixed(2) : '∞';

                const stats = selectedStrategy === 'ALL'
                    ? { wins: history.reduce((a, c) => a + c.wins, 0), trades: history.reduce((a, c) => a + c.trades, 0), profit: history.reduce((a, c) => a + (c.pnl > 0 ? c.pnl : 0), 0), loss: history.reduce((a, c) => a + (c.pnl < 0 ? Math.abs(c.pnl) : 0), 0), winDays: history.reduce((a, c) => a + (c.pnl > 0 ? 1 : 0), 0), lossDays: history.reduce((a, c) => a + (c.pnl < 0 ? 1 : 0), 0) }
                    : (() => {
                        return history.reduce((acc, curr) => {
                            const s = (curr.strategies || []).find(st => st.tag === selectedStrategy) || { wins: 0, trades: 0, pnl: 0 };
                            return {
                                wins: acc.wins + s.wins,
                                trades: acc.trades + s.trades,
                                profit: acc.profit + (s.pnl > 0 ? s.pnl : 0),
                                loss: acc.loss + (s.pnl < 0 ? Math.abs(s.pnl) : 0),
                                winDays: acc.winDays + (s.pnl > 0 ? 1 : 0),
                                lossDays: acc.lossDays + (s.pnl < 0 ? 1 : 0)
                            };
                        }, { wins: 0, trades: 0, profit: 0, loss: 0, winDays: 0, lossDays: 0 });
                    })();

                return (
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="bg-gray-50/50 p-4 rounded-xl border border-gray-100">
                            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">Profit Factor</p>
                            <p className="text-xl font-black text-gray-800">{profitFactor}</p>
                        </div>
                        <div className="bg-gray-50/50 p-4 rounded-xl border border-gray-100">
                            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">Max Drawdown</p>
                            <p className="text-xl font-black text-red-500">{metrics?.maxDD.toFixed(1)}%</p>
                        </div>
                        <div className="bg-gray-50/50 p-4 rounded-xl border border-gray-100">
                            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">Avg Session Profit</p>
                            <p className="text-xl font-black text-green-600">
                                ₹{stats.winDays > 0 ? (stats.profit / stats.winDays).toFixed(0) : 0}
                            </p>
                        </div>
                        <div className="bg-gray-50/50 p-4 rounded-xl border border-gray-100">
                            <p className="text-[10px] text-gray-400 font-black uppercase tracking-widest mb-1">Avg Session loss</p>
                            <p className="text-xl font-black text-red-600">
                                ₹{stats.lossDays > 0 ? (stats.loss / stats.lossDays).toFixed(0) : 0}
                            </p>
                        </div>
                    </div>
                );
            })()}

            {/* Strategy Comparison Cards */}
            {selectedStrategy === 'ALL' && strategyList.length > 0 && (
                <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-1.5 h-6 bg-blue-600 rounded-full"></div>
                        <h4 className="text-sm font-black text-gray-700 uppercase tracking-widest">Strategy Breakdown</h4>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {strategyList.map(([tag, stats]) => (
                            <StrategyMiniCard key={tag} tag={tag} stats={stats} />
                        ))}
                    </div>
                </div>
            )}


            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-lg font-bold text-gray-700">Equity Progression</h3>
                        <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Growth Curve</span>
                    </div>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={history}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F3F4F6" />
                                <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#9CA3AF' }} axisLine={false} tickLine={false} tickFormatter={(val) => {
                                    const d = new Date(val);
                                    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
                                }} />
                                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                                <RechartsTooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }} />
                                <Legend verticalAlign="top" align="right" height={36} iconType="circle" wrapperStyle={{ fontSize: '10px', fontWeight: 'bold' }} />

                                {strategies.map(tag => (
                                    (selectedStrategy === 'ALL' || selectedStrategy === tag) && (
                                        <Area
                                            key={tag}
                                            name={tag.replace('STRATEGY_', '')}
                                            type="monotone"
                                            dataKey={`equity_${tag}`}
                                            stroke={getStrategyColor(tag)}
                                            strokeWidth={selectedStrategy === tag ? 3 : 1.5}
                                            fillOpacity={selectedStrategy === 'ALL' ? 0.05 : 0.2}
                                            fill={getStrategyColor(tag)}
                                        />
                                    )
                                ))}
                                {selectedStrategy === 'ALL' && <Line name="Combined Core" type="monotone" dataKey="equity_TOTAL" stroke="#94A3B8" strokeDasharray="4 4" dot={false} strokeWidth={1} />}
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-lg font-bold text-gray-700">Daily P&L Comparison</h3>
                        <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Session Results</span>
                    </div>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={history}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F3F4F6" />
                                <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#9CA3AF' }} axisLine={false} tickLine={false} tickFormatter={(val) => {
                                    const d = new Date(val);
                                    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
                                }} />
                                <YAxis tick={{ fontSize: 9, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                                <RechartsTooltip cursor={{ fill: '#F9FAFB' }} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }} />
                                <Legend verticalAlign="top" align="right" height={36} iconType="rect" wrapperStyle={{ fontSize: '10px', fontWeight: 'bold' }} />

                                {strategies.map(tag => (
                                    (selectedStrategy === 'ALL' || selectedStrategy === tag) && (
                                        <Bar
                                            key={tag}
                                            name={tag.replace('STRATEGY_', '')}
                                            dataKey={`pnl_${tag}`}
                                            fill={getStrategyColor(tag)}
                                            radius={[4, 4, 0, 0]}
                                            barSize={selectedStrategy === 'ALL' ? Math.max(4, 40 / strategies.length) : 40}
                                        />
                                    )
                                ))}
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Daily Detailed Breakdown */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="p-6 border-b border-gray-50 flex justify-between items-center bg-gray-50/50">
                    <h3 className="text-lg font-bold text-gray-700">Daily Drill-down</h3>
                    <div className="flex items-center gap-3">
                        <label className="text-xs text-gray-400 font-black uppercase tracking-widest">Target Date</label>
                        <input
                            type="date"
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="bg-white border border-gray-200 rounded-xl px-4 py-2 text-sm font-bold text-gray-700 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
                        />
                    </div>
                </div>

                {loadingDay ? (
                    <div className="p-24 flex flex-col items-center justify-center gap-4">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        <p className="text-xs font-black text-gray-400 uppercase tracking-widest">Retrieving Details...</p>
                    </div>
                ) : dayDetails && dayDetails.stats ? (
                    <div className="p-8 space-y-10">
                        {/* Daily Strategy Cards */}
                        {dayDetails.stats.strategy_wise && (
                            <div className="space-y-6">
                                <div className="flex items-center gap-4">
                                    <h4 className="text-xs font-black text-gray-400 uppercase tracking-[0.2em]">Daily Strategy Variance</h4>
                                    <div className="h-[1px] bg-gray-100 flex-grow"></div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    {Object.entries(dayDetails.stats.strategy_wise).map(([tag, data]) => (
                                        <div key={tag} className="p-6 bg-gray-50/50 rounded-2xl border border-gray-100 flex flex-col justify-between group hover:bg-white hover:shadow-xl hover:border-blue-200 transition-all duration-500">
                                            <div className="flex justify-between items-center mb-6">
                                                <span className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${getStrategyClass(tag)}`}>
                                                    {tag.replace('STRATEGY_', '')}
                                                </span>
                                                <span className={`text-2xl font-black ${data.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                                    {data.pnl >= 0 ? '+' : ''}₹{data.pnl}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center border-t border-gray-100 pt-4 mt-2">
                                                <div className="flex flex-col">
                                                    <span className="text-[10px] text-gray-400 uppercase font-bold">Activity</span>
                                                    <span className="text-sm font-black text-gray-700">{data.trades} Trades</span>
                                                </div>
                                                <div className="text-right">
                                                    <span className="text-[10px] text-gray-400 uppercase font-bold">Accuracy</span>
                                                    <div className="text-sm font-black text-blue-600">
                                                        {data.trades > 0 ? (data.wins / data.trades * 100).toFixed(1) : 0}%
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Full Day Aggregate Stats */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 bg-gradient-to-br from-gray-50 to-white p-6 rounded-3xl border border-gray-100">
                            <div>
                                <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-1">Total Realized</p>
                                <p className={`text-xl font-black ${(selectedStrategy === 'ALL' ? dayDetails.stats.total_pnl : (dayDetails.stats.strategy_wise[selectedStrategy]?.pnl || 0)) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {(selectedStrategy === 'ALL' ? dayDetails.stats.total_pnl : (dayDetails.stats.strategy_wise[selectedStrategy]?.pnl || 0)) >= 0 ? '+' : ''}₹{(selectedStrategy === 'ALL' ? dayDetails.stats.total_pnl : (dayDetails.stats.strategy_wise[selectedStrategy]?.pnl || 0)).toLocaleString()}
                                </p>
                            </div>
                            <div>
                                <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-1">Total Events</p>
                                <p className="text-xl font-black text-gray-800">
                                    {selectedStrategy === 'ALL' ? dayDetails.stats.total_trades : (dayDetails.stats.strategy_wise[selectedStrategy]?.trades || 0)} Executions
                                </p>
                            </div>
                            <div>
                                <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-1">Aggregate WR</p>
                                <p className="text-xl font-black text-blue-600">
                                    {selectedStrategy === 'ALL'
                                        ? dayDetails.stats.win_rate
                                        : (dayDetails.stats.strategy_wise[selectedStrategy]?.trades > 0
                                            ? ((dayDetails.stats.strategy_wise[selectedStrategy].wins / dayDetails.stats.strategy_wise[selectedStrategy].trades) * 100).toFixed(1)
                                            : 0)}%
                                </p>
                            </div>
                            <div>
                                <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-1">Efficiency</p>
                                {selectedStrategy === 'ALL' ? (
                                    <>
                                        <p className="text-xs font-bold text-green-600">Best: +₹{dayDetails.stats.max_win}</p>
                                        <p className="text-xs font-bold text-red-600">Worst: ₹{dayDetails.stats.max_loss}</p>
                                    </>
                                ) : (
                                    <div className="flex flex-col">
                                        <span className="text-[10px] text-gray-400 uppercase font-bold">Wins/Losses</span>
                                        <span className="text-xs font-black text-gray-600">
                                            {dayDetails.stats.strategy_wise[selectedStrategy]?.wins || 0}W / {dayDetails.stats.strategy_wise[selectedStrategy]?.losses || 0}L
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Trade History Table Overlay */}
                        <div className="pt-8">
                            <div className="flex items-center gap-4 mb-6">
                                <h4 className="text-xs font-black text-gray-400 uppercase tracking-[0.2em]">Execution Log</h4>
                                <div className="h-[1px] bg-gray-100 flex-grow"></div>
                            </div>
                            {dayDetails.trades && dayDetails.trades.length > 0 ? (
                                <TradeHistoryTable
                                    trades={selectedStrategy === 'ALL'
                                        ? dayDetails.trades
                                        : dayDetails.trades.filter(t => t.strategy_tag === selectedStrategy)
                                    }
                                />
                            ) : (
                                <div className="text-center py-16 text-gray-300 bg-gray-50/50 rounded-3xl border-2 border-dashed border-gray-100 font-bold uppercase text-xs tracking-widest">
                                    No transaction logs for this period
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="p-24 text-center">
                        <div className="w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-4 border border-gray-100">
                            <svg className="w-8 h-8 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                        </div>
                        <p className="text-xs font-black text-gray-400 uppercase tracking-widest">Select a valid date for analysis</p>
                    </div>
                )}
            </div>
        </div>
    );
}

export default Performance;
