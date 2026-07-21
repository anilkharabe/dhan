import { useState, useEffect, useRef } from 'react';
import apiService from '../api';

const ALL_SCENARIOS = [
    { key: 'CREDIT_SPREAD', label: 'Credit Spread (Selling)', color: '#0D9488', group: 'Credit' },
];

const fmt = (n) => n == null ? '—' : `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
const fmtPct = (n) => n == null ? '—' : `${Number(n).toFixed(1)}%`;
const fmtNum = (n, d = 2) => n == null ? '—' : Number(n).toFixed(d);

function todayStr() { return new Date().toISOString().slice(0, 10); }

// ── Rating badge ──────────────────────────────────────────────────────────
const RATING_STYLES = {
    emerald: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    blue: 'bg-blue-100 text-blue-700 border-blue-200',
    amber: 'bg-amber-100 text-amber-700 border-amber-200',
    red: 'bg-red-100 text-red-700 border-red-200',
};
const INSIGHT_STYLES = {
    positive: 'bg-emerald-50 border-emerald-100 text-emerald-700',
    neutral: 'bg-gray-50 border-gray-100 text-gray-600',
    warning: 'bg-amber-50 border-amber-100 text-amber-700',
    negative: 'bg-red-50 border-red-100 text-red-700',
};

// ── Pill indicator badge ───────────────────────────────────────────────────
function IndicatorPill({ label, value, ok, na }) {
    const base = na ? 'bg-gray-50 text-gray-400 border-gray-100' :
        ok ? 'bg-emerald-50 text-emerald-700 border-emerald-100' :
            'bg-red-50 text-red-600 border-red-100';
    return (
        <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg border ${base}`}>
            {!na && (ok ? '✓' : '✗')} {label}: {value}
        </span>
    );
}

