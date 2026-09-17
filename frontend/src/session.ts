import type { PublicTurn, State } from "./types";

export function pendingHumanTurns(turns: PublicTurn[], pendingRequest: string): PublicTurn[] {
  if (!pendingRequest) return [];
  const humanTurns = turns.filter((turn) => turn.speaker_id === "human");
  for (let start = humanTurns.length - 1; start >= 0; start--) {
    const pending = humanTurns.slice(start);
    if (pending.map((turn) => turn.message).join("\n") === pendingRequest) return pending;
  }
  return [];
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

// Only additions can be merged without overwriting local edits or removals.
export function rosterAdditions(base: State, incoming: State) {
  if (base.run_id !== incoming.run_id) return null;
  const existingIds = new Set(base.agents.filter((agent) => agent.role === "user").map((agent) => agent.id));
  if (!sameRoster(base, { ...incoming, agents: incoming.agents.filter((agent) => existingIds.has(agent.id)) })) return null;
  return incoming.agents.filter((agent) => agent.role === "user" && !existingIds.has(agent.id));
}
