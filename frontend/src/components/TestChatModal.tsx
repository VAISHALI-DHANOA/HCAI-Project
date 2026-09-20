import { useCallback, useEffect, useRef, useState } from "react";
import { testChat } from "../api";
import type { ChatMessage, DraftAgent } from "../types";
import type { VoiceParams } from "../hooks/useTTS";

interface RecognitionResultEvent {
  results: { [index: number]: { [index: number]: { transcript: string } } };
}

interface RecognitionInstance {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
}

type RecognitionConstructor = new () => RecognitionInstance;

interface TestChatModalProps {
  agent: DraftAgent;
  onClose: () => void;
  onError: (message: string) => void;
  speak: (text: string, params: VoiceParams) => Promise<void>;
  stopAudio: () => void;
}

export function TestChatModal({ agent, onClose, onError, speak, stopAudio }: TestChatModalProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pendingRef = useRef(false);
  const recognitionRef = useRef<RecognitionInstance | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => () => {
    abortRef.current?.abort();
    recognitionRef.current?.stop();
    stopAudio();
  }, [stopAudio]);

  const send = useCallback(async (overrideMessage?: string) => {
    const message = (overrideMessage ?? input).trim();
    if (!message || pendingRef.current) return;

    const abort = new AbortController();
    abortRef.current = abort;
    pendingRef.current = true;
    setInput("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    setLoading(true);

    try {
      const result = await testChat(
        agent.name,
        agent.persona_text,
        agent.personality,
        messages.map((item) => ({
          role: item.role === "user" ? "user" : "assistant",
          content: item.content,
        })),
        message,
        abort.signal,
      );
      setMessages((current) => [...current, { role: "agent", content: result.reply }]);
      if (overrideMessage) {
        const voiceIndex = [...agent.name].reduce((sum, character) => sum + character.charCodeAt(0), 0);
        void speak(result.reply, { voiceIndex }).catch((error: unknown) => {
          onError(error instanceof Error ? error.message : "Voice playback failed");
        });
      }
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setMessages((current) => [...current, { role: "agent", content: "(Error: could not reach agent)" }]);
      }
    } finally {
      abortRef.current = null;
      pendingRef.current = false;
      setLoading(false);
    }
  }, [agent, input, messages, onError, speak]);

  const sendRef = useRef(send);
  sendRef.current = send;

  function stopListening() {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setListening(false);
  }

  function startListening() {
    if (pendingRef.current) return;
    const speechWindow = window as typeof window & {
      SpeechRecognition?: RecognitionConstructor;
      webkitSpeechRecognition?: RecognitionConstructor;
    };
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!Recognition) return;

    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      void sendRef.current(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  function close() {
    abortRef.current?.abort();
    stopListening();
    stopAudio();
    onClose();
  }

  return <div className="test-chat-overlay" onClick={close}>
    <div className="test-chat-modal setup-pixel-panel" onClick={(event) => event.stopPropagation()}>
      <div className="test-chat-modal__header">
        <div className="test-chat-modal__agent-info">
          <img
            className="test-chat-modal__avatar"
            src={`https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`}
            alt={agent.name}
            width={40}
            height={40}
          />
          <div>
            <div className="test-chat-modal__name">{agent.name}</div>
            <span className="personality-badge personality-badge--small">{agent.personality.role_name}</span>
          </div>
        </div>
        <button className="test-chat-modal__close" onClick={close}>X</button>
      </div>

      <div className="test-chat-modal__messages">
        {messages.length === 0 && <div className="test-chat-modal__empty">
          Say hello to {agent.name} to test their personality.
        </div>}
        {messages.map((message, index) => <div key={index} className={`test-chat__bubble test-chat__bubble--${message.role}`}>
          {message.content}
        </div>)}
        {loading && <div className="test-chat__bubble test-chat__bubble--agent test-chat__bubble--loading">
          Thinking...
        </div>}
        <div ref={logEndRef} />
      </div>

      <div className="test-chat-modal__input-bar">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder={listening ? "Listening..." : "Type or speak a message..."}
          disabled={loading || listening}
        />
        <button
          className={`btn-mic${listening ? " btn-mic--active" : ""}`}
          onClick={listening ? stopListening : startListening}
          disabled={loading}
          type="button"
          title={listening ? "Stop listening" : "Speak"}
        >
          {listening ? "\u23F9" : "\uD83C\uDFA4"}
        </button>
        <button onClick={() => void send()} disabled={loading || !input.trim()}>Send</button>
      </div>
    </div>
  </div>;
}
