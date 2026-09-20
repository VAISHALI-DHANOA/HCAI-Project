import { Fragment, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { addAgents, downloadLogs, endSession, getModeratorStrategies, getPersonalityCatalog, getSessionId, getState, intervene, loadDemo, loadExample, reset, runRounds, setAdminKey, setContributionDisplayTime, setModeratorStrategy, setTopic, syncAgents, uploadDataset } from "./api";
import { createWsClient } from "./ws";
import { acceptsSnapshot, pendingHumanTurns, rosterAdditions, sameRoster } from "./session";
import type { ConnectionStatus } from "./ws";
import type { Agent, AppPhase, CellAnnotation, CellHighlight, DashboardVisual, DraftAgent, EndSummary, Metrics, ModeratorStrategy, PersonalityCatalog, PublicTurn, State, WsEvent, WsRoundEvent } from "./types";
import { VisualCard } from "./components/VisualCard";
import { ArenaTable } from "./components/ArenaTable";
import { DashboardCanvas } from "./components/DashboardCanvas";
import { DataContribution } from "./components/DataContribution";
import { DataAgentStrip, type AgentFocus } from "./components/DataAgentStrip";
import { createPersonalityFromPreset as clonePreset, getPersonalityPreset as findPreset } from "./personality";
import { PlaybackController } from "./playback";
import { useTTS, agentVoiceParams } from "./hooks/useTTS";
import "./styles.css";
import "./components/AgentCreation.css";
import { AgentCard } from "./components/AgentCard";
import { EntryScreen } from "./components/EntryScreen";
import { ModeSelection } from "./components/ModeSelection";
import { ArrowIcon, SetupHeader, SetupProgress } from "./components/SetupChrome";
import { ParticipantWaiting } from "./components/ParticipantWaiting";
import { ModeratorSelection } from "./components/ModeratorSelection";
import { Brand } from "./components/Brand";
import { useSessionGate } from "./hooks/useSessionGate";
import { getModeratorAvatar } from "./moderatorAvatars";
import { TestChatModal } from "./components/TestChatModal";
import { downloadAgentRoster, MAX_AGENTS, parseAgentRoster } from "./agentRoster";

const MIN_USER_AGENTS = 4;

const AGENT_COLORS = [
  "#38bdf8", "#a78bfa", "#fb923c", "#4ade80", "#f87171",
  "#fbbf24", "#22d3ee", "#e879f9", "#34d399", "#f472b6",
];

function agentAvatarUrl(agent: Agent, moderatorStrategyId?: string): string {
  if (agent.role === "mediator") return getModeratorAvatar(moderatorStrategyId);
  return `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`;
}

function agentColor(agent: Agent): string {
  const seed = Array.from(agent.id).reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return AGENT_COLORS[seed % AGENT_COLORS.length];
}

function metricValue(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(3);
}

function authoritativeRoundCount(state: State | null): number {
  return state?.rounds?.length ?? state?.round_number ?? 0;
}

function draftFromAgent(agent: Agent): DraftAgent {
  if (!agent.personality) throw new Error(`Missing personality configuration for ${agent.name}`);
  return {
    id: agent.id,
    name: agent.name,
    persona_text: agent.persona_text,
    energy: agent.energy,
    personality: agent.personality,
  };
}

export default function App() {
  const session = useSessionGate();
  const [catalog, setCatalog] = useState<PersonalityCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setCatalogError("");
    getPersonalityCatalog()
      .then((data) => { if (active) setCatalog(data); })
      .catch((error: unknown) => {
        if (active) setCatalogError(error instanceof Error ? error.message : "Could not load personalities");
      });
    return () => { active = false; };
  }, [attempt]);

  if (session.gate === "entry") return <EntryScreen onCreate={session.create} onJoin={session.join} busy={session.busy} error={session.error} />;
  if (session.gate === "waiting") return <ParticipantWaiting error={session.error} onBack={session.back} />;
  if (session.gate === "mode") return <ModeSelection initialMode={session.mode} sessionCode={getSessionId()} onBack={session.back} onSelect={session.select} busy={session.busy} error={session.error} />;
  if (!catalog) return (
    <div className="app-shell">
      <p role={catalogError ? "alert" : "status"}>{catalogError || "Loading personality settings…"}</p>
      {catalogError && <button onClick={() => setAttempt((value) => value + 1)}>Retry</button>}
    </div>
  );
  return <Playground catalog={catalog} initialMode={session.mode} onModeChange={session.setMode} participant={session.participant} onSetupBack={session.participant ? session.back : session.backToMode} onReturnToEntry={session.back} />;
}

