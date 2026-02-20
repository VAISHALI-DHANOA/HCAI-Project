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

  const rate = isMediator ? 0.9 : 0.7 + energy * 0.6;
  const pitch = isMediator ? 1.0 : 0.8 + energy * 0.5;

  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return { rate, pitch, voiceIndex: seed };
}

export function useTTS() {
  const voicesRef = useRef<SpeechSynthesisVoice[]>([]);

  // Load voices (they may load asynchronously in some browsers)
  useEffect(() => {
    if (!("speechSynthesis" in window)) return;

    function loadVoices() {
      voicesRef.current = window.speechSynthesis.getVoices();
    }

    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, []);

  const speak = useCallback((text: string, params: VoiceParams) => {
    if (!("speechSynthesis" in window)) return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    const voices = voicesRef.current;

    if (voices.length > 0) {
      // Prefer standard American English voices
      const enUSVoices = voices.filter((v) => v.lang === "en-US");
      const pool = enUSVoices.length > 0 ? enUSVoices : voices;
      utterance.voice = pool[params.voiceIndex % pool.length];
    }
    utterance.rate = params.rate;
    utterance.pitch = params.pitch;
    utterance.volume = 0.8;

    window.speechSynthesis.speak(utterance);
  }, []);

  const stop = useCallback(() => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }, []);

  return { speak, stop };
}
