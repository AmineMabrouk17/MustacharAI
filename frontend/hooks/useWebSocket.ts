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
  const connectionIdRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<PipelineStatus>("idle");

  const onAudioReceivedRef = useRef(onAudioReceived);
  const onStatusChangeRef = useRef(onStatusChange);
  const onTranscriptRef = useRef(onTranscript);
  const onAnswerRef = useRef(onAnswer);
  const onErrorRef = useRef(onError);

  onAudioReceivedRef.current = onAudioReceived;
  onStatusChangeRef.current = onStatusChange;
  onTranscriptRef.current = onTranscript;
  onAnswerRef.current = onAnswer;
  onErrorRef.current = onError;

  const updateStatus = useCallback((newStatus: PipelineStatus) => {
    setStatus(newStatus);
    onStatusChangeRef.current?.(newStatus);
  }, []);

  useEffect(() => {
    const id = ++connectionIdRef.current;

    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      if (connectionIdRef.current !== id) { ws.close(); return; }
      setIsConnected(true);
      updateStatus("idle");
    };

    ws.onmessage = (event) => {
      if (connectionIdRef.current !== id) return;
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: "audio/mpeg" });
        onAudioReceivedRef.current?.(blob);
      } else {
        try {
          const message: WSMessage = JSON.parse(event.data);
          switch (message.type) {
            case "status":
              updateStatus(message.stage);
              break;
            case "transcript":
              onTranscriptRef.current?.(message.darja_text, message.latency_ms);
              break;
            case "answer":
              onAnswerRef.current?.(message.text, message.citations, message.fallback);
              break;
          }
        } catch {
          // Not JSON, ignore
        }
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

  const sendAudio = useCallback(
    (audioData: ArrayBuffer) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(audioData);
        updateStatus("processing");
      }
    },
    [updateStatus]
  );

  return {
    isConnected,
    status,
    sendAudio,
  };
}
