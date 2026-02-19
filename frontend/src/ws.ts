import { getWebSocketUrl } from "./api";
import type { WsEvent } from "./types";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function createWsClient(onEvent: (event: WsEvent) => void, onStatus: (status: ConnectionStatus) => void): () => void {
  let socket: WebSocket | null = null;
  let active = true;
  let reconnectMs = 1000;
  let reconnectTimer: number | null = null;

  const connect = () => {
    if (!active) return;
    onStatus("connecting");
    socket = new WebSocket(getWebSocketUrl());

    socket.onopen = () => {
      reconnectMs = 1000;
      onStatus("connected");
    };

    socket.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data) as WsEvent;
        onEvent(parsed);
      } catch {
        // Ignore malformed messages
      }
    };

    socket.onerror = () => {
      onStatus("disconnected");
    };

    socket.onclose = () => {
      onStatus("disconnected");
      if (!active) return;
      reconnectTimer = window.setTimeout(() => {
        reconnectMs = Math.min(10000, reconnectMs * 1.5);
        connect();
      }, reconnectMs);
    };
  };

  connect();

  return () => {
    active = false;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      socket.close();
    }
  };
}
