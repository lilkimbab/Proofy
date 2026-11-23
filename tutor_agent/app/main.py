from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.agents.tutor_agent import TutorAgent
from app.schemas.common import AgentRequest, AgentResponse


app = FastAPI(
    title="Tutor Agent",
    description="Document-grounded FastAPI tutor agent.",
    version="0.1.0",
)

agent_registry = {
    "tutor": TutorAgent(),
}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agents/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest) -> AgentResponse:
    agent = agent_registry.get(request.agent_type)
    if not agent:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {request.agent_type}")
    return await agent.run(request)


@app.post("/agents/tutor", response_model=AgentResponse)
async def run_tutor_agent(request: AgentRequest) -> AgentResponse:
    normalized = request.model_copy(update={"agent_type": "tutor"})
    return await agent_registry["tutor"].run(normalized)

