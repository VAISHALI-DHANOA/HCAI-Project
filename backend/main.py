from __future__ import annotations

import asyncio
import json
import os
import secrets
from uuid import uuid4
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.agent_factory import create_agents_from_user
from app.dataset import dataset_preview
from app.chart_compute import clear_cache
from app.config import TTS_MODEL
from app.personality import get_personality_catalog
from app.moderator import MODERATOR_STRATEGIES
from app.models import AddAgentsRequest, ChatRequest, DisplayTimeRequest, EndSessionRequest, InterveneRequest, ModeratorStrategyRequest, ResetRequest, RunRequest, SyncAgentsRequest, TopicRequest, TTSRequest
from app.simulation import run_round
from app.state import SESSIONS, SessionBusyError, utc_now

DEMO_FILE = Path(__file__).resolve().parent / "demo_agents.json"
DEMO_DATA_FILE = Path(__file__).resolve().parent / "demo_data_analysts.json"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
ADMIN_KEY = os.environ.get("ADMIN_KEY")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"


def _client_filename(raw_filename: str) -> str:
    """Keep a display name only; never use a client path for storage."""
    filename = raw_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if (not filename or filename in {".", ".."} or len(filename) > 255
            or any(ord(character) < 32 for character in filename)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


def _new_upload_path(extension: str) -> Path:
    """Create an opaque path and assert that it remains under uploads/."""
    root = UPLOADS_DIR.resolve()
    candidate = (root / f"{uuid4().hex}.{extension}").resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    return candidate


async def verify_admin(request: Request) -> None:
    if ADMIN_KEY is None:
        return  # no key configured = no protection (local dev)
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")


def get_session_id(
    session: str | None = Query(None),
    request: Request = None,
) -> str:
    """Extract session ID from query param or X-Session-Id header."""
    sid = session or (request.headers.get("X-Session-Id") if request else None)
    if not sid or len(sid) > 64:
        raise HTTPException(status_code=400, detail="Missing or invalid session ID")
    return sid



async def exclusive_session(request: Request, session_id: str = Depends(get_session_id)):
    store = SESSIONS.get_store(session_id)
    try:
        with store.mutation():
            yield
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections.get(session_id, set()))
        dead: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        if dead:
            async with self._lock:
                session_set = self._connections.get(session_id, set())
                for connection in dead:
                    session_set.discard(connection)


app = FastAPI(title="Creative Multi-Agent Playground API", version="2.0.0")
manager = ConnectionManager()

# Like SESSIONS, lobby metadata lives in this single backend worker.
class Lobby(BaseModel):
    code: str
    mode: Literal["debate", "data"] | None = None


class ModeChoice(BaseModel):
    mode: Literal["debate", "data"]


lobbies: dict[str, tuple[Lobby, str]] = {}
ended_sessions: dict[str, dict[str, Any]] = {}
session_display_times: dict[str, int] = {}


@app.post("/sessions", status_code=201)
async def create_session() -> dict:
    lobby = Lobby(code=str(uuid4()))
    host_key = secrets.token_urlsafe(32)
    SESSIONS.get_store(lobby.code)
    lobbies[lobby.code] = (lobby, host_key)
    return {**lobby.model_dump(), "host_key": host_key}


@app.get("/sessions/{code}")
async def session_status(code: str) -> Lobby:
    if code not in lobbies:
        raise HTTPException(status_code=404, detail="Session not found. Check the code with your host.")
    return lobbies[code][0]


