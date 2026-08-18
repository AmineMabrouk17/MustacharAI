"use client";

import { useEffect, useRef } from "react";
import { LegalCitationCard } from "./LegalCitationCard";
import type { Citation } from "@/hooks/useWebSocket";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  fallback?: boolean;
  timestamp: number;
}

interface ChatHistoryProps {
  messages: ChatMessage[];
}

export function ChatHistory({ messages }: ChatHistoryProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (messages.length === 0) return null;

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-3 max-h-[50vh] overflow-y-auto rounded-lg bg-zinc-900/30 p-4"
    >
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "user" ? "justify-start" : "justify-end"}`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-3 ${
              msg.role === "user"
                ? "bg-zinc-800 text-zinc-100 rounded-tr-sm"
                : "bg-emerald-900/40 text-zinc-100 rounded-tl-sm"
            }`}
          >
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {msg.text}
            </p>

            {msg.citations && msg.citations.length > 0 && (
              <div className="mt-3 flex flex-col gap-2">
                <span className="text-xs text-zinc-400 font-medium">
                  المراجع القانونية
                </span>
                {msg.citations.map((citation, i) => (
                  <LegalCitationCard
                    key={`${msg.id}-cite-${i}`}
                    citation={citation}
                    index={i}
                  />
                ))}
              </div>
            )}

            <div className="mt-1.5 text-[10px] text-zinc-500">
              {new Date(msg.timestamp).toLocaleTimeString("ar-TN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
