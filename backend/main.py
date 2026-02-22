from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.agent_factory import create_agents_from_user
from app.models import AddAgentsRequest, ChatRequest, ResetRequest, RunRequest, TopicRequest, TTSRequest
from app.simulation import run_round
from app.state import STORE

DEMO_FILE = Path(__file__).resolve().parent / "demo_agents.json"
ADMIN_KEY = os.environ.get("ADMIN_KEY")


async def verify_admin(request: Request) -> None:
    if ADMIN_KEY is None:
        return  # no key configured = no protection (local dev)
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)
        dead: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        if dead:
            async with self._lock:
                for connection in dead:
                    self._connections.discard(connection)


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
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    await websocket.send_json(
        {
            "type": "state",
            "state_snapshot": STORE.get_state().model_dump(),
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


@app.post("/topic", dependencies=[Depends(verify_admin)])
async def set_topic(payload: TopicRequest) -> dict:
    state = STORE.set_topic(payload.topic.strip())
    snapshot = state.model_dump()
    await manager.broadcast({"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/agents")
async def add_agents(payload: AddAgentsRequest) -> dict:
    state = STORE.get_state()
    current_users = [agent for agent in state.agents if agent.role == "user"]
    if len(current_users) + len(payload.user_agents) > 25:
        raise HTTPException(status_code=400, detail="Maximum 25 user agents allowed")

    created = create_agents_from_user(state.topic, payload.user_agents)
    updated = STORE.add_agents(created)
    snapshot = updated.model_dump()
    await manager.broadcast({"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


@app.post("/run", dependencies=[Depends(verify_admin)])
async def run(payload: RunRequest) -> dict:
    state = STORE.get_state()
    results = []

    async def broadcast_turn(turn: Any, round_number: int) -> None:
        await manager.broadcast({
            "type": "turn",
            "turn": turn.model_dump(),
            "round_number": round_number,
        })

    for _ in range(payload.rounds):
        try:
            result = await run_round(state, on_turn=broadcast_turn)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        STORE.save_round(result)

        event = {
            "type": "round",
            "round_result": result.model_dump(),
            "metrics": result.metrics,
            "state_snapshot": state.model_dump(),
        }
        await manager.broadcast(event)
        results.append(result.model_dump())

    return {
        "results": results,
        "state": state.model_dump(),
    }


@app.post("/reset", dependencies=[Depends(verify_admin)])
async def reset(payload: ResetRequest) -> dict:
    state = STORE.reset(payload.topic)
    snapshot = state.model_dump()
    await manager.broadcast({"type": "state", "state_snapshot": snapshot})
    return {"state": snapshot}


@app.post("/demo", dependencies=[Depends(verify_admin)])
async def load_demo() -> dict:
    if not DEMO_FILE.exists():
        raise HTTPException(status_code=404, detail="demo_agents.json not found")

    data = json.loads(DEMO_FILE.read_text())
    topic = data.get("topic", "Untitled classroom inquiry")
    agents_raw = data.get("agents", [])
    if not agents_raw:
        raise HTTPException(status_code=400, detail="No agents defined in demo file")

    state = STORE.reset(topic)
    created = create_agents_from_user(topic, agents_raw)
    state = STORE.add_agents(created)
    snapshot = state.model_dump()
    await manager.broadcast({"type": "state", "state_snapshot": snapshot})
    return {
        "added": [agent.model_dump() for agent in created],
        "state": snapshot,
    }


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
async def download_logs() -> JSONResponse:
    log = STORE.get_full_log()
    return JSONResponse(
        content=log,
        headers={
            "Content-Disposition": f'attachment; filename="session_{log["session_id"]}.json"',
        },
    )


@app.get("/state")
async def get_state() -> dict:
    return STORE.get_state().model_dump()
