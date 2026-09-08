"use client";

import { useEffect, useRef, useState } from "react";

export function useAudioPlayback() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [status, setStatus] = useState<"idle" | "speaking">("idle");
  const mountedRef = useRef(true);

  const mediaSourceRef = useRef<MediaSource | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sourceBufferRef = useRef<SourceBuffer | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const pendingRef = useRef<ArrayBuffer[]>([]);
  const updatingRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      audioRef.current?.pause();
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      if (mediaSourceRef.current?.readyState === "open") {
        try {
          mediaSourceRef.current.endOfStream();
        } catch {
          /* no-op */
        }
      }
      mediaSourceRef.current = null;
      audioRef.current = null;
      sourceBufferRef.current = null;
      objectUrlRef.current = null;
    };
  }, []);

  function appendBuffer(data: ArrayBuffer) {
    const sourceBuffer = sourceBufferRef.current;
    if (!sourceBuffer || updatingRef.current) {
      pendingRef.current.push(data);
      return;
    }
    try {
      updatingRef.current = true;
      sourceBuffer.appendBuffer(data);
    } catch (error) {
      updatingRef.current = false;
      pendingRef.current.push(data);
      console.error("Error appending audio chunk:", error);
    }
  }

  function flushPending() {
    updatingRef.current = false;
    const pending = pendingRef.current;
    pendingRef.current = [];
    for (const chunk of pending) {
      appendBuffer(chunk);
    }
  }

  function setupSourceBuffer() {
    const mediaSource = mediaSourceRef.current;
    if (sourceBufferRef.current || !mediaSource) return;
    try {
      sourceBufferRef.current = mediaSource.addSourceBuffer("audio/mpeg");
      sourceBufferRef.current.addEventListener("updateend", flushPending);
      sourceBufferRef.current.addEventListener("error", () => {
        updatingRef.current = false;
      });
    } catch (error) {
      console.error("Error adding source buffer:", error);
    }
  }

  function play() {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused) return;
    void audio
      .play()
      .then(() => {
        if (!mountedRef.current) return;
        setIsPlaying(true);
        setStatus("speaking");
      })
      .catch(() => {});
  }

  function ensureMediaSource() {
    if (mediaSourceRef.current || audioRef.current) return;

    const mediaSource = new MediaSource();
    const audio = new Audio();
    const objectUrl = URL.createObjectURL(mediaSource);
    audio.src = objectUrl;

    mediaSourceRef.current = mediaSource;
    audioRef.current = audio;
    objectUrlRef.current = objectUrl;

    mediaSource.addEventListener(
      "sourceopen",
      () => {
        setupSourceBuffer();
        for (const chunk of pendingRef.current) {
          appendBuffer(chunk);
        }
        pendingRef.current = [];
      },
      { once: true }
    );
    audio.addEventListener(
      "ended",
      () => {
        if (!mountedRef.current) return;
        setIsPlaying(false);
        setStatus("idle");
      },
      { once: true }
    );
  }

  async function enqueueAudio(audioData: Blob) {
    if (!mountedRef.current) return;
    ensureMediaSource();

    const chunk = await audioData.arrayBuffer();
    if (mediaSourceRef.current?.readyState === "open") {
      appendBuffer(chunk);
    } else {
      pendingRef.current.push(chunk);
    }
    play();
  }

  return {
    isPlaying,
    status,
    enqueueAudio,
  };
}
