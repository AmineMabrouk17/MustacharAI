"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { SetStateAction } from "react";
import type { ChatMessage } from "@/components/ChatHistory";

const STORAGE_KEY = "mustachar.chat.history.v1";

let cachedMessages: ChatMessage[] | null = null;

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false;
  const m = value as Record<string, unknown>;
  return (
    typeof m.id === "string" &&
    (m.role === "user" || m.role === "assistant") &&
    typeof m.text === "string" &&
    typeof m.timestamp === "number"
  );
}

function loadMessages(): ChatMessage[] {
  if (cachedMessages) return cachedMessages;
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    cachedMessages = Array.isArray(parsed) ? parsed.filter(isChatMessage) : [];
  } catch {
    cachedMessages = [];
  }
  return cachedMessages;
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emitChange(): void {
  for (const listener of listeners) listener();
}

function persist(messages: ChatMessage[]): void {
  cachedMessages = messages;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {}
  emitChange();
}

export function useChatHistory() {
  const messages = useSyncExternalStore(subscribe, loadMessages, () => []);

  const setMessages = useCallback((update: SetStateAction<ChatMessage[]>) => {
    persist(typeof update === "function" ? update(loadMessages()) : update);
  }, []);

  const clearHistory = useCallback(() => {
    persist([]);
  }, []);

  return { messages, setMessages, clearHistory };
}