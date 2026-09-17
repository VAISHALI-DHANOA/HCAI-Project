import { useCallback, useEffect, useRef } from "react";
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
  const cancelRef = useRef<() => void>(() => {});
  const stop = useCallback(() => { cancelRef.current(); }, []);
  useEffect(() => stop, [stop]);
  const speak = useCallback((text: string, params: VoiceParams): Promise<void> => {
    stop();
    return new Promise<void>((resolve, reject) => {
      const abort = new AbortController();
      let audio: HTMLAudioElement | undefined;
      let url: string | undefined;
      let settled = false;
      let timer: ReturnType<typeof setTimeout>;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        abort.abort();
        if (audio) { audio.onended = null; audio.onerror = null; audio.pause(); audio.removeAttribute("src"); }
        if (url) URL.revokeObjectURL(url);
        cancelRef.current = () => {};
        if (error) reject(error); else resolve();
      };
      cancelRef.current = () => finish();
      timer = setTimeout(() => finish(new Error("Voice audio loading timed out. Continuing with text.")), 30000);
      const voice = OPENAI_VOICES[params.voiceIndex % OPENAI_VOICES.length];
      void getTTSAudio(text, voice, abort.signal).then(async (blob) => {
        if (settled) return;
        url = URL.createObjectURL(blob);
        audio = new Audio(url);
        audio.onended = () => finish();
        audio.onerror = () => finish(new Error("Voice audio could not be played. Continuing with text."));
        clearTimeout(timer);
        timer = setTimeout(() => finish(new Error("Voice playback timed out. Continuing with text.")), 120000);
        await audio.play();
      }).catch((error: unknown) => finish(new Error(error instanceof Error ? error.message : "Voice playback failed")));
    });
  }, [stop]);
  return { speak, stop };
}
