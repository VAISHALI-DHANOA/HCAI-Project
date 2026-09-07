import type { PublicTurn, State } from "./types";

export function pendingHumanTurns(turns: PublicTurn[], pendingRequest: string): PublicTurn[] {
  if (!pendingRequest) return [];
  const pending = [...turns].reverse().find(
    (turn) => turn.speaker_id === "human" && turn.message === pendingRequest,
  );
  return pending ? [pending] : [];
}

export function acceptsSnapshot(current: State | null, incoming: State): boolean {
  if (!current) return true;
  if (incoming.revision < current.revision) return false;
  return incoming.revision !== current.revision || incoming.run_id === current.run_id;
}

export function sameRoster(a: State, b: State): boolean {
  return JSON.stringify(a.agents.filter((agent) => agent.role === "user"))
    === JSON.stringify(b.agents.filter((agent) => agent.role === "user"));
}
