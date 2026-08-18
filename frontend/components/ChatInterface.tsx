"use client";

import { useCallback, useEffect, useState } from "react";
import { PipelineStatusIndicator } from "./PipelineStatus";
import { WaveformVisualizer } from "./WaveformVisualizer";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useAudioPlayback } from "@/hooks/useAudioPlayback";
import { useWebSocket, type PipelineStatus } from "@/hooks/useWebSocket";

const WS_URL = typeof window !== "undefined"
  ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/v1/stream`
  : "ws://localhost:8000/api/v1/stream";

export function ChatInterface() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [queueLength, setQueueLength] = useState(0);

  const { isPlaying, status: playbackStatus, enqueueAudio } = useAudioPlayback();

  const handleAudioReceived = useCallback(
    (audioData: Blob) => {
      enqueueAudio(audioData);
      setQueueLength((prev) => prev + 1);
    },
    [enqueueAudio]
  );

  const { isConnected, connect, disconnect, sendAudio } = useWebSocket({
    url: WS_URL,
    onAudioReceived: handleAudioReceived,
    onStatusChange: setStatus,
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

  const { isRecording, analyserNode, startRecording, stopRecording } = useAudioRecorder({
    onDataAvailable: handleDataAvailable,
    timeSlice: 300,
  });

  const displayStatus = isRecording ? "listening" : playbackStatus === "speaking" ? "speaking" : status;

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

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
    <div className="flex flex-col items-center justify-center min-h-screen p-4" dir="rtl">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-zinc-100">مستشار تونس</h1>
          <p className="text-zinc-400">مساعد ذكي للقانون التونسي</p>
        </div>

        <div className="flex items-center justify-between bg-zinc-900/50 rounded-lg p-3">
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

        <div className="bg-zinc-900/50 rounded-lg p-4">
          <WaveformVisualizer
            analyserNode={analyserNode}
            isActive={isRecording}
          />
        </div>

        <div className="flex justify-center">
          <button
            onClick={handleRecordClick}
            disabled={!isConnected}
            className={`relative group flex items-center justify-center w-20 h-20 rounded-full transition-all duration-200 ${
              isRecording
                ? "bg-red-500 hover:bg-red-600 animate-pulse"
                : "bg-emerald-600 hover:bg-emerald-700"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            <span className="text-3xl">{isRecording ? "⏹️" : "🎙️"}</span>
            <span className="absolute -bottom-8 text-xs text-zinc-400 whitespace-nowrap">
              {isRecording ? "إيقاف التسجيل" : "ابدأ التسجيل"}
            </span>
          </button>
        </div>

        {queueLength > 0 && (
          <div className="text-center text-sm text-zinc-400">
            <span className="animate-pulse">🔊</span>{" "}
            {isPlaying ? "جاري التشغيل..." : `بانتظار التشغيل (${queueLength})`}
          </div>
        )}
      </div>
    </div>
  );
}
