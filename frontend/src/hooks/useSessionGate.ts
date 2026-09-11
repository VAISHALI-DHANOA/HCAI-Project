import { useEffect, useRef, useState } from "react";
import { chooseSessionMode, createSession, getSessionId, getSessionLobby, setSessionId } from "../api";
import type { SessionMode } from "../api";
import { createWsClient } from "../ws";

export function useSessionGate() {
  const [gate, setGate] = useState<"entry" | "mode" | "waiting" | "app">(() => {
    const params = new URLSearchParams(window.location.search);
    return params.has("demo") ? "app" : params.has("session") ? "waiting" : "entry";
  });
  const [mode, setMode] = useState<SessionMode>("debate");
  const [participant, setParticipant] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.has("session") && !params.has("demo");
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hostKey = useRef("");
  const pending = useRef(false);

  function enterApp(selected: SessionMode) {
    setMode(selected);
    setGate("app");
  }

  async function perform(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try { await action(); }
    catch (error) { setError(error instanceof Error ? error.message : "Could not connect. Please try again."); }
    finally { pending.current = false; setBusy(false); }
  }

  useEffect(() => {
    if (gate !== "waiting") return;
    let active = true;
    let disconnect: (() => void) | undefined;
    // Validate before opening a socket: the legacy socket endpoint creates stores.
    getSessionLobby(getSessionId()).then((lobby) => {
      if (!active) return;
      if (lobby.mode) { enterApp(lobby.mode); return; }
      disconnect = createWsClient((event) => {
        if (active && event.type === "lobby" && event.mode) enterApp(event.mode);
      }, (status) => {
        if (active) setError(status === "disconnected" ? "Connection lost. Reconnecting to your host…" : "");
      });
    }).catch((error) => {
      if (active) { setError(error instanceof Error ? error.message : "Could not validate the session."); setGate("entry"); }
    });
    return () => { active = false; disconnect?.(); };
  }, [gate]);

  return {
    gate, mode, participant, busy, error, setMode,
    back: () => { setError(""); setGate("entry"); },
    backToMode: () => { setError(""); setGate("mode"); },
    create: () => perform(async () => {
      const lobby = await createSession();
      hostKey.current = lobby.host_key;
      setParticipant(false);
      setSessionId(lobby.code);
      setGate("mode");
    }),
    join: (code: string) => perform(async () => {
      const normalized = code.trim();
      if (!normalized || normalized.length > 64) throw new Error("Enter a valid session code from your host.");
      const lobby = await getSessionLobby(normalized);
      setParticipant(true);
      setSessionId(lobby.code);
      if (lobby.mode) enterApp(lobby.mode);
      else setGate("waiting");
    }),
    select: (selected: SessionMode) => perform(async () => {
      await chooseSessionMode(getSessionId(), selected, hostKey.current);
      enterApp(selected);
    }),
  };
}
