import { useCallback, useEffect, useMemo, useRef } from "react";
import type { Agent, CellAnnotation, CellHighlight, PublicTurn, VisualSpec } from "../types";
import { VisualCard } from "./VisualCard";

const AGENT_COLORS = [
  "#38bdf8", "#a78bfa", "#fb923c", "#4ade80", "#f87171",
  "#fbbf24", "#22d3ee", "#e879f9", "#34d399", "#f472b6",
];

function agentColor(agent: Agent): string {
  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return AGENT_COLORS[seed % AGENT_COLORS.length];
}

function agentAvatarUrl(agent: Agent): string {
  return `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`;
}

interface AgentPosition {
  agentId: string;
  row: number;
  column: string;
}

interface ArenaTableProps {
  rows: Record<string, any>[];
  columns: string[];
  agents: Agent[];
  currentTurn: PublicTurn | null;
  pastTurns: PublicTurn[];
  accumulatedHighlights: CellHighlight[];
  accumulatedAnnotations: CellAnnotation[];
  agentPositions: Map<string, AgentPosition>;
  agentMap: Map<string, Agent>;
}

export function ArenaTable({
  rows,
  columns,
  agents,
  currentTurn,
  pastTurns,
  accumulatedHighlights,
  accumulatedAnnotations,
  agentPositions,
  agentMap,
}: ArenaTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const agentRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Build highlight map: "row-col" -> color
  const highlightMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const h of accumulatedHighlights) {
      for (let r = h.row_start; r <= h.row_end; r++) {
        for (const col of h.columns) {
          const key = `${r}-${col}`;
          // Later highlights overwrite earlier ones
          map.set(key, h.color);
        }
      }
    }
    return map;
  }, [accumulatedHighlights]);

  // Build annotation map: "row-col" -> annotation[]
  const annotationMap = useMemo(() => {
    const map = new Map<string, CellAnnotation[]>();
    for (const a of accumulatedAnnotations) {
      const key = `${a.row}-${a.column}`;
      const existing = map.get(key) ?? [];
      existing.push(a);
      map.set(key, existing);
    }
    return map;
  }, [accumulatedAnnotations]);

  // Compute pixel positions for agents based on their table positions
  const getAgentPixelPosition = useCallback((agentId: string): { top: number; left: number } | null => {
    const pos = agentPositions.get(agentId);
    const container = containerRef.current;
    if (!pos || !container) return null;

    const cell = container.querySelector(
      `td[data-row="${pos.row}"][data-col="${pos.column}"]`
    ) as HTMLElement | null;
    if (!cell) return null;

    const containerRect = container.getBoundingClientRect();
    const cellRect = cell.getBoundingClientRect();

    return {
      top: cellRect.top - containerRect.top + container.scrollTop,
      left: cellRect.left - containerRect.left + container.scrollLeft + cellRect.width / 2,
    };
  }, [agentPositions]);

  // Auto-scroll to the current speaker's cell
  useEffect(() => {
    if (!currentTurn || currentTurn.speaker_id === "human") return;
    const pos = agentPositions.get(currentTurn.speaker_id);
    const container = containerRef.current;
    if (!pos || !container) return;

    const cell = container.querySelector(
      `td[data-row="${pos.row}"][data-col="${pos.column}"]`
    ) as HTMLElement | null;
    if (cell) {
      cell.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    }
  }, [currentTurn, agentPositions]);

  // Default agent positions: spread evenly across header columns
  const defaultPositions = useMemo(() => {
    const positions = new Map<string, { row: number; column: string }>();
    agents.forEach((agent, i) => {
      const colIdx = Math.floor((i / agents.length) * columns.length);
      positions.set(agent.id, { row: 0, column: columns[colIdx] ?? columns[0] });
    });
    return positions;
  }, [agents, columns]);

  const currentSpeakerId = currentTurn?.speaker_id ?? null;

  return (
    <div className="arena-table-container" ref={containerRef}>
      <table className="arena-table">
        <thead>
          <tr>
            <th className="arena-table__row-index">#</th>
            {columns.map((col) => (
              <th key={col} className="arena-table__header-cell">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              <td className="arena-table__row-index">{ri}</td>
              {columns.map((col) => {
                const key = `${ri}-${col}`;
                const bgColor = highlightMap.get(key);
                const annotations = annotationMap.get(key);
                return (
                  <td
                    key={col}
                    data-row={ri}
                    data-col={col}
                    className="arena-table__cell"
                    style={bgColor ? { backgroundColor: bgColor } : undefined}
                  >
                    {String(row[col] ?? "")}
                    {annotations && annotations.length > 0 && (
                      <span className="arena-table__annotation-marker" title={annotations.map(a => a.text).join(" | ")}>
                        <span className="arena-table__annotation-tooltip">
                          {annotations.map((a, ai) => {
                            const annotAgent = agentMap.get(a.agent_id);
                            return (
                              <span key={ai} className="arena-table__annotation-line">
                                <strong>{annotAgent?.name ?? "?"}: </strong>{a.text}
                              </span>
                            );
                          })}
                        </span>
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Agent overlay layer */}
      {agents.map((agent) => {
        const pos = agentPositions.get(agent.id) ?? defaultPositions.get(agent.id);
        const isSpeaking = currentSpeakerId === agent.id;
        const isDimmed = currentSpeakerId !== null && !isSpeaking;
        const color = agentColor(agent);
        const pixelPos = getAgentPixelPosition(agent.id);

        // Find the cell for positioning
        const targetRow = pos?.row ?? 0;
        const targetCol = pos?.column ?? columns[0];

        return (
          <AgentOverlay
            key={agent.id}
            agent={agent}
            isSpeaking={isSpeaking}
            isDimmed={isDimmed}
            color={color}
            targetRow={targetRow}
            targetCol={targetCol}
            containerRef={containerRef}
            currentTurn={isSpeaking ? currentTurn : null}
            pastTurns={isSpeaking ? pastTurns : []}
            agentMap={agentMap}
          />
        );
      })}
    </div>
  );
}

interface AgentOverlayProps {
  agent: Agent;
  isSpeaking: boolean;
  isDimmed: boolean;
  color: string;
  targetRow: number;
  targetCol: string;
  containerRef: React.RefObject<HTMLDivElement | null>;
  currentTurn: PublicTurn | null;
  pastTurns: PublicTurn[];
  agentMap: Map<string, Agent>;
}

function AgentOverlay({
  agent,
  isSpeaking,
  isDimmed,
  color,
  targetRow,
  targetCol,
  containerRef,
  currentTurn,
  pastTurns,
  agentMap,
}: AgentOverlayProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Position the overlay based on the target cell
  useEffect(() => {
    const container = containerRef.current;
    const overlay = overlayRef.current;
    if (!container || !overlay) return;

    const updatePosition = () => {
      const cell = container.querySelector(
        `td[data-row="${targetRow}"][data-col="${targetCol}"]`
      ) as HTMLElement | null;
      if (!cell) return;

      const containerRect = container.getBoundingClientRect();
      const cellRect = cell.getBoundingClientRect();

      const top = cellRect.top - containerRect.top + container.scrollTop;
      const left = cellRect.left - containerRect.left + container.scrollLeft + cellRect.width / 2;

      overlay.style.top = `${top}px`;
      overlay.style.left = `${left}px`;
    };

    updatePosition();

    // Also update on scroll
    container.addEventListener("scroll", updatePosition);
    return () => container.removeEventListener("scroll", updatePosition);
  }, [targetRow, targetCol, containerRef]);

  return (
    <div
      ref={overlayRef}
      className={`arena-table-agent${isSpeaking ? " arena-table-agent--speaking" : ""}${isDimmed ? " arena-table-agent--dimmed" : ""}`}
      style={{ "--agent-color": color } as React.CSSProperties}
    >
      <img
        className="arena-table-agent__avatar"
        src={agentAvatarUrl(agent)}
        alt={agent.name}
        width={isSpeaking ? 48 : 36}
        height={isSpeaking ? 48 : 36}
      />
      {agent.role === "mediator" && <span className="arena-table-agent__role-badge">MOD</span>}
      <span className="arena-table-agent__name">{agent.name}</span>

      {isSpeaking && currentTurn && (
        <div className="speech-bubble">
          {pastTurns.length > 0 && (
            <div className="speech-bubble__history">
              {pastTurns.map((turn, i) => {
                const speaker = agentMap.get(turn.speaker_id);
                const isHuman = turn.speaker_id === "human";
                return (
                  <p className="speech-bubble__past" key={i}>
                    <strong>{isHuman ? "You" : (speaker?.name ?? "?")}: </strong>
                    {turn.message}
                  </p>
                );
              })}
            </div>
          )}
          <p className="speech-bubble__message">{currentTurn.message}</p>
          {currentTurn.visual && (
            <div className="speech-bubble__visual">
              <VisualCard
                visual={currentTurn.visual}
                agentColor={color}
                agentName={agent.name}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
