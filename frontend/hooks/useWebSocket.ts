"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PipelineStatus = "idle" | "listening" | "processing" | "speaking";

interface UseWebSocketOptions {
  url: string;
  onAudioReceived?: (audioData: Blob) => void;
  onStatusChange?: (status: PipelineStatus) => void;
  onError?: (error: Event) => void;
}

export function useWebSocket({
  url,
  onAudioReceived,
  onStatusChange,
  onError,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<PipelineStatus>("idle");

  const updateStatus = useCallback(
    (newStatus: PipelineStatus) => {
      setStatus(newStatus);
      onStatusChange?.(newStatus);
    },
    [onStatusChange]
  );

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setIsConnected(true);
      updateStatus("idle");
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: "audio/mpeg" });
        updateStatus("speaking");
        onAudioReceived?.(blob);
      } else {
        try {
          const message = JSON.parse(event.data);
          if (message.status) {
            updateStatus(message.status);
          }
        } catch {
          // Not JSON, ignore
        }
      }
    };

    ws.onerror = (error) => {
      onError?.(error);
    };

    ws.onclose = () => {
      setIsConnected(false);
      updateStatus("idle");
      wsRef.current = null;
    };

    wsRef.current = ws;
  }, [url, onAudioReceived, updateStatus, onError]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendAudio = useCallback((audioData: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(audioData);
      updateStatus("processing");
    }
  }, [updateStatus]);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    status,
    connect,
    disconnect,
    sendAudio,
  };
}
