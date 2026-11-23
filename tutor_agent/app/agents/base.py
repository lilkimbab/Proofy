from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.common import AgentContext, AgentRequest, AgentResponse, AgentTrace, GuardResult


class BaseAgent:
    name = "base"
    version = "1.0.0"

    async def run(self, request: AgentRequest) -> AgentResponse:
        trace = self.create_trace(request)
        try:
            self.add_step(trace, "normalize_input")
            normalized = await self.normalize_input(request, trace)

            self.add_step(trace, "check_preconditions")
            guard = await self.check_preconditions(normalized, trace)
            if not guard.allowed:
                return self.blocked_response(guard, trace)

            self.add_step(trace, "build_context")
            context = await self.build_context(normalized, trace)

            self.add_step(trace, "create_plan")
            plan = await self.create_plan(normalized, context, trace)

            self.add_step(trace, "generate")
            draft = await self.generate(normalized, context, plan, trace)

            self.add_step(trace, "postprocess")
            output = await self.postprocess(draft, normalized, context, plan, trace)
            trace.finished_at = self.now()
            output.trace = trace
            return output
        except Exception as error:
            trace.error = str(error)
            trace.finished_at = self.now()
            return AgentResponse(
                ok=False,
                agent_type=self.name,
                mode=f"{self.name}-error",
                answer="요청을 처리하는 중 문제가 발생했습니다.",
                trace=trace,
            )

    def create_trace(self, request: AgentRequest) -> AgentTrace:
        return AgentTrace(request_id=request.request_id, agent=self.name, version=self.version)

    def add_step(self, trace: AgentTrace, step: str) -> None:
        trace.steps.append(step)

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def normalize_input(self, request: AgentRequest, trace: AgentTrace) -> AgentRequest:
        return request

    async def check_preconditions(self, request: AgentRequest, trace: AgentTrace) -> GuardResult:
        return GuardResult(allowed=True, reason="allowed")

    async def build_context(self, request: AgentRequest, trace: AgentTrace) -> AgentContext:
        return AgentContext()

    async def create_plan(self, request: AgentRequest, context: AgentContext, trace: AgentTrace) -> dict[str, Any]:
        return {}

    async def generate(
        self,
        request: AgentRequest,
        context: AgentContext,
        plan: dict[str, Any],
        trace: AgentTrace,
    ) -> dict[str, Any]:
        return {}

    async def postprocess(
        self,
        draft: dict[str, Any],
        request: AgentRequest,
        context: AgentContext,
        plan: dict[str, Any],
        trace: AgentTrace,
    ) -> AgentResponse:
        return AgentResponse(
            ok=True,
            agent_type=self.name,
            mode=f"{self.name}-success",
            answer=draft.get("answer", ""),
            data=draft.get("data", {}),
            sources=context.sources,
            trace=trace,
        )

    def blocked_response(self, guard: GuardResult, trace: AgentTrace) -> AgentResponse:
        trace.finished_at = self.now()
        return AgentResponse(
            ok=False,
            agent_type=self.name,
            mode=f"{self.name}-blocked-{guard.reason}",
            answer=guard.message,
            guard=guard,
            trace=trace,
        )

