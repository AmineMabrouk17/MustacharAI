"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000");

let messageIdCounter = 0;
function nextId(): string {
  messageIdCounter += 1;
  return `msg-${messageIdCounter}-${Date.now()}`;
}

const QUICK_PROMPTS = [
  "شنوة شروط الترشح لرئاسة الجمهورية؟",
  "شنوة هي لغة الدولة التونسية وشعارها؟",
  "هل الإضراب حق مضمون في الدستور؟",
];

interface IndexedDoc {
  source: string;
  articles_count: number;
}

export function ChatInterface() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [input, setInput] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);
  const [indexedDocs, setIndexedDocs] = useState<IndexedDoc[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { messages, setMessages, clearHistory } = useChatHistory();

  // Fetch indexed documents on mount
  const refreshDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/documents`);
      if (res.ok) {
        const data = await res.json();
        setIndexedDocs(data);
      }
    } catch {
      // Backend not yet reachable
    }
  }, []);

  useEffect(() => {
    // Load indexed documents once on mount; setState happens after an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshDocuments();
  }, [refreshDocuments]);

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
      setStatus("idle");
    },
    [setMessages]
  );

  const { isConnected, sendMessage } = useWebSocket({
    url: WS_URL,
    onStatusChange: setStatus,
    onAnswer: handleAnswer,
  });

  const sendQuery = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !isConnected || status === "processing") return;
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", text: trimmed, timestamp: Date.now() },
      ]);
      setInput("");
      sendMessage(trimmed);
      setStatus("processing");
    },
    [isConnected, sendMessage, setMessages, status]
  );

  // File Upload Handler (PDF or TXT)
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadFeedback("جارٍ رفع وفهرسة المستند...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "فشل رفع الملف");
      }

      const data = await res.json();
      setUploadFeedback(`✅ تم بنجاح إضافة ${data.articles_indexed} فصلاً من "${data.source}"!`);
      await refreshDocuments();

      setTimeout(() => {
        setUploadFeedback(null);
      }, 5000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "حدث خطأ أثناء الفهرسة";
      setUploadFeedback(`❌ ${message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col h-screen max-h-screen bg-zinc-950 text-zinc-100 p-3 sm:p-6" dir="rtl">
      <div className="flex-1 flex flex-col w-full max-w-3xl mx-auto gap-3 overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-zinc-800/80 pb-3 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-lg shadow-md shadow-emerald-950">
              ⚖️
            </div>
            <div>
              <h1 className="text-lg font-bold text-zinc-100 leading-tight">مستشار القانوني</h1>
              <p className="text-xs text-zinc-400">مساعد ذكي للتشريع والقوانين التونسية</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                onClick={clearHistory}
                className="text-xs px-2.5 py-1 rounded-lg border border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:text-red-400 hover:border-red-900/50 transition-all"
              >
                مسح السجل
              </button>
            )}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs">
              <span
                className={`h-2 w-2 rounded-full ${
                  isConnected ? "bg-emerald-500 shadow-sm shadow-emerald-500/50" : "bg-red-500"
                }`}
              />
              <span className="text-zinc-400 font-medium">
                {isConnected ? "متصل" : "غير متصل"}
              </span>
            </div>
          </div>
        </header>

        {/* Active Documents & Status bar */}
        <div className="shrink-0 flex flex-wrap items-center justify-between gap-2">
          <PipelineStatusIndicator status={status} />

          {/* Upload Button */}
          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".pdf,.txt"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-emerald-700/50 bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 font-medium transition-all disabled:opacity-50"
            >
              <span>{isUploading ? "⏳" : "📎"}</span>
              <span>{isUploading ? "جارٍ الرفع..." : "إضافة قانون / PDF"}</span>
            </button>
          </div>
        </div>

        {/* Upload feedback banner */}
        {uploadFeedback && (
          <div className="shrink-0 p-2.5 rounded-xl bg-zinc-900/90 border border-zinc-800 text-xs text-zinc-200 animate-fadeIn">
            {uploadFeedback}
          </div>
        )}

        {/* Indexed Documents Tags */}
        {indexedDocs.length > 0 && (
          <div className="shrink-0 flex items-center gap-1.5 overflow-x-auto py-1 text-xs text-zinc-400">
            <span className="shrink-0 text-zinc-500">القوانين المفهرسة:</span>
            {indexedDocs.map((doc, idx) => (
              <span
                key={idx}
                className="shrink-0 px-2.5 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300"
              >
                📜 {doc.source} ({doc.articles_count} فصل)
              </span>
            ))}
          </div>
        )}

        {/* Chat Message Stream */}
        <main className="flex-1 overflow-hidden">
          <ChatHistory
            messages={messages}
            isThinking={status === "processing"}
          />
        </main>

        {/* Quick prompt suggestions */}
        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2 shrink-0 justify-center">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                onClick={() => sendQuery(prompt)}
                disabled={!isConnected || status === "processing"}
                className="text-xs px-3 py-1.5 rounded-full border border-zinc-800 bg-zinc-900/70 hover:bg-emerald-950/30 hover:border-emerald-600/50 text-zinc-300 transition-all text-right disabled:opacity-50"
              >
                💡 {prompt}
              </button>
            ))}
          </div>
        )}

        {/* Chat Input */}
        <footer className="shrink-0 bg-zinc-900/70 border border-zinc-800/80 rounded-2xl p-2 shadow-xl backdrop-blur-md">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendQuery(input);
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="اطرح استفسارك القانوني..."
              disabled={!isConnected || status === "processing"}
              className="flex-1 bg-transparent text-zinc-100 placeholder-zinc-500 text-sm px-3.5 py-2 outline-none disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={!isConnected || !input.trim() || status === "processing"}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-sm font-semibold shadow-md shadow-emerald-950/50 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              إرسال
            </button>
          </form>
        </footer>
      </div>
    </div>
  );
}