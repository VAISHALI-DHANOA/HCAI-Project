import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { addAgentsWithMBTI, downloadLogs, getState, intervene, loadDemo, loadDataDemo, reset, runRounds, setAdminKey, setTopic, testChat, uploadDataset } from "./api";
import { createWsClient } from "./ws";
import type { ConnectionStatus } from "./ws";
import type { Agent, AppPhase, ChatMessage, DatasetInfo, DraftAgent, Metrics, PublicTurn, State, WsEvent, WsRoundEvent } from "./types";
import { VisualCard } from "./components/VisualCard";
import { DataPreviewTable } from "./components/DataPreviewTable";
import { MBTI_DIMENSIONS, MBTI_QUESTIONS, scoreQuestionnaire, enrichPersonaWithMBTI } from "./mbti";
import { useTTS, agentVoiceParams } from "./hooks/useTTS";
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
  const [activeTurnIdx, setActiveTurnIdx] = useState<number>(-1);
  const [showReactions, setShowReactions] = useState(false);
  const [liveTurns, setLiveTurns] = useState<PublicTurn[]>([]);
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [appPhase, setAppPhase] = useState<AppPhase>("setup");
  const [draftAgents, setDraftAgents] = useState<DraftAgent[]>([]);
  const [testChatAgent, setTestChatAgent] = useState<DraftAgent | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [mbtiMode, setMbtiMode] = useState<"pick" | "quiz">("pick");
  const [mbtiPicks, setMbtiPicks] = useState<string[]>(["E", "S", "T", "J"]);
  const [quizAnswers, setQuizAnswers] = useState<(number | null)[]>(Array(8).fill(null));
  const [inputMode, setInputMode] = useState<"topic" | "dataset">("topic");
  const [datasetInfo, setDatasetInfo] = useState<DatasetInfo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sidePanelView, setSidePanelView] = useState<"controls" | "dashboard">("controls");
  const [interveneInput, setInterveneInput] = useState("");
  const [intervening, setIntervening] = useState(false);
  const { speak, stop: stopTTS } = useTTS();

  const [isAdmin] = useState<boolean>(() => {
    const key = new URLSearchParams(window.location.search).get("admin");
    if (key) { setAdminKey(key); return true; }
    return false;
  });

  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  const chatLogRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const appPhaseRef = useRef(appPhase);
  appPhaseRef.current = appPhase;

  // Turn queue: incoming turns are queued and revealed one at a time
  // with 20s display + 3s gap between each message.
  const turnQueueRef = useRef<PublicTurn[]>([]);
  const pendingRoundRef = useRef<WsRoundEvent | null>(null);
  const displayTimerRef = useRef<number | null>(null);

  const processQueue = useCallback(() => {
    if (displayTimerRef.current !== null) return; // timer already active

    const next = turnQueueRef.current.shift();
    if (next) {
      setShowReactions(false);
      setLiveTurns((prev) => [...prev, next]);
      displayTimerRef.current = window.setTimeout(() => {
        displayTimerRef.current = null;
        processQueue();
      }, 12000); // 15s display + 3s gap
    } else if (pendingRoundRef.current) {
      // All turns displayed — finalize round after 15s for last turn
      const ev = pendingRoundRef.current;
      displayTimerRef.current = window.setTimeout(() => {
        displayTimerRef.current = null;
        pendingRoundRef.current = null;
        // Preserve human intervention turns across round boundaries
        setLiveTurns((prev) => prev.filter((t) => t.speaker_id === "human"));
        setActiveTurnIdx(ev.round_result.turns.length - 1);
        setShowReactions(true);
        setFeed((prev) => [...prev, ev]);
        setStateValue(ev.state_snapshot);
      }, 12000); // 15s display for last turn
    }
  }, []);

  function clearTurnQueue() {
    turnQueueRef.current = [];
    pendingRoundRef.current = null;
    if (displayTimerRef.current !== null) {
      clearTimeout(displayTimerRef.current);
      displayTimerRef.current = null;
    }
  }

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
        if (event.type === "turn") {
          // Human interventions are shown locally on submit — skip WebSocket echo
          if (event.turn.speaker_id === "human") return;
          // Auto-transition students to arena when debate starts
          if (!isAdmin && appPhaseRef.current === "setup") {
            setAppPhase("arena");
          }
          // Queue turn for timed reveal (20s display + 3s gap)
          setShowReactions(false);
          turnQueueRef.current.push(event.turn);
          processQueue();
          return;
        }
        // event.type === "round" — save for finalization after queue drains
        pendingRoundRef.current = event;
        processQueue();
      },
      (status) => setConnection(status)
    );

    return () => {
      close();
      clearTurnQueue();
    };
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

  // Speak current turn aloud when voice is enabled
  useEffect(() => {
    if (!voiceEnabled || !currentTurn) {
      stopTTS();
      return;
    }
    const speaker = agentMap.get(currentTurn.speaker_id);
    if (!speaker) return;
    speak(currentTurn.message, agentVoiceParams(speaker));
  }, [voiceEnabled, currentTurn, agentMap, speak, stopTTS]);

  // Auto-advance: after the round finishes (summary shown), start the next round
  useEffect(() => {
    if (!showReactions || running) return;
    const timer = setTimeout(() => {
      onRun(1);
    }, 15000);
    return () => clearTimeout(timer);
  }, [showReactions, running]);

  // Auto-scroll center stage history to bottom so recent turns are visible
  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [liveTurns.length, activeTurnIdx]);

  // Auto-scroll chat log when feed updates
  useEffect(() => {
    if (sidebarCollapsed && chatLogRef.current) {
      chatLogRef.current.scrollTo({ top: chatLogRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [feed, sidebarCollapsed]);

  // Auto-switch side panel to dashboard when dataset is present
  useEffect(() => {
    if (state?.dataset_summary) {
      setSidePanelView("dashboard");
    }
  }, [state?.dataset_summary]);

  const hasAgents = (state?.agents ?? []).filter(a => a.role === "user").length > 0;

  const currentMbtiType = useMemo(() => {
    if (mbtiMode === "pick") return mbtiPicks.join("");
    const allAnswered = quizAnswers.every((a) => a !== null);
    if (!allAnswered) return "";
    return scoreQuestionnaire(quizAnswers as number[]);
  }, [mbtiMode, mbtiPicks, quizAnswers]);

  const chatLogEndRef = useRef<HTMLDivElement>(null);

  // Scroll test chat to bottom when messages change
  useEffect(() => {
    chatLogEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

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

  function onAddDraftAgent(event: FormEvent) {
    event.preventDefault();
    if (!nameInput.trim() || !personaInput.trim() || !currentMbtiType) return;
    setDraftAgents((prev) => [
      ...prev,
      {
        name: nameInput.trim(),
        persona_text: personaInput.trim(),
        energy: energyInput,
        mbti_type: currentMbtiType,
      },
    ]);
    setNameInput("");
    setPersonaInput("");
    setEnergyInput(0.6);
    setMbtiPicks(["E", "S", "T", "J"]);
    setQuizAnswers(Array(8).fill(null));
    setMbtiMode("pick");
  }

  async function onSubmitAgent(event: FormEvent) {
    event.preventDefault();
    if (!nameInput.trim() || !personaInput.trim() || !currentMbtiType) return;
    setError("");
    try {
      const enriched = enrichPersonaWithMBTI(personaInput.trim(), currentMbtiType);
      await addAgentsWithMBTI([{ name: nameInput.trim(), persona_text: enriched, energy: energyInput, mbti_type: currentMbtiType }]);
      setNameInput("");
      setPersonaInput("");
      setEnergyInput(0.6);
      setMbtiPicks(["E", "S", "T", "J"]);
      setQuizAnswers(Array(8).fill(null));
      setMbtiMode("pick");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to submit agent");
    }
  }

  function removeDraftAgent(idx: number) {
    setDraftAgents((prev) => prev.filter((_, i) => i !== idx));
  }

  function openTestChat(agent: DraftAgent) {
    setTestChatAgent(agent);
    setChatMessages([]);
    setChatInput("");
  }

  function closeTestChat() {
    stopListening();
    stopTTS();
    setTestChatAgent(null);
    setChatMessages([]);
    setChatInput("");
  }

  const sendTestMessage = useCallback(async (overrideMessage?: string) => {
    const msg = overrideMessage ?? chatInput;
    if (!testChatAgent || !msg.trim() || chatLoading) return;
    const userMsg = msg.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setChatLoading(true);
    try {
      const enrichedPersona = enrichPersonaWithMBTI(testChatAgent.persona_text, testChatAgent.mbti_type);
      const result = await testChat(
        testChatAgent.name,
        enrichedPersona,
        testChatAgent.mbti_type,
        chatMessages.map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content })),
        userMsg
      );
      setChatMessages((prev) => [...prev, { role: "agent", content: result.reply }]);
      // Speak the agent's reply aloud when input was via voice
      if (overrideMessage) {
        const agentSeed = testChatAgent.name.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
        speak(result.reply, { voiceIndex: agentSeed });
      }
    } catch (e: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { role: "agent", content: "(Error: could not reach agent)" },
      ]);
    } finally {
      setChatLoading(false);
    }
  }, [testChatAgent, chatInput, chatLoading, chatMessages, speak]);

  const sendTestMessageRef = useRef(sendTestMessage);
  sendTestMessageRef.current = sendTestMessage;

  function startListening() {
    const SpeechRecognitionAPI = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionAPI || chatLoading) return;
    const recognition = new SpeechRecognitionAPI();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event: any) => {
      const transcript: string = event.results[0][0].transcript;
      sendTestMessageRef.current(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  function stopListening() {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setListening(false);
  }

  async function launchArena() {
    if ((!topicInput.trim() && !datasetInfo) || draftAgents.length === 0) return;
    setError("");
    try {
      // In dataset mode the topic was already set by the upload endpoint
      if (!datasetInfo) {
        await setTopic(topicInput.trim());
      }
      const enrichedAgents = draftAgents.map((a) => ({
        ...a,
        persona_text: enrichPersonaWithMBTI(a.persona_text, a.mbti_type),
      }));
      const result = await addAgentsWithMBTI(enrichedAgents);
      setStateValue(result.state);
      setFeed([]);
      if (datasetInfo) setSidePanelView("dashboard");
      setAppPhase("arena");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to launch arena");
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
      setLiveTurns([]);
      clearTurnQueue();
      setAppPhase("setup");
      setDraftAgents([]);
      setDatasetInfo(null);
      setInputMode("topic");
      setSidePanelView("controls");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reset failed");
    }
  }

  async function onIntervene(event: FormEvent) {
    event.preventDefault();
    if (!interveneInput.trim() || intervening) return;
    const msg = interveneInput.trim();
    setError("");
    try {
      setIntervening(true);
      await intervene(msg);
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
      const result = await loadDemo();
      setStateValue(result.state);
      setTopicInput(result.state.topic);
      setFeed([]);
      setActiveTurnIdx(-1);
      setShowReactions(false);
      setLiveTurns([]);
      clearTurnQueue();
      setDatasetInfo(null);
      setAppPhase("arena");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load demo");
    }
  }

  async function onLoadDataDemo() {
    setError("");
    try {
      const result = await loadDataDemo();
      setStateValue(result.state);
      setTopicInput(result.state.topic);
      setFeed([]);
      setActiveTurnIdx(-1);
      setShowReactions(false);
      setLiveTurns([]);
      clearTurnQueue();
      if (result.parsed) {
        setDatasetInfo(result.parsed);
      }
      setSidePanelView("dashboard");
      setAppPhase("arena");
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
      setStateValue(result.state);
      setTopicInput(result.state.topic);
      setDatasetInfo(result.parsed);
      setFeed([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to upload dataset");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="app-shell">
      {/* ---- HUD HEADER ---- */}
      <header className="topbar">
        <h1 className="topbar__title" title={state?.topic ?? "The Arena"}>{state?.topic || "The Arena"}</h1>
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
            <span className="round-counter__value">{state?.round_number ?? 0}</span>
          </div>
          <div className={`status ${connection}`}>
            <span className="status__dot" />
            {connection === "connected" ? "ONLINE" : "OFFLINE"}
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {/* ================================================================
          SETUP PHASE
          ================================================================ */}
      {appPhase === "setup" ? (
        <main className="setup-phase">
          {/* ---- LEFT COLUMN: Topic + Agent Creator ---- */}
          <section className="setup-left">
            {/* Topic or Dataset (admin only) */}
            {isAdmin && (
              <div className="section-block">
                <h2 className="section-title">Mission Briefing</h2>
                <div className="mbti-tabs" style={{ marginBottom: "8px" }}>
                  <button type="button" className={`mbti-tab${inputMode === "topic" ? " mbti-tab--active" : ""}`}
                    onClick={() => setInputMode("topic")}>
                    Text Topic
                  </button>
                  <button type="button" className={`mbti-tab${inputMode === "dataset" ? " mbti-tab--active" : ""}`}
                    onClick={() => setInputMode("dataset")}>
                    Upload Dataset
                  </button>
                </div>

                {inputMode === "topic" ? (
                  <form onSubmit={onTopicSubmit} className="stacked-form">
                    <label className="form-label">Discussion Topic</label>
                    <textarea
                      value={topicInput}
                      onChange={(e) => setTopicInput(e.target.value)}
                      rows={2}
                      placeholder="What should the agents debate about?"
                    />
                    <button type="submit">Set Topic</button>
                  </form>
                ) : (
                  <div className="stacked-form">
                    <label className="form-label">CSV or Excel File</label>
                    <input type="file" accept=".csv,.xlsx,.xls" onChange={onDatasetUpload} disabled={uploading} />
                    {uploading && <p style={{ color: "#94a3b8", fontSize: "0.82rem" }}>Uploading and parsing...</p>}
                    {datasetInfo && (
                      <div className="dataset-preview">
                        <p style={{ color: "#4ade80", fontSize: "0.82rem", margin: "4px 0" }}>
                          {datasetInfo.filename} &mdash; {datasetInfo.shape[0]} rows x {datasetInfo.shape[1]} columns
                        </p>
                        <div className="dataset-columns">
                          {datasetInfo.columns.map((col, i) => (
                            <span key={i} className="arena-node__quirk">
                              {col.name} [{col.dtype}]{col.null_count > 0 ? ` (${col.null_count} nulls)` : ""}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {/* Show current topic for students */}
            {!isAdmin && state?.topic && (
              <div className="section-block">
                <h2 className="section-title">Discussion Topic</h2>
                <p style={{ color: "#94a3b8", margin: "0.5rem 0" }}>{state.topic}</p>
              </div>
            )}

            {/* Agent Creator */}
            <div className="section-block">
              <h2 className="section-title">Create Agent</h2>
              <form onSubmit={isAdmin ? onAddDraftAgent : onSubmitAgent} className="stacked-form">
                <label className="form-label">Agent Name</label>
                <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} placeholder="Name your agent..." />

                <label className="form-label">Persona (1-2 lines)</label>
                <textarea value={personaInput} onChange={(e) => setPersonaInput(e.target.value)} rows={2} placeholder="Describe their personality and perspective..." />

                <label className="form-label">Energy: {energyInput.toFixed(2)}</label>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={energyInput}
                  onChange={(e) => setEnergyInput(Number(e.target.value))}
                />

                {/* MBTI Mode Tabs */}
                <label className="form-label">Personality Type (MBTI)</label>
                <div className="mbti-tabs">
                  <button type="button" className={`mbti-tab${mbtiMode === "pick" ? " mbti-tab--active" : ""}`} onClick={() => setMbtiMode("pick")}>
                    Pick MBTI
                  </button>
                  <button type="button" className={`mbti-tab${mbtiMode === "quiz" ? " mbti-tab--active" : ""}`} onClick={() => setMbtiMode("quiz")}>
                    Questionnaire
                  </button>
                </div>

                {mbtiMode === "pick" ? (
                  <div className="mbti-picker">
                    {MBTI_DIMENSIONS.map((dim, di) => (
                      <div className="mbti-dimension" key={di}>
                        <span className="mbti-dimension__label">{dim.label}</span>
                        <div className="mbti-toggle-pair">
                          {dim.options.map((opt, oi) => (
                            <button
                              key={opt}
                              type="button"
                              className={`mbti-toggle__option${mbtiPicks[di] === opt ? " mbti-toggle__option--active" : ""}`}
                              onClick={() => setMbtiPicks((prev) => { const next = [...prev]; next[di] = opt; return next; })}
                              title={dim.descriptions[oi]}
                            >
                              {dim.fullLabels[oi]}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mbti-questionnaire">
                    {MBTI_QUESTIONS.map((q, qi) => (
                      <div className="mbti-question" key={qi}>
                        <p className="mbti-question__text">{q.question}</p>
                        <div className="mbti-question__choices">
                          <button
                            type="button"
                            className={`mbti-choice${quizAnswers[qi] === 0 ? " mbti-choice--selected" : ""}`}
                            onClick={() => setQuizAnswers((prev) => { const next = [...prev]; next[qi] = 0; return next; })}
                          >
                            {q.choiceA}
                          </button>
                          <button
                            type="button"
                            className={`mbti-choice${quizAnswers[qi] === 1 ? " mbti-choice--selected" : ""}`}
                            onClick={() => setQuizAnswers((prev) => { const next = [...prev]; next[qi] = 1; return next; })}
                          >
                            {q.choiceB}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {currentMbtiType && <div className="mbti-badge">{currentMbtiType}</div>}

                <button type="submit" className="btn-primary" disabled={!nameInput.trim() || !personaInput.trim() || !currentMbtiType}>
                  {isAdmin ? "Add to Roster" : "Submit Agent"}
                </button>
              </form>
            </div>
          </section>

          {/* ---- RIGHT COLUMN: Roster ---- */}
          <section className="setup-right">
            {isAdmin ? (
              /* Admin: draft roster (local agents before launch) */
              <div className="section-block">
                <h2 className="section-title">
                  Agent Roster
                  <span className="section-title__count">{draftAgents.length}</span>
                </h2>

                {draftAgents.length === 0 ? (
                  <div className="roster-empty">No agents yet. Create one to get started.</div>
                ) : (
                  <div className="draft-roster">
                    {draftAgents.map((agent, idx) => (
                      <div className="draft-agent-card" key={idx}>
                        <img
                          className="draft-agent-card__avatar"
                          src={`https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.name)}`}
                          alt={agent.name}
                          width={48}
                          height={48}
                        />
                        <div className="draft-agent-card__info">
                          <div className="draft-agent-card__header">
                            <span className="draft-agent-card__name">{agent.name}</span>
                            <span className="mbti-badge mbti-badge--small">{agent.mbti_type}</span>
                          </div>
                          <p className="draft-agent-card__persona">{agent.persona_text}</p>
                          <div className="draft-agent-card__energy-bar">
                            <div className="draft-agent-card__energy-fill" style={{ width: `${agent.energy * 100}%` }} />
                          </div>
                        </div>
                        <div className="draft-agent-card__actions">
                          <button className="btn-test" onClick={() => openTestChat(agent)}>Test</button>
                          <button className="btn-remove" onClick={() => removeDraftAgent(idx)}>X</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* Student: show agents already on the server */
              <div className="section-block">
                <h2 className="section-title">
                  Agents in Arena
                  <span className="section-title__count">{(state?.agents ?? []).filter(a => a.role === "user").length}</span>
                </h2>

                {(state?.agents ?? []).filter(a => a.role === "user").length === 0 ? (
                  <div className="roster-empty">No agents submitted yet. Add yours!</div>
                ) : (
                  <div className="draft-roster">
                    {(state?.agents ?? []).filter(a => a.role === "user").map((agent) => (
                      <div className="draft-agent-card" key={agent.id}>
                        <img
                          className="draft-agent-card__avatar"
                          src={agentAvatarUrl(agent)}
                          alt={agent.name}
                          width={48}
                          height={48}
                        />
                        <div className="draft-agent-card__info">
                          <div className="draft-agent-card__header">
                            <span className="draft-agent-card__name">{agent.name}</span>
                            {agent.mbti_type && <span className="mbti-badge mbti-badge--small">{agent.mbti_type}</span>}
                          </div>
                          <div className="draft-agent-card__energy-bar">
                            <div className="draft-agent-card__energy-fill" style={{ width: `${agent.energy * 100}%` }} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <p style={{ color: "#64748b", fontSize: "0.85rem", marginTop: "1rem", textAlign: "center" }}>
                  Waiting for the debate to begin...
                </p>
              </div>
            )}

            {/* Action Buttons (admin only) */}
            {isAdmin && (
            <div className="setup-actions">
              <button className="btn-demo" onClick={onLoadDemo}>Load Debate Demo</button>
              <button className="btn-demo" onClick={onLoadDataDemo}>Load Data Analysis Demo</button>
              <button
                className="launch-button"
                onClick={launchArena}
                disabled={(!topicInput.trim() && !datasetInfo) || draftAgents.length === 0}
              >
                Launch into Arena
              </button>
            </div>
            )}
          </section>
        </main>
      ) : (
        /* ================================================================
           ARENA PHASE
           ================================================================ */
        <main className="arena-layout">
          {/* ---- ARENA VIEWPORT ---- */}
          <section className="arena-viewport">
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
                      <img className="arena-node__avatar" src={agentAvatarUrl(agent)} alt={agent.name} width={64} height={64} />
                      {agent.role === "mediator" && <span className="arena-node__role-badge">MOD</span>}
                      {agent.mbti_type && <span className="arena-node__mbti-badge">{agent.mbti_type}</span>}
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
                          <span className="arena-reaction-bubble__emoji">{reaction.emoji}</span>
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
                        src={agentAvatarUrl(agentMap.get(currentTurn.speaker_id)!)}
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
          </section>

          {/* ---- RIGHT COLUMN: Chat Log or Side Panel ---- */}
          {hasAgents && sidebarCollapsed ? (
            <aside className="chat-log-panel">
              <div className="chat-log-panel__header">
                <h2 className="section-title">Conversation Log</h2>
                <button className="sidebar-toggle" onClick={() => setSidebarCollapsed(false)} title="Show controls">{"\u2630"}</button>
              </div>
              <div className="chat-log" ref={chatLogRef}>
                {feed.length === 0 && liveTurns.length === 0 && (
                  <div className="chat-log__empty">No conversations yet. Run a round to begin.</div>
                )}
                {feed.map((roundEvent) => (
                  <div key={roundEvent.round_result.round_number}>
                    <div className="chat-log__round-divider">
                      <span className="chat-log__round-divider-line" />
                      <span className="chat-log__round-divider-text">Round {roundEvent.round_result.round_number}</span>
                      <span className="chat-log__round-divider-line" />
                    </div>
                    {roundEvent.round_result.turns.map((turn, ti) => {
                      const isHuman = turn.speaker_id === "human";
                      const agent = agentMap.get(turn.speaker_id);
                      const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
                      return (
                        <div key={ti}>
                          <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
                            {isHuman ? (
                              <span className="chat-log__human-avatar">You</span>
                            ) : (
                              <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent) : ""} alt="" width={32} height={32} />
                            )}
                            <div className="chat-log__body">
                              <span className="chat-log__name">{isHuman ? "You" : (agent?.name ?? "?")}</span>
                              <p className="chat-log__message">{turn.message}</p>
                            </div>
                          </div>
                          {turn.visual && (
                            <VisualCard visual={turn.visual} agentColor={color} agentName={agent?.name ?? "Unknown"} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
                {liveTurns.length > 0 && (
                  <div>
                    <div className="chat-log__round-divider">
                      <span className="chat-log__round-divider-line" />
                      <span className="chat-log__round-divider-text">Round {(state?.round_number ?? feed.length) || feed.length + 1}</span>
                      <span className="chat-log__round-divider-line" />
                    </div>
                    {liveTurns.map((turn, ti) => {
                      const isHuman = turn.speaker_id === "human";
                      const agent = agentMap.get(turn.speaker_id);
                      const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
                      return (
                        <div key={`live-${ti}`}>
                          <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
                            {isHuman ? (
                              <span className="chat-log__human-avatar">You</span>
                            ) : (
                              <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent) : ""} alt="" width={32} height={32} />
                            )}
                            <div className="chat-log__body">
                              <span className="chat-log__name">{isHuman ? "You" : (agent?.name ?? "?")}</span>
                              <p className="chat-log__message">{turn.message}</p>
                            </div>
                          </div>
                          {turn.visual && (
                            <VisualCard visual={turn.visual} agentColor={color} agentName={agent?.name ?? "Unknown"} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              {isAdmin && (
                <div className="chat-log-panel__controls">
                  <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1</button>
                  <button disabled={running} onClick={() => onRun(5)}>Run 5</button>
                  <button onClick={() => downloadLogs().catch(() => setError("Download failed"))}>Download Log</button>
                  <button className="btn-danger" onClick={onReset}>Reset</button>
                </div>
              )}
            </aside>
          ) : (
            <aside className="side-panel">
              {/* Tab selector */}
              <div className="mbti-tabs" style={{ marginBottom: "8px" }}>
                <button type="button" className={`mbti-tab${sidePanelView === "controls" ? " mbti-tab--active" : ""}`}
                  onClick={() => setSidePanelView("controls")}>
                  Controls
                </button>
                <button type="button" className={`mbti-tab${sidePanelView === "dashboard" ? " mbti-tab--active" : ""}`}
                  onClick={() => setSidePanelView("dashboard")}>
                  Dashboard
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
                        <button className="btn-danger" onClick={onReset}>Reset</button>
                      </div>
                      <div className="control-row">
                        <label className="toggle-row">
                          <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} className="toggle-input" />
                          <span className="toggle-switch" />
                          <span className="toggle-label">Auto-Run</span>
                        </label>
                      </div>
                      <div className="control-row">
                        <label className="form-label">Interval (ms)</label>
                        <input type="number" min={200} step={100} value={intervalMs} onChange={(e) => setIntervalMs(Number(e.target.value) || 1000)} />
                      </div>
                    </div>
                  )}

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

                  {/* Conversation Log */}
                  <div className="section-block section-block--log">
                    <h2 className="section-title">
                      Conversation Log
                      <span className="section-title__count">{feed.length}</span>
                    </h2>
                    <div className="chat-log" ref={chatLogRef}>
                      {feed.length === 0 && liveTurns.length === 0 && (
                        <div className="chat-log__empty">No conversations yet. Run a round to begin.</div>
                      )}
                      {feed.map((roundEvent) => (
                        <div key={roundEvent.round_result.round_number}>
                          <div className="chat-log__round-divider">
                            <span className="chat-log__round-divider-line" />
                            <span className="chat-log__round-divider-text">Round {roundEvent.round_result.round_number}</span>
                            <span className="chat-log__round-divider-line" />
                          </div>
                          {roundEvent.round_result.turns.map((turn, ti) => {
                            const isHuman = turn.speaker_id === "human";
                            const agent = agentMap.get(turn.speaker_id);
                            const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
                            return (
                              <div key={ti}>
                                <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
                                  {isHuman ? (
                                    <span className="chat-log__human-avatar">You</span>
                                  ) : (
                                    <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent) : ""} alt="" width={32} height={32} />
                                  )}
                                  <div className="chat-log__body">
                                    <span className="chat-log__name">{isHuman ? "You" : (agent?.name ?? "?")}</span>
                                    <p className="chat-log__message">{turn.message}</p>
                                  </div>
                                </div>
                                {turn.visual && (
                                  <VisualCard visual={turn.visual} agentColor={color} agentName={agent?.name ?? "Unknown"} />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ))}
                      {liveTurns.length > 0 && (
                        <div>
                          <div className="chat-log__round-divider">
                            <span className="chat-log__round-divider-line" />
                            <span className="chat-log__round-divider-text">Round {(state?.round_number ?? feed.length) || feed.length + 1}</span>
                            <span className="chat-log__round-divider-line" />
                          </div>
                          {liveTurns.map((turn, ti) => {
                            const isHuman = turn.speaker_id === "human";
                            const agent = agentMap.get(turn.speaker_id);
                            const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
                            return (
                              <div key={`live-${ti}`}>
                                <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} style={{ "--agent-color": color } as React.CSSProperties}>
                                  {isHuman ? (
                                    <span className="chat-log__human-avatar">You</span>
                                  ) : (
                                    <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent) : ""} alt="" width={32} height={32} />
                                  )}
                                  <div className="chat-log__body">
                                    <span className="chat-log__name">{isHuman ? "You" : (agent?.name ?? "?")}</span>
                                    <p className="chat-log__message">{turn.message}</p>
                                  </div>
                                </div>
                                {turn.visual && (
                                  <VisualCard visual={turn.visual} agentColor={color} agentName={agent?.name ?? "Unknown"} />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                /* ---- Dashboard Tab: Visual Contributions ---- */
                <div className="section-block section-block--log">
                  <h2 className="section-title">Analysis Dashboard</h2>
                  {/* Admin controls row within dashboard */}
                  {isAdmin && (
                    <div className="button-row" style={{ marginBottom: "8px" }}>
                      <button className="btn-primary" disabled={running} onClick={() => onRun(1)}>Run 1</button>
                      <button disabled={running} onClick={() => onRun(5)}>Run 5</button>
                      <button className="btn-danger" onClick={onReset}>Reset</button>
                    </div>
                  )}
                  {/* Data Preview Table */}
                  {datasetInfo && (
                    <DataPreviewTable
                      datasetInfo={datasetInfo}
                      highlightedColumns={highlightedColumns}
                    />
                  )}
                  <div className="dashboard-section">
                    {feed.length === 0 ? (
                      <div className="chat-log__empty">No analysis yet. Run a round to begin.</div>
                    ) : (
                      feed.map((roundEvent) => {
                        const visuals = roundEvent.round_result.turns.filter(t => t.visual);
                        return (
                          <div className="dashboard-round-group" key={roundEvent.round_result.round_number}>
                            <div className="dashboard-round-label">Round {roundEvent.round_result.round_number}</div>
                            {/* Text summary for this round */}
                            {roundEvent.round_result.turns.map((turn, ti) => {
                              const isHuman = turn.speaker_id === "human";
                              const agent = agentMap.get(turn.speaker_id);
                              const color = isHuman ? "#10b981" : (agent ? agentColor(agent) : "#38bdf8");
                              return (
                                <div className={`chat-log__entry${isHuman ? " chat-log__entry--human" : ""}`} key={`text-${ti}`} style={{ "--agent-color": color } as React.CSSProperties}>
                                  {isHuman ? (
                                    <span className="chat-log__human-avatar">You</span>
                                  ) : (
                                    <img className="chat-log__avatar" src={agent ? agentAvatarUrl(agent) : ""} alt="" width={28} height={28} />
                                  )}
                                  <div className="chat-log__body">
                                    <span className="chat-log__name">{isHuman ? "You" : (agent?.name ?? "?")}</span>
                                    <p className="chat-log__message">{turn.message}</p>
                                  </div>
                                </div>
                              );
                            })}
                            {/* Visual contributions */}
                            {visuals.map((turn, ti) => {
                              const agent = agentMap.get(turn.speaker_id);
                              return (
                                <VisualCard
                                  key={`vis-${ti}`}
                                  visual={turn.visual!}
                                  agentColor={agent ? agentColor(agent) : "#38bdf8"}
                                  agentName={agent?.name ?? "Unknown"}
                                />
                              );
                            })}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </aside>
          )}
        </main>
      )}

      {/* ================================================================
         TEST CHAT MODAL
         ================================================================ */}
      {testChatAgent && (
        <div className="test-chat-overlay" onClick={closeTestChat}>
          <div className="test-chat-modal" onClick={(e) => e.stopPropagation()}>
            <div className="test-chat-modal__header">
              <div className="test-chat-modal__agent-info">
                <img
                  className="test-chat-modal__avatar"
                  src={`https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(testChatAgent.name)}`}
                  alt={testChatAgent.name}
                  width={40}
                  height={40}
                />
                <div>
                  <div className="test-chat-modal__name">{testChatAgent.name}</div>
                  <span className="mbti-badge mbti-badge--small">{testChatAgent.mbti_type}</span>
                </div>
              </div>
              <button className="test-chat-modal__close" onClick={closeTestChat}>X</button>
            </div>

            <div className="test-chat-modal__messages">
              {chatMessages.length === 0 && (
                <div className="test-chat-modal__empty">
                  Say hello to {testChatAgent.name} to test their personality.
                </div>
              )}
              {chatMessages.map((msg, i) => (
                <div key={i} className={`test-chat__bubble test-chat__bubble--${msg.role}`}>
                  {msg.content}
                </div>
              ))}
              {chatLoading && (
                <div className="test-chat__bubble test-chat__bubble--agent test-chat__bubble--loading">
                  Thinking...
                </div>
              )}
              <div ref={chatLogEndRef} />
            </div>

            <div className="test-chat-modal__input-bar">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTestMessage(); } }}
                placeholder={listening ? "Listening..." : "Type or speak a message..."}
                disabled={chatLoading || listening}
              />
              <button
                className={`btn-mic${listening ? " btn-mic--active" : ""}`}
                onClick={listening ? stopListening : startListening}
                disabled={chatLoading}
                type="button"
                title={listening ? "Stop listening" : "Speak"}
              >
                {listening ? "\u23F9" : "\uD83C\uDFA4"}
              </button>
              <button onClick={() => sendTestMessage()} disabled={chatLoading || !chatInput.trim()}>Send</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
