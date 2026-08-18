"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useAudioPlayback() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [status, setStatus] = useState<"idle" | "speaking">("idle");
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<Blob[]>([]);
  const isPlayingRef = useRef(false);
  const mountedRef = useRef(true);
  const processingRef = useRef(false);

  const processAll = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;

    while (audioQueueRef.current.length > 0) {
      if (!mountedRef.current) break;

      isPlayingRef.current = true;
      setIsPlaying(true);
      setStatus("speaking");

      const blob = audioQueueRef.current.shift();
      if (!blob) break;

      try {
        if (!audioContextRef.current) {
          audioContextRef.current = new AudioContext();
        }

        const arrayBuffer = await blob.arrayBuffer();
        const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);

        const source = audioContextRef.current.createBufferSource();
        source.buffer = audioBuffer;

        await new Promise<void>((resolve) => {
          source.onended = () => resolve();
          source.start();
        });
      } catch (error) {
        console.error("Error playing audio:", error);
      }
    }

    isPlayingRef.current = false;
    processingRef.current = false;
    if (mountedRef.current) {
      setIsPlaying(false);
      setStatus("idle");
    }
  }, []);

  const enqueueAudio = useCallback(
    (audioData: Blob) => {
      audioQueueRef.current.push(audioData);
      if (!processingRef.current) {
        void processAll();
      }
    },
    [processAll]
  );

  const getQueueLength = useCallback(() => {
    return audioQueueRef.current.length;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return {
    isPlaying,
    status,
    enqueueAudio,
    getQueueLength,
  };
}
