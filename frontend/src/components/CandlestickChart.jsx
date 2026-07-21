import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';

const CandlestickChart = ({ instrumentKey, liveTick, symbol = "NIFTY", interval = "1minute", activePosition }) => {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const candleSeriesRef = useRef(null);
    const vwapSeriesRef = useRef(null);

    const rsiContainerRef = useRef(null);
    const rsiChartRef = useRef(null);
    const rsiSeriesRef = useRef(null);

    const adxContainerRef = useRef(null);
    const adxChartRef = useRef(null);
    const adxSeriesRef = useRef(null);

    const oiContainerRef = useRef(null);
    const oiChartRef = useRef(null);
    const oiSeriesRef = useRef(null);
    const oiSmaSeriesRef = useRef(null);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [hasOiData, setHasOiData] = useState(false);
    const [tooltipData, setTooltipData] = useState(null);
    const lastCandleRef = useRef(null);

    // Helper to format time to IST for both Tooltip and X-Axis
    const formatToIST = (timestamp) => {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('en-IN', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: 'Asia/Kolkata'
        });
    };

    const commonTimeScaleOptions = {
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 20,
        barSpacing: 12,
        fixLeftEdge: false,
        shiftVisibleRangeOnNewBar: true,
        tickMarkFormatter: (time) => {
            return formatToIST(time);
        },
    };

    // Fetch historical data
    useEffect(() => {
        if (!instrumentKey) return;

        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000'}/api/historical-candles?instrument_key=${instrumentKey}&interval=${interval}`);
                const data = await response.json();

                if (data.error) throw new Error(data.error);

                const candles = (data.candles || []).sort((a, b) => a.time - b.time);
                const oiAvailable = candles.some(c => c.oi !== undefined && c.oi > 0);
                setHasOiData(oiAvailable);

                // Initialize Main Chart
                if (!chartRef.current && chartContainerRef.current) {
                    const chart = createChart(chartContainerRef.current, {
                        layout: { background: { color: '#ffffff' }, textColor: '#333' },
                        grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
                        width: chartContainerRef.current.clientWidth,
                        height: 350,
                        timeScale: commonTimeScaleOptions,
                        localization: { timeFormatter: formatToIST },
                        rightPriceScale: {
                            scaleMargins: {
                                top: 0.1,
                                bottom: 0.1,
                            },
                        },
                    });

                    candleSeriesRef.current = chart.addSeries(CandlestickSeries, {
                        upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                        wickUpColor: '#26a69a', wickDownColor: '#ef5350'
                    });

                    vwapSeriesRef.current = chart.addSeries(LineSeries, {
                        color: '#2962FF', lineWidth: 2, title: 'VWAP'
                    });

                    chartRef.current = chart;
                }

                // Initialize RSI Chart
                if (!rsiChartRef.current && rsiContainerRef.current) {
                    const rsiChart = createChart(rsiContainerRef.current, {
                        layout: { background: { color: '#ffffff' }, textColor: '#333' },
                        grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
                        width: rsiContainerRef.current.clientWidth,
                        height: 100,
                        timeScale: commonTimeScaleOptions,
                        localization: { timeFormatter: formatToIST },
                    });

                    rsiSeriesRef.current = rsiChart.addSeries(LineSeries, {
                        color: '#7B1FA2', lineWidth: 2, title: 'RSI(14)'
                    });
                    rsiSeriesRef.current.createPriceLine({ price: 60, color: '#ef5350', lineWidth: 1, lineStyle: 2, title: '60' });
                    rsiSeriesRef.current.createPriceLine({ price: 20, color: '#26a69a', lineWidth: 1, lineStyle: 2, title: '20' });

                    rsiChartRef.current = rsiChart;
                }

                // Initialize ADX Chart
                if (!adxChartRef.current && adxContainerRef.current) {
                    const adxChart = createChart(adxContainerRef.current, {
                        layout: { background: { color: '#ffffff' }, textColor: '#333' },
                        grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
                        width: adxContainerRef.current.clientWidth,
                        height: 100,
                        timeScale: commonTimeScaleOptions,
                        localization: { timeFormatter: formatToIST },
                    });

                    adxSeriesRef.current = adxChart.addSeries(LineSeries, {
                        color: '#E91E63', lineWidth: 2, title: 'ADX(14)'
                    });
                    adxSeriesRef.current.createPriceLine({ price: 25, color: '#2196F3', lineWidth: 1, lineStyle: 2, title: '25' });

                    adxChartRef.current = adxChart;
                }

                // Initialize OI Chart
                if (!oiChartRef.current && oiContainerRef.current && oiAvailable) {
                    const oiChart = createChart(oiContainerRef.current, {
                        layout: { background: { color: '#ffffff' }, textColor: '#333' },
                        grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
                        width: oiContainerRef.current.clientWidth,
                        height: 100,
                        timeScale: commonTimeScaleOptions,
                        localization: { timeFormatter: formatToIST },
                    });

                    oiSeriesRef.current = oiChart.addSeries(LineSeries, { color: '#FF9800', lineWidth: 2, title: 'OI' });
                    oiSmaSeriesRef.current = oiChart.addSeries(LineSeries, { color: '#4CAF50', lineWidth: 1.5, title: 'OI SMA' });

                    oiChartRef.current = oiChart;
                }

                // Set Data and Sync
                if (chartRef.current) {
                    const uniqueCandles = [];
                    const seenTimes = new Set();
                    for (const c of candles) {
                        if (!seenTimes.has(c.time)) {
                            seenTimes.add(c.time);
                            uniqueCandles.push(c);
                        }
                    }

                    candleSeriesRef.current.setData(uniqueCandles);

                    // Crosshair move handler for Tooltip
                    chartRef.current.subscribeCrosshairMove(param => {
                        if (
                            param.point === undefined ||
                            !param.time ||
                            param.point.x < 0 ||
                            param.point.x > chartContainerRef.current.clientWidth ||
                            param.point.y < 0 ||
                            param.point.y > chartContainerRef.current.clientHeight
                        ) {
                            setTooltipData(null);
                        } else {
                            const data = param.seriesData.get(candleSeriesRef.current);
                            if (data) {
                                setTooltipData({
                                    time: formatToIST(param.time),
                                    open: data.open.toFixed(2),
                                    high: data.high.toFixed(2),
                                    low: data.low.toFixed(2),
                                    close: data.close.toFixed(2),
                                });
                            }
                        }
                    });
                    vwapSeriesRef.current.setData(uniqueCandles.map(c => c.vwap !== undefined ? { time: c.time, value: c.vwap } : { time: c.time }));

                    if (rsiSeriesRef.current) {
                        rsiSeriesRef.current.setData(uniqueCandles.map(c => c.rsi !== undefined ? { time: c.time, value: c.rsi } : { time: c.time }));
                    }

                    if (adxSeriesRef.current) {
                        adxSeriesRef.current.setData(uniqueCandles.map(c => c.adx !== undefined ? { time: c.time, value: c.adx } : { time: c.time }));
                    }

                    if (oiSeriesRef.current) {
                        oiSeriesRef.current.setData(uniqueCandles.map(c => c.oi !== undefined ? { time: c.time, value: c.oi } : { time: c.time }));
                        oiSmaSeriesRef.current.setData(uniqueCandles.map(c => c.oi_sma !== undefined ? { time: c.time, value: c.oi_sma } : { time: c.time }));
                    }

                    if (uniqueCandles.length > 0) {
                        lastCandleRef.current = uniqueCandles[uniqueCandles.length - 1];
                    }

                    // Sync Time Scales — all charts have same time points now, so logical range works perfectly
                    const charts = [chartRef.current, rsiChartRef.current, adxChartRef.current, oiChartRef.current].filter(Boolean);
                    let _syncing = false;
                    charts.forEach(pivot => {
                        pivot.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
                            if (_syncing) return;
                            if (!logicalRange) return;
                            _syncing = true;
                            charts.forEach(other => {
                                if (other !== pivot) {
                                    try {
                                        other.timeScale().setVisibleLogicalRange(logicalRange);
                                    } catch (e) {
                                        // Ignore if data not ready
                                    }
                                }
                            });
                            _syncing = false;
                        });
                    });

                    // Match all offsets
                    charts.forEach(c => c.timeScale().applyOptions({ rightOffset: 20, barSpacing: 12 }));
                }

            } catch (err) {
                console.error("Failed to load chart data", err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();

        return () => {
            [chartRef, rsiChartRef, adxChartRef, oiChartRef].forEach(ref => {
                if (ref.current) {
                    ref.current.remove();
                    ref.current = null;
                }
            });
        };
    }, [instrumentKey, interval]);

    // Resize observer
    useEffect(() => {
        if (!chartContainerRef.current) return;
        const resizeObserver = new ResizeObserver((entries) => {
            if (entries.length === 0) return;
            const { width } = entries[0].contentRect;
            [chartRef, rsiChartRef, adxChartRef, oiChartRef].forEach(ref => {
                if (ref.current) ref.current.applyOptions({ width });
            });
        });
        resizeObserver.observe(chartContainerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    // Manage Position Lines
    const entryLineRef = useRef(null);
    const slLineRef = useRef(null);

    useEffect(() => {
        const updatePriceLines = () => {
            if (!candleSeriesRef.current) return;

            // Clear existing lines to update
            if (entryLineRef.current) {
                try { candleSeriesRef.current.removePriceLine(entryLineRef.current); } catch (e) { }
                entryLineRef.current = null;
            }
            if (slLineRef.current) {
                try { candleSeriesRef.current.removePriceLine(slLineRef.current); } catch (e) { }
                slLineRef.current = null;
            }

            if (activePosition) {
                if (activePosition.entry_price) {
                    entryLineRef.current = candleSeriesRef.current.createPriceLine({
                        price: activePosition.entry_price, color: '#4CAF50', lineWidth: 2, title: 'BUY',
                    });
                }
                if (activePosition.stop_loss) {
                    slLineRef.current = candleSeriesRef.current.createPriceLine({
                        price: activePosition.stop_loss, color: '#F44336', lineWidth: 2, lineStyle: 2, title: 'SL',
                    });
                }
            }
        };

        updatePriceLines();

        // Fallback: If chart was still initializing, retry ensuring lines are drawn
        const timer = setInterval(() => {
            if (candleSeriesRef.current && activePosition && !entryLineRef.current) {
                updatePriceLines();
            }
        }, 500);

        return () => clearInterval(timer);
    }, [activePosition, instrumentKey]);

    // Handle Live Ticks
    useEffect(() => {
        if (!liveTick) {
            // console.log("No live tick");
            return;
        }
        if (!candleSeriesRef.current) {
            // console.log("No candle series ref");
            return;
        }

        // Debug log
        // console.log("Live tick received:", liveTick);

        if (liveTick.instrument_key && liveTick.instrument_key.toUpperCase() !== instrumentKey.toUpperCase()) {
            // console.log("Key mismatch:", liveTick.instrument_key, instrumentKey);
            return;
        }

        const price = liveTick.ltp;
        // Parse timestamp correctly whether it's milliseconds or ISO string
        const timestampMs = typeof liveTick.timestamp === 'string'
            ? new Date(liveTick.timestamp).getTime()
            : liveTick.timestamp;
        const tickTime = Math.floor(timestampMs / 1000);
        const candleTime = Math.floor(tickTime / 60) * 60;

        // console.log("Processing tick:", { price, tickTime, candleTime });

        let lastCandle = lastCandleRef.current;
        if (!lastCandle) {
            lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: 0 };
            lastCandleRef.current = lastCandle;
            candleSeriesRef.current.update(lastCandle);
            return;
        }

        if (candleTime === lastCandle.time) {
            const updatedCandle = { ...lastCandle, close: price, high: Math.max(lastCandle.high, price), low: Math.min(lastCandle.low, price) };
            lastCandleRef.current = updatedCandle;
            candleSeriesRef.current.update(updatedCandle);
        } else if (candleTime > lastCandle.time) {
            const newCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: 0 };
            lastCandleRef.current = newCandle;
            candleSeriesRef.current.update(newCandle);

            // Force scroll to new candle while maintaining offset
            if (chartRef.current) {
                chartRef.current.timeScale().scrollToRealTime();
                chartRef.current.timeScale().applyOptions({ rightOffset: 20 });
            }
        }
    }, [liveTick, instrumentKey]);

    return (
        <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-100">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-4">
                    <h2 className="text-xl font-bold bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent">
                        {symbol}
                    </h2>
                    <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs font-bold border border-blue-100">VWAP</span>
                        <span className="px-2 py-0.5 bg-purple-50 text-purple-600 rounded text-xs font-bold border border-purple-100">RSI</span>
                        <span className="px-2 py-0.5 bg-pink-50 text-pink-600 rounded text-xs font-bold border border-pink-100">ADX</span>
                        {hasOiData && (
                            <>
                                <span className="px-2 py-0.5 bg-orange-50 text-orange-600 rounded text-xs font-bold border border-orange-100">OI</span>
                                <span className="px-2 py-0.5 bg-green-50 text-green-600 rounded text-xs font-bold border border-green-100">OI SMA</span>
                            </>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-bold ${liveTick ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                        <span className={`w-2 h-2 rounded-full ${liveTick ? 'bg-emerald-500 animate-pulse' : 'bg-gray-400'}`}></span>
                        LTP: {liveTick ? `₹${liveTick.ltp?.toFixed(2)}` : 'Offline'}
                    </div>
                </div>
            </div>

            <div ref={chartContainerRef} className="w-full relative min-h-[350px]">
                {tooltipData && (
                    <div className="absolute top-2 left-2 z-20 bg-white/95 p-3 rounded shadow pointer-events-none border border-gray-200 text-xs font-mono">
                        <div className="font-bold border-b pb-1 mb-1 text-gray-700">{tooltipData.time}</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                            <span className="text-gray-500">O:</span> <span className={tooltipData.open <= tooltipData.close ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{tooltipData.open}</span>
                            <span className="text-gray-500">H:</span> <span className="text-gray-800 font-medium">{tooltipData.high}</span>
                            <span className="text-gray-500">L:</span> <span className="text-gray-800 font-medium">{tooltipData.low}</span>
                            <span className="text-gray-500">C:</span> <span className={tooltipData.open <= tooltipData.close ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{tooltipData.close}</span>
                        </div>
                    </div>
                )}
                {loading && <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>}
                {error && <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10 text-red-500 text-sm">{error}</div>}
            </div>

            <div className="mt-4 border-t border-gray-100 pt-4 flex flex-col gap-4">
                <div>
                    <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1 flex items-center gap-2">
                        <span className="w-2 h-2 bg-purple-500 rounded-full"></span> RSI (14)
                    </p>
                    <div ref={rsiContainerRef} className="w-full h-[100px]"></div>
                </div>
                <div>
                    <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1 flex items-center gap-2">
                        <span className="w-2 h-2 bg-pink-500 rounded-full"></span> ADX (14)
                    </p>
                    <div ref={adxContainerRef} className="w-full h-[100px]"></div>
                </div>
                <div className={hasOiData ? "" : "opacity-30"}>
                    <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1 flex items-center gap-2">
                        <span className="w-2 h-2 bg-orange-500 rounded-full"></span> Open Interest {!hasOiData && "(No Data)"}
                    </p>
                    <div ref={oiContainerRef} className="w-full h-[100px]"></div>
                </div>
            </div>
            {/* Debug Info */}
            <div className="mt-2 text-[10px] text-gray-400 font-mono">
                Last Tick: {liveTick ? `${new Date(liveTick.timestamp).toLocaleTimeString()} @ ${liveTick.ltp}` : "None"} |
                Chart Key: {instrumentKey}
            </div>
        </div>
    );
};

export default CandlestickChart;
