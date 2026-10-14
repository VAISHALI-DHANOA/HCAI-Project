import { ArrowIcon, SetupHeader, SetupProgress } from "./SetupChrome";
import { useState } from "react";
import backgroundArtwork from "../../artwork/Background_mode.png";
import "./ModeSelection.css";

type Mode = "debate" | "data";

interface ModeSelectionProps {
  initialMode: Mode;
  onBack: () => void;
  onSelect: (mode: Mode) => void;
  sessionCode: string;
  busy?: boolean;
  error?: string;
}

const MODES: Record<Mode, { title: string; description: string; tags: string[] }> = {
  debate: { title: "DEBATE MODE", description: "Explore different perspectives in a moderated discussion.", tags: ["ROUND-BASED", "MODERATED"] },
  data: { title: "DATA ANALYSIS", description: "Explore a dataset together and compare interpretations.", tags: ["DATASET", "COLLABORATIVE"] },
};

export function ModeSelection({ initialMode, onBack, onSelect, sessionCode, busy = false, error }: ModeSelectionProps) {
  const [selectedMode, setSelectedMode] = useState<Mode>(initialMode);
  const selected = MODES[selectedMode];
  const toggleMode = () => setSelectedMode((current) => current === "debate" ? "data" : "debate");

  return <main className={`mode-screen mode-screen--${selectedMode}`}>
    <img className="mode-screen__artwork" src={backgroundArtwork} alt="" aria-hidden="true" />
    <SetupHeader onBack={onBack} sessionCode={sessionCode} busy={busy} />

    <section className="mode-screen__content" aria-live="polite">
      <div className="mode-screen__heading"><h1>CHOOSE YOUR PATH</h1><p>Choose how your team will work.</p></div>
      {error && <p role="alert">{error}</p>}
      <div className="mode-selector" aria-busy={busy}>
        <button type="button" className="mode-selector__arrow" onClick={toggleMode} disabled={busy} aria-label="Previous mode"><ArrowIcon direction="left" /></button>
        <article className="mode-choice">

          <h2>{selected.title}</h2><p>{selected.description}</p>
          <ul className="mode-choice__tags" aria-label="Mode features">{selected.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul>
          <button type="button" className="mode-choice__cta" disabled={busy} onClick={() => onSelect(selectedMode)}>CHOOSE THIS MODE <ArrowIcon direction="right" /></button>
        </article>
        <button type="button" className="mode-selector__arrow" onClick={toggleMode} disabled={busy} aria-label="Next mode"><ArrowIcon direction="right" /></button>
      </div>
      <div className="mode-dots" aria-label="Select a mode">
        <button type="button" className={selectedMode === "debate" ? "is-active" : ""} disabled={busy} onClick={() => setSelectedMode("debate")} aria-label="Debate Mode" aria-pressed={selectedMode === "debate"} />
        <button type="button" className={selectedMode === "data" ? "is-active" : ""} onClick={() => setSelectedMode("data")} aria-label="Data Analysis" aria-pressed={selectedMode === "data"} />
      </div>
    </section>

    <SetupProgress activeStep={0} />
  </main>;
}
