import { useCallback, useRef } from "react";
import type { Agent } from "../types";
import { getTTSAudio } from "../api";

const OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"];

export interface VoiceParams {
  voiceIndex: number;
}

export function agentVoiceParams(agent: Agent): VoiceParams {
  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return { voiceIndex: seed };
}

export function useTTS() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const generationRef = useRef(0);

  const speak = useCallback(async (text: string, params: VoiceParams, onEnd?: () => void) => {
    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    const gen = ++generationRef.current;

    try {
      const voice = OPENAI_VOICES[params.voiceIndex % OPENAI_VOICES.length];
      const blob = await getTTSAudio(text, voice);

      // If a newer speak() call was made while fetching, discard this result
      if (gen !== generationRef.current) return;

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        onEnd?.();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        onEnd?.();
      };

      await audio.play();
    } catch {
      if (gen === generationRef.current) onEnd?.();
    }
  }, []);

  const stop = useCallback(() => {
    generationRef.current++;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  }, []);

  return { speak, stop };
}
