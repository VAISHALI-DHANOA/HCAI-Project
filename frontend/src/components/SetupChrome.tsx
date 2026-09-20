import "./SetupChrome.css";
import type { ReactNode } from "react";
import { Brand } from "./Brand";

export function ArrowIcon({ direction }: { direction: "left" | "right" }) {
  return <svg viewBox="0 0 32 32" aria-hidden="true"><path d={direction === "left" ? "M18 7 9 16l9 9M10 16h14" : "m14 7 9 9-9 9m8-9H8"} /></svg>;
}

export function SetupHeader({ onBack, sessionCode, busy = false, children, backAccessory }: {
  onBack: () => void;
  sessionCode?: string;
  busy?: boolean;
  children?: ReactNode;
  backAccessory?: ReactNode;
}) {
  return <>
    <header className="mode-screen__topbar setup-global-header">
      <div className="mode-screen__nav">
        <Brand className="setup-header-brand" />
      </div>
    </header>
    <div className="setup-global-header__state">
      <button type="button" className="mode-back" onClick={onBack} disabled={busy}><ArrowIcon direction="left" /> BACK</button>
      {sessionCode && <div className="mode-token" aria-label={`Session token ${sessionCode}`}><span>SESSION TOKEN</span><strong>{sessionCode}</strong><button type="button" onClick={() => navigator.clipboard?.writeText(sessionCode)}>COPY</button></div>}
      {children}
    </div>
    {backAccessory && <div className="setup-header-accessory">{backAccessory}</div>}
  </>;
}

export function SetupProgress({ activeStep }: { activeStep: number }) {
  return <nav className="mode-progress" aria-label="Setup progress">
    {[["01", "CHOOSE MODE"], ["02", "TOPIC & TEAM"], ["03", "MODERATOR"]].map(([number, label], index) => <div className={index === activeStep ? "mode-progress__step is-active" : "mode-progress__step"} key={number} aria-current={index === activeStep ? "step" : undefined}><span>{number}</span><strong>{label}</strong></div>)}
  </nav>;
}
