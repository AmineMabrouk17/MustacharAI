"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PipelineStatus = "idle" | "listening" | "processing" | "speaking";

export interface Citation {
  source: string;
  article: string;
  content: string;
}

export interface TranscriptMessage {
  type: "transcript";
  darja_text: string;
  latency_ms: number;
}

export interface AnswerMessage {
  type: "answer";
  text: string;
  citations: Citation[];
  fallback: boolean;
  latency_ms: number;
}

export interface StatusMessage {
  type: "status";
  stage: PipelineStatus;
}

export type WSMessage = TranscriptMessage | AnswerMessage | StatusMessage;

interface UseWebSocketOptions {
  url: string;
  onAudioReceived?: (audioData: Blob) => void;
  onStatusChange?: (status: PipelineStatus) => void;
  onTranscript?: (text: string, latencyMs: number) => void;
  onAnswer?: (text: string, citations: Citation[], fallback: boolean) => void;
  onError?: (error: Event) => void;
}

export function useWebSocket({
  url,
  onAudioReceived,
  onStatusChange,
  onTranscript,
  onAnswer,
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
        onAudioReceived?.(blob);
      } else {
        try {
          const message: WSMessage = JSON.parse(event.data);
          switch (message.type) {
            case "status":
              updateStatus(message.stage);
              break;
            case "transcript":
              onTranscript?.(message.darja_text, message.latency_ms);
              break;
            case "answer":
              onAnswer?.(message.text, message.citations, message.fallback);
              break;
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
  }, [url, onAudioReceived, updateStatus, onTranscript, onAnswer, onError]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendAudio = useCallback(
    (audioData: ArrayBuffer) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(audioData);
        updateStatus("processing");
      }
    },
    [updateStatus]
  );

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
