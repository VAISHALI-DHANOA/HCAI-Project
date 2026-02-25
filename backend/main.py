from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.agent_factory import create_agents_from_user
from app.models import AddAgentsRequest, ChatRequest, InterveneRequest, ResetRequest, RunRequest, TopicRequest, TTSRequest
from app.models import PublicTurn
from app.simulation import run_round
from app.state import SESSIONS

DEMO_FILE = Path(__file__).resolve().parent / "demo_agents.json"
DEMO_DATA_FILE = Path(__file__).resolve().parent / "demo_data_analysts.json"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
ADMIN_KEY = os.environ.get("ADMIN_KEY")


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

_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra_origin = os.environ.get("CORS_ORIGIN")
if _extra_origin:
    _cors_origins.append(_extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session: str = Query(...)) -> None:
    store = SESSIONS.get_store(session)
    await manager.connect(websocket, session)
    try:
        await websocket.send_json(
            {
                "type": "state",
                "state_snapshot": store.get_state().model_dump(),
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, session)
    except Exception:
        await manager.disconnect(websocket, session)


@app.post("/topic", dependencies=[Depends(verify_admin)])
async def set_topic(payload: TopicRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.set_topic(payload.topic.strip())
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/agents")
async def add_agents(payload: AddAgentsRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.get_state()
    current_users = [agent for agent in state.agents if agent.role == "user"]
    if len(current_users) + len(payload.user_agents) > 25:
        raise HTTPException(status_code=400, detail="Maximum 25 user agents allowed")

    created = create_agents_from_user(state.topic, payload.user_agents)
    updated = store.add_agents(created)
    snapshot = updated.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


@app.post("/run", dependencies=[Depends(verify_admin)])
async def run(payload: RunRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.get_state()
    csv_path = SESSIONS.get_csv_path(session_id)
    results = []

    async def broadcast_turn(turn: Any, round_number: int) -> None:
        await manager.broadcast(session_id, {
            "type": "turn",
            "turn": turn.model_dump(),
            "round_number": round_number,
        })

    for _ in range(payload.rounds):
        try:
            result = await run_round(state, on_turn=broadcast_turn, csv_path=csv_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        store.save_round(result)

        event = {
            "type": "round",
            "round_result": result.model_dump(),
            "metrics": result.metrics,
            "state_snapshot": state.model_dump(),
        }
        await manager.broadcast(session_id, event)
        results.append(result.model_dump())

    return {
        "results": results,
        "state": state.model_dump(),
    }


@app.post("/reset", dependencies=[Depends(verify_admin)])
async def reset(payload: ResetRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.reset(payload.topic)
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/intervene")
async def intervene(payload: InterveneRequest, session_id: str = Depends(get_session_id)) -> dict:
    store = SESSIONS.get_store(session_id)
    state = store.get_state()
    msg = payload.message.strip()
    turn = PublicTurn(speaker_id="human", message=msg)
    state.public_history.append(turn)
    state.human_request = msg
    await manager.broadcast(session_id, {
        "type": "turn",
        "turn": turn.model_dump(),
        "round_number": state.round_number,
    })
    return {"state": state.model_dump()}


@app.post("/demo", dependencies=[Depends(verify_admin)])
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
    created = create_agents_from_user(topic, agents_raw)
    state = store.add_agents(created)
    snapshot = state.model_dump()
    await manager.broadcast(session_id, {"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


@app.post("/upload-dataset", dependencies=[Depends(verify_admin)])
async def upload_dataset(file: UploadFile = File(...), session_id: str = Depends(get_session_id)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    from app.dataset import parse_dataset, build_dataset_summary_text

    try:
        parsed = parse_dataset(contents, file.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    # Save uploaded file so chart_compute can read it for this session
    upload_dir = Path(__file__).resolve().parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    saved_path = upload_dir / f"{session_id}_{file.filename}"
    saved_path.write_bytes(contents)
    SESSIONS.set_csv_path(session_id, saved_path)

    store = SESSIONS.get_store(session_id)
    summary_text = build_dataset_summary_text(parsed)
    state = store.set_dataset_summary(summary_text, file.filename)
    state.dataset_columns = [c["name"] for c in parsed["columns"]]
    state.world_state["dataset_row_count"] = parsed["shape"][0]

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


@app.post("/demo-data", dependencies=[Depends(verify_admin)])
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
        parsed_data = data.get("parsed_data", None)

    store = SESSIONS.get_store(session_id)
    state = store.reset(topic)
    if dataset_summary:
        state.dataset_summary = dataset_summary
    if parsed_data:
        state.dataset_columns = [c["name"] for c in parsed_data["columns"]]
        state.world_state["dataset_row_count"] = parsed_data["shape"][0]
    created = create_agents_from_user(topic, agents_raw)
    state = store.add_agents(created)
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


@app.post("/load-example")
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
    if dataset_summary:
        state.dataset_summary = dataset_summary
    state.dataset_columns = [c["name"] for c in parsed_data["columns"]]
    state.world_state["dataset_row_count"] = parsed_data["shape"][0]
    created = create_agents_from_user(topic, agents_raw)
    state = store.add_agents(created)
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
        mbti_type=payload.mbti_type,
        messages=payload.messages,
        user_message=payload.user_message,
    )
    return {"reply": reply}


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
            model="tts-1",
            voice=payload.voice,
            input=payload.text,
        )
        return Response(content=response.content, media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/logs/download", dependencies=[Depends(verify_admin)])
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
