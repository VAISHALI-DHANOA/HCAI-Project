from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.agent_factory import create_agents_from_user
from app.models import AddAgentsRequest, RoundRequest
from app.simulation import run_round
from app.state import STORE

app = FastAPI(title="Creative Multi-Agent Playground", version="1.0.0")


@app.post("/agents")
def add_agents(payload: AddAgentsRequest) -> dict:
    topic = payload.topic or "Untitled classroom inquiry"
    current_state = STORE.ensure_state(topic)
    if len([a for a in current_state.agents if a.role == "user"]) + len(payload.user_agents) > 25:
        raise HTTPException(status_code=400, detail="Maximum 25 user agents allowed")
    created = create_agents_from_user(current_state.topic, payload.user_agents)
    state = STORE.add_agents(current_state.topic, created)
    return {
        "added": [agent.model_dump() for agent in created],
        "total_agents": len(state.agents),
        "topic": state.topic,
    }


@app.post("/round")
def post_round(payload: RoundRequest) -> dict:
    try:
        state = STORE.get_state()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    results = []
    try:
        for _ in range(payload.rounds):
            results.append(run_round(state).model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results, "state": state.model_dump()}


@app.get("/state")
def get_state() -> dict:
    try:
        state = STORE.get_state()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return state.model_dump()

