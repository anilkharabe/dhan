const fs = require('fs');

const path = '/home/anirudhakharabe/2026/upstox/files/frontend/src/components/CandlestickChart.jsx';
let content = fs.readFileSync(path, 'utf8');

// Add tooltip state and reference
const stateStr = "    const [hasOiData, setHasOiData] = useState(false);\n    const lastCandleRef = useRef(null);\n";
const newStateStr = `    const [hasOiData, setHasOiData] = useState(false);\n    const [tooltipData, setTooltipData] = useState(null);\n    const lastCandleRef = useRef(null);\n`;

content = content.replace(stateStr, newStateStr);

// Add tooltip HTML
const JSXTarget = `<div ref={chartContainerRef} className="w-full relative min-h-[350px]">\n`;
const JSXReplacement = `<div ref={chartContainerRef} className="w-full relative min-h-[350px]">\n                {tooltipData && (
                    <div className="absolute top-2 left-2 z-20 bg-white/95 p-3 rounded shadow pointer-events-none border border-gray-200 text-xs font-mono">
                        <div className="font-bold border-b pb-1 mb-1 text-gray-700">{tooltipData.time}</div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                            <span className="text-gray-500">O:</span> <span className={tooltipData.open <= tooltipData.close ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{tooltipData.open}</span>
                            <span className="text-gray-500">H:</span> <span className="text-gray-800 font-medium">{tooltipData.high}</span>
                            <span className="text-gray-500">L:</span> <span className="text-gray-800 font-medium">{tooltipData.low}</span>
                            <span className="text-gray-500">C:</span> <span className={tooltipData.open <= tooltipData.close ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{tooltipData.close}</span>
                            {tooltipData.volume !== undefined && (
                                <>
                                    <span className="text-gray-500">Vol:</span> <span className="text-gray-800 font-medium">{tooltipData.volume}</span>
                                </>
                            )}
                        </div>
                    </div>
                )}\n`;

content = content.replace(JSXTarget, JSXReplacement);

// Add crosshair logic for tooltip
const dataTarget = `                    candleSeriesRef.current.setData(uniqueCandles);\n`;
const dataReplacement = `                    candleSeriesRef.current.setData(uniqueCandles);\n                    
                    // Crosshair move handler for Tooltip
                    chart.subscribeCrosshairMove(param => {
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
                            const volData = param.seriesData.get(volumeSeriesRef.current);
                            if (data) {
                                setTooltipData({
                                    time: formatToIST(param.time),
                                    open: data.open.toFixed(2),
                                    high: data.high.toFixed(2),
                                    low: data.low.toFixed(2),
                                    close: data.close.toFixed(2),
                                    volume: volData ? volData.value : undefined
                                });
                            }
                        }
                    });\n`;
                    
content = content.replace(dataTarget, dataReplacement);



fs.writeFileSync(path, content);
console.log("Patched");

