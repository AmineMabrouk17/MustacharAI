"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseAudioRecorderOptions {
  onDataAvailable?: (data: ArrayBuffer) => void;
  onError?: (error: Error) => void;
  timeSlice?: number;
}

const SAMPLE_RATE = 16000;
const MIN_BUFFER_SIZE = 256;
const MAX_BUFFER_SIZE = 16384;

function nearestPowerOfTwo(value: number): number {
  return Math.max(
    MIN_BUFFER_SIZE,
    Math.min(MAX_BUFFER_SIZE, 2 ** Math.round(Math.log2(value)))
  );
}

function floatTo16BitPCM(channelData: Float32Array): Int16Array {
  const samples = new Int16Array(channelData.length);
  for (let i = 0; i < channelData.length; i++) {
    const sample = Math.max(-1, Math.min(1, channelData[i]));
    samples[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return samples;
}

export function useAudioRecorder({
  onDataAvailable,
  onError,
  timeSlice = 250,
}: UseAudioRecorderOptions = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  const stopRecording = useCallback(() => {
    const context = audioContextRef.current;
    const stream = streamRef.current;

    if (processorRef.current) {
      processorRef.current.onaudioprocess = null;
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (context) {
      void context.close();
      audioContextRef.current = null;
    }

    setAnalyserNode(null);
    setIsRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioContextRef.current = audioContext;

      const muteGain = audioContext.createGain();
      muteGain.gain.value = 0;
      muteGain.connect(audioContext.destination);

      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(muteGain);
      setAnalyserNode(analyser);

      const bufferSize = nearestPowerOfTwo((SAMPLE_RATE * timeSlice) / 1000);
      const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
      processor.onaudioprocess = (event) => {
        event.outputBuffer.getChannelData(0).fill(0);
        const channel = event.inputBuffer.getChannelData(0);
        const pcm = floatTo16BitPCM(channel);
        onDataAvailable?.(pcm.buffer as ArrayBuffer);
      };
      source.connect(processor);
      processor.connect(muteGain);
      processorRef.current = processor;

      setIsRecording(true);
    } catch (error) {
      onError?.(error instanceof Error ? error : new Error("Failed to start recording"));
    }
  }, [onDataAvailable, onError, timeSlice]);

  useEffect(() => {
    return () => {
      stopRecording();
    };
  }, [stopRecording]);

  return {
    isRecording,
    analyserNode,
    startRecording,
    stopRecording,
  };
}