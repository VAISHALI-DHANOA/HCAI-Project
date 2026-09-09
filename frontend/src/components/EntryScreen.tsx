import { FormEvent, useState } from "react";
import backgroundArtwork from "../../artwork/Background_2.png";
import createArtwork from "../../artwork/Create_session.png";
import joinArtwork from "../../artwork/Join_session.png";
import "./EntryScreen.css";

interface EntryScreenProps { onCreate: () => void; onJoin: (code: string) => void; }

export function EntryScreen({ onCreate, onJoin }: EntryScreenProps) {
  const [code, setCode] = useState("");
  const submit = (event: FormEvent) => { event.preventDefault(); if (code.trim()) onJoin(code); };
  return <main className="entry-screen">
    <img className="entry-screen__artwork" src={backgroundArtwork} alt="" aria-hidden="true" />
    <div className="entry-screen__brand"><div className="brand-mark" aria-hidden="true">A</div><div className="entry-brand-copy"><span className="entry-brand-name">THE ARENA</span><span className="entry-brand-tagline">A multi-agent playground</span></div></div>
    <div className="entry-screen__content"><h1>ENTER THE ARENA</h1><p className="entry-screen__intro">Start something together. Create a room or join your team.</p>
      <div className="session-ledgers">
        <section className="session-ledger session-ledger--create" aria-label="Create a session">
          <div className="session-ledger__meta"><i /><span>START TOGETHER</span></div>
          <div className="session-ledger__art"><img src={createArtwork} alt="" /></div>
          <button type="button" className="session-ledger__button session-ledger__create" onClick={onCreate}>CREATE SESSION <span aria-hidden="true">→</span></button>
        </section>
        <form className="session-ledger" onSubmit={submit} aria-label="Join a session">
          <div className="session-ledger__meta"><i /><span>JOIN THE QUEST</span></div>
          <div className="session-ledger__art"><img src={joinArtwork} alt="" /></div>
          <div className="session-ledger__controls"><input aria-label="Session code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Session code" /><button type="submit" className="session-ledger__button">JOIN</button></div>
        </form>
      </div>
    </div>
  </main>;
}