@app.put("/sessions/{code}/mode")
async def choose_session_mode(code: str, payload: ModeChoice, request: Request) -> Lobby:
    lobby = await session_status(code)
    if not secrets.compare_digest(request.headers.get("X-Host-Key", ""), lobbies[code][1]):
        raise HTTPException(status_code=403, detail="Only the host can choose the mode.")
    lobby.mode = payload.mode
    await manager.broadcast(code, {"type": "lobby", **lobby.model_dump()})
    return lobby

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session: str = Query(...)) -> None:
    store = SESSIONS.get_store(session)
    await manager.connect(websocket, session)
    try:
        if session in lobbies:
            await websocket.send_json({"type": "lobby", **lobbies[session][0].model_dump()})
        await websocket.send_json(
            {
                "type": "state",
                "state_snapshot": store.get_state().model_dump(),
            }
        )
        if session in ended_sessions:
            await websocket.send_json({"type": "session_ended", "summary": ended_sessions[session]})
        await websocket.send_json({
            "type": "playback_settings",
            "display_seconds": session_display_times.get(session, 12),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, session)
    except Exception:
        await manager.disconnect(websocket, session)


@app.post("/topic", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def set_topic(payload: TopicRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.set_topic(payload.topic.strip())
    SESSIONS.set_csv_path(session_id, None)
    store.record_configuration("/topic")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.get("/moderator-strategies")
async def list_moderator_strategies() -> dict:
    return {"strategies": [strategy.model_dump() for strategy in MODERATOR_STRATEGIES.values()]}


@app.get("/personality-presets")
async def list_personality_presets() -> dict:
    return get_personality_catalog()


@app.post("/moderator-strategy", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def set_moderator_strategy(
    payload: ModeratorStrategyRequest,
    session_id: str = Depends(get_session_id),
) -> dict:
    if payload.strategy_id not in MODERATOR_STRATEGIES:
        raise HTTPException(status_code=400, detail="Unknown moderator strategy")
    store = SESSIONS.get_store(session_id)
    state = store.set_moderator_strategy(payload.strategy_id)
    store.record_configuration("/moderator-strategy")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/agents", dependencies=[Depends(exclusive_session)])
async def add_agents(payload: AddAgentsRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.get_state()
    current_users = [agent for agent in state.agents if agent.role == "user"]
    if len(current_users) + len(payload.user_agents) > 25:
        raise HTTPException(status_code=400, detail="Maximum 25 user agents allowed")

    created = create_agents_from_user(state.topic, payload.user_agents)
    updated = store.add_agents(created)
    store.record_configuration("/agents")
    snapshot = updated.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


@app.post("/agents/sync", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def sync_agents(payload: SyncAgentsRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    try:
        state = store.sync_agents(payload.user_agents, payload.run_id, payload.revision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.record_configuration("/agents/sync")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/run", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def run(payload: RunRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    csv_path = SESSIONS.get_csv_path(session_id)
    results = []

    contribution_index = 0

    async def broadcast_turn(turn: Any, round_number: int) -> None:
        nonlocal contribution_index
        await manager.broadcast(session_id, {
            "type": "turn", "turn": turn.model_dump(), "round_number": round_number,
            "contribution_index": contribution_index,
            "run_id": store.get_state().run_id,
        })

        contribution_index += 1

    for _ in range(payload.rounds):
        contribution_index = 0
        working = store.begin_round()
        try:
            experiment = store.experiment_snapshot()
            experiment["started_at"] = utc_now()
            result = await run_round(working, on_turn=broadcast_turn, csv_path=csv_path)
            result.experiment = {
                **experiment, "completed_at": utc_now(),
                "human_request_at_end": working.human_request,
            }
            store.save_round(result, working_state=working)
        except BaseException as exc:
            store.abort_round(type(exc).__name__)
            await manager.broadcast(session_id, {
                "type": "state", "state_snapshot": store.get_state().model_dump(),
                "reset_playback": True,
            })
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if isinstance(exc, RuntimeError):
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            raise

        event = {
            "type": "round", "round_result": result.model_dump(),
            "state_snapshot": store.get_state().model_dump(),
        }
        await manager.broadcast(session_id, event)
        results.append(result.model_dump())

    return {"results": results, "state": store.get_state().model_dump()}


@app.post("/reset", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def reset(payload: ResetRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.reset(payload.topic, preserve_agents=True)
    ended_sessions.pop(session_id, None)
    session_display_times.pop(session_id, None)
    SESSIONS.set_csv_path(session_id, None)
    store.record_configuration("/reset")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/end", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def end_session(payload: EndSessionRequest, session_id: str = Depends(get_session_id)) -> dict:
    state = SESSIONS.get_store(session_id).get_state()
    summary = {
        "topic": state.topic,
        "rounds": len(state.rounds),
        "duration_seconds": payload.duration_seconds,
        "contributions": sum(len(round_result.turns) for round_result in state.rounds),
        "agents": len(state.agents),
    }
    ended_sessions[session_id] = summary
    await manager.broadcast(session_id, {"type": "session_ended", "summary": summary})
    return {"summary": summary}


@app.put("/playback-settings", dependencies=[Depends(verify_admin)])
async def set_playback_settings(payload: DisplayTimeRequest, session_id: str = Depends(get_session_id)) -> dict:
    session_display_times[session_id] = payload.seconds
    event = {"type": "playback_settings", "display_seconds": payload.seconds}
    await manager.broadcast(session_id, event)
    return event


@app.post("/intervene")
async def intervene(payload: InterveneRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    msg = payload.message.strip()
    turn = store.add_intervention(msg)
    state = store.get_state()
    await manager.broadcast(session_id, {
        "type": "turn",
        "turn": turn.model_dump(),
        "round_number": state.round_number,
        "run_id": state.run_id,
    })
    return {"state": state.model_dump()}


@app.post("/demo", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def load_demo(session_id: str = Depends(get_session_id)) -> dict:
    if not DEMO_FILE.exists():
        raise HTTPException(status_code=404, detail="demo_agents.json not found")

    data = json.loads(DEMO_FILE.read_text())
    topic = data.get("topic", "Untitled classroom inquiry")
    agents_raw = data.get("agents", [])
    if not agents_raw:
        raise HTTPException(status_code=400, detail="No agents defined in demo file")

    store = SESSIONS.get_store(session_id)
    state = store.reset(topic)
    SESSIONS.set_csv_path(session_id, None)
    created = create_agents_from_user(topic, agents_raw)
    store.record_configuration("/demo")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


@app.post("/upload-dataset", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def upload_dataset(file: UploadFile = File(...), session_id: str = Depends(get_session_id)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = _client_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")

    # Read at most one byte beyond the limit so oversized requests are not
    # buffered fully in application memory.
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    from app.dataset import parse_dataset, build_dataset_summary_text

    try:
        parsed = parse_dataset(contents, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    # Save uploaded file so chart_compute can read it for this session
    UPLOADS_DIR.mkdir(exist_ok=True)
    saved_path = _new_upload_path(ext)
    saved_path.write_bytes(contents)
    clear_cache(saved_path)
    SESSIONS.set_csv_path(session_id, saved_path)

    store = SESSIONS.get_store(session_id)
    summary_text = build_dataset_summary_text(parsed)
    state = store.set_dataset_summary(summary_text, filename)
    state.dataset_columns = [c["name"] for c in parsed["columns"]]
    state.dataset_preview = dataset_preview(parsed)
    state.world_state["dataset_row_count"] = parsed["shape"][0]
    store.set_dataset_identity(filename, contents)
    store.record_configuration("/upload-dataset")

    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})

    return {
        "parsed": {
            "filename": parsed["filename"],
            "shape": parsed["shape"],
            "columns": parsed["columns"],
            "sample_rows": parsed["sample_rows"],
        },
        "state": snapshot,
    }


@app.post("/demo-data", dependencies=[Depends(verify_admin), Depends(exclusive_session)])
async def load_data_demo(session_id: str = Depends(get_session_id)) -> dict:
    if not DEMO_DATA_FILE.exists():
        raise HTTPException(status_code=404, detail="demo_data_analysts.json not found")

    data = json.loads(DEMO_DATA_FILE.read_text())
    topic = data.get("topic", "Untitled data analysis")
    dataset_summary = data.get("dataset_summary", "")
    agents_raw = data.get("agents", [])
    if not agents_raw:
        raise HTTPException(status_code=400, detail="No agents defined in demo file")

    # Load actual CSV to get all rows
    from app.dataset import parse_dataset
    csv_path = Path(__file__).resolve().parent / "ExampleDataset.csv"
    if csv_path.exists():
        parsed_data = parse_dataset(csv_path.read_bytes(), csv_path.name)
        SESSIONS.set_csv_path(session_id, csv_path)
    else:
        SESSIONS.set_csv_path(session_id, None)
        parsed_data = data.get("parsed_data", None)

    store = SESSIONS.get_store(session_id)
    state = store.reset(topic)
    if csv_path.exists():
        store.set_dataset_identity(csv_path.name, csv_path.read_bytes())
    if dataset_summary:
        state.dataset_summary = dataset_summary
    if parsed_data:
        state.dataset_columns = [c["name"] for c in parsed_data["columns"]]
        state.dataset_preview = dataset_preview(parsed_data)
        state.world_state["dataset_row_count"] = parsed_data["shape"][0]
    created = create_agents_from_user(topic, agents_raw)
    state = store.add_agents(created)
    store.record_configuration("/demo-data")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    response: dict = {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }
    if parsed_data:
        response["parsed"] = {
            "filename": parsed_data["filename"],
            "shape": parsed_data["shape"],
            "columns": parsed_data["columns"],
            "sample_rows": parsed_data["sample_rows"],
        }
    return response


@app.get("/examples")
async def list_examples() -> dict:
    """List available example datasets in the examples/ folder."""
    if not EXAMPLES_DIR.is_dir():
        return {"examples": []}
    json_stems: dict[str, str] = {}
    csv_stems: set[str] = set()
    for f in sorted(EXAMPLES_DIR.iterdir()):
        if f.suffix.lower() == ".json":
            json_stems[f.stem.lower()] = f.stem
        elif f.suffix.lower() == ".csv":
            csv_stems.add(f.stem.lower())
    examples = [
        {"name": stem} for key, stem in sorted(json_stems.items()) if key in csv_stems
    ]
    return {"examples": examples}


@app.post("/load-example", dependencies=[Depends(exclusive_session)])
async def load_example(name: str, session_id: str = Depends(get_session_id)) -> dict:
    """Load an example dataset + agents by name (e.g. ExampleDataset1)."""
    if not EXAMPLES_DIR.is_dir():
        raise HTTPException(status_code=404, detail="examples/ directory not found")

    # Case-insensitive lookup: scan directory for matching JSON+CSV pair
    name_lower = name.lower()
    json_path: Path | None = None
    csv_path: Path | None = None
    for f in EXAMPLES_DIR.iterdir():
        if f.suffix.lower() == ".json" and f.stem.lower() == name_lower:
            json_path = f
        elif f.suffix.lower() == ".csv" and f.stem.lower() == name_lower:
            csv_path = f

    if json_path is None:
        raise HTTPException(status_code=404, detail=f"Example '{name}' not found")
    if csv_path is None:
        raise HTTPException(status_code=404, detail=f"CSV for example '{name}' not found")

    data = json.loads(json_path.read_text())
    topic = data.get("topic", "Untitled data analysis")
    dataset_summary = data.get("dataset_summary", "")
    agents_raw = data.get("agents", [])
    if not agents_raw:
        raise HTTPException(status_code=400, detail="No agents defined in example file")

    # Parse CSV to get columns, sample rows, and row count
    from app.dataset import parse_dataset
    parsed_data = parse_dataset(csv_path.read_bytes(), csv_path.name)

    # Store per-session CSV path for chart_compute
    SESSIONS.set_csv_path(session_id, csv_path)

    store = SESSIONS.get_store(session_id)
    state = store.reset(topic)
    store.set_dataset_identity(csv_path.name, csv_path.read_bytes())
    if dataset_summary:
        state.dataset_summary = dataset_summary
    state.dataset_columns = [c["name"] for c in parsed_data["columns"]]
    state.dataset_preview = dataset_preview(parsed_data)
    state.world_state["dataset_row_count"] = parsed_data["shape"][0]
    created = create_agents_from_user(topic, agents_raw)
    state = store.add_agents(created)
    store.record_configuration("/load-example")
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    response: dict = {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }
    response["parsed"] = {
        "filename": parsed_data["filename"],
        "shape": parsed_data["shape"],
        "columns": parsed_data["columns"],
        "sample_rows": parsed_data["sample_rows"],
    }
    return response


@app.post("/chat")
async def test_chat(payload: ChatRequest) -> dict:
    from app.llm import generate_test_chat_message

    reply = await generate_test_chat_message(
        agent_name=payload.agent_name,
        agent_persona=payload.agent_persona,
        personality=payload.personality,
        messages=payload.messages,
        user_message=payload.user_message,
    )
    return {"reply": reply.text, "generation": reply.generation.model_dump()}


@app.post("/tts")
async def text_to_speech(payload: TTSRequest) -> Response:
    import os

    from openai import AsyncOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")
    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.audio.speech.create(
            model=TTS_MODEL,
            voice=payload.voice,
            input=payload.text,
        )
        return Response(content=response.content, media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/logs/download")
async def download_logs(session_id: str = Depends(get_session_id)) -> JSONResponse:
    store = SESSIONS.get_store(session_id)
    log = store.get_full_log()
    return JSONResponse(
        content=log,
        headers={
            "Content-Disposition": f'attachment; filename="session_{log["session_id"]}.json"',
        },
    )


@app.get("/state")
async def get_state(session_id: str = Depends(get_session_id)) -> dict:
    return SESSIONS.get_store(session_id).get_state().model_dump()
