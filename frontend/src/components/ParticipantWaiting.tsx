import backgroundArtwork from "../../artwork/Background_2.png";
import "./EntryScreen.css";

export function ParticipantWaiting({ error, onBack }: { error: string; onBack: () => void }) {
  return <main className="entry-screen">
    <img className="entry-screen__artwork" src={backgroundArtwork} alt="" />
    <div className="entry-screen__content">
      <h1>YOU'RE IN</h1>
      <p className="entry-screen__intro" role="status">Waiting for your host to choose a mode.</p>
      <section className="session-ledger participant-waiting" aria-label="Waiting room">
        <p>Your team setup will open automatically when the host is ready.</p>
        {error && <p role="alert">{error}</p>}
        <button type="button" className="session-ledger__button" onClick={onBack}>BACK TO ENTRY</button>
      </section>
    </div>
  </main>;
}
