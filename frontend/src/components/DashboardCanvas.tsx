import { useMemo } from "react";
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
  dashboardNarrative: string;
}

export function DashboardCanvas({
  visuals,
  agents,
  agentMap,
  currentTurn,
  dashboardNarrative,
}: DashboardCanvasProps) {
  const currentSpeakerId = currentTurn?.speaker_id ?? null;

  const mediatorIds = useMemo(() => {
    return new Set(agents.filter(a => a.role === "mediator").map(a => a.id));
  }, [agents]);

  const filteredVisuals = useMemo(() => {
    return visuals.filter(v => !mediatorIds.has(v.speakerId));
  }, [visuals, mediatorIds]);

  const latestVisualPerAgent = useMemo(() => {
    const map = new Map<string, string>();
    for (const v of filteredVisuals) {
      map.set(v.speakerId, v.id);
    }
    return map;
  }, [filteredVisuals]);

  if (filteredVisuals.length === 0 && !dashboardNarrative) {
    return (
      <div className="dashboard-canvas">
        <div className="dashboard-canvas__empty">
          <p>Dashboard is ready. Visuals will appear as agents create them.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-canvas">
      {dashboardNarrative && (
        <div className="dashboard-canvas__narrative">
          <h2 className="dashboard-canvas__narrative-title">{dashboardNarrative}</h2>
        </div>
      )}
      <div className="dashboard-canvas__grid">
        {filteredVisuals.map((vis) => {
          const isLatestForAgent = latestVisualPerAgent.get(vis.speakerId) === vis.id;
          const isSpeaking = currentSpeakerId === vis.speakerId;
          const agent = agentMap.get(vis.speakerId);

          return (
            <div
              key={vis.id}
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

              <span className="dashboard-card__round-badge">R{vis.roundNumber}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
