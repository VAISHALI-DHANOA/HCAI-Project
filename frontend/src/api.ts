import type { DatasetInfo, State } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

let _adminKey: string | null = null;
export function setAdminKey(key: string | null) {
  _adminKey = key;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
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

export async function addAgent(name: string, persona_text: string, energy: number): Promise<{ state: State }> {
  return request<{ state: State }>("/agents", {
    method: "POST",
    body: JSON.stringify({
      user_agents: [{ name, persona_text, energy }]
    })
  });
}

export async function runRounds(rounds: number): Promise<{ state: State }> {
  return request<{ state: State }>("/run", {
    method: "POST",
    body: JSON.stringify({ rounds })
  });
}

export async function reset(topic?: string): Promise<{ state: State }> {
  return request<{ state: State }>("/reset", {
    method: "POST",
    body: JSON.stringify({ topic })
  });
}

export async function loadDemo(): Promise<{ state: State }> {
  return request<{ state: State }>("/demo", { method: "POST" });
}

export async function uploadDataset(file: File): Promise<{ parsed: DatasetInfo; state: State }> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }

  const response = await fetch(`${API_BASE}/upload-dataset`, {
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

export async function loadDataDemo(): Promise<{ state: State; parsed?: DatasetInfo }> {
  return request<{ state: State; parsed?: DatasetInfo }>("/demo-data", { method: "POST" });
}

export async function addAgentsWithMBTI(
  agents: Array<{ name: string; persona_text: string; energy: number; mbti_type: string }>
): Promise<{ state: State }> {
  return request<{ state: State }>("/agents", {
    method: "POST",
    body: JSON.stringify({ user_agents: agents }),
  });
}

export async function testChat(
  agent_name: string,
  agent_persona: string,
  mbti_type: string,
  messages: Array<{ role: string; content: string }>,
  user_message: string,
): Promise<{ reply: string }> {
  return request<{ reply: string }>("/chat", {
    method: "POST",
    body: JSON.stringify({ agent_name, agent_persona, mbti_type, messages, user_message }),
  });
}

export async function getTTSAudio(text: string, voice: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice }),
  });
  if (!response.ok) throw new Error(`TTS failed: ${response.status}`);
  return response.blob();
}

export async function downloadLogs(): Promise<void> {
  const headers: Record<string, string> = {};
  if (_adminKey) {
    headers["X-Admin-Key"] = _adminKey;
  }
  const response = await fetch(`${API_BASE}/logs/download`, { headers });
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
  if (explicit) return explicit;
  return API_BASE.replace(/^http/, "ws") + "/ws";
}
