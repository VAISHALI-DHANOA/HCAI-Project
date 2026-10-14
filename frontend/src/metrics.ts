import type { Agent, ConsensusRoundResult, RoundResult } from "./types";

export type MetricAvailability = "unavailable" | "pending" | "available" | "error";

export interface MetricAgentValue {
  agentId: string;
  agentLabel: string;
  formattedValue?: string;
}

export interface MetricDetail {
  label: string;
  value: string;
}

export interface MetricDisplayData {
  id: string;
  label: string;
  icon: string;
  status: MetricAvailability;
  formattedValue?: string;
  explanation?: string;
  agentValues?: MetricAgentValue[];
  details?: MetricDetail[];
  highlights?: MetricDetail[];
  progress?: number;
  steps?: string[];
  activeStep?: number;
  roundNumber?: number;
}

const METRIC_DEFINITIONS = [
  { id: "consensus", label: "Consensus", icon: "◎" },
  { id: "personality-stability", label: "Personality Stability", icon: "◆" },
  { id: "conversation-convergence", label: "Conversation Convergence", icon: "⇢" },
] as const;

function metricDefinition(id: typeof METRIC_DEFINITIONS[number]["id"]) {
  return METRIC_DEFINITIONS.find((definition) => definition.id === id)!;
}

const createUnavailableMetric = (
  definition: typeof METRIC_DEFINITIONS[number],
): MetricDisplayData => ({ ...definition, status: "unavailable" });

const RESULT_LABELS = {
  insufficient_evidence: "Insufficient evidence",
  unavailable: "Unavailable",
  error: "Error",
} as const;

const CONSENSUS_LABELS = ["No consensus", "Limited", "Partial", "Broad"];

function hasScore(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function statusFromResult(status: string, hasValue: boolean): MetricAvailability {
  if (hasValue) return "available";
  return status === "error" ? "error" : "unavailable";
}

function personalityMetric(round: RoundResult | undefined, agents: Agent[]): MetricDisplayData {
  const stability = round?.thesis_metrics?.personality_stability?.round;
  const base = metricDefinition("personality-stability");
  if (!stability) return createUnavailableMetric(base);
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]));
  const results = stability.per_agent ?? [];
  const hasErrors = results.some((result) => result.status === "error");
  const available = hasScore(stability.mean_score);
  return {
    ...base,
    status: available ? "available" : hasErrors ? "error" : "unavailable",
    formattedValue: available ? `${stability.mean_score!.toFixed(2)} / 4` : undefined,
    progress: available ? stability.mean_score! / 4 : undefined,
    roundNumber: round?.round_number,
    explanation: available
      ? `Profile consistency for ${stability.evaluated_agent_count} agent${stability.evaluated_agent_count === 1 ? "" : "s"}; not a measure of analytical accuracy.`
      : stability.insufficient_evidence_agent_count > 0
        ? "There is not enough observable behavior for a score yet."
        : hasErrors ? "The judge evaluation failed." : "No evaluation is available.",
    agentValues: results.map((result) => ({
      agentId: result.agent_id,
      agentLabel: agentNames.get(result.agent_id) ?? result.agent_id,
      formattedValue: result.status === "available" && hasScore(result.score)
        ? `${result.score} / 4`
        : result.status === "error" ? result.reason
          : RESULT_LABELS[result.status as keyof typeof RESULT_LABELS],
    })),
  };
}

function convergenceMetric(round: RoundResult | undefined): MetricDisplayData {
  const convergence = round?.thesis_metrics?.conversation_convergence?.round;
  const base = metricDefinition("conversation-convergence");
  if (!convergence) return createUnavailableMetric(base);
  const available = convergence.status === "available" && hasScore(convergence.round_score);
  return {
    ...base,
    status: statusFromResult(convergence.status, available),
    formattedValue: available ? `${Math.round(convergence.round_score! * 100)}%` : undefined,
    progress: available ? convergence.round_score! : undefined,
    roundNumber: convergence.round_number,
    explanation: available
      ? "Mean pairwise lexical overlap between participant contributions."
      : convergence.reason,
  };
}

function consensusMetric(result: ConsensusRoundResult | undefined): MetricDisplayData {
  const base = metricDefinition("consensus");
  if (!result) return createUnavailableMetric(base);
  const available = result.status === "available" && hasScore(result.score);
  const highlights: MetricDetail[] = [];
  if (available) {
    highlights.push({
      label: "Shared point(s)",
      value: result.shared_conclusion ?? "No shared point identified.",
    });
    highlights.push({
      label: "Open disagreement",
      value: result.unresolved_disagreement ?? "None identified.",
    });
  }
  return {
    ...base,
    status: statusFromResult(result.status, available),
    formattedValue: available ? CONSENSUS_LABELS[result.score!] : undefined,
    steps: CONSENSUS_LABELS,
    activeStep: available ? result.score! : undefined,
    roundNumber: result.round_number,
    explanation: result.reason,
    highlights,
  };
}

function latestRoundWith(
  rounds: RoundResult[], predicate: (round: RoundResult) => boolean,
): RoundResult | undefined {
  for (let index = rounds.length - 1; index >= 0; index -= 1) {
    if (predicate(rounds[index])) return rounds[index];
  }
  return undefined;
}

export function metricsForRound(
  round: RoundResult | undefined, agents: Agent[],
): MetricDisplayData[] {
  return [
    consensusMetric(round?.thesis_metrics?.consensus?.round),
    personalityMetric(round, agents),
    convergenceMetric(round),
  ];
}

export function metricsForEnd(
  rounds: RoundResult[], agents: Agent[],
): MetricDisplayData[] {
  const personalityRound = latestRoundWith(
    rounds, (round) => hasScore(round.thesis_metrics?.personality_stability?.round?.mean_score),
  );
  const convergenceRound = latestRoundWith(
    rounds,
    (round) => {
      const result = round.thesis_metrics?.conversation_convergence?.round;
      return result?.status === "available" && hasScore(result.round_score);
    },
  );
  const consensusRound = latestRoundWith(
    rounds, (round) => {
      const result = round.thesis_metrics?.consensus?.round;
      return result?.status === "available" && hasScore(result.score);
    },
  );
  return [
    consensusMetric(consensusRound?.thesis_metrics?.consensus?.round),
    personalityMetric(personalityRound, agents),
    convergenceMetric(convergenceRound),
  ];
}
