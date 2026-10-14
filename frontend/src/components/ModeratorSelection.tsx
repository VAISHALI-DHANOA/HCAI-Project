import type { ModeratorStrategy } from "../types";
import type { CSSProperties } from "react";
import { getModeratorAvatar } from "../moderatorAvatars";
import { ArrowIcon, SetupProgress } from "./SetupChrome";
import "./ModeratorSelection.css";

const CARD_ACCENTS: Record<string, string> = {
  consensus: "var(--color-primary)",
  facilitator: "var(--color-metric-consensus)",
  devils_advocate: "var(--color-mediator)",
};

const CARD_COPY: Record<string, { description: string; bullets: string[] }> = {
  consensus: {
    description: "Seeks areas of agreement while keeping unresolved disagreements visible.",
    bullets: [
      "Identify genuine common ground without forcing agreement.",
      "Clarify which differences remain unresolved.",
      "Distinguish tentative agreement from settled conclusions.",
    ],
  },
  facilitator: {
    description: "Keeps different perspectives visible and encourages balanced participation.",
    bullets: [
      "Keep different perspectives visible throughout the discussion.",
      "Encourage contributions from less represented viewpoints.",
      "Reopen the discussion when the group becomes too narrow or repetitive.",
    ],
  },
  devils_advocate: {
    description: "Challenges emerging agreement by testing assumptions, evidence, and alternative explanations.",
    bullets: [
      "Challenge emerging consensus when it appears under-examined.",
      "Test assumptions, evidence, and reasoning.",
      "Introduce plausible counterarguments or alternative framings.",
    ],
  },
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
        const copy = CARD_COPY[strategy.id];
        const traits = copy?.bullets ?? strategy.opening_rules.slice(0, 3);
        return <button
          type="button"
          role="radio"
          aria-checked={selected}
          className={`moderator-card setup-pixel-panel${selected ? " is-selected" : ""}`}
          style={{ "--moderator-accent": CARD_ACCENTS[strategy.id] ?? "var(--color-primary)" } as CSSProperties}
          key={strategy.id}
          disabled={saving || launching}
          onClick={() => onSelect(strategy.id)}
        >
          {selected && <span className="moderator-card__selected">SELECTED</span>}
          <div className="moderator-card__portrait"><img src={getModeratorAvatar(strategy.id)} alt={`${strategy.name} moderator`} /></div>
          <h2>{strategy.name}</h2>
          <p>{copy?.description ?? strategy.description}</p>
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
