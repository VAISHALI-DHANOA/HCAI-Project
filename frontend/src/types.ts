export type Role = "user" | "mediator";

export interface Agent {
  id: string;
  name: string;
  persona_text: string;
  quirks: string[];
  stance: string;
  energy: number;
  role: Role;
  mbti_type?: string;
}

export interface DraftAgent {
  name: string;
  persona_text: string;
  energy: number;
  mbti_type: string;
}

export interface ChatMessage {
  role: "user" | "agent";
  content: string;
}

export type AppPhase = "setup" | "arena";

export interface VisualSpec {
  visual_type: "bar_chart" | "table" | "scatter" | "line_chart" | "stat_card" | "heatmap";
  title: string;
  data: any;
  description?: string;
}

export interface PublicTurn {
  speaker_id: string;
  message: string;
  visual?: VisualSpec | null;
}

export interface DatasetInfo {
  filename: string;
  shape: [number, number];
  columns: Array<{ name: string; dtype: string; null_count: number; null_pct: number }>;
  sample_rows: Record<string, any>[];
}

export interface Reaction {
  agent_id: string;
  emoji: string;
  micro_comment: string;
}

export interface RoundResult {
  round_number: number;
  speaker_ids: string[];
  turns: PublicTurn[];
  reactions: Reaction[];
  emergent_pattern: string;
  metrics: Metrics;
}

export interface Metrics {
  consensus_score: number;
  polarization_score: number;
  civility_score: number;
  detected_coalitions: string[];
}

export interface State {
  topic: string;
  round_number: number;
  agents: Agent[];
  public_history: PublicTurn[];
  reactions: Reaction[];
  world_state: Record<string, unknown>;
  dataset_summary?: string;
}

export interface WsRoundEvent {
  type: "round";
  round_result: RoundResult;
  metrics: Metrics;
  state_snapshot: State;
}

export interface WsTurnEvent {
  type: "turn";
  turn: PublicTurn;
  round_number: number;
}

export interface WsStateEvent {
  type: "state";
  state_snapshot: State;
}

export type WsEvent = WsRoundEvent | WsTurnEvent | WsStateEvent;
