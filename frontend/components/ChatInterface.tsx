"use client";

import { useCallback, useState } from "react";
import { ChatHistory, type ChatMessage } from "./ChatHistory";
import { PipelineStatusIndicator } from "./PipelineStatus";
import { WaveformVisualizer } from "./WaveformVisualizer";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useAudioPlayback } from "@/hooks/useAudioPlayback";
import {
  useWebSocket,
  type PipelineStatus,
  type Citation,
} from "@/hooks/useWebSocket";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:8000/api/v1/stream`
    : "ws://localhost:8000/api/v1/stream";

let messageIdCounter = 0;
function nextId(): string {
  messageIdCounter += 1;
  return `msg-${messageIdCounter}-${Date.now()}`;
}

export function ChatInterface() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const { status: playbackStatus, enqueueAudio } = useAudioPlayback();

  const handleAudioReceived = useCallback(
    (audioData: Blob) => {
      enqueueAudio(audioData);
    },
    [enqueueAudio]
  );

  const handleTranscript = useCallback((text: string, _latencyMs: number) => {
    if (!text) return;
    setMessages((prev) => [
      ...prev,
      {
        id: nextId(),
        role: "user",
        text,
        timestamp: Date.now(),
      },
    ]);
  }, []);

  const handleAnswer = useCallback(
    (text: string, citations: Citation[], fallback: boolean) => {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          text,
          citations: fallback ? [] : citations,
          fallback,
          timestamp: Date.now(),
        },
      ]);
    },
    []
  );

  const { isConnected, sendAudio } = useWebSocket({
    url: WS_URL,
    onAudioReceived: handleAudioReceived,
    onStatusChange: setStatus,
    onTranscript: handleTranscript,
    onAnswer: handleAnswer,
  });

  const handleDataAvailable = useCallback(
    (data: Blob) => {
      const reader = new FileReader();
      reader.onload = () => {
        const arrayBuffer = reader.result as ArrayBuffer;
        sendAudio(arrayBuffer);
      };
      reader.readAsArrayBuffer(data);
    },
    [sendAudio]
  );

  const { isRecording, analyserNode, startRecording, stopRecording } =
    useAudioRecorder({
      onDataAvailable: handleDataAvailable,
      timeSlice: 300,
    });

  const displayStatus = isRecording
    ? "listening"
    : playbackStatus === "speaking"
      ? "speaking"
      : status;

  const handleRecordClick = useCallback(() => {
    if (isRecording) {
      stopRecording();
      setStatus("processing");
    } else {
      startRecording();
      setStatus("listening");
    }
  }, [isRecording, startRecording, stopRecording]);

  return (
    <div className="flex flex-col h-screen p-4" dir="rtl">
      <div className="flex-1 flex flex-col w-full max-w-2xl mx-auto gap-4 overflow-hidden">
        {/* Header */}
        <div className="text-center space-y-1 pt-2 shrink-0">
          <h1 className="text-2xl font-bold text-zinc-100">مستشار تونس</h1>
          <p className="text-zinc-400 text-sm">مساعد ذكي للقانون التونسي</p>
        </div>

        {/* Status bar */}
        <div className="flex items-center justify-between bg-zinc-900/50 rounded-lg p-3 shrink-0">
          <PipelineStatusIndicator status={displayStatus} />
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                isConnected ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
            <span className="text-xs text-zinc-400">
              {isConnected ? "متصل" : "غير متصل"}
            </span>
          </div>
        </div>

        {/* Chat history */}
        <div className="flex-1 overflow-hidden">
          <ChatHistory messages={messages} />
        </div>

        {/* Controls */}
        <div className="space-y-4 shrink-0">
          <div className="bg-zinc-900/50 rounded-lg p-3">
            <WaveformVisualizer
              analyserNode={analyserNode}
              isActive={isRecording}
            />
          </div>

          <div className="flex justify-center">
            <button
              onClick={handleRecordClick}
              disabled={!isConnected}
              className={`relative group flex items-center justify-center w-16 h-16 rounded-full transition-all duration-200 ${
                isRecording
                  ? "bg-red-500 hover:bg-red-600 animate-pulse"
                  : "bg-emerald-600 hover:bg-emerald-700"
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              <span className="text-2xl">{isRecording ? "⏹️" : "🎙️"}</span>
              <span className="absolute -bottom-7 text-xs text-zinc-400 whitespace-nowrap">
                {isRecording ? "إيقاف التسجيل" : "ابدأ التسجيل"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
