import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { addAgent, getState, loadDemo, reset, runRounds, setTopic } from "./api";
import { createWsClient } from "./ws";
import type { ConnectionStatus } from "./ws";
import type { Agent, Metrics, State, WsEvent, WsRoundEvent } from "./types";
import "./styles.css";

const AGENT_COLORS = [
  "#38bdf8", "#a78bfa", "#fb923c", "#4ade80", "#f87171",
  "#fbbf24", "#22d3ee", "#e879f9", "#34d399", "#f472b6",
];

function agentAvatarUrl(agent: Agent): string {
  return `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`;
}

function agentColor(agent: Agent): string {
  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return AGENT_COLORS[seed % AGENT_COLORS.length];
}

function metricValue(value: number): string {
  return value.toFixed(3);
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
  const [activeTurnIdx, setActiveTurnIdx] = useState<number>(-1);
  const [showReactions, setShowReactions] = useState(false);
  const [expandedRounds, setExpandedRounds] = useState<Set<number>>(new Set());

  const feedLenRef = useRef(0);

  const metrics: Metrics | null = useMemo(() => {
    const roundMetric = feed[feed.length - 1]?.metrics;
    if (roundMetric) return roundMetric;
    const snapshot = state?.world_state?.metrics;
    if (snapshot && typeof snapshot === "object") return snapshot as Metrics;
    return null;
  }, [feed, state]);

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    (state?.agents ?? []).forEach((agent) => map.set(agent.id, agent));
    return map;
  }, [state]);

  const latestRound = useMemo(() => {
    return feed.length > 0 ? feed[feed.length - 1] : null;
  }, [feed]);

  const latestTurns = useMemo(() => {
    return latestRound?.round_result.turns ?? [];
  }, [latestRound]);

  const currentTurn = useMemo(() => {
    if (activeTurnIdx < 0 || !latestTurns.length) return null;
    return latestTurns[Math.min(activeTurnIdx, latestTurns.length - 1)] ?? null;
  }, [latestTurns, activeTurnIdx]);

  const currentSpeakerId = currentTurn?.speaker_id ?? null;

  // Circular positioning
  const agentPositions = useMemo(() => {
    const agents = state?.agents ?? [];
    const N = agents.length;
    if (N === 0) return [];
    const R = Math.min(42, Math.max(32, 38 + (N - 6) * 0.3));
    return agents.map((agent, i) => {
      const angle = (i / N) * 2 * Math.PI - Math.PI / 2;
      const x = 50 + R * Math.cos(angle);
      const y = 50 + R * Math.sin(angle);
      return { agent, x, y };
    });
  }, [state?.agents]);

  // Initial state load + WebSocket
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

  // Auto-run timer
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

  // Sequential speaker animation when a new round arrives
  useEffect(() => {
    if (feed.length === 0) {
      setActiveTurnIdx(-1);
      setShowReactions(false);
      return;
    }

    // Only animate when feed grows (new round)
    if (feed.length === feedLenRef.current) return;
    feedLenRef.current = feed.length;

    const turns = feed[feed.length - 1].round_result.turns;
    if (turns.length === 0) return;

    let turnIndex = 0;
    setShowReactions(false);
    setActiveTurnIdx(0);

    const timer = setInterval(() => {
      turnIndex++;
      if (turnIndex >= turns.length) {
        clearInterval(timer);
        setShowReactions(true);
        return;
      }
      setActiveTurnIdx(turnIndex);
    }, 2500);

    return () => clearInterval(timer);
  }, [feed]);

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
      setActiveTurnIdx(-1);
      setShowReactions(false);
      feedLenRef.current = 0;
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
      setActiveTurnIdx(-1);
      setShowReactions(false);
      feedLenRef.current = 0;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load demo");
    }
  }

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

      <main className="arena-layout">
        {/* ---- ARENA VIEWPORT ---- */}
        <section className="arena-viewport">
          {/* Agent nodes in circular positions */}
          <div className="arena-ring">
            {agentPositions.map(({ agent, x, y }) => {
              const isSpeaking = currentSpeakerId === agent.id;
              const hasSomeoneActive = currentSpeakerId !== null;
              const color = agentColor(agent);

              const speakingTransform = isSpeaking
                ? `translate(-50%, -50%) scale(1.35) translate(${(50 - x) * 0.3}%, ${(50 - y) * 0.3}%)`
                : "translate(-50%, -50%)";

              return (
                <div
                  className={`arena-node${isSpeaking ? " arena-node--speaking" : ""}${hasSomeoneActive && !isSpeaking ? " arena-node--dimmed" : ""}`}
                  key={agent.id}
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                    transform: speakingTransform,
                    "--agent-color": color,
                  } as React.CSSProperties}
                >
                  <div className="arena-node__avatar-wrap">
                    <img
                      className="arena-node__avatar"
                      src={agentAvatarUrl(agent)}
                      alt={agent.name}
                      width={64}
                      height={64}
                    />
                    {agent.role === "mediator" && (
                      <span className="arena-node__role-badge">MOD</span>
                    )}
                  </div>
                  <div className="arena-node__name">{agent.name}</div>
                  <div className="arena-node__energy-bar">
                    <div
                      className={`arena-node__energy-fill${agent.energy < 0.3 ? " arena-node__energy-fill--low" : ""}`}
                      style={{ width: `${agent.energy * 100}%` }}
                    />
                  </div>
                  <div className="arena-node__quirks">
                    {agent.quirks.map((q, i) => (
                      <span className="arena-node__quirk" key={i}>{q}</span>
                    ))}
                  </div>

                  {/* Reaction bubble */}
                  {showReactions && latestRound?.round_result.reactions
                    .filter(r => r.agent_id === agent.id)
                    .map((reaction, ri) => (
                      <div className="arena-reaction-bubble" key={ri}>
                        <span className="arena-reaction-bubble__emoji">{reaction.emoji}</span>
                        <span className="arena-reaction-bubble__text">{reaction.micro_comment}</span>
                      </div>
                    ))
                  }
                </div>
              );
            })}
          </div>

          {/* Center Stage */}
          <div className="center-stage">
            {currentTurn && latestRound ? (
              <div className="center-stage__content">
                <div className="center-stage__speaker">
                  {agentMap.get(currentTurn.speaker_id) && (
                    <img
                      className="center-stage__speaker-avatar"
                      src={agentAvatarUrl(agentMap.get(currentTurn.speaker_id)!)}
                      alt=""
                      width={40}
                      height={40}
                    />
                  )}
                  <span className="center-stage__speaker-name">
                    {agentMap.get(currentTurn.speaker_id)?.name ?? currentTurn.speaker_id}
                  </span>
                </div>
                <p className="center-stage__message" key={`${latestRound.round_result.round_number}-${activeTurnIdx}`}>
                  {currentTurn.message}
                </p>
                {activeTurnIdx > 0 && (
                  <div className="center-stage__history">
                    {latestTurns.slice(0, activeTurnIdx).map((turn, i) => (
                      <p className="center-stage__past-turn" key={i}>
                        <strong>{agentMap.get(turn.speaker_id)?.name ?? "?"}: </strong>
                        {turn.message}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="center-stage__empty">
                <div className="center-stage__empty-icon">{"\u2694\uFE0F"}</div>
                <div className="center-stage__empty-text">Awaiting combatants...</div>
                <div className="center-stage__empty-sub">Set a topic and run a round to begin.</div>
              </div>
            )}
          </div>
        </section>

        {/* ---- SIDE PANEL ---- */}
        <aside className="side-panel">
          {/* Mission Briefing */}
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

          {/* Command Center */}
          <div className="section-block">
            <h2 className="section-title">Command Center</h2>
            <div className="button-row">
              <button className="btn-demo" onClick={onLoadDemo}>Load Demo</button>
            </div>
            <div className="button-row">
              <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1</button>
              <button disabled={running} onClick={() => onRun(5)}>Run 5</button>
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
          </div>

          {/* Battle Metrics */}
          <div className="section-block">
            <h2 className="section-title">Battle Metrics</h2>
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
          </div>

          {/* Simulation Info */}
          <div className="section-block">
            <h2 className="section-title">Simulation Info</h2>
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
          </div>

          {/* Recruit Agent */}
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
                <textarea value={personaInput} onChange={(e) => setPersonaInput(e.target.value)} rows={2} placeholder="Describe their personality..." />
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

          {/* Round History */}
          <div className="section-block">
            <h2 className="section-title">
              Round History
              <span className="section-title__count">{feed.length}</span>
            </h2>
            <div className="history-log">
              {[...feed].reverse().map((roundEvent) => {
                const rn = roundEvent.round_result.round_number;
                const isExpanded = expandedRounds.has(rn);
                return (
                  <div className="history-entry" key={rn}>
                    <button
                      className="history-entry__header"
                      onClick={() => {
                        setExpandedRounds(prev => {
                          const next = new Set(prev);
                          if (next.has(rn)) next.delete(rn);
                          else next.add(rn);
                          return next;
                        });
                      }}
                    >
                      <span>Round {rn}</span>
                      <span className="history-entry__speakers">
                        {roundEvent.round_result.turns.length} turns
                      </span>
                      <span className="history-entry__chevron">{isExpanded ? "\u25B2" : "\u25BC"}</span>
                    </button>
                    {isExpanded && (
                      <div className="history-entry__body">
                        {roundEvent.round_result.turns.map((turn, ti) => {
                          const sp = agentMap.get(turn.speaker_id);
                          return (
                            <div className="history-turn" key={ti}>
                              <img
                                className="history-turn__avatar"
                                src={sp ? agentAvatarUrl(sp) : ""}
                                alt=""
                                width={20}
                                height={20}
                              />
                              <strong className="history-turn__name">{sp?.name ?? "?"}</strong>
                              <span className="history-turn__msg">{turn.message}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}
