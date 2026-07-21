const fs = require('fs');

const path = '/home/anirudhakharabe/2026/upstox/files/frontend/src/components/CandlestickChart.jsx';
let content = fs.readFileSync(path, 'utf8');

const badTarget = `                    // Crosshair move handler for Tooltip
                    chart.subscribeCrosshairMove(param => {`;
                    
const goodReplacement = `                    // Crosshair move handler for Tooltip
                    chartRef.current.subscribeCrosshairMove(param => {`;

content = content.replace(badTarget, goodReplacement);


fs.writeFileSync(path, content);
console.log("Patched 2");

