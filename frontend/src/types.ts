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

export interface PublicTurn {
  speaker_id: string;
  message: string;
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
}

export interface WsRoundEvent {
  type: "round";
  round_result: RoundResult;
  metrics: Metrics;
  state_snapshot: State;
}

export interface WsStateEvent {
  type: "state";
  state_snapshot: State;
}

export type WsEvent = WsRoundEvent | WsStateEvent;
