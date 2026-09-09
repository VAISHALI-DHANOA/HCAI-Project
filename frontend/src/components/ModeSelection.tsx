import { useState } from "react";
import backgroundArtwork from "../../artwork/Background_mode.png";
import "./ModeSelection.css";

type Mode = "debate" | "data";

interface ModeSelectionProps {
  onBack: () => void;
  onSelect: (mode: Mode) => void;
  sessionCode: string;
}

const MODES: Record<Mode, { title: string; description: string; tags: string[] }> = {
  debate: { title: "DEBATE MODE", description: "Explore different perspectives in a moderated discussion.", tags: ["ROUND-BASED", "MODERATED"] },
  data: { title: "DATA ANALYSIS", description: "Explore a dataset together and compare interpretations.", tags: ["DATASET", "COLLABORATIVE"] },
};

function ArrowIcon({ direction }: { direction: "left" | "right" }) {
  return <svg viewBox="0 0 32 32" aria-hidden="true"><path d={direction === "left" ? "M18 7 9 16l9 9M10 16h14" : "m14 7 9 9-9 9m8-9H8"} /></svg>;
}

export function ModeSelection({ onBack, onSelect, sessionCode }: ModeSelectionProps) {
  const [selectedMode, setSelectedMode] = useState<Mode>("debate");
  const selected = MODES[selectedMode];
  const toggleMode = () => setSelectedMode((current) => current === "debate" ? "data" : "debate");

  return <main className={`mode-screen mode-screen--${selectedMode}`}>
    <img className="mode-screen__artwork" src={backgroundArtwork} alt="" aria-hidden="true" />
    <header className="mode-screen__topbar">
      <div className="mode-screen__nav">
        <button type="button" className="mode-brand" onClick={onBack} aria-label="The Arena, a multi-agent playground. Back to entry"><span className="mode-brand__mark" aria-hidden="true">A</span><span className="mode-brand__copy"><span className="mode-brand__name">THE ARENA</span><span className="mode-brand__tagline">A multi-agent playground</span></span></button>
        <button type="button" className="mode-back" onClick={onBack}><ArrowIcon direction="left" /> BACK</button>
      </div>
      <div className="mode-token" aria-label={`Session token ${sessionCode}`}><span>SESSION TOKEN</span><strong>{sessionCode}</strong><button type="button" onClick={() => navigator.clipboard?.writeText(sessionCode)}>COPY</button></div>
    </header>

    <section className="mode-screen__content" aria-live="polite">
      <div className="mode-screen__heading"><h1>CHOOSE YOUR PATH</h1><p>Choose how your team will work.</p></div>
      <div className="mode-selector">
        <button type="button" className="mode-selector__arrow" onClick={toggleMode} aria-label="Previous mode"><ArrowIcon direction="left" /></button>
        <article className="mode-choice">

          <h2>{selected.title}</h2><p>{selected.description}</p>
          <ul className="mode-choice__tags" aria-label="Mode features">{selected.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>
          <button type="button" className="mode-choice__cta" onClick={() => onSelect(selectedMode)}>CHOOSE THIS MODE <ArrowIcon direction="right" /></button>
        </article>
        <button type="button" className="mode-selector__arrow" onClick={toggleMode} aria-label="Next mode"><ArrowIcon direction="right" /></button>
      </div>
      <div className="mode-dots" aria-label="Select a mode">
        <button type="button" className={selectedMode === "debate" ? "is-active" : ""} onClick={() => setSelectedMode("debate")} aria-label="Debate Mode" aria-pressed={selectedMode === "debate"} />
        <button type="button" className={selectedMode === "data" ? "is-active" : ""} onClick={() => setSelectedMode("data")} aria-label="Data Analysis" aria-pressed={selectedMode === "data"} />
      </div>
    </section>

    <nav className="mode-progress" aria-label="Setup progress">
      {[["01", "CHOOSE MODE"], ["02", "TOPIC & TEAM"], ["03", "MODERATOR"], ["04", "REVIEW"]].map(([number, label], index) => <div className={index === 0 ? "mode-progress__step is-active" : "mode-progress__step"} key={number} aria-current={index === 0 ? "step" : undefined}><span>{number}</span><strong>{label}</strong></div>)}
    </nav>
  </main>;
}
