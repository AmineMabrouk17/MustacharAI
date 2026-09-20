"use client";

import { useCallback, useState } from "react";
import { ChatHistory } from "./ChatHistory";
import { PipelineStatusIndicator } from "./PipelineStatus";
import { useChatHistory } from "@/hooks/useChatHistory";
import {
  useWebSocket,
  type PipelineStatus,
  type Citation,
} from "@/hooks/useWebSocket";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:8000/api/v1/stream`
    : "ws://localhost:8000/api/v1/stream");

let messageIdCounter = 0;
function nextId(): string {
  messageIdCounter += 1;
  return `msg-${messageIdCounter}-${Date.now()}`;
}

export function ChatInterface() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [input, setInput] = useState("");
  const { messages, setMessages, clearHistory } = useChatHistory();

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
    [setMessages]
  );

  const { isConnected, sendMessage } = useWebSocket({
    url: WS_URL,
    onStatusChange: setStatus,
    onAnswer: handleAnswer,
  });

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || !isConnected) return;
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", text, timestamp: Date.now() },
    ]);
    setInput("");
    sendMessage(text);
    setStatus("processing");
  }, [input, isConnected, sendMessage, setMessages, setStatus]);

  const handleClearHistory = useCallback(() => {
    clearHistory();
  }, [clearHistory]);

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
          <PipelineStatusIndicator status={status} />
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <button
                onClick={handleClearHistory}
                className="text-xs text-zinc-400 hover:text-red-400 transition-colors"
              >
                مسح المحادثة
              </button>
            )}
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
        </div>

        {/* Chat history */}
        <div className="flex-1 overflow-hidden">
          <ChatHistory messages={messages} />
        </div>

        {/* Text input */}
        <div className="shrink-0 bg-zinc-900/50 rounded-lg p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-3"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="اكتب سؤالك عن القانون التونسي..."
              disabled={!isConnected}
              className="flex-1 bg-zinc-800 text-zinc-100 placeholder-zinc-500 text-sm rounded-lg px-4 py-2.5 outline-none focus:ring-2 focus:ring-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={!isConnected || !input.trim()}
              className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              إرسال
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}