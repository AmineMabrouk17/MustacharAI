"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PipelineStatus = "idle" | "processing";

export interface Citation {
  source: string;
  article: string;
  content: string;
  category?: string;
}

export interface AnswerMessage {
  type: "answer";
  text: string;
  citations: Citation[];
  fallback: boolean;
  error?: string;
  latency_ms: number;
}

export interface StatusMessage {
  type: "status";
  stage: PipelineStatus;
}

export type WSMessage = AnswerMessage | StatusMessage;

interface UseWebSocketOptions {
  url: string;
  onStatusChange?: (status: PipelineStatus) => void;
  onAnswer?: (
    text: string,
    citations: Citation[],
    fallback: boolean,
    error?: string
  ) => void;
  onError?: (error: Event) => void;
}

export function useWebSocket({
  url,
  onStatusChange,
  onAnswer,
  onError,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const connectionIdRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<PipelineStatus>("idle");

  const onStatusChangeRef = useRef(onStatusChange);
  const onAnswerRef = useRef(onAnswer);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
    onAnswerRef.current = onAnswer;
    onErrorRef.current = onError;
  }, [onStatusChange, onAnswer, onError]);

  const updateStatus = useCallback((newStatus: PipelineStatus) => {
    setStatus(newStatus);
    onStatusChangeRef.current?.(newStatus);
  }, []);

  useEffect(() => {
    const id = ++connectionIdRef.current;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (connectionIdRef.current !== id) { ws.close(); return; }
      setIsConnected(true);
      updateStatus("idle");
    };

    ws.onmessage = (event) => {
      if (connectionIdRef.current !== id) return;
      try {
        const message: WSMessage = JSON.parse(event.data);
        switch (message.type) {
          case "status":
            updateStatus(message.stage);
            break;
          case "answer":
            onAnswerRef.current?.(
              message.text,
              message.citations,
              message.fallback,
              message.error
            );
            break;
        }
      } catch {
        // Not JSON, ignore
      }
    };

    ws.onerror = (error) => {
      if (connectionIdRef.current === id) onErrorRef.current?.(error);
    };

    ws.onclose = () => {
      if (connectionIdRef.current !== id) return;
      setIsConnected(false);
      updateStatus("idle");
      wsRef.current = null;
    };

    return () => {
      connectionIdRef.current++;
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [url, updateStatus]);

  const sendMessage = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "chat", message: text }));
    }
  }, []);

  return {
    isConnected,
    status,
    sendMessage,
  };
}