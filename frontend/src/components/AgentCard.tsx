import type { ReactNode } from "react";
import type { Agent, DraftAgent, PersonalityCatalog } from "../types";
import { AgentStats } from "./AgentStats";

export function AgentCard({ agent, catalog, children }: {
  agent: Agent | DraftAgent;
  catalog: PersonalityCatalog;
  children: ReactNode;
}) {
  const presetName = agent.personality
    ? catalog.presets.find((preset) => preset.id === agent.personality?.preset_id)?.name
    : undefined;

  return <div className="draft-agent-card">
    <img className="draft-agent-card__avatar" src={`https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`} alt={agent.name} width={48} height={48} />
    <div className="draft-agent-card__info">
      <div className="draft-agent-card__header">
        <span className="draft-agent-card__name">{agent.name}</span>
        {presetName && <span className="personality-badge personality-badge--small">{presetName}</span>}
      </div>
      <p className="draft-agent-card__persona">{agent.persona_text}</p>
    </div>
    <AgentStats personality={agent.personality} catalog={catalog} />
    <div className="draft-agent-card__actions">{children}</div>
  </div>;
}
