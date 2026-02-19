import { FormEvent, useEffect, useMemo, useState } from "react";
import { addAgent, getState, loadDemo, reset, runRounds, setTopic } from "./api";
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
  if (!agent) return "\u2754";
  if (agent.name === "The Chair") return "\uD83E\uDE91";
  if (agent.name === "The Chaos Librarian") return "\uD83C\uDF00";
  const symbols = ["\uD83E\uDDE0", "\uD83D\uDEF0\uFE0F", "\uD83C\uDFAF", "\uD83E\uDDEA", "\u2699\uFE0F", "\uD83C\uDF1F", "\uD83C\uDFB2", "\uD83D\uDEE1\uFE0F"];
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
  const [showCreator, setShowCreator] = useState(false);

  const metrics: Metrics | null = useMemo(() => {
    const roundMetric = feed[feed.length - 1]?.metrics;
    if (roundMetric) return roundMetric;
    const snapshot = state?.world_state?.metrics;
    if (snapshot && typeof snapshot === "object") return snapshot as Metrics;
    return null;
  }, [feed, state]);

  const currentSpeakers = useMemo(() => {
    const lastRound = feed[feed.length - 1];
    if (!lastRound) return new Set<string>();
    return new Set(lastRound.round_result.speaker_ids);
  }, [feed]);

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

  async function onLoadDemo() {
    setError("");
    try {
      const result = await loadDemo();
      setStateValue(result.state);
      setTopicInput(result.state.topic);
      setFeed([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load demo");
    }
  }

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    (state?.agents ?? []).forEach((agent) => map.set(agent.id, agent));
    return map;
  }, [state]);

  return (
    <div className="app-shell">
      {/* ---- HUD HEADER ---- */}
      <header className="topbar">
        <h1 className="topbar__title">The Arena</h1>
        <div className="topbar__right">
          <div className="round-counter">
            <span className="round-counter__label">Round</span>
            <span className="round-counter__value">{state?.round_number ?? 0}</span>
          </div>
          <div className={`status ${connection}`}>
            <span className="status__dot" />
            {connection === "connected" ? "ONLINE" : "OFFLINE"}
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="grid">
        {/* ---- LEFT PANEL: ROSTER ---- */}
        <section className="panel left-panel">
          {/* Mission Briefing (Topic) */}
          <div className="section-block">
            <h2 className="section-title">Mission Briefing</h2>
            <form onSubmit={onTopicSubmit} className="stacked-form">
              <label className="form-label">Topic</label>
              <textarea
                value={topicInput}
                onChange={(e) => setTopicInput(e.target.value)}
                rows={2}
                placeholder="Define the arena topic..."
              />
              <button type="submit">Set Topic</button>
            </form>
          </div>

          {/* Agent Roster */}
          <div className="section-block">
            <h2 className="section-title">
              Agent Roster
              <span className="section-title__count">{state?.agents.length ?? 0}</span>
            </h2>
            <div className="agent-list">
              {(state?.agents ?? []).map((agent) => (
                <div
                  className={`agent-card${agent.role === "mediator" ? " agent-card--mediator-card" : ""}${currentSpeakers.has(agent.id) ? " agent-card--speaking" : ""}`}
                  key={agent.id}
                >
                  <div className="agent-card__header">
                    <div className="agent-card__identity">
                      <div className={`avatar-chip${agent.role === "mediator" ? " avatar-chip--mediator" : ""}`}>
                        {agentAvatar(agent)}
                      </div>
                      <div>
                        <strong className="agent-card__name">{agent.name}</strong>
                        {currentSpeakers.has(agent.id) && (
                          <span className="speaking-indicator">Speaking...</span>
                        )}
                      </div>
                    </div>
                    <span className={roleClass(agent.role)}>{agent.role}</span>
                  </div>
                  <div className="agent-card__stance">{agent.stance}</div>
                  <div className="energy-row">
                    <span className="form-label">Energy</span>
                    <div className="energy-bar-track">
                      <div
                        className={`energy-bar-fill${agent.energy < 0.3 ? " energy-bar-fill--low" : ""}`}
                        style={{ width: `${agent.energy * 100}%` }}
                      />
                    </div>
                    <span className="energy-value">{agent.energy.toFixed(2)}</span>
                  </div>
                  <div className="agent-card__quirks">
                    {agent.quirks.map((q, i) => (
                      <span className="quirk-chip" key={i}>{q}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recruit Agent (collapsible) */}
          <div className="section-block">
            <button
              className="recruit-toggle"
              type="button"
              onClick={() => setShowCreator((prev) => !prev)}
            >
              {showCreator ? "Close Recruitment" : "Recruit New Agent"}
            </button>
            <div className={`recruit-section${showCreator ? " recruit-section--open" : ""}`}>
              <form onSubmit={onAddAgent} className="stacked-form">
                <label className="form-label">Agent Name</label>
                <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} placeholder="Name your agent..." />
                <label className="form-label">Persona (1-2 lines)</label>
                <textarea value={personaInput} onChange={(e) => setPersonaInput(e.target.value)} rows={3} placeholder="Describe their personality..." />
                <label className="form-label">Energy: {energyInput.toFixed(2)}</label>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={energyInput}
                  onChange={(e) => setEnergyInput(Number(e.target.value))}
                />
                <button type="submit">Deploy Agent</button>
              </form>
            </div>
          </div>
        </section>

        {/* ---- CENTER PANEL: THE ARENA ---- */}
        <section className="panel center-panel">
          <h2 className="section-title">The Arena</h2>
          <div className="feed">
            {feed.length === 0 && (
              <div className="empty-arena">
                <div className="empty-arena__emoji">{"\u2694\uFE0F"}</div>
                <div className="empty-arena__text">Awaiting combatants...</div>
                <div className="empty-arena__sub">Set a topic and run a round to begin.</div>
              </div>
            )}
            {feed.map((roundEvent) => (
              <article className="round" key={`round-${roundEvent.round_result.round_number}`}>
                <header className="round-banner">
                  <span className="round-banner__line" />
                  <span className="round-banner__text">Round {roundEvent.round_result.round_number}</span>
                  <span className="round-banner__line" />
                </header>
                <div className="turns">
                  {roundEvent.round_result.turns.map((turn, idx) => {
                    const speaker =
                      roundEvent.state_snapshot.agents.find((a) => a.id === turn.speaker_id)
                      ?? agentMap.get(turn.speaker_id);
                    return (
                      <div
                        className="turn game-turn"
                        key={`${turn.speaker_id}-${idx}`}
                        style={{ animationDelay: `${idx * 0.15}s` }}
                      >
                        <div className={`avatar${speaker?.role === "mediator" ? " avatar--mediator" : ""}`}>
                          {agentAvatar(speaker)}
                        </div>
                        <div className="speech-wrap">
                          <div className="turn__header">
                            <strong className="turn__name">{speaker?.name ?? turn.speaker_id}</strong>
                            <span className={roleClass(speaker?.role ?? "user")}>{speaker?.role ?? "unknown"}</span>
                          </div>
                          <p className="speech-bubble">{turn.message}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {roundEvent.round_result.reactions.length > 0 && (
                  <div className="reactions">
                    <div className="reactions__label">Reactions</div>
                    <div className="reactions__list">
                      {roundEvent.round_result.reactions.map((reaction, idx) => {
                        const actor =
                          roundEvent.state_snapshot.agents.find((a) => a.id === reaction.agent_id)
                          ?? agentMap.get(reaction.agent_id);
                        return (
                          <div
                            className="reaction-chip"
                            key={reaction.agent_id}
                            style={{ animationDelay: `${idx * 0.08}s` }}
                          >
                            <span className="reaction-chip__avatar">{agentAvatar(actor)}</span>
                            <span className="reaction-chip__emoji">{reaction.emoji}</span>
                            <span className="reaction-chip__comment">{reaction.micro_comment}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>

        {/* ---- RIGHT PANEL: COMMAND CENTER ---- */}
        <section className="panel right-panel">
          <h2 className="section-title">Command Center</h2>

          <div className="button-row">
            <button className="btn-demo" onClick={onLoadDemo}>Load Demo</button>
          </div>

          <div className="button-row">
            <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1 Round</button>
            <button disabled={running} onClick={() => onRun(5)}>Run 5 Rounds</button>
            <button className="btn-danger" onClick={onReset}>Reset</button>
          </div>

          <div className="control-row">
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={autoRun}
                onChange={(e) => setAutoRun(e.target.checked)}
                className="toggle-input"
              />
              <span className="toggle-switch" />
              <span className="toggle-label">Auto-Run</span>
            </label>
          </div>

          <div className="control-row">
            <label className="form-label">Interval (ms)</label>
            <input
              type="number"
              min={200}
              step={100}
              value={intervalMs}
              onChange={(e) => setIntervalMs(Number(e.target.value) || 1000)}
            />
          </div>

          <h3 className="section-subtitle">Battle Metrics</h3>
          {metrics ? (
            <div className="metrics">
              <div className="metric-row">
                <span className="metric-label">Consensus</span>
                <div className="metric-bar-track">
                  <div className="metric-bar-fill metric-bar-fill--consensus" style={{ width: `${metrics.consensus_score * 100}%` }} />
                </div>
                <span className="metric-value">{metricValue(metrics.consensus_score)}</span>
              </div>
              <div className="metric-row">
                <span className="metric-label">Polarization</span>
                <div className="metric-bar-track">
                  <div className="metric-bar-fill metric-bar-fill--polarization" style={{ width: `${metrics.polarization_score * 100}%` }} />
                </div>
                <span className="metric-value">{metricValue(metrics.polarization_score)}</span>
              </div>
              <div className="metric-row">
                <span className="metric-label">Civility</span>
                <div className="metric-bar-track">
                  <div className="metric-bar-fill metric-bar-fill--civility" style={{ width: `${metrics.civility_score * 100}%` }} />
                </div>
                <span className="metric-value">{metricValue(metrics.civility_score)}</span>
              </div>
              <div className="coalitions-row">
                <span className="metric-label">Coalitions</span>
                <div className="coalitions-list">
                  {metrics.detected_coalitions.length
                    ? metrics.detected_coalitions.map((c, i) => <span className="coalition-chip" key={i}>{c}</span>)
                    : <span className="metric-value">None detected</span>
                  }
                </div>
              </div>
            </div>
          ) : (
            <div className="metrics-empty">No metrics yet</div>
          )}

          <h3 className="section-subtitle">Simulation Info</h3>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Round</span>
              <span className="info-value">{state?.round_number ?? 0}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Agents</span>
              <span className="info-value">{state?.agents.length ?? 0}</span>
            </div>
            <div className="info-item info-item--full">
              <span className="info-label">Topic</span>
              <span className="info-value">{state?.topic ?? "-"}</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
