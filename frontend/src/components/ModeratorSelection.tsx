import type { ModeratorStrategy } from "../types";
import type { CSSProperties } from "react";
import { getModeratorAvatar } from "../moderatorAvatars";
import { ArrowIcon, SetupProgress } from "./SetupChrome";
import "./ModeratorSelection.css";

const CARD_ACCENTS: Record<string, string> = {
  consensus: "#fa7778",
  facilitator: "#79c9ad",
  devils_advocate: "#efa65d",
};

export function ModeratorSelection({ strategies, selectedId, saving, launching, onSelect, onBack, onEnter }: {
  strategies: ModeratorStrategy[];
  selectedId: string;
  saving: boolean;
  launching: boolean;
  onSelect: (strategyId: string) => void;
  onBack: () => void;
  onEnter: () => void;
}) {
  return <main className="moderator-screen">
    <section className="moderator-intro setup-pixel-panel">
      <div className="moderator-intro__step"><span>SETUP STEP</span><strong>MODERATOR<br />SELECTION</strong></div>
      <div className="moderator-intro__copy"><h1>Choose a moderator for your arena</h1><p>The moderator guides the conversation, manages dynamics, and helps the team reach valuable outcomes.</p></div>
    </section>

    <div className="moderator-grid" role="radiogroup" aria-label="Choose a moderator">
      {strategies.map((strategy) => {
        const selected = strategy.id === selectedId;
        const traits = strategy.opening_rules.slice(0, 3);
        return <button
          type="button"
          role="radio"
          aria-checked={selected}
          className={`moderator-card setup-pixel-panel${selected ? " is-selected" : ""}`}
          style={{ "--moderator-accent": CARD_ACCENTS[strategy.id] ?? "#fa7778" } as CSSProperties}
          key={strategy.id}
          disabled={saving || launching}
          onClick={() => onSelect(strategy.id)}
        >
          {selected && <span className="moderator-card__selected">SELECTED</span>}
          <div className="moderator-card__portrait"><img src={getModeratorAvatar(strategy.id)} alt={`${strategy.name} moderator`} /></div>
          <h2>{strategy.name}</h2>
          <p>{strategy.description}</p>
          <ul>{traits.map((trait) => <li key={trait}>{trait}</li>)}</ul>
        </button>;
      })}
    </div>

    <div className="moderator-actions">
      <button type="button" className="moderator-actions__enter" onClick={onEnter} disabled={!selectedId || saving || launching}>{launching ? "ENTERING..." : "ENTER THE ARENA"}<ArrowIcon direction="right" /></button>
    </div>
    <SetupProgress activeStep={2} />
  </main>;
}
