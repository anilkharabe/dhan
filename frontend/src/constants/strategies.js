/**
 * Strategy tag metadata for charting - mirrors backend/config.py's
 * *_TAG / *_CANDLE_INTERVAL constants. Single source of truth so
 * Dashboard.jsx (which interval to fetch) and CandlestickChart.jsx (which
 * badge/panels to show) never drift apart the way the old
 * `strategyTag === SUPERTREND_TAG ? '3minute' : '1minute'` ternary did -
 * that only knew about one non-default strategy and silently charted
 * CREDIT_A_3MIN/CREDIT_A_PCR_3MIN trades at the wrong candle interval.
 */

export const STRATEGY_META = {
  CREDIT_A_1MIN: {
    label: 'CREDIT_A 1MIN',
    interval: '1minute',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-100',
    indicators: true,
    pcrGated: false,
  },
  SUPERTREND_CS: {
    label: 'SUPERTREND (Trailing SL)',
    interval: '3minute',
    badgeClass: 'bg-teal-50 text-teal-700 border-teal-100',
    indicators: false,
    pcrGated: false,
  },
  CREDIT_A_3MIN: {
    label: 'CREDIT_A 3MIN',
    interval: '3minute',
    badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-100',
    indicators: true,
    pcrGated: false,
  },
  CREDIT_A_PCR_1MIN: {
    label: 'CREDIT_A PCR 1MIN',
    interval: '1minute',
    badgeClass: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-100',
    indicators: true,
    pcrGated: true,
  },
  CREDIT_A_PCR_3MIN: {
    label: 'CREDIT_A PCR 3MIN',
    interval: '3minute',
    badgeClass: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-100',
    indicators: true,
    pcrGated: true,
  },
};

// Untagged charts (index charts, manually-searched strikes with no linked
// trade) - same indicator set as the original CREDIT_A engine, no badge.
const DEFAULT_META = {
  label: null,
  interval: '1minute',
  badgeClass: '',
  indicators: true,
  pcrGated: false,
};

export const getStrategyMeta = (tag) => (tag && STRATEGY_META[tag]) || DEFAULT_META;

export const getIntervalForStrategy = (tag) => getStrategyMeta(tag).interval;
