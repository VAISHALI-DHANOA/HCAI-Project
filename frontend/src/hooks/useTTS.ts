import { useCallback, useEffect, useRef } from "react";
import type { Agent } from "../types";

export interface VoiceParams {
  rate: number;
  pitch: number;
  voiceIndex: number;
}

export function agentVoiceParams(agent: Agent): VoiceParams {
  const energy = agent.energy;
  const isMediator = agent.role === "mediator";

  // Natural-sounding ranges close to normal speech
  const rate = isMediator ? 1.0 : 0.9 + energy * 0.15;
  const pitch = isMediator ? 1.0 : 0.95 + energy * 0.1;

  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return { rate, pitch, voiceIndex: seed };
}

export function useTTS() {
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);

  // Load and pre-filter voices (prefer en-US, sort by quality)
  useEffect(() => {
    if (!("speechSynthesis" in window)) return;

    function loadVoices() {
      const all = window.speechSynthesis.getVoices();
      // Prefer standard American English voices
      const enUS = all.filter((v) => v.lang === "en-US");
      const pool = enUS.length > 0 ? enUS : all;
      // Sort: local/high-quality first, compact/low-quality last
      pool.sort((a, b) => {
        const score = (v: SpeechSynthesisVoice) =>
          (v.localService ? 2 : 0) + (v.name.toLowerCase().includes("compact") ? -1 : 0);
        return score(b) - score(a);
      });
      voicesRef.current = pool;
    }

    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, []);

  const speak = useCallback((text: string, params: VoiceParams, onEnd?: () => void) => {
    if (!("speechSynthesis" in window)) {
      onEnd?.();
      return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    const voices = voicesRef.current;

    if (voices.length > 0) {
      utterance.voice = voices[params.voiceIndex % voices.length];
    }
    utterance.rate = params.rate;
    utterance.pitch = params.pitch;
    utterance.volume = 0.8;

    if (onEnd) {
      utterance.onend = () => onEnd();
      utterance.onerror = () => onEnd();
    }

    window.speechSynthesis.speak(utterance);
  }, []);

  const stop = useCallback(() => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }, []);

  return { speak, stop };
}
