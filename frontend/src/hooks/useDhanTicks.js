/**
 * Custom React hook for real-time tick data via SSE
 *
 * Connects to the Flask backend SSE endpoint which relays
 * ticks from Dhan's Live Market Feed WebSocket.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export default function useDhanTicks(instrumentKeys = [], onRefresh) {
  const [ticks, setTicks] = useState({});       // instrument_key → tick data
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [tickCount, setTickCount] = useState(0);
  const eventSourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const keysRef = useRef(instrumentKeys);

  // Keep keysRef in sync
  useEffect(() => {
    keysRef.current = instrumentKeys;
  }, [instrumentKeys]);

  const connect = useCallback(() => {
    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    if (keysRef.current.length === 0) {
      setConnected(false);
      setError(null);
      return;
    }

    const keys = keysRef.current.join(',');
    const url = `${API_BASE_URL}/api/ws-subscribe?instruments=${encodeURIComponent(keys)}`;

    try {
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
        setError(null);
        console.log('[Ticks] SSE connected for:', keysRef.current);
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'refresh') {
            console.log('[Ticks] Refresh signal received');
            if (onRefresh) onRefresh();
            return;
          }

          // console.log('[Ticks] Received:', data);

          setTicks(prev => ({
            ...prev,
            [data.instrument_key]: data,
          }));
          setTickCount(c => c + 1);
        } catch (e) {
          console.warn('[Ticks] Failed to parse tick:', e);
        }
      };

      es.onerror = (evt) => {
        console.warn('[Ticks] SSE error, will auto-reconnect');
        setConnected(false);
        setError('Connection lost — reconnecting…');

        es.close();
        eventSourceRef.current = null;

        // Reconnect after 3 seconds
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };

    } catch (e) {
      setError(`Failed to connect: ${e.message}`);
      setConnected(false);
    }
  }, []);

  // Connect whenever instrument keys change
  useEffect(() => {
    if (instrumentKeys.length > 0) {
      connect();
    } else {
      // No instruments — clean up
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setConnected(false);
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [instrumentKeys.join(','), connect]);

  return { ticks, connected, error, tickCount };
}
