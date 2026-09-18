import { Fragment, useEffect, useMemo, useRef } from "react";
import type { Agent, DashboardVisual, PublicTurn } from "../types";
import { VisualCard } from "./VisualCard";

function agentAvatarUrl(agent: Agent): string {
  return `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`;
}

interface DashboardCanvasProps {
  visuals: DashboardVisual[];
  agents: Agent[];
  agentMap: Map<string, Agent>;
  currentTurn: PublicTurn | null;
  currentRound: number;
  completedRound: number;
}

export function DashboardCanvas({
  visuals,
  agents,
  agentMap,
  currentTurn,
  currentRound,
  completedRound,
}: DashboardCanvasProps) {
  const currentSpeakerId = currentTurn?.speaker_id ?? null;
  const containerRef = useRef<HTMLDivElement>(null);
  const activeCardRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = containerRef.current;
    const card = activeCardRef.current;
    if (container && card) container.scrollTo({ top: container.scrollTop + card.getBoundingClientRect().top - container.getBoundingClientRect().top - 12, behavior: "smooth" });
  }, [currentTurn, currentRound]);

  const mediatorIds = useMemo(() => {
    return new Set(agents.filter(a => a.role === "mediator").map(a => a.id));
  }, [agents]);

  const filteredVisuals = useMemo(() => {
    return visuals.filter(v => !mediatorIds.has(v.speakerId)).sort((a, b) => b.roundNumber - a.roundNumber);
  }, [visuals, mediatorIds]);

  const latestVisualPerAgent = useMemo(() => {
    const map = new Map<string, string>();
    for (const v of filteredVisuals) {
      if (!map.has(v.speakerId)) map.set(v.speakerId, v.id);
    }
    return map;
  }, [filteredVisuals]);

  if (filteredVisuals.length === 0) {
    return (
      <div className="dashboard-canvas">
        <div className="dashboard-canvas__empty">
          <p>No visual contributions have been generated for this discussion.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-canvas" ref={containerRef}>
      <div className="dashboard-canvas__grid">
        {filteredVisuals.map((vis, index) => {
          const isLatestForAgent = latestVisualPerAgent.get(vis.speakerId) === vis.id;
          const isSpeaking = currentSpeakerId === vis.speakerId && vis.roundNumber === currentRound && currentRound > completedRound;
          const agent = agentMap.get(vis.speakerId);

          return (
            <Fragment key={vis.id}>
            {(index === 0 || filteredVisuals[index - 1].roundNumber !== vis.roundNumber) && <h3 className="dashboard-round-heading">Round {vis.roundNumber} - {vis.roundNumber <= completedRound ? "Completed results" : "Current contributions"}</h3>}
            <div
              ref={isSpeaking ? activeCardRef : undefined}
              className={`dashboard-card${isSpeaking && isLatestForAgent ? " dashboard-card--active" : ""}`}
              style={{ "--agent-color": vis.agentColor } as React.CSSProperties}
            >
              {isLatestForAgent && agent && (
                <div className={`dashboard-card__agent${isSpeaking ? " dashboard-card__agent--speaking" : ""}`}>
                  <img
                    className="dashboard-card__avatar"
                    src={agentAvatarUrl(agent)}
                    alt={agent.name}
                    width={36}
                    height={36}
                  />
                  <span className="dashboard-card__agent-name">{agent.name}</span>
                </div>
              )}

              <VisualCard
                visual={vis.visual}
                agentColor={vis.agentColor}
                agentName={vis.agentName}
                size="large"
              />

              {isLatestForAgent && (
                <div className="dashboard-card__speech">
                  <p className="dashboard-card__message">{vis.message}</p>
                </div>
              )}

              <span className="dashboard-card__round-badge">R{vis.roundNumber} - {vis.roundNumber <= completedRound ? "Completed" : isSpeaking ? "Current contribution" : "In progress"}</span>
            </div>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