// ── AI Analysis Panel ─────────────────────────────────────────────────────
function AIAnalysisPanel({ ai }) {
    if (!ai) return (
        <div className="mt-3 bg-gray-50 border border-gray-100 rounded-xl p-4 text-xs text-gray-400 text-center">
            No indicator data captured for this trade
        </div>
    );

    const ratingStyle = RATING_STYLES[ai.rating_color] || RATING_STYLES.amber;

    return (
        <div className="mt-3 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/60 to-purple-50/40 p-4 space-y-3">
            {/* Header row */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-indigo-700">🤖 AI Analysis</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-lg border ${ratingStyle}`}>
                        {ai.rating} — {ai.rating_label}
                    </span>
                </div>
                {/* Score bar */}
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{ai.score}/100</span>
                    <div className="w-20 h-2 rounded-full bg-gray-200 overflow-hidden">
                        <div
                            className={`h-2 rounded-full ${ai.score >= 75 ? 'bg-emerald-500' : ai.score >= 55 ? 'bg-blue-500' : ai.score >= 35 ? 'bg-amber-400' : 'bg-red-400'}`}
                            style={{ width: `${ai.score}%` }}
                        />
                    </div>
                </div>
            </div>

            {/* Summary */}
            <p className="text-xs text-gray-600 italic leading-relaxed">"{ai.summary}"</p>

            {/* Insight chips */}
            <div className="space-y-1.5">
                {ai.insights.map((ins, i) => (
                    <div key={i} className={`flex items-start gap-2 text-xs px-3 py-2 rounded-lg border ${INSIGHT_STYLES[ins.type] || INSIGHT_STYLES.neutral}`}>
                        <span className="shrink-0 text-sm leading-4">{ins.icon}</span>
                        <span className="leading-4">{ins.text}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Single trade row (expandable) ─────────────────────────────────────────
function TradeRow({ t, idx }) {
    const [expanded, setExpanded] = useState(false);
    const pnl = t.pnl ?? 0;
    const hasIndicators = t.rsi || t.adx || t.vwap;

    return (
        <>
            <tr
                className={`border-t border-gray-50 cursor-pointer hover:bg-indigo-50/30 transition-colors ${idx % 2 ? 'bg-gray-50/30' : ''}`}
                onClick={() => setExpanded(e => !e)}
            >
                {/* Option type */}
                <td className="px-3 py-2.5">
                    {t.is_spread ? (
                        <span className="font-bold text-xs px-1.5 py-0.5 rounded bg-teal-50 text-teal-700">
                            {t.spread_type === 'BULL_PUT' ? 'BULL PUT' : t.spread_type === 'BEAR_CALL' ? 'BEAR CALL' : t.spread_type}
                        </span>
                    ) : (
                        <span className={`font-bold text-xs px-1.5 py-0.5 rounded ${t.option_type === 'CE' || t.option_type === 'CALL' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
                            {t.option_type || '—'}
                        </span>
                    )}
                </td>
                {/* Strike */}
                <td className="px-3 py-2.5 font-mono text-gray-700 text-xs">
                    {t.is_spread ? `S${t.strike} / L${t.far_strike}` : (t.strike ?? '—')}
                </td>
                {/* Entry / Exit */}
                <td className="px-3 py-2.5 text-gray-500 text-xs">{t.entry_time ?? '—'}</td>
                <td className="px-3 py-2.5 text-gray-500 text-xs">{t.exit_time ?? '—'}</td>
                {/* Prices */}
                <td className="px-3 py-2.5 font-mono text-xs">₹{fmtNum(t.entry_price)}</td>
                <td className="px-3 py-2.5 font-mono text-xs">₹{fmtNum(t.exit_price ?? 0)}</td>
                {/* P&L */}
                <td className={`px-3 py-2.5 font-bold text-xs ${pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmt(pnl)}</td>
                <td className={`px-3 py-2.5 text-xs ${pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmtPct(t.pnl_percent)}</td>
                {/* Indicators summary */}
                <td className="px-3 py-2.5">
                    {hasIndicators ? (
                        <div className="flex gap-1 flex-wrap">
                            <span className={`text-xs font-mono px-1.5 py-0.5 rounded font-medium ${(t.rsi ?? 100) <= 40 ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                                RSI {fmtNum(t.rsi, 0)}
                            </span>
                            <span className={`text-xs font-mono px-1.5 py-0.5 rounded font-medium ${(t.adx ?? 0) >= 20 ? 'bg-blue-50 text-blue-700' : 'bg-gray-50 text-gray-500'}`}>
                                ADX {fmtNum(t.adx, 0)}
                            </span>
                        </div>
                    ) : <span className="text-gray-300 text-xs">—</span>}
                </td>
                {/* AI Rating */}
                <td className="px-3 py-2.5">
                    {t.ai_analysis ? (
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-lg border ${RATING_STYLES[t.ai_analysis.rating_color] || ''}`}>
                            {t.ai_analysis.rating}
                        </span>
                    ) : <span className="text-gray-300 text-xs">—</span>}
                </td>
                {/* Expand toggle */}
                <td className="px-3 py-2.5 text-gray-300 text-xs">{expanded ? '▲' : '▼'}</td>
            </tr>

            {/* Expanded row — indicators + AI analysis */}
            {expanded && (
                <tr className="border-t border-indigo-50">
                    <td colSpan={11} className="px-5 py-3 bg-indigo-50/20">
                        {/* Indicator pills */}
                        {hasIndicators && (
                            <div className="flex flex-wrap gap-2 mb-3">
                                <IndicatorPill label="RSI" value={fmtNum(t.rsi, 1)} ok={(t.rsi ?? 100) <= 40} />
                                <IndicatorPill label="ADX" value={fmtNum(t.adx, 1)} ok={(t.adx ?? 0) >= 20} />
                                <IndicatorPill label="VWAP" value={`₹${fmtNum(t.vwap)}`} ok={t.price_below_vwap} />
                                <IndicatorPill label="OI" value={Number(t.oi ?? 0).toLocaleString()} ok={t.oi_above_sma} />
                                <IndicatorPill label="OI SMA" value={Number(t.oi_sma ?? 0).toLocaleString()} na />
                                <IndicatorPill label="Vol Ratio" value={`${fmtNum(t.volume_ratio, 0)}%`} ok={(t.volume_ratio ?? 0) >= 100} />
                                <IndicatorPill label="Close@Entry" value={`₹${fmtNum(t.close_at_entry)}`} na />
                                {t.is_spread && <IndicatorPill label="Net Credit" value={`₹${fmtNum(t.net_credit)}`} na />}
                                <IndicatorPill label="Strategy" value={t.strategy_tag || '—'} na />
                                <IndicatorPill label="Exit" value={t.exit_reason || '—'} na />
                            </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                            {/* Left Col: AI Analysis */}
                            <div>
                                <AIAnalysisPanel ai={t.ai_analysis} />
                            </div>

                            {/* Right Col: Trade Timeline */}
                            <div>
                                {t.timeline && t.timeline.length > 0 ? (
                                    <div className="rounded-xl border border-indigo-100 bg-white p-4 space-y-3 h-full max-h-64 overflow-y-auto">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="text-sm font-bold text-indigo-700">⏱️ Trade Timeline</span>
                                        </div>
                                        <div className="relative border-l border-indigo-200 ml-2 space-y-4">
                                            {t.timeline.map((event, i) => (
                                                <div key={i} className="relative pl-4">
                                                    {/* Timeline Dot */}
                                                    <div className={`absolute -left-1.5 top-1 h-3 w-3 rounded-full border-2 border-white ${event.event === 'ENTRY' ? 'bg-blue-500' :
                                                            event.event.includes('EXIT') ? 'bg-indigo-600' :
                                                                event.event === 'TARGET_HIT' ? 'bg-emerald-500' :
                                                                    'bg-gray-400'
                                                        }`}></div>

                                                    <div className="text-[10px] text-gray-400 font-mono mb-0.5">{event.time}</div>
                                                    <div className="text-xs font-semibold text-gray-800">{event.event.replace('_', ' ')}</div>
                                                    <div className="text-xs text-gray-600 mt-0.5 leading-relaxed">{event.details}</div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="mt-3 bg-gray-50 border border-gray-100 rounded-xl p-4 text-xs text-gray-400 text-center h-full flex items-center justify-center">
                                        No timeline data recorded
                                    </div>
                                )}
                            </div>
                        </div>

                    </td>
                </tr>
            )}
        </>
    );
}

// ── Scenario metric card ───────────────────────────────────────────────────
function MetricCard({ label, value, sub, highlight }) {
    return (
        <div className={`rounded-xl p-4 border ${highlight ? 'bg-indigo-50 border-indigo-200' : 'bg-white border-gray-100'} shadow-sm`}>
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-1">{label}</p>
            <p className={`text-xl font-bold ${highlight ? 'text-indigo-700' : 'text-gray-800'}`}>{value}</p>
            {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
        </div>
    );
}

// ── Scenario result card ───────────────────────────────────────────────────
function ScenarioCard({ scenarioKey, data, isExpanded, onToggle }) {
    const meta = ALL_SCENARIOS.find(s => s.key === scenarioKey) || { label: scenarioKey, color: '#6B7280' };
    const m = data.metrics || {};
    const pnl = m.total_pnl ?? 0;
    const isError = !!data.error;

    return (
        <div className="rounded-2xl border border-gray-100 bg-white shadow-sm overflow-hidden">
            {/* Header */}
            <div
                className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={onToggle}
                style={{ borderLeft: `4px solid ${meta.color}` }}
            >
                <div className="flex items-center gap-3">
                    <span className="text-xs font-bold px-2.5 py-1 rounded-full text-white" style={{ background: meta.color }}>
                        {meta.group}
                    </span>
                    <div>
                        <p className="font-semibold text-gray-800 text-sm">{data.scenario_name || meta.label}</p>
                        {isError && <p className="text-xs text-red-500 mt-0.5">{data.error}</p>}
                    </div>
                </div>
                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className={`font-bold text-lg ${pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmt(pnl)}</p>
                        <p className="text-xs text-gray-400">{m.total_trades ?? 0} trades · {fmtPct(m.win_rate)} WR</p>
                    </div>
                    <span className="text-gray-300 text-lg">{isExpanded ? '▲' : '▼'}</span>
                </div>
            </div>

            {/* Expanded */}
            {isExpanded && !isError && (
                <div className="border-t border-gray-50 px-5 py-4">
                    <div className="grid grid-cols-4 gap-3 mb-4">
                        <MetricCard label="Total P&L" value={fmt(m.total_pnl)} highlight />
                        <MetricCard label="Win Rate" value={fmtPct(m.win_rate)} sub={`${m.winning_trades ?? 0}W / ${m.losing_trades ?? 0}L`} />
                        <MetricCard label="Profit Factor" value={fmtNum(m.profit_factor)} />
                        <MetricCard label="Max Drawdown" value={fmt(m.max_drawdown)} />
                        <MetricCard label="Avg Win" value={fmt(m.avg_win)} />
                        <MetricCard label="Avg Loss" value={fmt(m.avg_loss)} />
                        <MetricCard label="Best Trade" value={fmt(m.largest_win)} />
                        <MetricCard label="Worst Trade" value={fmt(m.largest_loss)} />
                    </div>

                    {data.trades && data.trades.length > 0 ? (
                        <div className="overflow-x-auto rounded-xl border border-gray-100">
                            <table className="w-full text-xs min-w-[900px]">
                                <thead>
                                    <tr className="bg-gray-50">
                                        {['Type', 'Strike', 'Entry', 'Exit', 'Entry ₹', 'Exit ₹', 'P&L', 'P&L%', 'Indicators', 'AI', ''].map(h => (
                                            <th key={h} className="px-3 py-2 text-left text-gray-400 font-semibold">{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.trades.map((t, i) => <TradeRow key={i} t={t} idx={i} />)}
                                </tbody>
                            </table>
                        </div>
                    ) : (
                        <p className="text-center text-gray-400 text-sm py-4">No trades simulated for this scenario</p>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Log console component ──────────────────────────────────────────────────
function LogConsole({ lines }) {
    const ref = useRef(null);
    useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [lines]);
    return (
        <div ref={ref} className="bg-gray-900 rounded-xl p-4 h-48 overflow-y-auto font-mono text-xs text-green-400 border border-gray-700">
            {lines.length === 0 && <span className="text-gray-500">Output will appear here…</span>}
            {lines.map((l, i) => (
                <div key={i} className={`leading-5 ${l.includes('❌') || l.includes('Error') ? 'text-red-400' : l.includes('✅') || l.includes('Done') ? 'text-emerald-400' : 'text-green-300'}`}>{l}</div>
            ))}
        </div>
    );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function Backtest() {
    const [date, setDate] = useState(todayStr());
    const [candleStatus, setCandleStatus] = useState(null);
    const [candleStatusLoading, setCandleStatusLoading] = useState(false);
    const [fetchRunning, setFetchRunning] = useState(false);
    const [fetchLogs, setFetchLogs] = useState([]);
    const [fetchDone, setFetchDone] = useState(false);
    const [selectedScenarios, setSelectedScenarios] = useState(['CREDIT_SPREAD']);
    const [btRunning, setBtRunning] = useState(false);
    const [btResults, setBtResults] = useState(null);
    const [btError, setBtError] = useState(null);
    const [expandedCard, setExpandedCard] = useState(null);

    useEffect(() => { checkCandleStatus(); }, [date]);

    async function checkCandleStatus() {
        setCandleStatusLoading(true);
        try { const r = await apiService.backtestCandleStatus(date); setCandleStatus(r); } catch { setCandleStatus(null); }
        setCandleStatusLoading(false);
    }

    function toggleScenario(key) {
        setSelectedScenarios(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
    }

    async function handleFetch() {
        setFetchRunning(true); setFetchDone(false); setFetchLogs([]);
        const baseUrl = apiService.getBaseUrl();
        try {
            const resp = await fetch(`${baseUrl}/api/backtest/fetch-candles`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date })
            });
            const reader = resp.body.getReader(); const decoder = new TextDecoder(); let buf = '';
            while (true) {
                const { done, value } = await reader.read(); if (done) break;
                buf += decoder.decode(value, { stream: true });
                const parts = buf.split('\n\n'); buf = parts.pop();
                for (const part of parts) {
                    if (part.startsWith('data: ')) {
                        try {
                            const payload = JSON.parse(part.slice(6));
                            if (payload.line !== undefined) setFetchLogs(p => [...p, payload.line]);
                            if (payload.done) { setFetchDone(true); setFetchRunning(false); checkCandleStatus(); }
                        } catch { }
                    }
                }
            }
        } catch (e) { setFetchLogs(p => [...p, `❌ Error: ${e.message}`]); setFetchRunning(false); }
    }

    async function handleRunBacktest() {
        if (!selectedScenarios.length) return;
        setBtRunning(true); setBtResults(null); setBtError(null); setExpandedCard(null);
        try {
            const resp = await apiService.runBacktest(date, selectedScenarios);
            if (!resp?.results) {
                throw new Error('Backtest returned no results — check the API server logs.');
            }
            setBtResults(resp);
            const firstKey = Object.keys(resp.results)[0];
            if (firstKey) setExpandedCard(firstKey);
        } catch (e) { setBtError(e?.response?.data?.error || e.message); }
        setBtRunning(false);
    }

    const hasData = candleStatus?.has_data;
    const bestScenario = btResults?.results
        ? Object.entries(btResults.results).filter(([, d]) => !d.error && d.metrics?.total_trades > 0)
            .sort(([, a], [, b]) => (b.metrics?.total_pnl ?? 0) - (a.metrics?.total_pnl ?? 0))[0]
        : null;

    const Spinner = () => <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" /></svg>;

    return (
        <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">

            {/* ── Header ── */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">📊 Backtesting Lab</h1>
                    <p className="text-sm text-gray-400 mt-1">Fetch 1-min candle data · Replay strategies · AI-rated trade analysis</p>
                </div>
                <div className="flex items-center gap-3">
                    <label className="text-sm text-gray-500 font-medium">Date</label>
                    <input type="date" value={date} max={todayStr()} onChange={e => setDate(e.target.value)}
                        className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                </div>
            </div>

            {/* ── Step 1: Fetch ── */}
            <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                            <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center">1</span>
                            Fetch Candle Data
                        </h2>
                        <p className="text-xs text-gray-400 mt-1 ml-8">ATM ±4 strikes (NIFTY + SENSEX, CE + PE) → 36 instruments → MongoDB</p>
                    </div>
                    <div className="flex items-center gap-2">
                        {candleStatusLoading && <span className="text-xs text-gray-400 animate-pulse">Checking…</span>}
                        {!candleStatusLoading && candleStatus && (
                            <span className={`text-xs font-semibold px-3 py-1 rounded-full ${hasData ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                                {hasData ? `✅ ${candleStatus.fetch_log?.total_candles_saved ?? candleStatus.candle_count ?? '?'} candles` : '⚠️ No data'}
                            </span>
                        )}
                    </div>
                </div>
                <button onClick={handleFetch} disabled={fetchRunning}
                    className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm ${fetchRunning ? 'bg-indigo-100 text-indigo-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}>
                    {fetchRunning ? <><Spinner /> Fetching…</> : <>⬇️ Fetch Candles for {date}</>}
                </button>
                {(fetchLogs.length > 0 || fetchRunning) && (
                    <div className="mt-4">
                        <LogConsole lines={fetchLogs} />
                        {fetchDone && <p className="mt-2 text-xs text-emerald-600 font-semibold">✅ Fetch complete — ready to backtest!</p>}
                    </div>
                )}
            </section>

            {/* ── Step 2: Run ── */}
            <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
                <h2 className="font-semibold text-gray-800 flex items-center gap-2 mb-4">
                    <span className="w-6 h-6 rounded-full bg-purple-100 text-purple-600 text-xs font-bold flex items-center justify-center">2</span>
                    Run Strategy Backtest
                </h2>
                <div className="mb-5">
                    <p className="text-xs text-gray-400 font-medium mb-3">Select scenarios:</p>
                    <div className="flex flex-wrap gap-2">
                        {ALL_SCENARIOS.map(s => {
                            const active = selectedScenarios.includes(s.key);
                            return (
                                <button key={s.key} onClick={() => toggleScenario(s.key)}
                                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${active ? 'text-white border-transparent shadow-sm' : 'bg-white text-gray-500 border-gray-200 hover:border-gray-300'}`}
                                    style={active ? { background: s.color, borderColor: s.color } : {}}>
                                    {s.label}
                                </button>
                            );
                        })}
                    </div>
                    <p className="text-xs text-gray-400 mt-2">{selectedScenarios.length} scenario{selectedScenarios.length !== 1 ? 's' : ''} selected</p>
                </div>
                <div className="flex items-center gap-3">
                    <button onClick={handleRunBacktest} disabled={btRunning || !selectedScenarios.length}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm ${btRunning || !selectedScenarios.length ? 'bg-purple-100 text-purple-400 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white'}`}>
                        {btRunning ? <><Spinner /> Running…</> : <>▶️ Run Backtest</>}
                    </button>
                    {!hasData && !btRunning && !selectedScenarios.every(k => k === 'CREDIT_SPREAD') && (
                        <p className="text-xs text-amber-500">⚠️ Fetch candle data first (Step 1)</p>
                    )}
                    {selectedScenarios.includes('CREDIT_SPREAD') && !btRunning && (
                        <p className="text-xs text-teal-600">ℹ️ Credit Spread fetches its own candles on demand — Step 1 not required for it</p>
                    )}
                </div>
                {btError && (
                    <div className="mt-4 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">❌ {btError}</div>
                )}
            </section>

            {/* ── Results ── */}
            {btResults?.results && (
                <section className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="font-semibold text-gray-800">Results — {btResults.date}</h2>
                        {bestScenario && (
                            <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2 text-sm">
                                🏆 Best: <span className="font-bold text-emerald-700">{ALL_SCENARIOS.find(s => s.key === bestScenario[0])?.label ?? bestScenario[0]}</span>
                                <span className="text-emerald-600 font-semibold ml-2">{fmt(bestScenario[1].metrics?.total_pnl)}</span>
                            </div>
                        )}
                    </div>

                    {/* Summary table */}
                    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-gray-50 border-b border-gray-100">
                                    {['Scenario', 'Trades', 'Win Rate', 'Total P&L', 'Avg P&L', 'Profit Factor', 'Drawdown'].map(h => (
                                        <th key={h} className={`px-4 py-3 text-gray-400 font-semibold text-xs ${h === 'Scenario' ? 'text-left' : 'text-right'}`}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(btResults.results).map(([key, data]) => {
                                    const m = data.metrics || {};
                                    const pnl = m.total_pnl ?? 0;
                                    const isBest = bestScenario && bestScenario[0] === key;
                                    return (
                                        <tr key={key} onClick={() => setExpandedCard(expandedCard === key ? null : key)}
                                            className={`border-b border-gray-50 cursor-pointer hover:bg-gray-50 transition-colors ${isBest ? 'bg-emerald-50/50' : ''}`}>
                                            <td className="px-4 py-3 text-xs font-medium text-gray-700">
                                                {isBest && <span className="text-emerald-500 mr-1">🏆</span>}{data.scenario_name || key}
                                            </td>
                                            <td className="px-4 py-3 text-right text-gray-600 text-xs">{m.total_trades ?? '—'}</td>
                                            <td className="px-4 py-3 text-right text-gray-600 text-xs">{fmtPct(m.win_rate)}</td>
                                            <td className={`px-4 py-3 text-right font-bold text-xs ${pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmt(pnl)}</td>
                                            <td className="px-4 py-3 text-right text-gray-600 text-xs">{fmt(m.avg_pnl_per_trade)}</td>
                                            <td className="px-4 py-3 text-right text-gray-600 text-xs">{fmtNum(m.profit_factor)}</td>
                                            <td className="px-4 py-3 text-right text-red-400 text-xs">{fmt(m.max_drawdown)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Per-scenario expanded cards */}
                    <div className="space-y-3">
                        {Object.entries(btResults.results).map(([key, data]) => (
                            <ScenarioCard key={key} scenarioKey={key} data={data}
                                isExpanded={expandedCard === key}
                                onToggle={() => setExpandedCard(expandedCard === key ? null : key)} />
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
}
