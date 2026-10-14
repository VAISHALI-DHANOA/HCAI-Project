import { Brand } from "./Brand";
import { FormEvent, useState } from "react";
import backgroundArtwork from "../../artwork/Background_2.png";
import createArtwork from "../../artwork/Create_session.png";
import joinArtwork from "../../artwork/Join_session.png";
import "./EntryScreen.css";

interface EntryScreenProps { onCreate: () => void; onJoin: (code: string) => void; busy?: boolean; error?: string; }

export function EntryScreen({ onCreate, onJoin, busy = false, error }: EntryScreenProps) {
  const [code, setCode] = useState("");
  const submit = (event: FormEvent) => { event.preventDefault(); if (code.trim()) onJoin(code); };
  return <main className="entry-screen">
    <img className="entry-screen__artwork" src={backgroundArtwork} alt="" aria-hidden="true" />
    <Brand />
    <div className="entry-screen__content"><h1>ENTER THE ARENA</h1><p className="entry-screen__intro">Start something together. Create a room or join your team.</p>
      {error && <p className="session-entry-error" role="alert">{error}</p>}
      <div className="session-ledgers" aria-busy={busy}>
        <section className="session-ledger session-ledger--create" aria-label="Create a session">
          <div className="session-ledger__meta"><i /><span>START TOGETHER</span></div>
          <div className="session-ledger__art"><img src={createArtwork} alt="" /></div>
          <button type="button" className="session-ledger__button session-ledger__create" onClick={onCreate} disabled={busy}>CREATE SESSION <span aria-hidden="true">→</span></button>
        </section>
        <form className="session-ledger" onSubmit={submit} aria-label="Join a session">
          <div className="session-ledger__meta"><i /><span>JOIN THE QUEST</span></div>
          <div className="session-ledger__art"><img src={joinArtwork} alt="" /></div>
          <div className="session-ledger__controls"><input disabled={busy} maxLength={64} required aria-label="Session code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Session code" /><button type="submit" disabled={busy} className="session-ledger__button">JOIN</button></div>
        </form>
      </div>
    </div>
  </main>;
}