function ConversationLog({ state, liveTurns, liveRound, agentMap, visibleVisualIds, completedRound }: {
  state: State | null; liveTurns: PublicTurn[]; liveRound: number; agentMap: Map<string, Agent>;
  visibleVisualIds?: Set<string>;
  completedRound?: number;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const roundNumbers = (state?.rounds ?? []).flatMap((round) => round.turns.map(() => round.round_number));
  const showLive = !(state?.rounds ?? []).some((round) => round.round_number === liveRound);
  const history = state?.public_history ?? [];
  const liveHumans = showLive ? liveTurns.filter((turn) => turn.speaker_id === "human") : [];
  let pendingHuman = liveHumans.length - 1;
  const inLiveHistory = new Set<number>();
  for (let index = history.length - 1; index >= 0 && pendingHuman >= 0; index--) {
    if (history[index].speaker_id === "human" && history[index].message === liveHumans[pendingHuman].message) {
      inLiveHistory.add(index);
      pendingHuman--;
    }
  }
  let contribution = 0;
  const entries = history.filter((_, index) => !inLiveHistory.has(index)).map((turn) => ({
    turn, round: turn.speaker_id === "human" ? undefined : roundNumbers[contribution++], live: false,
  }));
  if (showLive) {
    entries.push(...liveTurns.map((turn) => ({ turn, round: turn.speaker_id === "human" ? undefined : liveRound, live: true })));
  }
  useEffect(() => {
    if (followLatest.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [entries.length]);
  let previousRound: number | undefined;
  return (
    <div className="section-block section-block--log">
      <h2 className="section-title">Conversation Log <span className="section-title__count">{entries.length}</span></h2>
      <div className="chat-log" ref={scrollRef} onScroll={(event) => {
        const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
        followLatest.current = scrollHeight - scrollTop - clientHeight < 48;
      }}>
        {!entries.length && <div className="chat-log__empty">No conversations yet. Run a round to begin.</div>}
        {entries.map(({ turn, round, live }, index) => {
          const showRound = round !== undefined && round !== previousRound;
          const roundStatus = completedRound === undefined ? (live ? "In progress" : "")
            : round !== undefined && round <= completedRound ? "Completed"
            : round === liveRound ? "In progress" : "Awaiting playback";
          if (round !== undefined) previousRound = round;
          const isHuman = turn.speaker_id === "human";
          const agent = agentMap.get(turn.speaker_id);
          const name = isHuman ? "You" : (agent?.name ?? turn.speaker_id);
          const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
          return (
            <Fragment key={index}>
              {showRound && <div className="chat-log__round-divider">
                <span className="chat-log__round-divider-line" />
                <span className="chat-log__round-divider-text">Round {round}{roundStatus && ` - ${roundStatus}`}</span>
                <span className="chat-log__round-divider-line" />
              </div>}
              <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
                {isHuman ? <span className="chat-log__human-avatar">You</span> :
                  <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent, state?.moderator_strategy_id) : ""} alt="" width={32} height={32} />}
                <div className="chat-log__body">
                  <span className="chat-log__name">{name}</span>
                  <p className="chat-log__message">{turn.message}</p>
                </div>
              </div>
              {turn.visual && (!visibleVisualIds || visibleVisualIds.has(`${round}-${turn.speaker_id}`)) && <VisualCard visual={turn.visual} agentColor={color} agentName={name} />}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

function Playground({ catalog, initialMode, onModeChange, participant, onSetupBack, onReturnToEntry }: { catalog: PersonalityCatalog; initialMode: "debate" | "data"; onModeChange: (mode: "debate" | "data") => void; participant: boolean; onSetupBack: () => void; onReturnToEntry: () => void }) {
  const isDataMode = initialMode === "data";
  const OCEAN_SCALE = catalog.scale;
  const OCEAN_TRAITS = catalog.traits;
  const PERSONALITY_PRESETS = catalog.presets;
  const getPersonalityPreset = (id: string) => findPreset(catalog, id);
  const createPersonalityFromPreset = (
    id: string,
    overrides: Parameters<typeof clonePreset>[2] = {},
  ) => clonePreset(catalog, id, overrides);
  const [state, setStateValue] = useState<State | null>(null);
  const [topicInput, setTopicInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [personaInput, setPersonaInput] = useState("");
  const [energyInput, setEnergyInput] = useState(0.6);
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [displaySeconds, setDisplaySeconds] = useState(12);
  const [activeTurnIdx, setActiveTurnIdx] = useState<number>(-1);
  const [showReactions, setShowReactions] = useState(false);
  const [liveTurns, setLiveTurns] = useState<PublicTurn[]>([]);
  const [liveRound, setLiveRound] = useState(0);
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [appPhase, setAppPhase] = useState<AppPhase>("setup");
  const [setupStep, setSetupStep] = useState<"team" | "moderator">("team");
  const [draftAgents, setDraftAgents] = useState<DraftAgent[]>([]);
  const draftBaseRef = useRef<State | null>(null);
  const [testChatAgent, setTestChatAgent] = useState<DraftAgent | null>(null);
  const [personalityConfig, setPersonalityConfig] = useState(() => createPersonalityFromPreset(catalog.default_preset_id));
  const datasetInfo = state?.dataset_preview ?? null;
  const [uploading, setUploading] = useState(false);
  const [editingDraftIndex, setEditingDraftIndex] = useState<number | null>(null);
  const [chairSettingsOpen, setChairSettingsOpen] = useState(false);
  const [moderatorStrategies, setModeratorStrategies] = useState<ModeratorStrategy[]>([]);
  const [chairSaving, setChairSaving] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [topicSaving, setTopicSaving] = useState(false);
  const topicSaveRef = useRef<Promise<boolean> | null>(null);
  const launchPendingRef = useRef(false);
  const rosterFileRef = useRef<HTMLInputElement>(null);
  const [sidePanelView, setSidePanelView] = useState<"controls" | "log">("controls");
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false);
  const [interveneInput, setInterveneInput] = useState("");
  const [intervening, setIntervening] = useState(false);
  const [endConfirmationOpen, setEndConfirmationOpen] = useState(false);
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const [endSummary, setEndSummary] = useState<EndSummary | null>(null);
  const arenaStartedAtRef = useRef<number | null>(null);
  const [accumulatedHighlights, setAccumulatedHighlights] = useState<CellHighlight[]>([]);
  const [accumulatedAnnotations, setAccumulatedAnnotations] = useState<CellAnnotation[]>([]);
  const [agentTablePositions, setAgentTablePositions] = useState<Map<string, { agentId: string; row: number; column: string }>>(new Map());
  const fullDatasetRows = datasetInfo?.sample_rows ?? [];
  const previewColumns = useMemo(() => datasetInfo?.columns.map((column) => column.name) ?? [], [datasetInfo]);
  const [dashboardMode, setDashboardMode] = useState(false);
  const [agentFocus, setAgentFocus] = useState<AgentFocus | null>(null);
  const visibleAgentPositions = useMemo(() => new Map([...agentTablePositions].filter(([, pos]) => Number.isInteger(pos.row) && pos.row >= 0 && pos.row < fullDatasetRows.length && previewColumns.includes(pos.column))), [agentTablePositions, fullDatasetRows.length, previewColumns]);
  const [dashboardVisuals, setDashboardVisuals] = useState<DashboardVisual[]>([]);
  const [completedRound, setCompletedRound] = useState(0);
  const [revealedContribution, setRevealedContribution] = useState<{ round: number; index: number } | null>(null);
  const playbackRoundRef = useRef(0);
  const { speak, stop: stopTTS } = useTTS();

  useEffect(() => {
    if (!voiceEnabled) stopTTS();
  }, [voiceEnabled, stopTTS]);

  const [isAdmin] = useState<boolean>(() => {
    const params = new URLSearchParams(window.location.search);
    const key = participant ? null : params.get("adminKey") ?? params.get("admin");
    setAdminKey(key);
    return Boolean(key);
  });

  const historyRef = useRef<HTMLDivElement>(null);
  const appPhaseRef = useRef(appPhase);
  appPhaseRef.current = appPhase;
  const stateRef = useRef<State | null>(state);
  stateRef.current = state;
  const playbackSettings = useRef({ displaySeconds, voiceEnabled });
  playbackSettings.current = { displaySeconds, voiceEnabled };
  const playbackHandlers = useRef({ snapshot: applyStateSnapshot, show: showContribution });
  playbackHandlers.current = { snapshot: applyStateSnapshot, show: showContribution };
  const playbackRef = useRef<PlaybackController | null>(null);
  if (!playbackRef.current) playbackRef.current = new PlaybackController({
    duration: () => playbackSettings.current.displaySeconds,
    speak: (turn) => {
      const speaker = stateRef.current?.agents.find((agent) => agent.id === turn.speaker_id);
      return playbackSettings.current.voiceEnabled && speaker
        ? speak(turn.message, agentVoiceParams(speaker)) : Promise.resolve();
    },
    stopAudio: stopTTS,
    requestRound: async (signal) => (await runRounds(1, signal)).state,
    snapshot: (snapshot) => playbackHandlers.current.snapshot(snapshot),
    contribution: (turn, round, index) => playbackHandlers.current.show(turn, round, index),
    completed: (round) => {
      setCompletedRound(round.round_number);
      setLiveTurns((prev) => pendingHumanTurns(prev, stateRef.current?.human_request ?? ""));
      setActiveTurnIdx(round.turns.length - 1);
      setShowReactions(true);
    },
    busy: setRunning,
    autoChanged: setAutoRun,
    error: setError,
  });
  const playback = playbackRef.current;

  function showContribution(next: PublicTurn, turnRoundNum: number, index: number) {
    setShowReactions(false);
    setLiveRound(turnRoundNum);
    setRevealedContribution({ round: turnRoundNum, index });
    if (stateRef.current?.dataset_preview && turnRoundNum >= 3 && playbackRoundRef.current < 3) setDashboardMode(true);
    playbackRoundRef.current = turnRoundNum;
    setLiveTurns((prev) => [...prev, next]);
    // Determine if this turn belongs to a dashboard round (3+)
    const isDashboardRound = turnRoundNum >= 3;

    // Accumulate table actions from this turn (only in table mode, rounds 1-2)
    if (next.table_action && !isDashboardRound) {
      const ta = next.table_action;
      if (ta.navigate_to) {
        setAgentTablePositions((prev) => {
          const updated = new Map(prev);
          updated.set(next.speaker_id, {
            agentId: next.speaker_id,
            row: ta.navigate_to.row,
            column: ta.navigate_to.column,
          });
          return updated;
        });
      }
      if (ta.highlights?.length) {
        setAccumulatedHighlights((prev) => [...prev, ...ta.highlights]);
      }
      if (ta.annotations?.length) {
        setAccumulatedAnnotations((prev) => [...prev, ...ta.annotations]);
      }
    }

    // Reveal visuals only when their contribution is displayed.
    if (next.visual && next.speaker_id !== "human") {
      const speakerId = next.speaker_id;
      // Skip mediator/chair agents — they don't get dashboard cards
      const speakerAgent = stateRef.current?.agents?.find(
        (a: Agent) => a.id === speakerId
      );
      if (speakerAgent?.role !== "mediator") {
        setDashboardVisuals((prev) => {
          // Look up agent info from the state snapshot in the pending round
          const agents = stateRef.current?.agents ?? [];
          const agent = agents.find((a: Agent) => a.id === speakerId);
          const color = agent ? agentColor(agent) : "#38bdf8";
          const dv: DashboardVisual = {
            id: `${turnRoundNum}-${speakerId}`,
            roundNumber: turnRoundNum,
            speakerId,
            agentName: agent?.name ?? "Unknown",
            agentColor: color,
            visual: next.visual!,
            message: next.message,
          };
          const filtered = prev.filter((v) => v.id !== dv.id);
          return [...filtered, dv];
        });
      }
    }
  }

  function clearTurnQueue() {
    playback.cancel();
    setLiveTurns([]);
    setActiveTurnIdx(-1);
    setShowReactions(false);
    setRevealedContribution(null);
  }

  useEffect(() => {
    if (appPhase !== "arena") clearTurnQueue();
    else playback.resume();
  }, [appPhase]);

  const roundHistory: WsRoundEvent[] = useMemo(() => {
    if (!state) return [];
    return (state.rounds ?? []).map((round) => ({
      type: "round",
      round_result: round,
      metrics: round.metrics,
      state_snapshot: state,
    }));
  }, [state]);

  const activeModeratorName = moderatorStrategies.find(
    (strategy) => strategy.id === (state?.moderator_strategy_id ?? "consensus"),
  )?.name ?? "Moderator";

  const metrics: Metrics | null = useMemo(() => {
    const roundMetric = roundHistory[roundHistory.length - 1]?.metrics;
    if (roundMetric) return roundMetric;
    const snapshot = state?.world_state?.metrics;
    if (snapshot && typeof snapshot === "object") return snapshot as Metrics;
    return null;
  }, [roundHistory, state]);

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    (state?.agents ?? []).forEach((agent) => map.set(agent.id, agent));
    return map;
  }, [state]);

  const storedDashboardVisuals = useMemo<DashboardVisual[]>(() => {
    return roundHistory.flatMap((roundEvent) =>
      roundEvent.round_result.turns
        .filter((_, index) => roundEvent.round_result.round_number <= completedRound || (
          roundEvent.round_result.round_number === revealedContribution?.round && index <= revealedContribution.index
        ))
        .filter((turn) => turn.visual && turn.speaker_id !== "human")
        .map((turn) => {
          const agent = agentMap.get(turn.speaker_id);
          return {
            id: `${roundEvent.round_result.round_number}-${turn.speaker_id}`,
            roundNumber: roundEvent.round_result.round_number,
            speakerId: turn.speaker_id,
            agentName: agent?.name ?? "Unknown",
            agentColor: agent ? agentColor(agent) : "#38bdf8",
            visual: turn.visual!,
            message: turn.message,
          };
        }),
    );
  }, [agentMap, roundHistory, completedRound, revealedContribution]);

  const visibleDashboardVisuals = useMemo(() => {
    const storedIds = new Set(storedDashboardVisuals.map((visual) => visual.id));
    return [
      ...storedDashboardVisuals,
      ...dashboardVisuals.filter((visual) => !storedIds.has(visual.id)),
    ];
  }, [dashboardVisuals, storedDashboardVisuals]);

  const visibleVisualIds = useMemo(() => new Set(visibleDashboardVisuals.map((visual) => visual.id)), [visibleDashboardVisuals]);
  const analysisRound = revealedContribution?.round ?? completedRound;

  const latestRound = useMemo(() => {
    return roundHistory.find((round) => round.round_result.round_number === completedRound) ?? null;
  }, [roundHistory, completedRound]);

  const latestTurns = useMemo(() => {
    return latestRound?.round_result.turns ?? [];
  }, [latestRound]);

  const currentTurn = useMemo(() => {
    if (liveTurns.length > 0) return liveTurns[liveTurns.length - 1];
    if (activeTurnIdx < 0 || activeTurnIdx >= latestTurns.length) return null;
    return latestTurns[activeTurnIdx] ?? null;
  }, [liveTurns, latestTurns, activeTurnIdx]);

  const pastTurns = useMemo(() => {
    if (liveTurns.length > 1) return liveTurns.slice(0, -1);
    if (liveTurns.length > 0) return [];
    if (activeTurnIdx > 0) return latestTurns.slice(0, activeTurnIdx);
    return [];
  }, [liveTurns, latestTurns, activeTurnIdx]);

  const currentSpeakerId = currentTurn?.speaker_id ?? null;

  // Derive highlighted columns from current turn's message
  const highlightedColumns = useMemo(() => {
    const result = new Set<string>();
    if (!currentTurn || !datasetInfo) return result;
    const message = currentTurn.message.toLowerCase();
    for (const col of datasetInfo.columns) {
      const colName = col.name.toLowerCase();
      if (message.includes(colName)) {
        result.add(col.name);
      }
      const spacedName = colName.replace(/_/g, " ");
      if (spacedName !== colName && message.includes(spacedName)) {
        result.add(col.name);
      }
    }
    return result;
  }, [currentTurn, datasetInfo]);

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
    const params = new URLSearchParams(window.location.search);
    const demoName = participant ? null : params.get("demo");

    if (demoName) {
      // Auto-load example dataset + agents from ?demo= param
      loadExample(demoName)
        .then((result) => {
          if (!applyStateSnapshot(result.state)) return;
          setTopicInput(result.state.topic);
          setActiveTurnIdx(-1);
          setShowReactions(false);
          setLiveTurns([]);
          clearTurnQueue();
          setDraftAgents(result.state.agents.filter((agent) => agent.role === "user").map(draftFromAgent));
          draftBaseRef.current = result.state;
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : `Failed to load example: ${demoName}`);
        });
    } else {
      getState()
        .then((data) => {
          if (!applyStateSnapshot(data)) return;
          setTopicInput(data.topic);
          if (isAdmin) {
            setDraftAgents(data.agents.filter((agent) => agent.role === "user").map(draftFromAgent));
            draftBaseRef.current = data;
          }
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : "Failed to load state");
        });
    }

    getModeratorStrategies()
      .then((data) => setModeratorStrategies(data.strategies))
      .catch(() => setModeratorStrategies([]));

    const close = createWsClient(
      (event: WsEvent) => {
        if (event.type === "lobby") {
          if (participant && event.mode) onModeChange(event.mode);
          return;
        }
        if (event.type === "state") {
          applyStateSnapshot(event.state_snapshot, event.reset_playback);
          return;
        }
        if (event.type === "session_ended") {
          showEndOverview(event.summary);
          return;
        }
        if (event.type === "playback_settings") {
          setDisplaySeconds(event.display_seconds);
          return;
        }
        if (event.type === "turn") {
          if (stateRef.current?.run_id !== event.run_id) return;
          // Human interventions are shown locally on submit — skip WebSocket echo
          if (event.turn.speaker_id === "human") return;
          // Auto-transition students to arena when debate starts
          if (participant && appPhaseRef.current === "setup") {
            setAppPhase("arena");
            playback.resume();
          }
          if (appPhaseRef.current === "arena" || participant) {
            playback.turn(event.run_id, event.round_number, event.contribution_index ?? -1, event.turn);
          }
          return;
        }
        applyStateSnapshot(event.state_snapshot);
      },
      (status) => setConnection(status)
    );

    return () => {
      close();
      clearTurnQueue();
    };
  }, []);

  // Auto-scroll center stage history to bottom so recent turns are visible
  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [liveTurns.length, activeTurnIdx]);

  const userAgents = (state?.agents ?? []).filter(a => a.role === "user");
  const hasAgents = userAgents.length > 0;
  const completedRoundCount = authoritativeRoundCount(state);
  const setupLocked = isAdmin && (running || completedRoundCount > 0);
  const canContinueToModerator = Boolean(
    (topicInput.trim() || datasetInfo) && draftAgents.length >= MIN_USER_AGENTS,
  );

  const selectedPersonalityPreset = useMemo(
    () => getPersonalityPreset(personalityConfig.preset_id),
    [personalityConfig.preset_id],
  );

  function applyStateSnapshot(snapshot: State, resetPlayback = false): boolean {
    const previous = stateRef.current;
    if (!acceptsSnapshot(previous, snapshot)) return false;
    const newRun = previous !== null && previous.run_id !== snapshot.run_id;
    if (draftBaseRef.current && sameRoster(draftBaseRef.current, snapshot)) {
      draftBaseRef.current = snapshot;
    } else if (isAdmin && draftBaseRef.current) {
      const additions = rosterAdditions(draftBaseRef.current, snapshot);
      if (additions) {
        setDraftAgents((drafts) => [...drafts, ...additions.map(draftFromAgent)]);
        draftBaseRef.current = snapshot;
      }
    }
    if (newRun || resetPlayback) {
      clearTurnQueue();
      if (resetPlayback) setError("The round was interrupted. Playback has stopped; you can retry the round.");
      setDashboardVisuals([]);
    }
    if (newRun) {
      setAutoRun(false);
      setAppPhase("setup");
      setSetupStep("team");
      setTopicInput(snapshot.topic);
      setDashboardMode(false);
      setSidePanelView("controls");
      if (!sameRoster(previous!, snapshot)) {
        setDraftAgents(snapshot.agents.filter((agent) => agent.role === "user").map(draftFromAgent));
        draftBaseRef.current = snapshot;
        setEditingDraftIndex(null);
      }
    }
    stateRef.current = snapshot;
    setStateValue(snapshot);
    const baseline = previous === null || newRun || resetPlayback;
    if (baseline) {
      const savedRound = snapshot.rounds?.[snapshot.rounds.length - 1];
      const round = savedRound?.round_number ?? snapshot.round_number;
      setCompletedRound(round);
      setLiveRound(round);
      setAgentFocus(null);
      playbackRoundRef.current = round;
      setDashboardMode(Boolean(snapshot.dataset_preview && round >= 3));
      setDashboardVisuals([]);
      setActiveTurnIdx(savedRound ? savedRound.turns.length - 1 : -1);
      const actions = snapshot.public_history.flatMap((turn) => turn.table_action ? [{ turn, action: turn.table_action }] : []);
      setAccumulatedHighlights(actions.flatMap(({ action }) => action.highlights));
      setAccumulatedAnnotations(actions.flatMap(({ action }) => action.annotations));
      setAgentTablePositions(new Map(actions.map(({ turn, action }) => [turn.speaker_id, { agentId: turn.speaker_id, ...action.navigate_to }])));
      if (previous === null && savedRound) setAppPhase("arena");
    }
    playback.sync(snapshot, baseline);
    return true;
  }

  function updatePersonalityPreset(presetId: string) {
    setPersonalityConfig(createPersonalityFromPreset(presetId));
  }

  function updateOceanTrait(trait: keyof typeof personalityConfig.ocean, value: number) {
    setPersonalityConfig((prev) => ({
      ...prev,
      ocean: { ...prev.ocean, [trait]: value },
    }));
  }

  function updateCustomInstructions(value: string) {
    setPersonalityConfig((prev) => ({ ...prev, custom_instructions: value }));
  }

  function resetPersonalityDefaults() {
    setPersonalityConfig((prev) => createPersonalityFromPreset(prev.preset_id, {
      custom_instructions: prev.custom_instructions,
    }));
  }

  async function onChairStrategyChange(strategyId: string) {
    setError("");
    setChairSaving(true);
    try {
      const result = await setModeratorStrategy(strategyId);
      applyStateSnapshot(result.state);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update Chair strategy");
    } finally {
      setChairSaving(false);
    }
  }

  function onAddDraftAgent(event: FormEvent) {
    event.preventDefault();
    if (!nameInput.trim() || !personaInput.trim()) return;
    if (!draftBaseRef.current) draftBaseRef.current = stateRef.current;
    const draft: DraftAgent = {
      id: editingDraftIndex === null ? undefined : draftAgents[editingDraftIndex]?.id,
      name: nameInput.trim(),
      persona_text: personaInput.trim(),
      energy: energyInput,
      personality: personalityConfig,
    };
    setDraftAgents((prev) => {
      if (editingDraftIndex === null) return [...prev, draft];
      return prev.map((agent, idx) => idx === editingDraftIndex ? draft : agent);
    });
    setNameInput("");
    setPersonaInput("");
    setEnergyInput(0.6);
    setPersonalityConfig(createPersonalityFromPreset(catalog.default_preset_id));
    setEditingDraftIndex(null);
  }

  async function onSubmitAgent(event: FormEvent) {
    event.preventDefault();
    if (!nameInput.trim() || !personaInput.trim()) return;
    setError("");
    try {
      const result = await addAgents([{ name: nameInput.trim(), persona_text: personaInput.trim(), energy: energyInput, personality: personalityConfig }]);
      applyStateSnapshot(result.state);
      setNameInput("");
      setPersonaInput("");
      setEnergyInput(0.6);
      setPersonalityConfig(createPersonalityFromPreset(catalog.default_preset_id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to submit agent");
    }
  }

  function removeDraftAgent(idx: number) {
    setDraftAgents((prev) => prev.filter((_, i) => i !== idx));
    if (editingDraftIndex === idx) {
      setEditingDraftIndex(null);
      setNameInput("");
      setPersonaInput("");
      setEnergyInput(0.6);
      setPersonalityConfig(createPersonalityFromPreset(catalog.default_preset_id));
    } else if (editingDraftIndex !== null && editingDraftIndex > idx) {
      setEditingDraftIndex(editingDraftIndex - 1);
    }
  }

  function editDraftAgent(idx: number) {
    const agent = draftAgents[idx];
    if (!agent) return;
    setEditingDraftIndex(idx);
    setNameInput(agent.name);
    setPersonaInput(agent.persona_text);
    setEnergyInput(agent.energy);
    setPersonalityConfig(agent.personality);
  }

  function openTestChat(agent: DraftAgent) {
    setTestChatAgent(agent);
  }

  async function launchArena() {
    if (launchPendingRef.current || (!topicInput.trim() && !datasetInfo) || !stateRef.current) return;
    setError("");
    launchPendingRef.current = true;
    setLaunching(true);
    try {
      const expected = draftBaseRef.current ?? stateRef.current;
      if (expected.run_id !== stateRef.current.run_id || expected.revision !== stateRef.current.revision) {
        throw new Error("The roster changed in another request. Reload the page before saving.");
      }
      const drafts = draftAgents;
      const result = await syncAgents(drafts, expected);
      if (!applyStateSnapshot(result.state)) return;
      setDraftAgents(result.state.agents.filter((agent) => agent.role === "user").map(draftFromAgent));
      draftBaseRef.current = result.state;
      arenaStartedAtRef.current = Date.now();
      setAppPhase("arena");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to launch arena");
    } finally {
      launchPendingRef.current = false;
      setLaunching(false);
    }
  }

  async function persistTopic(topic: string): Promise<boolean> {
    if (!topic || stateRef.current?.topic === topic) return true;
    if (topicSaveRef.current) {
      await topicSaveRef.current;
      return persistTopic(topic);
    }
    setTopicSaving(true);
    const request = setTopic(topic).then(({ state: nextState }) => {
      if (!applyStateSnapshot(nextState)) return false;
      draftBaseRef.current = nextState;
      return true;
    });
    topicSaveRef.current = request;
    try {
      return await request;
    } finally {
      if (topicSaveRef.current === request) topicSaveRef.current = null;
      setTopicSaving(false);
    }
  }

  async function onTopicBlur() {
    setError("");
    try {
      await persistTopic(topicInput.trim());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update discussion topic");
    }
  }

  async function continueToModerator() {
    if (!canContinueToModerator) return;
    setError("");
    try {
      if (!datasetInfo && !await persistTopic(topicInput.trim())) return;
      setSetupStep("moderator");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update discussion topic");
    }
  }

  async function onImportAgents(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    try {
      const imported = parseAgentRoster(await file.text(), catalog);
      if (draftAgents.length + imported.length > MAX_AGENTS) {
        throw new Error(`Importing these agents would exceed the limit of ${MAX_AGENTS}.`);
      }
      setDraftAgents((current) => [...current, ...imported]);
      draftBaseRef.current = stateRef.current;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to import agents");
    }
  }

  function onRun(rounds: number) {
    setError("");
    playback.run(rounds);
  }

  function onDisplaySecondsChange(value: number) {
    if (!Number.isFinite(value)) return;
    const seconds = Math.min(300, Math.max(1, Math.round(value)));
    setDisplaySeconds(seconds);
    void setContributionDisplayTime(seconds).catch((e: unknown) => {
      setError(e instanceof Error ? e.message : "Could not update display time");
    });
  }

  async function onReset() {
    clearTurnQueue();
    setError("");
    try {
      const result = await reset(topicInput.trim() || undefined);
      if (!applyStateSnapshot(result.state)) return;
      setAutoRun(false);
      setActiveTurnIdx(-1);
      setShowReactions(false);
      setLiveTurns([]);
      clearTurnQueue();
      setAppPhase("setup");
      setDraftAgents([]);
      draftBaseRef.current = result.state;
      setAccumulatedHighlights([]);
      setAccumulatedAnnotations([]);
      setAgentTablePositions(new Map());
      setDashboardMode(false);
      setDashboardVisuals([]);
      setSidePanelView("controls");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reset failed");
    }
  }

  function showEndOverview(summary: EndSummary) {
    const startedAt = arenaStartedAtRef.current ?? Date.now();
    clearTurnQueue();
    playback.auto(false);
    stopTTS();
    setVoiceEnabled(false);
    setEndConfirmationOpen(false);
    setConfirmingEnd(false);
    setAppPhase("arena");
    setEndSummary(summary);
  }

  async function onConfirmEnd() {
    if (running || confirmingEnd) return;
    const startedAt = arenaStartedAtRef.current ?? Date.now();
    setConfirmingEnd(true);
    setError("");
    try {
      const result = await endSession((Date.now() - startedAt) / 1000);
      showEndOverview(result.summary);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not end the session");
      setConfirmingEnd(false);
    }
  }

  function onEndReturnToEntry() {
    clearTurnQueue();
    setEndSummary(null);
    onReturnToEntry();
  }

  function formatDuration(totalSeconds: number): string {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return hours > 0
      ? `${hours}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`
      : `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  }

  async function onIntervene(event: FormEvent) {
    event.preventDefault();
    if (!interveneInput.trim() || intervening) return;
    const msg = interveneInput.trim();
    setError("");
    try {
      setIntervening(true);
      const result = await intervene(msg);
      if (!applyStateSnapshot(result.state)) return;
      // Show immediately in center stage and logs (don't wait for WebSocket)
      const turn: PublicTurn = { speaker_id: "human", message: msg };
      setLiveTurns((prev) => [...prev, turn]);
      setInterveneInput("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to send message");
    } finally {
      setIntervening(false);
    }
  }

  async function onLoadDemo() {
    setError("");
    try {
      if (topicSaveRef.current) await topicSaveRef.current;
      const result = await loadDemo();
      if (!applyStateSnapshot(result.state)) return;
      setTopicInput(result.state.topic);
      setDraftAgents(result.added.map((agent) => {
        const { id, ...draft } = draftFromAgent(agent);
        return draft;
      }));
      draftBaseRef.current = result.state;
      setActiveTurnIdx(-1);
      setShowReactions(false);
      setLiveTurns([]);
      clearTurnQueue();
      setAccumulatedHighlights([]);
      setAccumulatedAnnotations([]);
      setAgentTablePositions(new Map());
      setDashboardMode(false);
      setDashboardVisuals([]);
      setSidePanelView("controls");
      setAppPhase("setup");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load debate preset");
    }
  }

  async function onLoadDataDemo() {
    setError("");
    try {
      const result = await loadExample("ExampleDataset1");
      if (!applyStateSnapshot(result.state)) return;
      setTopicInput(result.state.topic);
      setActiveTurnIdx(-1);
      setShowReactions(false);
      setLiveTurns([]);
      clearTurnQueue();
      setDraftAgents(result.state.agents.filter((agent) => agent.role === "user").map(draftFromAgent));
      draftBaseRef.current = result.state;
      setEditingDraftIndex(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load data demo");
    }
  }

  async function onDatasetUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setUploading(true);
    try {
      const result = await uploadDataset(file);
      if (!applyStateSnapshot(result.state)) return;
      setTopicInput(result.state.topic);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to upload dataset");
    } finally {
      setUploading(false);
    }
  }

  const missionActions = isAdmin ? <div className="setup-toolbar" aria-label="Setup actions">
    <button className="btn-demo" onClick={isDataMode ? onLoadDataDemo : onLoadDemo}>{isDataMode ? "Load Data Analysis Demo" : "Load Debate Preset"}</button>
    <button className="launch-button" onClick={continueToModerator} disabled={!canContinueToModerator}>{topicSaving ? "Saving Topic..." : "Continue to Moderator"}</button>
  </div> : null;
  const participantBriefingValue = state?.topic
    ? isDataMode ? state.topic.replace(/^Analyze the uploaded dataset:\s*/i, "") : state.topic
    : "";

  const missionBriefing = <section className="mission-briefing section-block setup-pixel-panel">
    <div className="mission-briefing__copy">
      <span className="mode-label">{isDataMode ? "Data Analysis Mode" : "Debate Mode"}</span>
      <h2 className="section-title">Mission Briefing</h2>
    </div>
    {isAdmin && <div className="mission-briefing__control">
      {!isDataMode ? <div className="stacked-form">
        <label className="form-label" htmlFor="discussion-topic">Discussion Topic</label>
        <div className="mission-briefing__input-row">
          <textarea id="discussion-topic" value={topicInput} onChange={(e) => setTopicInput(e.target.value)} onBlur={() => void onTopicBlur()} rows={2} placeholder="What should the agents debate about?" />
          {missionActions}
        </div>
      </div> : <div className="stacked-form">
        <label className="form-label" htmlFor="dataset-upload">Dataset Upload / Selection</label>
        <div className="mission-briefing__input-row">
          <input id="dataset-upload" type="file" accept=".csv,.xlsx,.xls" onChange={onDatasetUpload} disabled={uploading} />
          {missionActions}
        </div>
        {uploading && <p className="upload-status">Uploading and parsing...</p>}
        {datasetInfo && <div className="dataset-preview">
          <p className="dataset-preview__summary">{datasetInfo.filename} &mdash; {datasetInfo.shape[0]} rows x {datasetInfo.shape[1]} columns</p>
          <div className="dataset-columns" tabIndex={0} role="region" aria-label="Dataset columns">{datasetInfo.columns.map((col, i) => <span key={i} className="arena-node__quirk">{col.name} [{col.dtype}]{col.null_count > 0 ? ` (${col.null_count} nulls)` : ""}</span>)}</div>
        </div>}
      </div>}
    </div>}
    {participant && participantBriefingValue && <div className="mission-briefing__participant-value">
      <span>{isDataMode ? "Dataset" : "Discussion Topic"}</span>
      <p className="mission-briefing__topic">{participantBriefingValue}</p>
    </div>}
  </section>;

  return (
    <div className={`app-shell app-shell--${initialMode}`}>
      {/* ---- HUD HEADER ---- */}
      {appPhase === "setup" ? (
        <SetupHeader onBack={setupStep === "moderator" ? () => setSetupStep("team") : onSetupBack} busy={setupStep === "team" && setupLocked} sessionCode={isAdmin ? getSessionId() : undefined} backAccessory={setupStep === "team" ? missionBriefing : undefined}>
          {participant && (
            <div className="setup-header-round" aria-label={`Round ${completedRoundCount}`}>
              <span>ROUND</span><strong>{completedRoundCount}</strong>
            </div>
          )}
          <div className={`status ${connection}`}>
            <span className="status__dot" />
            {connection === "connected" ? "ONLINE" : "OFFLINE"}
          </div>
        </SetupHeader>
      ) : (
      <header className="topbar">
        <div className="topbar__identity">
          <button type="button" className="topbar__back" disabled={setupLocked} onClick={() => { setSetupStep("moderator"); setAppPhase("setup"); }} title={setupLocked ? "Setup is locked after the first round starts" : "Back to moderator selection"}><ArrowIcon direction="left" /> BACK</button>
          <Brand className="topbar__brand" />
          <h1 className="topbar__title" title={state?.topic ?? "The Arena"}>{state?.topic || "The Arena"}</h1>
        </div>
        <div className="topbar__right">
          {appPhase === "arena" && (
            <button
              className={`voice-toggle${voiceEnabled ? " voice-toggle--active" : ""}`}
              onClick={() => { setVoiceEnabled(v => !v); if (voiceEnabled) stopTTS(); }}
              title={voiceEnabled ? "Disable voice" : "Enable voice"}
            >
              {voiceEnabled ? "\uD83D\uDD0A" : "\uD83D\uDD07"}
            </button>
          )}
          <div className="round-counter">
            <span className="round-counter__label">Round</span>
            <span className="round-counter__value">{completedRoundCount}</span>
          </div>
          <div className={`status ${connection}`}>
            <span className="status__dot" />
            {connection === "connected" ? "ONLINE" : "OFFLINE"}
          </div>
        </div>
      </header>
      )}

      {error && <div className="error-banner">{error}</div>}

      {/* ================================================================
          SETUP PHASE
          ================================================================ */}
      {appPhase === "setup" ? (
        <main className="setup-screen">
          {setupStep === "moderator" && isAdmin ? (
            <ModeratorSelection
              strategies={moderatorStrategies}
              selectedId={state?.moderator_strategy_id ?? "consensus"}
              saving={chairSaving}
              launching={launching}
              onSelect={onChairStrategyChange}
              onBack={() => setSetupStep("team")}
              onEnter={launchArena}
            />
          ) : <>
          <div className="setup-phase">
          {/* ---- LEFT COLUMN: Agent Creator ---- */}
          <section className="setup-left">

            {/* Agent Creator */}
            <div className="section-block agent-creation setup-pixel-panel">
              <div className="settings-header">
                <h2 className="section-title">{editingDraftIndex === null ? "Add / Edit Agents" : "Edit Agent"}</h2>
              </div>
              <form onSubmit={isAdmin ? onAddDraftAgent : onSubmitAgent} className="stacked-form">
                <fieldset className="agent-creation__group">
                <legend>Identity</legend>
                <label className="form-label" htmlFor="agent-name">Agent Name</label>
                <input id="agent-name" value={nameInput} onChange={(e) => setNameInput(e.target.value)} placeholder="Name your agent..." />

                <label className="form-label" htmlFor="agent-persona">Persona (1-2 lines)</label>
                <textarea id="agent-persona" value={personaInput} onChange={(e) => setPersonaInput(e.target.value)} rows={2} placeholder="Describe their personality and perspective..." />
                </fieldset>

                <fieldset className="agent-creation__group">
                <legend>Personality</legend>
                <label className="form-label" htmlFor="agent-personality">Personality Preset</label>
                <select id="agent-personality" value={personalityConfig.preset_id} onChange={(e) => updatePersonalityPreset(e.target.value)}>
                  {PERSONALITY_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>{preset.name}</option>
                  ))}
                </select>

                <div className="personality-summary">
                  <p>{selectedPersonalityPreset.description}</p>
                  <small>{personalityConfig.role_goal}</small>
                </div>

                  <div className="ocean-panel" role="group" aria-labelledby="ocean-heading">
                    <div className="agent-creation__ocean-heading"><h3 id="ocean-heading">OCEAN traits</h3><span>{OCEAN_SCALE.min}–{OCEAN_SCALE.max}</span></div>
                    {OCEAN_TRAITS.map((trait) => (
                      <label className={`ocean-trait trait--${trait.key}`} key={trait.key}>
                        <span className="ocean-trait__label">{trait.label}</span>
                        <input
                          type="range"
                          min={OCEAN_SCALE.min}
                          max={OCEAN_SCALE.max}
                          step={1}
                          value={personalityConfig.ocean[trait.key]}
                          onChange={(e) => updateOceanTrait(trait.key, Number(e.target.value))}
                        />
                        <span className="ocean-trait__value">{personalityConfig.ocean[trait.key]}</span>
                      </label>
                    ))}
                    <button type="button" className="agent-creation__reset" onClick={resetPersonalityDefaults}>Reset to preset defaults</button>
                  </div>

                  <label className="ocean-trait trait--energy" htmlFor="agent-energy">
                    <span className="ocean-trait__label">Energy</span>
                    <input
                      id="agent-energy"
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={energyInput}
                      onChange={(e) => setEnergyInput(Number(e.target.value))}
                    />
                    <span className="ocean-trait__value">{Math.round(energyInput * 100)}%</span>
                  </label>
                </fieldset>

                <fieldset className="agent-creation__group">
                <legend>Additional details</legend>
                <label className="form-label" htmlFor="agent-instructions">Additional Instructions (optional)</label>
                <textarea
                  id="agent-instructions"
                  value={personalityConfig.custom_instructions}
                  onChange={(e) => updateCustomInstructions(e.target.value)}
                  rows={2}
                  placeholder="Add behavior notes for this agent..."
                />
                </fieldset>

                <button type="submit" className="btn-primary" disabled={!nameInput.trim() || !personaInput.trim()}>
                  {isAdmin ? (editingDraftIndex === null ? "Add to Roster" : "Save Agent") : "Submit Agent"}
                </button>
                {isAdmin && editingDraftIndex !== null && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingDraftIndex(null);
                      setNameInput("");
                      setPersonaInput("");
                      setEnergyInput(0.6);
                      setPersonalityConfig(createPersonalityFromPreset(catalog.default_preset_id));
                    }}
                  >
                    Cancel Edit
                  </button>
                )}
              </form>
            </div>
          </section>

          {/* ---- RIGHT COLUMN: Roster ---- */}
          <section className="setup-right">
            {!participant ? (
              /* Admin: draft roster (local agents before launch) */
              <div className="section-block agent-roster setup-pixel-panel">
                <div className="agent-roster__header">
                  <h2 className="section-title">
                    Agent Roster
                    <span className="section-title__count">{draftAgents.length} / {MIN_USER_AGENTS} minimum</span>
                  </h2>
                  <div className="agent-roster__actions">
                    <input ref={rosterFileRef} type="file" accept="application/json,.json" onChange={onImportAgents} hidden />
                    <button type="button" onClick={() => rosterFileRef.current?.click()}>Import</button>
                    <button type="button" onClick={() => downloadAgentRoster(draftAgents)} disabled={!draftAgents.length}>Export</button>
                  </div>
                </div>

                {draftAgents.length === 0 ? (
                  <div className="roster-empty">No agents yet. Create one to get started.</div>
                ) : (
                  <div className="draft-roster">
                    {draftAgents.map((agent, idx) => (
                      <AgentCard key={idx} agent={agent} catalog={catalog}>
                          <button className="btn-test" onClick={() => editDraftAgent(idx)}>Edit</button>
                          <button className="btn-test" onClick={() => openTestChat(agent)}>Test</button>
                          <button className="btn-remove" aria-label={`Remove ${agent.name}`} onClick={() => removeDraftAgent(idx)}>Remove</button>
                        </AgentCard>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* Student: show agents already on the server */
              <div className="section-block agent-roster setup-pixel-panel">
                <h2 className="section-title">
                  Agents in Arena
                  <span className="section-title__count">{userAgents.length}</span>
                </h2>

                {userAgents.length === 0 ? (
                  <div className="roster-empty">No agents submitted yet. Add yours!</div>
                ) : (
                  <div className="draft-roster">
                    {userAgents.map((agent) => (
                      <AgentCard key={agent.id} agent={agent} catalog={catalog}>
                          <button className="btn-test" onClick={() => openTestChat(draftFromAgent(agent))}>Test</button>
                        </AgentCard>
                    ))}
                  </div>
                )}
                <p style={{ color: "#b8a9c6", fontSize: "0.85rem", marginTop: "1rem", textAlign: "center" }}>
                  Waiting for the debate to begin...
                </p>
              </div>
            )}

          </section>
          </div>
          <SetupProgress activeStep={1} />
          </>}
        </main>
      ) : (
        /* ================================================================
           ARENA PHASE
           ================================================================ */
        <main className="arena-layout">
          {/* ---- ARENA VIEWPORT ---- */}
          <section className={`arena-viewport${isDataMode ? " arena-viewport--data" : ""}${dashboardMode ? " arena-viewport--dashboard" : datasetInfo && fullDatasetRows.length > 0 ? " arena-viewport--table" : ""}`}>
            {isDataMode && <div className="data-view-toolbar">
              <div className="arena-view-switch">
              <button
                type="button"
                className={`control-tab${!dashboardMode ? " control-tab--active" : ""}`}
                onClick={() => setDashboardMode(false)}
              >
                Dataset
              </button>
              <button
                type="button"
                className={`control-tab${dashboardMode ? " control-tab--active" : ""}`}
                onClick={() => setDashboardMode(true)}
              >
                Dashboard
              </button>
              </div>
              {(state?.round_number ?? 0) <= completedRound && !!state?.world_state?.dashboard_narrative && <p className="data-analysis-focus">{String(state.world_state.dashboard_narrative)}</p>}
              <span className="data-round-status">{analysisRound ? 'Round ' + analysisRound + (analysisRound > completedRound ? ' - In progress' : ' - Completed') : 'Ready'}</span>
            </div>}
            {isDataMode && <>
            <div className="data-discussion-header"><DataAgentStrip agents={state?.agents ?? []} positions={visibleAgentPositions}
              moderatorStrategyId={state?.moderator_strategy_id}
              currentSpeakerId={analysisRound > completedRound ? currentSpeakerId : null}
              onLocate={(agentId) => { setDashboardMode(false); setAgentFocus((previous) => ({ agentId, request: (previous?.request ?? 0) + 1 })); }} />
              {state && <div className="data-agent-speech"><DataContribution state={state} turn={currentTurn} active={analysisRound > completedRound} pastTurns={pastTurns} /></div>}
            </div>
            {!dashboardMode && datasetInfo && <div className="data-preview-caption">
              {fullDatasetRows.length} of {datasetInfo.shape[0]} rows{fullDatasetRows.length < datasetInfo.shape[0] ? ' - navigation within preview' : ''}
              {analysisRound >= 3 && <span>Earlier exploration (rounds 1-2)</span>}
            </div>}
            </>}
            {dashboardMode ? (
              /* ---- DASHBOARD CANVAS ---- */
              <>
                <DashboardCanvas
                  visuals={visibleDashboardVisuals}
                  agents={state?.agents ?? []}
                  agentMap={agentMap}
                  currentTurn={currentTurn}
                  currentRound={analysisRound}
                  completedRound={completedRound}
                />
                {/* Intervention Input Bar */}
                <form className="intervention-bar" onSubmit={onIntervene}>
                  <input
                    className="intervention-bar__input"
                    value={interveneInput}
                    onChange={(e) => setInterveneInput(e.target.value)}
                    placeholder="Type a message to intervene in the discussion..."
                    disabled={intervening}
                    maxLength={500}
                  />
                  <button
                    className="intervention-bar__send"
                    type="submit"
                    disabled={intervening || !interveneInput.trim()}
                  >
                    Send
                  </button>
                </form>
              </>
            ) : datasetInfo ? (
              /* ---- DATA TABLE ARENA ---- */
              <>
                <ArenaTable
                  rows={fullDatasetRows}
                  columns={previewColumns}
                  agents={state?.agents ?? []}
                  currentTurn={analysisRound >= 3 ? null : currentTurn}
                  accumulatedHighlights={accumulatedHighlights}
                  accumulatedAnnotations={accumulatedAnnotations}
                  focus={agentFocus}
                  agentPositions={visibleAgentPositions}
                  agentMap={agentMap}
                />
                {/* Intervention Input Bar */}
                <form className="intervention-bar" onSubmit={onIntervene}>
                  <input
                    className="intervention-bar__input"
                    value={interveneInput}
                    onChange={(e) => setInterveneInput(e.target.value)}
                    placeholder="Type a message to intervene in the discussion..."
                    disabled={intervening}
                    maxLength={500}
                  />
                  <button
                    className="intervention-bar__send"
                    type="submit"
                    disabled={intervening || !interveneInput.trim()}
                  >
                    Send
                  </button>
                </form>
              </>
            ) : (
              /* ---- CIRCULAR ARENA (fallback for non-dataset mode) ---- */
              <>
                <div className="arena-ring">
                  {agentPositions.map(({ agent, x, y }) => {
                    const isSpeaking = currentSpeakerId === agent.id;
                    const hasSomeoneActive = currentSpeakerId !== null;
                    const color = agentColor(agent);
                    const isHovered = hoveredAgentId === agent.id;
                    const visibleTurns = liveTurns.length > 0 ? liveTurns : latestTurns;
                    const lastMsg = visibleTurns.slice().reverse().find(t => t.speaker_id === agent.id)?.message ?? null;
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
                        onMouseEnter={() => setHoveredAgentId(agent.id)}
                        onMouseLeave={() => setHoveredAgentId(null)}
                      >
                        <div className="arena-node__avatar-wrap">
                          <img className="arena-node__avatar" src={agentAvatarUrl(agent, state?.moderator_strategy_id)} alt={agent.name} width={64} height={64} />
                          {agent.role === "mediator"
                            ? <span className="arena-node__personality-badge">{activeModeratorName}</span>
                            : agent.personality && <span className="arena-node__personality-badge">{agent.personality.role_name}</span>}
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

                        {showReactions && latestRound?.round_result.reactions
                          .filter(r => r.agent_id === agent.id)
                          .map((reaction, ri) => (
                            <div className="arena-reaction-bubble" key={ri}>
                              <span className="arena-reaction-bubble__text">{reaction.micro_comment}</span>
                            </div>
                          ))
                        }

                        {isHovered && lastMsg && !isSpeaking && (
                          <div className="agent-tooltip">
                            <p className="agent-tooltip__message">{lastMsg}</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Center Stage */}
                <div className="center-stage">
                  {currentTurn ? (
                    <div className="center-stage__content">
                      {pastTurns.length > 0 && (
                        <div className="center-stage__history" ref={historyRef}>
                          {pastTurns.map((turn, i) => (
                            <p className={`center-stage__past-turn${turn.speaker_id === "human" ? " center-stage__past-turn--human" : ""}`} key={i}>
                              <strong>{turn.speaker_id === "human" ? "You" : (agentMap.get(turn.speaker_id)?.name ?? "?")}: </strong>
                              {turn.message}
                            </p>
                          ))}
                        </div>
                      )}
                      <div className={`center-stage__speaker${currentTurn.speaker_id === "human" ? " center-stage__speaker--human" : ""}`}>
                        {currentTurn.speaker_id === "human" ? (
                          <span className="center-stage__speaker-avatar center-stage__human-icon">You</span>
                        ) : agentMap.get(currentTurn.speaker_id) ? (
                          <img
                            className="center-stage__speaker-avatar"
                            src={agentAvatarUrl(agentMap.get(currentTurn.speaker_id)!, state?.moderator_strategy_id)}
                            alt=""
                            width={40}
                            height={40}
                          />
                        ) : null}
                        <span className="center-stage__speaker-name">
                          {currentTurn.speaker_id === "human" ? "You" : (agentMap.get(currentTurn.speaker_id)?.name ?? currentTurn.speaker_id)}
                        </span>
                      </div>
                      <p className="center-stage__message" key={`turn-${currentTurn.speaker_id}-${pastTurns.length}`}>
                        {currentTurn.message}
                      </p>
                      {currentTurn.visual && (() => {
                        const speaker = agentMap.get(currentTurn.speaker_id);
                        const color = speaker ? agentColor(speaker) : "#38bdf8";
                        return (
                          <div className="center-stage__visual">
                            <VisualCard
                              visual={currentTurn.visual}
                              agentColor={color}
                              agentName={speaker?.name ?? "Unknown"}
                            />
                          </div>
                        );
                      })()}
                    </div>
                  ) : (
                    <div className="center-stage__empty">
                      <div className="center-stage__empty-icon">{"\u2694\uFE0F"}</div>
                      <div className="center-stage__empty-text">Awaiting combatants...</div>
                      <div className="center-stage__empty-sub">Run a round to begin the debate.</div>
                    </div>
                  )}
                </div>
                {/* Intervention Input Bar */}
                <form className="intervention-bar" onSubmit={onIntervene}>
                  <input
                    className="intervention-bar__input"
                    value={interveneInput}
                    onChange={(e) => setInterveneInput(e.target.value)}
                    placeholder="Type a message to intervene in the discussion..."
                    disabled={intervening}
                    maxLength={500}
                  />
                  <button
                    className="intervention-bar__send"
                    type="submit"
                    disabled={intervening || !interveneInput.trim()}
                  >
                    Send
                  </button>
                </form>
              </>
            )}
          </section>

          {/* ---- RIGHT COLUMN: Chat Log or Side Panel ---- */}
          {hasAgents && sidebarCollapsed ? (
            <aside className={`chat-log-panel${mobilePanelOpen ? " mobile-panel-open" : ""}`}>
              <button type="button" className="arena-mobile-panel-toggle" aria-expanded={mobilePanelOpen} onClick={() => setMobilePanelOpen((open) => !open)}>{mobilePanelOpen ? "Close discussion" : "Open discussion"}</button>
              <div className="chat-log-panel__header">
                <span className="section-title">Discussion</span>
                <button className="sidebar-toggle" onClick={() => setSidebarCollapsed(false)} title="Show controls">{"\u2630"}</button>
              </div>
              <ConversationLog state={state} liveTurns={liveTurns} liveRound={liveRound} agentMap={agentMap} visibleVisualIds={isDataMode ? visibleVisualIds : undefined} completedRound={isDataMode ? completedRound : undefined} />
              {isAdmin && (
                <div className="chat-log-panel__controls">
                  <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1</button>
                  <button disabled={running} onClick={() => onRun(5)}>Run 5</button>
                  <button onClick={() => downloadLogs().catch(() => setError("Download failed"))}>Download Log</button>
                  <button className="btn-end" disabled={running} onClick={() => setEndConfirmationOpen(true)}>End</button>
                  <button className="btn-danger" onClick={onReset}>Reset</button>
                </div>
              )}
            </aside>
          ) : (
            <aside className={`side-panel${mobilePanelOpen ? " mobile-panel-open" : ""}`}>
              <button type="button" className="arena-mobile-panel-toggle" aria-expanded={mobilePanelOpen} onClick={() => setMobilePanelOpen((open) => !open)}>{mobilePanelOpen ? "Close controls" : "Open controls"}</button>
              {/* Tab selector */}
              <div className="control-tabs" style={{ marginBottom: "8px" }}>
                <button type="button" className={`control-tab${sidePanelView === "controls" ? " control-tab--active" : ""}`}
                  onClick={() => setSidePanelView("controls")}>
                  Controls
                </button>
                <button type="button" className={`control-tab${sidePanelView === "log" ? " control-tab--active" : ""}`}
                  onClick={() => setSidePanelView("log")}>
                  Conversation Log
                </button>
              </div>

              {sidePanelView === "controls" ? (
                <>
                  {/* Command Center (admin only) */}
                  {isAdmin && (
                    <div className="section-block">
                      <h2 className="section-title">Command Center</h2>
                      <div className="button-row">
                        <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1</button>
                        <button disabled={running} onClick={() => onRun(5)}>Run 5</button>
                        <button onClick={() => downloadLogs().catch(() => setError("Download failed"))}>Download Log</button>
                        <button className="btn-end" disabled={running} onClick={() => setEndConfirmationOpen(true)}>End</button>
                        <button className="btn-danger" onClick={onReset}>Reset</button>
                      </div>
                      <div className="control-row">
                        <label className="toggle-row">
                          <input type="checkbox" checked={autoRun} onChange={(e) => playback.auto(e.target.checked)} className="toggle-input" />
                          <span className="toggle-switch" />
                          <span className="toggle-label">Auto-Run</span>
                        </label>
                      </div>
                      <div className="control-row">
                        <label className="form-label" htmlFor="contribution-display-time">Display time per contribution (s)</label>
                        <input id="contribution-display-time" type="number" min={1} max={300} step={1} value={displaySeconds} onChange={(e) => onDisplaySecondsChange(Number(e.target.value))} />
                      </div>
                    </div>
                  )}

                  {/* Simulation Info */}
                  <div className="section-block">
                    <h2 className="section-title">Simulation Info</h2>
                    <div className="info-grid">
                      <div className="info-item">
                        <span className="info-label">Round</span>
                        <span className="info-value">{completedRoundCount}</span>
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

                  {/* Battle Metrics */}
                  <div className="section-block">
                    <h2 className="section-title">Battle Metrics</h2>
                    {metrics ? (
                      <div className="metrics">
                        {!!metrics.evaluation?.excluded_fallback_turns && (
                          <p role="status">{metrics.evaluation.excluded_fallback_turns} fallback turns excluded. {metrics.evaluation.status === "insufficient_data" ? "Not enough valid participant data for comparison." : ""}</p>
                        )}
                        <div className="metric-row">
                          <span className="metric-label">Consensus</span>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill metric-bar-fill--consensus" style={{ width: `${(metrics.consensus_score ?? 0) * 100}%` }} />
                          </div>
                          <span className="metric-value">{metricValue(metrics.consensus_score)}</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Polarization</span>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill metric-bar-fill--polarization" style={{ width: `${(metrics.polarization_score ?? 0) * 100}%` }} />
                          </div>
                          <span className="metric-value">{metricValue(metrics.polarization_score)}</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Civility</span>
                          <div className="metric-bar-track">
                            <div className="metric-bar-fill metric-bar-fill--civility" style={{ width: `${(metrics.civility_score ?? 0) * 100}%` }} />
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

                </>
              ) : (
                <ConversationLog state={state} liveTurns={liveTurns} liveRound={liveRound} agentMap={agentMap} visibleVisualIds={isDataMode ? visibleVisualIds : undefined} completedRound={isDataMode ? completedRound : undefined} />
              )}
            </aside>
          )}

          {endConfirmationOpen && !endSummary && (
            <div className="arena-end-layer" role="presentation">
              <section className="arena-end-dialog arena-end-dialog--confirm" role="alertdialog" aria-modal="true" aria-labelledby="end-confirm-title" aria-describedby="end-confirm-description">
                <span className="arena-end-dialog__eyebrow">End session</span>
                <h2 id="end-confirm-title">End this {isDataMode ? "analysis" : "debate"}?</h2>
                <p id="end-confirm-description">No further rounds can be started after you continue. The session log will remain available in the overview.</p>
                <div className="arena-end-dialog__actions">
                  <button type="button" disabled={confirmingEnd} onClick={() => setEndConfirmationOpen(false)}>Cancel</button>
                  <button type="button" className="btn-end" disabled={confirmingEnd} onClick={() => void onConfirmEnd()}>{confirmingEnd ? "Ending..." : "End session"}</button>
                </div>
              </section>
            </div>
          )}

          {endSummary && (
            <div className="arena-end-layer arena-end-layer--overview">
              <section className="arena-end-dialog arena-end-overview" role="dialog" aria-modal="true" aria-labelledby="end-overview-title">
                <span className="arena-end-dialog__eyebrow">Session complete</span>
                <h2 id="end-overview-title">{endSummary.topic}</h2>
                <p className="arena-end-overview__intro">{isDataMode ? "Data analysis" : "Debate"} overview</p>
                <div className="arena-end-metrics" aria-label="Session metrics">
                  <div className="arena-end-metric"><span>Rounds</span><strong>{endSummary.rounds}</strong></div>
                  <div className="arena-end-metric"><span>Duration</span><strong>{formatDuration(endSummary.duration_seconds)}</strong></div>
                  <div className="arena-end-metric"><span>Contributions</span><strong>{endSummary.contributions}</strong></div>
                  <div className="arena-end-metric"><span>Agents</span><strong>{endSummary.agents}</strong></div>
                </div>
                 <div className="arena-end-dialog__actions arena-end-overview__actions">
                  <button type="button" onClick={() => downloadLogs().catch(() => setError("Download failed"))}>Download Log</button>
                  <button type="button" className="btn-primary" onClick={onEndReturnToEntry}>Back to Entry</button>
                </div>
              </section>
            </div>
          )}
        </main>
      )}

      {/* ================================================================
         TEST CHAT MODAL
         ================================================================ */}
      {testChatAgent && <TestChatModal
        agent={testChatAgent}
        onClose={() => setTestChatAgent(null)}
        onError={setError}
        speak={speak}
        stopAudio={stopTTS}
      />}
    </div>
  );
}
