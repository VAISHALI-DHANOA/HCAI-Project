import { useEffect, useRef } from "react";
import type { Agent } from "../types";
import { getModeratorAvatar } from "../moderatorAvatars";

export interface TablePosition { agentId: string; row: number; column: string }
export interface AgentFocus { agentId: string; request: number }

export function DataAgentAvatar({ agent, moderatorStrategyId }: { agent: Agent; moderatorStrategyId?: string }) {
  return <span className="data-agent-avatar" title={agent.name}>
    <span aria-hidden="true">{agent.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("")}</span>
    <img src={agent.role === "mediator" ? getModeratorAvatar(moderatorStrategyId) : `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`} alt={agent.name} width={28} height={28} />
  </span>;
}

export function DataAgentStrip({ agents, positions, currentSpeakerId, onLocate, moderatorStrategyId }: {
  agents: Agent[]; positions: Map<string, TablePosition>; currentSpeakerId: string | null;
  onLocate: (agentId: string) => void;
  moderatorStrategyId?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const speakerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const list = listRef.current;
    const speaker = speakerRef.current;
    if (!list || !speaker) return;
    const bounds = list.getBoundingClientRect();
    const target = speaker.getBoundingClientRect();
    if (target.top < bounds.top || target.bottom > bounds.bottom) {
      list.scrollTo({ top: list.scrollTop + target.top - bounds.top - (list.clientHeight - target.height) / 2, behavior: "smooth" });
    }
  }, [currentSpeakerId, agents]);
  return <div className="data-agent-list">
    <div className={`data-agent-strip${agents.length > 6 ? " data-agent-strip--scrollable" : ""}`} ref={listRef} aria-label="Analysis agents" tabIndex={agents.length > 6 ? 0 : undefined}>
    {agents.map((agent) => {
      const position = positions.get(agent.id);
      return <button type="button" key={agent.id}
        ref={currentSpeakerId === agent.id ? speakerRef : undefined}
        className={`data-agent-strip__agent${currentSpeakerId === agent.id ? " is-speaking" : ""}`}
        aria-label={position ? `Locate ${agent.name} in dataset` : `${agent.name}: no table position yet`}
        disabled={!position} onClick={() => onLocate(agent.id)}
        title={`${agent.name}${currentSpeakerId === agent.id ? " — Speaking" : ""}: ${position ? position.column : "No table position yet"}`}>
        <DataAgentAvatar agent={agent} moderatorStrategyId={moderatorStrategyId} />
        <span><small>{position ? position.column : agent.role === "mediator" ? "Moderator" : "Waiting"}</small></span>
      </button>;
    })}
    </div>
    {agents.length > 6 && <small className="data-agent-list__hint">{agents.length} agents · Scroll to see all ↕</small>}
  </div>;
}
