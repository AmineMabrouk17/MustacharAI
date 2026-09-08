"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface PlayableRegion {
  buffer: AudioBuffer;
  offset: number;
  duration: number;
}

export function useAudioPlayback() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [status, setStatus] = useState<"idle" | "speaking">("idle");
  const audioContextRef = useRef<AudioContext | null>(null);
  const accumulatorRef = useRef<Uint8Array>(new Uint8Array(0));
  const decodedBytesRef = useRef(0);
  const playedSecondsRef = useRef(0);
  const regionQueueRef = useRef<PlayableRegion[]>([]);
  const isPlayingRef = useRef(false);
  const mountedRef = useRef(true);
  const decodingRef = useRef(false);
  const processingRef = useRef(false);

  const ensureAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }
    return audioContextRef.current;
  }, []);

  const processQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;

    try {
      while (mountedRef.current) {
        const region = regionQueueRef.current.shift();
        if (!region) break;

        isPlayingRef.current = true;
        setIsPlaying(true);
        setStatus("speaking");

        try {
          const context = ensureAudioContext();
          const source = context.createBufferSource();
          source.buffer = region.buffer;
          source.connect(context.destination);

          source.start(0, region.offset, region.duration);
          await new Promise<void>((resolve) => {
            source.onended = () => resolve();
          });
        } catch (error) {
          console.error("Error playing audio:", error);
        }
      }
    } finally {
      isPlayingRef.current = false;
      processingRef.current = false;
      if (mountedRef.current) {
        setIsPlaying(false);
        setStatus("idle");
      }
    }
  }, [ensureAudioContext]);

  const decodeNewRegions = useCallback(async () => {
    if (decodingRef.current || !mountedRef.current) return;
    decodingRef.current = true;

    try {
      while (mountedRef.current) {
        const accumulated = accumulatorRef.current;
        if (accumulated.length <= decodedBytesRef.current) break;
        decodedBytesRef.current = accumulated.length;

        const context = ensureAudioContext();
        const copy = accumulated.slice();
        let audioBuffer: AudioBuffer;
        try {
          audioBuffer = await context.decodeAudioData(copy.buffer);
        } catch {
          // Not enough of the MP3 stream is available yet; retry when the
          // next part arrives.
          break;
        }

        const totalSeconds = audioBuffer.duration;
        if (totalSeconds > playedSecondsRef.current) {
          regionQueueRef.current.push({
            buffer: audioBuffer,
            offset: playedSecondsRef.current,
            duration: totalSeconds - playedSecondsRef.current,
          });
          playedSecondsRef.current = totalSeconds;
        }
      }
    } finally {
      decodingRef.current = false;
      void processQueue();
    }
  }, [ensureAudioContext, processQueue]);

  const enqueueAudio = useCallback(
    async (audioData: Blob) => {
      const part = new Uint8Array(await audioData.arrayBuffer());
      const previous = accumulatorRef.current;
      const combined = new Uint8Array(previous.length + part.length);
      combined.set(previous);
      combined.set(part, previous.length);
      accumulatorRef.current = combined;
      void decodeNewRegions();
    },
    [decodeNewRegions]
  );

  const getQueueLength = useCallback(() => {
    return regionQueueRef.current.length;
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
