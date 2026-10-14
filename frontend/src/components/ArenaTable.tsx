import { useEffect, useMemo, useRef } from "react";
import type { Agent, CellAnnotation, CellHighlight, PublicTurn } from "../types";
import { DataAgentAvatar, type AgentFocus, type TablePosition } from "./DataAgentStrip";

interface ArenaTableProps {
  rows: Record<string, unknown>[];
  columns: string[];
  agents: Agent[];
  currentTurn: PublicTurn | null;
  focus: AgentFocus | null;
  accumulatedHighlights: CellHighlight[];
  accumulatedAnnotations: CellAnnotation[];
  agentPositions: Map<string, TablePosition>;
  agentMap: Map<string, Agent>;
}

export function ArenaTable({ rows, columns, agents, currentTurn, focus, accumulatedHighlights,
  accumulatedAnnotations, agentPositions, agentMap }: ArenaTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const agentsByCell = useMemo(() => {
    const cells = new Map<string, Agent[]>();
    for (const agent of agents) {
      const pos = agentPositions.get(agent.id);
      if (!pos) continue;
      const key = JSON.stringify([pos.row, pos.column]);
      cells.set(key, [...(cells.get(key) ?? []), agent]);
    }
    return cells;
  }, [agents, agentPositions]);
  const highlights = useMemo(() => {
    const cells = new Map<string, string>();
    for (const h of accumulatedHighlights) {
      for (let row = Math.max(0, h.row_start); row <= Math.min(rows.length - 1, h.row_end); row++) {
        for (const column of h.columns) cells.set(JSON.stringify([row, column]), h.color);
      }
    }
    return cells;
  }, [accumulatedHighlights, rows.length]);
  const annotations = useMemo(() => {
    const cells = new Map<string, CellAnnotation[]>();
    for (const annotation of accumulatedAnnotations) {
      const key = JSON.stringify([annotation.row, annotation.column]);
      cells.set(key, [...(cells.get(key) ?? []), annotation]);
    }
    return cells;
  }, [accumulatedAnnotations]);

  function locate(agentId: string) {
    const container = containerRef.current;
    const pos = agentPositions.get(agentId);
    if (!container || !pos) return;
    const cell = Array.from(container.querySelectorAll<HTMLElement>('td[data-row="' + pos.row + '"]'))
      .find((item) => item.dataset.col === pos.column);
    if (!cell) return;
    const bounds = container.getBoundingClientRect();
    const target = cell.getBoundingClientRect();
    container.scrollTo({
      top: container.scrollTop + target.top - bounds.top - (container.clientHeight - target.height) / 2,
      left: container.scrollLeft + target.left - bounds.left - (container.clientWidth - target.width) / 2,
      behavior: "smooth",
    });
    cell.animate([{ outline: "3px solid #fbbf24", outlineOffset: "-3px" }, { outline: "3px solid transparent", outlineOffset: "-3px" }], { duration: 1800 });
  }
  useEffect(() => {
    if (currentTurn && currentTurn.speaker_id !== "human") locate(currentTurn.speaker_id);
  }, [currentTurn, agentPositions]);
  useEffect(() => {
    if (focus) locate(focus.agentId);
  }, [focus]);

  return <div className="arena-table-container" ref={containerRef} tabIndex={0} aria-label="Dataset table">
    <table className="arena-table">
      <thead><tr><th className="arena-table__row-index">#</th>
        {columns.map((column) => <th key={column} className="arena-table__header-cell">{column}</th>)}
      </tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>
        <td className="arena-table__row-index">{index + 1}</td>
        {columns.map((column) => {
          const key = JSON.stringify([index, column]);
          const notes = annotations.get(key) ?? [];
          const occupants = agentsByCell.get(key) ?? [];
          return <td key={column} data-row={index} data-col={column} className="arena-table__cell"
            style={{ backgroundColor: highlights.get(key) }}>
            <span className="arena-table__value" title={String(row[column] ?? "")}>{String(row[column] ?? "")}</span>
            {!!notes.length && <span className="arena-table__annotation-marker" tabIndex={0} aria-label="Cell annotations">
              <span className="arena-table__annotation-tooltip" role="tooltip">
                {notes.map((note, noteIndex) => <span key={noteIndex} className="arena-table__annotation-line">
                  <strong>{agentMap.get(note.agent_id)?.name ?? "Agent"}: </strong>{note.text}
                </span>)}
              </span>
            </span>}
            {!!occupants.length && <div className="arena-table__agents">
              {occupants.map((agent) => <span key={agent.id} className={currentTurn?.speaker_id === agent.id ? "is-speaking" : ""}><DataAgentAvatar agent={agent} /></span>)}
            </div>}
          </td>;
        })}
      </tr>)}</tbody>
    </table>
    {!rows.length && <p className="chat-log__empty">No rows in this dataset preview.</p>}
  </div>;
}
