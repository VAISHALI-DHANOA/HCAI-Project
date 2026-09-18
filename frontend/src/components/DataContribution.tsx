import type { PublicTurn, State } from "../types";
import { useEffect, useRef } from "react";
import { DataAgentAvatar } from "./DataAgentStrip";

export function DataContribution({ state, turn, active, pastTurns }: { state: State; turn: PublicTurn | null; active: boolean; pastTurns: PublicTurn[] }) {
  const speaker = state.agents.find((agent) => agent.id === turn?.speaker_id);
  const historyRef = useRef<HTMLDivElement>(null);
  const humanHistory = state.public_history.filter((past) => past.speaker_id === "human");
  // The current human message is already shown below; keep repeated questions.
  if (turn?.speaker_id === "human" && humanHistory[humanHistory.length - 1]?.message === turn.message) humanHistory.pop();
  useEffect(() => {
    if (historyRef.current) historyRef.current.scrollTop = historyRef.current.scrollHeight;
  }, [humanHistory.length]);
  return <div className="data-contribution center-stage__content" aria-label="Current contribution">
    {!!humanHistory.length && <div className="data-contribution__history" ref={historyRef}>
      {humanHistory.map((past, index) => <p className="center-stage__past-turn center-stage__past-turn--human" key={index}><strong>You: </strong>{past.message}</p>)}
    </div>}
    {turn ? <>
      {turn.speaker_id === "human" ? <div className="center-stage__speaker center-stage__speaker--human">
        <span className="center-stage__speaker-avatar center-stage__human-icon">You</span>
        <span className="center-stage__speaker-name">You</span>
      </div> : <div className="center-stage__speaker">{speaker && <DataAgentAvatar agent={speaker} moderatorStrategyId={state.moderator_strategy_id} />}<span className="center-stage__speaker-name">{speaker?.name ?? turn.speaker_id}</span><small>{active ? "Speaking" : "Last contribution"}</small></div>}
      <p className="center-stage__message" key={`${turn.speaker_id}-${pastTurns.length}-${turn.message}`}>{turn.message}</p>
    </> : <p className="data-contribution__empty">Ready for analysis. Contributions will appear here.</p>}
  </div>;
}
