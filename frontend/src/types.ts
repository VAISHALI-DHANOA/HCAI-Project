export type Role = "user" | "mediator";

export interface Agent {
  id: string;
  name: string;
  persona_text: string;
  quirks: string[];
  stance: string;
  energy: number;
  role: Role;
  personality?: AgentPersonality | null;
}

export interface DraftAgent {
  id?: string;
  name: string;
  persona_text: string;
  energy: number;
  personality: AgentPersonality;
}

export interface OceanTraits {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
}

export interface AgentPersonality {
  preset_id: string;
  role_name: string;
  role_goal: string;
  ocean: OceanTraits;
  behavioral_rules: string[];
  custom_instructions: string;
  scale_version: string;
  preset_version: string;
  prompt_mapping_version: string;
}

export interface PersonalityPreset {
  id: string;
  name: string;
  description: string;
  role_goal: string;
  ocean: OceanTraits;
  behavioral_rules: string[];
  personality: AgentPersonality;
}

export interface PersonalityCatalog {
  presets: PersonalityPreset[];
  default_preset_id: string;
  traits: Array<{ key: keyof OceanTraits; label: string }>;
  scale: { min: number; max: number; mid: number; version: string };
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

export interface CellHighlight {
  row_start: number;
  row_end: number;
  columns: string[];
  color: string;
  agent_id: string;
}

export interface CellAnnotation {
  row: number;
  column: string;
  text: string;
  agent_id: string;
}

export interface TableAction {
  navigate_to: { row: number; column: string };
  highlights: CellHighlight[];
  annotations: CellAnnotation[];
}

export interface PublicTurn {
  speaker_id: string;
  message: string;
  visual?: VisualSpec | null;
  table_action?: TableAction | null;
  generation?: GenerationMetadata | null;
}

export interface GenerationMetadata {
  source: "llm" | "fallback";
  operation: "discussion" | "summary" | "chat";
  model: string;
  max_tokens: number;
  temperature: number;
  timeout_seconds: number;
  error_type: string | null;
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
  consensus_score: number | null;
  polarization_score: number | null;
  civility_score: number | null;
  detected_coalitions: string[];
  evaluation?: {
    status: "available" | "insufficient_data";
    excluded_fallback_turns: number;
    eligible_participant_count: number;
  };
}

export interface State {
  human_request: string;
  run_id: string;
  revision: number;
  topic: string;
  round_number: number;
  agents: Agent[];
  public_history: PublicTurn[];
  reactions: Reaction[];
  rounds?: RoundResult[];
  world_state: Record<string, unknown>;
  dataset_summary?: string;
  dataset_columns?: string[];
  moderator_strategy_id?: string;
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
  run_id: string;
}

export interface WsStateEvent {
  type: "state";
  state_snapshot: State;
  reset_playback?: boolean;
}

export type WsEvent = WsRoundEvent | WsTurnEvent | WsStateEvent;

export interface DashboardVisual {
  id: string;
  roundNumber: number;
  speakerId: string;
  agentName: string;
  agentColor: string;
  visual: VisualSpec;
  message: string;
}

export interface ModeratorStrategy {
  id: string;
  name: string;
  description: string;
  opening_rules: string[];
  summary_rules: string[];
  summary_request: string;
  version: string;
}
