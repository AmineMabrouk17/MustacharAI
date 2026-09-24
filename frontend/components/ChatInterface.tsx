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

interface ModelOption {
  id: string;
  label: string;
  models: string[];
}

interface ModelsInfo {
  providers: ModelOption[];
  active: { provider: string; model: string } | null;
  openrouter_configured?: boolean;
}

export function ChatInterface() {
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [input, setInput] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);
  const [indexedDocs, setIndexedDocs] = useState<IndexedDoc[]>([]);
  const [modelsInfo, setModelsInfo] = useState<ModelsInfo | null>(null);
  const [activeModel, setActiveModel] = useState<string>("");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { messages, setMessages, clearHistory } = useChatHistory();

  // Document deletion: the ✕ button opens a styled modal (deleteTarget),
  // then the user confirms or cancels — no browser native confirm().
  const [deleteTarget, setDeleteTarget] = useState<IndexedDoc | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // OpenRouter: user-provided API key + model (configured through a modal)
  const [showOpenRouter, setShowOpenRouter] = useState(false);
  const [orApiKey, setOrApiKey] = useState("");
  const [orModel, setOrModel] = useState("");
  const [isSavingOpenRouter, setIsSavingOpenRouter] = useState(false);

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

  // Actually delete one indexed document (all its chunks) from ChromaDB
  const confirmDelete = useCallback(
    async (doc: IndexedDoc) => {
      if (isDeleting) return;
      const source = doc.source;
      setIsDeleting(true);
      setUploadFeedback(`🗑️ جارٍ حذف «${source}»...`);
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/v1/documents/${encodeURIComponent(source)}`,
          { method: "DELETE" }
        );
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          throw new Error(data?.detail || "فشل حذف المستند");
        }
        setUploadFeedback(`✅ تم حذف «${source}» (${data.removed_chunks} فصل).`);
        setDeleteTarget(null);
        await refreshDocuments();
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "حدث خطأ أثناء الحذف";
        setUploadFeedback(`❌ ${message}`);
        setDeleteTarget(null);
      } finally {
        setIsDeleting(false);
        setTimeout(() => setUploadFeedback(null), 5000);
      }
    },
    [API_BASE_URL, isDeleting, refreshDocuments]
  );

  // Close the delete modal with the Escape key (never while deleting)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isDeleting) setDeleteTarget(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDeleting]);

  useEffect(() => {
    // Load indexed documents once on mount; setState happens after an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshDocuments();

    // Load available LLM models and the active one
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/v1/models`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: ModelsInfo | null) => {
        if (cancelled || !data) return;
        setModelsInfo(data);
        if (data.active) {
          setActiveModel(`${data.active.provider}/${data.active.model}`);
        }
      })
      .catch(() => {
        /* Backend not yet reachable */
      });
    return () => {
      cancelled = true;
    };
  }, [API_BASE_URL, refreshDocuments]);

  // Switch the active LLM (Groq / Gemini)
  const handleModelChange = useCallback(
    async (value: string) => {
      const [provider, ...rest] = value.split("/");
      const model = rest.join("/");
      setUploadFeedback(`🔄 تبديل النموذج إلى ${model}...`);
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/models/active`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, model }),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          throw new Error(data?.detail || "فشل تبديل النموذج");
        }
        setActiveModel(`${data.active.provider}/${data.active.model}`);
        setUploadFeedback(
          `✅ النموذج النشط: ${data.active.provider}/${data.active.model}`
        );
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "حدث خطأ أثناء تبديل النموذج";
        setUploadFeedback(`❌ ${message}`);
      } finally {
        setTimeout(() => setUploadFeedback(null), 4000);
      }
    },
    [API_BASE_URL]
  );

  // Save the user's OpenRouter key + model (validated server-side)
  const saveOpenRouterConfig = useCallback(async () => {
    if (!orApiKey.trim() || !orModel.trim()) {
      setUploadFeedback("❌ أدخل مفتاح API واسم النموذج");
      return;
    }
    setIsSavingOpenRouter(true);
    setUploadFeedback("🔄 جارٍ التحقق من مفتاح OpenRouter...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/models/openrouter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: orApiKey.trim(), model: orModel.trim() }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail || "فشل إعداد OpenRouter");
      }
      setModelsInfo((prev) =>
        prev
          ? { ...prev, providers: data.providers, openrouter_configured: true }
          : prev
      );
      setShowOpenRouter(false);
      setOrApiKey("");
      setOrModel("");
      setUploadFeedback(`✅ نموذج OpenRouter «${data.model}» جاهز — اختره من القائمة.`);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "حدث خطأ أثناء إعداد OpenRouter";
      setUploadFeedback(`❌ ${message}`);
    } finally {
      setIsSavingOpenRouter(false);
      setTimeout(() => setUploadFeedback(null), 5000);
    }
  }, [API_BASE_URL, orApiKey, orModel]);

  const handleAnswer = useCallback(
    (
      text: string,
      citations: Citation[],
      fallback: boolean,
      error?: string
    ) => {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          text,
          citations: fallback ? [] : citations,
          fallback,
          error,
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
            {modelsInfo && modelsInfo.providers.length > 0 && activeModel && (
              <select
                value={activeModel}
                onChange={(e) => handleModelChange(e.target.value)}
                title="نموذج الذكاء الاصطناعي"
                aria-label="نموذج الذكاء الاصطناعي"
                className="max-w-[130px] text-xs px-2 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-zinc-300 focus:outline-none focus:border-emerald-600/50"
              >
                {modelsInfo.providers.map((p) => (
                  <optgroup key={p.id} label={p.label}>
                    {p.models.map((m) => (
                      <option key={`${p.id}/${m}`} value={`${p.id}/${m}`}>
                        {m.split("/").pop()}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            )}
            <button
              onClick={() => setShowOpenRouter(true)}
              title="إضافة نموذج OpenRouter (المفتاح واسم النموذج الخاصين بك)"
              className={`text-xs px-2 py-1 rounded-lg border transition-all ${
                modelsInfo?.openrouter_configured
                  ? "border-indigo-600/50 bg-indigo-900/30 text-indigo-300 hover:bg-indigo-900/50"
                  : "border-zinc-800 bg-zinc-900/80 text-zinc-400 hover:border-indigo-600/50 hover:text-indigo-300"
              }`}
            >
              OpenRouter
            </button>
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
                className="group shrink-0 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300"
              >
                <span>📜 {doc.source} ({doc.articles_count} فصل)</span>
                <button
                  onClick={() => setDeleteTarget(doc)}
                  title={`حذف ${doc.source}`}
                  aria-label={`حذف ${doc.source}`}
                  className="text-zinc-600 hover:text-red-400 transition-colors text-xs leading-none"
                >
                  ✕
                </button>
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

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => {
            if (!isDeleting) setDeleteTarget(null);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-zinc-700/60 bg-zinc-900 p-5 shadow-2xl animate-fadeIn"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-xl bg-red-600/15 border border-red-600/30 flex items-center justify-center text-lg">
                🗑️
              </div>
              <div>
                <h2 id="delete-modal-title" className="font-bold text-zinc-100">
                  تأكيد الحذف
                </h2>
                <p className="text-xs text-zinc-500">
                  {deleteTarget.articles_count} فصلاً سيتم إزالتها من الفهرس
                </p>
              </div>
            </div>
            <p className="text-sm text-zinc-300 leading-relaxed mb-5">
              هل تريد حذف «
              <span className="text-red-400 font-medium">
                {deleteTarget.source}
              </span>
              » من القوانين المفهرسة؟ لا يمكن التراجع عن هذه العملية.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-xl border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                إلغاء
              </button>
              <button
                onClick={() => confirmDelete(deleteTarget)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-semibold shadow-md shadow-red-950/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeleting ? "جارٍ الحذف..." : "حذف"}
              </button>
            </div>
          </div>
        </div>
      )}
    {/* OpenRouter configuration modal */}
      {showOpenRouter && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={() => {
            if (!isSavingOpenRouter) setShowOpenRouter(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="openrouter-modal-title"
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-zinc-700/60 bg-zinc-900 p-5 shadow-2xl animate-fadeIn"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-600/15 border border-indigo-600/30 flex items-center justify-center text-lg">
                🔑
              </div>
              <div>
                <h2 id="openrouter-modal-title" className="font-bold text-zinc-100">
                  إعداد OpenRouter
                </h2>
                <p className="text-xs text-zinc-500">
                  استخدم نموذجك الخاص (مفتاح API + اسم النموذج)
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-3 mb-5">
              <div>
                <label
                  htmlFor="or-api-key"
                  className="block text-xs text-zinc-400 mb-1"
                >
                  مفتاح API (sk-or-v1-...)
                </label>
                <input
                  id="or-api-key"
                  type="password"
                  value={orApiKey}
                  onChange={(e) => setOrApiKey(e.target.value)}
                  placeholder="sk-or-v1-..."
                  autoComplete="off"
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-700 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-600/60"
                />
              </div>
              <div>
                <label
                  htmlFor="or-model"
                  className="block text-xs text-zinc-400 mb-1"
                >
                  اسم النموذج (model ID)
                </label>
                <input
                  id="or-model"
                  type="text"
                  value={orModel}
                  onChange={(e) => setOrModel(e.target.value)}
                  placeholder="openai/gpt-6-luna"
                  className="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-700 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-600/60"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowOpenRouter(false)}
                disabled={isSavingOpenRouter}
                className="px-4 py-2 rounded-xl border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                إلغاء
              </button>
              <button
                onClick={saveOpenRouterConfig}
                disabled={isSavingOpenRouter || !orApiKey.trim() || !orModel.trim()}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-md shadow-indigo-950/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSavingOpenRouter ? "جارٍ الحفظ..." : "حفظ"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}