"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const WS_BASE = "ws://127.0.0.1:8000";

type MessageHandler = (data: any) => void;

export interface UseWebSocketOptions {
  sessionId?: string | null;
  onMessage?: MessageHandler;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
  reconnectInterval?: number;
  maxReconnects?: number;
}

export function useWebSocket(
  path: string,
  options: UseWebSocketOptions = {}
) {
  const {
    sessionId,
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnectInterval = 3000,
    maxReconnects = 10,
  } = options;

  const [readyState, setReadyState] = useState<number>(WebSocket.CLOSED);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const send = useCallback((data: any) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === "string" ? data : JSON.stringify(data));
      return true;
    }
    return false;
  }, []);

  const connect = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const query = `?session_id=${encodeURIComponent(sessionId)}`;
    const url = `${WS_BASE}${path}${query}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setReadyState(WebSocket.OPEN);
      setError(null);
      reconnectCountRef.current = 0;
      onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch {
        onMessage?.({ type: "raw", payload: event.data });
      }
    };

    ws.onclose = () => {
      setReadyState(WebSocket.CLOSED);
      onClose?.();
      if (!mountedRef.current) return;
      if (reconnectCountRef.current < maxReconnects) {
        reconnectTimerRef.current = setTimeout(() => {
          reconnectCountRef.current += 1;
          connect();
        }, reconnectInterval);
      }
    };

    ws.onerror = (ev: Event) => {
      setError("WebSocket connection error");
      onError?.(ev);
    };
  }, [path, sessionId, onMessage, onOpen, onClose, onError, reconnectInterval, maxReconnects]);

  useEffect(() => {
    mountedRef.current = true;

    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { send, readyState, error };
}
