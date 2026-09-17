import type { Agent, AgentPersonality, DatasetInfo, DraftAgent, ModeratorStrategy, PersonalityCatalog, State } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Unique session ID per browser tab — isolates state across tabs
const params = new URLSearchParams(window.location.search);
let _sessionId: string = params.get("session") ?? crypto.randomUUID();
export function getSessionId(): string {
  return _sessionId;
}

export function setSessionId(sessionId: string): void {
  _sessionId = sessionId.trim();
}

let _adminKey: string | null = null;
export function setAdminKey(key: string | null) {
  _adminKey = key;
}

function withSession(path: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}session=${encodeURIComponent(_sessionId)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }
  const response = await fetch(`${API_BASE}${withSession(path)}`, {
    ...init,
    headers: { ...headers, ...init?.headers },
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try { const body = JSON.parse(text); if (typeof body.detail === "string") message = body.detail; } catch { /* Plain-text response. */ }
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getState(): Promise<State> {
  return request<State>("/state");
}

export async function setTopic(topic: string): Promise<{ state: State }> {
  return request<{ state: State }>("/topic", {
    method: "POST",
    body: JSON.stringify({ topic })
  });
}

export async function getPersonalityCatalog(): Promise<PersonalityCatalog> {
  return request<PersonalityCatalog>("/personality-presets");
}

export type SessionMode = "debate" | "data";
export interface SessionLobby { code: string; mode: SessionMode | null; }
export function createSession() {
  return request<SessionLobby & { host_key: string }>("/sessions", { method: "POST" });
}
export function getSessionLobby(code: string) {
  return request<SessionLobby>(`/sessions/${encodeURIComponent(code)}`);
}
export function chooseSessionMode(code: string, mode: SessionMode, hostKey: string) {
  return request<SessionLobby>(`/sessions/${encodeURIComponent(code)}/mode`, {
    method: "PUT", headers: { "X-Host-Key": hostKey }, body: JSON.stringify({ mode }),
  });
}

export async function runRounds(rounds: number, signal?: AbortSignal): Promise<{ state: State }> {
  return request<{ state: State }>("/run", {
    method: "POST",
    body: JSON.stringify({ rounds }), signal,
  });
}

export async function reset(topic?: string): Promise<{ state: State }> {
  return request<{ state: State }>("/reset", {
    method: "POST",
    body: JSON.stringify({ topic })
  });
}

export async function loadDemo(): Promise<{ added: Agent[]; state: State }> {
  return request<{ added: Agent[]; state: State }>("/demo", { method: "POST" });
}

export async function getModeratorStrategies(): Promise<{ strategies: ModeratorStrategy[] }> {
  return request<{ strategies: ModeratorStrategy[] }>("/moderator-strategies");
}

export async function setModeratorStrategy(strategy_id: string): Promise<{ state: State }> {
  return request<{ state: State }>("/moderator-strategy", {
    method: "POST",
    body: JSON.stringify({ strategy_id }),
  });
}

export async function uploadDataset(file: File): Promise<{ parsed: DatasetInfo; state: State }> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }

  const response = await fetch(`${API_BASE}${withSession("/upload-dataset")}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Upload failed: ${response.status}`);
  }
  return (await response.json()) as { parsed: DatasetInfo; state: State };
}

export async function loadExample(name: string): Promise<{ state: State; parsed?: DatasetInfo }> {
  return request<{ state: State; parsed?: DatasetInfo }>(`/load-example?name=${encodeURIComponent(name)}`, { method: "POST" });
}

export async function intervene(message: string): Promise<{ state: State }> {
  return request<{ state: State }>("/intervene", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function addAgents(
  agents: Array<{ name: string; persona_text: string; energy: number; personality: AgentPersonality }>
): Promise<{ state: State }> {
  return request<{ state: State }>("/agents", {
    method: "POST",
    body: JSON.stringify({ user_agents: agents }),
  });
}

export async function syncAgents(agents: DraftAgent[], expected: State): Promise<{ state: State }> {
  return request<{ state: State }>("/agents/sync", {
    method: "POST",
    body: JSON.stringify({ user_agents: agents, run_id: expected.run_id, revision: expected.revision }),
  });
}

export async function testChat(
  agent_name: string,
  agent_persona: string,
  personality: AgentPersonality,
  messages: Array<{ role: string; content: string }>,
  user_message: string,
): Promise<{ reply: string }> {
  return request<{ reply: string }>("/chat", {
    method: "POST",
    body: JSON.stringify({ agent_name, agent_persona, personality, messages, user_message }),
  });
}

export async function getTTSAudio(text: string, voice: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${API_BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(`Voice request failed (${response.status}): ${body?.detail ?? response.statusText}`);
  }
  return response.blob();
}

export async function downloadLogs(): Promise<void> {
  const headers: Record<string, string> = {};
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }
  const response = await fetch(`${API_BASE}${withSession("/logs/download")}`, { headers });
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const match = disposition?.match(/filename="(.+)"/);
  const filename = match?.[1] ?? "conversation_log.json";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function getWebSocketUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL;
  const base = explicit ?? API_BASE.replace(/^http/, "ws") + "/ws";
  return `${base}?session=${_sessionId}`;
}
