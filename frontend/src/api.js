/**
 * API Service for Trading Dashboard
 */

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

export const apiService = {
  // Get trading profile
  getProfile: async () => {
    const response = await api.get('/api/profile');
    return response.data;
  },

  // Get current positions
  getCurrentPositions: async () => {
    const response = await api.get('/api/current-positions');
    return response.data;
  },

  // Get OI PCR metrics
  getOiPcr: async () => {
    const response = await api.get('/api/metrics/oi-pcr');
    return response.data;
  },

  // Get full-day OI/PCR + VWAP history table for one symbol (NIFTY/BANKNIFTY/SENSEX)
  getTrendScanner: async (symbol, timeframe) => {
    const response = await api.get('/api/scanner/trend', { params: { symbol, timeframe } });
    return response.data;
  },

  // Get daily summary
  getDailySummary: async () => {
    const response = await api.get('/api/summary/today');
    return response.data;
  },

  // Get positions with instrument keys (for WebSocket subscription)
  getPositionsInstruments: async () => {
    const response = await api.get('/api/positions-instruments');
    return response.data;
  },

  // Get latest ticks snapshot
  getLatestTicks: async () => {
    const response = await api.get('/api/latest-ticks');
    return response.data;
  },

  // Get selected instruments (Nifty/Sensex strikes)
  getSelectedInstruments: async () => {
    const response = await api.get('/api/selected-instruments');
    return response.data;
  },

  // Health check
  healthCheck: async () => {
    const response = await api.get('/api/health');
    return response.data;
  },

  // Get trade history for today
  getTradesHistory: async () => {
    const response = await api.get('/api/trades/history');
    return response.data;
  },

  // Get historical performance stats
  getPerformanceHistory: async (days = 30) => {
    const response = await api.get(`/api/performance/history?days=${days}`);
    return response.data;
  },

  // Get detailed stats for a specific date
  getDayDetails: async (date) => {
    const response = await api.get(`/api/performance/day?date=${date}`);
    return response.data;
  },

  // Token Management
  getTokenStatus: async () => {
    const response = await api.get('/api/token-status');
    return response.data;
  },

  getLoginUrl: async () => {
    const response = await api.get('/api/login-url');
    return response.data;
  },

  // Attempts automatic PIN+TOTP token generation (requires DHAN_PIN/DHAN_TOTP_SECRET
  // to be configured server-side); falls back to manual entry (saveToken) otherwise.
  generateToken: async () => {
    const response = await api.post('/api/generate-token', {});
    return response.data;
  },

  // Save manual token
  saveToken: async (token) => {
    const response = await api.post('/api/save-token', { access_token: token });
    return response.data;
  },

  // Generic POST request
  post: async (url, data) => {
    const response = await api.post(`/api${url}`, data);
    return response;
  },

  // ── Backtest ───────────────────────────────────────────────────────────

  // Check if candle data exists for a date
  backtestCandleStatus: async (date) => {
    const response = await api.get(`/api/backtest/candle-status?date=${date}`);
    return response.data;
  },

  // Run scenario backtest (returns metrics + trades)
  runBacktest: async (date, scenarios) => {
    const response = await api.post('/api/backtest/run', { date, scenarios }, { timeout: 120000 });
    return response.data;
  },

  // Base URL helper (for SSE fetch in Backtest page)
  getBaseUrl: () => API_BASE_URL,
};

export default apiService;
