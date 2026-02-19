import { FormEvent, useEffect, useMemo, useState } from "react";
import { addAgent, getState, reset, runRounds, setTopic } from "./api";
import { createWsClient } from "./ws";
import type { ConnectionStatus } from "./ws";
import type { Agent, Metrics, State, WsEvent, WsRoundEvent } from "./types";
import "./styles.css";

function roleClass(role: Agent["role"]): string {
  return role === "mediator" ? "tag mediator" : "tag user";
}

function metricValue(value: number): string {
  return value.toFixed(3);
}

function agentAvatar(agent?: Agent): string {
  if (!agent) return "❔";
  if (agent.name === "The Chair") return "🪑";
  if (agent.name === "The Chaos Librarian") return "🌀";
  const symbols = ["🧠", "🛰️", "🎯", "🧪", "⚙️", "🌟", "🎲", "🛡️"];
  const seed = `${agent.id}${agent.name}`;
  const index = Array.from(seed).reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % symbols.length;
  return symbols[index];
}

export default function App() {
  const [state, setStateValue] = useState<State | null>(null);
  const [topicInput, setTopicInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [personaInput, setPersonaInput] = useState("");
  const [energyInput, setEnergyInput] = useState(0.6);
  const [feed, setFeed] = useState<WsRoundEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [intervalMs, setIntervalMs] = useState(1800);

  const metrics: Metrics | null = useMemo(() => {
    const roundMetric = feed[feed.length - 1]?.metrics;
    if (roundMetric) return roundMetric;
    const snapshot = state?.world_state?.metrics;
    if (snapshot && typeof snapshot === "object") return snapshot as Metrics;
    return null;
  }, [feed, state]);

  useEffect(() => {
    getState()
      .then((data) => {
        setStateValue(data);
        setTopicInput(data.topic);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Failed to load state");
      });

    const close = createWsClient(
      (event: WsEvent) => {
        if (event.type === "state") {
          setStateValue(event.state_snapshot);
          return;
        }
        setFeed((prev) => [...prev, event]);
        setStateValue(event.state_snapshot);
      },
      (status) => setConnection(status)
    );

    return () => close();
  }, []);

  useEffect(() => {
    if (!autoRun) return;
    const timer = window.setInterval(async () => {
      if (running) return;
      try {
        setRunning(true);
        await runRounds(1);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Auto-run failed");
      } finally {
        setRunning(false);
      }
    }, Math.max(200, intervalMs));

    return () => window.clearInterval(timer);
  }, [autoRun, intervalMs, running]);

  async function onTopicSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await setTopic(topicInput.trim());
      setStateValue(result.state);
      setFeed([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to set topic");
    }
  }

  async function onAddAgent(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!nameInput.trim() || !personaInput.trim()) return;
    try {
      const result = await addAgent(nameInput.trim(), personaInput.trim(), energyInput);
      setStateValue(result.state);
      setNameInput("");
      setPersonaInput("");
      setEnergyInput(0.6);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add agent");
    }
  }

  async function onRun(rounds: number) {
    setError("");
    try {
      setRunning(true);
      await runRounds(rounds);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  async function onReset() {
    setError("");
    try {
      const result = await reset(topicInput.trim() || undefined);
      setStateValue(result.state);
      setFeed([]);
      setAutoRun(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reset failed");
    }
  }

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    (state?.agents ?? []).forEach((agent) => map.set(agent.id, agent));
    return map;
  }, [state]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>Creative Multi-Agent Playground</h1>
        <div className={`status ${connection}`}>{connection === "connected" ? "Connected" : "Disconnected"}</div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="grid">
        <section className="panel left-panel">
          <h2>Agent Creator</h2>
          <form onSubmit={onTopicSubmit} className="stacked-form">
            <label>Topic</label>
            <textarea value={topicInput} onChange={(e) => setTopicInput(e.target.value)} rows={2} />
            <button type="submit">Set Topic</button>
          </form>

          <form onSubmit={onAddAgent} className="stacked-form">
            <label>Agent Name</label>
            <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
            <label>Persona (1-2 lines)</label>
            <textarea value={personaInput} onChange={(e) => setPersonaInput(e.target.value)} rows={3} />
            <label>Energy: {energyInput.toFixed(2)}</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={energyInput}
              onChange={(e) => setEnergyInput(Number(e.target.value))}
            />
            <button type="submit">Add Agent</button>
          </form>

          <h3>Agents</h3>
          <div className="agent-list">
            {(state?.agents ?? []).map((agent) => (
              <div className="agent-card" key={agent.id}>
                <div className="row between">
                  <div className="row">
                    <div className="avatar-chip">{agentAvatar(agent)}</div>
                    <strong>{agent.name}</strong>
                  </div>
                  <span className={roleClass(agent.role)}>{agent.role}</span>
                </div>
                <div className="small">Energy: {agent.energy.toFixed(2)}</div>
                <div className="small">Quirks: {agent.quirks.join(" | ")}</div>
                <div className="small">Stance: {agent.stance}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel center-panel">
          <h2>Live Chat Feed</h2>
          <div className="feed">
            {feed.length === 0 && <div className="empty">No rounds yet.</div>}
            {feed.map((roundEvent) => (
              <article className="round" key={`round-${roundEvent.round_result.round_number}`}>
                <header className="round-header">Round {roundEvent.round_result.round_number}</header>
                <div className="turns">
                  {roundEvent.round_result.turns.map((turn, idx) => {
                    const speaker = roundEvent.state_snapshot.agents.find((a) => a.id === turn.speaker_id) ?? agentMap.get(turn.speaker_id);
                    return (
                      <div className="turn game-turn" key={`${turn.speaker_id}-${idx}`}>
                        <div className="avatar">{agentAvatar(speaker)}</div>
                        <div className="speech-wrap">
                          <div className="row between">
                            <strong>{speaker?.name ?? turn.speaker_id}</strong>
                            <span className={roleClass(speaker?.role ?? "user")}>{speaker?.role ?? "unknown"}</span>
                          </div>
                          <p className="speech-bubble">{turn.message}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="reactions">
                  <strong>Reactions</strong>
                  {roundEvent.round_result.reactions.map((reaction) => {
                    const actor = roundEvent.state_snapshot.agents.find((a) => a.id === reaction.agent_id) ?? agentMap.get(reaction.agent_id);
                    return (
                      <div className="reaction bubble-reaction" key={reaction.agent_id}>
                        <div className="avatar tiny">{agentAvatar(actor)}</div>
                        <span>{reaction.emoji}</span>
                        <span>{actor?.name ?? reaction.agent_id}</span>
                        <span className="reaction-bubble">{reaction.micro_comment}</span>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel right-panel">
          <h2>Controls & Metrics</h2>
          <div className="button-row">
            <button disabled={running} onClick={() => onRun(1)}>Run 1 Round</button>
            <button disabled={running} onClick={() => onRun(5)}>Run 5 Rounds</button>
            <button onClick={onReset}>Reset</button>
          </div>

          <label className="toggle-row">
            <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} />
            Auto-run
          </label>

          <label>Interval (ms)</label>
          <input
            type="number"
            min={200}
            step={100}
            value={intervalMs}
            onChange={(e) => setIntervalMs(Number(e.target.value) || 1000)}
          />

          <h3>Latest Metrics</h3>
          <div className="metrics">
            <div className="metric"><span>Consensus</span><strong>{metrics ? metricValue(metrics.consensus_score) : "-"}</strong></div>
            <div className="metric"><span>Polarization</span><strong>{metrics ? metricValue(metrics.polarization_score) : "-"}</strong></div>
            <div className="metric"><span>Civility</span><strong>{metrics ? metricValue(metrics.civility_score) : "-"}</strong></div>
            <div className="metric coalition">
              <span>Coalitions</span>
              <strong>{metrics ? (metrics.detected_coalitions.length ? metrics.detected_coalitions.join(", ") : "None") : "-"}</strong>
            </div>
          </div>

          <h3>Simulation</h3>
          <div className="small">Round: {state?.round_number ?? 0}</div>
          <div className="small">Topic: {state?.topic ?? "-"}</div>
          <div className="small">Total agents: {state?.agents.length ?? 0}</div>
        </section>
      </main>
    </div>
  );
}
